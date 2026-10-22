"""Bounded research-only static publication v2; no raw feeds or qualified rows.

Publication time is distinct from each sport's generation/capture clocks.
Content-addressed assets are written before the manifest commit point. A failed
sport retains its last validated bytes and generation time, or stays unavailable.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile

from .integrity import IntegrityError, canonical, digest, load_json, stamp, utc

SCHEMA_VERSION = 2
MAX_ASSET_BYTES = 512 * 1024
COLLECTIONS = ("events", "offers", "forecasts", "candidates", "tickets", "performance")
MARKETS = ("PTS", "PRA", "REB", "3PM", "AST", "RA", "PR", "TOV", "TD", "DD", "BLK", "STL", "BLK+STL")


def resolve_scope(mode: str, selected: list[str], supported: list[str]) -> frozenset[str]:
    """Same set contract as web scope: no silent expansion or unsupported sport."""
    if (not supported or len(set(supported)) != len(supported)
            or any(not isinstance(x, str) or not re.fullmatch(r"[A-Z]+", x) for x in supported)
            or not isinstance(selected, list) or len(set(selected)) != len(selected)
            or not set(selected) <= set(supported)):
        raise ValueError("Invalid or unsupported sport scope")
    if mode == "ALL" and not selected:
        return frozenset(supported)
    if mode == "SINGLE" and len(selected) == 1:
        return frozenset(selected)
    if mode == "SELECTED" and selected:
        return frozenset(selected)
    raise ValueError("SINGLE requires one; SELECTED a nonempty subset; ALL no explicit list")


def _text(value, name):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise IntegrityError(f"Invalid {name}")


def validate_sport(snapshot: dict, *, league: str, now: datetime) -> None:
    """Fail closed: v1 has a full category catalog but no typed observation rows."""
    if type(snapshot) is dict and type(snapshot.get("schema_version")) is int and snapshot["schema_version"] == 2:
        _validate_research_sport(snapshot, league=league, now=now)
        return
    fields = {"schema_version", "league", "generated_at", "evidence_lane", "status",
              "coverage", "markets", "sources", *COLLECTIONS}
    if type(snapshot) is not dict or set(snapshot) != fields:
        raise IntegrityError("Unknown sport schema fields")
    if (type(snapshot["schema_version"]) is not int or snapshot["schema_version"] != 1
            or snapshot["league"] != league or not re.fullmatch(r"[A-Z]+", league)
            or snapshot["status"] != "RESEARCH_ONLY"
            or snapshot["evidence_lane"] != "RECONSTRUCTED_RESEARCH"):
        raise IntegrityError("Unsupported sport schema or evidence status")
    generated = utc(snapshot["generated_at"])
    if generated > utc(now):
        raise IntegrityError("Sport generation clock is in the future")
    if snapshot["coverage"] != {"forecast": "UNVALIDATED", "quotes": "UNVERIFIED",
                               "settlement": "UNVERIFIED", "paper": "NO_ACTION"}:
        raise IntegrityError("Unsupported coverage claim")
    codes = set()
    if type(snapshot["markets"]) is not list:
        raise IntegrityError("Market catalog must be a list")
    for market in snapshot["markets"]:
        if type(market) is not dict or set(market) != {"code", "name", "requested", "forecast_status", "quote_status", "settlement_status"}:
            raise IntegrityError("Invalid market catalog")
        _text(market["code"], "market code")
        _text(market["name"], "market name")
        if (market["code"] in codes or type(market["requested"]) is not bool
                or market["forecast_status"] != "UNVALIDATED"
                or market["quote_status"] != "UNVERIFIED"
                or market["settlement_status"] != "UNVERIFIED"):
            raise IntegrityError("Duplicate market or unsupported admission claim")
        codes.add(market["code"])
    if league == "NBA" and ({m["code"] for m in snapshot["markets"] if m["requested"]} != set(MARKETS)
                            or not codes <= {*MARKETS, "PA"}):
        raise IntegrityError("NBA requires exactly all 13 requested markets plus optional PA")
    if type(snapshot["sources"]) is not list:
        raise IntegrityError("Sources must be a list")
    source_ids = set()
    for source in snapshot["sources"]:
        if type(source) is not dict or set(source) != {"id", "name", "status", "detail", "observed_at"}:
            raise IntegrityError("Invalid source catalog")
        for field in ("id", "name", "status", "detail"):
            _text(source[field], field)
        if source["id"] in source_ids:
            raise IntegrityError("Duplicate source identity")
        source_ids.add(source["id"])
        if source["observed_at"] is not None and utc(source["observed_at"]) > generated:
            raise IntegrityError("Source capture clock is after sport generation")
    for field in COLLECTIONS:
        if snapshot[field] != []:
            raise IntegrityError(f"Nonempty {field} needs a future typed export schema")
    if len(canonical(snapshot)) > MAX_ASSET_BYTES:
        raise IntegrityError("Sport asset exceeds byte budget")


def _validate_research_sport(snapshot: dict, *, league: str, now: datetime) -> None:
    from .forecast_contract import validate_forecast, validate_event
    from .ledger import validate_grade
    expected = {"schema_version", "league", "generated_at", "evidence_lane", "status",
                "coverage", "markets", "sources", "future_availability", *COLLECTIONS}
    if set(snapshot) != expected or league != "NBA":
        raise IntegrityError("Unsupported typed sport schema")
    # Reuse exact catalog/admission checks; v1 remains loadable for retained assets.
    catalog = {k: v for k, v in snapshot.items() if k != "future_availability"}
    if snapshot["evidence_lane"] not in {"RECONSTRUCTED_RESEARCH", "RESEARCH_COLLECTION"}:
        raise IntegrityError("Unsupported research collection evidence label")
    catalog.update(schema_version=1, evidence_lane="RECONSTRUCTED_RESEARCH",
                   **{field: [] for field in COLLECTIONS})
    validate_sport(catalog, league=league, now=now)
    generated = utc(snapshot["generated_at"])
    for field in COLLECTIONS:
        if type(snapshot[field]) is not list:
            raise IntegrityError("Typed collections must be lists")
    if any(snapshot[field] for field in ("offers", "candidates", "tickets")):
        raise IntegrityError("Research forecasts do not admit offers or tickets")
    if len(snapshot["forecasts"]) > 32 or len(snapshot["events"]) > 32 or len(snapshot["performance"]) > 64:
        raise IntegrityError("Typed research collection exceeds its budget")
    events = {}
    for event in snapshot["events"]:
        validate_event(event)
        if event["event_id"] in events:
            raise IntegrityError("Duplicate event identity")
        events[event["event_id"]] = event
    forecasts = {}
    identities = set()
    for bundle in snapshot["forecasts"]:
        validate_forecast(bundle, now=generated)
        key = (bundle["event_id"], bundle["player_id"], bundle["model_version"], bundle["cutoff_at"])
        if bundle["forecast_id"] in forecasts or key in identities:
            raise IntegrityError("Duplicate forecast identity or original issue revision")
        identities.add(key)
        event = events.get(bundle["event_id"])
        if (event is None or event["starts_at"] != bundle["event_starts_at"]
                or set(event["team_ids"]) != {bundle["team_id"], bundle["opponent_id"]}
                or (bundle["evidence_lane"] == "RECONSTRUCTED_RESEARCH" and event["status"] != "FINAL")
                or (bundle["evidence_lane"] == "REAL_TIME_CAPTURED" and event["status"] != "SCHEDULED")):
            raise IntegrityError("Forecast/event identity, version or status mismatch")
        forecasts[bundle["forecast_id"]] = bundle
    expected_lane = ("RESEARCH_COLLECTION" if any(bundle["evidence_lane"] == "REAL_TIME_CAPTURED"
                     for bundle in forecasts.values()) else "RECONSTRUCTED_RESEARCH")
    if snapshot["evidence_lane"] != expected_lane:
        raise IntegrityError("Collection evidence label must retain individual forecast lanes")
    grades = set()
    for grade in snapshot["performance"]:
        forecast = forecasts.get(grade.get("forecast_id")) if type(grade) is dict else None
        if forecast is None:
            raise IntegrityError("Grade references an unpublished forecast")
        validate_grade(grade, forecast=forecast)
        if grade["grade_id"] in grades or utc(grade["graded_at"]) > generated:
            raise IntegrityError("Duplicate grade or future grading clock")
        grades.add(grade["grade_id"])
    availability = snapshot["future_availability"]
    if (type(availability) is not dict or set(availability) != {"status", "reasons"}
            or availability["status"] not in {"AVAILABLE", "UNAVAILABLE"}
            or type(availability["reasons"]) is not list
            or any(type(reason) is not str or not reason.strip() for reason in availability["reasons"])):
        raise IntegrityError("Invalid future coverage explanation")
    has_future = any(bundle["evidence_lane"] == "REAL_TIME_CAPTURED"
                     and utc(bundle["event_starts_at"]) > generated for bundle in forecasts.values())
    if ((availability["status"] == "AVAILABLE") != has_future
            or (not has_future and not availability["reasons"])):
        raise IntegrityError("Future coverage status must match genuine available issuance")
    if len(canonical(snapshot)) > MAX_ASSET_BYTES:
        raise IntegrityError("Sport asset exceeds byte budget")


def empty_nba(root: Path, *, now: datetime) -> dict:
    registry = load_json(root / "config/nba_markets.json")
    caps = load_json(root / "config/capabilities.json")
    result = {"schema_version": 1, "league": "NBA", "generated_at": stamp(now),
              "evidence_lane": "RECONSTRUCTED_RESEARCH", "status": "RESEARCH_ONLY",
              "coverage": {"forecast": "UNVALIDATED", "quotes": "UNVERIFIED",
                           "settlement": "UNVERIFIED", "paper": "NO_ACTION"},
              "markets": [{"code": m["code"], "name": m["name"], "requested": m["requested"],
                           "forecast_status": "UNVALIDATED", "quote_status": "UNVERIFIED",
                           "settlement_status": "UNVERIFIED"} for m in registry["markets"]],
              "sources": [{"id": source_id, "name": caps["sources"][source_id]["name"],
                           "status": caps["sources"][source_id]["evidence_level"],
                           "detail": "Limited source evidence; automation, historical availability and public raw redistribution remain unadmitted.",
                           "observed_at": None} for source_id in caps["sports"]["NBA"]["source_ids"]],
              **{field: [] for field in COLLECTIONS}}
    result["sources"].extend([
        {"id": "espn_draftkings_player_props", "name": "ESPN Draft Kings-labelled NBA offers",
         "status": caps["live_feed_candidates"]["espn_draftkings_player_props"]["status"],
         "detail": "Bounded NBA audit: 1,135 items across both declared pages; 12 requested families plus PA and price fields observed. TOV absent this event. Side, full-game/OT and settlement unresolved; 138 future source-update clocks; zero complete quotes. Ongoing access permission unestablished.",
         "observed_at": None},
        {"id": "sleeper_picks", "name": "Sleeper NBA Picks observations",
         "status": caps["live_feed_candidates"]["sleeper_picks"]["status"],
         "detail": "Latest bounded capture: 675 NBA rows / 1,350 options across nine families, with matching player subject types. RA, PR, TD and BLK+STL absent this snapshot. Multipliers are not sportsbook odds; paging, full-game/OT and entry terms unresolved; live adapter disabled.",
         "observed_at": None},
    ])
    for source in result["sources"]:
        observed = caps["live_feed_candidates"].get(source["id"], {}).get("last_observed_at")
        if observed is not None and utc(observed) <= utc(now):
            source["observed_at"] = stamp(utc(observed))
    validate_sport(result, league="NBA", now=now)
    return result


def research_nba(root: Path, *, now: datetime) -> dict:
    """Read the durable repository ledger; build never regenerates forecasts."""
    from .publication_ledger import CompositeEnvelopeLedger
    from .forecast_contract import EVENT_SCHEMA
    result = empty_nba(root, now=now)
    result["schema_version"] = 2
    # The versioned facade validates the new shared-input kinds while inherited
    # legacy iterators continue to expose only unchanged historical/R1 bundles.
    # New PROS004 records have a separate paginated public contract below.
    ledger = CompositeEnvelopeLedger(root)
    # Recovery checks every checksum and reference before anything is published.
    ledger.scan()
    result["forecasts"] = list(ledger.iter_active_forecasts())
    result["performance"] = list(ledger.iter_active_grades())
    events = {}
    for bundle in result["forecasts"]:
        event = {"schema_version": EVENT_SCHEMA, "id_namespace": bundle["id_namespace"], "league": "NBA",
                 "event_id": bundle["event_id"], "starts_at": bundle["event_starts_at"],
                 "status": "FINAL" if bundle["evidence_lane"] == "RECONSTRUCTED_RESEARCH" else "SCHEDULED",
                 "team_ids": sorted([bundle["team_id"], bundle["opponent_id"]]),
                 "label": f"ESPN event {bundle['event_id']}",
                 "schedule_basis": "RETROSPECTIVE_ARCHIVE" if bundle["evidence_lane"] == "RECONSTRUCTED_RESEARCH" else "OBSERVED_CAPTURE"}
        if bundle["event_id"] in events and events[bundle["event_id"]] != event:
            raise IntegrityError("Conflicting retained event identities")
        events[bundle["event_id"]] = event
    result["events"] = list(events.values())
    has_future = any(bundle["evidence_lane"] == "REAL_TIME_CAPTURED" and utc(bundle["event_starts_at"]) > utc(now)
                     for bundle in result["forecasts"])
    has_captured = any(bundle["evidence_lane"] == "REAL_TIME_CAPTURED" for bundle in result["forecasts"])
    result["evidence_lane"] = "RESEARCH_COLLECTION" if has_captured else "RECONSTRUCTED_RESEARCH"
    reasons = (["No captured forecast remains upcoming at the publication clock. Past-event records are retained in History; an event starting does not establish a completed outcome."]
               if has_captured else [
                   "No timely event/player input capture has been admitted for an upcoming issuance.",
                   "Archive start+24h availability bounds support reconstruction only; they do not establish real-time input availability.",
                   "No genuinely pregame T-90 issuance has been captured for upcoming games. Historical reconstructions are available in History."])
    result["future_availability"] = {"status": "AVAILABLE" if has_future else "UNAVAILABLE", "reasons": [] if has_future else reasons}
    validate_sport(result, league="NBA", now=now)
    return result


def _write_atomic(path: Path, raw: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".publish-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


LEGACY_CHANNELS = ("pros004", "display", "offers", "paired_research")
DAILY_CHANNELS = (*LEGACY_CHANNELS, "daily_research")
AUXILIARY_CHANNELS = (*DAILY_CHANNELS, "production_research")
REJECTED_UPDATE = (ValueError, KeyError, TypeError, OSError, ImportError)


def _channel_names(version: int) -> tuple[str, ...]:
    if type(version) is not int:
        return ()
    return {3: ("pros004",), 4: ("display",), 5: LEGACY_CHANNELS, 6: DAILY_CHANNELS,
            7: AUXILIARY_CHANNELS}.get(version, ())


def _read_channel(data_dir: Path, channel: str, descriptor: dict, snapshots: list[dict], *, now: datetime,
                  allow_production_development: bool = False):
    """Each independent channel validates its own paths before opening any asset."""
    if channel == "pros004":
        from .pros004_publication import read_publication
        return read_publication(data_dir, descriptor, now=now)
    if channel == "display":
        from .display_metadata import read_asset
        return read_asset(data_dir, descriptor, snapshots, now=now)
    if channel == "offers":
        from .offer_publication import read_asset
        return read_asset(data_dir, descriptor, now=now)
    if channel == "paired_research":
        from .operational_publication import read_asset
        return read_asset(data_dir, descriptor, now=now)
    if channel == "daily_research":
        from .sdv_daily_publication import read_asset
        return read_asset(data_dir, descriptor, now=now)
    if channel == "production_research":
        from .sdv_production_publication import read_publication
        return read_publication(data_dir, descriptor, now=now,
                                allow_development=allow_production_development)
    raise IntegrityError("Unsupported publication channel")


def read_manifest(data_dir: Path, *, now: datetime, validate_display: bool = True,
                  validate_auxiliary: bool = True, allow_production_development: bool = False) -> dict:
    """Read legacy manifests exactly; v7 adds independent production research.

    Builders can recover the verified core before separately inspecting optional
    channels. Public artifact verification uses the strict default.
    """
    manifest = load_json(data_dir / "manifest.json", max_bytes=MAX_ASSET_BYTES)
    version = manifest.get("schema_version") if type(manifest) is dict else None
    fields = {"schema_version", "snapshot_id", "build_commit", "published_at", "publication_status", "supported_sports", "sports", "errors"}
    fields |= {field for channel in _channel_names(version) for field in (channel, channel + "_error")}
    if (type(manifest) is not dict or set(manifest) != fields
            or type(version) is not int or version not in {1, 2, 3, 4, 5, 6, 7}
            or manifest["publication_status"] != "RESEARCH_ONLY"
            or not re.fullmatch(r"[a-f0-9]{40}", manifest["build_commit"])
            or utc(manifest["published_at"]) > utc(now)):
        raise IntegrityError("Invalid publication manifest")
    if manifest["snapshot_id"] != digest({k: v for k, v in manifest.items() if k != "snapshot_id"}):
        raise IntegrityError("Manifest checksum mismatch")
    if (type(manifest["sports"]) is not list or not manifest["sports"]
            or type(manifest["supported_sports"]) is not list
            or type(manifest["errors"]) is not dict):
        raise IntegrityError("Invalid publication collections")
    for league, error in manifest["errors"].items():
        if not isinstance(league, str) or not re.fullmatch(r"[A-Z]+", league):
            raise IntegrityError("Invalid publication error league")
        _text(error, "publication error")
    seen, snapshots = set(), []
    for entry in manifest["sports"]:
        if type(entry) is not dict or set(entry) != {"league", "path", "sha256", "generated_at", "status", "retained", "error"}:
            raise IntegrityError("Invalid manifest sport entry")
        league = entry["league"]
        if not isinstance(league, str) or league in seen or not re.fullmatch(r"[A-Z]+", league):
            raise IntegrityError("Duplicate/invalid league")
        seen.add(league)
        if (not isinstance(entry["sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"])
                or entry["path"] != f"{league.lower()}.{entry['sha256']}.json"
                or type(entry["retained"]) is not bool or entry["status"] != "RESEARCH_ONLY"):
            raise IntegrityError("Invalid sport path/hash/status")
        if entry["error"] is not None:
            _text(entry["error"], "sport publication error")
        snapshot = load_json(data_dir / entry["path"], max_bytes=MAX_ASSET_BYTES)
        if hashlib.sha256((data_dir / entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
            raise IntegrityError("Sport asset checksum mismatch")
        validate_sport(snapshot, league=league, now=utc(manifest["published_at"]))
        if snapshot["generated_at"] != entry["generated_at"]:
            raise IntegrityError("Generation clock mismatch")
        snapshots.append(snapshot)
    if sorted(seen) != manifest["supported_sports"]:
        raise IntegrityError("Sport references do not match supported scope")
    for channel in _channel_names(version):
        if not validate_auxiliary or channel == "display" and not validate_display:
            continue
        error, descriptor = manifest[channel + "_error"], manifest[channel]
        if error is not None:
            _text(error, channel + " publication error")
        if descriptor is None:
            if error is None:
                raise IntegrityError("Missing publication channel requires an explanation")
        else:
            _read_channel(data_dir, channel, descriptor, snapshots, now=utc(manifest["published_at"]),
                          allow_production_development=allow_production_development)
    return manifest


def publish(data_dir: Path, snapshots: dict[str, dict | Exception], *, build_commit: str, now: datetime) -> dict:
    """Publish core catalogs, retaining validated previous sports on failure."""
    now = utc(now)
    if not re.fullmatch(r"[a-f0-9]{40}", build_commit):
        raise IntegrityError("Full build commit SHA required")
    previous = read_manifest(data_dir, now=now, validate_auxiliary=False) if (data_dir / "manifest.json").exists() else None
    entries = {item["league"]: dict(item) for item in previous["sports"]} if previous else {}
    errors = {}
    for league, snapshot in snapshots.items():
        try:
            if isinstance(snapshot, Exception):
                raise snapshot
            validate_sport(snapshot, league=league, now=now)
            raw = canonical(snapshot)
            sha = hashlib.sha256(raw).hexdigest()
            path = f"{league.lower()}.{sha}.json"
            _write_atomic(data_dir / path, raw)
            entries[league] = {"league": league, "path": path, "sha256": sha,
                              "generated_at": snapshot["generated_at"], "status": "RESEARCH_ONLY",
                              "retained": False, "error": None}
        except (ValueError, TypeError, KeyError, OSError) as error:
            errors[league] = f"{type(error).__name__}: sport update rejected"
            if league in entries:
                entries[league].update(retained=True, error=errors[league])
    if not entries:
        raise IntegrityError("No valid sport snapshot; previous publication unchanged")
    result = {"schema_version": SCHEMA_VERSION, "build_commit": build_commit, "published_at": stamp(now),
              "publication_status": "RESEARCH_ONLY", "supported_sports": sorted(entries),
              "sports": [entries[key] for key in sorted(entries)], "errors": errors}
    result["snapshot_id"] = digest(result)
    _write_atomic(data_dir / "manifest.json", canonical(result))
    return result


def _emit_asset(data_dir: Path, asset: dict, *, prefix: str, status: str) -> dict:
    raw = canonical(asset)
    sha = hashlib.sha256(raw).hexdigest()
    descriptor = {"path": f"{prefix}.{sha}.json", "sha256": sha,
                  "generated_at": asset["generated_at"], "status": status, "retained": False, "error": None}
    _write_atomic(data_dir / descriptor["path"], raw)
    return descriptor


def build_site(root: Path, output: Path, *, build_commit: str, now: datetime,
               production_development_preview: bool = False) -> dict:
    """Allowlisted artifact; each publication channel fails independently."""
    output = output.resolve() if not output.is_symlink() else output
    if output.is_symlink() or output == root.resolve() or root.resolve().is_relative_to(output):
        raise IntegrityError("Output must be a separate non-symlink artifact directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".site-build-", dir=output.parent))
    backup, old, retained = None, None, {}
    try:
        if (output / "data/manifest.json").exists():
            old = read_manifest(output / "data", now=now, validate_auxiliary=False)
            (staging / "data").mkdir()
            for name in ("manifest.json", *(item["path"] for item in old["sports"])):
                shutil.copyfile(output / "data" / name, staging / "data" / name)
            old_sports = [load_json(output / "data" / ref["path"], max_bytes=MAX_ASSET_BYTES) for ref in old["sports"]]
            for channel in AUXILIARY_CHANNELS:
                descriptor = old.get(channel)
                if descriptor is None:
                    continue
                try:
                    _read_channel(output / "data", channel, descriptor, old_sports, now=now,
                                  allow_production_development=production_development_preview)
                    names = [descriptor["path"]]
                    if channel == "pros004":
                        from .pros004_publication import publication_asset_paths
                        names = publication_asset_paths(output / "data", descriptor, now=now)
                    elif channel == "production_research":
                        from .sdv_production_publication import publication_asset_paths
                        names = publication_asset_paths(output / "data", descriptor, now=now,
                                                        allow_development=production_development_preview)
                    for name in names:
                        shutil.copyfile(output / "data" / name, staging / "data" / name)
                    retained[channel] = descriptor
                except REJECTED_UPDATE:
                    # Never copy a descriptor path until its strict reader admits it.
                    pass
        for source in (root / "web").iterdir():
            if source.is_file() and not source.is_symlink() and source.suffix in {".html", ".css", ".js", ".mjs", ".svg", ".webmanifest"}:
                shutil.copyfile(source, staging / source.name)
        if not (staging / "index.html").is_file():
            raise IntegrityError("Site artifact requires index.html at its root")
        research_error = None
        try:
            nba_snapshot = research_nba(root, now=now)
        except (ValueError, KeyError, TypeError, OSError) as error:
            nba_snapshot = error
            if not old or not any(ref["league"] == "NBA" for ref in old["sports"]):
                # A new category-only catalog permits independent admitted offers.
                # It is explicitly an unavailable research channel, never success.
                nba_snapshot = empty_nba(root, now=now)
                research_error = f"{type(error).__name__}: research records unavailable; category catalog only"
        result = publish(staging / "data", {"NBA": nba_snapshot}, build_commit=build_commit, now=now)
        if research_error:
            result["errors"]["NBA"] = research_error
            next(ref for ref in result["sports"] if ref["league"] == "NBA")["error"] = research_error
        snapshots = [load_json(staging / "data" / ref["path"], max_bytes=MAX_ASSET_BYTES) for ref in result["sports"]]
        for channel in AUXILIARY_CHANNELS:
            descriptor, error_text = None, None
            try:
                if channel == "pros004":
                    from .pros004_publication import emit_publication
                    descriptor = emit_publication(staging / "data", root, now=now)
                elif channel == "display":
                    from .display_metadata import make_asset
                    descriptor = _emit_asset(staging / "data", make_asset(root, snapshots, now=now), prefix="display", status="DISPLAY_METADATA_ONLY")
                elif channel == "offers":
                    from .offer_publication import make_asset
                    descriptor = _emit_asset(staging / "data", make_asset(root, now=now), prefix="nba-offers", status="OFFER_ONLY_RESEARCH")
                elif channel == "paired_research":
                    from .operational_publication import make_asset
                    descriptor = _emit_asset(staging / "data", make_asset(root, now=now), prefix="paired-research", status="RESEARCH_ONLY")
                elif channel == "daily_research":
                    from .sdv_daily_grading import validate_stored_admissions
                    from .sdv_daily_publication import make_asset
                    validate_stored_admissions(root)
                    descriptor = _emit_asset(staging / "data", make_asset(root, now=now), prefix="sdv-daily", status="DAILY_SNAPSHOT_RESEARCH")
                else:
                    from .sdv_production_publication import emit_publication
                    descriptor = emit_publication(staging / "data", root, now=now,
                                                  allow_development=production_development_preview,
                                                  existing_artifact_bytes=sum(path.stat().st_size for path in output.rglob("*")
                                                      if path.is_file() and not path.is_symlink()) if output.exists() else 0)
                _read_channel(staging / "data", channel, descriptor, snapshots, now=now,
                              allow_production_development=production_development_preview)
            except REJECTED_UPDATE as error:
                error_text = f"{type(error).__name__}: {channel} update unavailable"
                if channel == "display":
                    error_text += "; source IDs remain visible"
                previous = retained.get(channel)
                if previous is not None:
                    try:
                        _read_channel(staging / "data", channel, previous, snapshots, now=now,
                                      allow_production_development=production_development_preview)
                        descriptor = {**previous, "retained": True, "error": error_text}
                    except REJECTED_UPDATE:
                        descriptor = None
                else:
                    descriptor = None
            result[channel], result[channel + "_error"] = descriptor, error_text
        result["schema_version"] = 7
        result["snapshot_id"] = digest({k: v for k, v in result.items() if k != "snapshot_id"})
        _write_atomic(staging / "data/manifest.json", canonical(result))
        read_manifest(staging / "data", now=now, allow_production_development=production_development_preview)
        allowed = {"manifest.json", *(ref["path"] for ref in result["sports"])}
        for channel in AUXILIARY_CHANNELS:
            descriptor = result[channel]
            if descriptor is None:
                continue
            allowed.add(descriptor["path"])
            if channel == "pros004":
                from .pros004_publication import publication_asset_paths
                allowed.update(publication_asset_paths(staging / "data", descriptor, now=now))
            elif channel == "production_research":
                from .sdv_production_publication import publication_asset_paths
                allowed.update(publication_asset_paths(staging / "data", descriptor, now=now,
                                                       allow_development=production_development_preview))
        # Failed publishers may have written intermediate assets. Only admitted,
        # manifest-referenced bytes belong in the public artifact.
        for asset_path in (staging / "data").iterdir():
            if asset_path.name not in allowed:
                asset_path.unlink()
        if output.exists():
            backup = Path(tempfile.mkdtemp(prefix=".site-old-", dir=output.parent))
            backup.rmdir()
            os.replace(output, backup)
        try:
            os.replace(staging, output)
        except OSError:
            if backup is not None:
                os.replace(backup, output)
                backup = None
            raise
        return result
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if backup is not None and backup.exists():
            shutil.rmtree(backup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--build-commit", required=True)
    parser.add_argument("--production-development-preview", action="store_true",
                        help="Local invented-data preview only; never used by the Pages publication workflow")
    args = parser.parse_args()
    manifest = build_site(Path(__file__).resolve().parent.parent, args.output,
                          build_commit=args.build_commit, now=datetime.now(timezone.utc),
                          production_development_preview=args.production_development_preview)
    print(f"Built research-only snapshot {manifest['snapshot_id']} ({len(manifest['sports'])} sport); no qualified rows")


if __name__ == "__main__":
    main()

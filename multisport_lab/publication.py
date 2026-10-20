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
    catalog.update(schema_version=1, **{field: [] for field in COLLECTIONS})
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
    from .ledger import Ledger
    from .forecast_contract import EVENT_SCHEMA
    result = empty_nba(root, now=now)
    result["schema_version"] = 2
    ledger = Ledger(root)
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
    result["future_availability"] = {"status": "AVAILABLE" if has_future else "UNAVAILABLE", "reasons": [] if has_future else [
        "No admitted pregame event/player candidate universe and observed-input capture route is available.",
        "Archive start+24h availability bounds support reconstruction only; they do not establish real-time input availability.",
        "No genuinely pregame T-90 reference issuance has been captured for upcoming games. Historical reconstructions are available in History."]}
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


def read_manifest(data_dir: Path, *, now: datetime) -> dict:
    manifest = load_json(data_dir / "manifest.json", max_bytes=MAX_ASSET_BYTES)
    fields = {"schema_version", "snapshot_id", "build_commit", "published_at", "publication_status", "supported_sports", "sports", "errors"}
    if (type(manifest) is not dict or set(manifest) != fields
            or type(manifest["schema_version"]) is not int or manifest["schema_version"] not in {1, 2}
            or manifest["publication_status"] != "RESEARCH_ONLY"
            or not re.fullmatch(r"[a-f0-9]{40}", manifest["build_commit"])
            or utc(manifest["published_at"]) > utc(now)):
        raise IntegrityError("Invalid publication manifest")
    if manifest["snapshot_id"] != digest({k: v for k, v in manifest.items() if k != "snapshot_id"}):
        raise IntegrityError("Manifest checksum mismatch")
    seen = set()
    for entry in manifest["sports"]:
        if set(entry) != {"league", "path", "sha256", "generated_at", "status", "retained", "error"}:
            raise IntegrityError("Invalid manifest sport entry")
        league = entry["league"]
        if league in seen or not re.fullmatch(r"[A-Z]+", league):
            raise IntegrityError("Duplicate/invalid league")
        seen.add(league)
        if (entry["path"] != f"{league.lower()}.{entry['sha256']}.json"
                or not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"])
                or type(entry["retained"]) is not bool or entry["status"] != "RESEARCH_ONLY"):
            raise IntegrityError("Invalid sport path/hash/status")
        snapshot = load_json(data_dir / entry["path"], max_bytes=MAX_ASSET_BYTES)
        if hashlib.sha256((data_dir / entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
            raise IntegrityError("Sport asset checksum mismatch")
        validate_sport(snapshot, league=league, now=utc(manifest["published_at"]))
        if snapshot["generated_at"] != entry["generated_at"]:
            raise IntegrityError("Generation clock mismatch")
    if sorted(seen) != manifest["supported_sports"]:
        raise IntegrityError("Sport references do not match supported scope")
    return manifest


def publish(data_dir: Path, snapshots: dict[str, dict | Exception], *, build_commit: str, now: datetime) -> dict:
    """Publish admitted catalogs, retaining validated previous sports on failure."""
    now = utc(now)
    if not re.fullmatch(r"[a-f0-9]{40}", build_commit):
        raise IntegrityError("Full build commit SHA required")
    previous = read_manifest(data_dir, now=now) if (data_dir / "manifest.json").exists() else None
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
            # Never publish exception bodies: they may contain private upstream URLs/data.
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


def build_site(root: Path, output: Path, *, build_commit: str, now: datetime) -> dict:
    # Assemble from an allowlist into a fresh tree, never upload arbitrary stale
    # files left in a previous output directory. Carry only verified assets.
    output = output.resolve() if not output.is_symlink() else output
    if output.is_symlink() or output == root.resolve() or root.resolve().is_relative_to(output):
        raise IntegrityError("Output must be a separate non-symlink artifact directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".site-build-", dir=output.parent))
    backup = None
    try:
        if (output / "data/manifest.json").exists():
            old = read_manifest(output / "data", now=now)
            (staging / "data").mkdir()
            for name in ("manifest.json", *(item["path"] for item in old["sports"])):
                shutil.copyfile(output / "data" / name, staging / "data" / name)
        for source in (root / "web").iterdir():
            if source.is_file() and not source.is_symlink() and source.suffix in {".html", ".css", ".js", ".mjs", ".svg", ".webmanifest"}:
                shutil.copyfile(source, staging / source.name)
        if not (staging / "index.html").is_file():
            raise IntegrityError("Site artifact requires index.html at its root")
        try:
            nba_snapshot = research_nba(root, now=now)
        except (ValueError, KeyError, TypeError, OSError) as error:
            nba_snapshot = error
        result = publish(staging / "data", {"NBA": nba_snapshot}, build_commit=build_commit, now=now)
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
    args = parser.parse_args()
    manifest = build_site(Path(__file__).resolve().parent.parent, args.output,
                          build_commit=args.build_commit, now=datetime.now(timezone.utc))
    print(f"Built research-only snapshot {manifest['snapshot_id']} ({len(manifest['sports'])} sport); no qualified rows")


if __name__ == "__main__":
    main()

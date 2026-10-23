"""Create-only private catalogue/rule enrichment; never collects or admits offers.

The sealed companion refers to, and never rewrites, the original v1 review.
Recovery requires the base package and all exact retained source bodies/metadata.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import json
import re

from .integrity import IntegrityError, _bounded_bytes, _decode, canonical, digest, stamp, utc
from . import player_line_review as base
from .source_evidence import extract_source_text

SCHEMA = "nba-private-player-line-enrichment-v1"
MAX_BYTES = 256 * 1024
SOURCES = {
    "catalogue": "https://api.sleeper.app/v1/players/nba",
    "picks_rules": "https://support.sleeper.com/en/articles/9047931-sleeper-player-picks-rules",
    "stats_rules": "https://support.sleeper.com/en/articles/6262990-sleeper-player-picks-stats-explained",
}
WITNESSES = {
    "general_overtime": ("picks_rules", "Overtime and extra innings count toward stats"),
    "corrections_within_30_minutes": ("picks_rules", "Stat corrections made within 30 minutes of game end will trigger regrading"),
    "corrections_after_30_minutes": ("picks_rules", "Corrections after 30 minutes will not affect contest results"),
    "q1": ("stats_rules", "1st quarter projections will be graded based on the player's statistical totals at the end of the 1st quarter."),
    "quarter_overtime": ("stats_rules", "Quarter Markets: Resulted on score for relevant quarter. Overtime does not count."),
}
Q1 = {"first_qtr_points", "first_qtr_rebounds", "first_qtr_assists"}
TOP = {"schema_version", "scope", "source", "base", "generated_at", "evidence_lane", "sources", "rule_witnesses", "event_team_inventory",
       "counts", "observations", "public_admission", "ticket_eligibility", "qualification", "enrichment_id"}
SOURCE_FIELDS = {"source_url", "raw_sha256", "raw_bytes", "metadata_sha256", "request_started_at", "observed_at",
                 "upstream_observed_at"}
ROW_FIELDS = {"row_id", "league", "namespace", "provider_player_id", "provider_event_id", "player_label", "name_status",
              "catalogue_pointer", "catalogue_team", "board_team", "team_status", "raw_stat_label", "period", "overtime",
              "period_evidence", "event_status", "event_label", "event_starts_at", "settlement_status",
              "forecast_match_status", "ticket_eligible", "missing_fields"}
COUNT_FIELDS = {"catalogue_objects", "catalogue_players", "catalogue_team_entries", "source_nba_rows", "source_player_ids",
                "name_resolved_player_ids", "name_unresolved_player_ids", "source_side_observations", "q1_side_observations",
                "displayed_observations"}


def require(condition, message):
    if not condition:
        raise IntegrityError(message)


def _read(path, maximum):
    try: return _bounded_bytes(Path(path), maximum)
    except OSError as error: raise IntegrityError("Missing or unreadable retained enrichment/base body") from error


def visible(raw):
    return extract_source_text(raw, "text/html").decode("utf-8")


def source_fact(key, raw, metadata_raw, *, now):
    require(type(raw) is bytes and 0 < len(raw) <= base.MAX_INPUT_BYTES, "Enrichment original exceeds 8-MiB ceiling")
    require(type(metadata_raw) is bytes and 0 < len(metadata_raw) <= MAX_BYTES, "Enrichment metadata exceeds ceiling")
    meta = _decode(metadata_raw)
    require(type(meta) is dict and meta.get("complete_body") is True and meta.get("http_status") == 200
            and meta.get("url") == meta.get("final_url") == SOURCES[key], "Unsupported or incomplete enrichment source")
    expected_type = "json" if key == "catalogue" else "html"
    require(expected_type in str(meta.get("content_type", "")).lower(), "Unexpected enrichment content type")
    require(type(meta.get("raw_bytes")) is int and meta["raw_bytes"] == len(raw)
            and meta.get("raw_sha256") == hashlib.sha256(raw).hexdigest(), "Enrichment raw hash/bytes differ")
    require("request_started_at" in meta and "observed_at" in meta
            and base._clock(meta["request_started_at"]) <= base._clock(meta["observed_at"]) <= utc(now),
            "Enrichment source clocks disagree")
    # HTTP Date is a response clock, not evidence of upstream observation time.
    return {"source_url": SOURCES[key], "raw_sha256": meta["raw_sha256"], "raw_bytes": len(raw),
            "metadata_sha256": hashlib.sha256(metadata_raw).hexdigest(), "request_started_at": meta["request_started_at"],
            "observed_at": meta["observed_at"], "upstream_observed_at": None}


def catalogue_players(raw):
    catalogue = _decode(raw)
    require(type(catalogue) is dict and 0 < len(catalogue) <= 10000, "Expected bounded player-ID catalogue")
    players = {}; teams = 0; ids = set()
    for key, row in catalogue.items():
        require(type(row) is dict and base._text(key) and row.get("player_id") == key and row.get("sport") == "nba"
                and key not in ids, "Conflicting catalogue key/player_id/sport")
        ids.add(key)
        if row.get("position") == "DEF":
            require(re.fullmatch(r"[A-Z]{2,4}", key) is not None and row.get("team") == key,
                    "Unrecognized non-player catalogue subject")
            teams += 1; continue
        require(re.fullmatch(r"[0-9]+", key) is not None, "Unrecognized native player ID")
        require(all(base._text(row.get(k), 200) for k in ("first_name", "last_name", "full_name"))
                and row["full_name"] == row["first_name"]+" "+row["last_name"], "Conflicting or missing catalogue name")
        require(row.get("team") is None or base._text(row["team"], 200), "Invalid literal catalogue team")
        players[key] = {"name": row["full_name"], "team": row.get("team")}
    return players, len(catalogue), teams


def _row(original, players):
    player = players.get(original["provider_player_id"]); name = None if player is None else player["name"]
    catalogue_team = None if player is None else player["team"]; board_team = original["team_label"]
    team_status = "UNKNOWN" if catalogue_team is None or board_team is None else (
        "CONSISTENT_LITERALS_EVENT_UNVERIFIED" if catalogue_team == board_team else "CONFLICT_UNVERIFIED")
    q1 = original["raw_stat_label"] in Q1
    missing = ["native_event_mapping", "event_start", "product_variant", "complete_settlement_contract"]
    if name is None: missing.append("player_name")
    if not q1: missing += ["period", "overtime"]
    if team_status == "CONFLICT_UNVERIFIED": missing.append("team_conflict")
    return {"row_id": original["row_id"], "league": "NBA", "namespace": "sleeper",
            "provider_player_id": original["provider_player_id"], "provider_event_id": original["provider_event_id"],
            "player_label": name, "name_status": "VERIFIED_NATIVE_CATALOGUE" if player else "UNVERIFIED_NOT_IN_CATALOGUE",
            "catalogue_pointer": "/"+original["provider_player_id"] if player else None,
            "catalogue_team": catalogue_team, "board_team": board_team, "team_status": team_status,
            "raw_stat_label": original["raw_stat_label"], "period": "Q1" if q1 else "UNKNOWN",
            "overtime": "OT_EXCLUDED" if q1 else "UNKNOWN", "period_evidence": ["q1", "quarter_overtime"] if q1 else [],
            "event_status": "UNVERIFIED_NATIVE_ID", "event_label": None, "event_starts_at": None,
            "settlement_status": "PARTIAL_GENERIC_RULES_ONLY", "forecast_match_status": "NOT_MATCHED_UNVERIFIED_EVENT_PERIOD",
            "ticket_eligible": False, "missing_fields": missing}


def event_team_inventory(nba):
    events = {}
    for row in nba:
        if row.get("subject_type") != "player": continue
        identity = row.get("game_id")
        require(base._text(identity), "Missing native event identity for team inventory")
        labels = events.setdefault(identity, set())
        for option in row.get("options", []):
            if type(option) is dict and option.get("subject_team") is not None:
                require(base._text(option["subject_team"], 200), "Invalid native source team label")
                labels.add(option["subject_team"])
    return [{"provider_event_id": event, "source_team_labels": sorted(labels),
             "status": "CONFLICT_UNVERIFIED" if len(labels) > 2 else "UNVERIFIED_NATIVE_EVENT"}
            for event, labels in sorted(events.items())]


def project(review, assets, *, generated_at, now):
    base.validate_review(review, now=now)
    require(review["source_evidence"]["kind"] == "RAW_HTTP_BODY_REPLAYED", "Enrichment requires original board bytes")
    require(set(assets) == set(SOURCES), "Exact catalogue and rule originals required")
    facts = {key: source_fact(key, *assets[key], now=now) for key in SOURCES}
    generated_at = stamp(utc(generated_at))
    require(max([base._clock(review["generated_at"])]+[base._clock(v["observed_at"]) for v in facts.values()])
            <= base._clock(generated_at) <= utc(now), "Enrichment cannot backdate later source observations")
    players, objects, teams = catalogue_players(assets["catalogue"][0])
    witnesses = {}
    texts = {key: visible(assets[key][0]) for key in ("picks_rules", "stats_rules")}
    for key, (source, text) in WITNESSES.items():
        require(text in texts[source], "Required official rule witness missing: "+key)
        witnesses[key] = {"source": source, "text": text}
    return facts, players, objects, teams, witnesses, generated_at


def make_enrichment(review, board_raw, assets, *, generated_at, now):
    facts, players, objects, teams, witnesses, generated_at = project(review, assets, generated_at=generated_at, now=now)
    require(hashlib.sha256(board_raw).hexdigest() == review["source_evidence"]["raw_source_sha256"], "Whole board binding differs")
    board = _decode(board_raw)
    require(type(board) is list and len(board) == review["counts"]["source_rows"], "Board inventory differs")
    nba = [row for row in board if type(row) is dict and row.get("sport") == "nba"]
    ids = {str(row["subject_id"]) for row in nba if row.get("subject_type") == "player"}
    # Full source counts remain separate from the selected display window.
    q1 = sum(len(row["options"]) for row in nba if row.get("subject_type") == "player" and row.get("wager_type") in Q1)
    body = {"schema_version": SCHEMA, "scope": "LOCAL_REVIEW_ONLY", "source": "sleeper",
            "base": {"review_id": review["review_id"], "board_sha256": review["source_evidence"]["raw_source_sha256"],
                     "board_bytes": review["source_evidence"]["raw_source_bytes"], "observed_at": review["observed_at"]},
            "generated_at": generated_at, "evidence_lane": review["evidence_lane"], "sources": facts,
            "event_team_inventory": event_team_inventory(nba),
            "rule_witnesses": witnesses,
            "counts": {"catalogue_objects": objects, "catalogue_players": len(players), "catalogue_team_entries": teams,
                       "source_nba_rows": len(nba), "source_player_ids": len(ids), "name_resolved_player_ids": len(ids & players.keys()),
                       "name_unresolved_player_ids": len(ids-players.keys()), "source_side_observations": review["counts"]["parsed_observations"],
                       "q1_side_observations": q1, "displayed_observations": len(review["observations"])},
            "observations": [_row(row, players) for row in review["observations"]],
            "public_admission": False, "ticket_eligibility": False, "qualification": "UNAVAILABLE"}
    body["enrichment_id"] = digest(body)
    validate_enrichment(body, review, now=now)
    return body


def validate_enrichment(body, review, *, now):
    """Strict semantic checks survive optimized Python; seals alone are insufficient."""
    try:
        base.validate_review(review, now=now)
        base._fields(body, TOP, "enrichment")
        require(body["schema_version"] == SCHEMA and body["scope"] == "LOCAL_REVIEW_ONLY" and body["source"] == "sleeper"
                and body["public_admission"] is False and body["ticket_eligibility"] is False
                and body["qualification"] == "UNAVAILABLE" and body["evidence_lane"] == review["evidence_lane"], "Invalid enrichment scope")
        require(body["base"] == {"review_id": review["review_id"], "board_sha256": review["source_evidence"]["raw_source_sha256"],
                "board_bytes": review["source_evidence"]["raw_source_bytes"], "observed_at": review["observed_at"]}
                and review["source_evidence"]["kind"] == "RAW_HTTP_BODY_REPLAYED", "Enrichment base binding differs")
        require(base._clock(review["generated_at"]) <= base._clock(body["generated_at"]) <= utc(now), "Invalid enrichment generation clock")
        base._fields(body["sources"], set(SOURCES), "enrichment sources")
        for key, fact in body["sources"].items():
            base._fields(fact, SOURCE_FIELDS, "enrichment source")
            require(fact["source_url"] == SOURCES[key] and base._sha(fact["raw_sha256"]) and base._sha(fact["metadata_sha256"])
                    and type(fact["raw_bytes"]) is int and 0 < fact["raw_bytes"] <= base.MAX_INPUT_BYTES
                    and fact["upstream_observed_at"] is None
                    and base._clock(fact["request_started_at"]) <= base._clock(fact["observed_at"]) <= base._clock(body["generated_at"]),
                    "Invalid enrichment source identity/clocks")
        require(body["rule_witnesses"] == {key: {"source": source, "text": text} for key,(source,text) in WITNESSES.items()},
                "Rule witnesses differ")
        inventory = body["event_team_inventory"]
        require(type(inventory) is list and len(inventory) <= review["counts"]["nba_rows"], "Invalid native event inventory")
        ids = []
        for event in inventory:
            base._fields(event, {"provider_event_id", "source_team_labels", "status"}, "native event team inventory")
            labels = event["source_team_labels"]
            require(base._text(event["provider_event_id"]) and type(labels) is list
                    and all(base._text(label, 200) for label in labels) and labels == sorted(set(labels))
                    and event["status"] == ("CONFLICT_UNVERIFIED" if len(labels) > 2 else "UNVERIFIED_NATIVE_EVENT"),
                    "Native team inventory cannot establish verified event admission")
            ids.append(event["provider_event_id"])
        require(ids == sorted(set(ids)), "Duplicate/unordered native events")
        counts = body["counts"]; base._fields(counts, COUNT_FIELDS, "enrichment counts")
        require(all(type(v) is int and 0 <= v <= 20000 for v in counts.values())
                and counts["catalogue_objects"] == counts["catalogue_players"]+counts["catalogue_team_entries"]
                and counts["source_player_ids"] == counts["name_resolved_player_ids"]+counts["name_unresolved_player_ids"]
                and counts["source_player_ids"] <= counts["source_nba_rows"] == review["counts"]["nba_rows"]
                and counts["source_side_observations"] == review["counts"]["parsed_observations"]
                and counts["q1_side_observations"] <= counts["source_side_observations"]
                and counts["displayed_observations"] == len(body["observations"]) == len(review["observations"]), "Enrichment counts differ")
        for row, original in zip(body["observations"], review["observations"]):
            base._fields(row, ROW_FIELDS, "enriched observation")
            name = row["player_label"]
            require((name is None or base._text(name, 200))
                    and (row["catalogue_team"] is None or base._text(row["catalogue_team"], 200)), "Invalid enriched player name/team")
            players = {} if name is None else {original["provider_player_id"]: {"name": name, "team": row["catalogue_team"]}}
            require(row == _row(original, players), "Enriched meaning conflicts with original identity or unresolved fields")
        require(body["enrichment_id"] == digest({k:v for k,v in body.items() if k != "enrichment_id"})
                and len(canonical(body)) <= MAX_BYTES, "Enrichment seal or byte ceiling differs")
        return body
    except IntegrityError: raise
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise IntegrityError("Malformed player-line enrichment") from error


def _inventory(directory):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), "Invalid private package directory")
    entries = list(directory.iterdir())
    require(all(p.is_file() and not p.is_symlink() for p in entries), "Unsafe private package entry")
    return len(entries), sum(p.stat().st_size for p in entries)


def _combined_budget(base_directory, directory, planned=None):
    original = Path(base_directory).resolve(); companion = Path(directory).resolve()
    require(not companion.is_relative_to(original) and not original.is_relative_to(companion),
            "Companion must not overlap or alter the base package")
    files, size = _inventory(base_directory); count, total = _inventory(directory)
    for name, raw in (planned or {}).items():
        target = Path(directory)/name
        if target.exists(): require(_read(target, base.MAX_PACKAGE_BYTES) == raw, "Conflicting create-only enrichment artifact")
        else: count += 1; total += len(raw)
    require(files+count <= base.MAX_PACKAGE_FILES and size+total <= base.MAX_PACKAGE_BYTES,
            "Combined base/companion package exceeds unchanged 512-file/32-MiB limits")


def build_enrichment(*, base_directory, destination, source_root, assets, now):
    """Create-only companion. A retry retains the first enrichment clock and sources."""
    base.verify_package(base_directory, now=now)
    review = _decode(_read(Path(base_directory)/"review.json", base.MAX_REVIEW_BYTES))
    original = Path(base_directory).resolve(); companion = Path(destination).resolve()
    require(not companion.is_relative_to(original) and not original.is_relative_to(companion),
            "Companion must not overlap or alter the base package")
    destination = base._private_directory(destination, source_root)
    _combined_budget(base_directory, destination)
    old = destination/"enrichment.json"
    generated = _decode(_read(old, MAX_BYTES))["generated_at"] if old.exists() else stamp(utc(now))
    loaded = {key: (_read(paths[0], base.MAX_INPUT_BYTES), _read(paths[1], MAX_BYTES)) for key,paths in assets.items()}
    board = _read(Path(base_directory)/"source.body", base.MAX_INPUT_BYTES)
    enrichment = make_enrichment(review, board, loaded, generated_at=generated, now=now)
    planned = {"enrichment.json": canonical(enrichment)}
    for key,(raw,meta) in loaded.items():
        planned[key+".body"] = raw; planned[key+".metadata.json"] = meta
    # Intent itself is sealed content; publishing it first freezes sources and
    # clock across an interruption without changing the original base package.
    _combined_budget(base_directory, destination, planned)
    writes = 0
    for name,raw in planned.items():
        writes += int(base._create(destination, name, raw, maximum=base.MAX_INPUT_BYTES if name.endswith(".body") else MAX_BYTES))
    result = verify_package(destination, base_directory=base_directory, now=now)
    return {**result, "writes": writes, "operation": "CREATE_ONLY_LOCAL_ENRICHMENT"}


def verify_package(directory, *, base_directory, now):
    base.verify_package(base_directory, now=now)
    _combined_budget(base_directory, directory)
    body = _decode(_read(Path(directory)/"enrichment.json", MAX_BYTES))
    review = _decode(_read(Path(base_directory)/"review.json", base.MAX_REVIEW_BYTES))
    validate_enrichment(body, review, now=now)
    assets = {key: (_read(Path(directory)/(key+".body"), base.MAX_INPUT_BYTES),
                    _read(Path(directory)/(key+".metadata.json"), MAX_BYTES)) for key in SOURCES}
    board = _read(Path(base_directory)/"source.body", base.MAX_INPUT_BYTES)
    replay = make_enrichment(review, board, assets, generated_at=body["generated_at"], now=now)
    require(canonical(replay) == canonical(body), "Retained enrichment differs from original source replay")
    files, size = _inventory(directory); base_files, base_size = _inventory(base_directory)
    return {"enrichment_id": body["enrichment_id"], "review_id": review["review_id"], "counts": body["counts"],
            "recovery": "LOCAL_ORIGINAL_SOURCE_REPLAY_VERIFIED", "durable_remote_archive_verified": False,
            "source_http_requests": 0, "writes": 0, "public_admission": False, "ticket_eligibility": False,
            "companion_bytes": size, "combined_package_bytes": size+base_size, "combined_package_files": files+base_files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path); mode.add_argument("--verify", type=Path)
    for key in SOURCES:
        parser.add_argument("--"+key.replace("_", "-")+"-body", type=Path)
        parser.add_argument("--"+key.replace("_", "-")+"-metadata", type=Path)
    args = parser.parse_args(); now = datetime.now(timezone.utc)
    assets = {key: (getattr(args,key+"_body"), getattr(args,key+"_metadata")) for key in SOURCES}
    if args.verify:
        require(all(not any(paths) for paths in assets.values()), "Read-only replay does not accept source overrides")
        result = verify_package(args.verify, base_directory=args.base, now=now)
    else:
        require(all(all(paths) for paths in assets.values()), "Catalogue and both rule originals/metadata are required")
        result = build_enrichment(base_directory=args.base, destination=args.output,
                                  source_root=Path(__file__).resolve().parents[1], assets=assets, now=now)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__": main()

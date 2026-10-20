"""Offline, price-independent input checks; never admit real-time issuance.

Source clocks, access basis and normalization lineage are supplied assertions.
Matching local bytes and consistent metadata cannot establish their authenticity.
This module never fetches sources, records ledger captures or generates forecasts.
"""
from __future__ import annotations

import argparse
from dataclasses import fields
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re
import stat
import sys

from .integrity import IntegrityError, canonical, digest, load_json, stamp, utc
from .nba_data import COUNT_FIELDS, NBAPlayerGame, audit_rows

SCHEMA = "nba-input-readiness-v1"
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_HISTORY_ROWS = 20_000
MAX_CANDIDATES = 1000
STANDARD_TEAMS = frozenset(str(i) for i in range(1, 31))
ROW_FIELDS = {field.name for field in fields(NBAPlayerGame)}


def _now():
    return datetime.now(timezone.utc)


class InputError(IntegrityError):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code


def _require(condition, code, detail):
    if not condition:
        raise InputError(code, detail)


def _keys(value, expected, name):
    _require(type(value) is dict and set(value) == set(expected), "INVALID_SCHEMA", f"invalid {name} fields")


def _text(value, name):
    _require(type(value) is str and 0 < len(value) <= 500 and value.strip() == value,
             "INVALID_TEXT", f"{name} needs a nonempty trimmed string")


def _hash(value, name):
    _require(type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value), "INVALID_HASH", f"invalid {name}")


def _clock(value):
    _require(type(value) is str, "INVALID_CLOCK", "clock must be a full UTC timestamp")
    try:
        parsed = utc(value)
    except (ValueError, TypeError) as error:
        raise InputError("INVALID_CLOCK", str(error)) from error
    _require(stamp(parsed) == value, "INVALID_CLOCK", "clock requires six-digit microsecond UTC Z format")
    return parsed


def _read_local(path, remaining):
    path = Path(path)
    _require(stat.S_ISREG(path.lstat().st_mode), "INVALID_SOURCE_FILE", "local input must be a regular file, not a symlink")
    with path.open("rb") as handle:
        raw = handle.read(remaining + 1)
    _require(len(raw) <= remaining, "SOURCE_BUDGET", "local source files exceed 64 MiB aggregate budget")
    return raw


def _validate(snapshot, source_paths, imported_at):
    _require(len(canonical(snapshot)) <= MAX_METADATA_BYTES, "METADATA_BUDGET", "snapshot exceeds 8 MiB metadata budget")
    _keys(snapshot, {"schema_version", "snapshot_id", "input_kind", "producer_version", "conditioning",
                     "event", "cutoff_at", "history_freeze", "coverage", "candidates", "sources", "history"}, "snapshot")
    _require(snapshot["schema_version"] == SCHEMA, "INVALID_SCHEMA", "unsupported snapshot schema")
    _hash(snapshot["snapshot_id"], "snapshot_id")
    _require(snapshot["snapshot_id"] == digest({k: v for k, v in snapshot.items() if k != "snapshot_id"}),
             "SNAPSHOT_HASH", "snapshot content hash mismatch")
    _require(snapshot["input_kind"] in {"SYNTHETIC_FIXTURE", "RETAINED_ARCHIVE", "SUPPLIED_PREGAME_ASSERTION"},
             "UNSUPPORTED_INPUT_KIND", "input kind cannot assert real-time admission")
    _text(snapshot["producer_version"], "producer_version")
    _require(snapshot["conditioning"] == "CONDITIONAL_ON_APPEARANCE", "CONDITIONING", "only conditional appearance inputs are specified")
    event = snapshot["event"]
    _keys(event, {"id_namespace", "league", "event_id", "event_version", "event_starts_at",
                  "home_team_id", "away_team_id", "status", "source_ref"}, "event")
    _require(event["id_namespace"] == "espn" and event["league"] == "NBA", "EVENT_IDENTITY", "explicit ESPN NBA namespace is required")
    for name in ("event_id", "event_version", "source_ref"):
        _text(event[name], name)
    teams = {event["home_team_id"], event["away_team_id"]}
    _require(len(teams) == 2 and teams <= STANDARD_TEAMS, "EVENT_TEAMS", "event needs two distinct reviewed standard NBA team IDs")
    _require(event["status"] == "PRE_GAME", "EVENT_STATUS", "event must explicitly be pregame")
    start, cutoff, freeze = (_clock(value) for value in (event["event_starts_at"], snapshot["cutoff_at"], snapshot["history_freeze"]))
    _require(cutoff == start-timedelta(minutes=90) and freeze == cutoff.replace(hour=0, minute=0, second=0, microsecond=0),
             "CUTOFF", "T90 cutoff and midnight cutoff-date history freeze must match")
    _require(imported_at < start, "EVENT_ALREADY_STARTED", "local readiness import occurred at or after the event start")
    sources = snapshot["sources"]
    _require(type(sources) is list and 0 < len(sources) <= 1000, "SOURCE_COVERAGE", "one to 1000 explicit sources required")
    source_index, observed = {}, {}
    remaining = MAX_SOURCE_BYTES
    for source in sources:
        _keys(source, {"source_id", "source_url", "source_version", "raw_sha256", "observed_at",
                       "source_updated_at", "access_basis"}, "source")
        for name in ("source_id", "source_url", "source_version"):
            _text(source[name], name)
        key = source["source_id"]
        _require(key not in source_index, "DUPLICATE_SOURCE", "duplicate source ID")
        _hash(source["raw_sha256"], "raw_sha256")
        observed[key] = _clock(source["observed_at"])
        _require(observed[key] <= imported_at, "FUTURE_SOURCE_CLOCK", "supplied source observation is later than actual local import")
        if source["source_updated_at"] is not None:
            _require(_clock(source["source_updated_at"]) <= observed[key], "SOURCE_UPDATE_CLOCK", "source update is later than supplied observation")
        access = source["access_basis"]
        _keys(access, {"kind", "operation", "reference"}, "access basis assertion")
        _require(access["kind"] in {"USER_PROVIDED_FILE", "AUTHORIZED_LOCAL_FILE", "SYNTHETIC_TEST_FILE"}
                 and access["operation"] == "LOCAL_RESEARCH_IMPORT", "ACCESS_BASIS", "explicit local-import access assertion required; no automation rights inferred")
        _text(access["reference"], "access_basis.reference")
        _require(snapshot["input_kind"] == "SYNTHETIC_FIXTURE" or access["kind"] != "SYNTHETIC_TEST_FILE",
                 "SYNTHETIC_SOURCE_MISMATCH", "synthetic source files cannot be labeled as a supplied pregame/archive input")
        _require(key in source_paths, "SOURCE_FILE_MISSING", "every source hash needs a supplied local file")
        raw = _read_local(source_paths[key], remaining)
        remaining -= len(raw)
        _require(hashlib.sha256(raw).hexdigest() == source["raw_sha256"], "SOURCE_HASH", "local source bytes do not match their declared hash")
        source_index[key] = source
    _require(set(source_paths) == set(source_index), "SOURCE_FILE_MAPPING", "local file mappings must exactly match declared source IDs")

    def reference(key, *, historical=False):
        _require(key in source_index, "SOURCE_REFERENCE", "unknown source reference")
        _require(observed[key] <= (freeze if historical else cutoff),
                 "HISTORY_AFTER_FREEZE" if historical else "INPUT_AFTER_CUTOFF",
                 "supplied source observation is later than the permitted input bound")

    reference(event["source_ref"])
    candidates = snapshot["candidates"]
    _require(type(candidates) is list and 0 < len(candidates) <= MAX_CANDIDATES,
             "CANDIDATE_BUDGET", "one to 1000 explicitly selected candidates required")
    ids = set()
    for candidate in candidates:
        _keys(candidate, {"player_id", "team_id", "opponent_id", "event_id", "event_version", "event_starts_at", "source_ref"}, "candidate")
        _text(candidate["player_id"], "player_id")
        _require(candidate["player_id"] not in ids, "DUPLICATE_CANDIDATE", "duplicate selected player ID")
        ids.add(candidate["player_id"])
        _require(all(candidate[name] == event[name] for name in ("event_id", "event_version", "event_starts_at")),
                 "CANDIDATE_EVENT_IDENTITY", "candidate event/version/start must match the exact snapshot event")
        _require({candidate["team_id"], candidate["opponent_id"]} == teams,
                 "CANDIDATE_TEAM_IDENTITY", "candidate team/opponent must match event team pair")
        reference(candidate["source_ref"])
    coverage = snapshot["coverage"]
    _keys(coverage, {"basis", "requested_player_ids", "complete_declared_selection", "full_roster_claim", "participation_model_claim"}, "coverage")
    requested = coverage["requested_player_ids"]
    _require(coverage["basis"] == "DECLARED_SELECTED_PLAYERS" and type(requested) is list
             and all(type(key) is str for key in requested) and len(requested) == len(set(requested)) and set(requested) == ids
             and coverage["complete_declared_selection"] is True and coverage["full_roster_claim"] is False
             and coverage["participation_model_claim"] is False, "UNIVERSE_COVERAGE",
             "require complete declared selection; eventual appearances, full-roster and participation claims are unsupported")
    history = snapshot["history"]
    _require(type(history) is list and 0 < len(history) <= MAX_HISTORY_ROWS,
             "HISTORY_BUDGET", "one to 20,000 prior appearances required")
    identities, starts, rows = set(), {}, []
    for item in history:
        _keys(item, {"source_ref", "row"}, "history item")
        _keys(item["row"], ROW_FIELDS | {"game_duration_minutes"}, "normalized history row")
        row = NBAPlayerGame(**{name: item["row"][name] for name in ROW_FIELDS})
        _require(item["row"]["game_duration_minutes"] == row.game_duration_minutes, "HISTORY_DURATION", "history duration conflicts with final periods")
        _require(row.id_namespace == "espn" and row.team_id in STANDARD_TEAMS and row.opponent_id in STANDARD_TEAMS,
                 "HISTORY_IDENTITY", "history must use resolved ESPN standard NBA identities")
        _require(row.identity not in identities, "DUPLICATE_HISTORY", "duplicate history event/player; corrections need explicit version selection")
        identities.add(row.identity)
        _require(row.event_id not in starts or starts[row.event_id] == row.event_start, "HISTORY_EVENT_CLOCK", "conflicting history event starts")
        starts[row.event_id] = row.event_start
        _require(row.event_id != event["event_id"] and row.event_start < freeze,
                 "TARGET_OR_FUTURE_HISTORY", "target/current-freeze-date/future event cannot enter history")
        _require(row.final_status == "FINAL" and row.participation == "APPEARED" and row.minutes is not None
                 and all(getattr(row, name) is not None for name in COUNT_FIELDS)
                 and row.minutes_precision in {"seconds", "rounded_whole_minutes"},
                 "INCOMPLETE_HISTORY", "history needs explicit final appearance and complete counts/minutes/precision")
        reference(item["source_ref"], historical=True)
        _require(observed[item["source_ref"]] > row.event_start, "HISTORY_OBSERVATION_CLOCK", "final history observation must follow the historical event start")
        rows.append(row)
    _require(not audit_rows(rows, max_rows=MAX_HISTORY_ROWS)["identity_failures"], "HISTORY_RECONCILIATION", "history count arithmetic failed")
    return {"selected_candidate_count": len(ids), "prior_appearance_count": len(rows),
            "source_count": len(source_index), "verified_local_source_bytes": MAX_SOURCE_BYTES-remaining,
            "snapshot_id": snapshot["snapshot_id"], "event_id": event["event_id"], "event_version": event["event_version"],
            "input_kind": snapshot["input_kind"], "producer_version": snapshot["producer_version"],
            "conditioning": snapshot["conditioning"], "universe_basis": coverage["basis"]}


def assess_snapshot(snapshot, source_paths):
    """Check supplied assertions with an actual local clock; never record capture."""
    imported_at = _now()
    report = {"schema_version": "nba-input-readiness-report-v1", "imported_at": stamp(imported_at),
              "status": "BLOCKED", "future_issuance_admitted": False, "qualification": "UNAVAILABLE",
              "source_clock_authenticity_verified": False, "source_permission_verified": False,
              "normalization_lineage_verified": False,
              "admission_blockers": ["NO_ADMITTED_FUTURE_INPUT_PRODUCER", "CURRENT_R0_REAL_TIME_ISSUANCE_DISABLED"],
              "structural_blockers": []}
    try:
        report["inventory"] = _validate(snapshot, source_paths, imported_at)
    except (IntegrityError, ValueError, TypeError, KeyError, OSError) as error:
        report["structural_blockers"].append({"code": getattr(error, "code", "INVALID_INPUT"), "detail": str(error)})
    else:
        report["status"] = "STRUCTURAL_CHECKS_PASSED_NOT_ADMITTED"
    return report


def diagnose_archive(panel_path, receipts_path):
    """Bounded real retained-archive diagnostic, never a pregame snapshot import."""
    raw = _read_local(panel_path, MAX_SOURCE_BYTES)
    receipts = load_json(receipts_path, max_bytes=MAX_METADATA_BYTES)
    lines = raw.splitlines()
    # Raw assets may exceed the future snapshot row budget. Inspect only the
    # bounded prefix and report that the whole file cannot satisfy that contract.
    from .nba_data import _strict_json
    sample = [_strict_json(line.decode("utf-8")) for line in lines[:MAX_HISTORY_ROWS]]
    sources = [r for r in receipts["receipts"] if r["key"] in {"sdv_player_box_2026", "sdv_schedule_2026"}]
    starts = [utc(row["event_start"]) for row in sample]
    late_sources = [r["key"] for r in sources if starts and utc(r["observed_at"]) > max(starts)]
    blockers = ["ARCHIVE_ALONE_IS_NOT_A_COMPLETE_PROSPECTIVE_INPUT_BUNDLE", "NO_OBSERVED_PREGAME_SELECTED_PLAYER_UNIVERSE_IN_THIS_ARCHIVE",
                "NO_EVENT_VERSION_OR_ROW_SOURCE_CAPTURE_REFERENCES", "CURRENT_R0_REAL_TIME_ISSUANCE_DISABLED"]
    return {"schema_version": "nba-archive-input-diagnostic-v2", "checked_at": stamp(_now()),
            "status": "ARCHIVE_ALONE_NOT_ADMITTED_AS_PROSPECTIVE_BUNDLE", "evidence_lane": "RECONSTRUCTED_RESEARCH",
            "assessment_scope": "ARCHIVE_BUNDLE_COMPLETENESS_AND_HISTORICAL_ASOF_LIMITATIONS",
            "future_issuance_admitted": False, "qualification": "UNAVAILABLE", "no_capture_or_forecast_created": True,
            "future_event_history_timing_audit": {"status": "NOT_EVALUATED", "event_id": None,
                "event_starts_at": None, "cutoff_at": None, "history_freeze": None,
                "past_statistics_not_inherently_disqualified": True,
                "reason": "No future target was supplied. Retained past statistics may be eligible prior history for a later event if their actual observation precedes its declared freeze/cutoff and other input gates pass."},
            "historical_asof_limitations": {"sources_fetched_after_inspected_historical_event_cutoffs": late_sources,
                "effect": "These retrievals do not verify historical as-of availability; this is not a blanket prohibition on reuse as history for later future events."},
            "pilot_budget_scope": {"maximum_prior_rows": MAX_HISTORY_ROWS, "maximum_metadata_bytes": MAX_METADATA_BYTES,
                "whole_file_exceeds_prior_row_limit": len(lines) > MAX_HISTORY_ROWS,
                "meaning": "Bounded input-readiness pilot limits, not a universal limit on valid R0 history or proof of complete future history coverage."},
            "panel_sha256": hashlib.sha256(raw).hexdigest(), "panel_bytes": len(raw), "total_file_rows": len(lines),
            "inspected_prefix_rows": len(sample), "inspection_limit": MAX_HISTORY_ROWS,
            "inspected_rows_with_source_observed_at": sum("source_observed_at" in row for row in sample),
            "inspected_rows_with_source_version": sum("source_version" in row for row in sample),
            "inspected_rows_with_event_version": sum("event_version" in row for row in sample),
            "inspected_rows_with_candidate_universe": sum("candidate_universe" in row for row in sample),
            "receipts_sha256": hashlib.sha256(Path(receipts_path).read_bytes()).hexdigest(),
            "archive_observations": [{"source": r["key"], "observed_at": r["observed_at"], "source_version": r.get("source_version"),
                                      "source_updated_at": r.get("source_updated_at"), "github_asset_id": r.get("github_asset_id"),
                                      "raw_sha256": r.get("sha256")} for r in sources],
            "known_post_event_archive_sources": late_sources, "bundle_blockers": blockers}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check")
    check.add_argument("snapshot", type=Path)
    check.add_argument("--source", action="append", default=[], metavar="SOURCE_ID=LOCAL_PATH")
    archive = commands.add_parser("archive-diagnostic")
    archive.add_argument("--panel", type=Path, required=True)
    archive.add_argument("--source-receipts", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "check":
            paths = {}
            for mapping in args.source:
                key, separator, value = mapping.partition("=")
                if not separator or not key or not value or key in paths:
                    raise ValueError("source mappings need unique SOURCE_ID=LOCAL_PATH entries")
                paths[key] = Path(value)
            report = assess_snapshot(load_json(args.snapshot, max_bytes=MAX_METADATA_BYTES), paths)
        else:
            report = diagnose_archive(args.panel, args.source_receipts)
    except (IntegrityError, ValueError, TypeError, KeyError, OSError) as error:
        parser.error(str(error))
    import json
    print(json.dumps(report, indent=2, allow_nan=False))
    if args.command == "check" and report["status"] == "BLOCKED":
        sys.exit(1)


if __name__ == "__main__":
    main()

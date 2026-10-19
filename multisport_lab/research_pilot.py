"""Bounded, frozen-cohort R0 development diagnostics, never product qualification.

Inventory mode does not forecast or score. Evaluation requires an immutable
pre-scoring protocol receipt matching the exact input bytes and target dates.
Only an aggregate finite-JSON receipt is written; no player forecasts are exported.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import fields
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import resource
import stat
import subprocess
import sys
import time

from .baseline import (COUNT_FIELDS, EVIDENCE_LANE, HALF_LIFE_DAYS, MARKETS,
    MODEL_VERSION, PRIOR_APPEARANCES, ForecastTarget, HistoricalAppearance,
    evaluate_forecast, forecast_reference, variogram_score)
from .integrity import canonical, digest, read_receipt, stamp, utc, write_receipt
from .nba_data import NBAPlayerGame, audit_rows


MAX_BYTES = 64*1024*1024
MAX_ROWS = 100_000
MAX_SCORED = 200
MAX_WALL_SECONDS = 300
STANDARD_TEAMS = frozenset(str(value) for value in range(1, 31))
PROTOCOL_ID = "NBA-ALL13-JOINT-001/R0/development-pilot-v1"


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"nonfinite JSON value: {value}")


def read_normalized_panel(path: Path) -> tuple[list[HistoricalAppearance], dict]:
    """Validate before scoring; exclusions are fixed predicates with counts."""
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("input must be a regular file, not a symlink")
    with path.open("rb") as handle:
        raw = handle.read(MAX_BYTES+1)
    if len(raw) > MAX_BYTES:
        raise ValueError("input exceeds the 64 MiB budget")
    row_fields = {field.name for field in fields(NBAPlayerGame)}
    rows = []
    identities = set()
    event_starts = {}
    for index, line in enumerate(raw.splitlines(), start=1):
        if index > MAX_ROWS:
            raise ValueError("input exceeds the 100,000-row budget")
        record = json.loads(line, object_pairs_hook=_pairs, parse_constant=_constant)
        canonical(record)  # Also rejects overflowing exponents and unsupported JSON.
        if type(record) is not dict or set(record) != row_fields | {"game_duration_minutes"}:
            raise ValueError(f"line {index}: expected exact NBAPlayerGame.to_record schema")
        row = NBAPlayerGame(**{key: record[key] for key in row_fields})
        if record["game_duration_minutes"] != row.game_duration_minutes:
            raise ValueError(f"line {index}: derived duration conflicts with final periods")
        if row.identity in identities:
            raise ValueError("duplicate normalized event/player identity")
        identities.add(row.identity)
        event_key = row.id_namespace, row.event_id
        if event_key in event_starts and event_starts[event_key] != row.event_start:
            raise ValueError("one event has conflicting normalized start timestamps")
        event_starts[event_key] = row.event_start
        rows.append(row)
    source_audit = audit_rows(rows)
    if source_audit["identity_failures"]:
        raise ValueError(f"input reconciliation failure: {source_audit['identity_failures']}")
    exclusions = Counter()
    appearances = []
    for row in rows:
        # Exclusive reason precedence is recorded; never chosen after scores.
        if row.id_namespace != "espn":
            reason = "unsupported_identity_namespace"
        elif row.team_id not in STANDARD_TEAMS or row.opponent_id not in STANDARD_TEAMS:
            reason = "nonstandard_nba_teams_including_all_star"
        elif row.season_type != "2":
            reason = "outside_source_stage2"
        elif row.final_status != "FINAL":
            reason = "not_explicitly_final"
        elif row.participation != "APPEARED":
            reason = "dnp" if row.participation == "DNP" else "unknown_participation"
        elif row.minutes is None or any(getattr(row, name) is None for name in COUNT_FIELDS):
            reason = "incomplete_primitive_or_minutes"
        elif row.minutes_precision not in ("seconds", "rounded_whole_minutes"):
            reason = "unknown_minutes_precision"
        else:
            reason = None
        if reason is not None:
            exclusions[reason] += 1
            continue
        appearances.append(HistoricalAppearance(
            event_id=row.event_id, player_id=row.player_id,
            team_id=row.team_id, opponent_id=row.opponent_id,
            event_start=row.event_start,
            outcome_available_at=row.event_start+timedelta(hours=24),
            minutes=row.minutes, minutes_precision=row.minutes_precision,
            id_namespace=row.id_namespace, game_duration_minutes=row.game_duration_minutes,
            **{name: getattr(row, name) for name in COUNT_FIELDS}))
    appearances.sort(key=lambda row: (row.event_start, row.event_id, row.player_id))
    date_counts = Counter(row.event_start.date().isoformat() for row in appearances)
    observed_dates = sorted(date_counts)
    proposed = observed_dates[7:9]
    if len(proposed) != 2:
        raise ValueError("need at least nine eligible observed UTC dates for this pilot")
    selected = [row for row in appearances if row.event_start.date().isoformat() in proposed]
    selected = selected[:MAX_SCORED]
    inventory = {
        "input_file_sha256": hashlib.sha256(raw).hexdigest(), "input_bytes": len(raw),
        "input_rows": len(rows), "eligible_panel_rows": len(appearances),
        "eligible_event_count": len({row.event_id for row in appearances}),
        "eligible_player_count": len({row.player_id for row in appearances}),
        "input_exclusions": dict(sorted(exclusions.items())),
        "input_excluded_rows": sum(exclusions.values()),
        "upstream_exclusions": {"status": "EXTERNAL_TO_NORMALIZED_INPUT",
            "references": ["DATA_FEASIBILITY.md", "evidence/data/"],
            "interpretation": "zero input exclusions does not mean zero upstream exclusions"},
        "exclusion_precedence": ["unsupported_identity_namespace",
            "nonstandard_nba_teams_including_all_star", "outside_source_stage2",
            "not_explicitly_final", "dnp", "unknown_participation",
            "incomplete_primitive_or_minutes", "unknown_minutes_precision"],
        "eligible_observed_utc_dates": observed_dates,
        "eligible_rows_per_utc_date": dict(sorted(date_counts.items())),
        "warmup_utc_event_dates": observed_dates[:7],
        "proposed_target_utc_event_dates": proposed,
        "target_date_candidate_rows": sum(date_counts[day] for day in proposed),
        "bounded_target_rows": len(selected),
        "actual_target_rows_per_utc_date": dict(sorted(Counter(
            row.event_start.date().isoformat() for row in selected).items())),
        "capped_rows_not_selected": sum(date_counts[day] for day in proposed)-len(selected),
        "minutes_precision_counts": dict(Counter(row.minutes_precision for row in appearances)),
        "rounded_zero_minute_appearances": sum(row.minutes == 0 for row in appearances),
        "season_types": dict(Counter(row.season_type for row in rows)),
        "availability_bound": "archived_event_start_plus_24h_RECONSTRUCTED",
    }
    return appearances, inventory


def validate_protocol(protocol: dict, inventory: dict, target_dates: list[str]) -> None:
    """Require the pre-scoring receipt to bind this exact untuned run."""
    checks = {
        "protocol_id": PROTOCOL_ID,
        "status": "FROZEN_BEFORE_SCORING", "evidence_lane": EVIDENCE_LANE,
        "input_sha256": inventory["input_file_sha256"],
        "input_rows": inventory["input_rows"],
        "target_utc_event_dates": target_dates,
        "warmup_utc_event_dates": inventory["warmup_utc_event_dates"],
        "max_scored_appearances": MAX_SCORED, "tuning_trials": 1,
        "half_life_days": HALF_LIFE_DAYS,
        "league_prior_appearance_equivalents": PRIOR_APPEARANCES,
        "confirmation_window": None, "product_qualification": "UNAVAILABLE",
    }
    for key, expected in checks.items():
        if protocol.get(key) != expected:
            raise ValueError(f"frozen protocol mismatch: {key}")
    if target_dates != inventory["proposed_target_utc_event_dates"]:
        raise ValueError("target dates differ from the deterministic inventory rule")
    if utc(protocol["recorded_at"]) > datetime.now(timezone.utc):
        raise ValueError("protocol clock is in the future")
    if protocol.get("variogram") != {"claim": "within-player development diagnostic only",
            "pair_weights": "equal1/28", "power": 0.5,
            "primitive_scales": "all1 fixed count units"}:
        raise ValueError("frozen variogram definition does not match the implementation")


def _mean(values) -> float:
    values = list(values)
    if not values:
        raise ValueError("an empty scored cohort has no metrics")
    return math.fsum(values)/len(values)


def _interval_summary(rows: list[dict]) -> dict:
    return {str(level): {
        "observed_coverage": _mean(row[str(level)]["covered"] for row in rows),
        "mean_predicted_mass": _mean(row[str(level)]["predicted_mass"] for row in rows),
        "mean_width": _mean(row[str(level)]["width"] for row in rows),
    } for level in (0.5, 0.8, 0.95)}


def aggregate_reports(reports: list[dict]) -> dict:
    """Retain every scored row; an unseen outcome makes aggregate log loss infinite."""
    categories = {}
    for market in MARKETS:
        rows = [report["categories"][market] for report in reports]
        finite_logs = [row["log_loss"] for row in rows if row["log_loss"] is not None]
        zeros = len(rows)-len(finite_logs)
        result = {"scored_count": len(rows), "mean_crps_rps": _mean(row["crps"] for row in rows),
            "mean_absolute_error_of_mean": _mean(row["mean_absolute_error"] for row in rows),
            "rmse_of_mean": math.sqrt(_mean(row["mean_squared_error"] for row in rows)),
            "mean_absolute_error_of_median": _mean(abs(row["median"]-row["observed"]) for row in rows),
            "mean_log_loss": None if zeros else _mean(finite_logs),
            "log_loss_status": "INFINITE_ZERO_SUPPORT" if zeros else "FINITE",
            "zero_support_log_loss_count": zeros,
            "finite_log_loss_count": len(finite_logs), "finite_log_loss_sum": math.fsum(finite_logs),
            "observed_zero_rate": _mean(row["observed"] == 0 for row in rows),
            "mean_predicted_zero_probability": _mean(row["zero_probability"] for row in rows),
            "observed_above_upper95_rate": _mean(row["observed_above_upper95"] for row in rows),
            "mean_predicted_probability_above_upper95": _mean(
                row["probability_above_upper95"] for row in rows),
            "intervals": _interval_summary([row["intervals"] for row in rows])}
        if market in ("DD", "TD"):
            result.update(mean_brier=_mean(row["brier"] for row in rows),
                observed_event_rate=_mean(row["observed"] for row in rows),
                mean_predicted_probability=_mean(row["probability"] for row in rows))
        categories[market] = result
    minutes = [report["minutes_diagnostics"] for report in reports]
    return {"categories": categories, "minutes": {
        "interpretation": "reported_source_precision_not_exact_workload_calibration",
        "mean_crps": _mean(row["crps"] for row in minutes),
        "mean_absolute_error_of_mean": _mean(row["mean_absolute_error"] for row in minutes),
        "rmse_of_mean": math.sqrt(_mean(row["mean_squared_error"] for row in minutes)),
        "intervals": _interval_summary([row["intervals"] for row in minutes])}}


def _code_identity() -> dict:
    directory = Path(__file__).parent
    repository = directory.parent
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository,
                            capture_output=True, text=True, check=False)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repository,
                            capture_output=True, text=True, check=False)
    return {"repository_head_at_execution": result.stdout.strip() if result.returncode == 0 else None,
        "working_tree_dirty_at_execution": bool(status.stdout) if status.returncode == 0 else None,
        "source_file_sha256": {name: hashlib.sha256((directory/name).read_bytes()).hexdigest()
            for name in ("baseline.py", "research_pilot.py", "nba_data.py")}}


def run_pilot(appearances: list[HistoricalAppearance], inventory: dict, protocol: dict,
              target_dates: list[str], source_hashes: dict[str, str]) -> dict:
    validate_protocol(protocol, inventory, target_dates)
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc)
    targets = [row for row in appearances if row.event_start.date().isoformat() in target_dates][:MAX_SCORED]
    reports, pool_sizes, own_sizes, trained_times, issued_times = [], [], [], [], []
    variograms = []
    for observed in targets:
        if time.perf_counter()-started > MAX_WALL_SECONDS:
            raise ValueError("pilot exceeds 300-second wall budget; no partial result is published")
        forecast = forecast_reference(appearances, ForecastTarget(
            event_id=observed.event_id, player_id=observed.player_id,
            event_start=observed.event_start, id_namespace=observed.id_namespace))
        reports.append(evaluate_forecast(forecast, observed.primitive_line()))
        variograms.append(variogram_score(forecast, observed.primitive_line(),
                                         scales={name: 1 for name in COUNT_FIELDS}))
        pool_sizes.append(forecast.pool_history_count)
        own_sizes.append(forecast.player_history_count)
        trained_times.append(forecast.trained_through)
        issued_times.append(forecast.issued_at)
    if time.perf_counter()-started > MAX_WALL_SECONDS:
        raise ValueError("pilot exceeds 300-second wall budget; no partial result is published")
    aggregates = aggregate_reports(reports)
    return {"protocol_id": PROTOCOL_ID, "model_version": MODEL_VERSION,
        "protocol_payload_sha256": digest(protocol), "evidence_lane": EVIDENCE_LANE,
        "stage": "BOUNDED_HISTORICAL_DEVELOPMENT_ONLY", "tuning_trials": 1,
        "run_started_at": stamp(started_at), "run_finished_at": stamp(datetime.now(timezone.utc)),
        "forecast_actual_issuance_min": stamp(min(issued_times)),
        "forecast_actual_issuance_max": stamp(max(issued_times)),
        "runtime_wall_seconds": time.perf_counter()-started,
        "process_peak_rss_linux_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "budget": {"max_input_bytes": MAX_BYTES, "max_input_rows": MAX_ROWS,
                   "max_scored_rows": MAX_SCORED, "max_wall_seconds": MAX_WALL_SECONDS},
        "code_identity": _code_identity(), "source_file_hashes": source_hashes,
        "inventory": inventory, "registered_target_utc_event_dates": target_dates,
        "actual_scored_utc_event_dates": sorted({row.event_start.date().isoformat() for row in targets}),
        "scored_rows": len(reports), "scored_games": len({row.event_id for row in targets}),
        "scored_players": len({row.player_id for row in targets}),
        "post_score_exclusions": 0,
        "cold_start_rows": sum(size == 0 for size in own_sizes),
        "training_pool_row_count_min": min(pool_sizes), "training_pool_row_count_max": max(pool_sizes),
        "player_training_row_count_min": min(own_sizes), "player_training_row_count_max": max(own_sizes),
        "trained_through_bound_min": stamp(min(trained_times)),
        "trained_through_bound_max": stamp(max(trained_times)),
        "scored_rounded_zero_minutes": sum(row.minutes == 0 for row in targets),
        **aggregates,
        "within_player_variogram": {"mean_score": _mean(variograms), "power": 0.5,
            "primitive_scales": {name: 1 for name in COUNT_FIELDS}, "pair_weight": 1/28,
            "interpretation": "descriptive_within_player_only_no_ticket_dependence_validation"},
        "limitations": ["Archive event times and +24h availability are reconstructed, not historical as-of proof",
            "Conditional on eventual appearance, not a pregame candidate universe or participation model",
            "Finite empirical support has unsmoothed zero-probability outcomes and infinite log loss",
            "Player rows within games are dependent; no confirmatory uncertainty or promotion decision",
            "Rounded workload is not exact seconds; no rebound B0/B1/C1 comparison was run",
            "No market threshold calibration, quote economics, product qualification, prospective paper or deployment evidence"],
        "product_qualification": "UNAVAILABLE", "captured_future_evidence": False,
        "confirmatory_evaluation": False, "website_forecast_rows_exported": False}


def _source_hashes(values: list[str]) -> dict[str, str]:
    result = {}
    for value in values:
        name, separator, checksum = value.partition("=")
        if (not separator or not name or name.strip() != name or name in result
                or len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum)):
            raise ValueError("source hash needs unique NAME=lowercase-SHA256")
        result[name] = checksum
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--target-dates", nargs=2)
    parser.add_argument("--source-hash", action="append", default=[])
    parser.add_argument("--inventory-only", action="store_true")
    args = parser.parse_args()
    try:
        appearances, inventory = read_normalized_panel(args.input)
        source_hashes = _source_hashes(args.source_hash)
        if args.inventory_only:
            report = {"stage": "PRE_SCORING_INVENTORY_ONLY", "model_evaluated": False,
                      "recorded_at": stamp(datetime.now(timezone.utc)), "inventory": inventory,
                      "source_file_hashes": source_hashes}
            if args.protocol is not None:
                protocol = read_receipt(args.protocol)
                validate_protocol(protocol, inventory, inventory["proposed_target_utc_event_dates"])
                report["protocol_payload_sha256"] = digest(protocol)
        else:
            if args.protocol is None or args.target_dates is None:
                raise ValueError("evaluation requires --protocol and two frozen --target-dates")
            for day in args.target_dates:
                if date.fromisoformat(day).isoformat() != day:
                    raise ValueError("target dates require canonical YYYY-MM-DD")
            protocol = read_receipt(args.protocol)
            report = run_pilot(appearances, inventory, protocol, args.target_dates, source_hashes)
        report["invocation"] = [sys.executable, "-m", "multisport_lab.research_pilot", *sys.argv[1:]]
        created = write_receipt(args.output, report, max_bytes=2*1024*1024)
        print(json.dumps({"output": str(args.output), "created": created,
                          "stage": report["stage"], "scored_rows": report.get("scored_rows", 0)}))
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()

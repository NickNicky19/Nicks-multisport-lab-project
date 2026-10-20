"""Frozen, chronological R0 versus league-only NBA development comparison.

Inventory does not forecast or score. Evaluation requires a create-only protocol
receipt approved before scoring. All results remain RECONSTRUCTED_RESEARCH,
conditional on appearance; this is neither confirmation nor product selection.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import resource
import subprocess
import sys
import time

from .baseline import (COUNT_FIELDS, EVIDENCE_LANE, HALF_LIFE_DAYS, MARKETS,
    MODEL_VERSION, PRIOR_APPEARANCES, ForecastTarget, HistoricalAppearance,
    JointForecast, WeightedOutcome, evaluate_forecast, forecast_reference)
from .integrity import digest, read_receipt, stamp, utc, write_receipt
from .research_pilot import aggregate_reports, read_normalized_panel


PROTOCOL_ID = "NBA-ALL13-JOINT-DEV-002"
LEAGUE_VERSION = "nba_joint_league_empirical_l0_v1"
INPUT_SHA256 = "489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c"
WINDOW_START = date(2025, 11, 24)
WEEKS = 8
GAMES_PER_WEEK = 2
MAX_ROWS = 400
BOOTSTRAPS = 2000
BOOTSTRAP_SEED = 20261020
MAX_SECONDS = 900
MAX_RSS_KIB = 512*1024


def inventory_panel(rows: list[HistoricalAppearance], source: dict) -> tuple[list, dict]:
    """Select games from identity/timing only, never score-dependent criteria."""
    if source["input_file_sha256"] != INPUT_SHA256:
        raise ValueError("DEV002 requires the registered original normalized-panel SHA256")
    games = defaultdict(list)
    for row in rows:
        games[row.event_id].append(row)
    for appearances in games.values():
        starts = {row.event_start for row in appearances}
        teams = {row.team_id for row in appearances}
        pairings = {frozenset((row.team_id, row.opponent_id)) for row in appearances}
        if len(starts) != 1 or len(teams) != 2 or len(pairings) != 1:
            raise ValueError("selected source must have coherent event clocks and both team identities")
    selected, week_records = [], []
    for index in range(WEEKS):
        start = WINDOW_START+timedelta(weeks=index)
        stop = start+timedelta(days=7)
        candidates = sorted((appearances[0].event_start, event_id, appearances)
            for event_id, appearances in games.items()
            if start <= appearances[0].event_start.date() < stop)
        if len(candidates) < GAMES_PER_WEEK:
            raise ValueError("each registered calendar week requires two eligible complete games")
        chosen = candidates[:GAMES_PER_WEEK]
        week_rows = sorted((row for _, _, appearances in chosen for row in appearances),
                           key=lambda row: (row.event_start, row.event_id, row.player_id))
        selected.extend((start.isoformat(), row) for row in week_rows)
        week_records.append({"week_start": start.isoformat(),
            "week_end": (stop-timedelta(days=1)).isoformat(),
            "available_games": len(candidates), "selected_appearances": len(week_rows),
            "games": [{"event_id": event_id, "event_start": stamp(event_start),
                       "appearances": len(appearances)}
                      for event_start, event_id, appearances in chosen]})
    if len(selected) > MAX_ROWS:
        raise ValueError("complete selected games exceed the fixed 400-row budget; no game is split")
    selected_hash = digest([{ "week_start": week, "event_id": row.event_id,
        "player_id": row.player_id, "event_start": stamp(row.event_start)} for week, row in selected])
    relevant_source = {key: source[key] for key in ("input_file_sha256", "input_bytes", "input_rows",
        "eligible_panel_rows", "input_excluded_rows", "input_exclusions", "upstream_exclusions",
        "minutes_precision_counts", "rounded_zero_minute_appearances", "season_types")}
    return selected, {"source": relevant_source,
        "window_start": WINDOW_START.isoformat(),
        "window_end": (WINDOW_START+timedelta(weeks=WEEKS)-timedelta(days=1)).isoformat(),
        "warmup_source_first_date": min(row.event_start.date() for row in rows).isoformat(),
        "all_earlier_eligible_history_used": True,
        "weekly_inventory": week_records,
        "selected_games": WEEKS*GAMES_PER_WEEK, "selected_appearances": len(selected),
        "selected_cohort_identity_sha256": selected_hash,
        "selection": "first_two_games_per_UTC_Monday_Sunday_week_by_start_then_event_id_all_appearances",
        "budget_rule": "fail_before_scoring_if_complete_games_exceed_400_never_split_games"}


def protocol_specification(inventory: dict) -> dict:
    """The complete statistical specification; actual approval clock is external."""
    return {"protocol_id": PROTOCOL_ID, "status": "FROZEN_BEFORE_SCORING",
        "evidence_lane": EVIDENCE_LANE, "participation": "CONDITIONAL_ON_APPEARANCE",
        "input_sha256": INPUT_SHA256, "input_rows": inventory["source"]["input_rows"],
        "cohort_identity_sha256": inventory["selected_cohort_identity_sha256"],
        "cohort": "ESPN source_stage2 FINAL standard_team_and_opponent_IDs1_to30 complete_APPEARED",
        "window_start": inventory["window_start"], "window_end": inventory["window_end"],
        "weeks": WEEKS, "games_per_week": GAMES_PER_WEEK,
        "selected_games": inventory["selected_games"],
        "selected_appearances": inventory["selected_appearances"],
        "weekly_inventory": inventory["weekly_inventory"],
        "history": "all_earlier_eligible_source_rows_daily_00UTC_cutoff_date_freeze",
        "cutoff": "event_start_minus_exactly_90_minutes",
        "availability_bound": "archived_event_start_plus24h_reconstructed_not_asof_proof",
        "models": {"R0": {"version": MODEL_VERSION, "half_life_days": HALF_LIFE_DAYS,
            "league_prior_appearance_equivalents": PRIOR_APPEARANCES,
            "algorithm": "unchanged_baseline_forecast_reference"},
            "L0": {"version": LEAGUE_VERSION, "half_life_days": HALF_LIFE_DAYS,
                "algorithm": "league_only_same_completed_complete_line_recency_distribution"}},
        "tuning": "none_two_fixed_models_one_registered_development_comparison",
        "all_markets": list(MARKETS), "tail_policy": "finite_empirical_unsmoothed_zero_support_log_infinite",
        "primary": "per_category_paired_player_row_mean_discrete_CRPS_RPS_difference_R0_minus_L0",
        "bootstrap": {"replicates": BOOTSTRAPS, "seed": BOOTSTRAP_SEED,
            "unit": "complete_registered_UTC_calendar_week_selected_games_and_all_player_rows",
            "draw": "eight_weeks_with_replacement_recompute_player_row_weighted_mean_difference",
            "interval": "two_sided95_percentile_linear_interpolation_at_0.025_0.975",
            "multiplicity_adjustment": "none_descriptive_per_category_no_selection_or_promotion"},
        "secondary": ["DD_TD_Brier_unsmoothed_log", "zero_and_tail_diagnostics",
                      "central50_80_95_intervals_predicted_mass_and_coverage", "reported_precision_minutes_errors"],
        "budgets": {"max_scored_rows": MAX_ROWS, "max_wall_seconds": MAX_SECONDS,
                    "max_rss_kib": MAX_RSS_KIB},
        "post_score_exclusions": "none_fail_whole_run_on_integrity_or_budget_failure",
        "confirmation": False, "promotion_or_model_selection": False,
        "product_qualification": "UNAVAILABLE", "prospective_paper_evidence": False}


def validate_protocol(protocol: dict, inventory: dict) -> None:
    expected = protocol_specification(inventory)
    if set(protocol) != set(expected) | {"recorded_at", "approved_by"}:
        raise ValueError("protocol requires exact specification plus actual recorded_at and approved_by")
    for key, value in expected.items():
        if protocol[key] != value:
            raise ValueError(f"frozen DEV002 protocol mismatch: {key}")
    if protocol["approved_by"] != "root_integration_owner":
        raise ValueError("DEV002 requires integration-owner approval before evaluation")
    if utc(protocol["recorded_at"]) > datetime.now(timezone.utc):
        raise ValueError("protocol cannot be recorded in the future")


@dataclass(frozen=True)
class LeagueForecast:
    target: ForecastTarget
    issued_at: datetime
    trained_through: datetime
    input_sha256: str
    support: tuple[WeightedOutcome, ...]
    player_history_count: int
    pool_history_count: int

    def marginal(self, market):
        return JointForecast.marginal(self, market)


class DailyPool:
    """Cache only training-only full-line league laws, never target outcomes."""
    def __init__(self, rows):
        self.rows = rows
        self.cache = {}

    def get(self, target):
        freeze = target.history_freeze
        if freeze not in self.cache:
            rows = tuple(row for row in self.rows if row.event_start < freeze
                         and row.outcome_available_at <= freeze)
            if not rows:
                raise ValueError("no earlier completed league training pool")
            latest = max(row.event_start for row in rows)
            weights = [2**(-(latest-row.event_start).total_seconds()/86400/HALF_LIFE_DAYS)
                       for row in rows]
            total = math.fsum(weights)
            support = tuple(WeightedOutcome(row.event_id, row.player_id,
                row.primitive_line(), weight/total) for row, weight in zip(rows, weights) if weight > 0)
            pool_hash = digest([row.to_record() for row in rows])
            self.cache[freeze] = rows, support, max(row.outcome_available_at for row in rows), pool_hash
        rows, support, trained, pool_hash = self.cache[freeze]
        if any(row.event_id == target.event_id for row in rows):
            raise ValueError("target event entered its own historical pool")
        return rows, support, trained, pool_hash

    def forecast(self, target):
        rows, support, trained, pool_hash = self.get(target)
        issued_at = datetime.now(timezone.utc)
        if issued_at < target.cutoff:
            raise ValueError("cannot issue before T90 cutoff")
        return LeagueForecast(target, issued_at, trained,
            digest({"model_version": LEAGUE_VERSION, "pool_sha256": pool_hash,
                    "target": target.to_record()}), support,
            sum(row.player_id == target.player_id for row in rows), len(rows))


def _quantile_linear(values, probability):
    ordered = sorted(values)
    position = (len(ordered)-1)*probability
    lower = math.floor(position)
    fraction = position-lower
    return ordered[lower]+fraction*(ordered[min(lower+1, len(ordered)-1)]-ordered[lower])


def paired_week_bootstrap(week_sums: list[dict], week_counts: list[int]) -> dict:
    """Ratio of resampled sums to row counts, preserving unequal week sizes."""
    if len(week_sums) != WEEKS or len(week_counts) != WEEKS or any(n <= 0 for n in week_counts):
        raise ValueError("bootstrap requires all eight complete positive-sized week clusters")
    rng = random.Random(BOOTSTRAP_SEED)
    differences = {market: [] for market in MARKETS}
    for _ in range(BOOTSTRAPS):
        indices = [rng.randrange(WEEKS) for _ in range(WEEKS)]
        denominator = sum(week_counts[index] for index in indices)
        for market in MARKETS:
            differences[market].append(math.fsum(week_sums[index][market] for index in indices)/denominator)
    total_rows = sum(week_counts)
    return {market: {"mean_difference_R0_minus_L0": math.fsum(week[market] for week in week_sums)/total_rows,
        "cluster_percentile95_lower": _quantile_linear(differences[market], 0.025),
        "cluster_percentile95_upper": _quantile_linear(differences[market], 0.975),
        "bootstrap_replicates": BOOTSTRAPS, "week_clusters": WEEKS,
        "interpretation": "negative_favors_R0_descriptive_development_no_promotion_or_selection"}
        for market in MARKETS}


def code_identity():
    directory = Path(__file__).parent
    filenames = ("development_002.py", "baseline.py", "research_pilot.py", "nba_data.py")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=directory.parent,
                          capture_output=True, text=True, check=False)
    return {"repository_head": head.stdout.strip() if head.returncode == 0 else None,
        "source_file_sha256": {name: hashlib.sha256((directory/name).read_bytes()).hexdigest()
                               for name in filenames}}


def _budget(started):
    if time.perf_counter()-started > MAX_SECONDS:
        raise ValueError("DEV002 exceeds registered 900-second wall budget; no partial score publication")
    if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > MAX_RSS_KIB:
        raise ValueError("DEV002 exceeds registered 512-MiB peak-RSS budget; no partial score publication")


def run_development(rows, selected, inventory, protocol):
    validate_protocol(protocol, inventory)
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc)
    code_at_start = code_identity()
    pools = DailyPool(rows)
    reports = {"R0": [], "L0": []}
    weekly_reports = {model: defaultdict(list) for model in reports}
    hashes = {model: [] for model in reports}
    issued = {model: [] for model in reports}
    pool_counts, own_counts, trained = [], [], []
    week_differences = {week["week_start"]: {market: [] for market in MARKETS}
                        for week in inventory["weekly_inventory"]}
    for week, observed in selected:
        _budget(started)
        target = ForecastTarget(observed.event_id, observed.player_id, observed.event_start, observed.id_namespace)
        prior_rows, _, _, _ = pools.get(target)
        # The unchanged R0 receives exactly the eligible daily pool; global source
        # identity validation already ran. Excluded future rows cannot affect its
        # support or canonical input hash. This is a computation-only shortcut.
        forecasts = {"R0": forecast_reference(prior_rows, target), "L0": pools.forecast(target)}
        _budget(started)
        for model, forecast in forecasts.items():
            report = evaluate_forecast(forecast, observed.primitive_line())
            # The shared arithmetic evaluator's default metadata says R0; bind
            # L0 explicitly, retaining precisely the same category calculations.
            report["model_version"] = MODEL_VERSION if model == "R0" else LEAGUE_VERSION
            reports[model].append(report)
            weekly_reports[model][week].append(report)
            hashes[model].append(forecast.input_sha256)
            issued[model].append(forecast.issued_at)
        for market in MARKETS:
            week_differences[week][market].append(
                reports["R0"][-1]["categories"][market]["crps"]
                - reports["L0"][-1]["categories"][market]["crps"])
        pool_counts.append(forecasts["R0"].pool_history_count)
        own_counts.append(forecasts["R0"].player_history_count)
        trained.append(forecasts["R0"].trained_through)
    _budget(started)
    weeks = [week["week_start"] for week in inventory["weekly_inventory"]]
    week_sums = [{market: math.fsum(week_differences[week][market]) for market in MARKETS} for week in weeks]
    week_counts = [len(weekly_reports["R0"][week]) for week in weeks]
    paired = paired_week_bootstrap(week_sums, week_counts)
    aggregate = {model: aggregate_reports(values) for model, values in reports.items()}
    weekly = {model: {week: aggregate_reports(weekly_reports[model][week]) for week in weeks} for model in reports}
    for market in ("DD", "TD"):
        paired[market]["brier_mean_difference_R0_minus_L0"] = (
            aggregate["R0"]["categories"][market]["mean_brier"]
            - aggregate["L0"]["categories"][market]["mean_brier"])
        paired[market]["brier_interval_equals_binary_crps_interval"] = True
        logs = [aggregate[model]["categories"][market]["mean_log_loss"] for model in ("R0", "L0")]
        paired[market]["mean_log_loss_difference_R0_minus_L0"] = logs[0]-logs[1] if None not in logs else None
        paired[market]["log_difference_status"] = "FINITE" if None not in logs else "UNAVAILABLE_INFINITE_MODEL_LOSS"
    if code_identity() != code_at_start:
        raise ValueError("source code changed during registered run; no score publication")
    _budget(started)
    return {"protocol_id": PROTOCOL_ID, "protocol_payload_sha256": digest(protocol),
        "evidence_lane": EVIDENCE_LANE, "stage": "CHRONOLOGICAL_DEVELOPMENT_COMPARISON_ONLY",
        "run_started_at": stamp(started_at), "run_finished_at": stamp(datetime.now(timezone.utc)),
        "runtime_wall_seconds": time.perf_counter()-started,
        "process_peak_rss_linux_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "code_identity": code_at_start, "inventory": inventory,
        "scored_appearances_per_model": len(selected), "post_score_exclusions": 0,
        "cold_start_appearances": sum(count == 0 for count in own_counts),
        "rounded_zero_minute_appearances": sum(row.minutes == 0 for _, row in selected),
        "training_pool_rows_min": min(pool_counts), "training_pool_rows_max": max(pool_counts),
        "player_history_rows_min": min(own_counts), "player_history_rows_max": max(own_counts),
        "trained_through_bound_min": stamp(min(trained)), "trained_through_bound_max": stamp(max(trained)),
        "models": {model: {"version": MODEL_VERSION if model == "R0" else LEAGUE_VERSION,
            "forecast_input_hash_sequence_sha256": digest(hashes[model]),
            "actual_issuance_min": stamp(min(issued[model])), "actual_issuance_max": stamp(max(issued[model])),
            **aggregate[model]} for model in reports},
        "weekly_metrics": weekly,
        "paired_per_category_crps": paired,
        "bootstrap": {"replicates": BOOTSTRAPS, "seed": BOOTSTRAP_SEED,
            "week_counts": week_counts, "unit": "eight_registered_complete_calendar_week_clusters",
            "interval": "95_percentile_linear_quantiles", "multiplicity_adjustment": "none"},
        "claims": {"confirmation": False, "promotion": False, "model_selection": False,
            "product_qualification": "UNAVAILABLE", "same_game_ticket_dependence_validated": False,
            "prospective_paper_evidence": False},
        "limitations": ["Outcome availability and archived starts are reconstructed, not historical as-of proof",
            "First two eligible UTC games each week are a fixed sparse sample, not a representative full-slate sample",
            "Only eight week clusters; descriptive percentile intervals can be unstable and are not confirmation",
            "Fourteen category intervals have no multiplicity correction and do not authorize selection",
            "Conditional on eventual appearance, not a frozen operational pregame candidate universe",
            "Finite empirical tails retain zero support and infinite log loss; no smoothing or probability repairs",
            "Rounded minute diagnostics do not validate exact-second exposure or the REB B0/B1/C1 experiment"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--inventory-only", action="store_true")
    args = parser.parse_args()
    try:
        rows, source = read_normalized_panel(args.input)
        selected, inventory = inventory_panel(rows, source)
        if args.inventory_only:
            result = {"stage": "PRE_SCORING_INVENTORY_ONLY", "recorded_at": stamp(datetime.now(timezone.utc)),
                "model_evaluated": False, "inventory": inventory,
                "proposed_protocol": protocol_specification(inventory)}
        else:
            if args.protocol is None:
                raise ValueError("evaluation requires a frozen integration-owner --protocol receipt")
            resource.setrlimit(resource.RLIMIT_AS, (MAX_RSS_KIB*1024, MAX_RSS_KIB*1024))
            result = run_development(rows, selected, inventory, read_receipt(args.protocol))
        result["invocation"] = [sys.executable, "-m", "multisport_lab.development_002", *sys.argv[1:]]
        write_receipt(args.output, result, max_bytes=4*1024*1024)
        print(json.dumps({"output": str(args.output), "stage": result["stage"],
                          "scored_appearances_per_model": result.get("scored_appearances_per_model", 0)}))
    except (ValueError, OSError, MemoryError) as error:
        parser.error(str(error) or "memory budget exhausted; no partial score publication")


if __name__ == "__main__":
    main()

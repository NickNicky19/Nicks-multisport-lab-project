"""One untuned lagged-workload-prior NBA development challenger; no promotion.

Inventory mode does not forecast or score. Historical reconstructions remain
conditional on appearance. The K0 prior cannot improve zero-history cold starts:
its n=0 fallback is exactly the unchanged R0 law.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
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

from .baseline import (EVIDENCE_LANE, HALF_LIFE_DAYS, MARKETS, MODEL_VERSION,
    PRIOR_APPEARANCES, ForecastTarget, JointForecast, WeightedOutcome,
    evaluate_forecast, forecast_reference)
from .development_002 import DailyPool, LEAGUE_VERSION
from .integrity import digest, read_receipt, stamp, utc, write_receipt
from .research_pilot import aggregate_reports, read_normalized_panel


PROTOCOL_ID = "NBA-ALL13-JOINT-DEV-003"
KERNEL_VERSION = "nba_joint_lagged_workload_prior_k0_v1"
CONTEXT_VERSION = "nba_lagged_reported_minutes_context_v1"
INPUT_SHA256 = "489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c"
WINDOW_START = date(2025, 10, 27)
WEEKS = 12
GAMES_PER_WEEK = 2
SEED = 20261020
BOOTSTRAPS = 2000
MAX_ROWS = 600
MAX_SECONDS = 900
MAX_RSS_KIB = 512*1024
CONTEXT_APPEARANCES = 5
BANDWIDTH_MINUTES = 8.0
LEAGUE_FLOOR = 0.25
MODELS = {"R0": MODEL_VERSION, "L0": LEAGUE_VERSION, "K0": KERNEL_VERSION}
SOURCE_FILES = ("multisport_lab/development_003.py", "multisport_lab/development_002.py",
    "multisport_lab/baseline.py", "multisport_lab/research_pilot.py",
    "multisport_lab/nba_data.py", "multisport_lab/basketball.py", "multisport_lab/integrity.py",
    "tests/test_development_003.py")


@dataclass(frozen=True)
class LaggedContext:
    mean_minutes: float | None
    history_count: int
    source_identities: tuple
    source_available_max: datetime | None
    role_shift: bool

    @property
    def history_band(self):
        n = self.history_count
        return "0" if n == 0 else "1-3" if n <= 3 else "4-9" if n <= 9 else "10+"

    def to_record(self):
        return {"version": CONTEXT_VERSION, "mean_reported_minutes": self.mean_minutes,
            "history_count": self.history_count, "source_identities": [list(x) for x in self.source_identities],
            "source_available_max": stamp(self.source_available_max) if self.source_available_max else None,
            "lagged_5_vs_previous5_shift_ge8": self.role_shift}


class LaggedContextIndex:
    """Context at each target/donor's own cutoff, never that row's outcome minutes."""
    def __init__(self, rows):
        self.players = defaultdict(list)
        identities = set()
        for row in rows:
            identity = row.id_namespace, row.event_id, row.player_id
            if identity in identities:
                raise ValueError("duplicate context-panel event/player identity")
            identities.add(identity)
            self.players[row.id_namespace, row.player_id].append(row)
        self.available = {}
        for player, appearances in self.players.items():
            appearances.sort(key=lambda row: (row.outcome_available_at, row.event_start, row.event_id))
            self.available[player] = [row.outcome_available_at for row in appearances]
        self.donor_cache = {}

    def for_target(self, target):
        key = target.id_namespace, target.player_id
        count = bisect_right(self.available.get(key, []), target.history_freeze)
        history = [row for row in self.players.get(key, [])[:count]
                   if row.event_start < target.history_freeze and row.event_id != target.event_id]
        history.sort(key=lambda row: (row.event_start, row.event_id))
        recent = history[-CONTEXT_APPEARANCES:]
        mean = math.fsum(row.minutes for row in recent)/len(recent) if recent else None
        role_shift = len(history) >= 10 and abs(
            math.fsum(row.minutes for row in history[-5:])/5
            - math.fsum(row.minutes for row in history[-10:-5])/5) >= 8
        return LaggedContext(mean, len(history),
            tuple((row.id_namespace, row.event_id, row.player_id) for row in recent),
            max((row.outcome_available_at for row in recent), default=None), role_shift)

    def for_donor(self, row):
        identity = row.id_namespace, row.event_id, row.player_id
        if identity not in self.donor_cache:
            self.donor_cache[identity] = self.for_target(ForecastTarget(
                row.event_id, row.player_id, row.event_start, row.id_namespace))
        return self.donor_cache[identity]


def _rank(week, event_id):
    value = f"{PROTOCOL_ID}|{SEED}|{week}|{event_id}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def inventory_panel(rows, source):
    """Only identity, clocks, feature availability and predeclared lagged summaries."""
    if source["input_file_sha256"] != INPUT_SHA256:
        raise ValueError("DEV003 requires the original registered normalized-panel SHA256")
    games = defaultdict(list)
    for row in rows:
        games[row.event_id].append(row)
    for appearances in games.values():
        if (len({row.event_start for row in appearances}) != 1
                or len({row.team_id for row in appearances}) != 2
                or len({frozenset((row.team_id, row.opponent_id)) for row in appearances}) != 1):
            raise ValueError("source event clocks and both team identities must agree")
    selected, weeks = [], []
    for index in range(WEEKS):
        start = WINDOW_START+timedelta(weeks=index)
        stop = start+timedelta(days=7)
        candidates = [(event, appearances) for event, appearances in games.items()
            if start <= appearances[0].event_start.date() < stop]
        if len(candidates) < GAMES_PER_WEEK:
            raise ValueError("each registered calendar week requires two complete eligible games")
        chosen = sorted(candidates, key=lambda item: (
            _rank(start.isoformat(), item[0]), item[1][0].event_start, item[0]))[:GAMES_PER_WEEK]
        chosen.sort(key=lambda item: (item[1][0].event_start, item[0]))
        week_rows = sorted((row for _, appearances in chosen for row in appearances),
                           key=lambda row: (row.event_start, row.event_id, row.player_id))
        selected.extend((start.isoformat(), row) for row in week_rows)
        weeks.append({"week_start": start.isoformat(), "week_end": (stop-timedelta(days=1)).isoformat(),
            "eligible_games": len(candidates), "selected_appearances": len(week_rows),
            "games": [{"event_id": event, "event_start": stamp(appearances[0].event_start),
                "appearances": len(appearances), "selection_sha256": _rank(start.isoformat(), event)}
                for event, appearances in chosen]})
    if len(selected) > MAX_ROWS:
        raise ValueError("whole selected games exceed 600-row cap; no game is split")
    contexts = LaggedContextIndex(rows)
    target_contexts = [contexts.for_target(ForecastTarget(
        row.event_id, row.player_id, row.event_start, row.id_namespace)) for _, row in selected]
    root = Path(__file__).parent.parent
    exposed_protocol = read_receipt(root/"evidence/research/dev002-protocol.json")
    old_games = {game["event_id"] for week in exposed_protocol["weekly_inventory"] for game in week["games"]}
    overlap = old_games & {row.event_id for _, row in selected}
    old_pilot_rows = sorted((row for row in rows if row.event_start.date().isoformat()
        in ("2025-10-28", "2025-10-29")), key=lambda row: (row.event_start, row.event_id, row.player_id))[:200]
    return selected, {"source": {key: source[key] for key in (
        "input_file_sha256", "input_bytes", "input_rows", "eligible_panel_rows",
        "input_excluded_rows", "input_exclusions", "upstream_exclusions", "minutes_precision_counts")},
        "window_start": WINDOW_START.isoformat(),
        "window_end": (WINDOW_START+timedelta(weeks=WEEKS)-timedelta(days=1)).isoformat(),
        "selection_sha256_UTF8_template": "NBA-ALL13-JOINT-DEV-003|20261020|{week_start}|{event_id}",
        "selection": "lowest_two_hex_SHA256_per_UTC_Monday_Sunday_week_then_chronological_all_appearances",
        "weekly_inventory": weeks, "selected_games": WEEKS*GAMES_PER_WEEK,
        "selected_appearances": len(selected),
        "selected_cohort_identity_sha256": digest([{ "week": week, "event": row.event_id,
            "player": row.player_id, "start": stamp(row.event_start)} for week, row in selected]),
        "prior_history_bands": dict(Counter(context.history_band for context in target_contexts)),
        "lagged_role_shift_appearances": sum(context.role_shift for context in target_contexts),
        "rounded_zero_minute_appearances": sum(row.minutes == 0 for _, row in selected),
        "donors_with_known_lagged_context": sum(contexts.for_donor(row).mean_minutes is not None for row in rows),
        "context_version": CONTEXT_VERSION,
        "known_exposure": {"development_only": True,
            "DEV002_protocol_payload_sha256": digest(exposed_protocol),
            "DEV002_shared_games": sorted(overlap),
            "DEV002_shared_appearances": sum(row.event_id in overlap for _, row in selected),
            "original_R0_pilot_shared_games": len({row.event_id for row in old_pilot_rows}
                                                 & {row.event_id for _, row in selected}),
            "interpretation": "cohort_and_design_overlap_exposed_development_not_confirmation"}}


def implementation_hashes():
    root = Path(__file__).parent.parent
    return {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def protocol_specification(inventory):
    return {"protocol_id": PROTOCOL_ID, "status": "FROZEN_BEFORE_SCORING",
        "evidence_lane": EVIDENCE_LANE, "participation": "CONDITIONAL_ON_APPEARANCE",
        "input_sha256": INPUT_SHA256, "inventory": inventory,
        "implementation_source_sha256": implementation_hashes(),
        "models": MODELS, "registered_candidates": 1, "hyperparameter_searches": 0,
        "cutoff": "event_start_minus90_minutes_freeze00UTC_cutoff_date",
        "availability": "archived_event_start_plus24h_RECONSTRUCTED_not_asof_proof",
        "history": "all_earlier_eligible_appearances_expanding_window",
        "lagged_context": {"version": CONTEXT_VERSION, "history_limit": CONTEXT_APPEARANCES,
            "summary": "arithmetic_mean_reported_minutes_of_latest_up_to5_eligible_appearances",
            "donor_cutoff": "donors_own_T90_daily_freeze_no_own_or_future_row",
            "minimum_history": 1, "unknown_context": "None_never_observed_zero"},
        "kernel_prior": {"bandwidth_reported_minutes": BANDWIDTH_MINUTES,
            "kernel": "exp(-0.5*((target_lagged_context-donor_lagged_context)/8)^2)",
            "donor_weight": "same_28day_recency_weight_times_kernel_known_context_donors_only",
            "league_floor": LEAGUE_FLOOR, "kernel_share": 1-LEAGUE_FLOOR,
            "unknown_donor_context": "retained_in_league_floor_excluded_only_from_kernel_component",
            "personal_history_half_life_days": HALF_LIFE_DAYS,
            "league_prior_appearance_equivalents": PRIOR_APPEARANCES,
            "fallback": "exact_R0_support_for_n0_or_no_known_donors_or_zero_kernel_mass",
            "support": "same_complete_statline_atoms_positive_league_floor_no_tail_repair"},
        "all_markets": list(MARKETS),
        "primary": "per_category_paired_mean_CRPS_RPS_K0_minus_R0_negative_favors_K0",
        "reference_anchor": "L0_scores_descriptive_no_model_selection",
        "bootstrap": {"replicates": BOOTSTRAPS, "seed": SEED, "clusters": WEEKS,
            "unit": "whole_registered_UTC_week_selected_games_and_all_appearances",
            "method": "resample12weeks_with_replacement_ratio_of_sums_to_resampled_row_count",
            "interval": "95_percentile_linear_quantiles_0.025_0.975",
            "refit_in_replicate": False, "multiplicity_adjustment": "none_descriptive_only"},
        "secondary": ["DD_TD_Brier_unsmoothed_log_infinite_status_counts",
            "zero_tail_and50_80_95_interval_coverage_compared_with_predicted_mass",
            "reported_precision_minutes_errors", "full_coherent_joint_outcome_identity_checks"],
        "subgroups": {"history_bands": ["0", "1-3", "4-9", "10+"],
            "overlapping_role_shift": "history>=10_and_abs(mean_last5-minus_mean_preceding5)>=8_reported_minutes",
            "inference": "counts_and_point_diagnostics_only_no_sparse_subgroup_confidence_intervals"},
        "budgets": {"max_rows": MAX_ROWS, "max_seconds": MAX_SECONDS, "max_rss_kib": MAX_RSS_KIB},
        "failure_rule": "abort_whole_no_partial_score_publication_no_post_score_exclusions",
        "claims": {"confirmation": False, "promotion": False, "model_selection": False,
            "true_cold_start_improvement": False, "verified_upcoming_role": False,
            "product_qualification": "UNAVAILABLE", "prospective_paper_evidence": False}}


def validate_protocol(protocol, inventory):
    expected = protocol_specification(inventory)
    if set(protocol) != set(expected) | {"recorded_at", "approved_by"}:
        raise ValueError("protocol needs exact proposed specification plus actual approval clock and owner")
    for key, value in expected.items():
        if protocol[key] != value:
            raise ValueError(f"DEV003 frozen protocol mismatch: {key}")
    if protocol["approved_by"] != "root_integration_owner":
        raise ValueError("DEV003 requires integration-owner approval")
    if utc(protocol["recorded_at"]) > datetime.now(timezone.utc):
        raise ValueError("protocol approval clock is in the future")


@dataclass(frozen=True)
class WorkloadForecast:
    target: ForecastTarget
    issued_at: datetime
    trained_through: datetime
    input_sha256: str
    support: tuple
    player_history_count: int
    pool_history_count: int
    fallback: str | None

    def marginal(self, market):
        return JointForecast.marginal(self, market)


class WorkloadPrior:
    def __init__(self, rows):
        self.pools = DailyPool(rows)
        self.contexts = LaggedContextIndex(rows)
        self.donor_context_hashes = {}
        self.daily_donor_contexts = {}

    def forecast(self, target, reference):
        if not isinstance(reference, JointForecast) or reference.target != target:
            raise ValueError("R0 reference and workload target must agree")
        rows, league_support, trained, pool_hash = self.pools.get(target)
        context = self.contexts.for_target(target)
        if context.history_count != reference.player_history_count:
            raise ValueError("context and R0 training populations disagree")
        if target.history_freeze not in self.daily_donor_contexts:
            records = []
            daily_contexts = {}
            for row in rows:
                donor_context = self.contexts.for_donor(row)
                identity = row.event_id, row.player_id
                daily_contexts[identity] = donor_context
                records.append({"identity": list(identity), "context": donor_context.to_record()})
            self.daily_donor_contexts[target.history_freeze] = daily_contexts
            self.donor_context_hashes[target.history_freeze] = digest(records)
        kernel = {}
        for identity, donor_context in self.daily_donor_contexts[target.history_freeze].items():
            if context.mean_minutes is not None and donor_context.mean_minutes is not None:
                kernel[identity] = math.exp(-0.5*((context.mean_minutes-donor_context.mean_minutes)/BANDWIDTH_MINUTES)**2)
        league = {(item.source_event_id, item.source_player_id): item for item in league_support}
        kernel_mass = math.fsum(league[key].weight*value for key, value in kernel.items() if key in league)
        if context.mean_minutes is None:
            fallback = "N0_EXACT_R0"
        elif not kernel:
            fallback = "NO_KNOWN_DONOR_CONTEXT_EXACT_R0"
        elif kernel_mass == 0:
            fallback = "ZERO_KERNEL_MASS_EXACT_R0"
        else:
            fallback = None
        if not math.isfinite(kernel_mass):
            raise ValueError("nonfinite workload kernel mass")
        if fallback:
            support = reference.support
        else:
            own_weights = { (row.event_id, row.player_id):
                2**(-(target.cutoff-row.event_start).total_seconds()/86400/HALF_LIFE_DAYS)
                for row in rows if row.player_id == target.player_id}
            denominator = PRIOR_APPEARANCES+math.fsum(own_weights.values())
            support = tuple(WeightedOutcome(item.source_event_id, item.source_player_id, item.line,
                (own_weights.get(key, 0)+PRIOR_APPEARANCES*(LEAGUE_FLOOR*item.weight
                    +(1-LEAGUE_FLOOR)*item.weight*kernel.get(key, 0)/kernel_mass))/denominator)
                for key, item in league.items())
        if not math.isclose(math.fsum(item.weight for item in support), 1, abs_tol=1e-12, rel_tol=0):
            raise ValueError("workload distribution must sum to one")
        return WorkloadForecast(target, datetime.now(timezone.utc), trained,
            digest({"model_version": KERNEL_VERSION, "R0_input_sha256": reference.input_sha256,
                "target": target.to_record(), "context": context.to_record(),
                "daily_pool_sha256": pool_hash,
                "donor_context_sha256": self.donor_context_hashes[target.history_freeze],
                "bandwidth": BANDWIDTH_MINUTES, "league_floor": LEAGUE_FLOOR,
                "fallback": fallback}), support, reference.player_history_count, len(rows), fallback)


def _linear_quantile(values, probability):
    values = sorted(values)
    position = (len(values)-1)*probability
    index = math.floor(position)
    return values[index]+(position-index)*(values[min(index+1, len(values)-1)]-values[index])


def paired_bootstrap(week_sums, week_counts):
    if len(week_sums) != WEEKS or len(week_counts) != WEEKS or any(count <= 0 for count in week_counts):
        raise ValueError("paired bootstrap requires twelve complete positive-sized week clusters")
    rng = random.Random(SEED)
    draws = {market: [] for market in MARKETS}
    for _ in range(BOOTSTRAPS):
        indices = [rng.randrange(WEEKS) for _ in range(WEEKS)]
        n = sum(week_counts[index] for index in indices)
        for market in MARKETS:
            draws[market].append(math.fsum(week_sums[index][market] for index in indices)/n)
    return {market: {"mean_difference_K0_minus_R0": math.fsum(w[market] for w in week_sums)/sum(week_counts),
        "cluster_percentile95_lower": _linear_quantile(draws[market], 0.025),
        "cluster_percentile95_upper": _linear_quantile(draws[market], 0.975),
        "interpretation": "negative_favors_K0_descriptive_exposed_development_only"} for market in MARKETS}


def _budget(started):
    if time.perf_counter()-started > MAX_SECONDS:
        raise ValueError("DEV003 exceeds 900-second wall budget; abort whole run")
    if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > MAX_RSS_KIB:
        raise ValueError("DEV003 exceeds 512-MiB peak RSS budget; abort whole run")


def run_development(rows, selected, inventory, protocol):
    validate_protocol(protocol, inventory)
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc)
    versions_at_start = implementation_hashes()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent.parent,
                          capture_output=True, text=True, check=False).stdout.strip()
    model = WorkloadPrior(rows)
    reports = {name: [] for name in MODELS}
    weekly = {name: defaultdict(list) for name in MODELS}
    grouped = {name: defaultdict(list) for name in MODELS}
    input_hashes = {name: [] for name in MODELS}
    issued = {name: [] for name in MODELS}
    fallbacks = Counter()
    pool_sizes, history_sizes, trained = [], [], []
    for week, observed in selected:
        _budget(started)
        target = ForecastTarget(observed.event_id, observed.player_id, observed.event_start, observed.id_namespace)
        prior_rows, _, _, _ = model.pools.get(target)
        reference = forecast_reference(prior_rows, target)
        forecasts = {"R0": reference, "L0": model.pools.forecast(target), "K0": model.forecast(target, reference)}
        context = model.contexts.for_target(target)
        if context.history_count == 0 and forecasts["K0"].support is not reference.support:
            raise ValueError("cold-start fallback must reuse exact R0 support")
        fallbacks[forecasts["K0"].fallback or "KERNEL_PRIOR"] += 1
        for name, forecast in forecasts.items():
            report = evaluate_forecast(forecast, observed.primitive_line())
            report["model_version"] = MODELS[name]
            reports[name].append(report)
            weekly[name][week].append(report)
            grouped[name][f"history_{context.history_band}"].append(report)
            if context.role_shift:
                grouped[name]["overlapping_lagged_role_shift"].append(report)
            input_hashes[name].append(forecast.input_sha256)
            issued[name].append(forecast.issued_at)
        pool_sizes.append(reference.pool_history_count)
        history_sizes.append(reference.player_history_count)
        trained.append(reference.trained_through)
        _budget(started)
    week_names = [week["week_start"] for week in inventory["weekly_inventory"]]
    week_sums = [{market: math.fsum(k["categories"][market]["crps"]-r["categories"][market]["crps"]
        for k, r in zip(weekly["K0"][week], weekly["R0"][week])) for market in MARKETS} for week in week_names]
    week_counts = [len(weekly["R0"][week]) for week in week_names]
    paired = paired_bootstrap(week_sums, week_counts)
    aggregate = {name: aggregate_reports(values) for name, values in reports.items()}
    for market in ("DD", "TD"):
        paired[market]["brier_mean_difference_K0_minus_R0"] = (
            aggregate["K0"]["categories"][market]["mean_brier"]-aggregate["R0"]["categories"][market]["mean_brier"])
        paired[market]["binary_Brier_interval_equals_CRPS_interval"] = True
        logs = [aggregate[name]["categories"][market]["mean_log_loss"] for name in ("K0", "R0")]
        paired[market]["mean_log_loss_difference_K0_minus_R0"] = logs[0]-logs[1] if None not in logs else None
        paired[market]["log_difference_status"] = "FINITE" if None not in logs else "UNAVAILABLE_INFINITE_MODEL_LOSS"
    if implementation_hashes() != versions_at_start:
        raise ValueError("implementation changed during registered run; no score publication")
    _budget(started)
    return {"protocol_id": PROTOCOL_ID, "protocol_payload_sha256": digest(protocol),
        "evidence_lane": EVIDENCE_LANE, "stage": "EXPOSED_CHRONOLOGICAL_DEVELOPMENT_ONLY",
        "run_started_at": stamp(started_at), "run_finished_at": stamp(datetime.now(timezone.utc)),
        "runtime_wall_seconds": time.perf_counter()-started,
        "process_peak_rss_linux_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "repository_head_at_execution": head, "implementation_source_sha256": versions_at_start,
        "inventory": inventory, "scored_appearances_per_model": len(selected), "post_score_exclusions": 0,
        "K0_fallback_counts": dict(fallbacks), "training_pool_rows_min": min(pool_sizes),
        "training_pool_rows_max": max(pool_sizes), "player_history_min": min(history_sizes),
        "player_history_max": max(history_sizes), "trained_through_min": stamp(min(trained)),
        "trained_through_max": stamp(max(trained)),
        "models": {name: {"version": MODELS[name], **aggregate[name],
            "forecast_input_hash_sequence_sha256": digest(input_hashes[name]),
            "actual_issuance_min": stamp(min(issued[name])), "actual_issuance_max": stamp(max(issued[name]))}
            for name in MODELS},
        "weekly_metrics": {name: {week: aggregate_reports(weekly[name][week]) for week in week_names} for name in MODELS},
        "subgroup_point_diagnostics": {name: {group: {"rows": len(values), **aggregate_reports(values)}
            for group, values in grouped[name].items()} for name in MODELS},
        "subgroup_inference": "point_diagnostics_only_overlapping_role_group_not_an_additive_population",
        "paired_per_category_crps": paired, "bootstrap": {"replicates": BOOTSTRAPS, "seed": SEED,
            "clusters": WEEKS, "week_counts": week_counts, "multiplicity_adjustment": "none"},
        "claims": protocol["claims"],
        "limitations": ["Development informed by exposed DEV002; no confirmation or model-selection rule",
            "True zero-history cases have exact R0 fallback, not a new cold-start solution",
            "Lagged rounded workload is not verified role, injury, lineup, pace or exact-duration information",
            "Finite empirical support remains finite; the positive floor is not an unseen-tail model",
            "Sparse game sample and twelve clusters; bootstrap omits refitting and cross-week dependence",
            "No multiplicity correction or sparse-subgroup confidence claims",
            "No DNP, current quote, same-game ticket, settlement, qualification or prospective paper evidence"]}


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
                raise ValueError("scoring requires immutable integration-owner-approved --protocol")
            resource.setrlimit(resource.RLIMIT_AS, (MAX_RSS_KIB*1024, MAX_RSS_KIB*1024))
            result = run_development(rows, selected, inventory, read_receipt(args.protocol))
        result["invocation"] = [sys.executable, "-m", "multisport_lab.development_003", *sys.argv[1:]]
        write_receipt(args.output, result, max_bytes=8*1024*1024)
        print(json.dumps({"output": str(args.output), "stage": result["stage"],
                          "scored_appearances_per_model": result.get("scored_appearances_per_model", 0)}))
    except (ValueError, OSError, MemoryError) as error:
        parser.error(str(error) or "memory budget exhausted; no partial score publication")


if __name__ == "__main__":
    main()

"""One frozen, untuned offline S0 count-support comparison; never live issuance.

Inventory reads identities/clocks only. Actual scoring requires the exact frozen
protocol and a separately recorded independent readback of its pushed commit.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
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

from .baseline import (COUNT_FIELDS, EVIDENCE_LANE, MARKETS, MODEL_VERSION,
                       ForecastTarget, evaluate_forecast, forecast_reference)
from .development_003 import KERNEL_VERSION, LaggedContextIndex, WorkloadPrior
from .integrity import digest, read_receipt, stamp, utc, write_receipt
from .research_pilot import aggregate_reports, read_normalized_panel


PROTOCOL_ID = "NBA-ALL13-JOINT-DEV-005"
S0_VERSION = "nba_joint_count_support_s0_v1"
INPUT_SHA256 = "489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c"
INPUT_RECORD_ID = "dfa1c4345495eb3aa6b203f2e8309c89c112b6b78a36cd3d2c603d390776b6fc"
WINDOW_START = date(2026, 1, 19)
WEEKS = 8
GAMES_PER_WEEK = 2
SEED = 20261020005
BOOTSTRAPS = 2000
MAX_ROWS = 500
MAX_SECONDS = 900
MAX_RSS_KIB = 512*1024
MAX_RESULT_BYTES = 16*1024*1024
MODELS = {"R0": MODEL_VERSION, "K0": KERNEL_VERSION, "S0": S0_VERSION}
SOURCE_FILES = ("multisport_lab/development_005.py", "multisport_lab/count_support.py",
    "multisport_lab/development_003.py", "multisport_lab/development_002.py",
    "multisport_lab/baseline.py", "multisport_lab/research_pilot.py",
    "multisport_lab/nba_data.py", "multisport_lab/basketball.py", "multisport_lab/integrity.py",
    "tests/test_development_005.py", "tests/test_count_support.py", "scripts/verify_dev005_result.py")
INTERVAL_LEVELS = (0.5, 0.8, 0.95)
# Compact arrays retain all sufficient per-row data for independent aggregation.
CATEGORY_COLUMNS = ("observed", "mean", "median", "crps", "mean_absolute_error",
    "mean_squared_error", "log_loss", "observed_probability", "zero_probability",
    "probability_above_upper95", "observed_above_upper95")
INTERVAL_COLUMNS = ("lower", "upper", "predicted_mass", "covered", "width")


def _rank(week, event_id):
    return hashlib.sha256(f"{PROTOCOL_ID}|{SEED}|{week}|{event_id}".encode()).hexdigest()


def inventory_panel(rows, source):
    """No target counts or forecast scores affect identity/time game selection."""
    if source["input_file_sha256"] != INPUT_SHA256:
        raise ValueError("DEV005 requires the registered full normalized-panel SHA256")
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
        raise ValueError("whole selected games exceed 500-row cap; no game is split")
    contexts = LaggedContextIndex(rows)
    target_contexts = [contexts.for_target(ForecastTarget(
        row.event_id, row.player_id, row.event_start, row.id_namespace)) for _, row in selected]
    root = Path(__file__).parent.parent
    exposure = {}
    for label, filename in (("DEV002", "dev002-protocol.json"), ("DEV003", "dev003-protocol.json")):
        previous = read_receipt(root/"evidence/research"/filename)
        inventory = previous.get("inventory", previous)
        previous_games = {g["event_id"] for w in inventory["weekly_inventory"] for g in w["games"]}
        overlap = previous_games & {r.event_id for _, r in selected}
        exposure[label] = {"protocol_payload_sha256": digest(previous), "shared_games": sorted(overlap),
            "shared_appearances": sum(r.event_id in overlap for _, r in selected)}
    pilot = sorted((r for r in rows if r.event_start.date().isoformat() in ("2025-10-28", "2025-10-29")),
                   key=lambda r: (r.event_start, r.event_id, r.player_id))[:200]
    pilot_overlap = {r.event_id for r in pilot} & {r.event_id for _, r in selected}
    exposure["R0_pilot"] = {"shared_games": sorted(pilot_overlap),
        "shared_appearances": sum(r.event_id in pilot_overlap for _, r in selected)}
    return selected, {"source": {key: source[key] for key in (
        "input_file_sha256", "input_bytes", "input_rows", "eligible_panel_rows",
        "input_excluded_rows", "input_exclusions", "upstream_exclusions", "minutes_precision_counts")},
        "retained_input_record_id": INPUT_RECORD_ID,
        "window_start": WINDOW_START.isoformat(),
        "window_end": (WINDOW_START+timedelta(weeks=WEEKS)-timedelta(days=1)).isoformat(),
        "selection_sha256_UTF8_template": f"{PROTOCOL_ID}|{SEED}|{{week_start}}|{{event_id}}",
        "selection": "lowest_two_hex_SHA256_per_UTC_Monday_Sunday_week_then_chronological_all_appearances",
        "weekly_inventory": weeks, "selected_games": WEEKS*GAMES_PER_WEEK,
        "selected_appearances": len(selected),
        "selected_cohort_identity_sha256": digest([{"week": week, "event": row.event_id,
            "player": row.player_id, "start": stamp(row.event_start)} for week, row in selected]),
        "prior_history_bands": dict(Counter(c.history_band for c in target_contexts)),
        "rounded_zero_minute_appearances": sum(r.minutes == 0 for _, r in selected),
        "known_exposure": {"previous_comparisons": exposure, "development_only": True,
            "full_archive_previously_normalized": True,
            "interpretation": "new_consecutive_window_but_archive_and_previous_development_informed_design_not_confirmation"}}


def implementation_hashes():
    root = Path(__file__).parent.parent
    return {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def protocol_specification(inventory):
    from .count_support import (PRIMITIVE_TAIL_MASS, FIRST_TAIL_MOMENT,
        MASS_ROUNDOFF_TOLERANCE, DEPENDENCE_OMISSION_TOLERANCE)
    return {"protocol_id": PROTOCOL_ID, "status": "FROZEN_BEFORE_SCORING",
        "evidence_lane": EVIDENCE_LANE, "participation": "CONDITIONAL_ON_APPEARANCE",
        "input_sha256": INPUT_SHA256, "inventory": inventory,
        "implementation_source_sha256": implementation_hashes(), "models": MODELS,
        "registered_candidates": 1, "hyperparameter_searches": 0,
        "cutoff": "event_start_minus90_minutes_freeze00UTC_cutoff_date",
        "availability": "archived_event_start_plus24h_RECONSTRUCTED_not_asof_proof",
        "history": "all_earlier_eligible_appearances_expanding_window_no_truncation",
        "refit": "R0_K0_same_eligible_daily_pool_S0_fits_only_K0_weighted_means_and_effective_sample_size_each_target",
        "candidate": {"mixture_generator_share": 0.1, "empirical_share": 0.9,
            "generator": "eight_independent_negative_binomial_shape2_primitive_counts",
            "generator_mean": "(Neff*K0_primitive_mean+0.5)/(Neff+0.5)",
            "Neff": "1/sum_K0_atom_weight_squared", "gamma_pseudocount": 0.5,
            "gamma_pseudoexposure": 0.5, "support": "all_nonnegative_integer_primitive_vectors",
            "cold_start": "K0_exact_R0_fallback_then_same_S0_mixture_no_new_participation_model",
            "minutes": "exact_K0_marginal_generator_counts_independent_of_K0_minutes_draw",
            "dependence": "0.9_K0_empirical_joint_plus0.1_conditionally_independent_NB_joint",
            "markets": "all14_derived_from_one_primitive_joint_law_no_marginal_splicing"},
        "numerical": {"likelihood": "positive_coefficient_convolution_of_actual_infinite_law_no_floor_no_renormalization",
            "prediction_grid": "training_only_adaptive_tail_mass_and_first_moment_bounds",
            "max_grid": 4096, "CRPS_absolute_tail_error_max": 1e-9,
            "primitive_tail_mass_max": PRIMITIVE_TAIL_MASS,
            "primitive_first_tail_moment_max": FIRST_TAIL_MOMENT,
            "mass_roundoff_tolerance": MASS_ROUNDOFF_TOLERANCE,
            "dependence_omission_tolerance": DEPENDENCE_OMISSION_TOLERANCE,
            "floating_point": "IEEE754_double_roundoff_checked_by_convergence_tests_not_interval_arithmetic_certificate",
            "failure": "retain_failure_no_post_outcome_floor_or_exclusion"},
        "all_markets": list(MARKETS),
        "primary": "per_category_paired_mean_CRPS_RPS_S0_minus_K0_negative_favors_S0",
        "secondary": ["S0_minus_R0_and_K0_minus_R0_descriptive_reference_anchors",
            "DD_TD_Brier_event_counts_unsmoothed_log_and_zero_support_counts",
            "zeros_and50_80_95_interval_actual_coverage_predicted_mass_width",
            "above_upper95_tail_coverage_and_probability", "K0_S0_reported_minutes_identical_within1e-12"],
        "dependence_diagnostic": {"method": "primitive_variogram", "power": 1,
            "pair_weights": "equal1/28", "primitive_scales": "all1_count_units",
            "generator_expected_abs_difference": "mu_i+mu_j-2*sum_survival_i_times_survival_j_with_tail_bound",
            "claim": "within_player_non_strictly_proper_diagnostic_no_cross_player_or_ticket_validation"},
        "bootstrap": {"replicates": BOOTSTRAPS, "seed": SEED, "clusters": WEEKS,
            "unit": "whole_registered_UTC_week_selected_games_all_appearances",
            "method": "resample8weeks_with_replacement_ratio_of_sums_to_resampled_row_count",
            "interval": "95_percentile_linear_quantiles_0.025_0.975",
            "multiplicity": "one_sided_upper_percentile_1_minus0.05_div14_for14_primary_categories",
            "interpretation": "descriptive_sparse8clusters_extreme_Bonferroni_quantile_not_finite_sample_error_guarantee",
            "refit_in_replicate": False},
        "category_research_diagnostic_rule": {"primary_adjusted_upper_below": 0,
            "absolute_actual_minus_predicted_interval_mass_max_each_level": 0.05,
            "absolute_observed_minus_predicted_zero_rate_max": 0.05,
            "observed_minus_predicted_upper95_tail_rate_max": 0.02,
            "DD_TD_min_positive_and_negative_outcomes": 20, "BLK_min_nonzero_outcomes": 20,
            "finite_likelihood_and_error_bounds_required": True,
            "meaning": "exploratory_per_category_requirement_not_model_promotion_or_joint_splicing"},
        "common_workload_guard": {"S0_K0_reported_minutes_absolute_tolerance": 1e-12,
            "K0_95_coverage_absolute_gap_from_predicted_max": 0.03,
            "K0_95_coverage_not_more_than_below_R0": 0.01,
            "failure": "mark_all_category_requirements_failed_no_change_to_frozen_minutes_law"},
        "budgets": {"max_rows": MAX_ROWS, "max_seconds": MAX_SECONDS,
            "max_rss_kib": MAX_RSS_KIB, "max_result_bytes": MAX_RESULT_BYTES,
            "input_max_bytes": 64*1024*1024, "input_max_rows": 100000},
        "failure_rule": "one_registered_run_preserve_failures_no_retuning_or_post_score_exclusions",
        "claims": {"confirmation": False, "promotion": False, "model_selection": False,
            "workload_undercoverage_fixed": False, "product_qualification": "UNAVAILABLE",
            "prospective_paper_evidence": False, "live_activation": False}}


def validate_protocol(protocol, inventory):
    expected = protocol_specification(inventory)
    if set(protocol) != set(expected) | {"recorded_at", "approved_by"}:
        raise ValueError("protocol needs exact specification plus actual approval clock and owner")
    for key, value in expected.items():
        if protocol[key] != value:
            raise ValueError(f"DEV005 frozen protocol mismatch: {key}")
    if protocol["approved_by"] != "root_integration_owner":
        raise ValueError("DEV005 requires integration-owner approval after independent review")
    if utc(protocol["recorded_at"]) > datetime.now(timezone.utc):
        raise ValueError("protocol approval clock is in the future")


def validate_readback(readback, protocol):
    if (readback.get("independent_readback") is not True
            or readback.get("reviewed_by") != "support_review"
            or readback.get("protocol_payload_sha256") != digest(protocol)
            or readback.get("implementation_source_sha256") != implementation_hashes()):
        raise ValueError("DEV005 requires independent frozen remote source/protocol readback")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent.parent,
        capture_output=True, text=True, check=True).stdout.strip()
    if readback.get("commit") != head:
        raise ValueError("execution HEAD differs from independently recovered frozen commit")
    if utc(readback["recorded_at"]) > datetime.now(timezone.utc):
        raise ValueError("readback clock is in the future")
    if utc(readback["recorded_at"]) < utc(protocol["recorded_at"]):
        raise ValueError("readback clock precedes frozen protocol approval")


def _quantile(values, probability):
    values = sorted(values)
    position = (len(values)-1)*probability
    index = math.floor(position)
    return values[index]+(position-index)*(values[min(index+1, len(values)-1)]-values[index])


def paired_bootstrap(week_sums, week_counts, label="S0_minus_K0"):
    if len(week_sums) != WEEKS or len(week_counts) != WEEKS or any(n <= 0 for n in week_counts):
        raise ValueError("paired bootstrap requires eight complete positive-sized week clusters")
    rng = random.Random(SEED)
    draws = {market: [] for market in MARKETS}
    for _ in range(BOOTSTRAPS):
        indices = [rng.randrange(WEEKS) for _ in range(WEEKS)]
        n = sum(week_counts[i] for i in indices)
        for market in MARKETS:
            draws[market].append(math.fsum(week_sums[i][market] for i in indices)/n)
    return {market: {"mean_difference_"+label: math.fsum(w[market] for w in week_sums)/sum(week_counts),
        "cluster_percentile95_lower": _quantile(draws[market], 0.025),
        "cluster_percentile95_upper": _quantile(draws[market], 0.975),
        "one_sided_Bonferroni14_upper": _quantile(draws[market], 1-0.05/len(MARKETS)),
        "interpretation": "descriptive_development_sparse8clusters_no_finite_sample_familywise_guarantee"}
        for market in MARKETS}


def compact_report(report):
    return {market: [[report["categories"][market][key] for key in CATEGORY_COLUMNS],
        [[report["categories"][market]["intervals"][str(level)][key] for key in INTERVAL_COLUMNS]
         for level in INTERVAL_LEVELS],
        ([report["categories"][market]["probability"], report["categories"][market]["brier"]]
         if market in ("DD", "TD") else None)] for market in MARKETS}


def scalar_bootstrap(week_sums, week_counts):
    """Shared registered week resamples for a scalar score/rate, no refitting."""
    if len(week_sums) != WEEKS or any(n <= 0 for n in week_counts):
        raise ValueError("scalar uncertainty requires eight positive-sized week clusters")
    rng = random.Random(SEED)
    draws = []
    for _ in range(BOOTSTRAPS):
        indices = [rng.randrange(WEEKS) for _ in range(WEEKS)]
        draws.append(math.fsum(week_sums[i] for i in indices)/sum(week_counts[i] for i in indices))
    return {"mean": math.fsum(week_sums)/sum(week_counts),
        "cluster_percentile95_lower": _quantile(draws, 0.025),
        "cluster_percentile95_upper": _quantile(draws, 0.975),
        "interpretation": "descriptive_sparse8weeks_no_refit_or_binomial_independence_claim"}


def _budget(started):
    if time.perf_counter()-started > MAX_SECONDS:
        raise ValueError("DEV005 exceeds 900-second wall budget; retain failed trial")
    if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > MAX_RSS_KIB:
        raise ValueError("DEV005 exceeds 512-MiB RSS budget; retain failed trial")


def _guards(category, primary, observed, market, workload_failures=()):
    failures = list(workload_failures)
    if primary["one_sided_Bonferroni14_upper"] >= 0:
        failures.append("PRIMARY_ADJUSTED_UPPER_NOT_NEGATIVE")
    if category["zero_support_log_loss_count"]:
        failures.append("NONFINITE_LIKELIHOOD")
    if abs(category["observed_zero_rate"]-category["mean_predicted_zero_probability"]) > 0.05:
        failures.append("ZERO_CALIBRATION_GAP_GT0.05")
    if any(abs(interval["observed_coverage"]-interval["mean_predicted_mass"]) > 0.05
           for interval in category["intervals"].values()):
        failures.append("INTERVAL_CALIBRATION_GAP_GT0.05")
    if (category["observed_above_upper95_rate"]-
           category["mean_predicted_probability_above_upper95"]) > 0.02:
        failures.append("UPPER95_TAIL_GAP_GT0.02")
    if market in ("DD", "TD") and min(sum(observed), len(observed)-sum(observed)) < 20:
        failures.append("RARE_BINARY_COUNTS_LT20_POSITIVE_OR_NEGATIVE")
    if market == "BLK" and sum(x != 0 for x in observed) < 20:
        failures.append("BLK_NONZERO_COUNT_LT20")
    return {"all_exploratory_requirements_met": not failures, "failed_requirements": failures,
        "observed_positive_count": sum(x > 0 for x in observed),
        "observed_zero_count": sum(x == 0 for x in observed),
        "claim": "no_model_promotion_no_marginal_splicing"}


def run_development(rows, selected, inventory, protocol, readback=None):
    """Programmatic synthetic tests may omit readback; real CLI cannot."""
    from .count_support import CountSupportForecast, evaluate_count_support, empirical_variogram_score
    validate_protocol(protocol, inventory)
    if readback is not None:
        validate_readback(readback, protocol)
    started, started_at = time.perf_counter(), datetime.now(timezone.utc)
    versions = implementation_hashes()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent.parent,
        capture_output=True, text=True, check=True).stdout.strip()
    model = WorkloadPrior(rows)
    reports = {name: [] for name in MODELS}
    weekly = {name: defaultdict(list) for name in MODELS}
    variograms = {name: [] for name in MODELS}
    records, fallback, numerical = [], Counter(), []
    pool_sizes, history_sizes, trained = [], [], []
    for week, observed in selected:
        _budget(started)
        target = ForecastTarget(observed.event_id, observed.player_id, observed.event_start, observed.id_namespace)
        prior, _, _, _ = model.pools.get(target)
        reference = forecast_reference(prior, target)
        kernel = model.forecast(target, reference)
        candidate = CountSupportForecast(kernel)
        minute_weights = defaultdict(list)
        for item in kernel.support:
            minute_weights[item.line.minutes].append(item.weight)
        exact_minutes = {value: math.fsum(weights) for value, weights in sorted(minute_weights.items())}
        if candidate.reported_minutes_marginal() != exact_minutes:
            raise ValueError("S0 changed unchanged K0 reported-minute predictive distribution")
        forecasts = {"R0": reference, "K0": kernel, "S0": candidate}
        actual = observed.primitive_line()
        current = {"R0": evaluate_forecast(reference, actual), "K0": evaluate_forecast(kernel, actual)}
        current["S0"] = evaluate_count_support(candidate, actual, k0_report=current["K0"])
        if current["S0"]["minutes_diagnostics"] != current["K0"]["minutes_diagnostics"]:
            raise ValueError("S0 changed unchanged K0 reported-minute diagnostics")
        if current["S0"]["minutes_mean"] != current["K0"]["minutes_mean"]:
            raise ValueError("S0 changed unchanged K0 reported-minute mean")
        current_variograms = {"R0": empirical_variogram_score(reference, actual),
            "K0": empirical_variogram_score(kernel, actual), "S0": candidate.variogram_score(actual)}
        for name, report in current.items():
            report["model_version"] = MODELS[name]
            reports[name].append(report)
            weekly[name][week].append(report)
            variograms[name].append(current_variograms[name])
        numerical.append(current["S0"].get("numerical_diagnostics", {}))
        context = model.contexts.for_target(target)
        fallback[kernel.fallback or "KERNEL_PRIOR"] += 1
        records.append({"week": week, "event_id": observed.event_id, "player_id": observed.player_id,
            "event_start": stamp(observed.event_start), "cutoff": stamp(target.cutoff),
            "history_freeze": stamp(target.history_freeze), "trained_through": stamp(reference.trained_through),
            "pool_rows": reference.pool_history_count, "personal_rows": reference.player_history_count,
            "history_band": context.history_band, "K0_fallback": kernel.fallback,
            "forecast_input_sha256": {n: forecasts[n].input_sha256 for n in MODELS},
            "generation_clocks": {n: stamp(forecasts[n].issued_at) for n in MODELS},
            "categories": {n: compact_report(current[n]) for n in MODELS},
            "primitive_variogram_power1": current_variograms,
            "reported_minutes": {n: {"observed": current[n]["observed_minutes"],
                "mean": current[n]["minutes_mean"], "diagnostics": current[n]["minutes_diagnostics"]}
                for n in MODELS},
            "reported_minutes_K0_S0_diagnostics_identical": True,
            "S0_numerical_diagnostics": numerical[-1],
            "S0_dependence_diagnostics": candidate.dependence_diagnostics,
            "S0_fitting_metadata": candidate.fitting_metadata()})
        pool_sizes.append(reference.pool_history_count)
        history_sizes.append(reference.player_history_count)
        trained.append(reference.trained_through)
        _budget(started)
    week_names = [w["week_start"] for w in inventory["weekly_inventory"]]
    counts = [len(weekly["R0"][w]) for w in week_names]
    comparisons = {}
    for first, second in (("S0", "K0"), ("S0", "R0"), ("K0", "R0")):
        sums = [{m: math.fsum(a["categories"][m]["crps"]-b["categories"][m]["crps"]
            for a, b in zip(weekly[first][w], weekly[second][w])) for m in MARKETS} for w in week_names]
        comparisons[first+"_minus_"+second] = paired_bootstrap(sums, counts, first+"_minus_"+second)
    aggregates = {name: aggregate_reports(values) for name, values in reports.items()}
    for name in MODELS:
        for market in MARKETS:
            aggregates[name]["categories"][market]["finite_probability_underflow_count"] = sum(
                r["categories"][market].get("probability_underflow", False) for r in reports[name])
    binary_uncertainty = {}
    for market in ("DD", "TD"):
        binary_uncertainty[market] = {"observed_event_rate": scalar_bootstrap([
            math.fsum(r["categories"][market]["observed"] for r in weekly["R0"][w])
            for w in week_names], counts), "predicted_probability": {
            name: scalar_bootstrap([math.fsum(r["categories"][market]["probability"]
                for r in weekly[name][w]) for w in week_names], counts) for name in MODELS}}
    dependence_uncertainty = {}
    for first, second in (("S0", "K0"), ("S0", "R0"), ("K0", "R0")):
        dependence_uncertainty[first+"_minus_"+second] = scalar_bootstrap([
            math.fsum(r["primitive_variogram_power1"][first]-r["primitive_variogram_power1"][second]
                for r in records if r["week"] == w) for w in week_names], counts)
    k95 = aggregates["K0"]["minutes"]["intervals"]["0.95"]
    r95 = aggregates["R0"]["minutes"]["intervals"]["0.95"]
    workload_failures = []
    if abs(k95["observed_coverage"]-k95["mean_predicted_mass"]) > 0.03:
        workload_failures.append("COMMON_K0_WORKLOAD95_CALIBRATION_GAP_GT0.03")
    if k95["observed_coverage"] < r95["observed_coverage"]-0.01:
        workload_failures.append("COMMON_K0_WORKLOAD95_COVERAGE_GT0.01_BELOW_R0")
    primary = comparisons["S0_minus_K0"]
    for market in ("DD", "TD"):
        primary[market]["brier_mean_difference_S0_minus_K0"] = (
            aggregates["S0"]["categories"][market]["mean_brier"]-
            aggregates["K0"]["categories"][market]["mean_brier"])
        primary[market]["binary_Brier_interval_equals_CRPS_interval"] = True
    if implementation_hashes() != versions:
        raise ValueError("implementation changed during registered run; retain failure")
    _budget(started)
    return {"protocol_id": PROTOCOL_ID, "protocol_payload_sha256": digest(protocol),
        "stage": "EXPOSED_CHRONOLOGICAL_DEVELOPMENT_ONLY", "evidence_lane": EVIDENCE_LANE,
        "run_started_at": stamp(started_at), "run_finished_at": stamp(datetime.now(timezone.utc)),
        "runtime_wall_seconds": time.perf_counter()-started,
        "process_peak_rss_linux_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "repository_head_at_execution": head, "implementation_source_sha256": versions,
        "independent_remote_readback": readback, "inventory": inventory,
        "scored_appearances_per_model": len(selected), "post_score_exclusions": 0,
        "K0_fallback_counts": dict(fallback), "training_pool_rows_min": min(pool_sizes),
        "training_pool_rows_max": max(pool_sizes), "player_history_min": min(history_sizes),
        "player_history_max": max(history_sizes), "trained_through_min": stamp(min(trained)),
        "trained_through_max": stamp(max(trained)),
        "models": {n: {"version": MODELS[n], **aggregates[n],
            "primitive_variogram_power1_mean": math.fsum(variograms[n])/len(selected)} for n in MODELS},
        "weekly_metrics": {n: {w: aggregate_reports(weekly[n][w]) for w in week_names} for n in MODELS},
        "paired_per_category_crps": comparisons,
        "DD_TD_week_cluster_uncertainty": binary_uncertainty,
        "primitive_variogram_paired_week_cluster_uncertainty": dependence_uncertainty,
        "category_exploratory_requirements": {m: _guards(aggregates["S0"]["categories"][m], primary[m],
            [r["categories"][m]["observed"] for r in reports["S0"]], m, workload_failures) for m in MARKETS},
        "common_workload_guard": {"failed_requirements": workload_failures,
            "all_requirements_met": not workload_failures,
            "S0_K0_all_reported_minute_outputs_identical": True},
        "bootstrap": {"replicates": BOOTSTRAPS, "seed": SEED, "clusters": WEEKS, "week_counts": counts},
        "row_encoding": {"category_scalar_columns": list(CATEGORY_COLUMNS),
            "interval_levels": list(INTERVAL_LEVELS), "interval_columns": list(INTERVAL_COLUMNS),
            "binary_extra_columns": ["probability", "brier"],
            "category_value_layout": "[scalar_values,interval_arrays,binary_extra_or_null]"},
        "row_records": records, "reported_minutes_S0_K0_diagnostics_identical_count": len(selected),
        "claims": protocol["claims"], "limitations": [
            "Exposed archive and previous development informed design; no confirmation or live issuance",
            "Eight week clusters and extreme adjusted bootstrap tail are fragile descriptive uncertainty",
            "K0 reported-minute marginal is unchanged; workload undercoverage is not fixed",
            "NB lane assumes independent primitive counts and weakens empirical dependence",
            "Conditional appearance excludes DNP; no participation or cross-player law",
            "Finite likelihood alone does not establish calibration or qualification",
            "No post-score exclusions, retuning, category splicing, tickets, settlement or activation"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--readback", type=Path)
    parser.add_argument("--inventory-only", action="store_true")
    args = parser.parse_args()
    attempt_path = (args.protocol.with_name(args.protocol.stem+"-attempt.json")
                    if args.protocol else args.output.with_name(args.output.stem+"-attempt.json"))
    if args.output.exists() or (not args.inventory_only and attempt_path.exists()):
        parser.error("registered trial output already exists; preserve it instead of overwriting")
    started_at = stamp(datetime.now(timezone.utc))
    try:
        rows, source = read_normalized_panel(args.input)
        selected, inventory = inventory_panel(rows, source)
        if args.inventory_only:
            result = {"stage": "PRE_SCORING_INVENTORY_ONLY", "recorded_at": started_at,
                "model_evaluated": False, "inventory": inventory,
                "proposed_protocol": protocol_specification(inventory)}
        else:
            if args.protocol is None or args.readback is None:
                raise ValueError("scoring requires frozen --protocol and independent remote --readback")
            protocol, readback = read_receipt(args.protocol), read_receipt(args.readback)
            validate_protocol(protocol, inventory)
            validate_readback(readback, protocol)
            resource.setrlimit(resource.RLIMIT_AS, (MAX_RSS_KIB*1024, MAX_RSS_KIB*1024))
            claim = {"protocol_id": PROTOCOL_ID, "stage": "REGISTERED_TRIAL_CLAIMED",
                "claimed_at": stamp(datetime.now(timezone.utc)), "protocol_payload_sha256": digest(protocol),
                "frozen_commit": readback["commit"], "output": str(args.output),
                "input_sha256": source["input_file_sha256"], "no_retuning_authorized": True}
            attempt_path.parent.mkdir(parents=True, exist_ok=True)
            with attempt_path.open("x", encoding="utf-8") as handle:
                json.dump(claim, handle, sort_keys=True, indent=2, allow_nan=False)
                handle.write("\n")
            result = run_development(rows, selected, inventory, protocol, readback)
        result["invocation"] = [sys.executable, "-m", "multisport_lab.development_005", *sys.argv[1:]]
        write_receipt(args.output, result, max_bytes=MAX_RESULT_BYTES)
        print(json.dumps({"output": str(args.output), "stage": result["stage"],
                          "scored_appearances_per_model": result.get("scored_appearances_per_model", 0)}))
    except (Exception, KeyboardInterrupt) as error:
        failure = {"protocol_id": PROTOCOL_ID, "stage": "FAILED_REGISTERED_TRIAL" if attempt_path.exists()
            else "FAILED_PREFLIGHT_OR_INVENTORY", "started_at": started_at,
            "failed_at": stamp(datetime.now(timezone.utc)), "error": str(error) or "memory budget exhausted",
            "error_type": type(error).__name__,
            "invocation": [sys.executable, "-m", "multisport_lab.development_005", *sys.argv[1:]],
            "no_retuning_authorized": True, "partial_scores_published": False}
        write_receipt(args.output, failure, max_bytes=MAX_RESULT_BYTES)
        parser.exit(2, json.dumps(failure)+"\n")


if __name__ == "__main__":
    main()

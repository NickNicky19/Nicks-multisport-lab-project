"""Synthetic DEV003 causal/context/coherence checks; no real-data scoring."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import math
import unittest
from unittest.mock import patch

from multisport_lab.baseline import ForecastTarget, HistoricalAppearance, MARKETS, forecast_reference
from multisport_lab.development_003 import (INPUT_SHA256, PROTOCOL_ID, SEED, WINDOW_START,
    LaggedContextIndex, WorkloadPrior, _rank, inventory_panel, paired_bootstrap,
    protocol_specification, run_development, validate_protocol)
from multisport_lab.integrity import canonical


def row(event, player, start, minutes=20, team="1", **changes):
    values = dict(event_id=event, player_id=player, team_id=team,
        opponent_id="2" if team == "1" else "1", event_start=start,
        outcome_available_at=start+timedelta(hours=24), minutes=minutes,
        minutes_precision="rounded_whole_minutes", fg2m=4, fg3m=1, ftm=2,
        rebounds=5, assists=3, turnovers=2, blocks=1, steals=1)
    return HistoricalAppearance(**(values | changes))


def context_history():
    start = datetime(2025, 10, 21, 20, tzinfo=timezone.utc)
    return [row("abase", "a", start, 12), row("bbase", "b", start, 25),
        row("targetprior", "target", start+timedelta(days=1), 20),
        row("adonor", "a", start+timedelta(days=4), 40,
            fg2m=5, fg3m=2, ftm=4, rebounds=10, assists=10),
        row("bdonor", "b", start+timedelta(days=5), 35)]


def target(player="target"):
    return ForecastTarget("new", player, datetime(2025, 11, 2, 20, tzinfo=timezone.utc))


def candidate(rows, selected=None):
    selected = selected or target()
    reference = forecast_reference(rows, selected)
    model = WorkloadPrior(rows)
    return model, reference, model.forecast(selected, reference)


def sample_panel():
    rows = []
    for week in range(12):
        start = datetime.combine(WINDOW_START+timedelta(weeks=week), datetime.min.time(), tzinfo=timezone.utc)
        for game in range(3):
            for team in ("1", "2"):
                rows.append(row(f"w{week}g{game}", f"p{team}", start+timedelta(hours=18+game), team=team))
    source = {"input_file_sha256": INPUT_SHA256, "input_bytes": 1, "input_rows": len(rows),
        "eligible_panel_rows": len(rows), "input_excluded_rows": 0, "input_exclusions": {},
        "upstream_exclusions": {"status": "EXTERNAL_TO_NORMALIZED_INPUT"},
        "minutes_precision_counts": {"rounded_whole_minutes": len(rows)}}
    return rows, source


class Development003Tests(unittest.TestCase):
    def test_donor_context_and_kernel_weights_ignore_its_own_realized_minutes(self):
        rows = context_history()
        changed = [replace(r, minutes=1) if r.event_id == "adonor" else r for r in rows]
        first_model, _, first = candidate(rows)
        changed_model, _, second = candidate(changed)
        self.assertEqual(first_model.contexts.for_donor(rows[3]).mean_minutes, 12)
        self.assertEqual(changed_model.contexts.for_donor(changed[3]).mean_minutes, 12)
        weights = lambda forecast: {(s.source_event_id, s.source_player_id): s.weight for s in forecast.support}
        self.assertEqual(weights(first), weights(second))
        # Earlier donor history IS the feature; changing it alters the kernel.
        prior_changed = [replace(r, minutes=6) if r.event_id == "abase" else r for r in rows]
        _, _, third = candidate(prior_changed)
        self.assertNotEqual(weights(first)["adonor", "a"], weights(third)["adonor", "a"])

    def test_donor_uses_its_own_cutoff_date_and_availability_not_target_cutoff(self):
        donor = row("donor", "a", datetime(2025, 10, 25, 0, 30, tzinfo=timezone.utc), 40)
        before = row("before", "a", datetime(2025, 10, 22, 20, tzinfo=timezone.utc), 8)
        not_available = row("late", "a", datetime(2025, 10, 24, 1, tzinfo=timezone.utc), 35)
        context = LaggedContextIndex([before, not_available, donor]).for_donor(donor)
        self.assertEqual(context.mean_minutes, 8)
        self.assertEqual(context.history_count, 1)
        self.assertEqual(context.source_identities, (("espn", "before", "a"),))
        cutoff = ForecastTarget(donor.event_id, donor.player_id, donor.event_start).history_freeze
        self.assertLessEqual(context.source_available_max, cutoff)

    def test_latest_up_to_five_arithmetic_minutes_and_rounded_zero_are_known(self):
        start = datetime(2025, 10, 21, 20, tzinfo=timezone.utc)
        rows = [row(str(i), "target", start+timedelta(days=2*i), i) for i in range(6)]
        context = LaggedContextIndex(rows).for_target(target())
        self.assertEqual(context.history_count, 6)
        self.assertEqual(context.mean_minutes, 3)
        self.assertEqual(len(context.source_identities), 5)
        zero = LaggedContextIndex([rows[0]]).for_target(target())
        self.assertEqual(zero.mean_minutes, 0)
        self.assertEqual(zero.history_band, "1-3")
        canonical(context.to_record())

    def test_true_cold_start_reuses_exact_r0_support_and_all_marginals(self):
        _, reference, cold = candidate(context_history(), target("cold"))
        self.assertIs(cold.support, reference.support)
        self.assertEqual(cold.fallback, "N0_EXACT_R0")
        for market in MARKETS:
            self.assertEqual(cold.marginal(market), reference.marginal(market))

    def test_empty_known_donor_pool_falls_back_to_r0_not_fabricated_context(self):
        prior = context_history()[2]
        _, reference, forecast = candidate([prior])
        self.assertEqual(forecast.fallback, "NO_KNOWN_DONOR_CONTEXT_EXACT_R0")
        self.assertIs(forecast.support, reference.support)

    def test_support_floor_normalization_full_atoms_and_fourteen_joint_identities(self):
        model, reference, forecast = candidate(context_history())
        self.assertIsNone(forecast.fallback)
        _, league, _, _ = model.pools.get(target())
        league_weights = {(s.source_event_id, s.source_player_id): s.weight for s in league}
        own = math.fsum(2**(-(target().cutoff-r.event_start).total_seconds()/86400/28)
            for r in context_history() if r.player_id == "target")
        historical_lines = {(s.source_event_id, s.source_player_id): s.line for s in reference.support}
        self.assertAlmostEqual(math.fsum(s.weight for s in forecast.support), 1, places=12)
        for sample in forecast.support:
            key = sample.source_event_id, sample.source_player_id
            self.assertGreaterEqual(sample.weight, 0.25*5*league_weights[key]/(own+5))
            self.assertEqual(sample.line, historical_lines[key])
            values = sample.line.market_values()
            self.assertEqual(set(values), set(MARKETS))
            self.assertEqual(values["PTS"], 2*sample.line.fg2m+3*sample.line.fg3m+sample.line.ftm)
            self.assertEqual(values["PRA"], values["PR"]+values["AST"])
            self.assertEqual(values["PRA"], values["RA"]+values["PTS"])
            self.assertEqual(values["PA"], values["PTS"]+values["AST"])
            self.assertEqual(values["BLK+STL"], values["BLK"]+values["STL"])
            self.assertLessEqual(values["TD"], values["DD"])
        self.assertIn(1, forecast.marginal("TD"))

    def test_target_outcome_or_future_history_cannot_enter_context_or_forecast_hash(self):
        rows = context_history()
        selected = target()
        actual = row(selected.event_id, selected.player_id, selected.event_start, 42)
        later = row("future", "target", selected.event_start+timedelta(days=2), 1)
        _, _, expected = candidate(rows)
        _, _, with_future = candidate(rows+[actual, later])
        self.assertEqual(expected.input_sha256, with_future.input_sha256)
        self.assertEqual(expected.support, with_future.support)

    def test_exact_utf8_hash_selection_and_complete_game_cap(self):
        rows, source = sample_panel()
        selected, inventory = inventory_panel(rows, source)
        self.assertEqual(len(selected), 48)
        self.assertEqual(inventory["selected_games"], 24)
        self.assertEqual(inventory["window_end"], "2026-01-18")
        for week in inventory["weekly_inventory"]:
            for game in week["games"]:
                expected = hashlib.sha256(f"{PROTOCOL_ID}|{SEED}|{week['week_start']}|{game['event_id']}".encode("utf-8")).hexdigest()
                self.assertEqual(game["selection_sha256"], expected)
                self.assertEqual(game["appearances"], 2)
        with patch("multisport_lab.development_003.MAX_ROWS", 47):
            with self.assertRaisesRegex(ValueError, "no game is split"):
                inventory_panel(rows, source)

    def test_inventory_source_or_missing_week_fail_without_scoring(self):
        rows, source = sample_panel()
        with self.assertRaisesRegex(ValueError, "SHA256"):
            inventory_panel(rows, source | {"input_file_sha256": "0"*64})
        with self.assertRaisesRegex(ValueError, "each registered"):
            inventory_panel([r for r in rows if not r.event_id.startswith("w11")], source)

    def test_protocol_binds_source_code_kernel_cohort_and_owner_before_scoring(self):
        _, inventory = inventory_panel(*sample_panel())
        proposal = protocol_specification(inventory)
        frozen = proposal | {"recorded_at": "2026-01-01T00:00:00Z", "approved_by": "root_integration_owner"}
        validate_protocol(frozen, inventory)
        self.assertEqual(set(proposal["models"]), {"R0", "L0", "K0"})
        self.assertEqual(proposal["registered_candidates"], 1)
        changed = dict(frozen["kernel_prior"], league_floor=0.5)
        with self.assertRaisesRegex(ValueError, "kernel_prior"):
            validate_protocol(frozen | {"kernel_prior": changed}, inventory)
        changed_hashes = dict(frozen["implementation_source_sha256"])
        changed_hashes["multisport_lab/development_003.py"] = "0"*64
        with self.assertRaisesRegex(ValueError, "implementation_source_sha256"):
            validate_protocol(frozen | {"implementation_source_sha256": changed_hashes}, inventory)

    def test_twelve_week_cluster_bootstrap_preserves_row_weights_and_seed(self):
        counts = list(range(1, 13))
        sums = [{m: -index*n for m in MARKETS} for index, n in enumerate(counts)]
        result = paired_bootstrap(sums, counts)
        expected = -sum(index*n for index, n in enumerate(counts))/sum(counts)
        self.assertAlmostEqual(result["PTS"]["mean_difference_K0_minus_R0"], expected)
        self.assertEqual(result, paired_bootstrap(sums, counts))
        constant = [{m: -2*n for m in MARKETS} for n in counts]
        fixed = paired_bootstrap(constant, counts)["PTS"]
        self.assertEqual(fixed["cluster_percentile95_lower"], -2)
        self.assertEqual(fixed["cluster_percentile95_upper"], -2)
        with self.assertRaisesRegex(ValueError, "twelve"):
            paired_bootstrap(sums[:8], counts[:8])

    def test_synthetic_full_runner_retains_all_models_weeks_and_subgroup_points(self):
        rows, source = sample_panel()
        warmup = datetime(2025, 10, 21, 20, tzinfo=timezone.utc)
        rows += [row("warmup", f"p{team}", warmup, team=team) for team in ("1", "2")]
        source["input_rows"] = source["eligible_panel_rows"] = len(rows)
        selected, inventory = inventory_panel(rows, source)
        frozen = protocol_specification(inventory) | {
            "recorded_at": "2026-01-01T00:00:00Z", "approved_by": "root_integration_owner"}
        result = run_development(rows, selected, inventory, frozen)
        self.assertEqual(result["scored_appearances_per_model"], 48)
        self.assertEqual(result["post_score_exclusions"], 0)
        self.assertEqual(len(result["bootstrap"]["week_counts"]), 12)
        for name in ("R0", "L0", "K0"):
            self.assertEqual(set(result["models"][name]["categories"]), set(MARKETS))
            self.assertTrue(all(c["scored_count"] == 48 for c in result["models"][name]["categories"].values()))
            self.assertEqual(result["models"][name]["categories"]["PTS"]["mean_crps_rps"], 0)
        self.assertFalse(result["claims"]["confirmation"])
        self.assertFalse(result["claims"]["true_cold_start_improvement"])
        canonical(result)


if __name__ == "__main__":
    unittest.main()

"""Synthetic causal registration and evidence tests, never real NBA scoring."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab.baseline import HistoricalAppearance, MARKETS
from multisport_lab.development_005 import (BOOTSTRAPS, INPUT_SHA256, PROTOCOL_ID,
    SEED, WINDOW_START, _guards, _rank, compact_report, implementation_hashes,
    inventory_panel, paired_bootstrap, protocol_specification, run_development,
    validate_protocol, validate_readback)
from multisport_lab.integrity import canonical, digest, read_receipt


def row(event, player, start, team="1", **changes):
    values = dict(event_id=event, player_id=player, team_id=team,
        opponent_id="2" if team == "1" else "1", event_start=start,
        outcome_available_at=start+timedelta(hours=24), minutes=20,
        minutes_precision="rounded_whole_minutes", fg2m=4, fg3m=1, ftm=2,
        rebounds=5, assists=3, turnovers=2, blocks=1, steals=1)
    return HistoricalAppearance(**(values | changes))


def sample_panel():
    rows = []
    for week in range(8):
        start = datetime.combine(WINDOW_START+timedelta(weeks=week), datetime.min.time(), tzinfo=timezone.utc)
        for game in range(3):
            for team in ("1", "2"):
                rows.append(row(f"w{week}g{game}", f"p{team}", start+timedelta(hours=18+game), team))
    warmup = datetime(2025, 10, 21, 20, tzinfo=timezone.utc)
    rows += [row("warmup", f"p{team}", warmup, team) for team in ("1", "2")]
    source = {"input_file_sha256": INPUT_SHA256, "input_bytes": 1, "input_rows": len(rows),
        "eligible_panel_rows": len(rows), "input_excluded_rows": 0, "input_exclusions": {},
        "upstream_exclusions": {"status": "EXTERNAL_TO_NORMALIZED_INPUT"},
        "minutes_precision_counts": {"rounded_whole_minutes": len(rows)}}
    return rows, source


def frozen(inventory):
    return protocol_specification(inventory) | {
        "recorded_at": "2026-01-01T00:00:00Z", "approved_by": "root_integration_owner"}


class Development005Tests(unittest.TestCase):
    def test_identity_time_selection_keeps_complete_games_without_target_performance(self):
        rows, source = sample_panel()
        selected, inventory = inventory_panel(rows, source)
        changed = [replace(r, fg2m=40, rebounds=20, assists=20) for r in rows]
        changed_selected, changed_inventory = inventory_panel(changed, source)
        self.assertEqual([(w, r.event_id, r.player_id) for w, r in selected],
                         [(w, r.event_id, r.player_id) for w, r in changed_selected])
        self.assertEqual(inventory, changed_inventory)
        self.assertEqual(len(selected), 32)
        self.assertEqual(inventory["selected_games"], 16)
        self.assertEqual(inventory["window_end"], "2026-03-15")
        for week in inventory["weekly_inventory"]:
            for game in week["games"]:
                value = f"{PROTOCOL_ID}|{SEED}|{week['week_start']}|{game['event_id']}"
                self.assertEqual(game["selection_sha256"], hashlib.sha256(value.encode()).hexdigest())
                self.assertEqual(game["appearances"], 2)
        with patch("multisport_lab.development_005.MAX_ROWS", 31):
            with self.assertRaisesRegex(ValueError, "no game is split"):
                inventory_panel(rows, source)

    def test_source_missing_week_and_inconsistent_event_fail_before_forecasting(self):
        rows, source = sample_panel()
        with self.assertRaisesRegex(ValueError, "SHA256"):
            inventory_panel(rows, source | {"input_file_sha256": "0"*64})
        with self.assertRaisesRegex(ValueError, "each registered"):
            inventory_panel([r for r in rows if not r.event_id.startswith("w7")], source)
        with self.assertRaisesRegex(ValueError, "clocks"):
            inventory_panel([replace(rows[0], event_start=rows[0].event_start+timedelta(minutes=1))]+rows[1:], source)

    def test_protocol_binds_code_population_parameters_owner_and_clocks(self):
        _, inventory = inventory_panel(*sample_panel())
        protocol = frozen(inventory)
        validate_protocol(protocol, inventory)
        self.assertEqual(set(protocol["models"]), {"R0", "K0", "S0"})
        self.assertEqual(protocol["hyperparameter_searches"], 0)
        self.assertFalse(protocol["claims"]["workload_undercoverage_fixed"])
        for field, value in (("candidate", protocol["candidate"] | {"mixture_generator_share": 0.2}),
                             ("approved_by", "other"),
                             ("recorded_at", "2099-01-01T00:00:00Z")):
            with self.assertRaises(ValueError):
                validate_protocol(protocol | {field: value}, inventory)
        changed = dict(protocol["implementation_source_sha256"])
        changed["multisport_lab/baseline.py"] = "0"*64
        with self.assertRaisesRegex(ValueError, "implementation_source_sha256"):
            validate_protocol(protocol | {"implementation_source_sha256": changed}, inventory)

    def test_readback_requires_exact_pushed_revision_and_matching_protocol(self):
        _, inventory = inventory_panel(*sample_panel())
        protocol = frozen(inventory)
        readback = {"independent_readback": True, "reviewed_by": "support_review",
            "protocol_payload_sha256": digest(protocol),
            "implementation_source_sha256": implementation_hashes(), "commit": "a"*40,
            "recorded_at": "2026-01-02T00:00:00Z"}
        completed = type("Completed", (), {"stdout": "a"*40+"\n"})()
        with patch("multisport_lab.development_005.subprocess.run", return_value=completed):
            validate_readback(readback, protocol)
            with self.assertRaisesRegex(ValueError, "HEAD"):
                validate_readback(readback | {"commit": "b"*40}, protocol)
            with self.assertRaisesRegex(ValueError, "independent"):
                validate_readback(readback | {"independent_readback": False}, protocol)
            with self.assertRaisesRegex(ValueError, "independent"):
                validate_readback(readback | {"protocol_payload_sha256": "0"*64}, protocol)
            with self.assertRaisesRegex(ValueError, "precedes"):
                validate_readback(readback | {"recorded_at": "2025-01-01T00:00:00Z"}, protocol)

    def test_renaming_result_cannot_repeat_claimed_protocol_trial(self):
        from multisport_lab.development_005 import main
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder/"frozen-attempt.json").write_text('{"stage":"REGISTERED_TRIAL_CLAIMED"}')
            arguments = ["development_005", "--input", str(folder/"unused-input.jsonl"),
                "--protocol", str(folder/"frozen.json"), "--readback", str(folder/"readback.json"),
                "--output", str(folder/"renamed-result.json")]
            with patch("sys.argv", arguments), patch("multisport_lab.development_005.read_normalized_panel") as read:
                with self.assertRaises(SystemExit) as stopped:
                    main()
            self.assertEqual(stopped.exception.code, 2)
            read.assert_not_called()

    def test_scoring_failure_retains_claim_and_failure_receipt_without_retry(self):
        from multisport_lab.development_005 import main
        rows, source = sample_panel()
        selected, inventory = inventory_panel(rows, source)
        protocol = frozen(inventory)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            arguments = ["development_005", "--input", str(folder/"unused-input.jsonl"),
                "--protocol", str(folder/"frozen.json"), "--readback", str(folder/"readback.json"),
                "--output", str(folder/"result.json")]
            with patch("sys.argv", arguments), \
                 patch("multisport_lab.development_005.read_normalized_panel", return_value=(rows, source)), \
                 patch("multisport_lab.development_005.inventory_panel", return_value=(selected, inventory)), \
                 patch("multisport_lab.development_005.read_receipt", side_effect=[protocol, {"commit": "a"*40}]), \
                 patch("multisport_lab.development_005.validate_readback"), \
                 patch("multisport_lab.development_005.resource.setrlimit"), \
                 patch("multisport_lab.development_005.run_development", side_effect=ValueError("bounded failure")) as run:
                with self.assertRaises(SystemExit) as stopped:
                    main()
            self.assertEqual(stopped.exception.code, 2)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(read_receipt(folder/"result.json")["stage"], "FAILED_REGISTERED_TRIAL")
            self.assertEqual(json.loads((folder/"frozen-attempt.json").read_text())["stage"], "REGISTERED_TRIAL_CLAIMED")

    def test_week_bootstrap_preserves_paired_row_weights_and_adjusted_tail(self):
        counts = list(range(1, 9))
        sums = [{m: -index*n for m in MARKETS} for index, n in enumerate(counts)]
        result = paired_bootstrap(sums, counts)
        expected = -sum(i*n for i, n in enumerate(counts))/sum(counts)
        self.assertAlmostEqual(result["PTS"]["mean_difference_S0_minus_K0"], expected)
        self.assertEqual(result, paired_bootstrap(sums, counts))
        for category in result.values():
            self.assertGreaterEqual(category["one_sided_Bonferroni14_upper"], category["cluster_percentile95_upper"])
        constant = [{m: -2*n for m in MARKETS} for n in counts]
        self.assertEqual(paired_bootstrap(constant, counts)["DD"]["one_sided_Bonferroni14_upper"], -2)
        with self.assertRaisesRegex(ValueError, "eight"):
            paired_bootstrap(sums[:7], counts[:7])

    def test_no_favorable_category_claim_if_common_workload_or_rare_count_guard_fails(self):
        category = {"zero_support_log_loss_count": 0, "observed_zero_rate": 0,
            "mean_predicted_zero_probability": 0, "intervals": {"0.95": {
                "observed_coverage": 1, "mean_predicted_mass": 1}},
            "observed_above_upper95_rate": 0, "mean_predicted_probability_above_upper95": 0}
        primary = {"one_sided_Bonferroni14_upper": -1}
        result = _guards(category, primary, [0]*40, "TD", ["WORKLOAD_FAIL"])
        self.assertFalse(result["all_exploratory_requirements_met"])
        self.assertIn("WORKLOAD_FAIL", result["failed_requirements"])
        self.assertIn("RARE_BINARY_COUNTS_LT20_POSITIVE_OR_NEGATIVE", result["failed_requirements"])

    def test_synthetic_runner_retains_all_models_categories_population_and_causal_cutoffs(self):
        rows, source = sample_panel()
        selected, inventory = inventory_panel(rows, source)
        result = run_development(rows, selected, inventory, frozen(inventory))
        self.assertEqual(result["scored_appearances_per_model"], 32)
        self.assertEqual(result["post_score_exclusions"], 0)
        self.assertEqual(len(result["row_records"]), 32)
        self.assertEqual(result["reported_minutes_S0_K0_diagnostics_identical_count"], 32)
        for name in ("R0", "K0", "S0"):
            self.assertEqual(set(result["models"][name]["categories"]), set(MARKETS))
            self.assertTrue(all(c["scored_count"] == 32 for c in result["models"][name]["categories"].values()))
        self.assertEqual(result["models"]["S0"]["minutes"], result["models"]["K0"]["minutes"])
        for record in result["row_records"]:
            self.assertLessEqual(record["trained_through"], record["history_freeze"])
            self.assertEqual(set(record["categories"]), {"R0", "K0", "S0"})
            self.assertTrue(all(len(c) == 3 for c in record["categories"]["S0"].values()))
        self.assertFalse(result["claims"]["confirmation"])
        canonical(result)


if __name__ == "__main__":
    unittest.main()

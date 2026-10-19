"""Synthetic pilot-cohort/aggregation integrity checks, not NBA evaluation."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from multisport_lab.baseline import MARKETS
from multisport_lab.integrity import canonical
from multisport_lab.nba_data import COUNT_FIELDS, NBAPlayerGame
from multisport_lab.research_pilot import (
    PROTOCOL_ID, aggregate_reports, read_normalized_panel, run_pilot, validate_protocol,
)


def record(day, **changes):
    values = dict(id_namespace="espn", event_id=f"g{day}", player_id="p1",
        team_id="1", opponent_id="2", season_ending_year=2024, season_type="2",
        event_start=datetime(2024, 1, day, 20, tzinfo=timezone.utc),
        participation="APPEARED", minutes=1, minutes_precision="rounded_whole_minutes",
        final_status="FINAL", **{name: 0 for name in COUNT_FIELDS})
    return NBAPlayerGame(**(values | changes)).to_record()


def protocol(inventory):
    return {"protocol_id": PROTOCOL_ID, "status": "FROZEN_BEFORE_SCORING",
        "evidence_lane": "RECONSTRUCTED_RESEARCH",
        "input_sha256": inventory["input_file_sha256"], "input_rows": inventory["input_rows"],
        "target_utc_event_dates": inventory["proposed_target_utc_event_dates"],
        "warmup_utc_event_dates": inventory["warmup_utc_event_dates"],
        "max_scored_appearances": 200, "tuning_trials": 1, "half_life_days": 28,
        "league_prior_appearance_equivalents": 5, "confirmation_window": None,
        "product_qualification": "UNAVAILABLE", "recorded_at": "2023-01-01T00:00:00Z",
        "variogram": {"claim": "within-player development diagnostic only",
            "pair_weights": "equal1/28", "power": 0.5, "primitive_scales": "all1 fixed count units"}}


class ResearchPilotTests(unittest.TestCase):
    def load(self, records):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/"panel.jsonl"
            path.write_bytes(b"\n".join(canonical(row) for row in records)+b"\n")
            return read_normalized_panel(path)

    def test_inventory_fixed_dates_exclusions_and_rounded_zero(self):
        records = [record(day) for day in range(1, 10)]
        records.append(record(1, event_id="allstar", team_id="42", opponent_id="43"))
        records.append(record(1, event_id="dnp", participation="DNP", minutes=None,
                              **{name: None for name in COUNT_FIELDS}))
        records.append(record(1, event_id="missing", minutes=None))
        records.append(record(1, event_id="zero", minutes=0))
        rows, inventory = self.load(records)
        self.assertEqual(inventory["proposed_target_utc_event_dates"], ["2024-01-08", "2024-01-09"])
        self.assertEqual(inventory["warmup_utc_event_dates"], [f"2024-01-0{day}" for day in range(1, 8)])
        self.assertEqual(inventory["input_excluded_rows"], 3)
        self.assertEqual(inventory["rounded_zero_minute_appearances"], 1)
        self.assertEqual(len(rows), 10)
        self.assertEqual(inventory["upstream_exclusions"]["status"], "EXTERNAL_TO_NORMALIZED_INPUT")

    def test_duplicate_even_excluded_or_bad_scoring_is_not_silently_removed(self):
        rows = [record(day) for day in range(1, 10)]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.load(rows+[rows[0]])
        bad = record(1, event_id="bad", points=10)
        with self.assertRaisesRegex(ValueError, "reconciliation"):
            self.load(rows+[bad])

    def test_wrong_input_or_dates_cannot_match_the_frozen_protocol(self):
        _, inventory = self.load([record(day) for day in range(1, 10)])
        frozen = protocol(inventory)
        dates = inventory["proposed_target_utc_event_dates"]
        validate_protocol(frozen, inventory, dates)
        with self.assertRaisesRegex(ValueError, "input_sha256"):
            validate_protocol(frozen | {"input_sha256": "0"*64}, inventory, dates)
        with self.assertRaisesRegex(ValueError, "target_utc_event_dates"):
            validate_protocol(frozen, inventory, ["2024-01-07", "2024-01-08"])

    def test_synthetic_pilot_keeps_every_target_and_all_categories_in_finite_json(self):
        rows, inventory = self.load([record(day) for day in range(1, 10)])
        report = run_pilot(rows, inventory, protocol(inventory),
                           inventory["proposed_target_utc_event_dates"], {})
        self.assertEqual(report["scored_rows"], 2)
        self.assertEqual(report["post_score_exclusions"], 0)
        self.assertEqual(set(report["categories"]), set(MARKETS))
        self.assertTrue(all(result["scored_count"] == 2 for result in report["categories"].values()))
        self.assertFalse(report["confirmatory_evaluation"])
        self.assertEqual(report["product_qualification"], "UNAVAILABLE")
        self.assertEqual(report["within_player_variogram"]["mean_score"], 0)
        canonical(report)

    def test_zero_support_log_loss_is_infinite_instead_of_dropping_the_row(self):
        categories = {market: dict(crps=1.0, mean_absolute_error=1.0,
            mean_squared_error=1.0, median=0, observed=1, log_loss=None,
            zero_probability=1.0, observed_above_upper95=True,
            probability_above_upper95=0.0,
            intervals={str(level): dict(covered=False, predicted_mass=1.0, width=0)
                       for level in (0.5, 0.8, 0.95)}, brier=1.0, probability=0.0)
            for market in MARKETS}
        report = dict(categories=categories, minutes_diagnostics=dict(crps=1,
            mean_absolute_error=1, mean_squared_error=1,
            intervals=categories["PTS"]["intervals"]))
        result = aggregate_reports([report])["categories"]["TD"]
        self.assertEqual(result["scored_count"], 1)
        self.assertIsNone(result["mean_log_loss"])
        self.assertEqual(result["zero_support_log_loss_count"], 1)
        self.assertEqual(result["log_loss_status"], "INFINITE_ZERO_SUPPORT")


if __name__ == "__main__":
    unittest.main()

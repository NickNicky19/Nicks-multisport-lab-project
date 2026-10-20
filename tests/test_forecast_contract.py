"""Synthetic export integrity checks, not sports performance evidence."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from multisport_lab.baseline import HistoricalAppearance, ForecastTarget, forecast_reference
from multisport_lab.forecast_contract import FORECAST_SCHEMA_V2, from_reference, validate_forecast, verify_reference
from multisport_lab.integrity import IntegrityError, digest, stamp


def synthetic_reference():
    start = datetime(2025, 11, 24, 20, tzinfo=timezone.utc)
    observed = HistoricalAppearance(event_id="target", player_id="p", team_id="1", opponent_id="2",
        event_start=start, outcome_available_at=start+timedelta(days=1), minutes=30,
        fg2m=10, fg3m=0, ftm=0, rebounds=10, assists=0, turnovers=0, blocks=0, steals=0)
    earlier = HistoricalAppearance(event_id="past", player_id="p", team_id="1", opponent_id="2",
        event_start=start-timedelta(days=7), outcome_available_at=start-timedelta(days=6), minutes=30,
        fg2m=10, fg3m=0, ftm=0, rebounds=10, assists=0, turnovers=0, blocks=0, steals=0)
    reference = forecast_reference([earlier], ForecastTarget(observed.event_id, observed.player_id, start))
    return reference, observed


def rehash(value):
    value["forecast_id"] = digest({k: v for k, v in value.items() if k != "forecast_id"})
    return value


class ForecastContractTests(unittest.TestCase):
    def setUp(self):
        self.reference, self.observed = synthetic_reference()
        self.bundle = from_reference(self.reference, self.observed, model_commit="a"*40)

    def prospective_fixture(self):
        """Invented wire fixture only; never a captured or ledger-issued forecast."""
        result = deepcopy(self.bundle)
        cutoff = self.reference.target.cutoff
        result.update(schema_version=FORECAST_SCHEMA_V2,
                      model_version="nba_joint_empirical_pregame_r1_v1",
                      evidence_lane="REAL_TIME_CAPTURED", availability_basis="OBSERVED_INPUT_CAPTURE",
                      issued_at=stamp(cutoff + timedelta(seconds=30)), input_capture_ids=["f"*64],
                      prospective={"producer_version": "nba-pregame-r1-v1", "event_version": "1"*64,
                          "selection_sha256": "2"*64, "source_pack_sha256": "3"*64,
                          "source_pack_record_id": "f"*64,
                          "generation_started_at": stamp(cutoff),
                          "generation_completed_at": stamp(cutoff + timedelta(seconds=30)),
                          "source_observed_min_at": stamp(cutoff - timedelta(minutes=10)),
                          "source_observed_max_at": stamp(cutoff - timedelta(minutes=1)),
                          "imported_at": stamp(cutoff),
                          "base_model_version": "nba_joint_empirical_r0_v1",
                          "base_model_code_sha256": "4"*64, "history_rows": 26645,
                          "history_latest_event_at": stamp(cutoff - timedelta(days=10))})
        return rehash(result)

    def test_prospective_v2_retains_all_categories_and_rejects_r0_attestation(self):
        bundle = self.prospective_fixture()
        self.assertEqual(validate_forecast(bundle), bundle)
        self.assertEqual(len(bundle["categories"]), 14)
        with self.assertRaisesRegex(IntegrityError, "reconstructed reference"):
            verify_reference(bundle, self.reference)
        bundle["schema_version"] = "nba-research-forecast-v1"
        with self.assertRaisesRegex(IntegrityError, "schema"):
            validate_forecast(rehash(bundle))

    def test_prospective_v2_source_clocks_window_latency_and_full_history_budget(self):
        cutoff = self.reference.target.cutoff
        changes = [
            {"source_observed_min_at": stamp(cutoff - timedelta(minutes=10, microseconds=1))},
            {"source_observed_max_at": stamp(cutoff + timedelta(microseconds=1))},
            {"imported_at": stamp(cutoff + timedelta(microseconds=1))},
            {"generation_started_at": stamp(cutoff - timedelta(microseconds=1))},
            {"generation_started_at": stamp(cutoff + timedelta(seconds=31))},
            {"generation_completed_at": stamp(cutoff + timedelta(seconds=29))},
            {"generation_started_at": stamp(cutoff),
             "generation_completed_at": stamp(cutoff + timedelta(seconds=121))},
            {"history_latest_event_at": stamp(self.reference.target.history_freeze)},
            {"history_rows": 100001}, {"history_rows": True},
            {"source_pack_record_id": "5"*64}, {"event_version": "unknown"},
            {"producer_version": "nba-pregame-r2-v1"},
        ]
        for change in changes:
            bundle = self.prospective_fixture()
            bundle["prospective"].update(change)
            # Keep the completion/issue equality when specifically testing latency.
            if change.get("generation_completed_at") == stamp(cutoff + timedelta(seconds=121)):
                bundle["issued_at"] = change["generation_completed_at"]
            with self.subTest(change=change), self.assertRaises(IntegrityError):
                validate_forecast(rehash(bundle))
        bundle = self.prospective_fixture()
        bundle["issued_at"] = stamp(cutoff + timedelta(minutes=5, microseconds=1))
        bundle["prospective"].update(generation_started_at=stamp(cutoff + timedelta(minutes=4)),
                                     generation_completed_at=bundle["issued_at"])
        with self.assertRaisesRegex(IntegrityError, "window"):
            validate_forecast(rehash(bundle))

    def test_complete_reference_exports_compact_14_pmfs_without_raw_support(self):
        self.assertEqual(len(self.bundle["categories"]), 14)
        self.assertNotIn("support", self.bundle)
        self.assertTrue(all(isinstance(atom["probability"], str) for c in self.bundle["categories"] for atom in c["pmf"]))
        self.assertEqual(validate_forecast(self.bundle), self.bundle)
        proof = verify_reference(self.bundle, self.reference)
        self.assertEqual(proof["forecast_id"], self.bundle["forecast_id"])
        self.assertEqual(proof["joint_sha256"], self.bundle["joint_sha256"])

    def test_missing_category_units_and_bad_pmf_fail_even_after_rehash(self):
        for change in ("missing", "units", "mass", "boolean", "float"):
            bad = deepcopy(self.bundle)
            if change == "missing": bad["categories"].pop()
            elif change == "units": bad["categories"][0]["units"] = "rebounds"
            elif change == "mass": bad["categories"][0]["pmf"][0]["probability"] = "0.9"
            elif change == "boolean": bad["categories"][0]["pmf"][0]["value"] = True
            else: bad["categories"][0]["pmf"][0]["probability"] = 1.0
            with self.subTest(change=change), self.assertRaises(IntegrityError):
                validate_forecast(rehash(bad))

    def test_submillisecond_cutoff_and_false_pregame_history_are_rejected(self):
        bad = deepcopy(self.bundle)
        bad["cutoff_at"] = stamp(self.reference.target.cutoff+timedelta(microseconds=1))
        with self.assertRaises(IntegrityError): validate_forecast(rehash(bad))
        bad = deepcopy(self.bundle)
        bad["issued_at"] = stamp(self.observed.event_start-timedelta(minutes=1))
        with self.assertRaises(IntegrityError): validate_forecast(rehash(bad))

    def test_deterministic_double_double_cannot_be_erased(self):
        bad = deepcopy(self.bundle)
        dd = next(c for c in bad["categories"] if c["code"] == "DD")
        dd.update(pmf=[{"value": 0, "probability": "1"}], mean="0", interval80=[0, 0])
        with self.assertRaisesRegex(IntegrityError, "threshold bounds"):
            validate_forecast(rehash(bad))

    def test_hash_and_producer_input_prevent_silent_reassignment(self):
        bad = deepcopy(self.bundle)
        bad["player_id"] = "other"
        with self.assertRaisesRegex(IntegrityError, "checksum"):
            validate_forecast(bad)
        rehash(bad)
        validate_forecast(bad)  # Schema cannot establish source/model authenticity.
        with self.assertRaisesRegex(IntegrityError, "producer input"):
            verify_reference(bad, self.reference)

    def test_archive_cannot_be_upgraded_to_future_by_changing_lane(self):
        bad = deepcopy(self.bundle)
        bad.update(evidence_lane="REAL_TIME_CAPTURED", availability_basis="OBSERVED_INPUT_CAPTURE",
                   input_capture_ids=["f"*64])
        with self.assertRaises(IntegrityError): validate_forecast(rehash(bad))


if __name__ == "__main__":
    unittest.main()

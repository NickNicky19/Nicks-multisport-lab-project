"""Synthetic export integrity checks, not sports performance evidence."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from multisport_lab.baseline import HistoricalAppearance, ForecastTarget, forecast_reference
from multisport_lab.forecast_contract import from_reference, validate_forecast, verify_reference
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

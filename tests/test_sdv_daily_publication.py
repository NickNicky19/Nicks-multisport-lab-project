"""Synthetic contract and publication checks; no prospective issuance."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab.integrity import IntegrityError, canonical, digest, load_json
from multisport_lab.publication import build_site, read_manifest
from multisport_lab.sdv_daily_publication import make_asset, validate_asset, read_asset

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/sdv-daily-synthetic.json"


def reseal(body, key="asset_id"):
    body[key] = digest({k: v for k, v in body.items() if k != key})
    return body


class DailyPublicationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)

    def fixture(self):
        return load_json(FIXTURE)

    def test_empty_daily_store_is_inactive_without_changing_original_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            asset = make_asset(Path(tmp), now=self.now)
            self.assertEqual(asset["status"], "INACTIVE")
            self.assertEqual(asset["forecasts"], [])
            self.assertEqual(asset["counts"], {"development_forecasts": 0, "genuine_forecasts": 0,
                                               "eligible_forecasts": 0, "pending_grades": 0})
            self.assertIsNone(asset["activation"])
            self.assertNotIn("raw_base64", str(asset))

    def test_shared_synthetic_development_fixture_preserves_all_categories(self):
        asset = self.fixture()
        original = canonical(asset)
        validate_asset(asset, now=self.now)
        self.assertEqual(asset["status"], "DEVELOPMENT_PREVIEW")
        self.assertEqual(asset["counts"]["development_forecasts"], 8)
        self.assertEqual(asset["counts"]["genuine_forecasts"], 0)
        self.assertEqual({len(row["body"]["categories"]) for row in asset["forecasts"]}, {14})
        self.assertEqual({row["body"]["issued_at"] for row in asset["forecasts"]}, {None})
        self.assertEqual(canonical(asset), original)

    def test_checksum_consistent_development_cannot_claim_eligible_issuance(self):
        asset = self.fixture()
        asset["forecasts"][0]["admission"].update(eligible=True, reasons=[])
        reseal(asset)
        with self.assertRaises(IntegrityError):
            validate_asset(asset, now=self.now)

    def test_checksum_consistent_foreign_input_or_identity_is_rejected(self):
        for field, value in (("input_id", "e" * 64), ("player_label", "Unverified player"),
                             ("event_snapshot_id", "a" * 64), ("history_panel_sha256", "f" * 64)):
            with self.subTest(field=field):
                asset = self.fixture()
                forecast = asset["forecasts"][0]["body"]
                forecast[field] = value
                reseal(forecast, "forecast_id")
                reseal(asset)
                with self.assertRaises(IntegrityError):
                    validate_asset(asset, now=self.now)

    def test_checksum_consistent_stale_at_generation_or_future_clock_is_rejected(self):
        for field, value in (("generation_started_at", "2026-10-25T00:00:00.000000Z"),
                             ("verified_at", "2026-10-25T00:00:00.000000Z")):
            with self.subTest(field=field):
                asset = self.fixture()
                forecast = asset["forecasts"][0]["body"]
                forecast[field] = value
                reseal(forecast, "forecast_id")
                reseal(asset)
                with self.assertRaises(IntegrityError):
                    validate_asset(asset, now=self.now)

    def test_independent_readback_matches_exact_canonical_bytes_and_rejects_unsafe_path(self):
        asset = self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            raw = canonical(asset)
            checksum = hashlib.sha256(raw).hexdigest()
            descriptor = {"path": "sdv-daily." + checksum + ".json", "sha256": checksum,
                          "generated_at": asset["generated_at"], "status": "DAILY_SNAPSHOT_RESEARCH",
                          "retained": False, "error": None}
            (data / descriptor["path"]).write_bytes(raw)
            self.assertEqual(read_asset(data, descriptor, now=self.now), asset)
            descriptor["path"] = "../private.json"
            with self.assertRaises(IntegrityError):
                read_asset(data, descriptor, now=self.now)

    def lifecycle(self):
        from multisport_lab.sdv_daily_producer import seal, make_grade
        asset = self.fixture()
        forecast = asset["forecasts"][0]["body"]
        observed = asset["generated_at"]
        outcome = seal({"schema_version": "nba-sdv-daily-outcome-v1", "protocol_id": asset["protocol_id"],
            **{key: forecast[key] for key in ("cycle_id", "mode", "event_id", "event_snapshot_id", "event_starts_at",
                                             "player_id", "team_id", "opponent_id")},
            "status": "UNRESOLVED", "source_refs": [{"kind": "research_inputs", "record_id": "d" * 64,
                                                      "payload_sha256": "e" * 64}],
            "source_observed_at": observed, "normalized_at": observed,
            "normalizer_version": "synthetic-daily-outcome-test-v1", "primitives": None,
            "minutes": None, "minutes_precision": None, "categories": []}, "outcome_id")
        grade = make_grade(forecast, outcome, graded_at=observed)
        asset["outcomes"] = [{"reference": {"kind": "outcomes", "record_id": "1" * 64,
                                           "payload_sha256": "2" * 64}, "body": outcome}]
        asset["grades"] = [{"reference": {"kind": "grades", "record_id": "3" * 64,
                                         "payload_sha256": "4" * 64}, "body": grade}]
        return reseal(asset)

    def test_unresolved_outcome_is_not_zero_or_completed_grade(self):
        asset = self.lifecycle()
        validate_asset(asset, now=self.now)
        self.assertEqual(asset["counts"]["pending_grades"], 8)
        self.assertEqual(asset["grades"][0]["body"]["categories"], [])

    def test_checksum_consistent_invalid_outcome_or_grade_is_rejected(self):
        for kind, field, value in (("outcomes", "status", "ASSUMED_FINAL"),
                                   ("outcomes", "event_snapshot_id", "f" * 64),
                                   ("grades", "status", "DNP_NOT_SCORED"),
                                   ("grades", "graded_at", "2026-10-25T00:00:00.000000Z")):
            with self.subTest(kind=kind, field=field):
                asset = self.lifecycle()
                body = asset[kind][0]["body"]
                body[field] = value
                reseal(body, kind[:-1] + "_id")
                reseal(asset)
                with self.assertRaises(IntegrityError):
                    validate_asset(asset, now=self.now)

    def test_daily_failure_does_not_remove_history_or_offer_channel_and_v5_stays_loadable(self):
        originals = {p.relative_to(ROOT): p.read_bytes() for p in (ROOT / "records").rglob("*.json")}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            with patch("multisport_lab.sdv_daily_publication.make_asset", side_effect=IntegrityError("bad daily original")):
                manifest = build_site(ROOT, out, build_commit="a" * 40, now=self.now)
            self.assertEqual(manifest["schema_version"], 7)
            self.assertIsNone(manifest["daily_research"])
            self.assertIsNotNone(manifest["daily_research_error"])
            self.assertIsNotNone(manifest["offers"])
            nba = load_json(out / "data" / manifest["sports"][0]["path"])
            self.assertEqual((len(nba["forecasts"]), len(nba["performance"])), (6, 6))
            self.assertEqual([nba[key] for key in ("offers", "candidates", "tickets")], [[], [], []])
            old = {k: v for k, v in manifest.items() if k not in {"daily_research", "daily_research_error",
                                                             "production_research", "production_research_error"}}
            old["schema_version"] = 5
            old["snapshot_id"] = digest({k: v for k, v in old.items() if k != "snapshot_id"})
            (out / "data/manifest.json").write_bytes(canonical(old))
            self.assertEqual(read_manifest(out / "data", now=self.now), old)
        self.assertEqual(originals, {p.relative_to(ROOT): p.read_bytes() for p in (ROOT / "records").rglob("*.json")})


if __name__ == "__main__":
    unittest.main()

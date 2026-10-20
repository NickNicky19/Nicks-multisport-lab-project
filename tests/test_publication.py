from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab.integrity import IntegrityError, canonical, digest, read_receipt
from multisport_lab.publication import build_site, empty_nba, publish, read_manifest, research_nba, resolve_scope, validate_sport

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 19, 23, tzinfo=timezone.utc)
COMMIT = "a" * 40


class PublicationTests(unittest.TestCase):
    def research_fixture(self):
        """Pin six immutable exemplars; legitimate ledger growth must not fail CI."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name) / "project"
        for name in ("config", "web"):
            shutil.copytree(ROOT / name, root / name)
        summary = read_receipt(ROOT / "evidence/research/reference-publication-002.json")
        for example in summary["examples"]:
            for name in ("forecast_ref", "outcome_ref", "grade_ref"):
                ref = example[name]
                relative = Path("records", ref["kind"], ref["record_id"] + ".json")
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, root / relative)
        return root

    def test_single_selected_all_never_expand_unsupported_scope(self):
        supported = ["NBA", "WNBA"]  # synthetic future coverage, not admitted sports
        self.assertEqual(resolve_scope("SINGLE", ["NBA"], supported), {"NBA"})
        self.assertEqual(resolve_scope("SELECTED", ["WNBA"], supported), {"WNBA"})
        self.assertEqual(resolve_scope("ALL", [], supported), {"NBA", "WNBA"})
        for mode, selection in [("SELECTED", []), ("ALL", ["NBA"]), ("SINGLE", supported), ("SINGLE", ["NFL"])]:
            with self.assertRaises(ValueError):
                resolve_scope(mode, selection, supported)

    def test_research_schema_rejects_claims_missing_categories_or_rows(self):
        snapshot = empty_nba(ROOT, now=NOW)
        validate_sport(snapshot, league="NBA", now=NOW)
        for field, value in [("candidates", [{"qualified": True}]), ("offers", [{}]),
                             ("status", "QUALIFIED"), ("schema_version", True),
                             ("generated_at", "2026-10-20T00:00:00Z")]:
            bad = deepcopy(snapshot)
            bad[field] = value
            with self.assertRaises((ValueError, IntegrityError)):
                validate_sport(bad, league="NBA", now=NOW)
        bad = deepcopy(snapshot)
        bad["markets"] = [m for m in bad["markets"] if m["code"] != "TD"]
        with self.assertRaises(IntegrityError):
            validate_sport(bad, league="NBA", now=NOW)

    def test_failed_sport_preserves_old_bytes_and_time_other_sport_publishes(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            nba = empty_nba(ROOT, now=NOW)
            initial = publish(data, {"NBA": nba}, build_commit=COMMIT, now=NOW)
            old = initial["sports"][0]
            before = (data / old["path"]).read_bytes()
            # WNBA is fictional test coverage only, with no markets or observations.
            wnba = deepcopy(nba)
            wnba.update(league="WNBA", markets=[], generated_at="2026-10-19T23:01:00Z")
            later = NOW + timedelta(minutes=1)
            manifest = publish(data, {"NBA": ValueError("private upstream body"), "WNBA": wnba},
                               build_commit="b"*40, now=later)
            saved = next(x for x in manifest["sports"] if x["league"] == "NBA")
            self.assertTrue(saved["retained"])
            self.assertEqual(saved["generated_at"], old["generated_at"])
            self.assertEqual((data / old["path"]).read_bytes(), before)
            self.assertNotIn("private", canonical(manifest).decode())
            self.assertEqual(read_manifest(data, now=later), manifest)

    def test_corruption_and_failed_first_update_do_not_publish_success(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            with self.assertRaises(IntegrityError):
                publish(data, {"NBA": ValueError("failed")}, build_commit=COMMIT, now=NOW)
            self.assertFalse((data / "manifest.json").exists())
            manifest = publish(data, {"NBA": empty_nba(ROOT, now=NOW)}, build_commit=COMMIT, now=NOW)
            asset = data / manifest["sports"][0]["path"]
            raw = asset.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest["sports"][0]["sha256"])
            asset.write_bytes(raw.replace(b"UNVALIDATED", b"QUALIFIED!!"))
            with self.assertRaises(IntegrityError):
                read_manifest(data, now=NOW)

    def test_build_excludes_stale_private_files_and_keeps_modules(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            (root / "web").mkdir()
            (root / "web/index.html").write_text("<title>Research</title>")
            (root / "web/app.mjs").write_text("export const research = true;")
            (root / "config").mkdir()
            for name in ("nba_markets.json", "capabilities.json"):
                (root / "config" / name).write_bytes((ROOT / "config" / name).read_bytes())
            output = root / "output"
            output.mkdir()
            (output / "private-raw.json").write_text('{"must_not_publish":true}')
            build_site(root, output, build_commit=COMMIT, now=NOW)
            self.assertFalse((output / "private-raw.json").exists())
            self.assertTrue((output / "app.mjs").is_file())
            self.assertTrue((output / "index.html").is_file())
            read_manifest(output / "data", now=NOW)

    def test_retained_real_reconstructions_have_complete_typed_coverage_not_future(self):
        now = datetime.now(timezone.utc)
        snapshot = research_nba(self.research_fixture(), now=now)
        self.assertEqual(snapshot["schema_version"], 2)
        self.assertEqual(len(snapshot["forecasts"]), 6)
        self.assertEqual(len(snapshot["performance"]), 6)
        self.assertEqual(len(snapshot["events"]), 3)
        self.assertEqual(snapshot["future_availability"]["status"], "UNAVAILABLE")
        for bundle in snapshot["forecasts"]:
            self.assertEqual(len(bundle["categories"]), 14)
            self.assertGreater(bundle["issued_at"], bundle["event_starts_at"])
            self.assertEqual(bundle["evidence_lane"], "RECONSTRUCTED_RESEARCH")
        self.assertEqual(snapshot["tickets"], [])

    def prospective_fixture(self, snapshot):
        """Invented future wire object; no capture or actual issuance is claimed."""
        bundle = deepcopy(snapshot["forecasts"][0])
        start = datetime.now(timezone.utc) + timedelta(hours=1)
        cutoff = start - timedelta(minutes=90)
        freeze = cutoff.replace(hour=0, minute=0, second=0, microsecond=0)
        from multisport_lab.integrity import stamp
        bundle.update(schema_version="nba-research-forecast-v2", event_id="synthetic-upcoming",
                      model_version="nba_joint_empirical_pregame_r1_v1",
                      event_starts_at=stamp(start), cutoff_at=stamp(cutoff),
                      history_freeze=stamp(freeze), issued_at=stamp(cutoff+timedelta(seconds=30)),
                      evidence_lane="REAL_TIME_CAPTURED", availability_basis="OBSERVED_INPUT_CAPTURE",
                      input_capture_ids=["f"*64],
                      prospective={"producer_version": "nba-pregame-r1-v1", "event_version": "1"*64,
                          "selection_sha256": "2"*64, "source_pack_sha256": "3"*64,
                          "source_pack_record_id": "f"*64, "generation_started_at": stamp(cutoff),
                          "generation_completed_at": stamp(cutoff+timedelta(seconds=30)),
                          "source_observed_min_at": stamp(cutoff-timedelta(minutes=10)),
                          "source_observed_max_at": stamp(cutoff-timedelta(minutes=1)),
                          "imported_at": stamp(cutoff), "base_model_version": "nba_joint_empirical_r0_v1",
                          "base_model_code_sha256": "4"*64, "history_rows": 26645,
                          "history_latest_event_at": stamp(freeze-timedelta(days=1))})
        bundle["forecast_id"] = digest({k: v for k, v in bundle.items() if k != "forecast_id"})
        return bundle

    def test_prospective_export_preserves_pending_grade_and_each_evidence_lane(self):
        now = datetime.now(timezone.utc)
        root = self.research_fixture()
        original = research_nba(root, now=now)
        prospective = self.prospective_fixture(original)
        forecasts = original["forecasts"] + [prospective]
        # A wire/export fixture does not bypass or claim ledger producer admission.
        with patch("multisport_lab.ledger.Ledger.iter_active_forecasts", return_value=iter(forecasts)):
            result = research_nba(root, now=datetime.now(timezone.utc))
        self.assertEqual(result["evidence_lane"], "RESEARCH_COLLECTION")
        self.assertEqual(result["future_availability"], {"status": "AVAILABLE", "reasons": []})
        self.assertEqual(len(result["forecasts"]), 7)
        self.assertEqual(len(result["performance"]), 6)
        self.assertFalse(any(grade["forecast_id"] == prospective["forecast_id"] for grade in result["performance"]))
        self.assertEqual(result["forecasts"][-1], prospective)
        bad = deepcopy(result)
        bad["evidence_lane"] = "RECONSTRUCTED_RESEARCH"
        with self.assertRaisesRegex(IntegrityError, "Collection evidence"):
            validate_sport(bad, league="NBA", now=datetime.now(timezone.utc))
        with patch("multisport_lab.ledger.Ledger.iter_active_forecasts", return_value=iter(forecasts)):
            later = research_nba(root, now=datetime.now(timezone.utc)+timedelta(hours=2))
        self.assertEqual(later["future_availability"]["status"], "UNAVAILABLE")
        self.assertIn("publication clock", later["future_availability"]["reasons"][0])
        self.assertEqual(later["forecasts"][-1], prospective)
        self.assertEqual(len(later["performance"]), 6)

    def test_typed_export_rejects_event_mismatch_and_self_rehashed_wrong_grade(self):
        now = datetime.now(timezone.utc)
        snapshot = research_nba(self.research_fixture(), now=now)
        bad = deepcopy(snapshot)
        bad["events"][0]["team_ids"] = ["fake-team", "another-team"]
        with self.assertRaisesRegex(IntegrityError, "Forecast/event"):
            validate_sport(bad, league="NBA", now=now)
        bad = deepcopy(snapshot)
        grade = bad["performance"][0]
        grade["categories"][0]["crps"] = "1000000"
        grade["grade_id"] = digest({k: v for k, v in grade.items() if k != "grade_id"})
        with self.assertRaises(IntegrityError):
            validate_sport(bad, league="NBA", now=now)

    def test_corrupt_ledger_retains_previous_typed_asset_without_freshening_it(self):
        now = datetime.now(timezone.utc)
        root = self.research_fixture()
        output = root / "output"
        first = build_site(root, output, build_commit=COMMIT, now=now)
        previous = first["sports"][0]
        asset = (output / "data" / previous["path"]).read_bytes()
        record = next((root / "records/forecasts").glob("*.json"))
        record.write_text("{}")
        later = now + timedelta(seconds=10)
        retained = build_site(root, output, build_commit="b"*40, now=later)["sports"][0]
        self.assertTrue(retained["retained"])
        self.assertEqual(retained["generated_at"], previous["generated_at"])
        self.assertEqual((output / "data" / retained["path"]).read_bytes(), asset)


if __name__ == "__main__":
    unittest.main()

"""Synthetic operational-clock regressions; no actual prospective evidence."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import prospective as prod
from multisport_lab.integrity import IntegrityError, digest
from multisport_lab.ledger import Ledger
from multisport_lab.pregame_sources import sourcepack_digest
from prospective_fixtures import synthetic_pack, CUTOFF, CAPTURE, ISSUE


class ProspectiveTests(unittest.TestCase):
    def setUp(self):
        self.pack = synthetic_pack()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("multisport_lab.pregame_sources.PANEL_SHA", self.pack["history_provenance"]["normalized_panel_sha256"]))
        self.stack.enter_context(patch.object(prod, "PILOT_PANEL_SHA256", self.pack["history_provenance"]["normalized_panel_sha256"]))
        self.stack.enter_context(patch.object(prod, "PILOT_HISTORY_ROWS", 2))
        self.stack.enter_context(patch.object(prod, "PILOT_EVENT_VERSION", self.pack["event"]["event_version"]))
        self.stack.enter_context(patch.object(prod, "PILOT_SELECTION_SHA256", digest(self.pack["selection"])))
        self.stack.enter_context(patch("multisport_lab.pregame_sources._now", return_value=ISSUE))
        self.stack.enter_context(patch("multisport_lab.baseline._now", return_value=ISSUE))
        self.clock = self.stack.enter_context(patch.object(prod, "_now", return_value=ISSUE))
        self.ledger_clock = self.stack.enter_context(patch("multisport_lab.ledger._now", return_value=ISSUE))
        forecast_clock = self.stack.enter_context(patch("multisport_lab.forecast_contract.datetime"))
        forecast_clock.now.return_value = ISSUE+timedelta(hours=24)
        self.temp = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.store = Ledger(self.temp)
        with patch("multisport_lab.ledger._now", return_value=CAPTURE+timedelta(seconds=3)):
            self.input_ref = self.store.record_research_inputs(self.pack)

    def generate(self):
        return prod.generate(self.pack, "10", input_record_id=self.input_ref.record_id, model_commit="a"*40)

    def test_coherent_full_category_generation_persistence_and_late_recovery(self):
        bundle, reference = self.generate()
        self.assertEqual(len(bundle["categories"]), 14)
        self.assertEqual(bundle["evidence_lane"], "REAL_TIME_CAPTURED")
        self.assertEqual(bundle["qualification"], "UNAVAILABLE")
        self.assertEqual(bundle["issued_at"], bundle["prospective"]["generation_completed_at"])
        ref = self.store.issue_prospective(bundle, reference=reference, input_ref=self.input_ref)
        before = self.store._path("forecasts", ref.record_id).read_bytes()
        self.ledger_clock.return_value = ISSUE+timedelta(days=1)
        recovered = Ledger(self.temp)
        self.assertEqual(recovered.read(ref)["data"]["bundle"], bundle)
        retry = recovered.issue_prospective(bundle, reference=reference, input_ref=self.input_ref)
        self.assertEqual(ref, retry)
        self.assertEqual(before, self.store._path("forecasts", ref.record_id).read_bytes())
        self.assertEqual(len(recovered.scan()["grades"]), 0)

    def test_early_late_and_generation_latency_fail_before_forecast_persistence(self):
        for clock in (CUTOFF-timedelta(microseconds=1), CUTOFF+timedelta(minutes=5, microseconds=1)):
            self.clock.return_value = clock
            with self.subTest(clock=clock), self.assertRaisesRegex(IntegrityError, "outside"):
                self.generate()
        self.clock.side_effect = [ISSUE, ISSUE+timedelta(seconds=121)]
        with self.assertRaisesRegex(IntegrityError, "latency"):
            self.generate()
        self.assertEqual(len(self.store.scan()["forecasts"]), 0)

    def test_preparation_source_cannot_be_relabelled_as_timely_capture(self):
        self.pack["sources"][0]["observed_at"] = "2026-10-20T01:51:00.000000Z"
        self.pack["sources"][0]["response_completed_at"] = "2026-10-20T01:51:00.000000Z"
        self.pack["sources"][0]["request_started_at"] = "2026-10-20T01:50:59.000000Z"
        self.pack["sourcepack_id"] = sourcepack_digest(self.pack)
        with self.assertRaisesRegex(IntegrityError, "ten minutes"):
            self.generate()

    def test_reference_and_selected_identity_cannot_drift(self):
        bundle, reference = self.generate()
        changed = deepcopy(bundle)
        changed["player_label"] = "Other person"
        changed["forecast_id"] = digest({k:v for k,v in changed.items() if k!="forecast_id"})
        with self.assertRaisesRegex(IntegrityError, "identity differs"):
            prod.verify_prospective(changed, reference, self.pack, input_record_id=self.input_ref.record_id)
        with self.assertRaisesRegex(IntegrityError, "outside the frozen"):
            prod.generate(self.pack, "999", input_record_id=self.input_ref.record_id, model_commit="a"*40)

    def test_even_rehashed_history_subset_fails_the_pinned_pilot_cohort(self):
        with patch.object(prod, "PILOT_HISTORY_ROWS", 26645):
            with self.assertRaisesRegex(IntegrityError, "full frozen"):
                self.generate()

    def test_interrupted_cohort_recovers_originals_and_only_generates_missing_subjects(self):
        original_generate = prod.generate
        calls = []
        def interrupted(*args, **kwargs):
            calls.append(args[1])
            if len(calls) == 2:
                raise RuntimeError("synthetic interruption")
            return original_generate(*args, **kwargs)
        with patch.object(prod, "generate", side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError, "interruption"):
                prod.issue_cohort(self.store, self.input_ref, model_commit="a"*40)
        originals = {p.name:p.read_bytes() for p in Path(self.temp).glob("records/forecasts/*.json")}
        refs = prod.issue_cohort(Ledger(self.temp), self.input_ref, model_commit="a"*40)
        self.assertEqual(len(refs), 4)
        self.assertEqual(len(self.store.scan()["forecasts"]), 4)
        for name, raw in originals.items():
            self.assertEqual(raw, (Path(self.temp)/"records/forecasts"/name).read_bytes())
        with patch.object(prod, "generate", side_effect=AssertionError("retry cannot regenerate")):
            self.assertEqual(refs, prod.issue_cohort(Ledger(self.temp), self.input_ref, model_commit="a"*40))

    def test_model_commit_checks_executed_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "multisport_lab").mkdir()
            Path(tmp, "multisport_lab/prospective.py").write_bytes(b"modified")
            with patch.object(prod.subprocess, "check_output", return_value=b"committed"):
                with self.assertRaisesRegex(IntegrityError, "different model source"):
                    prod.require_committed_model(tmp, "a"*40)


if __name__ == "__main__":
    unittest.main()

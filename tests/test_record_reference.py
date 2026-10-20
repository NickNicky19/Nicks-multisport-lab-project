"""Synthetic interrupted publication/recovery checks; no actual source reruns."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab.baseline import HistoricalAppearance, forecast_reference
from multisport_lab.integrity import IntegrityError, canonical, read_receipt, stamp, write_receipt
from multisport_lab.ledger import Ledger
from multisport_lab.nba_data import NBAPlayerGame
from multisport_lab import record_reference as publication


NOW = datetime(2026, 10, 20, 12, 0, 0, 123456, tzinfo=timezone.utc)
LATER = NOW + timedelta(hours=1)
COMMIT = "f" * 40


def appearance(event, player, start, fg2m=2):
    return HistoricalAppearance(event, player, "1", "2", start, start+timedelta(hours=4),
                                20, fg2m, 1, 1, 4, 3, 1, 1, 1)


def normalized_row(row):
    return NBAPlayerGame(id_namespace="espn", event_id=row.event_id, player_id=row.player_id,
        team_id="1", opponent_id="2", season_ending_year=2026, season_type="2", event_start=row.event_start,
        participation="APPEARED", minutes=row.minutes, minutes_precision="seconds",
        points=2*row.fg2m+3*row.fg3m+row.ftm, fgm=row.fg2m+row.fg3m, fga=row.fg2m+row.fg3m+3,
        fg2m=row.fg2m, fg3m=row.fg3m, fg3a=row.fg3m+2, ftm=row.ftm, fta=row.ftm+1,
        oreb=1, dreb=3, rebounds=4, assists=3, turnovers=1, blocks=1, steals=1,
        final_status="FINAL", final_periods=4)


class ReferencePublicationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        self.path = self.root / "synthetic-normalized.jsonl"
        start = datetime(2025, 11, 24, 18, tzinfo=timezone.utc)
        self.panel = [appearance("history-a", "p1", start-timedelta(days=14), 1),
                      appearance("history-b", "p2", start-timedelta(days=13), 3)]
        self.panel += [appearance(f"game{game}", player, start+timedelta(days=game-1))
                       for game in range(1, 4) for player in ("p1", "p2")]
        raw = b"\n".join(canonical(normalized_row(row).to_record()) for row in self.panel) + b"\n"
        self.path.write_bytes(raw)
        self.panel_sha = hashlib.sha256(raw).hexdigest()
        self.now = NOW
        self.patches = ExitStack()
        self.patches.enter_context(patch.object(publication, "PANEL_SHA256", self.panel_sha))
        self.reader = self.patches.enter_context(patch.object(publication, "read_normalized_panel",
            return_value=(self.panel, {"input_file_sha256": self.panel_sha})))
        self.patches.enter_context(patch.object(publication, "_now", side_effect=lambda: self.now))
        self.patches.enter_context(patch("multisport_lab.baseline._now", side_effect=lambda: self.now))
        self.patches.enter_context(patch("multisport_lab.ledger._now", side_effect=lambda: self.now))
        clock = self.patches.enter_context(patch("multisport_lab.forecast_contract.datetime", wraps=datetime))
        clock.now.side_effect = lambda *_args: self.now

    def tearDown(self):
        self.patches.close()
        self.temporary.cleanup()

    def record(self):
        return publication.record_examples(self.root, self.path, COMMIT)

    def recover(self, summary, label):
        path = self.root / f"synthetic-{label}.json"
        write_receipt(path, summary)
        return publication.recover_summary(self.root, path)

    def receipts(self):
        return {path.relative_to(self.root): path.read_bytes() for path in self.root.glob("records/*/*.json")}

    def interrupt_partial_batch(self):
        original = Ledger.record_outcome
        calls = 0

        def interrupt(store, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("Synthetic interruption before second outcome")
            return original(store, *args, **kwargs)

        with patch.object(Ledger, "record_outcome", new=interrupt):
            with self.assertRaisesRegex(OSError, "Synthetic interruption"):
                self.record()

    def test_interruption_before_summary_preserves_original_clocks_and_bytes(self):
        with patch.object(publication, "write_receipt", side_effect=OSError("Synthetic summary interruption")):
            with self.assertRaisesRegex(OSError, "summary interruption"):
                self.record()
        before = self.receipts()
        self.assertEqual(len(before), 18)
        self.assertFalse((self.root / publication.SUMMARY_PATH).exists())
        self.now = LATER
        with patch.object(publication, "forecast_reference", side_effect=AssertionError("Must recover original forecasts")):
            summary = self.record()
        self.assertEqual(summary["schema_version"], publication.SUMMARY_V2)
        self.assertEqual(summary["recorded_at"], stamp(LATER))
        self.assertEqual(summary["common_source_observed_at"], stamp(NOW))
        self.assertEqual({row["source_observed_at"] for row in summary["examples"]}, {stamp(NOW)})
        self.assertEqual({row["outcome_received_at"] for row in summary["examples"]}, {stamp(NOW)})
        self.assertEqual(before, self.receipts())
        self.assertTrue(all(row["source_version"] is None for row in summary["examples"]))
        self.assertEqual(self.recover(summary, "restart"), summary)

    def test_partial_resume_records_per_outcome_mixed_clocks_without_false_aggregate(self):
        self.interrupt_partial_batch()
        before = self.receipts()
        self.assertEqual(len(before), 4)  # Two forecasts; one outcome and its grade.
        self.now = LATER
        with patch.object(publication, "forecast_reference", wraps=forecast_reference) as generator:
            summary = self.record()
        self.assertEqual(generator.call_count, 4)
        self.assertNotIn("common_source_observed_at", summary)
        self.assertNotIn("source_observed_at", summary)
        self.assertEqual([row["source_observed_at"] for row in summary["examples"]],
                         [stamp(NOW)] + [stamp(LATER)]*5)
        second = summary["examples"][1]
        self.assertEqual(second["issued_at"], stamp(NOW))
        self.assertGreater(second["source_observed_at"], second["issued_at"])
        self.assertEqual(second["outcome_received_at"], stamp(LATER))
        after = self.receipts()
        self.assertTrue(all(after[path] == raw for path, raw in before.items()))
        self.assertEqual(self.recover(summary, "mixed-restart"), summary)
        false_aggregate = deepcopy(summary)
        false_aggregate["common_source_observed_at"] = stamp(LATER)
        with self.assertRaisesRegex(IntegrityError, "Aggregate source clock"):
            self.recover(false_aggregate, "false-aggregate")

    def test_v1_compatibility_recovers_without_input_or_version_flip_and_checks_global_clock(self):
        summary = self.record()
        legacy = {key: summary[key] for key in publication.SUMMARY_FIELDS}
        legacy["schema_version"] = publication.SUMMARY_V1
        legacy["source_observed_at"] = summary["common_source_observed_at"]
        legacy["examples"] = [{key: example[key] for key in publication.BASE_EXAMPLE_FIELDS}
                              for example in summary["examples"]]
        legacy_root = Path(self.temporary.name) / "legacy"
        shutil.copytree(self.root / "records", legacy_root / "records")
        legacy_path = legacy_root / publication.SUMMARY_PATH
        write_receipt(legacy_path, legacy)
        before = legacy_path.read_bytes()
        with patch.object(publication, "read_normalized_panel", side_effect=AssertionError("No historical rerun")):
            self.assertEqual(publication.record_examples(legacy_root, Path("missing-input"), "unused"), legacy)
        self.assertEqual(legacy_path.read_bytes(), before)
        self.now = LATER
        wrong = deepcopy(legacy)
        wrong["source_observed_at"] = stamp(LATER)
        with self.assertRaisesRegex(IntegrityError, "Aggregate source clock"):
            self.recover(wrong, "legacy-wrong-clock")

    def test_recovery_crosschecks_ref_kinds_dependencies_and_all_example_metadata(self):
        summary = self.record()
        cases = []
        for field, value in (("purpose", "ACCURACY_EVALUATION"), ("evidence_lane", "REAL_TIME_CAPTURED"),
                             ("normalized_input_sha256", "0"*64), ("source_evidence_sha256", "0"*64),
                             ("model_commit", "0"*40), ("genuine_future_issuances", False)):
            changed = deepcopy(summary)
            changed[field] = value
            cases.append(changed)
        for field, value in (("issued_at", stamp(NOW-timedelta(microseconds=1))),
                             ("cutoff_at", stamp(NOW)), ("model_commit", "0"*40),
                             ("model_code_sha256", "0"*64), ("input_sha256", "0"*64),
                             ("joint_sha256", "0"*64), ("source_evidence_sha256", "0"*64),
                             ("source_version", "invented-version"), ("outcome_received_at", stamp(LATER)),
                             ("source_observed_at", stamp(LATER))):
            changed = deepcopy(summary)
            changed["examples"][0][field] = value
            cases.append(changed)
        changed = deepcopy(summary)
        changed["examples"][0]["forecast_ref"] = changed["examples"][0]["outcome_ref"]
        cases.append(changed)
        changed = deepcopy(summary)
        changed["examples"][0]["grade_ref"] = changed["examples"][1]["grade_ref"]
        cases.append(changed)
        changed = deepcopy(summary)
        changed["examples"][1] = deepcopy(changed["examples"][0])
        cases.append(changed)
        for index, changed in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(IntegrityError):
                self.recover(changed, f"tampered-{index}")

    def test_second_pass_panel_bytes_are_rechecked_before_outcomes_or_forecasts(self):
        def audit_then_change(_path):
            self.path.write_bytes(b"changed after synthetic audit\n")
            return self.panel, {"input_file_sha256": self.panel_sha}

        self.reader.side_effect = audit_then_change
        with self.assertRaisesRegex(IntegrityError, "outcome bytes differ"):
            self.record()
        self.assertEqual(self.receipts(), {})
        self.assertFalse((self.root / publication.SUMMARY_PATH).exists())

    def test_summary_cannot_predate_record_receipts_or_exceed_read_budget(self):
        summary = self.record()
        changed = deepcopy(summary)
        changed["recorded_at"] = stamp(NOW-timedelta(microseconds=1))
        with self.assertRaisesRegex(IntegrityError, "predates"):
            self.recover(changed, "predates-records")
        path = self.root / publication.SUMMARY_PATH
        with patch.object(publication, "MAX_SUMMARY_BYTES", 32):
            with self.assertRaisesRegex(IntegrityError, "byte limit"):
                publication.recover_summary(self.root, path)


if __name__ == "__main__":
    unittest.main()

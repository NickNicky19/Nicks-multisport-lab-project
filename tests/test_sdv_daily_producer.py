"""Bounded synthetic joint-law/control tests, never actual study issuance.

The historical loader and fitted laws are explicit tiny stand-ins. No retained
historical panel is fitted, scored, changed or treated as a model evaluation.
"""
from contextlib import ExitStack, nullcontext
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from multisport_lab import sdv_daily_cycle as cycles
from multisport_lab import sdv_daily_inputs as inputs
from multisport_lab import sdv_daily_producer as daily
from multisport_lab.baseline import ForecastTarget, JointForecast, PrimitiveLine, WeightedOutcome
from multisport_lab.integrity import IntegrityError, canonical, digest, stamp, utc
from multisport_lab.ledger import LedgerRef
from test_sdv_daily_cycle import proof
from test_sdv_daily_inputs import csv_bytes, metadata


ISSUE = utc("2026-10-23T00:00:10.000000Z")
NORMALIZED = utc("2026-10-22T23:30:00.000000Z")
HISTORY_CUTOFF = datetime(2026, 9, 1, tzinfo=timezone.utc)


class MemoryStore:
    """In-memory writer for producer control flow; not a durable-store claim."""
    def __init__(self):
        self.project_root = Path("/synthetic-only-do-not-create")
        self.ledger = self
        self.bodies = {}
        self.completions = []
        self.interrupt_model = None

    def lock(self):
        return nullcontext()

    def read(self, ref):
        return {"data": {"daily": self.bodies[ref][1]}}

    def add_input(self, body):
        return self.append_body("research_inputs", body)

    def append_body(self, kind, body, *, references=(), logical_id=None):
        identity = logical_id or digest(body)
        ref = LedgerRef(kind, digest({"kind": kind, "identity": identity}), digest(body))
        if self.interrupt_model is not None and body.get("model_key") == self.interrupt_model:
            raise InterruptedError("Synthetic interruption before missing peer persistence")
        if ref not in self.bodies:
            self.bodies[ref] = (tuple(references), deepcopy(body))
        return ref

    def records(self):
        return [(ref, value[1]) for ref, value in self.bodies.items()]

    def record_completion(self, ref, **clocks):
        self.completions.append((ref, clocks))

    def admission(self, ref):
        return {"eligible": True}

    def _verified_forecast_write(self, body, references):
        return nullcontext()

    def recover(self):
        rows = [(ref, body) for ref, body in self.records() if body["schema_version"] == daily.FORECAST_SCHEMA]
        return {"forecasts": rows}


class DailyProducerFixture(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.now = ISSUE
        self.stack.enter_context(patch.object(daily, "_now", side_effect=lambda: self.now))
        self.stack.enter_context(patch.object(cycles, "_now", side_effect=lambda: self.now))
        self.stack.enter_context(patch.object(inputs, "_now", side_effect=lambda: self.now))
        self.cycle = cycles.load_cycle()
        self.binding = daily.make_source_binding()
        self.binding["commit"] = "a" * 40
        self.binding = daily.seal({key: value for key, value in self.binding.items()
            if key != "binding_id"}, "binding_id")
        original_validate = daily.validate_binding
        self.stack.enter_context(patch.object(daily, "validate_binding",
            side_effect=lambda value, **kwargs: original_validate(value, current=False)))
        # Length only exercises the completeness guard; no panel rows are loaded
        # or fitted. Every object here is explicitly a synthetic placeholder.
        self.history = [SimpleNamespace(outcome_available_at=HISTORY_CUTOFF)] * daily.HISTORY_ROWS
        self.history_ref = LedgerRef("research_inputs", daily.HISTORY_ID, "e" * 64)
        self.stack.enter_context(patch.object(daily, "retained_history",
            return_value=(self.history_ref, self.history, {})))
        self.fit = self.stack.enter_context(patch.object(daily, "_fit_laws", side_effect=self.laws))
        self.store = MemoryStore()

    def input_body(self, mode="DEVELOPMENT_ONLY", *, normalized_at=NORMALIZED):
        event = self.cycle["event"]
        start = event["event_starts_at"]
        schedule = [{"id": event["event_id"], "game_id": event["event_id"],
            "uid": "s:40~l:46~e:" + event["event_id"] + "~c:" + event["event_id"],
            "season": "2027", "season_type": "2", "date": start, "start_date": start,
            "game_date_time": start, "home_id": event["home_team_id"],
            "home_display_name": "Synthetic Home", "away_id": event["away_team_id"],
            "away_display_name": "Synthetic Away", "status_type_name": "STATUS_SCHEDULED",
            "status_type_state": "pre", "status_type_completed": "false", "time_valid": "true"}]
        roster = [{"season": "2027", "athlete_id": row["player_id"],
            "uid": "s:40~l:46~a:" + row["player_id"], "team_id": row["team_id"],
            "team_display_name": "Synthetic Home" if row["team_id"] == "25" else "Synthetic Away",
            "display_name": row["player_label"], "status_type": "active", "status_name": "Active",
            "status_id": "1"} for row in self.cycle["candidates"]]
        raw_schedule, raw_roster = csv_bytes(schedule), csv_bytes(roster)
        sm = metadata(raw_schedule, "schedule", normalized_at)
        rm = metadata(raw_roster, "roster", normalized_at)
        # Genuine normalization takes its clock internally. This patched clock
        # is test-only; no caller clock is admitted in prospective software.
        with patch.object(inputs, "_now", return_value=normalized_at):
            return inputs.normalize_inputs(raw_schedule, raw_roster, sm, rm,
                event_id=event["event_id"], expected_candidates=self.cycle["candidates"],
                mode=mode, normalized_at=normalized_at if mode == "DEVELOPMENT_ONLY" else None)

    def laws(self, history, target):
        # Complete shared primitive atoms deliberately include DD and TD tails.
        lines = [PrimitiveLine(20, 4, 2, 1, 10, 10, 2, 0, 0),
                 PrimitiveLine(30, 5, 1, 2, 10, 4, 1, 0, 1),
                 PrimitiveLine(12, 1, 0, 0, 2, 1, 0, 1, 2)]
        result = {}
        for key, weights in [("R0", [.25, .25, .5]), ("K0", [.2, .3, .5])]:
            atoms = tuple(WeightedOutcome("SYNTHETIC-" + str(index), target.player_id,
                line, weight) for index, (line, weight) in enumerate(zip(lines, weights)))
            result[key] = JointForecast(target, target.cutoff, HISTORY_CUTOFF, "d" * 64,
                atoms, 3, 3)
        return result

    def generate(self, mode="DEVELOPMENT_ONLY"):
        body = self.input_body(mode)
        ref = self.store.add_input(body)
        return body, daily.generate_pair(body, ref, self.cycle, self.binding,
            self.history_ref, self.history, player_id=self.cycle["candidates"][0]["player_id"])


class DailyProducerTests(DailyProducerFixture):
    def test_shared_atoms_preserve_all_categories_and_conditional_participation(self):
        input_body, pair = self.generate()
        self.assertEqual({body["model_key"] for body in pair}, {"R0", "K0"})
        target = ForecastTarget(input_body["event"]["event_id"], pair[0]["player_id"],
            utc(input_body["event"]["event_starts_at"]))
        expected_laws = self.laws(self.history, target)
        for body in pair:
            with self.subTest(model=body["model_key"]):
                self.assertEqual(len(body["categories"]), 14)
                self.assertEqual(body["categories"], daily._categories(expected_laws[body["model_key"]]))
                self.assertEqual(body["joint_recipe"]["support_atom_count"], 3)
                self.assertEqual(body["joint_recipe"]["omitted_atoms"], 0)
                self.assertEqual(body["conditioning"], "CONDITIONAL_ON_APPEARANCE")
                self.assertEqual(body["qualification"], "UNAVAILABLE")
                self.assertEqual(body["history_rows"], 26645)
                self.assertEqual(body["history_panel_cutoff"], stamp(HISTORY_CUTOFF))

    def test_dev_generation_never_has_genuine_issue_time(self):
        _, pair = self.generate()
        for body in pair:
            self.assertEqual(body["evidence_lane"], "DEVELOPMENT_ONLY")
            self.assertIsNone(body["issued_at"])
        bad = deepcopy(pair[0])
        bad["issued_at"] = bad["verified_at"]
        bad = daily.seal({k: v for k, v in bad.items() if k != "forecast_id"}, "forecast_id")
        with self.assertRaisesRegex(IntegrityError, "Development became genuine"):
            daily.validate_forecast(bad)

    def test_tiny_synthetic_prospective_generation_requires_actual_window_and_latency(self):
        _, pair = self.generate("PROSPECTIVE_RESEARCH")
        self.assertTrue(all(body["issued_at"] == stamp(ISSUE) for body in pair))
        self.now = utc(self.cycle["cutoff_at"]) - timedelta(microseconds=1)
        with self.assertRaises(IntegrityError):
            self.generate("PROSPECTIVE_RESEARCH")
        self.now = utc(self.cycle["issuance_closes_at"]) + timedelta(microseconds=1)
        with self.assertRaises(IntegrityError):
            self.generate("PROSPECTIVE_RESEARCH")

    def test_generation_completion_after_five_minutes_is_not_timely(self):
        body = self.input_body("PROSPECTIVE_RESEARCH")
        ref = self.store.add_input(body)
        def delayed(history, target):
            self.now = ISSUE + timedelta(seconds=301)
            return self.laws(history, target)
        self.fit.side_effect = delayed
        with self.assertRaisesRegex(IntegrityError, "issuance window"):
            daily.generate_pair(body, ref, self.cycle, self.binding, self.history_ref,
                self.history, player_id=self.cycle["candidates"][0]["player_id"])
        self.assertFalse(self.store.recover()["forecasts"])

    def test_resealed_impossible_achievement_tails_and_missing_categories_reject(self):
        _, pair = self.generate()
        for mutation in [lambda rows: rows.pop(),
                         lambda rows: next(row for row in rows if row["code"] == "DD").update(
                             pmf=[{"value": 0, "probability": "0.1"}, {"value": 1, "probability": "0.9"}],
                             mean="0.9", interval80=[0, 1])]:
            with self.subTest(mutation=mutation), self.assertRaises(IntegrityError):
                changed = deepcopy(pair[0])
                mutation(changed["categories"])
                changed = daily.seal({k: v for k, v in changed.items() if k != "forecast_id"}, "forecast_id")
                daily.validate_forecast(changed)

    def test_direct_generation_rejects_changed_registered_input_identity(self):
        body = self.input_body()
        bad = deepcopy(body)
        bad["event"]["event_id"] = "999"
        bad["event"]["event_snapshot_id"] = digest({key: value for key, value in bad["event"].items()
            if key != "event_snapshot_id"})
        bad = daily.seal({k: v for k, v in bad.items() if k != "input_id"}, "input_id")
        ref = self.store.add_input(bad)
        with self.assertRaises(IntegrityError):
            daily.generate_pair(bad, ref, self.cycle, self.binding, self.history_ref,
                self.history, player_id=self.cycle["candidates"][0]["player_id"])

    def test_partial_peer_retry_recovers_original_and_generates_only_missing_records(self):
        body = self.input_body()
        ref = self.store.add_input(body)
        self.store.interrupt_model = "K0"
        with self.assertRaises(InterruptedError):
            daily.issue_cycle(self.store, ref, self.cycle, self.binding)
        originals = self.store.recover()["forecasts"]
        self.assertEqual(len(originals), 1)
        original_ref, original = originals[0]
        original_bytes = canonical(original)
        self.store.interrupt_model = None
        self.now += timedelta(seconds=1)
        result = daily.issue_cycle(self.store, ref, self.cycle, self.binding)
        self.assertEqual(len(result["forecasts"]), 8)
        self.assertEqual(canonical(self.store.read(original_ref)["data"]["daily"]), original_bytes)
        self.fit.reset_mock()
        self.assertEqual(len(daily.issue_cycle(self.store, ref, self.cycle, self.binding)["forecasts"]), 8)
        self.fit.assert_not_called()

    def test_partial_peer_recovery_rejects_different_input_and_source_revision(self):
        body = self.input_body()
        ref = self.store.add_input(body)
        self.store.interrupt_model = "K0"
        with self.assertRaises(InterruptedError):
            daily.issue_cycle(self.store, ref, self.cycle, self.binding)
        self.store.interrupt_model = None
        changed_ref = self.store.add_input(self.input_body(normalized_at=NORMALIZED + timedelta(seconds=1)))
        with self.assertRaisesRegex(IntegrityError, "different input or producer"):
            daily.issue_cycle(self.store, changed_ref, self.cycle, self.binding)
        changed = deepcopy(self.binding)
        changed["files"]["multisport_lab/sdv_daily_cycle.py"] = "f" * 64
        changed = daily.seal({k: v for k, v in changed.items() if k != "binding_id"}, "binding_id")
        with self.assertRaisesRegex(IntegrityError, "different input or producer"):
            daily.issue_cycle(self.store, ref, self.cycle, changed)
        self.assertEqual(len(self.store.recover()["forecasts"]), 1)

    def test_late_missing_prospective_peer_preserves_original_without_backfilling(self):
        body = self.input_body("PROSPECTIVE_RESEARCH")
        ref = self.store.add_input(body)
        authorization = proof(self.cycle, self.binding)
        authorization_ref = self.store.append_body("input_captures", authorization)
        # A synthetic in-memory context permits testing the producer's separate
        # deadline guard. Genuine runtime authentication has its own tests.
        with patch.object(cycles, "require_dispatch_context", return_value=authorization):
            self.store.interrupt_model = "K0"
            with self.assertRaises(InterruptedError):
                daily.issue_cycle(self.store, ref, self.cycle, self.binding,
                    authorization_ref=authorization_ref)
            original_ref, original = self.store.recover()["forecasts"][0]
            original_bytes = canonical(original)
            self.store.interrupt_model = None
            self.now = utc(self.cycle["issuance_closes_at"]) + timedelta(microseconds=1)
            with self.assertRaises(IntegrityError):
                daily.issue_cycle(self.store, ref, self.cycle, self.binding,
                    authorization_ref=authorization_ref)
            self.assertEqual(len(self.store.recover()["forecasts"]), 1)
            self.assertEqual(canonical(self.store.read(original_ref)["data"]["daily"]), original_bytes)

    def test_dnp_is_not_zero_production_or_financial_settlement(self):
        _, pair = self.generate()
        original = pair[0]
        original_bytes = canonical(original)
        self.now = utc(original["event_starts_at"]) + timedelta(hours=4)
        outcome = {"schema_version": daily.OUTCOME_SCHEMA, "protocol_id": daily.PROTOCOL_ID,
            **{key: original[key] for key in ("cycle_id", "mode", "event_id", "event_snapshot_id",
                "event_starts_at", "player_id", "team_id", "opponent_id")},
            "status": "DNP", "source_refs": [self.history_ref.to_record()],
            "source_observed_at": stamp(self.now), "normalized_at": stamp(self.now),
            "normalizer_version": "SYNTHETIC_ONLY", "primitives": None, "minutes": None,
            "minutes_precision": None, "categories": []}
        outcome = daily.seal(outcome, "outcome_id")
        grade = daily.make_grade(original, outcome)
        self.assertEqual(grade["status"], "DNP_NOT_SCORED")
        self.assertEqual(grade["categories"], [])
        self.assertEqual(grade["financial_settlement"], "NOT_EVALUATED")
        self.assertEqual(canonical(original), original_bytes)
        self.assertEqual(daily.validate_grade(grade, original, outcome), grade)
        invalid = deepcopy(outcome)
        invalid["minutes"] = 0
        invalid = daily.seal({k: v for k, v in invalid.items() if k != "outcome_id"}, "outcome_id")
        with self.assertRaisesRegex(IntegrityError, "cannot become zero"):
            daily.validate_outcome(invalid)

    def test_frozen_law_binding_or_truncated_history_cannot_generate(self):
        wrong = deepcopy(self.binding)
        wrong["files"]["multisport_lab/baseline.py"] = "0" * 64
        wrong = daily.seal({k: v for k, v in wrong.items() if k != "binding_id"}, "binding_id")
        with self.assertRaises(IntegrityError):
            daily.validate_binding(wrong)
        body = self.input_body()
        ref = self.store.add_input(body)
        with self.assertRaisesRegex(IntegrityError, "complete fixed history"):
            daily.generate_pair(body, ref, self.cycle, self.binding, self.history_ref,
                self.history[:-1], player_id=self.cycle["candidates"][0]["player_id"])
        self.fit.assert_not_called()


if __name__ == "__main__":
    unittest.main()

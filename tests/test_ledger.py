"""Synthetic receipt/grading checks in temporary storage; no future evidence."""
from dataclasses import replace
from copy import deepcopy
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab.integrity import IntegrityError, canonical, digest, read_receipt, stamp, write_receipt
from multisport_lab.ledger import Ledger, LedgerRef, SCHEMA, validate_grade, validate_outcome
from multisport_lab.baseline import ForecastTarget, HistoricalAppearance, forecast_reference
from multisport_lab.forecast_contract import from_reference
from multisport_lab.nba_data import NBAPlayerGame


NOW = datetime(2026, 10, 20, 12, 0, 0, 123456, tzinfo=timezone.utc)
LATER = NOW + timedelta(seconds=10)


def typed_bundle():
    start = datetime(2024, 1, 1, 20, tzinfo=timezone.utc)
    rows = [HistoricalAppearance("history", f"p{i}", "1", "2", start, start+timedelta(hours=4),
                                20, fg2m, 0, 0, rebounds, assists, 0, 0, 0)
            for i, fg2m, rebounds, assists in ((2, 1, 0, 0), (3, 5, 10, 10))]
    observed = HistoricalAppearance("target", "p1", "1", "2", start+timedelta(days=31),
                                    start+timedelta(days=31, hours=4), 20, 1, 0, 0, 0, 0, 0, 0, 0)
    target = ForecastTarget(observed.event_id, observed.player_id, observed.event_start)
    with patch("multisport_lab.baseline._now", return_value=NOW-timedelta(minutes=1)):
        forecast = forecast_reference(rows, target)
    with patch("multisport_lab.forecast_contract.datetime") as clock:
        clock.now.return_value = NOW
        typed_bundle.last_reference = forecast
        return from_reference(forecast, observed, model_commit="f"*40)


def outcome_row(**changes):
    values = dict(id_namespace="espn", event_id="target", player_id="p1", team_id="1", opponent_id="2",
                  season_ending_year=2024, season_type="2", event_start=datetime(2024, 2, 1, 20, tzinfo=timezone.utc),
                  participation="APPEARED", minutes=20, minutes_precision="seconds", points=2,
                  fgm=1, fga=2, fg2m=1, fg3m=0, fg3a=0, ftm=0, fta=0, oreb=0, dreb=0,
                  rebounds=0, assists=0, turnovers=0, blocks=0, steals=0, final_status="FINAL", final_periods=4)
    return NBAPlayerGame(**(values | changes))


def rehash(body, key):
    body = {k: v for k, v in body.items() if k != key}
    return {key: digest(body), **body}


class ReceiptStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = Ledger(self.root)
        self.clock = patch("multisport_lab.ledger._now", return_value=NOW)
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.temporary.cleanup()

    def record(self, kind="forecasts", logical="test-record", **changes):
        data = {"identity": {"event_id": "synthetic-g1", "player_id": "synthetic-p1"},
                "issued_at": "2026-10-20T11:59:00.000001Z", "evidence_lane": "SYNTHETIC_TEST"}
        data.update(changes)
        return self.store.append(kind, logical, data)

    def path(self, ref):
        return self.root / "records" / ref.kind / f"{ref.record_id}.json"

    def test_retry_after_restart_preserves_original_received_and_issued_clocks(self):
        original = self.record()
        before = self.path(original).read_bytes()
        with patch("multisport_lab.ledger._now", return_value=LATER):
            restarted = Ledger(self.root)
            retry = restarted.append("forecasts", "test-record", self.store.read(original)["data"])
        self.assertEqual(original, retry)
        self.assertEqual(self.path(original).read_bytes(), before)
        payload = restarted.read(retry)
        self.assertEqual(payload["received_at"], "2026-10-20T12:00:00.123456Z")
        self.assertEqual(payload["data"]["issued_at"], "2026-10-20T11:59:00.000001Z")
        self.assertEqual(len(restarted.scan()["forecasts"]), 1)
        self.assertEqual(payload["persistence_status"], "LOCAL_RECEIPT_ONLY")

    def test_changed_clock_or_data_cannot_overwrite_same_logical_record(self):
        original = self.record()
        before = self.path(original).read_bytes()
        for change in ({"issued_at": "2026-10-20T11:58:00.000001Z"}, {"new_field": 1}):
            with self.assertRaisesRegex(IntegrityError, "conflicting logical record"):
                self.record(**change)
        self.assertEqual(before, self.path(original).read_bytes())

    def test_missing_corrupt_and_inexact_references_fail(self):
        original = self.record()
        bad = LedgerRef(original.kind, original.record_id, "0" * 64)
        with self.assertRaisesRegex(IntegrityError, "referenced payload hash"):
            self.store.append("grades", "grade1", {}, references=(bad,))
        with self.assertRaises(FileNotFoundError):
            self.store.append("grades", "grade1", {}, references=(LedgerRef("forecasts", "1"*64, "2"*64),))
        self.path(original).write_bytes(b"{}")
        with self.assertRaises(IntegrityError):
            self.store.scan()

    def test_scan_checks_hashes_reference_clocks_and_schema(self):
        original = self.record()
        dependent = self.store.append("grades", "grade1", {}, references=(original,))
        self.assertEqual(len(Ledger(self.root).scan()["grades"]), 1)
        self.path(original).unlink()
        with self.assertRaisesRegex(IntegrityError, "missing or changed"):
            self.store.scan()
        self.assertTrue(self.path(dependent).exists())

    def test_create_only_corrections_chain_and_preserve_originals(self):
        old = self.record("outcomes", "outcome1", points=10)
        new = self.record("outcomes", "outcome2", points=11)
        newest = self.record("outcomes", "outcome3", points=12)
        before = self.path(old).read_bytes()
        correction = self.store.correct(old, new, reason="Synthetic scoring correction")
        self.assertEqual(self.store.correct(old, new, reason="Synthetic scoring correction"), correction)
        self.store.correct(new, newest, reason="Second synthetic correction")
        self.assertEqual(Ledger(self.root).latest(old), newest)
        self.assertEqual(self.path(old).read_bytes(), before)
        self.assertEqual(len(self.store.scan()["outcomes"]), 3)
        self.assertEqual(len(self.store.scan()["corrections"]), 2)

    def test_correction_branch_cycle_and_identity_change_are_rejected(self):
        old = self.record("outcomes", "outcome1", points=10)
        new = self.record("outcomes", "outcome2", points=11)
        other = self.record("outcomes", "outcome3", points=12)
        wrong = self.record("outcomes", "outcome4", identity={"event_id": "different", "player_id": "p1"})
        self.store.correct(old, new, reason="Synthetic correction")
        with self.assertRaisesRegex(IntegrityError, "conflicting logical record"):
            self.store.correct(old, other, reason="A second branch")
        with self.assertRaisesRegex(IntegrityError, "cycle"):
            self.store.correct(new, old, reason="Cycle")
        with self.assertRaisesRegex(IntegrityError, "subject identity"):
            self.store.correct(new, wrong, reason="Wrong event")

    def test_direct_append_cannot_poison_store_with_cycle_or_second_branch(self):
        old = self.record("outcomes", "outcome1", points=10)
        new = self.record("outcomes", "outcome2", points=11)
        other = self.record("outcomes", "outcome3", points=12)
        self.store.correct(old, new, reason="Synthetic correction")
        for logical, original, replacement, message in (
                ("bad-cycle", new, old, "cycle"), ("bad-branch", old, other, "branches")):
            with self.assertRaises(IntegrityError):
                self.store.append("corrections", logical,
                    {"reason": "Should fail before writing", "replacement": replacement.to_record()},
                    references=(original, replacement), supersedes=original)
            invalid_id = digest({"kind": "corrections", "logical_id": logical})
            self.assertFalse((self.root / "records/corrections" / f"{invalid_id}.json").exists())
        self.assertEqual(len(self.store.scan()["corrections"]), 1)

    def test_receipt_creation_clock_cannot_be_in_future_on_restart(self):
        ref = self.record()
        payload = self.store.read(ref)
        payload["received_at"] = "2026-10-21T00:00:00.000000Z"
        self.path(ref).unlink()
        write_receipt(self.path(ref), payload)
        with self.assertRaisesRegex(IntegrityError, "creation clock is in the future"):
            Ledger(self.root).scan()

    def test_total_receipt_count_cap_is_cross_kind_and_identical_retry_still_works(self):
        with patch("multisport_lab.ledger.MAX_LEDGER_RECORDS", 2):
            original = self.record("forecasts", "one")
            self.record("outcomes", "two")
            self.assertEqual(self.record("forecasts", "one"), original)
            with self.assertRaisesRegex(IntegrityError, "total receipt count budget"):
                self.record("grades", "three")
            self.assertEqual(sum(len(rows) for rows in self.store.scan().values()), 2)
            third_id = digest({"kind": "grades", "logical_id": "three"})
            self.assertFalse((self.root / "records/grades" / f"{third_id}.json").exists())
        with patch("multisport_lab.ledger.MAX_LEDGER_RECORDS", 1), patch("multisport_lab.ledger.read_receipt") as reader:
            with self.assertRaisesRegex(IntegrityError, "total receipt count budget"):
                self.store.scan()
            reader.assert_not_called()

    def test_total_byte_cap_uses_exact_envelope_bytes_and_rejects_before_decoding(self):
        original = self.record("forecasts", "one")
        size = self.path(original).stat().st_size
        with patch("multisport_lab.ledger.MAX_LEDGER_BYTES", size):
            self.assertEqual(self.record("forecasts", "one"), original)
            self.assertEqual(len(self.store.scan()["forecasts"]), 1)
            with self.assertRaisesRegex(IntegrityError, "total receipt byte budget"):
                self.record("outcomes", "two")
            self.assertEqual(len(list(self.root.glob("records/*/*.json"))), 1)
        with patch("multisport_lab.ledger.MAX_LEDGER_BYTES", size-1), patch("multisport_lab.ledger.read_receipt") as reader:
            with self.assertRaisesRegex(IntegrityError, "total receipt byte budget"):
                self.store.scan()
            reader.assert_not_called()

    def test_unpublished_interruption_files_consume_budget_without_becoming_records(self):
        original = self.record()
        temporary = self.path(original).parent / ".receipt-interrupted"
        temporary.write_bytes(b"partial")
        with patch("multisport_lab.ledger.MAX_LEDGER_RECORDS", 2):
            self.assertEqual(len(self.store.scan()["forecasts"]), 1)
            with self.assertRaisesRegex(IntegrityError, "total receipt count budget"):
                self.record("outcomes", "new")
        with patch("multisport_lab.ledger.MAX_LEDGER_BYTES", self.path(original).stat().st_size):
            with self.assertRaisesRegex(IntegrityError, "total receipt byte budget"):
                self.store.scan()

    def test_references_and_json_are_strict_and_paths_cannot_escape(self):
        for kind, record_id in (("../outcomes", "0"*64), ("forecasts", "../escape")):
            with self.assertRaises(IntegrityError):
                LedgerRef(kind, record_id, "0"*64)
        for bad in ({"n": float("nan")}, {"n": (1, 2)}, {1: "bad"}):
            with self.assertRaises(IntegrityError):
                self.store.append("forecasts", "bad", bad)
        (self.root / "records").symlink_to(self.root / "other", target_is_directory=True)
        with self.assertRaisesRegex(IntegrityError, "symlinks"):
            self.record()

    def test_partial_temp_files_are_ignored_but_unrecognized_records_fail(self):
        ref = self.record()
        directory = self.path(ref).parent
        (directory / ".receipt-interrupted").write_bytes(b"partial")
        self.assertEqual(len(self.store.scan()["forecasts"]), 1)
        (directory / "unrecognized.json").write_bytes(b"{}")
        with self.assertRaisesRegex(IntegrityError, "unrecognized file"):
            self.store.scan()

    def test_inputs_are_deep_copied_and_corrupt_files_are_never_repaired(self):
        data = {"nested": {"n": [1]}}
        ref = self.store.append("forecasts", "copied", data)
        data["nested"]["n"].append(2)
        self.assertEqual(self.store.read(ref)["data"], {"nested": {"n": [1]}})
        self.path(ref).write_bytes(b"broken")
        with self.assertRaises(IntegrityError):
            self.store.append("forecasts", "copied", {"nested": {"n": [1]}})
        self.assertEqual(self.path(ref).read_bytes(), b"broken")


class TypedIssuanceAndGradingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = Ledger(self.root)
        self.clock = patch("multisport_lab.ledger._now", return_value=NOW)
        self.clock.start()
        self.forecast_clock = patch("multisport_lab.forecast_contract.datetime")
        self.forecast_clock.start().now.return_value = NOW

    def tearDown(self):
        self.forecast_clock.stop()
        self.clock.stop()
        self.temporary.cleanup()

    def outcome(self, row=None, **kwargs):
        return self.store.record_outcome(row or outcome_row(), source_evidence_sha256="a"*64,
                                         source_observed_at=NOW-timedelta(minutes=10), **kwargs)

    def issue(self, bundle=None):
        bundle = bundle or typed_bundle()
        return self.store.issue_forecast(bundle, reference=typed_bundle.last_reference)

    def test_issue_readback_and_per_category_grade_reproduce_weighted_rps(self):
        bundle = typed_bundle()
        forecast = self.issue(bundle)
        outcome = self.outcome()
        grade_ref = self.store.grade_forecast(forecast, outcome)
        grade = self.store.read(grade_ref)["data"]["grade"]
        self.assertEqual(grade["status"], "SCORED")
        self.assertEqual(grade["financial_settlement"], "NOT_EVALUATED")
        rows = {row["code"]: row for row in grade["categories"]}
        self.assertEqual(len(rows), 14)
        self.assertEqual(rows["PTS"]["crps"], "2")
        self.assertEqual(rows["DD"]["brier"], "0.25")
        self.assertEqual(rows["TD"]["brier"], "0.25")
        self.assertIsNone(rows["PTS"]["brier"])
        self.assertEqual(self.store.read(forecast)["data"]["bundle"]["issued_at"], bundle["issued_at"])
        with patch("multisport_lab.ledger._now", return_value=LATER):
            restarted = Ledger(self.root)
            self.assertEqual(restarted.issue_forecast(bundle, reference=typed_bundle.last_reference), forecast)
            self.assertEqual(restarted.grade_forecast(forecast, outcome), grade_ref)
            self.assertEqual(list(restarted.iter_forecasts()), [bundle])
            self.assertEqual(list(restarted.iter_grades()), [grade])
        validate_grade(grade, bundle, self.store.read(outcome)["data"]["outcome"])

    def test_dnp_and_unresolved_outcomes_are_not_zero_stat_lines(self):
        bundle = typed_bundle()
        forecast = self.issue(bundle)
        row = outcome_row()
        nulls = {name: None for name in ("minutes", "points", "fgm", "fga", "fg2m", "fg3m", "fg3a", "ftm", "fta",
                                             "oreb", "dreb", "rebounds", "assists", "turnovers", "blocks", "steals")}
        dnp = self.outcome(replace(row, participation="DNP", **nulls))
        unresolved = self.outcome(replace(row, final_status="NOT_FINAL", final_periods=None))
        for ref, expected in ((dnp, "DNP_NOT_SCORED"), (unresolved, "UNRESOLVED")):
            grade = self.store.read(self.store.grade_forecast(forecast, ref))["data"]["grade"]
            self.assertEqual(grade["status"], expected)
            self.assertEqual(grade["categories"], [])
            outcome = self.store.read(ref)["data"]["outcome"]
            self.assertIsNone(outcome["primitives"])
            self.assertEqual(outcome["categories"], [])

    def test_wrong_identity_changed_scores_and_incoherent_primitives_fail(self):
        bundle = typed_bundle()
        forecast = self.issue(bundle)
        outcome = self.outcome()
        with self.assertRaisesRegex(IntegrityError, "target identity mismatch"):
            self.store.grade_forecast(forecast, self.outcome(outcome_row(player_id="another")))
        grade = self.store.read(self.store.grade_forecast(forecast, outcome))["data"]["grade"]
        grade["categories"][0]["crps"] = "999"
        grade = rehash(grade, "grade_id")
        with self.assertRaisesRegex(IntegrityError, "does not reproduce|does not match"):
            validate_grade(grade, bundle, self.store.read(outcome)["data"]["outcome"])
        actual = self.store.read(outcome)["data"]["outcome"]
        actual["primitives"]["FGM"] = 9
        with self.assertRaisesRegex(IntegrityError, "coherent nonnegative"):
            validate_outcome(rehash(actual, "outcome_id"))

    def test_zero_support_is_explicit_and_does_not_drop_category(self):
        bundle = typed_bundle()
        forecast = self.issue(bundle)
        outcome = self.outcome(outcome_row(points=4, fg2m=2, fgm=2))
        grade = self.store.read(self.store.grade_forecast(forecast, outcome))["data"]["grade"]
        pts = next(row for row in grade["categories"] if row["code"] == "PTS")
        self.assertEqual(pts["log_loss_status"], "ZERO_SUPPORT")
        self.assertIsNone(pts["log_loss"])
        self.assertEqual(len(grade["categories"]), 14)

    def future_bundle(self, capture_ids):
        bundle = typed_bundle()
        bundle.update(event_starts_at="2026-10-20T13:30:00.123456Z",
                      cutoff_at="2026-10-20T12:00:00.123456Z",
                      history_freeze="2026-10-20T00:00:00.000000Z",
                      issued_at="2026-10-20T12:00:00.123456Z",
                      evidence_lane="REAL_TIME_CAPTURED", availability_basis="OBSERVED_INPUT_CAPTURE",
                      input_capture_ids=capture_ids)
        return rehash(bundle, "forecast_id")

    def capture(self, **changes):
        metadata = {"id_namespace": "espn", "league": "NBA", "event_id": "target", "player_id": "p1",
                    "event_starts_at": "2026-10-20T13:30:00.123456Z", "input_sha256": typed_bundle()["input_sha256"],
                    "source_version": "synthetic-input-v1", "source_evidence_sha256": "b"*64,
                    "access_basis": "SYNTHETIC_TEMPORARY_TEST_ONLY"}
        return self.store.record_input_capture(metadata | changes)

    def test_real_time_lane_is_unavailable_for_current_r0_even_with_capture_receipt(self):
        with self.assertRaisesRegex(IntegrityError, "does not support REAL_TIME_CAPTURED"):
            self.issue(self.future_bundle(["d"*64]))
        ref = self.capture()
        capture = self.store.read(ref)["data"]["capture"]
        self.assertEqual(capture["observed_at"], "2026-10-20T12:00:00.123456Z")
        self.assertEqual(self.capture(), ref)
        bundle = self.future_bundle([capture["capture_id"]])
        with self.assertRaisesRegex(IntegrityError, "does not support REAL_TIME_CAPTURED"):
            self.issue(bundle)
        self.assertEqual(self.store.scan()["forecasts"], {})

    def test_real_time_capture_clock_is_local_and_relabeling_never_grants_issuance(self):
        for changes in ({"player_id": "wrong"}, {"input_sha256": "c"*64}):
            ref = self.capture(**changes)
            capture = self.store.read(ref)["data"]["capture"]
            with self.assertRaisesRegex(IntegrityError, "does not support REAL_TIME_CAPTURED"):
                self.issue(self.future_bundle([capture["capture_id"]]))
        with patch("multisport_lab.ledger._now", return_value=NOW+timedelta(seconds=1)):
            ref = self.capture(source_version="later-capture")
            capture = self.store.read(ref)["data"]["capture"]
            self.assertEqual(capture["observed_at"], "2026-10-20T12:00:01.123456Z")
            with self.assertRaisesRegex(IntegrityError, "does not support REAL_TIME_CAPTURED"):
                self.issue(self.future_bundle([capture["capture_id"]]))

    def test_actual_joint_reference_required_and_attestation_rechecked_on_restart(self):
        bundle = typed_bundle()
        with self.assertRaisesRegex(IntegrityError, "coherent generator reference"):
            self.store.issue_forecast(bundle)
        ref = self.issue(bundle)
        data = self.store.read(ref)["data"]
        self.assertEqual(data["producer_verification"]["forecast_sha256"], digest(bundle))
        self.assertEqual(data["producer_verification"]["producer_check"]["categories_sha256"], digest(bundle["categories"]))
        data["producer_verification"]["producer_check"]["joint_sha256"] = "0"*64
        original = self.store.read(ref)
        original["data"] = data
        self.path_for(ref).unlink()
        write_receipt(self.path_for(ref), original)
        with self.assertRaisesRegex(IntegrityError, "attestation"):
            Ledger(self.root).scan()

    def test_direct_typed_grade_append_requires_refs_and_recomputes_before_write(self):
        bundle = typed_bundle()
        forecast, outcome = self.issue(bundle), self.outcome()
        ref = self.store.grade_forecast(forecast, outcome)
        payload = self.store.read(ref)
        self.path_for(ref).unlink()
        with self.assertRaisesRegex(IntegrityError, "exact forecast/outcome references"):
            self.store.append("grades", payload["logical_id"], payload["data"])
        self.assertFalse(self.path_for(ref).exists())
        payload["data"]["grade"]["categories"][0]["crps"] = "999"
        payload["data"]["grade"] = rehash(payload["data"]["grade"], "grade_id")
        with self.assertRaisesRegex(IntegrityError, "does not reproduce|does not match"):
            self.store.append("grades", payload["logical_id"], payload["data"], references=(forecast, outcome))
        self.assertFalse(self.path_for(ref).exists())
        write_receipt(self.path_for(ref), payload)
        with self.assertRaisesRegex(IntegrityError, "does not reproduce|does not match"):
            Ledger(self.root).scan()

    def test_typed_outcome_and_capture_clocks_cannot_be_backfilled_past_receipt(self):
        outcome = self.outcome()
        payload = self.store.read(outcome)
        payload["received_at"] = "2026-10-20T11:00:00.000000Z"
        self.path_for(outcome).unlink()
        write_receipt(self.path_for(outcome), payload)
        with self.assertRaisesRegex(IntegrityError, "observation exceeds its receipt"):
            Ledger(self.root).scan()
        self.path_for(outcome).unlink()
        capture = self.capture()
        payload = self.store.read(capture)
        original = payload["data"]["capture"]
        original["observed_at"] = "2026-10-20T11:00:00.000000Z"
        payload["data"]["capture"] = rehash(original, "capture_id")
        self.path_for(capture).unlink()
        write_receipt(self.path_for(capture), payload)
        with self.assertRaisesRegex(IntegrityError, "actual receipt creation"):
            Ledger(self.root).scan()

    def test_public_forecast_only_validation_recomputes_crps_log_and_brier(self):
        bundle = typed_bundle()
        ref = self.store.grade_forecast(self.issue(bundle), self.outcome())
        grade = self.store.read(ref)["data"]["grade"]
        self.assertEqual(validate_grade(grade, forecast=bundle), grade)
        for code, field, value in (("PTS", "crps", "999"), ("PTS", "log_loss", "999"),
                                   ("DD", "brier", "0.1")):
            changed = deepcopy(grade)
            next(row for row in changed["categories"] if row["code"] == code)[field] = value
            changed = rehash(changed, "grade_id")
            with self.assertRaisesRegex(IntegrityError, "does not match its forecast PMF"):
                validate_grade(changed, forecast=bundle)

    def test_publication_active_views_follow_corrections_and_exclude_dependent_old_grades(self):
        bundle = typed_bundle()
        forecast = self.issue(bundle)
        original_outcome = self.outcome()
        original_grade = self.store.grade_forecast(forecast, original_outcome)
        self.assertEqual(len(list(self.store.iter_active_forecasts())), 1)
        self.assertEqual(len(list(self.store.iter_active_grades())), 1)

        replacement_outcome = self.outcome(outcome_row(points=4, fg2m=2, fgm=2))
        self.store.correct(original_outcome, replacement_outcome, reason="Synthetic outcome correction")
        self.assertEqual(list(Ledger(self.root).iter_active_grades()), [])
        replacement_grade = self.store.grade_forecast(forecast, replacement_outcome)
        self.store.correct(original_grade, replacement_grade, reason="Grade the corrected outcome")
        restarted = Ledger(self.root)
        self.assertEqual([grade["outcome_id"] for grade in restarted.iter_active_grades()],
                         [restarted.read(replacement_outcome)["data"]["outcome"]["outcome_id"]])
        self.assertEqual(len(list(restarted.iter_grades())), 2)

        reference = replace(typed_bundle.last_reference, issued_at=NOW)
        replacement_bundle = rehash(bundle | {"issued_at": "2026-10-20T12:00:00.123456Z"}, "forecast_id")
        replacement_forecast = self.store.issue_forecast(replacement_bundle, reference=reference)
        self.store.correct(forecast, replacement_forecast, reason="Synthetic forecast revision")
        restarted = Ledger(self.root)
        self.assertEqual(list(restarted.iter_active_forecasts()), [replacement_bundle])
        self.assertEqual(list(restarted.iter_active_grades()), [])
        newest_grade = restarted.grade_forecast(replacement_forecast, replacement_outcome)
        self.assertEqual([grade["grade_id"] for grade in Ledger(self.root).iter_active_grades()],
                         [restarted.read(newest_grade)["data"]["grade"]["grade_id"]])
        self.assertEqual(len(list(restarted.iter_forecasts())), 2)
        self.assertEqual(len(list(restarted.iter_grades())), 3)
        self.assertEqual(restarted.read(original_grade)["data"]["grade"]["forecast_id"], bundle["forecast_id"])

    def path_for(self, ref):
        return self.root / "records" / ref.kind / f"{ref.record_id}.json"

    def test_outcome_capture_is_actual_and_final_cannot_precede_event(self):
        with self.assertRaisesRegex(IntegrityError, "in the future"):
            self.store.record_outcome(outcome_row(), source_evidence_sha256="a"*64, source_observed_at=LATER)
        with self.assertRaisesRegex(IntegrityError, "before the event"):
            self.store.record_outcome(outcome_row(), source_evidence_sha256="a"*64,
                                      source_observed_at=datetime(2024, 1, 1, tzinfo=timezone.utc))


class ProspectiveLedgerTests(unittest.TestCase):
    """Synthetic actual-clock operating tests; no future research evidence."""

    def setUp(self):
        from prospective_fixtures import CUTOFF, synthetic_pack
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.temporary = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.root = Path(self.temporary)
        self.store = Ledger(self.root)
        self.cutoff = CUTOFF
        self.issue_time = CUTOFF + timedelta(seconds=1)
        self.pack = synthetic_pack()
        self.ledger_clock = self.stack.enter_context(patch("multisport_lab.ledger._now", return_value=self.issue_time))
        self.stack.enter_context(patch("multisport_lab.pregame_sources._now", return_value=self.issue_time))
        self.stack.enter_context(patch("multisport_lab.prospective._now", return_value=self.issue_time))
        self.stack.enter_context(patch("multisport_lab.baseline._now", return_value=self.issue_time))
        self.forecast_clock = self.stack.enter_context(patch("multisport_lab.forecast_contract.datetime"))
        self.forecast_clock.now.return_value = self.issue_time
        # The common two-row fixture replaces only explicit cohort/version pins;
        # production keeps the complete original panel and fixed selected event.
        panel_hash = self.pack["history_provenance"]["normalized_panel_sha256"]
        self.stack.enter_context(patch("multisport_lab.pregame_sources.PANEL_SHA", panel_hash))
        self.stack.enter_context(patch("multisport_lab.prospective.PILOT_PANEL_SHA256", panel_hash))
        self.stack.enter_context(patch("multisport_lab.prospective.PILOT_HISTORY_ROWS", 2))
        self.stack.enter_context(patch("multisport_lab.prospective.PILOT_EVENT_VERSION", self.pack["event"]["event_version"]))
        self.stack.enter_context(patch("multisport_lab.prospective.PILOT_SELECTION_SHA256", digest(self.pack["selection"])))

    def prepare(self):
        with patch("multisport_lab.ledger._now", return_value=self.cutoff-timedelta(minutes=3)):
            return self.store.record_research_inputs(self.pack)

    def generate(self, input_ref):
        from multisport_lab.prospective import generate
        return generate(self.pack, "10", input_record_id=input_ref.record_id, model_commit="f"*40)

    def path(self, ref):
        return self.root/"records"/ref.kind/f"{ref.record_id}.json"

    def test_separate_pregame_issue_survives_restart_without_resetting_original_clocks(self):
        input_ref = self.prepare()
        bundle, joint = self.generate(input_ref)
        forecast = self.store.issue_prospective(bundle, reference=joint, input_ref=input_ref)
        before = {ref: self.path(ref).read_bytes() for ref in (input_ref, forecast)}
        after_event = self.cutoff+timedelta(hours=3)
        with patch("multisport_lab.ledger._now", return_value=after_event):
            restarted = Ledger(self.root)
            self.assertEqual(restarted.issue_prospective(bundle, reference=joint, input_ref=input_ref), forecast)
            self.assertEqual(restarted.record_research_inputs(self.pack), input_ref)
            index = restarted.scan()
        self.assertEqual([len(index[key]) for key in ("research_inputs", "forecasts", "outcomes", "grades")], [1, 1, 0, 0])
        self.assertEqual(len(bundle["categories"]), 14)
        for ref, content in before.items():
            self.assertEqual(self.path(ref).read_bytes(), content)

    def test_new_forecast_requires_inputs_received_by_cutoff(self):
        input_ref = self.store.record_research_inputs(self.pack)
        bundle, joint = self.generate(input_ref)
        with self.assertRaisesRegex(IntegrityError, "not durably recorded by the cutoff"):
            self.store.issue_prospective(bundle, reference=joint, input_ref=input_ref)
        self.assertEqual(self.store.scan()["forecasts"], {})

    def test_generic_append_cannot_create_a_new_self_attested_prospective_record(self):
        input_ref = self.prepare()
        bundle, joint = self.generate(input_ref)
        forecast = self.store.issue_prospective(bundle, reference=joint, input_ref=input_ref)
        payload = self.store.read(forecast)
        self.path(forecast).unlink()
        with self.assertRaisesRegex(IntegrityError, "verified issue_prospective API"):
            self.store.append("forecasts", payload["logical_id"], payload["data"], references=(input_ref,))
        self.assertFalse(self.path(forecast).exists())
        self.assertIsNone(self.store._verified_prospective_append)

    def test_new_persistence_after_deadline_cannot_reuse_an_earlier_issue_string(self):
        input_ref = self.prepare()
        bundle, joint = self.generate(input_ref)
        with patch("multisport_lab.ledger._now", return_value=self.cutoff+timedelta(minutes=5, microseconds=1)):
            with self.assertRaisesRegex(IntegrityError, "outside the T90"):
                self.store.issue_prospective(bundle, reference=joint, input_ref=input_ref)
        self.assertEqual(self.store.scan()["forecasts"], {})

    def test_restart_rejects_missing_inputs_or_changed_original_receipt_window(self):
        input_ref = self.prepare()
        bundle, joint = self.generate(input_ref)
        forecast = self.store.issue_prospective(bundle, reference=joint, input_ref=input_ref)
        original_input = self.path(input_ref).read_bytes()
        self.path(input_ref).unlink()
        with self.assertRaises((FileNotFoundError, IntegrityError)):
            Ledger(self.root).scan()
        self.path(input_ref).write_bytes(original_input)
        payload = self.store.read(forecast)
        payload["received_at"] = stamp(self.cutoff+timedelta(minutes=5, microseconds=1))
        self.path(forecast).unlink()
        write_receipt(self.path(forecast), payload)
        with patch("multisport_lab.ledger._now", return_value=self.cutoff+timedelta(minutes=6)):
            with self.assertRaisesRegex(IntegrityError, "issuance window"):
                Ledger(self.root).scan()

    def test_legacy_r0_api_does_not_accept_the_new_pregame_lane(self):
        input_ref = self.prepare()
        bundle, joint = self.generate(input_ref)
        with self.assertRaisesRegex(IntegrityError, "does not support REAL_TIME_CAPTURED"):
            self.store.issue_forecast(bundle, reference=joint)
        self.assertEqual(self.store.scan()["forecasts"], {})

    def test_later_verified_synthetic_outcome_grades_r1_without_financial_settlement(self):
        input_ref = self.prepare()
        bundle, joint = self.generate(input_ref)
        forecast = self.store.issue_prospective(bundle, reference=joint, input_ref=input_ref)
        self.assertEqual(list(self.store.iter_grades()), [])
        event_start = self.cutoff+timedelta(minutes=90)
        observation = event_start+timedelta(hours=3)
        with patch("multisport_lab.ledger._now", return_value=observation):
            outcome = self.store.record_outcome(
                outcome_row(event_id=self.pack["event"]["event_id"], player_id="10", season_ending_year=2027,
                            event_start=event_start),
                source_evidence_sha256="c"*64, source_observed_at=observation)
            grade_ref = self.store.grade_forecast(forecast, outcome)
            restarted = Ledger(self.root)
            grade = restarted.read(grade_ref)["data"]["grade"]
            self.assertEqual(len(list(restarted.iter_active_grades())), 1)
        self.assertEqual(grade["evidence_lane"], "REAL_TIME_CAPTURED")
        self.assertEqual(grade["status"], "SCORED")
        self.assertEqual(len(grade["categories"]), 14)
        self.assertEqual(grade["financial_settlement"], "NOT_EVALUATED")
        self.assertEqual(self.store.read(forecast)["data"]["bundle"], bundle)


if __name__ == "__main__":
    unittest.main()

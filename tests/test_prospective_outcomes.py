"""Synthetic post-event fixtures only; no actual NBA future outcomes or HTTP."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from multisport_lab.baseline import ForecastTarget, HistoricalAppearance, forecast_reference
from multisport_lab.forecast_contract import from_reference
from multisport_lab.integrity import IntegrityError, digest, stamp, write_receipt, read_receipt
from multisport_lab.ledger import Ledger
from multisport_lab.prospective_outcomes import (
    normalize_summary, persist_grades, verify_report, capture_summary, main,
    issued_context,
)

START = datetime(2026, 2, 1, 20, tzinfo=timezone.utc)
OBSERVED = datetime(2026, 10, 19, 23, tzinfo=timezone.utc)
NOW = OBSERVED + timedelta(seconds=30)
LABELS = ["MIN", "FG", "3PT", "FT", "OREB", "DREB", "REB", "AST", "STL", "BLK", "TO", "PTS"]


def event():
    body = {"id_namespace": "espn", "league": "NBA", "event_id": "200", "event_starts_at": stamp(START),
            "home_team_id": "1", "away_team_id": "2", "status": "PRE_GAME", "season_ending_year": 2026, "season_type": "2"}
    return {**body, "event_version": digest(body)}


def candidates():
    return [{"player_id": "10", "team_id": "1", "opponent_id": "2", "player_label": "Fictional A"},
            {"player_id": "20", "team_id": "2", "opponent_id": "1", "player_label": "Fictional B"}]


def source(*, final=True, include_second=True):
    state = {"name": "STATUS_FINAL", "state": "post", "completed": True} if final else {
        "name": "STATUS_IN_PROGRESS", "state": "in", "completed": False}
    competition = {"id": "200", "date": stamp(START), "status": {"period": 5, "type": state},
                   "competitors": [{"id": t, "homeAway": side, "team": {"id": t}, "score": "100",
                                    "linescores": [{"displayValue": "20"} for _ in range(5)]}
                                   for t, side in (("1", "home"), ("2", "away"))]}
    groups = [{"team": {"id": "1"}, "statistics": [{"labels": list(LABELS),
               "athletes": [{"athlete": {"id": "10"}, "didNotPlay": False,
                             "stats": ["20:00", "1-2", "0-0", "0-0", "0", "0", "0", "0", "0", "0", "0", "2"]}]}]}]
    if include_second:
        groups.append({"team": {"id": "2"}, "statistics": [{"labels": list(LABELS),
                       "athletes": [{"athlete": {"id": "20"}, "didNotPlay": True, "stats": []}]}]})
    return {"header": {"id": "200", "date": stamp(START), "season": {"year": 2026, "type": 2},
                       "competitions": [competition]}, "boxscore": {"players": groups}}


def raw(body):
    return json.dumps(body).encode()


def normalized(body=None, observed=OBSERVED):
    with patch("multisport_lab.prospective_outcomes._now", return_value=NOW):
        return normalize_summary(raw(source() if body is None else body), event(), candidates(), observed_at=observed)


def fixture_forecast(store, player):
    earlier = START-timedelta(days=31)
    history = [HistoricalAppearance(str(100+i), str(30+i), "1", "2", earlier,
                earlier+timedelta(hours=4), 20, fgm, 0, 0, reb, ast, 0, 0, 0)
               for i, fgm, reb, ast in [(0, 1, 0, 0), (1, 5, 10, 10)]]
    team, opponent = ("1", "2") if player == "10" else ("2", "1")
    target = ForecastTarget("200", player, START)
    observed = HistoricalAppearance("200", player, team, opponent, START, START+timedelta(hours=4),
                                    20, 1, 0, 0, 0, 0, 0, 0, 0)
    with patch("multisport_lab.baseline._now", return_value=OBSERVED-timedelta(minutes=1)):
        reference = forecast_reference(history, target)
    bundle = from_reference(reference, observed, model_commit="f"*40)
    return store.issue_forecast(bundle, reference=reference)


class SummaryNormalizationTests(unittest.TestCase):
    def test_explicit_labels_full_period_and_dnp_keep_missing_separate(self):
        body = source()
        group = body["boxscore"]["players"][0]["statistics"][0]
        group["labels"] = list(reversed(group["labels"]))
        group["athletes"][0]["stats"] = list(reversed(group["athletes"][0]["stats"]))
        report = normalized(body)
        self.assertEqual(report["status"], "FINAL_COMPLETE_SELECTED_COHORT")
        row = report["rows"]["10"]
        self.assertEqual((row.points, row.fgm, row.fg2m, row.fg3m), (2, 1, 1, 0))
        self.assertEqual((row.final_periods, row.game_duration_minutes, row.minutes_precision), (5, 53, "seconds"))
        self.assertEqual(report["rows"]["20"].participation, "DNP")
        self.assertIsNone(report["rows"]["20"].points)
        partial = normalized(source(include_second=False))
        self.assertEqual(partial["status"], "FINAL_PARTIAL_SELECTED_COHORT")
        self.assertEqual(partial["pending"], [{"player_id": "20", "reason": "SELECTED_ATHLETE_MISSING_FROM_FINAL_BOXSCORE"}])
        body = source()
        del body["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["didNotPlay"]
        self.assertIn({"player_id": "10", "reason": "PARTICIPATION_NOT_EXPLICIT"}, normalized(body)["pending"])

    def test_nonfinal_never_returns_statistical_outcomes_or_guesses_zeros(self):
        report = normalized(source(final=False))
        self.assertEqual(report["rows"], {})
        self.assertEqual(report["status"], "PENDING")
        self.assertTrue(all(x["reason"] == "EVENT_NOT_VERIFIED_FINAL" for x in report["pending"]))

    def test_actual_summary_shape_can_prove_period_count_with_two_complete_score_arrays(self):
        body = source()
        del body["header"]["competitions"][0]["status"]["period"]
        body["format"] = {"regulation": {"periods": 4, "clock": 720.0}, "overtime": {"clock": 300.0}}
        for side in body["header"]["competitions"][0]["competitors"]:
            side["linescores"] = [{"displayValue": "20"} for _ in range(5)]
            side["score"] = "100"
        parsed = normalized(body)
        self.assertEqual(parsed["rows"]["10"].final_periods, 5)
        self.assertEqual(parsed["rows"]["10"].game_duration_minutes, 53)
        self.assertEqual(parsed["final_period_count_basis"], "MATCHING_FINAL_TEAM_QUARTER_ARRAYS_WITH_EXPLICIT_NBA_FORMAT")
        bad = deepcopy(body);bad["header"]["competitions"][0]["competitors"][0]["linescores"].pop()
        bad["header"]["competitions"][0]["competitors"][0]["score"] = "80"
        with self.assertRaisesRegex(IntegrityError, "counts conflict"):
            normalized(bad)
        bad = deepcopy(body);del bad["format"]
        with self.assertRaisesRegex(IntegrityError, "period format"):
            normalized(bad)
        bad = deepcopy(body);bad["header"]["competitions"][0]["competitors"][0]["linescores"][0] = {}
        with self.assertRaisesRegex(IntegrityError, "period score"):
            normalized(bad)
        bad = deepcopy(body);bad["header"]["competitions"][0]["competitors"][0]["score"] = "101"
        with self.assertRaisesRegex(IntegrityError, "sum to"):
            normalized(bad)
        bad = deepcopy(body);bad["header"]["competitions"][0]["competitors"][0]["linescores"][0]["period"] = 2
        with self.assertRaisesRegex(IntegrityError, "ordinals"):
            normalized(bad)
        for section, value in [("regulation", None), ("overtime", []),
                               ("regulation", {"periods": 4.0, "clock": 720}),
                               ("regulation", {"periods": 4, "clock": 600}),
                               ("overtime", {"clock": True})]:
            bad = deepcopy(body);bad["format"][section] = value
            with self.subTest(section=section, value=value), self.assertRaisesRegex(IntegrityError, "period format"):
                normalized(bad)
        for value in [21, True, "20", -1]:
            bad = deepcopy(body);bad["header"]["competitions"][0]["competitors"][0]["linescores"][0]["value"] = value
            with self.subTest(value=value), self.assertRaisesRegex(IntegrityError, "numeric period score"):
                normalized(bad)

    def test_identity_start_team_season_and_version_conflicts_fail_closed(self):
        for mutate in [
            lambda b: b["header"].update(id="201"),
            lambda b: b["header"]["competitions"][0].update(id="201"),
            lambda b: b["header"]["competitions"][0].update(date=stamp(START+timedelta(minutes=1))),
            lambda b: b["header"]["season"].update(year=2027),
            lambda b: b["header"]["competitions"][0]["competitors"][0]["team"].update(id="3"),
            lambda b: b["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["athlete"].update(team={"id": "2"}),
        ]:
            body = source(); mutate(body)
            with self.subTest(mutate=mutate), self.assertRaises((IntegrityError, ValueError)):
                normalized(body)
        expected = event(); expected["event_version"] = "0"*64
        with patch("multisport_lab.prospective_outcomes._now", return_value=NOW), self.assertRaisesRegex(IntegrityError, "version"):
            normalize_summary(raw(source()), expected, candidates(), observed_at=OBSERVED)

    def test_incomplete_contradictory_or_period_specific_lines_are_rejected(self):
        for mutate in [
            lambda g: g["labels"].remove("AST"),
            lambda g: g["labels"].append("PTS"),
            lambda g: g.update(period=1),
            lambda g: g.update(displayName="First Quarter"),
            lambda g: g["athletes"][0]["stats"].__setitem__(1, "0-2"),
            lambda g: g["athletes"][0]["stats"].__setitem__(4, "1"),
            lambda g: g["athletes"][0]["stats"].__setitem__(0, "0:00"),
            lambda g: g["athletes"][0].update(didNotPlay=True),
            lambda g: g["athletes"].append(deepcopy(g["athletes"][0])),
        ]:
            body = source();mutate(body["boxscore"]["players"][0]["statistics"][0])
            with self.subTest(mutate=mutate), self.assertRaises((IntegrityError, ValueError)):
                normalized(body)
        body = source();body["header"]["competitions"][0]["status"]["period"] = 6
        with self.assertRaisesRegex(IntegrityError, "period"):
            normalized(body)

    def test_source_clocks_and_duplicate_json_keys_do_not_become_authenticity(self):
        with patch("multisport_lab.prospective_outcomes._now", return_value=NOW):
            for observed in (NOW+timedelta(seconds=1), START-timedelta(seconds=1)):
                with self.assertRaisesRegex(IntegrityError, "observation"):
                    normalize_summary(raw(source()), event(), candidates(), observed_at=observed)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                normalize_summary(b'{"header":{},"header":{}}', event(), candidates(), observed_at=OBSERVED)
        report = normalized()
        self.assertEqual(report["source_observed_at"], stamp(OBSERVED))
        self.assertEqual(report["normalized_at"], stamp(NOW))
        self.assertIsNone(report["source_updated_at"])

    def test_capture_and_cli_never_request_future_or_unissued_outcomes(self):
        future = event();future["event_starts_at"] = stamp(NOW+timedelta(hours=1))
        with patch("multisport_lab.prospective_outcomes._now", return_value=NOW), patch(
                "multisport_lab.prospective_outcomes.urllib.request.urlopen") as network:
            with self.assertRaisesRegex(IntegrityError, "before event start"):
                capture_summary(future, Path("unused-synthetic-path"))
            network.assert_not_called()
        view = {"event": future}
        for forecasts, reason in [({}, "NO_ISSUED_FORECASTS"), ({"10": ["fictional-ref"]}, "EVENT_NOT_STARTED")]:
            output = StringIO()
            with patch("multisport_lab.prospective_outcomes._now", return_value=NOW), patch(
                    "multisport_lab.prospective_outcomes.issued_context", return_value=(view, forecasts)), patch(
                    "multisport_lab.prospective_outcomes.capture_summary") as capture, patch(
                    "sys.argv", ["prospective_outcomes", "--event", "200", "--input-record-id", "f"*64]), redirect_stdout(output):
                main()
            capture.assert_not_called()
            result = json.loads(output.getvalue())
            self.assertEqual((result["status"], result["reason"], result["source_requests"]), ("PENDING", reason, 0))

    def test_mocked_poststart_capture_owns_clocks_and_retains_exact_bytes_without_using_http_date(self):
        response = MagicMock()
        response.status = 200
        response.headers = {"Content-Type": "application/json", "Date": "Fictional remote response date"}
        response.read.return_value = raw(source())
        response.__enter__.return_value = response
        with tempfile.TemporaryDirectory() as directory, patch(
                "multisport_lab.prospective_outcomes._now", side_effect=[NOW, NOW+timedelta(seconds=1), NOW+timedelta(seconds=2)]), patch(
                "multisport_lab.prospective_outcomes.urllib.request.urlopen", return_value=response) as network:
            body, metadata = capture_summary(event(), Path(directory))
            self.assertEqual(body, raw(source()))
            self.assertEqual(network.call_count, 1)
            self.assertEqual(network.call_args.kwargs, {"timeout": 20})
            self.assertEqual(metadata["observed_at"], stamp(NOW+timedelta(seconds=2)))
            self.assertEqual(metadata["retrieval_started_at"], stamp(NOW+timedelta(seconds=1)))
            self.assertEqual(metadata["http_date"], "Fictional remote response date")
            self.assertIsNone(metadata["source_updated_at"])
            self.assertEqual((Path(directory)/f"{metadata['raw_sha256']}.raw").read_bytes(), body)
            self.assertEqual(read_receipt(next(Path(directory).glob("capture-*.json"))), metadata)

    def test_raw_public_paths_and_symlink_parents_fail_before_any_source_request(self):
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/"real").mkdir()
            (root/"linked-parent").symlink_to(root/"real", target_is_directory=True)
            paths = [repository/"web"/"private-outcome-raw", repository/"output"/"private-outcome-raw",
                     repository/"evidence"/"private-outcome-raw", root/"linked-parent"/"new-child"]
            with patch("multisport_lab.prospective_outcomes._now", return_value=NOW), patch(
                    "multisport_lab.prospective_outcomes.urllib.request.urlopen") as network:
                for path in paths:
                    with self.subTest(path=path), self.assertRaisesRegex(IntegrityError, "path"):
                        capture_summary(event(), path)
                network.assert_not_called()
            self.assertFalse((root/"real"/"new-child").exists())

    def test_socket_timeout_does_not_substitute_for_actual_capture_latency_budget(self):
        response = MagicMock()
        response.status = 200;response.headers = {"Content-Type": "application/json"}
        response.read.return_value = raw(source());response.__enter__.return_value = response
        with tempfile.TemporaryDirectory() as directory, patch(
                "multisport_lab.prospective_outcomes._now", return_value=NOW), patch(
                "multisport_lab.prospective_outcomes.monotonic", side_effect=[0, 31]), patch(
                "multisport_lab.prospective_outcomes.urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(IntegrityError, "30-second latency"):
                capture_summary(event(), Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_issued_context_excludes_other_input_records_and_historical_lanes(self):
        input_id = "f"*64
        input_body = {"data": {"source_pack": {"event": event(), "fictional": "input fixture"}}}
        def forecast_payload(lane, pack_id, logical):
            bundle = {"forecast_id": logical, "evidence_lane": lane, "player_id": "10",
                      "model_version": "nba_joint_empirical_pregame_r1_v1",
                      "prospective": {"source_pack_record_id": pack_id, "event_version": event()["event_version"]}}
            return {"kind": "forecasts", "record_id": digest(logical), "data": {"bundle": bundle}}
        payloads = [forecast_payload("REAL_TIME_CAPTURED", input_id, "selected"),
                    forecast_payload("REAL_TIME_CAPTURED", "e"*64, "other-input"),
                    forecast_payload("RECONSTRUCTED_RESEARCH", input_id, "historical")]
        fake = MagicMock()
        fake.scan.return_value = {"research_inputs": {input_id: input_body},
                                 "forecasts": {x["record_id"]: x for x in payloads}}
        fake.iter_active_forecasts.return_value = [x["data"]["bundle"] for x in payloads]
        # Match the actual producer's intentionally small binding_view event.
        partial_event = {k: event()[k] for k in ("event_id", "event_version", "event_starts_at", "home_team_id", "away_team_id")}
        with patch("multisport_lab.pregame_sources.binding_view", return_value={"event": partial_event}):
            view, forecasts = issued_context(fake, input_id, "200")
            self.assertEqual(len(forecasts["10"]), 1)
            self.assertEqual(forecasts["10"][0].record_id, payloads[0]["record_id"])
            self.assertEqual(view["event"], event())
            # Exercise the real context -> normalizer handoff; the small view
            # alone cannot establish the original season/namespace/status.
            with patch("multisport_lab.prospective_outcomes._now", return_value=NOW):
                parsed = normalize_summary(raw(source()), view["event"], candidates(), observed_at=OBSERVED)
            self.assertEqual(parsed["status"], "FINAL_COMPLETE_SELECTED_COHORT")
            with self.assertRaisesRegex(IntegrityError, "requested event differs"):
                issued_context(fake, input_id, "201")


class DurableGradingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = Ledger(self.root)
        self.clock = patch("multisport_lab.ledger._now", return_value=NOW)
        self.clock.start()
        self.module_clock = patch("multisport_lab.prospective_outcomes._now", return_value=NOW)
        self.module_clock.start()
        self.forecast_clock = patch("multisport_lab.forecast_contract.datetime")
        self.forecast_clock.start().now.return_value = NOW
        self.forecasts = {p: [fixture_forecast(self.store, p)] for p in ["10", "20"]}

    def tearDown(self):
        self.forecast_clock.stop();self.module_clock.stop();self.clock.stop();self.temporary.cleanup()

    def bytes(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*.json")}

    def test_restart_readback_and_fresh_identical_stats_reuse_original_source_and_grade_clocks(self):
        first = persist_grades(self.store, self.forecasts, normalized())
        before = self.bytes()
        body = source();body["news"] = "Fictional changed unrelated metadata"
        fresh = normalized(body, OBSERVED+timedelta(seconds=10))
        second = persist_grades(Ledger(self.root), self.forecasts, fresh)
        self.assertEqual(before, self.bytes())
        self.assertNotEqual(first["fresh_capture"]["source_raw_sha256"], second["fresh_capture"]["source_raw_sha256"])
        self.assertTrue(all(x["reused_original_outcome"] for x in second["results"]))
        for original, reused in zip(first["results"], second["results"]):
            self.assertEqual(original["outcome_reference"], reused["outcome_reference"])
            self.assertEqual(original["source_observed_at"], reused["source_observed_at"])
            self.assertEqual(original["grades"], reused["grades"])
        self.assertEqual(len(list(self.store.iter_active_grades())), 2)
        self.assertEqual(first["financial_settlement"], "NOT_EVALUATED")
        grades = list(self.store.iter_active_grades())
        self.assertEqual({x["status"] for x in grades}, {"SCORED", "DNP_NOT_SCORED"})
        self.assertEqual(len(next(x for x in grades if x["status"] == "SCORED")["categories"]), 14)

    def test_interruption_before_report_recovery_preserves_retained_and_new_outcome_clocks(self):
        persist_grades(self.store, self.forecasts, normalized(source(include_second=False)))
        original = self.bytes()
        # No summary was saved before a simulated restart. A later complete source
        # supplies the second explicit DNP while the first outcome is retained.
        recovered = persist_grades(Ledger(self.root), self.forecasts, normalized(observed=OBSERVED+timedelta(seconds=10)))
        clocks = {x["player_id"]: x["source_observed_at"] for x in recovered["results"]}
        self.assertEqual(clocks, {"10": stamp(OBSERVED), "20": stamp(OBSERVED+timedelta(seconds=10))})
        for path, content in original.items():
            self.assertEqual(content, (self.root/path).read_bytes())
        path = self.root/"recovered-report.json";write_receipt(path, recovered)
        verify_report(Ledger(self.root), read_receipt(path))
        bad = deepcopy(recovered);bad["results"][0]["source_observed_at"] = stamp(OBSERVED+timedelta(seconds=10))
        with self.assertRaisesRegex(IntegrityError, "original outcome source clocks"):
            verify_report(self.store, bad)

    def test_changed_outcome_requires_explicit_traceable_corrections(self):
        persist_grades(self.store, self.forecasts, normalized())
        originals = self.bytes()
        body = source();line = body["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["stats"]
        line[1], line[-1] = "2-3", "4"
        changed = normalized(body, OBSERVED+timedelta(seconds=10))
        with self.assertRaisesRegex(IntegrityError, "explicit correction"):
            persist_grades(self.store, self.forecasts, changed)
        self.assertEqual(originals, self.bytes())
        report = persist_grades(self.store, self.forecasts, changed, correction_reason="Fictional verified score correction")
        self.assertEqual(len(self.store.scan()["outcomes"]), 3)
        self.assertEqual(len(self.store.scan()["grades"]), 3)
        self.assertEqual(len(self.store.scan()["corrections"]), 2)
        self.assertEqual(len(list(self.store.iter_active_grades())), 2)
        for path, content in originals.items():
            self.assertEqual(content, (self.root/path).read_bytes())
        verify_report(Ledger(self.root), report)
        before = self.bytes()
        persist_grades(Ledger(self.root), self.forecasts, changed, correction_reason="Fictional verified score correction")
        self.assertEqual(before, self.bytes())

    def test_interrupted_outcome_correction_recovers_orphan_replacement_and_regrades(self):
        persist_grades(self.store, self.forecasts, normalized())
        body = source();line = body["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["stats"]
        line[1], line[-1] = "2-3", "4"
        changed = normalized(body, OBSERVED+timedelta(seconds=10))
        # The replacement outcome was written, but no correction link/summary yet.
        with patch.object(self.store, "correct", side_effect=RuntimeError("synthetic interruption")):
            with self.assertRaisesRegex(RuntimeError, "interruption"):
                persist_grades(self.store, self.forecasts, changed, correction_reason="Fictional correction")
        self.assertEqual(len(self.store.scan()["outcomes"]), 3)
        self.assertEqual(len(self.store.scan()["corrections"]), 0)
        recovered = persist_grades(Ledger(self.root), self.forecasts, changed, correction_reason="Fictional correction")
        self.assertEqual(len(self.store.scan()["outcomes"]), 3)
        self.assertEqual(len(self.store.scan()["grades"]), 3)
        self.assertEqual(len(self.store.scan()["corrections"]), 2)
        self.assertEqual(len(list(self.store.iter_active_grades())), 2)
        verify_report(Ledger(self.root), recovered)

    def test_report_event_or_grade_clock_cannot_drift_from_referenced_records(self):
        report = persist_grades(self.store, self.forecasts, normalized())
        for mutate in [lambda r: r.update(event_id="201"),
                       lambda r: r["results"][0]["grades"][0].update(graded_at=stamp(NOW+timedelta(seconds=1))),
                       lambda r: r["selected_normalized_rows"][0].update(team_id="2", opponent_id="1")]:
            bad = deepcopy(report);mutate(bad)
            with self.assertRaises(IntegrityError):
                verify_report(self.store, bad)


if __name__ == "__main__":
    unittest.main()

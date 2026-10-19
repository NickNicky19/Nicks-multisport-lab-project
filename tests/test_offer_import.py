"""Synthetic software fixtures follow observed shapes; no copied public offer data."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from multisport_lab.integrity import IntegrityError, load_json, read_receipt, write_receipt
from multisport_lab.offer_import import import_capture, REQUIRED_MARKETS

OBSERVED = "2026-10-19T12:00:00.123456Z"
IMPORTED = datetime(2026, 10, 19, 12, 1, tzinfo=timezone.utc)


def capture(rows=None, **changes):
    return {
        "schema_version": "nba-offer-capture-v1", "source": "synthetic-local-file",
        "source_url": "file:synthetic-fixture.json", "observed_at": OBSERVED,
        "evidence_lane": "SYNTHETIC_TEST", "http_status": 200,
        "content_type": "application/json", "format": "normalized_v1",
        "authorization": {"scope": "local_research", "public_redistribution": False,
                          "basis": "Original fictional software fixture authored for this test"},
        "pagination": {"complete": True, "pages_observed": 1},
        "data": rows if rows is not None else [normalized()],
    } | changes


def normalized():
    return {
        "provider_event_id": "fictional-event", "provider_player_id": "fictional-player",
        "provider_market_id": "fictional-market", "provider_selection_id": "fictional-selection",
        "semantic_evidence_reference": "synthetic terms; not a real provider rule",
        "contract": {
            "sport": "basketball", "league": "NBA", "event_id": "fictional-event",
            "player_id": "fictional-player", "stat": "PTS", "units": "points",
            "period": "full_game", "extra_time_policy": "includes_overtime", "line": "22.5",
            "side": "over", "variant": "standard", "venue": "fictional-book",
            "product": "sportsbook", "settlement_version": "fictional-rules-v1",
        },
        "event_starts_at": "2026-10-19T16:00:00Z", "source_updated_at": None,
        "status": "pre_game", "price": {"value": "1.91", "kind": "sportsbook_decimal"},
    }


def sleeper():
    common = {
        "sport": "nba", "game_id": "fictional-sleeper-event", "subject_id": "fictional-subject",
        "market_type": "points_over_under_player_fictional", "wager_type": "points",
        "outcome_type": "over_under", "line_type": "normal", "season": "2026",
        "season_type": "regular", "game_status": "pre_game",
    }
    return {**common, "status": "active", "updated_at": 1792400000000,
            "options": [{**common, "status": "active", "line_id": f"fictional-{side}",
                         "outcome": side, "outcome_value": 22.5, "metadata": {},
                         "payout_multiplier": multiplier}
                        for side, multiplier in (("over", "1.7"), ("under", "1.9"))]}


class OfferImportTests(unittest.TestCase):
    def test_explicit_complete_capture_preserves_exact_identity_and_same_evidence(self):
        row = normalized()
        row["contract"]["line"] = "22.500000000000000000000001"
        report = import_capture(capture([row]), imported_at=IMPORTED)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(set(report["coverage"]), set(REQUIRED_MARKETS))
        observation = report["observations"][0]
        self.assertEqual(observation["line"], "22.500000000000000000000001")
        self.assertEqual(observation["quote"]["line_evidence_id"],
                         observation["quote"]["price_evidence_id"])
        self.assertEqual(observation["quote"]["observed_at"], OBSERVED)
        self.assertFalse(observation["qualified"])
        self.assertFalse(report["capture_assertions_independently_verified"])

    def test_line_only_capture_never_invents_price_or_quote(self):
        row = normalized()
        row["price"] = None
        report = import_capture(capture([row]), imported_at=IMPORTED)
        observation = report["observations"][0]
        self.assertIsNotNone(observation["contract"])
        self.assertIsNone(observation["quote"])
        self.assertIsNone(observation["price"])
        self.assertIn("price_missing", observation["unavailable_reasons"])

    def test_transport_parser_empty_and_incomplete_states_remain_distinct(self):
        cases = [
            (capture([]), "empty"),
            (capture([], http_status=403), "blocked_access"),
            (capture([], http_status=404), "upstream_error"),
            (capture([], content_type="text/html"), "parser_failure"),
            (capture("<!doctype html>"), "parser_failure"),
            (capture([], pagination={"complete": False, "pages_observed": 1}), "partial"),
        ]
        for document, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(import_capture(document, imported_at=IMPORTED)["status"], expected)

    def test_missing_rights_capture_clocks_and_decimal_text_fail_closed(self):
        bad = [capture(observed_at="2026-10-19T13:00:00Z"),
               capture(observed_at="2026-10-19T12:00:00"),
               capture(authorization={"scope": "public", "basis": "accessible URL"}),
               capture(pagination={"complete": True, "pages_observed": True})]
        for document in bad:
            with self.subTest(document=document), self.assertRaises(ValueError):
                import_capture(document, imported_at=IMPORTED)
        for field in ("line", "price"):
            row = normalized()
            if field == "line":
                row["contract"]["line"] = 22.5
            else:
                row["price"]["value"] = 1.91
            self.assertEqual(import_capture(capture([row]), imported_at=IMPORTED)["status"],
                             "parser_failure")

    def test_sleeper_shape_keeps_multiplier_and_unknown_terms_without_kernel_quote(self):
        document = capture([sleeper()], source="sleeper", format="sleeper_lines_v1")
        report = import_capture(document, imported_at=IMPORTED)
        self.assertEqual(report["coverage"]["PTS"], 2)
        self.assertEqual(len(report["observations"]), 2)
        observation = report["observations"][0]
        self.assertEqual(observation["price"]["kind"], "pickem_multiplier")
        self.assertIsNone(observation["contract"])
        self.assertIsNone(observation["quote"])
        self.assertIsNone(observation["period"])
        self.assertIsNone(observation["extra_time_policy"])
        self.assertIn("entry_terms_unverified", observation["unavailable_reasons"])
        self.assertEqual(observation["provider_selection_id"], "fictional-over")

    def test_unmapped_labels_are_retained_and_identity_splicing_is_rejected(self):
        row = sleeper()
        row["wager_type"] = "unknown_statistic"
        for option in row["options"]:
            option["wager_type"] = row["wager_type"]
        report = import_capture(capture([row], source="sleeper", format="sleeper_lines_v1"),
                                imported_at=IMPORTED)
        self.assertEqual(report["status"], "unmapped")
        self.assertIsNone(report["observations"][0]["stat"])
        self.assertEqual(report["observations"][0]["raw_stat_label"], "unknown_statistic")
        row = sleeper()
        row["options"][0]["game_id"] = "another-event"
        report = import_capture(capture([row], source="sleeper", format="sleeper_lines_v1"),
                                imported_at=IMPORTED)
        self.assertEqual(report["status"], "parser_failure")
        self.assertIn("identity mismatch", report["diagnostics"][0]["reason"])
        report = import_capture(capture([{"error": "upstream envelope changed"}],
                                        source="sleeper", format="sleeper_lines_v1"),
                                imported_at=IMPORTED)
        self.assertEqual(report["status"], "parser_failure")

    def test_duplicates_source_future_and_incompatible_units_remain_unavailable(self):
        row = normalized()
        report = import_capture(capture([row, deepcopy(row)]), imported_at=IMPORTED)
        self.assertEqual(report["status"], "partial")
        self.assertTrue(all(o["quote"] is None for o in report["observations"]))
        for change in ("units", "source_time"):
            row = normalized()
            if change == "units":
                row["contract"]["units"] = "rebounds"
            else:
                row["source_updated_at"] = "2026-10-19T12:00:01Z"
            report = import_capture(capture([row]), imported_at=IMPORTED)
            self.assertEqual(report["status"], "parser_failure")

    def test_offline_file_import_reuses_bounded_strict_json_and_immutable_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "capture.json"
            target = Path(directory) / "report.json"
            source.write_text(json.dumps(capture()), encoding="utf-8")
            report = import_capture(load_json(source), imported_at=IMPORTED)
            self.assertTrue(write_receipt(target, report))
            self.assertEqual(read_receipt(target), report)
            self.assertFalse(write_receipt(target, report))
            source.write_text('{"schema_version":"v1","schema_version":"v2"}', encoding="utf-8")
            with self.assertRaises(IntegrityError):
                load_json(source)


if __name__ == "__main__":
    unittest.main()

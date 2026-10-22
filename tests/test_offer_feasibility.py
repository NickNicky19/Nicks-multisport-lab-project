"""Fictional source shapes only; tests never establish an actual player offer."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import unittest

from multisport_lab.integrity import IntegrityError, canonical
from multisport_lab.offer_feasibility import ALL_CATEGORIES, ROOT, inspect_espn_original

NOW = datetime(2026, 10, 21, 13, tzinfo=timezone.utc)
URL = "https://sports.core.api.espn.com" + ROOT


def ref(path):
    return {"$ref": URL + path}


def row(label="Total Points", athlete=True):
    value = {"competition": ref("events/123/competitions/123"),
             "provider": ref("casinos/100"), "type": {"id": "1", "name": label},
             "current": {"target": {"value": "22.500000000000000001"}},
             "odds": {"total": {"value": "22.500000000000000001"},
                      "american": {"value": "-110"}, "decimal": {"value": "1.91"},
                      "fraction": {"value": "10/11"}},
             "lastUpdated": "2026-10-21T10:59:00Z"}
    value["athlete" if athlete else "team"] = ref("athletes/1234" if athlete else "teams/7")
    return value


def original(data=None, path="events/123/competitions/123/odds/100/propBets"):
    if data is None:
        data = {"count": 1, "pageIndex": 1, "pageSize": 64, "pageCount": 1, "items": [row()]}
    body = canonical(data)
    return body, {"url": URL + path, "final_url": URL + path,
                  "request_started_at": "2026-10-21T10:59:59.900000Z",
                  "observed_at": "2026-10-21T11:00:00.123456Z", "http_status": 200,
                  "content_type": "application/json", "raw_bytes": len(body),
                  "raw_sha256": hashlib.sha256(body).hexdigest()}


class OfferFeasibilityTests(unittest.TestCase):
    def inspect(self, rows=None, **kw):
        data = {"count": len(rows or [row()]), "pageIndex": 1, "pageSize": 64,
                "pageCount": 1, "items": rows or [row()]}
        return inspect_espn_original(*original(data), imported_at=NOW, **kw)

    def test_source_id_not_assumed_draftkings_and_no_inferred_side_or_player_name(self):
        result = self.inspect()
        observation = result["observations"][0]
        self.assertEqual(result["attribution"]["data_source"], "ESPN")
        self.assertIsNone(result["attribution"]["provider_name"])
        self.assertEqual((observation["league"], observation["player_id_namespace"],
                          observation["player_id"], observation["event_id"]),
                         ("NBA", "espn", "1234", "123"))
        self.assertEqual(observation["threshold_source_value"], "22.500000000000000001")
        self.assertEqual(observation["prices_as_supplied"]["american"], "-110")
        for field in ("side", "player_name", "contract", "quote", "product", "period", "overtime"):
            self.assertIsNone(observation[field], field)
        self.assertFalse(observation["qualified"])
        self.assertFalse(observation["publication_admitted"])
        self.assertEqual(result["rights_status"], "NOT_ESTABLISHED_BY_PARSER")

    def test_attribution_requires_matching_original_provider_id_and_reference(self):
        lookup = {"id": "100", "name": "Fictional provider", "$ref": URL + "casinos/100"}
        body, metadata = original(lookup, "casinos/100")
        result = self.inspect(provider_body=body, provider_metadata=metadata)
        self.assertEqual(result["attribution"]["provider_name"], "Fictional provider")
        self.assertFalse(result["attribution"]["point_in_time_identity_proven"])
        for change in ({"id": "101"}, {"$ref": URL + "casinos/101"}):
            bad_body, bad_meta = original(lookup | change, "casinos/100")
            with self.assertRaises(IntegrityError):
                self.inspect(provider_body=bad_body, provider_metadata=bad_meta)
        with self.assertRaises(IntegrityError):
            self.inspect(provider_body=body)

    def test_all14_primary_labels_and_unsupported_quarter_are_distinct(self):
        from multisport_lab.offer_feasibility import ESPN_LABELS
        result = self.inspect([row(label) for label in ESPN_LABELS] + [row("Points Milestones - 1st Quarter")])
        self.assertEqual(set(result["category_coverage"]), set(ALL_CATEGORIES))
        self.assertEqual(len(result["category_coverage"]), 14)
        for category in ALL_CATEGORIES:
            self.assertEqual(result["category_coverage"][category]["parsed_partial_observations"], 1)
            self.assertEqual(result["category_coverage"][category]["complete_contracts"], 0)
        quarter = result["observations"][-1]
        self.assertIsNone(quarter["category"])
        self.assertIn("unsupported_market_label_or_variant", quarter["unresolved"])

    def test_nonplayer_snapshot_is_not_player_coverage_or_global_absence(self):
        result = self.inspect([row("Team Total Points", False), row("Will There Be Overtime?", False)])
        self.assertEqual(result["observations"], [])
        self.assertEqual(sum(result["nonplayer_label_counts"].values()), 2)
        self.assertTrue(result["all_pages_present"])
        for coverage in result["category_coverage"].values():
            self.assertEqual(coverage["sample_status"], "UNOBSERVED_IN_SAMPLE")

    def test_missing_prices_are_explicit_without_inventing_odds(self):
        value = row()
        value["odds"] = {"total": {"value": "22.500000000000000001"}}
        observation = self.inspect([value])["observations"][0]
        self.assertEqual(observation["price_status"], "PRICE_UNAVAILABLE")
        self.assertEqual(observation["prices_as_supplied"], {})
        self.assertIsNone(observation["quote"])
        self.assertNotIn("price_missing", observation["unresolved"])

    def test_missing_player_reference_is_unresolved_not_assumed_nonplayer(self):
        value = row()
        del value["athlete"]
        result = self.inspect([value])
        self.assertEqual(result["observations"], [])
        self.assertEqual(result["nonplayer_label_counts"], {})
        self.assertIn("Unresolved subject", result["diagnostics"][0]["reason"])
        value = row("Team Total Points", False)
        value["team"] = {"$ref": URL.replace("nba/", "nfl/") + "teams/7"}
        result = self.inspect([value])
        self.assertEqual(result["nonplayer_label_counts"], {})
        self.assertEqual(len(result["diagnostics"]), 1)

    def test_numeric_json_lexemes_do_not_round_thresholds_or_prices(self):
        body, metadata = original()
        body = body.replace(b'"22.500000000000000001"', b'22.500000000000000001')
        body = body.replace(b'"1.91"', b'1.9100000000000000001')
        metadata.update(raw_bytes=len(body), raw_sha256=hashlib.sha256(body).hexdigest())
        result = inspect_espn_original(body, metadata, imported_at=NOW)
        observation = result["observations"][0]
        self.assertEqual(observation["threshold_source_value"], "22.500000000000000001")
        self.assertEqual(observation["prices_as_supplied"]["decimal"], "1.9100000000000000001")
        self.assertEqual(observation["original_body_sha256"], hashlib.sha256(body).hexdigest())

    def test_observed_invalid_threshold_remains_distinct_from_unobserved_category(self):
        invalid = row()
        invalid["current"]["target"]["value"] = "invalid"
        result = self.inspect([invalid, row()])
        coverage = result["category_coverage"]["PTS"]
        self.assertEqual(coverage["observed_player_rows"], 2)
        self.assertEqual(coverage["parsed_partial_observations"], 1)
        self.assertEqual(coverage["parse_rejected_rows"], 1)
        self.assertEqual(coverage["sample_status"], "OBSERVED_WITH_PARSE_REJECTIONS")
        self.assertEqual(result["category_coverage"]["TD"]["sample_status"], "UNOBSERVED_IN_SAMPLE")

    def test_source_bytes_clocks_route_and_identity_checks_survive_optimized_execution(self):
        body, metadata = original()
        mutations = [metadata | {"raw_sha256": "0" * 64}, metadata | {"raw_bytes": True},
                     metadata | {"http_status": 403},
                     metadata | {"observed_at": "2026-10-22T11:00:00Z"},
                     metadata | {"request_started_at": "2026-10-21T11:01:00Z"},
                     metadata | {"url": metadata["url"].replace("propBets", "propbets")},
                     metadata | {"url": metadata["url"].replace("nba/", "nfl/")},
                     metadata | {"final_url": metadata["final_url"].replace("123/", "456/")}]
        for bad in mutations:
            with self.subTest(bad=bad), self.assertRaises(IntegrityError):
                inspect_espn_original(body, bad, imported_at=NOW)
        for field, value in (("competition", ref("events/456/competitions/456")),
                             ("provider", ref("casinos/101")),
                             ("athlete", {"$ref": URL.replace("nba/", "nfl/") + "athletes/1234"})):
            item = row() | {field: value}
            result = self.inspect([item])
            self.assertEqual(result["observations"], [])
            self.assertEqual(len(result["diagnostics"]), 1)

    def test_future_source_updates_and_conflicting_thresholds_stay_unusable(self):
        value = row()
        value["lastUpdated"] = "2026-10-21T12:00:00Z"
        value["odds"]["total"]["value"] = "23.5"
        result = self.inspect([value, deepcopy(value)])
        self.assertEqual(len(result["observations"]), 2)  # no row-order side assignment
        for observation in result["observations"]:
            self.assertIsNone(observation["threshold_source_value"])
            self.assertIsNone(observation["side"])
            self.assertIn("contradictory_threshold_fields", observation["unresolved"])
            self.assertIn("source_update_later_than_observation", observation["unresolved"])
        self.assertEqual(result["usable_quotes"], 0)

    def test_incomplete_pages_malformed_json_and_bad_pagination_do_not_become_empty(self):
        data = {"count": 2, "pageIndex": 1, "pageSize": 1, "pageCount": 2, "items": [row()]}
        result = inspect_espn_original(*original(data), imported_at=NOW)
        self.assertFalse(result["all_pages_present"])
        for update in ({"pageCount": True}, {"count": 0}, {"pageIndex": 3}):
            with self.assertRaises(IntegrityError):
                inspect_espn_original(*original(data | update), imported_at=NOW)
        for body in (b'{"items":[],"items":[]}', b'{"value":NaN}', b'{"value":1e999}'):
            _, metadata = original()
            metadata.update(raw_bytes=len(body), raw_sha256=hashlib.sha256(body).hexdigest())
            with self.assertRaises(IntegrityError):
                inspect_espn_original(body, metadata, imported_at=NOW)


if __name__ == "__main__":
    unittest.main()

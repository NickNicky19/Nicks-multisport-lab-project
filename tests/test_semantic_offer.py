"""Fictional source-shaped v2 contracts; no HTTP or actual offer fixture."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from multisport_lab.integrity import IntegrityError, canonical, digest
from multisport_lab.semantic_offer import (SCHEMA, MAX_ORIGINAL_BYTES, binding_fields,
    replay_semantic_offer, seal_semantic_offer, validate_semantic_batch, validate_semantic_offer)

NOW = "2026-10-21T13:00:00.000000Z"
FIXTURE = Path(__file__).parent / "fixtures" / "semantic_offer_v2.json"


def fixture():
    return json.loads(FIXTURE.read_text())


def raw_map(f):
    return {key: canonical(value) for key, value in f["originals"].items()}


def rehash(c):
    c["contract_id"] = digest({key: value for key, value in c.items() if key != "contract_id"})
    return c


def refresh_original(f, key):
    raw = canonical(f["originals"][key])
    evidence = next(item for item in f["contract"]["evidence"] if item["id"] == key)
    evidence["raw_sha256"], evidence["raw_bytes"] = hashlib.sha256(raw).hexdigest(), len(raw)
    f["contract"] = seal_semantic_offer(f["contract"])


def remove_fields(c, fields):
    for name in fields:
        target = c
        pieces = name.split(".")
        for part in pieces[:-1]: target = target[part]
        target[pieces[-1]] = None
    c["bindings"] = [binding for binding in c["bindings"] if binding["field"] not in fields]
    return seal_semantic_offer(c)


def add_clob(f):
    c = f["contract"]
    condition = c["selection"]["condition_id"]
    value = {"c": condition, "gst": c["event"]["starts_at"],
             "t": [{"o": "Yes", "t": "111111"}, {"o": "No", "t": "222222"}]}
    raw = canonical(value)
    f["originals"]["clob"] = value
    c["evidence"].append({"id": "clob", "url": "https://clob.polymarket.com/clob-markets/" + condition,
        "content_type": "application/json", "raw_sha256": hashlib.sha256(raw).hexdigest(), "raw_bytes": len(raw),
        "request_started_at": "2026-10-21T12:02:00.000000Z", "observed_at": "2026-10-21T12:02:00.000001Z", "source_updated_at": None})
    c["selection"]["native_token_id"] = "111111"
    c["bindings"].append({"field": "selection.native_token_id", "evidence_id": "clob", "pointer": "", "transform": "clob_token"})
    c["knowledge_observed_at"] = "2026-10-21T12:02:00.000001Z"
    c["normalized_at"] = "2026-10-21T12:03:00.000000Z"
    f["contract"] = seal_semantic_offer(c)
    return f


class SemanticOfferTests(unittest.TestCase):
    def test_known_source_field_roles_reject_checksum_consistent_aliases_and_transform_bypass(self):
        f = fixture()
        event = f["originals"]["event"]
        event["alias_id"], event["id"] = event["id"], "a-different-source-event"
        c = f["contract"]
        c["event"]["event_version"]["value"] = digest(event)
        next(binding for binding in c["bindings"] if binding["field"] == "event.id")["pointer"] = "/alias_id"
        refresh_original(f, "event")
        with self.assertRaisesRegex(IntegrityError, "source field/pointer/transform"):
            replay_semantic_offer(f["contract"], raw_map(f), now=NOW)
        for field in ("player.source_label", "event.starts_at", "event.participants", "event.source_version_literal",
                      "selection.market_id", "selection.outcome_label", "predicate.category", "predicate.units",
                      "predicate.threshold", "predicate.period", "predicate.extra_time_policy"):
            f = fixture()
            binding = next(binding for binding in f["contract"]["bindings"] if binding["field"] == field)
            binding["pointer"], binding["transform"] = "/invented_alias", "direct"
            f["contract"] = seal_semantic_offer(f["contract"])
            with self.subTest(field=field), self.assertRaisesRegex(IntegrityError, "source field/pointer/transform"):
                validate_semantic_offer(f["contract"], now=NOW)

    def test_event_markets_membership_and_contract_fields_must_match_original_primary(self):
        def linked_fixture(change=None):
            f = fixture()
            f["originals"]["market"].update(line="19.5", gameStartTime="2026-10-21T23:30:00Z", clobTokenIds='["111111","222222"]')
            refresh_original(f, "market")
            f["originals"]["event"]["markets"] = [deepcopy(f["originals"]["market"])]
            if change: change(f["originals"]["event"]["markets"])
            f["contract"]["event"]["event_version"]["value"] = digest(f["originals"]["event"])
            refresh_original(f, "event")
            return f
        valid = linked_fixture()
        replay_semantic_offer(valid["contract"], raw_map(valid), now=NOW)
        for change in (lambda rows: rows.clear(), lambda rows: rows.append(deepcopy(rows[0])),
                       lambda rows: rows[0].update(id="another-market"),
                       lambda rows: rows[0].update(conditionId="0x" + "cd" * 32),
                       lambda rows: rows[0].update(question="Different Player: Points O/U 19.5"),
                       lambda rows: rows[0].update(sportsMarketType="rebounds"),
                       lambda rows: rows[0].update(line="20.5"),
                       lambda rows: rows[0].update(gameStartTime="2026-10-22T23:30:00Z"),
                       lambda rows: rows[0].update(description="Different settlement meaning"),
                       lambda rows: rows[0].update(outcomes='["No","Yes"]'),
                       lambda rows: rows[0].update(clobTokenIds='["333333","444444"]')):
            f = linked_fixture(change)
            with self.subTest(change=change), self.assertRaises(IntegrityError):
                replay_semantic_offer(f["contract"], raw_map(f), now=NOW)

    def test_generic_correct_substring_and_unrelated_rules_are_not_correction_evidence(self):
        for policy in ("The correct generic oracle proposal challenge lasts two hours.",
                       "STATİSTICAL corrections apply to this NBA contract.",
                       "statistical\u0085corrections apply to this NBA contract."):
            f = fixture()
            f["originals"]["market"]["settlement"]["stat_corrections"] = policy
            f["contract"]["settlement"]["stat_corrections"] = policy
            refresh_original(f, "market")
            with self.subTest(policy=policy), self.assertRaisesRegex(IntegrityError, "Generic finality"):
                replay_semantic_offer(f["contract"], raw_map(f), now=NOW)
        f = fixture()
        value = {"description": f["contract"]["settlement"]["stat_corrections"]}
        f["originals"]["unrelated_rules"] = value
        raw = canonical(value)
        f["contract"]["evidence"].append({"id": "unrelated_rules", "url": "https://docs.polymarket.com/concepts/resolution",
            "content_type": "application/json", "raw_sha256": hashlib.sha256(raw).hexdigest(), "raw_bytes": len(raw),
            "request_started_at": "2026-10-21T12:00:15.000000Z", "observed_at": "2026-10-21T12:00:15.000000Z", "source_updated_at": None})
        b = next(b for b in f["contract"]["bindings"] if b["field"] == "settlement.stat_corrections")
        b.update(evidence_id="unrelated_rules", pointer="/description", transform="text_contains")
        f["contract"] = seal_semantic_offer(f["contract"])
        with self.assertRaisesRegex(IntegrityError, "does not bind its original market"):
            replay_semantic_offer(f["contract"], raw_map(f), now=NOW)
        actual = fixture(); actual["contract"]["evidence_lane"] = "ACTUAL_SOURCE_OBSERVATION"
        actual["contract"] = seal_semantic_offer(actual["contract"])
        with self.assertRaisesRegex(IntegrityError, "source field/pointer/transform"):
            validate_semantic_offer(actual["contract"], now=NOW)

    def test_ascii_numeric_wire_types_and_query_free_clob_identity_are_required(self):
        f = fixture(); c = f["contract"]
        f["originals"]["market"]["outcomePrices"] = '["0.٥","0.5"]'
        c["unassigned_source_economics"]["outcome_prices"] = ["0.٥", "0.5"]
        c["bindings"].append({"field": "unassigned_source_economics.outcome_prices", "evidence_id": "market", "pointer": "/outcomePrices", "transform": "json_array"})
        refresh_original(f, "market")
        with self.assertRaisesRegex(IntegrityError, "price array"):
            validate_semantic_offer(f["contract"], now=NOW)
        f = fixture(); f["contract"]["predicate"]["threshold"] = "19.٥"
        f["contract"] = seal_semantic_offer(f["contract"])
        with self.assertRaisesRegex(IntegrityError, "statistic predicate"):
            validate_semantic_offer(f["contract"], now=NOW)
        f = add_clob(fixture()); f["contract"]["selection"]["native_token_id"] = "1٢٣"
        f["originals"]["clob"]["t"][0]["t"] = "1٢٣"; refresh_original(f, "clob")
        with self.assertRaisesRegex(IntegrityError, "token ID"):
            validate_semantic_offer(f["contract"], now=NOW)
        f = add_clob(fixture())
        next(item for item in f["contract"]["evidence"] if item["id"] == "clob")["url"] += "?unreviewed=1"
        f["contract"] = seal_semantic_offer(f["contract"])
        with self.assertRaisesRegex(IntegrityError, "query-free"):
            replay_semantic_offer(f["contract"], raw_map(f), now=NOW)
        f = fixture()
        raw = canonical({"reason": "Fictional documentation."})
        f["contract"]["evidence"].append({"id": "bounded_docs", "url": "https://docs.polymarket.com/concepts/resolution?reference=" + "a" * 2048,
            "content_type": "application/json", "raw_sha256": hashlib.sha256(raw).hexdigest(), "raw_bytes": len(raw),
            "request_started_at": "2026-10-21T12:00:15.000000Z", "observed_at": "2026-10-21T12:00:15.000000Z", "source_updated_at": None})
        f["contract"] = seal_semantic_offer(f["contract"])
        with self.assertRaisesRegex(IntegrityError, "bounded original evidence URL"):
            validate_semantic_offer(f["contract"], now=NOW)

    def test_complete_price_free_external_identity_needs_no_native_player_or_token(self):
        f = fixture(); c = f["contract"]
        self.assertEqual(c["schema_version"], SCHEMA)
        self.assertIsNone(c["player"]["native_provider_id"])
        self.assertIsNone(c["selection"]["native_token_id"])
        self.assertEqual(c["price"], {"status": "PRICE_UNAVAILABLE", "value": None})
        self.assertEqual(c["required_gaps"], [])
        self.assertEqual(validate_semantic_offer(c, now=NOW)["semantic_status"], "COMPLETE_LOCAL")
        result = replay_semantic_offer(c, raw_map(f), now=NOW)
        self.assertEqual(result["bindings_verified"], 26)
        self.assertFalse(result["remote_durable_archive_verified"])
        self.assertFalse(result["ticket_eligibility"])
        self.assertFalse(result["public_admission"])

    def test_missing_affiliation_version_and_correction_are_computed_not_native_id_gaps(self):
        f = fixture(); c = remove_fields(f["contract"], {
            "event.player_team_id", "event.opponent_id", "event.event_version", "settlement.stat_corrections"})
        f["contract"] = c
        self.assertEqual(c["required_gaps"], ["PLAYER_TEAM", "PLAYER_OPPONENT", "EVENT_VERSION", "SETTLEMENT_STAT_CORRECTIONS"])
        self.assertEqual(c["semantic_status"], "INCOMPLETE")
        self.assertIsNone(c["completed_at"])
        replay_semantic_offer(c, raw_map(f), now=NOW)
        for key, value in (("required_gaps", []), ("semantic_status", "COMPLETE_LOCAL"),
                           ("completed_at", c["normalized_at"]), ("public_admission", True), ("ticket_eligibility", True)):
            changed = deepcopy(c); changed[key] = value; rehash(changed)
            with self.subTest(key=key), self.assertRaises(IntegrityError):
                validate_semantic_offer(changed, now=NOW)

    def test_new_token_witness_retains_later_knowledge_clock_and_unavailable_price(self):
        f = add_clob(fixture()); c = f["contract"]
        result = replay_semantic_offer(c, raw_map(f), now=NOW)
        self.assertEqual(result["originals_verified"], 5)
        self.assertEqual(c["contract_observed_at"], "2026-10-21T12:00:00.000000Z")
        self.assertEqual(c["knowledge_observed_at"], "2026-10-21T12:02:00.000001Z")
        self.assertEqual(c["completed_at"], "2026-10-21T12:03:00.000000Z")
        self.assertEqual(c["price_binding_gaps"], ["PRICE_TO_SELECTION_UNVERIFIED"])
        self.assertIsNone(c["price"]["value"])
        for key, value in (("knowledge_observed_at", c["contract_observed_at"]),
                           ("normalized_at", "2026-10-21T12:01:00.000000Z"),
                           ("contract_observed_at", c["knowledge_observed_at"]),
                           ("completed_at", "2026-10-21T12:01:00.000000Z")):
            bad = deepcopy(c); bad[key] = value; rehash(bad)
            with self.subTest(key=key), self.assertRaises(IntegrityError):
                validate_semantic_offer(bad, now=NOW)

    def test_checksum_consistent_clob_wrong_condition_time_and_duplicate_label_rejected(self):
        for change in (lambda value: value.update(c="0x" + "cd" * 32),
                       lambda value: value.update(gst="2026-10-22T23:30:00Z"),
                       lambda value: value["t"][1].update(o="Yes"),
                       lambda value: value["t"][1].update(t="111111")):
            f = add_clob(fixture()); change(f["originals"]["clob"]); refresh_original(f, "clob")
            with self.subTest(change=change), self.assertRaises(IntegrityError):
                replay_semantic_offer(f["contract"], raw_map(f), now=NOW)
        f = add_clob(fixture())
        next(binding for binding in f["contract"]["bindings"] if binding["field"] == "selection.native_token_id")["pointer"] = "/t"
        f["contract"] = seal_semantic_offer(f["contract"])
        with self.assertRaises(IntegrityError): validate_semantic_offer(f["contract"], now=NOW)

    def test_source_question_category_supplied_line_and_event_start_must_agree(self):
        for change in (lambda value: value.update(line="20.5"),
                       lambda value: value.update(gameStartTime="2026-10-22T23:30:00Z"),
                       lambda value: value.update(question="Different Player: Points O/U 19.5"),
                       lambda value: value.update(sportsMarketType="rebounds"),
                       lambda value: value.update(description=value["description"].replace("scores 19.5 points or fewer", "scores 20.5 points or fewer")),
                       lambda value: value.update(conditionId="0x" + "ef" * 32)):
            f = fixture(); change(f["originals"]["market"]); refresh_original(f, "market")
            with self.subTest(change=change), self.assertRaises(IntegrityError):
                replay_semantic_offer(f["contract"], raw_map(f), now=NOW)

    def test_canonical_identity_and_player_affiliation_are_bound_to_same_subject_and_event(self):
        f = fixture(); f["contract"]["player"]["canonical_identity"]["label"] = "Another Player"
        f["contract"] = seal_semantic_offer(f["contract"])
        with self.assertRaises(IntegrityError): validate_semantic_offer(f["contract"], now=NOW)
        for key, value in (("player_id", "Q90000002"), ("player_namespace", "espn"), ("event_id", "another-event")):
            f = fixture(); f["originals"]["affiliation"][key] = value; refresh_original(f, "affiliation")
            with self.subTest(key=key), self.assertRaises(IntegrityError):
                replay_semantic_offer(f["contract"], raw_map(f), now=NOW)
        f = fixture(); f["contract"]["player"]["native_provider_id"] = f["contract"]["selection"]["market_id"]
        f["contract"]["bindings"].append({"field": "player.native_provider_id", "evidence_id": "market", "pointer": "/id", "transform": "direct"})
        f["contract"] = seal_semantic_offer(f["contract"])
        with self.assertRaises(IntegrityError): validate_semantic_offer(f["contract"], now=NOW)

    def test_same_host_unrelated_routes_and_noncanonical_identity_pointer_rejected(self):
        for evidence_id, change in (("market", lambda evidence: evidence.update(url="https://gamma-api.polymarket.com/events/fictional-market")),
                                    ("event", lambda evidence: evidence.update(url="https://gamma-api.polymarket.com/markets/fictional-event")),
                                    ("identity", lambda evidence: evidence.update(url="https://www.wikidata.org/wiki/Special:EntityData/Q90000002.json"))):
            f = fixture(); change(next(e for e in f["contract"]["evidence"] if e["id"] == evidence_id))
            f["contract"] = seal_semantic_offer(f["contract"])
            with self.subTest(evidence_id=evidence_id), self.assertRaises(IntegrityError):
                validate_semantic_offer(f["contract"], now=NOW)

    def test_semantic_completion_does_not_grant_execution_or_public_offer_v1_admission(self):
        from multisport_lab.offer_publication import validate_offer
        f = fixture(); c = f["contract"]
        c["execution_review"]["flags"]["restricted"] = True
        f["originals"]["market"]["restricted"] = True
        c["bindings"].append({"field": "execution_review.flags.restricted", "evidence_id": "market", "pointer": "/restricted", "transform": "direct"})
        refresh_original(f, "market"); c = f["contract"]
        self.assertEqual(replay_semantic_offer(c, raw_map(f), now=NOW)["semantic_status"], "COMPLETE_LOCAL")
        with self.assertRaises(IntegrityError): validate_offer(c, {}, now=NOW)
        for value in (True, 1):
            bad = deepcopy(c); bad["execution_review"]["eligible"] = value; rehash(bad)
            with self.assertRaises(IntegrityError): validate_semantic_offer(bad, now=NOW)

    def test_missing_prices_and_unassigned_exact_source_prices_are_not_semantic_requirements(self):
        f = fixture(); c = f["contract"]
        f["originals"]["market"]["outcomePrices"] = '["0.123456789012345678901","0.876543210987654321099"]'
        c["unassigned_source_economics"]["outcome_prices"] = json.loads(f["originals"]["market"]["outcomePrices"])
        c["bindings"].append({"field": "unassigned_source_economics.outcome_prices", "evidence_id": "market", "pointer": "/outcomePrices", "transform": "json_array"})
        refresh_original(f, "market")
        self.assertEqual(replay_semantic_offer(f["contract"], raw_map(f), now=NOW)["semantic_status"], "COMPLETE_LOCAL")
        self.assertIsNone(f["contract"]["price"]["value"])
        for value in ("1.000000000000000000001", 0.5, "-0.1"):
            bad = deepcopy(f["contract"]); bad["unassigned_source_economics"]["outcome_prices"][0] = value; rehash(bad)
            with self.subTest(value=value), self.assertRaises(IntegrityError): validate_semantic_offer(bad, now=NOW)

    def test_original_corruption_missing_bindings_generic_finality_and_budget_overrun_fail(self):
        f = fixture(); originals = raw_map(f); originals["market"] += b" "
        with self.assertRaises(IntegrityError): replay_semantic_offer(f["contract"], originals, now=NOW)
        for change in (lambda c: c["bindings"].pop(), lambda c: c["category_inventory"].remove("PA"),
                       lambda c: c["evidence"][0].update(raw_bytes=MAX_ORIGINAL_BYTES + 1),
                       lambda c: c["settlement"].update(stat_corrections="A generic oracle challenge lasts two hours."),
                       lambda c: c["price"].update(value="0.5"), lambda c: c.update(qualification="QUALIFIED")):
            c = deepcopy(f["contract"]); change(c); rehash(c)
            with self.subTest(change=change), self.assertRaises(IntegrityError): validate_semantic_offer(c, now=NOW)
        with self.assertRaises(IntegrityError): validate_semantic_batch([f["contract"]] * 33, now=NOW)
        with self.assertRaises(IntegrityError): validate_semantic_batch([f["contract"]] * 2, now=NOW)
        self.assertEqual(validate_semantic_batch([f["contract"]], now=NOW), [f["contract"]])


if __name__ == "__main__":
    unittest.main()

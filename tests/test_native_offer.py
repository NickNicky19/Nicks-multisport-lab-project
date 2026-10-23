"""Fictional native-contract derivation and original-byte replay; no collection."""
from copy import deepcopy
import subprocess
import sys
import unittest

from multisport_lab.integrity import IntegrityError, canonical, digest
from multisport_lab.moviodds_offer import build_review
from multisport_lab.native_offer import (MAX_ASSET_BYTES, MAX_OFFERS, SCHEMA,
    build_native_offer, native_offer_publicly_admitted, replay_native_offer,
    validate_native_offer, validate_native_offers)
from test_moviodds_offer import FIXTURE, NOW, change_json, fictional_assets, fictional_review


def _seal(value):
    value.pop("offer_id", None)
    value["offer_id"] = digest(value)
    return value


class NativeOfferTests(unittest.TestCase):
    def test_boolean_contract_keeps_exact_originals_and_separate_event_conflict(self):
        review = fictional_review()
        before = canonical(review)
        offer = build_native_offer(review, 0, now=NOW)
        self.assertEqual(offer["schema_version"], SCHEMA)
        self.assertEqual(canonical(review), before)
        self.assertEqual(offer["original_review_id"], review["review_id"])
        for key in ["event", "rules", "evidence", "category_inventory"]:
            self.assertEqual(offer[key], review[key])
        self.assertEqual(offer["category"], "DD")
        self.assertEqual(offer["predicate"]["at_least_ten_in_categories"], 2)
        self.assertEqual(offer["selection"]["label"], "Yes")
        self.assertNotIn("line", offer)
        self.assertIsNone(offer["native_player_id"])
        self.assertEqual(offer["canonical_player"]["namespace"], "espn")
        self.assertEqual(offer["event"]["start_difference_seconds"], 600)
        self.assertEqual(offer["event"]["forecast_match_status"], "BLOCKED_EVENT_START_DISAGREEMENT")
        self.assertEqual(len(offer["rules"]["passages"]), 11)
        self.assertEqual(len(offer["category_inventory"]), 14)
        self.assertLessEqual(len(canonical(offer)), 32 * 1024)
        replay = replay_native_offer(offer, fictional_assets(), now=NOW, allow_synthetic=True)
        self.assertEqual(replay["originals_replayed"], 7)
        self.assertFalse(replay["durable_remote_archive_verified"])

    def test_no_selection_and_missing_price_are_semantic_offers_without_fake_threshold(self):
        assets = fictional_assets()
        def change(snapshot):
            row = next(q for q in snapshot["quotes"] if q["group_id"] == "181464")
            row["side"] = "No"
            row.pop("odds_dec")
        change_json(assets, "snapshot", change)
        review = build_review(assets, fixture=FIXTURE, normalized_at=NOW, evidence_lane="SYNTHETIC_TEST")
        offer = build_native_offer(review, 1, now=NOW)
        self.assertEqual(offer["category"], "TD")
        self.assertEqual(offer["selection"]["label"], "No")
        self.assertEqual(offer["predicate"]["selection"], "No")
        self.assertEqual(offer["predicate"]["at_least_ten_in_categories"], 3)
        self.assertIsNone(offer["price"]["value"])
        self.assertEqual(offer["price"]["status"], "PRICE_UNAVAILABLE")
        self.assertEqual(offer["price"]["fractional_as_supplied"], "5/4")
        replay_native_offer(offer, assets, now=NOW, allow_synthetic=True)

    def test_invalid_or_numeric_review_rows_cannot_be_promoted(self):
        review = fictional_review()
        for index in [-1, True, 2, 8, "0"]:
            with self.subTest(index=index), self.assertRaises(IntegrityError):
                build_native_offer(review, index, now=NOW)
        review["observations"][0]["gaps"] = ["INCOMPLETE"]
        review.pop("review_id"); review["review_id"] = digest(review)
        with self.assertRaises(IntegrityError):
            build_native_offer(review, 0, now=NOW)

    def test_resealed_invalid_meaning_is_rejected_before_raw_replay(self):
        offer = build_native_offer(fictional_review(), 0, now=NOW)
        mutations = [
            lambda o: o.update(public_admission=True), lambda o: o.update(ticket_eligible=True),
            lambda o: o.update(qualification="QUALIFIED"), lambda o: o.update(native_player_id="900001"),
            lambda o: o.update(category="PTS"), lambda o: o.update(period="first_quarter"),
            lambda o: o.update(overtime="excluded"), lambda o: o.update(league="NFL"),
            lambda o: o["event"].update(start_difference_seconds=0),
            lambda o: o["event"].update(forecast_match_status="MATCHED"),
            lambda o: o["event"].update(in_play=True),
            lambda o: o["selection"].update(label="OVER", line="0.5"),
            lambda o: o["canonical_player"].update(namespace="moviodds"),
            lambda o: o["canonical_player"].update(team_id="999"),
            lambda o: o["predicate"].update(at_least_ten_in_categories=3),
            lambda o: o["price"].update(value=2.25), lambda o: o["price"].update(status="QUALIFIED"),
            lambda o: o["evidence"]["rules"].update(raw_sha256="not-a-hash"),
            lambda o: o["rules"]["passages"].pop("official_statistics_and_corrections"),
            lambda o: o["rules"]["passages"]["official_statistics_and_corrections"].update(source_value="Later corrections always settle"),
            lambda o: o["category_inventory"].pop("PA"),
        ]
        for change in mutations:
            value = deepcopy(offer); change(value); _seal(value)
            with self.subTest(change=change), self.assertRaises(IntegrityError):
                validate_native_offer(value, now=NOW)

    def test_original_byte_replay_rejects_resealed_factual_changes_and_missing_sources(self):
        offer = build_native_offer(fictional_review(), 0, now=NOW)
        for change in [lambda o: o["selection"].update(selection_id="8888"),
                       lambda o: o["price"].update(value="2.5"),
                       lambda o: o["evidence"]["snapshot"].update(raw_sha256="a" * 64),
                       lambda o: o.update(original_review_id="a" * 64)]:
            value = deepcopy(offer); change(value); _seal(value)
            validate_native_offer(value, now=NOW)  # Meaning alone cannot authenticate originals.
            with self.assertRaises(IntegrityError):
                replay_native_offer(value, fictional_assets(), now=NOW, allow_synthetic=True)
        assets = fictional_assets(); assets.pop("rules")
        with self.assertRaises(IntegrityError):
            replay_native_offer(offer, assets, now=NOW, allow_synthetic=True)
        with self.assertRaises(IntegrityError):
            replay_native_offer(offer, fictional_assets(), now=NOW)

    def test_distinct_later_normalization_clocks_and_one_nanosecond_ordering(self):
        offer = build_native_offer(fictional_review(), 0, now="2026-10-23T12:01:00.000000001Z")
        self.assertNotEqual(offer["normalized_at"], offer["review_normalized_at"])
        replay_native_offer(offer, fictional_assets(), now=offer["normalized_at"], allow_synthetic=True)
        for change in [lambda o: o.update(normalized_at="2026-10-23T12:00:59.999999999Z"),
                       lambda o: o.update(price_changed_at="2026-10-23T11:59:59.987654322Z"),
                       lambda o: o.update(market_polled_at="2026-10-23T11:00:00Z"),
                       lambda o: o.update(knowledge_observed_at="2026-10-23T12:00:00.000000001Z")]:
            value = deepcopy(offer); change(value); _seal(value)
            with self.assertRaises(IntegrityError):
                validate_native_offer(value, now=offer["normalized_at"])
        with self.assertRaises(IntegrityError):
            validate_native_offer(offer, now=NOW)

    def test_digest_and_registry_cannot_be_self_granted(self):
        offer = build_native_offer(fictional_review(), 0, now=NOW)
        self.assertFalse(native_offer_publicly_admitted(offer))
        for key in ["public_admission", "qualification", "evidence_lane"]:
            value = deepcopy(offer); value[key] = True
            self.assertFalse(native_offer_publicly_admitted(value))
        offer["price"]["value"] = "2.5"
        with self.assertRaises(IntegrityError):
            validate_native_offer(offer, now=NOW)

    def test_decimal_bounds_and_status_keep_exact_supplied_precision(self):
        offer = build_native_offer(fictional_review(), 0, now=NOW)
        offer["price"]["value"] = "1.0000000000000000000000001"
        validate_native_offer(_seal(offer), now=NOW)
        for value, status in [("1.0000000000000000000000001", "UNAVAILABLE_AT_CAPTURE"),
                              ("1000000.0000000000000000001", "OBSERVED_PRICE_NOT_QUALIFIED")]:
            changed = deepcopy(offer); changed["price"].update(value=value, status=status)
            with self.assertRaises(IntegrityError):
                validate_native_offer(_seal(changed), now=NOW)

    def test_batch_limits_account_for_actual_encoded_bytes_and_duplicate_native_tuples(self):
        base = build_native_offer(fictional_review(), 0, now=NOW)
        self.assertEqual(validate_native_offers([], now=NOW), [])
        with self.assertRaises(IntegrityError):
            validate_native_offers([base, base], now=NOW)
        rows = []
        for index in range(MAX_OFFERS):
            row = deepcopy(base); row["selection"]["selection_id"] = str(80000 + index); rows.append(_seal(row))
        self.assertGreater(len(canonical(rows)), MAX_ASSET_BYTES)
        with self.assertRaises(IntegrityError):
            validate_native_offers(rows, now=NOW)
        with self.assertRaises(IntegrityError):
            validate_native_offers([base] * (MAX_OFFERS + 1), now=NOW)
        forged = deepcopy(base); forged["selection"]["label"] = "No"; forged["predicate"]["selection"] = "No"; _seal(forged)
        with self.assertRaises(IntegrityError):
            validate_native_offers([base, forged], now=NOW)

    def test_optimized_python_keeps_integrity_checks(self):
        script = """import sys
sys.path.insert(0, 'tests')
from test_moviodds_offer import fictional_assets, fictional_review, NOW
from multisport_lab.integrity import IntegrityError, digest
from multisport_lab.native_offer import build_native_offer, replay_native_offer, validate_native_offer
o=build_native_offer(fictional_review(),0,now=NOW)
replay_native_offer(o,fictional_assets(),now=NOW,allow_synthetic=True)
o['event']['forecast_match_status']='MATCHED'
o.pop('offer_id');o['offer_id']=digest(o)
try: validate_native_offer(o,now=NOW)
except IntegrityError: print('optimized integrity rejection passed')
else: raise SystemExit('optimized validation accepted a forged match')
"""
        result = subprocess.run([sys.executable, "-O", "-c", script], capture_output=True, text=True, timeout=15, check=True)
        self.assertIn("optimized integrity rejection passed", result.stdout)

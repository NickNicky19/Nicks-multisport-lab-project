"""Fictional local response shapes; no source requests or actual offer fixture."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from multisport_lab.gamma_offer_review import (CORRECTION_GAP, ID_GAP, TOKEN_GAP,
    build_preview, inspect_bundle, verify_request_ledger)
from multisport_lab.integrity import IntegrityError, canonical, read_receipt

NOW = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
OBSERVED = "2026-10-21T11:00:00.000001Z"


def market():
    return {"id": "123", "question": "Fictional Player: Points O/U 19.5", "conditionId": "fictional-condition",
            "description": 'This market will resolve to "Yes" if Fictional Player scores more than 19.5 points during the game.\n'
                'This market will resolve to "No" if Fictional Player scores 19.5 points or fewer during the game.\n'
                'The entire game including all overtime periods will be considered.\n'
                'If the game is postponed, this market will remain open until the game has been completed. If the game is canceled entirely, with no make-up game, this market will resolve 50-50.\n'
                'If the player is listed as inactive or otherwise does not take the court at any point, the market will resolve "No".\n'
                'The resolution source will be the official NBA box score as published on NBA.com.',
            "outcomes": '["Yes","No"]', "clobTokenIds": '["11111","22222"]',
            "outcomePrices": '["0.6100000000000000001","0.39"]', "bestBid": "0.5", "bestAsk": "0.72",
            "gameStartTime": "2026-10-21T23:30:00Z", "line": "19.5", "sportsMarketType": "points",
            "updatedAt": "2026-10-21T10:59:00Z", "customLiveness": 900}


def write_bundle(root, change=None):
    selected = market()
    event = {"id": "456", "title": "Fictional Away vs. Fictional Home", "startTime": selected["gameStartTime"],
             "teams": [{"id": 1, "league": "nba", "name": "Fictional Away", "ordering": "away"},
                       {"id": 2, "league": "nba", "name": "Fictional Home", "ordering": "home"}],
             "markets": [deepcopy(selected)]}
    entity = {"entities": {"Q123456": {"id": "Q123456", "labels": {"en": {"value": "Fictional Player"}},
        "descriptions": {"en": {"value": "Fictional basketball player"}}, "lastrevid": 1,
        "claims": {key: [{"mainsnak": {"datatype": "external-id", "datavalue": {"value": value}}}]
                   for key, value in (("P3647", "99999"), ("P3685", "88888"))}}}}
    properties = {"entities": {key: {"labels": {"en": {"value": label}}} for key, label in
                              (("P3647", "NBA.com player ID"), ("P3685", "ESPN.com NBA player ID"))}}
    data = {"gamma-game-event": event, "gamma-edwards-market": selected,
            "wikidata-edwards-entity": entity, "wikidata-identifier-properties": properties}
    if change:
        change(data)
    urls = {"gamma-game-event": "https://gamma-api.polymarket.com/events/456",
            "gamma-edwards-market": "https://gamma-api.polymarket.com/markets/123",
            "wikidata-edwards-entity": "https://www.wikidata.org/wiki/Special:EntityData/Q123456.json",
            "wikidata-identifier-properties": "https://www.wikidata.org/w/api.php?action=wbgetentities&ids=P3647%7CP3685"}
    entries = []
    for ordinal, (label, value) in enumerate(data.items(), 1):
        raw = canonical(value)
        metadata = {"ordinal": ordinal, "label": label, "url": urls[label], "final_url": urls[label],
            "http_status": 200, "complete_body": True, "request_started_at": "2026-10-21T10:59:59Z",
            "observed_at": OBSERVED, "raw_bytes": len(raw), "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "automatic_redirects": False, "retries": 0}
        (root / (label + ".body")).write_bytes(raw)
        (root / (label + ".metadata.json")).write_bytes(canonical(metadata))
        entries.append(metadata)
    (root / "requests.json").write_bytes(canonical({"limit": 12, "requests": entries}))


class GammaOfferReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundle = self.root / "originals"
        self.bundle.mkdir()

    def inspect(self, change=None):
        write_bundle(self.bundle, change)
        return inspect_bundle(self.bundle, now=NOW)

    def test_actual_contract_gaps_cannot_be_filled_with_market_id_or_name_hash(self):
        review, readiness = self.inspect()
        self.assertEqual(review["counts"], {"player_rows_observed": 1, "rows_parsed": 1, "complete_contracts": 0})
        row = review["observations"][0]
        self.assertEqual(row["player_identity"], {"namespace": "wikidata", "id": "Q123456"})
        self.assertIn(ID_GAP, row["gaps"])
        self.assertIn(CORRECTION_GAP, row["gaps"])
        self.assertIn(TOKEN_GAP, row["gaps"])
        self.assertIsNone(row["selection_id"])
        self.assertNotIn("stat_corrections", row["settlement"])
        self.assertFalse(row["normalized_offer_available"])
        self.assertIsNone(readiness["normalized_capture"])
        self.assertIsNone(readiness["canonical_player_crosswalk"]["gamma_player_entity_id"])
        self.assertEqual(readiness["source_fields_as_supplied"]["123"]["customLiveness"], "900")
        self.assertEqual(len(review["category_coverage"]), 14)

    def test_literal_exchange_prices_and_missing_prices_never_become_sportsbook_odds(self):
        review, _ = self.inspect()
        row = review["observations"][0]
        self.assertEqual(row["prices_as_supplied"]["outcomePrices"][0], "0.6100000000000000001")
        self.assertEqual(row["sportsbook_price_status"], "PRICE_UNAVAILABLE")
        def remove_prices(data):
            for label in ("gamma-game-event", "gamma-edwards-market"):
                m = data[label]["markets"][0] if label == "gamma-game-event" else data[label]
                m.pop("outcomePrices")
        review, _ = self.inspect(remove_prices)
        self.assertIsNone(review["observations"][0]["prices_as_supplied"]["outcomePrices"])
        self.assertFalse(any("price" in gap.lower() for gap in review["observations"][0]["gaps"]))

    def test_observed_unimplemented_families_do_not_disappear_as_unobserved(self):
        def add_families(data):
            for index, kind in enumerate(("threes", "assists_points_rebounds", "double_doubles")):
                data["gamma-game-event"]["markets"].append({"id": str(700 + index), "sportsMarketType": kind})
        review, readiness = self.inspect(add_families)
        self.assertEqual(review["counts"], {"player_rows_observed": 4, "rows_parsed": 1, "complete_contracts": 0})
        for category in ("3PM", "PRA", "DD"):
            self.assertEqual(review["category_coverage"][category],
                             {"observed_rows": 1, "parsed_rows": 0, "status": "UNSUPPORTED"})
        self.assertEqual(len(readiness["diagnostics"]), 3)
        self.assertEqual(review["category_coverage"]["TD"]["status"], "UNOBSERVED_IN_SAMPLE")

    def test_checksum_consistent_identity_and_contract_conflicts_are_rejected(self):
        changes = [lambda d: d["gamma-edwards-market"].update(line="20.5"),
                   lambda d: d["gamma-game-event"]["teams"][0].update(league="nfl"),
                   lambda d: d["gamma-game-event"]["teams"][0].update(name="Different Team"),
                   lambda d: d["wikidata-edwards-entity"]["entities"]["Q123456"]["descriptions"]["en"].update(value="Fictional actor"),
                   lambda d: d["wikidata-identifier-properties"]["entities"]["P3647"]["labels"]["en"].update(value="Unverified identifier")]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(IntegrityError):
                self.inspect(change)

    def test_byte_corruption_budget_overrun_and_path_traversal_fail_explicitly(self):
        write_bundle(self.bundle)
        p = self.bundle / "gamma-game-event.body"
        p.write_bytes(p.read_bytes() + b" ")
        with self.assertRaises(IntegrityError):
            inspect_bundle(self.bundle, now=NOW)
        write_bundle(self.bundle)
        ledger = json.loads((self.bundle / "requests.json").read_bytes())
        for entries in (ledger["requests"] * 4, [ledger["requests"][0] | {"label": "../outside"}]):
            (self.bundle / "requests.json").write_bytes(canonical({"limit": 12, "requests": entries}))
            with self.assertRaises(IntegrityError):
                verify_request_ledger(self.bundle)
        write_bundle(self.bundle)
        ledger = json.loads((self.bundle / "requests.json").read_bytes())
        entry = ledger["requests"][0]
        entry["url"] = entry["final_url"] = "https://www.wikidata.org/events/456"
        (self.bundle / "gamma-game-event.metadata.json").write_bytes(canonical(entry))
        (self.bundle / "requests.json").write_bytes(canonical(ledger))
        with self.assertRaises(IntegrityError):
            inspect_bundle(self.bundle, now=NOW)

    def test_original_capture_clock_is_not_refreshed_by_replay_and_future_source_clock_is_flagged(self):
        def future_update(data):
            data["gamma-game-event"]["markets"][0]["updatedAt"] = "2026-10-21T11:30:00Z"
        review, _ = self.inspect(future_update)
        row = review["observations"][0]
        self.assertEqual(row["observed_at"], OBSERVED)
        self.assertIn("source_update_later_than_observation", row["gaps"])
        self.assertNotEqual(review["generated_at"], row["observed_at"])
        with self.assertRaises(IntegrityError):
            inspect_bundle(self.bundle, now=datetime(2026, 10, 20, tzinfo=timezone.utc))

    def test_independent_copy_replays_same_originals_without_new_generation_or_identity_inference(self):
        first, proof = self.inspect()
        recovered = self.root / "recovered"
        shutil.copytree(self.bundle, recovered)
        second, recovered_proof = inspect_bundle(recovered, now=NOW)
        self.assertEqual(first, second)
        self.assertEqual(proof, recovered_proof)
        self.assertFalse(proof["canonical_player_crosswalk"]["current_team_affiliation_verified"])

    def test_preview_refuses_public_tree_and_conflicting_local_assets(self):
        write_bundle(self.bundle)
        source = self.root / "source"
        (source / "web").mkdir(parents=True)
        for name in ("local-offer-review.mjs", "local-offer-review.css", "research.mjs"):
            (source / "web" / name).write_text("/* fictional local asset */")
        with self.assertRaises(IntegrityError):
            build_preview(self.bundle, source / "web/public", now=NOW, source_root=source)
        (source / ".local-data").symlink_to(source / "web", target_is_directory=True)
        with self.assertRaises(IntegrityError):
            build_preview(self.bundle, source / ".local-data/public", now=NOW, source_root=source)
        self.assertFalse((source / "web/public").exists())
        (source / ".local-data").unlink()
        destination = source / ".local-data/preview"
        result = build_preview(self.bundle, destination, now=NOW, source_root=source)
        self.assertFalse(result["public_admission"])
        self.assertEqual(read_receipt(destination / "review.receipt.json")["counts"]["complete_contracts"], 0)
        (destination / "review.json").write_text("corrupt")
        with self.assertRaises(IntegrityError):
            build_preview(self.bundle, destination, now=NOW, source_root=source)


if __name__ == "__main__":
    unittest.main()

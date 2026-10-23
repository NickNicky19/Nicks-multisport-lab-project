"""Fictional offline contracts; no source capture or real model evaluation."""
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab.integrity import IntegrityError, canonical, digest
from multisport_lab.moviodds_offer import (GROUPS, RULE_PASSAGES, URLS, build_review,
    prepare_review, replay_review, rules_text, verify_package)

NOW = "2026-10-23T12:01:00.000000Z"
OBSERVED = "2026-10-23T12:00:00.000000Z"
FIXTURE = "9001"


def _csv(rows):
    out = io.StringIO(); writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows)
    return out.getvalue().encode()


def fictional_assets():
    """All identities, selections, prices and clocks below are fictional."""
    event = {"id": FIXTURE, "home": "TST Home", "away": "OTH Away", "league": "NBA",
             "sport": "basketball", "in_play": False, "kickoff_utc": "2026-10-23T20:10:00Z"}
    quotes = []
    for i, (group, (name, code)) in enumerate(GROUPS.items()):
        quotes.append({"fixture_id": FIXTURE, "group_id": group, "group_name": name,
            "market_id": group, "sel_id": str(10000 + i), "n2": "TST Home",
            "line": "Fictional Centre", "side": "Yes" if code in {"DD", "TD"} else "10",
            "odds_dec": 2.25, "odds_frac": "5/4", "ts": "2026-10-22T10:00:00.123456789Z"})
    quotes.append({"fixture_id": FIXTURE, "group_id": "1453", "group_name": "Game",
        "market_id": "1454", "sel_id": "20000", "line": "Total", "side": "Over",
        "label": "O 240.5", "handicap": "240.5", "odds_dec": 1.9,
        "ts": "2026-10-23T11:58:00.123456789Z"})
    status = {q["group_id"]: {"polled_at": "2026-10-23T11:59:59.123456789Z"} for q in quotes}
    raw = {"catalog": canonical({"count": 1, "fixtures": [event]}),
        "snapshot": canonical({"fixture": FIXTURE, "count": len(quotes), "quotes": quotes,
            "group_status": status, "polled_at": "2026-10-23T11:59:59.123456789Z",
            "server_time": "2026-10-23T11:59:59.987654321Z"}),
        "api": b"<!doctype html><html><body><p>Fictional test API: no key; bet365.</p></body></html>",
        "sports": b"<!doctype html><html><body><p>Fictional basketball player props.</p></body></html>",
        "rules": ("<!doctype html><html><body><svg><path d=\"M0 0\"/></svg>" +
            "".join("<p>" + s + "</p>" for s in RULE_PASSAGES.values()) + "</body></html>").encode(),
        "roster": _csv([{"athlete_id": "900001", "display_name": "Fictional Centre", "season": "2027",
                        "team_id": "900", "team_abbreviation": "TST"}]),
        "schedule": _csv([{"id": "900009", "date": "2026-10-23T20:00Z", "home_abbreviation": "TST",
            "home_name": "Home", "away_abbreviation": "OTH", "away_name": "Away", "home_id": "900",
            "away_id": "901", "season": "2027"}])}
    assets = {}
    for key, body in raw.items():
        url = URLS[key] + FIXTURE if key == "snapshot" else URLS[key]
        media = "application/json" if key in {"catalog", "snapshot"} else "text/csv" if key in {"schedule", "roster"} else "text/html"
        meta = {"url": url, "final_url": url, "http_status": 200, "complete_body": True,
            "content_type": media, "raw_bytes": len(body), "raw_sha256": hashlib.sha256(body).hexdigest(),
            "request_started_at": "2026-10-23T11:59:58.000000Z", "observed_at": OBSERVED}
        if key in {"roster", "schedule"}:
            target = "https://release-assets.githubusercontent.com/fictional/" + key
            meta = [{"url": url, "status": 302, "location": target,
                     "request_started_at": "2026-10-23T11:59:56.000000Z",
                     "observed_at": "2026-10-23T11:59:57.000000Z"},
                    {"url": target, "status": 200, "bytes": len(body), "sha256": meta["raw_sha256"],
                     "content_type": media, "request_started_at": meta["request_started_at"], "observed_at": OBSERVED}]
        assets[key] = {"raw": body, "metadata_raw": canonical(meta)}
    return assets


def change_json(assets, role, change):
    value = json.loads(assets[role]["raw"]); change(value)
    raw = canonical(value); meta = json.loads(assets[role]["metadata_raw"])
    meta["raw_sha256"] = hashlib.sha256(raw).hexdigest(); meta["raw_bytes"] = len(raw)
    assets[role] = {"raw": raw, "metadata_raw": canonical(meta)}


def fictional_review():
    return build_review(fictional_assets(), fixture=FIXTURE, normalized_at=NOW, evidence_lane="SYNTHETIC_TEST")


class MoviOddsOfferTests(unittest.TestCase):
    def test_binary_contract_and_complete_inventory_do_not_invent_ladder_operator(self):
        review = fictional_review()
        self.assertEqual(review["counts"]["complete_local_contracts"], 2)
        self.assertEqual(len(review["category_inventory"]), 14)
        self.assertEqual(review["category_inventory"]["TOV"]["status"], "UNOBSERVED_IN_SAMPLE")
        row = review["observations"][0]
        self.assertEqual(row["category"], "DD")
        self.assertEqual(row["predicate"]["at_least_ten_in_categories"], 2)
        self.assertIsNone(row["native_player_id"])
        self.assertEqual(row["price"]["value"], "2.25")
        self.assertEqual(row["price_changed_at"], "2026-10-22T10:00:00.123456789Z")
        partial = next(x for x in review["observations"] if x["category"] == "PTS")
        self.assertIsNone(partial["predicate"])
        self.assertIn("NUMERIC_SELECTION_OPERATOR_UNVERIFIED", partial["gaps"])
        self.assertEqual(review["event"]["start_difference_seconds"], 600)
        self.assertEqual(review["event"]["forecast_match_status"], "BLOCKED_EVENT_START_DISAGREEMENT")
        self.assertFalse(review["public_admission"])
        self.assertFalse(review["ticket_eligibility"])

    def test_replay_rejects_resealed_meaning_identity_clock_and_price_changes(self):
        review = fictional_review(); assets = fictional_assets()
        for name, change in [
            ("status", lambda b: b["observations"][0].update(semantic_status="INCOMPLETE")),
            ("price", lambda b: b["observations"][0]["price"].update(value="9.0")),
            ("identity", lambda b: b["observations"][0]["canonical_player"].update(id="999")),
            ("period", lambda b: b["observations"][0].update(period="first_quarter")),
            ("clock", lambda b: b.update(observed_at="2026-10-23T11:00:00.000000Z")),
            ("event", lambda b: b["event"].update(forecast_match_status="MATCHED")),
            ("rules", lambda b: b["rules"]["passages"]["official_statistics_and_corrections"].update(start=0)),
        ]:
            with self.subTest(name=name):
                bad = deepcopy(review); change(bad); bad.pop("review_id"); bad["review_id"] = digest(bad)
                with self.assertRaises(IntegrityError):
                    replay_review(bad, assets, now=NOW, allow_synthetic=True)
        with self.assertRaises(IntegrityError):
            replay_review(review, assets, now=NOW)  # synthetic cannot become actual
        self.assertEqual(replay_review(review, assets, now=NOW, allow_synthetic=True)["originals_replayed"], 7)

    def test_complete_response_and_original_hash_are_mandatory(self):
        for key, value in [("complete_body", False), ("http_status", 503), ("raw_sha256", "0" * 64)]:
            assets = fictional_assets(); meta = json.loads(assets["snapshot"]["metadata_raw"])
            meta[key] = value; assets["snapshot"]["metadata_raw"] = canonical(meta)
            with self.subTest(key=key), self.assertRaises(IntegrityError):
                build_review(assets, fixture=FIXTURE, normalized_at=NOW)

    def test_conflicting_fixture_market_period_duplicate_and_future_clocks_fail(self):
        changes = [lambda b: b.update(fixture="9002"),
            lambda b: b["quotes"][0].update(group_name="Team Points"),
            lambda b: b["quotes"][0].update(period="1"),
            lambda b: b["quotes"][1].update(sel_id=b["quotes"][0]["sel_id"],
                group_id=b["quotes"][0]["group_id"], market_id=b["quotes"][0]["market_id"]),
            lambda b: b["quotes"][0].update(ts="2026-10-23T13:00:00Z"),
            lambda b: b["group_status"]["181446"].update(polled_at="2026-10-23T13:00:00Z"),
            lambda b: b.update(server_time="2026-10-23T13:00:00Z")]
        for change in changes:
            assets = fictional_assets(); change_json(assets, "snapshot", change)
            with self.assertRaises(IntegrityError):
                build_review(assets, fixture=FIXTURE, normalized_at=NOW)

    def test_nanosecond_future_clocks_are_rejected_without_datetime_truncation(self):
        changes = [lambda b: b["quotes"][0].update(ts="2026-10-23T11:59:59.987654322Z"),
            lambda b: b["group_status"]["181463"].update(polled_at="2026-10-23T11:59:59.987654322Z"),
            lambda b: b.update(server_time="2026-10-23T12:00:00.000000001Z")]
        for change in changes:
            assets = fictional_assets(); change_json(assets, "snapshot", change)
            with self.assertRaises(IntegrityError):
                build_review(assets, fixture=FIXTURE, normalized_at=NOW)

    def test_redirect_clocks_and_boolean_catalog_count_are_rejected(self):
        assets = fictional_assets(); meta = json.loads(assets["roster"]["metadata_raw"])
        meta[0]["request_started_at"] = "2026-10-23T13:00:00.000000Z"
        assets["roster"]["metadata_raw"] = canonical(meta)
        with self.assertRaises(IntegrityError):
            build_review(assets, fixture=FIXTURE, normalized_at=NOW)
        assets = fictional_assets(); change_json(assets, "catalog", lambda b: b.update(count=True))
        with self.assertRaises(IntegrityError):
            build_review(assets, fixture=FIXTURE, normalized_at=NOW)

    def test_event_difference_and_latest_knowledge_preserve_nanoseconds(self):
        assets = fictional_assets()
        change_json(assets, "catalog", lambda b: b["fixtures"][0].update(kickoff_utc="2026-10-23T20:10:00.000000001Z"))
        for role, fraction in [("api", "000000001"), ("rules", "000000002")]:
            meta = json.loads(assets[role]["metadata_raw"])
            meta["observed_at"] = "2026-10-23T12:00:00." + fraction + "Z"
            assets[role]["metadata_raw"] = canonical(meta)
        review = build_review(assets, fixture=FIXTURE, normalized_at=NOW, evidence_lane="SYNTHETIC_TEST")
        self.assertEqual(review["event"]["start_difference_seconds"], "600.000000001")
        self.assertEqual(review["event"]["forecast_match_status"], "BLOCKED_EVENT_START_DISAGREEMENT")
        self.assertEqual(review["knowledge_observed_at"], "2026-10-23T12:00:00.000000002Z")

    def test_stale_exact_market_cannot_borrow_fresh_fixture_clock(self):
        for change in [lambda b: b["group_status"]["181463"].update(stale=True),
                       lambda b: b["group_status"]["181463"].update(polled_at="2026-10-23T10:00:00Z"),
                       lambda b: next(q for q in b["quotes"] if q["group_id"] == "181463").update(suspended=True)]:
            assets = fictional_assets(); change_json(assets, "snapshot", change)
            review = build_review(assets, fixture=FIXTURE, normalized_at=NOW, evidence_lane="SYNTHETIC_TEST")
            self.assertEqual(review["category_inventory"]["DD"]["complete"], 0)
            self.assertEqual(review["category_inventory"]["TD"]["complete"], 1)

    def test_missing_price_does_not_invalidate_otherwise_complete_binary_contract(self):
        assets = fictional_assets()
        change_json(assets, "snapshot", lambda b: next(q for q in b["quotes"] if q["group_id"] == "181463").pop("odds_dec"))
        review = build_review(assets, fixture=FIXTURE, normalized_at=NOW, evidence_lane="SYNTHETIC_TEST")
        self.assertEqual(review["category_inventory"]["DD"]["complete"], 1)
        self.assertIsNone(review["observations"][0]["price"]["value"])
        self.assertEqual(review["observations"][0]["price"]["status"], "PRICE_UNAVAILABLE")
        self.assertFalse(review["ticket_eligibility"])

    def test_unsupported_price_lexemes_fail_before_creating_an_unrenderable_review(self):
        for value in ["2e0", "+2.25", " 2.25", "2_0", "2" * 129]:
            assets = fictional_assets()
            change_json(assets, "snapshot", lambda b: b["quotes"][0].update(odds_dec=value))
            with self.subTest(value=value), self.assertRaises(IntegrityError):
                build_review(assets, fixture=FIXTURE, normalized_at=NOW)

    def test_live_or_post_start_capture_is_not_a_complete_pregame_contract(self):
        for change in [lambda b: b["fixtures"][0].update(in_play=True),
                       lambda b: b["fixtures"][0].update(kickoff_utc="2026-10-23T11:00:00Z")]:
            assets = fictional_assets(); change_json(assets, "catalog", change)
            review = build_review(assets, fixture=FIXTURE, normalized_at=NOW, evidence_lane="SYNTHETIC_TEST")
            self.assertEqual(review["counts"]["complete_local_contracts"], 0)
            self.assertTrue(all("NOT_A_VERIFIED_PREGAME_CAPTURE" in r["gaps"] for r in review["observations"]))

    def test_missing_or_conflicting_canonical_affiliation_is_not_invented(self):
        assets = fictional_assets()
        change_json(assets, "snapshot", lambda b: b["quotes"][0].update(n2="UNKNOWN TEAM"))
        review = build_review(assets, fixture=FIXTURE, normalized_at=NOW, evidence_lane="SYNTHETIC_TEST")
        points = next(r for r in review["observations"] if r["category"] == "PTS")
        self.assertIsNone(points["canonical_player"])
        self.assertIn("CANONICAL_PLAYER_AFFILIATION_UNVERIFIED", points["gaps"])

    def test_bad_native_ids_and_nontext_team_labels_cannot_build_complete_records(self):
        for change in [lambda b: b["quotes"][0].update(sel_id="UNKNOWN"),
                       lambda b: b["quotes"][0].update(n2=["TST Home"])]:
            assets = fictional_assets(); change_json(assets, "snapshot", change)
            with self.assertRaises(IntegrityError):
                build_review(assets, fixture=FIXTURE, normalized_at=NOW)

    def test_missing_canonical_player_or_event_identity_rejects_supplied_lookup(self):
        for role, field in [("roster", "athlete_id"), ("schedule", "id"), ("schedule", "season")]:
            assets = fictional_assets(); rows = list(csv.DictReader(io.StringIO(assets[role]["raw"].decode())))
            rows[0][field] = ""; raw = _csv(rows); meta = json.loads(assets[role]["metadata_raw"])
            meta[1].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            assets[role] = {"raw": raw, "metadata_raw": canonical(meta)}
            with self.subTest(role=role, field=field), self.assertRaises(IntegrityError):
                build_review(assets, fixture=FIXTURE, normalized_at=NOW)

    def test_versioned_svg_exclusion_does_not_loosen_original_extractor(self):
        from multisport_lab.source_evidence import extract_source_text
        original = fictional_assets()["rules"]["raw"]
        self.assertIn(b"Subsequent amendments", rules_text(original))
        with self.assertRaises(IntegrityError):
            extract_source_text(original, "text/html")
        with self.assertRaises(IntegrityError):
            rules_text(b"<html><body><path/>not SVG</body></html>")
        altered = original.replace(b"Subsequent amendments do not affect settlement.", b"Unknown correction rule.")
        assets = fictional_assets(); meta = json.loads(assets["rules"]["metadata_raw"])
        meta.update(raw_sha256=hashlib.sha256(altered).hexdigest(), raw_bytes=len(altered))
        assets["rules"] = {"raw": altered, "metadata_raw": canonical(meta)}
        with self.assertRaises(IntegrityError):
            build_review(assets, fixture=FIXTURE, normalized_at=NOW)

    def test_interrupted_private_copy_retry_and_readback_freeze_originals(self):
        from multisport_lab.player_line_review import _create
        root = Path(__file__).resolve().parents[1] / ".local-data"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="moviodds-fictional-test-", dir=root) as tmp:
            source = Path(tmp) / "originals"; source.mkdir(); destination = Path(tmp) / "review"
            for role, asset in fictional_assets().items():
                (source / (role + ".body")).write_bytes(asset["raw"])
                (source / (role + ".metadata.json")).write_bytes(asset["metadata_raw"])
            count = 0
            def interrupted(*args, **kwargs):
                nonlocal count
                count += 1
                if count == 4:
                    raise RuntimeError("Synthetic interruption after intent and some originals")
                return _create(*args, **kwargs)
            with patch("multisport_lab.player_line_review._create", side_effect=interrupted), self.assertRaises(RuntimeError):
                prepare_review(source, destination, fixture=FIXTURE, now=NOW, evidence_lane="SYNTHETIC_TEST")
            self.assertTrue((destination / "review-intent.json").is_file())
            result = prepare_review(source, destination, fixture=FIXTURE,
                now="2026-10-23T12:05:00.000000Z", evidence_lane="SYNTHETIC_TEST")
            verified = verify_package(destination, now="2026-10-23T12:05:00.000000Z", allow_synthetic=True)
            self.assertEqual(result["review_id"], verified["review_id"])
            body = json.loads((destination / "review.json").read_bytes())
            self.assertEqual(body["normalized_at"], NOW)
            with self.assertRaises(IntegrityError):
                prepare_review(source, destination, fixture="9002", now=NOW, evidence_lane="SYNTHETIC_TEST")
            body["normalized_at"] = "2026-10-23T12:04:00.000000Z"
            body.pop("review_id"); body["review_id"] = digest(body)
            (destination / "review.json").write_bytes(canonical(body))
            with self.assertRaises(IntegrityError):
                verify_package(destination, now="2026-10-23T12:05:00.000000Z", allow_synthetic=True)


if __name__ == "__main__":
    unittest.main()

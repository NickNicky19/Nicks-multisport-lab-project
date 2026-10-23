"""Version dispatch and independent offer delivery, using fictional sources."""
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab.integrity import IntegrityError, canonical, digest
from multisport_lab import offer_publication as publication
from multisport_lab.moviodds_offer import build_review
from multisport_lab.native_offer import build_native_offer
from multisport_lab.moviodds_archive import PrivateMoviOddsArchive
from multisport_lab.sdv_production_archive import FileArchive
from test_moviodds_offer import FIXTURE, NOW, change_json, fictional_assets, fictional_review
from test_offer_publication import fixture as legacy_fixture


def native_asset(offers, *, admissions=()):
    return publication.seal({"schema_version": publication.NATIVE_ASSET_SCHEMA, "league": "NBA",
        "generated_at": NOW, "status": "OFFER_ONLY_RESEARCH", "category_inventory": list(publication.CATEGORIES),
        "offers": offers, "admissions": list(admissions), "unavailable_reasons": []}, "asset_id")


@contextmanager
def fictional_retained_native(*, synthetic=False):
    """No real source/permission: inject an actual-lane shape to test its gates."""
    root = Path(__file__).resolve().parents[1]; (root / ".local-data").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root / ".local-data", prefix="fictional-native-default-") as folder:
        base = Path(folder); source = base / "originals"; source.mkdir()
        assets = fictional_assets()
        review = build_review(assets, fixture=FIXTURE, normalized_at=NOW,
                             evidence_lane="SYNTHETIC_TEST" if synthetic else "ACTUAL_SOURCE_REPLAY")
        for role, pair in assets.items():
            (source / (role + ".body")).write_bytes(pair["raw"])
            (source / (role + ".metadata.json")).write_bytes(pair["metadata_raw"])
        (source / "review-intent.json").write_bytes(canonical({"fixture": FIXTURE, "normalized_at": NOW,
            "originals": {role: {name: hashlib.sha256(raw).hexdigest() for name, raw in pair.items()}
                          for role, pair in assets.items()}}))
        (source / "review.json").write_bytes(canonical(review))
        archive = PrivateMoviOddsArchive(FileArchive(base / "archive", allow_diagnostics=True), allow_synthetic=synthetic)
        pointer = archive.archive(source, now=NOW)["reference"]
        recovered = archive.fresh_reader().load_recovered_assets(pointer, now=NOW)
        store = publication.OfferStore(base / "ledger", allow_synthetic=synthetic)
        reference = store.retain_native_archive(pointer)
        yield store, reference, pointer, build_native_offer(review, 0, now=NOW), recovered


class NativeOfferPublicationTests(unittest.TestCase):
    def test_make_asset_default_native_reader_recovers_fixed_authenticated_archive(self):
        with fictional_retained_native() as (store, reference, pointer, offer, retained):
            # Model the successful authenticated adapter response, never real I/O.
            remote = {**retained, "durable_remote_archive_verified": True}
            with patch("multisport_lab.native_offer.native_offer_publicly_admitted", return_value=True), \
                    patch("multisport_lab.moviodds_archive.GuardedGitHubReleaseArchive") as backend, \
                    patch("multisport_lab.moviodds_archive.PrivateMoviOddsArchive") as private:
                private.return_value.load_recovered_assets.return_value = remote
                saved = store.persist(offer, None, raw_references=[reference])
                value = publication.make_asset(store.root, now=datetime.now(timezone.utc))
                self.assertEqual(value["schema_version"], publication.NATIVE_ASSET_SCHEMA)
                self.assertEqual(value["offers"], [offer])
                self.assertEqual(value["admissions"], [])
                backend.assert_called_with(allow_diagnostics=True)
                self.assertGreaterEqual(private.return_value.load_recovered_assets.call_count, 3)
                for call in private.return_value.load_recovered_assets.call_args_list:
                    self.assertEqual(call.args, (pointer,))
                self.assertEqual(store.ledger.read(saved)["data"]["offer_capture"]["offer"], offer)

    def test_default_reader_rejects_actual_unreviewed_record_before_any_network(self):
        with fictional_retained_native() as (store, reference, _, offer, _):
            # Deliberately seed an unadmitted receipt, bypassing operating persist,
            # to exercise the actual Pages build path's independent gate.
            store._append("offer-publication-v1:" + offer["offer_id"],
                {"identity": store._identity(offer), "offer_capture": {"offer": offer, "admission": None}},
                (reference,))
            with patch("multisport_lab.moviodds_archive.GuardedGitHubReleaseArchive") as backend, \
                    patch("multisport_lab.moviodds_archive.PrivateMoviOddsArchive") as private:
                with self.assertRaisesRegex(IntegrityError, "public admission"):
                    publication.make_asset(store.root, now=datetime.now(timezone.utc))
                backend.assert_not_called(); private.assert_not_called()

    def test_default_reader_remote_failure_is_closed_without_fallback_or_record_write(self):
        with fictional_retained_native() as (store, reference, _, offer, _):
            with patch("multisport_lab.native_offer.native_offer_publicly_admitted", return_value=True), \
                    patch("multisport_lab.moviodds_archive.GuardedGitHubReleaseArchive"), \
                    patch("multisport_lab.moviodds_archive.PrivateMoviOddsArchive") as private:
                private.return_value.load_recovered_assets.side_effect = IntegrityError("Fictional remote unavailable")
                before = {p: p.read_bytes() for p in (store.root / "records").rglob("*.json")}
                with self.assertRaisesRegex(IntegrityError, "remote unavailable"):
                    store.persist(offer, None, raw_references=[reference])
                self.assertEqual({p: p.read_bytes() for p in (store.root / "records").rglob("*.json")}, before)
                store._append("offer-publication-v1:" + offer["offer_id"],
                    {"identity": store._identity(offer), "offer_capture": {"offer": offer, "admission": None}},
                    (reference,))
                before = {p: p.read_bytes() for p in (store.root / "records").rglob("*.json")}
                with self.assertRaisesRegex(IntegrityError, "remote unavailable"):
                    publication.make_asset(store.root, now=datetime.now(timezone.utc))
                self.assertEqual({p: p.read_bytes() for p in (store.root / "records").rglob("*.json")}, before)

    def test_actual_native_requires_true_remote_durability_even_with_explicit_reader(self):
        with fictional_retained_native() as (store, reference, _, offer, retained):
            self.assertIs(retained["durable_remote_archive_verified"], False)
            with patch("multisport_lab.native_offer.native_offer_publicly_admitted", return_value=True):
                for value in [None, False, "true", 1]:
                    store.raw_reader = lambda _: {**retained, "durable_remote_archive_verified": value}
                    with self.subTest(value=value), self.assertRaisesRegex(IntegrityError, "durable remote"):
                        store.persist(offer, None, raw_references=[reference])
                store.raw_reader = lambda _: {k: v for k, v in retained.items() if k != "durable_remote_archive_verified"}
                with self.assertRaisesRegex(IntegrityError, "durable remote"):
                    store.persist(offer, None, raw_references=[reference])

    def test_synthetic_default_reader_does_not_promote_local_archive_or_contact_github(self):
        with fictional_retained_native(synthetic=True) as (store, reference, _, offer, retained):
            with patch("multisport_lab.moviodds_archive.GuardedGitHubReleaseArchive") as backend:
                with self.assertRaisesRegex(IntegrityError, "explicit offline"):
                    store.persist(offer, None, raw_references=[reference])
                backend.assert_not_called()
            store.raw_reader = lambda _: retained
            saved = store.persist(offer, None, raw_references=[reference])
            self.assertEqual(store.active(), [(saved, {"offer": offer, "admission": None})])

    def test_existing_offer_ledger_recovers_native_contract_and_private_source_graph(self):
        root = Path(__file__).resolve().parents[1]; (root / ".local-data").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root / ".local-data", prefix="native-offer-ledger-") as folder:
            base = Path(folder); source = base / "originals"; source.mkdir()
            assets = fictional_assets(); review = fictional_review()
            for role, pair in assets.items():
                (source / (role + ".body")).write_bytes(pair["raw"])
                (source / (role + ".metadata.json")).write_bytes(pair["metadata_raw"])
            intent = {"fixture": FIXTURE, "normalized_at": NOW,
                "originals": {role: {name: hashlib.sha256(raw).hexdigest() for name, raw in pair.items()}
                              for role, pair in assets.items()}}
            (source / "review-intent.json").write_bytes(canonical(intent))
            (source / "review.json").write_bytes(canonical(review))
            archive = PrivateMoviOddsArchive(FileArchive(base / "archive", allow_diagnostics=True), allow_synthetic=True)
            pointer = archive.archive(source, now=NOW)["reference"]
            store = publication.OfferStore(base / "ledger", allow_synthetic=True)
            reference = store.retain_native_archive(pointer)
            def reader(ref):
                saved = store.ledger.read(ref)["data"]["native_offer_archive"]
                return archive.fresh_reader().load_recovered_assets(saved, now=NOW)
            store.raw_reader = reader
            offer = build_native_offer(review, 0, now=NOW)
            retained = store.persist(offer, None, raw_references=[reference])
            before = {p.relative_to(base / "ledger"): p.read_bytes() for p in (base / "ledger" / "records").rglob("*.json")}
            self.assertEqual(store.persist(offer, None, raw_references=[reference]), retained)
            recovered = publication.OfferStore(base / "ledger", allow_synthetic=True, raw_reader=reader).active()
            self.assertEqual(recovered, [(retained, {"offer": offer, "admission": None})])
            self.assertEqual(before, {p.relative_to(base / "ledger"): p.read_bytes() for p in (base / "ledger" / "records").rglob("*.json")})
            with self.assertRaisesRegex(IntegrityError, "public admission"):
                publication.OfferStore(base / "ledger", raw_reader=reader).active()
            changed = deepcopy(pointer); changed["review_id"] = "a" * 64
            bad_ref = store.retain_native_archive(changed)
            with self.assertRaises(IntegrityError):
                store.persist(offer, None, raw_references=[bad_ref])

    def test_new_version_is_explicit_and_unreviewed_actual_sources_remain_unpublished(self):
        offer = build_native_offer(fictional_review(), 0, now=NOW)
        value = native_asset([offer])
        self.assertEqual(publication.validate_asset(value, now=NOW, allow_synthetic=True), value)
        with self.assertRaisesRegex(IntegrityError, "public admission"):
            publication.validate_asset(value, now=NOW)
        actual = deepcopy(offer); actual["evidence_lane"] = "ACTUAL_SOURCE_REPLAY"
        actual.pop("offer_id"); actual["offer_id"] = digest(actual)
        with self.assertRaisesRegex(IntegrityError, "public admission"):
            publication.validate_asset(native_asset([actual]), now=NOW, allow_synthetic=True)
        old = deepcopy(value); old["schema_version"] = publication.ASSET_SCHEMA
        old = publication.seal(old, "asset_id")
        with self.assertRaisesRegex(IntegrityError, "versioned v2"):
            publication.validate_asset(old, now=NOW, allow_synthetic=True)

    def test_duplicate_native_selection_cannot_be_reimported_with_a_new_record_clock(self):
        first = build_native_offer(fictional_review(), 0, now=NOW)
        second = deepcopy(first); second["normalized_at"] = "2026-10-23T12:01:01.000000Z"
        second.pop("offer_id"); second["offer_id"] = digest(second)
        value = native_asset([first, second]); value["generated_at"] = "2026-10-23T12:02:00.000000Z"
        value = publication.seal(value, "asset_id")
        with self.assertRaisesRegex(IntegrityError, "Duplicate"):
            publication.validate_asset(value, now=value["generated_at"], allow_synthetic=True)

    def test_native_and_legacy_records_keep_independent_admissions_and_semantics(self):
        legacy, admission, _ = legacy_fixture()
        native = build_native_offer(fictional_review(), 0, now=NOW)
        value = native_asset([legacy, native], admissions=[admission])
        publication.validate_asset(value, now=NOW, allow_synthetic=True)
        missing = deepcopy(value); missing["admissions"] = []
        with self.assertRaisesRegex(IntegrityError, "publication review"):
            publication.validate_asset(publication.seal(missing, "asset_id"), now=NOW, allow_synthetic=True)
        before = canonical(native)
        result = publication.match_research_forecast(native, {}, at=NOW)
        self.assertEqual(result["status"], "UNMATCHED")
        self.assertIsNone(result["ev"]); self.assertFalse(result["ticket_eligible"])
        self.assertIn("BLOCKED_EVENT_START_DISAGREEMENT", result["reasons"][0])
        self.assertEqual(canonical(native), before)

    def test_unpriced_boolean_offer_roundtrips_through_frontend_without_fake_line(self):
        assets = fictional_assets()
        change_json(assets, "snapshot", lambda s: next(q for q in s["quotes"] if q["group_id"] == "181463").pop("odds_dec"))
        review = build_review(assets, fixture=FIXTURE, normalized_at=NOW, evidence_lane="SYNTHETIC_TEST")
        offer = build_native_offer(review, 0, now=NOW); value = native_asset([offer])
        script = """import fs from 'node:fs';import assert from 'node:assert/strict';import {webcrypto} from 'node:crypto';
import {validateOfferAsset,verifyOfferAssetHashes,filterOfferRows,renderOffers,matchResearchForecast} from './web/offers.mjs';
const a=JSON.parse(fs.readFileSync(0,'utf8')),now=a.generated_at;
validateOfferAsset(a,now,{allowSynthetic:true});await verifyOfferAssetHashes(a,webcrypto);
const o=a.offers[0],before=JSON.stringify(o),html=renderOffers(a,{now});
assert.match(html,/Fictional Centre/);assert.match(html,/PRICE_UNAVAILABLE/);assert.match(html,/NO_ACTION/);
assert.doesNotMatch(html,/OVER 0.5|UNDER 0.5/);assert.equal(o.native_player_id,null);
assert.equal(filterOfferRows(a.offers,{side:'YES',category:'DD'},Date.parse(now)).length,1);
assert.equal(filterOfferRows(a.offers,{side:'OVER'},Date.parse(now)).length,0);
assert.equal(filterOfferRows(a.offers,{view:'history'},Date.parse('2026-10-24T00:00:00Z')).length,1);
assert.equal(matchResearchForecast(o,{},now).ticket_eligible,false);assert.equal(JSON.stringify(o),before);
console.log(JSON.stringify({offers:a.offers.length,price:o.price.status,categories:Object.keys(o.category_inventory).length}));"""
        result = subprocess.run(["node", "--input-type=module", "-e", script], input=canonical(value),
            capture_output=True, timeout=30, cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(json.loads(result.stdout), {"offers": 1, "price": "PRICE_UNAVAILABLE", "categories": 14})

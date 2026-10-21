"""Synthetic offer software checks; no actual contracts, quotes or rights issued."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab.integrity import IntegrityError, canonical, digest, utc, write_receipt
from multisport_lab import offer_publication as offers
from multisport_lab import source_evidence

NOW = "2026-10-20T18:01:00.000000Z"


def finish(offer, admission):
    admission = deepcopy(admission)
    admission["subject_sha256"] = offers.offer_subject(offer)
    admission = offers.seal(admission, "admission_id")
    offer = {**offer, "admission_id": admission["admission_id"]}
    return offers.seal(offer, "offer_id"), admission


def fixture(raw_record_id="a" * 64, *, priced=False, line="12.5"):
    offer = {"schema_version": offers.OFFER_SCHEMA, "sport": "basketball", "league": "NBA", "id_namespace": "espn",
        "event_id": "synthetic-event", "event_version": "e" * 64, "event_starts_at": "2026-10-20T19:30:00.000000Z",
        "player_id": "synthetic-player", "player_label": "Synthetic Player", "team_id": "synthetic-home",
        "opponent_id": "synthetic-away", "stat": "PTS", "units": "points", "period": "full_game",
        "extra_time_policy": "includes_overtime", "line": line, "side": "over", "variant": "synthetic-standard",
        "venue": "Synthetic Test Venue", "product": "Synthetic Test Product", "settlement_version": "synthetic-rules-1",
        "stat_definition": "Synthetic points credited to this player in the full game including overtime.",
        "settlement_terms": {"status": "SOURCE_VERIFIED", "participation": "Synthetic rule: one recorded appearance is required.",
            "dnp": "Synthetic rule: no appearance voids this selection.", "postponement": "Synthetic rule: a postponed game voids this selection.",
            "ties": "Synthetic rule: an exact line tie pushes this selection.", "official_stat_source": "Fictional Test League official final box score.",
            "stat_corrections": "Synthetic rule: official corrections accepted within 24 hours of final status."},
        "provider": {"name": "Synthetic Provider", "id_namespace": "synthetic", "event_id": "test-event",
                     "player_id": "test-player", "market_id": "test-market", "selection_id": "test-selection"},
        "observed_at": "2026-10-20T17:59:00.000000Z", "source_updated_at": None,
        "imported_at": "2026-10-20T17:59:01.000000Z", "market_status": "PRE_GAME", "evidence_lane": "SYNTHETIC_TEST",
        "source_evidence": [], "price_status": "PRICE_UNAVAILABLE", "price": None, "quote": None, "qualification": "UNAVAILABLE"}
    if priced:
        offer.update(price_status="OBSERVED_PRICE_NOT_QUALIFIED",
                     price={"kind": "pickem_multiplier", "value": "1.04", "evidence_id": "synthetic-contract_view"})
    required = offers.BOUND_FIELDS | ({"price.kind", "price.value"} if priced else set())
    values = {key: offers._target(offer, key) for key in required}
    raw = canonical({"fields": values})
    capture = offers.make_raw_capture(raw, source_url="https://source.example.test/contract",
        request_started_at="2026-10-20T17:58:59.000000Z", observed_at=offer["observed_at"], imported_at=offer["imported_at"])
    for kind in sorted(offers.KINDS):
        fields = set(offers.KIND_BINDINGS[kind])
        if kind == "CONTRACT_VIEW":
            fields |= required  # Compact, fictional source exposes all meanings.
        offer["source_evidence"].append({"evidence_id": "synthetic-" + kind.lower(), "kind": kind,
            **{key: capture[key] for key in ("source_url", "raw_sha256", "raw_bytes", "request_started_at", "observed_at", "source_updated_at")},
            "raw_record_id": raw_record_id,
            "bindings": {key: {"pointer": "/fields/" + key, "source_value": values[key], "meaning": values[key]} for key in fields}})
    admission = {"schema_version": offers.ADMISSION_SCHEMA, "subject_sha256": "", "reviewed_at": NOW,
        "reviewer": "Synthetic software test reviewer", "decision": "SYNTHETIC_ONLY", "scope": "ONE_CAPTURE_DERIVED_FACTS_ONLY",
        "basis": {"kind": "SYNTHETIC_FIXTURE", "reference": "software-test-only", "evidence_sha256": "f" * 64,
                  "description": "Fictional fixture. No real provider permission or observed offer is claimed."},
        "raw_redistribution": False, "scheduled_collection": False}
    offer, admission = finish(offer, admission)
    return offer, admission, capture


def asset_fixture():
    offer, admission, _ = fixture()
    return offers.seal({"schema_version": offers.ASSET_SCHEMA, "league": "NBA", "generated_at": NOW,
        "status": "OFFER_ONLY_RESEARCH", "category_inventory": list(offers.CATEGORIES),
        "offers": [offer], "admissions": [admission], "unavailable_reasons": []}, "asset_id")


def text_rules_fixture(raw_record_id="a" * 64, text_record_id="b" * 64, *, media_type="text/html"):
    """Fictional source quotation mapping; never an actual rules interpretation."""
    offer, admission, capture = fixture(raw_record_id)
    rules = next(item for item in offer["source_evidence"] if item["kind"] == "RULES")
    quotes = {key: "Synthetic café source " + key + ": " + offers._target(offer, key)
              for key in sorted(offers.KIND_BINDINGS["RULES"])}
    raw = ("<main>" + "".join("<p>" + escape(quote) + "</p>" for quote in quotes.values()) + "</main>"
           if media_type == "text/html" else "\r\n".join(quotes.values())).encode("utf-8")
    text = source_evidence.extract_source_text(raw, media_type)
    rules.update(source_url="https://source.example.test/rules", raw_record_id=text_record_id,
                 raw_bytes=len(raw), raw_sha256=hashlib.sha256(raw).hexdigest(),
                 text_replay=source_evidence.make_text_replay(raw, media_type))
    rules["bindings"] = {}
    for key, quote in quotes.items():
        encoded = quote.encode("utf-8"); start = text.index(encoded)
        rules["bindings"][key] = {"start": start, "end": start + len(encoded),
                                   "source_value": quote, "meaning": offers._target(offer, key)}
    metadata = {key: rules[key] for key in ("source_url", "raw_sha256", "raw_bytes", "request_started_at", "observed_at", "source_updated_at")}
    metadata["imported_at"] = capture["imported_at"]
    offer, admission = finish(offer, admission)
    return offer, admission, capture, {"metadata": metadata, "raw": raw}


class OfferPublicationTests(unittest.TestCase):
    def test_html_and_plain_rules_replay_through_original_byte_reader_and_restart(self):
        for media_type in ("text/html", "text/plain"):
            with self.subTest(media_type=media_type), tempfile.TemporaryDirectory() as tmp:
                store = offers.OfferStore(tmp, allow_synthetic=True)
                _, _, capture, retained = text_rules_fixture(media_type=media_type)
                json_ref = store.retain_raw(capture)
                # Only a fictional reference enters the ledger. The supplied
                # test reader holds original fixture bytes outside that ledger.
                text_ref = store.ledger.append("input_captures", "synthetic-text-source",
                    {"synthetic_source_link": {"raw_sha256": retained["metadata"]["raw_sha256"]}})
                offer, admission, _, retained = text_rules_fixture(json_ref.record_id, text_ref.record_id, media_type=media_type)
                def reader(reference):
                    self.assertEqual(reference, text_ref)
                    return retained
                store.raw_reader = reader
                ref = store.persist(offer, admission, raw_references=(json_ref, text_ref))
                original = store.ledger._path(ref.kind, ref.record_id).read_bytes()
                self.assertEqual(store.persist(offer, admission, raw_references=(json_ref, text_ref)), ref)
                recovered = offers.OfferStore(tmp, allow_synthetic=True, raw_reader=reader).active()
                self.assertEqual(recovered[0][1]["offer"], offer)
                self.assertEqual(store.ledger._path(ref.kind, ref.record_id).read_bytes(), original)
                with self.assertRaisesRegex(IntegrityError, "raw reader"):
                    offers.OfferStore(tmp, allow_synthetic=True).active()
                damaged = deepcopy(retained); damaged["raw"] += b" "
                with self.assertRaisesRegex(IntegrityError, "bytes/hash mismatch"):
                    offers.OfferStore(tmp, allow_synthetic=True, raw_reader=lambda _: damaged).active()
                bad = deepcopy(offer)
                binding = next(iter(next(e for e in bad["source_evidence"] if e["kind"] == "RULES")["bindings"].values()))
                binding["source_value"] = binding["source_value"].replace("Synthetic", "Fabricate", 1)
                bad, changed = finish(bad, admission)
                with self.assertRaisesRegex(IntegrityError, "quotation contradicts"):
                    store.persist(bad, changed, raw_references=(json_ref, text_ref))

    def test_text_rules_are_explicit_and_cannot_relabel_json_or_change_meanings(self):
        for mutation in (lambda e: e["text_replay"].update(extractor="invented-summary"),
                         lambda e: e["text_replay"].update(media_type=["text/html"]),
                         lambda e: e["bindings"]["period"].update(pointer="/period"),
                         lambda e: e["bindings"]["period"].update(meaning="first_quarter"),
                         lambda e: e["bindings"]["period"].update(start=True)):
            offer, admission, _, _ = text_rules_fixture()
            mutation(next(e for e in offer["source_evidence"] if e["kind"] == "RULES"))
            offer, admission = finish(offer, admission)
            with self.assertRaises(IntegrityError):
                offers.validate_offer(offer, admission, now=NOW, allow_synthetic=True)
        offer, admission, _, _ = text_rules_fixture()
        rules = next(e for e in offer["source_evidence"] if e["kind"] == "RULES")
        next(e for e in offer["source_evidence"] if e["kind"] == "CONTRACT_VIEW")["text_replay"] = rules["text_replay"]
        offer, admission = finish(offer, admission)
        with self.assertRaisesRegex(IntegrityError, "restricted to RULES"):
            offers.validate_offer(offer, admission, now=NOW, allow_synthetic=True)
        with tempfile.TemporaryDirectory() as tmp:
            store = offers.OfferStore(tmp, allow_synthetic=True)
            _, _, capture, _ = text_rules_fixture(); ref = store.retain_raw(capture)
            offer, admission, _, _ = text_rules_fixture(ref.record_id, ref.record_id)
            with self.assertRaisesRegex(IntegrityError, "legacy helper is JSON-only"):
                store.persist(offer, admission, raw_references=(ref,))

    def test_python_text_rules_contract_matches_frontend_validation(self):
        offer, admission, _, _ = text_rules_fixture()
        code = ("import fs from 'node:fs'; import {validateOffer} from './web/offers.mjs'; "
                "const x=JSON.parse(fs.readFileSync(0,'utf8')); "
                "validateOffer(x.offer,x.admission,x.now,{allowSynthetic:true});")
        result = subprocess.run(["node", "--input-type=module", "-e", code],
            input=json.dumps({"offer": offer, "admission": admission, "now": NOW}), capture_output=True,
            text=True, cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_complete_priceless_contract_is_distinct_from_partial_and_usable_quote(self):
        offer, admission, _ = fixture()
        self.assertEqual(offers.validate_offer(offer, admission, now=NOW, allow_synthetic=True), offer)
        self.assertIsNone(offer["price"])
        self.assertIsNone(offer["quote"])
        self.assertEqual(offer["qualification"], "UNAVAILABLE")
        with self.assertRaisesRegex(IntegrityError, "publicly admitted"):
            offers.validate_offer(offer, admission, now=NOW)

    def test_actual_admission_cannot_self_authorize_from_a_review_declaration(self):
        offer, admission, _ = fixture()
        offer["evidence_lane"] = "REAL_TIME_CAPTURED"
        admission.update(decision="ADMITTED_DERIVED_FACTS")
        admission["basis"]["kind"] = "PUBLIC_SOURCE_SCOPED_REVIEW"
        offer, admission = finish(offer, admission)
        with self.assertRaisesRegex(IntegrityError, "reviewed registry"):
            offers.validate_offer(offer, admission, now=NOW)
        self.assertFalse(offers.APPROVED_PUBLIC_ADMISSION_IDS)

    def test_resealed_contradictory_contract_fields_and_partial_rows_fail(self):
        mutations = [lambda o: o.update(side="unknown"), lambda o: o.update(period=None),
            lambda o: o.update(extra_time_policy="unknown"), lambda o: o.update(units="rebounds"),
            lambda o: o.update(team_id=o["opponent_id"]), lambda o: o["provider"].update(player_id="wrong-player"),
            lambda o: o["source_evidence"].pop(), lambda o: o.update(quote={"decimal_odds": "1.04"}),
            lambda o: o.update(source_updated_at="2026-10-20T17:59:00.000001Z"),
            lambda o: o.update(imported_at="2026-10-20T18:01:00.000001Z"),
            lambda o: o["settlement_terms"].pop("dnp"), lambda o: o["settlement_terms"].update(dnp="UNKNOWN"),
            lambda o: o.update(stat_definition=""),
            lambda o: o["source_evidence"][0]["bindings"].update(line={"pointer": "/line", "source_value": "12.5", "meaning": "13.5"})]
        for change in mutations:
            with self.subTest(change=change):
                offer, admission, _ = fixture(); change(offer); offer, admission = finish(offer, admission)
                with self.assertRaises(IntegrityError):
                    offers.validate_offer(offer, admission, now=NOW, allow_synthetic=True)

    def test_price_retains_multiplier_kind_and_joint_observation(self):
        offer, admission, _ = fixture(priced=True)
        offers.validate_offer(offer, admission, now=NOW, allow_synthetic=True)
        self.assertEqual(offer["price"]["kind"], "pickem_multiplier")
        offer["price"]["kind"] = "sportsbook_decimal"
        offer, admission = finish(offer, admission)
        with self.assertRaisesRegex(IntegrityError, "contradicts"):
            offers.validate_offer(offer, admission, now=NOW, allow_synthetic=True)

    def test_actual_raw_body_cannot_enter_synthetic_plaintext_helper(self):
        _, _, capture = fixture()
        capture["source_url"] = "https://sports.core.api.espn.com/provider"
        with self.assertRaisesRegex(IntegrityError, "private retention"):
            offers.validate_raw_capture(capture)

    def test_source_binding_is_replayed_against_retained_raw_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = offers.OfferStore(tmp, allow_synthetic=True)
            _, _, raw = fixture(); raw_ref = store.retain_raw(raw)
            offer, admission, _ = fixture(raw_ref.record_id)
            reference = store.persist(offer, admission, raw_references=(raw_ref,))
            original = store.ledger._path(reference.kind, reference.record_id).read_bytes()
            self.assertEqual(store.persist(offer, admission, raw_references=(raw_ref,)), reference)
            recovered = offers.OfferStore(tmp, allow_synthetic=True).active()
            self.assertEqual(recovered[0][1]["offer"], offer)
            self.assertEqual(store.ledger._path(reference.kind, reference.record_id).read_bytes(), original)
            bad = deepcopy(offer); bad["source_evidence"][0]["bindings"]["line"]["source_value"] = "99.5"
            bad, changed = finish(bad, admission)
            with self.assertRaisesRegex(IntegrityError, "raw value"):
                store.persist(bad, changed, raw_references=(raw_ref,))

    def test_interrupted_retention_recovers_original_without_new_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = offers.OfferStore(tmp, allow_synthetic=True)
            _, _, body = fixture(); ref = store.retain_raw(body)
            self.assertEqual(offers.OfferStore(tmp, allow_synthetic=True).active(), [])
            self.assertEqual(store.retain_raw(body), ref)
            offer, admission, _ = fixture(ref.record_id)
            with patch.object(store, "_validate_retained", side_effect=[None, IntegrityError("simulated lost acknowledgment")]):
                with self.assertRaisesRegex(IntegrityError, "lost acknowledgment"):
                    store.persist(offer, admission, raw_references=(ref,))
            recovered = offers.OfferStore(tmp, allow_synthetic=True).active()
            self.assertEqual(len(recovered), 1)
            self.assertEqual(recovered[0][1]["offer"]["observed_at"], offer["observed_at"])

    def test_correction_appends_a_link_and_preserves_original_bytes_and_clocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = offers.OfferStore(tmp, allow_synthetic=True)
            refs = []
            for line in ("12.5", "13.5"):
                _, _, raw = fixture(line=line); raw_ref = store.retain_raw(raw)
                offer, admission, _ = fixture(raw_ref.record_id, line=line)
                refs.append(store.persist(offer, admission, raw_references=(raw_ref,)))
            original = store.ledger._path(refs[0].kind, refs[0].record_id).read_bytes()
            correction = store.correct(*refs, reason="Synthetic source correction test")
            self.assertEqual(store.correct(*refs, reason="Synthetic source correction test"), correction)
            self.assertEqual(store.ledger._path(refs[0].kind, refs[0].record_id).read_bytes(), original)
            active = offers.OfferStore(tmp, allow_synthetic=True).active()
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0][1]["offer"]["line"], "13.5")
            self.assertEqual(active[0][1]["offer"]["observed_at"], "2026-10-20T17:59:00.000000Z")

    def test_offer_readback_is_independent_of_unrelated_typed_forecast_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = offers.OfferStore(tmp, allow_synthetic=True)
            _, _, raw = fixture(); raw_ref = store.retain_raw(raw)
            offer, admission, _ = fixture(raw_ref.record_id)
            store.persist(offer, admission, raw_references=(raw_ref,))
            # A valid checksum around an invalid unrelated research record.
            write_receipt(Path(tmp) / "records" / "forecasts" / ("f" * 64 + ".json"),
                          {"data": {"bundle": {"schema_version": "invalid"}}})
            self.assertEqual(len(offers.OfferStore(tmp, allow_synthetic=True).active()), 1)

    def test_budget_failure_counts_existing_records_and_completion_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = offers.OfferStore(tmp, allow_synthetic=True)
            _, _, body = fixture()
            with patch("multisport_lab.operational_pilot.metadata_inventory", return_value={"file_count": 512, "total_bytes": 0}):
                with self.assertRaisesRegex(IntegrityError, "shared ledger budget"):
                    store.retain_raw(body)
            self.assertFalse(list(Path(tmp).glob("records/**/*.json")))

    def test_op_current_and_archived_proof_metadata_prevents_offer_writes_at_both_limits(self):
        from multisport_lab.operational_pilot import metadata_inventory
        for limit in ("records", "bytes"):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as tmp:
                store = offers.OfferStore(tmp, allow_synthetic=True)
                _, _, body = fixture(); raw_ref = store.retain_raw(body)
                original = store.ledger._path(raw_ref.kind, raw_ref.record_id).read_bytes()
                offer, admission, _ = fixture(raw_ref.record_id)
                directory = Path(tmp) / "evidence/operational002"; directory.mkdir(parents=True)
                # Deliberately synthetic proof metadata: size accounting only,
                # not a valid operational acknowledgment or admission.
                (directory / "completions.jsonl").write_bytes(b"{}\n")
                (directory / ("remote-recovery." + "a" * 64 + ".json")).write_bytes(b"{}")
                metadata = metadata_inventory(tmp)
                self.assertEqual(metadata["file_count"], 2)
                bound = patch("multisport_lab.ledger.MAX_LEDGER_RECORDS", 3) if limit == "records" else patch(
                    "multisport_lab.ledger.MAX_LEDGER_BYTES", len(original) + metadata["total_bytes"] + 1)
                with bound, self.assertRaisesRegex(IntegrityError, "shared ledger budget"):
                    store.persist(offer, admission, raw_references=(raw_ref,))
                self.assertEqual(store.ledger._path(raw_ref.kind, raw_ref.record_id).read_bytes(), original)
                self.assertEqual(store.active(), [])

    def test_duplicate_provider_selection_or_missing_category_inventory_fails(self):
        for mutate in [lambda a: a["offers"].append(deepcopy(a["offers"][0])),
                       lambda a: a["category_inventory"].remove("TD")]:
            value = asset_fixture(); mutate(value); value = offers.seal(value, "asset_id")
            with self.assertRaises(IntegrityError):
                offers.validate_asset(value, now=NOW, allow_synthetic=True)

    def test_default_empty_export_has_full_inventory_and_no_source_capture_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            asset = offers.make_asset(tmp, now=utc(NOW))
            self.assertEqual(asset["offers"], [])
            self.assertEqual(len(asset["category_inventory"]), 14)
            self.assertIn("retained source contract", asset["unavailable_reasons"][0])
            raw = canonical(asset); sha = hashlib.sha256(raw).hexdigest()
            descriptor = {"path": "nba-offers." + sha + ".json", "sha256": sha, "generated_at": NOW,
                          "status": "OFFER_ONLY_RESEARCH", "retained": False, "error": None}
            (Path(tmp) / descriptor["path"]).write_bytes(raw)
            self.assertEqual(offers.read_asset(tmp, descriptor, now=NOW), asset)
            descriptor["path"] = "../" + descriptor["path"]
            with self.assertRaisesRegex(IntegrityError, "Unsafe"):
                offers.read_asset(tmp, descriptor, now=NOW)

    def test_research_matching_needs_exact_meaning_clocks_but_not_price(self):
        offer, _, _ = fixture(); offer["evidence_lane"] = "REAL_TIME_CAPTURED"
        forecast = {key: offer[key] for key in ("league", "id_namespace", "event_id", "event_version", "player_id",
            "team_id", "opponent_id", "event_starts_at", "period", "extra_time_policy")}
        forecast.update(categories=[{"code": "PTS", "units": "points"}], cutoff_at="2026-10-20T18:00:00.000000Z",
            issued_at="2026-10-20T18:00:05.000000Z", evidence_lane="REAL_TIME_CAPTURED", conditioning="CONDITIONAL_ON_APPEARANCE")
        result = offers.match_research_forecast(offer, forecast, at=NOW)
        self.assertEqual(result["status"], "MATCHED_RESEARCH_ONLY")
        self.assertFalse(result["ticket_eligible"]); self.assertIsNone(result["ev"])
        for changed in ({"event_version": "b" * 64}, {"id_namespace": "sleeper"}, {"period": "first_quarter"},
                        {"extra_time_policy": "regulation_only"}, {"evidence_lane": "RECONSTRUCTED_RESEARCH"},
                        {"issued_at": "2026-10-20T18:01:00.000001Z"}):
            self.assertEqual(offers.match_research_forecast(offer, {**forecast, **changed}, at=NOW)["status"], "UNMATCHED")

    def test_optimized_python_keeps_semantic_rejection(self):
        code = "from multisport_lab.offer_publication import validate_raw_capture; from multisport_lab.integrity import IntegrityError\ntry: validate_raw_capture({'schema_version':'bad'})\nexcept IntegrityError: pass\nelse: raise RuntimeError('optimized validator admitted malformed evidence')"
        result = subprocess.run([sys.executable, "-O", "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

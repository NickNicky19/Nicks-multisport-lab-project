"""Fictional Sleeper-shaped rows exercise private line review, never collection."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab.integrity import IntegrityError, canonical, digest, read_receipt, stamp, utc, write_receipt
from multisport_lab import player_line_review as review


OBSERVED = utc("2026-10-22T10:00:00.000000Z")
IMPORTED = OBSERVED + timedelta(minutes=1)
GENERATED = OBSERVED + timedelta(minutes=2)


def source_row(label="points", *, player="1001", event="9001", threshold=22.5,
               multiplier=None, sport="nba"):
    """All identities and values in this helper are authored test fixtures."""
    common = {"sport": sport, "game_id": event, "subject_id": player,
              "subject_type": "player", "market_type": label+"_over_under_player_"+player,
              "wager_type": label, "outcome_type": "over_under", "line_type": "normal",
              "season": "2026", "season_type": "regular", "game_status": "pre_game"}
    options = []
    for side in ("over", "under"):
        option = {**common, "status": "active", "line_id": player+"-"+label+"-"+side,
                  "outcome": side, "outcome_value": threshold, "subject_team": "Fictional Team"}
        if multiplier is not None:
            option["payout_multiplier"] = multiplier
        options.append(option)
    return {**common, "status": "active", "updated_at": int((OBSERVED-timedelta(seconds=1)).timestamp()*1000),
            "options": options}


def original(rows=None, *, exact_line=None, exact_multiplier=None):
    rows = deepcopy(rows if rows is not None else [source_row()])
    if exact_line is not None:
        for option in rows[0]["options"]:
            option["outcome_value"] = "NUMERIC_LINE_LEXEME"
    if exact_multiplier is not None:
        for option in rows[0]["options"]:
            option["payout_multiplier"] = "NUMERIC_MULTIPLIER_LEXEME"
    raw = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()
    if exact_line is not None:
        raw = raw.replace(b'"NUMERIC_LINE_LEXEME"', exact_line.encode())
    if exact_multiplier is not None:
        raw = raw.replace(b'"NUMERIC_MULTIPLIER_LEXEME"', exact_multiplier.encode())
    metadata = {"url": review.URL, "final_url": review.URL, "http_status": 200,
                "content_type": "application/json", "complete_body": True,
                "request_started_at": stamp(OBSERVED-timedelta(seconds=1)), "observed_at": stamp(OBSERVED),
                "raw_bytes": len(raw), "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "evidence_lane": "SYNTHETIC_TEST"}
    return raw, canonical(metadata)


def reseal(body):
    body = deepcopy(body)
    body["review_id"] = digest({key: value for key, value in body.items() if key != "review_id"})
    return body


class PlayerLineReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.inputs = self.root/"inputs"
        self.inputs.mkdir()

    def files(self, raw=None, metadata=None, *, name="fixture"):
        if raw is None:
            raw, metadata = original()
        body_path = self.inputs/(name+".body")
        meta_path = self.inputs/(name+".metadata.json")
        body_path.write_bytes(raw)
        meta_path.write_bytes(metadata)
        return body_path, meta_path

    def build(self, *, rows=None, exact_line=None, exact_multiplier=None,
              output="review", now=GENERATED, offset=0, limit=32):
        raw, metadata = original(rows, exact_line=exact_line, exact_multiplier=exact_multiplier)
        body, meta = self.files(raw, metadata, name=output)
        destination = self.root/".local-data"/output
        result = review.build_preview(destination=destination, source_root=self.root, now=now,
                                      body=body, metadata=meta, offset=offset, limit=limit)
        return result, json.loads((destination/"review.json").read_bytes()), destination, body, meta

    @staticmethod
    def inventory(directory):
        return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir() if p.is_file()}

    def test_exact_numeric_lexemes_and_source_multiplier_stay_price_independent(self):
        line = "22.500000000000000000000001"
        multiplier = "1.700000000000000000000001"
        result, body, destination, source, metadata = self.build(exact_line=line, exact_multiplier=multiplier)
        self.assertEqual(body["evidence_lane"], "SYNTHETIC_TEST")
        self.assertEqual([r["line"] for r in body["observations"]], [line, line])
        row = body["observations"][0]
        self.assertEqual(row["source_economics"], {"kind": "pickem_multiplier", "value": multiplier})
        self.assertEqual(row["price_status"], "PRICE_UNAVAILABLE")
        self.assertIsNone(row["quote"])
        self.assertIsNone(row["contract"])
        self.assertFalse(row["ticket_eligible"])
        evidence = result["source_evidence"]
        self.assertEqual(evidence["kind"], "RAW_HTTP_BODY_REPLAYED")
        self.assertEqual(evidence["input_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(evidence["raw_source_sha256"], evidence["input_sha256"])
        self.assertEqual(evidence["metadata_sha256"], hashlib.sha256(metadata.read_bytes()).hexdigest())
        self.assertEqual(row["source_pointer"], "/0/options/0/outcome_value")
        self.assertEqual((destination/"source.body").read_bytes(), source.read_bytes())

    def test_absent_price_does_not_discard_valid_threshold_observations(self):
        result, body, *_ = self.build()
        self.assertEqual(result["counts"]["parsed_observations"], 2)
        self.assertEqual(body["counts"]["complete_contracts"], 0)
        for row in body["observations"]:
            self.assertIsNone(row["source_economics"])
            self.assertEqual(row["price_status"], "PRICE_UNAVAILABLE")
            self.assertIn("price_missing", row["unavailable_reasons"])
            self.assertEqual(row["forecast_match_status"], "NOT_MATCHED_UNVERIFIED_IDENTITY_EVENT_PERIOD")

    def test_all14_counts_include_pa_and_keep_quarters_unmapped(self):
        rows = [source_row(label, player=str(1100+index)) for index, label in enumerate(review.SLEEPER_LABELS)]
        rows += [source_row("first_qtr_points", player="1300"), source_row(sport="nfl", player="1301")]
        _, body, *_ = self.build(rows=rows, limit=2)
        self.assertEqual(set(body["category_coverage"]), set(review.ALL_CATEGORIES))
        self.assertEqual(len(body["category_coverage"]), 14)
        self.assertEqual(body["counts"]["source_rows"], len(rows))
        self.assertEqual(body["counts"]["nba_rows"], len(rows)-1)
        self.assertEqual(body["counts"]["parsed_observations"], 2*(len(rows)-1))
        self.assertEqual(body["counts"]["displayed_observations"], 2)
        self.assertEqual(body["counts"]["unmapped_observations"], 2)
        self.assertEqual(body["category_coverage"]["PA"]["observed_side_options"], 2)
        self.assertEqual(body["category_coverage"]["PA"]["displayed_side_options"], 0)
        self.assertEqual(body["category_coverage"]["TD"]["status"], "UNOBSERVED_IN_SAMPLE")

    def test_explicit_display_page_keeps_full_source_inventory(self):
        rows = [source_row(player=str(1400+index)) for index in range(20)]
        _, first, *_ = self.build(rows=rows, output="first")
        _, last, *_ = self.build(rows=rows, output="last", offset=32)
        self.assertEqual(first["counts"]["displayed_observations"], 32)
        self.assertEqual(last["counts"]["displayed_observations"], 8)
        self.assertEqual(first["counts"]["parsed_observations"], 40)
        self.assertEqual(last["category_coverage"]["PTS"]["observed_side_options"], 40)
        self.assertEqual(last["selection"]["offset"], 32)
        self.assertEqual(first["source_evidence"]["input_sha256"], last["source_evidence"]["input_sha256"])

    def test_derived_receipt_never_claims_recovered_original_bytes(self):
        raw, metadata = original(exact_line="22.500000000000000000000001")
        report, _ = review.normalize_original(raw, metadata, imported_at=IMPORTED)
        receipt = self.inputs/"derived.receipt.json"
        write_receipt(receipt, report)
        destination = self.root/".local-data"/"derived"
        result = review.build_preview(destination=destination, source_root=self.root, now=GENERATED, receipt=receipt)
        body = json.loads((destination/"review.json").read_bytes())
        self.assertEqual(result["source_evidence"]["kind"], "DERIVED_RECEIPT_ONLY")
        for key in ("raw_source_sha256", "raw_source_bytes", "metadata_sha256"):
            self.assertIsNone(result["source_evidence"][key])
        self.assertEqual(result["source_evidence"]["source_payload_sha256"], report["source_payload_sha256"])
        self.assertEqual(result["source_evidence"]["capture_sha256"], report["capture_sha256"])
        self.assertEqual(body["observations"][0]["precision_basis"], "DERIVED_TEXT_ONLY")
        self.assertEqual(body["observations"][0]["source_pointer"], "/payload/observations/0/line")
        self.assertEqual(body["imported_at"], stamp(IMPORTED))
        self.assertFalse(review.verify_package(destination, now=GENERATED)["original_http_bytes_recovered"])

    def test_old_observation_remains_old_and_future_clocks_reject(self):
        _, body, *_ = self.build(now=GENERATED+timedelta(days=60))
        self.assertEqual(body["observed_at"], stamp(OBSERVED))
        self.assertEqual(body["observations"][0]["source_updated_at"], stamp(OBSERVED-timedelta(seconds=1)))
        raw, metadata = original()
        future = json.loads(metadata)
        future["observed_at"] = stamp(GENERATED+timedelta(seconds=1))
        with self.assertRaises(IntegrityError):
            review.normalize_original(raw, canonical(future), imported_at=GENERATED)
        for mutate in (
                lambda b: b.update(generated_at=stamp(GENERATED+timedelta(seconds=1))),
                lambda b: b["observations"][0].update(source_updated_at=stamp(OBSERVED+timedelta(seconds=1)))):
            changed = deepcopy(self.build(output="clock-"+str(id(mutate)))[1])
            mutate(changed)
            with self.assertRaises(IntegrityError):
                review.validate_review(reseal(changed), now=GENERATED)

    def test_valid_seal_does_not_admit_invalid_semantics(self):
        _, body, *_ = self.build()
        mutations = [
            lambda b: b.update(public_admission=True),
            lambda b: b["source_evidence"].update(provider_permission_verified=True),
            lambda b: b["observations"][0].update(player_namespace="espn"),
            lambda b: b["observations"][0].update(player_label="Invented Verified Name"),
            lambda b: b["observations"][0].update(provider_player_id=""),
            lambda b: b["observations"][0].update(stat="REB"),
            lambda b: b["observations"][0].update(period="full_game"),
            lambda b: b["observations"][0].update(price_status="OBSERVED_PRICE_NOT_QUALIFIED"),
            lambda b: b["observations"][0].update(ticket_eligible=True),
            lambda b: b["observations"][0].update(unavailable_reasons=[]),
            lambda b: b["category_coverage"]["PA"].update(observed_side_options=1),
        ]
        for index, mutate in enumerate(mutations):
            changed = deepcopy(body)
            mutate(changed)
            with self.subTest(case=index), self.assertRaises(IntegrityError):
                review.validate_review(reseal(changed), now=GENERATED)

    def test_failed_or_empty_status_cannot_describe_nonempty_observations(self):
        _, body, *_ = self.build()
        for status in ("empty", "blocked_access", "upstream_error", "parser_failure"):
            changed = deepcopy(body)
            changed["parse_status"] = status
            with self.subTest(status=status), self.assertRaises(IntegrityError):
                review.validate_review(reseal(changed), now=GENERATED)

    def test_resealed_derived_receipt_validates_unselected_source_observations(self):
        raw, metadata = original([source_row(player="1501"), source_row(player="1502")])
        report, _ = review.normalize_original(raw, metadata, imported_at=IMPORTED)
        # Index three is outside the explicit first-two-observation display.
        # A small display must not hide corrupt records in whole-source counts.
        mutations = [
            lambda b: b["observations"][3].update(provider_player_id=""),
            lambda b: b["observations"][3].update(player_id="espn:nba:player:1502"),
            lambda b: b["observations"][3].update(event_id="another-provider:9001"),
            lambda b: b["observations"][3].update(side="either"),
            lambda b: b["observations"][3].update(source_updated_at=stamp(OBSERVED+timedelta(seconds=1))),
            lambda b: b["observations"][3].update(line="-1"),
            lambda b: b["observations"][3].update(line="NaN"),
            lambda b: b["observations"][3].update(stat="REB"),
            lambda b: b["observations"][3].update(price={"kind": "sportsbook_decimal", "value": "1.9"}),
            lambda b: b["observations"][3].update(unavailable_reasons=["same", "same"]),
            lambda b: b["observations"][3].update(row_id=b["observations"][0]["row_id"]),
            lambda b: b["observations"][3].update(row_id="row:01/option:1"),
        ]
        for index, mutate in enumerate(mutations):
            changed = deepcopy(report)
            mutate(changed)
            receipt = self.inputs/("unselected-"+str(index)+".receipt.json")
            write_receipt(receipt, changed)
            with self.subTest(case=index), self.assertRaises(IntegrityError):
                review.build_preview(destination=self.root/".local-data"/("unselected-"+str(index)),
                                     source_root=self.root, now=GENERATED, receipt=receipt, limit=2)

    def test_duplicate_provider_selections_remain_partial_source_evidence(self):
        # Repeated source identities are not silently deduplicated or asserted
        # unique: the importer preserves the distinct positions and diagnoses them.
        result, body, destination, *_ = self.build(
            rows=[source_row(player="1601"), source_row(player="1601")],
            output="duplicate-selections", limit=2)
        self.assertEqual(body["parse_status"], "partial")
        self.assertEqual(result["counts"]["parsed_observations"], 4)
        self.assertEqual(result["counts"]["diagnostics"], 4)
        self.assertEqual(result["counts"]["complete_contracts"], 0)
        self.assertEqual(result["counts"]["displayed_observations"], 2)
        for row in body["observations"]:
            self.assertIn("duplicate_provider_selection_id", row["unavailable_reasons"])
            self.assertIsNone(row["quote"])
            self.assertIsNone(row["contract"])
            self.assertFalse(row["ticket_eligible"])
        self.assertEqual(review.verify_package(destination, now=GENERATED)["recovery"],
                         "LOCAL_SOURCE_REPLAY_VERIFIED")

    def test_source_positions_are_canonical_ascii_and_option_bounded(self):
        _, body, *_ = self.build()
        pairs = [("row:00/option:0", "/00/options/0/outcome_value"),
                 ("row:0/option:00", "/0/options/00/outcome_value"),
                 ("row:0/option:64", "/0/options/64/outcome_value"),
                 ("row:1/option:0", "/1/options/0/outcome_value"),
                 ("row:٠/option:0", "/٠/options/0/outcome_value"),
                 ("row:0/option:0", "/0/options/1/outcome_value")]
        for row_id, pointer in pairs:
            changed = deepcopy(body)
            changed["observations"][0].update(row_id=row_id, source_pointer=pointer)
            with self.subTest(row_id=row_id, pointer=pointer), self.assertRaises(IntegrityError):
                review.validate_review(reseal(changed), now=GENERATED)

    def test_invalid_originals_and_metadata_fail_without_partial_import(self):
        raw, metadata = original()
        for key, value in (("complete_body", False), ("http_status", 403), ("content_type", "text/html"),
                           ("raw_bytes", len(raw)+1), ("raw_sha256", "a"*64),
                           ("final_url", "https://example.invalid/changed")):
            changed = json.loads(metadata)
            changed[key] = value
            with self.subTest(field=key), self.assertRaises(IntegrityError):
                review.normalize_original(raw, canonical(changed), imported_at=IMPORTED)
        for malformed in (b'[{"sport":"nba","sport":"nba"}]', b'[NaN]', b'{}'):
            changed = json.loads(metadata)
            changed.update(raw_bytes=len(malformed), raw_sha256=hashlib.sha256(malformed).hexdigest())
            with self.subTest(raw=malformed), self.assertRaises(IntegrityError):
                review.normalize_original(malformed, canonical(changed), imported_at=IMPORTED)
        excessive = source_row()
        excessive["options"] = [deepcopy(excessive["options"][0]) for _ in range(65)]
        raw, metadata = original([excessive])
        with self.assertRaises(IntegrityError):
            review.normalize_original(raw, metadata, imported_at=IMPORTED)

    def test_interrupted_private_write_recovers_same_input_and_clocks(self):
        for target in ("source.body", "review.json"):
            with self.subTest(interrupted=target):
                raw, metadata = original()
                body, meta = self.files(raw, metadata, name="interrupt-"+target)
                destination = self.root/".local-data"/("interrupted-"+target)
                create = review._create
                def interrupted(directory, name, value, *, maximum):
                    if name == target:
                        raise OSError("invented interrupted write")
                    return create(directory, name, value, maximum=maximum)
                with patch.object(review, "_create", side_effect=interrupted), self.assertRaises(OSError):
                    review.build_preview(destination=destination, source_root=self.root, now=GENERATED,
                                         body=body, metadata=meta)
                intent_before = (destination/"review-intent.receipt.json").read_bytes()
                result = review.build_preview(destination=destination, source_root=self.root,
                                              now=GENERATED+timedelta(days=1), body=body, metadata=meta)
                self.assertTrue(result["recovered_existing_preview"])
                recovered = json.loads((destination/"review.json").read_bytes())
                self.assertEqual(recovered["generated_at"], stamp(GENERATED))
                self.assertEqual(recovered["imported_at"], stamp(GENERATED))
                self.assertEqual(recovered["observed_at"], stamp(OBSERVED))
                self.assertEqual((destination/"review-intent.receipt.json").read_bytes(), intent_before)
                self.assertEqual((destination/"source.body").read_bytes(), raw)

    def test_retries_reject_changed_input_metadata_or_window_without_overwrite(self):
        _, _, destination, body, meta = self.build()
        before = self.inventory(destination)
        raw2, metadata2 = original([source_row(threshold=23.5)])
        other_body, other_meta = self.files(raw2, metadata2, name="changed")
        changed_meta = json.loads(meta.read_bytes())
        changed_meta["request_started_at"] = stamp(OBSERVED-timedelta(seconds=2))
        altered = self.inputs/"other.metadata.json"
        altered.write_bytes(canonical(changed_meta))
        cases = [(other_body, other_meta, 0), (body, altered, 0), (body, meta, 1)]
        for chosen_body, chosen_meta, offset in cases:
            with self.subTest(offset=offset, metadata=chosen_meta.name), self.assertRaises(IntegrityError):
                review.build_preview(destination=destination, source_root=self.root, now=GENERATED+timedelta(days=1),
                                     body=chosen_body, metadata=chosen_meta, offset=offset)
            self.assertEqual(self.inventory(destination), before)

    def test_independent_package_replay_is_read_only_and_rejects_resealed_source_change(self):
        _, body, destination, *_ = self.build()
        before = self.inventory(destination)
        proof = review.verify_package(destination, now=GENERATED+timedelta(days=1))
        self.assertEqual(proof["writes"], 0)
        self.assertEqual(proof["source_http_requests"], 0)
        self.assertTrue(proof["original_http_bytes_recovered"])
        self.assertFalse(proof["durable_remote_archive_verified"])
        self.assertEqual(self.inventory(destination), before)
        changed = deepcopy(body)
        changed["observations"][0]["provider_player_id"] = "a-different-native-player"
        changed = reseal(changed)
        review.validate_review(changed, now=GENERATED)
        (destination/"review.json").write_bytes(canonical(changed))
        envelope = json.loads((destination/"review.receipt.json").read_bytes())
        envelope.update(payload=changed, payload_sha256=digest(changed))
        (destination/"review.receipt.json").write_bytes(canonical(envelope))
        with self.assertRaises(IntegrityError):
            review.verify_package(destination, now=GENERATED)

    def test_public_or_symlinked_output_and_oversized_input_are_rejected(self):
        body, meta = self.files()
        for destination in (self.root/"public", self.root/".local-data", self.root/".local-data-extra"/"preview"):
            with self.subTest(destination=destination), self.assertRaises(IntegrityError):
                review.build_preview(destination=destination, source_root=self.root, now=GENERATED, body=body, metadata=meta)
        (self.root/".local-data").mkdir(exist_ok=True)
        outside = self.root/"outside"
        outside.mkdir()
        (self.root/".local-data"/"link").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(IntegrityError):
            review.build_preview(destination=self.root/".local-data"/"link"/"preview", source_root=self.root,
                                 now=GENERATED, body=body, metadata=meta)
        with patch.object(review, "MAX_INPUT_BYTES", len(body.read_bytes())-1), self.assertRaises(IntegrityError):
            review.build_preview(destination=self.root/".local-data"/"too-large", source_root=self.root,
                                 now=GENERATED, body=body, metadata=meta)

    def test_package_budgets_cover_intent_and_all_retained_files(self):
        body, meta = self.files()
        for limit_kind in ("files", "bytes"):
            destination = self.root/".local-data"/("budget-"+limit_kind)
            destination.mkdir(parents=True)
            (destination/"retained-a").write_bytes(b"12345")
            (destination/"retained-b").write_bytes(b"67890")
            before = self.inventory(destination)
            setting = ("MAX_PACKAGE_FILES", 2) if limit_kind == "files" else ("MAX_PACKAGE_BYTES", 10)
            with self.subTest(limit=limit_kind), patch.object(review, setting[0], setting[1]), self.assertRaises(IntegrityError):
                review.build_preview(destination=destination, source_root=self.root, now=GENERATED,
                                     body=body, metadata=meta)
            self.assertEqual(self.inventory(destination), before)

    def test_huge_decimal_exponents_are_rejected_before_expansion(self):
        for value in ("1e100000000", "1e-100000000", "-1", "NaN", "Infinity"):
            with self.subTest(value=value), self.assertRaises(IntegrityError):
                review._decimal(value)


if __name__ == "__main__":
    unittest.main()

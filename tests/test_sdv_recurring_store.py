"""Synthetic planning receipts; no source collection, models or real issuance."""
import base64
from copy import deepcopy
from datetime import timedelta
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

from multisport_lab import integrity, ledger
from multisport_lab import pregame_sources as historical
from multisport_lab import sdv_daily_store as old_store
from multisport_lab import sdv_recurring_store as recurring
from multisport_lab.integrity import IntegrityError, canonical, digest, read_receipt, stamp, utc
import test_sdv_recurring_plan as plan_fixture
import test_pregame_sources as history_fixture


class RecurringStoreTests(unittest.TestCase):
    def setUp(self):
        self.fixture = plan_fixture.RecurringPlanTests(
            "test_fixed_seven_days_first_two_events_and_eight_subjects_have_no_issuance_authority")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        for module in (recurring, ledger, old_store):
            clock = patch.object(module, "_now", side_effect=lambda: self.fixture.now)
            clock.start(); self.addCleanup(clock.stop)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.parent = ledger.Ledger(self.root)
        self.fixture.now = utc("2026-10-21T10:00:00.000000Z")
        # Existing one-row typed synthetic history fixture; the real 26,645-row
        # panel is neither generated nor evaluated by these tests.
        with patch.object(historical, "_now", return_value=history_fixture.NOW):
            self.history_pack = history_fixture.pack_fixture()
        pin = patch.object(historical, "PANEL_SHA",
            self.history_pack["history_provenance"]["normalized_panel_sha256"])
        pin.start(); self.addCleanup(pin.stop)
        clock = patch.object(historical, "_now", side_effect=lambda: self.fixture.now)
        clock.start(); self.addCleanup(clock.stop)
        self.history = self.parent.append("research_inputs", "research-inputs:" + digest(self.history_pack),
            {"source_pack": self.history_pack})
        history_pin = patch.object(recurring.planning.first, "HISTORY_RECORD_ID", self.history.record_id)
        history_pin.start(); self.addCleanup(history_pin.stop)
        self.fixture.now = utc("2026-10-22T10:00:00.000000Z")
        self.fixture.reservation = recurring.planning.make_reservation()
        self.store = recurring.RecurringStore(self.root)
        self.reservation_ref = self.store.persist_reservation(self.fixture.reservation, self.history)
        self.fixture.now = utc("2026-10-23T13:17:00.000000Z")

    def path(self, ref):
        return self.root / "recurring/records" / ref.kind / (ref.record_id + ".json")

    def assets(self):
        return self.fixture.assets()

    def retain(self, assets=None):
        sr, rr, sm, rm, originals = assets or self.assets()
        return (self.store.retain_source_pack(sr, sm, originals["schedule"]),
                self.store.retain_source_pack(rr, rm, originals["roster"]))

    def plan(self, assets=None):
        assets = assets or self.assets()
        refs = self.retain(assets)
        body = self.fixture.build(assets)
        return self.store.persist_plan(body, refs), body, refs

    def reseal_payload(self, ref, change):
        payload = read_receipt(self.path(ref), max_bytes=recurring.MAX_RECORD_BYTES)
        change(payload)
        self.path(ref).write_bytes(canonical({"schema_version": integrity.RECEIPT_SCHEMA,
            "hash_format": integrity.HASH_FORMAT, "payload_sha256": digest(payload),
            "payload": payload}) + b"\n")

    def test_exact_sources_plan_and_restart_preserve_original_bytes(self):
        old_path = self.root / "records/research_inputs" / (self.history.record_id + ".json")
        original_history = old_path.read_bytes()
        assets = self.assets()
        ref, body, source_refs = self.plan(assets)
        before = {path.relative_to(self.root): path.read_bytes()
                  for path in self.root.rglob("*.json")}
        recovered = recurring.RecurringStore(self.root)
        report = recovered.recover()
        self.assertEqual(report["plans"], [(ref, body)])
        self.assertEqual(body["subject_count"], 8)
        self.assertEqual(body["unique_player_count"], 8)
        self.assertEqual(report["genuine_forecasts"], 0)
        self.assertFalse(report["prospective_admission"])
        self.assertEqual(report["local_persistence_completion"], "NOT_ESTABLISHED_BY_RECEIPT_CLOCK")
        self.assertEqual(recovered.read_source_pack(source_refs[0]),
                         (assets[0], assets[2], assets[4]["schedule"]))
        self.fixture.now += timedelta(days=3)
        self.assertEqual(recovered.persist_plan(body, source_refs), ref)
        self.assertEqual(recovered.retain_source_pack(assets[0], assets[2], assets[4]["schedule"]), source_refs[0])
        self.assertEqual({path.relative_to(self.root): path.read_bytes()
                          for path in self.root.rglob("*.json")}, before)
        self.assertEqual(old_path.read_bytes(), original_history)

    def test_reservation_retains_fixed_pool_and_preserves_first_cycle_reserve(self):
        report = self.store.capacity()
        self.assertEqual(report["maximum_projected_bytes"], 31_431_880 + 2_097_152)
        self.assertEqual(report["maximum_projected_records"], 155 + 64)
        self.assertEqual(report["maximum_bytes"] - report["maximum_projected_bytes"], 25_400)
        self.assertTrue(report["fits"])
        payload = self.store.ledger.read(self.reservation_ref)
        self.assertEqual(payload["data"]["retention_budget"]["scope"], "PLANNING_ONLY_SHARED_POOL")
        self.assertEqual(payload["data"]["history_ref"], self.history.to_record())

    def test_consumed_pool_bytes_are_credited_once_including_interrupted_files(self):
        before = self.store.capacity()
        refs = self.retain()
        after = self.store.capacity()
        self.assertGreater(after["planning_bytes"], before["planning_bytes"])
        self.assertEqual(after["maximum_projected_bytes"], before["maximum_projected_bytes"])
        self.assertEqual(after["planning_bytes"] + after["remaining_bytes"], 2_097_152)
        directory = self.path(refs[0]).parent
        interrupted = directory / ".receipt-interrupted"
        interrupted.write_bytes(b"actual interrupted bytes")
        partial = self.store.recover()
        self.assertEqual(len(partial["source_packs"]), 2)
        self.assertEqual(partial["capacity"]["planning_records"], after["planning_records"] + 1)
        self.assertEqual(partial["capacity"]["remaining_bytes"],
                         after["remaining_bytes"] - interrupted.stat().st_size)

    def test_changed_source_clock_never_overwrites_or_refreshes_first_capture(self):
        assets = self.assets()
        ref = self.store.retain_source_pack(assets[0], assets[2], assets[4]["schedule"])
        original = self.path(ref).read_bytes()
        metadata = deepcopy(assets[2])
        metadata["retrieval_started_at"] = stamp(self.fixture.now)
        metadata["retrieved_at"] = stamp(self.fixture.now)
        with self.assertRaisesRegex(IntegrityError, "conflicting logical record"):
            self.store.retain_source_pack(assets[0], metadata, assets[4]["schedule"])
        self.assertEqual(self.path(ref).read_bytes(), original)
        self.assertEqual(self.store.read_source_pack(ref)[1], assets[2])

    def test_actual_csv_release_and_identity_are_cross_checked(self):
        sr, _, sm, _, originals = self.assets()
        for mutate in (lambda value: value.update(asset_id=999),
                       lambda value: value.update(asset_sha256="0" * 64),
                       lambda value: value.update(asset_url=value["asset_url"] + "?other=1"),
                       lambda value: value.update(upstream_observed_at=value["publisher_updated_at"]),
                       lambda value: value.update(retrieved_at=stamp(self.fixture.now + timedelta(seconds=1)))):
            changed = deepcopy(sm); mutate(changed)
            with self.subTest(changed=changed), self.assertRaises(IntegrityError):
                self.store.retain_source_pack(sr, changed, originals["schedule"])
        with self.assertRaises(IntegrityError):
            self.store.retain_source_pack(sr + b"changed", sm, originals["schedule"])
        with self.assertRaises(IntegrityError):
            self.store.retain_source_pack(sr, sm, originals["schedule"] + b" ")

    def test_missing_wrong_hash_and_swapped_source_references_are_rejected(self):
        assets = self.assets(); refs = self.retain(assets); body = self.fixture.build(assets)
        bad = ledger.LedgerRef(refs[0].kind, refs[0].record_id, "0" * 64)
        for changed in ((bad, refs[1]), (refs[1], refs[0]), (refs[0], self.reservation_ref)):
            with self.subTest(changed=changed), self.assertRaises(IntegrityError):
                self.store.persist_plan(body, changed)

    def test_semantically_changed_resealed_plan_cannot_replace_original(self):
        assets = self.assets(); refs = self.retain(assets); body = self.fixture.build(assets)
        changed = deepcopy(body)
        changed["source_schedule_rows"] += 1
        changed["outside_game_date_rows"] += 1
        changed = recurring.planning._seal({k: v for k, v in changed.items() if k != "plan_id"}, "plan_id")
        recurring.planning.validate_plan(changed)
        with self.assertRaisesRegex(IntegrityError, "exact original source replay"):
            self.store.persist_plan(changed, refs)
        ref = self.store.persist_plan(body, refs)
        self.assertEqual(len(self.store.recover()["plans"]), 1)
        self.assertEqual(self.store.persist_plan(body, refs), ref)

    def test_valid_receipt_checksum_cannot_hide_invalid_source_meaning(self):
        assets = self.assets()
        ref = self.store.retain_source_pack(assets[0], assets[2], assets[4]["schedule"])
        def change(payload):
            body = payload["data"]["sdv_recurring"]
            release = integrity._decode(assets[4]["schedule"])
            release["assets"][0]["id"] = 999
            raw = canonical(release)
            body["metadata_raw_base64"] = base64.b64encode(zlib.compress(raw, 9)).decode()
            body["metadata_raw_bytes"] = len(raw)
            body["metadata_raw_sha256"] = hashlib.sha256(raw).hexdigest()
            body["metadata"].update(metadata_bytes=len(raw), metadata_sha256=hashlib.sha256(raw).hexdigest())
            body["asset_id"] = digest({k: v for k, v in body.items() if k != "asset_id"})
        self.reseal_payload(ref, change)
        with self.assertRaisesRegex(IntegrityError, "asset ID is absent"):
            recurring.RecurringStore(self.root).recover()

    def test_bad_budget_unknown_wrapper_and_hidden_forecasts_fail_closed(self):
        def bad_budget(payload):
            payload["data"]["retention_budget"]["maximum_encoded_bytes"] += 1
        self.reseal_payload(self.reservation_ref, bad_budget)
        with self.assertRaisesRegex(IntegrityError, "budget changed"):
            self.store.recover()
        # A fresh generic namespace cannot turn an invented forecast into a
        # supported body merely by using a valid generic receipt envelope.
        with tempfile.TemporaryDirectory() as other:
            hidden = recurring.RecurringStore(other)
            hidden.ledger.append("forecasts", "hidden", {"identity": {}, "sdv_recurring": {
                "schema_version": "nba-sdv-daily-forecast-v1", "protocol_id": recurring.PROTOCOL_ID}})
            with self.assertRaisesRegex(IntegrityError, "only reservation, source pack and plan"):
                hidden.recover()

    def test_missing_and_modified_parent_history_are_not_trusted_from_hash_alone(self):
        parent_path = self.root / "records/research_inputs" / (self.history.record_id + ".json")
        exact = parent_path.read_bytes()
        parent_path.unlink()
        with self.assertRaises(IntegrityError): self.store.recover()
        parent_path.write_bytes(exact)
        payload = read_receipt(parent_path)
        # A validly checksummed replacement still differs from the exact parent
        # reference retained with the reservation.
        payload["received_at"] = stamp(utc(payload["received_at"]) + timedelta(seconds=1))
        parent_path.write_bytes(canonical({"schema_version": integrity.RECEIPT_SCHEMA,
            "hash_format": integrity.HASH_FORMAT, "payload_sha256": digest(payload), "payload": payload}) + b"\n")
        with self.assertRaisesRegex(IntegrityError, "hash mismatch"):
            recurring.RecurringStore(self.root).recover()

    def test_stale_originals_cannot_become_valid_by_retrieving_again(self):
        assets = self.fixture.assets(publisher_age=timedelta(hours=36, seconds=1))
        self.retain(assets)
        with self.assertRaisesRegex(IntegrityError, "asset is stale"):
            self.fixture.build(assets)
        self.assertEqual(self.store.recover()["genuine_forecasts"], 0)

    def test_interruption_after_publication_recovers_original_without_new_clock(self):
        sr, _, sm, _, originals = self.assets()
        write = ledger.write_receipt
        def interrupted(*args, **kwargs):
            write(*args, **kwargs)
            raise KeyboardInterrupt("synthetic interruption after atomic publication")
        with patch.object(ledger, "write_receipt", side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            self.store.retain_source_pack(sr, sm, originals["schedule"])
        recovered = recurring.RecurringStore(self.root)
        sources = recovered.recover()["source_packs"]
        self.assertEqual(len(sources), 1)
        ref = sources[0][0]; exact = self.path(ref).read_bytes()
        self.fixture.now += timedelta(seconds=5)
        self.assertEqual(recovered.retain_source_pack(sr, sm, originals["schedule"]), ref)
        self.assertEqual(self.path(ref).read_bytes(), exact)

    def test_delayed_write_never_claims_timely_completion_from_receipt_clock(self):
        assets = self.assets(); refs = self.retain(assets); body = self.fixture.build(assets)
        write = ledger.write_receipt
        def delayed(*args, **kwargs):
            self.fixture.now += timedelta(hours=1)
            return write(*args, **kwargs)
        with patch.object(ledger, "write_receipt", side_effect=delayed):
            ref = self.store.persist_plan(body, refs)
        receipt = self.store.ledger.read(ref)
        self.assertLess(utc(receipt["received_at"]), utc(body["planning_closes_at"]))
        self.assertGreater(self.fixture.now, utc(body["planning_closes_at"]))
        recovered = recurring.RecurringStore(self.root).recover()
        self.assertEqual(recovered["plans"], [(ref, body)])
        self.assertEqual(recovered["local_persistence_completion"], "NOT_ESTABLISHED_BY_RECEIPT_CLOCK")
        self.assertFalse(recovered["prospective_admission"])
        self.assertEqual(recovered["genuine_forecasts"], 0)

    def test_pool_rejects_complete_incompressible_source_without_truncation(self):
        raw = os.urandom(recurring.MAX_SOURCE_BYTES)
        # The raw is deliberately not a CSV. Retention only stores original
        # evidence; even a small retained body would still need CSV replay to
        # become a valid plan. This incompressible original exceeds the pool.
        tag = "espn_nba_schedules"; name = "nba_schedule_2027.csv"
        source = self.assets()[2]
        original = canonical({"tag_name": tag, "assets": [{"id": source["asset_id"],
            "name": name, "size": len(raw), "browser_download_url": source["asset_url"],
            "digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "updated_at": source["publisher_updated_at"]}]})
        metadata = recurring.planning.source_metadata(raw, original, source,
            retrieval_started_at=source["retrieval_started_at"], retrieved_at=source["retrieved_at"])
        before = self.store.capacity()
        with self.assertRaisesRegex(IntegrityError, "budget is exhausted"):
            self.store.retain_source_pack(raw, metadata, original)
        self.assertEqual(self.store.capacity()["planning_bytes"], before["planning_bytes"])
        with self.assertRaisesRegex(IntegrityError, "2-MiB"):
            self.store.retain_source_pack(raw + b"x", metadata, original)

    def test_actual_original_namespace_growth_cannot_consume_protected_reserve_twice(self):
        # Each bounded file and the aggregate fit the generic inventory. Their
        # actual size exceeds the protected floor, so the additional pool must
        # fail against the unchanged global cap before any new source write.
        folder = self.root / "daily/records/research_inputs"
        folder.mkdir(parents=True)
        content = b" " * (recurring.MAX_RECORD_BYTES - 4096)
        for index in range(8):
            (folder / (format(index + 1, "064x") + ".json")).write_bytes(content)
        report = self.store.capacity()
        self.assertFalse(report["fits"])
        self.assertGreater(report["maximum_projected_bytes"], recurring.MAX_LEDGER_BYTES)
        with self.assertRaisesRegex(IntegrityError, "budget is exhausted"):
            self.store.recover()

    def test_late_reservation_and_symlink_inventories_are_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            other = Path(other)
            (other / "records").symlink_to(self.root / "records", target_is_directory=True)
            with self.assertRaisesRegex(IntegrityError, "symlink"):
                recurring.RecurringStore(other).capacity()
        with tempfile.TemporaryDirectory() as other:
            other = Path(other)
            old = ledger.Ledger(other)
            self.fixture.now = utc("2026-10-21T10:00:00.000000Z")
            history = old.append("research_inputs", "research-inputs:" + digest(self.history_pack),
                {"source_pack": self.history_pack})
            self.fixture.now = utc("2026-10-23T13:17:00.000000Z")
            with self.assertRaisesRegex(IntegrityError, "before planning opens"):
                recurring.RecurringStore(other).persist_reservation(self.fixture.reservation, history)

    def test_ledger_documentation_remains_allowed_and_unmodified(self):
        notice = self.root / "records/README.md"
        notice.write_bytes(b"Existing project ledger instructions\n")
        self.assertTrue(self.store.recover()["capacity"]["fits"])
        self.assertEqual(notice.read_bytes(), b"Existing project ledger instructions\n")


if __name__ == "__main__":
    unittest.main()

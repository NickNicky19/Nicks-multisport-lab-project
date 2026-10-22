"""Checksum-consistent invented attempt evidence; no authority or model execution."""
from copy import deepcopy
from datetime import timedelta
import unittest

from multisport_lab import sdv_production_archive as archives
from multisport_lab import sdv_production_common as common
from multisport_lab import sdv_production_runner as runner
from multisport_lab import sdv_production_store as production
from multisport_lab.integrity import IntegrityError,digest,stamp
import test_sdv_production_store as fixture


class ProductionIssueStatusTests(unittest.TestCase):
    def setUp(self):
        self.case=fixture.ProductionStoreTests("test_independent_archive_restart_keeps_exact_originals_and_all14_categories")
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.store=self.case.store

    def opening(self,number=1):
        details={"task_id":"a"*64,"shard_index":0,"player_ids":self.case.input["shards"][0],
            "error":None,"final_source_pack_ref":None,"processing_complete":False}
        attempt={"attempt_number":number,"run_attempt":1,"opened_at":stamp(self.case.fixture.now),
            "open_status_id":None,"footprint_snapshot_ref":None,"footprint_snapshot_id":None,"footprint_recovered_at":None}
        attempt["attempt_id"]=digest({key:details[key] for key in ("task_id","shard_index","player_ids")}|{
            "run_id":123,**{key:attempt[key] for key in ("run_attempt","opened_at","attempt_number")}})
        details["issuance_attempt"]=attempt
        return common.seal({"schema_version":common.STATUS_SCHEMA,"protocol_id":common.PROTOCOL_ID,
            "plan_id":self.case.input["plan_id"],"cycle_id":self.case.input["cycle_id"],"phase":"ISSUE",
            "status":runner.ISSUE_OPEN,"details":details,"observed_at":attempt["opened_at"],"run_id":123},"status_id")

    def snapshot(self):return archives.archive_snapshot(self.store,self.case.archive,tag=fixture.TAG)

    def closing(self,opened,snapshot=None):
        snapshot=snapshot or self.snapshot();manifest=self.case.archive.get_json(snapshot)["ledger_snapshot"]
        body=deepcopy(opened);body["status"]=runner.ISSUE_CLOSED;body["observed_at"]=stamp(self.case.fixture.now)
        body["details"]["issuance_attempt"].update(open_status_id=opened["status_id"],
            footprint_snapshot_ref=snapshot,footprint_snapshot_id=manifest["snapshot_id"],
            footprint_recovered_at=stamp(self.case.fixture.now))
        return self.reseal(body)

    def reseal(self,body):return common.seal({key:value for key,value in body.items() if key != "status_id"},"status_id")

    def append_closed(self,body):
        attempt=body["details"]["issuance_attempt"]
        # Explicit synthetic stand-in for the private coordinator capability;
        # no hosted writer or actual issuance is represented by this fixture.
        with self.store._verified_issue_closure(body,attempt["footprint_snapshot_ref"],attempt["footprint_recovered_at"]):
            return self.store.append_body(body)

    def append_raw(self,body):
        # Bypass new-write admission deliberately: Ledger still produces valid
        # original receipt hashes. Recovery must reject invalid typed meaning.
        return self.store.ledger.append(common.KINDS[common.STATUS_SCHEMA],production._logical(body),
            {"identity":production._identity(body),"production":body,"archive_refs":[]})

    def test_valid_closure_is_exact_and_later_statuses_do_not_rewrite_its_footprint(self):
        opened=self.opening();self.store.append_body(opened)
        originals,bodies=self.case.persisted_pair(ack=False)
        closed=self.closing(opened);self.append_closed(closed)
        later=deepcopy(opened);later["status"]="LATER_PENDING_OUTCOME";later["phase"]="GRADE"
        later["details"].pop("issuance_attempt");self.store.append_body(self.reseal(later))
        recovered=self.case.new_store().recover()
        self.assertEqual(len(recovered["forecasts"]),2)
        self.assertEqual([self.store.read_body(ref) for ref in originals],bodies)

    def test_known_open_and_snapshot_do_not_mint_a_fresh_writer_closure_capability(self):
        opened=self.opening();self.store.append_body(opened);closed=self.closing(opened)
        before=self.store.snapshot_manifest()
        with self.assertRaisesRegex(IntegrityError,"owned attempt"):
            self.case.new_store().append_body(closed)
        self.assertEqual(self.store.snapshot_manifest(),before)

    def test_missing_open_rejected_before_write_and_with_valid_receipt_hash_on_restart(self):
        closed=self.closing(self.opening());before=self.store.snapshot_manifest()
        with self.assertRaisesRegex(IntegrityError,"retained OPEN"):
            self.append_closed(closed)
        self.assertEqual(self.store.snapshot_manifest(),before)
        ref=self.append_raw(closed);self.store.ledger.read(ref)
        with self.assertRaisesRegex(IntegrityError,"retained OPEN"):
            self.case.new_store().recover()

    def test_changed_task_and_resealed_attempt_identity_rejected_on_readback(self):
        opened=self.opening();self.store.append_body(opened);closed=self.closing(opened)
        closed["details"]["task_id"]="b"*64
        attempt=closed["details"]["issuance_attempt"]
        attempt["attempt_id"]=digest({key:closed["details"][key] for key in ("task_id","shard_index","player_ids")}|{
            "run_id":closed["run_id"],**{key:attempt[key] for key in ("run_attempt","opened_at","attempt_number")}})
        closed=self.reseal(closed);runner.validate_body(closed)
        self.append_raw(closed)
        with self.assertRaisesRegex(IntegrityError,"task identity"):
            self.case.new_store().recover()

    def test_stale_open_only_footprint_cannot_hide_retained_originals(self):
        opened=self.opening();self.store.append_body(opened);stale=self.snapshot()
        self.case.persisted_pair(ack=False);closed=self.closing(opened,stale)
        before=self.store.snapshot_manifest()
        with self.assertRaisesRegex(IntegrityError,"omits a retained original"):
            self.append_closed(closed)
        self.assertEqual(self.store.snapshot_manifest(),before)
        self.append_raw(closed)
        with self.assertRaisesRegex(IntegrityError,"omits a retained original"):
            self.case.new_store().recover()

    def test_wrong_snapshot_identity_and_valid_checksums_rejected(self):
        opened=self.opening();self.store.append_body(opened);closed=self.closing(opened)
        closed["details"]["issuance_attempt"]["footprint_snapshot_id"]="f"*64
        closed=self.reseal(closed);runner.validate_body(closed);self.append_raw(closed)
        with self.assertRaisesRegex(IntegrityError,"snapshot identity"):
            self.case.new_store().recover()

    def test_resealed_snapshot_cannot_change_exact_original_receipt_hash(self):
        opened=self.opening();self.store.append_body(opened);closed=self.closing(opened)
        attempt=closed["details"]["issuance_attempt"]
        transport=deepcopy(self.case.archive.get_json(attempt["footprint_snapshot_ref"]))
        snapshot=transport["ledger_snapshot"];snapshot["entries"][0]["sha256"]="f"*64
        snapshot=common.seal({key:value for key,value in snapshot.items() if key != "snapshot_id"},"snapshot_id")
        transport["ledger_snapshot"]=snapshot
        transport=common.seal({key:value for key,value in transport.items() if key != "archive_snapshot_id"},"archive_snapshot_id")
        attempt.update(footprint_snapshot_ref=self.case.archive.put_json(transport,tag=fixture.TAG),
            footprint_snapshot_id=snapshot["snapshot_id"])
        closed=self.reseal(closed);runner.validate_body(closed);self.append_raw(closed)
        with self.assertRaisesRegex(IntegrityError,"original bytes"):
            self.case.new_store().recover()

    def test_duplicate_closure_rejected_and_original_footprint_preserved(self):
        opened=self.opening();self.store.append_body(opened);first=self.closing(opened);self.append_closed(first)
        second=self.closing(opened);second["details"]["error"]="Invented duplicate closure";second=self.reseal(second)
        before=self.store.snapshot_manifest()
        with self.assertRaisesRegex(IntegrityError,"unique retained OPEN"):
            self.append_closed(second)
        self.assertEqual(self.store.snapshot_manifest(),before)
        self.append_raw(second)
        with self.assertRaisesRegex(IntegrityError,"unique retained OPEN"):
            self.case.new_store().recover()

    def test_skipped_ordinals_and_unresolved_open_block_another_attempt(self):
        with self.assertRaisesRegex(IntegrityError,"ordinals"):
            self.store.append_body(self.opening(2))
        self.store.append_body(self.opening())
        with self.assertRaisesRegex(IntegrityError,"unresolved OPEN"):
            self.store.append_body(self.opening(2))

    def test_resealed_closure_with_clock_before_footprint_rejected_on_restart(self):
        opened=self.opening();self.store.append_body(opened);closed=self.closing(opened)
        closed["observed_at"]=stamp(self.case.fixture.now-timedelta(microseconds=1))
        closed=self.reseal(closed);self.append_raw(closed)
        with self.assertRaises(IntegrityError):self.case.new_store().recover()


if __name__ == "__main__":unittest.main()

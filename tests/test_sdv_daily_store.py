"""Bounded storage and post-write admission checks; all clocks/data synthetic."""
from copy import deepcopy
from datetime import timedelta
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib
import base64

from multisport_lab import sdv_daily_inputs as inputs
from multisport_lab import sdv_daily_store as daily
from multisport_lab import ledger
from multisport_lab.integrity import IntegrityError, canonical, digest, stamp, read_receipt
from test_sdv_daily_inputs import fixtures, csv_bytes, metadata


def original(raw, role, at):
    meta=metadata(raw,role,at)
    release={"tag_name":meta["release_tag"],"assets":[{
        "id":meta["asset_id"],"name":meta["asset_name"],"size":len(raw),
        "browser_download_url":meta["asset_url"],"digest":"sha256:"+meta["asset_sha256"],
        "updated_at":meta["publisher_updated_at"]}]}
    metadata_raw=canonical(release)
    meta.update(metadata_sha256=hashlib.sha256(metadata_raw).hexdigest(),metadata_bytes=len(metadata_raw))
    return meta,metadata_raw


class DailyStorageTests(unittest.TestCase):
    def setUp(self):
        self.start,self.at,self.schedule,self.roster,self.expected=fixtures()
        self.current=self.at
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for module in (daily,inputs,ledger):
            clock=patch.object(module,"_now",side_effect=lambda:self.current)
            clock.start();self.addCleanup(clock.stop)
        self.store=daily.DailyStore(self.root)

    def source(self, role="schedule"):
        raw=csv_bytes(self.schedule if role == "schedule" else self.roster)
        meta,metadata_raw=original(raw,role,self.at)
        return raw,meta,metadata_raw

    def persist_inputs(self,mode="DEVELOPMENT_ONLY"):
        sources=[self.source(role) for role in ("schedule","roster")]
        refs=[self.store.retain_asset(*row) for row in sources]
        body=inputs.normalize_inputs(sources[0][0],sources[1][0],sources[0][1],sources[1][1],
            event_id="900",expected_candidates=self.expected,mode=mode,
            normalized_at=self.at if mode == "DEVELOPMENT_ONLY" else None)
        return self.store.persist_input(body,refs),body,refs

    def test_exact_originals_idempotent_restart_and_parent_ledger_unchanged(self):
        parent=ledger.Ledger(self.root)
        old=parent.append("input_captures","prior",{"identity":{"legacy":"kept"}})
        old_bytes=parent._path(old.kind,old.record_id).read_bytes()
        raw,meta,metadata_raw=self.source()
        first=self.store.retain_asset(raw,meta,metadata_raw)
        exact=self.store.ledger._path(first.kind,first.record_id).read_bytes()
        self.current+=timedelta(seconds=2)
        self.assertEqual(self.store.retain_asset(raw,meta,metadata_raw),first)
        recovered=daily.DailyStore(self.root)
        self.assertEqual(recovered.read_asset(first),(raw,meta,metadata_raw))
        self.assertEqual(recovered.ledger._path(first.kind,first.record_id).read_bytes(),exact)
        self.assertEqual(parent._path(old.kind,old.record_id).read_bytes(),old_bytes)
        self.assertEqual(recovered.capacity()["existing_records"],2)
        self.assertEqual(recovered.recover()["genuine_issued"],0)

    def test_exact_input_replays_original_csv_and_cannot_invent_changed_candidate(self):
        ref,body,assets=self.persist_inputs()
        recovered=daily.DailyStore(self.root)
        self.assertEqual(recovered.ledger.read(ref)["data"]["daily"],body)
        bad=deepcopy(body);bad["candidates"][0]["player_label"]="Invented name"
        bad["input_id"]=digest({k:v for k,v in bad.items() if k != "input_id"})
        with self.assertRaisesRegex(IntegrityError,"cohort changed|normalization"):
            self.store.persist_input(bad,assets)

    def test_publisher_identity_bytes_and_release_metadata_are_cross_checked(self):
        raw,meta,metadata_raw=self.source()
        cases=[]
        for key,value in (("asset_id",999),("asset_sha256","0"*64),
                ("asset_url",meta["asset_url"]+"?alternate=1"),
                ("publisher_updated_at",stamp(self.at+timedelta(seconds=1)))):
            changed=deepcopy(meta);changed[key]=value;cases.append(changed)
        for changed in cases:
            with self.subTest(changed=changed),self.assertRaises(IntegrityError):
                self.store.retain_asset(raw,changed,metadata_raw)
        with self.assertRaises(IntegrityError):
            self.store.retain_asset(raw+b"changed",meta,metadata_raw)
        with self.assertRaises(IntegrityError):
            self.store.retain_asset(raw,meta,metadata_raw+b" ")

    def test_source_limits_and_bounded_decompression_reject_before_truncation(self):
        with self.assertRaises(IntegrityError):daily._encode(b"x"*(daily.MAX_SOURCE_BYTES+1))
        bomb=b"x"*(daily.MAX_SOURCE_BYTES+1)
        encoded=base64.b64encode(zlib.compress(bomb)).decode()
        with self.assertRaises(IntegrityError):daily._decode_source(encoded,len(bomb),hashlib.sha256(bomb).hexdigest())
        raw=b"abc"
        encoded=base64.b64encode(zlib.compress(raw)+b"trailing").decode()
        with self.assertRaises(IntegrityError):daily._decode_source(encoded,len(raw),hashlib.sha256(raw).hexdigest())

    def test_valid_receipt_checksum_does_not_excuse_invalid_original_meaning(self):
        ref=self.store.retain_asset(*self.source())
        payload=self.store.ledger.read(ref)
        payload["data"]["daily"]["metadata"]["asset_id"]=999
        body=payload["data"]["daily"]
        body["asset_id"]=digest({k:v for k,v in body.items() if k != "asset_id"})
        path=self.store.ledger._path(ref.kind,ref.record_id)
        envelope={"schema_version":daily.RECEIPT_SCHEMA,"hash_format":daily.HASH_FORMAT,
                  "payload_sha256":digest(payload),"payload":payload}
        path.write_bytes(canonical(envelope)+b"\n")
        with self.assertRaises(IntegrityError):daily.DailyStore(self.root).recover()

    def test_combined_original_and_daily_record_budget_and_capacity_are_bounded(self):
        ledger.Ledger(self.root).append("input_captures","old",{"identity":{"legacy":"kept"}})
        self.store.retain_asset(*self.source())
        with patch.object(daily,"MAX_LEDGER_RECORDS",2),self.assertRaisesRegex(IntegrityError,"budget"):
            self.store.retain_asset(*self.source("roster"))
        report=self.store.capacity(planned_forecasts=8)
        self.assertEqual(report["existing_records"],2)
        self.assertLessEqual(report["existing_records"]+report["reserved_records"],512)
        self.assertLessEqual(report["existing_bytes"]+report["reserved_bytes"],32*1024*1024)
        self.assertEqual(report["slots"]["forecast_completions"]["records"],24)
        self.assertEqual(report["slots"]["intent_completions"]["records"],3)
        self.assertTrue(report["fits"])

    def test_completion_time_is_after_actual_write_and_retry_keeps_original(self):
        ref,body,_=self.persist_inputs()
        self.current+=timedelta(seconds=121)
        completion=self.store.record_completion(ref,started_at=self.at)
        first_bytes=self.store.ledger._path(completion.kind,completion.record_id).read_bytes()
        stored=self.store.ledger.read(completion)["data"]["daily"]
        self.assertEqual(stored["completed_at"],stamp(self.current))
        self.current+=timedelta(seconds=99)
        self.assertEqual(self.store.record_completion(ref,started_at=self.at),completion)
        self.assertEqual(first_bytes,self.store.ledger._path(completion.kind,completion.record_id).read_bytes())
        status=daily.DailyStore(self.root).admission(ref)
        self.assertFalse(status["eligible"])
        self.assertIn("REMOTE_CHECKPOINT_UNACKNOWLEDGED",status["reasons"])
        self.assertIn("FINAL_RECOVERY_UNACKNOWLEDGED",status["reasons"])

    def test_input_late_completion_is_preserved_and_never_admitted_after_restart(self):
        ref,body,_=self.persist_inputs()
        cutoff=self.start-timedelta(minutes=90)
        self.current=cutoff+timedelta(seconds=1)
        for stage in ("LOCAL_PERSISTENCE","REMOTE_CHECKPOINT","FINAL_RECOVERY"):
            self.store.record_completion(ref,started_at=self.at,stage=stage,
                remote_commit=None if stage == "LOCAL_PERSISTENCE" else "a"*40)
        recovered=daily.DailyStore(self.root).admission(ref)
        self.assertFalse(recovered["eligible"])
        self.assertIn("INPUT_PERSISTENCE_OR_RECOVERY_AFTER_CUTOFF",recovered["reasons"])

    def test_completion_cannot_precede_retained_receipt_or_change_operation_identity(self):
        ref,_,_=self.persist_inputs()
        with self.assertRaises(IntegrityError):
            self.store.record_completion(ref,started_at=self.at-timedelta(seconds=5),completed_at=self.at-timedelta(seconds=1))
        saved=self.store.record_completion(ref,started_at=self.at)
        with self.assertRaisesRegex(IntegrityError,"changed its original operation"):
            self.store.record_completion(ref,started_at=self.at-timedelta(seconds=1))
        self.assertEqual(len([b for _,b in self.store.records() if b["schema_version"] == daily.COMPLETION_SCHEMA]),1)
        self.assertEqual(saved.kind,"input_captures")

    def synthetic_admission(self,*,local_seconds=5,remote_seconds=10,final_seconds=15,
                            include_input_acks=True,publisher_boundary=False,include_intent_acks=True):
        # Test only the completion/admission calculation. These are ephemeral
        # dictionaries, never ledger writes or genuinely issued forecasts.
        ref,input_body,_=self.persist_inputs(mode="PROSPECTIVE_RESEARCH")
        cutoff=self.start-timedelta(minutes=90)
        if publisher_boundary:
            input_body=deepcopy(input_body)
            input_body["sources"][0]["publisher_updated_at"]=stamp(cutoff-timedelta(hours=36)+timedelta(seconds=60))
        forecast_ref=ledger.LedgerRef("forecasts",digest("synthetic forecast"),digest("synthetic payload"))
        forecast={"schema_version":"nba-sdv-daily-forecast-v1","mode":"PROSPECTIVE_RESEARCH",
            "input_ref":ref.to_record(),"generation_started_at":stamp(cutoff),"event_starts_at":stamp(self.start)}
        intent_ref=ledger.LedgerRef("input_captures",digest("synthetic intent"),digest("synthetic intent payload"))
        intent={"schema_version":"nba-sdv-daily-intent-v1","mode":"PROSPECTIVE_RESEARCH","input_ref":ref.to_record()}
        records=[(ref,input_body),(forecast_ref,forecast),(intent_ref,intent)]
        def add(target,stage,at):
            body={"schema_version":daily.COMPLETION_SCHEMA,"reference":target.to_record(),
                "stage":stage,"completed_at":stamp(at),"remote_commit":None if stage == "LOCAL_PERSISTENCE" else "a"*40}
            records.append((ledger.LedgerRef("input_captures",digest([target.record_id,stage]),digest(body)),body))
        if include_input_acks:
            for stage in ("LOCAL_PERSISTENCE","REMOTE_CHECKPOINT","FINAL_RECOVERY"):add(ref,stage,self.at)
        if include_intent_acks:
            for stage in ("LOCAL_PERSISTENCE","REMOTE_CHECKPOINT","FINAL_RECOVERY"):add(intent_ref,stage,self.at)
        for stage,seconds in (("LOCAL_PERSISTENCE",local_seconds),("REMOTE_CHECKPOINT",remote_seconds),("FINAL_RECOVERY",final_seconds)):
            if seconds is not None:add(forecast_ref,stage,cutoff+timedelta(seconds=seconds))
        envelope={"references":[ref.to_record(),intent_ref.to_record()]}
        with patch.object(self.store.ledger,"read",return_value=envelope):
            return self.store._admission(forecast_ref,records)

    def test_delayed_original_and_readback_never_admit_after_restart_calculation(self):
        timely=self.synthetic_admission()
        self.assertTrue(timely["eligible"])
        # Pre-write would have been T90+299. Actual completion T90+301
        # exceeds this separate protocol's registered 300-second latency.
        late=self.synthetic_admission(local_seconds=301,remote_seconds=302,final_seconds=303)
        self.assertFalse(late["eligible"])
        self.assertIn("LOCAL_PERSISTENCE_LATE",late["reasons"])
        unacked=self.synthetic_admission(remote_seconds=None,final_seconds=None)
        self.assertFalse(unacked["eligible"])
        self.assertIn("FINAL_RECOVERY_UNACKNOWLEDGED",unacked["reasons"])
        missing_input=self.synthetic_admission(include_input_acks=False)
        self.assertFalse(missing_input["eligible"])
        self.assertIn("INPUT_LOCAL_PERSISTENCE_UNACKNOWLEDGED",missing_input["reasons"])
        missing_intent=self.synthetic_admission(include_intent_acks=False)
        self.assertFalse(missing_intent["eligible"])
        self.assertIn("INTENT_FINAL_RECOVERY_UNACKNOWLEDGED",missing_intent["reasons"])

    def test_original_fresh_at_generation_can_expire_before_final_remote_readback(self):
        status=self.synthetic_admission(final_seconds=61,publisher_boundary=True)
        self.assertFalse(status["eligible"])
        self.assertIn("INPUT_FRESHNESS_FAILED_AT_FINAL_RECOVERY",status["reasons"])

    def test_prospective_completion_cannot_accept_caller_time_and_recovery_replays_genuine_input(self):
        ref,body,_=self.persist_inputs(mode="PROSPECTIVE_RESEARCH")
        self.assertEqual(daily.DailyStore(self.root).ledger.read(ref)["data"]["daily"],body)
        with self.assertRaisesRegex(IntegrityError,"caller-supplied clock"):
            self.store.record_completion(ref,started_at=self.at,completed_at=self.at)
        self.assertFalse(daily.DailyStore(self.root).admission(ref)["eligible"])
        before=self.store.ledger._path(ref.kind,ref.record_id).read_bytes()
        with self.assertRaisesRegex(IntegrityError,"actual checkpoint writer proof"):
            self.store.record_completion(ref,started_at=self.at,stage="REMOTE_CHECKPOINT",remote_commit="a"*40)
        body=daily._sealed({"schema_version":daily.COMPLETION_SCHEMA,"protocol_id":daily.PROTOCOL_ID,
            "stage":"LOCAL_PERSISTENCE","reference":ref.to_record(),"operation_started_at":stamp(self.at),
            "completed_at":stamp(self.at),"remote_commit":None},"completion_id")
        with self.assertRaisesRegex(IntegrityError,"post-action clock capture"):
            self.store.append_body("input_captures",body,references=(ref,))
        self.assertEqual(before,self.store.ledger._path(ref.kind,ref.record_id).read_bytes())
        self.assertFalse([b for _,b in self.store.records() if b["schema_version"] == daily.COMPLETION_SCHEMA])

    def test_new_genuine_forecast_cannot_bypass_producer_and_encoded_ceiling(self):
        body={"schema_version":"nba-sdv-daily-forecast-v1","mode":"PROSPECTIVE_RESEARCH"}
        with self.assertRaisesRegex(IntegrityError,"verified producer"):
            self.store.ledger.append("forecasts","unverified",{"daily":body})
        payload={"kind":"forecasts","data":{"daily":{"schema_version":"nba-sdv-daily-forecast-v1",
                 "padding":"x"*65536}}}
        with self.assertRaisesRegex(IntegrityError,"individual envelope ceiling"):
            self.store.ledger._check_append_budget(payload)

    def test_typed_recovery_requires_exact_retained_parent_history_bytes(self):
        missing=ledger.LedgerRef("research_inputs",digest("missing history"),digest("missing original"))
        for schema in ("nba-sdv-daily-intent-v1","nba-sdv-daily-forecast-v1"):
            payload={"kind":"input_captures","data":{"daily":{"schema_version":schema,
                     "history_ref":missing.to_record()}},"references":[]}
            with self.subTest(schema=schema),self.assertRaisesRegex(IntegrityError,"parent history"):
                self.store.ledger._validate_typed_references(payload)

    def test_outcome_originals_are_exact_and_dont_grant_source_admission(self):
        raw=b'{"synthetic":"final boxscore"}'
        meta={"source_kind":"SYNTHETIC_TEST","source_url":"https://example.invalid/final",
            "source_observed_at":stamp(self.at),"retrieval_started_at":stamp(self.at),
            "retrieved_at":stamp(self.at),"content_type":"application/json",
            "source_use_basis":"development fixture; not a source allowance"}
        ref=self.store.retain_outcome_evidence(raw,meta)
        self.assertEqual(daily.DailyStore(self.root).read_outcome_evidence(ref),(raw,meta))
        body=self.store.ledger.read(ref)["data"]["daily"]
        self.assertEqual(body["source_use_status"],"REQUIRES_SEPARATE_ADMISSION")

    def test_authenticated_parent_memo_lasts_only_one_operation_and_failure_clears_it(self):
        parent=ledger.Ledger(self.root)
        ref=parent.append("input_captures","retained history stand-in",{"identity":{"source":"synthetic"}})
        original_validator=ledger.Ledger._validate_payload
        validations=[]
        def counted(payload,*,kind,record_id):
            validations.append((kind,record_id))
            return original_validator(payload,kind=kind,record_id=record_id)
        with patch.object(ledger.Ledger,"_validate_payload",side_effect=counted):
            with self.store.ledger.validation_scope():
                self.store.ledger.parent.read(ref)
                self.store.ledger.parent.scan()
                self.store.ledger.parent.read(ref)
            self.assertEqual(validations,[(ref.kind,ref.record_id)])
            self.store.ledger.parent.read(ref)
            self.assertEqual(len(validations),2)
        self.assertEqual(self.store.ledger._parent_read_cache,{})
        self.assertEqual(self.store.ledger._read_cache,{})
        path=parent._path(ref.kind,ref.record_id)
        payload=read_receipt(path);payload["data"]["identity"]["source"]="changed between operations"
        envelope={"schema_version":daily.RECEIPT_SCHEMA,"hash_format":daily.HASH_FORMAT,
            "payload_sha256":digest(payload),"payload":payload}
        path.write_bytes(canonical(envelope)+b"\n")
        with self.assertRaisesRegex(IntegrityError,"payload hash mismatch"):
            self.store.ledger.parent.read(ref)
        self.assertEqual(self.store.ledger._parent_read_cache,{})
        self.assertEqual(self.store.ledger._parent_payload_cache,set())
        path.unlink()
        with self.assertRaises(OSError):self.store.ledger.parent.read(ref)

    def test_daily_memo_is_not_reused_after_receipt_changes_between_operations(self):
        ref=self.store.retain_asset(*self.source())
        self.store.ledger.read(ref)
        path=self.store.ledger._path(ref.kind,ref.record_id)
        original=path.read_bytes();path.write_bytes(original+b"corruption")
        with self.assertRaises(IntegrityError):self.store.ledger.read(ref)
        self.assertEqual(self.store.ledger._read_cache,{})

    def test_symlinked_store_is_rejected(self):
        alias=self.root/"alias";alias.symlink_to(self.root,target_is_directory=True)
        with self.assertRaisesRegex(IntegrityError,"symlink"):
            daily.DailyStore(alias)


if __name__ == "__main__":unittest.main()

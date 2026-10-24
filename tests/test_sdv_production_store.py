"""Strict synthetic shard/archive recovery, never collected or issued evidence."""
from copy import deepcopy
from datetime import timedelta
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from multisport_lab import integrity, ledger, pregame_sources as historical
from multisport_lab import sdv_production_common as common
from multisport_lab import sdv_production_inputs as inputs
from multisport_lab import sdv_production_forecasts as forecasts
from multisport_lab import sdv_production_runner as runner
from multisport_lab import sdv_production_store as production
from multisport_lab import sdv_production_archive as archives
from multisport_lab.baseline import PrimitiveLine, WeightedOutcome, JointForecast
from multisport_lab.integrity import IntegrityError, canonical, digest, stamp, utc, read_receipt
import test_sdv_production_inputs as input_fixture
import test_sdv_production_forecasts as forecast_fixture
import test_pregame_sources as history_fixture


TAG = "nml-nba-records-v1-202610"


class ProductionStoreTests(unittest.TestCase):
    def setUp(self):
        self.fixture = input_fixture.ProductionInputTests(
            "test_all_events_all_active_players_and_exact_shards_are_native_production_records")
        self.addCleanup(self.fixture.doCleanups); self.fixture.setUp()
        self.fixture.binding = forecast_fixture.binding()
        # Explicit invented executable trust fixture. Structural source binding
        # and all graph/source/clock validators remain active; no reviewed code
        # commit or actual hosted authorization is claimed by this unit test.
        original_binding = forecasts.validate_binding
        binding_check = patch.object(forecasts,"validate_binding",
            side_effect=lambda body,**kwargs:original_binding(body,current=False))
        binding_check.start();self.addCleanup(binding_check.stop)
        for module in (ledger, historical):
            clock = patch.object(module,"_now",side_effect=lambda:self.fixture.now)
            clock.start();self.addCleanup(clock.stop)
        clock = patch.object(forecasts,"_now",side_effect=lambda:self.fixture.now)
        clock.start();self.addCleanup(clock.stop)
        temporary = tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name);self.source = self.folder/"source";self.state = self.folder/"state"
        self.source.mkdir()
        with patch.object(historical,"_now",return_value=history_fixture.NOW):
            pack = history_fixture.pack_fixture()
        pin = patch.object(historical,"PANEL_SHA",pack["history_provenance"]["normalized_panel_sha256"])
        pin.start();self.addCleanup(pin.stop)
        parent = ledger.Ledger(self.source)
        self.history_ref = parent.append("research_inputs","research-inputs:"+digest(pack),{"source_pack":pack})
        pin = patch.object(common,"HISTORY_ID",self.history_ref.record_id)
        pin.start();self.addCleanup(pin.stop)
        self.archive = archives.FileArchive(self.folder/"archive")
        self.store = self.new_store()
        self.mode = "PROSPECTIVE_RESEARCH"
        assets = self.fixture.assets()
        self.plan = self.fixture.build(assets,mode=self.mode)
        self.plan_ref = self.store.append_body(self.plan,archive_refs=self.retain_assets(assets))
        self.start = common.clock(self.plan["events"][0]["event"]["event_starts_at"])
        self.cutoff = self.start-timedelta(minutes=90)
        self.fixture.now = self.start-timedelta(minutes=100)
        assets = self.fixture.assets()
        self.input = self.fixture.fresh(self.plan,assets,mode=self.mode)
        self.input_ref = self.store.append_body(self.input,references=(self.plan_ref,),archive_refs=self.retain_assets(assets))
        self.ack(self.input_ref)
        self.auth_ref = self.store.append_body(self.authorization())
        self.intent = common.seal({"schema_version":common.INTENT_SCHEMA,"protocol_id":common.PROTOCOL_ID,
            "plan_id":self.plan["plan_id"],"cycle_id":self.input["cycle_id"],"mode":self.mode,
            "input_ref":self.input_ref.to_record(),"input_id":self.input["input_id"],
            "producer_binding_id":self.fixture.binding["binding_id"],"history_ref":self.history_ref.to_record(),
            "player_ids":self.input["shards"][0],"created_at":stamp(self.fixture.now)},"intent_id")
        self.intent_ref = self.store.append_body(self.intent,references=(self.input_ref,self.plan_ref,self.auth_ref))
        self.ack(self.intent_ref)
        self.fixture.now = self.cutoff+timedelta(seconds=5)

    def new_store(self,root=None):
        return production.ProductionStore(root or self.state,source_root=self.source,
            source_resolver=self.archive.recover_source,
            snapshot_resolver=lambda ref:self.archive.get_json(ref)["ledger_snapshot"])

    def retain_assets(self,assets):
        return tuple(self.archive.retain_source(raw,meta,assets[4][role],tag=TAG)
                     for role,raw,meta in (("schedule",assets[0],assets[2]),("roster",assets[1],assets[3])))

    def authorization(self):
        event={"repository":{"full_name":common.REPOSITORY},"schedule":common.CRON}
        run={"id":123,"run_attempt":1,"event":"schedule","head_sha":"b"*40,"head_branch":"main",
            "path":common.WORKFLOW,"status":"in_progress","conclusion":None,
            "repository":{"full_name":common.REPOSITORY},"actor":{"login":common.OWNER},
            "triggering_actor":{"login":common.OWNER},
            "run_started_at":stamp(self.fixture.now-timedelta(minutes=1))}
        return common.seal({"schema_version":common.AUTH_SCHEMA,"protocol_id":common.PROTOCOL_ID,
            "repository":common.REPOSITORY,"workflow_path":common.WORKFLOW,"event":"schedule","actor":common.OWNER,
            "run_id":123,"run_attempt":1,"head_sha":"b"*40,"run_started_at":run["run_started_at"],
            "verified_at":stamp(self.fixture.now),"event_original":runner._encoded(canonical(event)),
            "run_original":runner._encoded(canonical(run)),"executed_files":self.fixture.binding["files"]},"authorization_id")

    def ack(self,ref,*,delay=1):
        snapshot_ref = archives.archive_snapshot(self.store,self.archive,tag=TAG)
        # Local file archives are explicit test stand-ins. This fresh exact
        # readback is real filesystem recovery, not a GitHub durability claim.
        self.archive.get_json(snapshot_ref)
        self.fixture.now += timedelta(seconds=delay)
        remote = stamp(self.fixture.now)
        with self.store._verified_remote_completion((ref,),snapshot_ref,remote):
            return self.store.record_completion(ref,self.store.local_completion(ref)["local_completed_at"],remote,snapshot_ref)

    def laws(self,history,target):
        trained=utc("2025-01-02T00:00:00.000000Z")
        lines=[PrimitiveLine(20,4,2,1,10,10,2,0,0),PrimitiveLine(30,5,1,2,10,4,1,0,1),PrimitiveLine(12,1,0,0,2,1,0,1,2)]
        return {key:JointForecast(target,target.cutoff,trained,"d"*64,
            tuple(WeightedOutcome("invented-"+str(i),target.player_id,line,w) for i,(line,w) in enumerate(zip(lines,weights))),3,3)
            for key,weights in (("R0",(.25,.25,.5)),("K0",(.2,.3,.5)))}

    def pair(self,player_id=None):
        player_id = player_id or self.intent["player_ids"][0]
        history=[SimpleNamespace(outcome_available_at=utc("2025-01-02T00:00:00.000000Z"))]*common.HISTORY_ROWS
        with patch.object(forecasts,"_fit_laws",side_effect=self.laws):
            return forecasts.generate_pair(self.input,self.input_ref,self.fixture.binding,self.history_ref,history,
                player_id=player_id,mode=self.mode)

    def append_forecast(self,body):
        refs=(self.input_ref,self.intent_ref)
        with self.store._verified_forecast_write(body,refs):
            return self.store.append_body(body,references=refs)

    def persisted_pair(self,*,ack=True):
        bodies=self.pair();refs=[self.append_forecast(body) for body in bodies]
        if ack:
            for ref in refs:self.ack(ref)
        return refs,bodies

    def final_sources(self,*,points=12):
        event,rows=forecast_fixture.ProductionFixture.final_rows(self)
        event.update(season="2027",game_date_time=stamp(self.start),home_id="100",away_id="101",
                     home_score=str(points))
        for index,row in enumerate(rows):
            row.update(season="2027",game_date_time=stamp(self.start),athlete_id=str(1000+index*20),
                team_id="100" if index == 0 else "101",opponent_team_id="101" if index == 0 else "100",
                team_score=str(points) if index == 0 else "12",opponent_team_score="12" if index == 0 else str(points))
            if index == 0:
                row.update(points=str(points),free_throws_made=str(points-10),free_throws_attempted=str(points-10))
        refs=[]
        for role,raw in (("schedule",forecast_fixture.csv_bytes([event])),("boxscore",forecast_fixture.csv_bytes(rows))):
            tag="espn_nba_schedules" if role == "schedule" else "espn_nba_player_boxscores"
            name="nba_schedule_2027.csv" if role == "schedule" else "player_box_2027.csv"
            descriptor={"role":role,"release_tag":tag,"asset_name":name,"asset_url":
                "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"+tag+"/"+name}
            original=canonical({"tag_name":tag,"assets":[{"id":123 if role == "schedule" else 999,
                "name":name,"size":len(raw),"browser_download_url":descriptor["asset_url"],
                "digest":"sha256:"+hashlib.sha256(raw).hexdigest(),"updated_at":stamp(self.fixture.now-timedelta(minutes=10))}]})
            metadata=inputs.source_metadata(raw,original,descriptor,
                retrieval_started_at=self.fixture.now-timedelta(seconds=2),retrieved_at=self.fixture.now,
                metadata_retrieval_started_at=self.fixture.now-timedelta(seconds=4),metadata_retrieved_at=self.fixture.now-timedelta(seconds=3))
            refs.append(self.archive.retain_source(raw,metadata,original,tag=TAG))
        return refs

    def append_outcome(self,forecast_refs,*,previous=None,points=12):
        source_refs=self.final_sources(points=points)
        body=forecasts.normalize_outcome(self.store.read_body(forecast_refs[0]),self.input,archive=self.archive,
            schedule_ref=source_refs[0],boxscore_ref=source_refs[1],previous=previous[1] if previous else None)
        references=tuple(forecast_refs)+((previous[0],) if previous else ())
        return self.store.append_body(body,references=references,archive_refs=source_refs),body

    def path(self,ref):return self.state/"records"/ref.kind/(ref.record_id+".json")

    def test_independent_archive_restart_keeps_exact_originals_and_all14_categories(self):
        refs,bodies=self.persisted_pair()
        originals={ref:self.path(ref).read_bytes() for ref in refs}
        snapshot_ref=archives.archive_snapshot(self.store,self.archive,tag=TAG)
        recovered=archives.recover_snapshot(snapshot_ref,self.archive,self.folder/"recovered",source_root=self.source)
        report=recovered.recover()
        self.assertEqual(recovered.snapshot_manifest()["capacity"],self.store.capacity())
        self.assertEqual(production.archive_liability(report["capacity"]),
            2*(report["capacity"]["remaining_bytes"]+report["capacity"]["remaining_forensic_bytes"])
            +(report["capacity"]["remaining_records"]+report["capacity"]["remaining_forensic_files"]+1)*archives.SNAPSHOT_MAX_WIRE+1024*1024)
        self.assertEqual(report["genuine_issued"],2)  # Synthetic wire mode only.
        self.assertEqual(len(report["forecasts"]),2)
        self.assertTrue(all(len(body["categories"]) == 14 for _,body in report["forecasts"]))
        self.assertTrue(all(recovered.admission(ref)["eligible"] for ref in refs))
        self.assertEqual({ref:(recovered.root/"records"/ref.kind/(ref.record_id+".json")).read_bytes() for ref in refs},originals)
        self.assertFalse((recovered.root/"records/research_inputs").exists())

    def test_full16_player_shard_has_conservative_future_grade_and_marker_capacity(self):
        capacity=self.store.capacity()
        self.assertEqual(sum(production.SLOTS.values()),319)
        self.assertEqual(sum(n*(8192 if key == "corrections" else production.CEILINGS[key]) for key,n in production.SLOTS.items()),9_609_216)
        self.assertEqual(capacity["future_grading_receipt_bytes"],3_538_944)
        self.assertEqual(capacity["future_grading_liability_bytes"],8_126_464)
        self.assertEqual(capacity["future_status_receipt_bytes"],524_288)
        self.assertEqual(capacity["future_status_liability_bytes"],1_310_720)
        self.assertEqual(production.SLOTS[common.LOCAL_COMPLETION_SCHEMA],34)
        self.assertLessEqual(capacity["maximum_projected_records"],512)
        self.assertLessEqual(capacity["maximum_projected_bytes"],32*1024*1024)
        self.assertTrue(capacity["fits"])
        empty=production.empty_capacity()
        self.assertEqual(empty["existing_records"],0)
        self.assertEqual(empty["existing_bytes"],0)
        self.assertEqual(empty["remaining_records"],319)
        self.assertEqual(empty["remaining_forensic_files"],8)
        self.assertEqual(empty["remaining_forensic_bytes"],4*1024*1024)
        self.assertEqual(empty["maximum_projected_records"],327)
        self.assertEqual(empty["maximum_projected_bytes"],9_609_216+4*1024*1024)
        self.assertEqual(production.archive_liability(empty),
            2*(9_609_216+4*1024*1024)+328*archives.SNAPSHOT_MAX_WIRE+1024*1024)

    def test_original_without_local_marker_remains_unacknowledged_after_restart(self):
        body=self.pair()[0];write=ledger.write_receipt
        def interrupted(*args,**kwargs):
            result=write(*args,**kwargs)
            if args[1].get("kind") == "forecasts":raise KeyboardInterrupt("after original before post-write marker")
            return result
        with patch.object(ledger,"write_receipt",side_effect=interrupted),self.assertRaises(KeyboardInterrupt):
            self.append_forecast(body)
        rows=self.store.recover()["forecasts"];self.assertEqual(len(rows),1)
        ref=rows[0][0];original=self.path(ref).read_bytes()
        self.store=self.new_store()
        self.assertFalse(self.store.admission(ref)["eligible"])
        self.assertIn("LOCAL_POSTWRITE_COMPLETION_UNACKNOWLEDGED",self.store.admission(ref)["reasons"])
        self.assertEqual(self.append_forecast(body),ref)
        self.assertEqual(self.path(ref).read_bytes(),original)
        with self.assertRaisesRegex(IntegrityError,"post-write completion"):self.store.local_completion(ref)

    def test_actual_delayed_write_and_remote_completion_remain_ineligible(self):
        body=self.pair()[0];write=ledger.write_receipt
        def delayed(*args,**kwargs):
            if args[1].get("kind") == "forecasts":self.fixture.now+=timedelta(seconds=301)
            return write(*args,**kwargs)
        with patch.object(ledger,"write_receipt",side_effect=delayed):ref=self.append_forecast(body)
        local=self.store.local_completion(ref)
        self.assertGreater(common.clock(local["local_completed_at"]),common.clock(body["generation_started_at"])+timedelta(seconds=300))
        self.ack(ref)
        reasons=self.new_store().admission(ref)["reasons"]
        self.assertIn("ORIGINAL_LATENCY_EXCEEDED",reasons)
        self.assertFalse(self.store.admission(ref)["eligible"])

    def test_late_remote_recovery_and_missing_peer_are_preserved(self):
        body=self.pair()[0];ref=self.append_forecast(body)
        self.fixture.now=self.cutoff+timedelta(seconds=901)
        self.ack(ref)
        report=self.new_store().recover()
        self.assertEqual(len(report["forecasts"]),1);self.assertEqual(report["genuine_issued"],0)
        self.assertIn("FORECAST_REMOTE_RECOVERY_AFTER_WINDOW",report["admissions"][ref.record_id]["reasons"])

    def test_forged_direct_completion_and_changed_original_are_rejected(self):
        ref=self.append_forecast(self.pair()[0])
        snapshot=archives.archive_snapshot(self.store,self.archive,tag=TAG)
        local=self.store.local_completion(ref)["local_completed_at"]
        with self.assertRaisesRegex(IntegrityError,"actual independent archive recovery"):
            self.store.record_completion(ref,local,stamp(self.fixture.now),snapshot)
        original=self.path(ref).read_bytes();changed=deepcopy(self.store.read_body(ref))
        changed["producer_binding"]["commit"]="c"*40
        changed["producer_binding"]=common.seal({k:v for k,v in changed["producer_binding"].items() if k != "binding_id"},"binding_id")
        changed=common.seal({k:v for k,v in changed.items() if k != "forecast_id"},"forecast_id")
        with self.assertRaises(IntegrityError):self.append_forecast(changed)
        self.assertEqual(self.path(ref).read_bytes(),original)

    def test_changed_input_reference_and_checksum_consistent_wrong_admission_fail(self):
        body=self.pair()[0];body["input_ref"]=self.intent_ref.to_record()
        body=common.seal({k:v for k,v in body.items() if k != "forecast_id"},"forecast_id")
        with self.assertRaisesRegex(IntegrityError,"bound intent"):self.append_forecast(body)
        ref=self.append_forecast(self.pair()[0]);completion=self.ack(ref)
        payload=read_receipt(self.path(completion));claimed=payload["data"]["production"]
        claimed.update(eligible=False,reasons=["INVENTED_REASON"])
        claimed["completion_id"]=digest({k:v for k,v in claimed.items() if k != "completion_id"})
        self.path(completion).write_bytes(canonical({"schema_version":integrity.RECEIPT_SCHEMA,"hash_format":integrity.HASH_FORMAT,
            "payload_sha256":digest(payload),"payload":payload}))
        with self.assertRaisesRegex(IntegrityError,"contradicts actual completion"):self.new_store().recover()

    def test_snapshot_reference_and_receipt_hashes_are_independently_checked(self):
        refs,_=self.persisted_pair()
        snapshot=self.store.snapshot_manifest();production.validate_snapshot_manifest(snapshot)
        broken=deepcopy(snapshot);broken["entries"][0]["path"]="../outside.json"
        broken=common.seal({k:v for k,v in broken.items() if k != "snapshot_id"},"snapshot_id")
        with self.assertRaises(IntegrityError):production.validate_snapshot_manifest(broken)
        for mutate in (lambda cap:cap.update(existing_bytes=cap["existing_bytes"]+1),
                       lambda cap:cap["role_counts"].update({common.FORECAST_SCHEMA:0}),
                       lambda cap:cap.update(remaining_bytes=cap["remaining_bytes"]-1),
                       lambda cap:cap.update(future_grading_liability_bytes=0)):
            broken=deepcopy(snapshot);mutate(broken["capacity"])
            broken=common.seal({k:v for k,v in broken.items() if k != "snapshot_id"},"snapshot_id")
            with self.assertRaises(IntegrityError):production.validate_snapshot_manifest(broken)
            with self.assertRaises(IntegrityError):production.archive_liability(broken["capacity"])
        self.path(refs[0]).write_bytes(self.path(refs[0]).read_bytes()+b"changed")
        with self.assertRaises(IntegrityError):self.new_store().recover()

    def test_warm_history_semantic_cache_still_authenticates_actual_parent_bytes(self):
        self.persisted_pair()
        self.assertTrue(self.store._history_semantics)
        path=self.source/"records/research_inputs"/(self.history_ref.record_id+".json")
        original=path.read_bytes();path.write_bytes(original+b"changed")
        with self.assertRaises(IntegrityError):self.store.recover()
        path.write_bytes(original)
        payload=read_receipt(path);payload["received_at"]=stamp(utc(payload["received_at"])+timedelta(seconds=1))
        path.write_bytes(canonical({"schema_version":integrity.RECEIPT_SCHEMA,"hash_format":integrity.HASH_FORMAT,
            "payload_sha256":digest(payload),"payload":payload}))
        with self.assertRaisesRegex(IntegrityError,"history reference"):self.store.recover()

    def test_hardkill_orphans_are_archived_exactly_without_admitting_partial_records(self):
        refs,_=self.persisted_pair();originals={ref:self.path(ref).read_bytes() for ref in refs}
        before=self.store.capacity()
        folder=self.state/"records/forecasts"
        partial=folder/".receipt-killed"
        partial.write_bytes(b'{"partial":"synthetic SIGKILL before atomic publication"')
        empty=folder/".receipt-empty";empty.write_bytes(b"")
        report=self.store.recover()
        self.assertEqual(report["genuine_issued"],2)
        self.assertEqual(len(report["unpublished_entries"]),2)
        self.assertEqual(report["capacity"]["existing_records"],before["existing_records"]+2)
        self.assertEqual(report["capacity"]["existing_bytes"],before["existing_bytes"]+partial.stat().st_size)
        snapshot=self.store.snapshot_manifest();production.validate_snapshot_manifest(snapshot)
        self.assertEqual(snapshot["records"],len(self.store.records()))
        self.assertEqual(len(snapshot["unpublished_entries"]),2)
        ref=archives.archive_snapshot(self.store,self.archive,tag=TAG)
        recovered=archives.recover_snapshot(ref,self.archive,self.folder/"killed-recovered",source_root=self.source)
        self.assertEqual((recovered.root/partial.relative_to(self.state)).read_bytes(),partial.read_bytes())
        self.assertEqual((recovered.root/empty.relative_to(self.state)).read_bytes(),b"")
        self.assertEqual(recovered.recover()["genuine_issued"],2)
        self.assertEqual({ref:(recovered.root/self.path(ref).relative_to(self.state)).read_bytes() for ref in refs},originals)

    def test_exhausted_forensic_allowance_stops_new_writes_but_recovers_all_actual_bytes(self):
        folder=self.state/"records/forecasts";folder.mkdir(exist_ok=True)
        for index in range(8):(folder/(".receipt-failed-"+str(index))).write_bytes(b"")
        self.assertTrue(self.store.capacity()["forensic_fits"])
        self.assertEqual(self.store.capacity()["remaining_forensic_files"],0)
        with self.assertRaisesRegex(IntegrityError,"forensic failure allowance"):
            self.append_forecast(self.pair()[0])
        overflow=folder/".receipt-preserved-over-limit"
        overflow.write_bytes(b"x"*(production.MAX_FORENSIC_FILE_BYTES+1))
        report=self.new_store().recover()
        self.assertFalse(report["capacity"]["forensic_fits"])
        self.assertEqual(len(report["unpublished_entries"]),9)
        self.assertEqual(report["capacity"]["forensic_oversized_files"],1)
        snapshot=archives.archive_snapshot(self.store,self.archive,tag=TAG)
        recovered=archives.recover_snapshot(snapshot,self.archive,self.folder/"overflow-recovered",source_root=self.source)
        self.assertEqual((recovered.root/overflow.relative_to(self.state)).read_bytes(),overflow.read_bytes())
        self.assertEqual(recovered.recover()["unpublished_entries"],report["unpublished_entries"])
        body=self.pair()[0];refs=(self.input_ref,self.intent_ref)
        with recovered._verified_forecast_write(body,refs),self.assertRaisesRegex(IntegrityError,"forensic failure allowance"):
            recovered.append_body(body,references=refs)

    def test_shared_outcome_grades_and_corrections_preserve_original_probabilities(self):
        refs,bodies=self.persisted_pair();originals={ref:self.path(ref).read_bytes() for ref in refs}
        self.fixture.now=self.start+timedelta(hours=4)
        outcome_ref,outcome=self.append_outcome(refs)
        grades=[]
        for ref,forecast in zip(refs,bodies):
            grade=forecasts.make_grade(forecast,outcome)
            grades.append((self.store.append_body(grade,references=(ref,outcome_ref)),grade))
        self.assertEqual(len(self.store.recover()["outcomes"]),1)
        self.assertEqual(len(self.store.recover()["grades"]),2)
        self.fixture.now+=timedelta(minutes=10)
        next_ref,next_outcome=self.append_outcome(refs,previous=(outcome_ref,outcome),points=13)
        self.store.correct(outcome_ref,next_ref,reason="Synthetic corrected official count")
        for index,(ref,forecast) in enumerate(zip(refs,bodies)):
            grade=forecasts.make_grade(forecast,next_outcome,previous=grades[index][1])
            replacement=self.store.append_body(grade,references=(ref,next_ref,grades[index][0]))
            self.store.correct(grades[index][0],replacement,reason="Synthetic statistical regrade")
        recovered=self.new_store().recover()
        self.assertEqual(len(recovered["outcomes"]),2);self.assertEqual(len(recovered["grades"]),4)
        self.assertEqual(len(recovered["corrections"]),3)
        self.assertTrue(all(grade["financial_settlement"] == "NOT_EVALUATED" for _,grade in recovered["grades"]))
        self.assertEqual({ref:self.path(ref).read_bytes() for ref in refs},originals)

    def test_interrupted_shared_outcome_recovery_adds_only_missing_grade(self):
        refs,bodies=self.persisted_pair();self.fixture.now=self.start+timedelta(hours=4)
        outcome_ref,outcome=self.append_outcome(refs)
        grade=forecasts.make_grade(bodies[0],outcome)
        original=self.store.append_body(grade,references=(refs[0],outcome_ref))
        exact=self.path(original).read_bytes();self.store=self.new_store()
        next_grade=forecasts.make_grade(bodies[1],outcome)
        self.store.append_body(next_grade,references=(refs[1],outcome_ref))
        self.assertEqual(len(self.store.recover()["outcomes"]),1)
        self.assertEqual(len(self.store.recover()["grades"]),2)
        self.assertEqual(self.path(original).read_bytes(),exact)

    def test_reverse_correction_is_rejected_before_receipt_and_restart_remains_valid(self):
        refs,_=self.persisted_pair();self.fixture.now=self.start+timedelta(hours=4)
        first,body=self.append_outcome(refs)
        self.fixture.now+=timedelta(minutes=10)
        second,_=self.append_outcome(refs,previous=(first,body),points=13)
        before={path.relative_to(self.state):path.read_bytes() for path in self.state.glob("records/*/*.json")}
        with self.assertRaisesRegex(IntegrityError,"revision chain"):
            self.store.correct(second,first,reason="Synthetic invalid reverse correction")
        self.assertEqual({path.relative_to(self.state):path.read_bytes() for path in self.state.glob("records/*/*.json")},before)
        self.assertEqual(len(self.new_store().recover()["outcomes"]),2)
        self.store.correct(first,second,reason="Synthetic valid forward correction")
        self.assertEqual(len(self.new_store().recover()["corrections"]),1)

    def test_ineligible_peer_grade_is_rejected_before_write_and_restart_keeps_eligible_peer(self):
        bodies=self.pair();refs=[self.append_forecast(body) for body in bodies]
        self.ack(refs[0])
        self.fixture.now=self.cutoff+timedelta(seconds=901)
        self.ack(refs[1])
        self.assertEqual([self.store.admission(ref)["eligible"] for ref in refs],[True,False])
        originals={ref:self.path(ref).read_bytes() for ref in refs}
        self.fixture.now=self.start+timedelta(hours=4)
        outcome_ref,outcome=self.append_outcome(refs)
        before={path.relative_to(self.state):path.read_bytes() for path in self.state.glob("records/*/*.json")}
        rejected=forecasts.make_grade(bodies[1],outcome)
        with self.assertRaisesRegex(IntegrityError,"ineligible forecast"):
            self.store.append_body(rejected,references=(refs[1],outcome_ref))
        self.assertEqual({path.relative_to(self.state):path.read_bytes() for path in self.state.glob("records/*/*.json")},before)
        self.store=self.new_store()
        report=self.store.recover()
        self.assertEqual(len(report["outcomes"]),1)
        self.assertEqual(report["grades"],[])
        self.assertEqual(report["genuine_issued"],1)
        accepted=forecasts.make_grade(bodies[0],outcome)
        self.store.append_body(accepted,references=(refs[0],outcome_ref))
        self.assertEqual(len(self.new_store().recover()["grades"]),1)
        self.assertEqual({ref:self.path(ref).read_bytes() for ref in refs},originals)

    def test_diagnostic_archives_require_optin_and_never_accept_genuine_bodies(self):
        diagnostic=archives.FileArchive(self.folder/"diagnostic",allow_diagnostics=True)
        assets=self.fixture.assets();tag="diagnostics-nml-nba-store-test"
        refs=tuple(diagnostic.retain_source(raw,meta,assets[4][role],tag=tag)
            for role,raw,meta in (("schedule",assets[0],assets[2]),("roster",assets[1],assets[3])))
        body=self.fixture.build(assets,mode="DEVELOPMENT_ONLY")
        other=production.ProductionStore(self.folder/"dev",source_root=self.source,
            source_resolver=diagnostic.recover_source,allow_diagnostics=True)
        other.append_body(body,archive_refs=refs)
        self.assertEqual(other.recover()["genuine_issued"],0)
        body=common.seal({key:value for key,value in body.items() if key != "plan_id"}|{"mode":"PROSPECTIVE_RESEARCH"},"plan_id")
        with self.assertRaises(IntegrityError):other.append_body(body,archive_refs=refs)

    def test_production_cannot_reuse_any_protected_original_namespace(self):
        for relative in ("records","daily","daily/nested","recurring"):
            with self.subTest(relative=relative),self.assertRaisesRegex(IntegrityError,"protected pilot/planning"):
                production.ProductionStore(self.source/relative,source_root=self.source)

    def test_status_authenticates_exact_native_event_input_and_player_shard(self):
        body=common.seal({"schema_version":common.STATUS_SCHEMA,"protocol_id":common.PROTOCOL_ID,
            "plan_id":self.plan["plan_id"],"cycle_id":self.input["cycle_id"],"phase":"GRADE",
            "status":"FAILED_OR_PARTIAL","details":{"task_id":"a"*64,"shard_index":0,
                "player_ids":self.input["shards"][0],"error":"Synthetic unresolved source evidence"},
            "observed_at":stamp(self.fixture.now),"run_id":123},"status_id")
        before={path.relative_to(self.state):path.read_bytes() for path in self.state.glob("records/*/*.json")}
        for changes in ({"details":{"player_ids":["999999999"]}},
                        {"details":{"shard_index":len(self.input["shards"])}},
                        {"details":{"shard_index":True}},
                        {"details":{"task_id":"invalid-task"}},
                        {"plan_id":"f"*64},
                        {"cycle_id":self.input["cycle_id"].replace("-100-","-999-")}):
            candidate=deepcopy(body)
            if "details" in changes:candidate["details"].update(changes["details"])
            else:candidate.update(changes)
            # Use a distinct, syntactically valid foreign event even when the
            # fixture's event ID differs from the convenient replacement above.
            if "cycle_id" in changes:
                pieces=self.input["cycle_id"].split("-");pieces[2]="999999999";candidate["cycle_id"]="-".join(pieces)
            candidate=common.seal({key:value for key,value in candidate.items() if key != "status_id"},"status_id")
            with self.subTest(changes=changes),self.assertRaises(IntegrityError):self.store.append_body(candidate)
            self.assertEqual({path.relative_to(self.state):path.read_bytes() for path in self.state.glob("records/*/*.json")},before)
        original=self.store.append_body(body)
        self.assertEqual(self.new_store().read_body(original),body)
        invalid=deepcopy(body);invalid["details"]["player_ids"]=["999999999"]
        invalid=common.seal({key:value for key,value in invalid.items() if key != "status_id"},"status_id")
        self.store.ledger.append("input_captures",production._logical(invalid),
            {"identity":production._identity(invalid),"production":invalid,"archive_refs":[]})
        with self.assertRaisesRegex(IntegrityError,"registered player shard"):self.new_store().recover()

    def test_reserved_future_obligations_fail_before_new_write_and_unknown_bodies_fail(self):
        before=len(self.store.records())
        ceiling=self.store.capacity()["maximum_projected_bytes"]-1
        with patch.object(production,"MAX_BYTES",ceiling),self.assertRaisesRegex(IntegrityError,"capacity|obligations exceed"):
            self.append_forecast(self.pair()[0])
        self.assertEqual(len(self.store.records()),before)
        hidden={"schema_version":"invented-forecast","protocol_id":common.PROTOCOL_ID,"forecast_id":"0"*64}
        with self.assertRaisesRegex(IntegrityError,"Unsupported production"):self.store.append_body(hidden)
        self.store.ledger.append("forecasts","checksum-valid-generic-carrier",
            {"identity":{},"production":hidden,"archive_refs":[]})
        with self.assertRaisesRegex(IntegrityError,"Unsupported production"):
            self.new_store().recover()


if __name__ == "__main__":unittest.main()

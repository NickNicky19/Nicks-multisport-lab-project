"""Synthetic native phases with actual local archives and bare-Git recovery.

No provider requests, reviewed activation, real history fit or issued predictions.
Only the hosted-auth boundary and mathematical fitting use explicit test doubles.
"""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from multisport_lab import sdv_production_archive as archives
from multisport_lab import sdv_production_common as common
from multisport_lab import sdv_production_coordinator as engine
from multisport_lab import sdv_production_forecasts as forecasts
from multisport_lab import sdv_production_remote as remote
from multisport_lab import sdv_production_runner as runner
from multisport_lab.integrity import IntegrityError, canonical, digest, stamp, utc
import test_sdv_production_store as store_fixture


class LocalRegistryWriter:
    """An explicit local index double; never a GitHub checkpoint claim."""
    def __init__(self):self.history=[]
    def write(self,body):
        body=common.seal({key:value for key,value in deepcopy(body).items() if key != "registry_id"}|{"updated_at":stamp(common.now())},"registry_id")
        runner.validate_registry(body);self.history.append(deepcopy(body));return deepcopy(body)


class ProductionCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.case=store_fixture.ProductionStoreTests("test_independent_archive_restart_keeps_exact_originals_and_all14_categories")
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.fixture=self.case.fixture;self.folder=self.case.folder;self.archive=self.case.archive
        self.fixture.schedule=self.fixture.schedule[:1]
        self.fixture.roster=[row for row in self.fixture.roster if row["athlete_id"] in {"1000","1020"}]
        self.fixture.now=utc("2026-10-23T13:17:00.000000Z")
        self.writer=LocalRegistryWriter();self.packs={};self.calls=[]
        self.git("init","--quiet","-b","main",cwd=self.case.source)
        self.git("add",".",cwd=self.case.source)
        self.git("-c","user.name=Invented Local Test","-c","user.email=synthetic@example.invalid","commit","--quiet","-m","Synthetic parent history",cwd=self.case.source)
        self.base=self.git("rev-parse","HEAD",cwd=self.case.source).stdout.decode().strip()
        self.bare=self.folder/"remote.git";self.git("init","--bare","--quiet",str(self.bare),cwd=self.folder)
        self.git("push",str(self.bare),"HEAD:refs/heads/main",cwd=self.case.source)
        history=[SimpleNamespace(outcome_available_at=utc("2025-01-02T00:00:00.000000Z"))]*common.HISTORY_ROWS
        self.history_patch=patch.object(forecasts,"retained_history",return_value=(self.case.history_ref,history,{}))
        self.history_patch.start();self.addCleanup(self.history_patch.stop)
        def prepared(history,target,*,mode):
            return SimpleNamespace(started_at=self.fixture.now,for_target=lambda selected:self.case.laws(history,selected))
        self.laws_patch=patch.object(forecasts,"PreparedLaws",side_effect=prepared)
        self.laws_patch.start();self.addCleanup(self.laws_patch.stop)
        self.count=0;self.current=self.coordinator()

    def git(self,*args,cwd):
        result=subprocess.run(["git",*args],cwd=cwd,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors="replace"));return result

    def remote_factory(self,*args,**kwargs):
        kwargs.update(base_commit=self.base,remote_url=self.bare,allow_local_test_remote=True)
        return remote.ProductionGitCheckpointWriter(*args,**kwargs)

    def coordinator(self,registry=None):
        self.count+=1
        result=engine.Coordinator(registry or runner.empty_registry(),self.writer,self.archive,None,self.folder/("worker-"+str(self.count)),
            mode="DEVELOPMENT_ONLY",source_root=self.case.source,binding=self.fixture.binding,collector=self.collect,remote_factory=self.remote_factory)
        # All asset originals, hashes, source semantics, typed DAG, independent
        # archive bytes and Git transport stay real. This bypasses only the
        # production source-pack's hosted run proof for invented fixtures.
        result._pack=lambda ref:self.recover_pack(ref)
        return result

    def recover_pack(self,ref):
        pack=self.archive.get_json(ref)
        values={row["role"]:self.archive.recover_source(row["source_ref"]) for row in pack["sources"]}
        return pack,values

    def collect(self,root,archive,*,season,tag,opens_at,closes_at,final,authorization):
        self.calls.append((final,deepcopy(self.current.registry["attempts"])))
        # Prove a retained index reservation precedes the would-be collector.
        self.assertTrue(self.writer.history)
        self.assertEqual(self.writer.history[-1]["attempts"][-1]["status"],"RESERVED")
        # Distinct invented attempts have distinct actual fixture clocks. This
        # is not a measurement of provider or hosted-run latency.
        self.fixture.now+=timedelta(seconds=1)
        if final:
            refs=self.case.final_sources(points=getattr(self,"points",12));roles=("schedule","boxscore")
        else:
            values=self.fixture.assets();refs=self.case.retain_assets(values);roles=("schedule","roster")
        body=common.seal({"schema_version":"synthetic-local-source-pack-v1","sources":[
            {"role":role,"source_ref":ref} for role,ref in zip(roles,refs)],"requests":[{"synthetic_not_executed":True} for _ in range(4)],"captured_at":stamp(common.now())},"source_pack_id")
        ref=archive.put_json(body,tag=tag);self.packs[digest(ref)]=body;return ref,body

    def planned(self):
        self.assertEqual(self.current.prepare_tasks(),[])
        self.assertEqual(len(self.current.registry["days"][0]["shards"]),1)
        self.assertEqual(len(self.calls),1)

    def prepared(self):
        self.planned();self.fixture.now=self.case.start-timedelta(minutes=140)
        tasks=self.current.prepare_tasks();self.assertEqual([row["action"] for row in tasks],["PREPARE"])
        report=self.current.work(tasks[0]);self.assertEqual(report["status"],"PREPARED",report)
        self.assertNotIn("durability_error",report)
        recovered=self.current.refresh();self.assertEqual(recovered[0]["status"],"INDEPENDENTLY_RECOVERED",recovered)
        self.assertEqual(self.current.prepare_tasks(),[])
        return tasks[0]

    def issued(self):
        task=self.prepared();self.fixture.now=self.case.cutoff+timedelta(seconds=1)
        tasks=self.current.prepare_tasks();self.assertEqual([row["action"] for row in tasks],["ISSUE"])
        report=self.current.work(tasks[0]);self.assertEqual(report["status"],"ISSUED_PENDING_OUTCOMES",report)
        self.assertNotIn("durability_error",report)
        self.assertEqual(report["counts"]["forecasts"],4);self.assertEqual(report["genuine_issued"],0)
        self.current.refresh();self.assertEqual(self.current.prepare_tasks(),[])
        return tasks[0]

    def test_cold_global_reserve_precedes_writes_and_rejects_false_snapshot_capacity(self):
        self.planned();registry=deepcopy(self.current.registry)
        cold=self.coordinator(registry)
        self.assertEqual(cold.archive.reserved_bytes,registry["archive_budget"]["reserved_bytes"])
        self.assertEqual(cold.archive.reserved_objects,registry["archive_budget"]["reserved_objects"])
        # Admission uses the actual one-shard cohort, never a hypothetical
        # maximum league population.
        self.assertEqual(len(registry["archive_budget"]["shards"]),1)
        self.assertLess(cold.archive.reserved_objects,100000)
        with patch.object(cold.archive,"quota",return_value={"fits":False}):
            calls=len(self.calls)
            with self.assertRaisesRegex(IntegrityError,"Archive quota"):
                cold._reserve_archive(source_headroom=64*1024*1024)
            self.assertEqual(len(self.calls),calls)
        # Cold readers cannot trust a merely checksum-consistent summary that
        # contradicts its exact archived snapshot bytes.
        self.fixture.now=self.case.start-timedelta(minutes=140)
        task=self.current.prepare_tasks()[0];self.current.work(task);self.current.refresh()
        registry=deepcopy(self.current.registry);row=registry["archive_budget"]["shards"][0]
        original=self.archive.get_json(row["snapshot_ref"])
        forged=deepcopy(original);forged["ledger_snapshot"]["capacity"]=engine.ProductionStore(self.folder/"empty-store",source_root=self.case.source).capacity()
        with patch.object(self.archive,"get_json",return_value=forged):
            with self.assertRaises(IntegrityError):self.coordinator(registry)

    def test_unchanged_head_probe_skips_only_exact_prior_typed_readback(self):
        self.prepared();shard=self.current.registry["days"][0]["shards"][0]
        self.current.mode="PROSPECTIVE_RESEARCH"
        same=SimpleNamespace(stdout=(shard["latest_commit"]+"\trefs/heads/"+shard["branch"]+"\n").encode())
        with patch.object(self.current,"_authority"),patch.object(self.current,"_save"),patch.object(runner,"_git",return_value=same) as probe,patch.object(self.current,"_read_store",side_effect=IntegrityError("changed path must recover")) as recover:
            result=self.current.refresh()
            self.assertEqual(result[0]["status"],"UNCHANGED_INDEPENDENTLY_RECOVERED_HEAD")
            self.assertEqual(probe.call_count,1);recover.assert_not_called()
            different=SimpleNamespace(stdout=("f"*40+"\trefs/heads/"+shard["branch"]+"\n").encode())
            probe.return_value=different
            result=self.current.refresh()
            self.assertEqual(result[0]["status"],"RECOVERY_FAILED");recover.assert_called_once()

    def test_parallel_workers_keep_all_other_shards_and_metadata_in_the_reserve(self):
        self.planned();budget=self.current._budget()
        self.current._reserve_archive()
        from multisport_lab.sdv_production_store import archive_liability
        own=budget["shards"][0]["capacity"]
        self.assertEqual(self.archive.reserved_bytes-archive_liability(own),budget["shared_source_bytes"]+budget["parallel_headroom_bytes"]+budget["shared_metadata_bytes"])
        self.assertEqual(self.archive.reserved_objects-runner.archive_object_liability(own),1876+256+4096)
        self.assertEqual(budget["parallel_headroom_bytes"],16*16*1024*1024)

    def test_complete_native_local_phases_recover_exact_forecasts_and_separate_grades(self):
        descriptor=self.issued();registry=deepcopy(self.current.registry)
        original=self.current._store(engine.validate_task(self.archive.get_json(descriptor["task_ref"])))[0].recover()
        self.assertTrue(all(len(body["categories"]) == 14 and body["issued_at"] is None for _,body in original["forecasts"]))
        # A new work tree independently fetches every retained original, with no
        # source collection or generation needed merely to recover.
        self.current=self.coordinator(registry);self.current.refresh()
        self.assertEqual(len(self.calls),2)
        self.fixture.now=self.case.start+timedelta(hours=13,minutes=17)
        tasks=self.current.prepare_tasks();self.assertEqual([row["action"] for row in tasks],["GRADE"])
        report=self.current.work(tasks[0]);self.assertEqual(report["status"],"STATISTICAL_GRADING_RETAINED",report)
        self.assertEqual(report["counts"],{"forecasts":4,"outcomes":2,"grades":4})
        self.assertEqual(report["genuine_issued"],0)
        self.current.refresh();before=len(self.calls)
        # Two bounded final snapshots are possible per day; after the second
        # observation is acknowledged there is no repeated grade task.
        more=self.current.prepare_tasks()
        if more:self.current.work(more[0]);self.current.refresh()
        self.assertEqual(self.current.prepare_tasks(),[])
        self.assertLessEqual(len(self.calls)-before,1)
        task=engine.validate_task(self.archive.get_json(descriptor["task_ref"]))
        recovered=self.current._store(task)[0].recover()
        self.assertEqual(recovered["forecasts"],original["forecasts"])
        self.assertTrue(all(body["financial_settlement"] == "NOT_EVALUATED" for _,body in recovered["grades"]))

    def test_restart_does_not_regenerate_or_rebind_and_derived_acks_are_durable(self):
        descriptor=self.issued();calls=len(self.calls);registry=deepcopy(self.current.registry)
        self.current=self.coordinator(registry)
        with patch.object(forecasts,"generate_pair",side_effect=AssertionError("Must recover originals")):
            report=self.current.work(descriptor)
        self.assertEqual(report["counts"]["forecasts"],4)
        self.assertEqual(len(self.calls),calls)
        self.current.refresh();self.assertEqual(self.current.prepare_tasks(),[])
        shard=self.current.registry["days"][0]["shards"][0]
        self.assertEqual(shard["issued_input_task_ref"],shard["input_task_ref"])
        self.assertIsNotNone(shard["snapshot_ref"])

    def test_late_worker_preserves_originals_without_filling_or_new_source(self):
        descriptor=self.issued();calls=len(self.calls)
        self.fixture.now=self.case.cutoff+timedelta(minutes=16)
        report=self.current.work(descriptor)
        self.assertEqual(report["status"],"FAILED_OR_PARTIAL");self.assertIn("window",report["error"])
        self.assertEqual(report["counts"]["forecasts"],4);self.assertNotIn("durability_error",report)
        self.assertEqual(len(self.calls),calls)

    def test_no_originals_no_final_capture_and_no_forged_owner_capability(self):
        self.prepared();calls=len(self.calls);self.fixture.now=self.case.start+timedelta(hours=13,minutes=17)
        self.assertEqual(self.current.prepare_tasks(),[])
        self.assertFalse(any(final for final,_ in self.calls[calls:]))
        with self.assertRaises(IntegrityError):
            engine.Coordinator(runner.empty_registry(),self.writer,self.archive,{"approved":True},self.folder/"forged")

    def test_capture_quota_and_attempt_failures_precede_more_provider_requests(self):
        self.planned();self.fixture.now=self.case.start-timedelta(minutes=140)
        with patch.object(self.archive,"quota",return_value={"fits":False}):
            self.assertEqual(self.current.prepare_tasks(),[])
        self.assertEqual(len(self.calls),1)
        def failed(*args,**kwargs):
            self.fixture.now+=timedelta(seconds=1)
            raise IntegrityError("Invented source failure")
        self.current.collector=failed
        self.assertEqual(self.current.prepare_tasks(),[])
        self.assertEqual(self.current.registry["attempts"][-1]["status"],"FAILED")
        self.assertIsNotNone(self.current.registry["attempts"][-1]["source_pack_ref"])
        self.current.prepare_tasks()
        attempts=len(self.current.registry["attempts"])
        self.current.prepare_tasks();self.assertEqual(len(self.current.registry["attempts"]),attempts)
        self.assertEqual(sum(row["phase"] == "INPUT" for row in self.current.registry["attempts"]),2)
        self.assertTrue(any("attempt" in row["error"].lower() for row in self.current.reports))

    def test_interrupted_peer_is_preserved_and_restart_generates_only_missing_originals(self):
        self.prepared();self.fixture.now=self.case.cutoff+timedelta(seconds=1)
        descriptor=self.current.prepare_tasks()[0]
        original=engine.ProductionStore.append_body;interrupted=[False]
        def append(store,body,**kwargs):
            if body.get("schema_version") == common.FORECAST_SCHEMA and body.get("model_key") == "K0" and not interrupted[0]:
                interrupted[0]=True;raise InterruptedError("Invented interruption before peer write")
            return original(store,body,**kwargs)
        with patch.object(engine.ProductionStore,"append_body",new=append):report=self.current.work(descriptor)
        self.assertEqual(report["status"],"FAILED_OR_PARTIAL");self.assertEqual(report["counts"]["forecasts"],1)
        task=engine.validate_task(self.archive.get_json(descriptor["task_ref"]))
        retained=self.current._store(task)[0].recover()["forecasts"][0]
        self.current=self.coordinator(deepcopy(self.current.registry));report=self.current.work(descriptor)
        self.assertEqual(report["counts"]["forecasts"],4);self.assertEqual(report["genuine_issued"],0)
        self.assertIn(retained,self.current._store(task)[0].recover()["forecasts"])
        self.assertEqual(len(self.calls),2)

    def test_corrected_sources_append_two_versions_and_never_replace_originals(self):
        descriptor=self.issued();self.fixture.now=self.case.start+timedelta(hours=13,minutes=17)
        first=self.current.prepare_tasks()[0];report=self.current.work(first)
        self.assertEqual(report["counts"],{"forecasts":4,"outcomes":2,"grades":4});self.current.refresh()
        self.points=13;second=self.current.prepare_tasks()[0]
        original=engine.ProductionStore.append_body
        def interrupted_grade(store,body,**kwargs):
            if body.get("schema_version") == common.GRADE_SCHEMA and body.get("model_key") == "K0" and body.get("correction_revision") == 2:
                raise InterruptedError("Invented interruption before corrected peer grade")
            return original(store,body,**kwargs)
        with patch.object(engine.ProductionStore,"append_body",new=interrupted_grade):report=self.current.work(second)
        self.assertEqual(report["status"],"FAILED_OR_PARTIAL")
        self.assertEqual(report["counts"]["forecasts"],4);self.assertEqual(report["counts"]["outcomes"],3)
        # Receipt hash order may encounter the interrupted K0 peer before R0.
        # Either partial retains fewer than both corrected grades; recovery
        # below must fill the exact missing history in either ordering.
        self.assertIn(report["counts"]["grades"],(4,5));self.current.refresh()
        self.points=14;self.fixture.now+=timedelta(days=1)
        third=self.current.prepare_tasks()[0];report=self.current.work(third)
        self.assertEqual(report["grading"]["correction_quota_exhausted"],["1000"])
        self.assertEqual(report["counts"],{"forecasts":4,"outcomes":3,"grades":6})
        task=engine.validate_task(self.archive.get_json(descriptor["task_ref"]))
        result=self.current._store(task)[0].recover();self.assertEqual(len(result["corrections"]),3)
        self.assertEqual(sorted(body["correction_revision"] for _,body in result["outcomes"]),[1,1,2])

    def test_retained_final_evidence_can_finish_after_capture_deadline_without_new_get(self):
        self.issued();self.fixture.now=self.case.start+timedelta(hours=13,minutes=17)
        descriptor=self.current.prepare_tasks()[0];calls=len(self.calls)
        # A deferred worker starts after seven days. Its already-admitted
        # source observation retains its original time; no late data is read.
        self.fixture.now=self.case.start+timedelta(days=8,hours=5)
        tasks=self.current.prepare_tasks();self.assertEqual(len(self.calls),calls)
        self.assertEqual(tasks,[descriptor]);self.assertEqual(len(self.current.registry["days"]),1)
        report=self.current.work(descriptor);self.assertEqual(report["counts"]["grades"],4,report)
        self.current.refresh();self.assertEqual(self.current.prepare_tasks(),[])
        self.assertEqual(self.current.registry["days"],[])
        self.assertEqual(sum(day["game_date"] == "2026-10-24" for day in self.current.registry["archived_days"]),1)

    def test_only_timely_peer_is_scored_while_shared_outcome_keeps_both_originals(self):
        # Actual typed store/admission graph using an invented hosted wire proof;
        # this is not a real authorization or issuance claim.
        self.fixture.now=self.case.cutoff+timedelta(seconds=5)
        refs,bodies=self.case.persisted_pair(ack=False);self.case.ack(refs[0])
        self.assertTrue(self.case.store.admission(refs[0])["eligible"])
        self.assertFalse(self.case.store.admission(refs[1])["eligible"])
        self.fixture.now=self.case.start+timedelta(hours=4)
        final_refs=self.case.final_sources()
        pack={"sources":[{"role":role,"source_ref":ref} for role,ref in zip(("schedule","boxscore"),final_refs)],"captured_at":stamp(common.now())}
        pack_ref=self.archive.put_json(pack,tag=common.archive_month(common.now()))
        self.current.mode="PROSPECTIVE_RESEARCH"
        result=self.current._grade(self.case.store,{"player_ids":[bodies[0]["player_id"]]},self.case.input_ref,pack_ref)
        self.assertEqual(result["grades"],1);self.assertEqual(result["unscored_originals"],[bodies[0]["player_id"]+":K0"])
        recovered=self.case.store.recover();self.assertEqual(len(recovered["forecasts"]),2)
        self.assertEqual(len(recovered["outcomes"]),1);self.assertEqual(len(recovered["grades"]),1)
        self.assertEqual(recovered["grades"][0][1]["model_key"],"R0")
        outcome_ref=recovered["outcomes"][0][0]
        payload=self.case.store.ledger.read(outcome_ref)
        self.assertEqual(len(payload["references"]),2)

    def test_many_readonly_shard_recoveries_keep_constant_disk_and_preserve_worker_state(self):
        retained=self.current.root/"retained-worker-original";retained.write_bytes(b"Keep unacknowledged worker bytes.")
        baseline=self.current._runtime_guard()["actual_bytes"]
        def materialize(task,*,work_root=None):
            self.assertIsNotNone(work_root)
            (work_root/"invented-recovered-cache").write_bytes(b"x"*2048)
            return object(),object()
        with patch.object(self.current,"_store",side_effect=materialize):
            for _ in range(128):
                with self.current._read_store({}):
                    self.assertEqual(self.current._runtime_guard()["actual_bytes"],baseline+2048)
                self.assertEqual(self.current._runtime_guard()["actual_bytes"],baseline)
        self.assertEqual(list(self.current.root.glob("read-only-*")),[])
        self.assertEqual(retained.read_bytes(),b"Keep unacknowledged worker bytes.")

    def test_runtime_budget_rejects_before_materializing_or_collecting(self):
        maximum=common.make_policy()["runtime_disk_bytes"]
        with patch.object(self.current,"_directory_bytes",return_value=maximum),patch.object(self.current,"store_factory") as factory:
            with self.assertRaisesRegex(IntegrityError,"disk budget"):self.current._store({})
            factory.assert_not_called()
            self.assertEqual(self.current.prepare_tasks(),[])
        self.assertEqual(self.calls,[]);self.assertEqual(self.current.registry["attempts"],[])

    def test_captured_input_pack_is_recovered_after_registration_interruption_without_get(self):
        self.planned();self.fixture.now=self.case.start-timedelta(minutes=140)
        day=self.current.registry["days"][0];plan=self.archive.get_json(day["plan_ref"]);event=plan["events"][0]
        original,_=self.current._capture("INPUT",[event["cycle_id"]],season=2027,
            opens=common.clock(event["capture_opens_at"]),closes=common.clock(event["cutoff_at"]))
        self.assertIsNone(self.current.registry["days"][0]["shards"][0]["input_task_ref"])
        calls=len(self.calls);registry=deepcopy(self.current.registry)
        self.fixture.now=self.case.start-timedelta(minutes=100)
        self.current=self.coordinator(registry);tasks=self.current.prepare_tasks()
        self.assertEqual([task["action"] for task in tasks],["PREPARE"]);self.assertEqual(len(self.calls),calls)
        task=self.archive.get_json(tasks[0]["task_ref"])
        self.assertEqual(task["input_source_pack_ref"],original)
        self.assertEqual(self.archive.get_json(task["input_ref"])["normalized_at"],stamp(self.fixture.now))

    def test_closed_windows_report_unobserved_state_without_replacement_capture(self):
        self.fixture.now=utc("2026-10-23T14:01:00.000000Z")
        self.assertEqual(self.current.prepare_tasks(),[]);self.assertEqual(self.calls,[])
        status=self.current._window_status()
        self.assertEqual(status["reason"],"INCOMPLETE_OR_UNOBSERVED_WINDOW")
        self.assertEqual(status["affected_game_dates"],["2026-10-24"])
        self.fixture.now=utc("2026-10-23T13:17:00.000000Z");self.current=self.coordinator();self.planned()
        self.fixture.now=self.case.cutoff+timedelta(minutes=16)
        self.assertEqual(self.current.prepare_tasks(),[]);self.assertEqual(len(self.calls),1)
        status=self.current._window_status();self.assertEqual(status["unacknowledged_issuance_shards"],1)
        self.assertEqual(len(status["affected_branches"]),1)
        self.assertIsNone(self.current.registry["days"][0]["shards"][0]["input_task_ref"])
        with patch.object(self.current,"_save",wraps=self.current._save) as saved:self.current.refresh()
        self.assertEqual(saved.call_args.args[1]["reason"],"INCOMPLETE_OR_UNOBSERVED_WINDOW")

    def test_two_shard_task_archive_interruption_retries_exact_original_input_atomically(self):
        originals=deepcopy(self.fixture.roster);self.fixture.roster=[]
        for original in originals:
            for index in range(10):
                row=deepcopy(original);pid=str(int(original["athlete_id"])+index)
                row.update(athlete_id=pid,uid="s:40~l:46~a:"+pid,display_name="Invented Player "+pid)
                self.fixture.roster.append(row)
        self.current.prepare_tasks();self.assertEqual(len(self.current.registry["days"][0]["shards"]),2)
        self.fixture.now=self.case.start-timedelta(minutes=140)
        original_put=self.archive.put_json;attempts=[];inputs_seen=[]
        def interrupted(body,**kwargs):
            if body.get("schema_version") == engine.TASK_SCHEMA:
                attempts.append(body["task_id"]);inputs_seen.append(body["input_ref"])
                if len(attempts) == 2:raise IntegrityError("Invented second task archive interruption")
            return original_put(body,**kwargs)
        with patch.object(self.archive,"put_json",side_effect=interrupted):self.assertEqual(self.current.prepare_tasks(),[])
        day=self.current.registry["days"][0]
        self.assertTrue(all(shard["input_task_ref"] is None for shard in day["shards"]))
        self.assertEqual(len(day["pending_inputs"]),1)
        pending=deepcopy(day["pending_inputs"][0]);original_body=self.archive.get_json(pending["input_ref"])
        self.assertEqual(inputs_seen,[pending["input_ref"],pending["input_ref"]])
        calls=len(self.calls);self.fixture.now+=timedelta(minutes=1)
        self.current=self.coordinator(deepcopy(self.current.registry));tasks=self.current.prepare_tasks()
        self.assertEqual([row["action"] for row in tasks],["PREPARE","PREPARE"])
        self.assertEqual(len(self.calls),calls);self.assertEqual(self.current.registry["days"][0]["pending_inputs"],[])
        for descriptor in tasks:
            task=self.archive.get_json(descriptor["task_ref"])
            self.assertEqual(task["input_ref"],pending["input_ref"])
            self.assertEqual(task["input_source_pack_ref"],pending["input_source_pack_ref"])
            self.assertEqual(self.archive.get_json(task["input_ref"]),original_body)

    def test_changed_task_reference_rejected_before_records_are_opened(self):
        self.prepared();self.fixture.now=self.case.cutoff+timedelta(seconds=1)
        task=self.current.prepare_tasks()[0];task["branch"]+="-changed"
        with self.assertRaisesRegex(IntegrityError,"immutable task"):self.current.work(task)


if __name__ == "__main__":unittest.main()

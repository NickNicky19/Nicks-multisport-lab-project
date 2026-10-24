"""Synthetic hosted authority and independent registry persistence, no sources."""
from copy import deepcopy
from contextlib import redirect_stdout
from datetime import timedelta
import io
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import hashlib
import re
import warnings

from multisport_lab import sdv_production_common as common
from multisport_lab import sdv_production_runner as runner
from multisport_lab import sdv_production_archive as archives
from multisport_lab.integrity import IntegrityError, canonical, stamp, utc


class ProductionRunnerTests(unittest.TestCase):
    def setUp(self):
        self.now=utc("2026-10-24T00:02:00.000000Z")
        self.clock=patch.object(common,"now",return_value=self.now);self.clock.start();self.addCleanup(self.clock.stop)
        self.binding={"schema_version":"nba-sdv-production-producer-binding-v1","commit":"1"*40,
            "files":{"multisport_lab/baseline.py":common.LAW_SHA256["R0"],"multisport_lab/development_003.py":common.LAW_SHA256["K0"]},
            "law_sha256":common.LAW_SHA256}
        self.binding=common.seal(self.binding,"binding_id")

    def authority(self,event="schedule"):
        body={"repository":{"full_name":common.REPOSITORY},"schedule":common.CRON}
        actor="github-actions[bot]"
        if event == "workflow_dispatch":
            actor=common.OWNER;body={"repository":{"full_name":common.REPOSITORY},"sender":{"login":actor},"inputs":{"mode":"operate"}}
        run={"id":123,"run_attempt":1,"event":event,"path":common.WORKFLOW,"head_sha":"1"*40,"head_branch":"main",
            "actor":{"login":actor},"triggering_actor":{"login":actor},"repository":{"full_name":common.REPOSITORY},
            "status":"in_progress","conclusion":None,"run_started_at":stamp(self.now)}
        return common.seal({"schema_version":common.AUTH_SCHEMA,"protocol_id":common.PROTOCOL_ID,"repository":common.REPOSITORY,
            "workflow_path":common.WORKFLOW,"event":event,"actor":actor,"run_id":123,"run_attempt":1,"head_sha":"1"*40,
            "run_started_at":stamp(self.now),"verified_at":stamp(self.now),"event_original":runner._encoded(canonical(body)),
            "run_original":runner._encoded(canonical(run)),"executed_files":self.binding["files"]},"authorization_id")

    def reseal(self,body):return common.seal({k:v for k,v in body.items() if k != "authorization_id"},"authorization_id")

    def test_issuance_attempt_status_rejects_checksum_consistent_wrong_meaning(self):
        details={"task_id":"a"*64,"shard_index":0,"player_ids":["1000"],"error":None,"final_source_pack_ref":None,"processing_complete":False}
        opened=stamp(self.now);attempt={"run_attempt":1,"attempt_number":1,"opened_at":opened,"open_status_id":None,
            "footprint_snapshot_ref":None,"footprint_snapshot_id":None,"footprint_recovered_at":None}
        attempt["attempt_id"]=hashlib.sha256(canonical({key:details[key] for key in ("task_id","shard_index","player_ids")}|{
            "run_id":123,"run_attempt":1,"attempt_number":1,"opened_at":opened})).hexdigest()
        details["issuance_attempt"]=attempt
        body=common.seal({"schema_version":common.STATUS_SCHEMA,"protocol_id":common.PROTOCOL_ID,"plan_id":"b"*64,
            "cycle_id":"prod-20261024-900-"+"c"*12,"phase":"ISSUE","status":runner.ISSUE_OPEN,"details":details,"observed_at":opened,"run_id":123},"status_id")
        runner.validate_body(body)
        for mutate in (lambda b:b.update(protocol_id="different"),lambda b:b.update(phase="GRADE"),
                lambda b:b["details"].update(processing_complete=True),lambda b:b["details"]["issuance_attempt"].update(attempt_number=2),
                lambda b:b["details"]["issuance_attempt"].update(open_status_id="f"*64),lambda b:b.update(status=runner.ISSUE_CLOSED)):
            wrong=deepcopy(body);mutate(wrong)
            wrong=common.seal({key:value for key,value in wrong.items() if key != "status_id"},"status_id")
            with self.subTest(wrong=wrong["status"]),self.assertRaises(IntegrityError):runner.validate_body(wrong)

    def test_production_emergency_artifacts_are_failure_only_narrow_and_temporary(self):
        text=(Path(__file__).resolve().parents[1]/".github/workflows/nba-operations.yml").read_text(encoding="utf-8")
        def job(name):
            start=text.index("\n  "+name+":\n")+1
            following=re.search(r"\n  [a-z][a-z-]*:\n",text[start+len(name)+4:])
            end=start+len(name)+4+following.start() if following else len(text)
            return text[start:end]
        for name in ("prepare","work","grade","finish"):
            with self.subTest(job=name):
                block=job(name);upload=block.split("uses: actions/upload-artifact@",1)[1]
                condition=block.split("uses: actions/upload-artifact@",1)[0].split("- name:")[-1]
                expected=("if: failure() || steps.prepare.outputs.has_failures == 'true'" if name == "prepare" else "if: failure()")
                self.assertIn(expected,condition)
                self.assertNotIn("if: always()",condition)
                self.assertIn("retention-days: 1\n",upload)
                self.assertNotIn("retention-days: 14",upload)
                paths=[line.strip() for line in upload.splitlines() if line.strip().startswith("${{ runner.temp }}")]
                if name == "finish":
                    self.assertEqual(paths,[])
                    self.assertIn("path: ${{ runner.temp }}/nml-production-finish/execution-report.json",upload)
                else:
                    prefix="${{ runner.temp }}/nml-production-"+name
                    self.assertEqual(paths,[prefix+"/execution-report.json",prefix+"/phases/originals/",prefix+"/phases/shards/*/records/"])
                    self.assertIn("include-hidden-files: true",upload)
                self.assertNotIn("/writers/",upload);self.assertNotIn("/.git",upload);self.assertNotIn("/archive/",upload)
        self.assertIn("needs: [prepare, work, capture-held]",job("grade-prepare"))
        self.assertIn("if: always() && needs.prepare.result == 'success'",job("grade-prepare"))
        self.assertIn("if: always() && needs.grade-prepare.result == 'success' && needs.grade-prepare.outputs.has_grade_tasks == 'true'",job("grade"))
        self.assertIn("fromJSON(needs.grade-prepare.outputs.grade_matrix)",job("grade"))
        self.assertIn("if: always() && needs.prepare.result == 'success'",job("finish"))
        diagnostic=job("diagnostic");self.assertIn("retention-days: 1\n",diagnostic)
        self.assertIn("DEVELOPMENT_ONLY",diagnostic);self.assertIn("include-hidden-files: true",diagnostic)
        self.assertIn("/nml-production-diagnostic/state/records/",diagnostic)
        self.assertNotIn("path: ${{ runner.temp }}/nml-production-diagnostic/\n",diagnostic)
        # Protect the original first-cycle job byte-for-byte: its separate
        # emergency path and fourteen-day retention were not part of this fix.
        first=text.split("  first-cycle-postgame:\n",1)[1].split("\n  diagnostic:",1)[0]
        self.assertEqual(hashlib.sha256(first.encode()).hexdigest(),"7fc9504dd80dcdf3e503ae3f224652a9fe782a7a7d31d3177e8c2a722182aef0")

    def test_stored_authority_requires_actual_run_semantics_with_valid_checksums(self):
        body=self.authority();self.assertIs(runner.validate_authorization(body),body)
        for mutate in (lambda b:b.update(actor=common.OWNER),lambda b:b.update(head_sha="2"*40),
                lambda b:b.update(run_attempt=2),lambda b:b.update(repository="another/repository")):
            bad=deepcopy(body);mutate(bad)
            with self.assertRaises(IntegrityError):runner.validate_authorization(self.reseal(bad))
        bad=deepcopy(body);event=runner._original(bad["event_original"],32768);event["schedule"]="* * * * *"
        bad["event_original"]=runner._encoded(canonical(event))
        with self.assertRaises(IntegrityError):runner.validate_authorization(self.reseal(bad))
        for field in ("repository","actor","triggering_actor"):
            bad=deepcopy(body);run=runner._original(bad["run_original"],384*1024);run[field]=None
            bad["run_original"]=runner._encoded(canonical(run))
            with self.subTest(field=field),self.assertRaises(IntegrityError):runner.validate_authorization(self.reseal(bad))

    def test_no_environment_cannot_probe_or_obtain_authority(self):
        with patch.dict(os.environ,{},clear=True),patch.object(runner,"_read_run") as request:
            with self.assertRaises(IntegrityError):runner.authorize_current_run()
            request.assert_not_called()

    def hosted_environment(self,event_path):
        return {"GITHUB_ACTIONS":"true","GITHUB_REPOSITORY":common.REPOSITORY,
            "GITHUB_REF":"refs/heads/main","GITHUB_WORKFLOW_REF":common.REPOSITORY+"/"+common.WORKFLOW+"@refs/heads/main",
            "GITHUB_EVENT_NAME":"schedule","GITHUB_ACTOR":"github-actions[bot]","GITHUB_TRIGGERING_ACTOR":"github-actions[bot]",
            "GITHUB_RUN_ID":"123","GITHUB_RUN_ATTEMPT":"1","GITHUB_SHA":"1"*40,"GITHUB_EVENT_PATH":str(event_path)}

    def test_module_entrypoint_shares_current_authority_with_real_coordinator(self):
        # Exercise the deployed -m entrypoint, not only imported functions. All
        # hosted bytes are invented; archive, Git and provider access are mocked.
        from multisport_lab.sdv_production_coordinator import Coordinator
        from multisport_lab import sdv_production_forecasts as forecasts
        auth=self.authority();event_raw=canonical(runner._original(auth["event_original"],32768))
        run_raw=canonical(runner._original(auth["run_original"],384*1024))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);event_path=root/"invented-event.json";event_path.write_bytes(event_raw)
            with patch.dict(os.environ,self.hosted_environment(event_path),clear=True),patch.dict(runner._CAPABILITIES,{},clear=True),\
                    patch.object(runner,"_read_run",return_value=run_raw) as request,\
                    patch.object(runner,"_git",return_value=SimpleNamespace(stdout=b"1"*40+b"\n")),\
                    patch.object(forecasts,"make_source_binding",return_value=self.binding),\
                    patch.object(archives,"GitHubReleaseArchive"),patch.object(runner,"RegistryWriter") as writer,\
                    patch.object(subprocess,"run",side_effect=AssertionError("No subprocess or live request in this synthetic entrypoint test")),\
                    patch.object(Coordinator,"prepare_tasks",return_value=[]) as tasks,\
                    patch.object(runner,"require_current_authority",wraps=runner.require_current_authority) as gate,\
                    patch.object(runner,"failure_alert") as alert,\
                    patch.object(sys,"argv",["multisport_lab.sdv_production_runner","prepare","--work-root",str(root/"work")]),\
                    redirect_stdout(io.StringIO()),warnings.catch_warnings():
                writer.return_value.prepare.return_value=runner.empty_registry(self.now)
                # runpy warns because this test imported the canonical module;
                # the real interpreter starts without that test import.
                warnings.filterwarnings("ignore",category=RuntimeWarning,module="runpy")
                with self.assertRaises(SystemExit) as exited:
                    runpy.run_module("multisport_lab.sdv_production_runner",run_name="__main__",alter_sys=True)
                self.assertEqual(exited.exception.code,0)
                self.assertEqual(request.call_count,1);tasks.assert_called_once();alert.assert_not_called()
                self.assertGreaterEqual(gate.call_count,1)
                report=runner._decode((root/"work/execution-report.json").read_bytes())
                self.assertEqual(report["status"],"NO_DUE_PHASE");self.assertEqual(report["genuine_issued"],0)
                observation=report["hosted_run_observation"]
                self.assertEqual(observation["status"],"VERIFIED_CURRENT_RUN")
                self.assertIn(observation["authorization_id"],runner._CAPABILITIES)
                self.assertEqual(observation["run_original"],runner._encoded(run_raw))

    def test_rejected_hosted_metadata_retains_originals_without_granting_capability(self):
        from multisport_lab import sdv_production_forecasts as forecasts
        auth=self.authority();event_raw=canonical(runner._original(auth["event_original"],32768))
        for field,value in (("status","queued"),("status","completed"),("head_branch","other"),
                ("id",124),("id",True),("conclusion","failure")):
            with self.subTest(field=field,value=value),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);event_path=root/"invented-event.json";event_path.write_bytes(event_raw)
                bad=runner._original(auth["run_original"],384*1024);bad[field]=value;run_raw=canonical(bad)
                with patch.dict(os.environ,self.hosted_environment(event_path),clear=True),patch.dict(runner._CAPABILITIES,{},clear=True),\
                        patch.object(runner,"_read_run",return_value=run_raw),\
                        patch.object(runner,"_git",return_value=SimpleNamespace(stdout=b"1"*40+b"\n")),\
                        patch.object(forecasts,"make_source_binding",return_value=self.binding),\
                        patch.object(archives,"GitHubReleaseArchive") as archive:
                    report=runner.execute("prepare",work_root=root/"work")
                    self.assertEqual(report["status"],"PARTIAL_OR_FAILED")
                    self.assertIn("Actual production run metadata differs: "+field,report["error"])
                    self.assertEqual(report["genuine_issued"],0);self.assertEqual(runner._CAPABILITIES,{})
                    archive.assert_not_called()
                    observation=report["hosted_run_observation"]
                    self.assertEqual(observation["status"],"UNVERIFIED_OR_REJECTED")
                    self.assertIsNone(observation["authorization_id"])
                    self.assertEqual(observation["event_original"],runner._encoded(event_raw))
                    self.assertEqual(observation["run_original"],runner._encoded(run_raw))
                    recovered=runner._decode((root/"work/execution-report.json").read_bytes())
                    self.assertEqual(recovered,report)
                    with self.assertRaisesRegex(IntegrityError,"not a new issuance capability"):
                        runner.require_current_authority(auth)

    def test_hosted_run_observation_retains_full_bounded_originals(self):
        from multisport_lab import sdv_production_forecasts as forecasts
        auth=self.authority()
        event=runner._original(auth["event_original"],32768);event["invented_padding"]=""
        event["invented_padding"]="x"*(32768-len(canonical(event)));event_raw=canonical(event)
        run=runner._original(auth["run_original"],384*1024);run["invented_padding"]=""
        run["invented_padding"]="x"*(384*1024-len(canonical(run)));run_raw=canonical(run)
        self.assertEqual(len(event_raw),32768);self.assertEqual(len(run_raw),384*1024)
        with tempfile.TemporaryDirectory() as directory:
            event_path=Path(directory)/"invented-event.json";event_path.write_bytes(event_raw);observation={}
            with patch.dict(os.environ,self.hosted_environment(event_path),clear=True),patch.dict(runner._CAPABILITIES,{},clear=True),\
                    patch.object(runner,"_read_run",return_value=run_raw),\
                    patch.object(runner,"_git",return_value=SimpleNamespace(stdout=b"1"*40+b"\n")),\
                    patch.object(forecasts,"make_source_binding",return_value=self.binding):
                runner.authorize_current_run(observation=observation)
            self.assertLessEqual(len(canonical(observation)),640*1024)
            self.assertEqual(observation["event_original"],runner._encoded(event_raw))
            self.assertEqual(observation["run_original"],runner._encoded(run_raw))

    def test_recovered_auth_is_not_execution_capability_and_each_phase_uses_its_window(self):
        auth=self.authority();body={"mode":"PROSPECTIVE_RESEARCH","producer_binding":self.binding,
            "event":{"event_starts_at":"2026-10-24T01:30:00.000000Z"}}
        with self.assertRaisesRegex(IntegrityError,"capability"):
            runner.require_execution_context(auth,body,self.binding)
        runner._CAPABILITIES[auth["authorization_id"]]=auth["head_sha"]
        self.addCleanup(runner._CAPABILITIES.clear)
        original_run_id=os.environ.get("GITHUB_RUN_ID")
        with patch.dict(os.environ,{"GITHUB_RUN_ID":str(auth["run_id"])}),patch("multisport_lab.sdv_production_forecasts.validate_binding"):
            self.assertTrue(runner.require_execution_context(deepcopy(auth),body,self.binding))
            with patch.dict(os.environ,{"GITHUB_RUN_ID":str(auth["run_id"]+1)}):
                with self.assertRaisesRegex(IntegrityError,"Actual executing run changed"):
                    runner.require_execution_context(auth,body,self.binding)
            with self.assertRaisesRegex(IntegrityError,"PREPARE window"):
                runner.require_execution_context(auth,body,self.binding,phase="PREPARE")
            with patch.object(common,"now",return_value=self.now+timedelta(minutes=14)):
                with self.assertRaisesRegex(IntegrityError,"ISSUE window"):
                    runner.require_execution_context(auth,body,self.binding)
        self.assertEqual(os.environ.get("GITHUB_RUN_ID"),original_run_id)

    def test_failed_hosted_phase_is_durably_written_before_publication_reconciliation(self):
        from multisport_lab import sdv_production_coordinator as engine
        from multisport_lab import sdv_production_archive as archive_module
        events=[];initial=runner.empty_registry()
        coordinator=SimpleNamespace(registry=deepcopy(initial),refresh=lambda:[])
        def write(body):
            events.append(("write",body["status"]))
            return common.seal({key:deepcopy(value) for key,value in body.items() if key != "registry_id"},"registry_id")
        writer=SimpleNamespace(prepare=lambda:deepcopy(initial),write=write)
        def reconcile(body,actual_writer,archive):
            self.assertIs(actual_writer,writer)
            self.assertEqual(body["status"],"HOSTED_PHASES_PARTIAL_OR_FAILED")
            self.assertEqual(body["last_run"]["details"]["PRODUCTION_PREGAME_RESULT"],"failure")
            self.assertIs(coordinator.registry,body)
            self.assertEqual(events,[("write","HOSTED_PHASES_PARTIAL_OR_FAILED")])
            events.append(("publish",body["registry_id"]))
            return body
        with tempfile.TemporaryDirectory(prefix="nml-finish-order-") as directory, \
                patch.object(runner,"authorize_current_run",return_value={"run_id":123,"run_attempt":1}), \
                patch.object(runner,"RegistryWriter",return_value=writer), \
                patch.object(archive_module,"GitHubReleaseArchive"), \
                patch.object(engine,"Coordinator",return_value=coordinator), \
                patch.object(runner,"reconcile_publication",side_effect=reconcile), \
                patch.object(runner,"failure_alert",return_value={"status":"EXISTING_DAILY_ALERT"}), \
                patch.dict(os.environ,{"PRODUCTION_PREPARE_HAS_FAILURES":"false","PRODUCTION_PREGAME_RESULT":"failure", \
                    "PRODUCTION_GRADE_RESULT":"skipped","PRODUCTION_CAPTURE_RESULT":"success","PRODUCTION_GRADE_PREPARE_RESULT":"success"}):
            report=runner.execute("finish",work_root=directory,policy_version="v2")
        self.assertEqual(report["status"],"PARTIAL_OR_FAILED")
        self.assertEqual(len(events),2)
        self.assertEqual(coordinator.registry["status"],"HOSTED_PHASES_PARTIAL_OR_FAILED")

    def test_index_survives_new_object_database_and_refuses_conflicting_writers(self):
        with tempfile.TemporaryDirectory(prefix="nml-prod-registry-test-") as directory:
            root=Path(directory);remote=root/"remote.git";archive=archives.FileArchive(root/"archive")
            subprocess.run(["git","init","--bare","--quiet",str(remote)],check=True)
            first=runner.RegistryWriter(root/"first",archive=archive,remote_url=remote,allow_local_test_remote=True)
            registry=first.prepare()
            row=runner.reserve_capture(registry,first,phase="PLAN",scope=["2026-10-25"],at=self.now)
            registry["attempts"].append(row);registry=first.write(registry)
            other=runner.RegistryWriter(root/"other",archive=archive,remote_url=remote,allow_local_test_remote=True)
            recovered=other.prepare();self.assertEqual(recovered,registry);self.assertEqual(other.commit,first.commit)
            original_commit=first.commit
            registry["status"]="CAPTURE_FAILED";registry=first.write(registry)
            pinned=runner.RegistryWriter(root/"pinned",archive=archive,remote_url=remote,allow_local_test_remote=True)
            pinned_old=pinned.prepare(commit=original_commit)
            self.assertEqual(pinned_old["status"],"NOT_STARTED")
            with self.assertRaisesRegex(IntegrityError,"read-only"):pinned.write(pinned_old)
            recovered["status"]="STALE_WRITER"
            with self.assertRaises(IntegrityError):other.write(recovered)
            self.assertNotEqual(first.commit,original_commit)
            last=runner.RegistryWriter(root/"last",archive=archive,remote_url=remote,allow_local_test_remote=True)
            self.assertEqual(last.prepare(),registry)

    def test_thin_registry_pointer_retains_originals_and_ignores_volatile_only_ticks(self):
        with tempfile.TemporaryDirectory(prefix="nml-prod-thin-pointer-") as directory:
            root=Path(directory);remote=root/"remote.git";archive=archives.FileArchive(root/"archive")
            subprocess.run(["git","init","--bare","--quiet",str(remote)],check=True)
            writer=runner.RegistryWriter(root/"writer",archive=archive,remote_url=remote,allow_local_test_remote=True)
            retained=writer.write(writer.prepare());commit=writer.commit;charged=archive.new_bytes_reserved
            pointer=runner._decode((root/"writer"/runner.INDEX_PATH).read_bytes())
            runner.validate_index_pointer(pointer)
            self.assertLessEqual(len(canonical(pointer)),4096)
            self.assertEqual(b"".join(archive.get(ref,max_raw_bytes=1024*1024) for ref in pointer["chunks"]),canonical(retained))
            tick=deepcopy(retained);tick["last_run"]={"run_id":991,"run_attempt":1,"observed_at":stamp(self.now),"status":"CHECKED","details":{}}
            self.assertEqual(writer.write(tick),retained)
            self.assertEqual(writer.commit,commit);self.assertEqual(archive.new_bytes_reserved,charged)
            tick["last_run"]["details"]={"reason":"INCOMPLETE_OR_UNOBSERVED_WINDOW","missed_planning_dates":1}
            changed=writer.write(tick);self.assertNotEqual(writer.commit,commit)
            fresh=runner.RegistryWriter(root/"fresh",archive=archives.FileArchive(root/"archive"),remote_url=remote,allow_local_test_remote=True)
            self.assertEqual(fresh.prepare(commit=commit),retained)
            self.assertEqual(changed["last_run"]["details"]["missed_planning_dates"],1)
            corrupt=deepcopy(pointer);corrupt["raw_sha256"]="f"*64
            corrupt=common.seal({k:v for k,v in corrupt.items() if k != "pointer_id"},"pointer_id")
            # Pointer integrity is semantic too: archived original bytes must
            # match the selected sealed digest, even if the pointer re-seals.
            with patch.object(archives.FileArchive,"get",return_value=b"invalid"):
                bad=runner.RegistryWriter(root/"bad",archive=archive,remote_url=remote,allow_local_test_remote=True)
                with self.assertRaises(IntegrityError):bad.prepare(commit=commit)

    def test_global_reservation_funds_byte_and_object_roles_without_calendar_expiry(self):
        from multisport_lab.sdv_production_store import empty_capacity,archive_liability
        capacity=empty_capacity();rows=[{"branch":"records/sdv-prod-20261024-900-"+"a"*12+"-s0","snapshot_ref":None,"capacity":capacity}]
        budget=runner.make_archive_budget(rows)
        self.assertEqual(budget["reserved_bytes"],archive_liability(capacity)+14*(2*64*1024*1024+2*1024*1024)+16*16*1024*1024+512*1024*1024)
        self.assertEqual(budget["reserved_objects"],runner.archive_object_liability(capacity)+1876+256+4096)
        later=self.now+timedelta(days=8)
        with patch.object(common,"now",return_value=later):
            self.assertEqual(runner.make_archive_budget(rows)["reserved_bytes"],budget["reserved_bytes"])
            self.assertEqual(runner.make_archive_budget(rows)["reserved_objects"],budget["reserved_objects"])
        for key in ("reserved_bytes","reserved_objects"):
            forged=deepcopy(budget);forged[key]-=1
            forged=common.seal({k:v for k,v in forged.items() if k != "budget_id"},"budget_id")
            with self.assertRaises(IntegrityError):runner.validate_archive_budget(forged)
        self.assertGreater(315*runner.archive_object_liability(capacity),100000)
        # Byte safety does not claim that 315 entirely unused shards fit the
        # independent immutable object ceiling.
        self.assertLess(315*archive_liability(capacity)+budget["shared_source_bytes"]+budget["parallel_headroom_bytes"]+budget["shared_metadata_bytes"],32*1024**3)

    def test_durable_unknown_attempt_consumes_full_budget_without_reset(self):
        registry=runner.empty_registry(self.now)
        for index in range(4):
            row=runner.reserve_capture(registry,None,phase="INPUT",scope=[str(index)],at=self.now)
            registry["attempts"].append(row)
        with self.assertRaisesRegex(IntegrityError,"GET budget"):
            runner.reserve_capture(registry,None,phase="INPUT",scope=["next"],at=self.now)
        registry=runner.empty_registry(self.now)
        for index in range(2):
            registry["attempts"].append(runner.reserve_capture(registry,None,phase="INPUT",scope=["event"],at=self.now+timedelta(hours=index)))
        with self.assertRaisesRegex(IntegrityError,"attempt limit"):
            runner.reserve_capture(registry,None,phase="INPUT",scope=["event"],at=self.now+timedelta(hours=2))

    def test_resealed_future_reservations_cannot_restore_get_budget(self):
        registry=runner.empty_registry(self.now)
        row=runner.reserve_capture(registry,None,phase="INPUT",scope=["event"],at=self.now)
        registry["attempts"].append(row)
        registry=common.seal({k:v for k,v in registry.items() if k != "registry_id"},"registry_id")
        runner.validate_registry(registry)
        bad=deepcopy(registry);bad["attempts"][0]["started_at"]=stamp(self.now+timedelta(days=1))
        bad=common.seal({k:v for k,v in bad.items() if k != "registry_id"},"registry_id")
        with self.assertRaises(IntegrityError):runner.validate_registry(bad)
        bad=deepcopy(registry);bad["attempts"][0]["phase"]="FINAL"
        bad=common.seal({k:v for k,v in bad.items() if k != "registry_id"},"registry_id")
        with self.assertRaisesRegex(IntegrityError,"identity differs"):runner.validate_registry(bad)
        with tempfile.TemporaryDirectory(prefix="nml-prod-reservation-monotonic-") as directory:
            root=Path(directory);remote=root/'remote.git';archive=archives.FileArchive(root/'archive')
            subprocess.run(['git','init','--bare','--quiet',str(remote)],check=True)
            writer=runner.RegistryWriter(root/'writer',archive=archive,remote_url=remote,allow_local_test_remote=True)
            writer.prepare();retained=writer.write(registry)
            changed=deepcopy(retained);changed['attempts']=[]
            with self.assertRaisesRegex(IntegrityError,'erase a source reservation'):writer.write(changed)

    def test_single_local_writer_and_source_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            with runner.retained_lock(directory):
                with self.assertRaisesRegex(IntegrityError,"writer is active"):
                    with runner.retained_lock(directory):self.fail("Second writer entered")
        self.assertEqual([r["role"] for r in runner.source_routes(2027)],["schedule","roster"])
        self.assertEqual([r["role"] for r in runner.source_routes(2027,final=True)],["schedule","boxscore"])
        with self.assertRaises(IntegrityError):runner.source_routes(True)

    def test_source_collection_cannot_start_without_real_run_capability(self):
        with patch("multisport_lab.sdv_daily_runner.BoundedCapture") as capture:
            with self.assertRaises(IntegrityError):
                runner.collect_sources("/tmp/not-used",None,season=2027,tag="nml-nba-records-v1-202610",
                    opens_at=self.now,closes_at=self.now+timedelta(hours=1))
            capture.assert_not_called()

    def test_typed_served_index_and_assets_are_verified_not_dispatch_acceptance(self):
        from multisport_lab import sdv_production_publication as public
        registry=runner.empty_registry(self.now)
        index,_=public.make_publication([],now=self.now,registry=registry)
        index_raw=canonical(index);sha=hashlib.sha256(index_raw).hexdigest()
        descriptor={"path":"sdv-production."+sha+".json","sha256":sha,"generated_at":index["generated_at"],
            "status":public.STATUS,"retained":False,"error":None}
        manifest={"build_commit":"1"*40,"production_research":descriptor}
        bodies={"manifest.json":canonical(manifest),descriptor["path"]:index_raw}
        with patch.object(runner,"_public_get",side_effect=lambda path,limit:bodies[path]):
            proof=runner.verify_publication(registry["registry_id"])
            self.assertEqual(proof["served_build_commit"],"1"*40)
            self.assertEqual(proof["counts"]["genuine_forecasts"],0)
            with self.assertRaisesRegex(IntegrityError,"earlier registry"):runner.verify_publication("2"*64)
        bodies[descriptor["path"]]=index_raw+b" "
        with patch.object(runner,"_public_get",side_effect=lambda path,limit:bodies[path]):
            with self.assertRaisesRegex(IntegrityError,"hash differs"):runner.verify_publication(registry["registry_id"])

    def test_new_operational_failure_and_its_clearance_publish_without_forecasts(self):
        registry=runner.empty_registry(self.now)
        writer=SimpleNamespace(write=lambda body:body,commit="1"*40)
        with patch.object(runner.subprocess,"run",return_value=SimpleNamespace(returncode=0)) as dispatch:
            runner.reconcile_publication(registry,writer,None);dispatch.assert_not_called()
            row=runner.reserve_capture(registry,None,phase="PLAN",scope=["2026-10-25"],at=self.now)
            row["status"]="FAILED";registry["attempts"].append(row)
            retained=runner.reconcile_publication(registry,writer,None)
            self.assertEqual(retained["publication"]["state"],"DISPATCH_REQUESTED")
            self.assertEqual(dispatch.call_count,1)
            # Simulate independently verified publication; an actual successful
            # replacement capture must clear the visitor's stale error even
            # before forecast records exist. No real dispatch occurs here.
            retained["publication"]["state"]="PUBLICATION_VERIFIED"
            with tempfile.TemporaryDirectory() as archive_directory:
                ref=archives.FileArchive(archive_directory).put_json({"synthetic_not_a_source_original":True},tag="nml-nba-records-v1-202610")
            # The content identity only projects a reference. Strict original
            # source admission is independently exercised by persistence tests.
            retained["attempts"][0].update(status="CAPTURED",used_gets=4,source_pack_ref=ref)
            runner.reconcile_publication(retained,writer,None)
            self.assertEqual(dispatch.call_count,2)

    def test_early_interruption_report_never_claims_completed_operating_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.object(runner,"authorize_current_run",side_effect=KeyboardInterrupt("invented early SIGINT")):
                with self.assertRaises(KeyboardInterrupt):runner.execute("prepare",work_root=root/"work")
            report=runner._decode((root/"work/execution-report.json").read_bytes())
            self.assertEqual(report["status"],"PARTIAL_OR_FAILED")
            self.assertIn("KeyboardInterrupt",report["error"])
            self.assertEqual(report["qualified_tickets"],0)

    def test_source_request_chain_must_authenticate_exact_consumed_bodies(self):
        from multisport_lab import sdv_production_inputs as inputs
        from multisport_lab.sdv_production_archive import FileArchive
        from test_sdv_daily_inputs import fixtures,csv_bytes
        _,_,schedule,roster,_=fixtures()
        raw_s,raw_r=csv_bytes(schedule),csv_bytes(roster)
        original_time=self.now
        self.now-=timedelta(minutes=10)
        auth=self.authority()
        self.now=original_time
        requests=[];sources=[]
        with tempfile.TemporaryDirectory() as directory:
            archive=FileArchive(directory);tag="nml-nba-records-v1-202610"
            for index,(role,raw) in enumerate((("schedule",raw_s),("roster",raw_r))):
                route=runner.source_routes(2027)[index]
                start=self.now-timedelta(minutes=8-index*4);meta_end=start+timedelta(seconds=10)
                asset_start=start+timedelta(seconds=20);asset_end=start+timedelta(seconds=30)
                original=canonical({"tag_name":route["release_tag"],"assets":[{"id":index+1,"name":route["asset_name"],
                    "browser_download_url":route["asset_url"],"size":len(raw),"digest":"sha256:"+hashlib.sha256(raw).hexdigest(),
                    "updated_at":stamp(self.now-timedelta(hours=1))}]})
                meta=inputs.source_metadata(raw,original,route,retrieval_started_at=asset_start,retrieved_at=asset_end,
                    metadata_retrieval_started_at=start,metadata_retrieved_at=meta_end)
                sources.append({"role":role,"metadata":meta,"source_ref":archive.retain_source(raw,meta,original,tag=tag)})
                for url,body,beg,end,limit in ((route["metadata_url"],original,start,meta_end,common.make_policy()["maximum_metadata_bytes"]),
                        (route["asset_url"],raw,asset_start,asset_end,common.make_policy()["maximum_csv_bytes"])):
                    requests.append({"request_number":len(requests)+1,"route":url,"status":200,"automatic_redirects":False,
                        "automatic_retries":0,"retrieval_started_at":stamp(beg),"retrieved_at":stamp(end),"response_limit_bytes":limit,
                        "bytes":len(body),"sha256":hashlib.sha256(body).hexdigest()})
            pack=common.seal({"schema_version":runner.SOURCE_PACK_SCHEMA,"protocol_id":common.PROTOCOL_ID,"sources":sources,
                "requests":requests,"captured_at":stamp(self.now),"attribution":runner.source_attribution(),"authorization":auth},"source_pack_id")
            ref=archive.put_json(pack,tag=tag)
            recovered,raws=runner.recover_source_pack(ref,archive)
            self.assertEqual(raws["schedule"][0],raw_s)
            for key,value in (("route","https://github.com/unrelated/not-the-source"),("sha256","f"*64),("bytes",1)):
                forged=deepcopy(pack);forged["requests"][0][key]=value
                forged=common.seal({k:v for k,v in forged.items() if k != "source_pack_id"},"source_pack_id")
                with self.subTest(key=key),self.assertRaises(IntegrityError):
                    runner.recover_source_pack(archive.put_json(forged,tag=tag),archive)


if __name__ == "__main__":unittest.main()

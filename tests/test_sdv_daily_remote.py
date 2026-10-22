"""Local bare-Git recovery tests: no HTTP, genuine issuance or provider access."""
from datetime import timedelta
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import sdv_daily_inputs as inputs
from multisport_lab import sdv_daily_store as stores
from multisport_lab import sdv_daily_remote as remote
from multisport_lab import ledger
from multisport_lab.integrity import IntegrityError
from test_sdv_daily_inputs import fixtures,csv_bytes
from test_sdv_daily_store import original


class DailyRemoteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name);self.root=self.folder/"source";self.root.mkdir()
        self.bare=self.folder/"remote.git";self.writer=self.folder/"writer"
        self.start,self.at,schedule,roster,expected=fixtures();self.current=self.at
        for module in (inputs,stores,ledger,remote):
            clock=patch.object(module,"_now",side_effect=lambda:self.current)
            clock.start();self.addCleanup(clock.stop)
        self.git("init","--quiet",cwd=self.root)
        self.git("init","--bare","--quiet",str(self.bare),cwd=self.folder)
        self.git("config","user.name","Daily Test",cwd=self.root)
        self.git("config","user.email","test@example.invalid",cwd=self.root)
        self.original=ledger.Ledger(self.root).append("input_captures","kept",{"identity":{"legacy":"kept"}})
        self.git("add","records",cwd=self.root);self.git("commit","--quiet","-m","Synthetic baseline",cwd=self.root)
        self.base=self.git("rev-parse","HEAD",cwd=self.root).stdout.strip()
        self.git("remote","add","origin",str(self.bare),cwd=self.root)
        self.git("push","origin","HEAD:refs/heads/main",cwd=self.root)
        self.store=stores.DailyStore(self.root)
        originals=[];refs=[]
        for role,rows in (("schedule",schedule),("roster",roster)):
            raw=csv_bytes(rows);meta,witness=original(raw,role,self.at)
            originals.append((raw,meta));refs.append(self.store.retain_asset(raw,meta,witness))
        body=inputs.normalize_inputs(originals[0][0],originals[1][0],originals[0][1],originals[1][1],
            event_id="900",expected_candidates=expected,normalized_at=self.at)
        self.input_ref=self.store.persist_input(body,refs)
        self.store.record_completion(self.input_ref,started_at=self.at)
        self.checkpoint=remote.DailyGitCheckpointWriter(self.root,self.writer,base_commit=self.base,
            branch="diagnostics/sdv-daily-unit-test",remote_url=str(self.bare),allow_local_test_remote=True)
        self.checkpoint.prepare()

    def git(self,*args,cwd):
        return subprocess.run(["git",*args],cwd=cwd,capture_output=True,text=True,check=True,timeout=30)

    def test_originals_and_post_readback_proof_survive_independent_git_recovery_and_retry(self):
        before=self.store.ledger._path(self.input_ref.kind,self.input_ref.record_id).read_bytes()
        result=self.checkpoint.checkpoint(self.input_ref)
        self.assertNotEqual(result["originals_commit"],result["commit"])
        self.assertEqual(result["proof_recovered_records"],6)
        self.assertFalse(result["metadata_acknowledgment_recursive"])
        self.assertEqual(before,self.store.ledger._path(self.input_ref.kind,self.input_ref.record_id).read_bytes())
        clone=self.folder/"independent"
        self.git("clone","--quiet","--branch",self.checkpoint.branch,str(self.bare),str(clone),cwd=self.folder)
        recovered=stores.DailyStore(clone).recover()
        self.assertEqual(len(recovered["records"]),6)
        self.assertEqual(recovered["genuine_issued"],0)
        self.assertEqual(ledger.Ledger(clone).read(self.original)["data"]["identity"],{"legacy":"kept"})
        first_stages=[(ref,body) for ref,body in self.store.records() if body["schema_version"] == stores.COMPLETION_SCHEMA]
        second=self.checkpoint.checkpoint(self.input_ref)
        self.assertEqual(second["commit"],result["commit"])
        self.assertEqual(first_stages,[(ref,body) for ref,body in self.store.records() if body["schema_version"] == stores.COMPLETION_SCHEMA])

    def test_interruption_after_push_preserves_original_unacknowledged_then_exact_retry(self):
        with patch.object(self.checkpoint,"_readback",side_effect=IntegrityError("synthetic readback interruption")):
            with self.assertRaisesRegex(IntegrityError,"interruption"):
                self.checkpoint.checkpoint(self.input_ref)
        status=stores.DailyStore(self.root).admission(self.input_ref)
        self.assertIn("FINAL_RECOVERY_UNACKNOWLEDGED",status["reasons"])
        self.assertFalse(status["eligible"])
        old_ref=self.input_ref
        self.current+=timedelta(seconds=2)
        retried=self.checkpoint.checkpoint(old_ref)
        self.assertEqual(retried["proof_recovered_records"],6)
        self.assertEqual(stores.DailyStore(self.root).recover()["inputs"][0][0],old_ref)
        self.assertEqual(len([body for _,body in self.store.records() if body["schema_version"] == stores.COMPLETION_SCHEMA]),3)

    def test_actual_writer_boundary_records_genuine_input_acks_without_issuance(self):
        # Synthetic source bytes/clock; only an input exists, never a forecast.
        assets=[(ref,body) for ref,body in self.store.records() if body["schema_version"] == stores.ASSET_SCHEMA]
        by_role={body["metadata"]["role"]:(ref,self.store.read_asset(ref)) for ref,body in assets}
        dev=self.store.ledger.read(self.input_ref)["data"]["daily"]
        sr,sm,_=by_role["schedule"][1];rr,rm,_=by_role["roster"][1]
        body=inputs.normalize_inputs(sr,rr,sm,rm,event_id="900",expected_candidates=dev["candidates"],mode="PROSPECTIVE_RESEARCH")
        ref=self.store.persist_input(body,[by_role["schedule"][0],by_role["roster"][0]])
        self.store.record_completion(ref,started_at=self.at)
        result=self.checkpoint.checkpoint(ref)
        self.assertEqual(len(result["commit"]),40)
        self.assertTrue(self.store.admission(ref)["eligible"])
        self.assertEqual(self.store.recover()["genuine_issued"],0)

    def test_flush_preserves_partial_state_without_adding_acknowledgments(self):
        result=self.checkpoint.flush()
        self.assertEqual(result["issuance_acknowledgments_added"],0)
        self.assertEqual(result["recovered_records"],4)
        self.assertIn("FINAL_RECOVERY_UNACKNOWLEDGED",self.store.admission(self.input_ref)["reasons"])
        self.assertEqual(remote.snapshot_manifest(self.root),remote.snapshot_manifest(self.writer))

    def test_remote_newer_work_rejected_without_force_or_lost_originals(self):
        self.checkpoint.flush()
        clone=self.folder/"foreign"
        self.git("clone","--quiet","--branch",self.checkpoint.branch,str(self.bare),str(clone),cwd=self.folder)
        self.git("config","user.name","Other Writer",cwd=clone)
        self.git("config","user.email","other@example.invalid",cwd=clone)
        (clone/"newer.txt").write_text("legitimate newer work\n")
        self.git("add","newer.txt",cwd=clone);self.git("commit","--quiet","-m","Newer work",cwd=clone)
        self.git("push","origin","HEAD",cwd=clone)
        expected=self.git("rev-parse","HEAD",cwd=clone).stdout.strip()
        with self.assertRaises(IntegrityError):self.checkpoint.checkpoint(self.input_ref)
        actual=self.git("ls-remote",str(self.bare),"refs/heads/"+self.checkpoint.branch,cwd=self.folder).stdout.split()[0]
        self.assertEqual(actual,expected)
        self.assertTrue(self.store.ledger._path(self.input_ref.kind,self.input_ref.record_id).exists())


if __name__ == "__main__":unittest.main()

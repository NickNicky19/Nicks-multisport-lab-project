"""Actual local bare-Git/readback operations with invented typed receipts only."""
from datetime import timedelta
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from multisport_lab.integrity import IntegrityError
from multisport_lab import sdv_production_common as common
from multisport_lab import sdv_production_remote as remote
import test_sdv_production_store as store_fixture


class ProductionRemoteTests(unittest.TestCase):
    def setUp(self):
        self.case=store_fixture.ProductionStoreTests(
            "test_independent_archive_restart_keeps_exact_originals_and_all14_categories")
        self.case.setUp(); self.addCleanup(self.case.doCleanups)
        self.folder=self.case.folder
        self.git("init","--quiet","-b","main",cwd=self.case.source)
        self.git("add",".",cwd=self.case.source)
        self.git("-c","user.name=Synthetic Test","-c","user.email=synthetic@example.invalid",
                 "commit","--quiet","-m","Synthetic retained history",cwd=self.case.source)
        self.base=self.git("rev-parse","HEAD",cwd=self.case.source).stdout.decode().strip()
        self.bare=self.folder/"remote.git"
        self.git("init","--bare","--quiet",str(self.bare),cwd=self.folder)
        self.git("push",str(self.bare),"HEAD:refs/heads/main",cwd=self.case.source)
        self.branch="records/sdv-prod-20261024-900-0123456789ab-s0"

    def git(self,*args,cwd):
        value=subprocess.run(["git",*args],cwd=cwd,capture_output=True,timeout=20)
        self.assertEqual(value.returncode,0,value.stderr.decode(errors="replace"))
        return value

    def writer(self,name="writer"):
        return remote.ProductionGitCheckpointWriter(self.case.source,self.folder/name,
            base_commit=self.base,branch=self.branch,archive=self.case.archive,tag=store_fixture.TAG,
            remote_url=self.bare,allow_local_test_remote=True)

    def test_actual_git_push_fresh_database_recovery_and_idempotent_restart(self):
        refs,bodies=self.case.persisted_pair(ack=False)
        writer=self.writer();writer.prepare()
        proof=writer.checkpoint(self.case.store,refs)
        self.assertTrue(all(self.case.store.admission(ref)["eligible"] for ref in refs))
        self.assertFalse(proof["metadata_acknowledgment_recursive"])
        self.assertEqual(proof["recovered_records"],self.case.store.snapshot_manifest()["records"])
        original=self.case.store.snapshot_manifest()
        second=self.writer("restarted-writer");second.prepare()
        before=second._head
        observed=second.inspect()
        self.assertEqual(observed["commit"],proof["commit"])
        self.assertEqual(observed["snapshot_ref"],proof["snapshot_ref"])
        self.assertEqual(second._head,before)
        restored=self.case.new_store(self.folder/"restored")
        restored.source_resolver=None; restored.snapshot_resolver=None
        second.restore(restored)
        self.assertEqual(restored.snapshot_manifest(),original)
        self.assertEqual([restored.read_body(ref) for ref in refs],bodies)
        retry=second.checkpoint(restored,refs)
        self.assertEqual(restored.snapshot_manifest(),original)
        self.assertEqual(proof["commit"],retry["commit"])
        self.assertFalse((second.root/".git/objects/info/alternates").exists())

    def test_interrupted_readback_retains_originals_without_invented_completion(self):
        refs,bodies=self.case.persisted_pair(ack=False)
        writer=self.writer();writer.prepare()
        with patch.object(writer,"_readback",side_effect=IntegrityError("invented readback interruption")):
            with self.assertRaisesRegex(IntegrityError,"readback interruption"):
                writer.checkpoint(self.case.store,refs)
        self.assertTrue(all(not self.case.store.admission(ref)["eligible"] for ref in refs))
        second=self.writer("recovered-writer");second.prepare()
        restored=self.case.new_store(self.folder/"recovered-state");second.restore(restored)
        self.assertEqual([restored.read_body(ref) for ref in refs],bodies)
        self.assertTrue(all(not restored.admission(ref)["eligible"] for ref in refs))
        second.checkpoint(restored,refs)
        self.assertTrue(all(restored.admission(ref)["eligible"] for ref in refs))

    def test_late_actual_readback_is_retained_and_restart_never_admits_it(self):
        refs,bodies=self.case.persisted_pair(ack=False)
        writer=self.writer();writer.prepare()
        original=writer._readback
        def delayed(*args,**kwargs):
            self.case.fixture.now=self.case.cutoff+timedelta(seconds=601)
            return original(*args,**kwargs)
        with patch.object(writer,"_readback",side_effect=delayed):
            writer.checkpoint(self.case.store,refs)
        self.assertTrue(all(not self.case.store.admission(ref)["eligible"] for ref in refs))
        second=self.writer("late-restarted");second.prepare()
        restored=self.case.new_store(self.folder/"late-state");second.restore(restored)
        self.assertTrue(all(not restored.admission(ref)["eligible"] for ref in refs))
        self.assertEqual([restored.read_body(ref) for ref in refs],bodies)

    def test_timely_originals_and_later_proof_retention_keep_separate_clocks(self):
        refs,_=self.case.persisted_pair(ack=False)
        writer=self.writer();writer.prepare();original=writer._readback
        calls=[]
        def later_metadata(*args,**kwargs):
            if calls: self.case.fixture.now=self.case.cutoff+timedelta(seconds=901)
            calls.append(True)
            return original(*args,**kwargs)
        with patch.object(writer,"_readback",side_effect=later_metadata):
            proof=writer.checkpoint(self.case.store,refs)
        self.assertNotEqual(proof["original_records_recovered_at"],proof["proof_metadata_recovered_at"])
        self.assertTrue(all(self.case.store.admission(ref)["eligible"] for ref in refs))
        restored=self.case.new_store(self.folder/"later-proof-state")
        second=self.writer("later-proof-writer");second.prepare();second.restore(restored)
        self.assertTrue(all(restored.admission(ref)["eligible"] for ref in refs))

    def test_newer_remote_work_is_not_overwritten(self):
        writer=self.writer();writer.prepare();writer.flush(self.case.store)
        other=self.folder/"other"
        self.git("clone","--quiet","--single-branch","--branch",self.branch,str(self.bare),str(other),cwd=self.folder)
        (other/"newer-legitimate.txt").write_text("Preserve this work.\n")
        self.git("add","newer-legitimate.txt",cwd=other)
        self.git("-c","user.name=Synthetic Test","-c","user.email=synthetic@example.invalid",
            "commit","--quiet","-m","Newer legitimate test work",cwd=other)
        self.git("push",str(self.bare),"HEAD:refs/heads/"+self.branch,cwd=other)
        expected=self.git("rev-parse","HEAD",cwd=other).stdout
        with self.assertRaisesRegex(IntegrityError,"newer legitimate work"):
            writer.prepare()
        current=self.git("rev-parse","refs/heads/"+self.branch,cwd=self.bare).stdout
        self.assertEqual(current,expected)

    def test_interrupted_pointer_commit_recovers_without_including_unrelated_work(self):
        writer=self.writer();writer.prepare()
        original=writer._git
        def interrupted(*args,**kwargs):
            if "commit" in args: raise IntegrityError("invented interruption before commit")
            return original(*args,**kwargs)
        with patch.object(writer,"_git",side_effect=interrupted):
            with self.assertRaisesRegex(IntegrityError,"before commit"):
                writer.flush(self.case.store)
        writer.flush(self.case.store)
        retained=writer._head
        path=writer.root/"unrelated-owner-work.txt";path.write_text("Preserve me.\n")
        writer._git("add","unrelated-owner-work.txt")
        with self.assertRaisesRegex(IntegrityError,"unrelated work"):
            writer.flush(self.case.store)
        self.assertEqual(writer._head,retained)
        self.assertEqual(path.read_text(),"Preserve me.\n")

    def test_hardkill_forensic_files_survive_exact_git_archive_recovery_unadmitted(self):
        refs,bodies=self.case.persisted_pair(ack=False)
        folder=self.case.store.root/"records/forecasts"
        folder.mkdir(parents=True,exist_ok=True)
        originals={".receipt-empty":b"", ".receipt-interrupted":b'{"incomplete":'}
        for name,raw in originals.items(): (folder/name).write_bytes(raw)
        writer=self.writer();writer.prepare();proof=writer.checkpoint(self.case.store,refs)
        manifest=self.case.store.snapshot_manifest()
        self.assertEqual(len(manifest["unpublished_entries"]),2)
        second=self.writer("forensic-restart");second.prepare()
        restored=self.case.new_store(self.folder/"forensic-state");second.restore(restored)
        self.assertEqual(restored.snapshot_manifest(),manifest)
        self.assertEqual([restored.read_body(ref) for ref in refs],bodies)
        for name,raw in originals.items():
            self.assertEqual((restored.root/"records/forecasts"/name).read_bytes(),raw)
        self.assertEqual(proof["recovered_records"],manifest["records"])
        self.assertEqual(proof["recovered_unpublished_files"],2)
        self.assertEqual(proof["recovered_unpublished_bytes"],len(originals[".receipt-interrupted"]))
        self.assertEqual(len(restored.records()),manifest["records"])


if __name__ == "__main__": unittest.main()

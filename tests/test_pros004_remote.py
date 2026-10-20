"""Real local bare-Git checkpoint tests; no GitHub/source operations."""
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab.integrity import IntegrityError
from multisport_lab.ledger import Ledger
from multisport_lab.pros004_remote import GitCheckpointWriter, DIAGNOSTIC_BRANCH, validate_remote_plan
from multisport_lab import pros004_completion as completion


def git(root, *args):
    return subprocess.run(['git',*args],cwd=root,check=True,capture_output=True,text=True).stdout.strip()


class RemoteFixture:
    def __init__(self, case):
        self.tmp=tempfile.TemporaryDirectory();case.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.remote=self.root/'remote.git';self.remote.mkdir();git(self.remote,'init','--bare','--quiet')
        self.seed=self.root/'seed';self.seed.mkdir();git(self.seed,'init','--quiet')
        (self.seed/'README.md').write_text('Synthetic checkpoint test repository.\n')
        git(self.seed,'add','README.md')
        git(self.seed,'-c','user.name=Test','-c','user.email=test@example.invalid','commit','--quiet','-m','Seed')
        self.base=git(self.seed,'rev-parse','HEAD')
        git(self.seed,'remote','add','origin',str(self.remote));git(self.seed,'push','origin','HEAD:refs/heads/main')
        self.source=self.root/'source';self.store=Ledger(self.source)
        self.ref=self.store.append('input_captures','synthetic-first',{'note':'Synthetic checkpoint only'})
        self.writer=GitCheckpointWriter(self.source,self.root/'writer',base_commit=self.base,
            remote_url=str(self.remote),allow_local_test_remote=True)
        self.writer.prepare()


class Pros004RemoteTests(unittest.TestCase):
    def test_normal_push_independent_fetch_and_restart_exact_original(self):
        f=RemoteFixture(self)
        original=(f.source/'records'/f.ref.kind/(f.ref.record_id+'.json')).read_bytes()
        first=f.writer.checkpoint(f.ref)
        self.assertEqual(first['reference'],f.ref.to_record())
        self.assertEqual(first['readback_raw_sha256'],hashlib.sha256(original).hexdigest())
        self.assertEqual(git(f.remote,'rev-parse','refs/heads/'+DIAGNOSTIC_BRANCH),first['remote_commit'])
        reloaded=GitCheckpointWriter(f.source,f.root/'writer',base_commit=f.base,
            remote_url=str(f.remote),allow_local_test_remote=True)
        reloaded.prepare();second=reloaded.checkpoint(f.ref)
        self.assertEqual(first['remote_commit'],second['remote_commit'])
        self.assertGreaterEqual(second['remote_completed_at'],first['remote_completed_at'])
        self.assertEqual((f.source/'records'/f.ref.kind/(f.ref.record_id+'.json')).read_bytes(),original)

    def test_unacknowledged_push_retains_commit_and_exact_retry_does_not_regenerate(self):
        f=RemoteFixture(self)
        with patch.object(f.writer,'_readback',side_effect=OSError('independent fetch interrupted')):
            with self.assertRaisesRegex(OSError,'interrupted'):
                f.writer.checkpoint(f.ref)
        actual=git(f.remote,'rev-parse','refs/heads/'+DIAGNOSTIC_BRANCH)
        self.assertEqual(git(f.root/'writer','rev-parse','HEAD'),actual)
        recovered=f.writer.checkpoint(f.ref)
        self.assertEqual(recovered['remote_commit'],actual)

    def test_journal_prefix_is_remotely_retained_and_cannot_be_truncated(self):
        f=RemoteFixture(self)
        path=f.source/'records'/f.ref.kind/(f.ref.record_id+'.json')
        raw_sha=hashlib.sha256(path.read_bytes()).hexdigest()
        clock=datetime.now(timezone.utc)
        completion.append_completion(f.source,f.ref,mode='SYNTHETIC_DIAGNOSTIC',raw_sha256=raw_sha,
            completed_at=clock,recorded_at=clock)
        journal=f.source/completion.JOURNAL_RELATIVE_PATH
        original_prefix=journal.read_bytes()
        started=datetime.now(timezone.utc);first=f.writer.checkpoint(f.ref)
        ended=datetime.now(timezone.utc)
        completion.append_completion(f.source,f.ref,mode='SYNTHETIC_DIAGNOSTIC',raw_sha256=raw_sha,
            completed_at=ended,recorded_at=ended,started_at=started,acknowledgment=first)
        second=f.writer.checkpoint(f.ref)
        self.assertNotEqual(first['remote_commit'],second['remote_commit'])
        remote_journal=git(f.remote,'show',second['remote_commit']+':'+completion.JOURNAL_RELATIVE_PATH)
        self.assertEqual(remote_journal+'\n',journal.read_text())
        journal.write_bytes(original_prefix)
        with self.assertRaisesRegex(IntegrityError,'truncate'):
            f.writer.checkpoint(f.ref)
        self.assertEqual(git(f.remote,'rev-parse','refs/heads/'+DIAGNOSTIC_BRANCH),second['remote_commit'])

    def test_foreign_remote_head_is_not_overwritten(self):
        f=RemoteFixture(self);first=f.writer.checkpoint(f.ref)
        foreign=f.root/'foreign';git(f.root,'clone','--quiet','--branch',DIAGNOSTIC_BRANCH,str(f.remote),str(foreign))
        (foreign/'foreign.txt').write_text('Preserve newer legitimate work.\n')
        git(foreign,'add','foreign.txt')
        git(foreign,'-c','user.name=Test','-c','user.email=test@example.invalid','commit','--quiet','-m','Foreign')
        git(foreign,'push','origin','HEAD:refs/heads/'+DIAGNOSTIC_BRANCH)
        newer=git(foreign,'rev-parse','HEAD')
        with self.assertRaisesRegex(IntegrityError,'another writer'):
            f.writer.checkpoint(f.ref)
        self.assertEqual(git(f.remote,'rev-parse','refs/heads/'+DIAGNOSTIC_BRANCH),newer)
        self.assertNotEqual(newer,first['remote_commit'])

    def test_changed_or_missing_original_and_dirty_interruption_are_rejected(self):
        f=RemoteFixture(self);first=f.writer.checkpoint(f.ref)
        original=f.source/'records'/f.ref.kind/(f.ref.record_id+'.json')
        original.unlink()
        f.store.append('input_captures','other',{'note':'still synthetic'})
        with self.assertRaises(IntegrityError):f.writer.checkpoint(f.ref)
        self.assertEqual(git(f.remote,'rev-parse','refs/heads/'+DIAGNOSTIC_BRANCH),first['remote_commit'])
        (f.root/'writer'/'interrupted.txt').write_text('Retain partial local state')
        with self.assertRaisesRegex(IntegrityError,'interrupted'):
            f.writer.checkpoint(f.ref)

    def test_protected_branches_actual_mode_and_other_repositories_fail_closed(self):
        with self.assertRaisesRegex(IntegrityError,'isolated'):
            validate_remote_plan(branch='records/nba-20261020-401909088-t90')
        with self.assertRaisesRegex(IntegrityError,'authorized repository'):
            validate_remote_plan(branch=DIAGNOSTIC_BRANCH,remote_url='https://github.com/other/repository.git')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for kwargs in ({'diagnostic':False},{'branch':'main'},{'branch':'records/pros004-unapproved'}):
                with self.assertRaises(IntegrityError):
                    GitCheckpointWriter(root/'source',root/'writer',base_commit='a'*40,**kwargs)


if __name__=='__main__':
    unittest.main()

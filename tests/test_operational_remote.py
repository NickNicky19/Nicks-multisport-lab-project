"""OP002 diagnostic transport tests use isolated local Git, no providers."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from multisport_lab import operational_pilot as op
from multisport_lab import operational_remote as remote
from multisport_lab.integrity import IntegrityError,canonical,digest
from multisport_lab.ledger import Ledger
from multisport_lab.pros004_remote import GitCheckpointWriter,DIAGNOSTIC_BRANCH as OLD_BRANCH
from test_pros004_remote import RemoteFixture,git


class OperationalRemoteTests(unittest.TestCase):
    def fixture(self):
        f=RemoteFixture(self)
        f.writer=remote.OperatingDiagnosticWriter(f.source,f.root/'operating-writer',base_commit=f.base,
            remote_url=str(f.remote),allow_local_test_remote=True)
        f.writer.prepare();return f

    def test_named_guard_does_not_relax_old_writer_or_allow_real_writes(self):
        f=RemoteFixture(self)
        for kwargs in ({'branch':OLD_BRANCH},{'branch':'main'},{'diagnostic':False},
                       {'remote_url':'https://github.com/other/repository.git'}):
            with self.assertRaises(IntegrityError):
                remote.OperatingDiagnosticWriter(f.source,f.root/'unused',base_commit=f.base,**kwargs)
        with self.assertRaisesRegex(IntegrityError,'only the explicitly isolated'):
            GitCheckpointWriter(f.source,f.root/'unused',base_commit=f.base,branch=remote.DIAGNOSTIC_BRANCH)

    def test_real_git_fresh_typed_readback_restart_and_actual_telemetry(self):
        f=self.fixture();strict=op.verify_store;seen=[]
        def verify(root,**kwargs):seen.append(Path(root));return strict(root,**kwargs)
        with patch.object(op,'verify_store',side_effect=verify):ack=f.writer.checkpoint(f.ref)
        self.assertEqual(len(seen),2)
        self.assertEqual(seen[0],f.source)
        self.assertIn('op002-independent-',str(seen[1]))
        self.assertEqual(ack['schema_version'],op._schema('remote-checkpoint'))
        self.assertEqual(ack['remote_branch'],remote.DIAGNOSTIC_BRANCH)
        self.assertEqual(ack['journal_prefix_sha256'],hashlib.sha256(b'').hexdigest())
        self.assertEqual(ack['remote_commit'],git(f.remote,'rev-parse','refs/heads/'+remote.DIAGNOSTIC_BRANCH))
        entry=f.writer.operations[0]
        self.assertEqual(entry['status'],'PASS_FULL_TYPED_FRESH_FETCH')
        self.assertGreaterEqual(entry['wall_seconds'],entry['process_cpu_seconds'])
        self.assertGreaterEqual(entry['actual_completed_at'],entry['actual_started_at'])
        recovered=remote.OperatingDiagnosticWriter(f.source,f.writer.root,base_commit=f.base,
            remote_url=str(f.remote),allow_local_test_remote=True)
        recovered.prepare();second=recovered.checkpoint(f.ref)
        self.assertEqual(second['remote_commit'],ack['remote_commit'])

    def test_final_exact_prefix_readback_does_not_create_a_new_original(self):
        f=self.fixture();before=op.snapshot_manifest(f.source)
        proof=f.writer.final_checkpoint(hashlib.sha256(b'').hexdigest())
        self.assertEqual(proof['schema_version'],op._schema('remote-recovery'))
        self.assertEqual(proof['journal_sha256'],hashlib.sha256(b'').hexdigest())
        self.assertEqual(op.snapshot_manifest(f.source),before)
        with self.assertRaisesRegex(IntegrityError,'prefix differs'):
            f.writer.final_checkpoint('f'*64)
        self.assertEqual(git(f.remote,'rev-parse','refs/heads/'+remote.DIAGNOSTIC_BRANCH),proof['remote_commit'])

    def test_interrupted_remote_readback_retains_original_push_and_recovers_same_commit(self):
        f=self.fixture()
        with patch.object(f.writer,'_fresh_readback',side_effect=OSError('independent fetch interrupted')):
            with self.assertRaisesRegex(OSError,'interrupted'):f.writer.checkpoint(f.ref)
        committed=git(f.remote,'rev-parse','refs/heads/'+remote.DIAGNOSTIC_BRANCH)
        self.assertEqual(f.writer.operations[-1]['status'],'UNACKNOWLEDGED_RETAINED_STATE')
        recovered=f.writer.checkpoint(f.ref)
        self.assertEqual(recovered['remote_commit'],committed)

    def test_checksum_consistent_invalid_typed_fetched_record_cannot_get_ack(self):
        f=self.fixture();strict=op.verify_store
        def invalid(root,**kwargs):
            if Path(root)!=f.source:
                path=Path(root)/'records'/f.ref.kind/(f.ref.record_id+'.json')
                body=json.loads(path.read_bytes());body['payload']['data']['operational']={
                    'schema_version':'not-an-operational-contract','mode':'SYNTHETIC_DIAGNOSTIC'}
                body['payload_sha256']=digest(body['payload']);path.write_bytes(canonical(body))
            return strict(root,**kwargs)
        with patch.object(op,'verify_store',side_effect=invalid):
            with self.assertRaises(IntegrityError):f.writer.checkpoint(f.ref)
        self.assertEqual(f.writer.operations[-1]['status'],'UNACKNOWLEDGED_RETAINED_STATE')
        committed=git(f.remote,'rev-parse','refs/heads/'+remote.DIAGNOSTIC_BRANCH)
        self.assertEqual(f.writer.checkpoint(f.ref)['remote_commit'],committed)

    def test_checksum_consistent_invalid_foreign_typed_lane_cannot_get_ack(self):
        for marker,body in (('pros004',{'schema_version':'nba-pros004-outcome-v1','status':'INVALID'}),
                            ('offer_capture',{'schema_version':'unknown-offer-contract','status':'INVALID'})):
            with self.subTest(marker=marker):
                f=self.fixture();strict=op.verify_store
                def invalid(root,**kwargs):
                    if Path(root)!=f.source:
                        path=Path(root)/'records'/f.ref.kind/(f.ref.record_id+'.json')
                        envelope=json.loads(path.read_bytes());envelope['payload']['data'][marker]=body
                        envelope['payload_sha256']=digest(envelope['payload']);path.write_bytes(canonical(envelope))
                    return strict(root,**kwargs)
                with patch.object(op,'verify_store',side_effect=invalid):
                    with self.assertRaises(IntegrityError):f.writer.checkpoint(f.ref)
                self.assertEqual(f.writer.operations[-1]['status'],'UNACKNOWLEDGED_RETAINED_STATE')

    def test_changed_or_missing_retained_original_and_foreign_writer_fail_closed(self):
        f=self.fixture();first=f.writer.checkpoint(f.ref)
        extra=Ledger(f.source).append('input_captures','extra',{'note':'Synthetic extension'})
        (f.source/'records'/f.ref.kind/(f.ref.record_id+'.json')).unlink()
        with self.assertRaisesRegex(IntegrityError,'missing a retained'):f.writer.checkpoint(extra)
        self.assertEqual(git(f.remote,'rev-parse','refs/heads/'+remote.DIAGNOSTIC_BRANCH),first['remote_commit'])
        (f.writer.root/'interrupted.txt').write_text('Retain interrupted state')
        with self.assertRaisesRegex(IntegrityError,'interrupted dirty'):f.writer.checkpoint(extra)


if __name__=='__main__':unittest.main()

"""OP002 diagnostic transport tests use isolated local Git, no providers."""
import hashlib
import json
from datetime import timedelta
from pathlib import Path
import unittest
from unittest.mock import patch

from multisport_lab import operational_pilot as op
from multisport_lab import operational_remote as remote
from multisport_lab.integrity import IntegrityError,canonical,digest
from multisport_lab.ledger import Ledger,LedgerRef
from multisport_lab.pros004_remote import GitCheckpointWriter,DIAGNOSTIC_BRANCH as OLD_BRANCH
from test_pros004_remote import RemoteFixture,git
from test_operational_pilot import OperationalFixture,CUTOFF


class OperationalRemoteTests(unittest.TestCase):
    def fixture(self):
        f=RemoteFixture(self)
        f.writer=remote.OperatingDiagnosticWriter(f.source,f.root/'operating-writer',base_commit=f.base,
            remote_url=str(f.remote),allow_local_test_remote=True)
        f.writer.prepare();return f

    def pair_fixture(self):
        operating=OperationalFixture(self);transport=RemoteFixture(self)
        prepared=op.prepare_pair(operating.event,operating.history,operating.rows,
            event_ref=operating.event_ref,history_ref=operating.history_ref,
            player_id='10',producer_binding=operating.binding)
        refs=tuple(operating.persist(prepared[model]) for model in ('R0','K0'))
        writer=remote.OperatingDiagnosticWriter(operating.root,transport.root/'pair-writer',base_commit=transport.base,
            remote_url=str(transport.remote),allow_local_test_remote=True)
        writer.prepare()
        return operating,transport,writer,refs

    def test_named_guard_does_not_relax_old_writer_or_allow_real_writes(self):
        f=RemoteFixture(self)
        for kwargs in ({'branch':OLD_BRANCH},{'branch':'diagnostics/ops002-timing-20261021'},
                       {'branch':'main'},{'diagnostic':False},
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

    def test_one_pair_has_one_full_source_and_one_fresh_typed_fetch_with_separate_acks(self):
        f,transport,writer,refs=self.pair_fixture();strict=op.verify_store;seen=[]
        original={ref:f.store.ledger._path(ref.kind,ref.record_id).read_bytes() for ref in refs}
        def verify(root,**kwargs):seen.append(Path(root));return strict(root,**kwargs)
        prefix=hashlib.sha256(f.store._journal_path().read_bytes()).hexdigest()
        with patch.object(op,'verify_store',side_effect=verify):acks=writer.checkpoint_many(refs)
        self.assertEqual(len(seen),2);self.assertEqual(seen[0],f.root)
        self.assertIn('op002-independent-',str(seen[1]))
        self.assertEqual(type(acks),tuple);self.assertEqual(len(acks),2)
        common=('remote_repository','remote_branch','remote_commit','snapshot_sha256','journal_prefix_sha256','remote_completed_at')
        self.assertTrue(all(acks[0][key] == acks[1][key] for key in common))
        self.assertEqual(acks[0]['journal_prefix_sha256'],prefix)
        for ref,ack in zip(refs,acks):
            self.assertEqual(ack['reference'],ref.to_record())
            self.assertEqual(ack['readback_raw_sha256'],hashlib.sha256(original[ref]).hexdigest())
            self.assertEqual(f.store.ledger._path(ref.kind,ref.record_id).read_bytes(),original[ref])
        self.assertEqual(len(writer.operations),1)
        reloaded=remote.OperatingDiagnosticWriter(f.root,writer.root,base_commit=transport.base,
            remote_url=str(transport.remote),allow_local_test_remote=True)
        reloaded.prepare();again=reloaded.checkpoint_many(refs)
        self.assertEqual(again[0]['remote_commit'],acks[0]['remote_commit'])
        single=reloaded.checkpoint_many((refs[0],))
        self.assertEqual(len(single),1);self.assertEqual(single[0]['reference'],refs[0].to_record())

    def test_paired_request_budget_duplicate_kind_and_different_subject_fail_before_push(self):
        f,transport,writer,refs=self.pair_fixture()
        for values in ([],(),refs+(refs[0],),(refs[0],refs[0]),(f.event_ref,)):
            with self.subTest(values=values),self.assertRaises(IntegrityError):writer.checkpoint_many(values)
        other=f.persist(f.generate('K0',player='20'))
        with self.assertRaisesRegex(IntegrityError,'different subjects'):
            writer.checkpoint_many((refs[0],other))
        with self.assertRaisesRegex(IntegrityError,'reference changed'):
            writer.checkpoint_many((refs[0],LedgerRef(refs[1].kind,refs[1].record_id,'f'*64)))
        self.assertEqual(git(transport.remote,'for-each-ref','--format=%(refname)','refs/heads/'+remote.DIAGNOSTIC_BRANCH),'')

    def test_pair_cannot_truncate_journal_or_overwrite_independent_remote_writer(self):
        f,transport,writer,refs=self.pair_fixture();first=writer.checkpoint_many(refs)
        path=f.store._journal_path();original=path.read_bytes()
        path.write_bytes(b''.join(original.splitlines(keepends=True)[:-1]))
        with self.assertRaisesRegex(IntegrityError,'cannot truncate'):writer.checkpoint_many(refs)
        self.assertEqual(git(transport.remote,'rev-parse','refs/heads/'+remote.DIAGNOSTIC_BRANCH),first[0]['remote_commit'])
        path.write_bytes(original)
        foreign=transport.root/'foreign-paired-writer'
        git(transport.root,'clone','--quiet','--branch',remote.DIAGNOSTIC_BRANCH,str(transport.remote),str(foreign))
        (foreign/'foreign.txt').write_text('Preserve legitimate independent work.\n')
        git(foreign,'add','foreign.txt')
        git(foreign,'-c','user.name=Test','-c','user.email=test@example.invalid','commit','--quiet','-m','Foreign')
        git(foreign,'push','origin','HEAD:refs/heads/'+remote.DIAGNOSTIC_BRANCH)
        newer=git(foreign,'rev-parse','HEAD')
        with self.assertRaisesRegex(IntegrityError,'another writer advanced'):writer.checkpoint_many(refs)
        self.assertEqual(git(transport.remote,'rev-parse','refs/heads/'+remote.DIAGNOSTIC_BRANCH),newer)

    def test_interrupted_pair_readback_retains_push_and_recovery_returns_exact_originals(self):
        f,transport,writer,refs=self.pair_fixture()
        original={ref:f.store.ledger._path(ref.kind,ref.record_id).read_bytes() for ref in refs}
        actual_readback=writer._fresh_readback
        def interrupted(*args):
            actual_readback(*args)
            raise OSError('both independently verified but acknowledgment delivery interrupted')
        with patch.object(writer,'_fresh_readback',side_effect=interrupted):
            with self.assertRaisesRegex(OSError,'delivery interrupted'):writer.checkpoint_many(refs)
        committed=git(transport.remote,'rev-parse','refs/heads/'+remote.DIAGNOSTIC_BRANCH)
        self.assertEqual(writer.operations[-1]['status'],'UNACKNOWLEDGED_RETAINED_STATE')
        again=writer.checkpoint_many(refs)
        self.assertEqual({ack['remote_commit'] for ack in again},{committed})
        for ref in refs:self.assertEqual(f.store.ledger._path(ref.kind,ref.record_id).read_bytes(),original[ref])

    def test_partial_per_original_ack_write_recovers_only_missing_remote_witness(self):
        f,_,writer,refs=self.pair_fixture();append=f.store._append_completion
        def interrupted(reference,**kwargs):
            if reference == refs[1] and kwargs.get('acknowledgment') is not None:
                raise OSError('second REMOTE witness persistence interrupted')
            return append(reference,**kwargs)
        with patch.object(f.store,'_append_completion',side_effect=interrupted):
            with self.assertRaisesRegex(OSError,'second REMOTE'):f.store.checkpoint_many(refs,writer.checkpoint_many)
        original_first=next(row for row in f.store.journal() if row['kind']=='REMOTE' and row['reference']==refs[0].to_record())
        restarted=op.OperationalStore(f.root,diagnostic=True)
        self.assertEqual(len(restarted.recover(replay=False)['forecasts']),2)
        requests=[]
        def tracked(values):requests.append(values);return writer.checkpoint_many(values)
        restarted.checkpoint_many(refs,tracked)
        self.assertEqual(requests,[(refs[1],)])
        self.assertEqual(next(row for row in restarted.journal() if row['kind']=='REMOTE' and row['reference']==refs[0].to_record()),original_first)
        restarted.finalize_checkpoint(writer.final_checkpoint)
        self.assertTrue(all(restarted.admission(ref)['eligible'] for ref in refs))

    def test_late_shared_ack_is_retained_without_timely_admission_on_restart(self):
        f,_,writer,refs=self.pair_fixture();actual=writer._fresh_readback
        def late(*args):
            result=actual(*args);f.at(CUTOFF+timedelta(seconds=301));return result
        with patch.object(writer,'_fresh_readback',side_effect=late):f.store.checkpoint_many(refs,writer.checkpoint_many)
        f.store.finalize_checkpoint(writer.final_checkpoint)
        restarted=op.OperationalStore(f.root,diagnostic=True)
        self.assertEqual(len(restarted.recover(replay=False)['forecasts']),2)
        self.assertFalse(any(restarted.admission(ref)['eligible'] for ref in refs))

    def test_paired_fresh_fetch_rejects_checksum_consistent_invalid_second_original(self):
        f,_,writer,refs=self.pair_fixture();strict=op.verify_store
        def invalid(root,**kwargs):
            if Path(root)!=f.root:
                path=Path(root)/'records'/refs[1].kind/(refs[1].record_id+'.json')
                envelope=json.loads(path.read_bytes());envelope['payload']['data']['operational']['model_key']='S0'
                envelope['payload_sha256']=digest(envelope['payload']);path.write_bytes(canonical(envelope))
            return strict(root,**kwargs)
        with patch.object(op,'verify_store',side_effect=invalid):
            with self.assertRaises(IntegrityError):writer.checkpoint_many(refs)
        self.assertEqual(writer.operations[-1]['status'],'UNACKNOWLEDGED_RETAINED_STATE')


if __name__=='__main__':unittest.main()

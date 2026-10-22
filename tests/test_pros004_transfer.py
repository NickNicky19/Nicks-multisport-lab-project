"""Single-operation byte proofs; synthetic and isolated local Git only."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import pros004_snapshot as snap
from multisport_lab import pros004_producer as producer
from multisport_lab import pros004_records as records
from multisport_lab.integrity import IntegrityError, canonical, digest
from multisport_lab.ledger import Ledger
from test_pros004_remote import RemoteFixture, git
from test_pros004_snapshot import make_store
from test_pros004_producer import ProducerFixture, CUTOFF
from test_pros004_inputs import NOW


def reseal(path, change):
    envelope=json.loads(path.read_bytes());change(envelope['payload'])
    envelope['payload_sha256']=digest(envelope['payload'])
    path.write_bytes(canonical(envelope))


def copy_entries(source,target,manifest):
    for entry in manifest['entries']:
        destination=target/entry['path'];destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes((source/entry['path']).read_bytes())


class Pros004TransferTests(unittest.TestCase):
    def proof(self,root):
        source=root/'source';make_store(source)
        proof=snap._begin_exact_transfer(source)
        manifest=proof.export(root/'export')
        return source,proof,manifest

    def test_complete_checkpoint_has_one_source_and_one_fresh_remote_typed_pass(self):
        f=RemoteFixture(self);strict=snap.snapshot_manifest;seen=[]
        def verify(root):
            seen.append(Path(root));return strict(root)
        before={p.relative_to(f.source):p.read_bytes() for p in f.source.glob('records/*/*.json')}
        with patch.object(snap,'snapshot_manifest',side_effect=verify):
            acknowledgment=f.writer.checkpoint(f.ref)
        self.assertEqual(len(seen),2)
        self.assertEqual(seen[0],f.source)
        self.assertNotEqual(seen[1],f.writer.root)
        self.assertIn('independent-checkpoint-',str(seen[1]))
        self.assertEqual(before,{p.relative_to(f.source):p.read_bytes() for p in f.source.glob('records/*/*.json')})
        self.assertEqual(acknowledgment['readback_raw_sha256'],hashlib.sha256(next(iter(before.values()))).hexdigest())

    def test_private_proof_has_no_supplied_manifest_and_consumes_every_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,proof,manifest=self.proof(root)
            with self.assertRaises(TypeError):snap._begin_exact_transfer(source,manifest)
            with self.assertRaisesRegex(snap.SnapshotError,'originate from strict'):
                snap._ExactTransfer(source,manifest,'not a proof')
            exported=proof.manifest;exported['entries'].clear()
            self.assertEqual(proof.manifest,manifest)
            with self.assertRaisesRegex(snap.SnapshotError,'consumed'):proof.export(root/'second')
            writer=root/'writer';writer.mkdir()
            proof.preserve_writer(writer);copy_entries(root/'export',writer,manifest)
            self.assertEqual(proof.verify_writer(writer),manifest)
            with self.assertRaisesRegex(snap.SnapshotError,'consumed'):proof.verify_writer(writer)
            with self.assertRaisesRegex(snap.SnapshotError,'consumed'):proof.preserve_writer(writer)

    def test_copy_and_source_resealed_raw_changes_or_partial_copy_are_rejected(self):
        for problem in ('source','copy','partial','inventory'):
            with self.subTest(problem=problem),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);source=root/'source';make_store(source)
                proof=snap._begin_exact_transfer(source);original=snap._copy_record;calls=[]
                def copy(*args):
                    original(*args);calls.append(args)
                    if len(calls)==2:
                        target=root/'export'
                        if problem=='source':
                            path=source/proof.manifest['entries'][0]['path']
                            reseal(path,lambda p:p['data'].update(note='Valid checksum, changed source'))
                        elif problem=='copy':
                            path=target/proof.manifest['entries'][0]['path']
                            reseal(path,lambda p:p['data'].update(note='Valid checksum, changed copy'))
                        elif problem=='partial':(target/proof.manifest['entries'][0]['path']).unlink()
                        else:Ledger(target).append('input_captures','extra',{'note':'Unplanned inventory'})
                with patch.object(snap,'_copy_record',side_effect=copy):
                    with self.assertRaises(snap.SnapshotError):proof.export(root/'export')
                self.assertFalse((root/'export'/snap.MANIFEST).exists())
                with self.assertRaisesRegex(snap.SnapshotError,'consumed'):proof.export(root/'retry')

    def test_retained_subset_requires_closed_parent_references_and_exact_original_bytes(self):
        for problem in ('missing-parent','changed-original','extra-original'):
            with self.subTest(problem=problem),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);source=root/'source';store=Ledger(source)
                parent=store.append('input_captures','parent',{'note':'Synthetic retained parent'})
                child=store.append('input_captures','child',{'note':'Synthetic child'},references=(parent,))
                proof=snap._begin_exact_transfer(source);manifest=proof.export(root/'export')
                writer=root/'writer';writer.mkdir();copy_entries(source,writer,manifest)
                if problem=='missing-parent':(writer/'records'/parent.kind/(parent.record_id+'.json')).unlink()
                elif problem=='changed-original':
                    reseal(writer/'records'/child.kind/(child.record_id+'.json'),lambda p:p['data'].update(note='Changed'))
                else:Ledger(writer).append('input_captures','foreign',{'note':'Must preserve newer work'})
                before={p.relative_to(writer):p.read_bytes() for p in writer.glob('records/*/*.json')}
                with self.assertRaises(snap.SnapshotError):proof.preserve_writer(writer)
                self.assertEqual(before,{p.relative_to(writer):p.read_bytes() for p in writer.glob('records/*/*.json')})
                with self.assertRaisesRegex(snap.SnapshotError,'consumed'):proof.preserve_writer(writer)

    def test_completion_rejects_changed_destination_and_context_or_export_bytes(self):
        for problem in ('changed-writer','other-writer','replaced-directory','export-mutation'):
            with self.subTest(problem=problem),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);_,proof,manifest=self.proof(root)
                writer=root/'writer';writer.mkdir();proof.preserve_writer(writer)
                copy_entries(root/'export',writer,manifest)
                target=writer
                if problem=='changed-writer':
                    reseal(writer/manifest['entries'][0]['path'],lambda p:p['data'].update(note='Changed'))
                elif problem=='other-writer':
                    target=root/'other';shutil.copytree(writer,target)
                elif problem=='replaced-directory':
                    writer.rename(root/'retained-original');shutil.copytree(root/'retained-original',writer)
                else:
                    reseal(root/'export'/manifest['entries'][0]['path'],lambda p:p['data'].update(note='Changed export'))
                with self.assertRaises(snap.SnapshotError):proof.verify_writer(target)
                with self.assertRaisesRegex(snap.SnapshotError,'consumed'):proof.verify_writer(writer)

    def test_changed_validation_source_or_retained_correction_parent_cannot_reuse_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,proof,_=self.proof(root)
            writer=root/'writer';writer.mkdir()
            with patch.object(producer,'source_hashes',return_value={'changed':'f'*64}):
                with self.assertRaisesRegex(snap.SnapshotError,'source context changed'):
                    proof.preserve_writer(writer)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';store=Ledger(source)
            old=store.append('outcomes','first',{'identity':{'player_id':'10'},'note':'Synthetic old'})
            replacement=store.append('outcomes','second',{'identity':{'player_id':'10'},'note':'Synthetic correction'})
            store.correct(old,replacement,reason='Synthetic correction relationship')
            proof=snap._begin_exact_transfer(source);manifest=proof.export(root/'export')
            writer=root/'writer';writer.mkdir();copy_entries(source,writer,manifest)
            (writer/'records'/replacement.kind/(replacement.record_id+'.json')).unlink()
            with self.assertRaises(snap.SnapshotError):proof.preserve_writer(writer)

    def test_retained_admission_cannot_omit_unreferenced_original_snapshot_member(self):
        f=ProducerFixture(self,prepare_admission=False)
        for clock in (f.record_clock,f.ledger_clock):clock.return_value=NOW
        # Keep this non-PROS004 receipt before both the synthetic checkpoint
        # clock and actual transport clock, regardless of the calendar date.
        f.ledger_clock.return_value=min(NOW,datetime.now(timezone.utc))-timedelta(days=1)
        extra=f.store.ledger.append('input_captures','unreferenced-prefix-member',
            {'note':'Synthetic original included in durable input phase snapshot'})
        f.ledger_clock.return_value=NOW
        final=f.store.finalize_checkpoint((f.event_ref,),f.ack)
        for clock in (f.record_clock,f.ledger_clock):clock.return_value=NOW+timedelta(microseconds=1)
        f.store.claim_event(f.event_ref,f.binding,input_final_checkpoint=final)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);proof=snap._begin_exact_transfer(f.tmp)
            manifest=proof.export(root/'export');writer=root/'writer';writer.mkdir()
            copy_entries(root/'export',writer,manifest)
            missing=writer/'records'/extra.kind/(extra.record_id+'.json');missing.unlink()
            with self.assertRaisesRegex(snap.SnapshotError,'snapshot prefix is incomplete'):
                proof.preserve_writer(writer)
            self.assertFalse(missing.exists())

    def test_actual_clock_rechecked_and_backwards_clock_cannot_complete_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,proof,_=self.proof(root)
            writer=root/'writer';writer.mkdir();past=datetime(2000,1,1,tzinfo=timezone.utc)
            with patch.object(snap,'_transport_now',return_value=past):
                # Source semantics was checked at the actual clock, but this
                # older operation clock must not reuse that successful result.
                with self.assertRaisesRegex(snap.SnapshotError,'moved backwards'):proof.preserve_writer(writer)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';make_store(source)
            proof=snap._begin_exact_transfer(source)
            current=datetime.now(timezone.utc)+timedelta(seconds=1)
            with patch.object(snap,'_transport_now',side_effect=[current,current-timedelta(seconds=1)]):
                with self.assertRaisesRegex(snap.SnapshotError,'moved backwards'):proof.export(root/'export')

    def test_partial_or_late_diagnostic_original_remains_unadmitted_after_transport(self):
        f=ProducerFixture(self)
        for clock in (f.record_clock,f.ledger_clock,f.producer_clock):
            clock.return_value=CUTOFF+timedelta(seconds=299)
        body,_=f.generate('R0')
        original_write=records.frozen_ledger.write_receipt
        def delayed(path,payload,**kwargs):
            result=original_write(path,payload,**kwargs)
            if payload.get('kind')=='forecasts':
                f.record_clock.return_value=CUTOFF+timedelta(seconds=301)
                f.ledger_clock.return_value=CUTOFF+timedelta(seconds=301)
            return result
        with patch.object(records.frozen_ledger,'write_receipt',side_effect=delayed):
            with self.assertRaisesRegex(IntegrityError,'local persistence completed late'):
                f.store.persist_forecast(body,f.event_ref,f.history_ref,f.claim_ref)
        original=f.store.lookup_forecast(f.event_ref,'10','R0')
        self.assertIsNotNone(original)
        raw=f.store.ledger._path(original.kind,original.record_id).read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.object(producer,'generate_forecast',side_effect=RuntimeError('Transport cannot generate')):
                manifest=snap.export_snapshot(f.tmp,root/'export')
                recovered=records.Pros004Store(root/'export',diagnostic=True)
                report=recovered.recover_event(f.event_ref,f.binding)
            self.assertEqual(len(list((root/'export'/'records/forecasts').glob('*.json'))),1)
            self.assertEqual((root/'export'/'records'/original.kind/(original.record_id+'.json')).read_bytes(),raw)
            self.assertEqual(report['timing_complete_models'],0)
            self.assertEqual(report['eligible_models'],0)
            self.assertEqual(manifest['genuine_issuance'],0)

    def test_remote_readback_never_accepts_local_source_proof_instead_of_semantics(self):
        f=RemoteFixture(self);strict=snap.snapshot_manifest
        def reject_fetched(root):
            if Path(root)!=f.source:
                raise snap.SnapshotError('fresh independent typed meanings rejected')
            return strict(root)
        with patch.object(snap,'snapshot_manifest',side_effect=reject_fetched):
            with self.assertRaisesRegex(snap.SnapshotError,'fresh independent typed'):
                f.writer.checkpoint(f.ref)
        committed=git(f.writer.root,'rev-parse','HEAD')
        self.assertEqual(git(f.remote,'rev-parse','refs/heads/'+f.writer.branch),committed)
        # No ACK escaped. Retained interrupted originals recover through a new
        # writer instance and a completely fresh independent readback.
        f.writer.prepare();ack=f.writer.checkpoint(f.ref)
        self.assertEqual(ack['remote_commit'],committed)

    def test_fresh_remote_strict_pass_rejects_checksum_consistent_invalid_outcome(self):
        from test_pros004_records import issue_both, at_outcomes, synthetic_outcome
        from multisport_lab.pros004_remote import GitCheckpointWriter
        f=ProducerFixture(self);peers=issue_both(f);at_outcomes(f)
        outcome=f.store.append_outcome(synthetic_outcome(f),peers)
        before=f.store.ledger._path(outcome.kind,outcome.record_id).read_bytes()
        remote=RemoteFixture(self)
        writer=GitCheckpointWriter(f.tmp,remote.root/'typed-writer',base_commit=remote.base,
            remote_url=str(remote.remote),allow_local_test_remote=True)
        writer.prepare();strict=snap.snapshot_manifest
        def verify(root):
            if Path(root)!=Path(f.tmp):
                path=Path(root)/'records'/outcome.kind/(outcome.record_id+'.json')
                reseal(path,lambda p:p['data']['pros004'].update(status='INVALID_CHECKSUM_CONSISTENT'))
            return strict(root)
        with patch.object(snap,'snapshot_manifest',side_effect=verify):
            with self.assertRaises(snap.SnapshotError):writer.checkpoint(outcome)
        self.assertEqual(f.store.ledger._path(outcome.kind,outcome.record_id).read_bytes(),before)
        # The attempted independent copy, not the immutable original or its
        # remote committed source, was corrupted. No acknowledgment was returned.
        self.assertEqual(git(remote.remote,'rev-parse','refs/heads/'+writer.branch),git(writer.root,'rev-parse','HEAD'))


if __name__=='__main__':
    unittest.main()

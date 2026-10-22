"""Offline receipt snapshot integrity/recovery; no captures or real issuance."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import pros004_snapshot as snapshot
from multisport_lab.integrity import IntegrityError, canonical, digest, read_receipt, write_receipt
from multisport_lab.ledger import Ledger
from multisport_lab.integrity import stamp


def make_store(root, count=2):
    store = Ledger(root)
    for index in range(count):
        store.append('input_captures','synthetic-'+str(index),{'note':'synthetic '+str(index)})
    return store


def refresh_manifest(root):
    """Re-seal valid hashes after a deliberately invalid semantic mutation."""
    path=root/snapshot.MANIFEST;body=read_receipt(path)
    for entry in body['entries']:
        raw=(root/entry['path']).read_bytes()
        entry['encoded_bytes']=len(raw);entry['raw_sha256']=hashlib.sha256(raw).hexdigest()
        if entry['entry_type']=='LEDGER_RECEIPT':
            entry['payload_sha256']=digest(read_receipt(root/entry['path']))
        else:
            entry['payload_sha256']=digest([json.loads(line) for line in raw.splitlines()])
    body['encoded_bytes']=sum(item['encoded_bytes'] for item in body['entries'])
    body['manifest_id']=digest({k:v for k,v in body.items() if k!='manifest_id'})
    path.unlink();write_receipt(path,body)
    return body


class Pros004SnapshotTests(unittest.TestCase):
    def test_callback_proof_reuses_only_identical_semantics_and_is_single_use(self):
        from multisport_lab import pros004_producer as producer
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);make_store(root)
            proof=snapshot.begin_callback_verification(root)
            expected=proof.manifest
            returned=proof.manifest;returned['entries'][0]['raw_sha256']='f'*64
            with (patch.object(snapshot,'verify_store',side_effect=RuntimeError('No second semantic pass')),
                    patch.object(producer,'generate_forecast',side_effect=RuntimeError('No generation')),
                    patch.object(producer,'_fit_laws',side_effect=RuntimeError('No model fit'))):
                actual=proof.verify_unchanged(clock=lambda:datetime.now(timezone.utc))
            self.assertEqual(actual,expected)
            actual['entries'].clear()
            self.assertEqual(proof.manifest,expected)
            with self.assertRaisesRegex(snapshot.SnapshotError,'consumed'):
                proof.verify_unchanged(clock=lambda:datetime.now(timezone.utc))
            with self.assertRaisesRegex(snapshot.SnapshotError,'originate from strict'):
                snapshot._CallbackVerification(root,expected,'not a proof')

    def test_callback_proof_rejects_resealed_receipt_and_cannot_retry_after_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);store=make_store(root)
            proof=snapshot.begin_callback_verification(root)
            path=next((root/'records/input_captures').glob('*.json'))
            original=path.read_bytes();envelope=json.loads(original)
            envelope['payload']['data']['note']='Changed with a valid checksum'
            envelope['payload_sha256']=digest(envelope['payload']);path.write_bytes(canonical(envelope))
            with self.assertRaisesRegex(snapshot.SnapshotError,'original receipt bytes'):
                proof.verify_unchanged(clock=lambda:datetime.now(timezone.utc))
            path.write_bytes(original)
            with self.assertRaisesRegex(snapshot.SnapshotError,'consumed'):
                proof.verify_unchanged(clock=lambda:datetime.now(timezone.utc))

    def test_callback_proof_rejects_resealed_typed_status_phase_and_parent_mutations(self):
        from test_pros004_producer import ProducerFixture
        for subject in ('event-status','phase-proof','parent-history'):
            with self.subTest(subject=subject):
                f=ProducerFixture(self);proof=snapshot.begin_callback_verification(f.tmp)
                reference={'event-status':f.event_ref,'phase-proof':f.claim_ref,'parent-history':f.history_ref}[subject]
                path=f.store.ledger._path(reference.kind,reference.record_id)
                envelope=json.loads(path.read_bytes());body=envelope['payload']['data']['pros004']
                if subject=='event-status':
                    body['event']['status']='FINAL'
                    body['sourcepack_id']=digest({key:value for key,value in body.items() if key!='sourcepack_id'})
                elif subject=='phase-proof':body['input_final_checkpoint']['snapshot_sha256']='f'*64
                else:body['history_id']='f'*64
                envelope['payload_sha256']=digest(envelope['payload']);path.write_bytes(canonical(envelope))
                with self.assertRaisesRegex(snapshot.SnapshotError,'original receipt bytes'):
                    proof.verify_unchanged(clock=f.record_clock)

    def test_callback_proof_rejects_fresh_inventory_and_directory_replacements(self):
        for change in ('unpublished','removed','symlink','replaced-root'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                parent=Path(folder);root=parent/'source';make_store(root)
                proof=snapshot.begin_callback_verification(root)
                if change=='unpublished':
                    (root/'records/input_captures/.receipt-interrupted').write_bytes(b'Unpublished original')
                elif change=='removed':next((root/'records/input_captures').glob('*.json')).unlink()
                elif change=='symlink':
                    (root/'records').rename(parent/'original-records')
                    (root/'records').symlink_to(parent/'original-records',target_is_directory=True)
                else:
                    root.rename(parent/'original-root');shutil.copytree(parent/'original-root',root)
                with self.assertRaises(snapshot.SnapshotError):
                    proof.verify_unchanged(clock=lambda:datetime.now(timezone.utc))

    def test_callback_proof_rejects_journal_append_removal_and_resealed_replacement(self):
        from multisport_lab import pros004_completion as completion
        for change in ('added','removed','replaced'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);past=datetime.now(timezone.utc)-timedelta(minutes=1)
                with patch('multisport_lab.ledger._now',return_value=past):
                    store=make_store(root,count=1)
                payload=next(iter(store.scan()['input_captures'].values()))
                from multisport_lab.ledger import LedgerRef
                reference=LedgerRef('input_captures',payload['record_id'],digest(payload))
                raw_sha=hashlib.sha256(store._path(reference.kind,reference.record_id).read_bytes()).hexdigest()
                def append():
                    completion.append_completion(root,reference,mode='SYNTHETIC_DIAGNOSTIC',raw_sha256=raw_sha,
                        completed_at=past+timedelta(seconds=1),recorded_at=past+timedelta(seconds=1))
                if change!='added':append()
                proof=snapshot.begin_callback_verification(root);path=completion.journal_path(root)
                if change=='added':append()
                elif change=='removed':path.unlink()
                else:
                    entry=json.loads(path.read_bytes())
                    entry['recorded_at']=stamp(past+timedelta(seconds=2))
                    entry['entry_sha256']=digest({key:value for key,value in entry.items() if key!='entry_sha256'})
                    path.write_bytes(canonical(entry)+b'\n')
                with self.assertRaisesRegex(snapshot.SnapshotError,'journal'):
                    proof.verify_unchanged(clock=lambda:datetime.now(timezone.utc))

    def test_callback_proof_rejects_new_correction_and_actual_clock_or_source_changes(self):
        from multisport_lab import pros004_producer as producer
        for change in ('correction','old-clock','backwards-clock','source-context'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);store=make_store(root)
                first=store.append('outcomes','synthetic-original',{'identity':{'player':'10'},'note':'Original'})
                replacement=store.append('outcomes','synthetic-replacement',{'identity':{'player':'10'},'note':'Replacement'})
                proof=snapshot.begin_callback_verification(root)
                if change=='correction':
                    store.correct(first,replacement,reason='Synthetic correction after snapshot')
                    with self.assertRaises(snapshot.SnapshotError):proof.verify_unchanged(clock=lambda:datetime.now(timezone.utc))
                elif change=='old-clock':
                    with self.assertRaisesRegex(snapshot.SnapshotError,'clock'):
                        proof.verify_unchanged(clock=lambda:datetime(2020,1,1,tzinfo=timezone.utc))
                elif change=='backwards-clock':
                    now=datetime.now(timezone.utc);values=iter((now+timedelta(seconds=1),now))
                    with self.assertRaisesRegex(snapshot.SnapshotError,'moved backwards'):
                        proof.verify_unchanged(clock=lambda:next(values))
                else:
                    with patch.object(producer,'source_hashes',return_value={'changed_source':'f'*64}):
                        with self.assertRaisesRegex(snapshot.SnapshotError,'context changed'):
                            proof.verify_unchanged(clock=lambda:datetime.now(timezone.utc))

    def test_raw_prefix_reconstruction_is_exact_without_semantic_recursion(self):
        from multisport_lab import pros004_completion as completion
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);clock=datetime.now(timezone.utc)-timedelta(minutes=1)
            ledger=Ledger(root)
            with patch('multisport_lab.ledger._now',return_value=clock):
                first=ledger.append('input_captures','synthetic-prefix-original',{'note':'Explicit synthetic prefix'})
            path=ledger._path(first.kind,first.record_id)
            completion.append_completion(root,first,mode='SYNTHETIC_DIAGNOSTIC',
                raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                completed_at=clock+timedelta(seconds=1),recorded_at=clock+timedelta(seconds=1))
            original=snapshot.snapshot_manifest(root)
            journal_hash=completion.journal_inventory(root)['raw_sha256']
            started=clock+timedelta(seconds=2)
            with patch('multisport_lab.ledger._now',return_value=clock+timedelta(seconds=3)):
                later=ledger.append('input_captures','synthetic-prefix-later',
                    {'note':'Later original, outside earlier prefix'},references=(first,))
            completion.append_completion(root,later,mode='SYNTHETIC_DIAGNOSTIC',
                raw_sha256=hashlib.sha256(ledger._path(later.kind,later.record_id).read_bytes()).hexdigest(),
                completed_at=clock+timedelta(seconds=4),recorded_at=clock+timedelta(seconds=4))
            with (patch.object(snapshot,'snapshot_manifest',side_effect=RuntimeError('No semantic recursion')),
                    patch.object(snapshot,'verify_store',side_effect=RuntimeError('No semantic recursion'))):
                recovered=snapshot.recover_manifest_prefix(root,journal_hash,stamp(started))
            self.assertEqual(recovered,original)
            for bad_hash,bad_start in (('f'*64,stamp(started)),(journal_hash,stamp(clock))):
                with self.subTest(hash=bad_hash,start=bad_start),self.assertRaises(snapshot.SnapshotError):
                    snapshot.recover_manifest_prefix(root,bad_hash,bad_start)
            # Tied clocks never silently drop a later original to make an old
            # proof fit. Inclusion changes the digest, so its caller rejects it.
            with patch('multisport_lab.ledger._now',return_value=started):
                ledger.append('input_captures','synthetic-prefix-clock-tie',{'note':'Ambiguous tied original'})
            tied=snapshot.recover_manifest_prefix(root,journal_hash,stamp(started))
            self.assertNotEqual(tied['manifest_id'],original['manifest_id'])
            self.assertEqual(tied['record_count'],original['record_count']+1)

    def test_raw_prefix_rejects_changed_original_bytes_even_with_resealed_receipt(self):
        from multisport_lab import pros004_completion as completion
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);clock=datetime.now(timezone.utc)-timedelta(minutes=1)
            ledger=Ledger(root)
            with patch('multisport_lab.ledger._now',return_value=clock):
                first=ledger.append('input_captures','synthetic-prefix-tampering',{'note':'Original meaning'})
            path=ledger._path(first.kind,first.record_id)
            completion.append_completion(root,first,mode='SYNTHETIC_DIAGNOSTIC',
                raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                completed_at=clock+timedelta(seconds=1),recorded_at=clock+timedelta(seconds=1))
            prefix=completion.journal_inventory(root)['raw_sha256']
            envelope=json.loads(path.read_bytes());envelope['payload']['data']['note']='Different meaning'
            envelope['payload_sha256']=digest(envelope['payload']);path.write_bytes(canonical(envelope))
            with self.assertRaisesRegex(snapshot.SnapshotError,'identity/bytes/clocks'):
                snapshot.recover_manifest_prefix(root,prefix,stamp(clock+timedelta(seconds=2)))

    def test_exact_export_reopen_readback_and_documented_readme(self):
        with tempfile.TemporaryDirectory() as folder:
            parent=Path(folder);source=parent/'source';make_store(source)
            (source/'records'/'README.md').write_text('Synthetic documentation, not a receipt.\n')
            original={p.relative_to(source).as_posix():p.read_bytes() for p in source.glob('records/*/*.json')}
            manifest=snapshot.export_snapshot(source,parent/'snapshot')
            self.assertEqual(manifest,snapshot.snapshot_manifest(source))
            self.assertEqual(manifest['record_count'],2)
            ack=snapshot.recover_snapshot(parent/'snapshot',parent/'readback')
            self.assertEqual(ack['status'],'PASS_VERIFIED_DIAGNOSTIC_READBACK')
            self.assertEqual(ack['manifest_id'],manifest['manifest_id'])
            self.assertTrue(ack['all_original_bytes_preserved'])
            self.assertFalse(ack['activation']);self.assertFalse(ack['remote_durability_established'])
            for name,raw in original.items():
                self.assertEqual((source/name).read_bytes(),raw)
                self.assertEqual((parent/'readback'/name).read_bytes(),raw)
            self.assertEqual(read_receipt(parent/'readback'/'pros004-readback.json'),ack)
            with self.assertRaisesRegex(snapshot.SnapshotError,'new destination'):
                snapshot.recover_snapshot(parent/'snapshot',parent/'readback')

    def test_tampered_raw_bytes_or_manifest_cannot_obtain_acknowledgment(self):
        for target in ('raw','manifest'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);source=root/'source';make_store(source)
                manifest=snapshot.export_snapshot(source,root/'snapshot')
                if target=='raw':
                    path=root/'snapshot'/manifest['entries'][0]['path']
                    path.write_bytes(path.read_bytes()+b' ')
                else:
                    path=root/'snapshot'/snapshot.MANIFEST
                    envelope=json.loads(path.read_text())
                    body=envelope['payload'];body['record_count']+=1
                    body['manifest_id']=digest({k:v for k,v in body.items() if k!='manifest_id'})
                    envelope['payload_sha256']=digest(body);path.write_bytes(canonical(envelope))
                with self.assertRaises(snapshot.SnapshotError):
                    snapshot.recover_snapshot(root/'snapshot',root/'readback')
                self.assertFalse((root/'readback').exists())

    def test_source_bytes_cannot_change_between_semantic_scan_and_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';make_store(source,1)
            path=next(source.glob('records/*/*.json'));original=path.read_bytes()
            independent_verify=snapshot.verify_store
            def mutate_after_scan(value):
                result=independent_verify(value)
                envelope=json.loads(path.read_bytes())
                changed=json.dumps(dict(reversed(list(envelope.items()))),
                    separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
                self.assertEqual(len(changed),len(original));self.assertNotEqual(changed,original)
                path.write_bytes(changed)
                return result
            with patch.object(snapshot,'verify_store',side_effect=mutate_after_scan):
                with self.assertRaisesRegex(snapshot.SnapshotError,'bytes changed after semantic verification'):
                    snapshot.export_snapshot(source,root/'snapshot')
            self.assertFalse((root/'snapshot').exists())

    def test_missing_reference_or_orphan_or_unknown_kind_is_rejected(self):
        for problem in ('missing-reference','orphan','unknown-kind','symlink','readme-symlink'):
            with self.subTest(problem=problem),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);source=root/'source';make_store(source,1)
                path=next(source.glob('records/*/*.json'))
                if problem=='missing-reference':
                    envelope=json.loads(path.read_text())
                    envelope['payload']['references']=[{'kind':'input_captures','record_id':'f'*64,'payload_sha256':'e'*64}]
                    envelope['payload_sha256']=digest(envelope['payload']);path.write_bytes(canonical(envelope))
                elif problem=='orphan':
                    (path.parent/'.receipt-unacknowledged').write_text('partial')
                elif problem=='unknown-kind':
                    (source/'records'/'unexpected').mkdir()
                elif problem=='symlink':
                    (path.parent/('f'*64+'.json')).symlink_to(path)
                else:
                    (source/'records'/'README.md').symlink_to(path)
                with self.assertRaises(snapshot.SnapshotError):
                    snapshot.export_snapshot(source,root/'snapshot')
                self.assertFalse((root/'snapshot').exists())

    def test_interrupted_copy_retained_without_manifest_or_retry_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';make_store(source,2)
            original=snapshot._copy_record;calls=[]
            def interrupt(*args):
                calls.append(args)
                if len(calls)==2:raise OSError('simulated interruption')
                return original(*args)
            with patch.object(snapshot,'_copy_record',side_effect=interrupt):
                with self.assertRaisesRegex(OSError,'simulated interruption'):
                    snapshot.export_snapshot(source,root/'snapshot')
            self.assertEqual(len(list((root/'snapshot').glob('records/*/*.json'))),1)
            self.assertFalse((root/'snapshot'/snapshot.MANIFEST).exists())
            with self.assertRaisesRegex(snapshot.SnapshotError,'incomplete'):
                snapshot.recover_snapshot(root/'snapshot',root/'readback')
            with self.assertRaisesRegex(snapshot.SnapshotError,'new destination'):
                snapshot.export_snapshot(source,root/'snapshot')
            self.assertEqual(snapshot.snapshot_manifest(source)['record_count'],2)

    def test_partial_model_original_is_preserved_without_missing_peer_generation(self):
        from test_pros004_producer import ProducerFixture
        from multisport_lab import pros004_producer as producer
        fixture=ProducerFixture(self)
        claim,_=fixture.store.claim_event(fixture.event_ref,fixture.binding)
        body,_=fixture.generate('R0')
        original=fixture.store.persist_forecast(body,fixture.event_ref,fixture.history_ref,claim)
        self.assertIsNone(fixture.store.lookup_forecast(fixture.event_ref,'10','K0'))
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.object(producer,'generate_forecast',side_effect=AssertionError('snapshot cannot generate')):
                manifest=snapshot.export_snapshot(fixture.store.root,root/'snapshot')
                ack=snapshot.recover_snapshot(root/'snapshot',root/'recovered')
            self.assertEqual(ack['record_count'],manifest['record_count'])
            self.assertEqual(len(list((root/'recovered'/'records'/'forecasts').glob('*.json'))),1)
            rel=Path('records')/'forecasts'/(original.record_id+'.json')
            self.assertEqual((root/'recovered'/rel).read_bytes(),(fixture.store.root/rel).read_bytes())
            self.assertFalse(ack['missing_peers_repaired'])
            self.assertEqual(ack['prospective_eligibility'],'NOT_ESTABLISHED_BY_SNAPSHOT')

    def test_completion_journal_exact_bytes_are_retained_and_counted(self):
        from test_pros004_producer import ProducerFixture
        from multisport_lab import pros004_records as records
        fixture=ProducerFixture(self)
        relative=Path(snapshot.JOURNAL_RELATIVE_PATH)
        original=(fixture.store.root/relative).read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest=snapshot.export_snapshot(fixture.store.root,root/'snapshot')
            self.assertEqual(manifest['ledger_record_count'],3)
            self.assertEqual(manifest['completion_journal_count'],1)
            self.assertEqual(manifest['record_count'],4)
            entry=next(e for e in manifest['entries'] if e['entry_type']=='COMPLETION_JOURNAL')
            self.assertEqual(entry['raw_sha256'],hashlib.sha256(original).hexdigest())
            self.assertEqual(entry['encoded_bytes'],len(original))
            ack=snapshot.recover_snapshot(root/'snapshot',root/'recovered')
            self.assertTrue(ack['completion_journal_copied'])
            self.assertEqual((root/'recovered'/relative).read_bytes(),original)
            recovered=records.Pros004Store(root/'recovered',diagnostic=True)
            self.assertTrue(recovered.admission_status(fixture.event_ref)['timing_complete'])
            self.assertFalse(recovered.admission_status(fixture.event_ref)['eligible_for_comparison'])
            with patch.object(snapshot,'MAX_RECORDS',3):
                with self.assertRaisesRegex(snapshot.SnapshotError,'capacity'):
                    snapshot.snapshot_manifest(fixture.store.root)

    def test_torn_omitted_or_resealed_incorrect_journal_cannot_get_acknowledgment(self):
        from test_pros004_producer import ProducerFixture
        fixture=ProducerFixture(self,prepare_admission=False)
        for change in ('torn','omitted','wrong-original','pre-receipt-clock'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);snapshot.export_snapshot(fixture.store.root,root/'snapshot')
                path=root/'snapshot'/snapshot.JOURNAL_RELATIVE_PATH
                if change=='torn':path.write_bytes(path.read_bytes()[:-1])
                elif change=='omitted':path.unlink()
                else:
                    entries=[json.loads(line) for line in path.read_bytes().splitlines()]
                    if change=='wrong-original':entries[0]['record_raw_sha256']='f'*64
                    else:entries[0]['completed_at']='2026-01-01T00:00:00.000000Z'
                    previous='0'*64
                    for entry in entries:
                        entry['previous_sha256']=previous
                        entry['entry_sha256']=digest({k:v for k,v in entry.items() if k!='entry_sha256'})
                        previous=entry['entry_sha256']
                    path.write_bytes(b''.join(canonical(e)+b'\n' for e in entries))
                    refresh_manifest(root/'snapshot')
                with self.assertRaises(snapshot.SnapshotError):
                    snapshot.recover_snapshot(root/'snapshot',root/'recovered')
                self.assertFalse((root/'recovered').exists())

    def test_legacy_snapshot_recovers_originals_without_inventing_completion_proof(self):
        from test_pros004_producer import ProducerFixture
        from multisport_lab import pros004_records as records
        import shutil
        fixture=ProducerFixture(self,prepare_admission=False)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source'
            shutil.copytree(fixture.store.root/'records',source/'records')
            # Legacy snapshots have no journal field or bytes. They remain
            # readable under the stricter semantic pass and unadmitted.
            manifest=snapshot._manifest_for_schema(source,snapshot.LEGACY_SCHEMA)
            write_receipt(source/snapshot.MANIFEST,manifest)
            ack=snapshot.recover_snapshot(source,root/'recovered')
            recovered=records.Pros004Store(root/'recovered',diagnostic=True)
            status=recovered.admission_status(fixture.event_ref)
            self.assertFalse(status['timing_complete']);self.assertFalse(status['eligible_for_comparison'])
            self.assertIn('LOCAL_COMPLETION_UNOBSERVED',status['reasons'])
            self.assertFalse(ack['completion_journal_copied'])
            self.assertFalse((root/'recovered'/snapshot.JOURNAL_RELATIVE_PATH).exists())

    def test_resealed_invalid_typed_outcome_is_rejected_before_readback_ack(self):
        from test_pros004_verifier import typed_fixture,replace_typed_receipt
        from test_pros004_records import at_outcomes,synthetic_outcome
        fixture,refs=typed_fixture(self);at_outcomes(fixture)
        outcome=fixture.store.append_outcome(synthetic_outcome(fixture),refs)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);snapshot.export_snapshot(fixture.store.root,root/'snapshot')
            path=root/'snapshot'/'records'/outcome.kind/(outcome.record_id+'.json')
            original=read_receipt(path);body=original['data']['pros004'];body['status']='ALIEN'
            revised=replace_typed_receipt(root/'snapshot',original,body)
            # Retain the exact earlier input-proof journal while excluding the
            # later outcome's byte seal, so typed meaning is what rejects it.
            journal=root/'snapshot'/snapshot.JOURNAL_RELATIVE_PATH
            target=fixture.store.body(fixture.claim_ref)['input_final_checkpoint']['journal_raw_sha256']
            prefix=bytearray()
            for line in journal.read_bytes().splitlines(keepends=True):
                prefix.extend(line)
                if hashlib.sha256(prefix).hexdigest()==target:break
            else:self.fail('Synthetic fixture lost its input proof')
            journal.write_bytes(prefix)
            manifest=read_receipt(root/'snapshot'/snapshot.MANIFEST)
            for entry in manifest['entries']:
                if entry['path']==path.relative_to(root/'snapshot').as_posix():
                    entry['path']='records/outcomes/'+revised['record_id']+'.json'
            manifest['entries'].sort(key=lambda e:e['path'])
            manifest_path=root/'snapshot'/snapshot.MANIFEST
            manifest_path.unlink();write_receipt(manifest_path,manifest)
            refresh_manifest(root/'snapshot')
            with self.assertRaisesRegex(snapshot.SnapshotError,'strict typed'):
                snapshot.recover_snapshot(root/'snapshot',root/'recovered')
            self.assertFalse((root/'recovered').exists())

    def test_global_budget_safe_paths_and_optimized_failures_are_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';make_store(source,2)
            with patch.object(snapshot,'MAX_RECORDS',1):
                with self.assertRaisesRegex(snapshot.SnapshotError,'capacity'):
                    snapshot.snapshot_manifest(source)
            with self.assertRaisesRegex(snapshot.SnapshotError,'inside source'):
                snapshot.export_snapshot(source,source/'nested')
            self.assertFalse((source/'nested').exists())
            with self.assertRaisesRegex(snapshot.SnapshotError,'outside every Git'):
                snapshot.export_snapshot(source,Path(__file__).resolve().parents[1]/'.local-data'/'forbidden-snapshot')
            destination=root/'existing';destination.mkdir()
            result=subprocess.run([sys.executable,'-O','-c',
                'from multisport_lab.pros004_snapshot import _new_root; _new_root('+repr(str(destination))+')'],
                cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('SnapshotError',result.stderr)


if __name__=='__main__':
    unittest.main()

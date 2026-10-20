"""Offline receipt snapshot integrity/recovery; no captures or real issuance."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import pros004_snapshot as snapshot
from multisport_lab.integrity import IntegrityError, canonical, digest, read_receipt, write_receipt
from multisport_lab.ledger import Ledger


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
            self.assertEqual(manifest['ledger_record_count'],2)
            self.assertEqual(manifest['completion_journal_count'],1)
            self.assertEqual(manifest['record_count'],3)
            entry=next(e for e in manifest['entries'] if e['entry_type']=='COMPLETION_JOURNAL')
            self.assertEqual(entry['raw_sha256'],hashlib.sha256(original).hexdigest())
            self.assertEqual(entry['encoded_bytes'],len(original))
            ack=snapshot.recover_snapshot(root/'snapshot',root/'recovered')
            self.assertTrue(ack['completion_journal_copied'])
            self.assertEqual((root/'recovered'/relative).read_bytes(),original)
            recovered=records.Pros004Store(root/'recovered',diagnostic=True)
            self.assertTrue(recovered.admission_status(fixture.event_ref)['timing_complete'])
            self.assertFalse(recovered.admission_status(fixture.event_ref)['eligible_for_comparison'])
            with patch.object(snapshot,'MAX_RECORDS',2):
                with self.assertRaisesRegex(snapshot.SnapshotError,'journal.*capacity'):
                    snapshot.snapshot_manifest(fixture.store.root)

    def test_torn_omitted_or_resealed_incorrect_journal_cannot_get_acknowledgment(self):
        from test_pros004_producer import ProducerFixture
        fixture=ProducerFixture(self)
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
        fixture=ProducerFixture(self)
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
            # The manifest and completion chain are valid hashes for the bad
            # body. Drop the journal for this legacy-style semantic-only case.
            journal=root/'snapshot'/snapshot.JOURNAL_RELATIVE_PATH
            journal.unlink();journal.parent.rmdir();journal.parent.parent.rmdir()
            manifest=read_receipt(root/'snapshot'/snapshot.MANIFEST)
            for entry in manifest['entries']:
                if entry['path']==path.relative_to(root/'snapshot').as_posix():
                    entry['path']='records/outcomes/'+revised['record_id']+'.json'
            manifest['entries']=[e for e in manifest['entries'] if e['entry_type']=='LEDGER_RECEIPT']
            manifest['entries'].sort(key=lambda e:e['path'])
            manifest['completion_journal_count']=0;manifest['record_count']=len(manifest['entries'])
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

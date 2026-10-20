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
from multisport_lab.integrity import IntegrityError, canonical, digest, read_receipt
from multisport_lab.ledger import Ledger


def make_store(root, count=2):
    store = Ledger(root)
    for index in range(count):
        store.append('input_captures','synthetic-'+str(index),{'note':'synthetic '+str(index)})
    return store


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
            with self.assertRaisesRegex(snapshot.SnapshotError,'interrupted'):
                snapshot.recover_snapshot(root/'snapshot',root/'readback')
            with self.assertRaisesRegex(snapshot.SnapshotError,'new destination'):
                snapshot.export_snapshot(source,root/'snapshot')
            self.assertEqual(snapshot.snapshot_manifest(source)['record_count'],2)

    def test_partial_model_original_is_preserved_without_missing_peer_generation(self):
        from test_pros004_producer import ProducerFixture
        from multisport_lab import pros004_producer as producer
        fixture=ProducerFixture(self)
        with self.assertRaises(IntegrityError):
            producer.issue_pair(fixture.store,fixture.event_ref,fixture.binding,player_id='10',
                                checkpoint=lambda ref:ref.kind!='forecasts')
        original=fixture.store.lookup_forecast(fixture.event_ref,'10','R0')
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

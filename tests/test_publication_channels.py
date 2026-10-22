"""Joint manifest5 integration; synthetic failures never create issuance."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import shutil
import unittest
from unittest.mock import patch

from multisport_lab.integrity import IntegrityError, canonical, digest, load_json
from multisport_lab.publication import build_site, read_manifest, REJECTED_UPDATE

ROOT=Path(__file__).resolve().parents[1]

class PublicationChannelsTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)

    def test_joint_build_keeps_each_typed_channel_and_original_research_bytes(self):
        originals={p.relative_to(ROOT):p.read_bytes() for p in (ROOT/'records').rglob('*.json')}
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'site'
            manifest=build_site(ROOT,out,build_commit='a'*40,now=self.now)
            self.assertEqual(manifest['schema_version'],6)
            self.assertIsNotNone(manifest['pros004'])
            self.assertIsNotNone(manifest['display'])
            self.assertIsNotNone(manifest['offers'])
            self.assertEqual(read_manifest(out/'data',now=self.now),manifest)
            nba=load_json(out/'data'/manifest['sports'][0]['path'])
            self.assertEqual(len(nba['forecasts']),6)
            self.assertEqual([nba[k] for k in ('offers','candidates','tickets')],[[],[],[]])
            self.assertEqual({len(f['categories']) for f in nba['forecasts']},{14})
        self.assertEqual(originals,{p.relative_to(ROOT):p.read_bytes() for p in (ROOT/'records').rglob('*.json')})

    def test_failed_fresh_research_has_explicit_catalog_error_and_independent_offers(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'site'
            with patch('multisport_lab.publication.research_nba',side_effect=IntegrityError('private source detail')):
                manifest=build_site(ROOT,out,build_commit='b'*40,now=self.now)
            self.assertIsNotNone(manifest['offers'])
            self.assertIn('catalog only',manifest['errors']['NBA'])
            self.assertFalse(manifest['sports'][0]['retained'])
            self.assertEqual(manifest['sports'][0]['error'],manifest['errors']['NBA'])
            self.assertNotIn('private source detail',str(manifest))
            nba=load_json(out/'data'/manifest['sports'][0]['path'])
            self.assertEqual(nba['forecasts'],[])
            self.assertEqual(len(nba['markets']),14)

    def test_failed_updates_retain_original_generation_clocks_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'site'
            first=build_site(ROOT,out,build_commit='a'*40,now=self.now)
            old=first['sports'][0]
            with patch('multisport_lab.publication.research_nba',side_effect=IntegrityError('bad ledger')),patch('multisport_lab.offer_publication.make_asset',side_effect=IntegrityError('secret source')):
                second=build_site(ROOT,out,build_commit='b'*40,now=self.now+timedelta(seconds=1))
            self.assertTrue(second['sports'][0]['retained'])
            self.assertEqual(second['sports'][0]['sha256'],old['sha256'])
            self.assertEqual(second['sports'][0]['generated_at'],old['generated_at'])
            self.assertTrue(second['offers']['retained'])
            self.assertEqual(second['offers']['generated_at'],first['offers']['generated_at'])
            self.assertIsNotNone(second['pros004'])
            self.assertIsNotNone(second['display'])

    def test_bad_optional_descriptor_cannot_poison_core_rebuild_or_open_external_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'site'
            manifest=build_site(ROOT,out,build_commit='a'*40,now=self.now)
            manifest['display']['path']='../private.json'
            manifest['pros004']['path']='../private.json'
            manifest['offers']['path']='../private.json'
            manifest['snapshot_id']=digest({k:v for k,v in manifest.items() if k!='snapshot_id'})
            (out/'data/manifest.json').write_bytes(canonical(manifest))
            with self.assertRaises(REJECTED_UPDATE):read_manifest(out/'data',now=self.now)
            second=build_site(ROOT,out,build_commit='b'*40,now=self.now+timedelta(seconds=1))
            self.assertIsNone(second['display_error'])
            self.assertIsNone(second['pros004_error'])
            self.assertIsNone(second['offers_error'])
            self.assertEqual(len(load_json(out/'data'/second['sports'][0]['path'])['forecasts']),6)

    def test_valid_nonempty_both_input_protocols_coexist_with_original_history_and_display(self):
        from multisport_lab import operational_pilot as op, pros004_inputs as inp
        from multisport_lab.pros004_records import Pros004Store
        from multisport_lab.publication_ledger import CompositeEnvelopeLedger
        from multisport_lab.ledger import LedgerRef
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'fixture';root.mkdir()
            for directory in ('web','config','records'):
                shutil.copytree(ROOT/directory,root/directory)
            before={p.relative_to(root):p.read_bytes() for p in (root/'records').rglob('*.json')}
            bridge=CompositeEnvelopeLedger(root)
            original=bridge.scan()['research_inputs'][op.ORIGINAL_HISTORY_ID]
            reference=LedgerRef('research_inputs',op.ORIGINAL_HISTORY_ID,digest(original))
            operational=op.OperationalStore(root,diagnostic=True)
            history=op.make_history_body(reference,root=root,mode='SYNTHETIC_DIAGNOSTIC')
            operational_ref=operational.persist(history,references=(reference,))
            pack=original['data']['source_pack']
            reserved=Pros004Store(root,diagnostic=True)
            reserved.ledger=CompositeEnvelopeLedger(root)
            reserved_ref=reserved.store_history(inp.make_history_body(pack['history'],pack['history_provenance'],mode='SYNTHETIC_DIAGNOSTIC'))
            self.assertEqual(operational.body(operational_ref)['history_rows'],26645)
            self.assertEqual(reserved.body(reserved_ref)['history_provenance']['normalized_panel_rows'],26645)
            self.assertEqual(len(op.OperationalStore(root,diagnostic=True).recover(replay=False)['records']),1)
            manifest=build_site(root,Path(tmp)/'site',build_commit='c'*40,now=datetime.now(timezone.utc))
            self.assertEqual(manifest['errors'],{})
            for channel in ('pros004','display','offers','paired_research'):
                self.assertIsNotNone(manifest[channel],channel)
                self.assertIsNone(manifest[channel+'_error'],channel)
            nba=load_json(Path(tmp)/'site/data'/manifest['sports'][0]['path'])
            self.assertEqual(len(nba['forecasts']),6)
            self.assertEqual({len(f['categories']) for f in nba['forecasts']},{14})
            display=load_json(Path(tmp)/'site/data'/manifest['display']['path'])
            self.assertEqual(len(display['catalog']['players']),6)
            paired=load_json(Path(tmp)/'site/data'/manifest['paired_research']['path'])
            self.assertEqual(paired['status'],'INACTIVE')
            self.assertEqual(paired['forecasts'],[])
            self.assertTrue(all((root/name).read_bytes()==raw for name,raw in before.items()))

    def test_nonempty_foreign_semantic_failure_does_not_hide_original_research_or_names(self):
        from multisport_lab.publication_ledger import CompositeEnvelopeLedger
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'fixture'
            root.mkdir()
            for directory in ('web','config','records'):
                shutil.copytree(ROOT/directory,root/directory)
            # Deliberately invalid typed meaning, but an independently valid
            # checksum/envelope. It is test evidence, never an actual issuance.
            ledger=CompositeEnvelopeLedger(root)
            ledger.append('research_inputs','synthetic malformed OP002 publication input',
                {'identity':{},'operational':{'schema_version':'nba-operational002-history-v1'}})
            manifest=build_site(root,Path(tmp)/'site',build_commit='c'*40,now=self.now+timedelta(seconds=30))
            nba=load_json(Path(tmp)/'site/data'/manifest['sports'][0]['path'])
            self.assertEqual(len(nba['forecasts']),6)
            self.assertIsNotNone(manifest['display'])
            self.assertIsNotNone(manifest['pros004'])
            self.assertIsNotNone(manifest['offers'])
            self.assertIsNone(manifest['paired_research'])
            self.assertIsNotNone(manifest['paired_research_error'])
            labels=load_json(Path(tmp)/'site/data'/manifest['display']['path'])
            self.assertEqual(len(labels['catalog']['players']),6)
            self.assertEqual(len(list((root/'records/research_inputs').glob('*.json'))),2)

    def test_rejected_intermediate_auxiliary_bytes_are_excluded_from_artifact(self):
        from multisport_lab.offer_publication import make_asset
        rejected=make_asset(ROOT,now=self.now)
        rejected['status']='NOT_ADMITTED'
        rejected['unavailable_reasons']=['private rejected publisher body']
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'site'
            with patch('multisport_lab.offer_publication.make_asset',return_value=rejected):
                manifest=build_site(ROOT,out,build_commit='a'*40,now=self.now)
            self.assertIsNone(manifest['offers'])
            self.assertIsNotNone(manifest['offers_error'])
            self.assertTrue(all(b'private rejected publisher body' not in path.read_bytes() for path in (out/'data').iterdir()))
            self.assertIsNotNone(manifest['display'])
            self.assertIsNotNone(manifest['pros004'])

    def test_strict_legacy_manifest_three_and_four_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'site'
            current=build_site(ROOT,out,build_commit='a'*40,now=self.now)
            for version,keep in [(3,'pros004'),(4,'display')]:
                old={k:v for k,v in current.items() if k not in {'pros004','pros004_error','display','display_error','offers','offers_error','paired_research','paired_research_error','daily_research','daily_research_error'}}
                old.update(schema_version=version,**{keep:current[keep],keep+'_error':None})
                old['snapshot_id']=digest({k:v for k,v in old.items() if k!='snapshot_id'})
                (out/'data/manifest.json').write_bytes(canonical(old))
                self.assertEqual(read_manifest(out/'data',now=self.now)['schema_version'],version)
                old['offers']=None
                old['snapshot_id']=digest({k:v for k,v in old.items() if k!='snapshot_id'})
                (out/'data/manifest.json').write_bytes(canonical(old))
                with self.assertRaises(IntegrityError):read_manifest(out/'data',now=self.now)

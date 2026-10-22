"""Synthetic external raw-byte retention and private-backend contract risks."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import pros004_raw as rawmod
from multisport_lab.integrity import IntegrityError, canonical, digest, read_receipt, stamp


def plan():
    return {'schema_version':'nba-pros004-private-raw-plan-v1','backend_id':'diagnostic-private-fixture',
            'privacy':'PRIVATE_VERIFIED','durability':'PRIMARY_DURABLE','reviewed_evidence_sha256':'a'*64,
            'permitted_raw_retention':True,'retention_through':'INDEFINITE_REVIEWED'}


class MemoryTransport:
    def __init__(self,*,visibility='PRIVATE',corrupt=False):
        self.visibility=visibility;self.corrupt=corrupt;self.data={};self.calls=[]
    def describe(self):
        return {'backend_id':'diagnostic-private-fixture','visibility':self.visibility}
    def put(self,reference,raw):
        self.calls.append('put');self.data[reference['raw_sha256']]=raw
        return 'fixture:'+reference['raw_sha256']
    def readback(self,locator):
        self.calls.append('independent-readback');raw=self.data[locator.split(':')[1]]
        return raw+b'changed' if self.corrupt else raw


class Pros004RawTests(unittest.TestCase):
    def retain(self,store,*,mode='SYNTHETIC_DIAGNOSTIC',event='999000004',data=b'{"synthetic":true}',**kwargs):
        return store.retain(data,mode=mode,event_id=event,
            source_url=('https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event='+event
                        if mode=='REAL_TIME_CAPTURED' else 'synthetic://pros004/outcome/'+event),
            observed_at=datetime.now(timezone.utc)-timedelta(seconds=10),**kwargs)

    def test_restart_idempotency_preserves_original_bytes_and_clocks(self):
        with tempfile.TemporaryDirectory() as folder:
            store=rawmod.RawEvidenceArchive(folder)
            observed=datetime.now(timezone.utc)-timedelta(seconds=1)
            kwargs={'mode':'SYNTHETIC_DIAGNOSTIC','event_id':'999000004',
                    'source_url':'synthetic://pros004/outcome/999000004','observed_at':observed}
            reference=store.retain(b'EXPLICIT_SYNTHETIC_BYTES',**kwargs)
            body,data=store.read(reference)
            path=Path(folder)/'captures'/(reference['capture_id']+'.json');original=path.read_bytes()
            reloaded=rawmod.RawEvidenceArchive(folder)
            with patch.object(rawmod,'_now',return_value=datetime.now(timezone.utc)+timedelta(minutes=1)):
                second=reloaded.retain(data,**kwargs)
            self.assertEqual(second,reference);self.assertEqual(path.read_bytes(),original)
            self.assertEqual(reloaded.recover(),[reference])
            self.assertLessEqual(body['source_observed_at'],body['raw_persistence_completed_at'])

    def test_correction_appends_link_and_keeps_original(self):
        with tempfile.TemporaryDirectory() as folder:
            store=rawmod.RawEvidenceArchive(folder);first=self.retain(store)
            original=store.read(first)[1]
            second=self.retain(store,data=b'{"synthetic_correction":true}',supersedes=first,
                               correction_reason='Invented diagnostic correction only')
            self.assertEqual(store.read(second)[0]['supersedes'],first)
            self.assertEqual(store.read(first)[1],original)
            self.assertEqual(len(store.recover()),2)
            with self.assertRaisesRegex(IntegrityError,'changes event'):
                self.retain(store,event='999000005',data=b'other',supersedes=first,correction_reason='Invented')

    def test_hash_consistent_future_clock_and_tampered_raw_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            store=rawmod.RawEvidenceArchive(folder);reference=self.retain(store)
            blob=Path(folder)/'blobs'/(reference['raw_sha256']+'.bin');original=blob.read_bytes()
            blob.write_bytes(b'x'*len(original))
            with self.assertRaisesRegex(IntegrityError,'hash changed'):store.read(reference)
            blob.write_bytes(original)
            path=Path(folder)/'captures'/(reference['capture_id']+'.json')
            envelope=json.loads(path.read_text());body=envelope['payload']
            body['raw_persistence_completed_at']=stamp(datetime.now(timezone.utc)+timedelta(minutes=1))
            envelope['payload_sha256']=digest(body);path.write_bytes(canonical(envelope))
            changed={**reference,'payload_sha256':digest(body)}
            with self.assertRaisesRegex(IntegrityError,'clocks conflict'):store.read(changed)

    def test_public_destinations_and_actual_raw_publication_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            store=rawmod.RawEvidenceArchive(folder);reference=self.retain(store)
            public=MemoryTransport(visibility='PUBLIC')
            with self.assertRaisesRegex(IntegrityError,'reviewed private'):
                store.checkpoint_private(reference,public,plan=plan())
            self.assertEqual(public.calls,[])
            actual=self.retain(store,mode='REAL_TIME_CAPTURED')
            transport=MemoryTransport()
            with self.assertRaisesRegex(IntegrityError,'INACTIVE'):
                store.checkpoint_private(actual,transport,plan=plan())
            self.assertEqual(transport.calls,[])

    def test_private_synthetic_transport_needs_exact_independent_readback(self):
        with tempfile.TemporaryDirectory() as folder:
            store=rawmod.RawEvidenceArchive(folder);reference=self.retain(store)
            backend=MemoryTransport();ack=store.checkpoint_private(reference,backend,plan=plan())
            self.assertEqual(backend.calls,['put','independent-readback'])
            self.assertEqual(ack['raw_sha256'],reference['raw_sha256'])
            self.assertFalse(ack['actual_raw_primary_durability_established'])
            self.assertFalse(ack['source_permission_established'])
            with self.assertRaisesRegex(IntegrityError,'differs'):
                store.checkpoint_private(reference,MemoryTransport(corrupt=True),plan=plan())

    def test_evaluation_start_is_not_a_primary_retention_expiry(self):
        candidate = plan()
        candidate['retention_through'] = '2026-11-25T00:00:00.000000Z'
        with self.assertRaisesRegex(IntegrityError, 'indefinite retention'):
            rawmod.validate_private_retention_plan(candidate)

    def test_outcome_link_preserves_raw_identity_and_original_source_clocks(self):
        with tempfile.TemporaryDirectory() as folder:
            store = rawmod.RawEvidenceArchive(folder)
            reference = self.retain(store)
            capture, _ = store.read(reference)
            body = {'schema_version':'nba-pros004-outcome-v1',
                'study_id':'NBA-ALL13-JOINT-PROS-004', 'mode':'SYNTHETIC_DIAGNOSTIC',
                'event_id':capture['event_id'], 'event_version':'a'*64,
                'event_starts_at':'2026-10-20T00:00:00.000000Z',
                'player_id':'10', 'team_id':'8', 'opponent_id':'2', 'status':'MISSING',
                'source_observed_at':capture['source_observed_at'], 'source_updated_at':None,
                'normalized_at':stamp(datetime.now(timezone.utc)),
                'source_raw_sha256':capture['raw_sha256'], 'normalizer_version':'SYNTHETIC_ONLY',
                'primitives':None, 'minutes':None, 'minutes_precision':None, 'categories':{}}
            outcome = {**body, 'outcome_id':digest(body)}
            result = store.verify_outcome_reference(outcome, reference)
            self.assertTrue(result['exact_byte_identity_and_source_clocks_verified'])
            self.assertFalse(result['actual_raw_primary_durability_established'])
            for field,value in [('event_id','999000005'), ('source_raw_sha256','b'*64),
                                ('source_observed_at',stamp(datetime.now(timezone.utc)-timedelta(seconds=5)))]:
                changed = {**body, field:value}
                changed['outcome_id'] = digest(changed)
                with self.assertRaisesRegex(IntegrityError, 'source clocks conflict'):
                    store.verify_outcome_reference(changed, reference)

    def test_source_identity_budgets_orphans_and_git_roots_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            store=rawmod.RawEvidenceArchive(folder)
            with patch.object(rawmod,'MAX_ARCHIVE_BYTES',1):
                with self.assertRaisesRegex(IntegrityError,'capacity'):self.retain(store)
            self.assertFalse((Path(folder)/'blobs').exists())
            with self.assertRaisesRegex(IntegrityError,'outcome-source identity'):
                store.retain(b'fake',mode='SYNTHETIC_DIAGNOSTIC',event_id='999000004',
                             source_url='https://arbitrary.example/',observed_at=datetime.now(timezone.utc))
            (Path(folder)/'blobs').mkdir();(Path(folder)/'blobs'/'.raw-interrupted').write_text('partial')
            with self.assertRaisesRegex(IntegrityError,'interrupted'):store.recover()
        with self.assertRaisesRegex(IntegrityError,'outside every Git'):
            rawmod.RawEvidenceArchive(Path(__file__).resolve().parents[1]/'.local-data'/'raw-not-admitted')


if __name__=='__main__':
    unittest.main()

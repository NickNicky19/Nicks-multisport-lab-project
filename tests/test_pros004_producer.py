"""Synthetic producer timing/coherence/recovery tests; no genuine issuance."""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import pros004_inputs as inp
from multisport_lab import pros004_producer as prod
from multisport_lab import pros004_records as rec
from multisport_lab.baseline import ForecastTarget, forecast_reference
from multisport_lab.development_003 import WorkloadPrior
from multisport_lab.integrity import IntegrityError, digest, stamp
from multisport_lab.ledger import LedgerRef
from multisport_lab.pregame_sources import compact_history, _panel_bytes
from test_pregame_sources import tiny_history, provenance
from test_pros004_inputs import input_fixture, NOW, START, reseal

CUTOFF=START-timedelta(minutes=90)
ISSUE=CUTOFF+timedelta(seconds=5)


class ProducerFixture:
    """Only temporary synthetic data; original frozen modules are merely patched."""
    def __init__(self, case):
        stack=ExitStack();case.addCleanup(stack.close);self.stack=stack
        base=tiny_history()[0]
        rows=[replace(base,event_id='1001',player_id='10',minutes=20),
              replace(base,event_id='1002',player_id='10',event_start=base.event_start+timedelta(days=2),minutes=35,rebounds=7,dreb=6),
              replace(base,event_id='1003',player_id='20',event_start=base.event_start+timedelta(days=3),minutes=10,blocks=3)]
        p=provenance(rows);raw=_panel_bytes(rows)
        for name,value in (('PANEL_SHA256',hashlib.sha256(raw).hexdigest()),('PANEL_ROWS',len(rows)),('PANEL_BYTES',len(raw))):
            stack.enter_context(patch.object(inp,name,value))
        stack.enter_context(patch.object(inp,'_original_provenance',return_value=p))
        self.input_clock=stack.enter_context(patch.object(inp,'_now',return_value=NOW))
        self.producer_clock=stack.enter_context(patch.object(prod,'_now',return_value=ISSUE))
        self.record_clock=stack.enter_context(patch.object(rec,'_now',return_value=NOW))
        self.ledger_clock=stack.enter_context(patch('multisport_lab.ledger._now',return_value=NOW))
        self.baseline_clock=stack.enter_context(patch('multisport_lab.baseline._now',return_value=ISSUE))
        self.tmp=stack.enter_context(tempfile.TemporaryDirectory())
        self.store=rec.Pros004Store(self.tmp,diagnostic=True)
        self.history=inp.make_history_body(compact_history(rows),p,mode='SYNTHETIC_DIAGNOSTIC')
        self.history_ref=self.store.store_history(self.history)
        self.event=input_fixture();self.event['history_ref']=self.history_ref.to_record();reseal(self.event,'sourcepack_id')
        self.event_ref=self.store.store_event(self.event,self.history_ref)
        self.store.complete_checkpoint(self.event_ref,self.ack)
        self.input_final_checkpoint=self.store.finalize_checkpoint((self.event_ref,),self.ack)
        self.record_clock.return_value=ISSUE;self.ledger_clock.return_value=ISSUE
        self.binding=prod.make_source_binding(diagnostic=True)

    def ack(self, reference):
        # Explicitly fictitious remote metadata for timing/control tests only.
        from multisport_lab.pros004_snapshot import snapshot_manifest
        return {'schema_version':'nba-pros004-remote-checkpoint-v1','reference':reference.to_record(),
            'remote_repository':'NickNicky19/Nicks-multisport-lab-project','remote_branch':'records/SYNTHETIC_ONLY',
            'remote_commit':'a'*40,'snapshot_sha256':digest(snapshot_manifest(self.tmp)),
            'readback_raw_sha256':self.store._raw_sha256(reference),
            'remote_completed_at':stamp(self.record_clock.return_value)}

    def issue(self, store=None, **kwargs):
        kwargs.setdefault('checkpoint',self.ack)
        kwargs.setdefault('input_final_checkpoint',self.input_final_checkpoint)
        return prod.issue_pair(store or self.store,self.event_ref,self.binding,**kwargs)

    def generate(self, model='R0', player='10'):
        return prod.generate_forecast(self.event,self.history,event_ref=self.event_ref,
            history_ref=self.history_ref,player_id=player,model_key=model,producer_binding=self.binding)


class Pros004ProducerTests(unittest.TestCase):
    def test_both_producers_reuse_exact_laws_all_markets_and_full_joint_recipe(self):
        f=ProducerFixture(self)
        rows=inp.history_rows(f.history)
        target=ForecastTarget(f.event['event']['event_id'],'10',START)
        original=forecast_reference(rows,target)
        kernel=WorkloadPrior(rows).forecast(target,original)
        for key,expected in (('R0',original),('K0',kernel)):
            body,reference=f.generate(key)
            self.assertEqual(body['model_version'],prod.MODEL_VERSIONS[key])
            self.assertEqual(body['producer_version'],prod.PRODUCER_VERSIONS[key])
            self.assertEqual(len(body['categories']),14)
            self.assertEqual(body['joint_recipe']['omitted_atoms'],0)
            self.assertEqual(body['joint_recipe']['support_atom_count'],3)
            self.assertEqual(prod.joint_fingerprint(reference),digest([r.to_record() for r in reference.support]))
            self.assertEqual(reference.support,expected.support)
            self.assertEqual(body['categories'],prod._categories(expected))
            self.assertEqual(body['reported_minutes'],prod._minutes(expected))
            self.assertEqual(body['qualification'],'UNAVAILABLE')
            self.assertEqual(prod.verify_replay(body,f.event,f.history)['verified_atom_count'],3)

    def test_live_admission_fails_closed_for_any_caller_activation_flag(self):
        f=ProducerFixture(self)
        for activation in (None,True,{'status':'ACTIVE','independent_readback':True}):
            with self.assertRaisesRegex(IntegrityError,'READINESS_ONLY'):
                prod.validate_activation_binding(activation,producer_binding=f.binding,event_body=f.event)
        actual=rec.Pros004Store(f.tmp,diagnostic=False,activation={'status':'ACTIVE'})
        with self.assertRaisesRegex(IntegrityError,'READINESS_ONLY'):
            prod.issue_pair(actual,f.event_ref,f.binding,player_id='10')
        with self.assertRaisesRegex(IntegrityError,'only unchanged R0 and K0'):
            f.generate('S0')

    def test_input_gate_rejects_live_event_bound_to_diagnostic_history(self):
        f=ProducerFixture(self)
        event=deepcopy(f.event);event['mode']='REAL_TIME_CAPTURED'
        # Isolate this relationship guard from the separately tested structural
        # validators. It must fail before any activation or generation call.
        with patch.object(inp,'validate_event',return_value=event), patch.object(inp,'validate_history',return_value=f.history):
            with self.assertRaisesRegex(IntegrityError,'evidence lanes differ'):
                prod._input_gate(event,f.history)

    def test_early_late_and_generation_completion_cannot_issue(self):
        f=ProducerFixture(self)
        for clock in (CUTOFF-timedelta(microseconds=1),CUTOFF+timedelta(minutes=5,microseconds=1)):
            f.producer_clock.return_value=clock
            with self.assertRaisesRegex(IntegrityError,'outside'):
                f.generate()
        # Exceed the clock budget after fitting/serialization rather than changing input.
        f.producer_clock.return_value=ISSUE
        real_fit=prod._fit_laws
        def slow(*args,**kwargs):
            result=real_fit(*args,**kwargs)
            f.producer_clock.return_value=ISSUE+timedelta(seconds=121)
            return result
        with patch.object(prod,'_fit_laws',side_effect=slow):
            with self.assertRaisesRegex(IntegrityError,'latency'):
                f.generate()
        self.assertFalse(list((Path(f.tmp)/'records/forecasts').glob('*.json')))

    def test_partial_checkpoint_failure_retains_original_and_late_peer_missing(self):
        f=ProducerFixture(self)
        def fail_after_original(ref):
            if ref.kind=='forecasts':
                raise OSError('unacknowledged remote checkpoint')
            return f.ack(ref)
        with self.assertRaisesRegex(OSError,'unacknowledged'):
            f.issue(player_id='10',checkpoint=fail_after_original)
        first=f.store.lookup_forecast(f.event_ref,'10','R0')
        original=f.store.ledger._path(first.kind,first.record_id).read_bytes()
        self.assertIsNone(f.store.lookup_forecast(f.event_ref,'10','K0'))
        f.producer_clock.return_value=CUTOFF+timedelta(minutes=6)
        f.record_clock.return_value=CUTOFF+timedelta(minutes=6)
        f.ledger_clock.return_value=CUTOFF+timedelta(minutes=6)
        with patch.object(prod,'generate_forecast',side_effect=AssertionError('late recovery cannot generate')):
            report=f.issue(store=rec.Pros004Store(f.tmp,diagnostic=True),player_id='10')
        self.assertEqual(report['status'],'PARTIAL_WINDOW_CLOSED')
        self.assertEqual(report['retained_models'],1)
        self.assertEqual(report['issued_models'],0)
        self.assertEqual(original,f.store.ledger._path(first.kind,first.record_id).read_bytes())

    def test_timely_resume_only_generates_missing_peer_and_preserves_clocks(self):
        f=ProducerFixture(self)
        calls=[]
        def fail_once(ref):
            calls.append(ref.kind)
            return f.ack(ref) if ref.kind!='forecasts' else False
        with self.assertRaisesRegex(IntegrityError,'structured independent'):
            f.issue(player_id='10',checkpoint=fail_once)
        original=f.store.lookup_forecast(f.event_ref,'10','R0')
        raw=f.store.ledger._path(original.kind,original.record_id).read_bytes()
        generation=prod.generate_forecast;models=[]
        def track(*args,**kwargs):
            models.append(kwargs['model_key']);return generation(*args,**kwargs)
        with patch.object(prod,'generate_forecast',side_effect=track):
            report=f.issue(store=rec.Pros004Store(f.tmp,diagnostic=True),player_id='10',checkpoint=f.ack)
        self.assertEqual(models,['K0'])
        self.assertEqual(report['retained_models'],2)
        self.assertEqual(report['timing_complete_models'],2)
        self.assertEqual(report['issued_models'],0)
        self.assertEqual(raw,f.store.ledger._path(original.kind,original.record_id).read_bytes())
        with patch.object(prod,'generate_forecast',side_effect=AssertionError('duplicate attempt')):
            f.issue(player_id='10')

    def test_interrupted_final_prefix_flush_retries_originals_without_generation(self):
        f=ProducerFixture(self)
        real=f.store.finalize_checkpoint
        with patch.object(f.store,'finalize_checkpoint',side_effect=OSError('interrupted final proof publication')):
            with self.assertRaisesRegex(OSError,'final proof publication'):
                f.issue(player_id='10')
        refs=[f.store.lookup_forecast(f.event_ref,'10',model) for model in ('R0','K0')]
        before=[f.store.ledger._path(ref.kind,ref.record_id).read_bytes() for ref in refs]
        journal_before=rec.completion.journal_path(f.tmp).read_bytes()
        with patch.object(prod,'generate_forecast',side_effect=AssertionError('final flush must not regenerate')):
            report=f.issue(store=rec.Pros004Store(f.tmp,diagnostic=True),player_id='10')
        self.assertTrue(report['final_checkpoint']['timely'])
        self.assertEqual(report['metadata_publication_status'],'INDEPENDENTLY_RECOVERED_CURRENT_PREFIX')
        self.assertEqual(before,[f.store.ledger._path(ref.kind,ref.record_id).read_bytes() for ref in refs])
        self.assertEqual(journal_before,rec.completion.journal_path(f.tmp).read_bytes())
        for clock in (f.producer_clock,f.record_clock,f.ledger_clock):
            clock.return_value=CUTOFF+timedelta(seconds=301)
        with patch.object(prod,'generate_forecast',side_effect=AssertionError('late recovery cannot regenerate')):
            late=f.issue(store=rec.Pros004Store(f.tmp,diagnostic=True),player_id='10')
        self.assertFalse(late['final_checkpoint']['timely'])
        self.assertEqual(late['metadata_publication_status'],'LATE_METADATA_PUBLICATION')

    def test_missing_or_invalid_original_input_phase_receipt_prevents_generation(self):
        f=ProducerFixture(self)
        with patch.object(prod,'generate_forecast',side_effect=AssertionError('unproved phase cannot generate')):
            missing=f.issue(player_id='10',input_final_checkpoint=None)
            self.assertEqual(missing['status'],'INPUT_FINAL_CHECKPOINT_REQUIRED')
            self.assertFalse(missing['generation_attempted'])
            for field,value in [('references',[f.history_ref.to_record()]),
                    ('snapshot_sha256','e'*64),('journal_raw_sha256','e'*64),
                    ('completed_at',stamp(CUTOFF-timedelta(minutes=10)+timedelta(microseconds=1)))]:
                with self.subTest(field=field):
                    changed=deepcopy(f.input_final_checkpoint);changed[field]=value
                    with self.assertRaises(IntegrityError):
                        f.issue(player_id='10',input_final_checkpoint=changed)
        self.assertIsNone(f.store.lookup_forecast(f.event_ref,'10','R0'))
        self.assertIsNone(f.store.lookup_forecast(f.event_ref,'10','K0'))
        # A missing phase receipt on recovery never permits replacement of an
        # existing original, even though a valid fresh receipt would allow its
        # genuinely missing peer to proceed while timely.
        def partial(reference):
            if reference.kind=='forecasts':raise OSError('synthetic partial original')
            return f.ack(reference)
        with self.assertRaisesRegex(OSError,'partial original'):
            f.issue(player_id='10',checkpoint=partial)
        ref=f.store.lookup_forecast(f.event_ref,'10','R0')
        original=f.store.ledger._path(ref.kind,ref.record_id).read_bytes()
        with patch.object(prod,'generate_forecast',side_effect=AssertionError('missing receipt recovery cannot generate')):
            recovery=f.issue(store=rec.Pros004Store(f.tmp,diagnostic=True),player_id='10',input_final_checkpoint=None)
        self.assertEqual(recovery['status'],'INPUT_FINAL_CHECKPOINT_REQUIRED')
        self.assertEqual(recovery['retained_models'],1)
        self.assertEqual(f.store.ledger._path(ref.kind,ref.record_id).read_bytes(),original)

    def test_input_phase_snapshot_reconstruction_rejects_ambiguous_tied_receipts(self):
        f=ProducerFixture(self)
        # This new receipt was absent from the original remote input snapshot.
        # A forged/tied pre-write clock cannot silently choose a convenient
        # subset when reconstructing that snapshot on restart.
        f.record_clock.return_value=f.input_clock.return_value
        f.ledger_clock.return_value=f.input_clock.return_value
        f.store.store_manifest()
        f.record_clock.return_value=ISSUE;f.ledger_clock.return_value=ISSUE
        with patch.object(prod,'generate_forecast',side_effect=AssertionError('ambiguous input cannot generate')):
            with self.assertRaisesRegex(IntegrityError,'cannot be recovered unambiguously'):
                f.issue(player_id='10')

    def test_before_persistence_interruption_has_no_original_and_can_retry_timely(self):
        f=ProducerFixture(self)
        real=f.store.persist_forecast
        with patch.object(f.store,'persist_forecast',side_effect=OSError('before atomic link')):
            with self.assertRaisesRegex(OSError,'before atomic'):
                f.issue(player_id='10')
        self.assertIsNone(f.store.lookup_forecast(f.event_ref,'10','R0'))
        report=f.issue(player_id='10')
        self.assertEqual(report['retained_models'],2)
        self.assertEqual(report['timing_complete_models'],2)
        self.assertEqual(report['issued_models'],0)

    def test_interruption_immediately_after_atomic_persistence_recovers_original(self):
        f=ProducerFixture(self)
        persist=f.store.persist_forecast
        def linked_then_interrupted(*args,**kwargs):
            persist(*args,**kwargs)
            raise OSError('interrupted after atomic link')
        with patch.object(f.store,'persist_forecast',side_effect=linked_then_interrupted):
            with self.assertRaisesRegex(OSError,'after atomic link'):
                f.issue(player_id='10')
        original=f.store.lookup_forecast(f.event_ref,'10','R0')
        self.assertIsNotNone(original)
        raw=f.store.ledger._path(original.kind,original.record_id).read_bytes()
        generation=prod.generate_forecast;models=[]
        def track(*args,**kwargs):
            models.append(kwargs['model_key']);return generation(*args,**kwargs)
        with patch.object(prod,'generate_forecast',side_effect=track):
            report=f.issue(store=rec.Pros004Store(f.tmp,diagnostic=True),player_id='10')
        self.assertEqual(models,['K0'])
        self.assertEqual(report['retained_models'],2)
        self.assertEqual(report['timing_complete_models'],2)
        self.assertEqual(report['issued_models'],0)
        self.assertEqual(raw,f.store.ledger._path(original.kind,original.record_id).read_bytes())

    def test_pair_before_window_and_failed_admission_ack_never_start_generation(self):
        f=ProducerFixture(self)
        f.producer_clock.return_value=CUTOFF-timedelta(seconds=1)
        with patch.object(prod,'generate_forecast',side_effect=AssertionError('early generation')):
            report=f.issue(player_id='10')
        self.assertEqual(report['status'],'ISSUANCE_NOT_YET_OPEN')
        self.assertFalse(report['generation_attempted'])
        self.assertIsNone(report['claim_ref'])
        f.producer_clock.return_value=ISSUE
        with patch.object(prod,'generate_forecast',side_effect=AssertionError('unacknowledged admission')):
            with self.assertRaisesRegex(IntegrityError,'structured independent'):
                f.issue(player_id='10',checkpoint=lambda ref:False)
        self.assertIsNone(f.store.lookup_forecast(f.event_ref,'10','R0'))
        self.assertIsNone(f.store.lookup_forecast(f.event_ref,'10','K0'))

    def test_changed_binding_or_event_cannot_create_another_original(self):
        f=ProducerFixture(self)
        f.issue(player_id='10')
        changed=deepcopy(f.binding);changed['runtime']['python']+='changed'
        with self.assertRaisesRegex(IntegrityError,'source/runtime changed'):
            prod.issue_pair(f.store,f.event_ref,changed,player_id='10')
        body,law=f.generate()
        body['event_version']='f'*64;body['forecast_id']=digest({k:v for k,v in body.items() if k!='forecast_id'})
        with self.assertRaisesRegex(IntegrityError,'target/event/version'):
            prod.validate_forecast_record(body,f.event,f.history)

    def test_replay_rejects_changed_joint_or_original_probability_without_rewriting(self):
        f=ProducerFixture(self);body,law=f.generate('K0')
        changed=deepcopy(body);changed['joint_recipe']['joint_sha256']='f'*64
        changed['forecast_id']=digest({k:v for k,v in changed.items() if k!='forecast_id'})
        with self.assertRaisesRegex(IntegrityError,'atom identities/lines/weights'):
            prod.verify_replay(changed,f.event,f.history)
        wrong=deepcopy(body);wrong['joint_recipe']['omitted_atoms']=1
        wrong['forecast_id']=digest({k:v for k,v in wrong.items() if k!='forecast_id'})
        with self.assertRaisesRegex(IntegrityError,'dropped atoms'):
            prod.validate_forecast_record(wrong,f.event,f.history)
        bad=deepcopy(body);bad['categories'][0]['pmf'][0]['probability']='0'
        bad['forecast_id']=digest({k:v for k,v in bad.items() if k!='forecast_id'})
        with self.assertRaisesRegex(IntegrityError,'positive probability'):
            prod.validate_forecast_record(bad,f.event,f.history)

    def test_source_binding_requires_all_reviewed_bytes_and_optimized_guard_survives(self):
        f=ProducerFixture(self)
        with self.assertRaisesRegex(IntegrityError,'differs from reviewed commit'):
            prod.make_source_binding('735a464e9e8718303ef481abf711a8969de56694')
        command=[sys.executable,'-O','-c',"from multisport_lab.pros004_producer import validate_activation_binding; validate_activation_binding(True,producer_binding={},event_body={})"]
        result=subprocess.run(command,capture_output=True,text=True,cwd=Path(__file__).resolve().parents[1])
        self.assertNotEqual(result.returncode,0)
        self.assertIn('READINESS_ONLY',result.stderr)

    def test_law_diagnostic_only_accepts_invented_event_and_has_no_issuance_or_scores(self):
        f=ProducerFixture(self)
        rows=inp.history_rows(f.history)
        target=ForecastTarget('DIAGNOSTIC_PROS004','10',START)
        result=prod.diagnostic_distributions(rows,target)
        self.assertEqual(result['issued_forecasts'],0);self.assertEqual(result['statistical_scores'],0)
        self.assertEqual(set(result['laws']),{'R0','K0'})
        self.assertTrue(all(len(value['categories'])==14 for value in result['laws'].values()))
        with self.assertRaisesRegex(IntegrityError,'invented event'):
            prod.diagnostic_distributions(rows,ForecastTarget('401900001','10',START))


if __name__=='__main__':
    unittest.main()

"""Synthetic one-shot phase/control tests; no provider or real model execution."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import scheduled_cycle as runner
from multisport_lab import manual_cycle as guard
from multisport_lab.integrity import digest,read_receipt,stamp,utc,write_receipt
from multisport_lab.ledger import LedgerRef


class ScheduledCycleTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.plan=read_receipt(guard.ROOT/runner.PLAN_PATH)
        self.selection=read_receipt(guard.ROOT/runner.SELECTION_PATH)
        self.actual=runner.PREPARATION_START
        self.events=[];self.sleeps=[];self.saved={};self.binding=None;self.intents={};self.capture_intent=False
        self.retained_inputs={}
        self.input_ref=LedgerRef('research_inputs','b'*64,'c'*64)
        self.clock=self.stack.enter_context(patch.object(runner,'_now',side_effect=lambda:self.actual))
        self.stack.enter_context(patch.object(runner,'_sleep',side_effect=self.sleep))
        self.stack.enter_context(patch('urllib.request.urlopen',side_effect=AssertionError('provider HTTP forbidden')))
        self.stack.enter_context(patch.object(guard,'load_plan',return_value=deepcopy(self.plan)))
        self.recover_mock=self.stack.enter_context(patch.object(guard,'recover',side_effect=self.recover))
        self.stack.enter_context(patch.object(guard,'preflight',side_effect=self.preflight))
        self.stack.enter_context(patch.object(guard,'bind',side_effect=self.bind))
        self.stack.enter_context(patch.object(guard,'issue',side_effect=self.issue))
        self.generation=self.stack.enter_context(patch.object(guard.producer,'generate',side_effect=self.generate))
        self.capture=self.stack.enter_context(patch.object(runner,'capture_espn',return_value=({}, {}, [])))
        self.history=self.stack.enter_context(patch.object(runner,'history_from_input_record',return_value=({'synthetic':True},{'original_clocks':'unchanged'})))
        self.stack.enter_context(patch.object(runner,'make_pack',return_value={'synthetic_source_pack':True}))
        self.stack.enter_context(patch.object(runner,'load_pack',side_effect=lambda path:read_receipt(path)))
        self.stack.enter_context(patch.object(runner,'read_receipt',side_effect=self.read))
        owner=self

        class MemoryLedger:
            def __init__(self,root):self.root=Path(root)
            def record_research_inputs(self,pack):
                owner.events.append('INPUT_PERSISTED')
                owner.retained_inputs.setdefault(digest(pack),{'source_pack':deepcopy(pack),'received_at':stamp(owner.actual)})
                return owner.input_ref
            def issue_prospective(self,bundle,*,reference,input_ref):
                player=bundle['player_id']
                if player in owner.saved:raise AssertionError('duplicate original')
                ref=LedgerRef('forecasts',digest({'player':player}),digest(bundle))
                owner.saved[player]={'reference':ref.to_record(),'bundle':deepcopy(bundle),
                                     'received_at':stamp(owner.actual)}
                owner.events.append('LOCAL_ORIGINAL:'+player)
                return ref
            def read(self,reference):
                if reference.kind!='forecasts':raise AssertionError('unexpected fixture read')
                saved=next(value for value in owner.saved.values() if value['reference']==reference.to_record())
                return {'received_at':saved['received_at'],'data':{'bundle':saved['bundle']}}

        self.stack.enter_context(patch.object(runner,'Ledger',MemoryLedger))
        self.stack.enter_context(patch.object(guard,'Ledger',MemoryLedger))

    def sleep(self,seconds):
        self.assertGreater(seconds,0);self.assertLessEqual(seconds,30)
        self.sleeps.append(seconds);self.actual+=timedelta(seconds=seconds)

    def read(self,path,**kwargs):
        path=Path(path)
        if path==self.root/runner.SELECTION_PATH:return deepcopy(self.selection)
        if path.name.endswith('-binding.json') and self.binding is not None:return deepcopy(self.binding)
        raise AssertionError(f'unexpected fixture receipt {path}')

    def recover(self,*args,**kwargs):
        count=len(self.saved)
        return {'status':'NOT_READY' if self.binding is None else 'COMPLETE' if count==4 else 'PARTIAL' if count else 'BOUND_PENDING',
                'input_reference':self.binding['input_reference'] if self.binding else None,
                'selected_forecasts_retained':count,
                'forecast_records':{p:{'reference':s['reference'],'forecast_id':s['bundle']['forecast_id'],
                                       'issued_at':s['bundle']['issued_at'],'received_at':s['received_at']}
                                    for p,s in self.saved.items()},
                'missing_player_ids':[p for p in guard.PLAYERS if p not in self.saved]}

    def preflight(self,*args,**kwargs):
        self.assertTrue(kwargs['require_capture_window'])
        self.assertTrue(utc(self.plan['capture_opens_at'])<=self.actual<utc(self.plan['capture_closes_at']))
        return self.recover()

    def bind(self,record_id,*args,**kwargs):
        self.assertEqual(record_id,self.input_ref.record_id)
        self.binding={'schema_version':'nba-manual-cycle-binding-v1','cycle_id':guard.CYCLE_ID,
                      'plan_sha256':digest(self.plan),'producer_commit':guard.PRODUCER_COMMIT,
                      'input_reference':self.input_ref.to_record(),'bound_at':stamp(self.actual)}
        return deepcopy(self.binding)

    def generate(self,pack,player_id,*,input_record_id,model_commit):
        self.assertEqual(input_record_id,self.input_ref.record_id)
        self.assertEqual(model_commit,guard.PRODUCER_COMMIT)
        self.events.append('GENERATE:'+player_id)
        bundle={'player_id':player_id,'forecast_id':digest({'synthetic_player':player_id}),
                'issued_at':stamp(self.actual)}
        return bundle,object()

    def issue(self,input_record_id,model_commit,*args,**kwargs):
        self.assertEqual(input_record_id,self.input_ref.record_id)
        self.assertEqual(model_commit,guard.PRODUCER_COMMIT)
        self.assertTrue(utc(self.plan['issuance_opens_at'])<=self.actual<=utc(self.plan['issuance_closes_at']))
        self.events.append('GUARDED_ISSUE')
        store=guard.Ledger(self.root)
        for player in guard.PLAYERS:
            if player in self.saved:continue
            bundle,reference=guard.producer.generate({},player,input_record_id=input_record_id,model_commit=model_commit)
            store.issue_prospective(bundle,reference=reference,input_ref=self.input_ref)
        return self.recover()

    def checkpoint(self,info):
        self.assertEqual(info['producer_commit'],guard.PRODUCER_COMMIT)
        phase=info['phase'];self.events.append(phase+(':'+info['player_id'] if 'player_id' in info else ''))
        if phase=='CAPTURE_STARTED':
            self.assertIsNone(info['input_reference'])
            self.assertEqual(info['history_input_record_id'],guard.HISTORY_RECORD_ID)
            if self.capture_intent:raise RuntimeError('ambiguous prior durable capture intent')
            self.capture_intent=True
        else:self.assertEqual(info['input_reference'],self.input_ref.to_record())
        if phase=='GENERATION_STARTED':
            player=info['player_id']
            if player in self.intents and player not in self.saved:raise RuntimeError('ambiguous prior durable intent')
            self.intents[player]=deepcopy(info)

    def test_early_invocation_refuses_without_wait_source_or_generation(self):
        self.actual-=timedelta(hours=1)
        report=runner.run_cycle(root=self.root,checkpoint=self.checkpoint)
        self.assertEqual(report['status'],'EARLY_NO_ACTION');self.assertNotEqual(report['exit_code'],0)
        self.assertFalse(self.sleeps);self.capture.assert_not_called();self.generation.assert_not_called()
        self.assertEqual(list(self.root.rglob('*')),[])

    def test_ordered_input_remote_checkpoint_then_per_subject_intent_and_original(self):
        report=runner.run_cycle(root=self.root,checkpoint=self.checkpoint)
        self.assertEqual(report['status'],'COMPLETE');self.assertEqual(report['exit_code'],0)
        self.history.assert_called_once_with(guard.HISTORY_RECORD_ID,repository_root=self.root)
        self.capture.assert_called_once();self.assertTrue(all(s<=30 for s in self.sleeps))
        self.assertLess(self.events.index('INPUT_BOUND'),self.events.index('GUARDED_ISSUE'))
        for index,player in enumerate(guard.PLAYERS):
            self.assertLess(self.events.index('GENERATION_STARTED:'+player),self.events.index('GENERATE:'+player))
            self.assertLess(self.events.index('LOCAL_ORIGINAL:'+player),self.events.index('FORECAST_RETAINED:'+player))
            if index<3:self.assertLess(self.events.index('FORECAST_RETAINED:'+player),self.events.index('GENERATION_STARTED:'+guard.PLAYERS[index+1]))

    def test_source_failure_preserves_failure_without_input_or_math(self):
        self.capture.side_effect=OSError('synthetic upstream unavailable')
        report=runner.run_cycle(root=self.root,checkpoint=self.checkpoint)
        self.assertEqual(report['exit_code'],1);self.assertTrue(report['source_capture_attempted'])
        self.assertIn('upstream unavailable',report['errors'][0]);self.assertIsNone(self.binding)
        self.assertFalse(self.saved);self.generation.assert_not_called()

    def test_late_valid_input_is_retained_diagnostically_never_bound_or_issued(self):
        def late(*args,**kwargs):self.actual=utc(self.plan['capture_closes_at'])+timedelta(seconds=1);return {},{},[]
        self.capture.side_effect=late
        report=runner.run_cycle(root=self.root,checkpoint=self.checkpoint)
        self.assertEqual(report['status'],'REJECTED_LATE_INPUT');self.assertEqual(report['exit_code'],1)
        self.assertIsNone(self.binding);self.generation.assert_not_called()
        self.assertEqual(report['retained_input_reference'],self.input_ref.to_record())
        self.assertEqual(len(self.retained_inputs),1)
        retained=next(iter(self.retained_inputs.values()))
        self.assertGreater(utc(retained['received_at']),utc(self.plan['capture_closes_at']))
        self.assertEqual(retained['source_pack'],{'synthetic_source_pack':True})
        self.assertTrue((self.root/'.local-data/pregame-cycle'/guard.CYCLE_ID/'sourcepack.json').is_file())
        before=deepcopy(self.retained_inputs)
        # An identical persistence retry retains the first actual receipt clock.
        self.actual+=timedelta(seconds=5)
        runner.Ledger(self.root).record_research_inputs({'synthetic_source_pack':True})
        self.assertEqual(self.retained_inputs,before)

    def test_bound_retry_recovers_original_and_never_recaptures(self):
        self.actual=utc(self.plan['capture_opens_at'])+timedelta(seconds=1);self.bind(self.input_ref.record_id)
        self.actual=utc(self.plan['issuance_opens_at'])+timedelta(seconds=1)
        bundle,reference=self.generate({},guard.PLAYERS[0],input_record_id=self.input_ref.record_id,model_commit=guard.PRODUCER_COMMIT)
        guard.Ledger(self.root).issue_prospective(bundle,reference=reference,input_ref=self.input_ref)
        original=deepcopy(self.saved[guard.PLAYERS[0]])
        self.generation.reset_mock()
        report=runner.run_cycle(root=self.root,checkpoint=self.checkpoint)
        self.assertEqual(report['exit_code'],0);self.assertEqual(self.saved[guard.PLAYERS[0]],original)
        self.assertEqual(self.generation.call_count,3);self.capture.assert_not_called();self.history.assert_not_called()

    def test_late_partial_is_read_only_and_complete_late_can_recover(self):
        self.actual=utc(self.plan['capture_opens_at']);self.bind(self.input_ref.record_id)
        self.actual=utc(self.plan['issuance_opens_at'])
        for player in guard.PLAYERS:
            bundle,reference=self.generate({},player,input_record_id=self.input_ref.record_id,model_commit=guard.PRODUCER_COMMIT)
            guard.Ledger(self.root).issue_prospective(bundle,reference=reference,input_ref=self.input_ref)
        all_saved=deepcopy(self.saved);self.saved.pop(guard.PLAYERS[-1]);partial=deepcopy(self.saved)
        self.actual=utc(self.plan['issuance_closes_at'])+timedelta(seconds=1);self.generation.reset_mock()
        report=runner.run_cycle(root=self.root,checkpoint=self.checkpoint)
        self.assertEqual(report['status'],'EXPIRED_INCOMPLETE');self.assertEqual(report['exit_code'],1)
        self.assertEqual(self.saved,partial);self.capture.assert_not_called();self.generation.assert_not_called()
        self.saved=all_saved
        report=runner.run_cycle(root=self.root,checkpoint=self.checkpoint)
        self.assertEqual(report['status'],'COMPLETE_RECOVERED');self.assertEqual(report['exit_code'],0)
        self.generation.assert_not_called()

    def test_input_checkpoint_failure_prevents_any_generation(self):
        def failed(info):
            self.checkpoint(info)
            if info['phase']=='INPUT_BOUND':raise RuntimeError('input remote push failed')
        report=runner.run_cycle(root=self.root,checkpoint=failed)
        self.assertEqual(report['exit_code'],1);self.assertEqual(report['checkpoints'][-1]['status'],'FAILED')
        self.assertIsNotNone(self.binding);self.generation.assert_not_called();self.assertFalse(self.saved)

    def test_capture_intent_failure_prevents_http_and_ambiguous_retry(self):
        def lost_ack(info):
            self.checkpoint(info)
            if info['phase']=='CAPTURE_STARTED':raise RuntimeError('capture intent durable but acknowledgement lost')
        report=runner.run_cycle(root=self.root,checkpoint=lost_ack)
        self.assertEqual(report['exit_code'],1);self.assertFalse(report['source_capture_attempted'])
        self.capture.assert_not_called();self.generation.assert_not_called();self.assertTrue(self.capture_intent)
        report=runner.run_cycle(root=self.root,checkpoint=self.checkpoint)
        self.assertEqual(report['exit_code'],1);self.capture.assert_not_called()
        self.assertIn('ambiguous prior durable capture intent',report['errors'][0])

    def test_slow_capture_intent_checkpoint_cannot_start_late_http(self):
        def slow(info):
            self.checkpoint(info)
            if info['phase']=='CAPTURE_STARTED':self.actual=utc(self.plan['capture_closes_at'])+timedelta(seconds=1)
        report=runner.run_cycle(root=self.root,checkpoint=slow)
        self.assertEqual(report['status'],'MISSED_CAPTURE_WINDOW');self.assertEqual(report['exit_code'],1)
        self.capture.assert_not_called();self.generation.assert_not_called()

    def test_existing_complete_sourcepack_recovers_without_fresh_capture_or_clocks(self):
        path=self.root/'.local-data/pregame-cycle'/guard.CYCLE_ID/'sourcepack.json'
        original={'synthetic_source_pack':True,'original_observation_clock':'retained'}
        write_receipt(path,original);before=path.read_bytes();self.capture_intent=True
        report=runner.run_cycle(root=self.root,checkpoint=self.checkpoint)
        self.assertEqual(report['exit_code'],0);self.assertEqual(report['status'],'COMPLETE')
        self.assertEqual(path.read_bytes(),before);self.capture.assert_not_called();self.history.assert_not_called()
        self.assertFalse(any(c['phase']=='CAPTURE_STARTED' for c in report['checkpoints']))

    def test_per_original_checkpoint_failure_stops_before_second_generation(self):
        def failed(info):
            self.checkpoint(info)
            if info['phase']=='FORECAST_RETAINED':raise RuntimeError('first original remote push failed')
        report=runner.run_cycle(root=self.root,checkpoint=failed)
        self.assertEqual(report['exit_code'],1);self.assertEqual(len(self.saved),1)
        self.assertEqual(self.generation.call_count,1);self.assertEqual(report['recovery']['status'],'PARTIAL')
        self.assertEqual(guard.Ledger.__name__,'MemoryLedger')

    def test_intent_checkpoint_failure_and_lost_original_never_regenerate(self):
        def lost_ack(info):
            self.checkpoint(info)
            if info['phase']=='GENERATION_STARTED':raise RuntimeError('intent durable but acknowledgement lost')
        first=runner.run_cycle(root=self.root,checkpoint=lost_ack)
        self.assertEqual(first['exit_code'],1);self.generation.assert_not_called()
        self.assertEqual(len(self.intents),1);self.assertFalse(self.saved)
        retry=runner.run_cycle(root=self.root,checkpoint=self.checkpoint)
        self.assertEqual(retry['exit_code'],1);self.generation.assert_not_called();self.assertFalse(self.saved)
        self.assertIn('ambiguous prior durable intent',retry['errors'][0])


class ReviewedProducerReadOnlyTests(unittest.TestCase):
    def test_all_nine_reviewed_producer_files_remain_exact(self):
        guard.producer.require_committed_model(guard.ROOT,guard.PRODUCER_COMMIT)


if __name__=='__main__':unittest.main()

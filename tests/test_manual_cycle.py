"""Synthetic operating guard tests; no provider HTTP or actual cycle issuance."""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import manual_cycle as guard
from multisport_lab import prospective as producer
from multisport_lab.integrity import IntegrityError,canonical,digest,read_receipt,stamp,write_receipt
from multisport_lab.ledger import Ledger,LedgerRef
from multisport_lab.pregame_sources import sourcepack_digest
from prospective_fixtures import synthetic_pack,CAPTURE,CUTOFF,ISSUE


class ManualCycleTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.temp=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.pack=synthetic_pack()
        event=self.pack['event'];event.update(event_id='401909088',home_team_id='8')
        event['event_version']=digest({k:v for k,v in event.items() if k!='event_version'})
        self.pack['selection']['event_id']='401909088'
        self.pack['selection']['declared_at']='2026-10-20T01:00:00.000000Z'
        player_map={'10':'2596112','11':'2990962','20':'3195','21':'4251'}
        for collection in [self.pack['selection']['players'],self.pack['candidates']]:
            for player in collection:
                player['player_id']=player_map[player['player_id']]
                if player['team_id']=='1':player['team_id']='8'
                if player['opponent_id']=='1':player['opponent_id']='8'
        for source in self.pack['sources']:
            if source['source_id']=='summary':source['source_url']=source['source_url'].replace('999999999','401909088')
            if source['source_id']=='roster-1':
                source['source_id']='roster-8';source['source_url']=source['source_url'].replace('teams/1/','teams/8/')
        self.pack['sourcepack_id']=sourcepack_digest(self.pack)
        for target,value in [('multisport_lab.pregame_sources.PANEL_SHA',self.pack['history_provenance']['normalized_panel_sha256']),
                             ('multisport_lab.prospective.PILOT_PANEL_SHA256',self.pack['history_provenance']['normalized_panel_sha256']),
                             ('multisport_lab.prospective.PILOT_HISTORY_ROWS',2),
                             ('multisport_lab.prospective.PILOT_EVENT_VERSION',event['event_version']),
                             ('multisport_lab.prospective.PILOT_SELECTION_SHA256',digest(self.pack['selection']))]:
            self.stack.enter_context(patch(target,value))
        self.stack.enter_context(patch('urllib.request.urlopen',side_effect=AssertionError('provider HTTP forbidden')))
        self.stack.enter_context(patch('multisport_lab.pregame_sources._now',return_value=ISSUE))
        self.stack.enter_context(patch('multisport_lab.baseline._now',return_value=ISSUE))
        self.producer_clock=self.stack.enter_context(patch.object(producer,'_now',return_value=ISSUE))
        self.ledger_clock=self.stack.enter_context(patch('multisport_lab.ledger._now',return_value=CAPTURE+timedelta(seconds=3)))
        self.guard_clock=self.stack.enter_context(patch.object(guard,'_now',return_value=CAPTURE+timedelta(seconds=4)))
        future=self.stack.enter_context(patch('multisport_lab.forecast_contract.datetime'))
        future.now.return_value=ISSUE+timedelta(days=2)
        # Synthetic temp stores do not contain Git/source history. Separate tests
        # exercise the actual pinned source check against the real read-only repo.
        self.check=self.stack.enter_context(patch.object(guard,'_check_reviewed_files'))
        self.plan=read_receipt(guard.DEFAULT_PLAN)
        self.plan['event_version']=event['event_version']
        self.plan['selection_sha256']=digest(self.pack['selection'])
        self.plan_path=self.temp/'plan.json';write_receipt(self.plan_path,self.plan)
        self.store=Ledger(self.temp);self.input_ref=self.store.record_research_inputs(self.pack)

    def bind(self):
        return guard.bind(self.input_ref.record_id,self.plan_path,repository_root=self.temp)

    def issue(self,**kwargs):
        self.guard_clock.return_value=ISSUE;self.ledger_clock.return_value=ISSUE
        return guard.issue(self.input_ref.record_id,kwargs.get('model_commit',guard.PRODUCER_COMMIT),self.plan_path,repository_root=self.temp)

    def files(self):
        return {str(p.relative_to(self.temp)):p.read_bytes() for p in self.temp.rglob('*') if p.is_file()}

    def test_preflight_and_recover_pending_read_only_and_capture_window_gate(self):
        before=self.files()
        with patch.object(producer,'generate',side_effect=AssertionError('preparation cannot generate')):
            result=guard.preflight(self.plan_path,repository_root=self.temp)
            self.assertEqual(result['status'],'NOT_READY')
            self.assertEqual(result['selected_forecasts_retained'],0)
            self.assertEqual(result['provider_requests'],0)
            self.assertEqual(guard.recover(self.plan_path,repository_root=self.temp)['missing_player_ids'],guard.PLAYERS)
            self.guard_clock.return_value=CUTOFF-timedelta(minutes=11)
            with self.assertRaisesRegex(IntegrityError,'window is not open'):
                guard.preflight(self.plan_path,repository_root=self.temp,require_capture_window=True)
        self.assertEqual(before,self.files())

    def test_binding_is_create_only_and_same_id_retry_preserves_original_clock(self):
        binding=self.bind();path=guard._binding_path(self.temp,self.plan);before=path.read_bytes()
        self.assertEqual(binding['producer_commit'],guard.PRODUCER_COMMIT)
        self.assertEqual(binding['input_reference'],self.input_ref.to_record())
        self.guard_clock.return_value=ISSUE+timedelta(days=1)
        self.assertEqual(self.bind(),binding)
        self.assertEqual(path.read_bytes(),before)
        with self.assertRaisesRegex(IntegrityError,'already has an immutable'):
            self.guard_clock.return_value=CAPTURE+timedelta(seconds=5)
            guard.preflight(self.plan_path,repository_root=self.temp,require_capture_window=True)

    def test_preparation_id_and_early_capture_cannot_bind(self):
        with self.assertRaisesRegex(IntegrityError,'early preparation'):
            guard._validate_input(self.plan,self.store,LedgerRef('research_inputs',guard.HISTORY_RECORD_ID,'a'*64),{})
        early=deepcopy(self.pack)
        for source in early['sources']:
            source['request_started_at']='2026-10-20T01:51:00.000000Z'
            source['observed_at']=source['response_completed_at']='2026-10-20T01:51:01.000000Z'
        early['imported_at']='2026-10-20T02:10:00.000000Z';early['sourcepack_id']=sourcepack_digest(early)
        early_ref=self.store.record_research_inputs(early)
        with self.assertRaisesRegex(IntegrityError,'ten minutes'):
            guard.bind(early_ref.record_id,self.plan_path,repository_root=self.temp)
        self.assertFalse(guard._binding_path(self.temp,self.plan).exists())

    def test_changed_model_revision_including_docs_head_fails_before_generation(self):
        self.bind();before=self.files()
        for revision in [guard.PREPARATION_COMMIT,'a'*40]:
            with self.subTest(revision=revision),patch.object(producer,'generate',side_effect=AssertionError('must reject before generation')):
                with self.assertRaisesRegex(IntegrityError,'exact pinned producer'):
                    self.issue(model_commit=revision)
        self.assertEqual(before,self.files())

    def test_changed_input_retry_and_binding_cannot_create_another_cohort(self):
        self.bind();other=deepcopy(self.pack)
        other['imported_at']=stamp(CAPTURE+timedelta(seconds=2,microseconds=1));other['sourcepack_id']=sourcepack_digest(other)
        other_ref=self.store.record_research_inputs(other);before=self.files()
        with self.assertRaisesRegex(IntegrityError,'never rebind'):
            guard.bind(other_ref.record_id,self.plan_path,repository_root=self.temp)
        with patch.object(producer,'generate',side_effect=AssertionError('must reject before generation')):
            with self.assertRaisesRegex(IntegrityError,'input differs'):
                guard.issue(other_ref.record_id,guard.PRODUCER_COMMIT,self.plan_path,repository_root=self.temp)
        self.assertEqual(before,self.files())

    def test_partial_original_changed_model_or_input_is_seen_across_all_originals(self):
        self.bind();self.ledger_clock.return_value=ISSUE;self.guard_clock.return_value=ISSUE
        bundle,reference=producer.generate(self.pack,guard.PLAYERS[0],input_record_id=self.input_ref.record_id,model_commit=guard.PRODUCER_COMMIT)
        original=self.store.issue_prospective(bundle,reference=reference,input_ref=self.input_ref)
        original_bytes=self.store._path('forecasts',original.record_id).read_bytes()
        # Reproduce the reviewed helper's permissive different-revision path in a
        # synthetic temp ledger, then prove the new wrapper refuses to extend it.
        changed,changed_reference=producer.generate(self.pack,guard.PLAYERS[0],input_record_id=self.input_ref.record_id,model_commit=guard.PREPARATION_COMMIT)
        self.store.issue_prospective(changed,reference=changed_reference,input_ref=self.input_ref)
        before=self.files()
        with patch.object(producer,'generate',side_effect=AssertionError('drift must fail before generation')):
            with self.assertRaisesRegex(IntegrityError,'different model or producer'):
                self.issue()
        self.assertEqual(before,self.files())
        self.assertEqual(self.store._path('forecasts',original.record_id).read_bytes(),original_bytes)

    def test_duplicate_original_same_revision_is_rejected(self):
        self.bind();self.ledger_clock.return_value=ISSUE;self.guard_clock.return_value=ISSUE
        for clock in [ISSUE,ISSUE+timedelta(microseconds=1)]:
            self.producer_clock.return_value=clock
            self.ledger_clock.return_value=clock
            bundle,reference=producer.generate(self.pack,guard.PLAYERS[0],input_record_id=self.input_ref.record_id,model_commit=guard.PRODUCER_COMMIT)
            self.store.issue_prospective(bundle,reference=reference,input_ref=self.input_ref)
        with patch.object(producer,'generate',side_effect=AssertionError('duplicate must fail before generation')):
            with self.assertRaisesRegex(IntegrityError,'duplicate original'):
                self.ledger_clock.return_value=ISSUE+timedelta(seconds=1)
                self.guard_clock.return_value=ISSUE+timedelta(seconds=1)
                guard.issue(self.input_ref.record_id,guard.PRODUCER_COMMIT,self.plan_path,repository_root=self.temp)

    def test_original_under_another_input_is_rejected_before_missing_subject_generation(self):
        self.bind();other=deepcopy(self.pack)
        other['imported_at']=stamp(CAPTURE+timedelta(seconds=2,microseconds=1));other['sourcepack_id']=sourcepack_digest(other)
        other_ref=self.store.record_research_inputs(other)
        self.ledger_clock.return_value=ISSUE;self.guard_clock.return_value=ISSUE
        bundle,reference=producer.generate(other,guard.PLAYERS[0],input_record_id=other_ref.record_id,model_commit=guard.PRODUCER_COMMIT)
        original=self.store.issue_prospective(bundle,reference=reference,input_ref=other_ref)
        before=self.files()
        with patch.object(producer,'generate',side_effect=AssertionError('other-input drift must fail before generation')):
            with self.assertRaisesRegex(IntegrityError,'different input binding'):
                self.issue()
        self.assertEqual(before,self.files())
        self.assertIn(str(self.store._path('forecasts',original.record_id).relative_to(self.temp)),before)

    def test_partial_late_recovery_never_generates_or_writes(self):
        self.bind();self.ledger_clock.return_value=ISSUE;self.guard_clock.return_value=ISSUE
        bundle,reference=producer.generate(self.pack,guard.PLAYERS[0],input_record_id=self.input_ref.record_id,model_commit=guard.PRODUCER_COMMIT)
        self.store.issue_prospective(bundle,reference=reference,input_ref=self.input_ref)
        before=self.files();late=ISSUE+timedelta(days=1)
        self.guard_clock.return_value=late;self.ledger_clock.return_value=late
        with patch.object(producer,'generate',side_effect=AssertionError('late partial cannot generate')):
            report=guard.recover(self.plan_path,repository_root=self.temp)
            self.assertEqual(report['status'],'PARTIAL')
            self.assertEqual(report['selected_forecasts_retained'],1)
            self.assertEqual(report['pending_statistical_grades'],1)
            with self.assertRaisesRegex(IntegrityError,'outside the window'):
                guard.issue(self.input_ref.record_id,guard.PRODUCER_COMMIT,self.plan_path,repository_root=self.temp)
        self.assertEqual(before,self.files())

    def test_partial_retry_completes_only_missing_and_complete_late_recovers(self):
        self.bind();self.ledger_clock.return_value=ISSUE;self.guard_clock.return_value=ISSUE
        bundle,reference=producer.generate(self.pack,guard.PLAYERS[0],input_record_id=self.input_ref.record_id,model_commit=guard.PRODUCER_COMMIT)
        original=self.store.issue_prospective(bundle,reference=reference,input_ref=self.input_ref)
        path=self.store._path('forecasts',original.record_id);before=path.read_bytes()
        original_generate=producer.generate;calls=[]
        def tracked(*args,**kwargs):calls.append(args[1]);return original_generate(*args,**kwargs)
        with patch.object(producer,'generate',side_effect=tracked):result=self.issue()
        self.assertEqual(result['status'],'COMPLETE');self.assertEqual(result['forecasts_generated'],3)
        self.assertEqual(calls,guard.PLAYERS[1:]);self.assertEqual(path.read_bytes(),before)
        records=self.files();late=ISSUE+timedelta(days=1)
        self.guard_clock.return_value=late;self.ledger_clock.return_value=late
        with patch.object(producer,'generate',side_effect=AssertionError('complete late retry cannot generate')):
            late_report=guard.issue(self.input_ref.record_id,guard.PRODUCER_COMMIT,self.plan_path,repository_root=self.temp)
        self.assertEqual(late_report['status'],'COMPLETE');self.assertEqual(late_report['forecasts_generated'],0)
        self.assertEqual(records,self.files())

    def test_missing_bound_input_reference_fails_closed(self):
        self.bind();self.store._path('research_inputs',self.input_ref.record_id).unlink()
        with self.assertRaises(FileNotFoundError):guard.recover(self.plan_path,repository_root=self.temp)

    def test_unresolved_or_superseded_outcome_grades_remain_pending(self):
        from multisport_lab.pregame_sources import unpack_history
        self.bind();self.ledger_clock.return_value=ISSUE;self.guard_clock.return_value=ISSUE
        bundle,reference=producer.generate(self.pack,guard.PLAYERS[0],input_record_id=self.input_ref.record_id,model_commit=guard.PRODUCER_COMMIT)
        forecast=self.store.issue_prospective(bundle,reference=reference,input_ref=self.input_ref)
        final_at=CUTOFF+timedelta(hours=5)
        self.ledger_clock.return_value=final_at;self.guard_clock.return_value=final_at
        row=replace(unpack_history(self.pack)[0],event_id='401909088',player_id=guard.PLAYERS[0],
                    team_id='8',opponent_id='2',season_ending_year=2027,event_start=CUTOFF+timedelta(minutes=90))
        unresolved=replace(row,final_status='NOT_FINAL')
        unresolved_ref=self.store.record_outcome(unresolved,source_evidence_sha256='c'*64,source_observed_at=final_at)
        self.store.grade_forecast(forecast,unresolved_ref)
        self.assertEqual(guard.recover(self.plan_path,repository_root=self.temp)['pending_statistical_grades'],1)
        original=self.store.record_outcome(row,source_evidence_sha256='d'*64,source_observed_at=final_at)
        self.store.grade_forecast(forecast,original)
        self.assertEqual(guard.recover(self.plan_path,repository_root=self.temp)['pending_statistical_grades'],0)
        corrected=replace(row,dreb=row.dreb+1,rebounds=row.rebounds+1)
        replacement=self.store.record_outcome(corrected,source_evidence_sha256='e'*64,source_observed_at=final_at)
        self.store.correct(original,replacement,reason='Synthetic corrected rebound; replacement not graded yet')
        with patch.object(producer,'generate',side_effect=AssertionError('grading recovery cannot generate')):
            self.assertEqual(guard.recover(self.plan_path,repository_root=self.temp)['pending_statistical_grades'],1)


class ActualReadOnlyPinTests(unittest.TestCase):
    def test_pinned_sources_still_match_despite_documentation_head(self):
        plan=guard.load_plan()
        self.assertTrue((guard.ROOT/'records/README.md').is_file())
        self.assertNotIn('records/README.md',plan['original_records_sha256'])
        with patch('urllib.request.urlopen',side_effect=AssertionError('HTTP forbidden')),patch.object(producer,'generate',side_effect=AssertionError('generation forbidden')):
            guard._check_reviewed_files(plan,guard.ROOT)


if __name__=='__main__':unittest.main()

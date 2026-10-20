"""Synthetic paired-record integrity/recovery only; no reserved-study scores."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import pros004_records as rec
from multisport_lab import pros004_producer as prod
from multisport_lab.integrity import IntegrityError, canonical, digest, stamp
from multisport_lab.ledger import LedgerRef
from test_pregame_sources import tiny_history
from test_pros004_producer import ProducerFixture, CUTOFF, ISSUE, START

OBSERVED=START+timedelta(hours=4)
GRADED=OBSERVED+timedelta(seconds=10)


def at_outcomes(f):
    for clock in (f.record_clock,f.ledger_clock,f.input_clock):
        clock.return_value=GRADED


def synthetic_outcome(f,*,extra_points=0,dnp=False):
    row=replace(tiny_history()[0],event_id=f.event['event']['event_id'],event_start=START,
        season_ending_year=2027,player_id='10',team_id='8',opponent_id='2')
    if extra_points:
        row=replace(row,points=row.points+2*extra_points,fgm=row.fgm+extra_points,
            fg2m=row.fg2m+extra_points,fga=row.fga+extra_points)
    if dnp:
        row=replace(row,participation='DNP',minutes=None,minutes_precision='unknown',
            **{name:None for name in ('points','fgm','fga','fg2m','fg3m','fg3a','ftm','fta',
                'oreb','dreb','rebounds','assists','turnovers','blocks','steals')})
    return rec.outcome_from_normalized(row,event_version=f.event['event']['event_version'],
        mode='SYNTHETIC_DIAGNOSTIC',source_raw_sha256=digest({'invented_source':extra_points,'dnp':dnp}),
        source_observed_at=OBSERVED,normalized_at=GRADED)


def issue_both(f):
    prod.issue_pair(f.store,f.event_ref,f.binding,player_id='10')
    return [f.store.lookup_forecast(f.event_ref,'10',key) for key in ('R0','K0')]


def outcome_bytes(f,*,final=True,postponed=False):
    status={'name':'STATUS_FINAL','state':'post','completed':True}
    if not final:
        status={'name':'STATUS_POSTPONED' if postponed else 'STATUS_IN_PROGRESS',
                'state':'pre' if postponed else 'in','completed':False}
    competitors=[{'id':team,'homeAway':side,'team':{'id':team},'score':'100',
        'linescores':[{'displayValue':'25'} for _ in range(4)]}
        for team,side in [('8','home'),('2','away')]]
    competition={'id':f.event['event']['event_id'],'date':stamp(START),
        'status':{'type':status,'period':4},'competitors':competitors}
    labels=['MIN','FG','3PT','FT','OREB','DREB','REB','AST','STL','BLK','TO','PTS']
    group={'team':{'id':'8'},'statistics':[{'labels':labels,'athletes':[
        {'athlete':{'id':'10'},'didNotPlay':False,
         'stats':['20:00','2-4','1-2','0-0','1','2','3','0','0','0','0','5']},
        {'athlete':{'id':'20'},'didNotPlay':True,'stats':[]}]}]}
    return canonical({'header':{'id':f.event['event']['event_id'],'date':stamp(START),
        'season':{'year':2027,'type':2},'competitions':[competition]},'boxscore':{'players':[group]}})


class Pros004RecordsTests(unittest.TestCase):
    def test_full_comparison_and_metadata_are_reserved_before_first_write(self):
        plan=rec.full_study_capacity()
        self.assertEqual(plan['comparison_records'],442)
        self.assertEqual(plan['full_study_records_before_reserve'],499)
        self.assertEqual(plan['maximum_records_including_reserve'],512)
        self.assertEqual(plan['counts']['correction_or_failure_reserve'],13)
        self.assertEqual(plan['maximum_planned_bytes'],22487040)
        self.assertEqual(plan['remaining_bytes_after_reserve'],11067392)
        self.assertEqual(plan['global_byte_limit'],32*1024*1024)

    def test_typed_input_extension_restart_and_independent_copy_preserve_originals(self):
        f=ProducerFixture(self)
        original=f.store.ledger._path(f.history_ref.kind,f.history_ref.record_id).read_bytes()
        self.assertEqual(f.store.store_history(f.history),f.history_ref)
        restart=rec.Pros004Store(f.tmp,diagnostic=True)
        self.assertEqual(restart.body(f.event_ref),f.event)
        self.assertNotIn('history',f.event)
        self.assertEqual(restart.body(f.history_ref),f.history)
        with tempfile.TemporaryDirectory() as independent:
            shutil.copytree(Path(f.tmp)/'records',Path(independent)/'records')
            recovered=rec.Pros004Store(independent,diagnostic=True)
            self.assertEqual(recovered.body(f.event_ref),f.event)
            self.assertEqual(recovered.capacity_report()['actual_records'],2)
            self.assertEqual(original,recovered.ledger._path(f.history_ref.kind,f.history_ref.record_id).read_bytes())
        payload=restart.read(f.event_ref)
        measured=rec.encoded_envelope_size(payload['kind'],payload['logical_id'],payload['data'],
            references=(f.history_ref,),received_at=payload['received_at'])
        self.assertEqual(measured,restart.ledger._path(f.event_ref.kind,f.event_ref.record_id).stat().st_size)

    def test_diagnostics_reject_any_real_git_worktree_and_live_writes_are_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            result=subprocess.run(['git','init','--quiet',directory],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            with self.assertRaisesRegex(IntegrityError,'outside every Git worktree'):
                rec.Pros004Store(Path(directory)/'nested',diagnostic=True)
            self.assertFalse((Path(directory)/'records').exists())
        f=ProducerFixture(self);live=deepcopy(f.history);live['mode']='REAL_TIME_CAPTURED'
        # A caller-provided activation object never opens genuine writes.
        other=rec.Pros004Store(f.tmp,activation={'status':'ACTIVE','remote_readback':True})
        with self.assertRaisesRegex(IntegrityError,'readiness-only'):
            other.store_history(live)
        with self.assertRaisesRegex(IntegrityError,'readiness-only'):
            other.store_manifest()
        self.assertEqual(f.store.capacity_report()['actual_records'],2)

    def test_event_cannot_bind_history_from_another_evidence_lane(self):
        f=ProducerFixture(self)
        changed=deepcopy(f.event);changed['mode']='READINESS_DIAGNOSTIC'
        changed['sourcepack_id']=digest({k:v for k,v in changed.items() if k!='sourcepack_id'})
        with self.assertRaisesRegex(IntegrityError,'evidence lanes differ'):
            f.store.store_event(changed,f.history_ref)
        self.assertEqual(f.store.capacity_report()['actual_records'],2)

    def test_complete_snapshot_and_single_writer_are_required_for_recovery(self):
        f=ProducerFixture(self)
        second=rec.Pros004Store(f.tmp,diagnostic=True)
        with f.store.writer_lock():
            with self.assertRaisesRegex(IntegrityError,'another PROS004 writer'):
                with second.writer_lock():
                    self.fail('concurrent writer entered')
        location=Path(f.tmp)/'records'/'forecasts';location.mkdir(parents=True,exist_ok=True)
        (location/'.receipt-ambiguous').write_bytes(b'incomplete unpublished bytes')
        with self.assertRaisesRegex(IntegrityError,'ambiguous'):
            second.recover_event(f.event_ref,f.binding)

    def test_stable_admission_rejects_well_formed_model_revision_and_input_retry(self):
        f=ProducerFixture(self)
        original,created=f.store.claim_event(f.event_ref,f.binding)
        self.assertTrue(created)
        f.record_clock.return_value=ISSUE+timedelta(seconds=1)
        f.ledger_clock.return_value=ISSUE+timedelta(seconds=1)
        self.assertEqual(f.store.claim_event(f.event_ref,f.binding),(original,False))
        changed=deepcopy(f.binding)
        changed['verification']='VERIFIED_COMMIT';changed['model_commit']='f'*40
        prod.validate_source_binding(changed)
        with self.assertRaisesRegex(IntegrityError,'different input/cohort/producer'):
            f.store.claim_event(f.event_ref,changed)
        with self.assertRaisesRegex(IntegrityError,'cannot change producer revision'):
            f.store.recover_event(f.event_ref,changed)
        changed_event=deepcopy(f.event);changed_event['imported_at']=stamp(ISSUE)
        changed_event['sourcepack_id']=digest({k:v for k,v in changed_event.items() if k!='sourcepack_id'})
        with self.assertRaises(IntegrityError):
            f.store.store_event(changed_event,f.history_ref)
        self.assertEqual(f.store.capacity_report()['actual_records'],3)

    def test_one_missing_peer_is_preserved_on_restart_and_late_completion_rejected(self):
        f=ProducerFixture(self);claim,_=f.store.claim_event(f.event_ref,f.binding)
        first,_=f.generate('R0');ref=f.store.persist_forecast(first,f.event_ref,f.history_ref,claim)
        raw=f.store.ledger._path(ref.kind,ref.record_id).read_bytes()
        peer,_=f.generate('K0')
        f.record_clock.return_value=CUTOFF+timedelta(minutes=6)
        f.ledger_clock.return_value=CUTOFF+timedelta(minutes=6)
        recovered=rec.Pros004Store(f.tmp,diagnostic=True)
        report=recovered.recover_event(f.event_ref,f.binding)
        self.assertEqual(report['status'],'PARTIAL_MISSING_PEERS')
        self.assertEqual(report['issued_models'],1)
        subject=next(row for row in report['subjects'] if row['player_id']=='10')
        self.assertEqual(subject['missing_models'],['K0'])
        self.assertEqual(recovered.persist_forecast(first,f.event_ref,f.history_ref,claim),ref)
        with self.assertRaisesRegex(IntegrityError,'outside actual T90'):
            recovered.persist_forecast(peer,f.event_ref,f.history_ref,claim)
        self.assertEqual(raw,recovered.ledger._path(ref.kind,ref.record_id).read_bytes())

    def test_shared_outcome_links_both_actual_originals_and_two_separate_grades(self):
        f=ProducerFixture(self);forecasts=issue_both(f);at_outcomes(f)
        outcome=synthetic_outcome(f)
        with self.assertRaisesRegex(IntegrityError,'every actually issued peer'):
            f.store.append_outcome(outcome,forecasts[:1])
        ref=f.store.append_outcome(outcome,forecasts)
        self.assertEqual(f.store.append_outcome(outcome,list(reversed(forecasts))),ref)
        grades=[f.store.grade_forecast(forecast,ref) for forecast in forecasts]
        self.assertNotEqual(grades[0],grades[1])
        self.assertEqual({f.store.body(grade)['model_key'] for grade in grades},{'R0','K0'})
        for forecast,grade in zip(forecasts,grades):
            body=f.store.body(grade)
            self.assertEqual(body['status'],'SCORED')
            self.assertEqual(len(body['categories']),14)
            self.assertEqual(body['reported_minutes']['observed'],20)
            self.assertEqual(len(body['reported_minutes']['intervals']),3)
            self.assertEqual(body['financial_settlement'],'NOT_EVALUATED')
            self.assertEqual(body['qualification'],'UNAVAILABLE')
            self.assertEqual(f.store.grade_forecast(forecast,ref),grade)

    def test_repeat_evidence_reuses_original_outcome_source_and_import_clocks(self):
        f=ProducerFixture(self);forecasts=issue_both(f);at_outcomes(f)
        original=synthetic_outcome(f)
        ref=f.store.append_outcome(original,forecasts)
        raw=f.store.ledger._path(ref.kind,ref.record_id).read_bytes()
        later=deepcopy(original)
        later['source_observed_at']=stamp(OBSERVED+timedelta(seconds=1))
        later['normalized_at']=stamp(GRADED+timedelta(seconds=1))
        later['source_raw_sha256']='b'*64
        later['outcome_id']=digest({k:v for k,v in later.items() if k!='outcome_id'})
        f.record_clock.return_value=GRADED+timedelta(seconds=2)
        f.ledger_clock.return_value=GRADED+timedelta(seconds=2)
        restart=rec.Pros004Store(f.tmp,diagnostic=True)
        self.assertEqual(restart.append_outcome(later,forecasts),ref)
        self.assertEqual(restart.body(ref)['source_observed_at'],stamp(OBSERVED))
        self.assertEqual(restart.body(ref)['normalized_at'],stamp(GRADED))
        self.assertEqual(raw,restart.ledger._path(ref.kind,ref.record_id).read_bytes())

    def test_dnp_and_pending_states_never_become_zero_or_statistical_grades(self):
        for state in ('DNP','MISSING','POSTPONED','NONFINAL','UNRESOLVED'):
            with self.subTest(state=state):
                f=ProducerFixture(self);forecasts=issue_both(f);at_outcomes(f)
                outcome=synthetic_outcome(f,dnp=True) if state=='DNP' else rec.pending_outcome(
                    f.store.body(forecasts[0]),status=state,source_raw_sha256='a'*64,
                    source_observed_at=OBSERVED,normalized_at=GRADED)
                ref=f.store.append_outcome(outcome,forecasts)
                grade=f.store.body(f.store.grade_forecast(forecasts[0],ref))
                self.assertEqual(grade['status'],'DNP_NOT_SCORED' if state=='DNP' else state)
                self.assertEqual(grade['categories'],[])
                self.assertIsNone(grade['reported_minutes'])
                self.assertIsNone(f.store.body(ref)['primitives'])

    def test_correction_and_regrade_append_traceable_revisions_preserving_originals(self):
        f=ProducerFixture(self);forecasts=issue_both(f);at_outcomes(f)
        old=f.store.append_outcome(synthetic_outcome(f),forecasts)
        grades=[f.store.grade_forecast(ref,old) for ref in forecasts]
        originals={ref:f.store.ledger._path(ref.kind,ref.record_id).read_bytes() for ref in [*forecasts,old,*grades]}
        changed=synthetic_outcome(f,extra_points=1)
        with self.assertRaisesRegex(IntegrityError,'correction reason'):
            f.store.append_outcome(changed,forecasts)
        new=f.store.append_outcome(changed,forecasts,correction_reason='Synthetic official count correction')
        newgrades=[f.store.grade_forecast(ref,new) for ref in forecasts]
        self.assertEqual(f.store.ledger.latest(old),new)
        self.assertEqual([f.store.ledger.latest(ref) for ref in grades],newgrades)
        report=f.store.capacity_report()
        self.assertEqual(report['used_correction_failure_reserve'],6)
        self.assertEqual(report['existing_or_pilot_records'],0)
        self.assertEqual(report['pros004_schema_counts']['nba-pros004-outcome-v1'],2)
        for ref,raw in originals.items():
            self.assertEqual(raw,f.store.ledger._path(ref.kind,ref.record_id).read_bytes())
        with self.assertRaisesRegex(IntegrityError,'cannot be corrected'):
            f.store.correct(forecasts[0],forecasts[0],reason='Forbidden replacement')

    def test_interrupted_outcome_and_grade_correction_recover_without_new_clocks(self):
        f=ProducerFixture(self);forecasts=issue_both(f);at_outcomes(f)
        old=f.store.append_outcome(synthetic_outcome(f),forecasts)
        oldgrade=f.store.grade_forecast(forecasts[0],old)
        changed=synthetic_outcome(f,extra_points=1)
        with patch.object(f.store,'correct',side_effect=OSError('interrupted before correction link')):
            with self.assertRaisesRegex(OSError,'before correction'):
                f.store.append_outcome(changed,forecasts,correction_reason='Synthetic evidence correction')
        restart=rec.Pros004Store(f.tmp,diagnostic=True)
        new=restart.append_outcome(changed,forecasts,correction_reason='Synthetic evidence correction')
        self.assertEqual(restart.ledger.latest(old),new)
        with patch.object(restart,'correct',side_effect=OSError('interrupted regrade link')):
            with self.assertRaisesRegex(OSError,'regrade link'):
                restart.grade_forecast(forecasts[0],new)
        count_before=restart.capacity_report()['actual_records']
        f.record_clock.return_value=GRADED+timedelta(seconds=5)
        f.ledger_clock.return_value=GRADED+timedelta(seconds=5)
        again=rec.Pros004Store(f.tmp,diagnostic=True)
        recoveredgrade=again.grade_forecast(forecasts[0],new)
        self.assertEqual(again.ledger.latest(oldgrade),recoveredgrade)
        self.assertEqual(again.body(recoveredgrade)['graded_at'],stamp(GRADED))
        self.assertEqual(again.capacity_report()['actual_records'],count_before+1)

    def test_future_subject_reserve_and_individual_encoded_limits_fail_before_write(self):
        f=ProducerFixture(self);forecasts=issue_both(f);at_outcomes(f)
        f.store.append_outcome(synthetic_outcome(f),forecasts)
        report=f.store.capacity_report();before=report['actual_records']
        report['used_correction_failure_reserve']=13
        with patch.object(f.store,'capacity_report',return_value=report):
            with self.assertRaisesRegex(IntegrityError,'reserved capacity'):
                f.store.append_outcome(synthetic_outcome(f,extra_points=1),forecasts,correction_reason='Synthetic correction')
        self.assertEqual(f.store.capacity_report()['actual_records'],before)
        enormous=synthetic_outcome(f,extra_points=1);enormous['normalizer_version']='x'*9000
        enormous['outcome_id']=digest({k:v for k,v in enormous.items() if k!='outcome_id'})
        with self.assertRaisesRegex(IntegrityError,'individual encoded-envelope'):
            f.store.append_outcome(enormous,forecasts,correction_reason='Synthetic correction')
        self.assertEqual(f.store.capacity_report()['actual_records'],before)

    def test_paired_correction_preflights_all_six_revision_and_link_slots(self):
        f=ProducerFixture(self);forecasts=issue_both(f);at_outcomes(f)
        original=f.store.append_outcome(synthetic_outcome(f),forecasts)
        for forecast in forecasts:
            f.store.grade_forecast(forecast,original)
        report=f.store.capacity_report();before=report['actual_records']
        report['used_correction_failure_reserve']=8
        with patch.object(f.store,'capacity_report',return_value=report):
            with self.assertRaisesRegex(IntegrityError,'paired correction.*reserved capacity'):
                f.store.append_outcome(synthetic_outcome(f,extra_points=1),forecasts,
                    correction_reason='Synthetic paired correction requiring six slots')
        self.assertEqual(f.store.capacity_report()['actual_records'],before)
        self.assertEqual(f.store.ledger.latest(original),original)

    def test_partial_peer_outcome_links_only_the_genuinely_existing_model(self):
        f=ProducerFixture(self);claim,_=f.store.claim_event(f.event_ref,f.binding)
        body,_=f.generate('R0')
        forecast=f.store.persist_forecast(body,f.event_ref,f.history_ref,claim)
        at_outcomes(f)
        outcome=f.store.append_outcome(synthetic_outcome(f),[forecast])
        grade=f.store.grade_forecast(forecast,outcome)
        self.assertEqual(f.store.read(outcome)['references'],[forecast.to_record()])
        self.assertEqual(f.store.body(grade)['model_key'],'R0')
        self.assertIsNone(f.store.lookup_forecast(f.event_ref,'10','K0'))
        self.assertEqual(f.store.recover_event(f.event_ref,f.binding)['issued_models'],1)

    def test_event_actual_receipt_cannot_be_late_even_with_timely_import_metadata(self):
        f=ProducerFixture(self)
        with tempfile.TemporaryDirectory() as independent:
            # Retain the shared history, but attempt a new event receipt after
            # selection closed. Claimed import time alone does not admit it.
            target=rec.Pros004Store(independent,diagnostic=True)
            shutil.copytree(Path(f.tmp)/'records'/'research_inputs',
                Path(independent)/'records'/'research_inputs')
            target.ledger._path(f.event_ref.kind,f.event_ref.record_id).unlink()
            f.record_clock.return_value=CUTOFF-timedelta(minutes=9)
            f.ledger_clock.return_value=CUTOFF-timedelta(minutes=9)
            with self.assertRaisesRegex(IntegrityError,'before selection closed'):
                target.store_event(f.event,f.history_ref)
            self.assertIsNone(target.ledger._existing('research_inputs',rec._logical(f.event)))

    def test_new_outcome_bytes_path_binds_event_counts_clocks_and_pending_states(self):
        f=ProducerFixture(self);at_outcomes(f)
        with patch('multisport_lab.prospective_outcomes._now',return_value=GRADED):
            raw=outcome_bytes(f)
            report=rec.normalize_outcome_bytes(raw,f.event,observed_at=OBSERVED)
            self.assertEqual(report['source_raw_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(report['source_observed_at'],stamp(OBSERVED))
            self.assertEqual(report['normalized_at'],stamp(GRADED))
            self.assertEqual(report['outcomes']['10']['status'],'APPEARED')
            self.assertEqual(report['outcomes']['20']['status'],'DNP')
            self.assertEqual(report['outcomes']['30']['status'],'MISSING')
            self.assertEqual(report['outcomes']['50']['status'],'MISSING')
            self.assertEqual(report['raw_retention_status'],'EXTERNAL_RAW_ARTIFACT_REQUIRED')
            for postponed,expected in ((False,'NONFINAL'),(True,'POSTPONED')):
                pending=rec.normalize_outcome_bytes(outcome_bytes(f,final=False,postponed=postponed),f.event,observed_at=OBSERVED)
                self.assertEqual({row['status'] for row in pending['outcomes'].values()},{expected})
            bad=json.loads(raw);bad['header']['competitions'][0]['competitors'][0]['team']['id']='999'
            with self.assertRaisesRegex(IntegrityError,'identity conflict|teams differ'):
                rec.normalize_outcome_bytes(canonical(bad),f.event,observed_at=OBSERVED)
            bad=json.loads(raw);bad['boxscore']['players'][0]['statistics'][0]['athletes'][0]['stats'][-1]='99'
            with self.assertRaisesRegex(IntegrityError,'contradicts scoring'):
                rec.normalize_outcome_bytes(canonical(bad),f.event,observed_at=OBSERVED)

    def test_reserved_aggregate_time_gate_is_explicit_under_optimized_python(self):
        f=ProducerFixture(self)
        with self.assertRaisesRegex(IntegrityError,'unavailable before'):
            f.store.require_evaluation_window()
        source=("from multisport_lab import pros004_records as r; import tempfile; from datetime import datetime, timezone; "
            "r._now=lambda:datetime(2026,10,20,tzinfo=timezone.utc); "
            "s=r.Pros004Store(tempfile.mkdtemp(),diagnostic=True); s.require_evaluation_window()")
        process=subprocess.run([sys.executable,'-O','-c',source],capture_output=True,text=True,
            cwd=Path(__file__).resolve().parents[1])
        self.assertNotEqual(process.returncode,0)
        self.assertIn('IntegrityError',process.stderr)
        self.assertIn('unavailable before',process.stderr)


if __name__=='__main__':
    unittest.main()

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
from test_pregame_sources import pack_fixture, NOW as LEGACY_NOW
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
    f.issue(player_id='10')
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
    def legacy_source_fixture(self):
        from multisport_lab import pregame_sources
        root=self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(pregame_sources,'_now',return_value=LEGACY_NOW))
        self.enterContext(patch.object(rec.frozen_ledger,'_now',return_value=LEGACY_NOW))
        pack=pack_fixture()
        self.enterContext(patch.object(pregame_sources,'PANEL_SHA',pack['history_provenance']['normalized_panel_sha256']))
        source=rec.frozen_ledger.Ledger(root)
        reference=source.record_research_inputs(pack)
        return rec._Pros004Ledger(root),reference

    def test_legacy_semantic_cache_preserves_fresh_bytes_hashes_objects_and_clocks(self):
        from multisport_lab import pregame_sources
        ledger,reference=self.legacy_source_fixture()
        validator=pregame_sources.validate_pack
        with patch.object(pregame_sources,'validate_pack',wraps=validator) as checked:
            first=ledger.read(reference);second=ledger.read(reference)
            self.assertEqual(checked.call_count,1)
            self.assertEqual(first,second);self.assertIsNot(first,second)
            first['data']['source_pack']['history']['rows'].clear()
            self.assertTrue(ledger.read(reference)['data']['source_pack']['history']['rows'])
            self.assertEqual(checked.call_count,1)
        with patch.object(rec.frozen_ledger,'_now',return_value=LEGACY_NOW-timedelta(microseconds=1)):
            with self.assertRaisesRegex(IntegrityError,'future'):
                ledger.read(reference)
        self.assertEqual(len(ledger._legacy_source_validations),1)
        path=ledger._path(reference.kind,reference.record_id)
        original=path.read_bytes();changed=json.loads(original)
        changed['payload']['data']['source_pack']['history']['rows'].clear()
        changed['payload_sha256']=digest(changed['payload']);path.write_bytes(canonical(changed))
        # A valid envelope checksum with changed semantics cannot reuse the old
        # successful cache key, even if the caller supplies its new payload hash.
        altered=LedgerRef(reference.kind,reference.record_id,changed['payload_sha256'])
        with self.assertRaises(ValueError):ledger.read(altered)
        self.assertEqual(len(ledger._legacy_source_validations),1)
        # The ordinary original reference and a broken checksum also still fail.
        with self.assertRaises(ValueError):ledger.read(reference)
        path.write_bytes(original+b' ')
        # Extra harmless JSON whitespace has the same valid semantics but is
        # freshly decoded: it is not a cached mutable payload object.
        self.assertEqual(ledger.read(reference)['record_id'],reference.record_id)
        path.write_bytes(original.replace(b'LOCAL_RECEIPT_ONLY',b'LOCAL_RECEIPT_XNLY'))
        with self.assertRaises(IntegrityError):ledger.read(reference)

    def test_legacy_semantic_cache_is_bounded_and_does_not_cache_new_compact_inputs(self):
        ledger,reference=self.legacy_source_fixture();payload=ledger.read(reference)
        original_key=next(iter(ledger._legacy_source_validations))
        with patch.object(rec,'MAX_LEDGER_RECORDS',2),patch.object(rec.frozen_ledger,'_now',return_value=LEGACY_NOW+timedelta(seconds=3)):
            for offset in (1,2):
                changed=deepcopy(payload);changed['received_at']=stamp(LEGACY_NOW+timedelta(seconds=offset))
                ledger._validate_payload(changed,kind=reference.kind,record_id=reference.record_id)
            self.assertEqual(len(ledger._legacy_source_validations),2)
            self.assertNotIn(original_key,ledger._legacy_source_validations)
        f=ProducerFixture(self)
        f.store.body(f.history_ref);f.store.body(f.event_ref)
        self.assertEqual(len(f.store.ledger._legacy_source_validations),0)

    def test_legacy_semantic_cache_does_not_cache_parent_or_correction_graph_checks(self):
        ledger,reference=self.legacy_source_fixture();ledger.read(reference)
        child=ledger.append('input_captures','synthetic-child',{'note':'No evidence claim'},references=(reference,))
        index=ledger.scan();self.assertIn(child.record_id,index['input_captures'])
        path=ledger._path(reference.kind,reference.record_id);original=path.read_bytes()
        changed=json.loads(original);changed['payload']['received_at']=stamp(LEGACY_NOW+timedelta(seconds=1))
        changed['payload_sha256']=digest(changed['payload']);path.write_bytes(canonical(changed))
        with patch.object(rec.frozen_ledger,'_now',return_value=LEGACY_NOW+timedelta(seconds=2)):
            with self.assertRaisesRegex(IntegrityError,'missing or changed|chronology'):
                ledger.scan()
        path.write_bytes(original)
        first=ledger.append('outcomes','synthetic-cache-correction-first',{'identity':{'player':'10'},'note':'First'})
        replacement=ledger.append('outcomes','synthetic-cache-correction-second',{'identity':{'player':'10'},'note':'Second'})
        other=ledger.append('outcomes','synthetic-cache-correction-other-subject',{'identity':{'player':'20'},'note':'Other'})
        corrected=ledger.correct(first,replacement,reason='Synthetic correction graph test')
        ledger.scan()
        correction=ledger._path(corrected.kind,corrected.record_id)
        content=json.loads(correction.read_bytes())
        content['payload']['data']['replacement']=other.to_record()
        content['payload']['references']=[first.to_record(),other.to_record()]
        content['payload_sha256']=digest(content['payload']);correction.write_bytes(canonical(content))
        with self.assertRaisesRegex(IntegrityError,'correction changes subject identity'):ledger.scan()

    def test_full_comparison_and_metadata_are_reserved_before_first_write(self):
        plan=rec.full_study_capacity()
        self.assertEqual(plan['comparison_records'],442)
        self.assertEqual(plan['full_study_records_before_reserve'],499)
        self.assertEqual(plan['maximum_records_including_reserve'],512)
        self.assertEqual(plan['counts']['correction_or_failure_reserve'],13)
        self.assertEqual(plan['maximum_planned_bytes'],24576000)
        self.assertEqual(plan['remaining_bytes_after_reserve'],8978432)
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
        self.assertEqual(f.store.capacity_report()['actual_records'],3)

    def test_event_cannot_bind_history_from_another_evidence_lane(self):
        f=ProducerFixture(self)
        changed=deepcopy(f.event);changed['mode']='READINESS_DIAGNOSTIC'
        changed['sourcepack_id']=digest({k:v for k,v in changed.items() if k!='sourcepack_id'})
        with self.assertRaisesRegex(IntegrityError,'evidence lanes differ'):
            f.store.store_event(changed,f.history_ref)
        self.assertEqual(f.store.capacity_report()['actual_records'],3)

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
        self.assertEqual(f.store.capacity_report()['actual_records'],4)

    def test_one_missing_peer_is_preserved_on_restart_and_late_completion_rejected(self):
        f=ProducerFixture(self);claim,_=f.store.claim_event(f.event_ref,f.binding)
        first,_=f.generate('R0');ref=f.store.persist_forecast(first,f.event_ref,f.history_ref,claim)
        raw=f.store.ledger._path(ref.kind,ref.record_id).read_bytes()
        peer,_=f.generate('K0')
        f.record_clock.return_value=CUTOFF+timedelta(minutes=6)
        f.ledger_clock.return_value=CUTOFF+timedelta(minutes=6)
        recovered=rec.Pros004Store(f.tmp,diagnostic=True)
        report=recovered.recover_event(f.event_ref,f.binding)
        self.assertEqual(report['status'],'RETAINED_UNADMITTED')
        self.assertEqual(report['retained_models'],1)
        self.assertEqual(report['issued_models'],0)
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
        self.assertEqual(f.store.recover_event(f.event_ref,f.binding)['retained_models'],1)

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


    def test_actual_write_completion_after_deadline_or_latency_is_unadmitted_on_restart(self):
        for prewrite,complete in ((299,301),(5,126)):
            with self.subTest(prewrite=prewrite,actual_complete=complete):
                f=ProducerFixture(self)
                for clock in (f.record_clock,f.ledger_clock,f.producer_clock):
                    clock.return_value=CUTOFF+timedelta(seconds=prewrite)
                claim,_=f.store.claim_event(f.event_ref,f.binding)
                body,_=f.generate('R0')
                original_write=rec.frozen_ledger.write_receipt
                def delayed(path,payload,**kwargs):
                    result=original_write(path,payload,**kwargs)
                    if payload.get('kind')=='forecasts':
                        f.record_clock.return_value=CUTOFF+timedelta(seconds=complete)
                        f.ledger_clock.return_value=CUTOFF+timedelta(seconds=complete)
                    return result
                with patch.object(rec.frozen_ledger,'write_receipt',side_effect=delayed):
                    with self.assertRaisesRegex(IntegrityError,'local persistence completed late'):
                        f.store.persist_forecast(body,f.event_ref,f.history_ref,claim)
                ref=f.store.lookup_forecast(f.event_ref,'10','R0')
                self.assertIsNotNone(ref)
                original=f.store.ledger._path(ref.kind,ref.record_id).read_bytes()
                fresh=rec.Pros004Store(f.tmp,diagnostic=True)
                status=fresh.admission_status(ref)
                self.assertEqual(status['received_at_prewrite'],stamp(CUTOFF+timedelta(seconds=prewrite)))
                self.assertEqual(status['local_persistence_completed_at'],stamp(CUTOFF+timedelta(seconds=complete)))
                self.assertFalse(status['local_timely']);self.assertFalse(status['eligible_for_comparison'])
                recovery=fresh.recover_event(f.event_ref,f.binding)
                self.assertEqual(recovery['retained_models'],1);self.assertEqual(recovery['issued_models'],0)
                with self.assertRaisesRegex(IntegrityError,'lacks timely local'):
                    fresh.complete_checkpoint(ref,f.ack)
                self.assertEqual(original,fresh.ledger._path(ref.kind,ref.record_id).read_bytes())

    def test_event_input_actual_persistence_must_finish_before_selection_close(self):
        f=ProducerFixture(self)
        temporary=self.enterContext(tempfile.TemporaryDirectory())
        for clock in (f.record_clock,f.ledger_clock):clock.return_value=f.input_clock.return_value
        fresh=rec.Pros004Store(temporary,diagnostic=True)
        history=fresh.store_history(f.history)
        self.assertEqual(history,f.history_ref)
        close=CUTOFF-timedelta(minutes=10)
        for clock in (f.record_clock,f.ledger_clock):clock.return_value=close-timedelta(seconds=1)
        original_write=rec.frozen_ledger.write_receipt
        def delayed(path,payload,**kwargs):
            result=original_write(path,payload,**kwargs)
            if payload.get('data',{}).get('pros004',{}).get('schema_version')=='nba-pros004-event-v1':
                for clock in (f.record_clock,f.ledger_clock):clock.return_value=close+timedelta(seconds=1)
            return result
        with patch.object(rec.frozen_ledger,'write_receipt',side_effect=delayed):
            with self.assertRaisesRegex(IntegrityError,'before selection closed'):
                fresh.store_event(f.event,history)
        ref=fresh.ledger._existing('research_inputs',rec._logical(f.event))
        self.assertIsNotNone(ref)
        status=rec.Pros004Store(temporary,diagnostic=True).admission_status(ref)
        self.assertFalse(status['local_timely']);self.assertFalse(status['timing_complete'])
        self.assertEqual(status['local_persistence_completed_at'],stamp(close+timedelta(seconds=1)))

    def test_interruption_before_completion_journal_cannot_be_repaired_as_timely(self):
        f=ProducerFixture(self);claim,_=f.store.claim_event(f.event_ref,f.binding)
        body,_=f.generate('R0')
        append=rec.completion.append_completion
        def fail_original(root,reference,**kwargs):
            if reference.kind=='forecasts':raise OSError('crash before completion evidence')
            return append(root,reference,**kwargs)
        with patch.object(rec.completion,'append_completion',side_effect=fail_original):
            with self.assertRaisesRegex(OSError,'before completion evidence'):
                f.store.persist_forecast(body,f.event_ref,f.history_ref,claim)
        ref=f.store.lookup_forecast(f.event_ref,'10','R0')
        fresh=rec.Pros004Store(f.tmp,diagnostic=True)
        self.assertIsNone(fresh.admission_status(ref)['local_persistence_completed_at'])
        with patch.object(prod,'generate_forecast',side_effect=AssertionError('must not regenerate retained original')):
            with self.assertRaisesRegex(IntegrityError,'no replacement generation'):
                f.issue(store=fresh,player_id='10')
        self.assertEqual(fresh.recover_event(f.event_ref,f.binding)['issued_models'],0)

    def test_remote_completion_latency_is_durable_and_bool_is_not_an_ack(self):
        f=ProducerFixture(self);claim,_=f.store.claim_event(f.event_ref,f.binding)
        body,_=f.generate('R0');ref=f.store.persist_forecast(body,f.event_ref,f.history_ref,claim)
        with self.assertRaisesRegex(IntegrityError,'structured independent'):
            f.store.complete_checkpoint(ref,lambda value:True)
        self.assertIsNone(f.store.admission_status(ref)['remote_checkpoint_completed_at'])
        def delayed(value):
            for clock in (f.record_clock,f.ledger_clock):clock.return_value=CUTOFF+timedelta(seconds=126)
            return f.ack(value)
        with self.assertRaisesRegex(IntegrityError,'remote checkpoint completed late'):
            f.store.complete_checkpoint(ref,delayed)
        status=rec.Pros004Store(f.tmp,diagnostic=True).admission_status(ref)
        self.assertTrue(status['local_timely']);self.assertFalse(status['remote_timely'])
        self.assertEqual(status['remote_checkpoint_completed_at'],stamp(CUTOFF+timedelta(seconds=126)))
        self.assertFalse(status['timing_complete']);self.assertFalse(status['eligible_for_comparison'])
        # A durable but late acknowledgment cannot be renewed on restart or
        # silently let the missing peer proceed within the wider five minutes.
        f.producer_clock.return_value=CUTOFF+timedelta(seconds=126)
        original=f.store.ledger._path(ref.kind,ref.record_id).read_bytes()
        with patch.object(prod,'generate_forecast',side_effect=AssertionError('late original cannot be repaired by a peer')):
            with self.assertRaisesRegex(IntegrityError,'retained remote checkpoint completed late'):
                f.issue(store=rec.Pros004Store(f.tmp,diagnostic=True),player_id='10')
        self.assertIsNone(f.store.lookup_forecast(f.event_ref,'10','K0'))
        self.assertEqual(f.store.ledger._path(ref.kind,ref.record_id).read_bytes(),original)

    def test_event_remote_readback_must_also_finish_before_selection_close(self):
        f=ProducerFixture(self)
        # Retain an independent local-only diagnostic pack, with no original
        # remote acknowledgment that could be mistaken for this operation.
        temporary=self.enterContext(tempfile.TemporaryDirectory())
        store=rec.Pros004Store(temporary,diagnostic=True)
        close=START-timedelta(minutes=100)
        for clock in (f.record_clock,f.ledger_clock):clock.return_value=f.input_clock.return_value
        history=store.store_history(f.history)
        for clock in (f.record_clock,f.ledger_clock):clock.return_value=close-timedelta(seconds=1)
        event=store.store_event(f.event,history)
        def delayed(reference):
            for clock in (f.record_clock,f.ledger_clock):clock.return_value=close+timedelta(seconds=1)
            value=f.ack(reference);value['readback_raw_sha256']=store._raw_sha256(reference)
            from multisport_lab.pros004_snapshot import snapshot_manifest
            value['snapshot_sha256']=digest(snapshot_manifest(store.root))
            return value
        with self.assertRaisesRegex(IntegrityError,'remote checkpoint completed late'):
            store.complete_checkpoint(event,delayed)
        status=rec.Pros004Store(temporary,diagnostic=True).admission_status(event)
        self.assertTrue(status['local_timely']);self.assertFalse(status['remote_timely'])
        self.assertFalse(status['timing_complete'])
        self.assertEqual(status['remote_checkpoint_completed_at'],stamp(close+timedelta(seconds=1)))

    def test_bounded_operational_failure_is_event_bound_and_never_future_dated(self):
        f=ProducerFixture(self)
        ref=f.store.store_failure(f.event_ref,status='MISSING_PEER',reason='Synthetic blocked peer',
            operation='REMOTE_CHECKPOINT',subject_id='10')
        self.assertEqual(f.store.body(ref)['event_ref'],f.event_ref.to_record())
        bad=deepcopy(f.store.body(ref));bad['recorded_at']=stamp(ISSUE+timedelta(seconds=1))
        with self.assertRaisesRegex(IntegrityError,'observation clock'):
            f.store._append(bad,references=(f.event_ref,))
        with self.assertRaisesRegex(IntegrityError,'outside the frozen cohort'):
            f.store.store_failure(f.event_ref,status='PARTIAL',reason='Synthetic',operation='GENERATION',subject_id='999')

    def test_all_operational_source_clocks_precede_the_immutable_receipt(self):
        f=ProducerFixture(self)
        claim,_=f.store.claim_event(f.event_ref,f.binding)
        schemas=[(f.store.body(claim),'claimed_at'),
            ({'schema_version':'nba-pros004-date-status-v1','recorded_at':stamp(ISSUE)},'recorded_at'),
            ({'schema_version':'nba-pros004-study-manifest-v1','recorded_at':stamp(ISSUE)},'recorded_at'),
            (f.history,'imported_at')]
        for body,clock in schemas:
            with self.subTest(schema=body['schema_version']):
                changed=deepcopy(body);changed[clock]=stamp(ISSUE+timedelta(seconds=1))
                with self.assertRaisesRegex(IntegrityError,'after its receipt'):
                    rec.Pros004Store._validate_receipt_clocks({'received_at':stamp(ISSUE)},changed)
        early=deepcopy(f.store.body(claim))
        early['claimed_at']=stamp(f.input_clock.return_value-timedelta(microseconds=1))
        with self.assertRaisesRegex(IntegrityError,'precedes its retained input'):
            f.store._validate(early,(f.event_ref,))

    def test_exact_snapshot_ack_and_final_journal_prefix_are_required(self):
        f=ProducerFixture(self)
        claim,_=f.store.claim_event(f.event_ref,f.binding)
        body,_=f.generate('R0');ref=f.store.persist_forecast(body,f.event_ref,f.history_ref,claim)
        def unrelated(reference):
            value=f.ack(reference);value['snapshot_sha256']='f'*64;return value
        with self.assertRaisesRegex(IntegrityError,'exact retained snapshot prefix'):
            f.store.complete_checkpoint(ref,unrelated)
        self.assertIsNone(f.store.admission_status(ref)['remote_checkpoint_completed_at'])
        f.store.complete_checkpoint(ref,f.ack)
        original=rec.completion.journal_path(f.tmp).read_bytes()
        result=f.store.finalize_checkpoint((ref,),f.ack)
        self.assertTrue(result['timely'])
        self.assertEqual(result['metadata_publication_status'],'INDEPENDENTLY_RECOVERED_CURRENT_PREFIX')
        self.assertEqual(rec.completion.journal_path(f.tmp).read_bytes(),original)
        with self.assertRaisesRegex(IntegrityError,'exact completion-journal prefix'):
            f.store.finalize_checkpoint((ref,),unrelated)
        def late(reference):
            for clock in (f.record_clock,f.ledger_clock):clock.return_value=CUTOFF+timedelta(seconds=301)
            return f.ack(reference)
        report=f.store.finalize_checkpoint((ref,),late)
        self.assertFalse(report['timely'])
        self.assertEqual(report['metadata_publication_status'],'LATE_METADATA_PUBLICATION')
        restarted=rec.Pros004Store(f.tmp,diagnostic=True)
        status=restarted.admission_status(ref)
        self.assertTrue(status['timing_complete'])  # Original ACK is unchanged.
        self.assertFalse(status['eligible_for_comparison'])
        self.assertEqual(status['metadata_publication_status'],'NOT_ESTABLISHED_BY_LOCAL_JOURNAL')
        self.assertEqual(rec.completion.journal_path(f.tmp).read_bytes(),original)


if __name__=='__main__':
    unittest.main()

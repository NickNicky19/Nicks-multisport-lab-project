"""Invented OP002 fixtures only: timing, immutable recovery and publication."""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import operational_pilot as op, operational_publication as public
from multisport_lab import pregame_sources as src
from multisport_lab.integrity import IntegrityError, canonical, digest, stamp
from multisport_lab.ledger import Ledger, LedgerRef
from test_pregame_sources import pack_fixture, tiny_history, provenance, NOW as OLD_NOW
from test_pros004_inputs import NOW, START, event_observations
from test_pros004_records import outcome_bytes

CUTOFF=START-timedelta(minutes=90)
ISSUE=CUTOFF+timedelta(seconds=5)
ACTUAL_HISTORY_ID=op.ORIGINAL_HISTORY_ID
ACTUAL_PANEL_SHA=op.PANEL_SHA256


def synthetic_raw(raw,*,observed,mode='SYNTHETIC_DIAGNOSTIC',event_id='401900001',supersedes=None):
    """Invented metadata only; real authenticated crypto has separate tests."""
    from multisport_lab import operational_raw as raw_contract
    body={'schema_version':raw_contract.SCHEMA,'pilot_id':op.PROTOCOL_ID,'mode':mode,'event_id':event_id,
        'source_url':'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event='+event_id,
        'request_started_at':stamp(observed-timedelta(seconds=1)),'source_observed_at':stamp(observed),
        'source_updated_at':None,'imported_at':stamp(observed),'encryption_completed_at':stamp(observed),
        'cipher_persistence_completed_at':stamp(observed),'manifest_prepared_at':stamp(observed),
        'encryption':raw_contract.ENCRYPTION,'raw_sha256':hashlib.sha256(raw).hexdigest(),'raw_bytes':len(raw),
        'cipher_sha256':'b'*64,'cipher_bytes':len(raw)+100,'recipient_certificate_sha256':'c'*64,
        'admission_sha256':'d'*64 if mode=='REAL_TIME_CAPTURED' else None,'supersedes':supersedes,
        'correction_reason':'Synthetic source correction' if supersedes else None}
    body['capture_id']=digest({k:v for k,v in body.items() if k not in raw_contract._IDENTITY_EXCLUDED})
    return raw_contract._reference(body),body


class OperationalFixture:
    def __init__(self,case,*,acknowledge_event=True):
        stack=ExitStack();case.addCleanup(stack.close)
        self.tmp=stack.enter_context(tempfile.TemporaryDirectory());self.root=Path(self.tmp)
        self.clock=stack.enter_context(patch.object(op,'_now',return_value=NOW))
        self.ledger_clock=stack.enter_context(patch('multisport_lab.ledger._now',return_value=NOW))
        self.source_clock=stack.enter_context(patch.object(src,'_now',return_value=NOW))
        stack.enter_context(patch('multisport_lab.baseline._now',side_effect=lambda:self.clock.return_value))
        base=tiny_history()[0]
        rows=[replace(base,event_id='1001',player_id='10'),
              replace(base,event_id='1002',player_id='20',event_start=base.event_start+timedelta(days=1)),
              replace(base,event_id='1003',player_id='30',event_start=base.event_start+timedelta(days=2))]
        p=provenance(rows);raw=src._panel_bytes(rows)
        for name,value in (('PANEL_ROWS',len(rows)),('PANEL_BYTES',len(raw)),('PANEL_SHA256',hashlib.sha256(raw).hexdigest())):
            stack.enter_context(patch.object(op,name,value))
        stack.enter_context(patch.object(src,'PANEL_SHA',p['normalized_panel_sha256']))
        with patch.object(src,'_now',return_value=OLD_NOW):pack=pack_fixture()
        pack['history']=src.compact_history(rows);pack['history_provenance']=p
        pack['sourcepack_id']=digest({k:v for k,v in pack.items() if k!='sourcepack_id'})
        self.original=Ledger(self.root).append('research_inputs','research-inputs:'+digest(pack),{'source_pack':pack})
        stack.enter_context(patch.object(op,'ORIGINAL_HISTORY_ID',self.original.record_id))
        self.store=op.OperationalStore(self.root,diagnostic=True)
        self.history=op.make_history_body(self.original,root=self.root,mode='SYNTHETIC_DIAGNOSTIC')
        self.history_ref=self.store.persist(self.history,references=(self.original,))
        observations=event_observations()
        self.observations=[{'source_id':name,'raw':value['raw'],'metadata':value['source']} for name,value in observations.items()]
        event=src.normalize_event(observations['scoreboard']['raw'],observations['summary']['raw'],'401900001')
        rosters={team:src.normalize_roster(observations['roster-'+team]['raw'],team,season_ending_year=2027) for team in ('8','2')}
        candidates=src.freeze_selection(event,rosters)['players']
        self.plan=op.make_plan(event,candidates,registered_at=NOW-timedelta(days=1))
        self.event=op.make_event_body(self.plan,self.history_ref,self.observations,mode='SYNTHETIC_DIAGNOSTIC')
        self.event_ref=self.store.persist(self.event,references=(self.history_ref,))
        if acknowledge_event:
            self.store.checkpoint(self.event_ref,self.ack)
            self.store.finalize_checkpoint(self.final)
        self.binding=op.make_source_binding(diagnostic=True)
        self.rows=op.history_rows(self.history,self.root)
        self.at(ISSUE)

    def at(self,value):
        self.clock.return_value=self.ledger_clock.return_value=self.source_clock.return_value=value

    def ack(self,reference):
        return {'schema_version':op._schema('remote-checkpoint'),'reference':reference.to_record(),
            'remote_repository':op.REPOSITORY,'remote_branch':'diagnostics/SYNTHETIC_ONLY','remote_commit':'a'*40,
            'snapshot_sha256':digest(op.snapshot_manifest(self.root)),
            'readback_raw_sha256':hashlib.sha256(self.store.ledger._path(reference.kind,reference.record_id).read_bytes()).hexdigest(),
            'journal_prefix_sha256':hashlib.sha256(self.store._journal_path().read_bytes()).hexdigest(),
            'remote_completed_at':stamp(self.clock.return_value)}

    def final(self,prefix):
        return {'schema_version':op._schema('remote-recovery'),'protocol_id':op.PROTOCOL_ID,
            'remote_repository':op.REPOSITORY,'remote_branch':'diagnostics/SYNTHETIC_ONLY','remote_commit':'b'*40,
            'snapshot_sha256':digest(op.snapshot_manifest(self.root)),'journal_sha256':prefix,
            'independent_recovery_completed_at':stamp(self.clock.return_value)}

    def generate(self,model='R0',player='10'):
        return op.generate_forecast(self.event,self.history,self.rows,event_ref=self.event_ref,
            history_ref=self.history_ref,player_id=player,model_key=model,producer_binding=self.binding)

    def persist(self,body):
        return self.store.persist(body,references=(self.event_ref,self.history_ref))


def public_fixture():
    """Pure synthetic wire fixture: no real source, original issuance or write.

    A checksum-consistent REAL_TIME label is deliberately UNADMITTED. This tests
    the browser's nonempty recovery contract without manufacturing live evidence.
    """
    case=unittest.TestCase()
    try:
        f=OperationalFixture(case);event=deepcopy(f.event)
        plan=event['plan'];plan['history_record_id']=ACTUAL_HISTORY_ID;plan['history_rows']=26645
        plan['history_panel_sha256']=ACTUAL_PANEL_SHA;plan['plan_id']=digest({k:v for k,v in plan.items() if k!='plan_id'})
        event['mode']='REAL_TIME_CAPTURED';event['event_input_id']=digest({k:v for k,v in event.items() if k!='event_input_id'})
        event_ref=LedgerRef('research_inputs','e'*64,'f'*64)
        binding=deepcopy(f.binding);binding['commit']='a'*40;binding['verification']='VERIFIED_COMMIT'
        binding['binding_id']=digest({k:v for k,v in binding.items() if k!='binding_id'})
        originals=[]
        for player,model in [('10','R0'),('10','K0'),('20','R0')]:
            body=f.generate(model,player);body['mode']=body['evidence_lane']='REAL_TIME_CAPTURED'
            body['plan_id']=plan['plan_id'];body['producer_binding']=binding;body['event_ref']=event_ref.to_record()
            body['joint_recipe']['event_ref']=event_ref.to_record();body['forecast_id']=digest({k:v for k,v in body.items() if k!='forecast_id'})
            originals.append(body)
        graded=START+timedelta(hours=4,seconds=10);observed=graded-timedelta(seconds=10);f.at(graded)
        raw=outcome_bytes(f);reference,metadata=synthetic_raw(raw,observed=observed,mode='REAL_TIME_CAPTURED')
        with patch.object(op,'ORIGINAL_HISTORY_ID',ACTUAL_HISTORY_ID),patch.object(op,'PANEL_ROWS',26645),patch.object(op,'PANEL_SHA256',ACTUAL_PANEL_SHA),patch('multisport_lab.prospective_outcomes._now',return_value=graded):
            outcomes=op.normalize_outcome_bytes(event,reference,resolver=lambda _:(metadata,raw))
            def admission(at):return {'retained':True,'eligible':False,'local_persistence_completed_at':stamp(at),
                'remote_checkpoint_completed_at':stamp(at),'final_recovery_completed_at':stamp(at),
                'reasons':['Synthetic checksum-consistent fixture has no installed reviewed activation.']}
            forecasts=[public._project(LedgerRef('forecasts',digest({'synthetic':body['forecast_id']}),'1'*64),body,admission(ISSUE)) for body in originals]
            out=[public._project(LedgerRef('outcomes',digest({'synthetic':outcomes[player]['outcome_id']}),'2'*64),outcomes[player]) for player in ('10','20')]
            grades=[]
            for body in originals:
                grade=op.make_grade(body,outcomes[body['player_id']]);grades.append(public._project(LedgerRef('grades',digest({'synthetic':grade['grade_id']}),'3'*64),grade))
            missing=[{'player_id':player,'model_key':model} for player,model in [('20','K0'),('30','R0'),('30','K0'),('50','R0'),('50','K0')]]
            asset=op.seal({'schema_version':public.SCHEMA,'protocol_id':op.PROTOCOL_ID,'generated_at':stamp(graded),
                'status':'PARTIAL','reason':'NON_ISSUANCE SYNTHETIC WIRE FIXTURE; never a genuine future forecast.',
                'counts':{'forecasts':3,'eligible_forecasts':0,'outcomes':2,'grades':3,'pending_grades':0,'missing_peers':5},
                'clocks':{'last_source_capture_at':max(source['observed_at'] for source in event['sources']),
                    'last_issuance_at':stamp(ISSUE),'last_grade_at':stamp(graded)},
                'inputs':[public._project(event_ref,event,admission(NOW))],'forecasts':forecasts,'outcomes':out,'grades':grades,
                'corrections':[],'missing_peers':missing,'qualification':'UNAVAILABLE','financial_settlement':'NOT_EVALUATED'},'asset_id')
            public.validate_asset(asset,now=graded)
            return asset
    finally:case.doCleanups()


class OperationalPilotTests(unittest.TestCase):
    def test_pair_unchanged_laws_all14_and_complete_recovery(self):
        f=OperationalFixture(self)
        result=op.issue_pair(f.store,f.event_ref,f.binding,checkpoint=f.ack,final_checkpoint=f.final)
        self.assertEqual(len(result['forecasts']),8)
        self.assertEqual(result['eligible_originals'],8)
        self.assertEqual(result['genuine_issued'],0)
        self.assertEqual(result['missing'],[])
        for ref,body,admission in result['forecasts']:
            self.assertEqual([c['code'] for c in body['categories']],list(op.MARKETS))
            law=op._fit_laws(f.rows,op._target(body,body['player_id']))[body['model_key']]
            self.assertEqual(body['categories'],op._categories(law))
            self.assertEqual(body['joint_recipe']['joint_sha256'],op.joint_fingerprint(law))
            self.assertEqual(body['joint_recipe']['omitted_atoms'],0)
            self.assertTrue(admission['eligible'])
        before=op.snapshot_manifest(f.root)
        restarted=op.OperationalStore(f.root,diagnostic=True).recover()
        self.assertEqual(restarted['eligible_originals'],8)
        self.assertEqual(before,op.snapshot_manifest(f.root))

    def test_k0_preflight_failure_writes_no_r0(self):
        f=OperationalFixture(self)
        with patch.object(op,'_fit_laws',side_effect=IntegrityError('K0 preflight failed')):
            with self.assertRaisesRegex(IntegrityError,'K0 preflight'):
                op.issue_pair(f.store,f.event_ref,f.binding,checkpoint=f.ack,final_checkpoint=f.final)
        self.assertEqual(f.store.recover(replay=False)['forecasts'],[])

    def test_delayed_local_completion_is_retained_but_never_admitted_on_restart(self):
        f=OperationalFixture(self);body=f.generate();f.at(CUTOFF+timedelta(seconds=299))
        original=f.store.ledger.append
        def delayed(*args,**kwargs):
            value=original(*args,**kwargs);f.at(CUTOFF+timedelta(seconds=301));return value
        with patch.object(f.store.ledger,'append',side_effect=delayed):ref=f.persist(body)
        f.store.checkpoint(ref,f.ack);f.store.finalize_checkpoint(f.final)
        recovered=op.OperationalStore(f.root,diagnostic=True).recover(replay=False)
        self.assertEqual(len(recovered['forecasts']),1)
        self.assertFalse(recovered['forecasts'][0][2]['eligible'])
        self.assertIn('after its registered deadline',str(recovered['forecasts'][0][2]['reasons']))

    def test_local_latency_126s_rejected_after_restart(self):
        f=OperationalFixture(self);body=f.generate();f.at(CUTOFF+timedelta(seconds=131))
        ref=f.persist(body);f.store.checkpoint(ref,f.ack);f.store.finalize_checkpoint(f.final)
        self.assertFalse(op.OperationalStore(f.root,diagnostic=True).admission(ref)['eligible'])

    def test_interrupted_local_ack_cannot_be_manufactured_on_retry(self):
        f=OperationalFixture(self);body=f.generate()
        with patch.object(f.store,'_append_completion',side_effect=OSError('interrupted acknowledgment')):
            with self.assertRaises(OSError):f.persist(body)
        recovered=op.OperationalStore(f.root,diagnostic=True).recover(replay=False)
        self.assertEqual(len(recovered['forecasts']),1)
        ref=recovered['forecasts'][0][0]
        f.persist(body)
        with self.assertRaisesRegex(IntegrityError,'local completion is unacknowledged'):f.store.checkpoint(ref,f.ack)
        self.assertFalse(f.store.admission(ref)['eligible'])

    def test_remote_interruption_retains_original_missing_peer_and_late_repair_fails(self):
        f=OperationalFixture(self)
        def interrupted(_):raise OSError('network interruption')
        with self.assertRaises(OSError):op.issue_pair(f.store,f.event_ref,f.binding,checkpoint=interrupted,final_checkpoint=f.final)
        recovered=f.store.recover(replay=False)
        self.assertEqual(len(recovered['forecasts']),1);self.assertEqual(len(recovered['missing']),7)
        original_raw=f.store.ledger._path('forecasts',recovered['forecasts'][0][0].record_id).read_bytes()
        f.at(CUTOFF+timedelta(seconds=301))
        with self.assertRaisesRegex(IntegrityError,'window missed'):
            op.issue_pair(f.store,f.event_ref,f.binding,checkpoint=f.ack,final_checkpoint=f.final)
        self.assertEqual(original_raw,f.store.ledger._path('forecasts',recovered['forecasts'][0][0].record_id).read_bytes())

    def test_changed_event_stale_inputs_and_different_source_recovery_reject(self):
        f=OperationalFixture(self);changed=deepcopy(f.plan)
        changed['event']['event_starts_at']=stamp(START+timedelta(hours=1))
        changed['event']['event_version']=digest({k:v for k,v in changed['event'].items() if k!='event_version'})
        changed['plan_id']=digest({k:v for k,v in changed.items() if k!='plan_id'})
        f.at(NOW)
        with self.assertRaisesRegex(IntegrityError,'version/status/start/teams changed'):
            op.make_event_body(changed,f.history_ref,f.observations,mode='SYNTHETIC_DIAGNOSTIC')
        stale=deepcopy(f.event);stale['sources'][0]['observed_at']=stamp(CUTOFF-timedelta(minutes=21));stale['sources'][0]['response_completed_at']=stale['sources'][0]['observed_at'];stale['sources'][0]['request_started_at']=stale['sources'][0]['observed_at']
        stale['event_input_id']=digest({k:v for k,v in stale.items() if k!='event_input_id'})
        with self.assertRaisesRegex(IntegrityError,'capture window'):op.validate_event(stale)
        f.at(ISSUE);body=f.generate();f.persist(body)
        binding=deepcopy(f.binding);binding['files']['multisport_lab/operational_pilot.py']='a'*64
        binding['binding_id']=digest({k:v for k,v in binding.items() if k!='binding_id'})
        with self.assertRaisesRegex(IntegrityError,'source binding differs'):
            op.issue_pair(f.store,f.event_ref,binding,checkpoint=f.ack,final_checkpoint=f.final)

    def test_event_input_late_fsync_blocks_generation(self):
        f=OperationalFixture(self)
        # Existing input is timely, but an independently retained proof from its
        # real capture phase stays timely even after subsequent forecast proofs.
        self.assertTrue(f.store.admission(f.event_ref)['eligible'])
        f.at(ISSUE);ref=f.persist(f.generate());f.store.checkpoint(ref,f.ack);f.store.finalize_checkpoint(f.final)
        self.assertTrue(f.store.admission(f.event_ref)['eligible'])
        self.assertGreater(len(f.store.recovery_proofs()),1)

    def test_archive_metadata_and_global_budget_are_counted(self):
        f=OperationalFixture(self)
        ref=f.persist(f.generate());f.store.checkpoint(ref,f.ack);f.store.finalize_checkpoint(f.final)
        inventory=op.metadata_inventory(f.root)
        self.assertEqual(inventory['file_count'],3)
        self.assertTrue(any('remote-recovery.' in row['path'] and row['path'].endswith('.json') for row in inventory['files']))
        with patch.object(op,'MAX_LEDGER_RECORDS',sum(len(items) for items in f.store.ledger.scan().values())+2):
            with self.assertRaisesRegex(IntegrityError,'shared ledger limits'):f.store._check_budget()
        with patch.object(op,'MAX_LEDGER_BYTES',1):
            with self.assertRaisesRegex(IntegrityError,'shared ledger limits'):f.store._check_budget()

    def test_inactive_gate_rejects_hash_dictionary_even_optimized(self):
        with self.assertRaisesRegex(IntegrityError,'NO_REVIEWED_ACTIVATION_INSTALLED'):
            op.require_activation({'status':'REVIEWED_READY'})
        result=subprocess.run([sys.executable,'-O','-c',
            'from multisport_lab.operational_pilot import require_activation; require_activation({"status":"REVIEWED_READY"})'],
            cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertIn('NO_REVIEWED_ACTIVATION_INSTALLED',result.stderr)

    def test_empty_publication_readback_and_checksums(self):
        f=OperationalFixture(self)
        asset=public.make_asset(f.root,now=ISSUE)
        self.assertEqual(asset['status'],'INACTIVE');self.assertEqual(asset['counts']['forecasts'],0)
        directory=f.root/'public';descriptor=public.emit_publication(directory,f.root,now=ISSUE)
        self.assertEqual(public.read_asset(directory,descriptor,now=ISSUE),asset)
        mutated=deepcopy(asset);mutated['counts']['forecasts']=1
        mutated['asset_id']=digest({k:v for k,v in mutated.items() if k!='asset_id'})
        with self.assertRaisesRegex(IntegrityError,'counts differ'):public.validate_asset(mutated,now=ISSUE)

    def test_outcome_bytes_shared_grades_dnp_pending_and_corrections(self):
        f=OperationalFixture(self)
        r0=f.persist(f.generate('R0'));k0=f.persist(f.generate('K0'))
        dnp_forecast=f.persist(f.generate('R0','20'))
        observed=START+timedelta(hours=4);f.at(observed+timedelta(seconds=10))
        raw=outcome_bytes(f);reference,metadata=synthetic_raw(raw,observed=observed)
        with patch('multisport_lab.prospective_outcomes._now',side_effect=lambda:f.clock.return_value):
            outcomes=op.normalize_outcome_bytes(f.event,reference,resolver=lambda ref:(metadata,raw))
        self.assertEqual(outcomes['10']['status'],'APPEARED')
        self.assertEqual(outcomes['20']['status'],'DNP');self.assertEqual(outcomes['30']['status'],'MISSING')
        shared=f.store.persist(outcomes['10'],references=(r0,k0))
        old_grade=f.store.persist(op.make_grade(f.store.body(r0),outcomes['10']),references=(r0,shared))
        f.store.persist(op.make_grade(f.store.body(k0),outcomes['10']),references=(k0,shared))
        dnp=f.store.persist(outcomes['20'],references=(dnp_forecast,))
        self.assertEqual(op.make_grade(f.store.body(dnp_forecast),outcomes['20'])['status'],'DNP_NOT_SCORED')
        self.assertEqual(outcomes['20']['primitives'],None)
        raw2=outcome_bytes(f,final=False);reference2,metadata2=synthetic_raw(raw2,observed=observed,supersedes=reference)
        with patch('multisport_lab.prospective_outcomes._now',side_effect=lambda:f.clock.return_value):
            pending=op.normalize_outcome_bytes(f.event,reference2,resolver=lambda ref:(metadata2,raw2))
        self.assertEqual(pending['10']['status'],'NONFINAL')
        new=f.store.persist(pending['10'],references=(r0,k0));f.store.correct(shared,new,reason='Synthetic final status corrected')
        new_grade=f.store.persist(op.make_grade(f.store.body(r0),pending['10']),references=(r0,new))
        f.store.correct(old_grade,new_grade,reason='Synthetic grade correction')
        recovered=op.OperationalStore(f.root,diagnostic=True).recover(replay=False)
        self.assertEqual(len([body for _,body in recovered['records'] if body['schema_version']==op._schema('outcome')]),3)
        wrong=deepcopy(metadata);wrong['event_id']='999002'
        with self.assertRaisesRegex(IntegrityError,'identity|event/lane'):
            op.normalize_outcome_bytes(f.event,reference,resolver=lambda ref:(wrong,raw))
        with self.assertRaisesRegex(IntegrityError,'readback bytes changed'):
            op.normalize_outcome_bytes(f.event,reference,resolver=lambda ref:(metadata,raw+b' '))

    def test_full_snapshot_rejects_checksum_valid_invalid_foreign_types_optimized(self):
        for kind,schema in [('outcomes','outcome'),('grades','grade'),('research_inputs','history')]:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as root:
                ledger=op._OperationalLedger(root)
                if kind=='research_inputs':
                    body={'schema_version':'nba-pros004-history-v1','study_id':'NBA-ALL13-JOINT-PROS-004','mode':'SYNTHETIC_DIAGNOSTIC'}
                else:body={'schema_version':'nba-pros004-'+schema+'-v1','status':'INVALID','mode':'SYNTHETIC_DIAGNOSTIC'}
                ledger.append(kind,'synthetic-invalid-pros004-'+schema,{'identity':{'event_id':'999004','player_id':'10'},'pros004':body})
                with self.assertRaises((IntegrityError,KeyError)):op.verify_store(root,replay=False)
                result=subprocess.run([sys.executable,'-O','-c',
                    'import sys; from multisport_lab.operational_pilot import verify_store; verify_store(sys.argv[1],replay=False)',root],
                    cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)

    def test_post_fsync_proof_clock_late_and_missing_witness_never_admit(self):
        f=OperationalFixture(self);body=f.generate();ref=f.persist(body);f.store.checkpoint(ref,f.ack)
        f.at(CUTOFF+timedelta(seconds=124));original=op.os.write
        def delayed(descriptor,raw):
            result=original(descriptor,raw)
            if b'"proof_id"' in raw and b'"schema_version":"nba-operational002-remote-recovery-v1"' in raw:
                f.at(CUTOFF+timedelta(seconds=126))
            return result
        with patch.object(op.os,'write',side_effect=delayed):f.store.finalize_checkpoint(f.final)
        self.assertFalse(op.OperationalStore(f.root,diagnostic=True).admission(ref)['eligible'])
        witnesses=[entry for entry in f.store.journal() if entry['kind']=='PROOF_LOCAL']
        self.assertEqual(witnesses[-1]['completed_at'],stamp(CUTOFF+timedelta(seconds=126)))

    def test_nonempty_standalone_public_semantics_and_summary_clocks(self):
        asset=public_fixture();now=op.clock(asset['generated_at'])
        self.assertEqual(asset['counts']['eligible_forecasts'],0)
        with patch.object(op,'_now',return_value=now):public.validate_asset(asset,now=now)
        for mutate in ('clock','foreign_outcome','grade','eligible'):
            with self.subTest(mutate=mutate):
                bad=deepcopy(asset)
                if mutate=='clock':bad['clocks']['last_issuance_at']=None
                elif mutate=='eligible':bad['forecasts'][0]['admission']['eligible']=True;bad['forecasts'][0]['admission']['reasons']=[]
                else:
                    kind='outcomes' if mutate=='foreign_outcome' else 'grades';row=bad[kind][0];record=public.original_record(row)
                    if mutate=='foreign_outcome':record['player_id']='999009'
                    else:record['categories'][0]['crps']='999'
                    key=row['kind']+'_id';record[key]=digest({k:v for k,v in record.items() if k!=key})
                    bad[kind][0]=public._project(LedgerRef.from_record(row['source_record']),record)
                bad['asset_id']=digest({k:v for k,v in bad.items() if k!='asset_id'})
                with patch.object(op,'_now',return_value=now),self.assertRaises(IntegrityError):public.validate_asset(bad,now=now)

    def test_interrupted_proof_witness_allows_new_timely_recovery_without_rewriting_original(self):
        f=OperationalFixture(self);ref=f.persist(f.generate());f.store.checkpoint(ref,f.ack)
        original=f.store.ledger._path(ref.kind,ref.record_id).read_bytes();append=f.store._append_completion
        def interrupted(*args,**kwargs):
            if kwargs.get('proof') is not None:raise OSError('proof witness interrupted')
            return append(*args,**kwargs)
        with patch.object(f.store,'_append_completion',side_effect=interrupted):
            with self.assertRaises(OSError):f.store.finalize_checkpoint(f.final)
        self.assertFalse(f.store.admission(ref)['eligible'])
        f.at(ISSUE+timedelta(seconds=1));f.store.finalize_checkpoint(f.final)
        self.assertTrue(op.OperationalStore(f.root,diagnostic=True).admission(ref)['eligible'])
        self.assertEqual(original,f.store.ledger._path(ref.kind,ref.record_id).read_bytes())

    def test_public_missing_peers_are_exact_fixed_input_cohort_minus_originals(self):
        asset=public_fixture();now=op.clock(asset['generated_at'])
        for mutation in ('foreign','omitted','duplicate','missing_input'):
            with self.subTest(mutation=mutation):
                bad=deepcopy(asset)
                if mutation=='foreign':bad['missing_peers'][0]['player_id']='999999'
                elif mutation=='omitted':bad['missing_peers'].pop()
                elif mutation=='duplicate':bad['missing_peers'].append(deepcopy(bad['missing_peers'][0]))
                else:bad['inputs']=[]
                bad['counts']['missing_peers']=len(bad['missing_peers'])
                bad['asset_id']=digest({k:v for k,v in bad.items() if k!='asset_id'})
                with patch.object(op,'_now',return_value=now),self.assertRaises(IntegrityError):
                    public.validate_asset(bad,now=now)

    def test_final_proof_write_global_and_input_close_boundaries(self):
        for phase in ('forecast','event'):
            with self.subTest(phase=phase):
                f=OperationalFixture(self,acknowledge_event=phase!='event')
                ref=f.persist(f.generate()) if phase=='forecast' else f.event_ref
                before=CUTOFF+timedelta(seconds=299) if phase=='forecast' else CUTOFF-timedelta(seconds=601)
                after=before+timedelta(seconds=2);f.at(before);f.store.checkpoint(ref,f.ack)
                original=op.os.write
                def delayed(descriptor,raw):
                    result=original(descriptor,raw)
                    if b'"schema_version":"nba-operational002-remote-recovery-v1"' in raw:f.at(after)
                    return result
                with patch.object(op.os,'write',side_effect=delayed):f.store.finalize_checkpoint(f.final)
                self.assertFalse(op.OperationalStore(f.root,diagnostic=True).admission(ref)['eligible'])


if __name__=='__main__':unittest.main()

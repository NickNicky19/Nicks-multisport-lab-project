"""Synthetic, disk-backed orchestration fixtures; never actual pilot results.

Only the already-admitted original-forecast boundary is an explicit fixture.
Source clocks, hashes, publisher/config/review originals, final CSV semantics,
append-only files and restart/idempotence are exercised without model fitting.
"""
from contextlib import nullcontext
from copy import deepcopy
import csv
import io
from datetime import timedelta
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

from multisport_lab import sdv_daily_grading as grading
from multisport_lab import sdv_daily_store as storage
from multisport_lab import sdv_daily_producer as producer
from multisport_lab import sdv_daily_outcomes as outcomes
from multisport_lab import sdv_daily_runner as runner
from multisport_lab.integrity import (IntegrityError,canonical,digest,load_json,read_receipt,
    write_receipt,stamp,utc)
from multisport_lab.ledger import LedgerRef,SCHEMA
from test_sdv_daily_inputs import csv_bytes


class SyntheticDiskStore:
    """Known synthetic eligible originals, with actual immutable receipt files.

    This fixture does not claim live dispatch authentication or remote durability.
    The production DailyStore admission boundary is covered separately by the
    existing full typed tests; no actual original forecast is created here.
    """
    def __init__(self,root):
        self.project_root=Path(root);self.ledger=self
        self.interrupt_after=None;self.eligible=True

    def path(self,ref):return self.project_root/'records'/ref.kind/(ref.record_id+'.json')
    def lock(self):return nullcontext()
    def capacity(self,**kwargs):return storage.DailyStore(self.project_root).capacity(**kwargs)
    def admission(self,ref):return {"eligible":self.eligible}
    def append_body(self,kind,body,*,references=(),logical_id=None):
        storage.validate_body(body,kind=kind)
        logical_id=logical_id or digest(body)
        rid=digest({"kind":kind,"logical_id":logical_id});path=self.project_root/'records'/kind/(rid+'.json')
        if path.exists():
            old=read_receipt(path)
            if old['data']['daily'] != body or old['references'] != [ref.to_record() for ref in references]:raise IntegrityError('Synthetic fixture conflicting retry')
            return LedgerRef(kind,rid,digest(old))
        payload={"schema_version":SCHEMA,"kind":kind,"record_id":rid,"logical_id":logical_id,
            "received_at":stamp(grading._now()),"data":{"identity":storage._identity(body),"daily":deepcopy(body)},
            "references":[ref.to_record() for ref in references],"supersedes":None,"persistence_status":"LOCAL_RECEIPT_ONLY"}
        write_receipt(path,payload);ref=LedgerRef(kind,rid,digest(payload))
        if self.interrupt_after == kind:self.interrupt_after=None;raise InterruptedError('Synthetic interruption after '+kind)
        return ref
    def read(self,ref):
        payload=read_receipt(self.path(ref))
        if digest(payload) != ref.payload_sha256:raise IntegrityError('Synthetic reference hash differs')
        return payload
    def records(self):
        rows=[]
        for path in sorted((self.project_root/'records').glob('*/*.json')):
            body=read_receipt(path)
            if body['kind'] != 'corrections':rows.append((LedgerRef(body['kind'],body['record_id'],digest(body)),body['data']['daily']))
        return rows
    def corrections(self):
        result=[]
        for path in (self.project_root/'records/corrections').glob('*.json'):
            payload=read_receipt(path)
            result.append({'reference':LedgerRef('corrections',payload['record_id'],digest(payload)).to_record(),
                'original_ref':payload['supersedes'],'replacement_ref':payload['data']['replacement'],'reason':payload['data']['reason']})
        return result
    def read_outcome_evidence(self,ref):
        body=self.read(ref)['data']['daily'];storage.validate_body(body,kind='research_inputs')
        return storage._validate_outcome_evidence(body)
    def latest(self,ref):
        while True:
            candidates=[]
            for path in (self.project_root/'records/corrections').glob('*.json'):
                p=read_receipt(path)
                if p['supersedes'] == ref.to_record():candidates.append(LedgerRef.from_record(p['data']['replacement']))
            if not candidates:return ref
            if len(candidates) != 1:raise IntegrityError('Synthetic conflicting correction')
            ref=candidates[0]
    def correct(self,original,replacement,*,reason):
        if self.read(original)['data']['identity'] != self.read(replacement)['data']['identity']:raise IntegrityError('Correction changed identity')
        logical='supersedes:'+original.kind+':'+original.record_id;rid=digest({'kind':'corrections','logical_id':logical})
        payload={"schema_version":SCHEMA,"kind":"corrections","record_id":rid,"logical_id":logical,
            "received_at":stamp(grading._now()),"data":{"reason":reason,"replacement":replacement.to_record()},
            "references":[original.to_record(),replacement.to_record()],"supersedes":original.to_record(),"persistence_status":"LOCAL_RECEIPT_ONLY"}
        path=self.project_root/'records/corrections'/(rid+'.json')
        if path.exists():return LedgerRef('corrections',rid,digest(read_receipt(path)))
        write_receipt(path,payload);return LedgerRef('corrections',rid,digest(payload))


class GenuineGradingReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='nml-synthetic-grading-');self.addCleanup(self.temp.cleanup)
        self.store=SyntheticDiskStore(self.temp.name)
        self.now=utc('2026-10-24T12:00:00.000000Z')
        for module in (grading,storage,producer,outcomes,runner):
            p=patch.object(module,'_now',side_effect=lambda:self.now);p.start();self.addCleanup(p.stop)
        self.config=grading.load_config()
        fixture=load_json(Path(__file__).parent/'fixtures/sdv-daily-synthetic.json')
        source=deepcopy(fixture['inputs'][0]);source['mode']='PROSPECTIVE_RESEARCH'
        source=producer.seal({k:v for k,v in source.items() if k != 'input_id'},'input_id')
        # Synthetic registry insertion: authentic live-source admission is not
        # asserted by this fixture's local original references.
        input_ref=self.store.append_body('research_inputs',source)
        self.refs=[]
        for row in fixture['forecasts'][:2]:
            b=deepcopy(row['body']);b.update(mode='PROSPECTIVE_RESEARCH',evidence_lane='DAILY_SNAPSHOT_PROSPECTIVE',
                input_ref=input_ref.to_record(),input_id=source['input_id'],
                generation_started_at='2026-10-23T00:00:01.000000Z',generation_completed_at='2026-10-23T00:00:02.000000Z',
                verified_at='2026-10-23T00:00:03.000000Z',issued_at='2026-10-23T00:00:03.000000Z')
            binding=b['producer_binding'];binding['commit']=grading.FIRST_PRODUCER
            b['producer_binding']=producer.seal({k:v for k,v in binding.items() if k != 'binding_id'},'binding_id')
            b=producer.seal({k:v for k,v in b.items() if k != 'forecast_id'},'forecast_id')
            self.refs.append(self.store.append_body('forecasts',b))
        self.forecast=self.store.read(self.refs[0])['data']['daily']
        role=self.config['roles']['schedule']
        self.event={name:'' for name in role['required_headers']}
        self.event.update(game_id=self.forecast['event_id'],home_id='25',away_id='7',season='2027',season_type='2',
            game_date_time=self.forecast['event_starts_at'],status_type_completed='true',status_type_name='STATUS_FINAL',
            status_type_state='post',home_score='12',away_score='11')
        self.rows=[self.line(self.forecast['player_id'],'25','7',12),self.line('9000001','7','25',11)]

    def line(self,pid,team,opponent,points):
        row={name:'' for name in self.config['roles']['boxscore']['required_headers']}
        row.update(game_id=self.forecast['event_id'],athlete_id=pid,team_id=team,opponent_team_id=opponent,
            season='2027',season_type='2',game_date_time=self.forecast['event_starts_at'],did_not_play='false',minutes='20.0',
            points=str(points),field_goals_made='4',field_goals_attempted='10',three_point_field_goals_made='2',three_point_field_goals_attempted='5',
            free_throws_made=str(points-10),free_throws_attempted=str(points-10),rebounds='4',offensive_rebounds='1',defensive_rebounds='3',
            assists='3',turnovers='1',blocks='0',steals='1',team_score='12' if team == '25' else '11',opponent_team_score='11' if team == '25' else '12')
        return row

    def capture(self,mutator=None):
        triples=[];requests=[]
        for index,(role,rows) in enumerate((('schedule',[self.event]),('boxscore',self.rows))):
            rule=self.config['roles'][role]
            if rows:raw=csv_bytes(rows)
            else:
                stream=io.StringIO(newline="")
                csv.DictWriter(stream,fieldnames=rule['required_headers']).writeheader()
                raw=stream.getvalue().encode()
            metadata=canonical({'tag_name':rule['release_tag'],'assets':[{'id':123+index,'name':rule['asset_name'],
                'size':len(raw),'browser_download_url':rule['asset_url'],'digest':'sha256:'+grading.sha(raw),
                'updated_at':'2026-10-23T04:00:00.000000Z'}]})
            base=self.now-timedelta(seconds=8-index*4)
            clocks={key:stamp(base+timedelta(seconds=n)) for n,key in enumerate(('metadata_retrieval_started_at','metadata_retrieved_at','asset_retrieval_started_at','asset_retrieved_at'))}
            triples.append((raw,metadata,clocks))
            for label,route,body,start,end,limit in ((role+'_metadata',rule['metadata_url'],metadata,base,base+timedelta(seconds=1),262144),
                    (role+'_asset',rule['asset_url'],raw,base+timedelta(seconds=2),base+timedelta(seconds=3),2097152)):
                requests.append({'request_number':len(requests)+1,'label':label,'route':route,'retrieval_started_at':stamp(start),
                    'response_limit_bytes':limit,'automatic_redirects':False,'automatic_retries':0,'status':200,
                    'retrieved_at':stamp(end),'response_read_completed_at':stamp(end),'bytes':len(body),'bytes_read':len(body),
                    'response_exceeded_limit':False,'sha256':grading.sha(body)})
        if mutator:mutator(requests)
        self.last_capture=(triples,requests)
        return grading.retain_source_with_proof(self.store,self.refs,schedule=triples[0],boxscore=triples[1],requests=requests)

    def grade(self):
        refs=self.capture();return grading.normalize_and_grade(self.store,self.refs,*refs)

    def test_complete_originals_shared_outcome_separate_grades_and_restart_are_idempotent(self):
        first=self.grade();self.assertEqual(len(first['outcomes']),1);self.assertEqual(len(first['grades']),2)
        original={path.relative_to(self.store.project_root):path.read_bytes() for path in self.store.project_root.rglob('*.json')}
        self.store=SyntheticDiskStore(self.store.project_root)
        second=self.grade();self.assertEqual(second['outcomes'],first['outcomes']);self.assertEqual(second['grades'],first['grades'])
        self.assertEqual(original,{path.relative_to(self.store.project_root):path.read_bytes() for path in self.store.project_root.rglob('*.json')})
        self.assertEqual(grading.validate_stored_admissions(self.store)['genuine_grades'],2)
        grade=self.store.read(first['grades'][0])['data']['daily']
        self.assertEqual(grade['status'],'SCORED');self.assertEqual(grade['financial_settlement'],'NOT_EVALUATED')

    def test_nonfinal_stays_pending_and_cancelled_has_no_invented_v1_outcome(self):
        self.event.update(status_type_completed='false',status_type_name='STATUS_IN_PROGRESS',status_type_state='in')
        result=self.grade();self.assertEqual(result['grades'],[]);self.assertEqual(len(result['pending']),1)
        self.assertEqual(self.store.read(result['outcomes'][0])['data']['daily']['status'],'NONFINAL')
        self.now+=timedelta(days=1);self.event.update(status_type_name='STATUS_CANCELED',status_type_state='post')
        result=self.grade();self.assertEqual(result['outcomes'],[]);self.assertEqual(result['grades'],[])
        self.assertIn('CANCELLED',result['unresolved_event_state'])

    def test_missing_player_never_becomes_zero_or_dnp(self):
        self.rows[0]['athlete_id']='9000002'
        result=self.grade();outcome=self.store.read(result['outcomes'][0])['data']['daily']
        self.assertEqual(outcome['status'],'MISSING');self.assertIsNone(outcome['primitives']);self.assertEqual(result['grades'],[])

    def test_final_without_target_boxscore_stays_pending_without_invented_missing_outcome(self):
        self.rows=[]
        refs=self.capture()
        original={path:path.read_bytes() for path in self.store.project_root.rglob('*.json')}
        result=grading.normalize_and_grade(self.store,self.refs,*refs)
        self.assertEqual(result['pending'],[self.forecast['player_id']])
        self.assertEqual(result['unresolved_event_state'],'FINAL_BOXSCORE_UNAVAILABLE')
        self.assertEqual(result['outcomes'],[]);self.assertEqual(result['grades'],[])
        self.assertEqual(original,{path:path.read_bytes() for path in self.store.project_root.rglob('*.json')})
        # The generic v1 normalizer's MISSING fallback is not admitted when the
        # whole final event has no boxscore evidence; this is not a player DNP.
        forged=outcomes._normalize(self.store,self.forecast,schedule_ref=refs[0],boxscore_ref=refs[1],normalized_at=stamp(self.now))
        self.assertEqual(forged['status'],'MISSING')
        with self.assertRaisesRegex(grading.FinalEvidencePending,'no target-event'):
            grading.validate_admission_graph(self.store,forged)
        self.assertEqual(grading.validate_stored_admissions(self.store)['genuine_grades'],0)
        repeated=grading.normalize_and_grade(self.store,self.refs,*refs)
        self.assertEqual(repeated,result)
        self.assertEqual(original,{path:path.read_bytes() for path in self.store.project_root.rglob('*.json')})

    def test_unrelated_boxscore_events_do_not_make_target_evidence_available(self):
        for row in self.rows:row['game_id']='999999999'
        result=self.grade()
        self.assertEqual(result['unresolved_event_state'],'FINAL_BOXSCORE_UNAVAILABLE')
        self.assertEqual(result['pending'],[self.forecast['player_id']])
        self.assertEqual(result['outcomes'],[]);self.assertEqual(result['grades'],[])

    def test_missing_boxscore_does_not_hide_invalid_final_schedule_identity(self):
        self.rows=[];self.event['home_id']='999'
        with self.assertRaisesRegex(IntegrityError,'identity/version') as caught:self.grade()
        self.assertNotIsInstance(caught.exception,grading.FinalEvidencePending)

    def test_explicit_dnp_is_not_zero_production(self):
        self.rows[0]['did_not_play']='true';self.rows[0]['minutes']=''
        for key in {'points',*outcomes.SDV_FIELDS.values()}:self.rows[0][key]=''
        self.event['home_score']='0';self.rows[0]['team_score']='0';self.rows[1]['opponent_team_score']='0'
        result=self.grade();body=self.store.read(result['outcomes'][0])['data']['daily']
        self.assertEqual(body['status'],'DNP');self.assertIsNone(body['primitives'])
        self.assertEqual(self.store.read(result['grades'][0])['data']['daily']['status'],'DNP_NOT_SCORED')

    def test_team_total_or_duplicate_player_cannot_be_graded(self):
        self.rows[0]['points']='13';self.rows[0]['free_throws_made']='3';self.rows[0]['free_throws_attempted']='3'
        with self.assertRaisesRegex(IntegrityError,'PTS totals'):self.grade()
        self.rows[0]['points']='12';self.rows[0]['free_throws_made']='2';self.rows[0]['free_throws_attempted']='2'
        self.now+=timedelta(seconds=30);self.rows.append(deepcopy(self.rows[0]))
        with self.assertRaisesRegex(IntegrityError,'Duplicate'):self.grade()

    def test_corrected_stats_append_outcome_and_grade_links_without_changing_originals(self):
        first=self.grade();old={ref:self.store.path(ref).read_bytes() for ref in [*first['outcomes'],*first['grades'],*self.refs]}
        self.now+=timedelta(days=1)
        self.rows[0].update(points='13',free_throws_made='3',free_throws_attempted='3',team_score='13')
        self.rows[1]['opponent_team_score']='13';self.event['home_score']='13'
        revised=self.grade();self.assertEqual(len(revised['corrections']),3)
        for ref,raw in old.items():self.assertEqual(raw,self.store.path(ref).read_bytes())
        self.assertEqual(self.store.latest(first['outcomes'][0]),revised['outcomes'][0])
        repeated=grading.normalize_and_grade(self.store,self.refs,*self.capture());self.assertEqual(repeated['grades'],revised['grades'])

    def test_interrupted_after_original_outcome_restart_writes_only_missing_grades(self):
        refs=self.capture();self.store.interrupt_after='outcomes'
        with self.assertRaises(InterruptedError):grading.normalize_and_grade(self.store,self.refs,*refs)
        original=[(ref,body) for ref,body in self.store.records() if body['schema_version']==producer.OUTCOME_SCHEMA]
        self.assertEqual(len(original),1);raw=self.store.path(original[0][0]).read_bytes()
        self.now+=timedelta(seconds=15);self.store=SyntheticDiskStore(self.store.project_root)
        recovered=grading.normalize_and_grade(self.store,self.refs,*refs)
        self.assertEqual(recovered['outcomes'],[original[0][0]]);self.assertEqual(len(recovered['grades']),2)
        self.assertEqual(raw,self.store.path(original[0][0]).read_bytes())

    def test_interrupted_proof_publication_retry_fills_only_missing_original_csvs(self):
        self.store.interrupt_after='research_inputs'
        with self.assertRaises(InterruptedError):self.capture()
        # Retry the exact same capture clocks. No newly captured observation is
        # manufactured, and original proof creation bytes are retained.
        before=[(ref,self.store.path(ref).read_bytes()) for ref,body in self.store.records() if body['schema_version']==storage.OUTCOME_EVIDENCE_SCHEMA]
        self.assertEqual(len(before),1)
        refs=self.capture();self.assertEqual(len(refs),2)
        self.assertEqual(before[0][1],self.store.path(before[0][0]).read_bytes())
        self.assertEqual(len([body for _,body in self.store.records() if body['schema_version']==storage.OUTCOME_EVIDENCE_SCHEMA]),3)

    def test_noneligible_original_and_budget_failure_do_not_create_proof(self):
        self.store.eligible=False
        with self.assertRaisesRegex(IntegrityError,'not eligible'):self.capture()
        self.store.eligible=True
        with patch.object(storage,'MAX_LEDGER_BYTES',1),self.assertRaisesRegex(IntegrityError,'budget'):
            self.capture()
        self.assertFalse([b for _,b in self.store.records() if b['schema_version']==storage.OUTCOME_EVIDENCE_SCHEMA])

    def test_config_pin_and_proof_tamper_rejected_despite_valid_raw_receipt_checksums(self):
        result=self.grade();outcome=self.store.read(result['outcomes'][0])['data']['daily']
        source_ref=LedgerRef.from_record(outcome['source_refs'][0])
        proof_ref=LedgerRef.from_record(self.store.read(source_ref)['references'][0])
        raw,meta=self.store.read_outcome_evidence(proof_ref)
        proof=grading._decode(raw);proof['config_original_sha256']='0'*64
        proof=grading.sealed({k:v for k,v in proof.items() if k != 'proof_id'},'proof_id')
        bad_body=grading._retained_body(canonical(proof),meta)
        bad=self.store.append_body('research_inputs',bad_body,references=(LedgerRef.from_record(self.forecast['input_ref']),))
        # New checksum-consistent source nodes still cannot supply the wrong
        # review/config original or inherit operational admission.
        refs=[]
        for source in outcome['source_refs']:
            ref=LedgerRef.from_record(source);body=self.store.read(ref)['data']['daily']
            refs.append(self.store.append_body('research_inputs',body,references=(bad,),logical_id='tampered:'+ref.record_id))
        changed=deepcopy(outcome);changed['source_refs']=[ref.to_record() for ref in refs]
        changed=producer.seal({k:v for k,v in changed.items() if k != 'outcome_id'},'outcome_id')
        with self.assertRaisesRegex(IntegrityError,'reviewed committed bytes'):grading.validate_admission_graph(self.store,changed)

    def test_unrelated_routes_or_changed_canonical_asset_clock_are_rejected(self):
        changes=[lambda rows:rows[0].update(route='https://api.github.com/repos/unrelated/release'),
            lambda rows:rows[1].update(route='https://github.com/unrelated/file.csv'),
            lambda rows:rows[1].update(retrieval_started_at=stamp(utc(rows[1]['retrieval_started_at'])-timedelta(seconds=1)))]
        for change in changes:
            with self.subTest(change=change),self.assertRaisesRegex(IntegrityError,'route or canonical'):
                self.capture(change)
        self.assertFalse([b for _,b in self.store.records() if b['schema_version']==storage.OUTCOME_EVIDENCE_SCHEMA])

    def test_cancelled_source_cannot_be_forged_into_nonfinal_outcome_admission(self):
        self.event.update(status_type_completed='false',status_type_name='STATUS_CANCELED',status_type_state='post')
        refs=self.capture()
        forged=outcomes._normalize(self.store,self.forecast,schedule_ref=refs[0],boxscore_ref=refs[1],normalized_at=stamp(self.now))
        self.assertEqual(forged['status'],'NONFINAL')  # Existing v1 generic fallback, explicitly not admitted.
        with self.assertRaisesRegex(IntegrityError,'Unsupported event state'):grading.validate_admission_graph(self.store,forged)

    def test_interrupted_correction_links_and_missing_peer_grades_recover_once(self):
        first=self.grade();self.now+=timedelta(days=1)
        self.rows[0].update(points='13',free_throws_made='3',free_throws_attempted='3',team_score='13')
        self.rows[1]['opponent_team_score']='13';self.event['home_score']='13'
        refs=self.capture();self.store.interrupt_after='outcomes'
        with self.assertRaises(InterruptedError):grading.normalize_and_grade(self.store,self.refs,*refs)
        self.store=SyntheticDiskStore(self.store.project_root)
        recovered=grading.normalize_and_grade(self.store,self.refs,*refs)
        self.assertEqual(len(recovered['grades']),2);self.assertEqual(len(recovered['corrections']),3)
        self.assertEqual(self.store.latest(first['outcomes'][0]),recovered['outcomes'][0])

    def test_changed_proof_retention_clock_is_not_repaired_by_valid_checksums(self):
        result=self.grade();outcome=self.store.read(result['outcomes'][0])['data']['daily']
        original=LedgerRef.from_record(outcome['source_refs'][0]);oldproof=LedgerRef.from_record(self.store.read(original)['references'][0])
        raw,meta=self.store.read_outcome_evidence(oldproof)
        meta['source_observed_at']=stamp(self.now-timedelta(seconds=1))
        bad=self.store.append_body('research_inputs',grading._retained_body(raw,meta),references=(LedgerRef.from_record(self.forecast['input_ref']),))
        refs=[]
        for source in outcome['source_refs']:
            old=LedgerRef.from_record(source);body=self.store.read(old)['data']['daily']
            refs.append(self.store.append_body('research_inputs',body,references=(bad,),logical_id='badclock:'+old.record_id))
        changed=deepcopy(outcome);changed['source_refs']=[ref.to_record() for ref in refs]
        changed=producer.seal({k:v for k,v in changed.items() if k != 'outcome_id'},'outcome_id')
        with self.assertRaisesRegex(IntegrityError,'retention clocks'):grading.validate_admission_graph(self.store,changed)

    def test_proof_envelope_is_light_input_link_but_embedded_originals_are_authenticated(self):
        result=self.grade();outcome=self.store.read(result['outcomes'][0])['data']['daily']
        source=LedgerRef.from_record(outcome['source_refs'][0]);proof_ref=LedgerRef.from_record(self.store.read(source)['references'][0])
        self.assertEqual(self.store.read(proof_ref)['references'],[self.forecast['input_ref']])
        self.store.eligible=False
        with self.assertRaisesRegex(IntegrityError,'not eligible'):grading.validate_admission_graph(self.store,outcome)

    def test_publication_fast_path_cannot_hide_a_grade_without_its_outcome(self):
        result=self.grade();self.store.path(result['outcomes'][0]).unlink()
        with self.assertRaisesRegex(IntegrityError,'lacks an admitted outcome'):
            grading.validate_stored_admissions(self.store)

    def test_review_ancestor_requires_full_history_and_recovers_after_unshallow_fetch(self):
        # Exact config/review copies, two tiny local Git commits, no models or
        # HTTP. A Pages depth-one checkout cannot authenticate an older proof.
        config,config_raw,review_raw,_=grading._trusted_materials()
        source=self.store.project_root/'reviewed-source';source.mkdir()
        def git(*args,cwd=source):
            return subprocess.run(['git',*args],cwd=cwd,capture_output=True,text=True,
                check=True,timeout=20)
        git('init','--quiet','--initial-branch=main')
        git('config','user.name','Synthetic Grading Review')
        git('config','user.email','synthetic-review@example.invalid')
        for relative,raw in ((grading.DEFAULT_CONFIG_PATH,config_raw),(config['source_review_receipt_path'],review_raw)):
            path=source/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        git('add','--all');git('commit','--quiet','-m','Reviewed config and review software fixture')
        reviewed=git('rev-parse','HEAD').stdout.strip()
        (source/'later-main.txt').write_text('Later main commit; source review bytes remain unchanged.\n')
        git('add','later-main.txt');git('commit','--quiet','-m','Advance main without changing source review')
        with patch.object(grading,'ROOT',source):
            resolved=grading._trusted_materials(reviewed)
        self.assertEqual(resolved[0]['config_id'],config['config_id'])
        self.assertEqual(resolved[1:3],(config_raw,review_raw))
        shallow=self.store.project_root/'shallow'
        git('clone','--quiet','--depth=1','--branch','main',source.as_uri(),str(shallow),cwd=self.store.project_root)
        self.assertEqual(git('rev-parse','--is-shallow-repository',cwd=shallow).stdout.strip(),'true')
        with patch.object(grading,'ROOT',shallow):
            with self.assertRaisesRegex(IntegrityError,'not retained in this source ancestry'):
                grading._trusted_materials(reviewed)
        git('fetch','--quiet','--unshallow','origin','main',cwd=shallow)
        self.assertEqual(git('rev-parse','--is-shallow-repository',cwd=shallow).stdout.strip(),'false')
        with patch.object(grading,'ROOT',shallow):
            recovered=grading._trusted_materials(reviewed)
        self.assertEqual(recovered[0]['config_id'],config['config_id'])
        self.assertEqual(recovered[1:3],(config_raw,review_raw))
        self.assertEqual(recovered[3],reviewed)

    def append_imported_later_partial_proof(self,original_ref,days):
        # Deliberately import a typed/checksummed proof without the writer API,
        # as a damaged/untrusted archive could. Recovery must enforce limits.
        raw,meta=self.store.read_outcome_evidence(original_ref)
        proof=grading._decode(raw);delta=timedelta(days=days)
        proof['created_at']=stamp(utc(proof['created_at'])+delta)
        for source in proof['sources']:
            for key in grading.CLOCK_FIELDS:source[key]=stamp(utc(source[key])+delta)
        for row in proof['requests']:
            for key in ('retrieval_started_at','retrieved_at','response_read_completed_at'):
                if key in row:row[key]=stamp(utc(row[key])+delta)
        proof=grading.sealed({key:value for key,value in proof.items() if key != 'proof_id'},'proof_id')
        for key in ('source_observed_at','retrieval_started_at','retrieved_at'):meta[key]=proof['created_at']
        return self.store.append_body('research_inputs',grading._retained_body(canonical(proof),meta),
            references=(LedgerRef.from_record(proof['input_ref']),))

    def test_recovery_rejects_third_partial_proof_before_any_outcome(self):
        refs=self.capture();first=LedgerRef.from_record(self.store.read(refs[0])['references'][0])
        self.now+=timedelta(days=2)
        self.append_imported_later_partial_proof(first,1)
        self.assertEqual(grading.validate_stored_admissions(self.store)['genuine_outcomes'],0)
        self.append_imported_later_partial_proof(first,2)
        with self.assertRaisesRegex(IntegrityError,'two-capture admission budget'):
            grading.validate_stored_admissions(self.store)

    def test_publication_rejects_excess_imported_proof_even_with_valid_outcome_and_grades(self):
        result=self.grade();body=self.store.read(result['outcomes'][0])['data']['daily']
        source=LedgerRef.from_record(body['source_refs'][0]);first=LedgerRef.from_record(self.store.read(source)['references'][0])
        self.now+=timedelta(days=2)
        self.append_imported_later_partial_proof(first,1);self.append_imported_later_partial_proof(first,2)
        with self.assertRaisesRegex(IntegrityError,'two-capture admission budget'):
            grading.validate_stored_admissions(self.store)

    def test_capacity_credits_completed_capture_instead_of_reserving_it_again(self):
        initial=grading.grading_capacity(self.store)
        self.grade()
        first=grading.grading_capacity(self.store)
        self.assertEqual(first['future_capture_attempts'],1)
        self.assertLess(first['reserved_bytes'],initial['reserved_bytes'])
        # Other legitimate retained bytes must count, while the already closed
        # source observation must not consume the complete two-capture reserve
        # for a second time. The remaining second observation still fits.
        original_capacity=self.store.capacity
        def actual_retained(**kwargs):
            result=original_capacity(**kwargs)
            result.update(existing_bytes=20*1024*1024,existing_records=200)
            return result
        self.store.capacity=actual_retained
        self.assertTrue(grading.grading_capacity(self.store)['fits'])
        self.now+=timedelta(days=1)
        second=self.grade()
        self.assertEqual(len(second['grades']),2)
        after=grading.grading_capacity(self.store)
        self.assertEqual(after['future_capture_attempts'],0)
        self.assertLess(after['reserved_bytes'],first['reserved_bytes'])
        self.assertTrue(after['fits'])

    def test_capacity_accounts_for_proof_originals_and_one_later_capture(self):
        report=grading.grading_capacity(self.store)
        self.assertTrue(report['fits']);self.assertEqual(report['grading_evidence']['proof_records'],2)
        self.assertEqual(report['grading_evidence']['csv_records'],4)
        self.assertLessEqual(report['existing_bytes']+report['reserved_bytes'],32*1024*1024)


if __name__=='__main__':unittest.main()

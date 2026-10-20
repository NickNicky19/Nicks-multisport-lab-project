"""Synthetic public contracts only. No source captures, real issuance or study scores."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import pros004_publication as pub
from multisport_lab.integrity import IntegrityError, canonical, digest, stamp
from multisport_lab.ledger import LedgerRef
from test_pros004_producer import ProducerFixture, ISSUE, START

NOW = START + timedelta(days=2)


def reseal(record, key):
    record[key] = digest({k:v for k,v in record.items() if k != key})
    return record


def synthetic_forecast(case, model='R0'):
    """Invented tiny history and simulated clocks; never persist this lane change."""
    f = ProducerFixture(case)
    body, _ = f.generate(model)
    f.ledger_clock.return_value = NOW
    body['mode'] = 'REAL_TIME_CAPTURED'
    body['producer_binding']['verification'] = 'VERIFIED_COMMIT'
    body['producer_binding']['model_commit'] = 'a'*40  # Fictitious contract test identity.
    reseal(body, 'forecast_id')
    admission = {'retained':True, 'local_persistence_completed_at':None, 'remote_checkpoint_completed_at':None,
                 'eligible_for_comparison':False, 'reasons':['Synthetic test: no actual independent completion acknowledgment.']}
    return pub.project_original(body, LedgerRef('forecasts','1'*64,'2'*64).to_record(), admission=admission)


def synthetic_grade(row, *, scored=False):
    f = pub.original_record(row)
    grade = {'schema_version':'nba-pros004-grade-v1','study_id':pub.STUDY_ID,'mode':'REAL_TIME_CAPTURED',
        **{key:f[key] for key in ('event_id','event_version','event_starts_at','player_id','team_id','opponent_id','model_key','forecast_id')},
        'outcome_id':digest({'synthetic_outcome':[f['event_id'],f['event_version'],f['player_id']]}),'graded_at':stamp(NOW),'status':'DNP_NOT_SCORED','categories':[],'reported_minutes':None,
        'financial_settlement':'NOT_EVALUATED','qualification':'UNAVAILABLE'}
    if scored:
        from multisport_lab.ledger import _score_categories
        from multisport_lab.pros004_records import _score_reported_minutes
        grade['status']='SCORED'
        grade['categories']=_score_categories(f,{'categories':[{'code':c['code'],'units':c['units'],'observed':0} for c in f['categories']]})
        grade['reported_minutes']=_score_reported_minutes(f,{'minutes':20.0,'minutes_precision':'seconds'})
    reseal(grade,'grade_id')
    return pub.project_original(grade,LedgerRef('grades','3'*64,'4'*64).to_record(),model_version=f['model_version'])


class Pros004PublicationTests(unittest.TestCase):
    def test_empty_inactive_index_and_current_legacy_collection_stay_separate(self):
        descriptor,index,assets = pub.make_assets([],[],now=NOW)
        self.assertEqual(index['activation'],'INACTIVE')
        self.assertEqual(index['totals'],{'forecasts':0,'grades':0})
        self.assertEqual(index['categories'],list(pub.MARKETS))
        self.assertEqual(index['aggregate_evaluation']['status'],'NOT_RUN')
        with tempfile.TemporaryDirectory() as name:
            for path,raw in assets.items(): (Path(name)/path).write_bytes(raw)
            self.assertEqual(pub.read_publication(Path(name),descriptor,now=NOW)['forecasts'],[])
        # The real ledger remains legacy-only; merely reading does not issue.
        root=Path(__file__).resolve().parents[1]
        with patch('multisport_lab.pros004_records._now',return_value=NOW), patch('multisport_lab.ledger._now',return_value=NOW):
            forecasts,grades,excluded=pub.collect_public_records(root,now=NOW)
        self.assertEqual((forecasts,grades),([],[]))

    def test_operational_versions_bind_exact_corresponding_source_contract(self):
        from multisport_lab.pros004_producer import LEGACY_SOURCE_FILES
        row=synthetic_forecast(self)
        for version in (1,2,3):
            body=pub.original_record(row)
            body['producer_version']=f"pros004-r0-producer-v{version}"
            body['producer_binding']['schema_version']=f"nba-pros004-source-binding-v{version}"
            if version==1:
                body['producer_binding']['source_sha256']={k:v for k,v in body['producer_binding']['source_sha256'].items() if k in LEGACY_SOURCE_FILES}
            reseal(body,'forecast_id');projected=pub.project_original(body,row['source_record'],admission=row['admission'])
            pub.validate_forecast_projection(projected,now=NOW)
            body['producer_binding']['schema_version']=f"nba-pros004-source-binding-v{2 if version==1 else 1}"
            reseal(body,'forecast_id')
            with self.assertRaises(IntegrityError):pub.validate_forecast_projection(pub.project_original(body,row['source_record'],admission=row['admission']),now=NOW)

    def test_exact_unsigned_json_preserves_integral_float_source_bytes(self):
        row=synthetic_forecast(self)
        original=pub.original_record(row)
        original['reported_minutes']['pmf'][0]['value']=float(original['reported_minutes']['pmf'][0]['value'])
        reseal(original,'forecast_id')
        row=pub.project_original(original,row['source_record'],admission=row['admission'])
        self.assertIn('.0',row['record_json'])
        self.assertEqual(hashlib.sha256(row['record_json'].encode()).hexdigest(),row['original_id'])
        self.assertEqual(pub.original_record(row),original)
        pub.validate_forecast_projection(row,now=NOW)
        # A numeric parse/re-encode in another runtime cannot replace the exact text.
        bad=deepcopy(row);bad['record_json']=bad['record_json'].replace('10.0','10',1)
        reseal(bad,'projection_id')
        with self.assertRaises(IntegrityError): pub.validate_forecast_projection(bad,now=NOW)

    def test_negative_workload_support_rejects_even_with_consistent_checksum_and_mean(self):
        row=synthetic_forecast(self);body=pub.original_record(row)
        body['reported_minutes']={'pmf':[{'value':-.5,'probability':'0.5'},{'value':1.5,'probability':'0.5'}],
            'mean':'0.5','interval80':[-.5,1.5],'precision':'reported_source_precision_not_exact_workload'}
        reseal(body,'forecast_id');bad=pub.project_original(body,row['source_record'],admission=row['admission'])
        with self.assertRaisesRegex(IntegrityError,'reported-minute support'):pub.validate_forecast_projection(bad,now=NOW)

    def test_unadmitted_original_is_retained_but_cannot_claim_completion(self):
        row=synthetic_forecast(self)
        pub.validate_forecast_projection(row,now=NOW)
        for admission in (
            {**row['admission'],'eligible_for_comparison':True,'reasons':[]},
            {**row['admission'],'eligible_for_comparison':True,'reasons':[],
             'local_persistence_completed_at':stamp(ISSUE+timedelta(seconds=121)),
             'remote_checkpoint_completed_at':stamp(ISSUE+timedelta(seconds=122))},
            {**row['admission'],'reasons':[]},
        ):
            bad=deepcopy(row);bad['admission']=admission;reseal(bad,'projection_id')
            with self.assertRaises(IntegrityError):pub.validate_forecast_projection(bad,now=NOW)

    def test_inactive_collection_rejects_eligible_claim_even_with_timely_clocks(self):
        row=synthetic_forecast(self)
        row['admission']={'retained':True,'local_persistence_completed_at':stamp(ISSUE+timedelta(seconds=1)),
            'remote_checkpoint_completed_at':stamp(ISSUE+timedelta(seconds=2)),'eligible_for_comparison':True,'reasons':[]}
        reseal(row,'projection_id')
        pub.validate_forecast_projection(row,now=NOW)  # Clock proof alone is not activation.
        with self.assertRaisesRegex(IntegrityError,'Inactive'):pub.make_assets([row],[],now=NOW)

    def test_complete_planned_inventory_is_paged_without_dropping_atoms(self):
        first=synthetic_forecast(self);rows=[];grades=[]
        for i in range(168):
            body=pub.original_record(first);body['player_id']=str(1000+i);body['player_label']='Synthetic '+str(i);body['joint_recipe']['target']['player_id']=body['player_id']
            reseal(body,'forecast_id');row=pub.project_original(body,LedgerRef('forecasts',digest({'synthetic':i}),'2'*64).to_record(),admission=first['admission'])
            rows.append(row);grades.append(synthetic_grade(row))
        descriptor,index,assets=pub.make_assets(rows,grades,now=NOW)
        self.assertEqual(len(index['pages']),84)
        self.assertEqual(index['totals'],{'forecasts':168,'grades':168})
        self.assertLessEqual(max(map(len,assets.values())),pub.MAX_ASSET_BYTES)
        with tempfile.TemporaryDirectory() as name:
            for path,raw in assets.items():(Path(name)/path).write_bytes(raw)
            recovered=pub.read_publication(Path(name),descriptor,now=NOW)
        self.assertEqual(recovered['forecasts'],rows)
        self.assertEqual(recovered['grades'],grades)
        self.assertEqual(pub.original_record(recovered['forecasts'][0])['categories'],pub.original_record(first)['categories'])
        with self.assertRaisesRegex(IntegrityError,'bounds'):pub.make_assets(rows+[first],grades,now=NOW)

    def test_checksum_consistent_bad_grade_identity_status_and_metrics_reject(self):
        row=synthetic_forecast(self);grade=synthetic_grade(row);forecasts={row['original_id']:row}
        pub.validate_grade_projection(grade,forecasts,now=NOW)
        for field,value in [('player_id','other'),('status','WON'),('graded_at',stamp(ISSUE-timedelta(seconds=1))),('financial_settlement','WON')]:
            body=pub.original_record(grade);body[field]=value;reseal(body,'grade_id')
            bad=pub.project_original(body,grade['source_record'],model_version=grade['model_version'])
            with self.assertRaises(IntegrityError):pub.validate_grade_projection(bad,forecasts,now=NOW)
        body=pub.original_record(grade);body['categories']=[{'code':'PTS','observed':0}];reseal(body,'grade_id')
        with self.assertRaises(IntegrityError):pub.validate_grade_projection(pub.project_original(body,grade['source_record'],model_version=grade['model_version']),forecasts,now=NOW)

    def test_scored_metrics_and_workload_are_checked_against_exact_original(self):
        row=synthetic_forecast(self);good=synthetic_grade(row,scored=True);by_id={row['original_id']:row}
        pub.validate_grade_projection(good,by_id,now=NOW)
        for change in (lambda g:g['categories'][0].update(crps='999'),lambda g:g['reported_minutes'].update(crps='999'),
                       lambda g:g['reported_minutes']['intervals'][0].update(predicted_mass='0')):
            body=pub.original_record(good);change(body);reseal(body,'grade_id')
            bad=pub.project_original(body,good['source_record'],model_version=good['model_version'])
            with self.assertRaises(IntegrityError):pub.validate_grade_projection(bad,by_id,now=NOW)

    def test_duplicate_targets_active_grades_and_cross_subject_shared_outcomes_reject(self):
        row=synthetic_forecast(self);other=pub.original_record(row);other['player_label']='Changed duplicate label';reseal(other,'forecast_id')
        duplicate=pub.project_original(other,row['source_record'],admission=row['admission'])
        with self.assertRaisesRegex(IntegrityError,'target/model'):pub.make_assets([row,duplicate],[],now=NOW)
        grade=synthetic_grade(row);revision=pub.original_record(grade);revision['graded_at']=stamp(NOW-timedelta(seconds=1));reseal(revision,'grade_id')
        with self.assertRaisesRegex(IntegrityError,'Multiple active'):pub.make_assets([row],[grade,pub.project_original(revision,grade['source_record'],model_version=grade['model_version'])],now=NOW)
        body=pub.original_record(row);body['player_id']='999';body['joint_recipe']['target']['player_id']='999';reseal(body,'forecast_id')
        peer=pub.project_original(body,row['source_record'],admission=row['admission']);wrong=pub.original_record(synthetic_grade(peer))
        wrong['outcome_id']=pub.original_record(grade)['outcome_id'];reseal(wrong,'grade_id')
        with self.assertRaisesRegex(IntegrityError,'another subject'):pub.make_assets([row,peer],[grade,pub.project_original(wrong,grade['source_record'],model_version=grade['model_version'])],now=NOW)

    def test_page_tampering_and_checksum_consistent_omission_reject(self):
        descriptor,index,assets=pub.make_assets([synthetic_forecast(self)],[],now=NOW)
        bad=deepcopy(index);bad['totals']['forecasts']=0;reseal(bad,'index_id')
        with self.assertRaisesRegex(IntegrityError,'omit'):pub.validate_index(bad,descriptor,now=NOW)
        with tempfile.TemporaryDirectory() as name:
            for path,raw in assets.items():(Path(name)/path).write_bytes(raw)
            (Path(name)/index['pages'][0]['path']).write_bytes(b'{}')
            with self.assertRaises(IntegrityError):pub.read_publication(Path(name),descriptor,now=NOW)

    @unittest.skipUnless(shutil.which('node'), 'Node is required for the cross-runtime publication contract')
    def test_python_generated_source_bound_pages_recover_through_browser_loader(self):
        from multisport_lab import publication as legacy
        row=synthetic_forecast(self);peer=synthetic_forecast(self,model='K0')
        grade=synthetic_grade(row,scored=True);peer_grade=synthetic_grade(peer,scored=True)
        descriptor,index,assets=pub.make_assets([row,peer],[grade,peer_grade],now=NOW)
        sport=legacy.empty_nba(Path(__file__).resolve().parents[1],now=NOW)
        sport_raw=canonical(sport);sport_hash=hashlib.sha256(sport_raw).hexdigest()
        sport_name=f'nba.{sport_hash}.json';assets[sport_name]=sport_raw
        manifest={'schema_version':3,'build_commit':'a'*40,'published_at':stamp(NOW),'publication_status':'RESEARCH_ONLY',
            'supported_sports':['NBA'],'sports':[{'league':'NBA','path':sport_name,'sha256':sport_hash,'generated_at':sport['generated_at'],
                'status':'RESEARCH_ONLY','retained':False,'error':None}],'errors':{},'pros004':descriptor,'pros004_error':None}
        manifest['snapshot_id']=digest(manifest);assets['manifest.json']=canonical(manifest)
        code="""import {webcrypto} from 'node:crypto';
import {loadSnapshot} from './web/snapshot.mjs';
let input='';for await(const chunk of process.stdin)input+=chunk;
const assets=JSON.parse(input);
// Frozen synthetic fixture date may follow the machine clock: this controls
// browser publication-clock checking only, never a producer/source clock.
Date.now=()=>Date.parse('2026-10-25T00:00:00Z');
const result=await loadSnapshot(async path=>new Response(assets[path.replace('./data/','')]),webcrypto);
if(result.errors.length||result.pros004Error||result.pros004?.forecasts.length!==2||result.pros004?.grades.length!==2)throw new Error(JSON.stringify({errors:result.errors,pros004Error:result.pros004Error}));
if(new Set(result.pros004.forecasts.map(row=>JSON.parse(row.record_json).model_key)).size!==2)throw new Error('R0/K0 identity lost');
console.log('Python19-file paired '+JSON.parse(result.pros004.forecasts[0].record_json).producer_version+' + original LedgerRef + complete PMFs + grade browser readback passed');"""
        result=subprocess.run(['node','--input-type=module','-e',code],input=json.dumps({k:v.decode() for k,v in assets.items()}),
            cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('browser readback passed',result.stdout)

    def test_explicit_integrity_checks_survive_optimized_python(self):
        code="from multisport_lab.pros004_publication import validate_forecast_projection; from multisport_lab.integrity import IntegrityError\ntry: validate_forecast_projection({},now='2026-10-24T00:00:00.000000Z')\nexcept IntegrityError: print('rejected')\nelse: raise RuntimeError('invalid public record admitted')"
        result=subprocess.run([sys.executable,'-O','-c',code],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'rejected')

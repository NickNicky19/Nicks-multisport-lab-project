// Invented software fixtures only; excluded from site assets and ledger builds.
import {typedFixture, fixture, canonical, hash, clock} from './fixtures.mjs';
import {PROS004_STUDY} from '../pros004.mjs';
const laws={R0:'2a217b021ae25041920d14db6fbb1a14197ef4593b2b59965bbdef6f01304689',K0:'282bb23a570bc6aaa217ab7f65ba223613c805801d8c479bc51aef0291b72be7'};
export const models={R0:'nba_joint_empirical_r0_v1',K0:'nba_joint_lagged_workload_prior_k0_v1'};
export function project(record, admission, modelVersion) {
  const forecast=record.schema_version==='nba-pros004-forecast-v1',key=forecast?'forecast_id':'grade_id';
  const {[key]:ignore,...body}=record;
  let record_json=canonical(body);
  if(forecast)record_json=record_json.replace('"value":10}', '"value":10.0}');
  const row={schema_version:forecast?'nba-pros004-public-forecast-v1':'nba-pros004-public-grade-v1',study_id:PROS004_STUDY,evidence_lane:'REAL_TIME_CAPTURED',source_record:{kind:forecast?'forecasts':'grades',record_id:hash({synthetic_original:record_json}),payload_sha256:'2'.repeat(64)},record_encoding:'CANONICAL_ORIGINAL_BODY_WITHOUT_ID',record_json,original_id:hash(record_json),...(forecast?{admission}:{model_version:modelVersion})};
  row.projection_id=hash(row);return row;
}
export function prospectiveRow(i=0,model='R0') {
  const base=typedFixture().sport.forecasts[0],source_sha256=Object.fromEntries(['pros004_producer','pros004_inputs','pros004_records','baseline','development_003','development_002','research_pilot','nba_data','basketball','integrity','ledger','forecast_contract','pregame_sources','pros004_completion','pros004_activation','pros004_remote','pros004_raw','pros004_snapshot'].map(n=>[`multisport_lab/${n}.py`,'a'.repeat(64)]));
  source_sha256['scripts/verify_pros004_readiness.py']='a'.repeat(64);
  Object.assign(source_sha256,{'multisport_lab/baseline.py':laws.R0,'multisport_lab/development_003.py':laws.K0});
  const history_ref={kind:'research_inputs',record_id:'3'.repeat(64),payload_sha256:'4'.repeat(64)},event_ref={kind:'research_inputs',record_id:'5'.repeat(64),payload_sha256:'6'.repeat(64)};
  const r={schema_version:'nba-pros004-forecast-v1',study_id:PROS004_STUDY,mode:'REAL_TIME_CAPTURED',...Object.fromEntries(['id_namespace','league','event_id','team_id','opponent_id','event_starts_at','trained_through','cutoff_at','history_freeze','conditioning','categories','qualification'].map(k=>[k,base[k]])),player_id:`synthetic-${i}`,player_label:`Synthetic ${i}`,model_key:model,model_version:models[model],producer_version:`pros004-${model.toLowerCase()}-producer-v3`,producer_binding:{schema_version:'nba-pros004-source-binding-v3',model_commit:'a'.repeat(40),verification:'VERIFIED_COMMIT',source_sha256,law_sha256:laws,runtime:{python:'SYNTHETIC',implementation:'CPython',libc:['',''],machine:'SYNTHETIC',float_mantissa_bits:53}},history_ref,event_ref,event_version:'7'.repeat(64),generation_started_at:'1999-12-01T18:30:00.000000Z',generation_completed_at:'1999-12-01T18:30:05.000000Z',verified_at:'1999-12-01T18:30:05.000000Z',issued_at:'1999-12-01T18:30:05.000000Z',reported_minutes:{pmf:[{value:10,probability:'1'}],mean:'10',interval80:[10,10],precision:'reported_source_precision_not_exact_workload'}};
  r.joint_recipe={schema_version:'nba-pros004-complete-joint-replay-v1',algorithm:r.model_version,history_ref,event_ref,target:{sport:'basketball',league:'NBA',id_namespace:'espn',event_id:r.event_id,player_id:r.player_id,event_start:r.event_starts_at,cutoff:r.cutoff_at},support_atom_count:2,atom_order:'frozen_algorithm_order_no_sampling_or_truncation',joint_sha256:'8'.repeat(64),input_sha256:'9'.repeat(64),pool_history_count:2,player_history_count:2,fallback:null,encoding:'COMPLETE_SOURCE_BOUND_REPLAY_PLUS_ALL_ORIGINAL_MARGINALS',omitted_atoms:0};
  return project(r,{retained:true,local_persistence_completed_at:null,remote_checkpoint_completed_at:null,eligible_for_comparison:false,reasons:['Synthetic: no actual activation or completion evidence.']});
}
export function gradeRow(row, scored=false) {
  const f=JSON.parse(row.record_json),base=typedFixture().sport.performance[0];
  return project({schema_version:'nba-pros004-grade-v1',study_id:PROS004_STUDY,mode:'REAL_TIME_CAPTURED',...Object.fromEntries(['event_id','event_version','event_starts_at','player_id','team_id','opponent_id','model_key'].map(k=>[k,f[k]])),forecast_id:row.original_id,outcome_id:hash({synthetic_outcome:[f.event_id,f.event_version,f.player_id]}),graded_at:clock,status:scored?'SCORED':'DNP_NOT_SCORED',categories:scored?base.categories:[],reported_minutes:scored?{observed:10,observed_precision:'seconds',forecast_precision:f.reported_minutes.precision,crps:'0',absolute_mean_error:'0',log_loss:'0',log_loss_status:'FINITE',intervals:[.5,.8,.95].map(n=>({nominal:String(n),lower:10,upper:10,covered:true,predicted_mass:'1'}))}:null,financial_settlement:'NOT_EVALUATED',qualification:'UNAVAILABLE'},null,f.model_version);
}
export function pairedCollection(count=2, withGrades=true) {
  const forecasts=Array.from({length:count},(_,i)=>prospectiveRow(Math.floor(i/2),i%2?'K0':'R0')),grades=withGrades?forecasts.map(row=>gradeRow(row)):[],assets={};
  const index={schema_version:'nba-pros004-public-index-v1',study_id:PROS004_STUDY,league:'NBA',generated_at:clock,status:'RESEARCH_ONLY',activation:'INACTIVE',qualification:'UNAVAILABLE',financial_settlement:'NOT_EVALUATED',categories:typedFixture().sport.forecasts[0].categories.map(x=>x.code),page_size:4,totals:{forecasts:forecasts.length,grades:grades.length},excluded:{diagnostic_forecasts:0,diagnostic_grades:0,superseded_grades:0},grade_visibility:'LATEST_ACTIVE_WITH_SOURCE_LEDGER_REFERENCES_SUPERSEDED_COUNTED',aggregate_evaluation:{status:'NOT_RUN',not_before:'2026-11-25T00:00:00.000000Z'},future_availability:{status:'UNAVAILABLE',reasons:['PROS004 remains inactive.','Complete permitted UTC-date source inventory remains unresolved.','Timely persistence and independent remote completion remain required.']},pages:[]};
  for(const [kind,records] of [['forecasts',forecasts],['grades',grades]])for(let offset=0;offset<records.length;offset+=4){
    const page={schema_version:'nba-pros004-public-page-v1',study_id:PROS004_STUDY,league:'NBA',kind,page_number:offset/4,page_size:4,total_records:records.length,generated_at:clock,records:records.slice(offset,offset+4)},sha256=hash(page),path=`pros004.${kind}.${sha256}.json`,raw=canonical(page);
    assets[path]=raw;index.pages.push({kind,page_number:offset/4,path,sha256,encoded_bytes:Buffer.byteLength(raw),records:page.records.length});
  }
  index.index_id=hash(index);const sha256=hash(index),path=`pros004.index.${sha256}.json`;assets[path]=canonical(index);
  const descriptor={path,sha256,generated_at:clock,status:'RESEARCH_ONLY',retained:false,error:null};
  const {sport,manifest}=typedFixture();manifest.schema_version=3;manifest.pros004=descriptor;manifest.pros004_error=null;delete manifest.snapshot_id;manifest.snapshot_id=hash(manifest);
  assets[manifest.sports[0].path]=canonical(sport);assets['manifest.json']=canonical(manifest);
  return {index,descriptor,assets,manifest,forecasts,grades};
}

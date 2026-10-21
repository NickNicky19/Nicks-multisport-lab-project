// New one-event OP002 operational records. No activation, aggregate or ticket gate.
import {ALL_NBA_CATEGORIES, NBA_UNITS, validateResearchForecast, validateResearchGrade, utcMicros} from './research.mjs';

export const PAIRED_RESEARCH_PROTOCOL = 'NBA-PAIRED-OPS-002';
export const PAIRED_RESEARCH_MAX_BYTES = 1024 * 1024;
const SHA=/^[a-f0-9]{64}$/;
const MODELS={R0:'nba_joint_empirical_r0_v1',K0:'nba_joint_lagged_workload_prior_k0_v1'};
const LAWS={R0:'2a217b021ae25041920d14db6fbb1a14197ef4593b2b59965bbdef6f01304689',K0:'282bb23a570bc6aaa217ab7f65ba223613c805801d8c479bc51aef0291b72be7'};
const SOURCE_FILES=["multisport_lab/operational_pilot.py","multisport_lab/operational_publication.py","multisport_lab/operational_remote.py","multisport_lab/operating_diagnostic.py","multisport_lab/publication_ledger.py","multisport_lab/operational_preflight.py","multisport_lab/operational_raw.py","multisport_lab/prospective_outcomes.py","multisport_lab/offer_publication.py","multisport_lab/pros004_records.py","multisport_lab/pros004_completion.py","multisport_lab/pros004_remote.py","multisport_lab/pros004_snapshot.py","multisport_lab/baseline.py","multisport_lab/development_003.py","multisport_lab/development_002.py","multisport_lab/research_pilot.py","multisport_lab/pros004_producer.py","multisport_lab/pros004_inputs.py","multisport_lab/pros004_publication.py","multisport_lab/nba_data.py","multisport_lab/basketball.py","multisport_lab/integrity.py","multisport_lab/ledger.py","multisport_lab/forecast_contract.py","multisport_lab/pregame_sources.py","scripts/verify_pros004_readiness.py"];
const schema=name=>`nba-operational002-${name}-v1`;
const fields=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join(',')===[...keys].sort().join(',');
const require=(ok,message)=>{if(!ok)throw new Error(message);};
const text=v=>typeof v==='string'&&v.trim()===v&&v.length>0&&v.length<=2048;
const canonical=v=>v&&typeof v==='object'?Array.isArray(v)?`[${v.map(canonical).join(',')}]`:`{${Object.keys(v).sort().map(k=>`${JSON.stringify(k)}:${canonical(v[k])}`).join(',')}}`:JSON.stringify(v);
const bytes=v=>new TextEncoder().encode(v);
const reference=(v,kind)=>fields(v,['kind','record_id','payload_sha256'])&&v.kind===kind&&SHA.test(v.record_id)&&SHA.test(v.payload_sha256);

function unambiguousJson(raw) {
  require(typeof raw==='string'&&bytes(raw).length<=64*1024,'Original paired record exceeds its encoded bound.');
  let at=0;const ws=()=>{while(at<raw.length&&/\s/.test(raw[at]))at++;};
  const string=()=>{const start=at++;while(at<raw.length){const c=raw[at++];if(c==='\\'){at++;continue;}if(c==='"')return JSON.parse(raw.slice(start,at));}throw new Error('Unterminated paired JSON string.');};
  const value=depth=>{require(depth<=64,'Paired JSON nesting exceeds its bound.');ws();const c=raw[at];
    if(c==='"'){string();return;}
    if(c==='{'){at++;ws();const keys=new Set();if(raw[at]==='}'){at++;return;}while(at<raw.length){require(raw[at]==='"','Invalid paired JSON object key.');const key=string();require(!keys.has(key),'Duplicate paired original JSON key.');keys.add(key);ws();require(raw[at++]===':','Invalid paired JSON separator.');value(depth+1);ws();if(raw[at]==='}'){at++;return;}require(raw[at++]===',','Invalid paired object delimiter.');ws();}throw new Error('Unterminated paired object.');}
    if(c==='['){at++;ws();if(raw[at]===']'){at++;return;}while(at<raw.length){value(depth+1);ws();if(raw[at]===']'){at++;return;}require(raw[at++]===',','Invalid paired array delimiter.');}throw new Error('Unterminated paired array.');}
    const token=/^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(raw.slice(at));require(token,'Invalid paired JSON token.');at+=token[0].length;
  };value(0);ws();require(at===raw.length,'Trailing paired JSON data.');return JSON.parse(raw);
}

export function originalPairedRecord(row) {
  require(fields(row,['kind','source_record','record_encoding','original_id','record_json','admission'])&&['event','forecast','outcome','grade'].includes(row.kind)&&row.record_encoding==='CANONICAL_ORIGINAL_BODY_WITHOUT_ID'&&SHA.test(row.original_id),'Invalid paired original wrapper.');
  const body=unambiguousJson(row.record_json),key=row.kind==='event'?'event_input_id':`${row.kind}_id`;
  require(body&&typeof body==='object'&&!Array.isArray(body)&&!Object.hasOwn(body,key),'Invalid paired original identity.');
  return {...body,[key]:row.original_id};
}

function sourceBinding(b) {
  require(fields(b,['schema_version','protocol_id','commit','files','law_sha256','model_versions','producer_versions','verification','binding_id'])&&b.schema_version===schema('source-binding')&&b.protocol_id===PAIRED_RESEARCH_PROTOCOL&&b.verification==='VERIFIED_COMMIT'&&/^[a-f0-9]{40}$/.test(b.commit)&&fields(b.files,SOURCE_FILES)&&Object.values(b.files).every(v=>SHA.test(v))&&canonical(b.law_sha256)===canonical(LAWS)&&canonical(b.model_versions)===canonical(MODELS)&&canonical(b.producer_versions)===canonical({R0:'operational002-r0-producer-v1',K0:'operational002-k0-producer-v1'})&&b.files['multisport_lab/baseline.py']===LAWS.R0&&b.files['multisport_lab/development_003.py']===LAWS.K0&&SHA.test(b.binding_id),'Invalid exact paired source binding.');
}

function validationView(r) {
  return {schema_version:'nba-research-forecast-v1',...Object.fromEntries(['id_namespace','league','event_id','player_id','player_label','team_id','opponent_id','event_starts_at','period','extra_time_policy','model_version','trained_through','cutoff_at','history_freeze','issued_at','conditioning','categories','qualification'].map(k=>[k,r[k]])),forecast_id:r.forecast_id,model_commit:r.producer_binding.commit,model_code_sha256:LAWS[r.model_key],input_sha256:r.joint_recipe.input_sha256,joint_sha256:r.joint_recipe.joint_sha256,evidence_lane:'REAL_TIME_CAPTURED',availability_basis:'OBSERVED_INPUT_CAPTURE',input_capture_ids:[r.event_ref.record_id,r.history_ref.record_id],joint_method:'COMPLETE_LINE_EMPIRICAL',tail_policy:'FINITE_EMPIRICAL_SUPPORT_NO_SMOOTHING'};
}

function minutes(value) {
  require(fields(value,['pmf','mean','interval80','precision'])&&value.precision==='reported_source_precision_not_exact_workload'&&Array.isArray(value.pmf)&&value.pmf.length>0&&value.pmf.length<=1025,'Invalid reported-minute distribution.');
  let previous=-1,mass=0,mean=0;
  for(const atom of value.pmf){require(fields(atom,['value','probability'])&&Number.isFinite(atom.value)&&atom.value>=0&&atom.value>previous&&typeof atom.probability==='string'&&/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(atom.probability)&&Number(atom.probability)>0&&Number(atom.probability)<=1,'Invalid minute atom.');previous=atom.value;mass+=Number(atom.probability);mean+=atom.value*Number(atom.probability);}
  const q=t=>{let total=0;for(const atom of value.pmf){total+=Number(atom.probability);if(total>=t)return atom.value;}return value.pmf.at(-1).value;};
  require(Math.abs(mass-1)<=1e-12&&typeof value.mean==='string'&&/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value.mean)&&Math.abs(Number(value.mean)-mean)<=1e-10&&canonical(value.interval80)===canonical([q(.1),q(.9)]),'Minute summaries differ from complete distribution.');
}

function eventInput(row,generatedAt) {
  const r=originalPairedRecord(row);
  require(fields(r,['schema_version','protocol_id','mode','plan','history_ref','event','selection','candidates','sources','imported_at','raw_retention','event_input_id'])&&r.schema_version===schema('event')&&r.protocol_id===PAIRED_RESEARCH_PROTOCOL&&r.mode==='REAL_TIME_CAPTURED'&&reference(row.source_record,'research_inputs')&&reference(r.history_ref,'research_inputs')&&r.raw_retention==='REQUIRES_SEPARATE_ADMITTED_IMMUTABLE_RAW_EVIDENCE','Invalid public compact event input.');
  const e=r.event,p=r.plan,s=r.selection;
  require(fields(e,['id_namespace','league','event_id','event_starts_at','home_team_id','away_team_id','status','season_ending_year','season_type','event_version'])&&e.id_namespace==='espn'&&e.league==='NBA'&&e.status==='PRE_GAME'&&e.season_type==='2'&&Number.isInteger(e.season_ending_year)&&e.season_ending_year>=2026&&['event_id','home_team_id','away_team_id'].every(k=>/^[1-9][0-9]{0,19}$/.test(e[k]))&&e.home_team_id!==e.away_team_id&&SHA.test(e.event_version),'Invalid named public event identity.');
  require(fields(p,['schema_version','protocol_id','registered_at','event','candidates','selection_rule','model_versions','producer_versions','history_record_id','history_rows','history_panel_sha256','categories','purpose','capture_minutes_before_t90','issuance_seconds_after_t90','maximum_original_latency_seconds','maximum_source_age_seconds','qualification','plan_id'])&&p.schema_version===schema('plan')&&p.protocol_id===PAIRED_RESEARCH_PROTOCOL&&canonical(p.event)===canonical(e)&&canonical(p.candidates)===canonical(r.candidates)&&p.selection_rule==='two_lowest_numeric_active_ids_per_current_event_team_v1'&&canonical(p.model_versions)===canonical(MODELS)&&canonical(p.producer_versions)===canonical({R0:'operational002-r0-producer-v1',K0:'operational002-k0-producer-v1'})&&p.history_record_id==='dfa1c4345495eb3aa6b203f2e8309c89c112b6b78a36cd3d2c603d390776b6fc'&&p.history_rows===26645&&p.history_panel_sha256==='489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c'&&canonical(p.categories)===canonical(ALL_NBA_CATEGORIES)&&p.purpose==='ONE_NAMED_GAME_OPERATIONAL_DESCRIPTIVE_NOT_ACCURACY_COMPARISON'&&canonical(p.capture_minutes_before_t90)==='[20,10]'&&canonical(p.issuance_seconds_after_t90)==='[0,300]'&&p.maximum_original_latency_seconds===120&&p.maximum_source_age_seconds===1200&&p.qualification==='UNAVAILABLE'&&SHA.test(p.plan_id),'Public input differs from registered one-event rules.');
  require(Array.isArray(r.candidates)&&r.candidates.length===4&&new Set(r.candidates.map(c=>c.player_id)).size===4&&r.candidates.every(c=>fields(c,['player_id','player_label','team_id','opponent_id'])&&/^[1-9][0-9]{0,19}$/.test(c.player_id)&&text(c.player_label)&&new Set([c.team_id,c.opponent_id]).size===2&&[c.team_id,c.opponent_id].every(t=>[e.home_team_id,e.away_team_id].includes(t)))&&[e.home_team_id,e.away_team_id].every(t=>r.candidates.filter(c=>c.team_id===t).length===2),'Invalid fixed public player cohort.');
  require(fields(s,['schema_version','declared_at','event_id','rule','players'])&&s.schema_version==='nba-pregame-selected-cohort-v1'&&s.event_id===e.event_id&&s.rule===p.selection_rule&&canonical(s.players)===canonical(r.candidates),'Public selected cohort differs.');
  const cutoff=utcMicros(e.event_starts_at)-5400000000n,opens=cutoff-1200000000n,closes=cutoff-600000000n,imported=utcMicros(r.imported_at);
  require(utcMicros(p.registered_at)<opens&&opens<=utcMicros(s.declared_at)&&utcMicros(s.declared_at)<=imported&&imported<=closes&&imported<=utcMicros(generatedAt),'Public input capture/selection completion missed its window.');
  const seen=new Set();require(Array.isArray(r.sources)&&r.sources.length===4,'Public source evidence incomplete.');
  for(const source of r.sources){require(fields(source,['source_id','source_url','request_started_at','observed_at','response_completed_at','source_updated_at','source_response_generated_at','raw_sha256','raw_bytes','http_status','http_date','etag','last_modified'])&&!seen.has(source.source_id)&&SHA.test(source.raw_sha256)&&Number.isSafeInteger(source.raw_bytes)&&source.raw_bytes>0&&source.raw_bytes<=2*1024*1024&&source.http_status===200&&typeof source.source_url==='string'&&['http_date','etag','last_modified'].every(k=>source[k]===null||typeof source[k]==='string'),'Invalid source capture metadata.');seen.add(source.source_id);const started=utcMicros(source.request_started_at),observed=utcMicros(source.observed_at),completed=utcMicros(source.response_completed_at);require(opens<=started&&started<=observed&&observed===completed&&completed<=imported&&completed-started<=30000000n&&cutoff-observed<=1200000000n&&['source_updated_at','source_response_generated_at'].every(k=>source[k]===null||utcMicros(source[k])<=observed),'Source clocks/freshness conflict.');}
  require(canonical([...seen].sort())===canonical(['scoreboard','summary',`roster-${e.home_team_id}`,`roster-${e.away_team_id}`].sort()),'Source inventory differs from named game.');
  const a=row.admission;require(fields(a,['retained','eligible','local_persistence_completed_at','remote_checkpoint_completed_at','final_recovery_completed_at','reasons'])&&a.retained===true&&a.eligible===false&&Array.isArray(a.reasons)&&a.reasons.length>0&&a.reasons.length<=16&&a.reasons.every(text),'Inactive public input admission is invalid.');
  const times=['local_persistence_completed_at','remote_checkpoint_completed_at','final_recovery_completed_at'].map(k=>a[k]===null?null:utcMicros(a[k]));require(times.every(t=>t===null||imported<=t&&t<=utcMicros(generatedAt))&&(times[1]===null||times[0]!==null&&times[0]<=times[1])&&(times[2]===null||times[1]!==null&&times[1]<=times[2]),'Input persistence clocks conflict.');
  return r;
}

function forecast(row,generatedAt) {
  const r=originalPairedRecord(row);
  require(fields(r,['schema_version','protocol_id','plan_id','mode','evidence_lane','period','extra_time_policy','id_namespace','league','model_key','model_version','producer_version','producer_binding','history_ref','event_ref','event_id','event_version','event_starts_at','player_id','player_label','team_id','opponent_id','cutoff_at','history_freeze','trained_through','conditioning','qualification','generation_started_at','generation_completed_at','verified_at','issued_at','categories','reported_minutes','joint_recipe','forecast_id'])&&r.schema_version===schema('forecast')&&r.protocol_id===PAIRED_RESEARCH_PROTOCOL&&r.mode==='REAL_TIME_CAPTURED'&&r.evidence_lane===r.mode&&Object.hasOwn(MODELS,r.model_key)&&r.model_version===MODELS[r.model_key]&&r.producer_version===`operational002-${r.model_key.toLowerCase()}-producer-v1`&&SHA.test(r.plan_id)&&SHA.test(r.event_version)&&reference(row.source_record,'forecasts')&&reference(r.event_ref,'research_inputs')&&reference(r.history_ref,'research_inputs'),'Invalid prospective paired forecast identity.');
  sourceBinding(r.producer_binding);
  const recipe=r.joint_recipe;
  require(fields(recipe,['schema_version','algorithm','history_ref','event_ref','target','support_atom_count','atom_order','joint_sha256','input_sha256','pool_history_count','player_history_count','fallback','encoding','omitted_atoms'])&&recipe.schema_version===schema('complete-joint-replay')&&recipe.algorithm===r.model_version&&canonical(recipe.history_ref)===canonical(r.history_ref)&&canonical(recipe.event_ref)===canonical(r.event_ref)&&canonical(recipe.target)===canonical({sport:'basketball',league:'NBA',id_namespace:'espn',event_id:r.event_id,player_id:r.player_id,event_start:r.event_starts_at,cutoff:r.cutoff_at})&&recipe.atom_order==='frozen_algorithm_order_no_sampling_or_truncation'&&recipe.encoding==='COMPLETE_SOURCE_BOUND_REPLAY_PLUS_ALL_ORIGINAL_MARGINALS'&&recipe.omitted_atoms===0&&Number.isSafeInteger(recipe.support_atom_count)&&recipe.support_atom_count>0&&recipe.pool_history_count===recipe.support_atom_count&&Number.isSafeInteger(recipe.player_history_count)&&recipe.player_history_count>=0&&recipe.player_history_count<=recipe.pool_history_count&&SHA.test(recipe.joint_sha256)&&SHA.test(recipe.input_sha256),'Changed or incomplete paired joint-law recipe.');
  const event={schema_version:'nba-research-event-v1',id_namespace:'espn',league:'NBA',event_id:r.event_id,starts_at:r.event_starts_at,status:'SCHEDULED',team_ids:[r.team_id,r.opponent_id],label:r.event_id,schedule_basis:'OBSERVED_CAPTURE'};
  validateResearchForecast(validationView(r),event,generatedAt);minutes(r.reported_minutes);
  const cutoff=utcMicros(r.cutoff_at),start=utcMicros(r.generation_started_at),end=utcMicros(r.generation_completed_at),verified=utcMicros(r.verified_at),issued=utcMicros(r.issued_at),published=utcMicros(generatedAt);
  require(cutoff<=start&&start<=end&&end<=verified&&verified===issued&&issued<=cutoff+300000000n&&issued-start<=120000000n,'Paired generation window violated.');
  const a=row.admission;
  require(fields(a,['retained','eligible','local_persistence_completed_at','remote_checkpoint_completed_at','final_recovery_completed_at','reasons'])&&a.retained===true&&typeof a.eligible==='boolean'&&Array.isArray(a.reasons)&&a.reasons.length<=16&&a.reasons.every(text),'Invalid paired admission.');
  const times=['local_persistence_completed_at','remote_checkpoint_completed_at','final_recovery_completed_at'].map(k=>a[k]===null?null:utcMicros(a[k]));
  require(times.every(t=>t===null||issued<=t&&t<=published)&&(times[1]===null||times[0]!==null&&times[0]<=times[1])&&(times[2]===null||times[1]!==null&&times[1]<=times[2]),'Paired persistence completion clocks conflict.');
  require(a.eligible?times.every(t=>t!==null)&&times[2]<=cutoff+300000000n&&times[2]-start<=120000000n&&a.reasons.length===0:a.reasons.length>0,'Paired original lacks timely independent durable recovery.');
  return r;
}

function rawOutcomeEvidence(r) {
  const value=r.raw_evidence_ref;
  require(fields(value,['reference','metadata']),'Outcome lacks structured retained raw evidence.');
  const ref=value.reference,m=value.metadata;
  require(fields(ref,['schema_version','capture_id','manifest_payload_sha256','cipher_sha256','cipher_bytes','raw_sha256','raw_bytes','recipient_certificate_sha256'])&&ref.schema_version==='nba-op002-encrypted-raw-reference-v1'&&['capture_id','manifest_payload_sha256','cipher_sha256','raw_sha256','recipient_certificate_sha256'].every(k=>SHA.test(ref[k])),'Invalid encrypted outcome raw reference.');
  require(fields(m,['schema_version','pilot_id','mode','event_id','source_url','request_started_at','source_observed_at','source_updated_at','imported_at','encryption_completed_at','cipher_persistence_completed_at','manifest_prepared_at','encryption','raw_sha256','raw_bytes','cipher_sha256','cipher_bytes','recipient_certificate_sha256','admission_sha256','supersedes','correction_reason','capture_id'])&&m.schema_version==='nba-op002-encrypted-raw-v1'&&m.pilot_id===PAIRED_RESEARCH_PROTOCOL&&m.mode===r.mode&&m.event_id===r.event_id&&m.source_observed_at===r.source_observed_at&&m.source_updated_at===r.source_updated_at&&m.raw_sha256===r.source_raw_sha256&&['capture_id','raw_sha256','raw_bytes','cipher_sha256','cipher_bytes','recipient_certificate_sha256'].every(k=>m[k]===ref[k])&&m.encryption==='openssl-cms-authenveloped-aes256gcm-rsaoaep-sha256-v1'&&SHA.test(m.admission_sha256)&&Number.isSafeInteger(m.raw_bytes)&&Number.isSafeInteger(m.cipher_bytes)&&m.raw_bytes>0&&m.raw_bytes<m.cipher_bytes&&m.cipher_bytes<=8*1024*1024&&m.cipher_bytes-m.raw_bytes<=16*1024,'Outcome differs from retained encrypted capture metadata.');
  const times=['request_started_at','source_observed_at','imported_at','encryption_completed_at','cipher_persistence_completed_at','manifest_prepared_at'].map(k=>utcMicros(m[k]));
  require(times.every((t,i)=>i===0||times[i-1]<=t)&&times.at(-1)<=utcMicros(r.normalized_at)&&(m.source_updated_at===null||utcMicros(m.source_updated_at)<=times[1]),'Raw capture/encryption/persistence clocks conflict.');
  require(m.source_url===`https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=${r.event_id}`&&(m.supersedes===null?m.correction_reason===null:text(m.correction_reason)),'Outcome raw route/correction differs.');
}

function outcome(row,generatedAt) {
  const r=originalPairedRecord(row);
  require(fields(r,['schema_version','protocol_id','mode','event_id','event_version','event_starts_at','player_id','team_id','opponent_id','status','source_observed_at','source_updated_at','normalized_at','source_raw_sha256','raw_evidence_ref','normalizer_version','primitives','minutes','minutes_precision','categories','outcome_id'])&&r.schema_version===schema('outcome')&&r.protocol_id===PAIRED_RESEARCH_PROTOCOL&&r.mode==='REAL_TIME_CAPTURED'&&['APPEARED','DNP','MISSING','POSTPONED','NONFINAL','UNRESOLVED'].includes(r.status)&&['event_id','player_id','team_id','opponent_id','normalizer_version'].every(k=>text(r[k]))&&r.team_id!==r.opponent_id&&SHA.test(r.event_version)&&SHA.test(r.source_raw_sha256)&&reference(row.source_record,'outcomes')&&row.admission===null,'Invalid paired verified outcome.');
  const observed=utcMicros(r.source_observed_at),normalized=utcMicros(r.normalized_at);
  rawOutcomeEvidence(r);
  require(observed<=normalized&&normalized<=utcMicros(generatedAt)&&(r.source_updated_at===null||utcMicros(r.source_updated_at)<=observed),'Outcome source/import clocks conflict.');
  if(['APPEARED','DNP'].includes(r.status))require(observed>=utcMicros(r.event_starts_at),'Final evidence precedes game.');
  if(r.status==='APPEARED'){
    const p=r.primitives;require(fields(p,['FGM','FG2M','FG3M','FTM','PTS','REB','AST','TOV','BLK','STL'])&&Object.values(p).every(n=>Number.isSafeInteger(n)&&n>=0)&&p.FGM===p.FG2M+p.FG3M&&p.PTS===2*p.FG2M+3*p.FG3M+p.FTM,'Contradictory outcome counts.');
    require(Number.isFinite(r.minutes)&&r.minutes>=0&&['seconds','rounded_whole_minutes'].includes(r.minutes_precision)&&(r.minutes>0||r.minutes_precision==='rounded_whole_minutes')&&(r.minutes_precision!=='rounded_whole_minutes'||Number.isInteger(r.minutes)),'Invalid appearance/minute precision.');
    const values={PTS:p.PTS,PRA:p.PTS+p.REB+p.AST,REB:p.REB,'3PM':p.FG3M,AST:p.AST,RA:p.REB+p.AST,PR:p.PTS+p.REB,TOV:p.TOV,TD:Number([p.PTS,p.REB,p.AST,p.BLK,p.STL].filter(n=>n>=10).length>=3),DD:Number([p.PTS,p.REB,p.AST,p.BLK,p.STL].filter(n=>n>=10).length>=2),BLK:p.BLK,STL:p.STL,'BLK+STL':p.BLK+p.STL,PA:p.PTS+p.AST};
    require(Array.isArray(r.categories)&&r.categories.length===14&&new Set(r.categories.map(c=>c.code)).size===14&&r.categories.every(c=>fields(c,['code','units','observed'])&&ALL_NBA_CATEGORIES.includes(c.code)&&c.units===NBA_UNITS[c.code]&&c.observed===values[c.code]),'Outcome categories are not coherent.');
  } else require(r.primitives===null&&r.minutes===null&&r.minutes_precision===null&&Array.isArray(r.categories)&&r.categories.length===0,'DNP/pending cannot become a zero outcome.');
  return r;
}

function grade(row,forecasts,outcomes,generatedAt) {
  const r=originalPairedRecord(row),f=forecasts.get(r.forecast_id),o=outcomes.get(r.outcome_id);
  require(fields(r,['schema_version','protocol_id','mode','event_id','event_version','event_starts_at','player_id','team_id','opponent_id','model_key','forecast_id','outcome_id','graded_at','status','categories','financial_settlement','qualification','grade_id'])&&r.schema_version===schema('grade')&&r.protocol_id===PAIRED_RESEARCH_PROTOCOL&&r.mode==='REAL_TIME_CAPTURED'&&f&&o&&reference(row.source_record,'grades')&&row.admission===null&&r.financial_settlement==='NOT_EVALUATED'&&r.qualification==='UNAVAILABLE'&&['event_id','event_version','event_starts_at','player_id','team_id','opponent_id','model_key'].every(k=>r[k]===f[k])&&['event_id','event_version','event_starts_at','player_id','team_id','opponent_id'].every(k=>r[k]===o[k]),'Paired grade identity differs from originals.');
  const status=o.status==='APPEARED'?'SCORED':o.status==='DNP'?'DNP_NOT_SCORED':o.status;
  require(r.status===status&&utcMicros(o.normalized_at)<=utcMicros(r.graded_at),'Grade status or clock conflicts with verified outcome.');
  const vf=validationView(f),vg={schema_version:'nba-forecast-grade-v1',grade_id:r.grade_id,forecast_id:f.forecast_id,outcome_id:o.outcome_id,id_namespace:'espn',league:'NBA',event_id:r.event_id,player_id:r.player_id,graded_at:r.graded_at,status:['SCORED','DNP_NOT_SCORED'].includes(r.status)?r.status:'UNRESOLVED',evidence_lane:'REAL_TIME_CAPTURED',categories:r.categories,financial_settlement:'NOT_EVALUATED'};
  validateResearchGrade(vg,vf,generatedAt);
  if(r.status==='SCORED')require(r.categories.every(c=>o.categories.some(value=>value.code===c.code&&value.observed===c.observed)),'Grade observations differ from shared verified outcome.');
  return r;
}

export function activePairedGrades(asset) {
  const superseded=new Set(asset.corrections.filter(c=>c.kind==='grade').map(c=>c.original_id));
  const outcomes=new Set(asset.corrections.filter(c=>c.kind==='outcome').map(c=>c.original_id));
  return asset.grades.filter(row=>!superseded.has(row.original_id)&&!outcomes.has(originalPairedRecord(row).outcome_id));
}

export function validatePairedResearchDescriptor(d,publishedAt) {
  require(fields(d,['path','sha256','generated_at','status','retained','error'])&&SHA.test(d.sha256)&&d.path===`paired-research.${d.sha256}.json`&&d.status==='RESEARCH_ONLY'&&typeof d.retained==='boolean'&&(d.error===null||text(d.error))&&utcMicros(d.generated_at)<=utcMicros(publishedAt),'Unsafe paired research descriptor.');
  return d;
}

export function validatePairedResearchAsset(asset,publishedAt) {
  require(fields(asset,['schema_version','protocol_id','generated_at','status','reason','counts','clocks','inputs','forecasts','outcomes','grades','corrections','missing_peers','qualification','financial_settlement','asset_id'])&&asset.schema_version==='nba-operational-paired-publication-v1'&&asset.protocol_id===PAIRED_RESEARCH_PROTOCOL&&['INACTIVE','ISSUED','PARTIAL','COMPLETED'].includes(asset.status)&&text(asset.reason)&&asset.qualification==='UNAVAILABLE'&&asset.financial_settlement==='NOT_EVALUATED'&&SHA.test(asset.asset_id)&&utcMicros(asset.generated_at)<=utcMicros(publishedAt),'Invalid paired research asset.');
  require(fields(asset.counts,['forecasts','eligible_forecasts','outcomes','grades','pending_grades','missing_peers'])&&Object.values(asset.counts).every(n=>Number.isSafeInteger(n)&&n>=0)&&fields(asset.clocks,['last_source_capture_at','last_issuance_at','last_grade_at'])&&Object.values(asset.clocks).every(v=>v===null||utcMicros(v)<=utcMicros(asset.generated_at)),'Invalid paired counts or evidence clocks.');
  const forecasts=new Map(),outcomes=new Map(),grades=new Map(),subjects=new Set(),inputs=new Map(),observations=[];
  require(Array.isArray(asset.inputs)&&asset.inputs.length<=1,'Invalid compact input publication count.');
  for(const row of asset.inputs){const r=eventInput(row,asset.generated_at);inputs.set(canonical(row.source_record),r);observations.push(...r.sources.map(s=>s.observed_at));}
  for(const [key,limit] of [['forecasts',8],['outcomes',32],['grades',32]])require(Array.isArray(asset[key])&&asset[key].length<=limit,'Paired publication budget exceeded.');
  for(const row of asset.forecasts){const r=forecast(row,asset.generated_at),subject=`${r.event_id}:${r.player_id}:${r.model_key}`,input=inputs.get(canonical(r.event_ref));require(input&&r.plan_id===input.plan.plan_id&&r.mode===input.mode&&canonical(r.history_ref)===canonical(input.history_ref)&&['event_id','event_version','event_starts_at'].every(k=>r[k]===input.event[k])&&input.candidates.some(c=>['player_id','player_label','team_id','opponent_id'].every(k=>r[k]===c[k])),'Forecast differs from exact public compact input.');require(!forecasts.has(r.forecast_id)&&!subjects.has(subject),'Duplicate original paired model/subject.');forecasts.set(r.forecast_id,r);subjects.add(subject);}
  for(const row of asset.outcomes){const r=outcome(row,asset.generated_at);require(!outcomes.has(r.outcome_id),'Duplicate paired outcome.');outcomes.set(r.outcome_id,r);}
  for(const row of asset.grades){const r=grade(row,forecasts,outcomes,asset.generated_at);require(!grades.has(r.grade_id),'Duplicate paired grade.');grades.set(r.grade_id,r);}
  for(const o of outcomes.values())require([...forecasts.values()].some(f=>['event_id','event_version','event_starts_at','player_id','team_id','opponent_id','mode'].every(k=>o[k]===f[k])&&utcMicros(f.issued_at)<=utcMicros(o.source_observed_at)),'Unlinked public outcome differs from every original.');
  require(!asset.forecasts.some(row=>row.admission.eligible),'OP002 readiness has no installed reviewed activation; eligibility is unavailable.');
  const identities=new Set([...forecasts.values()].map(r=>canonical([r.event_id,r.event_version,r.event_starts_at,r.plan_id,r.producer_binding,r.event_ref])));
  require(identities.size<=1,'Paired forecasts use different fixed inputs/source.');
  require(Array.isArray(asset.corrections)&&asset.corrections.length<=16,'Too many paired corrections.');
  const graph=new Map();
  for(const c of asset.corrections){require(fields(c,['kind','original_id','replacement_id','reason','source_record'])&&['outcome','grade'].includes(c.kind)&&SHA.test(c.original_id)&&SHA.test(c.replacement_id)&&c.original_id!==c.replacement_id&&text(c.reason)&&reference(c.source_record,'corrections')&&!graph.has(c.original_id),'Invalid paired correction link.');const index=c.kind==='grade'?grades:outcomes,before=index.get(c.original_id),after=index.get(c.replacement_id);require(before&&after&&['protocol_id','event_id','event_version','event_starts_at','player_id','team_id','opponent_id','mode',...(c.kind==='grade'?['model_key','forecast_id']:[])].every(k=>before[k]===after[k]),'Correction changes original subject/lane.');graph.set(c.original_id,c.replacement_id);}
  for(const start of graph.keys()){let cursor=start;const seen=new Set();while(graph.has(cursor)){require(!seen.has(cursor),'Paired correction cycle.');seen.add(cursor);cursor=graph.get(cursor);}}
  const active=activePairedGrades(asset),activeForecasts=new Set(),complete=new Set();
  for(const row of active){const r=grades.get(row.original_id);require(!activeForecasts.has(r.forecast_id)&&!graph.has(r.outcome_id),'Conflicting active grade or superseded outcome.');activeForecasts.add(r.forecast_id);if(['SCORED','DNP_NOT_SCORED'].includes(r.status))complete.add(r.forecast_id);}
  require(Array.isArray(asset.missing_peers)&&asset.missing_peers.length<=8,'Invalid missing peer inventory.');
  const missing=new Set();for(const p of asset.missing_peers){require(fields(p,['player_id','model_key'])&&text(p.player_id)&&Object.hasOwn(MODELS,p.model_key)&&!missing.has(`${p.player_id}:${p.model_key}`)&&![...forecasts.values()].some(r=>r.player_id===p.player_id&&r.model_key===p.model_key),'Duplicate or retained peer claimed missing.');missing.add(`${p.player_id}:${p.model_key}`);}
  const registered=new Set([...inputs.values()].flatMap(input=>input.candidates.flatMap(candidate=>Object.keys(MODELS).map(model=>`${candidate.player_id}:${model}`))));
  const retained=new Set([...forecasts.values()].map(r=>`${r.player_id}:${r.model_key}`));
  const expectedMissing=[...registered].filter(key=>!retained.has(key)).sort();
  require(canonical([...missing].sort())===canonical(expectedMissing),'Public missing peers differ from exact fixed input cohort minus retained originals.');
  const expected={forecasts:forecasts.size,eligible_forecasts:asset.forecasts.filter(r=>r.admission.eligible).length,outcomes:outcomes.size,grades:grades.size,pending_grades:forecasts.size-complete.size,missing_peers:missing.size};
  require(canonical(expected)===canonical(asset.counts),'Paired counts differ from originals.');
  const latest=values=>values.length?[...values].sort().at(-1):null;
  require(canonical(asset.clocks)===canonical({last_source_capture_at:latest(observations),last_issuance_at:latest([...forecasts.values()].map(r=>r.issued_at)),last_grade_at:latest([...grades.values()].map(r=>r.graded_at))}),'Public summary clocks differ from retained originals.');
  const status=!forecasts.size?'INACTIVE':forecasts.size<8||expected.eligible_forecasts<8?'PARTIAL':expected.pending_grades?'ISSUED':'COMPLETED';
  require(asset.status===status&&bytes(canonical(asset)).length<=PAIRED_RESEARCH_MAX_BYTES,'Paired state or encoded asset limit is invalid.');
  return asset;
}

async function hash(raw,provider) {
  require(provider?.subtle,'Paired original integrity requires a secure context.');
  return [...new Uint8Array(await provider.subtle.digest('SHA-256',bytes(raw)))].map(v=>v.toString(16).padStart(2,'0')).join('');
}

export async function verifyPairedResearchHashes(asset,provider=globalThis.crypto) {
  const {asset_id,...unsigned}=asset;require(await hash(canonical(unsigned),provider)===asset_id,'Paired asset checksum mismatch.');
  for(const row of [...asset.inputs,...asset.forecasts,...asset.outcomes,...asset.grades]){
    require(await hash(row.record_json,provider)===row.original_id,'Paired original source checksum mismatch.');
    if(row.kind==='forecast'){const binding=originalPairedRecord(row).producer_binding,{binding_id,...unsignedBinding}=binding;require(await hash(canonical(unsignedBinding),provider)===binding_id,'Paired source binding checksum mismatch.');}
    if(row.kind==='event'){const r=originalPairedRecord(row),{plan_id,...p}=r.plan,{event_version,...e}=r.event;require(await hash(canonical(p),provider)===plan_id&&await hash(canonical(e),provider)===event_version,'Public compact plan/event checksum mismatch.');}
    if(row.kind==='outcome'){const {reference:ref,metadata:m}=originalPairedRecord(row).raw_evidence_ref;require(await hash(canonical(m),provider)===ref.manifest_payload_sha256,'Raw outcome manifest checksum mismatch.');const excluded=new Set(['capture_id','imported_at','encryption_completed_at','cipher_persistence_completed_at','manifest_prepared_at','encryption','cipher_sha256','cipher_bytes']);require(await hash(canonical(Object.fromEntries(Object.entries(m).filter(([k])=>!excluded.has(k)))),provider)===m.capture_id,'Raw capture identity checksum mismatch.');}
  }
  return asset;
}

export function pairedResearchRows(asset) {
  return asset.forecasts.map(row=>({row,forecast:originalPairedRecord(row),grade:activePairedGrades(asset).find(candidate=>originalPairedRecord(candidate).forecast_id===row.original_id)||null}));
}

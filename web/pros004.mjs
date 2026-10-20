// Versioned PROS004 public records. No activation, reserved aggregate or ticket admission.
import {ALL_NBA_CATEGORIES, validateResearchForecast, validateResearchGrade, utcMicros} from './research.mjs';
export const PROS004_STUDY = 'NBA-ALL13-JOINT-PROS-004';
export const PROS004_PAGE_SIZE = 4;
export const PROS004_MAX_BYTES = 512 * 1024;
export const PROS004_MAX_TOTAL = 24 * 1024 * 1024;
const SHA = /^[a-f0-9]{64}$/;
const MODELS = {R0: 'nba_joint_empirical_r0_v1', K0: 'nba_joint_lagged_workload_prior_k0_v1'};
const SOURCE_FILES = ['pros004_producer','pros004_inputs','pros004_records','baseline','development_003','development_002','research_pilot','nba_data','basketball','integrity','ledger','forecast_contract','pregame_sources'].map(name=>`multisport_lab/${name}.py`);
const LAWS = {R0: '2a217b021ae25041920d14db6fbb1a14197ef4593b2b59965bbdef6f01304689', K0: '282bb23a570bc6aaa217ab7f65ba223613c805801d8c479bc51aef0291b72be7'};
const fields = (o, keys) => o && typeof o === 'object' && !Array.isArray(o) && Object.keys(o).sort().join(',') === [...keys].sort().join(',');
const text = v => typeof v === 'string' && v.length > 0 && v.length <= 2048 && v.trim() === v;
const require = (ok, message) => {if (!ok) throw new Error(message);};
export const canonicalPros004 = v => v && typeof v === 'object' ? Array.isArray(v) ? `[${v.map(canonicalPros004).join(',')}]` : `{${Object.keys(v).sort().map(k => `${JSON.stringify(k)}:${canonicalPros004(v[k])}`).join(',')}}` : JSON.stringify(v);
const bytes = value => new TextEncoder().encode(value);
export async function pros004Hash(value, provider = globalThis.crypto) {
  require(provider?.subtle, 'PROS004 integrity requires a secure browser context.');
  return [...new Uint8Array(await provider.subtle.digest('SHA-256', typeof value === 'string' ? bytes(value) : value))].map(v => v.toString(16).padStart(2, '0')).join('');
}
async function seal(value, key, crypto) {
  const {[key]: id, ...unsigned} = value;
  require(SHA.test(id) && await pros004Hash(canonicalPros004(unsigned), crypto) === id, 'PROS004 content checksum mismatch.');
}
const ref = (r, kind) => fields(r, ['kind', 'record_id', 'payload_sha256']) && r.kind === kind && SHA.test(r.record_id) && SHA.test(r.payload_sha256);
export function validatePros004Descriptor(d, publishedAt) {
  require(fields(d, ['path', 'sha256', 'generated_at', 'status', 'retained', 'error']) && SHA.test(d.sha256) && d.path === `pros004.index.${d.sha256}.json` && d.status === 'RESEARCH_ONLY' && typeof d.retained === 'boolean' && (d.error === null || text(d.error)), 'Unsafe PROS004 descriptor.');
  require(utcMicros(d.generated_at) <= utcMicros(publishedAt), 'PROS004 generation exceeds publication.');
  return d;
}
export async function validatePros004Index(index, descriptor, crypto) {
  require(fields(index, ['schema_version','study_id','league','generated_at','status','activation','qualification','financial_settlement','categories','page_size','totals','excluded','grade_visibility','aggregate_evaluation','future_availability','pages','index_id']), 'Invalid PROS004 public index.');
  await seal(index, 'index_id', crypto);
  require(index.schema_version === 'nba-pros004-public-index-v1' && index.study_id === PROS004_STUDY && index.league === 'NBA' && index.generated_at === descriptor.generated_at && index.status === 'RESEARCH_ONLY' && index.activation === 'INACTIVE' && index.qualification === 'UNAVAILABLE' && index.financial_settlement === 'NOT_EVALUATED' && canonicalPros004(index.categories) === canonicalPros004(ALL_NBA_CATEGORIES) && index.page_size === PROS004_PAGE_SIZE, 'Unsupported PROS004 index meaning.');
  require(fields(index.totals,['forecasts','grades']) && Object.values(index.totals).every(n => Number.isSafeInteger(n) && n >= 0 && n <= 168), 'Invalid complete PROS004 totals.');
  require(fields(index.excluded,['diagnostic_forecasts','diagnostic_grades','superseded_grades']) && Object.values(index.excluded).every(n => Number.isSafeInteger(n) && n >= 0) && index.grade_visibility === 'LATEST_ACTIVE_WITH_SOURCE_LEDGER_REFERENCES_SUPERSEDED_COUNTED', 'Invalid PROS004 exclusions.');
  require(fields(index.aggregate_evaluation,['status','not_before']) && index.aggregate_evaluation.status === 'NOT_RUN' && index.aggregate_evaluation.not_before === '2026-11-25T00:00:00.000000Z', 'Reserved PROS004 comparative evaluation is not published.');
  require(fields(index.future_availability,['status','reasons']) && index.future_availability.status === 'UNAVAILABLE' && Array.isArray(index.future_availability.reasons) && index.future_availability.reasons.length > 0 && index.future_availability.reasons.every(text), 'Inactive PROS004 needs specific unavailable reasons.');
  require(Array.isArray(index.pages) && index.pages.length <= 84, 'PROS004 page budget exceeded.');
  const counts = {forecasts:0,grades:0}, nums = {forecasts:0,grades:0}; let size = bytes(canonicalPros004(index)).length;
  for (const p of index.pages) {
    require(fields(p,['kind','page_number','path','sha256','encoded_bytes','records']) && Object.hasOwn(counts,p.kind) && Number.isSafeInteger(p.page_number) && p.page_number === nums[p.kind] && SHA.test(p.sha256) && p.path === `pros004.${p.kind}.${p.sha256}.json` && Number.isSafeInteger(p.encoded_bytes) && p.encoded_bytes > 0 && p.encoded_bytes <= PROS004_MAX_BYTES && Number.isSafeInteger(p.records) && p.records > 0 && p.records <= PROS004_PAGE_SIZE, 'Invalid PROS004 page sequence or path.');
    counts[p.kind] += p.records; nums[p.kind]++; size += p.encoded_bytes;
  }
  require(canonicalPros004(counts) === canonicalPros004(index.totals) && size <= PROS004_MAX_TOTAL, 'PROS004 pages omit records or exceed total budget.');
  return index;
}
export function validatePros004Page(page, reference, index) {
  require(fields(page,['schema_version','study_id','league','kind','page_number','page_size','total_records','generated_at','records']) && page.schema_version === 'nba-pros004-public-page-v1' && page.study_id === PROS004_STUDY && page.league === 'NBA' && page.kind === reference.kind && page.page_number === reference.page_number && page.page_size === PROS004_PAGE_SIZE && page.total_records === index.totals[page.kind] && page.generated_at === index.generated_at && Array.isArray(page.records) && page.records.length === reference.records, 'PROS004 page inventory mismatch.');
  return page;
}
// JSON.parse alone permits duplicate keys. This bounded structural pass rejects
// ambiguity without rewriting numeric lexemes before the source-byte hash check.
function unambiguousJson(raw) {
  require(typeof raw==='string' && bytes(raw).length<=96*1024,'Original JSON exceeds its bounded contract.');
  let at=0;const whitespace=()=>{while(/\s/.test(raw[at]||'')&&at<raw.length)at++;};
  const string=()=>{const start=at++;while(at<raw.length){const c=raw[at++];if(c==='\\'){at++;continue;}if(c==='"')return JSON.parse(raw.slice(start,at));}throw new Error('Unterminated original JSON string.');};
  const value=depth=>{require(depth<=64,'Original JSON nesting exceeds its bound.');whitespace();const c=raw[at];
    if(c==='"'){string();return;}
    if(c==='{'){at++;whitespace();const keys=new Set();if(raw[at]==='}'){at++;return;}while(at<raw.length){require(raw[at]==='"','Invalid original object key.');const key=string();require(!keys.has(key),'Duplicate original JSON key.');keys.add(key);whitespace();require(raw[at++]===':','Invalid original object separator.');value(depth+1);whitespace();if(raw[at]==='}'){at++;return;}require(raw[at++]===',','Invalid original object delimiter.');whitespace();}throw new Error('Unterminated original object.');}
    if(c==='['){at++;whitespace();if(raw[at]===']'){at++;return;}while(at<raw.length){value(depth+1);whitespace();if(raw[at]===']'){at++;return;}require(raw[at++]===',','Invalid original array delimiter.');}throw new Error('Unterminated original array.');}
    const token=/^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(raw.slice(at));require(token,'Invalid original JSON token.');at+=token[0].length;
  };
  value(0);whitespace();require(at===raw.length,'Trailing original JSON data.');return JSON.parse(raw);
}
/** Exact unsigned source text retains Python numeric spelling, including 0.0. */
export function pros004Original(row) {
  require(row.record_encoding === 'CANONICAL_ORIGINAL_BODY_WITHOUT_ID' && typeof row.record_json === 'string' && SHA.test(row.original_id), 'Invalid PROS004 original encoding.');
  const record = unambiguousJson(row.record_json), key = row.schema_version === 'nba-pros004-public-forecast-v1' ? 'forecast_id' : 'grade_id';
  require(record && typeof record === 'object' && !Array.isArray(record) && !Object.hasOwn(record,key), 'Invalid PROS004 original body.');
  return {...record,[key]:row.original_id};
}
function validationView(record) {
  return {schema_version:'nba-research-forecast-v1', ...Object.fromEntries(['id_namespace','league','event_id','player_id','player_label','team_id','opponent_id','event_starts_at','model_version','trained_through','cutoff_at','history_freeze','issued_at','conditioning','categories','qualification'].map(k=>[k,record[k]])), forecast_id:record.forecast_id, period:'full_game',extra_time_policy:'includes_overtime',model_commit:record.producer_binding.model_commit,model_code_sha256:record.producer_binding.law_sha256[record.model_key],input_sha256:record.joint_recipe.input_sha256,evidence_lane:'REAL_TIME_CAPTURED',availability_basis:'OBSERVED_INPUT_CAPTURE',input_capture_ids:[record.event_ref.record_id,record.history_ref.record_id],joint_method:'COMPLETE_LINE_EMPIRICAL',joint_sha256:record.joint_recipe.joint_sha256,tail_policy:'FINITE_EMPIRICAL_SUPPORT_NO_SMOOTHING'};
}
function minutePmf(distribution) {
  require(fields(distribution,['pmf','mean','interval80','precision']) && distribution.precision === 'reported_source_precision_not_exact_workload' && Array.isArray(distribution.pmf) && distribution.pmf.length > 0 && distribution.pmf.length <= 1025, 'Invalid PROS004 workload PMF.');
  let previous=-1,mass=0,mean=0; const q=t=>{let c=0;for(const p of distribution.pmf){c+=Number(p.probability);if(c>=t)return p.value;}return distribution.pmf.at(-1).value;};
  for(const p of distribution.pmf){require(fields(p,['value','probability']) && Number.isFinite(p.value) && p.value>=0 && p.value>previous && typeof p.probability==='string' && /^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(p.probability) && Number(p.probability)>0 && Number(p.probability)<=1,'Invalid complete workload atom.');previous=p.value;mass+=Number(p.probability);mean+=p.value*Number(p.probability);}
  require(Math.abs(mass-1)<=1e-12 && typeof distribution.mean==='string' && Math.abs(Number(distribution.mean)-mean)<=1e-10 && canonicalPros004(distribution.interval80)===canonicalPros004([q(.1),q(.9)]),'Workload summary differs from PMF.');
}
async function originalSeal(row, crypto) {
  await seal(row,'projection_id',crypto);
  require(await pros004Hash(row.record_json,crypto)===row.original_id,'PROS004 original source checksum mismatch.');
}
export function validatePros004AdmissionContext(row,index) {
  require(!(index.activation==='INACTIVE'&&row.admission.eligible_for_comparison),'Inactive PROS004 collection cannot admit comparison eligibility.');
  return row;
}
export async function validatePros004Forecast(row, generatedAt, crypto) {
  require(fields(row,['schema_version','study_id','evidence_lane','source_record','record_encoding','record_json','original_id','admission','projection_id']) && row.schema_version==='nba-pros004-public-forecast-v1' && row.study_id===PROS004_STUDY && row.evidence_lane==='REAL_TIME_CAPTURED' && ref(row.source_record,'forecasts'),'Invalid PROS004 forecast projection.');
  await originalSeal(row,crypto); const r=pros004Original(row);
  require(fields(r,['schema_version','study_id','mode','id_namespace','league','model_key','model_version','producer_version','producer_binding','history_ref','event_ref','event_id','event_version','event_starts_at','player_id','player_label','team_id','opponent_id','cutoff_at','history_freeze','trained_through','conditioning','qualification','generation_started_at','generation_completed_at','verified_at','issued_at','categories','reported_minutes','joint_recipe','forecast_id']) && r.schema_version==='nba-pros004-forecast-v1' && r.study_id===PROS004_STUDY && r.mode==='REAL_TIME_CAPTURED' && Object.hasOwn(MODELS,r.model_key) && r.model_version===MODELS[r.model_key] && [1,2,3].some(v=>r.producer_version===`pros004-${r.model_key.toLowerCase()}-producer-v${v}`) && SHA.test(r.event_version),'Invalid original PROS004 model or identity.');
  const b=r.producer_binding;
  require(fields(b,['schema_version','model_commit','verification','source_sha256','law_sha256','runtime']) && ['nba-pros004-source-binding-v1','nba-pros004-source-binding-v2','nba-pros004-source-binding-v3'].includes(b.schema_version) && b.verification==='VERIFIED_COMMIT' && /^[a-f0-9]{40}$/.test(b.model_commit) && canonicalPros004(b.law_sha256)===canonicalPros004(LAWS) && fields(b.source_sha256,[...SOURCE_FILES,...(b.schema_version!=='nba-pros004-source-binding-v1'?[...['pros004_completion','pros004_activation','pros004_remote','pros004_raw','pros004_snapshot'].map(name=>`multisport_lab/${name}.py`),'scripts/verify_pros004_readiness.py']:[])]) && Object.values(b.source_sha256).every(x=>SHA.test(x)) && b.schema_version===`nba-pros004-source-binding-${r.producer_version.split('-').at(-1)}` && b.source_sha256['multisport_lab/baseline.py']===LAWS.R0 && b.source_sha256['multisport_lab/development_003.py']===LAWS.K0 && fields(b.runtime,['python','implementation','libc','machine','float_mantissa_bits']) && ['python','implementation','machine'].every(k=>text(b.runtime[k])) && Array.isArray(b.runtime.libc) && b.runtime.libc.length===2 && b.runtime.libc.every(v=>typeof v==='string') && Number.isSafeInteger(b.runtime.float_mantissa_bits) && b.runtime.float_mantissa_bits>0,'Invalid PROS004 frozen source binding.');
  require(ref(r.history_ref,'research_inputs') && ref(r.event_ref,'research_inputs'),'Invalid shared PROS004 inputs.');
  const recipe=r.joint_recipe;
  require(fields(recipe,['schema_version','algorithm','history_ref','event_ref','target','support_atom_count','atom_order','joint_sha256','input_sha256','pool_history_count','player_history_count','fallback','encoding','omitted_atoms']) && recipe.schema_version==='nba-pros004-complete-joint-replay-v1' && recipe.algorithm===r.model_version && canonicalPros004(recipe.target)===canonicalPros004({sport:'basketball',league:'NBA',id_namespace:'espn',event_id:r.event_id,player_id:r.player_id,event_start:r.event_starts_at,cutoff:r.cutoff_at}) && recipe.atom_order==='frozen_algorithm_order_no_sampling_or_truncation' && recipe.encoding==='COMPLETE_SOURCE_BOUND_REPLAY_PLUS_ALL_ORIGINAL_MARGINALS' && SHA.test(recipe.input_sha256) && canonicalPros004(recipe.history_ref)===canonicalPros004(r.history_ref) && canonicalPros004(recipe.event_ref)===canonicalPros004(r.event_ref) && recipe.omitted_atoms===0 && Number.isSafeInteger(recipe.support_atom_count) && recipe.support_atom_count>0 && recipe.pool_history_count===recipe.support_atom_count && SHA.test(recipe.joint_sha256),'Incomplete PROS004 joint-law recipe.');
  const event={schema_version:'nba-research-event-v1',id_namespace:'espn',league:'NBA',event_id:r.event_id,starts_at:r.event_starts_at,status:'SCHEDULED',team_ids:[r.team_id,r.opponent_id],label:r.event_id,schedule_basis:'OBSERVED_CAPTURE'};
  validateResearchForecast(validationView(r),event,generatedAt);minutePmf(r.reported_minutes);
  const cutoff=utcMicros(r.cutoff_at),start=utcMicros(r.generation_started_at),end=utcMicros(r.generation_completed_at),verified=utcMicros(r.verified_at),issued=utcMicros(r.issued_at),generated=utcMicros(generatedAt);
  require(cutoff<=start && start<=end && end<=verified && verified===issued && issued<=cutoff+300000000n && issued-start<=120000000n,'Invalid original PROS004 generation clocks.');
  const a=row.admission;
  require(fields(a,['retained','local_persistence_completed_at','remote_checkpoint_completed_at','eligible_for_comparison','reasons']) && a.retained===true && typeof a.eligible_for_comparison==='boolean' && Array.isArray(a.reasons) && a.reasons.length<=16 && a.reasons.every(text),'Invalid PROS004 completion proof.');
  const local=a.local_persistence_completed_at===null?null:utcMicros(a.local_persistence_completed_at),remote=a.remote_checkpoint_completed_at===null?null:utcMicros(a.remote_checkpoint_completed_at);
  require((local===null||issued<=local&&local<=generated)&&(remote===null||local!==null&&local<=remote&&remote<=generated),'Invalid PROS004 completion ordering.');
  require(a.eligible_for_comparison ? local!==null&&remote!==null&&remote<=cutoff+300000000n&&remote-start<=120000000n&&a.reasons.length===0 : a.reasons.length>0,'Unacknowledged or late originals cannot be admitted.');
  require(bytes(canonicalPros004(row)).length<=96*1024,'PROS004 original exceeds public budget.'); return row;
}
function validateMinuteGrade(g, distribution) {
  require(fields(g,['observed','observed_precision','forecast_precision','crps','absolute_mean_error','log_loss','log_loss_status','intervals']) && Number.isFinite(g.observed) && g.observed>=0 && ['seconds','rounded_whole_minutes'].includes(g.observed_precision) && (g.observed>0||g.observed_precision==='rounded_whole_minutes') && (g.observed_precision!=='rounded_whole_minutes'||Number.isInteger(g.observed)) && g.forecast_precision===distribution.precision,'Invalid observed PROS004 workload grade.');
  const dec=(v,expected)=>typeof v==='string'&&/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(v)&&Number.isFinite(Number(v))&&Math.abs(Number(v)-expected)<=1e-9;
  let absolute=0,pair=0,cumulative=0,moment=0;const pmf=distribution.pmf,mass=Number(pmf.find(p=>p.value===g.observed)?.probability||0);
  for(const p of pmf){const weight=Number(p.probability);absolute+=weight*Math.abs(p.value-g.observed);pair+=weight*(p.value*cumulative-moment);cumulative+=weight;moment+=weight*p.value;}
  require(dec(g.crps,Math.max(0,absolute-pair))&&dec(g.absolute_mean_error,Math.abs(Number(distribution.mean)-g.observed))&&(mass===0?g.log_loss===null&&g.log_loss_status==='ZERO_SUPPORT':g.log_loss_status==='FINITE'&&dec(g.log_loss,-Math.log(mass))),'Workload grade differs from original PMF.');
  require(Array.isArray(g.intervals)&&g.intervals.length===3,'Invalid workload grade intervals.');
  const q=t=>{let c=0;for(const p of pmf){c+=Number(p.probability);if(c>=t)return p.value;}return pmf.at(-1).value;};
  for(let i=0;i<3;i++){const level=[.5,.8,.95][i],a=g.intervals[i],lower=q((1-level)/2),upper=q(1-(1-level)/2),predicted=pmf.filter(p=>lower<=p.value&&p.value<=upper).reduce((n,p)=>n+Number(p.probability),0);require(fields(a,['nominal','lower','upper','covered','predicted_mass'])&&a.nominal===String(level)&&a.lower===lower&&a.upper===upper&&a.covered===(lower<=g.observed&&g.observed<=upper)&&dec(a.predicted_mass,predicted),'Workload interval grade differs from original PMF.');}
}
export async function validatePros004Grade(row, forecasts, generatedAt, crypto) {
  require(fields(row,['schema_version','study_id','evidence_lane','source_record','record_encoding','record_json','original_id','model_version','projection_id']) && row.schema_version==='nba-pros004-public-grade-v1' && row.study_id===PROS004_STUDY && row.evidence_lane==='REAL_TIME_CAPTURED' && ref(row.source_record,'grades'),'Invalid PROS004 grade projection.');
  await originalSeal(row,crypto);const g=pros004Original(row), frow=forecasts.get(g.forecast_id), f=frow&&pros004Original(frow);
  require(fields(g,['schema_version','study_id','mode','event_id','event_version','event_starts_at','player_id','team_id','opponent_id','model_key','forecast_id','outcome_id','graded_at','status','categories','reported_minutes','financial_settlement','qualification','grade_id']) && g.schema_version==='nba-pros004-grade-v1' && g.study_id===PROS004_STUDY && g.mode==='REAL_TIME_CAPTURED' && f && row.model_version===f.model_version && ['event_id','event_version','event_starts_at','player_id','team_id','opponent_id','model_key'].every(k=>g[k]===f[k]) && ['SCORED','DNP_NOT_SCORED','MISSING','POSTPONED','NONFINAL','UNRESOLVED'].includes(g.status) && g.financial_settlement==='NOT_EVALUATED' && g.qualification==='UNAVAILABLE','PROS004 grade conflicts with original identity.');
  const vf=validationView(f), vg={schema_version:'nba-forecast-grade-v1',grade_id:g.grade_id,forecast_id:f.forecast_id,outcome_id:g.outcome_id,id_namespace:'espn',league:'NBA',event_id:g.event_id,player_id:g.player_id,graded_at:g.graded_at,status:['SCORED','DNP_NOT_SCORED'].includes(g.status)?g.status:'UNRESOLVED',evidence_lane:'REAL_TIME_CAPTURED',categories:g.categories,financial_settlement:'NOT_EVALUATED'};
  validateResearchGrade(vg,vf,generatedAt);
  require((g.status==='SCORED')===(g.reported_minutes!==null),'Invalid workload grade state.');
  if(g.status==='SCORED')validateMinuteGrade(g.reported_minutes,f.reported_minutes);
  require(bytes(canonicalPros004(row)).length<=24*1024,'PROS004 grade exceeds public budget.');return row;
}
const escape = v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
/** Reserved study records never enter legacy means, builder candidates or Upcoming. */
export function renderPros004(collection,{view='upcoming',category='ALL',nbaSelected=true,limit=28,performance=false}={}) {
  if(!nbaSelected)return '';
  if(!collection)return '<section class="panel"><h2>PROS004 paired research</h2><p>Typed PROS004 records are unavailable in this publication. This does not establish a valid empty upstream source.</p></section>';
  const {index,forecasts,grades}=collection;
  const header='<section class="panel pros004-research"><div class="panel-heading"><h2>PROS004 · paired R0 / K0 research</h2><span class="pill neutral">INACTIVE · research only</span></div><p>All 13 requested NBA categories plus optional PA share each model’s coherent joint law. Qualification unavailable; financial settlement NOT_EVALUATED. This reserved study has no published comparative aggregates.</p>';
  if(!performance&&view!=='history')return header+`<h3>No upcoming PROS004 research forecasts</h3><ul class="availability-reasons">${index.future_availability.reasons.map(x=>`<li>${escape(x)}</li>`).join('')}</ul><p>${forecasts.length} retained original forecasts · ${grades.length} statistical grades. Retained unadmitted records remain visible in History.</p></section>`;
  const gradeById=new Map(grades.map(x=>[pros004Original(x).forecast_id,x]));
  let records=forecasts.flatMap(row=>{const f=pros004Original(row);return performance?[{row,f,grade:gradeById.get(f.forecast_id)}]:f.categories.filter(c=>category==='ALL'||category===c.code).map(c=>({row,f,c}));});
  const cards=records.slice(0,limit).map(({row,f,c,grade})=>{
    const g=grade&&pros004Original(grade);const title=performance?`${f.model_key} · ${f.player_label} · ${g?.status||'PENDING'}`:`${f.model_key} · ${f.player_label} · ${c.code}${c.code==='PA'?' · OPTIONAL':''}`;
    const other=f.model_key==='R0'?'K0':'R0', peer=forecasts.some(candidate=>{const r=pros004Original(candidate);return r.model_key===other&&r.player_id===f.player_id&&r.event_ref.record_id===f.event_ref.record_id&&r.history_ref.record_id===f.history_ref.record_id&&r.producer_binding.model_commit===f.producer_binding.model_commit;});
    const peerStatus=peer?`Peer retained: ${other}`:`Missing peer: ${other}; this view never generates a replacement.`;
    const status=row.admission.eligible_for_comparison?'Completion evidence recorded; study remains inactive':'Retained original · unadmitted';
    const detail=performance?(g?`<p>Statistical grade ${escape(g.status)} · Graded ${escape(g.graded_at)}.</p>${g.status==='SCORED'?`<div class="table-wrap"><table><thead><tr><th>Category</th><th>Observed</th><th>CRPS / RPS</th><th>Log loss</th></tr></thead><tbody>${g.categories.filter(x=>category==='ALL'||category===x.code).map(x=>`<tr><th>${escape(x.code)}</th><td>${x.observed}</td><td>${escape(x.crps)}</td><td>${x.log_loss_status==='ZERO_SUPPORT'?'∞ · ZERO_SUPPORT':escape(x.log_loss)}</td></tr>`).join('')}</tbody></table></div>`:'<p>No statistical score is assigned.</p>'}`:'<p>Statistical grade pending. Event start alone establishes no outcome.</p>'):`<p>Mean ${escape(c.mean)} · Central 80% ${c.interval80.join('–')} · Conditional on appearance, includes overtime.</p><details><summary>Complete ${escape(c.code)} probability mass</summary><div class="table-wrap"><table><thead><tr><th>Outcome</th><th>Probability</th></tr></thead><tbody>${c.pmf.map(a=>`<tr><th>${a.value}</th><td><code>${escape(a.probability)}</code></td></tr>`).join('')}</tbody></table></div></details>`;
    return `<article class="forecast-card" data-pros004-model="${f.model_key}" data-evidence-lane="REAL_TIME_CAPTURED"><h3>${escape(title)}</h3><p>${escape(status)}</p><p>${escape(peerStatus)}</p><ul>${row.admission.reasons.map(x=>`<li>${escape(x)}</li>`).join('')}</ul><p>Event ${escape(f.event_id)} · ${escape(f.event_starts_at)}<br>Actual issued ${escape(f.issued_at)}<br>Model ${escape(f.model_version)} · REAL_TIME_CAPTURED</p>${detail}<details><summary>Original provenance and completion</summary><dl class="forecast-provenance">${[['Original forecast',f.forecast_id],['Source forecast receipt',row.source_record.record_id],['Source forecast payload SHA-256',row.source_record.payload_sha256],['Producer commit',f.producer_binding.model_commit],['Event input receipt',f.event_ref.record_id],['Shared history receipt',f.history_ref.record_id],['T90 cutoff',f.cutoff_at],['Generation completed',f.generation_completed_at],['Verified',f.verified_at],['Local persistence completed',row.admission.local_persistence_completed_at||'Unacknowledged'],['Remote checkpoint completed',row.admission.remote_checkpoint_completed_at||'Unacknowledged'],...(g?[['Grade',g.grade_id],['Outcome',g.outcome_id],['Source grade receipt',grade.source_record.record_id],['Source grade payload SHA-256',grade.source_record.payload_sha256]]:[])].map(([k,v])=>`<div><dt>${escape(k)}</dt><dd><code>${escape(v)}</code></dd></div>`).join('')}</dl></details></article>`;
  }).join('');
  return header+`<p>${records.length} ${performance?'forecast grade states':'category distributions'} · ${Math.min(limit,records.length)} shown. ${index.excluded.superseded_grades} superseded grade receipts remain in the immutable source ledger.</p>${cards?`<div class="forecast-grid">${cards}</div>`:'<p>No original PROS004 records are published. Diagnostics are excluded; the study remains inactive.</p>'}${records.length>limit?'<button type="button" class="button dark" id="more-pros004">Show next retained research records</button>':''}<p>Individual statistical grades are separate from financial settlement. No reserved aggregate scores or model selection are computed here.</p></section>`;
}

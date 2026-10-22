// Daily publisher snapshots have their own operating policy. These records never
// inherit the fresh-input T90 protocol or establish ticket/model qualification.
import {ALL_NBA_CATEGORIES, NBA_UNITS, summarizePmf, utcMicros, validateResearchGrade} from './research.mjs';

export const DAILY_PROTOCOL = 'NBA-SDV-DAILY-001';
export const DAILY_MAX_BYTES = 1024 * 1024;
const SHA=/^[a-f0-9]{64}$/, COMMIT=/^[a-f0-9]{40}$/, ID=/^[1-9][0-9]*$/;
const MODELS={R0:'nba_joint_empirical_r0_v1',K0:'nba_joint_lagged_workload_prior_k0_v1'};
const LAWS={R0:'2a217b021ae25041920d14db6fbb1a14197ef4593b2b59965bbdef6f01304689',K0:'282bb23a570bc6aaa217ab7f65ba223613c805801d8c479bc51aef0291b72be7'};
const SOURCE_FILES=[...['sdv_daily_inputs','sdv_daily_store','sdv_daily_producer','sdv_daily_cycle','sdv_daily_runner','sdv_daily_remote','sdv_daily_outcomes','sdv_daily_publication','pros004_remote','baseline','development_003','development_002','research_pilot','pros004_producer','pros004_inputs','pregame_sources','nba_data','basketball','ledger','forecast_contract','integrity'].map(n=>`multisport_lab/${n}.py`),'config/sdv_daily_cycle_v1.json','.github/workflows/sdv-daily.yml'];
const HISTORY_ID='dfa1c4345495eb3aa6b203f2e8309c89c112b6b78a36cd3d2c603d390776b6fc';
const HISTORY_SHA='489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c';
const CYCLE_EVENT={event_id:'401909094',event_starts_at:'2026-10-23T01:30:00.000000Z',home_team_id:'25',away_team_id:'7'};
const CYCLE_CANDIDATES=[{player_id:'2991350',player_label:'Alex Caruso',team_id:'25',opponent_id:'7'},{player_id:'3133626',player_label:'Kenrich Williams',team_id:'25',opponent_id:'7'},{player_id:'3978',player_label:'DeMar DeRozan',team_id:'7',opponent_id:'25'},{player_id:'3064290',player_label:'Aaron Gordon',team_id:'7',opponent_id:'25'}];
const SELECTION='two_lowest_numeric_active_ids_per_current_event_team_v1';
const POLICY={schema_version:'nba-sdv-daily-policy-v1',protocol_id:DAILY_PROTOCOL,
  schedule_max_age_seconds:129600,roster_max_age_seconds:129600,retrieval_lookback_seconds:3600,
  issuance_open_minutes_before_start:90,issuance_window_seconds:900,maximum_original_latency_seconds:300,
  participation:'CONDITIONAL_ON_APPEARANCE',upstream_observation:'UNKNOWN_UNLESS_SUPPLIED',
  rationale:'Initial research operating policy: one documented daily publication interval (24 hours) plus 12 hours of publication-delay tolerance. Retrieve and normalize within one hour before T90; allow fifteen minutes after T90 for bounded generation and durable recovery. These are operational limits, not scientifically optimal thresholds or the original fresh-input T90 protocol.'};
const require=(ok,message)=>{if(!ok)throw new Error(message);};
const fields=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join(',')===[...keys].sort().join(',');
const text=v=>typeof v==='string'&&v.trim()===v&&v.length>0&&v.length<=2048;
const bytes=s=>new TextEncoder().encode(s);
const canonical=v=>v&&typeof v==='object'?Array.isArray(v)?`[${v.map(canonical).join(',')}]`:`{${Object.keys(v).sort().map(k=>`${JSON.stringify(k)}:${canonical(v[k])}`).join(',')}}`:JSON.stringify(v);
const equal=(a,b)=>canonical(a)===canonical(b);
const reference=(v,kind)=>fields(v,['kind','record_id','payload_sha256'])&&v.kind===kind&&SHA.test(v.record_id)&&SHA.test(v.payload_sha256);
const clock=v=>utcMicros(v), second=1000000n;
const emptyOrClock=(v,latest)=>v===null||clock(v)<=latest;
const escaped=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const datetime=v=>v===null?'Not issued':`${v.replace('T',' ').replace('.000000Z',' UTC')} <span class="sr-only">UTC</span>`;
const idKey=(f)=>`${f.event_id}:${f.player_id}:${f.model_key}`;
function decoded(encoded,limit) {
  require(typeof encoded==='string'&&encoded.length<=4*Math.ceil(limit/3)&&/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(encoded),'Invalid daily proof base64.');
  const raw=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
  require(raw.length>0&&raw.length<=limit,'Daily original proof exceeds its byte limit.');
  return {raw,json:unambiguousJson(new TextDecoder('utf-8',{fatal:true}).decode(raw))};
}
function unambiguousJson(raw) {
  let at=0;const ws=()=>{while(at<raw.length&&/\s/.test(raw[at]))at++;};
  const string=()=>{const start=at++;while(at<raw.length){const c=raw[at++];if(c==='\\'){at++;continue;}if(c==='"')return JSON.parse(raw.slice(start,at));}throw new Error('Unterminated daily proof string.');};
  const value=depth=>{require(depth<=64,'Daily proof JSON exceeds its nesting bound.');ws();const c=raw[at];if(c==='"'){string();return;}if(c==='{'){at++;ws();const seen=new Set();if(raw[at]==='}'){at++;return;}while(at<raw.length){require(raw[at]==='"','Invalid daily proof object key.');const key=string();require(!seen.has(key),'Duplicate daily proof JSON key.');seen.add(key);ws();require(raw[at++]===':','Invalid daily proof object.');value(depth+1);ws();if(raw[at]==='}'){at++;return;}require(raw[at++]===',','Invalid daily proof object.');ws();}throw new Error('Unterminated daily proof object.');}if(c==='['){at++;ws();if(raw[at]===']'){at++;return;}while(at<raw.length){value(depth+1);ws();if(raw[at]===']'){at++;return;}require(raw[at++]===',','Invalid daily proof array.');}throw new Error('Unterminated daily proof array.');}const token=/^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(raw.slice(at));require(token,'Invalid daily proof value.');at+=token[0].length;};
  value(0);ws();require(at===raw.length,'Trailing daily proof JSON bytes.');return JSON.parse(raw);
}

function policy(p) {
  require(fields(p,[...Object.keys(POLICY),'policy_id'])&&SHA.test(p.policy_id)&&Object.keys(POLICY).every(k=>equal(p[k],POLICY[k])),'Daily snapshot policy differs from the reviewed version.');
  return p;
}

function source(s,event,normalized) {
  const names=['role','publisher','release_tag','asset_name','asset_url','asset_id','asset_bytes','asset_sha256','publisher_updated_at','upstream_observed_at','upstream_observation_status','retrieval_started_at','retrieved_at','metadata_sha256','metadata_bytes'];
  require(fields(s,names)&&['schedule','roster'].includes(s.role)&&s.publisher==='SportsDataverse','Invalid daily source metadata.');
  const tag=s.role==='schedule'?'espn_nba_schedules':'espn_nba_rosters', name=(s.role==='schedule'?'nba_schedule_':'rosters_')+event.season_ending_year+'.csv';
  require(s.release_tag===tag&&s.asset_name===name&&s.asset_url===`https://github.com/sportsdataverse/sportsdataverse-data/releases/download/${tag}/${name}`,'Daily source identity or season conflict.');
  require(Number.isSafeInteger(s.asset_id)&&s.asset_id>0&&['asset_bytes','metadata_bytes'].every(k=>Number.isSafeInteger(s[k])&&s[k]>0&&s[k]<=2*1024*1024)&&SHA.test(s.asset_sha256)&&SHA.test(s.metadata_sha256),'Daily source hash or byte limit is invalid.');
  require(clock(s.publisher_updated_at)<=clock(s.retrieval_started_at)&&clock(s.retrieval_started_at)<=clock(s.retrieved_at)&&clock(s.retrieved_at)<=normalized,'Daily source clocks conflict.');
  require(s.upstream_observation_status==='UNKNOWN'&&s.upstream_observed_at===null,'The daily v1 assets have no mapped upstream observation clock; it must remain UNKNOWN/null.');
}

function candidates(rows,event) {
  require(Array.isArray(rows)&&rows.length===4,'Daily cycle requires four selected subjects.');
  const seen=new Set();
  for(const c of rows){require(fields(c,['player_id','player_label','team_id','opponent_id'])&&ID.test(c.player_id)&&text(c.player_label)&&ID.test(c.team_id)&&ID.test(c.opponent_id)&&c.team_id!==c.opponent_id&&equal([c.team_id,c.opponent_id].sort(),[event.home_team_id,event.away_team_id].sort())&&!seen.has(c.player_id),'Daily selected-player identity conflict.');seen.add(c.player_id);}
  require([event.home_team_id,event.away_team_id].every(t=>rows.filter(c=>c.team_id===t).length===2),'Daily cohort requires two players from each event team.');
}

function input(r,generated) {
  require(fields(r,['schema_version','protocol_id','mode','policy','event','candidates','sources','selection_rule','normalized_at','missing_information','qualification','input_id'])&&r.schema_version==='nba-sdv-daily-input-v1'&&r.protocol_id===DAILY_PROTOCOL&&['DEVELOPMENT_ONLY','PROSPECTIVE_RESEARCH'].includes(r.mode)&&r.selection_rule===SELECTION&&r.qualification==='UNAVAILABLE'&&SHA.test(r.input_id),'Invalid daily input contract.');
  policy(r.policy);
  const e=r.event;
  require(fields(e,['event_id','id_namespace','league','season_ending_year','season_type','home_team_id','home_team_name','away_team_id','away_team_name','event_starts_at','status','event_snapshot_id','provider_event_revision'])&&['event_id','home_team_id','away_team_id'].every(k=>ID.test(e[k]))&&text(e.home_team_name)&&text(e.away_team_name)&&e.home_team_id!==e.away_team_id&&e.id_namespace==='espn'&&e.league==='NBA'&&Number.isInteger(e.season_ending_year)&&e.season_ending_year>=2000&&e.season_ending_year<=2099&&['1','2','3'].includes(e.season_type)&&e.status==='SCHEDULED'&&e.provider_event_revision===null&&SHA.test(e.event_snapshot_id),'Invalid daily event contract.');
  const normalized=clock(r.normalized_at);
  require(normalized<=generated&&normalized<clock(e.event_starts_at),'Daily normalization is future-dated or post-start.');
  candidates(r.candidates,e);
  require(Array.isArray(r.sources)&&r.sources.length===2&&r.sources[0].role==='schedule'&&r.sources[1].role==='roster','Daily source inventory must be schedule and roster.');
  r.sources.forEach(s=>source(s,e,normalized));
  const missing=['INJURIES','STARTING_LINEUP','CONFIRMED_PARTICIPATION'];
  if(r.sources.some(s=>s.upstream_observation_status==='UNKNOWN'))missing.unshift('UPSTREAM_OBSERVATION_CLOCK');
  require(equal(r.missing_information,missing),'Daily missing information was hidden or invented.');
  return r;
}

function binding(b,mode) {
  require(fields(b,['schema_version','commit','files','law_sha256','binding_id'])&&b.schema_version==='nba-sdv-daily-producer-binding-v1'&&(COMMIT.test(b.commit)||mode==='DEVELOPMENT_ONLY'&&b.commit===null)&&SHA.test(b.binding_id)&&equal(b.law_sha256,LAWS)&&fields(b.files,SOURCE_FILES),'Invalid daily producer source binding.');
  for(const [name,sha] of Object.entries(b.files))require(SOURCE_FILES.includes(name)&&SHA.test(sha),'Invalid bound daily source file.');
  require(b.files['multisport_lab/baseline.py']===LAWS.R0&&b.files['multisport_lab/development_003.py']===LAWS.K0,'Daily producer changes the frozen mathematical laws.');
}

function distribution(r) {
  require(Array.isArray(r.categories)&&r.categories.length===ALL_NBA_CATEGORIES.length&&new Set(r.categories.map(c=>c.code)).size===ALL_NBA_CATEGORIES.length,'All fourteen daily category outputs are required.');
  for(const c of r.categories){require(fields(c,['code','units','pmf','mean','interval80'])&&ALL_NBA_CATEGORIES.includes(c.code)&&c.units===NBA_UNITS[c.code]&&Array.isArray(c.pmf)&&c.pmf.length>0&&c.pmf.length<=1025,'Invalid daily category.');let previous=-1,mass=0;
    for(const atom of c.pmf){require(fields(atom,['value','probability'])&&Number.isSafeInteger(atom.value)&&atom.value>=0&&atom.value<=1024&&atom.value>previous&&(!['TD','DD'].includes(c.code)||atom.value<=1)&&typeof atom.probability==='string'&&/^(?:0|1)(?:\.\d+)?$/.test(atom.probability)&&Number(atom.probability)>0&&Number(atom.probability)<=1,'Invalid daily probability atom.');previous=atom.value;mass+=Number(atom.probability);}
    const summary=summarizePmf(c.pmf);
    require(Math.abs(mass-1)<=1e-12&&typeof c.mean==='string'&&/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(c.mean)&&Math.abs(Number(c.mean)-summary.mean)<=1e-10&&equal(c.interval80,summary.interval80),'Daily PMF summary or mass differs.');
  }
  const means=Object.fromEntries(r.categories.map(c=>[c.code,Number(c.mean)]));
  for(const [total,parts] of [['PRA',['PTS','REB','AST']],['PR',['PTS','REB']],['RA',['REB','AST']],['PA',['PTS','AST']],['BLK+STL',['BLK','STL']]])require(Math.abs(means[total]-parts.reduce((s,k)=>s+means[k],0))<=1e-10,'Daily combination means are incoherent.');
  require(means.TD<=means.DD+1e-12&&means.PTS+1e-10>=3*means['3PM'],'Daily scoring or achievement means are incoherent.');
  const tails=['PTS','REB','AST','STL','BLK'].map(code=>r.categories.find(c=>c.code===code).pmf.filter(a=>a.value>=10).reduce((s,a)=>s+Number(a.probability),0)).sort((a,b)=>b-a);
  for(const [code,count] of [['DD',2],['TD',3]]){let lower=0,upper=1;for(let m=count;m<=5;m++)lower=Math.max(lower,(tails.slice(0,m).reduce((a,b)=>a+b,0)-(count-1))/(m-count+1));for(let j=0;j<count;j++)upper=Math.min(upper,tails.slice(j).reduce((a,b)=>a+b,0)/(count-j));require(means[code]>=lower-1e-12&&means[code]<=upper+1e-12,'Daily achievement probability conflicts with primitive thresholds.');}
  const m=r.reported_minutes;
  require(fields(m,['pmf','mean','interval80','precision'])&&m.precision==='reported_source_precision_not_exact_workload'&&Array.isArray(m.pmf)&&m.pmf.length>0&&m.pmf.length<=1025,'Invalid reported-minutes distribution.');
  let previous=-1,mass=0;
  for(const atom of m.pmf){require(fields(atom,['value','probability'])&&Number.isFinite(atom.value)&&atom.value>=0&&atom.value<=100&&atom.value>previous&&typeof atom.probability==='string'&&/^(?:0|1)(?:\.\d+)?$/.test(atom.probability)&&Number(atom.probability)>0&&Number(atom.probability)<=1,'Invalid reported-minutes atom.');previous=atom.value;mass+=Number(atom.probability);}
  const summary=summarizePmf(m.pmf);require(Math.abs(mass-1)<=1e-12&&typeof m.mean==='string'&&Number.isFinite(Number(m.mean))&&Math.abs(Number(m.mean)-summary.mean)<=1e-10&&equal(m.interval80,summary.interval80),'Reported-minutes summary differs.');
}

function forecast(row,inputs,generated) {
  require(fields(row,['reference','body','admission'])&&reference(row.reference,'forecasts'),'Invalid daily forecast reference.');
  const r=row.body,names=['schema_version','protocol_id','cycle_id','mode','evidence_lane','model_key','model_version','producer_version','producer_binding','history_ref','history_rows','history_panel_sha256','history_panel_cutoff','history_availability','input_ref','input_id','event_snapshot_id','event_id','event_starts_at','player_id','player_label','team_id','opponent_id','matchup','cutoff_at','history_freeze','trained_through','conditioning','period','extra_time_policy','qualification','generation_started_at','generation_completed_at','verified_at','issued_at','categories','reported_minutes','joint_recipe','forecast_id'];
  require(fields(r,names)&&r.schema_version==='nba-sdv-daily-forecast-v1'&&r.protocol_id===DAILY_PROTOCOL&&text(r.cycle_id)&&Object.hasOwn(MODELS,r.model_key)&&r.model_version===MODELS[r.model_key]&&r.producer_version===`sdv-daily-${r.model_key.toLowerCase()}-producer-v1`&&reference(r.history_ref,'research_inputs')&&r.history_ref.record_id===HISTORY_ID&&reference(r.input_ref,'research_inputs')&&r.history_rows===26645&&r.history_panel_sha256===HISTORY_SHA&&SHA.test(r.forecast_id)&&r.history_availability==='RECONSTRUCTED_COMPLETION_BOUND'&&r.conditioning==='CONDITIONAL_ON_APPEARANCE'&&r.period==='full_game'&&r.extra_time_policy==='includes_overtime'&&r.qualification==='UNAVAILABLE','Invalid daily forecast identity or semantics.');
  const i=inputs.get(r.input_id);require(i&&r.mode===i.mode&&r.event_snapshot_id===i.event.event_snapshot_id&&r.event_id===i.event.event_id&&r.event_starts_at===i.event.event_starts_at&&i.candidates.some(c=>['player_id','player_label','team_id','opponent_id'].every(k=>r[k]===c[k]))&&r.matchup===`${i.event.away_team_name} @ ${i.event.home_team_name}`,'Daily forecast differs from its admitted input.');
  binding(r.producer_binding,r.mode);
  const start=clock(r.event_starts_at),cutoff=start-90n*60n*second,begin=clock(r.generation_started_at),end=clock(r.generation_completed_at),verified=clock(r.verified_at);
  require(clock(r.cutoff_at)===cutoff&&r.history_freeze===r.cutoff_at.slice(0,10)+'T00:00:00.000000Z'&&clock(r.trained_through)<=clock(r.history_freeze)&&clock(r.history_panel_cutoff)<=clock(r.history_freeze)&&clock(i.normalized_at)<=begin&&begin<=end&&end<=verified&&verified<=generated&&verified<start,'Daily forecast clocks conflict.');
  if(r.mode==='DEVELOPMENT_ONLY')require(r.evidence_lane==='DEVELOPMENT_ONLY'&&r.issued_at===null,'Development previews cannot be issued.');
  else require(r.mode==='PROSPECTIVE_RESEARCH'&&r.evidence_lane==='DAILY_SNAPSHOT_PROSPECTIVE'&&verified===clock(r.issued_at)&&clock(r.issued_at)<=generated&&cutoff<=begin&&verified<=cutoff+900n*second&&verified-begin<=300n*second&&clock(r.issued_at)<start,'Prospective daily issuance clock or lane is invalid.');
  for(const s of i.sources)require(verified-clock(s.publisher_updated_at)<=BigInt(i.policy[s.role+'_max_age_seconds'])*second,'Daily source was stale when the forecast was generated.');
  const recipe=r.joint_recipe;require(fields(recipe,['algorithm','input_sha256','joint_sha256','support_atom_count','player_history_count','pool_history_count','omitted_atoms'])&&recipe.algorithm===MODELS[r.model_key]&&SHA.test(recipe.input_sha256)&&SHA.test(recipe.joint_sha256)&&Number.isSafeInteger(recipe.support_atom_count)&&recipe.support_atom_count>0&&recipe.support_atom_count<=26645&&recipe.pool_history_count===recipe.support_atom_count&&Number.isSafeInteger(recipe.player_history_count)&&recipe.player_history_count>=0&&recipe.player_history_count<=recipe.pool_history_count&&recipe.omitted_atoms===0,'Invalid coherent daily joint recipe.');
  distribution(r);
  const a=row.admission;require(fields(a,['eligible','local_persistence_completed_at','remote_recovery_completed_at','reasons'])&&typeof a.eligible==='boolean'&&emptyOrClock(a.local_persistence_completed_at,generated)&&emptyOrClock(a.remote_recovery_completed_at,generated)&&Array.isArray(a.reasons)&&a.reasons.length<=16&&a.reasons.every(text),'Invalid daily completion admission.');
  if(a.local_persistence_completed_at!==null)require(clock(a.local_persistence_completed_at)>=verified,'Daily local persistence precedes verification.');
  if(a.remote_recovery_completed_at!==null)require(a.local_persistence_completed_at!==null&&clock(a.remote_recovery_completed_at)>=clock(a.local_persistence_completed_at),'Daily recovery precedes local completion.');
  require(a.eligible?a.reasons.length===0:a.reasons.length>0,'Daily eligibility reason is inconsistent.');
  require(bytes(canonical(r)).length<=62*1024,'Complete daily forecast exceeds its encoded reserve.');
  return r;
}

function cycle(c,p,generated) {
  require(fields(c,['schema_version','protocol_id','cycle_id','registered_at','event','candidates','selection_rule','policy_id','history_record_id','history_rows','history_panel_sha256','source_schema_version','producer_versions','model_versions','source_assets','runner_start_earliest_at','activation_deadline','retrieval_opens_at','cutoff_at','issuance_closes_at','records_branch','qualification','purpose','cycle_digest'])&&c.schema_version==='nba-sdv-daily-cycle-v1'&&c.protocol_id===DAILY_PROTOCOL&&c.cycle_id==='NBA-SDV-DAILY-001-20261023-401909094'&&equal(c.event,CYCLE_EVENT)&&equal(c.candidates,CYCLE_CANDIDATES)&&SHA.test(c.cycle_digest)&&c.policy_id===p.policy_id&&c.history_record_id===HISTORY_ID&&c.history_rows===26645&&c.history_panel_sha256===HISTORY_SHA&&c.source_schema_version==='nba-sdv-daily-input-v1'&&c.selection_rule===SELECTION&&equal(c.model_versions,MODELS)&&equal(c.producer_versions,{R0:'sdv-daily-r0-producer-v1',K0:'sdv-daily-k0-producer-v1'})&&c.records_branch==='records/sdv-daily-001-20261023-401909094'&&c.qualification==='UNAVAILABLE'&&c.purpose==='OPERATIONAL_RESEARCH_NO_ACCURACY_CLAIM','Invalid daily cycle registration.');
  require(fields(c.event,['event_id','event_starts_at','home_team_id','away_team_id'])&&['event_id','home_team_id','away_team_id'].every(k=>ID.test(c.event[k]))&&c.event.home_team_id!==c.event.away_team_id,'Invalid registered daily event.');
  candidates(c.candidates,c.event);
  const cutoff=clock(c.event.event_starts_at)-90n*60n*second;
  require(clock(c.cutoff_at)===cutoff&&clock(c.retrieval_opens_at)===cutoff-3600n*second&&clock(c.issuance_closes_at)===cutoff+900n*second&&clock(c.registered_at)<=generated&&clock(c.registered_at)<clock(c.activation_deadline)&&clock(c.runner_start_earliest_at)===cutoff-120n*60n*second&&clock(c.activation_deadline)===cutoff-90n*60n*second,'Daily registered operating clocks conflict.');
  require(Array.isArray(c.source_assets)&&c.source_assets.length===2&&equal(c.source_assets.map(s=>s.role),['schedule','roster']),'Invalid registered source inventory.');
  for(const s of c.source_assets){const tag=s.role==='schedule'?'espn_nba_schedules':'espn_nba_rosters';require(fields(s,['role','release_tag','asset_name','metadata_url','asset_url'])&&s.release_tag===tag&&s.asset_name===(s.role==='schedule'?'nba_schedule_2027.csv':'rosters_2027.csv')&&s.metadata_url===`https://api.github.com/repos/sportsdataverse/sportsdataverse-data/releases/tags/${tag}`&&s.asset_url===`https://github.com/sportsdataverse/sportsdataverse-data/releases/download/${tag}/${s.asset_name}`,'Invalid registered daily source route.');}
  return c;
}

// An authenticated workflow-dispatch proof is checked independently from the
// forecast body. It authorizes this exact cycle and exact producer revision.
function authorization(a,c,generated) {
  require(c&&fields(a,['schema_version','protocol_id','cycle_id','cycle_digest','policy_id','producer_commit','producer_binding_id','repository','workflow_path','workflow_run_id','run_attempt','actor','run_head_sha','run_started_at','checked_at','confirmation','event_payload_base64','event_payload_sha256','run_metadata_base64','run_metadata_sha256','executed_file_sha256','authorization_id'])&&a.schema_version==='nba-sdv-daily-authorization-v1'&&a.protocol_id===DAILY_PROTOCOL&&a.cycle_id===c.cycle_id&&a.cycle_digest===c.cycle_digest&&a.policy_id===c.policy_id&&COMMIT.test(a.producer_commit)&&SHA.test(a.producer_binding_id)&&a.repository==='NickNicky19/Nicks-multisport-lab-project'&&a.workflow_path==='.github/workflows/sdv-daily.yml'&&Number.isSafeInteger(a.workflow_run_id)&&a.workflow_run_id>0&&Number.isSafeInteger(a.run_attempt)&&a.run_attempt>0&&a.actor==='NickNicky19'&&COMMIT.test(a.run_head_sha)&&a.confirmation===`APPROVE ${c.cycle_id} ${a.producer_commit}`&&SHA.test(a.event_payload_sha256)&&SHA.test(a.run_metadata_sha256)&&SHA.test(a.authorization_id)&&a.executed_file_sha256&&typeof a.executed_file_sha256==='object'&&!Array.isArray(a.executed_file_sha256),'Invalid daily operating authorization.');
  require(clock(c.registered_at)<=clock(a.checked_at)&&clock(c.runner_start_earliest_at)<=clock(a.run_started_at)&&clock(a.run_started_at)<=clock(a.checked_at)&&clock(a.checked_at)<clock(c.activation_deadline)&&clock(a.checked_at)<=generated,'Daily authorization missed its registered activation window.');
  let m,e;try{m=decoded(a.run_metadata_base64,128*1024).json;e=decoded(a.event_payload_base64,32*1024).json;}catch(error){throw new Error(`Invalid original daily workflow metadata: ${error.message}`);}
  const precise=v=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(v)?v.replace('Z','.000000Z'):v;
  require(m&&m.id===a.workflow_run_id&&m.run_attempt===a.run_attempt&&m.event==='workflow_dispatch'&&m.path===a.workflow_path&&m.status==='in_progress'&&m.conclusion===null&&m.head_branch==='main'&&m.head_sha===a.run_head_sha&&m.actor?.login===a.actor&&m.repository?.full_name===a.repository&&(m.triggering_actor===undefined||m.triggering_actor===null||m.triggering_actor.login===a.actor)&&clock(precise(m.run_started_at))===clock(a.run_started_at),'Original workflow metadata differs from daily authorization.');
  require(e.repository?.full_name===a.repository&&e.sender?.login===a.actor&&['main','refs/heads/main'].includes(e.ref)&&fields(e.inputs,['cycle_id','producer_commit','confirmation'])&&e.inputs.cycle_id===c.cycle_id&&e.inputs.producer_commit===a.producer_commit&&e.inputs.confirmation===a.confirmation,'Original dispatch event differs from exact daily authorization.');
}

function timely(row,i,p) {
  const r=row.body,a=row.admission;if(r.mode!=='PROSPECTIVE_RESEARCH'||a.local_persistence_completed_at===null||a.remote_recovery_completed_at===null)return false;
  const cutoff=clock(r.cutoff_at),end=cutoff+BigInt(p.issuance_window_seconds)*second,begin=clock(r.generation_started_at),remote=clock(a.remote_recovery_completed_at);
  if(!(cutoff<=begin&&begin<=clock(r.verified_at)&&clock(r.issued_at)<=clock(a.local_persistence_completed_at)&&remote<=end&&remote-begin<=BigInt(p.maximum_original_latency_seconds)*second&&clock(i.normalized_at)<=cutoff&&clock(i.normalized_at)>=cutoff-BigInt(p.retrieval_lookback_seconds)*second))return false;
  return i.sources.every(s=>clock(s.retrieval_started_at)>=cutoff-BigInt(p.retrieval_lookback_seconds)*second&&clock(s.retrieved_at)<=cutoff&&remote-clock(s.publisher_updated_at)<=BigInt(p[s.role+'_max_age_seconds'])*second);
}

const SUBJECT_FIELDS=['cycle_id','mode','event_id','event_snapshot_id','player_id','team_id','opponent_id'];
function outcome(row,forecasts,generated) {
  require(fields(row,['reference','body'])&&reference(row.reference,'outcomes'),'Invalid daily outcome reference.');
  const o=row.body;
  require(fields(o,['schema_version','protocol_id','cycle_id','mode','event_id','event_snapshot_id','event_starts_at','player_id','team_id','opponent_id','status','source_refs','source_observed_at','normalized_at','normalizer_version','primitives','minutes','minutes_precision','categories','outcome_id'])&&o.schema_version==='nba-sdv-daily-outcome-v1'&&o.protocol_id===DAILY_PROTOCOL&&SHA.test(o.outcome_id)&&SHA.test(o.event_snapshot_id)&&['APPEARED','DNP','MISSING','POSTPONED','NONFINAL','UNRESOLVED'].includes(o.status)&&text(o.normalizer_version)&&Array.isArray(o.source_refs)&&o.source_refs.length>0&&o.source_refs.length<=2&&o.source_refs.every(r=>reference(r,'research_inputs')),'Invalid daily outcome contract.');
  const matching=[...forecasts.values()].filter(f=>[...SUBJECT_FIELDS,'event_starts_at'].every(k=>o[k]===f[k]));
  require(matching.length>0&&clock(o.source_observed_at)<=clock(o.normalized_at)&&clock(o.normalized_at)<=generated&&matching.every(f=>clock(f.issued_at??f.verified_at)<=clock(o.source_observed_at)),'Daily outcome differs from original identity or evidence clocks.');
  if(['APPEARED','DNP'].includes(o.status))require(clock(o.source_observed_at)>=clock(o.event_starts_at),'Final daily outcome precedes its event.');
  if(o.status==='APPEARED'){
    const p=o.primitives;require(fields(p,['FGM','FG2M','FG3M','FTM','PTS','REB','AST','TOV','BLK','STL'])&&Object.values(p).every(v=>Number.isSafeInteger(v)&&v>=0)&&p.FGM===p.FG2M+p.FG3M&&p.PTS===2*p.FG2M+3*p.FG3M+p.FTM,'Contradictory daily outcome scoring counts.');
    require(Number.isFinite(o.minutes)&&o.minutes>=0&&['seconds','rounded_whole_minutes'].includes(o.minutes_precision)&&(o.minutes_precision==='rounded_whole_minutes'?Number.isInteger(o.minutes):o.minutes>0),'Daily appearance minutes are invalid.');
    const tens=[p.PTS,p.REB,p.AST,p.BLK,p.STL].filter(n=>n>=10).length,actual={PTS:p.PTS,PRA:p.PTS+p.REB+p.AST,REB:p.REB,'3PM':p.FG3M,AST:p.AST,RA:p.REB+p.AST,PR:p.PTS+p.REB,TOV:p.TOV,TD:Number(tens>=3),DD:Number(tens>=2),BLK:p.BLK,STL:p.STL,'BLK+STL':p.BLK+p.STL,PA:p.PTS+p.AST};
    require(Array.isArray(o.categories)&&o.categories.length===14&&new Set(o.categories.map(c=>c.code)).size===14&&o.categories.every(c=>fields(c,['code','units','observed'])&&Object.hasOwn(actual,c.code)&&c.units===NBA_UNITS[c.code]&&c.observed===actual[c.code]),'Daily outcome category derivation differs from its primitive line.');
  }else require(o.primitives===null&&o.minutes===null&&o.minutes_precision===null&&Array.isArray(o.categories)&&o.categories.length===0,'DNP or unresolved daily outcome cannot become zero production.');
  return o;
}

function grade(row,forecasts,outcomes,generatedAt) {
  require(fields(row,['reference','body'])&&reference(row.reference,'grades'),'Invalid daily grade reference.');
  const g=row.body,f=forecasts.get(g?.forecast_id),o=outcomes.get(g?.outcome_id);
  require(fields(g,['schema_version','protocol_id','cycle_id','mode','event_id','event_snapshot_id','player_id','team_id','opponent_id','model_key','forecast_id','outcome_id','graded_at','status','categories','financial_settlement','qualification','grade_id'])&&g.schema_version==='nba-sdv-daily-grade-v1'&&g.protocol_id===DAILY_PROTOCOL&&SHA.test(g.grade_id)&&f&&o&&SUBJECT_FIELDS.every(k=>g[k]===f[k]&&g[k]===o[k])&&g.model_key===f.model_key&&g.qualification==='UNAVAILABLE'&&g.financial_settlement==='NOT_EVALUATED'&&clock(o.normalized_at)<=clock(g.graded_at)&&clock(g.graded_at)<=clock(generatedAt),'Invalid daily grade linkage or clock.');
  const expected=o.status==='APPEARED'?'SCORED':o.status==='DNP'?'DNP_NOT_SCORED':o.status;
  require(g.status===expected,'Daily grade status differs from verified outcome.');
  // Reuse the existing independently recomputed score contract. Only the local
  // validation view changes names; no original record or probability is changed.
  const mapped={schema_version:'nba-forecast-grade-v1',grade_id:g.grade_id,forecast_id:g.forecast_id,outcome_id:g.outcome_id,id_namespace:'espn',league:'NBA',event_id:g.event_id,player_id:g.player_id,graded_at:g.graded_at,status:['SCORED','DNP_NOT_SCORED'].includes(g.status)?g.status:'UNRESOLVED',evidence_lane:f.evidence_lane,categories:g.categories,financial_settlement:g.financial_settlement};
  validateResearchGrade(mapped,{...f,id_namespace:'espn',league:'NBA',issued_at:f.issued_at??f.verified_at},generatedAt);
  if(g.status==='SCORED')require(g.categories.every(c=>o.categories.some(actual=>actual.code===c.code&&actual.observed===c.observed)),'Daily grade observed values differ from verified outcome.');
  return g;
}

export function activeDailyGrades(asset) {
  const superseded=new Set(asset.corrections.map(c=>c.original_ref.record_id)),oldOutcomes=new Set(asset.outcomes.filter(r=>superseded.has(r.reference.record_id)).map(r=>r.body.outcome_id));
  return asset.grades.filter(r=>!superseded.has(r.reference.record_id)&&!oldOutcomes.has(r.body.outcome_id));
}

export function validateDailyDescriptor(d,publishedAt) {
  require(fields(d,['path','sha256','generated_at','status','retained','error'])&&SHA.test(d.sha256)&&d.path===`sdv-daily.${d.sha256}.json`&&d.status==='DAILY_SNAPSHOT_RESEARCH'&&typeof d.retained==='boolean'&&(d.error===null||text(d.error))&&clock(d.generated_at)<=clock(publishedAt),'Invalid daily research descriptor.');
  return d;
}

export function validateDailyAsset(asset,publishedAt) {
  require(fields(asset,['schema_version','protocol_id','generated_at','policy','cycle','inputs','forecasts','outcomes','grades','corrections','activation','counts','status','reason','qualification','financial_settlement','asset_id'])&&asset.schema_version==='nba-sdv-daily-publication-v1'&&asset.protocol_id===DAILY_PROTOCOL&&SHA.test(asset.asset_id)&&text(asset.reason)&&asset.qualification==='UNAVAILABLE'&&asset.financial_settlement==='NOT_EVALUATED','Invalid daily research publication.');
  const generated=clock(asset.generated_at);require(generated<=clock(publishedAt),'Daily asset was generated after publication.');policy(asset.policy);
  if(asset.cycle!==null)cycle(asset.cycle,asset.policy,generated);
  if(asset.activation!==null)authorization(asset.activation,asset.cycle,generated);
  require(Array.isArray(asset.inputs)&&asset.inputs.length<=1&&Array.isArray(asset.forecasts)&&asset.forecasts.length<=8,'Daily public input or forecast count exceeds its bound.');
  const inputs=new Map(),forecasts=new Map(),subjects=new Set(),modes=new Set(),refs=new Map(),outcomes=new Map(),grades=new Map();
  for(const r of asset.inputs){input(r,generated);require(equal(r.policy,asset.policy)&&!inputs.has(r.input_id),'Duplicate input or differing daily policy.');if(asset.cycle)require(equal(r.candidates,asset.cycle.candidates)&&['event_id','event_starts_at','home_team_id','away_team_id'].every(k=>r.event[k]===asset.cycle.event[k]),'Daily input differs from fixed registered cohort.');inputs.set(r.input_id,r);}
  for(const row of asset.forecasts){const r=forecast(row,inputs,generated);require(!forecasts.has(r.forecast_id)&&!subjects.has(idKey(r))&&!refs.has(row.reference.record_id),'Duplicate original daily model/subject.');forecasts.set(r.forecast_id,r);subjects.add(idKey(r));modes.add(r.mode);refs.set(row.reference.record_id,row);const i=inputs.get(r.input_id);require(asset.cycle!==null,'Daily forecast lacks its registered cycle.');
    if(asset.cycle)require(r.cycle_id===asset.cycle.cycle_id&&r.history_ref.record_id===asset.cycle.history_record_id&&r.history_panel_sha256===asset.cycle.history_panel_sha256,'Daily forecast differs from registered history or cycle.');
    if(r.mode==='PROSPECTIVE_RESEARCH'){require(asset.activation!==null&&asset.cycle!==null&&r.producer_binding.commit===asset.activation.producer_commit&&r.producer_binding.binding_id===asset.activation.producer_binding_id&&equal(r.producer_binding.files,asset.activation.executed_file_sha256),'Prospective daily record lacks exact reviewed operating authorization.');}
    const eligible=r.mode==='PROSPECTIVE_RESEARCH'&&asset.activation!==null&&timely(row,i,asset.policy);
    // An ineligible original can also carry input/checkpoint failure reasons
    // whose original completion receipts remain in the recovery archive.
    require(!row.admission.eligible||eligible,'Daily admission differs from actual persistence/recovery timing.');
  }
  require(modes.size<=1,'Development and genuine originals cannot share a daily cycle.');
  require(Array.isArray(asset.outcomes)&&asset.outcomes.length<=16&&Array.isArray(asset.grades)&&asset.grades.length<=32&&Array.isArray(asset.corrections)&&asset.corrections.length<=16,'Daily outcome/grade/correction count exceeds its bound.');
  for(const row of asset.outcomes){const r=outcome(row,forecasts,generated);require(!outcomes.has(r.outcome_id)&&!refs.has(row.reference.record_id),'Duplicate daily outcome.');outcomes.set(r.outcome_id,r);refs.set(row.reference.record_id,row);}
  for(const row of asset.grades){const r=grade(row,forecasts,outcomes,asset.generated_at);require(!grades.has(r.grade_id)&&!refs.has(row.reference.record_id),'Duplicate daily grade.');grades.set(r.grade_id,r);refs.set(row.reference.record_id,row);}
  const edges=new Map();
  for(const c of asset.corrections){require(fields(c,['reference','original_ref','replacement_ref','reason'])&&reference(c.reference,'corrections')&&['outcomes','grades'].includes(c.original_ref?.kind)&&reference(c.original_ref,c.original_ref.kind)&&reference(c.replacement_ref,c.original_ref.kind)&&text(c.reason)&&c.original_ref.record_id!==c.replacement_ref.record_id&&!edges.has(c.original_ref.record_id),'Invalid daily correction reference.');const before=refs.get(c.original_ref.record_id),after=refs.get(c.replacement_ref.record_id);require(before&&after&&equal(before.reference,c.original_ref)&&equal(after.reference,c.replacement_ref)&&SUBJECT_FIELDS.every(k=>before.body[k]===after.body[k])&&(c.original_ref.kind!=='grades'||before.body.forecast_id===after.body.forecast_id),'Daily correction changed original subject or forecast.');const key=c.original_ref.kind==='grades'?'graded_at':'source_observed_at';require(clock(before.body[key])<=clock(after.body[key]),'Daily correction clock precedes its original.');edges.set(c.original_ref.record_id,c.replacement_ref.record_id);}
  for(const start of edges.keys()){let at=start;const seen=new Set();while(edges.has(at)){require(!seen.has(at),'Daily correction cycle.');seen.add(at);at=edges.get(at);}}
  const active=activeDailyGrades(asset);require(new Set(active.map(r=>r.body.forecast_id)).size===active.length,'Multiple active daily grades for an original forecast.');
  const development=[...forecasts.values()].filter(r=>r.mode==='DEVELOPMENT_ONLY').length,genuine=forecasts.size-development,eligible=asset.forecasts.filter(r=>r.admission.eligible).length;
  const final=new Set(active.filter(r=>['SCORED','DNP_NOT_SCORED'].includes(r.body.status)).map(r=>r.body.forecast_id));
  require(equal(asset.counts,{development_forecasts:development,genuine_forecasts:genuine,eligible_forecasts:eligible,pending_grades:forecasts.size-final.size}),'Daily publication counts differ from original records.');
  const status=!forecasts.size?'INACTIVE':development?'DEVELOPMENT_PREVIEW':genuine<8||eligible<8?'PARTIAL':asset.counts.pending_grades?'ISSUED':'COMPLETED';
  require(asset.status===status&&bytes(canonical(asset)).length<=DAILY_MAX_BYTES,'Daily publication state or complete encoded byte limit is invalid.');
  return asset;
}

async function hash(raw,provider){require(provider?.subtle,'Daily research integrity requires a secure context.');return [...new Uint8Array(await provider.subtle.digest('SHA-256',typeof raw==='string'?bytes(raw):raw))].map(v=>v.toString(16).padStart(2,'0')).join('');}
async function sealed(body,key,provider){const {[key]:id,...rest}=body;require(await hash(canonical(rest),provider)===id,`Daily ${key} checksum mismatch.`);}
export async function verifyDailyHashes(asset,provider=globalThis.crypto) {
  await sealed(asset,'asset_id',provider);await sealed(asset.policy,'policy_id',provider);
  if(asset.cycle)await sealed(asset.cycle,'cycle_digest',provider);
  if(asset.activation){await sealed(asset.activation,'authorization_id',provider);require(await hash(decoded(asset.activation.run_metadata_base64,128*1024).raw,provider)===asset.activation.run_metadata_sha256&&await hash(decoded(asset.activation.event_payload_base64,32*1024).raw,provider)===asset.activation.event_payload_sha256,'Original daily workflow metadata checksum mismatch.');}
  for(const i of asset.inputs){await sealed(i,'input_id',provider);await sealed(i.event,'event_snapshot_id',provider);await sealed(i.policy,'policy_id',provider);}
  for(const row of asset.forecasts){await sealed(row.body,'forecast_id',provider);await sealed(row.body.producer_binding,'binding_id',provider);}
  for(const row of asset.outcomes)await sealed(row.body,'outcome_id',provider);
  for(const row of asset.grades)await sealed(row.body,'grade_id',provider);
  return asset;
}

export function dailyViewCounts(asset,{now=Date.now()}={}) {
  if(!asset)return {upcoming:0,history:0,development:0,genuine:0,eligible:0};
  const dev=asset.forecasts.filter(row=>row.body.mode==='DEVELOPMENT_ONLY'),genuine=asset.forecasts.filter(row=>row.body.mode==='PROSPECTIVE_RESEARCH');
  const upcoming=genuine.filter(row=>row.admission.eligible&&Date.parse(row.body.event_starts_at)>now).length;
  return {upcoming,history:genuine.length-upcoming,development:dev.length,genuine:genuine.length,eligible:genuine.filter(row=>row.admission.eligible).length};
}

function card(row,asset,category,now) {
  const r=row.body,i=asset.inputs.find(i=>i.input_id===r.input_id),dev=r.mode==='DEVELOPMENT_ONLY';
  const grade=activeDailyGrades(asset).find(g=>g.body.forecast_id===r.forecast_id)?.body;
  const gradeText=grade?grade.status==='SCORED'?'Statistical forecast graded; financial settlement not evaluated.':grade.status==='DNP_NOT_SCORED'?'Did not play; statistical forecast not scored.':`Outcome ${grade.status.toLowerCase()}; no statistical score.`:'Statistical outcome and grade pending.';
  const sourceRows=i.sources.map(s=>{const age=(now-Date.parse(s.publisher_updated_at))/3600000,atGeneration=(Date.parse(r.verified_at)-Date.parse(s.publisher_updated_at))/3600000,stale=age>asset.policy[s.role+'_max_age_seconds']/3600;return `<li><strong>${escaped(s.role==='schedule'?'Schedule':'Roster')} asset</strong>: publisher updated ${datetime(s.publisher_updated_at)}; retrieved ${datetime(s.retrieved_at)}. Publisher asset age at generation ${atGeneration.toFixed(1)} hours; now ${Math.max(0,age).toFixed(1)} hours${stale?' — outside the operating age limit':''}. Upstream observation ${s.upstream_observation_status==='UNKNOWN'?'UNKNOWN':datetime(s.upstream_observed_at)}. <a href="${escaped(s.asset_url)}" rel="noopener noreferrer">Publisher asset ${escaped(s.asset_name)}</a>, original SHA-256 <code class="break-code">${escaped(s.asset_sha256)}</code>.</li>`;}).join('');
  const horizon=(Date.parse(r.event_starts_at)-Date.parse(r.issued_at??r.verified_at))/60000;
  const horizonText=`${dev?'Development generation':'Issued'} ${horizon.toFixed(1)} minutes before scheduled start. This forecast horizon is separate from the asset ages.`;
  const stale=i.sources.some(s=>now-Date.parse(s.publisher_updated_at)>asset.policy[s.role+'_max_age_seconds']*1000);
  const categories=r.categories.filter(c=>category==='ALL'||c.code===category);
  return `<article class="forecast-card"><div class="forecast-card-heading"><div><p class="eyebrow">${dev?'Development preview · not issued':'Daily-snapshot research'} · ${escaped(r.model_key)}</p><h3>${escaped(r.player_label)}</h3><p>${escaped(r.matchup)} · ${datetime(r.event_starts_at)}</p></div><span class="pill">${dev?'NOT ISSUED':row.admission.eligible?'Research forecast':'Ineligible retained original'}</span></div><p>Conditional on this player appearing in the game. Roster membership does not confirm participation, health, a starting role or minutes.</p>${stale?'<p class="notice warning">These exact publisher assets are now older than the daily operating limit. A new download of unchanged content would not make them fresh. Original research probabilities remain unchanged.</p>':''}<div class="table-wrap"><table><thead><tr><th>Category</th><th>Mean</th><th>80% interval</th></tr></thead><tbody>${categories.map(c=>`<tr><td>${escaped(c.code)}</td><td>${Number(c.mean).toFixed(2)}</td><td>${c.interval80.map(escaped).join('–')}</td></tr>`).join('')}</tbody></table></div><p>Actual issue time: ${datetime(r.issued_at)}. Generation completed: ${datetime(r.generation_completed_at)}. ${escaped(gradeText)} ${escaped(horizonText)}</p><details class="forecast-provenance"><summary>Source identities, clocks and research limitations</summary><p>Model ${escaped(r.model_version)}; producer ${escaped(r.producer_version)}. Historical panel cutoff ${datetime(r.history_panel_cutoff)} (${r.history_rows.toLocaleString('en-US')} retained rows; reconstructed completion-bound availability).</p><ul>${sourceRows}</ul><p>Missing injury, starting-lineup and confirmed-participation information. Daily publisher update age is separate from forecast horizon and upstream observation age. This is not the original fresh-input T90 protocol.</p><p>NBA / ESPN identity namespace · player <code>${escaped(r.player_id)}</code> · event <code>${escaped(r.event_id)}</code> · forecast event team / opponent IDs <code>${escaped(r.team_id)}</code> / <code>${escaped(r.opponent_id)}</code>.</p><p class="break-code">Forecast ${escaped(r.forecast_id)}; input ${escaped(r.input_id)}; source commit ${escaped(r.producer_binding.commit||'uncommitted development source')}.</p><p>Local persistence: ${r.issued_at===null?'development only':datetime(row.admission.local_persistence_completed_at)}; independent recovery: ${row.admission.remote_recovery_completed_at===null?'not acknowledged':datetime(row.admission.remote_recovery_completed_at)}.</p>${row.admission.reasons.length?`<p>${row.admission.reasons.map(escaped).join('; ')}</p>`:''}<p>Qualification unavailable. No sportsbook price, ticket EV, financial settlement or betting recommendation is implied.</p></details></article>`;
}

export function renderDailyResearch(asset,{view='upcoming',category='ALL',nbaSelected=true,performance=false,limit=28,window='upcoming',now=Date.now()}={}) {
  if(!asset||!nbaSelected)return '';
  require(['upcoming','history'].includes(view)&&['ALL',...ALL_NBA_CATEGORIES].includes(category)&&['upcoming','24h','7d'].includes(window)&&Number.isSafeInteger(limit)&&limit>0&&limit<=112&&Number.isFinite(now),'Invalid daily display filters.');
  if(performance){const grades=activeDailyGrades(asset);return `<section class="panel sdv-daily-research"><h2>Daily-snapshot research performance</h2>${grades.length?`<p>${grades.length} statistical grade records; each model and evidence lane remains separate. No comparative aggregate or qualification is established.</p><ul>${grades.map(row=>{const f=asset.forecasts.find(f=>f.body.forecast_id===row.body.forecast_id).body;return `<li>${escaped(f.player_label)} · ${escaped(f.model_key)} · ${escaped(f.mode==='DEVELOPMENT_ONLY'?'Development only':'Daily-snapshot prospective research')} · ${escaped(row.body.status)} · graded ${datetime(row.body.graded_at)}</li>`;}).join('')}</ul>`:'<p>No statistical grades are published for this daily-source cycle. Upcoming forecasts and development previews do not establish accuracy or qualification.</p>'}</section>`;}
  const horizon=window==='24h'?86400000:window==='7d'?7*86400000:Infinity;
  const genuine=asset.forecasts.filter(row=>row.body.mode==='PROSPECTIVE_RESEARCH'),selected=genuine.filter(row=>view==='upcoming'?row.admission.eligible&&Date.parse(row.body.event_starts_at)>now&&Date.parse(row.body.event_starts_at)<=now+horizon:!row.admission.eligible||Date.parse(row.body.event_starts_at)<=now),dev=asset.forecasts.filter(row=>row.body.mode==='DEVELOPMENT_ONLY');
  let html=`<section class="panel sdv-daily-research"><h2>Daily-snapshot research forecasts</h2><p>${selected.length} ${view==='upcoming'?'genuinely issued upcoming':'retained past-event or ineligible'} research bundles in this view. Publication generated ${datetime(asset.generated_at)}; this is not a source-capture or issuance clock.</p>`;
  html+=selected.length?`<div class="forecast-grid">${selected.slice(0,limit).map(row=>card(row,asset,category,now)).join('')}</div>`:`<p class="notice">${view==='upcoming'?'No genuinely issued daily-snapshot forecast is upcoming in this publication. Fresh permitted inputs, approved activation and timely durable issuance are required.':'No daily-snapshot past-event or ineligible originals are present. Starting a game alone never establishes its outcome.'} ${escaped(asset.reason)}</p>`;
  html+='<p>Source: <a href="https://github.com/sportsdataverse/sportsdataverse-data" rel="noopener noreferrer">SportsDataverse ESPN/hoopR-derived publisher releases</a>. Publisher-asserted <a href="https://creativecommons.org/licenses/by/4.0/" rel="noopener noreferrer">CC BY 4.0</a>. Modifications: schedule/roster normalization, fixed-cohort joins and model summaries. This is not ESPN endorsement or permission for direct ESPN collection. Original release files remain in the records archive, outside the website assets.</p></section>';
  if(dev.length)html+=`<section class="panel sdv-daily-development"><h2>Development preview · not issued</h2><p>${dev.length} development-only bundles demonstrate the website path. They have no issuance timestamp, are excluded from Upcoming and genuine forecast counts, and establish no prospective results.</p><div class="forecast-grid">${dev.slice(0,limit).map(row=>card(row,asset,category,now)).join('')}</div></section>`;
  return html;
}

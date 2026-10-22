// Every prospective clock/authority below is an invented software fixture.
// These tests perform no capture, issuance, HTTP, model fitting or publication.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash,webcrypto} from 'node:crypto';
import {originalProduction,validateProductionDescriptor,validateProductionIndex,validateProductionPage,validateProductionCollection,verifyProductionHashes,productionViewCounts,activeProductionGrades,summarizeProductionPerformance,renderProductionResearch,selectProductionDate,PRODUCTION_MAX_TOTAL_BYTES,PRODUCTION_CLIENT_MAX_BYTES} from '../production.mjs';
import {loadSnapshot,loadProductionDate} from '../snapshot.mjs';
import {typedFixture} from './fixtures.mjs';

const canonical=v=>v&&typeof v==='object'?Array.isArray(v)?`[${v.map(canonical).join(',')}]`:`{${Object.keys(v).sort().map(k=>`${JSON.stringify(k)}:${canonical(v[k])}`).join(',')}}`:JSON.stringify(v);
const hash=v=>createHash('sha256').update(typeof v==='string'?v:canonical(v)).digest('hex');
const seal=(body,key)=>{const {[key]:_,...unsigned}=body;return {...unsigned,[key]:hash(unsigned)};};
const stamp=ms=>new Date(ms).toISOString().replace(/\.(\d{3})Z$/,'.$1000Z');
const fixture=JSON.parse(readFileSync(new URL('../../tests/fixtures/sdv-production-synthetic.json',import.meta.url),'utf8'));
const copy=()=>structuredClone(fixture);
const all=bundle=>bundle.pages.flatMap(page=>page.records);
const of=(bundle,suffix)=>all(bundle).filter(row=>originalProduction(row).schema_version===`nba-sdv-production-${suffix}-v1`);
const key=body=>({'nba-sdv-production-plan-v1':'plan_id','nba-sdv-production-input-v1':'input_id','nba-sdv-production-run-v1':'authorization_id','nba-sdv-production-status-v1':'status_id','nba-sdv-production-forecast-v1':'forecast_id','nba-sdv-production-outcome-v1':'outcome_id','nba-sdv-production-grade-v1':'grade_id'}[body.schema_version]);
const ref=(kind,seed)=>({kind,record_id:hash('SYNTHETIC RECORD '+seed),payload_sha256:hash('SYNTHETIC ENVELOPE '+seed)});
function wrap(row,body){const {[key(body)]:_,...unsigned}=body;return {...row,record_json:canonical(unsigned),original_id:hash(unsigned)};}
function projection(body,kind,seed,admission=null){return wrap({reference:ref(kind,seed),record_encoding:'CANONICAL_ORIGINAL_BODY_WITHOUT_ID',admission},body);}
function nextCheck(at){const start=Date.parse(at);let value=Math.floor(start/60000)*60000;while(value<=start||![2,17,32,47].includes(new Date(value).getUTCMinutes()))value+=60000;return stamp(value);}

function counts(records) {
  records=[...new Map(records.map(row=>[originalProduction(row).schema_version+row.original_id,row])).values()];const bodies=records.map(originalProduction),forecasts=records.filter(row=>originalProduction(row).schema_version==='nba-sdv-production-forecast-v1'),eligible=forecasts.filter(row=>row.admission.eligible).map(originalProduction),eligibleIds=new Set(eligible.map(f=>f.forecast_id)),grades=activeProductionGrades({records}).filter(g=>eligibleIds.has(g.forecast_id)),final=new Set(grades.filter(g=>['SCORED','DNP_NOT_SCORED'].includes(g.status)).map(g=>g.forecast_id));
  return {forecasts:forecasts.length,genuine_forecasts:eligible.length,eligible_forecasts:eligible.length,development_forecasts:forecasts.filter(row=>originalProduction(row).mode==='DEVELOPMENT_ONLY').length,outcomes:bodies.filter(b=>b.schema_version==='nba-sdv-production-outcome-v1').length,grades:bodies.filter(b=>b.schema_version==='nba-sdv-production-grade-v1').length,active_grades:grades.length,scored_grades:grades.filter(g=>g.status==='SCORED').length,dnp_grades:grades.filter(g=>g.status==='DNP_NOT_SCORED').length,pending_grades:eligible.filter(f=>!final.has(f.forecast_id)).length,players:new Set(eligible.map(f=>f.player_id)).size,events:new Set(eligible.map(f=>f.event_id)).size};
}
function repack(bundle,records=all(bundle),generated=bundle.index.generated_at) {
  const index=structuredClone(bundle.index);index.generated_at=generated;const bodies=records.map(originalProduction),planDates=new Map(bodies.filter(b=>b.schema_version==='nba-sdv-production-plan-v1').map(p=>[p.plan_id,p.game_date])),forecastDates=new Map(bodies.filter(b=>b.schema_version==='nba-sdv-production-forecast-v1').map(f=>[f.forecast_id,f.event_starts_at.slice(0,10)])),groups=new Map(),shared=[];
  for(const row of records){const b=originalProduction(row),day=b.game_date??b.event_starts_at?.slice(0,10)??(b.event&&typeof b.event==='object'?b.event.event_starts_at?.slice(0,10):null)??(b.schema_version==='nba-sdv-production-grade-v1'?forecastDates.get(b.forecast_id):null)??(b.schema_version==='nba-sdv-production-status-v1'?planDates.get(b.plan_id):null);if(day){if(!groups.has(day))groups.set(day,[]);groups.get(day).push(row);}else shared.push(row);}
  const pages=[...groups].sort(([a],[b])=>a.localeCompare(b)).map(([game_date,rows])=>seal({schema_version:'nba-sdv-production-public-page-v1',protocol_id:index.protocol_id,generated_at:generated,game_date,records:[...rows,...shared]},'page_id'));
  index.pages=pages.map(page=>({path:`sdv-production-page.${hash(page)}.json`,sha256:hash(page),generated_at:generated,game_date:page.game_date,record_count:page.records.length}));index.dates=pages.map(page=>{const starts=page.records.filter(r=>originalProduction(r).schema_version==='nba-sdv-production-forecast-v1'&&r.admission.eligible).map(r=>originalProduction(r).event_starts_at).sort();return {game_date:page.game_date,counts:counts(page.records),first_event_starts_at:starts[0]??null,last_event_starts_at:starts.at(-1)??null};});index.counts=counts(records);const eligible=records.filter(r=>originalProduction(r).schema_version==='nba-sdv-production-forecast-v1'&&r.admission.eligible).map(originalProduction);
  const latest=values=>values.length?values.sort().at(-1):null;
  index.operations.last_source_capture_at=latest(bodies.filter(b=>b.schema_version==='nba-sdv-production-input-v1').flatMap(b=>b.sources.map(s=>s.retrieved_at)));
  index.operations.last_issued_at=latest(eligible.map(f=>f.issued_at));index.operations.next_configured_check_at=nextCheck(generated);
  index.coverage.from_game_date=new Date(Date.parse(generated.slice(0,10)+'T00:00:00Z')-6*86400000).toISOString().slice(0,10);index.coverage.to_game_date=latest([generated.slice(0,10),...bodies.filter(b=>b.schema_version==='nba-sdv-production-plan-v1').map(b=>b.game_date)]);
  return {index:seal(index,'index_id'),pages};
}

function prospective(days=1) {
  const bundle=copy();for(const row of all(bundle))row.reference=ref(row.reference.kind,'synthetic cycle '+days+' '+row.reference.record_id);
  const planRow=of(bundle,'plan')[0],inputRow=of(bundle,'input')[0],p=originalProduction(planRow),i=originalProduction(inputRow),oldForecasts=of(bundle,'forecast');
  const shift=value=>stamp(Date.parse(value)+days*86400000),binding=seal({...i.producer_binding,commit:'a'.repeat(40)},'binding_id');
  p.mode='PROSPECTIVE_RESEARCH';p.game_date=shift(p.game_date+'T00:00:00.000000Z').slice(0,10);p.planning_started_at=shift(p.planning_started_at);p.planned_at=shift(p.planned_at);p.producer_binding=binding;
  const planTime=Date.parse(p.planning_started_at),sourceAt=(source,at)=>({...source,publisher_updated_at:stamp(planTime-12*3600000),retrieval_started_at:stamp(at-60000),retrieved_at:stamp(at-59000),metadata_retrieval_started_at:stamp(at-120000),metadata_retrieved_at:stamp(at-119000),metadata_observation_status:'OBSERVED'});
  p.sources=p.sources.map(s=>sourceAt(s,planTime));p.missing_information=p.missing_information.filter(s=>s!=='PUBLISHER_METADATA_OBSERVATION_CLOCK');
  p.inventory=p.inventory.map(row=>({...row,event_starts_at:shift(row.event_starts_at)}));
  p.events=p.events.map(row=>({...row,event:seal({...row.event,event_starts_at:shift(row.event.event_starts_at)},'event_snapshot_id'),cutoff_at:shift(row.cutoff_at),capture_opens_at:shift(row.capture_opens_at),issuance_closes_at:shift(row.issuance_closes_at)}));
  p.plan_seed=hash({protocol_id:p.protocol_id,policy_id:p.policy.policy_id,game_date:p.game_date,sources:p.sources,producer_binding:binding,events:p.events.map(e=>({event:e.event,candidates:e.candidates,shards:e.shards}))});
  for(const e of p.events)e.cycle_id=`prod-${p.game_date.replaceAll('-','')}-${e.event.event_id}-${p.plan_seed.slice(0,12)}`;
  const planned=wrap(planRow,p),selected=p.events.find(e=>e.event.event_id===i.event.event_id),cutoff=Date.parse(selected.cutoff_at),normalized=cutoff-300000;
  Object.assign(i,{mode:'PROSPECTIVE_RESEARCH',plan_id:planned.original_id,plan_seed:p.plan_seed,cycle_id:selected.cycle_id,event:selected.event,candidates:selected.candidates,shards:selected.shards,producer_binding:binding,normalization_started_at:stamp(normalized),normalized_at:stamp(normalized+1000)});i.sources=i.sources.map(s=>sourceAt(s,normalized));i.missing_information=i.missing_information.filter(s=>s!=='PUBLISHER_METADATA_OBSERVATION_CLOCK');const admitted=wrap(inputRow,i);
  const archive={tag:'nml-nba-records-v1-202610',sha256:'d'.repeat(64),name:`object-${'d'.repeat(64)}.z`,bytes:128};
  const forecasts=oldForecasts.map(row=>{const f=originalProduction(row);Object.assign(f,{mode:'PROSPECTIVE_RESEARCH',evidence_lane:'SDV_PRODUCTION_PROSPECTIVE',plan_id:planned.original_id,cycle_id:i.cycle_id,input_id:admitted.original_id,input_ref:admitted.reference,event_snapshot_id:i.event.event_snapshot_id,event_starts_at:i.event.event_starts_at,cutoff_at:selected.cutoff_at,history_freeze:selected.cutoff_at.slice(0,10)+'T00:00:00.000000Z',producer_binding:binding,generation_started_at:stamp(cutoff+10000),generation_completed_at:stamp(cutoff+11000),verified_at:stamp(cutoff+12000),issued_at:stamp(cutoff+12000)});return wrap({...row,admission:{eligible:true,local_completed_at:stamp(cutoff+13000),remote_recovered_at:stamp(cutoff+60000),reasons:[],archive_ref:archive}},f);});
  const runStarted=stamp(cutoff-60000),proof=body=>{const raw=JSON.stringify(body);return {base64:Buffer.from(raw).toString('base64'),bytes:Buffer.byteLength(raw),sha256:hash(raw)};};
  const auth={schema_version:'nba-sdv-production-run-v1',protocol_id:p.protocol_id,repository:'NickNicky19/Nicks-multisport-lab-project',workflow_path:'.github/workflows/nba-operations.yml',event:'schedule',actor:'NickNicky19',run_id:123,run_attempt:1,head_sha:binding.commit,run_started_at:runStarted,verified_at:stamp(cutoff-59000),event_original:proof({repository:{full_name:'NickNicky19/Nicks-multisport-lab-project'},schedule:p.policy.cron,note:'SYNTHETIC Ω authority test'}),run_original:proof({id:123,run_attempt:1,event:'schedule',head_sha:binding.commit,head_branch:'main',path:'.github/workflows/nba-operations.yml',status:'in_progress',conclusion:null,repository:{full_name:'NickNicky19/Nicks-multisport-lab-project'},actor:{login:'NickNicky19'},run_started_at:runStarted,note:'SYNTHETIC Ω run metadata'}),executed_files:binding.files};
  return repack(bundle,[planned,admitted,projection(auth,'input_captures','synthetic authority '+days),...forecasts],stamp(cutoff+120000));
}

function withOutcome(status='DNP') {
  const bundle=prospective(),forecasts=of(bundle,'forecast'),f=originalProduction(forecasts[0]),input=originalProduction(of(bundle,'input')[0]),at=Date.parse(f.event_starts_at)+3*3600000;
  const shared=Object.fromEntries(['protocol_id','plan_id','cycle_id','mode','event_id','event_snapshot_id','player_id','team_id','opponent_id'].map(k=>[k,f[k]])),archive=n=>({tag:'nml-nba-records-v1-202610',sha256:String(n).repeat(64),name:`object-${String(n).repeat(64)}.z`,bytes:128});
  const o={schema_version:'nba-sdv-production-outcome-v1',...shared,event_starts_at:f.event_starts_at,season_ending_year:input.event.season_ending_year,season_type:input.event.season_type,status,source_archive_refs:[archive(1),archive(2)],source_observed_at:stamp(at),normalized_at:stamp(at+1000),normalizer_version:'sdv-production-final-csv-v1',primitives:status==='APPEARED'?{FGM:0,FG2M:0,FG3M:0,FTM:0,PTS:0,REB:0,AST:0,TOV:0,BLK:0,STL:0}:null,minutes:status==='APPEARED'?1:null,minutes_precision:status==='APPEARED'?'rounded_whole_minutes':null,categories:status==='APPEARED'?f.categories.map(c=>({code:c.code,units:c.units,observed:0})):[],correction_revision:1,previous_outcome_id:null};
  const outcome=projection(o,'outcomes','synthetic outcome'),grades=forecasts.map((row,n)=>{const forecast=originalProduction(row),g={schema_version:'nba-sdv-production-grade-v1',...shared,model_key:forecast.model_key,forecast_id:forecast.forecast_id,outcome_id:outcome.original_id,graded_at:stamp(at+2000),status:status==='APPEARED'?'SCORED':status==='DNP'?'DNP_NOT_SCORED':status,categories:status==='APPEARED'?forecast.categories.map(c=>({code:c.code,observed:0,crps:'0',log_loss:'0',log_loss_status:'FINITE',brier:['DD','TD'].includes(c.code)?'0':null})):[],financial_settlement:'NOT_EVALUATED',qualification:'UNAVAILABLE',correction_revision:1,previous_grade_id:null};return projection(g,'grades','synthetic grade '+n);});
  return repack(bundle,[...all(bundle),outcome,...grades],stamp(at+60000));
}

function validate(bundle){return validateProductionCollection(bundle.index,bundle.pages);}
function mutate(bundle,suffix,fn){const row=of(bundle,suffix)[0],at=all(bundle).indexOf(row),records=all(bundle),body=originalProduction(row);fn(body,row);records[at]=wrap(row,body);return repack(bundle,records);}

test('actual Python normalized development fixture independently validates every typed body and hash',async()=>{
  const b=copy(),before=JSON.stringify(b);validateProductionIndex(b.index);const c=validate(b);await verifyProductionHashes(b.index,b.pages,webcrypto);
  assert.equal(c.forecasts.length,2);assert.equal(c.inputs.length,1);assert.equal(c.plans[0].events.length,3);assert.equal(c.forecasts.every(r=>r.body.categories.length===14&&r.body.issued_at===null),true);assert.equal(JSON.stringify(b),before);
  assert.deepEqual(productionViewCounts(c),{upcoming:0,history:0,development:2,genuine:0,eligible:0});
  const html=renderProductionResearch(c,{now:Date.parse(b.index.generated_at)});assert.match(html,/Development preview · not issued/);assert.match(html,/Synthetic Player/);assert.match(html,/Conditional on the player appearing/);assert.match(html,/No genuinely issued recurring NBA forecast/);assert.match(html,/execution is not guaranteed/);assert.match(html,/CC BY 4.0/);
});

test('history-based minutes render their mean and interval without changing originals or promising participation',()=>{
  const b=mutate(copy(),'forecast',f=>{f.reported_minutes={pmf:[{value:12,probability:'0.25'},{value:28,probability:'0.75'}],mean:'24',interval80:[12,28],precision:'reported_source_precision_not_exact_workload'};}),c=validate(b),before=JSON.stringify(c.records);
  const html=renderProductionResearch(c,{category:'REB',limit:1,now:Date.parse(b.index.generated_at)});
  assert.match(html,/History-based minutes estimate: <strong>24 minutes<\/strong>; 80% interval 12–28 minutes/);
  assert.match(html,/Conditional on appearance; this is not confirmed playing time/);
  assert.match(html,/Injury, starting-lineup and confirmed-participation information are unavailable/);
  assert.match(html,/<th scope="row">REB/);assert.doesNotMatch(html,/<th scope="row">PTS/);
  assert.equal(JSON.stringify(c.records),before);assert.equal(c.forecasts.every(r=>r.body.categories.length===14&&r.body.issued_at===null),true);
  // Rendering-boundary injection only; it is not new source/admission evidence.
  const display=structuredClone(c),row=display.records.find(r=>originalProduction(r).schema_version==='nba-sdv-production-forecast-v1'),body=originalProduction(row);
  Object.assign(row,wrap(row,{...body,player_label:'<img src=x onerror="alert(1)"> & Player'}));
  const escapedHtml=renderProductionResearch(display,{limit:1,now:Date.parse(b.index.generated_at)});
  assert.match(escapedHtml,/&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt; &amp; Player/);assert.doesNotMatch(escapedHtml,/<img src=x/);
  assert.match(escapedHtml,/History-based minutes estimate: <strong>24 minutes<\/strong>/);
});

test('empty production index remains an honest separate inactive channel',async()=>{
  const b=repack(copy(),[]),c=validate(b);await verifyProductionHashes(b.index,b.pages,webcrypto);assert.equal(c.forecasts.length,0);assert.equal(c.index.counts.pending_grades,0);assert.match(renderProductionResearch(c),/No genuinely issued recurring NBA forecast/);assert.equal(renderProductionResearch(c,{nbaSelected:false}),'');
  const descriptor={path:`sdv-production.${hash(b.index)}.json`,sha256:hash(b.index),generated_at:b.index.generated_at,status:'PRODUCTION_RESEARCH',retained:false,error:null};validateProductionDescriptor(descriptor,b.index.generated_at);assert.throws(()=>validateProductionDescriptor({...descriptor,path:'../production.json'},b.index.generated_at));assert.throws(()=>validateProductionDescriptor({...descriptor,status:'DAILY_SNAPSHOT_RESEARCH'},b.index.generated_at));
});

test('invented authorized prospective wire clocks admit only timely recovered originals',async()=>{
  const b=prospective(),c=validate(b);await verifyProductionHashes(b.index,b.pages,webcrypto);assert.equal(productionViewCounts(c,{now:Date.parse(b.index.generated_at)}).upcoming,2);assert.equal(productionViewCounts(c,{now:Date.parse(c.forecasts[0].body.event_starts_at)}).history,2);
  const html=renderProductionResearch(c,{category:'REB',window:'24h',limit:1,now:Date.parse(b.index.generated_at)});assert.match(html,/Issued 89\.8 minutes/);assert.match(html,/id="more-production"/);assert.match(html,/Publisher asset age at verification/);assert.match(html,/<th scope="row">REB/);assert.doesNotMatch(html,/<th scope="row">PTS/);
  const newer=mutate(b,'run',a=>{a.head_sha='b'.repeat(40);const run=JSON.parse(Buffer.from(a.run_original.base64,'base64').toString('utf8'));run.head_sha=a.head_sha;const raw=JSON.stringify(run);a.run_original={base64:Buffer.from(raw).toString('base64'),bytes:Buffer.byteLength(raw),sha256:hash(raw)};});const recovered=validate(newer);await verifyProductionHashes(newer.index,newer.pages,webcrypto);assert.equal(recovered.authorizations[0].head_sha,'b'.repeat(40));assert.equal(recovered.forecasts[0].body.producer_binding.commit,'a'.repeat(40));
});

test('genuine mode cannot borrow old daily protocol, omit authority or change exact input references',()=>{
  for(const change of ['protocol','lane','authority','identity','reference','input_mode','conditioning'])assert.throws(()=>{let b=prospective();if(change==='authority')b=repack(b,all(b).filter(r=>originalProduction(r).schema_version!=='nba-sdv-production-run-v1'));else if(change==='input_mode')b=mutate(b,'input',i=>i.mode='DEVELOPMENT_ONLY');else b=mutate(b,'forecast',f=>{if(change==='protocol')f.protocol_id='NBA-SDV-DAILY-001';if(change==='lane')f.evidence_lane='DAILY_SNAPSHOT_PROSPECTIVE';if(change==='identity')f.player_label='Unverified renamed subject';if(change==='reference')f.input_ref=ref('input_captures','foreign input');if(change==='conditioning')f.conditioning='UNCONDITIONAL';});validate(b);},undefined,change);
});

test('stale, missing metadata clocks, changed event/capture windows and impossible combinations reject',()=>{
  for(const change of ['stale','metadata','post_start','cohort','window','pmf','combination','law']){let b=prospective();if(['stale','metadata','post_start','cohort','window'].includes(change))b=mutate(b,'input',i=>{if(change==='stale')i.sources[0].publisher_updated_at='2026-01-01T00:00:00.000000Z';if(change==='metadata'){i.sources[0].metadata_observation_status='UNKNOWN';i.sources[0].metadata_retrieved_at=null;i.sources[0].metadata_retrieval_started_at=null;}if(change==='post_start')i.normalized_at=i.event.event_starts_at;if(change==='cohort')i.candidates[0].player_id='999999';if(change==='window')i.sources[0].metadata_retrieval_started_at=stamp(Date.parse(i.event.event_starts_at)-3*3600000);});else b=mutate(b,'forecast',f=>{if(change==='pmf')f.categories[0].pmf[0].probability='0.5';if(change==='combination'){f.categories.find(c=>c.code==='PRA').pmf=[{value:1,probability:'1'}];f.categories.find(c=>c.code==='PRA').mean='1';f.categories.find(c=>c.code==='PRA').interval80=[1,1];}if(change==='law')f.producer_binding.law_sha256.R0='f'.repeat(64);});assert.throws(()=>validate(b),undefined,change);}
});

test('late or unacknowledged originals remain visible evidence without timely eligibility',()=>{
  let b=prospective(),row=of(b,'forecast')[0];row.admission.remote_recovered_at=stamp(Date.parse(originalProduction(row).generation_started_at)+301000);b=repack(b,all(b),stamp(Date.parse(row.admission.remote_recovered_at)+1000));assert.throws(()=>validate(b),/timely durable completion/);row=of(b,'forecast')[0];row.admission.eligible=false;row.admission.reasons=['SYNTHETIC late original'];b=repack(b);const c=validate(b);assert.equal(c.index.counts.eligible_forecasts,1);assert.equal(productionViewCounts(c,{now:Date.parse(b.index.generated_at)}).history,1);
  assert.equal(c.index.counts.genuine_forecasts,1);assert.equal(productionViewCounts(c,{now:Date.parse(b.index.generated_at)}).genuine,1);assert.match(renderProductionResearch(c,{view:'history',now:Date.parse(b.index.generated_at)}),/not admitted to prospective grading/);row.admission.remote_recovered_at=null;row.admission.archive_ref=null;row.admission.reasons=['SYNTHETIC missing acknowledgment'];validate(repack(b));
});

test('checksum verification preserves numeric spelling and rejects modified probability bytes',async()=>{
  const b=copy(),row=of(b,'forecast')[0];row.record_json=row.record_json.replace('"value":0','"value":0.0');row.original_id=hash(row.record_json);const changed=repack(b);await verifyProductionHashes(changed.index,changed.pages,webcrypto);
  row.record_json=row.record_json.replace('"probability":"1"','"probability":"0.5"');const bad=repack(b);await assert.rejects(verifyProductionHashes(bad.index,bad.pages,webcrypto),/original byte hash/);
  const invalid={...row,record_json:'{"mode":"DEVELOPMENT_ONLY","mode":"PROSPECTIVE_RESEARCH"}'};assert.throws(()=>originalProduction(invalid),/Duplicate production JSON key/);
  assert.throws(()=>originalProduction({...row,record_json:'{"overflow":1e999}'}),/Non-finite production JSON number/);
});

test('DNP uses one shared outcome and separate grades without numerical zero scores',async()=>{
  const b=withOutcome(),c=validate(b);await verifyProductionHashes(b.index,b.pages,webcrypto);assert.equal(c.outcomes.length,1);assert.equal(c.grades.length,2);assert.equal(c.index.counts.pending_grades,0);assert.equal(c.index.counts.dnp_grades,2);assert.equal(c.grades.every(r=>r.body.categories.length===0),true);
  const s=summarizeProductionPerformance(c);assert.equal(s.counts.scored,0);assert.equal(s.counts.dnp,2);assert.match(renderProductionResearch(c,{view:'history',now:Date.parse(b.index.generated_at)}),/Did not play; forecast not scored/);
});

test('scored grades independently recompute and stay grouped by exact production model identity',async()=>{
  const b=withOutcome('APPEARED'),c=validate(b);await verifyProductionHashes(b.index,b.pages,webcrypto);const s=summarizeProductionPerformance(c);assert.equal(s.groups.length,2);assert.equal(s.groups.every(g=>g.protocol_id==='NBA-SDV-PRODUCTION-001'&&g.conditioning==='CONDITIONAL_ON_APPEARANCE'&&g.categories.length===14),true);assert.equal(s.groups[0].categories[0].mean_crps,0);assert.equal(summarizeProductionPerformance(c,{model:'R0',category:'REB'}).groups.length,1);assert.equal(summarizeProductionPerformance(c,{dateFrom:'2026-02-30'}).valid,false);
  const html=renderProductionResearch(c,{performance:true});for(const name of ['productionModel','productionDateFrom','productionDateTo','productionLead'])assert.match(html,new RegExp(`data-filter="${name}"`));assert.match(html,/not lifetime performance/);assert.match(html,/CDF calibration/);
});

test('invalid outcome status, season, identities and inconsistent grades reject after rehashing',()=>{
  for(const change of ['status','season','snapshot','counts','grade']){let b=withOutcome('APPEARED');if(change==='grade')b=mutate(b,'grade',g=>g.categories[0].crps='999');else b=mutate(b,'outcome',o=>{if(change==='status')o.status='ASSUMED_FINAL';if(change==='season')o.season_type='3';if(change==='snapshot')o.event_snapshot_id='f'.repeat(64);if(change==='counts')o.primitives.FGM=1;});assert.throws(()=>validate(b),undefined,change);}
});

test('corrections append originals and remove superseded outcome grades; forks reject',()=>{
  const b=withOutcome(),old=of(b,'outcome')[0],o=originalProduction(old),replacement=projection({...o,status:'NONFINAL',source_observed_at:stamp(Date.parse(o.source_observed_at)+3000),normalized_at:stamp(Date.parse(o.normalized_at)+3000),correction_revision:2,previous_outcome_id:o.outcome_id},'outcomes','synthetic outcome correction');const corrected=repack(b,[...all(b),replacement]);const c=validate(corrected);assert.equal(c.outcomes.length,2);assert.equal(c.grades.length,2);assert.equal(activeProductionGrades(c).length,0);assert.equal(c.index.counts.pending_grades,2);
  const fork=projection({...originalProduction(replacement),status:'UNRESOLVED'},'outcomes','synthetic forbidden fork');assert.throws(()=>validate(repack(b,[...all(corrected),fork])),/Multiple active production outcomes/);
});

test('duplicate originals preserve distinct receipt references and reject conflicting admission',()=>{
  const b=prospective(),input=of(b,'input')[0],duplicate={...structuredClone(input),reference:ref('input_captures','second receipt same input')};const duplicated=repack(b,[...all(b),duplicate]);duplicated.index.counts=b.index.counts;const c=validate(duplicated);assert.equal(c.inputs.length,1);assert.equal(c.records.length,all(b).length+1);
  const forecast={...structuredClone(of(b,'forecast')[0]),reference:ref('forecasts','conflicting repeated original')};forecast.admission.eligible=false;forecast.admission.reasons=['SYNTHETIC conflicting duplicate admission'];assert.throws(()=>validate(repack(b,[...all(b),forecast])),/Conflicting admission/);
});

test('all pages must be present and bounded, with safe names and exact count/hash bindings',async()=>{
  const b=copy(),rows=all(b),split=[rows.slice(0,2),rows.slice(2)].map(records=>seal({schema_version:'nba-sdv-production-public-page-v1',protocol_id:b.index.protocol_id,generated_at:b.index.generated_at,game_date:b.index.dates[0].game_date,records},'page_id'));b.pages=split;b.index.pages=split.map(page=>({path:`sdv-production-page.${hash(page)}.json`,sha256:hash(page),generated_at:page.generated_at,game_date:page.game_date,record_count:page.records.length}));b.index=seal(b.index,'index_id');validate(b);await verifyProductionHashes(b.index,b.pages,webcrypto);assert.throws(()=>validateProductionCollection(b.index,b.pages.slice(0,1)),/omitted a declared page/);assert.throws(()=>validateProductionIndex({...b.index,pages:[{...b.index.pages[0],path:'../outside.json'}]}),/page path/);assert.throws(()=>validateProductionPage({...b.pages[0],records:[]},b.index.pages[0]),/publication page/);
});

test('view-time source ages, actual clocks and source IDs remain honest without mutating originals',()=>{
  const b=copy(),c=validate(b),before=JSON.stringify(c.records),html=renderProductionResearch(c,{now:Date.parse('2026-11-01T00:00:00.000000Z')});assert.match(html,/now older than the operating limit/);assert.match(html,/Actual issue time: Not issued/);assert.match(html,/Upstream observation: UNKNOWN/);assert.match(html,/metadata retrieved/);assert.match(html,/NBA \/ ESPN namespace/);assert.match(html,/That planned time has passed; no newer run evidence is published here/);assert.match(html,/Last published-input retrieval/);assert.equal(JSON.stringify(c.records),before);
});

test('multiple cycles retain exact original joins and covered records cannot escape the declared dates',()=>{
  const first=prospective(1),second=prospective(2),both=repack(second,[...all(first),...all(second)]),c=validate(both),summary=summarizeProductionPerformance(c);assert.equal(c.forecasts.length,4);assert.equal(summary.groups.length,2);assert.equal(summary.groups.every(g=>g.cycle_ids.length===2),true);assert.equal(summary.counts.players,1);assert.equal(summary.counts.events,1);
  const excluded=structuredClone(both);excluded.index.coverage.to_game_date=excluded.index.generated_at.slice(0,10);assert.throws(()=>validate(excluded),/date or clock|date coverage/);
  const outcomeBundle=withOutcome(),foreignCycle=originalProduction(of(second,'forecast')[0]).cycle_id;assert.throws(()=>validate(mutate(outcomeBundle,'outcome',o=>o.cycle_id=foreignCycle)),/identity, season or actual evidence clocks/);
});

test('manifest7 isolates checksum-consistent invalid production meaning and preserves six historical bundles',async()=>{
  const broken=mutate(copy(),'forecast',f=>f.conditioning='UNCONDITIONAL'),old=typedFixture(),sport=old.sport,templateForecast=structuredClone(sport.forecasts[0]),templateGrade=structuredClone(sport.performance[0]);sport.forecasts=[];sport.performance=[];
  for(let n=0;n<6;n++){const f=seal({...templateForecast,player_id:'synthetic-history-'+n,player_label:'Synthetic Historical Player '+n},'forecast_id');sport.forecasts.push(f);sport.performance.push(seal({...templateGrade,player_id:f.player_id,forecast_id:f.forecast_id},'grade_id'));}
  const sportSha=hash(sport),reference={...old.reference,path:`nba.${sportSha}.json`,sha256:sportSha},descriptor={path:`sdv-production.${hash(broken.index)}.json`,sha256:hash(broken.index),generated_at:broken.index.generated_at,status:'PRODUCTION_RESEARCH',retained:false,error:null};
  const manifest={...old.manifest,schema_version:7,published_at:broken.index.generated_at,sports:[reference],production_research:descriptor,production_research_error:null};for(const channel of ['pros004','display','offers','paired_research','daily_research']){manifest[channel]=null;manifest[channel+'_error']='Explicitly absent from this synthetic isolation fixture.';}const signed=seal(manifest,'snapshot_id'),assets=new Map([['./data/manifest.json',signed],[`./data/${reference.path}`,sport],[`./data/${descriptor.path}`,broken.index],...broken.pages.map((p,n)=>[`./data/${broken.index.pages[n].path}`,p])]);
  const originalNow=Date.now;Date.now=()=>Date.parse(signed.published_at)+1000;
  try{const snapshot=await loadSnapshot(async url=>assets.has(url)?new Response(canonical(assets.get(url))):new Response('',{status:404}),webcrypto);assert.equal(snapshot.productionResearch,null);assert.match(snapshot.productionResearchError,/forecast meaning/);assert.equal(snapshot.sports.length,1);assert.equal(snapshot.sports[0].forecasts.length,6);assert.equal(snapshot.sports[0].performance.length,6);assert.deepEqual(snapshot.sports[0].candidates,[]);assert.deepEqual(snapshot.sports[0].tickets,[]);}finally{Date.now=originalNow;}
});

test('date-partitioned lazy loading verifies only the exact selected graph and keeps global metadata distinct',async()=>{
  const first=prospective(1),second=prospective(2),b=repack(second,[...all(first),...all(second)]),firstDate=b.index.dates[0].game_date,secondDate=b.index.dates[1].game_date,now=Date.parse(first.index.generated_at);
  assert.equal(selectProductionDate(b.index,{view:'upcoming',now}),firstDate);assert.equal(selectProductionDate(b.index,{view:'history',now}),secondDate);assert.equal(selectProductionDate(b.index,{gameDate:secondDate,now}),secondDate);assert.throws(()=>selectProductionDate(b.index,{gameDate:'2099-01-01'}),/unavailable/);
  const urls=[],assets=new Map(b.pages.map((page,n)=>[`./data/${b.index.pages[n].path}`,page]));const c=await loadProductionDate({index:b.index},{gameDate:firstDate,now,cryptoProvider:webcrypto,fetcher:async url=>{urls.push(url);return assets.has(url)?new Response(canonical(assets.get(url))):new Response('',{status:404});}});
  assert.deepEqual(urls,b.index.pages.filter(p=>p.game_date===firstDate).map(p=>'./data/'+p.path));assert.equal(c.loaded_game_date,firstDate);assert.equal(c.loaded_counts.genuine_forecasts,2);assert.equal(c.index.counts.genuine_forecasts,4);assert.equal(c.forecasts.every(f=>f.body.event_starts_at.startsWith(firstDate)),true);assert.equal(summarizeProductionPerformance(c).counts.eligible,2);
  const html=renderProductionResearch(c,{now});assert.match(html,/data-filter="productionDate"/);assert.match(html,/reports 4 admitted research bundles across 2 indexed dates/);assert.match(html,/Verified full records loaded for/);assert.match(html,/Other dates have index metadata only until selected/);assert.match(renderProductionResearch(c,{performance:true,now}),/data-filter="productionDate"/);
  const selected=b.pages.filter(p=>p.game_date===firstDate);await verifyProductionHashes(b.index,selected,webcrypto,{gameDate:firstDate});assert.throws(()=>validateProductionCollection(b.index,selected),/omitted a declared page/);await assert.rejects(verifyProductionHashes(b.index,selected,webcrypto),/omitted a declared page/);assert.throws(()=>validateProductionCollection(b.index,b.pages,{gameDate:firstDate}),/omitted a declared page/);
  assert.equal(PRODUCTION_MAX_TOTAL_BYTES,512*1024*1024);assert.equal(PRODUCTION_CLIENT_MAX_BYTES,64*1024*1024);
});

function gradingStatus(bundle,{pending=[],quota=[],unscored=[],complete=true,offset=1000,cycle=null,shard=0,task=null}={}) {
  const f=originalProduction(of(bundle,'forecast')[0]),at=Date.parse(bundle.index.generated_at)+offset,archive={tag:'nml-nba-records-v1-202610',sha256:'9'.repeat(64),name:`object-${'9'.repeat(64)}.z`,bytes:128};
  const body={schema_version:'nba-sdv-production-status-v1',protocol_id:f.protocol_id,plan_id:f.plan_id,cycle_id:cycle??f.cycle_id,phase:'GRADE',status:complete?'PARTIAL':'FAILED',details:{task_id:task??hash('SYNTHETIC GRADE TASK '+f.cycle_id+' '+shard),shard_index:shard,player_ids:originalProduction(of(bundle,'input')[0]).shards[shard],processing_complete:complete,final_source_pack_ref:archive,grading:{outcomes:0,grades:0,pending,correction_quota_exhausted:quota,unscored_originals:unscored,unscored_reason:'ORIGINAL_NOT_TIMELY_ADMITTED'}},observed_at:stamp(at),run_id:123};return projection(body,'input_captures','SYNTHETIC GRADING '+at+' '+(cycle??f.cycle_id));
}
function expectUnresolved(bundle) {
  bundle.index.counts={...bundle.index.counts,active_grades:0,scored_grades:0,dnp_grades:0,pending_grades:2};for(const day of bundle.index.dates)day.counts={...day.counts,active_grades:0,scored_grades:0,dnp_grades:0,pending_grades:2};bundle.index=seal(bundle.index,'index_id');return bundle;
}

test('latest completed grading evidence excludes earlier scores after an unresolved correction without overwriting them',()=>{
  const original=withOutcome('APPEARED'),pid=originalProduction(of(original,'forecast')[0]).player_id,status=gradingStatus(original,{quota:[pid]}),b=expectUnresolved(repack(original,[...all(original),status],stamp(Date.parse(original.index.generated_at)+5000))),c=validate(b);assert.equal(c.grades.length,2);assert.equal(activeProductionGrades(c).length,2);assert.equal(c.index.counts.scored_grades,0);assert.equal(c.index.counts.pending_grades,2);const s=summarizeProductionPerformance(c);assert.equal(s.counts.scored,0);assert.equal(s.counts.pending,2);assert.equal(s.rows.every(r=>r.status==='UNRESOLVED_LATER_CORRECTION'),true);assert.match(renderProductionResearch(c,{view:'history',now:Date.parse(b.index.generated_at)}),/earlier retained grades are excluded/);assert.match(renderProductionResearch(c,{view:'history',now:Date.parse(b.index.generated_at)}),/Retained original statistical grade receipts/);
  const failed=gradingStatus(b,{complete:false,offset:1000}),still=expectUnresolved(repack(b,[...all(b),failed],stamp(Date.parse(b.index.generated_at)+5000)));assert.equal(summarizeProductionPerformance(validate(still)).rows.every(r=>r.status==='UNRESOLVED_LATER_CORRECTION'),true);
  const next=gradingStatus(still,{pending:[pid],offset:1000}),pending=expectUnresolved(repack(still,[...all(still),next],stamp(Date.parse(still.index.generated_at)+5000)));assert.equal(summarizeProductionPerformance(validate(pending)).rows.every(r=>r.status==='PENDING_FINAL_EVIDENCE'),true);
  assert.deepEqual(of(pending,'grade').map(r=>r.record_json),of(original,'grade').map(r=>r.record_json));
});

test('grading flags are scoped to the exact original cycle and malformed player lists reject',()=>{
  const b=withOutcome('APPEARED'),pid=originalProduction(of(b,'forecast')[0]).player_id,foreign=gradingStatus(b,{quota:[pid],cycle:'prod-20990101-999-aaaaaaaaaaaa'}),other=repack(b,[...all(b),foreign],stamp(Date.parse(b.index.generated_at)+5000));assert.throws(()=>validate(other),/exact bound input shard/);
  const invalid=gradingStatus(b,{quota:['not-a-stable-id']}),bad=repack(b,[...all(b),invalid],stamp(Date.parse(b.index.generated_at)+5000));assert.throws(()=>validate(bad),/unresolved grading player identity/);
});

test('complete six-key grading status preserves a late unscored peer without counting it as an eligible grade',()=>{
  const b=withOutcome('APPEARED'),late=of(b,'forecast').find(row=>originalProduction(row).model_key==='K0'),f=originalProduction(late),pid=f.player_id;late.admission={eligible:false,local_completed_at:late.admission.local_completed_at,remote_recovered_at:null,reasons:['REMOTE_RECOVERY_UNACKNOWLEDGED'],archive_ref:null};const kept=all(b).filter(row=>{const body=originalProduction(row);return body.schema_version!=='nba-sdv-production-grade-v1'||body.forecast_id!==late.original_id;});
  const status=gradingStatus(b,{unscored:[pid+':K0']}),body=originalProduction(status);body.details.grading.outcomes=1;body.details.grading.grades=1;const completed=wrap(status,body),result=repack(b,[...kept,completed],stamp(Date.parse(b.index.generated_at)+5000)),c=validate(result),summary=summarizeProductionPerformance(c);
  assert.equal(c.forecasts.length,2);assert.equal(c.grades.length,1);assert.equal(c.loaded_counts.genuine_forecasts,1);assert.equal(c.loaded_counts.active_grades,1);assert.equal(c.loaded_counts.scored_grades,1);assert.equal(c.loaded_counts.pending_grades,0);assert.equal(summary.counts.scored,1);assert.equal(summary.counts.excluded_ineligible,1);assert.equal(summary.groups.length,1);assert.equal(summary.groups[0].model_key,'R0');
  for(const change of ['reason','duplicate','model','player']){const invalid=originalProduction(completed);if(change==='reason')invalid.details.grading.unscored_reason='NO_OUTCOME_ASSUMED_ZERO';if(change==='duplicate')invalid.details.grading.unscored_originals=[pid+':K0',pid+':K0'];if(change==='model')invalid.details.grading.unscored_originals=[pid+':S0'];if(change==='player')invalid.details.grading.unscored_originals=['unknown:K0'];assert.throws(()=>validate(repack(b,[...kept,wrap(completed,invalid)],result.index.generated_at)),/unscored original reason or player\/model identity/,change);}
});


function withSecondShardScores() {
  const b=withOutcome('APPEARED'),i=originalProduction(of(b,'input')[0]),candidate=i.candidates.find(c=>c.player_id===i.shards[1][0]),changed={player_id:candidate.player_id,player_label:candidate.player_label,team_id:candidate.team_id,opponent_id:candidate.opponent_id};
  const forecasts=of(b,'forecast').map(row=>{const f=originalProduction(row);return projection({...f,...changed},'forecasts','SYNTHETIC SECOND SHARD '+f.model_key,structuredClone(row.admission));}),outcome=originalProduction(of(b,'outcome')[0]),additionalOutcome=projection({...outcome,player_id:changed.player_id,team_id:changed.team_id,opponent_id:changed.opponent_id},'outcomes','SYNTHETIC SECOND SHARD OUTCOME');
  const grades=of(b,'grade').map(row=>{const g=originalProduction(row),forecast=forecasts.find(f=>originalProduction(f).model_key===g.model_key);return projection({...g,player_id:changed.player_id,team_id:changed.team_id,opponent_id:changed.opponent_id,forecast_id:forecast.original_id,outcome_id:additionalOutcome.original_id},'grades','SYNTHETIC SECOND SHARD GRADE '+g.model_key);});
  return repack(b,[...all(b),...forecasts,additionalOutcome,...grades]);
}

test('later healthy shard grading cannot clear a different shard correction or pending state',async()=>{
  for(const kind of ['quota','pending']){const original=withSecondShardScores(),input=originalProduction(of(original,'input')[0]),pid=input.shards[0][0],blocked=gradingStatus(original,{[kind]:[pid],shard:0}),healthy=gradingStatus(original,{shard:1,offset:2000}),b=repack(original,[...all(original),blocked,healthy],stamp(Date.parse(original.index.generated_at)+5000));
    b.index.counts={...b.index.counts,active_grades:2,scored_grades:2,pending_grades:2};for(const date of b.index.dates)date.counts={...date.counts,active_grades:2,scored_grades:2,pending_grades:2};b.index=seal(b.index,'index_id');
    const c=validate(b);await verifyProductionHashes(b.index,b.pages,webcrypto);const summary=summarizeProductionPerformance(c);assert.equal(c.grades.length,4);assert.equal(c.loaded_counts.scored_grades,2);assert.equal(c.loaded_counts.pending_grades,2);assert.equal(summary.counts.scored,2);assert.equal(summary.rows.filter(row=>row.player_id===pid).every(row=>row.status===(kind==='quota'?'UNRESOLVED_LATER_CORRECTION':'PENDING_FINAL_EVIDENCE')),true);assert.equal(summary.rows.filter(row=>row.player_id===input.shards[1][0]).every(row=>row.status==='SCORED'),true);
  }
});

test('checksum-consistent foreign grading players, unbound tasks and mutable task shards reject',async()=>{
  const b=withSecondShardScores(),input=originalProduction(of(b,'input')[0]),valid=gradingStatus(b,{quota:[input.shards[0][0]],shard:0}),good=originalProduction(valid);
  for(const change of ['foreign_flag','foreign_unscored','foreign_cohort','unbound_cycle','unknown_shard','invalid_task','missing_task','changed_task_shard','changed_shard_task','duplicate_logical_input']){const body=structuredClone(good),extra=[];if(change==='foreign_flag')body.details.grading.pending=[input.shards[1][0]];if(change==='foreign_unscored')body.details.grading.unscored_originals=[input.shards[1][0]+':R0'];if(change==='foreign_cohort')body.details.player_ids=[input.shards[1][0]];if(change==='unbound_cycle')body.cycle_id='prod-20990101-999-aaaaaaaaaaaa';if(change==='unknown_shard')body.details.shard_index=99;if(change==='invalid_task')body.details.task_id='not-a-task-hash';if(change==='missing_task')delete body.details.task_id;if(change==='changed_task_shard'){body.details.shard_index=1;body.details.player_ids=input.shards[1];body.details.grading.correction_quota_exhausted=[];body.observed_at=stamp(Date.parse(body.observed_at)+1000);extra.push(valid);}if(change==='changed_shard_task'){body.details.task_id=hash('SYNTHETIC REPLACEMENT TASK SAME SHARD');body.observed_at=stamp(Date.parse(body.observed_at)+1000);extra.push(valid);}if(change==='duplicate_logical_input'){const duplicate=structuredClone(input);duplicate.normalized_at=stamp(Date.parse(duplicate.normalized_at)+1000);extra.push(projection(duplicate,'input_captures','SYNTHETIC ALTERED LOGICAL INPUT'));}
    const changed=repack(b,[...all(b),...extra,projection(body,'input_captures','SYNTHETIC BAD SHARD '+change)],stamp(Date.parse(b.index.generated_at)+5000));await verifyProductionHashes(changed.index,changed.pages,webcrypto);assert.throws(()=>validate(changed),/exact bound input shard|foreign shard player|immutable shard binding|immutable task identity|conflicting exact input identities/,change);
  }
});


test('configured cron check before the first enabled game date is the next actual quarter-hour slot',()=>{
  const b=repack(copy(),[],'2026-10-23T13:17:00.000000Z');assert.equal(b.index.policy.enabled_after,'2026-10-24T00:00:00.000000Z');assert.equal(b.index.operations.next_configured_check_at,'2026-10-23T13:32:00.000000Z');validate(b);
  b.index.operations.next_configured_check_at='2026-10-24T00:02:00.000000Z';b.index=seal(b.index,'index_id');assert.throws(()=>validate(b),/configured next check/);
});

function issuanceStatuses(bundle,{number=1,openedOffset=1000,closedOffset=60000,shard=0,task=null}={}) {
  const f=originalProduction(of(bundle,'forecast')[0]),input=originalProduction(of(bundle,'input')[0]),opened=Date.parse(f.cutoff_at)+openedOffset,details={task_id:task??hash('SYNTHETIC ISSUE TASK '+f.cycle_id+' '+shard),shard_index:shard,player_ids:input.shards[shard],error:null,final_source_pack_ref:null,processing_complete:false},identity={...details,run_id:123,run_attempt:1,opened_at:stamp(opened),attempt_number:number};
  delete identity.error;delete identity.final_source_pack_ref;delete identity.processing_complete;
  details.issuance_attempt={attempt_id:hash(identity),attempt_number:number,run_attempt:1,opened_at:stamp(opened),open_status_id:null,footprint_snapshot_ref:null,footprint_snapshot_id:null,footprint_recovered_at:null};
  const body={schema_version:'nba-sdv-production-status-v1',protocol_id:f.protocol_id,plan_id:f.plan_id,cycle_id:f.cycle_id,phase:'ISSUE',status:'ISSUANCE_ATTEMPT_OPEN',details,observed_at:stamp(opened),run_id:123},original=projection(body,'input_captures','SYNTHETIC OPEN '+number+' '+shard+' '+opened);
  if(closedOffset===null)return [original];
  const closed=structuredClone(body),at=Date.parse(f.cutoff_at)+closedOffset,sha=hash('SYNTHETIC FOOTPRINT '+number+' '+shard);closed.status='ISSUANCE_ATTEMPT_CLOSED';closed.observed_at=stamp(at);Object.assign(closed.details.issuance_attempt,{open_status_id:original.original_id,footprint_snapshot_ref:{tag:'nml-nba-records-v1-202610',name:`object-${sha}.z`,sha256:sha,bytes:128},footprint_snapshot_id:hash('SYNTHETIC SNAPSHOT MANIFEST '+number+' '+shard),footprint_recovered_at:stamp(at-1000)});
  return [original,projection(closed,'input_captures','SYNTHETIC CLOSED '+number+' '+shard+' '+at)];
}

test('typed issuance attempts preserve closed originals and a later unresolved OPEN without changing admission',async()=>{
  const b=prospective(),first=issuanceStatuses(b),second=issuanceStatuses(b,{number:2,openedOffset:70000,closedOffset:100000}),third=issuanceStatuses(b,{number:3,openedOffset:110000,closedOffset:null}),result=repack(b,[...all(b),...first,...second,...third]);
  const before=all(result).map(row=>row.record_json),c=validate(result);await verifyProductionHashes(result.index,result.pages,webcrypto);assert.equal(c.statuses.length,5);assert.equal(c.loaded_counts.genuine_forecasts,2);assert.equal(c.loaded_counts.pending_grades,2);assert.deepEqual(all(result).map(row=>row.record_json),before);
  assert.doesNotMatch(renderProductionResearch(c,{now:Date.parse(result.index.generated_at)}),/<h[1-6][^>]*>ISSUANCE_ATTEMPT_/);
});

test('checksum-consistent issuance status meaning and exact OPEN closure relationships fail closed',async()=>{
  const b=prospective(),[open,close]=issuanceStatuses(b);
  for(const change of ['phase','complete','cohort','unbound','missing','error','run_attempt','future_open','open_closure','close_clock','orphan','changed_run','changed_attempt','duplicate_close','skip_attempt','reordered_attempt']){
    let records=[open,close],body=originalProduction(change==='open_closure'||change==='future_open'||change==='run_attempt'||change==='phase'||change==='complete'||change==='cohort'||change==='unbound'||change==='missing'||change==='error'?open:close);
    if(change==='phase')body.phase='GRADE';if(change==='complete')body.details.processing_complete=true;if(change==='cohort')body.details.player_ids=['999999'];if(change==='unbound')body.cycle_id='prod-20990101-999-aaaaaaaaaaaa';if(change==='missing')delete body.details.issuance_attempt.run_attempt;if(change==='error')body.details.error='x'.repeat(1001);if(change==='run_attempt')body.details.issuance_attempt.run_attempt=0;if(change==='future_open')body.details.issuance_attempt.opened_at=stamp(Date.parse(body.observed_at)+1000);if(change==='open_closure')body.details.issuance_attempt.open_status_id='f'.repeat(64);if(change==='close_clock')body.details.issuance_attempt.footprint_recovered_at=stamp(Date.parse(body.observed_at)+1000);if(change==='orphan')body.details.issuance_attempt.open_status_id='f'.repeat(64);if(change==='changed_run')body.run_id=999;if(change==='changed_attempt')body.details.issuance_attempt.attempt_number=2;
    if(change==='duplicate_close'){const duplicate=structuredClone(body);duplicate.details.error='SYNTHETIC second closure';records.push(projection(duplicate,'input_captures','SYNTHETIC DUPLICATE CLOSURE'));}else if(change==='skip_attempt')records.push(...issuanceStatuses(b,{number:3,openedOffset:70000,closedOffset:null}));else if(change==='reordered_attempt')records.push(...issuanceStatuses(b,{number:2,openedOffset:50000,closedOffset:null}));else records=records.map(row=>row.original_id===(body.status==='ISSUANCE_ATTEMPT_OPEN'?open.original_id:close.original_id)?projection(body,'input_captures','SYNTHETIC INVALID ISSUE '+change):row);
    const result=repack(b,[...all(b),...records]);await assert.rejects(async()=>{validate(result);await verifyProductionHashes(result.index,result.pages,webcrypto);},/issuance|operating task|operating shard|grading task|unscored|bound input/i,change);
  }
});

test('issuance attempt hash is independently verified even when outer status and page checksums agree',async()=>{
  const b=prospective(),[opened]=issuanceStatuses(b,{closedOffset:null}),body=originalProduction(opened);body.details.issuance_attempt.attempt_id='f'.repeat(64);const result=repack(b,[...all(b),projection(body,'input_captures','SYNTHETIC INCORRECT ATTEMPT HASH')]);validate(result);await assert.rejects(verifyProductionHashes(result.index,result.pages,webcrypto),/issuance attempt identity checksum/);
});

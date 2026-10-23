// Shared invented wire graphs for Python/browser validation tests only.
// Adapted from existing SDV fixtures; no HTTP, model execution or genuine issue.
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {originalProduction, validateProductionCollection, activeProductionGrades} from '../production.mjs';

export const dailyFixtures=(()=>{
const canonical=v=>v&&typeof v==='object'?Array.isArray(v)?`[${v.map(canonical).join(',')}]`:`{${Object.keys(v).sort().map(k=>`${JSON.stringify(k)}:${canonical(v[k])}`).join(',')}}`:JSON.stringify(v);
const hash=v=>createHash('sha256').update(typeof v==='string'?v:canonical(v)).digest('hex');
const seal=(v,key)=>{const {[key]:_,...body}=v;return {...body,[key]:hash(body)};};
const fixture=JSON.parse(readFileSync(new URL('../../tests/fixtures/sdv-daily-synthetic.json',import.meta.url),'utf8'));
const copy=()=>structuredClone(fixture);
const ref=(kind,seed)=>({kind,record_id:hash('synthetic record '+seed),payload_sha256:hash('synthetic payload '+seed)});
const proof=body=>({base64:Buffer.from(JSON.stringify(body)).toString('base64'),sha256:hash(JSON.stringify(body))});

// This fixture changes no real records. Its invented clocks/proofs demonstrate
// browser admission checks; it is never publicly published or counted as genuine issuance.
function buildDaily() {
  const a=copy(),i=a.inputs[0],commit='a'.repeat(40);
  i.mode='PROSPECTIVE_RESEARCH';i.normalized_at='2026-10-22T23:59:59.000000Z';
  for(const s of i.sources){s.publisher_updated_at='2026-10-22T03:00:00.000000Z';s.retrieval_started_at='2026-10-22T23:59:00.000000Z';s.retrieved_at='2026-10-22T23:59:30.000000Z';}
  a.inputs[0]=seal(i,'input_id');
  for(const row of a.forecasts){const f=row.body;f.mode='PROSPECTIVE_RESEARCH';f.evidence_lane='DAILY_SNAPSHOT_PROSPECTIVE';f.producer_binding=seal({...f.producer_binding,commit},'binding_id');f.input_id=a.inputs[0].input_id;f.generation_started_at='2026-10-23T00:00:01.000000Z';f.generation_completed_at='2026-10-23T00:00:02.000000Z';f.verified_at='2026-10-23T00:00:03.000000Z';f.issued_at=f.verified_at;row.body=seal(f,'forecast_id');row.admission={eligible:true,local_persistence_completed_at:'2026-10-23T00:00:04.000000Z',remote_recovery_completed_at:'2026-10-23T00:01:00.000000Z',reasons:[]};}
  const confirmation=`APPROVE ${a.cycle.cycle_id} ${commit}`;
  const run=proof({id:123,run_attempt:1,event:'workflow_dispatch',path:'.github/workflows/sdv-daily.yml',status:'in_progress',conclusion:null,head_branch:'main',head_sha:'b'.repeat(40),run_started_at:'2026-10-22T22:00:00Z',actor:{login:'NickNicky19'},repository:{full_name:'NickNicky19/Nicks-multisport-lab-project'},display_title:'Synthetic Ω test metadata'});
  const event=proof({repository:{full_name:'NickNicky19/Nicks-multisport-lab-project'},sender:{login:'NickNicky19'},ref:'refs/heads/main',inputs:{cycle_id:a.cycle.cycle_id,producer_commit:commit,confirmation},synthetic_note:'UTF-8 Ω test only'});
  a.activation=seal({schema_version:'nba-sdv-daily-authorization-v1',protocol_id:a.protocol_id,cycle_id:a.cycle.cycle_id,cycle_digest:a.cycle.cycle_digest,policy_id:a.policy.policy_id,producer_commit:commit,producer_binding_id:a.forecasts[0].body.producer_binding.binding_id,repository:'NickNicky19/Nicks-multisport-lab-project',workflow_path:'.github/workflows/sdv-daily.yml',workflow_run_id:123,run_attempt:1,actor:'NickNicky19',run_head_sha:'b'.repeat(40),run_started_at:'2026-10-22T22:00:00.000000Z',checked_at:'2026-10-22T22:00:01.000000Z',confirmation,event_payload_base64:event.base64,event_payload_sha256:event.sha256,run_metadata_base64:run.base64,run_metadata_sha256:run.sha256,executed_file_sha256:a.forecasts[0].body.producer_binding.files},'authorization_id');
  a.generated_at='2026-10-23T00:02:00.000000Z';a.counts={development_forecasts:0,genuine_forecasts:8,eligible_forecasts:8,pending_grades:8};a.status='ISSUED';
  return seal(a,'asset_id');
}


return {prospective:buildDaily, development:copy, seal};
})();

export const productionFixtures=(()=>{
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
  const auth={schema_version:'nba-sdv-production-run-v1',protocol_id:p.protocol_id,repository:'NickNicky19/Nicks-multisport-lab-project',workflow_path:'.github/workflows/nba-operations.yml',event:'schedule',actor:'NickNicky19',run_id:123,run_attempt:1,head_sha:binding.commit,run_started_at:runStarted,verified_at:stamp(cutoff-59000),event_original:proof({repository:{full_name:'NickNicky19/Nicks-multisport-lab-project'},schedule:p.policy.cron,note:'SYNTHETIC Ω authority test'}),run_original:proof({id:123,run_attempt:1,event:'schedule',head_sha:binding.commit,head_branch:'main',path:'.github/workflows/nba-operations.yml',status:'in_progress',conclusion:null,repository:{full_name:'NickNicky19/Nicks-multisport-lab-project'},actor:{login:'NickNicky19'},triggering_actor:{login:'NickNicky19'},run_started_at:runStarted,note:'SYNTHETIC Ω run metadata'}),executed_files:binding.files};
  return repack(bundle,[planned,admitted,projection(auth,'input_captures','synthetic authority '+days),...forecasts],stamp(cutoff+120000));
}


return {prospective, development:copy, repack, all, of, wrap, stamp};
})();

export function contractFor(body,input){
  return {league:input.event.league,id_namespace:input.event.id_namespace,
    event_id:body.event_id,event_version:body.event_snapshot_id,event_starts_at:body.event_starts_at,
    player_id:body.player_id,player_label:body.player_label,team_id:body.team_id,opponent_id:body.opponent_id,
    stat:'PTS',units:'points',period:body.period,extra_time_policy:body.extra_time_policy,
    line:'12.5',side:'over',variant:'synthetic-standard',venue:'Synthetic Test Venue',product:'Synthetic Test Product',
    settlement_version:'synthetic-rules-v1',stat_definition:'Synthetic full-game points including overtime.',
    settlement_terms:{participation:'Synthetic appearance rule.',dnp:'Synthetic DNP rule.',postponement:'Synthetic postponement rule.',ties:'Synthetic ties rule.',official_stat_source:'Synthetic official source.',stat_corrections:'Synthetic corrections rule.'},
    evidence_lane:'REAL_TIME_CAPTURED',market_status:'PRE_GAME',observed_at:body.issued_at,imported_at:body.issued_at,
    source_updated_at:null,source_evidence:[],price_status:'PRICE_UNAVAILABLE',price:null,quote:null,qualification:'UNAVAILABLE'};
}
export function channelFixture(kind){
  if(kind==='daily'){
    const daily=dailyFixtures.prospective();
    return {channel:{daily},raw:daily,at:daily.generated_at,body:daily.forecasts[0].body,input:daily.inputs[0]};
  }
  const raw=productionFixtures.prospective(),production=validateProductionCollection(raw.index,raw.pages);
  return {channel:{production},raw,at:raw.index.generated_at,body:production.forecasts[0].body,input:production.inputs[0]};
}

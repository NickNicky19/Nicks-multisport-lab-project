import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash,webcrypto} from 'node:crypto';
import {validateDailyAsset,validateDailyDescriptor,verifyDailyHashes,dailyViewCounts,renderDailyResearch,activeDailyGrades} from '../sdv-daily.mjs';

const canonical=v=>v&&typeof v==='object'?Array.isArray(v)?`[${v.map(canonical).join(',')}]`:`{${Object.keys(v).sort().map(k=>`${JSON.stringify(k)}:${canonical(v[k])}`).join(',')}}`:JSON.stringify(v);
const hash=v=>createHash('sha256').update(typeof v==='string'?v:canonical(v)).digest('hex');
const seal=(v,key)=>{const {[key]:_,...body}=v;return {...body,[key]:hash(body)};};
const fixture=JSON.parse(readFileSync(new URL('../../tests/fixtures/sdv-daily-synthetic.json',import.meta.url),'utf8'));
const copy=()=>structuredClone(fixture);
const ref=(kind,seed)=>({kind,record_id:hash('synthetic record '+seed),payload_sha256:hash('synthetic payload '+seed)});
const proof=body=>({base64:Buffer.from(JSON.stringify(body)).toString('base64'),sha256:hash(JSON.stringify(body))});

// This fixture changes no real records. Its invented clocks/proofs demonstrate
// browser admission checks; it is never exported or counted as genuine issuance.
function prospective() {
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

function withDnp() {
  const a=prospective(),f=a.forecasts[0].body;a.generated_at='2026-10-23T03:01:00.000000Z';
  const common=Object.fromEntries(['cycle_id','mode','event_id','event_snapshot_id','player_id','team_id','opponent_id'].map(k=>[k,f[k]]));
  const o=seal({schema_version:'nba-sdv-daily-outcome-v1',protocol_id:a.protocol_id,...common,event_starts_at:f.event_starts_at,status:'DNP',source_refs:[ref('research_inputs','synthetic outcome raw')],source_observed_at:'2026-10-23T03:00:00.000000Z',normalized_at:'2026-10-23T03:00:01.000000Z',normalizer_version:'synthetic-dnp-test-v1',primitives:null,minutes:null,minutes_precision:null,categories:[]},'outcome_id');
  a.outcomes=[{reference:ref('outcomes','dnp'),body:o}];
  a.grades=a.forecasts.slice(0,2).map((row,index)=>({reference:ref('grades','dnp '+index),body:seal({schema_version:'nba-sdv-daily-grade-v1',protocol_id:a.protocol_id,...common,model_key:row.body.model_key,forecast_id:row.body.forecast_id,outcome_id:o.outcome_id,graded_at:'2026-10-23T03:00:02.000000Z',status:'DNP_NOT_SCORED',categories:[],financial_settlement:'NOT_EVALUATED',qualification:'UNAVAILABLE'},'grade_id')}));
  a.counts.pending_grades=6;return seal(a,'asset_id');
}

test('synthetic DEV candidate validates all14 categories without becoming issued',async()=>{
  const a=copy();validateDailyAsset(a,a.generated_at);await verifyDailyHashes(a,webcrypto);
  assert.equal(a.forecasts.length,8);assert.equal(a.forecasts.every(r=>r.body.categories.length===14),true);
  assert.deepEqual(dailyViewCounts(a),{upcoming:0,history:0,development:8,genuine:0,eligible:0});
  const html=renderDailyResearch(a,{now:Date.parse(a.generated_at)});
  assert.match(html,/Development preview · not issued/);assert.match(html,/Alex Caruso/);assert.match(html,/Conditional on this player appearing/);assert.match(html,/0 genuinely issued upcoming/);assert.match(html,/CC BY 4.0/);assert.match(html,/Upstream observation UNKNOWN/);assert.match(html,/Development generation [\d.]+ minutes before scheduled start/);assert.match(html,/Publisher asset age at generation/);
  assert.equal(renderDailyResearch(a,{nbaSelected:false}),'');
});

test('manifest descriptor remains versioned and independent from other channels',()=>{
  const d={path:`sdv-daily.${'a'.repeat(64)}.json`,sha256:'a'.repeat(64),generated_at:fixture.generated_at,status:'DAILY_SNAPSHOT_RESEARCH',retained:false,error:null};
  validateDailyDescriptor(d,fixture.generated_at);validateDailyDescriptor({...d,retained:true,error:'Retained last valid source asset.'},fixture.generated_at);
  for(const change of [{status:'RESEARCH_ONLY'},{path:'../daily.json'},{error:''},{generated_at:'2026-10-23T00:00:00.000000Z'}])assert.throws(()=>validateDailyDescriptor({...d,...change},fixture.generated_at));
});

test('synthetic exact dispatch, UTF8 originals and timely complete recovery admit genuine wire shape',async()=>{
  const a=prospective();validateDailyAsset(a,a.generated_at);await verifyDailyHashes(a,webcrypto);
  assert.equal(dailyViewCounts(a,{now:Date.parse(a.generated_at)}).upcoming,8);
  assert.equal(dailyViewCounts(a,{now:Date.parse(a.inputs[0].event.event_starts_at)}).upcoming,0);
  assert.equal(dailyViewCounts(a,{now:Date.parse(a.inputs[0].event.event_starts_at)}).history,8);
  const html=renderDailyResearch(a,{now:Date.parse(a.generated_at),window:'24h',category:'REB'});
  assert.match(html,/Actual issue time: 2026-10-23 00:00:03 UTC/);assert.match(html,/Synthetic away display fixture @ Synthetic home display fixture/);assert.doesNotMatch(html,/<td>PTS<\/td>/);assert.match(html,/<td>REB<\/td>/);
});

test('forged mode, missing activation, fixed cohort and source conflicts reject despite repaired seals',()=>{
  for(const mutation of ['mode','activation','cohort','event','stale','future','sourceclock','invented_observation','cutoff','participation','atoms']){
    const a=prospective();
    if(mutation==='mode')a.forecasts[0].body.mode='DEVELOPMENT_ONLY';
    if(mutation==='activation')a.activation=null;
    if(mutation==='cohort')a.inputs[0].candidates[0].player_id='999999';
    if(mutation==='event')a.inputs[0].event.event_id='999999';
    if(mutation==='stale')a.inputs[0].sources[0].publisher_updated_at='2026-10-20T00:00:00.000000Z';
    if(mutation==='future')a.inputs[0].sources[0].publisher_updated_at='2026-10-23T01:00:00.000000Z';
    if(mutation==='sourceclock')a.inputs[0].sources[0].upstream_observed_at='2026-10-22T00:00:00.000000Z';
    if(mutation==='invented_observation'){a.inputs[0].sources[0].upstream_observation_status='SUPPLIED';a.inputs[0].sources[0].upstream_observed_at='2026-10-22T00:00:00.000000Z';}
    if(mutation==='cutoff')a.forecasts[0].body.cutoff_at='2026-10-22T23:59:59.999999Z';
    if(mutation==='participation')a.forecasts[0].body.conditioning='UNCONDITIONAL';
    if(mutation==='atoms')a.forecasts[0].body.categories[0].pmf[0].probability='0.5';
    assert.throws(()=>validateDailyAsset(seal(a,'asset_id'),a.generated_at),undefined,mutation);
  }
});

test('late and unacknowledged originals survive but cannot recover as timely issuance',()=>{
  const a=prospective(),row=a.forecasts[0];a.generated_at='2026-10-23T00:06:00.000000Z';
  row.admission.remote_recovery_completed_at='2026-10-23T00:05:02.000000Z';
  assert.throws(()=>validateDailyAsset(a,a.generated_at),/actual persistence\/recovery timing/);
  row.admission.eligible=false;row.admission.reasons=['Actual independent recovery exceeded 300 seconds.'];a.counts.eligible_forecasts=7;a.status='PARTIAL';validateDailyAsset(seal(a,'asset_id'),a.generated_at);
  assert.equal(dailyViewCounts(a,{now:Date.parse(a.generated_at)}).upcoming,7);assert.equal(dailyViewCounts(a,{now:Date.parse(a.generated_at)}).history,1);
  row.admission.remote_recovery_completed_at=null;row.admission.reasons=['Remote completion remains unacknowledged.'];validateDailyAsset(seal(a,'asset_id'),a.generated_at);
  row.admission.eligible=true;row.admission.reasons=[];assert.throws(()=>validateDailyAsset(a,a.generated_at));
  row.admission.remote_recovery_completed_at='2026-10-23T00:01:00.000000Z';row.admission.eligible=false;row.admission.reasons=['INPUT_FINAL_RECOVERY_UNACKNOWLEDGED'];validateDailyAsset(seal(a,'asset_id'),a.generated_at);
});

test('original hashes reject probability changes and malformed or duplicate proof JSON',async()=>{
  const a=copy();a.forecasts[0].body.categories[0].pmf[0].probability='0.9';
  await assert.rejects(verifyDailyHashes(seal(a,'asset_id'),webcrypto),/forecast_id checksum/);
  const b=prospective(),raw='{"inputs":{},"inputs":{}}';b.activation.event_payload_base64=Buffer.from(raw).toString('base64');b.activation.event_payload_sha256=hash(raw);b.activation=seal(b.activation,'authorization_id');
  assert.throws(()=>validateDailyAsset(seal(b,'asset_id'),b.generated_at),/Duplicate daily proof JSON key/);
});

test('DNP is one shared unscored outcome with two separate linked model grades',async()=>{
  const a=withDnp();validateDailyAsset(a,a.generated_at);await verifyDailyHashes(a,webcrypto);assert.equal(activeDailyGrades(a).length,2);assert.equal(a.counts.pending_grades,6);
  const html=renderDailyResearch(a,{view:'history',now:Date.parse(a.generated_at)});assert.match(html,/Did not play; statistical forecast not scored/);
  for(const mutation of ['status','identity','clock','grade','zero']){const b=withDnp();if(mutation==='status')b.outcomes[0].body.status='FINISHED';if(mutation==='identity')b.outcomes[0].body.event_snapshot_id='f'.repeat(64);if(mutation==='clock')b.outcomes[0].body.normalized_at='2026-10-23T04:00:00.000000Z';if(mutation==='grade')b.grades[0].body.status='SCORED';if(mutation==='zero')b.outcomes[0].body.minutes=0;assert.throws(()=>validateDailyAsset(seal(b,'asset_id'),b.generated_at),undefined,mutation);}
});

test('append-only corrections preserve original outcome and invalidate superseded grades',()=>{
  const a=withDnp(),original=a.outcomes[0],replacement=structuredClone(original);replacement.reference=ref('outcomes','nonfinal correction');replacement.body=seal({...replacement.body,status:'NONFINAL',source_observed_at:'2026-10-23T03:00:03.000000Z',normalized_at:'2026-10-23T03:00:04.000000Z'},'outcome_id');a.outcomes.push(replacement);a.corrections=[{reference:ref('corrections','nonfinal correction'),original_ref:original.reference,replacement_ref:replacement.reference,reason:'Synthetic revised finality evidence.'}];a.counts.pending_grades=8;validateDailyAsset(seal(a,'asset_id'),a.generated_at);assert.equal(a.outcomes.length,2);assert.equal(a.grades.length,2);assert.equal(activeDailyGrades(a).length,0);
  a.corrections[0].replacement_ref=ref('outcomes','absent replacement');assert.throws(()=>validateDailyAsset(a,a.generated_at),/correction changed/);
});

test('viewing old assets shows age warning without inventing a new capture or issuance',()=>{
  const a=copy(),html=renderDailyResearch(a,{now:Date.parse('2026-10-24T00:00:00.000000Z')});
  assert.match(html,/now older than the daily operating limit/);assert.match(html,/new download of unchanged content would not make them fresh/);assert.match(html,/Actual issue time: Not issued/);
  assert.equal(a.inputs[0].sources[0].retrieved_at,fixture.inputs[0].sources[0].retrieved_at);
});

test('complete encoded asset and original-per-subject limits are enforced',()=>{
  const a=copy();a.forecasts.push(structuredClone(a.forecasts[0]));assert.throws(()=>validateDailyAsset(a,a.generated_at),/count exceeds/);
  const b=copy();b.reason='x'.repeat(2048);b.forecasts[0].body.reported_minutes.pmf=Array.from({length:1026},(_,i)=>({value:i,probability:'1'}));assert.throws(()=>validateDailyAsset(b,b.generated_at),/reported-minutes distribution/);
  const c=copy();c.forecasts[0].body.categories[0].pmf[0].probability='1.'+'0'.repeat(64*1024);assert.throws(()=>validateDailyAsset(c,c.generated_at),/encoded reserve/);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash,webcrypto} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {dirname,resolve} from 'node:path';
import {validatePairedResearchAsset,verifyPairedResearchHashes,originalPairedRecord,activePairedGrades,validatePairedResearchDescriptor} from '../paired-research.mjs';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const canonical=v=>v&&typeof v==='object'?Array.isArray(v)?`[${v.map(canonical).join(',')}]`:`{${Object.keys(v).sort().map(k=>`${JSON.stringify(k)}:${canonical(v[k])}`).join(',')}}`:JSON.stringify(v);
const hash=v=>createHash('sha256').update(typeof v==='string'?v:canonical(v)).digest('hex');
const reseal=a=>{const {asset_id,...unsigned}=a;a.asset_id=hash(unsigned);return a;};
const fixture=JSON.parse(readFileSync(resolve(root,'web/tests/fixtures/paired-research-synthetic.json'),'utf8'));
const copy=()=>structuredClone(fixture);
const wrap=(row,body)=>{const key=row.kind==='event'?'event_input_id':row.kind+'_id';const {[key]:_,...unsigned}=body;return {...row,original_id:hash(unsigned),record_json:canonical(unsigned)};};

test('Python nonempty one-event originals validate with exact source bytes and14 categories',async()=>{
  const asset=copy();validatePairedResearchAsset(asset,asset.generated_at);await verifyPairedResearchHashes(asset,webcrypto);
  assert.equal(asset.counts.forecasts,3);assert.equal(asset.counts.eligible_forecasts,0);
  assert.equal(originalPairedRecord(asset.forecasts[0]).categories.length,14);
  assert.equal(originalPairedRecord(asset.outcomes[1]).status,'DNP');assert.equal(activePairedGrades(asset).length,3);
});

test('inactive empty paired channel is independent and exact counted',async()=>{
  const asset=copy();asset.inputs=[];asset.forecasts=[];asset.outcomes=[];asset.grades=[];asset.corrections=[];asset.missing_peers=[];
  asset.counts={forecasts:0,eligible_forecasts:0,outcomes:0,grades:0,pending_grades:0,missing_peers:0};
  asset.clocks={last_source_capture_at:null,last_issuance_at:null,last_grade_at:null};asset.status='INACTIVE';reseal(asset);
  validatePairedResearchAsset(asset,asset.generated_at);await verifyPairedResearchHashes(asset,webcrypto);
});

test('inactive source dictionaries never establish public Upcoming eligibility',()=>{
  const asset=copy();asset.forecasts[0].admission.eligible=true;asset.forecasts[0].admission.reasons=[];reseal(asset);
  assert.throws(()=>validatePairedResearchAsset(asset,asset.generated_at),/no installed reviewed activation/);
});

test('exact original hashes survive numeric spelling and reject changed PMFs',async()=>{
  const asset=copy(),body=originalPairedRecord(asset.forecasts[0]);body.categories[0].pmf[0].probability='0.5';
  asset.forecasts[0].record_json=JSON.stringify(Object.fromEntries(Object.entries(body).filter(([k])=>k!=='forecast_id')));reseal(asset);
  await assert.rejects(verifyPairedResearchHashes(asset,webcrypto),/original source checksum/);
});

test('checksum-consistent invalid outcomes, raw metadata and summary clocks reject',()=>{
  for(const mutation of ['status','raw_clock','summary_clock','foreign_outcome','grade']){
    const asset=copy();
    if(mutation==='summary_clock')asset.clocks.last_issuance_at=null;
    else if(mutation==='grade'){const row=asset.grades[0],body=originalPairedRecord(row);body.categories[0].crps='999';asset.grades[0]=wrap(row,body);}
    else {const row=asset.outcomes[0],body=originalPairedRecord(row);
      if(mutation==='status')body.status='INVALID';
      if(mutation==='raw_clock')body.raw_evidence_ref.metadata.cipher_persistence_completed_at='2026-10-23T00:00:00.000000Z';
      if(mutation==='foreign_outcome'){body.player_id='999009';asset.grades=[];asset.counts.grades=0;asset.counts.pending_grades=3;asset.clocks.last_grade_at=null;}
      asset.outcomes[0]=wrap(row,body);
    }
    reseal(asset);assert.throws(()=>validatePairedResearchAsset(asset,asset.generated_at),undefined,mutation);
  }
});

test('stale selected event evidence rejects even with repaired record checksums',()=>{
  const asset=copy(),row=asset.inputs[0],body=originalPairedRecord(row);
  body.sources[0].observed_at='2026-10-21T22:00:00.000000Z';body.sources[0].response_completed_at=body.sources[0].observed_at;
  asset.inputs[0]=wrap(row,body);reseal(asset);
  assert.throws(()=>validatePairedResearchAsset(asset,asset.generated_at),/Source clocks/);
});

test('missing peers equal the exact fixed input cohort minus retained originals',()=>{
  for(const mutation of ['foreign','omitted','duplicate','missing_input']){
    const asset=copy();
    if(mutation==='foreign')asset.missing_peers[0].player_id='999999';
    if(mutation==='omitted')asset.missing_peers.pop();
    if(mutation==='duplicate')asset.missing_peers.push(structuredClone(asset.missing_peers[0]));
    if(mutation==='missing_input')asset.inputs=[];
    asset.counts.missing_peers=asset.missing_peers.length;reseal(asset);
    assert.throws(()=>validatePairedResearchAsset(asset,asset.generated_at),undefined,mutation);
  }
});

test('interrupted outcome correction removes old grades from current completion',async()=>{
  const asset=copy(),old=asset.outcomes[0],body=originalPairedRecord(old);
  body.status='NONFINAL';body.primitives=null;body.minutes=null;body.minutes_precision=null;body.categories=[];
  const replacement=wrap({...old,source_record:{kind:'outcomes',record_id:'7'.repeat(64),payload_sha256:'8'.repeat(64)}},body);
  asset.outcomes.push(replacement);asset.corrections.push({kind:'outcome',original_id:old.original_id,replacement_id:replacement.original_id,reason:'Synthetic correction before replacement grades',source_record:{kind:'corrections',record_id:'9'.repeat(64),payload_sha256:'a'.repeat(64)}});
  asset.counts.outcomes=3;asset.counts.pending_grades=2;reseal(asset);
  validatePairedResearchAsset(asset,asset.generated_at);await verifyPairedResearchHashes(asset,webcrypto);
  assert.equal(activePairedGrades(asset).length,1);assert.equal(asset.grades.length,3);
});

test('duplicate JSON keys and descriptor path/clock confusion reject',()=>{
  const row=structuredClone(fixture.forecasts[0]);row.record_json='{"mode":"REAL_TIME_CAPTURED","mode":"SYNTHETIC_DIAGNOSTIC"}';
  assert.throws(()=>originalPairedRecord(row),/Duplicate/);
  const descriptor={path:`paired-research.${'a'.repeat(64)}.json`,sha256:'a'.repeat(64),generated_at:fixture.generated_at,status:'RESEARCH_ONLY',retained:false,error:null};
  validatePairedResearchDescriptor(descriptor,fixture.generated_at);
  assert.throws(()=>validatePairedResearchDescriptor({...descriptor,error:''},fixture.generated_at));
  assert.throws(()=>validatePairedResearchDescriptor({...descriptor,path:'../paired.json'},fixture.generated_at));
});

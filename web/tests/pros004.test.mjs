import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {loadSnapshot, validateManifest} from '../snapshot.mjs';
import {validatePros004Forecast, validatePros004Grade, validatePros004Index, pros004Original, renderPros004, validatePros004AdmissionContext} from '../pros004.mjs';
import {pairedCollection, prospectiveRow, gradeRow, project} from './pros004-fixtures.mjs';
import {clock, hash} from './fixtures.mjs';
const fetchAssets = assets => async url => Object.hasOwn(assets,url.replace('./data/',''))?new Response(assets[url.replace('./data/','')]):new Response('',{status:404});

test('schema3 recovers complete paired originals separately from legacy historical rows', async()=>{
  const f=pairedCollection(),r=await loadSnapshot(fetchAssets(f.assets),webcrypto);
  assert.equal(r.errors.length,0);assert.equal(r.pros004Error,null);assert.equal(r.sports[0].forecasts.length,1);
  assert.equal(r.pros004.forecasts.length,2);assert.equal(r.pros004.grades.length,2);
  assert.equal(pros004Original(r.pros004.forecasts[1]).model_key,'K0');
  assert.equal(pros004Original(r.pros004.forecasts[0]).categories.length,14);
  assert.match(r.pros004.forecasts[0].record_json,/10\.0/); // Original numeric bytes survive browser recovery.
  assert.equal(r.sports[0].candidates.length,0);
});

test('checksum-consistent duplicated original keys reject without reformatting floats',async()=>{
  const row=prospectiveRow();row.record_json=row.record_json.replace('{','{"player_id":"ambiguous",');row.original_id=hash(row.record_json);delete row.projection_id;row.projection_id=hash(row);
  await assert.rejects(()=>validatePros004Forecast(row,clock,webcrypto),/Duplicate/);
});

test('inactive empty index is specific and never supplies research candidates',async()=>{
  const f=pairedCollection(0),r=await loadSnapshot(fetchAssets(f.assets),webcrypto),html=renderPros004(r.pros004);
  assert.equal(r.pros004.forecasts.length,0);assert.match(html,/No upcoming PROS004/);assert.match(html,/UTC-date/);assert.match(html,/INACTIVE/);
  assert.match(renderPros004(r.pros004,{view:'history'}),/Diagnostics are excluded/);
  assert.equal(renderPros004(r.pros004,{nbaSelected:false}),'');
});

test('all168 forecasts and168 grades recover across84 pages without silent truncation',async()=>{
  const f=pairedCollection(168),r=await loadSnapshot(fetchAssets(f.assets),webcrypto);
  assert.equal(r.pros004Error,null);assert.equal(r.pros004.forecasts.length,168);assert.equal(r.pros004.grades.length,168);assert.equal(r.pros004.index.pages.length,84);
});

test('late, unacknowledged and checksum-consistent invalid originals reject',async()=>{
  const good=prospectiveRow();await validatePros004Forecast(good,clock,webcrypto);
  for(const change of [
    row=>Object.assign(row.admission,{eligible_for_comparison:true,reasons:[]}),
    row=>Object.assign(row.admission,{eligible_for_comparison:true,reasons:[],local_persistence_completed_at:'1999-12-01T18:35:00.000000Z',remote_checkpoint_completed_at:'1999-12-01T18:35:01.000000Z'}),
    row=>row.admission.reasons=[],
  ]){const row=structuredClone(good);change(row);delete row.projection_id;row.projection_id=hash(row);await assert.rejects(()=>validatePros004Forecast(row,clock,webcrypto));}
  for(const change of [r=>r.event_version='invalid',r=>r.producer_version='pros004-k0-producer-v2',r=>r.joint_recipe.omitted_atoms=1,r=>r.joint_recipe.target.player_id='wrong',r=>r.categories[0].mean='999',r=>r.generation_completed_at='1999-12-01T18:32:01.000000Z',r=>r.reported_minutes={pmf:[{value:-.5,probability:'0.5'},{value:1.5,probability:'0.5'}],mean:'0.5',interval80:[-.5,1.5],precision:'reported_source_precision_not_exact_workload'}]){
    const record=pros004Original(good);change(record);const row=project(record,good.admission);await assert.rejects(()=>validatePros004Forecast(row,clock,webcrypto));
  }
});

test('timely completion alone cannot admit comparison eligibility under inactive index',async()=>{
  const row=prospectiveRow();row.admission={retained:true,local_persistence_completed_at:'1999-12-01T18:30:06.000000Z',remote_checkpoint_completed_at:'1999-12-01T18:30:07.000000Z',eligible_for_comparison:true,reasons:[]};delete row.projection_id;row.projection_id=hash(row);
  await validatePros004Forecast(row,clock,webcrypto);
  assert.throws(()=>validatePros004AdmissionContext(row,pairedCollection().index),/Inactive/);
});

test('grade status, identities, clock and score consistency reject despite valid checksums',async()=>{
  const f=prospectiveRow(),good=gradeRow(f),byId=new Map([[f.original_id,f]]);await validatePros004Grade(good,byId,clock,webcrypto);
  for(const change of [r=>r.status='WON',r=>r.player_id='wrong',r=>r.graded_at='1999-12-01T18:29:59.000000Z',r=>r.financial_settlement='WON',r=>r.categories=[{code:'PTS',observed:0}],r=>r.reported_minutes={observed:0}]){
    const record=pros004Original(good);change(record);const row=project(record,null,good.model_version);await assert.rejects(()=>validatePros004Grade(row,byId,clock,webcrypto));
  }
});

test('individual scored category and minute metrics match original PMFs',async()=>{
  const f=prospectiveRow(),g=gradeRow(f,true),byId=new Map([[f.original_id,f]]);await validatePros004Grade(g,byId,clock,webcrypto);
  for(const change of [r=>r.categories[0].crps='999',r=>r.reported_minutes.crps='999',r=>r.reported_minutes.intervals[0].covered=false]){
    const record=pros004Original(g);change(record);await assert.rejects(()=>validatePros004Grade(project(record,null,g.model_version),byId,clock,webcrypto));
  }
});

test('missing/hash-changed pages fail collection while preserving legacy rows',async()=>{
  for(const corrupt of [assets=>delete assets[Object.keys(assets).find(k=>k.startsWith('pros004.forecasts'))],assets=>assets[Object.keys(assets).find(k=>k.startsWith('pros004.grades'))]='{}']){
    const f=pairedCollection();corrupt(f.assets);const r=await loadSnapshot(fetchAssets(f.assets),webcrypto);assert.equal(r.pros004,null);assert.ok(r.pros004Error);assert.equal(r.sports[0].forecasts.length,1);
  }
  const f=pairedCollection();f.index.totals.forecasts=0;delete f.index.index_id;f.index.index_id=hash(f.index);await assert.rejects(()=>validatePros004Index(f.index,f.descriptor,webcrypto),/omit/);
  const bad=structuredClone(f.manifest);bad.pros004.path='../outside.json';assert.throws(()=>validateManifest(bad),/Unsafe/);
});

test('History retains partial peer and completion status; Performance has individual grades and no comparative means',()=>{
  const f=pairedCollection(1,false),history=renderPros004(f,{view:'history',category:'PA'}),performance=renderPros004(f,{performance:true});
  assert.match(history,/R0/);assert.match(history,/PA · OPTIONAL/);assert.match(history,/Retained original · unadmitted/);assert.match(history,/Unacknowledged/);assert.match(history,/Missing peer: K0/);assert.match(performance,/PENDING/);
  assert.doesNotMatch(history,/K0 · Synthetic/);assert.doesNotMatch(performance,/Mean CRPS|best model|mean_log_loss/);
  assert.match(renderPros004(pairedCollection(),{performance:true}),/DNP_NOT_SCORED/);
  assert.match(renderPros004(f),/No upcoming PROS004/); // No unadmitted record is promoted into Upcoming.
});

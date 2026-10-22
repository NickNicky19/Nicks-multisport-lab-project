// Synthetic joint-transport tests only; no capture, issuance or ledger writes.
import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {loadSnapshot,validateManifest} from '../snapshot.mjs';
import {pairedCollection} from './pros004-fixtures.mjs';
import {canonical,hash,clock,typedFixture} from './fixtures.mjs';
const request = files => async url=>Object.hasOwn(files,url.replace('./data/',''))?new Response(files[url.replace('./data/','')]):new Response('',{status:404});
function joint() {
  const f=pairedCollection(),sport=typedFixture().sport;
  const catalog={schema_version:'nba-display-catalog-v1',verified_at:'1999-12-31T23:59:00.000000Z',sources:[],players:[],events:[],appearances:[]};catalog.catalog_id=hash(catalog);
  const display={schema_version:'multisport-display-metadata-v1',generated_at:clock,catalog,status:{schema_version:'multisport-display-status-v1',generated_at:clock,counts:{forecasts:1,reconstructed_forecasts:1,captured_forecasts:0,upcoming_forecasts:0,forecast_grades:1,offers:0,qualified_tickets:0},latest_retained_input_capture:null,last_genuine_issued_at:null}};display.metadata_id=hash(display);
  const offers={schema_version:'nba-player-offers-v1',league:'NBA',generated_at:clock,status:'OFFER_ONLY_RESEARCH',category_inventory:sport.forecasts[0].categories.map(x=>x.code),admissions:[],offers:[],unavailable_reasons:['Synthetic software fixture: no reviewed admitted contract.']};offers.asset_id=hash(offers);
  f.manifest.schema_version=5;
  for (const [channel,asset,prefix,status] of [['display',display,'display','DISPLAY_METADATA_ONLY'],['offers',offers,'nba-offers','OFFER_ONLY_RESEARCH']]) {
    const sha=hash(asset),path=`${prefix}.${sha}.json`;
    f.manifest[channel]={path,sha256:sha,generated_at:clock,status,retained:false,error:null};f.manifest[`${channel}_error`]=null;f.assets[path]=canonical(asset);
  }
  const paired={schema_version:'nba-operational-paired-publication-v1',protocol_id:'NBA-PAIRED-OPS-002',generated_at:clock,status:'INACTIVE',reason:'Synthetic fixture: operational pilot remains inactive.',counts:{forecasts:0,eligible_forecasts:0,outcomes:0,grades:0,pending_grades:0,missing_peers:0},clocks:{last_source_capture_at:null,last_issuance_at:null,last_grade_at:null},inputs:[],forecasts:[],outcomes:[],grades:[],corrections:[],missing_peers:[],qualification:'UNAVAILABLE',financial_settlement:'NOT_EVALUATED'};paired.asset_id=hash(paired);
  const pairedSha=hash(paired),pairedPath=`paired-research.${pairedSha}.json`;f.manifest.paired_research={path:pairedPath,sha256:pairedSha,generated_at:clock,status:'RESEARCH_ONLY',retained:false,error:null};f.manifest.paired_research_error=null;f.assets[pairedPath]=canonical(paired);
  f.display=display;f.offers=offers;return seal(f);
}
function seal(f) {delete f.manifest.snapshot_id;f.manifest.snapshot_id=hash(f.manifest);f.assets['manifest.json']=canonical(f.manifest);return f;}
function replace(f,channel,asset) {
  const sha=hash(asset),prefix={display:'display',offers:'nba-offers',pros004:'pros004.index'}[channel],path=`${prefix}.${sha}.json`;
  Object.assign(f.manifest[channel],{path,sha256:sha});f.assets[path]=canonical(asset);return seal(f);
}

test('manifest5 recovers historical, reserved-study, display and offer lanes independently',async()=>{
  const f=joint(),loaded=await loadSnapshot(request(f.assets),webcrypto);
  assert.equal(loaded.errors.length,0);assert.equal(loaded.pros004Error,null);assert.equal(loaded.displayError,null);assert.equal(loaded.offersError,null);
  assert.equal(loaded.sports[0].forecasts.length,1);assert.equal(loaded.pros004.forecasts.length,2);assert.equal(loaded.display.status.counts.forecasts,1);assert.deepEqual(loaded.offers.offers,[]);
  assert.equal(loaded.pairedResearchError,null);assert.equal(loaded.pairedResearch.status,'INACTIVE');assert.equal(loaded.sports[0].candidates.length,0);
});

test('a corrupted auxiliary hash cannot hide valid independent peers',async()=>{
  for(const channel of ['pros004','display','offers','paired_research']) {
    const f=joint();f.assets[f.manifest[channel].path]='{}';
    const loaded=await loadSnapshot(request(f.assets),webcrypto),key=channel==='paired_research'?'pairedResearch':channel;
    assert.equal(loaded[key],null);assert.ok(loaded[`${key}Error`]);assert.equal(loaded.sports[0].forecasts.length,1);
    for(const other of ['pros004','display','offers','paired_research'].filter(x=>x!==channel))assert.ok(loaded[other==='paired_research'?'pairedResearch':other]);
  }
});

test('unsafe optional descriptor paths reject before fetch and preserve other channels',async()=>{
  for(const channel of ['pros004','display','offers','paired_research']) {
    const f=joint();f.manifest[channel]={...f.manifest.display,path:'../outside.json'};f.manifest[`${channel}_error`]=null;seal(f);
    const calls=[],loaded=await loadSnapshot(async path=>{calls.push(path);return request(f.assets)(path);},webcrypto);
    assert.ok(calls.every(path=>!path.includes('outside')));assert.equal(loaded.sports.length,1);
    const key={paired_research:'pairedResearch'}[channel]||channel;assert.equal(loaded[key],null);assert.ok(loaded[`${key}Error`]);
  }
});

test('checksum-consistent invalid display and offer meaning rejects independently',async()=>{
  for(const [channel,change] of [['display',asset=>asset.status.counts.upcoming_forecasts=1],['offers',asset=>asset.status='QUALIFIED']]) {
    const f=joint(),asset=structuredClone(f[channel]);change(asset);const id=channel==='display'?'metadata_id':'asset_id';delete asset[id];asset[id]=hash(asset);replace(f,channel,asset);
    const loaded=await loadSnapshot(request(f.assets),webcrypto);assert.equal(loaded[channel],null);assert.ok(loaded[`${channel}Error`]);assert.ok(loaded.pros004);assert.equal(loaded.sports[0].forecasts.length,1);
  }
});

test('missing-channel explanations and legacy schema boundaries remain strict',async()=>{
  const f=joint();f.manifest.offers=null;f.manifest.offers_error=null;seal(f);const loaded=await loadSnapshot(request(f.assets),webcrypto);
  assert.match(loaded.offersError,/explanation/);assert.ok(loaded.display);assert.ok(loaded.pros004);
  for(const version of [1,2,3,4])assert.throws(()=>validateManifest({...f.manifest,schema_version:version}));
});

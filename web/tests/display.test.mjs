// Display-only software fixtures; no records are issued or changed by these tests.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {webcrypto} from 'node:crypto';
import {displayTarget,researchAvailability,validateDisplayCatalog,validateDisplayMetadata} from '../display.mjs';
import {loadSnapshot,validateManifest} from '../snapshot.mjs';
import {typedFixture,prospectiveFixture,canonical,hash} from './fixtures.mjs';
const catalog=JSON.parse(await readFile(new URL('../../config/display_metadata_nba_v1.json',import.meta.url),'utf8'));
function fixture(){
  const {sport}=typedFixture(),f=sport.forecasts[0],g=sport.performance[0],clock=catalog.verified_at;
  Object.assign(f,{player_id:'2583632',player_label:'ESPN player 2583632',event_id:'401810136',team_id:'21',opponent_id:'24',event_starts_at:'2025-11-24T01:00:00.000000Z',trained_through:'2025-11-22T00:00:00.000000Z',cutoff_at:'2025-11-23T23:30:00.000000Z',history_freeze:'2025-11-23T00:00:00.000000Z',issued_at:'2026-10-20T00:21:46.411304Z'});delete f.forecast_id;f.forecast_id=hash(f);
  Object.assign(g,{forecast_id:f.forecast_id,player_id:f.player_id,event_id:f.event_id,graded_at:clock});delete g.grade_id;g.grade_id=hash(g);
  Object.assign(sport.events[0],{event_id:f.event_id,starts_at:f.event_starts_at,team_ids:[f.team_id,f.opponent_id],label:'Synthetic display software fixture'});sport.generated_at=clock;
  const asset={schema_version:'multisport-display-metadata-v1',generated_at:clock,catalog:structuredClone(catalog),status:{schema_version:'multisport-display-status-v1',generated_at:clock,counts:{forecasts:1,reconstructed_forecasts:1,captured_forecasts:0,upcoming_forecasts:0,forecast_grades:1,offers:0,qualified_tickets:0},latest_retained_input_capture:null,last_genuine_issued_at:null}};
  asset.metadata_id=hash(asset);return packageAssets(sport,asset);
}
function packageAssets(sport,asset){
  const sha=hash(sport),displaySha=hash(asset),descriptor={path:`display.${displaySha}.json`,sha256:displaySha,generated_at:asset.generated_at,status:'DISPLAY_METADATA_ONLY',retained:false,error:null};
  const manifest={schema_version:4,build_commit:'a'.repeat(40),published_at:asset.generated_at,publication_status:'RESEARCH_ONLY',supported_sports:['NBA'],sports:[{league:'NBA',path:`nba.${sha}.json`,sha256:sha,generated_at:sport.generated_at,status:'RESEARCH_ONLY',retained:false,error:null}],errors:{},display:descriptor,display_error:null};manifest.snapshot_id=hash(manifest);
  return {sport,asset,manifest,descriptor,files:{'manifest.json':canonical(manifest),[descriptor.path]:canonical(asset),[`nba.${sha}.json`]:canonical(sport)}};
}
const fetcher=files=>async url=>Object.hasOwn(files,url.replace('./data/',''))?new Response(files[url.replace('./data/','')]):new Response('',{status:404});
test('source-backed namespace lookup resolves Royce and historical Suns/Spurs without changing original label',async()=>{
  const f=fixture(),r=await loadSnapshot(fetcher(f.files),webcrypto);assert.equal(r.errors.length,0);assert.equal(r.displayError,null);
  const row=r.sports[0].forecasts[0],d=displayTarget(row,r.display);
  assert.equal(d.playerName,"Royce O'Neale");assert.equal(d.teamName,'Phoenix Suns');assert.equal(d.opponentName,'San Antonio Spurs');assert.equal(d.matchup,'San Antonio Spurs @ Phoenix Suns');assert.equal(row.player_label,'ESPN player 2583632');assert.equal(row.issued_at,'2026-10-20T00:21:46.411304Z');assert.equal(row.categories.length,14);
});
test('same numeric ID in another namespace or league cannot borrow a readable name',()=>{
  const f=fixture(),row=f.sport.forecasts[0];
  for(const delta of [{id_namespace:'nba'},{league:'WNBA'},{player_id:'unknown',player_label:'ESPN player unknown'}]){
    const d=displayTarget({...row,...delta},f.asset);assert.equal(d.nameBasis,'ID_FALLBACK');assert.match(d.playerName,/name unavailable/);
  }
  const wrongEvent=displayTarget({...row,event_id:'future-unknown'},f.asset);assert.match(wrongEvent.matchup,/matchup names unavailable/);assert.equal(wrongEvent.teamName,'Team 21');
});
test('checksum-consistent catalog semantic errors reject wrong names, historical membership, dates and clocks',()=>{
  for(const change of [c=>c.players[0].display_name='Wrong name',c=>c.players[0].id_namespace='nba',c=>c.appearances[0].team_id='25',c=>c.events[0].event_starts_at='2025-11-24T01:00:00.000000Z',c=>c.sources[0].observed_at='2099-01-01T00:00:00.000000Z',c=>c.sources[0].http_status=true,c=>c.players[0].source_ids=['unknown']]){
    const c=structuredClone(catalog);change(c);delete c.catalog_id;c.catalog_id=hash(c);assert.throws(()=>validateDisplayCatalog(c,catalog.verified_at));
  }
});
test('metadata hash, HTTP and semantic failure preserve valid forecasts with honest ID fallback',async()=>{
  for(const change of [f=>delete f.files[f.descriptor.path],f=>f.files[f.descriptor.path]='{}',f=>{f.asset.catalog.players.find(p=>p.player_id==='2583632').display_name='Wrong name';delete f.asset.catalog.catalog_id;f.asset.catalog.catalog_id=hash(f.asset.catalog);delete f.asset.metadata_id;f.asset.metadata_id=hash(f.asset);Object.assign(f,packageAssets(f.sport,f.asset));}]){
    const f=fixture();change(f);const r=await loadSnapshot(fetcher(f.files),webcrypto);assert.equal(r.sports[0].forecasts.length,1);assert.equal(r.display,null);assert.ok(r.displayError);assert.match(displayTarget(r.sports[0].forecasts[0],r.display).playerName,/name unavailable/);
  }
});
test('display status clocks and counts cannot relabel reconstruction as genuine issuance',()=>{
  const f=fixture();validateDisplayMetadata(f.asset,[f.sport],f.asset.generated_at);
  for(const change of [a=>a.status.counts.upcoming_forecasts=1,a=>a.status.last_genuine_issued_at=f.sport.forecasts[0].issued_at]){
    const bad=structuredClone(f.asset);change(bad);delete bad.metadata_id;bad.metadata_id=hash(bad);assert.throws(()=>validateDisplayMetadata(bad,[f.sport],bad.generated_at));
  }
});
test('manifest4 does not reinterpret independent manifest3 and rejects unsafe display requests',()=>{
  const f=fixture();assert.equal(validateManifest(f.manifest),f.manifest);
  for(const change of [m=>m.schema_version=3,m=>delete m.display]){const bad=structuredClone(f.manifest);change(bad);assert.throws(()=>validateManifest(bad));}
});
test('invalid optional display descriptors are isolated before fetch while valid sport records remain',async()=>{
  for(const change of [m=>m.display.path='../outside.json',m=>m.display.generated_at='2099-01-01T00:00:00.000000Z',m=>m.display.status='QUALIFIED',m=>m.display={},m=>{m.display=null;m.display_error=null;}]){
    const f=fixture();change(f.manifest);delete f.manifest.snapshot_id;f.manifest.snapshot_id=hash(f.manifest);f.files['manifest.json']=canonical(f.manifest);
    const requested=[],r=await loadSnapshot(async path=>{requested.push(path);return fetcher(f.files)(path);},webcrypto);
    assert.equal(r.sports[0].forecasts.length,1);assert.equal(r.display,null);assert.ok(r.displayError);assert.equal(requested.length,2);assert.match(displayTarget(r.sports[0].forecasts[0],r.display).playerName,/name unavailable/);
  }
});

test('synthetic valid future research publishes with zero prices and moves into History as the clock advances',async()=>{
  const {sport}=prospectiveFixture(),f=sport.forecasts[0],wire=canonical(f),clock=sport.generated_at;
  const emptyCatalog={schema_version:'nba-display-catalog-v1',verified_at:'1999-12-31T23:59:00.000000Z',sources:[],players:[],events:[],appearances:[]};emptyCatalog.catalog_id=hash(emptyCatalog);
  const asset={schema_version:'multisport-display-metadata-v1',generated_at:clock,catalog:emptyCatalog,status:{schema_version:'multisport-display-status-v1',generated_at:clock,counts:{forecasts:1,reconstructed_forecasts:0,captured_forecasts:1,upcoming_forecasts:1,forecast_grades:0,offers:0,qualified_tickets:0},latest_retained_input_capture:null,last_genuine_issued_at:f.issued_at}};asset.metadata_id=hash(asset);
  const packaged=packageAssets(sport,asset),loaded=await loadSnapshot(fetcher(packaged.files),webcrypto);
  assert.equal(loaded.errors.length,0);assert.equal(loaded.displayError,null);assert.equal(loaded.sports[0].future_availability.status,'AVAILABLE');
  let counts=researchAvailability(loaded.sports,Date.parse('2000-01-01T00:00:00Z'));
  assert.equal(counts.upcoming,1);assert.equal(counts.offers,0);assert.equal(counts.tickets,0);assert.equal(counts.history,0);
  counts=researchAvailability(loaded.sports,Date.parse('2000-01-01T01:00:00Z'));
  assert.equal(counts.upcoming,0);assert.equal(counts.history,1);assert.equal(canonical(loaded.sports[0].forecasts[0]),wire);
  assert.equal(loaded.sports[0].forecasts[0].evidence_lane,'REAL_TIME_CAPTURED');assert.equal(loaded.sports[0].performance.length,0);
  assert.equal(displayTarget(f,null).nameBasis,'ORIGINAL_RESEARCH_LABEL');
});

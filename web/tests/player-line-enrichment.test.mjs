// Authored source-shaped fixtures, never an actual offer or source request.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash,webcrypto} from 'node:crypto';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {ALL_NBA_CATEGORIES} from '../research.mjs';
import {canonicalPlayerLineReview} from '../player-line-review.mjs';
import {PLAYER_LINE_ENRICHMENT_SCHEMA,ENRICHMENT_SOURCE_URLS,RULE_WITNESSES,validatePlayerLineEnrichment,
  verifyPlayerLineEnrichmentHash,verifyPlayerLineEnrichmentSources,renderEnrichedPlayerLineReview} from '../player-line-enrichment.mjs';
import {renderPreparedLocalReview} from '../../scripts/render_local_offer_review.mjs';

const now='2026-10-22T12:05:00.000000Z',captured='2026-10-22T12:03:00.000000Z';
const hash=raw=>createHash('sha256').update(raw).digest('hex');
const encode=value=>Buffer.from(canonicalPlayerLineReview(value));
function seal(value,key){delete value[key];value[key]=hash(encode(value));return value;}
function fixture(){
  const board=[{sport:'nba',subject_type:'player',subject_id:'1001',game_id:'9001',wager_type:'first_qtr_points',options:[{subject_team:'AAA'},{subject_team:'AAA'}]},
    {sport:'nba',subject_type:'player',subject_id:'1001',game_id:'9001',wager_type:'points',options:[{subject_team:'AAA'},{subject_team:'AAA'}]}];
  const boardRaw=encode(board), originals=Array.from({length:4},(_,i)=>({row_id:`row:${Math.floor(i/2)}/option:${i%2}`,
    provider_player_id:'1001',provider_event_id:'9001',provider_selection_id:`selection-${i}`,player_namespace:'sleeper',player_label:null,event_label:null,team_label:'AAA',
    stat:i<2?null:'PTS',raw_stat_label:i<2?'first_qtr_points':'points',line:i<2?'4.5':'20.5',side:i%2?'under':'over',variant:'normal',period:null,overtime:null,event_starts_at:null,
    source_updated_at:null,source_declared_status:'pre_game',source_economics:null,price_status:'PRICE_UNAVAILABLE',quote:null,contract:null,
    precision_basis:'RAW_NUMERIC_LEXEME_REPLAYED',source_pointer:`/${Math.floor(i/2)}/options/${i%2}/outcome_value`,
    unavailable_reasons:['player_name_unverified','event_identity_unverified','period_unverified','overtime_unverified','settlement_rules_unverified'],
    forecast_match_status:'NOT_MATCHED_UNVERIFIED_IDENTITY_EVENT_PERIOD',ticket_eligible:false}));
  const review=seal({schema_version:'nba-private-player-lines-v1',scope:'LOCAL_REVIEW_ONLY',source:'sleeper',venue:'Sleeper',product:'Picks variant unverified',parse_status:'unmapped',
    generated_at:'2026-10-22T12:02:00.000000Z',observed_at:'2026-10-22T12:00:00.000000Z',imported_at:'2026-10-22T12:01:00.000000Z',evidence_lane:'SYNTHETIC_TEST',
    source_evidence:{kind:'RAW_HTTP_BODY_REPLAYED',input_sha256:hash(boardRaw),input_bytes:boardRaw.length,metadata_sha256:'a'.repeat(64),source_payload_sha256:'b'.repeat(64),
      capture_sha256:'c'.repeat(64),source_payload_hash_basis:'CANONICAL_OPTION_DECIMAL_LEXEME_JSON',raw_source_sha256:hash(boardRaw),raw_source_bytes:boardRaw.length,
      source_url:'https://api.sleeper.com/lines/available',provider_permission_verified:false},
    counts:{source_rows:2,nba_rows:2,parsed_observations:4,displayed_observations:4,unmapped_observations:2,complete_contracts:0,diagnostics:0},
    selection:{offset:0,limit:32,ordering:'SOURCE_ROW_OPTION_ORDER'},
    category_coverage:Object.fromEntries(ALL_NBA_CATEGORIES.map(code=>[code,{observed_side_options:code==='PTS'?2:0,displayed_side_options:code==='PTS'?2:0,
      status:code==='PTS'?'OBSERVED_IN_SAMPLE':'UNOBSERVED_IN_SAMPLE'}])),observations:originals,public_admission:false,ticket_eligibility:false,qualification:'UNAVAILABLE'},'review_id');
  const catalogue={'1001':{player_id:'1001',sport:'nba',first_name:'Test',last_name:'Player',full_name:'Test Player',team:'AAA',position:'SF'}};
  const assets={},sources={};
  for(const key of Object.keys(ENRICHMENT_SOURCE_URLS)){
    const raw=key==='catalogue'?encode(catalogue):Buffer.from('<html><body>'+Object.values(RULE_WITNESSES).filter(w=>w.source===key).map(w=>w.text).join(' ').replace('Quarter Markets:','<strong>Quarter Markets</strong>:')+'</body></html>');
    const metadata={url:ENRICHMENT_SOURCE_URLS[key],final_url:ENRICHMENT_SOURCE_URLS[key],http_status:200,content_type:key==='catalogue'?'application/json':'text/html',complete_body:true,
      request_started_at:'2026-10-22T12:02:59.000000Z',observed_at:captured,raw_sha256:hash(raw),raw_bytes:raw.length};
    const metadataRaw=encode(metadata);assets[key]={raw,metadataRaw};
    sources[key]={source_url:metadata.url,raw_sha256:metadata.raw_sha256,raw_bytes:raw.length,metadata_sha256:hash(metadataRaw),
      request_started_at:metadata.request_started_at,observed_at:captured,upstream_observed_at:null};
  }
  const enrichment=seal({schema_version:PLAYER_LINE_ENRICHMENT_SCHEMA,scope:'LOCAL_REVIEW_ONLY',source:'sleeper',
    base:{review_id:review.review_id,board_sha256:hash(boardRaw),board_bytes:boardRaw.length,observed_at:review.observed_at},generated_at:now,evidence_lane:'SYNTHETIC_TEST',sources,
    rule_witnesses:structuredClone(RULE_WITNESSES),event_team_inventory:[{provider_event_id:'9001',source_team_labels:['AAA'],status:'UNVERIFIED_NATIVE_EVENT'}],
    counts:{catalogue_objects:1,catalogue_players:1,catalogue_team_entries:0,source_nba_rows:2,source_player_ids:1,name_resolved_player_ids:1,name_unresolved_player_ids:0,
      source_side_observations:4,q1_side_observations:2,displayed_observations:4},
    observations:originals.map((r,i)=>({row_id:r.row_id,league:'NBA',namespace:'sleeper',provider_player_id:r.provider_player_id,provider_event_id:r.provider_event_id,
      player_label:'Test Player',name_status:'VERIFIED_NATIVE_CATALOGUE',catalogue_pointer:'/1001',catalogue_team:'AAA',board_team:'AAA',team_status:'CONSISTENT_LITERALS_EVENT_UNVERIFIED',
      raw_stat_label:r.raw_stat_label,period:i<2?'Q1':'UNKNOWN',overtime:i<2?'OT_EXCLUDED':'UNKNOWN',period_evidence:i<2?['q1','quarter_overtime']:[],event_status:'UNVERIFIED_NATIVE_ID',
      event_label:null,event_starts_at:null,settlement_status:'PARTIAL_GENERIC_RULES_ONLY',forecast_match_status:'NOT_MATCHED_UNVERIFIED_EVENT_PERIOD',ticket_eligible:false,
      missing_fields:['native_event_mapping','event_start','product_variant','complete_settlement_contract',...(i<2?[]:['period','overtime'])]})),
    public_admission:false,ticket_eligibility:false,qualification:'UNAVAILABLE'},'enrichment_id');
  return {review,enrichment,assets,boardRaw};
}

test('private names, explicit Q1 rules and later clocks render without rewriting originals',async()=>{
  const {review,enrichment,assets,boardRaw}=fixture(),before=JSON.stringify(review);
  validatePlayerLineEnrichment(enrichment,review,now);await verifyPlayerLineEnrichmentSources(enrichment,review,assets,boardRaw,webcrypto);
  const html=renderEnrichedPlayerLineReview(review,enrichment,{now});
  for(const value of ['<h2>Test Player</h2>','first quarter (Q1). Overtime excluded.','Period and overtime: UNKNOWN','Player 1001','event 9001',
    'PRICE_UNAVAILABLE','0 complete contracts','No forecast match or qualified ticket','upstream observation UNKNOWN','Original records remain unchanged',
    '2026-10-22 12:00:00.000000 UTC','2026-10-22 12:03:00.000000 UTC','Unverified native-event source team labels'])assert.ok(html.includes(value),value);
  assert.equal(JSON.stringify(review),before);for(const code of ALL_NBA_CATEGORIES)assert.ok(html.includes(`<th scope="row">${code}</th>`));
});

test('checksum-consistent semantic promotion and backdated enrichment are rejected',()=>{
  for(const mutate of [e=>e.observations[0].event_label='Invented matchup',e=>e.observations[0].event_starts_at=now,
    e=>e.observations[2].period='FULL_GAME',e=>e.observations[0].overtime='OT_INCLUDED',e=>e.observations[0].provider_player_id='9999',
    e=>e.observations[0].ticket_eligible=true,e=>e.generated_at='2026-10-22T12:02:00.000000Z',e=>e.sources.catalogue.upstream_observed_at=captured,
    e=>e.event_team_inventory[0].status='VERIFIED',e=>e.public_admission=true]){
    const {review,enrichment}=fixture();mutate(enrichment);seal(enrichment,'enrichment_id');assert.throws(()=>validatePlayerLineEnrichment(enrichment,review,now));
  }
});

test('seals and original-byte replay reject changed names, source hashes and whole-board bytes',async()=>{
  let f=fixture();f.enrichment.observations[0].player_label='Invented Name';
  await assert.rejects(verifyPlayerLineEnrichmentHash(f.enrichment,f.review,webcrypto),/seal mismatch/);
  seal(f.enrichment,'enrichment_id');
  await assert.rejects(verifyPlayerLineEnrichmentSources(f.enrichment,f.review,f.assets,f.boardRaw,webcrypto),/catalogue/);
  f=fixture();f.assets.catalogue.raw=Buffer.concat([f.assets.catalogue.raw,Buffer.from(' ')]);
  await assert.rejects(verifyPlayerLineEnrichmentSources(f.enrichment,f.review,f.assets,f.boardRaw,webcrypto),/source bytes/);
  f=fixture();await assert.rejects(verifyPlayerLineEnrichmentSources(f.enrichment,f.review,f.assets,Buffer.from('[]'),webcrypto),/whole-board/);
});

test('catalogue key, sport and name contradictions fail even with consistent body hashes',async()=>{
  for(const mutation of [p=>p.player_id='9999',p=>p.sport='nfl',p=>p.full_name='Other Name',p=>p.first_name='']){
    const f=fixture(),data=JSON.parse(f.assets.catalogue.raw);mutation(data['1001']);
    const raw=encode(data),meta=JSON.parse(f.assets.catalogue.metadataRaw);meta.raw_sha256=hash(raw);meta.raw_bytes=raw.length;
    const metadataRaw=encode(meta);f.assets.catalogue={raw,metadataRaw};
    Object.assign(f.enrichment.sources.catalogue,{raw_sha256:hash(raw),raw_bytes:raw.length,metadata_sha256:hash(metadataRaw)});seal(f.enrichment,'enrichment_id');
    await assert.rejects(verifyPlayerLineEnrichmentSources(f.enrichment,f.review,f.assets,f.boardRaw,webcrypto));
  }
});

test('original-byte replay rejects duplicate and escaped-duplicate source keys despite recomputed hashes',async()=>{
  const replaceAsset=(f,key,raw,{metadataRaw=null}={})=>{
    const meta=JSON.parse(f.assets[key].metadataRaw);meta.raw_sha256=hash(raw);meta.raw_bytes=raw.length;
    metadataRaw??=encode(meta);f.assets[key]={raw,metadataRaw};
    Object.assign(f.enrichment.sources[key],{raw_sha256:hash(raw),raw_bytes:raw.length,metadata_sha256:hash(metadataRaw)});
    seal(f.enrichment,'enrichment_id');
  };
  const replaceBoard=(f,raw)=>{
    f.boardRaw=raw;Object.assign(f.review.source_evidence,{input_sha256:hash(raw),raw_source_sha256:hash(raw),input_bytes:raw.length,raw_source_bytes:raw.length});
    seal(f.review,'review_id');Object.assign(f.enrichment.base,{review_id:f.review.review_id,board_sha256:hash(raw),board_bytes:raw.length});seal(f.enrichment,'enrichment_id');
  };
  for(const escaped of [false,true]){
    let f=fixture(),key=escaped?'observed\\u005fat':'observed_at';
    const metadataRaw=Buffer.from('{"'+key+'":"1900-01-01T00:00:00.000000Z",'+f.assets.catalogue.metadataRaw.toString('utf8').slice(1));
    replaceAsset(f,'catalogue',f.assets.catalogue.raw,{metadataRaw});
    await assert.rejects(verifyPlayerLineEnrichmentSources(f.enrichment,f.review,f.assets,f.boardRaw,webcrypto),/Duplicate private source JSON key/);

    f=fixture();key=escaped?'full\\u005fname':'full_name';
    const raw=Buffer.from(f.assets.catalogue.raw.toString('utf8').replace('"full_name":"Test Player"','"'+key+'":"Discarded Name","full_name":"Test Player"'));
    replaceAsset(f,'catalogue',raw);
    await assert.rejects(verifyPlayerLineEnrichmentSources(f.enrichment,f.review,f.assets,f.boardRaw,webcrypto),/Duplicate private source JSON key/);

    f=fixture();key=escaped?'sp\\u006frt':'sport';
    const board=Buffer.from(f.boardRaw.toString('utf8').replace('"sport":"nba"','"'+key+'":"nfl","sport":"nba"'));replaceBoard(f,board);
    await assert.rejects(verifyPlayerLineEnrichmentSources(f.enrichment,f.review,f.assets,f.boardRaw,webcrypto),/Duplicate private source JSON key/);
  }
});

test('source replay rejects overflow exponents and excessive nesting even in otherwise unused fields',async()=>{
  for(const target of ['metadata','catalogue','board']){
    for(const token of ['1e999','NaN','['.repeat(65)+'0'+']'.repeat(65)]){
      const f=fixture();
      if(target==='metadata'){
        const raw=Buffer.from('{"unused":'+token+','+f.assets.catalogue.metadataRaw.toString('utf8').slice(1));
        f.assets.catalogue.metadataRaw=raw;f.enrichment.sources.catalogue.metadata_sha256=hash(raw);
      }else if(target==='catalogue'){
        const raw=Buffer.from(f.assets.catalogue.raw.toString('utf8').replace('"position":"SF"','"position":"SF","unused":'+token));
        const meta=JSON.parse(f.assets.catalogue.metadataRaw);Object.assign(meta,{raw_sha256:hash(raw),raw_bytes:raw.length});
        const metadataRaw=encode(meta);f.assets.catalogue={raw,metadataRaw};
        Object.assign(f.enrichment.sources.catalogue,{raw_sha256:hash(raw),raw_bytes:raw.length,metadata_sha256:hash(metadataRaw)});
      }else{
        const raw=Buffer.from(f.boardRaw.toString('utf8').replace('"sport":"nba"','"sport":"nba","unused":'+token));
        f.boardRaw=raw;Object.assign(f.review.source_evidence,{input_sha256:hash(raw),raw_source_sha256:hash(raw),input_bytes:raw.length,raw_source_bytes:raw.length});
        seal(f.review,'review_id');Object.assign(f.enrichment.base,{review_id:f.review.review_id,board_sha256:hash(raw),board_bytes:raw.length});
      }
      seal(f.enrichment,'enrichment_id');
      await assert.rejects(verifyPlayerLineEnrichmentSources(f.enrichment,f.review,f.assets,f.boardRaw,webcrypto),/Non-finite private source JSON number|Invalid private source JSON value|nesting bound/);
    }
  }
});

test('source-level counts and team conflicts cannot masquerade as verified matchup evidence',async()=>{
  const f=fixture();f.enrichment.counts.catalogue_players=2;seal(f.enrichment,'enrichment_id');
  assert.throws(()=>validatePlayerLineEnrichment(f.enrichment,f.review,now));
  const g=fixture();g.enrichment.event_team_inventory[0].source_team_labels=['AAA','BBB','CCC'];seal(g.enrichment,'enrichment_id');
  assert.throws(()=>validatePlayerLineEnrichment(g.enrichment,g.review,now));
});

test('renderer optional companion replays retained sources, produces create-only HTML and preserves base',async()=>{
  const temporary=await fs.mkdtemp(path.join(os.tmpdir(),'nml-enrichment-render-'));
  try{
    const {review,enrichment,assets,boardRaw}=fixture(),base=path.join(temporary,'base'),companion=path.join(temporary,'companion');
    await fs.mkdir(base);await fs.mkdir(companion);
    const input=path.join(base,'review.json'),enrichmentFilename=path.join(companion,'enrichment.json');
    await fs.writeFile(input,encode(review));await fs.writeFile(path.join(base,'source.body'),boardRaw);await fs.writeFile(enrichmentFilename,encode(enrichment));
    for(const[key,a]of Object.entries(assets)){await fs.writeFile(path.join(companion,key+'.body'),a.raw);await fs.writeFile(path.join(companion,key+'.metadata.json'),a.metadataRaw);}
    const before=await fs.readFile(input),output='.local-data/enriched.html';
    const first=await renderPreparedLocalReview(input,output,{cwd:temporary,enrichmentFilename});assert.equal(first.created,true);
    const html=await fs.readFile(path.join(temporary,output),'utf8');assert.match(html,/<h2>Test Player<\/h2>/);assert.match(html,/script-src 'none'/);
    assert.deepEqual(await fs.readFile(input),before);
    assert.equal((await renderPreparedLocalReview(input,output,{cwd:temporary,enrichmentFilename})).created,false);
    await fs.writeFile(path.join(companion,'catalogue.body'),Buffer.from('{}'));
    await assert.rejects(renderPreparedLocalReview(input,'.local-data/invalid.html',{cwd:temporary,enrichmentFilename}));
  }finally{await fs.rm(temporary,{recursive:true,force:true});}
});

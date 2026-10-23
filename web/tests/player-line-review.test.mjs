// Invented source-shaped records only; no actual player offer or source request.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash,webcrypto} from 'node:crypto';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {ALL_NBA_CATEGORIES} from '../research.mjs';
import {validateOfferAsset} from '../offers.mjs';
import {renderPreparedLocalReview} from '../../scripts/render_local_offer_review.mjs';
import {PLAYER_LINE_REVIEW_SCHEMA,canonicalPlayerLineReview,validatePlayerLineReview,
  verifyPlayerLineReviewHash,renderPlayerLineReview} from '../player-line-review.mjs';

const now='2026-10-21T12:02:00.000000Z';
const sourceUrl='https://api.sleeper.com/lines/available';
const gaps=['player_name_unverified','event_identity_unverified','period_unverified','overtime_unverified','settlement_rules_unverified'];
const labels={points:'PTS',points_and_assists:'PA'};
function seal(review){delete review.review_id;review.review_id=createHash('sha256').update(canonicalPlayerLineReview(review)).digest('hex');return review;}
function fixture({kind='RAW_HTTP_BODY_REPLAYED',total=2,offset=0,limit=32,rawLabels=null}={}){
  const raw=kind==='RAW_HTTP_BODY_REPLAYED';
  const all=Array.from({length:total},(_,index)=>{
    const sourceRow=Math.floor(index/2),option=index%2,rawLabel=rawLabels?.[index]??'points';
    return {row_id:`row:${sourceRow}/option:${option}`,provider_player_id:`fictional-native-player-${sourceRow}`,
      provider_event_id:'fictional-native-event',provider_selection_id:`fictional-native-selection-${index}`,
      player_namespace:'sleeper',player_label:null,event_label:null,team_label:null,
      stat:Object.hasOwn(labels,rawLabel)?labels[rawLabel]:null,raw_stat_label:rawLabel,line:'22.500000000000000001',side:option?'under':'over',variant:'normal',
      period:null,overtime:null,event_starts_at:null,source_updated_at:'2026-10-21T11:59:00.000000Z',source_declared_status:'pre_game',
      source_economics:option?{kind:'pickem_multiplier',value:'1.900000000000000001'}:null,
      price_status:'PRICE_UNAVAILABLE',quote:null,contract:null,
      precision_basis:raw?'RAW_NUMERIC_LEXEME_REPLAYED':'DERIVED_TEXT_ONLY',
      source_pointer:raw?`/${sourceRow}/options/${option}/outcome_value`:`/payload/observations/${index}/line`,
      unavailable_reasons:[...gaps],forecast_match_status:'NOT_MATCHED_UNVERIFIED_IDENTITY_EVENT_PERIOD',ticket_eligible:false};
  });
  const selected=all.slice(offset,offset+limit);
  return seal({schema_version:PLAYER_LINE_REVIEW_SCHEMA,scope:'LOCAL_REVIEW_ONLY',source:'sleeper',venue:'Sleeper',product:'Picks variant unverified',
    parse_status:all.some(row=>row.stat===null)?'unmapped':total?'partial':'empty',generated_at:now,
    observed_at:'2026-10-21T12:00:00.000000Z',imported_at:'2026-10-21T12:01:00.000000Z',evidence_lane:'SYNTHETIC_TEST',
    source_evidence:{kind,input_sha256:'a'.repeat(64),input_bytes:1000,metadata_sha256:raw?'b'.repeat(64):null,
      source_payload_sha256:'c'.repeat(64),capture_sha256:'d'.repeat(64),
      source_payload_hash_basis:raw?'CANONICAL_OPTION_DECIMAL_LEXEME_JSON':'CANONICAL_IMPORT_INPUT_JSON',
      raw_source_sha256:raw?'a'.repeat(64):null,raw_source_bytes:raw?1000:null,source_url:sourceUrl,provider_permission_verified:false},
    counts:{source_rows:Math.ceil(total/2),nba_rows:Math.ceil(total/2),parsed_observations:total,displayed_observations:selected.length,
      unmapped_observations:all.filter(row=>row.stat===null).length,complete_contracts:0,diagnostics:0},
    selection:{offset,limit,ordering:'SOURCE_ROW_OPTION_ORDER'},
    category_coverage:Object.fromEntries(ALL_NBA_CATEGORIES.map(code=>[code,{observed_side_options:all.filter(row=>row.stat===code).length,
      displayed_side_options:selected.filter(row=>row.stat===code).length,status:all.some(row=>row.stat===code)?'OBSERVED_IN_SAMPLE':'UNOBSERVED_IN_SAMPLE'}])),
    observations:selected,public_admission:false,ticket_eligibility:false,qualification:'UNAVAILABLE'});
}
function change(mutate,options){const review=fixture(options);mutate(review);return seal(review);}

test('private player lines preserve missing prices, exact thresholds and native identity gaps',async()=>{
  const review=fixture(),before=JSON.stringify(review);
  assert.equal(validatePlayerLineReview(review,now),review);await verifyPlayerLineReviewHash(review,webcrypto);
  const html=renderPlayerLineReview(review,{now});
  for(const value of ['Sleeper player fictional-native-player-0','OVER 22.500000000000000001 PTS','UNDER 22.500000000000000001 PTS',
    'PRICE_UNAVAILABLE','1.900000000000000001','not standalone sportsbook odds','0 complete contracts','Player name and matchup unverified',
    'Original source bytes replayed','No matching forecast or qualified ticket is attached.'])assert.ok(html.includes(value),value);
  assert.doesNotMatch(html,/MATCHED_RESEARCH_ONLY|Qualified ticket|Verified player name/);
  assert.equal(JSON.stringify(review),before);
});

test('derived receipt review cannot claim raw source bytes, lexemes or refreshed observation clocks',async()=>{
  const review=fixture({kind:'DERIVED_RECEIPT_ONLY'});validatePlayerLineReview(review,now);await verifyPlayerLineReviewHash(review,webcrypto);
  const html=renderPlayerLineReview(review,{now});
  assert.match(html,/Derived receipt only; original HTTP response bytes are unavailable/);
  assert.match(html,/Original decimal precision is unverified/);
  assert.match(html,/Observed: 2026-10-21 12:00:00.000000 UTC/);
  for(const mutate of [r=>r.source_evidence.raw_source_sha256='a'.repeat(64),r=>r.source_evidence.raw_source_bytes=1000,
    r=>r.source_evidence.metadata_sha256='b'.repeat(64),r=>r.source_evidence.source_payload_hash_basis='CANONICAL_OPTION_DECIMAL_LEXEME_JSON',
    r=>r.observations[0].precision_basis='RAW_NUMERIC_LEXEME_REPLAYED'])
    assert.throws(()=>validatePlayerLineReview(change(mutate,{kind:'DERIVED_RECEIPT_ONLY'}),now));
});

test('explicit windows preserve complete input counts and all fourteen category states',()=>{
  const first=fixture({total:40}),later=fixture({total:40,offset:32,limit:8});
  validatePlayerLineReview(first,now);validatePlayerLineReview(later,now);
  assert.equal(first.observations.length,32);assert.equal(later.observations.length,8);
  const html=renderPlayerLineReview(later,{now});
  assert.match(html,/40 parsed side options · displaying 33–40 of 40/);
  assert.match(html,/offset 32, limit 8, source row\/option order/);
  assert.equal(later.category_coverage.PTS.observed_side_options,40);assert.equal(later.category_coverage.PTS.displayed_side_options,8);
  for(const category of ALL_NBA_CATEGORIES)assert.ok(html.includes(`<th scope="row">${category}</th>`),category);
  const emptyWindow=fixture({total:40,offset:40});validatePlayerLineReview(emptyWindow,now);
  assert.match(renderPlayerLineReview(emptyWindow,{now}),/empty window does not establish permanent source absence/);
  for(const mutate of [r=>r.selection.limit=33,r=>r.selection.offset=41,r=>r.selection.ordering='VALUE_RANKED',
    r=>r.counts.displayed_observations=1,r=>r.counts.source_rows=10001,r=>r.counts.parsed_observations=20001,
    r=>delete r.category_coverage.PA,r=>r.category_coverage.PTS.status='UNOBSERVED_IN_SAMPLE',
    r=>r.category_coverage.PTS.observed_side_options=1,r=>r.category_coverage.PTS.displayed_side_options=1,
    r=>r.counts.unmapped_observations=1,r=>r.counts.nba_rows=2])
    assert.throws(()=>validatePlayerLineReview(change(mutate),now));
});

test('a sealed nonempty source cannot claim an empty, blocked or failed parser result',async()=>{
  for(const options of [{},{offset:2}]){
    for(const status of ['empty','blocked_access','upstream_error','parser_failure']){
      const contradictory=change(review=>review.parse_status=status,options);
      await verifyPlayerLineReviewHash(contradictory,webcrypto);
      assert.throws(()=>validatePlayerLineReview(contradictory,now),status);
      assert.throws(()=>renderPlayerLineReview(contradictory,{now}),status);
    }
  }
  validatePlayerLineReview(fixture({total:0}),now);
});

test('optional PA remains mapped while quarter labels remain explicit unmapped observations',()=>{
  const review=fixture({total:4,rawLabels:['points_and_assists','points_and_assists','first_qtr_points','first_qtr_points']});
  validatePlayerLineReview(review,now);
  assert.equal(review.category_coverage.PA.observed_side_options,2);assert.equal(review.category_coverage.PTS.observed_side_options,0);
  assert.equal(review.counts.unmapped_observations,2);
  const html=renderPlayerLineReview(review,{now});assert.match(html,/first_qtr_points/);assert.match(html,/2 unmapped side options/);
  const bad=structuredClone(review);bad.observations[2].stat='PTS';seal(bad);
  assert.throws(()=>validatePlayerLineReview(bad,now),/statistic/);
  validatePlayerLineReview(fixture({rawLabels:['constructor','toString']}),now);
});

test('private source and namespace facts cannot become public offers or forecast matches',()=>{
  for(const mutate of [r=>r.public_admission=true,r=>r.ticket_eligibility=true,r=>r.scope='PUBLIC',r=>r.source='ESPN',
    r=>r.venue='DraftKings',r=>r.product='sportsbook',r=>r.qualification='QUALIFIED',
    r=>r.source_evidence.provider_permission_verified=true,r=>r.observations[0].player_namespace='espn',
    r=>r.observations[0].player_label='Invented Verified Name',r=>r.observations[0].event_label='Invented Matchup',
    r=>r.observations[0].period='full_game',r=>r.observations[0].overtime='includes_overtime',
    r=>r.observations[0].event_starts_at='2026-10-21T23:00:00.000000Z',r=>r.observations[0].quote={},
    r=>r.observations[0].contract={},r=>r.observations[0].ticket_eligible=true,
    r=>r.observations[0].forecast_match_status='MATCHED_RESEARCH_ONLY',r=>r.counts.complete_contracts=1,
    r=>r.extra='unreviewed'])assert.throws(()=>validatePlayerLineReview(change(mutate),now));
  assert.throws(()=>validateOfferAsset(fixture(),now),/asset/);
});

test('precise source, import and generation clocks remain separate and reject future updates',()=>{
  for(const mutate of [r=>r.observed_at='2026-10-21T12:01:00.000001Z',r=>r.imported_at='2026-10-21T12:02:00.000001Z',
    r=>r.generated_at='2026-10-21T12:02:00.000001Z',r=>r.observations[0].source_updated_at='2026-10-21T12:00:00.000001Z',
    r=>r.observed_at='2026-10-21T12:00:00Z',r=>r.observed_at='2026-02-30T12:00:00.000000Z'])
    assert.throws(()=>validatePlayerLineReview(change(mutate),now));
  const html=renderPlayerLineReview(fixture(),{now});
  for(const value of ['Observed: 2026-10-21 12:00:00.000000 UTC','Imported: 2026-10-21 12:01:00.000000 UTC',
    'Review generated: 2026-10-21 12:02:00.000000 UTC','Source updated: 2026-10-21 11:59:00.000000 UTC'])assert.ok(html.includes(value));
});

test('decimal text and literal multipliers never become rounded or converted sportsbook prices',()=>{
  for(const value of [22.5,'NaN','Infinity','-0','+2.5','01.5','2e1','٢٢.٥','',null])
    assert.throws(()=>validatePlayerLineReview(change(r=>r.observations[0].line=value),now));
  for(const value of ['0','0.000','-1','1e2',1.9,null])
    assert.throws(()=>validatePlayerLineReview(change(r=>r.observations[1].source_economics.value=value),now));
  for(const mutate of [r=>r.observations[1].source_economics.kind='sportsbook_decimal',r=>r.observations[0].side='Yes',
    r=>r.observations[0].price_status='OBSERVED_PRICE_NOT_QUALIFIED'])assert.throws(()=>validatePlayerLineReview(change(mutate),now));
});

test('exact original and derived source pointers preserve gaps and reject duplicate source rows',()=>{
  for(const mutate of [r=>r.source_evidence.raw_source_sha256='f'.repeat(64),r=>r.source_evidence.raw_source_bytes=999,
    r=>r.source_evidence.metadata_sha256=null,r=>r.source_evidence.source_url='https://example.invalid/board',
    r=>r.observations[0].source_pointer='/0/options/1/outcome_value',r=>r.observations[0].source_pointer='/00/options/0/outcome_value',
    r=>r.observations[0].row_id='row:9/option:0',r=>r.observations[0].row_id='row:0/option:64',r=>r.observations[1].row_id=r.observations[0].row_id,
    r=>r.observations[0].unavailable_reasons=[],r=>r.observations[0].unavailable_reasons.push(gaps[0])])
    assert.throws(()=>validatePlayerLineReview(change(mutate),now));
  assert.throws(()=>validatePlayerLineReview(change(r=>r.observations[0].source_pointer='/payload/observations/1/line',{kind:'DERIVED_RECEIPT_ONLY'}),now));
  const duplicateNative=change(r=>{r.observations[1].provider_selection_id=r.observations[0].provider_selection_id;
    r.observations[0].unavailable_reasons.push('duplicate_provider_selection_id');r.observations[1].unavailable_reasons.push('duplicate_provider_selection_id');r.counts.diagnostics=2;});
  validatePlayerLineReview(duplicateNative,now);
  assert.match(renderPlayerLineReview(duplicateNative,{now}),/duplicate provider selection id/);
});

test('review seals are independently checked after semantic validation',async()=>{
  const review=fixture();await verifyPlayerLineReviewHash(review,webcrypto);
  review.observations[0].variant='a different source variant';validatePlayerLineReview(review,now);
  await assert.rejects(verifyPlayerLineReviewHash(review,webcrypto),/seal mismatch/);
  await assert.rejects(verifyPlayerLineReviewHash(fixture(),{}),/SHA-256 support/);
});

test('opaque source text is escaped and the private card contains no collection or publication actions',()=>{
  const review=change(r=>{r.observations[0].provider_player_id='<img src=x onerror=alert(1)>';
    r.observations[0].provider_event_id='<script>untrusted</script>';r.observations[0].team_label='<a href="https://example.invalid">team</a>';
    r.observations[0].unavailable_reasons.push('<iframe src="https://example.invalid"></iframe>');});
  const html=renderPlayerLineReview(review,{now});
  for(const value of ['&lt;img src=x onerror=alert(1)&gt;','&lt;script&gt;untrusted&lt;/script&gt;','&lt;a href=','&lt;iframe src='])assert.ok(html.includes(value));
  assert.doesNotMatch(html,/<(?:img|script|iframe|a\s|button|form)\b/i);
});

test('existing private renderer autodetects sealed line reviews and preserves create-only output and Gamma fallback',async()=>{
  const directory=await fs.mkdtemp(path.join(os.tmpdir(),'nml-player-line-render-test-'));
  const invoke=(input,output)=>renderPreparedLocalReview(input,output,{cwd:directory});
  try{
    const input=path.join(directory,'invented-review.json'),output=path.join(directory,'.local-data','lines','preview.html');
    await fs.writeFile(input,JSON.stringify(fixture()));
    const first=await invoke(input,output);assert.equal(first.created,true);
    const html=await fs.readFile(output,'utf8');assert.match(html,/NBA player-line observations/);assert.match(html,/connect-src 'none'/);
    assert.match(html,/script-src 'none'/);assert.doesNotMatch(html,/<script\b/i);
    assert.equal((await fs.stat(output)).mode&0o777,0o600);
    const retry=await invoke(input,output);assert.equal(retry.created,false);
    await assert.rejects(invoke(input,path.join(directory,'public.html')),/Output must remain under/);
    const modified=change(r=>r.observations[0].variant='alternate');
    await fs.writeFile(input,JSON.stringify(modified));
    await assert.rejects(invoke(input,output),/Conflicting output exists/);
    assert.equal(await fs.readFile(output,'utf8'),html);
    const inputLink=path.join(directory,'input-symlink.json');await fs.symlink(input,inputLink);
    await assert.rejects(invoke(inputLink,path.join(directory,'.local-data','input-link.html')),/not a symlink/);
    const parentLink=path.join(directory,'.local-data','parent-link');await fs.symlink(directory,parentLink);
    await assert.rejects(invoke(input,path.join(parentLink,'escaped.html')),/not symlinks/);
    const wrong=fixture();wrong.review_id='f'.repeat(64);await fs.writeFile(input,JSON.stringify(wrong));
    const wrongOutput=path.join(directory,'.local-data','wrong.html');
    await assert.rejects(invoke(input,wrongOutput),/seal mismatch/);
    await assert.rejects(fs.stat(wrongOutput),{code:'ENOENT'});
    const gamma={schema_version:'nba-local-offer-review-v1',scope:'LOCAL_REVIEW_ONLY',generated_at:now,
      source:'Polymarket Gamma API',venue:'Polymarket',product:'binary_event_contract',public_admission:false,ticket_eligibility:false,
      counts:{player_rows_observed:0,rows_parsed:0,complete_contracts:0},
      category_coverage:Object.fromEntries(ALL_NBA_CATEGORIES.map(code=>[code,{observed_rows:0,parsed_rows:0,status:'UNOBSERVED_IN_SAMPLE'}])),observations:[]};
    await fs.writeFile(input,JSON.stringify(gamma));const gammaOutput=path.join(directory,'.local-data','gamma.html');
    await invoke(input,gammaOutput);
    assert.match(await fs.readFile(gammaOutput,'utf8'),/NBA player-contract inspection/);
  }finally{await fs.rm(directory,{recursive:true,force:true});}
});

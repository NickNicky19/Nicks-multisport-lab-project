// Fictional source-shaped fixtures only. No provider request or issued forecast.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash,webcrypto} from 'node:crypto';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {ALL_NBA_CATEGORIES} from '../research.mjs';
import {MOVIODDS_REVIEW_SCHEMA,canonicalMovioddsReview,movioddsClock,validateMovioddsReview,
  verifyMovioddsReviewHash,renderMovioddsReview} from '../moviodds-review.mjs';
import {renderPreparedLocalReview} from '../../scripts/render_local_offer_review.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url)),fixtureFile=path.join(root,'tests/fixtures/moviodds_review_v1.json');
const original=JSON.parse(await fs.readFile(fixtureFile,'utf8'));
const now='2026-10-23T22:00:00.000000Z';
const fixture=()=>structuredClone(original);
function seal(value){delete value.review_id;value.review_id=createHash('sha256').update(canonicalMovioddsReview(value)).digest('hex');return value;}

test('fictional private snapshot preserves names, Boolean DD/TD and source/normalization clocks',async()=>{
  const f=fixture(),before=JSON.stringify(f);assert.equal(f.schema_version,MOVIODDS_REVIEW_SCHEMA);assert.equal(f.evidence_lane,'SYNTHETIC_TEST');
  validateMovioddsReview(f,now);await verifyMovioddsReviewHash(f,webcrypto);
  const html=renderMovioddsReview(f,{now});
  for(const value of ['Fictional Centre','SYNTHETIC DEVELOPMENT EXAMPLE','PRIVATE SNAPSHOT','Publisher: <strong>MoviOdds</strong>','<strong>bet365</strong>',
    'independent project','Yes — double-double','Yes — triple-double','at least 10 in 2','at least 10 in 3','Yes/No selection; no numeric line is assigned',
    '600 seconds','BLOCKED_EVENT_START_DISAGREEMENT','not a live/current feed','numeric operator UNKNOWN','Permanent native player ID: not supplied',
    'Canonical player ESPN:900001','group 181463','selection 10004','2026-10-22 10:00:00.123456789 UTC','2026-10-23 11:59:59.123456789 UTC',
    '2026-10-23 12:00:00.000000 UTC','2026-10-23 12:01:00.000000 UTC','Supplied standalone decimal price: <strong>2.25</strong>',
    'OBSERVED_PRICE_NOT_QUALIFIED','NO_ACTION','Public admission false','SportsDataverse','ESPN-derived via hoopR, CC BY 4.0','identity evidence, not new live captures'])
    assert.ok(html.includes(value),value);
  assert.doesNotMatch(html,/OVER 0\.5|UNDER 0\.5|over 0\.5|under 0\.5|MATCHED_RESEARCH_ONLY/);assert.equal(JSON.stringify(f),before);
});

test('all fourteen category states and every literal game line remain visible',()=>{
  const f=fixture(),html=renderMovioddsReview(f,{now});
  for(const code of ALL_NBA_CATEGORIES)assert.ok(html.includes(`<th scope="row">${code}</th>`),code);
  assert.match(html,/<th scope="row">TOV<\/th><td>0<\/td><td>0<\/td><td>0<\/td><td>UNOBSERVED_IN_SAMPLE/);
  for(const game of f.game_lines){assert.ok(html.includes(game.odds_decimal_as_supplied));assert.ok(html.includes(game.selection_id));assert.ok(html.includes(game.market_id));}
  assert.ok(html.includes('Recorded game lines (1)'));assert.ok(html.includes('240.5'));assert.ok(html.includes('no estimated minutes or blowout probability is inferred'));
});

test('checksum-consistent identity, category, participation and admission promotions fail typed validation',()=>{
  const mutations=[f=>f.public_admission=true,f=>f.ticket_eligibility=true,f=>f.event.forecast_match_status='MATCHED',
    f=>f.event.start_difference_seconds=0,f=>f.observations[0].native_player_id='900001',f=>f.observations[0].canonical_player.namespace='moviodds',
    f=>f.observations[0].canonical_player.source_pointer='/csv/rows/5000',f=>f.event.source_pointer='/fixtures/5000',f=>f.counts.verified_player_selections=2,
    f=>f.observations[0].canonical_player.team_id='999',f=>f.observations[0].source_team_label='Other Team',f=>f.observations[0].source_selection.group_id='181446',
    f=>f.observations[0].period='first_quarter',f=>f.observations[0].overtime='regulation_only',f=>f.observations[0].ticket_eligible=true,
    f=>f.observations[0].source_selection.line='0.5',f=>f.observations[0].predicate.at_least_ten_in_categories=3,
    f=>f.observations[2].predicate={kind:'GREATER_THAN',line:'10'},f=>f.observations[2].gaps=[],f=>f.observations[0].price.kind='pickem_multiplier',
    f=>delete f.category_inventory.PA,f=>f.counts.source_selections++,f=>f.game_lines.pop(),f=>f.category_inventory.PTS.complete=1,
    f=>f.rules.jurisdiction='US_VERIFIED',f=>f.rules.passages.official_statistics_and_corrections.source_value='Every later correction changes settlement',
    f=>f.limitations=['Current live feed with guaranteed EV']];
  for(const mutate of mutations){const f=fixture();mutate(f);seal(f);assert.throws(()=>validateMovioddsReview(f,now),String(mutate));}
  const duplicated=fixture();duplicated.game_lines.push({...duplicated.game_lines[0],source_pointer:'/quotes/14'});
  duplicated.counts.game_selections++;duplicated.counts.source_selections++;seal(duplicated);assert.throws(()=>validateMovioddsReview(duplicated,now),/Duplicate native game selection/);
});

test('nanosecond ordering is exact and schedule minute resolution is explicitly scoped',()=>{
  assert.equal(movioddsClock('2026-10-23T12:00:00.000000001Z')-movioddsClock('2026-10-23T12:00:00Z'),1n);
  assert.throws(()=>movioddsClock('2026-10-23T12:00Z'));assert.equal(movioddsClock('2026-10-23T12:00Z',{allowMinuteResolution:true}),movioddsClock('2026-10-23T12:00:00Z'));
  for(const value of ['2026-02-30T12:00:00Z','2026-10-23T25:00:00Z','2026-10-23T12:00:00.1234567890Z',null])assert.throws(()=>movioddsClock(value));
  const f=fixture();f.event.starts_at='2026-10-23T20:00:00.000000001Z';f.event.start_difference_seconds='0.000000001';seal(f);
  validateMovioddsReview(f,now);f.event.start_difference_seconds=0;seal(f);assert.throws(()=>validateMovioddsReview(f,now));
  for(const mutate of [f=>f.observations[0].price_changed_at='2026-10-23T11:59:59.987654322Z',
    f=>f.observations[0].market_polled_at='2026-10-23T11:59:59.987654322Z',f=>f.publisher_server_time='2026-10-23T12:00:00.000000001Z',
    f=>f.knowledge_observed_at='2026-10-23T11:59:59.999999999Z',f=>f.normalized_at='2026-10-23T11:59:59.999999999Z']){
    const changed=fixture();mutate(changed);seal(changed);assert.throws(()=>validateMovioddsReview(changed,now));
  }
});

test('complete-first bounded preview and stale exact-market gates cannot borrow other clocks',()=>{
  let f=fixture();[f.observations[0],f.observations[2]]=[f.observations[2],f.observations[0]];seal(f);assert.throws(()=>validateMovioddsReview(f,now));
  f=fixture();f.observations[0].market_polled_at='2026-10-23T10:00:00Z';seal(f);assert.throws(()=>validateMovioddsReview(f,now));
  f=fixture();f.observations[0].price_changed_at='2026-10-01T00:00:00Z';seal(f);validateMovioddsReview(f,now); // Old change, fresh exact-group confirmation.
  f=fixture();f.event.in_play=true;seal(f);assert.throws(()=>validateMovioddsReview(f,now));
});

test('NO Boolean selection, unpriced raw decimal and HTML escaping preserve stated meaning',()=>{
  const f=fixture();f.observations[0].source_selection.label='No';f.observations[0].predicate.selection='No';
  f.observations[0].price.value='0';f.observations[0].price.status='UNAVAILABLE_AT_CAPTURE';
  for(const row of f.observations){row.player_label='<img src=x onerror=bad> & Fictional';row.canonical_player.name=row.player_label;}
  seal(f);const html=renderMovioddsReview(f,{now});assert.ok(html.includes('No — double-double'));
  assert.ok(html.includes('Source decimal field, unavailable at capture: <strong>0</strong>'));assert.ok(html.includes('&lt;img src=x onerror=bad&gt; &amp; Fictional'));
  assert.doesNotMatch(html,/<img|<script/);
});

test('seal verification remains separate from typed meaning checks',async()=>{
  const f=fixture();f.observations[0].price.value='2.25000000000001';
  validateMovioddsReview(f,now);await assert.rejects(verifyMovioddsReviewHash(f,webcrypto),/seal mismatch/);
  seal(f);await verifyMovioddsReviewHash(f,webcrypto); // Source replay is a further mandatory CLI gate.
});

test('missing decimal prices preserve complete Boolean contracts and literal game lines without conversion',async()=>{
  const f=fixture();f.observations[0].price.value=null;f.observations[0].price.status='PRICE_UNAVAILABLE';f.game_lines[0].odds_decimal_as_supplied=null;seal(f);
  validateMovioddsReview(f,now);await verifyMovioddsReviewHash(f,webcrypto);assert.equal(f.observations[0].semantic_status,'COMPLETE_LOCAL');assert.equal(f.counts.complete_local_contracts,2);
  const html=renderMovioddsReview(f,{now});assert.ok(html.includes('<strong>Price unavailable (PRICE_UNAVAILABLE).</strong>'));
  assert.ok(html.includes('Fractional field 5/4 retained literally; no conversion or replacement price'));assert.ok(html.includes('<td>Price unavailable (PRICE_UNAVAILABLE)</td>'));
  assert.doesNotMatch(html,/Source decimal field, unavailable at capture: <strong>0/);
  for(const mutate of [f=>f.observations[0].price.status='OBSERVED_PRICE_NOT_QUALIFIED',f=>f.observations[0].price.value=0,
    f=>f.observations[0].price.value='0',f=>delete f.game_lines[0].odds_decimal_as_supplied]){
    const changed=structuredClone(f);mutate(changed);seal(changed);assert.throws(()=>validateMovioddsReview(changed,now));
  }
});

test('CLI rejects missing originals and synthetic recovery before creating any rendered output',async()=>{
  const temporary=await fs.mkdtemp(path.join(os.tmpdir(),'nml-moviodds-render-'));
  try{
    const directory=path.join(temporary,'package');await fs.mkdir(directory);const input=path.join(directory,'review.json');await fs.writeFile(input,canonicalMovioddsReview(fixture()));
    await assert.rejects(renderPreparedLocalReview(input,'.local-data/missing.html',{cwd:temporary}),/original-source replay failed/);
    await assert.rejects(fs.access(path.join(temporary,'.local-data/missing.html')));
    const prepare=`import sys,hashlib\nfrom pathlib import Path\nsys.path.insert(0,'tests')\nfrom test_moviodds_offer import fictional_assets,fictional_review,FIXTURE\nfrom multisport_lab.integrity import canonical\np=Path(sys.argv[1]);assets=fictional_assets();r=fictional_review()\nfor k,v in assets.items():\n (p/(k+'.body')).write_bytes(v['raw']);(p/(k+'.metadata.json')).write_bytes(v['metadata_raw'])\ns={k:{a:hashlib.sha256(b).hexdigest() for a,b in v.items()} for k,v in assets.items()}\n(p/'review-intent.json').write_bytes(canonical({'fixture':FIXTURE,'originals':s,'normalized_at':r['normalized_at']}))\n(p/'review.json').write_bytes(canonical(r))\n`;
    await promisify(execFile)('python3',['-c',prepare,directory],{cwd:root,timeout:10000,maxBuffer:128*1024});
    await assert.rejects(renderPreparedLocalReview(input,'.local-data/synthetic.html',{cwd:temporary}),/Unadmitted synthetic review/);
    await assert.rejects(fs.access(path.join(temporary,'.local-data/synthetic.html')));
    await assert.rejects(renderPreparedLocalReview(input,'.local-data/wrong-enrichment.html',{cwd:temporary,enrichmentFilename:'irrelevant.json'}),/no Sleeper enrichment/);
  }finally{await fs.rm(temporary,{recursive:true,force:true});}
});

// Fictional source-shaped inputs only. No real player offer or source rights.
import test from 'node:test';
import assert from 'node:assert/strict';
import {ALL_NBA_CATEGORIES} from '../research.mjs';
import {validateOfferAsset} from '../offers.mjs';
import {LOCAL_REVIEW_SCHEMA,validateLocalOfferReview,renderLocalOfferReview} from '../local-offer-review.mjs';

const now='2026-10-21T12:01:00.000000Z';
function fixture(){
  const review={schema_version:LOCAL_REVIEW_SCHEMA,scope:'LOCAL_REVIEW_ONLY',generated_at:now,
    source:'Polymarket Gamma API',venue:'Polymarket',product:'binary_event_contract',
    public_admission:false,ticket_eligibility:false,
    counts:{player_rows_observed:1,rows_parsed:1,complete_contracts:0},
    category_coverage:Object.fromEntries(ALL_NBA_CATEGORIES.map(category=>[category,{observed_rows:category==='PTS'?1:0,parsed_rows:category==='PTS'?1:0,status:category==='PTS'?'OBSERVED_PARTIAL':'UNOBSERVED_IN_SAMPLE'}])),
    observations:[{source_market_id:'fictional-market',source_event_id:'fictional-event',player_name:'Fictional Player',player_identity:null,
      event_label:'Fictional Away vs Fictional Home',event_starts_at:'2026-10-21T23:30:00.000000Z',category:'PTS',threshold:'20.500000000000000001',operator:'>',
      selection:'Yes',selection_id:'fictional-yes-token',variant:'binary_player_stat_threshold',period:'full_game',overtime:'includes_overtime',
      observed_at:'2026-10-21T12:00:00.000000Z',source_updated_at:'2026-10-21T11:59:59.999999Z',
      prices_as_supplied:{outcomes:['Yes','No'],outcomePrices:['0.570000000000000001','0.43'],bestBid:'0.56',bestAsk:'0.58'},
      sportsbook_price_status:'PRICE_UNAVAILABLE',settlement:{participation:'Fictional participation rule.',dnp:'Fictional no-play resolves No.',
        postponement:'Fictional cancellation resolves at0.5.',ties:'Fictional equality resolves No.',official_stat_source:'Fictional official statistics.'},
      gaps:['Stable player identity remains unverified.','Stat-correction scope remains unverified.'],complete:false,normalized_offer_available:false,raw_source_sha256:'a'.repeat(64)}]};
  return review;
}
function mutate(change){const review=fixture();change(review);return review;}

test('partial source-shaped fixture remains local observation with literal binary economics and missing sportsbook price',()=>{
  const review=fixture();assert.equal(validateLocalOfferReview(review,now),review);
  const html=renderLocalOfferReview(review,{now});
  for(const text of ['Fictional Player','Fictional Away vs Fictional Home','LOCAL REVIEW ONLY','Partial source observation','YES: PTS &gt; 20.500000000000000001',
    '0.570000000000000001','Standalone sportsbook price: unavailable','No stable player entity ID verified','Paper Builder: NO_ACTION'])assert.ok(html.includes(text),text);
  assert.match(html,/not sportsbook odds, Sleeper multipliers, or compatible parlay legs/);
  assert.match(html,/Source: Polymarket Gamma API\. Venue: Polymarket/);
  assert.match(html,/0 complete contracts/);
  assert.doesNotMatch(html,/Complete local contract review/);
  assert.match(html,/does not infer their selection\/token or price alignment from array order/);
  assert.doesNotMatch(html,/Yes: 0\.57/);
});

test('schema and public admissions remain separate and cannot be spoofed by local data',()=>{
  for(const change of [r=>r.scope='PUBLIC',r=>r.public_admission=true,r=>r.ticket_eligibility=true,
    r=>r.source='ESPN',r=>r.venue='DraftKings',r=>r.product='sportsbook',r=>r.extra='unreviewed'])
    assert.throws(()=>validateLocalOfferReview(mutate(change),now));
  assert.throws(()=>validateOfferAsset(fixture(),now),/asset/);
});

test('missing identity and rules cannot become a complete normalized offer by toggling flags',()=>{
  for(const change of [r=>r.observations[0].complete=true,r=>r.observations[0].normalized_offer_available=true,
    r=>r.counts.complete_contracts=1,r=>{r.observations[0].gaps=[];},r=>{r.observations[0].gaps=[];r.observations[0].complete=true;r.observations[0].normalized_offer_available=true;r.counts.complete_contracts=1;}])
    assert.throws(()=>validateLocalOfferReview(mutate(change),now));
  const complete=fixture(),row=complete.observations[0];
  row.player_identity={namespace:'fictional-official-player',id:'fictional-player-id'};
  row.settlement.stat_corrections='Fictional exact correction policy.';row.gaps=[];row.complete=true;row.normalized_offer_available=true;
  complete.counts.complete_contracts=1;complete.category_coverage.PTS.status='OBSERVED_COMPLETE';
  validateLocalOfferReview(complete,now);
  assert.match(renderLocalOfferReview(complete,{now}),/Public admission remains unavailable/);
  for(const change of [r=>r.observations[0].period=null,r=>r.observations[0].overtime=null,
    r=>r.observations[0].settlement.stat_corrections='UNKNOWN',r=>r.observations[0].selection_id=null]){
    const bad=structuredClone(complete);change(bad);assert.throws(()=>validateLocalOfferReview(bad,now));
  }
  complete.observations[0].prices_as_supplied.outcomePrices=null;
  complete.observations[0].prices_as_supplied.bestBid=null;
  complete.observations[0].prices_as_supplied.bestAsk=null;
  validateLocalOfferReview(complete,now);
  assert.match(renderLocalOfferReview(complete,{now}),/Source outcomePrices array: not supplied/);
});

test('unverified selection token stays null and missing prices do not invent a contract gap',()=>{
  const review=fixture(),row=review.observations[0];
  row.selection_id=null;
  row.gaps.push('Offered selection token mapping remains unverified.');
  row.prices_as_supplied.outcomePrices=null;
  row.prices_as_supplied.bestBid=null;row.prices_as_supplied.bestAsk=null;
  validateLocalOfferReview(review,now);
  const html=renderLocalOfferReview(review,{now});
  assert.match(html,/selection\/token mapping unverified/);
  assert.match(html,/Source outcomePrices array: not supplied/);
  assert.equal(row.gaps.some(gap=>/price/i.test(gap)),false);
  assert.doesNotMatch(html,/offered Yes token: null/);
  for(const invalid of ['',12,{},false]){
    const changed=structuredClone(review);changed.observations[0].selection_id=invalid;
    assert.throws(()=>validateLocalOfferReview(changed,now),/selection identity/);
  }
});

test('capture and publication clocks stay distinct with microsecond ordering and explicit source anomalies',()=>{
  assert.throws(()=>validateLocalOfferReview(mutate(r=>r.observations[0].observed_at='2026-10-21T12:01:00.000001Z'),now),/observation/);
  assert.throws(()=>validateLocalOfferReview(fixture(),'2026-10-21T12:00:59.999999Z'),/generation/);
  for(const clock of ['2026-10-21T12:00:00Z','2026-02-30T12:00:00.000000Z','invalid'])
    assert.throws(()=>validateLocalOfferReview(mutate(r=>r.observations[0].observed_at=clock),now));
  const anomaly=mutate(r=>r.observations[0].source_updated_at='2026-10-21T12:00:00.000001Z');
  assert.throws(()=>validateLocalOfferReview(anomaly,now),/source-update/);
  anomaly.observations[0].gaps.push('source_update_later_than_observation');
  validateLocalOfferReview(anomaly,now);
  const html=renderLocalOfferReview(anomaly,{now});
  assert.match(html,/Review generated: 2026-10-21 12:01:00.000000 UTC/);
  assert.match(html,/Source observed: 2026-10-21 12:00:00.000000 UTC/);
});

test('literal outcome prices cannot be relabeled or silently converted into sportsbook or pickem prices',()=>{
  const aboveOne='1.0000000000000000001';
  for(const change of [r=>r.observations[0].selection='over',r=>r.observations[0].operator='>=',
    r=>r.observations[0].prices_as_supplied.outcomes=['Over','Under'],r=>r.observations[0].prices_as_supplied.outcomePrices=[1.8,1.9],
    r=>r.observations[0].prices_as_supplied.bestBid='1.91',r=>r.observations[0].sportsbook_price_status='OBSERVED_PRICE_NOT_QUALIFIED',
    r=>r.observations[0].threshold=20.5,r=>r.observations[0].variant='Sleeper Picks',
    r=>r.observations[0].prices_as_supplied.outcomePrices=[aboveOne,'0'],
    r=>r.observations[0].prices_as_supplied.bestBid=aboveOne,
    r=>r.observations[0].prices_as_supplied.bestAsk=aboveOne])
    assert.throws(()=>validateLocalOfferReview(mutate(change),now));
  const tiny='0.0000000000000000001';
  const exact=mutate(r=>{r.observations[0].prices_as_supplied.outcomePrices=[tiny,'1.0000000000000000000'];
    r.observations[0].prices_as_supplied.bestBid=tiny;r.observations[0].prices_as_supplied.bestAsk='1.0000000000000000000';});
  validateLocalOfferReview(exact,now);
  assert.ok(renderLocalOfferReview(exact,{now}).includes(tiny));
});

test('full category inventory, parsed counts and unique source markets are enforced',()=>{
  for(const change of [r=>delete r.category_coverage.PA,r=>r.category_coverage.PTS.status='UNOBSERVED_IN_SAMPLE',
    r=>r.category_coverage.PTS.parsed_rows=0,r=>r.counts.rows_parsed=0,r=>r.counts.player_rows_observed=33,
    r=>r.category_coverage.PTS.status='OBSERVED_COMPLETE',r=>r.counts.rows_parsed=true,
    r=>{r.observations.push(structuredClone(r.observations[0]));r.counts.player_rows_observed=2;r.counts.rows_parsed=2;r.category_coverage.PTS.observed_rows=2;r.category_coverage.PTS.parsed_rows=2;}])
    assert.throws(()=>validateLocalOfferReview(mutate(change),now));
  const html=renderLocalOfferReview(fixture(),{now});
  for(const category of ALL_NBA_CATEGORIES)assert.ok(html.includes(`<th scope="row">${category}</th>`));
});

test('all source strings are escaped and no network or qualification action is rendered',()=>{
  const review=fixture();review.observations[0].player_name='<img src=x onerror=alert(1)>';
  review.observations[0].event_label='<script>untrusted</script>';
  review.observations[0].gaps[0]='<a href="https://example.invalid">gap</a>';
  const html=renderLocalOfferReview(review,{now});
  assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;'));
  assert.ok(html.includes('&lt;script&gt;untrusted&lt;/script&gt;'));
  assert.doesNotMatch(html,/<(?:img|script|iframe|a\s|button|form)\b/i);
});

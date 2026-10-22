// Shared, explicitly fictional fixture. No real source permission or offer proof.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash,webcrypto} from 'node:crypto';
import {ALL_NBA_CATEGORIES} from '../research.mjs';
import {validateOfferAsset} from '../offers.mjs';
import {validateLocalOfferReview} from '../local-offer-review.mjs';
import {canonicalSemanticReview,requiredSemanticGaps,validateSemanticOfferReview,
  verifySemanticOfferReviewHash,renderSemanticOfferReview} from '../semantic-offer-review.mjs';

const fixture=JSON.parse(await readFile(new URL('../../tests/fixtures/semantic_offer_v2.json',import.meta.url),'utf8'));
const now='2026-10-21T12:02:00.000000Z';
const original=()=>structuredClone(fixture.contract);
function seal(contract){delete contract.contract_id;contract.contract_id=createHash('sha256').update(canonicalSemanticReview(contract)).digest('hex');return contract;}
function change(mutate){const contract=original();mutate(contract);return seal(contract);}
function derive(contract){contract.required_gaps=requiredSemanticGaps(contract);contract.semantic_status=contract.required_gaps.length?'INCOMPLETE':'COMPLETE_LOCAL';contract.completed_at=contract.required_gaps.length?null:contract.normalized_at;return seal(contract);}
const removeBindings=(contract,fields)=>{contract.bindings=contract.bindings.filter(binding=>!fields.includes(binding.field));};

test('shared complete price-free fixture keeps native IDs and execution separate from semantics',async()=>{
  const contract=original();validateSemanticOfferReview(contract,now);await verifySemanticOfferReviewHash(contract,webcrypto);
  assert.equal(contract.semantic_status,'COMPLETE_LOCAL');assert.deepEqual(contract.required_gaps,[]);
  assert.equal(contract.player.native_provider_id,null);assert.equal(contract.selection.native_token_id,null);
  assert.deepEqual(contract.price,{status:'PRICE_UNAVAILABLE',value:null});
  assert.equal(contract.execution_review.eligible,false);assert.equal(contract.public_admission,false);
  const html=renderSemanticOfferReview(contract,{now});
  for(const text of ['Synthetic software fixture','Fictional Player','Fictional Away vs. Fictional Home','YES: PTS &gt; 19.5',
    'Complete under the registered local semantic v2 requirements','PRICE_UNAVAILABLE','Paper Builder: NO_ACTION'])assert.ok(html.includes(text),text);
  assert.match(html,/native provider revision/);
  assert.match(html,/Source: Polymarket\. Venue: Polymarket/);
  assert.match(html,/source market fictional-market \+ outcome label Yes/);
});

test('required gaps are recomputed and cannot be erased or flag-flipped',()=>{
  const incomplete=original();incomplete.event.player_team_id=null;incomplete.event.opponent_id=null;
  incomplete.settlement.stat_corrections=null;incomplete.event.source_version_literal=null;
  removeBindings(incomplete,['event.player_team_id','event.opponent_id','settlement.stat_corrections','event.source_version_literal']);
  derive(incomplete);validateSemanticOfferReview(incomplete,now);
  assert.deepEqual(incomplete.required_gaps,['PLAYER_TEAM','PLAYER_OPPONENT','SETTLEMENT_STAT_CORRECTIONS']);
  const html=renderSemanticOfferReview(incomplete,{now});
  assert.match(html,/Semantic interpretation incomplete/);assert.match(html,/stat corrections/);assert.match(html,/UNRESOLVED/);
  for(const mutate of [c=>c.required_gaps=[],c=>c.semantic_status='COMPLETE_LOCAL',c=>c.completed_at=c.normalized_at]){
    const bad=structuredClone(incomplete);mutate(bad);seal(bad);assert.throws(()=>validateSemanticOfferReview(bad,now));
  }
  const placeholder=change(c=>c.settlement.stat_corrections='UNRESOLVED');
  assert.throws(()=>validateSemanticOfferReview(placeholder,now),/settlement/);
  assert.throws(()=>validateSemanticOfferReview(change(c=>c.settlement.stat_corrections='The decision is final after arbitration.'),now),/Generic finality/);
  assert.throws(()=>validateSemanticOfferReview(change(c=>c.settlement.stat_corrections='The correct winner receives the payout.'),now),/Generic finality/);
  for (const policy of ['STATİSTICAL corrections are applied.', 'Stat\u0085corrections are applied.'])
    assert.throws(()=>validateSemanticOfferReview(change(c=>c.settlement.stat_corrections=policy),now),/Generic finality/);
});

test('later knowledge cannot backdate, freshen or replace the original contract observation',()=>{
  for(const mutate of [c=>c.contract_observed_at=c.knowledge_observed_at,c=>c.knowledge_observed_at=c.contract_observed_at,
    c=>c.normalized_at=c.contract_observed_at,c=>c.completed_at=c.knowledge_observed_at,
    c=>c.evidence[0].source_updated_at='2026-10-21T12:00:00.000001Z',
    c=>c.evidence[0].request_started_at='2026-10-21T12:00:00.000001Z'])
    assert.throws(()=>validateSemanticOfferReview(change(mutate),now));
  assert.throws(()=>validateSemanticOfferReview(original(),'2026-10-21T12:00:59.999999Z'),/clocks/);
  const html=renderSemanticOfferReview(original(),{now});
  assert.match(html,/Contract observed: 2026-10-21 12:00:00.000000 UTC/);
  assert.match(html,/Latest linked knowledge observed: 2026-10-21 12:00:15.000000 UTC/);
  assert.match(html,/Later knowledge does not refresh the original contract observation/);
});

test('all critical source fields need exact reviewed binding roles and references',()=>{
  for(const mutate of [c=>c.bindings.pop(),c=>c.bindings.push(structuredClone(c.bindings[0])),
    c=>c.bindings[0].evidence_id='missing',c=>c.bindings[0].transform='eval',
    c=>c.bindings.find(binding=>binding.field==='player.canonical_identity').transform='direct',
    c=>c.bindings.find(binding=>binding.field==='event.event_version').transform='direct',
    c=>c.bindings.find(binding=>binding.field==='predicate.operator').transform='direct',
    c=>c.bindings.find(binding=>binding.field==='player.canonical_identity').pointer='',
    c=>c.bindings.find(binding=>binding.field==='event.event_version').pointer='/version',
    c=>c.bindings.find(binding=>binding.field==='predicate.units').evidence_id='event',
    c=>{const b=c.bindings.find(binding=>binding.field==='player.source_label');b.pointer='/playerAlias';b.transform='direct';},
    c=>c.bindings.find(binding=>binding.field==='event.label').pointer='/titleAlias',
    c=>{const b=c.bindings.find(binding=>binding.field==='selection.market_id');b.pointer='/marketAlias';b.transform='direct';},
    c=>c.bindings.find(binding=>binding.field==='settlement.stat_corrections').evidence_id='event',
    c=>c.evidence_lane='ACTUAL_SOURCE_OBSERVATION',
    c=>c.evidence[0].url='https://gamma-api.polymarket.com/markets/wrong-market',
    c=>c.evidence[1].url='https://gamma-api.polymarket.com/events/wrong-event',
    c=>c.evidence[2].url='https://www.wikidata.org/wiki/Special:EntityData/Q90000002.json',
    c=>c.bindings.push({field:'player.native_provider_id',evidence_id:'market',pointer:'/id',transform:'native_player_id'}),
    c=>c.evidence[0].url='https://unreviewed.example/market',c=>c.evidence[0].url='https://gamma-api.polymarket.com:443/markets/id',
    c=>c.evidence[0].url='https://actor:secret@gamma-api.polymarket.com/markets/id'])
    assert.throws(()=>validateSemanticOfferReview(change(mutate),now));
});

test('exact binary price strings and semantic thresholds never pass through floating-point range rounding',()=>{
  const aboveOne='1.0000000000000000001';
  for(const mutate of [c=>c.unassigned_source_economics.outcome_prices=[aboveOne,'0'],
    c=>c.unassigned_source_economics.best_bid=aboveOne,c=>c.unassigned_source_economics.best_ask=aboveOne,
    c=>c.predicate.threshold='1000000.0000000000000001',c=>c.price={status:'OBSERVED_PRICE_NOT_QUALIFIED',value:'0.5'}])
    assert.throws(()=>validateSemanticOfferReview(change(mutate),now));
  const tiny='0.0000000000000000001',contract=original();
  contract.unassigned_source_economics.outcome_prices=[tiny,'1.0000000000000000000'];
  contract.bindings.push({field:'unassigned_source_economics.outcome_prices',evidence_id:'market',pointer:'/outcomePrices',transform:'json_array'});
  seal(contract);validateSemanticOfferReview(contract,now);
  assert.deepEqual(contract.required_gaps,[]);assert.equal(contract.semantic_status,'COMPLETE_LOCAL');
  const html=renderSemanticOfferReview(contract,{now});assert.ok(html.includes(tiny));
  assert.match(html,/Array order is not used to assign a selection price/);
  assert.doesNotMatch(html,/Yes: 0\./);
});

test('v2 is isolated from old local/public schemas, sport scope and qualification',()=>{
  const contract=original();
  assert.throws(()=>validateOfferAsset(contract,now));assert.throws(()=>validateLocalOfferReview(contract,now));
  for(const mutate of [c=>c.public_admission=true,c=>c.ticket_eligibility=true,c=>c.execution_review.eligible=true,
    c=>c.qualification='QUALIFIED',c=>c.source.venue='DraftKings',c=>c.source.product='sportsbook',
    c=>c.selection.outcome_label='over',c=>c.category_inventory.pop(),c=>c.selection.condition_id='wrong',
    c=>c.selection.native_token_id='0',c=>c.player.canonical_identity.id='Q0'])
    assert.throws(()=>validateSemanticOfferReview(change(mutate),now));
  const html=renderSemanticOfferReview(contract,{now});
  for(const category of ALL_NBA_CATEGORIES)assert.ok(html.includes(`<th scope="row">${category}</th>`));
  assert.match(html,/does not assert that every category was observed or qualified/);
});

test('source text is escaped and record hashes detect coherent-looking modified content',async()=>{
  const changed=original();changed.player.source_label='<img src=x onerror=alert(1)>';changed.player.canonical_identity.label=changed.player.source_label;
  changed.event.label='<script>untrusted</script>';seal(changed);
  const html=renderSemanticOfferReview(changed,{now});
  assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;'));assert.ok(html.includes('&lt;script&gt;untrusted&lt;/script&gt;'));
  assert.doesNotMatch(html,/<(?:img|script|iframe|a\s|button|form)\b/i);
  await verifySemanticOfferReviewHash(changed,webcrypto);
  changed.event.label='Changed without resealing';
  await assert.rejects(()=>verifySemanticOfferReviewHash(changed,webcrypto),/seal mismatch/);
});

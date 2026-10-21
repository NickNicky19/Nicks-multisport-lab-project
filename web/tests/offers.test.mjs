// Entirely fictional contracts. No real source rights, prices, or offers issued.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash, webcrypto} from 'node:crypto';
import {ALL_NBA_CATEGORIES} from '../research.mjs';
import {APPROVED_PUBLIC_ADMISSION_IDS,canonicalOffer,validateOffer,validateOfferAsset,validateOfferDescriptor,
  verifyOfferAssetHashes,matchResearchForecast,offerDisplayState,renderOffers} from '../offers.mjs';

const now='2026-10-20T18:01:00.000000Z';
const hash=value=>createHash('sha256').update(canonicalOffer(value)).digest('hex');
const seal=(value,key)=>{value=structuredClone(value);delete value[key];return {...value,[key]:hash(value)};};
const providerFields=['name','id_namespace','event_id','player_id','market_id','selection_id'];
const settlementFields=['participation','dnp','postponement','ties','official_stat_source','stat_corrections'];
const boundFields=['id_namespace','event_id','event_version','event_starts_at','player_id','player_label','team_id','opponent_id','stat','period','extra_time_policy','line','side','variant','venue','product','settlement_version','stat_definition','market_status',...providerFields.map(key=>`provider.${key}`),...settlementFields.map(key=>`settlement_terms.${key}`)];
const roles={
  CONTRACT_VIEW:['provider.selection_id','provider.market_id','provider.event_id','provider.player_id','stat','line','side','market_status'],
  EVENT_IDENTITY:['event_id','event_version','event_starts_at','team_id','opponent_id'],
  PLAYER_IDENTITY:['player_id','player_label','team_id'],
  RULES:['period','extra_time_policy','variant','product','settlement_version','stat_definition',...settlementFields.map(key=>`settlement_terms.${key}`)],
  CROSSWALK:['id_namespace','provider.id_namespace','provider.event_id','provider.player_id']};
const target=(o,k)=>k.includes('.')?o[k.split('.')[0]][k.split('.')[1]]:o[k];
function finish(offer,admission){
  admission={...admission,subject_sha256:hash(Object.fromEntries(Object.entries(offer).filter(([k])=>!['offer_id','admission_id'].includes(k))))};
  admission=seal(admission,'admission_id');offer=seal({...offer,admission_id:admission.admission_id},'offer_id');return {offer,admission};
}
function fixture({priced=false}={}){
  let offer={schema_version:'nba-player-offer-v1',sport:'basketball',league:'NBA',id_namespace:'espn',event_id:'synthetic-event',event_version:'e'.repeat(64),
    event_starts_at:'2026-10-20T19:30:00.000000Z',player_id:'synthetic-player',player_label:'Synthetic Player',team_id:'synthetic-home',opponent_id:'synthetic-away',
    stat:'PTS',units:'points',period:'full_game',extra_time_policy:'includes_overtime',line:'12.5',side:'over',variant:'synthetic-standard',venue:'Synthetic Test Venue',product:'Synthetic Test Product',settlement_version:'synthetic-rules-1',
    stat_definition:'Synthetic points credited to this player in the full game including overtime.',
    settlement_terms:{status:'SOURCE_VERIFIED',participation:'Synthetic rule: one recorded appearance is required.',dnp:'Synthetic rule: no appearance voids this selection.',
      postponement:'Synthetic rule: a postponed game voids this selection.',ties:'Synthetic rule: an exact line tie pushes this selection.',official_stat_source:'Fictional Test League official final box score.',
      stat_corrections:'Synthetic rule: official corrections accepted within 24 hours of final status.'},
    provider:{name:'Synthetic Provider',id_namespace:'synthetic',event_id:'test-event',player_id:'test-player',market_id:'test-market',selection_id:'test-selection'},
    observed_at:'2026-10-20T17:59:00.000000Z',source_updated_at:null,imported_at:'2026-10-20T17:59:01.000000Z',market_status:'PRE_GAME',evidence_lane:'SYNTHETIC_TEST',source_evidence:[],
    price_status:priced?'OBSERVED_PRICE_NOT_QUALIFIED':'PRICE_UNAVAILABLE',price:priced?{kind:'pickem_multiplier',value:'1.04',evidence_id:'synthetic-contract_view'}:null,quote:null,qualification:'UNAVAILABLE'};
  const required=[...boundFields,...(priced?['price.kind','price.value']:[])];
  for(const [kind,keys]of Object.entries(roles))offer.source_evidence.push({evidence_id:`synthetic-${kind.toLowerCase()}`,kind,
    source_url:'https://source.example.test/contract',raw_sha256:'c'.repeat(64),raw_bytes:1000,raw_record_id:'a'.repeat(64),
    request_started_at:'2026-10-20T17:58:59.000000Z',observed_at:offer.observed_at,source_updated_at:null,
    bindings:Object.fromEntries((kind==='CONTRACT_VIEW'?required:keys).map(key=>[key,{pointer:`/fields/${key}`,source_value:target(offer,key),meaning:target(offer,key)}]))});
  let admission={schema_version:'nba-offer-publication-admission-v1',subject_sha256:'',reviewed_at:now,reviewer:'Synthetic software test reviewer',decision:'SYNTHETIC_ONLY',scope:'ONE_CAPTURE_DERIVED_FACTS_ONLY',
    basis:{kind:'SYNTHETIC_FIXTURE',reference:'software-test-only',evidence_sha256:'f'.repeat(64),description:'Fictional fixture; no real source permission or observation claimed.'},raw_redistribution:false,scheduled_collection:false};
  return finish(offer,admission);
}
function assetFixture(){const {offer,admission}=fixture();return seal({schema_version:'nba-player-offers-v1',league:'NBA',generated_at:now,status:'OFFER_ONLY_RESEARCH',category_inventory:ALL_NBA_CATEGORIES,offers:[offer],admissions:[admission],unavailable_reasons:[]},'asset_id');}
function textRulesFixture(mediaType='text/html'){
  let {offer,admission}=fixture();const e=offer.source_evidence.find(e=>e.kind==='RULES');
  const quotes=Object.fromEntries(roles.RULES.map(key=>[key,`Synthetic café source ${key}: ${target(offer,key)}`]));
  const text=Buffer.from(Object.values(quotes).join(mediaType==='text/plain'?'\r\n':' '),'utf8');
  const raw=mediaType==='text/plain'?text:Buffer.from(`<main>${Object.values(quotes).map(quote=>`<p>${quote}</p>`).join('')}</main>`,'utf8');
  Object.assign(e,{source_url:'https://source.example.test/rules',raw_record_id:'b'.repeat(64),raw_bytes:raw.byteLength,
    raw_sha256:createHash('sha256').update(raw).digest('hex'),text_replay:{schema_version:'source-evidence-text-v1',media_type:mediaType,encoding:'utf-8',
      extractor:mediaType==='text/plain'?'utf8-text-v1':'html-static-text-v1',text_sha256:createHash('sha256').update(text).digest('hex'),text_bytes:text.byteLength},
    bindings:Object.fromEntries(Object.entries(quotes).map(([key,quote])=>{const encoded=Buffer.from(quote,'utf8'),start=text.indexOf(encoded);
      return [key,{start,end:start+encoded.byteLength,source_value:quote,meaning:target(offer,key)}];}))});
  return finish(offer,admission);
}
function forecastFixture(offer){return {...Object.fromEntries(['league','id_namespace','event_id','event_version','player_id','team_id','opponent_id','event_starts_at','period','extra_time_policy'].map(key=>[key,offer[key]])),
  cutoff_at:'2026-10-20T18:00:00.000000Z',issued_at:'2026-10-20T18:00:05.000000Z',evidence_lane:'REAL_TIME_CAPTURED',conditioning:'CONDITIONAL_ON_APPEARANCE',categories:[{code:'PTS',units:'points'}]};}

test('complete price-unavailable contract is distinct from a partial observation or quote',async()=>{
  const asset=assetFixture();validateOfferAsset(asset,now,{allowSynthetic:true});await verifyOfferAssetHashes(asset,webcrypto);
  assert.equal(asset.offers[0].price,null);assert.equal(asset.offers[0].quote,null);assert.equal(asset.offers[0].qualification,'UNAVAILABLE');
  assert.throws(()=>validateOfferAsset(asset,now),/publicly admitted/);
});
test('explicit HTML/plain RULES quotation descriptors preserve coherent offer-only validation',async()=>{
  for(const mediaType of ['text/html','text/plain']){
    const {offer,admission}=textRulesFixture(mediaType);validateOffer(offer,admission,now,{allowSynthetic:true});
    const asset=seal({schema_version:'nba-player-offers-v1',league:'NBA',generated_at:now,status:'OFFER_ONLY_RESEARCH',category_inventory:ALL_NBA_CATEGORIES,
      offers:[offer],admissions:[admission],unavailable_reasons:[]},'asset_id');
    validateOfferAsset(asset,now,{allowSynthetic:true});await verifyOfferAssetHashes(asset,webcrypto);
    assert.equal(offer.price,null);assert.equal(offer.qualification,'UNAVAILABLE');
    assert.throws(()=>validateOffer(offer,admission,now),/publicly admitted/);
    const binding=offer.source_evidence.find(e=>e.kind==='RULES').bindings.period;
    assert.equal(binding.end-binding.start,Buffer.byteLength(binding.source_value,'utf8'));
    assert.notEqual(binding.end-binding.start,binding.source_value.length);
  }
});
test('text RULES versions, byte spans and meanings cannot be silently reinterpreted',()=>{
  const mutations=[e=>e.text_replay.extractor='json-summary-v1',e=>e.text_replay.media_type=['text/html'],e=>e.text_replay.encoding='latin-1',
    e=>e.text_replay.text_bytes=true,e=>e.text_replay.text_bytes=0,e=>e.text_replay.text_sha256='bad',
    e=>e.bindings.period.pointer='/period',e=>e.bindings.period.start=true,e=>e.bindings.period.end++,
    e=>e.bindings.period.source_value='\ud800',e=>e.bindings.period.meaning='first_quarter'];
  for(const change of mutations){let {offer,admission}=textRulesFixture();change(offer.source_evidence.find(e=>e.kind==='RULES'));
    ({offer,admission}=finish(offer,admission));assert.throws(()=>validateOffer(offer,admission,now,{allowSynthetic:true}));}
  let {offer,admission}=textRulesFixture();offer.source_evidence.find(e=>e.kind==='CONTRACT_VIEW').text_replay=offer.source_evidence.find(e=>e.kind==='RULES').text_replay;
  ({offer,admission}=finish(offer,admission));assert.throws(()=>validateOffer(offer,admission,now,{allowSynthetic:true}),/restricted to RULES/);
});
test('actual permission review cannot self-admit and the reviewed registry is empty',()=>{
  let {offer,admission}=fixture();offer.evidence_lane='REAL_TIME_CAPTURED';admission.decision='ADMITTED_DERIVED_FACTS';admission.basis.kind='PUBLIC_SOURCE_SCOPED_REVIEW';
  ({offer,admission}=finish(offer,admission));assert.throws(()=>validateOffer(offer,admission,now),/reviewed registry/);assert.deepEqual(APPROVED_PUBLIC_ADMISSION_IDS,[]);
});
test('rehashed contradictions in identity, period, rules, side and clocks fail',()=>{
  for(const change of [o=>o.side='unknown',o=>o.period=null,o=>o.extra_time_policy='unknown',o=>o.units='rebounds',o=>o.provider.player_id='wrong',
    o=>o.source_updated_at='2026-10-20T17:59:00.000001Z',o=>o.source_evidence.pop(),o=>o.quote={decimal_odds:'1.04'},
    o=>delete o.settlement_terms.dnp,o=>o.settlement_terms.dnp='UNKNOWN',o=>o.stat_definition='',
    o=>o.source_evidence.find(e=>e.kind==='RULES').bindings.period.meaning='first_quarter']){
    let {offer,admission}=fixture();change(offer);({offer,admission}=finish(offer,admission));assert.throws(()=>validateOffer(offer,admission,now,{allowSynthetic:true}));
  }
});
test('observed side multiplier stays a multiplier and line/side/price share observation',()=>{
  let {offer,admission}=fixture({priced:true});validateOffer(offer,admission,now,{allowSynthetic:true});
  assert.match(offerDisplayState(offer,now).price_label,/not sportsbook odds/);
  offer.price.kind='sportsbook_decimal';({offer,admission}=finish(offer,admission));assert.throws(()=>validateOffer(offer,admission,now,{allowSynthetic:true}),/contradicts/);
});
test('nested byte/hash seals and reviewed subject binding are verified independently',async()=>{
  const asset=assetFixture();asset.offers[0].player_label='Altered name';asset.asset_id=hash(Object.fromEntries(Object.entries(asset).filter(([k])=>k!=='asset_id')));
  await assert.rejects(()=>verifyOfferAssetHashes(asset,webcrypto),/record seal/);
  const other=assetFixture();other.admissions[0].subject_sha256='d'.repeat(64);other.admissions[0]=seal(other.admissions[0],'admission_id');
  other.offers[0].admission_id=other.admissions[0].admission_id;other.offers[0]=seal(other.offers[0],'offer_id');const re=seal(other,'asset_id');
  await assert.rejects(()=>verifyOfferAssetHashes(re,webcrypto),/exact offer/);
});
test('unsafe descriptor, duplicated selection and incomplete inventory fail before use',()=>{
  const sha='a'.repeat(64),d={path:`nba-offers.${sha}.json`,sha256:sha,generated_at:now,status:'OFFER_ONLY_RESEARCH',retained:false,error:null};
  validateOfferDescriptor(d,now);assert.throws(()=>validateOfferDescriptor({...d,path:`../${d.path}`},now));
  const duplicate=assetFixture();duplicate.offers.push(structuredClone(duplicate.offers[0]));assert.throws(()=>validateOfferAsset(duplicate,now,{allowSynthetic:true}),/Duplicate/);
  const missing=assetFixture();missing.category_inventory=missing.category_inventory.filter(c=>c!=='TD');assert.throws(()=>validateOfferAsset(missing,now,{allowSynthetic:true}),/inventory/);
});
test('matching requires exact namespaces, version, meaning and pregame decision clocks without requiring a price',()=>{
  const {offer}=fixture();offer.evidence_lane='REAL_TIME_CAPTURED';const forecast=forecastFixture(offer);
  const result=matchResearchForecast(offer,forecast,now);assert.equal(result.status,'MATCHED_RESEARCH_ONLY');assert.equal(result.ev,null);assert.equal(result.ticket_eligible,false);
  for(const delta of [{event_version:'b'.repeat(64)},{id_namespace:'sleeper'},{period:'first_quarter'},{extra_time_policy:'regulation_only'},
    {evidence_lane:'RECONSTRUCTED_RESEARCH'},{issued_at:'2026-10-20T18:01:00.000001Z'}])assert.equal(matchResearchForecast(offer,{...forecast,...delta},now).status,'UNMATCHED');
  assert.equal(matchResearchForecast(offer,forecast,'2026-10-20T19:30:00.000000Z').status,'UNMATCHED');
});
test('display makes research, capture time, price limitations and source IDs visible and escapes names',()=>{
  const asset=assetFixture();asset.offers[0].player_label='<script>fictional</script>';const html=renderOffers(asset,{now});
  assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);assert.match(html,/Price unavailable/);assert.match(html,/not a recommendation/);
  assert.match(html,/Observed 2026-10-20T17:59:00.000000Z/);assert.match(html,/event version/);assert.match(html,/No published research forecast matches/);
  assert.equal(offerDisplayState(asset.offers[0],'2026-10-20T19:30:00.000000Z').status,'HISTORICAL_CAPTURE');
});

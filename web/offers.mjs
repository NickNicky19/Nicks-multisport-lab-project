// Complete, separately reviewed offer-only facts. Never an executable quote.
import {ALL_NBA_CATEGORIES, NBA_UNITS, utcMicros} from './research.mjs';
import {validateDailyAsset, verifyDailyHashes} from './sdv-daily.mjs';
import {validateProductionCollection, validateProductionIndex, verifyProductionHashes} from './production.mjs';
import {validateNativeOffer,verifyNativeOfferHash,renderNativeOffer,nativeOfferPubliclyAdmitted} from './native-offer.mjs';

// Add only after exact source/contract/rights review, with the Python pin.
export const APPROVED_PUBLIC_ADMISSION_IDS = Object.freeze([]);

const SHA = /^[a-f0-9]{64}$/;
const fields = (value, names) => value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).sort().join(',') === [...names].sort().join(',');
const require = (condition, message) => {if (!condition) throw new Error(message);};
const text = (value, max = 200) => typeof value === 'string' && value.length > 0 && value.length <= max && value.trim() === value;
const providerFields = ['name','id_namespace','event_id','player_id','market_id','selection_id'];
const settlementFields=['participation','dnp','postponement','ties','official_stat_source','stat_corrections'];
const boundFields = ['id_namespace','event_id','event_version','event_starts_at','player_id','player_label','team_id','opponent_id','stat','period','extra_time_policy','line','side','variant','venue','product','settlement_version','stat_definition','market_status',...providerFields.map(key=>`provider.${key}`),...settlementFields.map(key=>`settlement_terms.${key}`)];
const offerFields = ['schema_version','offer_id','sport','league','id_namespace','event_id','event_version','event_starts_at','player_id','player_label','team_id','opponent_id','stat','units','period','extra_time_policy','line','side','variant','venue','product','settlement_version','settlement_terms','stat_definition','provider','observed_at','source_updated_at','imported_at','market_status','evidence_lane','source_evidence','admission_id','price_status','price','quote','qualification'];
const admissionFields = ['schema_version','admission_id','subject_sha256','reviewed_at','reviewer','decision','scope','basis','raw_redistribution','scheduled_collection'];
const evidenceFields = ['evidence_id','kind','source_url','raw_sha256','raw_bytes','raw_record_id','request_started_at','observed_at','source_updated_at','bindings'];
const textReplayFields = ['schema_version','media_type','encoding','extractor','text_sha256','text_bytes'];
const textExtractors = Object.freeze({'text/html':'html-static-text-v1','text/plain':'utf8-text-v1'});
const evidenceKinds = ['CONTRACT_VIEW','EVENT_IDENTITY','PLAYER_IDENTITY','RULES','CROSSWALK'];
const kindBindings = {
  CONTRACT_VIEW:['provider.selection_id','provider.market_id','provider.event_id','provider.player_id','stat','line','side','market_status'],
  EVENT_IDENTITY:['event_id','event_version','event_starts_at','team_id','opponent_id'],
  PLAYER_IDENTITY:['player_id','player_label','team_id'],
  RULES:['period','extra_time_policy','variant','product','settlement_version','stat_definition',...settlementFields.map(key=>`settlement_terms.${key}`)],
  CROSSWALK:['id_namespace','provider.id_namespace','provider.event_id','provider.player_id']
};
const bytes = value => new TextEncoder().encode(canonicalOffer(value)).byteLength;
const same = (a,b) => canonicalOffer(a) === canonicalOffer(b);
const target = (offer,path) => path.includes('.') ? offer[path.split('.')[0]][path.split('.')[1]] : offer[path];
const decimal = value => typeof value === 'string' && value.length <= 32 && /^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value) && Number.isFinite(Number(value)) && Number(value)<=1000000;
const url = value => {try {const u=new URL(value);return text(value,2048)&&u.protocol==='https:'&&!!u.hostname&&!u.username&&!u.password&&!u.hash;} catch{return false;}};

// Public validation checks the reviewed descriptor and exact quotation span.
// Only backend replay against privately recovered original bytes proves a quote.
function validateTextReplay(replay){
  require(fields(replay,textReplayFields)&&replay.schema_version==='source-evidence-text-v1'&&replay.encoding==='utf-8'
    &&typeof replay.media_type==='string'&&Object.hasOwn(textExtractors,replay.media_type)&&replay.extractor===textExtractors[replay.media_type]
    &&typeof replay.text_sha256==='string'&&SHA.test(replay.text_sha256)
    &&Number.isSafeInteger(replay.text_bytes)&&replay.text_bytes>0&&replay.text_bytes<=512*1024,
    'Unsupported text replay descriptor/version/format.');
}
function validateTextBinding(binding,replay){
  require(fields(binding,['start','end','source_value','meaning'])&&Number.isSafeInteger(binding.start)&&Number.isSafeInteger(binding.end)
    &&binding.start>=0&&binding.end>binding.start&&binding.end<=replay.text_bytes
    &&typeof binding.source_value==='string'&&binding.source_value.length>0&&!/[\uD800-\uDFFF]/u.test(binding.source_value),
    'Invalid exact text quotation or UTF-8 byte span.');
  const length=new TextEncoder().encode(binding.source_value).byteLength;
  require(length<=4096&&length===binding.end-binding.start,'Quotation and UTF-8 byte span disagree.');
}

export function canonicalOffer(value) {
  if (value && typeof value === 'object') return Array.isArray(value) ? `[${value.map(canonicalOffer).join(',')}]` : `{${Object.keys(value).sort().map(key=>`${JSON.stringify(key)}:${canonicalOffer(value[key])}`).join(',')}}`;
  require(value === null || ['string','boolean','number'].includes(typeof value), 'Invalid offer JSON value.');
  if (typeof value === 'number') require(Number.isFinite(value) && (!Number.isInteger(value)||Number.isSafeInteger(value)), 'Unsafe offer JSON number.');
  return JSON.stringify(value);
}

export function validateOfferDescriptor(d,publishedAt) {
  require(fields(d,['path','sha256','generated_at','status','retained','error']) && SHA.test(d.sha256)
    && d.path===`nba-offers.${d.sha256}.json` && d.status==='OFFER_ONLY_RESEARCH'
    && typeof d.retained==='boolean' && (d.error===null||text(d.error,1000)), 'Invalid offer descriptor/path.');
  require(utcMicros(d.generated_at)<=utcMicros(publishedAt),'Future offer descriptor clock.');
  return d;
}

export function validateOffer(offer,admission,now,{allowSynthetic=false}={}) {
  require(fields(offer,offerFields)&&fields(admission,admissionFields)
    && offer.schema_version==='nba-player-offer-v1' && admission.schema_version==='nba-offer-publication-admission-v1'
    && SHA.test(offer.offer_id)&&SHA.test(admission.admission_id)&&SHA.test(admission.subject_sha256)
    && offer.admission_id===admission.admission_id,'Invalid offer/admission contract.');
  require(offer.sport==='basketball'&&offer.league==='NBA'&&SHA.test(offer.event_version),'Unsupported offer identity.');
  for(const key of ['id_namespace','event_id','player_id','player_label','team_id','opponent_id','variant','venue','product','settlement_version']) require(text(offer[key]),`Invalid offer ${key}.`);
  require(offer.team_id!==offer.opponent_id && ALL_NBA_CATEGORIES.includes(offer.stat)&&offer.units===NBA_UNITS[offer.stat],'Invalid offer teams/category/units.');
  require(text(offer.stat_definition,600)&&fields(offer.settlement_terms,['status',...settlementFields])&&offer.settlement_terms.status==='SOURCE_VERIFIED'
    &&settlementFields.every(key=>text(offer.settlement_terms[key],600)&&!['UNKNOWN','UNVERIFIED','UNRESOLVED','TBD','N/A'].includes(offer.settlement_terms[key].toUpperCase())),
    'Missing source-verified statistic or settlement meaning.');
  require(offer.period==='full_game'&&['includes_overtime','regulation_only'].includes(offer.extra_time_policy)
    && decimal(offer.line)&&['over','under'].includes(offer.side),'Unverified offer period/OT/line/side.');
  require(fields(offer.provider,providerFields)&&Object.values(offer.provider).every(v=>text(v)),'Incomplete provider identity.');
  const observed=utcMicros(offer.observed_at), imported=utcMicros(offer.imported_at), start=utcMicros(offer.event_starts_at), reviewed=utcMicros(admission.reviewed_at);
  require(observed<=imported&&imported<=reviewed&&reviewed<=utcMicros(now),'Offer/import/review clocks disagree.');
  if(offer.source_updated_at!==null)require(utcMicros(offer.source_updated_at)<=observed,'Source update after observation.');
  require(['PRE_GAME','LIVE','CLOSED','SUSPENDED'].includes(offer.market_status),'Unknown source market status.');
  if(offer.market_status==='PRE_GAME')require(observed<start,'Pregame offer captured after event start.');
  const synthetic=offer.evidence_lane==='SYNTHETIC_TEST';
  require(['REAL_TIME_CAPTURED','SYNTHETIC_TEST'].includes(offer.evidence_lane)&&(!synthetic||allowSynthetic),'Synthetic/reconstructed offers cannot be publicly admitted.');
  require(admission.decision===(synthetic?'SYNTHETIC_ONLY':'ADMITTED_DERIVED_FACTS')&&admission.scope==='ONE_CAPTURE_DERIVED_FACTS_ONLY'
    &&admission.raw_redistribution===false&&admission.scheduled_collection===false&&text(admission.reviewer),'Unreviewed offer publication scope.');
  require(synthetic||APPROVED_PUBLIC_ADMISSION_IDS.includes(admission.admission_id),'Actual public offer admission is not in the reviewed registry.');
  require(fields(admission.basis,['kind','reference','evidence_sha256','description'])
    &&(synthetic?['SYNTHETIC_FIXTURE']:['PUBLIC_SOURCE_SCOPED_REVIEW','SOURCE_LICENSE','EXPLICIT_PROVIDER_PERMISSION','USER_PROVIDED_RIGHTS']).includes(admission.basis.kind)
    &&text(admission.basis.reference,2048)&&SHA.test(admission.basis.evidence_sha256)&&text(admission.basis.description,1000),'Unestablished offer review basis.');
  require(Array.isArray(offer.source_evidence)&&offer.source_evidence.length>=1&&offer.source_evidence.length<=8,'Bounded offer evidence required.');
  const required=[...boundFields,...(offer.price===null?[]:['price.kind','price.value'])];
  if(offer.price!==null)require(fields(offer.price,['kind','value','evidence_id']),'Malformed observed price.');
  const ids=new Set(),covered=new Set(),kinds=new Set();
  for(const e of offer.source_evidence){
    const textRules=!!e&&typeof e==='object'&&Object.hasOwn(e,'text_replay');
    require(fields(e,textRules?[...evidenceFields,'text_replay']:evidenceFields)&&text(e.evidence_id)&&!ids.has(e.evidence_id)&&evidenceKinds.includes(e.kind)
      &&url(e.source_url)&&SHA.test(e.raw_sha256)&&SHA.test(e.raw_record_id)&&Number.isSafeInteger(e.raw_bytes)&&e.raw_bytes>0&&e.raw_bytes<=2*1024*1024,'Invalid offer source evidence.');
    if(textRules){require(e.kind==='RULES','Text replay is restricted to RULES evidence.');validateTextReplay(e.text_replay);}
    ids.add(e.evidence_id);kinds.add(e.kind);
    const at=utcMicros(e.observed_at);
    require(utcMicros(e.request_started_at)<=at&&at<=imported,'Evidence observation clocks disagree.');
    if(e.source_updated_at!==null)require(utcMicros(e.source_updated_at)<=at,'Evidence source update after observation.');
    require(e.bindings&&typeof e.bindings==='object'&&!Array.isArray(e.bindings)&&Object.keys(e.bindings).length>0,'Missing normalized offer bindings.');
    require(kindBindings[e.kind].every(key=>Object.hasOwn(e.bindings,key)),'Source evidence lacks the fields required for its claimed role.');
    if(e.kind==='CONTRACT_VIEW')require(e.observed_at===offer.observed_at&&e.source_updated_at===offer.source_updated_at,'Contract observation/update clocks differ from offer.');
    for(const [key,binding]of Object.entries(e.bindings)){
      require(required.includes(key),'Unknown normalized source binding.');
      if(textRules)validateTextBinding(binding,e.text_replay);
      else require(fields(binding,['pointer','source_value','meaning'])&&text(binding.pointer,512)&&binding.pointer.startsWith('/'),'Source binding requires a JSON pointer.');
      require(same(binding.meaning,target(offer,key)),'Source binding contradicts normalized offer.');
      covered.add(key);
    }
  }
  require(covered.size===required.length&&required.every(key=>covered.has(key))&&evidenceKinds.every(kind=>kinds.has(kind)),'Incomplete contract, identity, crosswalk, or rules evidence.');
  require(offer.quote===null&&offer.qualification==='UNAVAILABLE','Offer display does not confer quote/ticket eligibility.');
  if(offer.price===null)require(offer.price_status==='PRICE_UNAVAILABLE','Missing price status disagrees.');
  else {
    require(fields(offer.price,['kind','value','evidence_id'])&&offer.price_status==='OBSERVED_PRICE_NOT_QUALIFIED'
      &&['sportsbook_decimal','pickem_multiplier'].includes(offer.price.kind)&&ids.has(offer.price.evidence_id)&&decimal(offer.price.value)
      &&Number(offer.price.value)>(offer.price.kind==='sportsbook_decimal'?1:0),'Invalid observed price source/type/value.');
    const source=offer.source_evidence.find(e=>e.evidence_id===offer.price.evidence_id);
    require(['price.kind','price.value','line','side','provider.selection_id'].every(key=>Object.hasOwn(source.bindings,key))
      &&source.observed_at===offer.observed_at,'Line, side and price must be one observation.');
  }
  require(bytes(offer)<=32*1024,'Offer exceeds encoded limit.');
  return offer;
}

export function validateOfferAsset(asset,now,{allowSynthetic=false}={}){
  require(fields(asset,['schema_version','asset_id','league','generated_at','status','category_inventory','admissions','offers','unavailable_reasons'])
    &&['nba-player-offers-v1','nba-player-offers-v2'].includes(asset.schema_version)&&SHA.test(asset.asset_id)&&asset.league==='NBA'
    &&asset.status==='OFFER_ONLY_RESEARCH'&&same(asset.category_inventory,ALL_NBA_CATEGORIES),'Invalid offer asset/category inventory.');
  require(utcMicros(asset.generated_at)<=utcMicros(now)&&Array.isArray(asset.offers)&&asset.offers.length<=32
    &&Array.isArray(asset.admissions)&&asset.admissions.length<=32,'Offer asset clock/count limit exceeded.');
  const admissions=new Map();
  for(const a of asset.admissions){require(a&&typeof a==='object'&&!admissions.has(a.admission_id),'Duplicate offer review.');admissions.set(a.admission_id,a);}
  const ids=new Set(),used=new Set(),selections=new Set();
  for(const o of asset.offers){
    require(o&&typeof o==='object','Invalid typed offer.');
    let selection;
    if(o.schema_version==='nba-native-player-offer-v2'){
      require(asset.schema_version==='nba-player-offers-v2','Native offers require the versioned v2 asset.');
      validateNativeOffer(o,asset.generated_at);
      require((allowSynthetic&&o.evidence_lane==='SYNTHETIC_TEST')||nativeOfferPubliclyAdmitted(o),'Native offer has no reviewed public admission.');
      selection=JSON.stringify([o.venue,o.product,o.event.id_namespace,o.event.id,o.selection.group_id,o.selection.market_id,o.selection.selection_id,o.observed_at]);
    }else{
      require(admissions.has(o.admission_id),'Offer missing publication review.');
      validateOffer(o,admissions.get(o.admission_id),asset.generated_at,{allowSynthetic});
      selection=JSON.stringify([o.venue,o.product,o.provider.id_namespace,o.provider.selection_id,o.observed_at]);
      used.add(o.admission_id);
    }
    require(!ids.has(o.offer_id)&&!selections.has(selection),'Duplicate offer/provider selection.');
    ids.add(o.offer_id);selections.add(selection);
  }
  require(used.size===admissions.size,'Unreferenced offer review.');
  require(Array.isArray(asset.unavailable_reasons)&&asset.unavailable_reasons.length<=16&&asset.unavailable_reasons.every(v=>text(v,1000))
    &&(asset.offers.length>0||asset.unavailable_reasons.length>0),'Empty offers require an ordinary-language reason.');
  require(bytes(asset)<=256*1024,'Offer asset exceeds byte limit.');
  return asset;
}

export async function verifyOfferAssetHashes(asset,cryptoProvider=globalThis.crypto){
  require(cryptoProvider?.subtle,'SHA-256 support is required.');
  const hash=async value=>Array.from(new Uint8Array(await cryptoProvider.subtle.digest('SHA-256',new TextEncoder().encode(canonicalOffer(value))))).map(x=>x.toString(16).padStart(2,'0')).join('');
  const unsigned=(value,key)=>Object.fromEntries(Object.entries(value).filter(([k])=>k!==key));
  require(await hash(unsigned(asset,'asset_id'))===asset.asset_id,'Offer asset seal mismatch.');
  for(const a of asset.admissions)require(await hash(unsigned(a,'admission_id'))===a.admission_id,'Offer admission seal mismatch.');
  for(const o of asset.offers){
    if(o.schema_version==='nba-native-player-offer-v2'){
      await verifyNativeOfferHash(o,cryptoProvider);
      continue;
    }
    require(await hash(unsigned(o,'offer_id'))===o.offer_id,'Offer record seal mismatch.');
    const admission=asset.admissions.find(a=>a.admission_id===o.admission_id);
    require(admission&&await hash(Object.fromEntries(Object.entries(o).filter(([k])=>!['offer_id','admission_id'].includes(k))))===admission.subject_sha256,'Review does not bind exact offer.');
  }
  return asset;
}

// These are immutable, local matching views of already published originals, not
// a new forecast lane. Only a complete validated source graph can create one.
const admittedMatchViews=new WeakMap();
function immutableCopy(value){
  const freeze=v=>{if(v&&typeof v==='object'){Object.values(v).forEach(freeze);Object.freeze(v);}return v;};
  return freeze(structuredClone(value));
}
export async function offerResearchForecasts({legacy=[],paired=[],daily=null,production=null}={},at,cryptoProvider=globalThis.crypto){
  require(Array.isArray(legacy)&&Array.isArray(paired),'Invalid offer research forecast collections');
  // Snapshot both graphs before yielding to hashing. Caller mutation during an
  // await must never change the bytes whose semantics are admitted afterwards.
  daily=daily===null?null:structuredClone(daily);
  production=production===null?null:structuredClone({index:production.index,pages:production.pages,loaded_game_date:production.loaded_game_date??null});
  const result=[...legacy,...paired];
  const append=(rows,inputs,kind,lane,publishedAt)=>{
    const byId=new Map(inputs.map(input=>[input.input_id,input]));
    for(const row of rows){
      const body=row.body;
      if(!row.admission.eligible||body.mode!=='PROSPECTIVE_RESEARCH'||body.evidence_lane!==lane)continue;
      const input=byId.get(body.input_id);
      require(input&&body.event_snapshot_id===input.event.event_snapshot_id,'Offer matching lost the exact admitted forecast input');
      const view=immutableCopy({kind,reference:row.reference,original:body,admission:row.admission,input});
      const availability=[publishedAt,row.admission.local_persistence_completed_at??row.admission.local_completed_at,row.admission.remote_recovery_completed_at??row.admission.remote_recovered_at].map(utcMicros).reduce((latest,value)=>value>latest?value:latest);
      admittedMatchViews.set(view,{forecast:Object.freeze({...view.original,league:view.input.event.league,id_namespace:view.input.event.id_namespace,event_version:view.original.event_snapshot_id}),availability});
      result.push(view);
    }
  };
  if(daily!==null){
    await verifyDailyHashes(daily,cryptoProvider);
    validateDailyAsset(daily,at);
    append(daily.forecasts,daily.inputs,'SDV_DAILY','DAILY_SNAPSHOT_PROSPECTIVE',daily.generated_at);
  }
  if(production!==null){
    await verifyProductionHashes(production.index,production.pages,cryptoProvider,{gameDate:production.loaded_game_date});
    validateProductionIndex(production.index,at);
    // Preserve original page/receipt bytes. A flattened forecast projection alone
    // cannot establish the source, hosted authority or durable admission graph.
    const verified=validateProductionCollection(production.index,production.pages,{gameDate:production.loaded_game_date??null});
    append(verified.forecasts,verified.inputs,'SDV_PRODUCTION','SDV_PRODUCTION_PROSPECTIVE',production.index.generated_at);
  }
  return result;
}

export function matchResearchForecast(offer,forecast,at){
  if(offer.schema_version==='nba-native-player-offer-v2'){
    validateNativeOffer(offer,at);
    return {status:'UNMATCHED',reasons:['Native event requires a reviewed canonical event/version crosswalk; '+offer.event.forecast_match_status],qualification:'UNAVAILABLE',ticket_eligible:false,ev:null};
  }
  const admitted=admittedMatchViews.get(forecast);
  forecast=admitted?.forecast??forecast??{};
  const reasons=[];
  for(const key of ['league','id_namespace','event_id','player_id','team_id','opponent_id','event_starts_at','period','extra_time_policy'])if(forecast[key]!==offer[key])reasons.push(`Forecast and offer differ: ${key}`);
  if((forecast.event_version??forecast.prospective?.event_version)!==offer.event_version)reasons.push('Forecast and offer have different or absent event versions');
  if(!forecast.categories?.some(c=>c.code===offer.stat&&c.units===offer.units))reasons.push('Forecast does not support the exact offered category and units');
  try{const when=utcMicros(at);if(!(utcMicros(offer.observed_at)<=utcMicros(offer.imported_at)&&utcMicros(offer.imported_at)<=when&&when<utcMicros(offer.event_starts_at)&&utcMicros(forecast.cutoff_at)<=utcMicros(forecast.issued_at)&&utcMicros(forecast.issued_at)<=when))reasons.push('Forecast/offer were not both available at this pregame decision time');if(admitted&&when<admitted.availability)reasons.push('Research forecast publication or required durable recovery was not complete at this decision time');}
  catch{reasons.push('Missing or invalid forecast decision clocks');}
  if(offer.evidence_lane!=='REAL_TIME_CAPTURED'||(!admitted&&forecast.evidence_lane!=='REAL_TIME_CAPTURED')||offer.market_status!=='PRE_GAME'||forecast.conditioning!=='CONDITIONAL_ON_APPEARANCE')reasons.push('A genuinely captured pregame research forecast and offer are required');
  return {status:reasons.length?'UNMATCHED':'MATCHED_RESEARCH_ONLY',reasons,qualification:'UNAVAILABLE',ticket_eligible:false,ev:null};
}

export function offerDisplayState(offer,now){
  if(offer.schema_version==='nba-native-player-offer-v2'){
    validateNativeOffer(offer,now);
    const eventStarted=Date.parse(now)>=Date.parse(offer.event.starts_at);
    return {status:eventStarted?'HISTORICAL_CAPTURE':'RECORDED_OFFER',label:eventStarted?'Historical offer capture':'Recorded offer — research only',
      price_label:offer.price.value===null?'Price unavailable':`Observed decimal price ${offer.price.value}`,
      explanation:'Source-native Boolean contract. Canonical forecast matching and ticket qualification are unavailable.',ticket_eligible:false};
  }
  const eventStarted=utcMicros(now)>=utcMicros(offer.event_starts_at);
  return {status:eventStarted?'HISTORICAL_CAPTURE':'RECORDED_OFFER',label:eventStarted?'Historical offer capture':'Recorded offer — research only',
    price_label:offer.price===null?'Price unavailable':offer.price.kind==='pickem_multiplier'?`Observed side multiplier ${offer.price.value}×; not sportsbook odds`:`Observed decimal price ${offer.price.value}`,
    explanation:'A displayed contract is not a recommendation or a qualified paper-ticket leg. No value or financial settlement is claimed.',ticket_eligible:false};
}

// Display/filter projection only. A Yes/No achievement keeps its literal side;
// this projection never creates a numeric line or a forecast crosswalk.
export function offerView(offer){
  return offer.schema_version==='nba-native-player-offer-v2'
    ? {starts_at:offer.event.starts_at,category:offer.category,side:offer.selection.label.toUpperCase(),venue:offer.venue,period:offer.period}
    : {starts_at:offer.event_starts_at,category:offer.stat,side:offer.side.toUpperCase(),venue:offer.venue,period:offer.period};
}

export function filterOfferRows(offers,{view='upcoming',category='ALL',side='ALL',venue='ALL',period='full_game',window='upcoming',evidence='ALL'}={},now=Date.now()){
  require(Array.isArray(offers)&&Number.isFinite(now),'Invalid offer filter inputs.');
  const horizon=window==='24h'?86400000:window==='7d'?7*86400000:Infinity;
  return offers.filter(offer=>{
    const value=offerView(offer),start=Date.parse(value.starts_at),upcoming=start>now;
    return (view==='history'?!upcoming:upcoming)&&(view==='history'||start<=now+horizon)
      &&(category==='ALL'||value.category===category)&&(side==='ALL'||value.side===side)
      &&(venue==='ALL'||value.venue===venue)&&value.period===period&&['ALL','OFFER_ONLY'].includes(evidence);
  });
}

const esc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function renderOffers(asset,{offers=asset.offers,forecasts=[],now=asset.generated_at}={}){
  if(!offers.length)return `<p>${esc(asset.unavailable_reasons.join(' '))}</p>`;
  return offers.map(o=>{
    if(o.schema_version==='nba-native-player-offer-v2')return renderNativeOffer(o,{now,published:nativeOfferPubliclyAdmitted(o)});
    const state=offerDisplayState(o,now),matches=forecasts.filter(f=>matchResearchForecast(o,f,now).status==='MATCHED_RESEARCH_ONLY');
    return `<article class="offer-card forecast-card">
      <p class="eyebrow">${esc(state.label)}</p>
      <h3>${esc(o.player_label)} · ${esc(o.side.toUpperCase())} ${esc(o.line)} ${esc(o.stat)}</h3>
      <p class="forecast-semantics">${esc(o.venue)} / ${esc(o.product)} · ${esc(o.event_starts_at)} · ${esc(o.period.replaceAll('_',' '))}, ${esc(o.extra_time_policy.replaceAll('_',' '))}</p>
      <p class="forecast-semantics">${esc(state.price_label)}. ${esc(matches.length?`${matches.length} matching research forecast${matches.length===1?'':'s'}.`:'No published research forecast matches this exact contract and decision time.')}</p>
      <p class="forecast-semantics">${esc(state.explanation)}</p>
      <details class="forecast-details"><summary>Contract and source details</summary>
        <p>Event ${esc(o.id_namespace)}:${esc(o.event_id)} · player ${esc(o.player_id)} · event version <code class="break-code">${esc(o.event_version)}</code></p>
        <p>Captured team identity ${esc(o.team_id)} vs ${esc(o.opponent_id)}. Variant ${esc(o.variant)}. Rules ${esc(o.settlement_version)}.</p>
        <p>Statistic meaning: ${esc(o.stat_definition)}</p>
        <dl class="forecast-provenance">${settlementFields.map(key=>`<div><dt>${esc(key.replaceAll('_',' '))}</dt><dd>${esc(o.settlement_terms[key])}</dd></div>`).join('')}</dl>
        <p>Observed ${esc(o.observed_at)}; source updated ${esc(o.source_updated_at??'not supplied')}; imported ${esc(o.imported_at)}.</p>
        ${o.source_evidence.map(e=>`<p>${esc(e.kind)}: <a href="${esc(e.source_url)}" rel="noreferrer">source</a> · raw SHA-256 <code class="break-code">${esc(e.raw_sha256)}</code></p>`).join('')}
      </details></article>`;
  }).join('');
}

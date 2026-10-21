// Isolated local semantic-contract review. No collection, trading or publication.
import {ALL_NBA_CATEGORIES, NBA_UNITS, utcMicros} from './research.mjs';

export const SEMANTIC_REVIEW_SCHEMA = 'nba-local-semantic-offer-v2';
const TOP = ['schema_version','scope','evidence_lane','contract_id','source','normalized_at','contract_observed_at','knowledge_observed_at','primary_evidence_id','category_inventory','player','event','selection','predicate','settlement','price','unassigned_source_economics','execution_review','evidence','bindings','required_gaps','price_binding_gaps','semantic_status','completed_at','public_admission','ticket_eligibility','qualification'];
const SETTLEMENT = ['participation','dnp','postponement','ties','official_stat_source','stat_corrections'];
const FLAGS = ['restricted','ready','funded','accepting_orders','context_requires_regen'];
const HOSTS = ['gamma-api.polymarket.com','clob.polymarket.com','docs.polymarket.com','help.polymarket.com','www.wikidata.org'];
const TRANSFORMS = ['direct','string','utc','json_array','outcome_label','decimal_lexeme','question_player','question_threshold','category','units','yes_operator','full_game','overtime','gamma_teams','wikidata_identity','source_version_literal','observed_snapshot_version','affiliation_team','affiliation_opponent','native_player_id','clob_token','text_contains'];
const BINDING_ROLES = {
  'player.source_label':['primary','/question','question_player'],
  'player.native_provider_id':['primary','/player','native_player_id'],
  'event.id':['event','/id','string'], 'event.label':['event','/title','direct'],
  'event.starts_at':['event','/startTime','utc'], 'event.participants':['event','/teams','gamma_teams'],
  'event.source_version_literal':['event','/version','source_version_literal'],
  'event.event_version':['event','','observed_snapshot_version'],
  'event.player_team_id':['affiliation','','affiliation_team'],
  'event.opponent_id':['affiliation','','affiliation_opponent'],
  'selection.market_id':['primary','/id','string'],
  'selection.condition_id':['primary','/conditionId','direct'],
  'selection.outcome_label':['primary','/outcomes','outcome_label'],
  'selection.native_token_id':['clob','','clob_token'],
  'predicate.category':['primary','/sportsMarketType','category'],
  'predicate.units':['primary','/sportsMarketType','units'],
  'predicate.operator':['primary','/description','yes_operator'],
  'predicate.threshold':['primary','/question','question_threshold'],
  'predicate.period':['primary','/description','full_game'],
  'predicate.extra_time_policy':['primary','/description','overtime'],
  'unassigned_source_economics.outcomes':['primary','/outcomes','json_array'],
  'unassigned_source_economics.outcome_prices':['primary','/outcomePrices','json_array'],
  'unassigned_source_economics.best_bid':['primary','/bestBid','decimal_lexeme'],
  'unassigned_source_economics.best_ask':['primary','/bestAsk','decimal_lexeme'],
  'execution_review.flags.restricted':['primary','/restricted','direct'],
  'execution_review.flags.ready':['primary','/ready','direct'],
  'execution_review.flags.funded':['primary','/funded','direct'],
  'execution_review.flags.accepting_orders':['primary','/acceptingOrders','direct'],
  'execution_review.flags.context_requires_regen':['event','/eventMetadata/context_requires_regen','direct']
};
const SHA = /^[a-f0-9]{64}$/;
const require = (condition,message) => {if (!condition) throw new Error(message);};
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const fields = (value,expected) => object(value) && Object.keys(value).sort().join(',') === [...expected].sort().join(',');
const text = (value,max=600) => typeof value === 'string' && value.length > 0 && value.length <= max && value.trim() === value;
const nullableText = (value,max=600) => value === null || text(value,max);
const decimal = value => typeof value === 'string' && value.length <= 128 && /^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value);
const binaryPrice = value => typeof value === 'string' && value.length <= 128 && /^(?:0(?:\.\d+)?|1(?:\.0+)?)$/.test(value);
const threshold = value => {
  if (!decimal(value) || value.length > 32) return false;
  const [integer,fraction='']=value.split('.');
  return integer.length < 7 || (integer.length === 7 && (integer < '1000000' || (integer === '1000000' && /^0*$/.test(fraction))));
};
const same = (left,right) => canonicalSemanticReview(left) === canonicalSemanticReview(right);
const clockNow = () => new Date().toISOString().replace(/\.(\d{3})Z$/,(_,ms)=>`.${ms}000Z`);
const esc = value => String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clockLabel = value => value.replace('T',' ').replace('Z',' UTC');
const url = value => {try {const parsed=new URL(value),authority=value.replace(/^[a-z]+:\/\//i,'').split(/[/?#]/,1)[0];return text(value,2048)&&parsed.protocol==='https:'&&HOSTS.includes(authority)&&!parsed.username&&!parsed.password&&!parsed.hash;} catch{return false;}};

export function canonicalSemanticReview(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalSemanticReview).join(',')}]`;
  if (object(value)) return `{${Object.keys(value).sort().map(key=>`${JSON.stringify(key)}:${canonicalSemanticReview(value[key])}`).join(',')}}`;
  require(value === null || ['string','boolean','number'].includes(typeof value),'Invalid semantic-review JSON value.');
  if (typeof value === 'number') require(Number.isFinite(value) && (!Number.isInteger(value)||Number.isSafeInteger(value)),'Unsafe semantic-review JSON number.');
  return JSON.stringify(value);
}

export function requiredSemanticGaps(contract) {
  const gaps=[];
  if (contract.player.canonical_identity === null) gaps.push('PLAYER_CANONICAL_IDENTITY');
  if (contract.event.player_team_id === null) gaps.push('PLAYER_TEAM');
  if (contract.event.opponent_id === null) gaps.push('PLAYER_OPPONENT');
  if (contract.event.event_version === null) gaps.push('EVENT_VERSION');
  if (contract.predicate.period === null) gaps.push('PERIOD');
  if (contract.predicate.extra_time_policy === null) gaps.push('OVERTIME');
  for (const key of [...SETTLEMENT].sort()) if (contract.settlement[key] === null) gaps.push(`SETTLEMENT_${key.toUpperCase()}`);
  return gaps;
}

function target(contract,field) {
  let value=contract;
  for (const part of field.split('.')) {
    require(object(value) && Object.hasOwn(value,part),'Unknown semantic source binding field.');
    value=value[part];
  }
  return value;
}

function bindingFields(contract) {
  const required=['player.source_label','event.id','event.label','event.starts_at','event.participants','selection.market_id','selection.condition_id','selection.outcome_label','predicate.category','predicate.units','predicate.operator','predicate.threshold','unassigned_source_economics.outcomes'];
  const optional=['player.canonical_identity','player.native_provider_id','event.player_team_id','event.opponent_id','event.event_version','event.source_version_literal','selection.native_token_id','predicate.period','predicate.extra_time_policy',...SETTLEMENT.map(key=>`settlement.${key}`),...['outcome_prices','best_bid','best_ask'].map(key=>`unassigned_source_economics.${key}`),...FLAGS.map(key=>`execution_review.flags.${key}`)];
  return [...required,...optional.filter(field=>target(contract,field) !== null)].sort();
}

function allowedBindingRoles(contract,field) {
  if (field === 'player.canonical_identity') return [['canonical',`/entities/${contract.player.canonical_identity.id}`,'wikidata_identity']];
  if (field.startsWith('settlement.')) {
    const key=field.slice('settlement.'.length);
    return [['primary','/description','text_contains'],...(contract.evidence_lane === 'SYNTHETIC'?[['primary',`/settlement/${key}`,'direct']]:[])];
  }
  require(Object.hasOwn(BINDING_ROLES,field),'Unknown reviewed semantic field role.');
  return [BINDING_ROLES[field]];
}

export function validateSemanticOfferReview(contract,now=clockNow()) {
  require(fields(contract,TOP) && contract.schema_version === SEMANTIC_REVIEW_SCHEMA
    && contract.scope === 'LOCAL_REVIEW_ONLY' && ['ACTUAL_SOURCE_OBSERVATION','SYNTHETIC'].includes(contract.evidence_lane)
    && typeof contract.contract_id === 'string' && SHA.test(contract.contract_id), 'Invalid local semantic-review version, scope or identity.');
  require(fields(contract.source,['name','venue','product']) && contract.source.name === 'Polymarket'
    && contract.source.venue === 'Polymarket' && contract.source.product === 'binary_event_contract',
    'Unsupported semantic source, venue or product.');
  require(contract.public_admission === false && contract.ticket_eligibility === false
    && contract.qualification === 'UNAVAILABLE','Semantic review confers no public admission or ticket qualification.');
  require(same(contract.category_inventory,ALL_NBA_CATEGORIES),'The full fourteen-category inventory is required.');
  const normalized=utcMicros(contract.normalized_at), observed=utcMicros(contract.contract_observed_at), knowledge=utcMicros(contract.knowledge_observed_at);
  require(observed <= knowledge && knowledge <= normalized && normalized <= utcMicros(now),'Semantic capture, knowledge and normalization clocks disagree.');
  require(fields(contract.player,['source_label','canonical_identity','native_provider_id']) && text(contract.player.source_label,200)
    && nullableText(contract.player.native_provider_id,200),'Invalid player labels or native identity.');
  const identity=contract.player.canonical_identity;
  require(identity === null || (fields(identity,['namespace','id','label']) && identity.namespace === 'wikidata'
    && typeof identity.id === 'string' && /^Q[1-9]\d*$/.test(identity.id) && text(identity.label,200)
    && identity.label === contract.player.source_label),'Unverified external canonical-player identity.');
  const event=contract.event;
  require(fields(event,['namespace','id','label','starts_at','participants','player_team_id','opponent_id','event_version','source_version_literal'])
    && event.namespace === 'polymarket_gamma' && text(event.id,200) && text(event.label,300)
    && nullableText(event.player_team_id,200) && nullableText(event.opponent_id,200)
    && nullableText(event.source_version_literal,200),'Invalid semantic event identity.');
  utcMicros(event.starts_at);
  require(Array.isArray(event.participants) && event.participants.length === 2
    && event.participants.every(participant=>fields(participant,['id','label','role']) && text(participant.id,200)
      && text(participant.label,200) && ['away','home'].includes(participant.role))
    && new Set(event.participants.map(participant=>participant.id)).size === 2
    && new Set(event.participants.map(participant=>participant.role)).size === 2,'Invalid captured matchup participants.');
  for (const id of [event.player_team_id,event.opponent_id]) if (id !== null)
    require(event.participants.some(participant=>participant.id === id),'Player team or opponent is outside captured event.');
  if (event.player_team_id !== null && event.opponent_id !== null)
    require(event.player_team_id !== event.opponent_id,'Player team and opponent conflict.');
  require(event.event_version === null || (fields(event.event_version,['kind','value'])
    && event.event_version.kind === 'OBSERVED_SNAPSHOT_SHA256' && typeof event.event_version.value === 'string'
    && SHA.test(event.event_version.value)),'Invalid observed event snapshot version.');
  const selection=contract.selection;
  require(fields(selection,['kind','market_id','condition_id','outcome_label','native_token_id'])
    && selection.kind === 'MARKET_OUTCOME_LABEL' && text(selection.market_id,200)
    && typeof selection.condition_id === 'string' && /^0x[a-fA-F0-9]{64}$/.test(selection.condition_id)
    && selection.outcome_label === 'Yes' && (selection.native_token_id === null || (typeof selection.native_token_id === 'string' && /^[1-9]\d{0,100}$/.test(selection.native_token_id))),
    'Semantic identity requires an explicit source market and outcome label.');
  const predicate=contract.predicate;
  require(fields(predicate,['category','units','operator','threshold','period','extra_time_policy','variant'])
    && ALL_NBA_CATEGORIES.includes(predicate.category) && predicate.units === NBA_UNITS[predicate.category]
    && predicate.operator === '>' && threshold(predicate.threshold) && predicate.variant === 'binary_player_stat_threshold'
    && [null,'full_game'].includes(predicate.period) && [null,'includes_overtime'].includes(predicate.extra_time_policy),
    'Invalid explicit semantic predicate, period or overtime.');
  require(fields(contract.settlement,SETTLEMENT) && Object.values(contract.settlement).every(value=>value === null
    || (text(value,2000) && !['UNKNOWN','UNRESOLVED','TBD','N/A','UNVERIFIED'].includes(value.toUpperCase()))),
    'Invalid bounded semantic settlement meanings.');
  if (contract.settlement.stat_corrections !== null) require(/\b(?:stat(?:istic(?:al|s)?)?[ \t\r\n\f\v-]+corrections?|regrad(?:e|es|ed|ing)|re[- ]?settl(?:e|es|ed|ing|ements?))\b/i.test(contract.settlement.stat_corrections),
    'Generic finality does not establish statistical-correction meaning.');
  require(fields(contract.price,['status','value']) && contract.price.status === 'PRICE_UNAVAILABLE'
    && contract.price.value === null,'No bound normalized price is admitted in this semantic version.');
  const economics=contract.unassigned_source_economics;
  require(fields(economics,['outcomes','outcome_prices','best_bid','best_ask']) && same(economics.outcomes,['Yes','No'])
    && (economics.outcome_prices === null || (Array.isArray(economics.outcome_prices)
      && economics.outcome_prices.length === 2 && economics.outcome_prices.every(binaryPrice)))
    && (economics.best_bid === null || binaryPrice(economics.best_bid))
    && (economics.best_ask === null || binaryPrice(economics.best_ask)),
    'Unassigned binary economics must preserve exact source strings and bounds.');
  require(fields(contract.execution_review,['eligible','flags']) && contract.execution_review.eligible === false
    && fields(contract.execution_review.flags,FLAGS) && Object.values(contract.execution_review.flags).every(value=>value === null || typeof value === 'boolean'),
    'Execution flags cannot confer eligibility or semantic completeness.');
  require(Array.isArray(contract.evidence) && contract.evidence.length >= 1 && contract.evidence.length <= 16,
    'Bounded original-evidence metadata is required.');
  const evidenceIds=new Set();let latest=0n;
  for (const item of contract.evidence) {
    require(fields(item,['id','url','content_type','raw_sha256','raw_bytes','request_started_at','observed_at','source_updated_at'])
      && text(item.id,120) && !evidenceIds.has(item.id) && url(item.url) && ['application/json','text/html','text/plain'].includes(item.content_type)
      && typeof item.raw_sha256 === 'string' && SHA.test(item.raw_sha256)
      && Number.isSafeInteger(item.raw_bytes) && item.raw_bytes >= 0 && item.raw_bytes <= 2*1024*1024,
      'Invalid original-evidence identity, URL, hash or bytes.');
    evidenceIds.add(item.id);
    const at=utcMicros(item.observed_at);
    require(utcMicros(item.request_started_at) <= at && at <= knowledge,'Original-evidence clocks disagree.');
    if (item.source_updated_at !== null) require(utcMicros(item.source_updated_at) <= at,'Original source update follows capture.');
    if (at > latest) latest=at;
  }
  require(text(contract.primary_evidence_id,200) && evidenceIds.has(contract.primary_evidence_id)
    && utcMicros(contract.evidence.find(item=>item.id === contract.primary_evidence_id).observed_at) === observed,
    'Primary contract observation clock does not bind its original evidence.');
  const byId=new Map(contract.evidence.map(item=>[item.id,item]));
  const primary=byId.get(contract.primary_evidence_id), primaryUrl=new URL(primary.url);
  require(primaryUrl.host === 'gamma-api.polymarket.com' && primaryUrl.pathname === `/markets/${selection.market_id}`
    && !primaryUrl.search && primary.content_type === 'application/json',
    'Primary original is not the exact captured Gamma market route.');
  require(latest === knowledge,'Knowledge clock must retain the latest linked evidence observation.');
  require(Array.isArray(contract.bindings) && contract.bindings.length <= 64,
    'Bounded source bindings are required.');
  const boundFields=new Set();
  const special={'player.canonical_identity':'wikidata_identity','player.native_provider_id':'native_player_id','event.player_team_id':'affiliation_team','event.opponent_id':'affiliation_opponent','event.event_version':'observed_snapshot_version','selection.native_token_id':'clob_token','predicate.operator':'yes_operator'};
  for (const binding of contract.bindings) {
    require(fields(binding,['field','evidence_id','pointer','transform']) && text(binding.field,120)
      && !boundFields.has(binding.field) && evidenceIds.has(binding.evidence_id)
      && typeof binding.pointer === 'string' && binding.pointer.length <= 1000
      && (binding.pointer === '' || binding.pointer.startsWith('/')) && TRANSFORMS.includes(binding.transform),
      'Invalid or duplicate semantic source binding.');
    require(target(contract,binding.field) !== null,'Unresolved fields cannot have verified source bindings.');
    if (Object.hasOwn(special,binding.field)) require(binding.transform === special[binding.field],
      'Identity, snapshot or predicate lacks its reviewed source transform.');
    const evidenceUrl=new URL(byId.get(binding.evidence_id).url), field=binding.field;
    if (['event.id','event.label','event.starts_at','event.participants','event.event_version','event.source_version_literal'].includes(field))
      require(evidenceUrl.host === 'gamma-api.polymarket.com' && evidenceUrl.pathname === `/events/${event.id}` && !evidenceUrl.search,
        'Event binding is not the exact retained Gamma event.');
    if (field === 'player.canonical_identity') require(evidenceUrl.host === 'www.wikidata.org'
      && evidenceUrl.pathname === `/wiki/Special:EntityData/${identity.id}.json` && !evidenceUrl.search
      && binding.pointer === `/entities/${identity.id}`,'Canonical identity URL, entity or pointer conflicts.');
    if (((field.startsWith('predicate.') || field.startsWith('selection.')) && field !== 'selection.native_token_id')
      || field === 'player.source_label' || field.startsWith('unassigned_source_economics.'))
      require(binding.evidence_id === contract.primary_evidence_id,'Market semantics or economics do not bind their original market.');
    if (['selection.native_token_id','event.event_version'].includes(field))
      require(binding.pointer === '', 'Token or snapshot binding requires the complete source object.');
    const roles=allowedBindingRoles(contract,field).filter(([,pointer,transform])=>pointer === binding.pointer && transform === binding.transform);
    require(roles.length === 1,'Semantic field uses an unreviewed source pointer or transform.');
    const role=roles[0][0];
    if (role === 'primary') require(binding.evidence_id === contract.primary_evidence_id,'Semantic field must bind the primary market source.');
    if (role === 'event') require(evidenceUrl.host === 'gamma-api.polymarket.com'
      && evidenceUrl.pathname === `/events/${event.id}` && !evidenceUrl.search,'Semantic field must bind its exact event source.');
    if (role === 'clob') require(evidenceUrl.host === 'clob.polymarket.com'
      && evidenceUrl.pathname === `/clob-markets/${selection.condition_id}` && !evidenceUrl.search,'Native token must bind the exact condition CLOB source.');
    boundFields.add(binding.field);
  }
  require(same([...boundFields].sort(),bindingFields(contract)),'Missing or unexpected semantic/source field bindings.');
  require(Array.isArray(contract.required_gaps) && contract.required_gaps.every(value=>text(value,200))
    && new Set(contract.required_gaps).size === contract.required_gaps.length
    && same(contract.required_gaps,requiredSemanticGaps(contract)),
    'Required semantic gaps must be computed from the registered contract fields.');
  require(same(contract.price_binding_gaps,['PRICE_TO_SELECTION_UNVERIFIED']),
    'Unassigned price evidence remains separate from semantic gaps.');
  const complete=contract.required_gaps.length === 0;
  require(contract.semantic_status === (complete?'COMPLETE_LOCAL':'INCOMPLETE')
    && contract.completed_at === (complete?contract.normalized_at:null),
    'Semantic completion flags or clocks contradict the required fields.');
  require(new TextEncoder().encode(canonicalSemanticReview(contract)).byteLength <= 256*1024,'Semantic review exceeds its byte limit.');
  return contract;
}

export async function verifySemanticOfferReviewHash(contract,cryptoProvider=globalThis.crypto) {
  require(cryptoProvider?.subtle,'SHA-256 support is required.');
  const unsigned=Object.fromEntries(Object.entries(contract).filter(([key])=>key !== 'contract_id'));
  const bytes=await cryptoProvider.subtle.digest('SHA-256',new TextEncoder().encode(canonicalSemanticReview(unsigned)));
  const expected=Array.from(new Uint8Array(bytes)).map(value=>value.toString(16).padStart(2,'0')).join('');
  require(contract.contract_id === expected,'Semantic contract seal mismatch.');
  return contract;
}

const gapLabels={PLAYER_CANONICAL_IDENTITY:'The player lacks a verified external canonical identity.',PLAYER_TEAM:'The player’s team for this captured game is unverified.',PLAYER_OPPONENT:'The player’s opponent for this captured game is unverified.',EVENT_VERSION:'A retained source snapshot has not established the event version.',PERIOD:'The market period is unresolved.',OVERTIME:'Overtime treatment is unresolved.'};
const gapLabel=gap=>gapLabels[gap]??(gap.startsWith('SETTLEMENT_')?`Settlement meaning remains unresolved: ${gap.slice(11).toLowerCase().replaceAll('_',' ')}.`:gap);
const unknown=value=>value === null?'UNRESOLVED':value;

export function renderSemanticOfferReview(contract,{now=clockNow()}={}) {
  validateSemanticOfferReview(contract,now);
  const complete=contract.semantic_status === 'COMPLETE_LOCAL', synthetic=contract.evidence_lane === 'SYNTHETIC';
  const identity=contract.player.canonical_identity, event=contract.event, selection=contract.selection, predicate=contract.predicate;
  const economics=contract.unassigned_source_economics;
  return `<section class="local-offer-review">
    <header><p class="review-eyebrow">${synthetic?'Synthetic software fixture':'Actual source observation'} · local semantic v2 · unpublished</p>
      <h1>NBA semantic contract review</h1>
      <p class="review-banner">LOCAL REVIEW ONLY. Semantic interpretation, price binding, execution and public publication are separate. Public admission: unavailable. Paper Builder: NO_ACTION.</p>
      <p><strong>One selected contract · semantic status: ${esc(contract.semantic_status)} · ${contract.required_gaps.length} required gaps</strong></p>
      <p>Contract observed: ${esc(clockLabel(contract.contract_observed_at))}. Latest linked knowledge observed: ${esc(clockLabel(contract.knowledge_observed_at))}. Normalized: ${esc(clockLabel(contract.normalized_at))}.</p>
      <p>Later knowledge does not refresh the original contract observation. No current availability, forecast quality, recommendation or financial settlement is claimed.</p>
    </header>
    <article class="local-observation" data-semantic-status="${esc(contract.semantic_status)}">
      <p class="review-eyebrow">${complete?'Complete under the registered local semantic v2 requirements':'Semantic interpretation incomplete'} · ${utcMicros(now)>=utcMicros(event.starts_at)?'historical captured contract':'recorded contract facts'}</p>
      <h2>${esc(contract.player.source_label)} · YES: ${esc(predicate.category)} &gt; ${esc(predicate.threshold)}</h2>
      <p class="review-matchup">${esc(event.label)} · ${esc(clockLabel(event.starts_at))}</p>
      <p>Source: ${esc(contract.source.name)}. Venue: ${esc(contract.source.venue)}. Product: binary event contract — Yes/No.</p>
      <p>Selection identity: source market ${esc(selection.market_id)} + outcome label ${esc(selection.outcome_label)}. Native token: <code>${esc(selection.native_token_id??'not supplied or unverified')}</code>.</p>
      <p>Canonical player: ${identity?`${esc(identity.label)} · ${esc(identity.namespace)}:${esc(identity.id)}`:'UNRESOLVED'}. Native provider player ID: ${esc(contract.player.native_provider_id??'not supplied or unverified')}.</p>
      <p>Period: ${esc(predicate.period?.replaceAll('_',' ')??'UNRESOLVED')}; overtime: ${esc(predicate.extra_time_policy?.replaceAll('_',' ')??'UNRESOLVED')}.</p>
      ${complete?'<p>Semantic completeness does not establish a usable quote, executable offer, public admission or qualified ticket.</p>':`<section class="review-gaps"><h3>Required semantic gaps</h3><ul>${contract.required_gaps.map(gap=>`<li>${esc(gapLabel(gap))}</li>`).join('')}</ul></section>`}
      <section class="review-gaps"><h3>Price binding remains separate</h3><p><strong>PRICE_UNAVAILABLE</strong>: no normalized price is assigned to this selection.</p>
        <p>Source outcomes array: ${esc(JSON.stringify(economics.outcomes))}. Unassigned source outcome-price array: ${esc(economics.outcome_prices === null?'not supplied':JSON.stringify(economics.outcome_prices))}. Source best bid: ${esc(economics.best_bid??'not supplied')}; best ask: ${esc(economics.best_ask??'not supplied')}.</p>
        <p>Array order is not used to assign a selection price. These values are not DraftKings odds, Sleeper multipliers or compatible parlay legs. No odds conversion or EV is calculated.</p>
      </section>
      <details><summary>Settlement meanings and explicit unknowns</summary>
        <dl>${SETTLEMENT.map(key=>`<dt>${esc(key.replaceAll('_',' '))}</dt><dd>${esc(unknown(contract.settlement[key]))}</dd>`).join('')}</dl>
        <p>Captured player team: ${esc(unknown(event.player_team_id))}; opponent: ${esc(unknown(event.opponent_id))}. Participant labels do not establish the player’s affiliation.</p>
        <p>Event version: ${event.event_version?`observed snapshot SHA-256 <code>${esc(event.event_version.value)}</code> (not a native provider revision)`:'UNRESOLVED'}. Native source version literal: ${esc(unknown(event.source_version_literal))}.</p>
      </details>
      <details><summary>Execution flags and original evidence</summary>
        <p>Execution eligible: false. ${FLAGS.map(flag=>`${esc(flag.replaceAll('_',' '))}: ${esc(contract.execution_review.flags[flag] === null?'UNRESOLVED':String(contract.execution_review.flags[flag]))}`).join(' · ')}.</p>
        <p>Contract ID <code>${esc(contract.contract_id)}</code>. Event ${esc(event.namespace)}:${esc(event.id)}; source condition <code>${esc(selection.condition_id)}</code>.</p>
        ${contract.evidence.map(item=>`<p>${esc(item.id)} · ${esc(item.url)} · observed ${esc(clockLabel(item.observed_at))} · source updated ${esc(item.source_updated_at===null?'not supplied':clockLabel(item.source_updated_at))} · ${item.raw_bytes} bytes · SHA-256 <code>${esc(item.raw_sha256)}</code>.</p>`).join('')}
        <p>Hash and metadata consistency do not establish upstream authenticity or source-use permission. Original retention and independent replay are separate evidence.</p>
      </details>
    </article>
    <section class="review-coverage"><h2>Full NBA category scope</h2><p>This selected contract concerns ${esc(predicate.category)}. The inventory retains all thirteen requested categories plus PA; it does not assert that every category was observed or qualified.</p>
      <div class="review-table"><table><thead><tr><th scope="col">Category</th><th scope="col">Selected-contract coverage</th></tr></thead><tbody>${ALL_NBA_CATEGORIES.map(category=>`<tr><th scope="row">${esc(category)}</th><td>${category===predicate.category?'This selected contract':'Not assessed by this selected contract'}</td></tr>`).join('')}</tbody></table></div>
    </section><p class="review-banner">Qualification UNAVAILABLE. No public offer, genuine forecast, statistical grade or ticket is issued by this preview.</p>
  </section>`;
}

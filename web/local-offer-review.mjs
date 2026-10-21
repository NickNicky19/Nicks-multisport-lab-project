// Local source-inspection review only. This module never fetches or publishes.
// It does not alter the public offer admission registry or ticket candidates.
import {ALL_NBA_CATEGORIES, utcMicros} from './research.mjs';

export const LOCAL_REVIEW_SCHEMA = 'nba-local-offer-review-v1';
const MAX_ROWS = 32;
const SHA = /^[a-f0-9]{64}$/;
const TOP = ['schema_version','scope','generated_at','source','venue','product','public_admission','ticket_eligibility','counts','category_coverage','observations'];
const OBSERVATION = ['source_market_id','source_event_id','player_name','player_identity','event_label','event_starts_at','category','threshold','operator','selection','selection_id','variant','period','overtime','observed_at','source_updated_at','prices_as_supplied','sportsbook_price_status','settlement','gaps','complete','normalized_offer_available','raw_source_sha256'];
const SETTLEMENT = ['participation','dnp','postponement','ties','official_stat_source','stat_corrections'];
const COVERAGE_STATES = ['OBSERVED_PARTIAL','OBSERVED_COMPLETE','UNOBSERVED_IN_SAMPLE','UNSUPPORTED'];
const require = (condition, message) => {if (!condition) throw new Error(message);};
const fields = (value, expected) => value !== null && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).sort().join(',') === [...expected].sort().join(',');
const text = (value, max=600) => typeof value === 'string' && value.length > 0 && value.length <= max && value.trim() === value;
const count = value => Number.isSafeInteger(value) && value >= 0;
const decimal = value => typeof value === 'string' && value.length <= 128 && /^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value) && Number.isFinite(Number(value));
// Compare binary prices lexically: Number() rounds values just above one to one.
const price = value => typeof value === 'string' && value.length <= 128
  && /^(?:0(?:\.\d+)?|1(?:\.0+)?)$/.test(value);
const actualClock = () => new Date().toISOString().replace(/\.(\d{3})Z$/, (_, milliseconds) => `.${milliseconds}000Z`);
const esc = value => String(value).replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const clockLabel = value => value.replace('T',' ').replace('Z',' UTC');

/** A local review is deliberately incompatible with the public offer schema. */
export function validateLocalOfferReview(review, now=actualClock()) {
  require(fields(review,TOP) && review.schema_version === LOCAL_REVIEW_SCHEMA
    && review.scope === 'LOCAL_REVIEW_ONLY' && review.source === 'Polymarket Gamma API'
    && review.venue === 'Polymarket' && review.product === 'binary_event_contract'
    && review.public_admission === false && review.ticket_eligibility === false,
    'Unsupported local review schema, source, product or admission state.');
  const generated = utcMicros(review.generated_at);
  require(generated <= utcMicros(now),'Local review generation clock is in the future.');
  require(fields(review.counts,['player_rows_observed','rows_parsed','complete_contracts'])
    && Object.values(review.counts).every(count)
    && review.counts.player_rows_observed <= MAX_ROWS
    && review.counts.rows_parsed <= review.counts.player_rows_observed
    && review.counts.complete_contracts <= review.counts.rows_parsed,
    'Invalid bounded source-review counts.');
  require(Array.isArray(review.observations) && review.observations.length === review.counts.rows_parsed
    && review.observations.length <= MAX_ROWS,'Parsed count disagrees with local observations.');
  require(fields(review.category_coverage,ALL_NBA_CATEGORIES),'All fourteen NBA categories are required.');
  const marketIds = new Set();
  for (const observation of review.observations) {
    require(fields(observation,OBSERVATION),'Invalid local observation fields.');
    for (const key of ['source_market_id','source_event_id','player_name','event_label'])
      require(text(observation[key],512),`Invalid local observation ${key}.`);
    require(observation.selection_id === null || text(observation.selection_id,512),
      'Invalid source selection identity.');
    require(!marketIds.has(observation.source_market_id),'Duplicate source market observation.');
    marketIds.add(observation.source_market_id);
    require(ALL_NBA_CATEGORIES.includes(observation.category) && decimal(observation.threshold)
      && observation.operator === '>' && observation.selection === 'Yes'
      && observation.variant === 'binary_player_stat_threshold',
      'Unverified category, threshold operator, selection or variant.');
    require(observation.player_identity === null || (fields(observation.player_identity,['namespace','id'])
      && text(observation.player_identity.namespace,200) && text(observation.player_identity.id,512)),
      'Invalid verified player identity.');
    require(observation.period === null || observation.period === 'full_game','Unsupported period.');
    require(observation.overtime === null || observation.overtime === 'includes_overtime','Unsupported overtime meaning.');
    const observed = utcMicros(observation.observed_at);
    require(observed <= generated,'Source observation follows review generation.');
    utcMicros(observation.event_starts_at);
    if (observation.source_updated_at !== null) utcMicros(observation.source_updated_at);
    const supplied = observation.prices_as_supplied;
    require(fields(supplied,['outcomes','outcomePrices','bestBid','bestAsk'])
      && Array.isArray(supplied.outcomes) && supplied.outcomes.length === 2
      && supplied.outcomes[0] === 'Yes' && supplied.outcomes[1] === 'No'
      && (supplied.outcomePrices === null || (Array.isArray(supplied.outcomePrices)
        && supplied.outcomePrices.length === 2 && supplied.outcomePrices.every(price)))
      && (supplied.bestBid === null || price(supplied.bestBid))
      && (supplied.bestAsk === null || price(supplied.bestAsk))
      && observation.sportsbook_price_status === 'PRICE_UNAVAILABLE',
      'Binary source prices must remain exact source strings, separate from sportsbook odds.');
    require(observation.settlement !== null && typeof observation.settlement === 'object'
      && !Array.isArray(observation.settlement) && Object.keys(observation.settlement).every(key => SETTLEMENT.includes(key))
      && Object.values(observation.settlement).every(value => text(value,2000)),
      'Invalid explicit source settlement meanings.');
    require(Array.isArray(observation.gaps) && observation.gaps.length <= 32
      && observation.gaps.every(value => text(value,600))
      && new Set(observation.gaps).size === observation.gaps.length,
      'Invalid contract gap inventory.');
    require(typeof observation.complete === 'boolean' && typeof observation.normalized_offer_available === 'boolean'
      && SHA.test(observation.raw_source_sha256),'Invalid local completion or original reference.');
    if (observation.source_updated_at !== null && utcMicros(observation.source_updated_at) > observed)
      require(observation.gaps.includes('source_update_later_than_observation'),
        'A future source-update clock requires an explicit unresolved gap.');
    const complete = observation.gaps.length === 0;
    require(observation.complete === complete && observation.normalized_offer_available === complete,
      'Local contract completion disagrees with gaps or normalized availability.');
    if (complete) require(observation.player_identity !== null && text(observation.selection_id,512)
      && observation.period === 'full_game'
      && observation.overtime === 'includes_overtime'
      && SETTLEMENT.every(key => text(observation.settlement[key],2000)
        && !['UNKNOWN','UNVERIFIED','UNRESOLVED','TBD','N/A'].includes(observation.settlement[key].toUpperCase())),
      'Complete local contract lacks verified identity, period, overtime or settlement.');
  }
  require(review.counts.complete_contracts === review.observations.filter(row => row.complete).length,
    'Complete-contract count disagrees with observed records.');
  let observedTotal = 0, parsedTotal = 0;
  for (const category of ALL_NBA_CATEGORIES) {
    const coverage = review.category_coverage[category];
    require(fields(coverage,['observed_rows','parsed_rows','status']) && count(coverage.observed_rows)
      && count(coverage.parsed_rows) && coverage.parsed_rows <= coverage.observed_rows
      && coverage.observed_rows <= MAX_ROWS && COVERAGE_STATES.includes(coverage.status),
      'Invalid category-specific source coverage.');
    const rows = review.observations.filter(row => row.category === category);
    require(coverage.parsed_rows === rows.length,'Category parsed count disagrees with records.');
    if (coverage.status === 'UNOBSERVED_IN_SAMPLE') require(coverage.observed_rows === 0,'Observed category cannot be unobserved.');
    if (coverage.status === 'OBSERVED_PARTIAL') require(coverage.observed_rows > 0,'Partial category requires observations.');
    if (coverage.status === 'OBSERVED_COMPLETE') require(coverage.observed_rows > 0
      && coverage.observed_rows === coverage.parsed_rows && rows.every(row => row.complete),
      'Complete category coverage lacks complete contracts.');
    observedTotal += coverage.observed_rows;
    parsedTotal += coverage.parsed_rows;
  }
  require(observedTotal === review.counts.player_rows_observed && parsedTotal === review.counts.rows_parsed,
    'Category inventory disagrees with total source counts.');
  require(new TextEncoder().encode(JSON.stringify(review)).byteLength <= 256*1024,'Local review exceeds byte limit.');
  return review;
}

export function renderLocalOfferReview(review,{now=actualClock()}={}) {
  validateLocalOfferReview(review,now);
  const cards = review.observations.map(observation => {
    const supplied = observation.prices_as_supplied;
    const prices = supplied.outcomePrices === null ? 'not supplied' : JSON.stringify(supplied.outcomePrices);
    const identity = observation.player_identity
      ? `${observation.player_identity.namespace}:${observation.player_identity.id}` : 'No stable player entity ID verified';
    return `<article class="local-observation" data-review-state="${observation.complete?'COMPLETE_LOCAL_CONTRACT':'PARTIAL_SOURCE_OBSERVATION'}">
      <p class="review-eyebrow">${observation.complete?'Complete local contract review':'Partial source observation · contract incomplete'}</p>
      <h2>${esc(observation.player_name)} · YES: ${esc(observation.category)} &gt; ${esc(observation.threshold)}</h2>
      <p class="review-matchup">${esc(observation.event_label)} · ${esc(clockLabel(observation.event_starts_at))}</p>
      <p>Source: ${esc(review.source)}. Venue: ${esc(review.venue)}. Product: binary event contract — Yes/No.</p>
      <p>Period: ${esc(observation.period?.replaceAll('_',' ')??'unverified')}; overtime: ${esc(observation.overtime?.replaceAll('_',' ')??'unverified')}.</p>
      <p><strong>Standalone sportsbook price: unavailable.</strong> Source outcomes array: ${esc(JSON.stringify(supplied.outcomes))}. Source outcomePrices array: ${esc(prices)}. Best bid: ${esc(supplied.bestBid??'not supplied')}; best ask: ${esc(supplied.bestAsk??'not supplied')}.</p>
      <p>Source arrays are retained literally; this review does not infer their selection/token or price alignment from array order.</p>
      <p class="review-limit">These source prices are not sportsbook odds, Sleeper multipliers, or compatible parlay legs. No conversion, value claim or ticket eligibility is implied.</p>
      <p>Source observed: ${esc(clockLabel(observation.observed_at))}. Source updated: ${esc(observation.source_updated_at?clockLabel(observation.source_updated_at):'not supplied')}.</p>
      ${observation.gaps.length?`<section class="review-gaps"><h3>Unresolved contract gaps</h3><ul>${observation.gaps.map(gap=>`<li>${esc(gap)}</li>`).join('')}</ul></section>`:'<p>Required contract fields passed this local review. Public admission remains unavailable.</p>'}
      <details><summary>Source IDs, original evidence and settlement</summary>
        <p>Player identity: ${esc(identity)}. Source event ${esc(observation.source_event_id)}; market ${esc(observation.source_market_id)}; offered Yes token: ${esc(observation.selection_id??'selection/token mapping unverified')}.</p>
        <p>Variant: ${esc(observation.variant)}. Original response SHA-256: <code>${esc(observation.raw_source_sha256)}</code>.</p>
        <dl>${SETTLEMENT.map(key=>`<dt>${esc(key.replaceAll('_',' '))}</dt><dd>${esc(observation.settlement[key]??'Unverified; remains a contract gap.')}</dd>`).join('')}</dl>
      </details>
    </article>`;
  }).join('');
  return `<section class="local-offer-review">
    <header><p class="review-eyebrow">Local source review · unpublished</p><h1>NBA player-contract inspection</h1>
      <p class="review-banner">LOCAL REVIEW ONLY. These observations have no public publication admission. No qualified offer, forecast, recommendation or paper ticket is created.</p>
      <p><strong>${review.counts.player_rows_observed} player rows observed · ${review.counts.rows_parsed} parsed · ${review.counts.complete_contracts} complete contracts</strong></p>
      <p>Review generated: ${esc(clockLabel(review.generated_at))}. This is separate from each original source-observation clock. Recorded observations do not assert current availability.</p></header>
    ${cards||'<p>No player observations were parsed in this bounded inspection.</p>'}
    <section class="review-coverage"><h2>Full NBA category inventory</h2><p>Unobserved means absent from this bounded sample; it does not establish permanent source absence.</p>
      <div class="review-table"><table><thead><tr><th scope="col">Category</th><th scope="col">Observed</th><th scope="col">Parsed</th><th scope="col">Sample state</th></tr></thead>
      <tbody>${ALL_NBA_CATEGORIES.map(category=>{const coverage=review.category_coverage[category];return `<tr><th scope="row">${esc(category)}</th><td>${coverage.observed_rows}</td><td>${coverage.parsed_rows}</td><td>${esc(coverage.status.replaceAll('_',' '))}</td></tr>`;}).join('')}</tbody></table></div></section>
    <p class="review-banner">Paper Builder: NO_ACTION. Source observations do not enter its candidate universe. Genuine forecasts, outcomes, grades and financial settlement remain separate.</p>
  </section>`;
}

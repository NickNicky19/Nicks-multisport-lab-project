// Private source threshold observations. No collection, publication or ticket path.
import {ALL_NBA_CATEGORIES, utcMicros} from './research.mjs';
import {canonicalOffer} from './offers.mjs';

export const PLAYER_LINE_REVIEW_SCHEMA = 'nba-private-player-lines-v1';
const MAX_ROWS = 10000, MAX_OPTIONS = 20000, MAX_DISPLAY = 32;
const MAX_INPUT_BYTES = 8*1024*1024, MAX_REVIEW_BYTES = 256*1024;
const SOURCE_URL = 'https://api.sleeper.com/lines/available';
const SHA = /^[a-f0-9]{64}$/;
const TOP = ['schema_version','scope','source','venue','product','parse_status','generated_at','observed_at','imported_at','evidence_lane','source_evidence','counts','selection','category_coverage','observations','public_admission','ticket_eligibility','qualification','review_id'];
const EVIDENCE = ['kind','input_sha256','input_bytes','metadata_sha256','source_payload_sha256','capture_sha256','source_payload_hash_basis','raw_source_sha256','raw_source_bytes','source_url','provider_permission_verified'];
const COUNTS = ['source_rows','nba_rows','parsed_observations','displayed_observations','unmapped_observations','complete_contracts','diagnostics'];
const ROW = ['row_id','provider_player_id','provider_event_id','provider_selection_id','player_namespace','player_label','event_label','team_label','stat','raw_stat_label','line','side','variant','period','overtime','event_starts_at','source_updated_at','source_declared_status','source_economics','price_status','quote','contract','precision_basis','source_pointer','unavailable_reasons','forecast_match_status','ticket_eligible'];
const LABELS = Object.freeze({points:'PTS',pts_reb_ast:'PRA',rebounds:'REB',threes_made:'3PM',assists:'AST',turnovers:'TOV',double_double:'DD',blocks:'BLK',steals:'STL',points_and_assists:'PA',points_and_rebounds:'PR',rebounds_and_assists:'RA',blocks_and_steals:'BLK+STL'});
const PARSE_STATUSES = ['ok','partial','unmapped','empty','blocked_access','upstream_error','parser_failure'];
const EVIDENCE_LANES = ['SYNTHETIC_TEST','RECONSTRUCTED_RESEARCH','VERIFIED_ASOF_REPLAY','REAL_TIME_CAPTURED'];
const require = (condition,message) => {if (!condition) throw new Error(message);};
const fields = (value,expected) => value !== null && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).sort().join(',') === [...expected].sort().join(',');
const text = (value,maximum=600) => typeof value === 'string' && value.length > 0 && value.length <= maximum && value.trim() === value;
const count = (value,maximum=MAX_OPTIONS) => Number.isSafeInteger(value) && value >= 0 && value <= maximum;
const decimal = value => typeof value === 'string' && value.length <= 128 && /^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(value);
const positiveDecimal = value => decimal(value) && /[1-9]/.test(value);
const clockNow = () => new Date().toISOString().replace(/\.(\d{3})Z$/,(_,ms)=>`.${ms}000Z`);
const esc = value => String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clockLabel = value => value.replace('T',' ').replace('Z',' UTC');

export const canonicalPlayerLineReview = value => canonicalOffer(value);

/** Validate private meaning independently of a caller's content seal. */
export function validatePlayerLineReview(review,now=clockNow()) {
  require(fields(review,TOP) && review.schema_version === PLAYER_LINE_REVIEW_SCHEMA
    && review.scope === 'LOCAL_REVIEW_ONLY' && review.source === 'sleeper' && review.venue === 'Sleeper'
    && review.product === 'Picks variant unverified' && PARSE_STATUSES.includes(review.parse_status)
    && EVIDENCE_LANES.includes(review.evidence_lane) && review.public_admission === false
    && review.ticket_eligibility === false && review.qualification === 'UNAVAILABLE'
    && typeof review.review_id === 'string' && SHA.test(review.review_id),
    'Invalid private player-line source, scope, status or admission.');
  const observed = utcMicros(review.observed_at), imported = utcMicros(review.imported_at), generated = utcMicros(review.generated_at);
  require(observed <= imported && imported <= generated && generated <= utcMicros(now),
    'Player-line observation, import and review clocks disagree.');
  const evidence = review.source_evidence;
  require(fields(evidence,EVIDENCE) && ['RAW_HTTP_BODY_REPLAYED','DERIVED_RECEIPT_ONLY'].includes(evidence.kind)
    && ['input_sha256','source_payload_sha256','capture_sha256'].every(key=>typeof evidence[key] === 'string' && SHA.test(evidence[key]))
    && count(evidence.input_bytes,MAX_INPUT_BYTES) && evidence.input_bytes > 0
    && evidence.source_url === SOURCE_URL && evidence.provider_permission_verified === false,
    'Invalid player-line input evidence.');
  const raw = evidence.kind === 'RAW_HTTP_BODY_REPLAYED';
  if (raw) require(typeof evidence.raw_source_sha256 === 'string' && SHA.test(evidence.raw_source_sha256)
    && typeof evidence.metadata_sha256 === 'string' && SHA.test(evidence.metadata_sha256)
    && count(evidence.raw_source_bytes,MAX_INPUT_BYTES) && evidence.raw_source_bytes > 0
    && evidence.raw_source_sha256 === evidence.input_sha256 && evidence.raw_source_bytes === evidence.input_bytes
    && evidence.source_payload_hash_basis === 'CANONICAL_OPTION_DECIMAL_LEXEME_JSON',
    'Original-byte replay requires its exact raw source and metadata references.');
  else require(evidence.raw_source_sha256 === null && evidence.raw_source_bytes === null && evidence.metadata_sha256 === null
    && evidence.source_payload_hash_basis === 'CANONICAL_IMPORT_INPUT_JSON',
    'A derived receipt cannot claim original HTTP bytes or replay precision.');
  const totals = review.counts, selection = review.selection;
  require(fields(totals,COUNTS) && Object.values(totals).every(value=>count(value,Number.MAX_SAFE_INTEGER))
    && totals.source_rows <= MAX_ROWS && totals.nba_rows <= totals.source_rows
    && totals.parsed_observations <= MAX_OPTIONS && totals.unmapped_observations <= totals.parsed_observations && totals.complete_contracts === 0,
    'Invalid complete-source player-line counts.');
  require(totals.parsed_observations === 0 || ['ok','partial','unmapped'].includes(review.parse_status),
    'A failed or empty import cannot contain parsed observations.');
  require(fields(selection,['offset','limit','ordering']) && count(selection.offset)
    && count(selection.limit,MAX_DISPLAY) && selection.limit > 0 && selection.ordering === 'SOURCE_ROW_OPTION_ORDER'
    && selection.offset <= totals.parsed_observations
    && totals.displayed_observations === Math.min(selection.limit,totals.parsed_observations-selection.offset)
    && Array.isArray(review.observations) && review.observations.length === totals.displayed_observations,
    'Player-line window does not match its explicit source offset and limit.');
  require(fields(review.category_coverage,ALL_NBA_CATEGORIES),'All fourteen NBA categories are required.');
  let observedCategories = 0, displayedCategories = 0;
  const rowIds = new Set();
  for (const [index,row] of review.observations.entries()) {
    require(fields(row,ROW),'Invalid private player-line row fields.');
    for (const key of ['row_id','provider_player_id','provider_event_id','provider_selection_id','raw_stat_label','variant','source_pointer'])
      require(text(row[key]),`Invalid player-line ${key}.`);
    require(row.player_namespace === 'sleeper' && row.player_label === null && row.event_label === null
      && row.period === null && row.overtime === null && row.event_starts_at === null
      && (row.team_label === null || text(row.team_label,200))
      && (row.source_declared_status === null || text(row.source_declared_status,100)),
      'Unverified identity, affiliation, period or event facts cannot be supplied by this version.');
    require((row.stat === null || ALL_NBA_CATEGORIES.includes(row.stat))
      && row.stat === (Object.hasOwn(LABELS,row.raw_stat_label) ? LABELS[row.raw_stat_label] : null)
      && decimal(row.line) && ['over','under'].includes(row.side),
      'Unverified player-line statistic, decimal threshold or side.');
    require(!rowIds.has(row.row_id),'Duplicate player-line source row.');
    rowIds.add(row.row_id);
    if (row.source_updated_at !== null)
      require(utcMicros(row.source_updated_at) <= observed,'Source update follows the original observation.');
    require(row.source_economics === null || (fields(row.source_economics,['kind','value'])
      && row.source_economics.kind === 'pickem_multiplier' && positiveDecimal(row.source_economics.value)),
      'Source economics must remain a literal positive pick’em multiplier.');
    require(row.price_status === 'PRICE_UNAVAILABLE' && row.quote === null && row.contract === null
      && row.forecast_match_status === 'NOT_MATCHED_UNVERIFIED_IDENTITY_EVENT_PERIOD' && row.ticket_eligible === false,
      'A private threshold cannot become a price, full contract, forecast match or ticket.');
    require(Array.isArray(row.unavailable_reasons) && row.unavailable_reasons.length <= 32
      && row.unavailable_reasons.every(reason=>text(reason))
      && new Set(row.unavailable_reasons).size === row.unavailable_reasons.length
      && ['player_name_unverified','event_identity_unverified','period_unverified','overtime_unverified']
        .every(reason=>row.unavailable_reasons.includes(reason)),
      'Invalid player-line unresolved fields.');
    const sourceRow = /^row:(0|[1-9][0-9]*)\/option:(0|[1-9][0-9]*)$/.exec(row.row_id);
    require(sourceRow !== null && Number.isSafeInteger(Number(sourceRow[1])) && Number(sourceRow[1]) < totals.source_rows
      && Number.isSafeInteger(Number(sourceRow[2])) && Number(sourceRow[2]) < 64,
      'Player-line source row is outside the complete input.');
    if (raw) require(row.precision_basis === 'RAW_NUMERIC_LEXEME_REPLAYED'
      && row.source_pointer === `/${sourceRow[1]}/options/${sourceRow[2]}/outcome_value`,
      'Original threshold replay must bind its exact row and option pointer.');
    else require(row.precision_basis === 'DERIVED_TEXT_ONLY'
      && row.source_pointer === `/payload/observations/${selection.offset+index}/line`,
      'A derived threshold must retain its exact receipt pointer.');
  }
  for (const category of ALL_NBA_CATEGORIES) {
    const coverage = review.category_coverage[category];
    require(fields(coverage,['observed_side_options','displayed_side_options','status'])
      && count(coverage.observed_side_options) && count(coverage.displayed_side_options,MAX_DISPLAY)
      && coverage.displayed_side_options <= coverage.observed_side_options
      && coverage.displayed_side_options === review.observations.filter(row=>row.stat === category).length
      && coverage.status === (coverage.observed_side_options ? 'OBSERVED_IN_SAMPLE' : 'UNOBSERVED_IN_SAMPLE'),
      'Player-line category coverage disagrees with the source or selected window.');
    observedCategories += coverage.observed_side_options; displayedCategories += coverage.displayed_side_options;
  }
  require(observedCategories+totals.unmapped_observations === totals.parsed_observations
    && displayedCategories+review.observations.filter(row=>row.stat === null).length === totals.displayed_observations,
    'Mapped and unmapped player-line counts disagree.');
  require(new TextEncoder().encode(canonicalPlayerLineReview(review)).byteLength <= MAX_REVIEW_BYTES,
    'Private player-line review exceeds its byte limit.');
  return review;
}

export async function verifyPlayerLineReviewHash(review,cryptoProvider=globalThis.crypto) {
  require(cryptoProvider?.subtle,'SHA-256 support is required.');
  const unsigned = Object.fromEntries(Object.entries(review).filter(([key])=>key !== 'review_id'));
  const bytes = await cryptoProvider.subtle.digest('SHA-256',new TextEncoder().encode(canonicalPlayerLineReview(unsigned)));
  const expected = Array.from(new Uint8Array(bytes)).map(value=>value.toString(16).padStart(2,'0')).join('');
  require(review.review_id === expected,'Private player-line review seal mismatch.');
  return review;
}

export function renderPlayerLineReview(review,{now=clockNow()}={}) {
  validatePlayerLineReview(review,now);
  const totals = review.counts, evidence = review.source_evidence, selection = review.selection;
  const position = totals.displayed_observations ? `${selection.offset+1}–${selection.offset+totals.displayed_observations}` : 'none';
  const provenance = evidence.kind === 'RAW_HTTP_BODY_REPLAYED'
    ? 'Original source bytes replayed; numeric line lexemes preserved.'
    : 'Derived receipt only; original HTTP response bytes are unavailable. Original decimal precision is unverified.';
  const cards = review.observations.map(row=>`<article class="local-observation" data-review-state="OBSERVED_PLAYER_THRESHOLD">
    <p class="review-eyebrow">Recorded player threshold · private review</p>
    <h2>Sleeper player ${esc(row.provider_player_id)} · ${esc(row.side.toUpperCase())} ${esc(row.line)} ${esc(row.stat ?? row.raw_stat_label)}</h2>
    <p class="review-matchup">Player name and matchup unverified · Sleeper event ${esc(row.provider_event_id)}.</p>
    ${row.team_label === null ? '' : `<p>Source team label: ${esc(row.team_label)}. This label does not establish a verified player/event crosswalk.</p>`}
    <p><strong>Price unavailable (PRICE_UNAVAILABLE).</strong> No matching forecast or qualified ticket is attached.</p>
    <p>Period, overtime and event start: unverified. Source-declared status: ${esc(row.source_declared_status ?? 'not supplied')}.</p>
    <p>Source updated: ${esc(row.source_updated_at === null ? 'not supplied' : clockLabel(row.source_updated_at))}. The review clock does not refresh this source value.</p>
    <section class="review-gaps"><h3>Unresolved fields</h3>${row.unavailable_reasons.length ? `<ul>${row.unavailable_reasons.map(reason=>`<li>${esc(reason.replaceAll('_',' '))}</li>`).join('')}</ul>` : '<p>The row remains unverified for identity, event and period matching.</p>'}</section>
    <details><summary>Native IDs, source evidence and literal economics</summary>
      <p>Player namespace: sleeper. Player ${esc(row.provider_player_id)}; event ${esc(row.provider_event_id)}; selection ${esc(row.provider_selection_id)}; row ${esc(row.row_id)}.</p>
      <p>Source statistic: ${esc(row.raw_stat_label)}. Variant: ${esc(row.variant)}. Source pointer: <code>${esc(row.source_pointer)}</code>.</p>
      <p>Precision basis: ${esc(row.precision_basis)}.</p>
      <p>${row.source_economics === null ? 'No source economics supplied.' : `Observed pick’em side multiplier: ${esc(row.source_economics.value)}×. Retained literally; this is not standalone sportsbook odds.`}</p>
    </details>
  </article>`).join('');
  return `<section class="local-offer-review">
    <header><p class="review-eyebrow">Private player-line review · unpublished</p><h1>NBA player-line observations</h1>
      <p class="review-banner">LOCAL REVIEW ONLY. Recorded thresholds remain separate from complete contracts, recommendations and qualified paper tickets.</p>
      <p>Source: Sleeper. Product: ${esc(review.product)}. Parser result: ${esc(review.parse_status)}.</p>
      <p><strong>${totals.parsed_observations} parsed side options · displaying ${position} of ${totals.parsed_observations}</strong>.</p>
      <p>Explicit window: offset ${selection.offset}, limit ${selection.limit}, source row/option order. Complete input: ${totals.source_rows} source rows, ${totals.nba_rows} NBA rows; ${totals.unmapped_observations} unmapped side options; ${totals.diagnostics} diagnostics. ${totals.complete_contracts} complete contracts.</p>
      <p>Observed: ${esc(clockLabel(review.observed_at))}. Imported: ${esc(clockLabel(review.imported_at))}. Review generated: ${esc(clockLabel(review.generated_at))}.</p>
      <p class="review-limit">${esc(provenance)} This private review does not establish current availability or provider permission for collection or publication.</p>
    </header>
    ${cards || '<p>No player thresholds are present in this selected window. An empty window does not establish permanent source absence.</p>'}
    <section class="review-coverage"><h2>Full NBA category inventory</h2><p>Observed counts cover the complete parsed input. Displayed counts cover only the explicit window above. An unobserved category is not a claim of permanent source absence.</p>
      <div class="review-table"><table><thead><tr><th scope="col">Category</th><th scope="col">Observed side options</th><th scope="col">Displayed side options</th><th scope="col">Sample state</th></tr></thead><tbody>
      ${ALL_NBA_CATEGORIES.map(category=>{const row=review.category_coverage[category];return `<tr><th scope="row">${esc(category)}</th><td>${row.observed_side_options}</td><td>${row.displayed_side_options}</td><td>${esc(row.status.replaceAll('_',' '))}</td></tr>`;}).join('')}
      </tbody></table></div>
    </section>
    <details><summary>Input provenance</summary><p>Source URL: ${esc(evidence.source_url)}.</p>
      <p>Input SHA-256: <code>${esc(evidence.input_sha256)}</code> (${evidence.input_bytes} bytes). Source-payload hash basis: ${esc(evidence.source_payload_hash_basis)}; SHA-256 <code>${esc(evidence.source_payload_sha256)}</code>.</p>
      <p>Original response SHA-256: <code>${esc(evidence.raw_source_sha256 ?? 'not available')}</code>; original byte count: ${esc(evidence.raw_source_bytes ?? 'not available')}.</p>
      <p>Provider permission independently verified: no. Public admission: no. Ticket eligibility: no.</p></details>
  </section>`;
}

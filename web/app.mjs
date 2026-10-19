import {filterRowsByScope, filterCandidateUniverse, resolveSportScope, validRequestedLegCount} from './scope.mjs';
import {loadSnapshot} from './snapshot.mjs';

const routes = [
  ['overview', 'Overview', '◫'], ['props', 'Props', '≡'], ['value', 'Value Research', '⇄'],
  ['builder', 'Paper Builder', '⊞'], ['performance', 'Performance', '▥'], ['sources', 'Source Health', '◉'], ['specials', 'Specials', '✧'],
];
const state = {snapshot: null, error: null, scope: {mode: 'SINGLE', sports: ['NBA']}, filters: {category: 'ALL', side: 'ALL', period: 'full_game', window: 'upcoming', venue: 'ALL', evidence: 'ALL'}, builder: {legs: 6, mode: 'MIXED', checked: false}};
const main = document.querySelector('#main');
const escape = value => String(value).replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
const pill = (text, tone = '') => `<span class="pill ${tone}">${escape(text)}</span>`;
const datetime = value => value ? new Intl.DateTimeFormat('en-GB', {dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC'}).format(new Date(value)) + ' UTC' : 'Unknown';
const sports = () => state.snapshot?.sports || [];
const supported = () => sports().map(sport => sport.league);
const scopedSports = () => filterRowsByScope(sports(), state.scope, supported());
const allRows = key => sports().flatMap(sport => sport[key]);
const scopedRows = key => filterRowsByScope(allRows(key), state.scope, supported());
const scopeLabel = () => {
  const selected = resolveSportScope(state.scope, supported());
  if (!selected.length) return 'No sports selected';
  return state.scope.mode === 'ALL' ? `All supported sports · ${selected.join(', ')}` : selected.join(' + ');
};
const empty = (title, text, icon = '◌') => `<div class="empty-state"><span class="empty-icon" aria-hidden="true">${icon}</span><h3>${title}</h3><p>${text}</p></div>`;
const pageHeading = (eyebrow, title, description, extra = '') => `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${description}</p></div>${extra}</div>`;
const panel = (title, content, sub = '', extra = '') => `<section class="panel"><div class="panel-heading"><div><h2>${title}</h2>${sub ? `<p>${sub}</p>` : ''}</div>${extra}</div>${content}</section>`;

function publicationStatus() {
  if (state.error) return `<div class="notice error" role="alert"><strong>Published snapshot unavailable</strong><p>${escape(state.error)} No opportunities or paper candidates can be shown. Refresh to retry the published files.</p></div>`;
  const errors = state.snapshot?.errors || [];
  const missing = Object.entries(state.snapshot?.manifest.errors || {}).filter(([league]) => !state.snapshot.manifest.sports.some(reference => reference.league === league));
  return errors.map(error => `<div class="notice error" role="alert"><strong>${escape(error.league)} snapshot unavailable</strong><p>${escape(error.message)} Other valid sport snapshots remain visible.</p></div>`).join('') + missing.map(([league, message]) => `<div class="notice error" role="alert"><strong>${escape(league)} update unavailable</strong><p>${escape(message)} No valid prior snapshot is available for this sport.</p></div>`).join('') + (state.snapshot?.manifest.sports || []).filter(reference => reference.retained).map(reference => `<div class="notice warning"><strong>${escape(reference.league)} retains an earlier snapshot</strong><p>Generated ${datetime(reference.generated_at)}. ${escape(reference.error || 'The new observation was not published.')} This publication time does not refresh its inputs.</p></div>`).join('');
}

function snapshotNote() {
  const manifest = state.snapshot?.manifest;
  return `<div class="snapshot-note"><span class="status-dot"></span>${manifest ? `Publication ${datetime(manifest.published_at)} <span class="note-divider">/</span> Build <code title="${escape(manifest.build_commit)}">${manifest.build_commit.slice(0, 10)}</code>` : 'No verified publication loaded'}<span class="snapshot-qualifier">Publication time is not a quote observation time.</span></div>`;
}

function scopeControl() {
  return `<fieldset class="scope-control"><legend>Sport scope</legend><div class="segmented" role="group" aria-label="Sport selection mode">${[['SINGLE', 'One sport'], ['SELECTED', 'Selected sports'], ['ALL', 'All supported']].map(([value, label]) => `<button type="button" class="${state.scope.mode === value ? 'active' : ''}" data-scope="${value}" aria-pressed="${state.scope.mode === value}">${label}</button>`).join('')}</div><div class="sport-choices">${supported().length ? supported().map(league => `<label class="sport-choice"><input type="${state.scope.mode === 'SINGLE' ? 'radio' : 'checkbox'}" name="sport" value="${escape(league)}" ${resolveSportScope(state.scope, supported()).includes(league) ? 'checked' : ''} ${state.scope.mode === 'ALL' ? 'disabled' : ''}><span>${escape(league)}</span><span class="mini-label">Research coverage</span></label>`).join('') : '<span class="muted">No sport snapshot available.</span>'}</div><p class="control-help">Available choices follow published coverage. “All” currently means ${supported().join(', ') || 'no available sports'}. Coverage does not qualify forecasts or products.</p></fieldset>`;
}

function categoryGrid(markets) {
  if (!markets.length) return empty('Category snapshot unavailable', 'No validated inventory has loaded. Research scope remains defined in the repository.');
  return `<div class="category-grid">${markets.filter(market => market.requested).map(market => `<div class="category-card"><span class="category-code">${escape(market.code)}</span><span>${escape(market.name.replace(' indicator', ''))}</span><span class="category-status">Research scope</span></div>`).join('')}</div>`;
}

function overview() {
  const nba = sports().find(sport => sport.league === 'NBA');
  const marketCount = nba?.markets.filter(market => market.requested).length;
  return `<section class="hero"><div class="hero-content"><div class="eyebrow"><span class="status-dot"></span> THE LAB IS TAKING SHAPE</div><h1>Better questions.<br><em>Stronger evidence.</em></h1><p>A shared home for player-outcome research, exact offers and carefully evaluated paper decisions. Starting with the NBA.</p><div class="hero-actions"><a class="button primary" href="#/props">Explore the research <span aria-hidden="true">↗</span></a><a class="text-link light" href="#/sources">See source status <span aria-hidden="true">→</span></a></div></div><div class="hero-aside" aria-label="Research process"><div class="lab-orbit" aria-hidden="true"><div class="orbit-ring ring-one"></div><div class="orbit-ring ring-two"></div><div class="orbit-ring ring-three"></div><span class="orbit-center">N<span>THE LAB</span></span><span class="orbit-dot dot-one"></span><span class="orbit-dot dot-two"></span><span class="orbit-dot dot-three"></span></div><p>OBSERVE <span>→</span> FORECAST <span>→</span> EVALUATE</p></div></section>
  <div class="summary-grid"><div class="summary-card"><span class="summary-label">INITIAL COVERAGE</span><strong>NBA<span class="tiny-tag">Research</span></strong><p>Other sports require independent admission.</p></div><div class="summary-card"><span class="summary-label">REQUIRED CATEGORIES</span><strong>${marketCount ?? '—'}<span class="summary-unit">in development scope</span></strong><p>One coherent joint-outcome foundation.</p></div><div class="summary-card"><span class="summary-label">PAPER DECISION</span><strong class="no-action">NO_ACTION</strong><p>No qualified ticket is available.</p></div></div>
  ${panel('A full-category foundation', categoryGrid(nba?.markets || []), 'Every requested NBA category is in scope. Each must earn its own evidence.', '<a class="text-link" href="#/props">View inventory <span aria-hidden="true">→</span></a>')}
  <div class="two-col">${panel('Where the evidence stands', `<div class="stage-list">${[['01', 'Source & identity', 'Audit actual rows, capture clocks and permitted use.'], ['02', 'Forecast research', 'Evaluate all categories under shared chronological definitions.'], ['03', 'Paper qualification', 'Require supported quotes, terms and joint outcomes.']].map(([number, title, text]) => `<div class="stage-row"><span>${number}</span><div><h3>${title}</h3><p>${text}</p></div>${pill('In progress', 'neutral')}</div>`).join('')}</div>`)}${panel('Research is not a result', `<p class="body-copy">An inventory, a software check and a statistical evaluation establish different things. This publication makes no validated forecast, profitability or product qualification claim.</p><div class="callout"><strong>No invented picks.</strong><p>Offers, probabilities and outcomes appear only when supported by retained evidence.</p></div><a class="text-link" href="#/performance">Understand the scorecards <span aria-hidden="true">→</span></a>`)}</div>`;
}

function selectControl(label, key, options, value) {
  return `<label class="filter-label">${label}<select data-filter="${key}">${options.map(([option, name]) => `<option value="${escape(option)}" ${value === option ? 'selected' : ''}>${escape(name)}</option>`).join('')}</select></label>`;
}

function props() {
  const markets = scopedSports().flatMap(sport => sport.markets);
  const categories = [...new Map(markets.map(market => [market.code, market])).values()];
  const rows = scopedRows('offers');
  return pageHeading('THE RESEARCH BOARD', 'Props', 'Explore exact offers and outcome research within your selected sport scope.', pill('No qualified opportunities', 'neutral')) + `<section class="panel filter-panel">${scopeControl()}<div class="filter-grid">${selectControl('Category', 'category', [['ALL', 'All categories'], ...categories.map(market => [market.code, `${market.code} · ${market.name.replace(' indicator', '')}`])], state.filters.category)}${selectControl('Event window', 'window', [['upcoming', 'Upcoming events'], ['24h', 'Next 24 hours'], ['7d', 'Next 7 days']], state.filters.window)}${selectControl('Period', 'period', [['full_game', 'Full game']], state.filters.period)}${selectControl('Side', 'side', [['ALL', 'All sides'], ['OVER', 'Over'], ['UNDER', 'Under']], state.filters.side)}${selectControl('Venue', 'venue', [['ALL', 'All observed venues']], state.filters.venue)}${selectControl('Evidence', 'evidence', [['ALL', 'All evidence states'], ['OFFER_ONLY', 'Offer only'], ['RESEARCH', 'Research forecast'], ['EVALUATED', 'Evaluated forecast'], ['PRICED', 'Priced paper candidate']], state.filters.evidence)}</div></section>` + panel('Published opportunities', empty('No offers published in this scope', 'Source access, exact contract mapping and price evidence are still under review. Missing prices stay unknown; no default odds are supplied.'), `${scopeLabel()} · ${rows.length} published offers`, pill('Research only', 'research-pill')) + panel('Category evidence inventory', `<div class="table-wrap"><table><caption class="sr-only">Category-specific forecast, quote and settlement admission</caption><thead><tr><th scope="col">Category</th><th scope="col">Forecast</th><th scope="col">Quotes</th><th scope="col">Settlement</th></tr></thead><tbody>${categories.map(market => `<tr><th scope="row"><strong>${escape(market.code)}</strong><span class="cell-sub">${escape(market.name)}${market.requested ? '' : ' · optional'}</span></th><td>${pill('Unvalidated', 'neutral')}</td><td>${pill('Unverified', 'neutral')}</td><td>${pill('Unverified', 'neutral')}</td></tr>`).join('') || '<tr><td colspan="4">No inventory is available for this selection.</td></tr>'}</tbody></table></div>`, 'Each category retains its own status. Registry membership is not qualification.') + `<div class="notice"><strong>Independent evidence dimensions</strong><p>An observed offer, a research forecast, an evaluated model, a priced candidate and a settlement rule are separate states. No single badge substitutes for all five.</p></div>`;
}

function valueResearch() {
  return pageHeading('EXACT CONTRACTS, EXPLICIT ASSUMPTIONS', 'Value Research', 'A supported probability and an actual price are both required to estimate value.') + `<div class="two-col">${panel('Contract comparison', empty('No comparable priced contracts', 'No verified contemporaneous matching offers are published. An ESPN DraftKings label alone does not establish two-sided prices.', '⇄'))}${panel('Entry economics', empty('Payout terms not qualified', 'Sleeper side multipliers are not standalone sportsbook decimal odds. A complete entry needs actual payout and settlement terms.', '∑'))}</div>` + panel('What a value estimate must preserve', `<div class="requirements-grid">${[['Exact identity', 'League, player, event, stat, period, line, side, variant, venue and product.'], ['Probability source', 'Evaluated model, matching market reference or separately evaluated hybrid.'], ['Actual clocks', 'One observation for line and price; capture age and source update time or unknown.'], ['Settlement semantics', 'Pushes, voids, participation rules, guaranteed returns and any pool terms.']].map(([title, text]) => `<div><h3>${title}</h3><p>${text}</p></div>`).join('')}</div>`, 'Forecast accuracy and economic opportunity are evaluated separately.') + `<div class="notice"><strong>Value unavailable</strong><p>No live price, margin-removal reference, probability or provider payout is inferred from a missing field.</p></div>`;
}

function builder() {
  const universe = filterCandidateUniverse(allRows('candidates'), state.scope, supported(), state.builder.mode);
  return pageHeading('PROSPECTIVE PAPER RESEARCH', 'Paper Builder', 'Configure a 2–6-leg research request. A complete ticket must qualify on its own terms.', pill('NO_ACTION', 'warning-pill')) + `<div class="builder-layout"><section class="panel filter-panel"><h2 class="section-title">Define your paper request</h2>${scopeControl()}<fieldset class="leg-control"><legend>Requested legs</legend><div class="leg-choices">${[2, 3, 4, 5, 6].map(count => `<label><input type="radio" name="legs" value="${count}" ${state.builder.legs === count ? 'checked' : ''}><span>${count}</span></label>`).join('')}</div><p class="control-help">Six is preferred only when the complete ticket qualifies. Smaller tickets or NO_ACTION remain valid.</p></fieldset><fieldset class="mode-control"><legend>Direction policy</legend><div class="mode-choices">${[['OVER_ONLY', 'Over only'], ['UNDER_ONLY', 'Under only'], ['MIXED', 'Mixed']].map(([value, title]) => `<label><input type="radio" name="direction" value="${value}" ${state.builder.mode === value ? 'checked' : ''}><span>${title}</span></label>`).join('')}</div></fieldset><label class="filter-label venue-label">Eligible venue / product<select disabled aria-describedby="venue-help"><option>No admitted products</option></select></label><p id="venue-help" class="control-help">A ticket stays within one exact eligible venue, product and rules variant. Venue comparisons remain separate.</p><button type="button" class="button dark full-width" id="readiness">Check paper readiness <span aria-hidden="true">→</span></button><p class="control-help">This checks the published research state. It does not issue a ticket or create a prospective receipt.</p></section><div>${panel('Paper request', `<dl class="request-summary"><div><dt>Sport scope</dt><dd>${escape(scopeLabel())}</dd></div><div><dt>Requested size</dt><dd>${state.builder.legs} legs</dd></div><div><dt>Direction</dt><dd>${escape(state.builder.mode)}</dd></div><div><dt>Candidate universe</dt><dd>${universe.length} admitted candidates</dd></div><div><dt>Decision time</dt><dd>Not issued</dd></div><div><dt>Joint outcome method</dt><dd>Not qualified</dd></div><div><dt>Payout & settlement</dt><dd>Not verified</dd></div></dl><div class="decision-box" ${state.builder.checked ? 'role="status"' : ''}><span class="eyebrow">${state.builder.checked ? 'READINESS CHECK COMPLETE' : 'CURRENT PAPER STATE'}</span><strong>NO_ACTION</strong><p>No admitted candidates, complete product terms or qualified joint ticket calculation are published.</p></div>`, 'A request is not a frozen paper ticket.')}${panel('Qualification stays strict', `<ul class="plain-list"><li>A selected sport group never expands to fill legs.</li><li>All forecasts, quotes and terms precede one common decision time.</li><li>Initial suggested tickets require distinct players and events.</li><li>Independence, if used later, must be an explicit assumption.</li><li>No local draft is a durable prospective evidence ledger.</li></ul>`)}</div></div>`;
}

function performance() {
  return pageHeading('EVIDENCE, KEPT SEPARATE', 'Performance', 'Software behavior, statistical evaluation and future paper outcomes answer different questions.') + `<div class="scorecard-grid">${[['01', 'Forecast accuracy', 'No validated evaluation published', 'Per-category distribution scores, calibration, chronological cohorts and uncertainty.'], ['02', 'Selected-leg outcomes', 'No prospective leg results published', 'Frozen candidate universes and genuine decision clocks before events occur.'], ['03', 'Complete tickets', 'No settled paper tickets published', 'Actual product payouts, full and partial returns, voids, paper ROI and exposure.']].map(([number, title, status, text]) => `<section class="panel scorecard"><span class="scorecard-number">${number}</span><h2>${title}</h2><div class="scorecard-value">—</div><strong>${status}</strong><p>${text}</p></section>`).join('')}</div>` + panel('Evidence lanes', `<div class="table-wrap"><table><thead><tr><th scope="col">Lane</th><th scope="col">What it can establish</th></tr></thead><tbody>${[['SYNTHETIC_TEST', 'Specified software behavior on invented examples.'], ['RECONSTRUCTED_RESEARCH', 'Historical research; original pregame availability is not implied.'], ['VERIFIED_ASOF_REPLAY', 'Archived inputs independently verified at the historical cutoff.'], ['REAL_TIME_CAPTURED', 'Actual future information captured before the declared decision deadline.']].map(([lane, text]) => `<tr><th scope="row"><code>${lane}</code></th><td>${text}</td></tr>`).join('')}</tbody></table></div>`, 'A successful unit test is not model performance. A future outcome cannot be created ahead of its event.') + `<div class="notice"><strong>Product qualification remains unavailable</strong><p>No hit rate, ROI, accuracy label or completed model claim is supported by this empty research publication.</p></div>`;
}

function sources() {
  const sources = sports().flatMap(sport => sport.sources.map(source => ({...source, league: sport.league})));
  return pageHeading('COVERAGE & PROVENANCE', 'Source Health', 'Actual access evidence and category coverage determine what the lab can publish.') + panel('Published source observations', sources.length ? `<div class="source-list">${sources.map(source => `<article class="source-card"><div class="source-symbol" aria-hidden="true">◎</div><div><div class="source-card-heading"><h3>${escape(source.name)}</h3>${pill(source.status.replaceAll('_', ' '), 'neutral')}</div><p>${escape(source.detail)}</p><div class="source-meta">${escape(source.league)} <span>·</span> Observation clock: ${datetime(source.observed_at)}</div></div></article>`).join('')}</div>` : empty('Source evidence unavailable', 'No source-status snapshot has loaded. This is not evidence of a valid empty upstream board.'), 'A failed request, a blocked source, a parser error and a valid empty board are different states.') + `<div class="two-col">${panel('Snapshot provenance', `<dl class="request-summary"><div><dt>Publication</dt><dd>${datetime(state.snapshot?.manifest.published_at)}</dd></div><div><dt>Build commit</dt><dd><code class="break-code">${escape(state.snapshot?.manifest.build_commit || 'Unavailable')}</code></dd></div><div><dt>Snapshot ID</dt><dd><code class="break-code">${escape(state.snapshot?.manifest.snapshot_id || 'Unavailable')}</code></dd></div><div><dt>Integrity</dt><dd>${sports().length ? 'Loaded sport bytes matched manifest SHA-256' : 'No sport snapshot verified'}</dd></div></dl><p class="control-help">Hashes detect changed content; they do not prove upstream authenticity, permission or original publication time.</p>`)}${panel('Boundaries of this publication', `<ul class="plain-list"><li>No new paid services, signups or API keys.</li><li>Public URL access does not establish collection or redistribution permission.</li><li>No upstream scraping or model rebuilding runs in your browser.</li><li>Unknown source update clocks stay unknown.</li><li>Raw archives and private inputs are excluded from site assets.</li></ul>`)}</div>`;
}

function specials() {
  return pageHeading('JOINT OUTCOMES & THRESHOLDS', 'Specials', 'Double-doubles and triple-doubles remain in the full NBA research scope.') + `<div class="two-col">${panel('Double-double · DD', `<div class="special-number">2<span>or more categories at ten</span></div><p class="body-copy">Count PTS, REB, AST, STL and BLK reaching at least ten in the same outcome sample.</p>${pill('Forecast unvalidated', 'neutral')}`)}${panel('Triple-double · TD', `<div class="special-number">3<span>or more categories at ten</span></div><p class="body-copy">Use the same five categories and the same joint outcome sample. Every triple-double also satisfies a double-double.</p>${pill('Forecast unvalidated', 'neutral')}`)}</div>` + panel('Separately qualified Specials', empty('No supported Specials offers', 'Category definitions do not establish observed product availability, calibrated probabilities or exact venue settlement rules.', '✧')) + `<div class="notice"><strong>Coherence before qualification</strong><p>Scoring, combinations, DD and TD share outcomes. Derived identities preserve TD ≤ DD; each category still needs its own evaluation. Turnovers and three-point makes do not count as extra DD/TD categories.</p></div>`;
}

function bindControls() {
  document.querySelectorAll('[data-scope]').forEach(button => button.addEventListener('click', () => {
    const mode = button.dataset.scope;
    const existing = resolveSportScope(state.scope, supported());
    state.scope = {mode, sports: mode === 'ALL' ? [] : mode === 'SINGLE' ? existing.slice(0, 1).length ? existing.slice(0, 1) : supported().slice(0, 1) : existing};
    state.filters.category = 'ALL'; state.builder.checked = false; render();
  }));
  document.querySelectorAll('input[name="sport"]').forEach(input => input.addEventListener('change', () => {
    const checked = [...document.querySelectorAll('input[name="sport"]:checked')].map(element => element.value);
    state.scope.sports = checked; state.filters.category = 'ALL'; state.builder.checked = false; render();
  }));
  document.querySelectorAll('[data-filter]').forEach(input => input.addEventListener('change', () => {state.filters[input.dataset.filter] = input.value; render();}));
  document.querySelectorAll('input[name="legs"]').forEach(input => input.addEventListener('change', () => {const count = Number(input.value); if (validRequestedLegCount(count)) state.builder.legs = count; state.builder.checked = false; render();}));
  document.querySelectorAll('input[name="direction"]').forEach(input => input.addEventListener('change', () => {state.builder.mode = input.value; state.builder.checked = false; render();}));
  document.querySelector('#readiness')?.addEventListener('click', () => {state.builder.checked = true; render(); document.querySelector('.decision-box').focus?.();});
}

function render() {
  const requested = location.hash.slice(2) || 'overview';
  const route = routes.find(([key]) => key === requested);
  const key = route?.[0] || 'unknown';
  document.querySelector('#navigation').innerHTML = routes.map(([id, label, icon]) => `<a href="#/${id}" class="nav-item ${id === key ? 'active' : ''}" ${id === key ? 'aria-current="page"' : ''}><span aria-hidden="true">${icon}</span>${label}${id === 'specials' ? '<span class="nav-small">DD / TD</span>' : ''}</a>`).join('');
  document.querySelector('#breadcrumb').textContent = `The lab / ${route?.[1] || 'Page unavailable'}`;
  document.title = `${route?.[1] || 'Page unavailable'} · Nick’s Multisport Lab`;
  const views = {overview, props, value: valueResearch, builder, performance, sources, specials};
  main.innerHTML = publicationStatus() + (views[key] ? views[key]() : pageHeading('PAGE UNAVAILABLE', 'This route is not in the lab.', 'Use the navigation to return to a published research view.') + '<a class="button dark" href="#/overview">Back to overview</a>') + snapshotNote();
  bindControls();
}

window.addEventListener('hashchange', () => {
  if (location.hash === '#main') {main.focus(); return;}
  render(); main.focus(); window.scrollTo(0, 0);
});

try {state.snapshot = await loadSnapshot();} catch (error) {state.error = error.message || 'The publication could not be verified.';}
render();

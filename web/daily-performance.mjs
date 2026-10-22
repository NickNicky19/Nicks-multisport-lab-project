// Descriptive display over already validated daily research originals/grades.
// No source collection, forecast generation, qualification or model selection.
import {ALL_NBA_CATEGORIES,utcMicros} from './research.mjs';

export const DAILY_CALIBRATION_QUANTILES = [0.1, 0.5, 0.9];
export const DAILY_LEAD_BINS = ['UNDER_90', '90_TO_180', '180_PLUS'];
const MODELS = ['R0', 'K0'];
const escaped = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const finite = (value, label) => {
  if (!['number', 'string'].includes(typeof value) || value === '' || !Number.isFinite(Number(value))) throw new Error(`Invalid daily ${label}.`);
  return Number(value);
};
const mean = values => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
const number = value => value === null ? '—' : Number(value).toLocaleString('en-GB', {maximumSignificantDigits: 5});
const percent = value => value === null ? '—' : `${number(value * 100)}%`;

function dateValue(value) {
  if (value === '') return null;
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return NaN;
  const millis = Date.parse(value + 'T00:00:00Z');
  return Number.isFinite(millis) && new Date(millis).toISOString().slice(0, 10) === value ? millis : NaN;
}

function filters(options) {
  const selected = {model: options.model ?? 'ALL', category: options.category ?? 'ALL',
    dateFrom: options.dateFrom ?? '', dateTo: options.dateTo ?? '', leadTime: options.leadTime ?? 'ALL'};
  const first = dateValue(selected.dateFrom), last = dateValue(selected.dateTo);
  const valid = ['ALL', ...MODELS].includes(selected.model) && ['ALL', ...ALL_NBA_CATEGORIES].includes(selected.category)
    && ['ALL', ...DAILY_LEAD_BINS].includes(selected.leadTime) && !Number.isNaN(first) && !Number.isNaN(last)
    && (first === null || last === null || first <= last);
  return {...selected, first, last, valid};
}

function leadMinutes(forecast) {
  const start = utcMicros(forecast.event_starts_at), issued = utcMicros(forecast.issued_at);
  if (start <= issued) throw new Error('Invalid daily issuance lead time.');
  return Number(start - issued) / 60000000;
}

function leadBin(minutes) { return minutes < 90 ? 'UNDER_90' : minutes < 180 ? '90_TO_180' : '180_PLUS'; }

// Decimal strings are summed exactly for the display's fixed CDF thresholds.
// Comparing observed frequencies with CDF(q), rather than tau, preserves ties.
function calibrationAt(pmf, tau) {
  if (!Array.isArray(pmf) || !pmf.length) throw new Error('Empty daily calibration distribution.');
  const digits = pmf.map(atom => {
    const text = String(atom.probability);
    if (!/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(text) || text.length > 128) throw new Error('Invalid daily calibration probability.');
    return text;
  });
  const places = Math.max(...digits.map(text => (text.split('.')[1] || '').length));
  const scale = 10n ** BigInt(places), threshold = BigInt(Math.round(tau * 10));
  let cumulative = 0n;
  for (let index = 0; index < pmf.length; index++) {
    const [whole, fraction = ''] = digits[index].split('.');
    cumulative += BigInt(whole + fraction) * 10n ** BigInt(places - fraction.length);
    if (cumulative * 10n >= threshold * scale || index === pmf.length - 1) {
      return {quantile: tau, threshold: pmf[index].value, predicted: Number(cumulative) / Number(scale)};
    }
  }
  throw new Error('Empty daily calibration distribution.');
}

function currentOutcome(asset, forecast) {
  const old = new Set((asset.corrections || []).map(row => row.original_ref.record_id));
  const matches = (asset.outcomes || []).filter(row => !old.has(row.reference.record_id)
    && row.body.mode === 'PROSPECTIVE_RESEARCH' && ['event_id', 'event_snapshot_id', 'player_id', 'team_id', 'opponent_id'].every(key => row.body[key] === forecast[key]));
  if (matches.length > 1) throw new Error('Multiple active daily outcomes for a subject.');
  return matches[0]?.body ?? null;
}

function statusFor(asset, forecast, grade) {
  if (grade) return grade.status;
  return currentOutcome(asset, forecast)?.status || 'PENDING';
}

function revision(forecast) {
  return {evidence_lane: forecast.evidence_lane, model_key: forecast.model_key, model_version: forecast.model_version,
    model_commit: forecast.producer_binding.commit, producer_version: forecast.producer_version,
    history_panel_sha256: forecast.history_panel_sha256, history_panel_cutoff: forecast.history_panel_cutoff,
    conditioning: forecast.conditioning};
}

function populationKeys(asset, forecast) {
  const inputEvent = asset.inputs?.find(row => row.input_id === forecast.input_id)?.event;
  // The admitted daily-v1 contract binds NBA/ESPN IDs in its shared event.
  const league = forecast.league ?? inputEvent?.league ?? 'NBA';
  return {player: JSON.stringify([league, forecast.player_id_namespace ?? inputEvent?.id_namespace ?? 'espn', forecast.player_id]),
    event: JSON.stringify([league, forecast.event_id_namespace ?? inputEvent?.id_namespace ?? 'espn', forecast.event_id])};
}

/** Grade rows must be activeDailyGrades(asset), supplied by the typed channel. */
export function summarizeDailyPerformance(asset, activeGrades, options = {}) {
  const selected = filters(options);
  const result = {filters: selected, valid: selected.valid, groups: [], rows: [],
    counts: {eligible: 0, distinct_players: 0, distinct_events: 0, scored: 0, dnp: 0, pending: 0, excluded_development: 0, excluded_ineligible: 0, excluded_other_lanes: 0}, statuses: {}};
  if (!asset) return result;
  if (!Array.isArray(activeGrades)) throw new Error('Active daily grades are required.');
  result.counts.excluded_development = asset.forecasts.filter(row => row.body.mode === 'DEVELOPMENT_ONLY').length;
  result.counts.excluded_other_lanes = asset.forecasts.filter(row => row.body.mode !== 'DEVELOPMENT_ONLY' && (row.body.mode !== 'PROSPECTIVE_RESEARCH' || row.body.evidence_lane !== 'DAILY_SNAPSHOT_PROSPECTIVE')).length;
  result.counts.excluded_ineligible = asset.forecasts.filter(row => row.body.mode === 'PROSPECTIVE_RESEARCH' && row.body.evidence_lane === 'DAILY_SNAPSHOT_PROSPECTIVE' && !row.admission.eligible).length;
  if (!selected.valid) return result;
  const grades = new Map();
  for (const row of activeGrades) {
    if (grades.has(row.body.forecast_id)) throw new Error('Duplicate active daily grades.');
    grades.set(row.body.forecast_id, row.body);
  }
  const groups = new Map(), population = {players: new Set(), events: new Set()};
  for (const row of asset.forecasts) {
    const f = row.body;
    if (f.mode !== 'PROSPECTIVE_RESEARCH' || f.evidence_lane !== 'DAILY_SNAPSHOT_PROSPECTIVE' || !row.admission.eligible) continue;
    if (!MODELS.includes(f.model_key) || f.conditioning !== 'CONDITIONAL_ON_APPEARANCE') throw new Error('Unsupported daily research semantics.');
    const start = Date.parse(f.event_starts_at), lead = leadMinutes(f), bin = leadBin(lead);
    if (selected.model !== 'ALL' && f.model_key !== selected.model || selected.first !== null && start < selected.first
      || selected.last !== null && start >= selected.last + 86400000 || selected.leadTime !== 'ALL' && bin !== selected.leadTime) continue;
    const grade = grades.get(f.forecast_id), status = statusFor(asset, f, grade), identity = revision(f), key = JSON.stringify(identity);
    if (!groups.has(key)) groups.set(key, {...identity, counts: {eligible: 0, distinct_players: 0, distinct_events: 0, scored: 0, dnp: 0, pending: 0},
      players: new Set(), events: new Set(),
      statuses: {}, dates: {}, lead_times: Object.fromEntries(DAILY_LEAD_BINS.map(value => [value, 0])), categories: new Map()});
    const group = groups.get(key), date = f.event_starts_at.slice(0, 10);
    const subject = populationKeys(asset, f);
    for (const target of [population, group]) {target.players.add(subject.player); target.events.add(subject.event);}
    for (const counts of [result.counts, group.counts]) {
      counts.eligible++;
      if (status === 'SCORED') counts.scored++;
      else if (['DNP', 'DNP_NOT_SCORED'].includes(status)) counts.dnp++;
      else counts.pending++;
    }
    for (const statuses of [result.statuses, group.statuses]) statuses[status] = (statuses[status] || 0) + 1;
    group.dates[date] = (group.dates[date] || 0) + 1;
    group.lead_times[bin]++;
    result.rows.push({forecast: f, grade: grade ?? null, status, lead_minutes: lead});
    if (status !== 'SCORED') continue;
    for (const category of grade.categories) {
      if (selected.category !== 'ALL' && category.code !== selected.category) continue;
      const marginal = f.categories.find(item => item.code === category.code);
      if (!marginal) throw new Error('Daily grade category lacks its original marginal.');
      if (!group.categories.has(category.code)) group.categories.set(category.code, []);
      const observed = finite(category.observed, 'observation'), error = finite(marginal.mean, 'mean') - observed;
      const logLoss = category.log_loss_status === 'ZERO_SUPPORT' ? Infinity : finite(category.log_loss, 'log loss');
      group.categories.get(category.code).push({error, crps: finite(category.crps, 'CRPS'), log_loss: logLoss,
        brier: ['DD', 'TD'].includes(category.code) ? finite(category.brier, 'Brier') : null,
        covered: observed >= marginal.interval80[0] && observed <= marginal.interval80[1],
        calibration: DAILY_CALIBRATION_QUANTILES.map(tau => {const c = calibrationAt(marginal.pmf, tau);return {...c, observed: Number(observed <= c.threshold)};})});
    }
  }
  result.counts.distinct_players = population.players.size;
  result.counts.distinct_events = population.events.size;
  result.groups = [...groups.values()].sort((a, b) => JSON.stringify([a.model_key, a.model_version, a.model_commit, a.producer_version, a.history_panel_sha256, a.history_panel_cutoff, a.conditioning]).localeCompare(JSON.stringify([b.model_key, b.model_version, b.model_commit, b.producer_version, b.history_panel_sha256, b.history_panel_cutoff, b.conditioning]))).map(({players, events, ...group}) => ({...group,
    counts: {...group.counts, distinct_players: players.size, distinct_events: events.size},
    categories: ALL_NBA_CATEGORIES.filter(code => group.categories.has(code)).map(code => {
      const rows = group.categories.get(code), zeros = rows.filter(row => row.log_loss === Infinity).length;
      return {code, n: rows.length, mae: mean(rows.map(row => Math.abs(row.error))), bias: mean(rows.map(row => row.error)),
        mean_crps: mean(rows.map(row => row.crps)), mean_log_loss: zeros ? Infinity : mean(rows.map(row => row.log_loss)),
        zero_support_count: zeros, mean_brier: ['DD', 'TD'].includes(code) ? mean(rows.map(row => row.brier)) : null,
        interval80_coverage: mean(rows.map(row => Number(row.covered))), calibration: DAILY_CALIBRATION_QUANTILES.map((tau, index) => ({quantile: tau,
          n: rows.length, mean_predicted_cdf: mean(rows.map(row => row.calibration[index].predicted)),
          observed_fraction: mean(rows.map(row => row.calibration[index].observed))}))};
    })}));
  return result;
}

function controls(options) {
  const select = (label, key, values, value) => `<label class="filter-label">${label}<select data-filter="${key}">${values.map(([key, text]) => `<option value="${escaped(key)}"${key === value ? ' selected' : ''}>${escaped(text)}</option>`).join('')}</select></label>`;
  const date = (label, key, value) => `<label class="filter-label">${label}<input type="date" data-filter="${key}" value="${escaped(value)}" style="width:100%;min-width:0;max-width:100%;box-sizing:border-box"></label>`;
  return `<div class="filter-grid daily-performance-filters">${select('Daily model', 'dailyModel', [['ALL', 'All models'], ['R0', 'R0'], ['K0', 'K0']], options.model)}${select('Category', 'category', [['ALL', 'All categories'], ...ALL_NBA_CATEGORIES.map(code => [code, code])], options.category)}${select('Issue lead time', 'dailyLead', [['ALL', 'All lead times'], ['UNDER_90', 'Under 90 minutes'], ['90_TO_180', '90–under 180 minutes'], ['180_PLUS', '180 minutes or more']], options.leadTime)}${date('Event date from · UTC', 'dailyDateFrom', options.dateFrom)}${date('Event date to · UTC', 'dailyDateTo', options.dateTo)}</div>`;
}

function renderGroup(group) {
  const metrics = group.categories.length ? `<div class="table-wrap"><table><thead><tr><th scope="col">Category</th><th scope="col">Scored N</th><th scope="col">MAE</th><th scope="col">Bias</th><th scope="col">CRPS / RPS</th><th scope="col">Log loss</th><th scope="col">Brier</th><th scope="col">80% coverage</th></tr></thead><tbody>${group.categories.map(c => `<tr><th scope="row">${escaped(c.code)}</th><td>${c.n}</td><td>${number(c.mae)}</td><td>${number(c.bias)}</td><td>${number(c.mean_crps)}</td><td>${c.zero_support_count ? `∞ · ${c.zero_support_count} zero-support` : number(c.mean_log_loss)}</td><td>${c.mean_brier === null ? 'Not binary' : number(c.mean_brier)}</td><td>${percent(c.interval80_coverage)}</td></tr>`).join('')}</tbody></table></div><details><summary>CDF calibration at fixed forecast quantiles</summary><p>Discrete ties are included: observed frequencies are compared with each forecast’s CDF at its 10%, 50% and 90% quantiles, not with the nominal quantile itself.</p><div class="table-wrap"><table><thead><tr><th scope="col">Category</th><th scope="col">Quantile</th><th scope="col">N</th><th scope="col">Mean forecast CDF(q)</th><th scope="col">Observed outcome ≤ q</th></tr></thead><tbody>${group.categories.flatMap(c => c.calibration.map(row => `<tr><th scope="row">${escaped(c.code)}</th><td>${percent(row.quantile)}</td><td>${row.n}</td><td>${percent(row.mean_predicted_cdf)}</td><td>${percent(row.observed_fraction)}</td></tr>`)).join('')}</tbody></table></div></details>` : '<p>No scored category outcomes in this group. DNP and unresolved records do not enter numerical summaries.</p>';
  return `<section class="daily-performance-group" data-model-key="${escaped(group.model_key)}"><h3>${escaped(group.model_key)} · Daily-snapshot prospective research</h3><p>${group.counts.eligible} eligible bundles · ${group.counts.distinct_players} distinct players · ${group.counts.distinct_events} distinct events · ${group.counts.scored} scored bundles · ${group.counts.dnp} DNP · ${group.counts.pending} pending or unresolved. UTC event-date counts: ${Object.entries(group.dates).sort().map(([date, count]) => `${escaped(date)}: ${count}`).join('; ')}. Issue lead-time counts: under 90 minutes ${group.lead_times.UNDER_90}, 90–under 180 ${group.lead_times['90_TO_180']}, 180+ ${group.lead_times['180_PLUS']}.</p><details class="forecast-details forecast-provenance"><summary>Exact model, history and participation identity</summary><p>${escaped(group.model_version)} · ${escaped(group.producer_version)} · ${escaped(group.evidence_lane)}.</p><p class="break-code">Producer commit ${escaped(group.model_commit)}; historical panel ${escaped(group.history_panel_sha256)}; cutoff ${escaped(group.history_panel_cutoff)}. ${escaped(group.conditioning)}.</p></details>${metrics}</section>`;
}

export function renderDailyPerformance(asset, activeGrades, options = {}) {
  const summary = summarizeDailyPerformance(asset, activeGrades, options), count = summary.counts;
  let content = controls(summary.filters);
  if (!summary.valid) content += '<p class="notice warning" role="status">Choose valid daily research filters. The UTC start date must not follow the end date.</p>';
  else {
    content += `<p>${count.eligible} eligible prospective research bundles in these filters · ${count.distinct_players} distinct players · ${count.distinct_events} distinct events · ${count.scored} scored bundles · ${count.dnp} DNP · ${count.pending} pending or unresolved. ${count.excluded_development} development bundles, ${count.excluded_ineligible} ineligible originals and ${count.excluded_other_lanes} originals from other evidence lanes are excluded from these summaries.</p>`;
    if (!activeGrades.length) content += '<p>No statistical grades are published for this daily-source cycle. Upcoming forecasts and development previews do not establish accuracy or qualification.</p>';
    else if (!summary.groups.length) content += '<p>No eligible daily research records match these filters.</p>';
    content += summary.groups.map(renderGroup).join('');
    if (summary.rows.length) content += `<details class="grade-receipts"><summary>Selected forecast and grade identities</summary><ul class="performance-targets">${summary.rows.map(row => `<li><div><strong>${escaped(row.forecast.player_label)}</strong><span>${escaped(row.forecast.matchup)} · ${escaped(row.forecast.event_starts_at)}</span><span>${escaped(row.forecast.model_key)} · ${escaped(row.status)}${row.grade ? ` · graded ${escaped(row.grade.graded_at)}` : ''}</span><span class="break-code">Player ${escaped(row.forecast.player_id)} · event ${escaped(row.forecast.event_id)} · forecast ${escaped(row.forecast.forecast_id)}</span></div></li>`).join('')}</ul></details>`;
  }
  return `<section class="panel sdv-daily-research"><h2>Daily-snapshot research performance</h2>${content}<p>Descriptive research only, conditional on the player appearing. Bias is forecast mean minus observed production; MAE uses that same mean. DNP is not zero. Scores retain category-specific units; models, exact revisions and evidence lanes are kept separate. Paired model records are not independent trials. Small samples, interval coverage and calibration summaries do not establish confirmatory accuracy, a winning model, betting qualification or financial settlement.</p></section>`;
}

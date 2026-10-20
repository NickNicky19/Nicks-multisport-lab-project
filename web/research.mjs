// Typed price-independent research records. These checks confer no product admission.
export const ALL_NBA_CATEGORIES = ['PTS', 'PRA', 'REB', '3PM', 'AST', 'RA', 'PR', 'TOV', 'TD', 'DD', 'BLK', 'STL', 'BLK+STL', 'PA'];
export const NBA_UNITS = {PTS: 'points', PRA: 'stat_sum', REB: 'rebounds', '3PM': 'made_three_point_field_goals', AST: 'assists', RA: 'stat_sum', PR: 'stat_sum', TOV: 'turnovers', TD: 'indicator_0_or_1', DD: 'indicator_0_or_1', BLK: 'blocks', STL: 'steals', 'BLK+STL': 'stat_sum', PA: 'stat_sum'};
const SHA = /^[a-f0-9]{64}$/;
const isText = value => typeof value === 'string' && value.trim() === value && value.length > 0 && value.length <= 200;
const fields = (value, expected) => value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).sort().join(',') === [...expected].sort().join(',');
const fail = message => {throw new Error(message);};

/** Preserve microsecond ordering rather than silently rounding to browser milliseconds. */
export function utcMicros(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$/.test(value)) return fail('A microsecond UTC clock is required.');
  const seconds = value.slice(0, 19) + 'Z';
  const milliseconds = Date.parse(seconds);
  if (!Number.isFinite(milliseconds) || new Date(milliseconds).toISOString().slice(0, 19) !== value.slice(0, 19)) return fail('Invalid calendar clock.');
  return BigInt(milliseconds) * 1000n + BigInt(value.slice(20, 26));
}

function decimal(value, label) {
  if (typeof value !== 'string' || value.length > 128 || !/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value) || !Number.isFinite(Number(value))) return fail(`Invalid ${label} decimal string.`);
  return Number(value);
}

function quantile(pmf, threshold) {
  let sum = 0;
  for (const item of pmf) {sum += Number(item.probability); if (sum >= threshold) return item.value;}
  return pmf.at(-1).value;
}

export function summarizePmf(pmf) {
  const mean = pmf.reduce((sum, item) => sum + item.value * Number(item.probability), 0);
  const upper95 = quantile(pmf, 0.975);
  return {mean, interval80: [quantile(pmf, 0.1), quantile(pmf, 0.9)], zero: Number(pmf.find(item => item.value === 0)?.probability || 0), support: [pmf[0].value, pmf.at(-1).value], upper95, tail: pmf.filter(item => item.value > upper95).reduce((sum, item) => sum + Number(item.probability), 0)};
}

function category(record) {
  if (!fields(record, ['code', 'units', 'pmf', 'mean', 'interval80']) || !ALL_NBA_CATEGORIES.includes(record.code) || record.units !== NBA_UNITS[record.code] || !Array.isArray(record.pmf) || !record.pmf.length || record.pmf.length > 1025) return fail('Invalid typed category.');
  let previous = -1, mass = 0;
  for (const item of record.pmf) {
    if (!fields(item, ['value', 'probability']) || !Number.isSafeInteger(item.value) || item.value < 0 || item.value > 1024 || item.value <= previous || (['DD', 'TD'].includes(record.code) && item.value > 1)) return fail('PMF support must be ordered, unique nonnegative integers.');
    const probability = decimal(item.probability, 'probability');
    if (probability <= 0 || probability > 1) return fail('Invalid PMF probability.');
    mass += probability; previous = item.value;
  }
  if (Math.abs(mass - 1) > 1e-12) return fail('PMF probability mass must sum to one.');
  const summary = summarizePmf(record.pmf), mean = decimal(record.mean, 'mean');
  if (Math.abs(mean - summary.mean) > 1e-10) return fail('Supplied mean does not match its PMF.');
  if (!Array.isArray(record.interval80) || record.interval80.length !== 2 || record.interval80.some((value, i) => !Number.isSafeInteger(value) || value !== summary.interval80[i])) return fail('Supplied interval does not match its PMF.');
  return record;
}

export function validateResearchEvent(record) {
  if (!fields(record, ['schema_version', 'id_namespace', 'league', 'event_id', 'starts_at', 'status', 'team_ids', 'label', 'schedule_basis']) || record.schema_version !== 'nba-research-event-v1' || record.id_namespace !== 'espn' || record.league !== 'NBA' || !isText(record.event_id) || !isText(record.label) || !['FINAL', 'SCHEDULED'].includes(record.status) || !['RETROSPECTIVE_ARCHIVE', 'OBSERVED_CAPTURE'].includes(record.schedule_basis) || !Array.isArray(record.team_ids) || record.team_ids.length !== 2 || record.team_ids.some(value => !isText(value)) || record.team_ids[0] === record.team_ids[1]) return fail('Invalid research event identity.');
  utcMicros(record.starts_at);
  if (!(record.status === 'FINAL' && record.schedule_basis === 'RETROSPECTIVE_ARCHIVE' || record.status === 'SCHEDULED' && record.schedule_basis === 'OBSERVED_CAPTURE')) return fail('Event status and schedule provenance disagree.');
  return record;
}

export function validateResearchForecast(record, event, generatedAt) {
  const names = ['schema_version', 'forecast_id', 'id_namespace', 'league', 'event_id', 'player_id', 'player_label', 'team_id', 'opponent_id', 'event_starts_at', 'period', 'extra_time_policy', 'model_version', 'model_commit', 'model_code_sha256', 'input_sha256', 'trained_through', 'cutoff_at', 'history_freeze', 'issued_at', 'conditioning', 'evidence_lane', 'availability_basis', 'input_capture_ids', 'joint_method', 'joint_sha256', 'tail_policy', 'categories', 'qualification'];
  if (!fields(record, names) || record.schema_version !== 'nba-research-forecast-v1' || record.id_namespace !== 'espn' || record.league !== 'NBA' || !['event_id', 'player_id', 'player_label', 'team_id', 'opponent_id', 'model_version'].every(key => isText(record[key])) || !['forecast_id', 'model_code_sha256', 'input_sha256', 'joint_sha256'].every(key => SHA.test(record[key]))) return fail('Invalid typed forecast identity.');
  if (!event || event.event_id !== record.event_id || event.league !== record.league || event.id_namespace !== record.id_namespace || record.event_starts_at !== event.starts_at || record.team_id === record.opponent_id || !event.team_ids.includes(record.team_id) || !event.team_ids.includes(record.opponent_id)) return fail('Forecast references an inconsistent event.');
  if (!/^[a-f0-9]{40}$/.test(record.model_commit) || record.period !== 'full_game' || record.extra_time_policy !== 'includes_overtime' || record.conditioning !== 'CONDITIONAL_ON_APPEARANCE' || record.joint_method !== 'COMPLETE_LINE_EMPIRICAL' || record.tail_policy !== 'FINITE_EMPIRICAL_SUPPORT_NO_SMOOTHING' || record.qualification !== 'UNAVAILABLE') return fail('Unsupported forecast period, conditioning, method or qualification.');
  const start = utcMicros(record.event_starts_at), cutoff = utcMicros(record.cutoff_at), freeze = utcMicros(record.history_freeze), issued = utcMicros(record.issued_at), trained = utcMicros(record.trained_through);
  const generated = utcMicros(generatedAt);
  if (cutoff !== start - 90n * 60n * 1000000n || record.history_freeze !== record.cutoff_at.slice(0, 10) + 'T00:00:00.000000Z' || trained > freeze || freeze > cutoff || cutoff > issued || issued > generated) return fail('Forecast clocks violate the common cutoff or issuance order.');
  if (!Array.isArray(record.input_capture_ids) || record.input_capture_ids.some(value => !SHA.test(value)) || new Set(record.input_capture_ids).size !== record.input_capture_ids.length) return fail('Invalid input capture identities.');
  if (record.evidence_lane === 'RECONSTRUCTED_RESEARCH') {
    if (record.availability_basis !== 'RECONSTRUCTED_BOUND' || record.input_capture_ids.length || issued < start || event.status !== 'FINAL' || event.schedule_basis !== 'RETROSPECTIVE_ARCHIVE') return fail('Invalid historical reconstruction semantics.');
  } else if (record.evidence_lane === 'REAL_TIME_CAPTURED') {
    if (record.availability_basis !== 'OBSERVED_INPUT_CAPTURE' || !record.input_capture_ids.length || issued >= start || event.status !== 'SCHEDULED' || event.schedule_basis !== 'OBSERVED_CAPTURE') return fail('Invalid prospective capture semantics.');
  } else return fail('Unsupported research evidence lane.');
  if (!Array.isArray(record.categories) || record.categories.length !== ALL_NBA_CATEGORIES.length || new Set(record.categories.map(item => item.code)).size !== ALL_NBA_CATEGORIES.length) return fail('All fourteen NBA category outputs are required.');
  record.categories.forEach(category);
  const means = Object.fromEntries(record.categories.map(item => [item.code, Number(item.mean)]));
  for (const [total, parts] of [['PRA', ['PTS', 'REB', 'AST']], ['PR', ['PTS', 'REB']], ['RA', ['REB', 'AST']], ['PA', ['PTS', 'AST']], ['BLK+STL', ['BLK', 'STL']]]) {
    if (Math.abs(means[total] - parts.reduce((sum, code) => sum + means[code], 0)) > 1e-10) return fail('Derived category means are inconsistent.');
  }
  if (means.TD > means.DD + 1e-12 || means.PTS + 1e-10 < 3 * means['3PM']) return fail('Scoring or achievement mean coherence is invalid.');
  const tails = ['PTS', 'REB', 'AST', 'STL', 'BLK'].map(code => record.categories.find(item => item.code === code).pmf.filter(item => item.value >= 10).reduce((sum, item) => sum + Number(item.probability), 0)).sort((a, b) => b - a);
  for (const [code, count] of [['DD', 2], ['TD', 3]]) {
    let lower = 0, upper = 1;
    for (let m = count; m <= 5; m++) lower = Math.max(lower, (tails.slice(0, m).reduce((sum, value) => sum + value, 0) - (count - 1)) / (m - count + 1));
    for (let j = 0; j < count; j++) upper = Math.min(upper, tails.slice(j).reduce((sum, value) => sum + value, 0) / (count - j));
    if (means[code] < lower - 1e-12 || means[code] > upper + 1e-12) return fail('Achievement probability conflicts with necessary component threshold bounds.');
  }
  return record;
}

/** History includes reconstructions and captured forecasts whose events have started.
 * Passing a start clock alone does not establish a completed event or an outcome.
 */
export function isHistoryForecast(row, now = Date.now()) {
  return row.evidence_lane === 'RECONSTRUCTED_RESEARCH' || row.evidence_lane === 'REAL_TIME_CAPTURED' && Date.parse(row.event_starts_at) <= now;
}

/** Historical reconstructions never enter the upcoming research view. */
export function filterResearchForecasts(rows, filters, now = Date.now()) {
  return rows.filter(row => {
    const historical = isHistoryForecast(row, now);
    if (filters.view === 'history' ? !historical : row.evidence_lane !== 'REAL_TIME_CAPTURED' || !Number.isFinite(Date.parse(row.event_starts_at)) || historical) return false;
    if (filters.view !== 'history' && (filters.window === '24h' && Date.parse(row.event_starts_at) > now + 86400000 || filters.window === '7d' && Date.parse(row.event_starts_at) > now + 7 * 86400000)) return false;
    return true;
  }).flatMap(forecast => forecast.categories.filter(item => filters.category === 'ALL' || item.code === filters.category).map(item => ({forecast, category: item})));
}

/** Summarize validated grade records within one lane and exact model identity.
 * Counts are grade records, never independent trials or product qualification.
 */
export function groupForecastGrades(grades, forecasts) {
  const identities = ['league', 'evidence_lane', 'model_version', 'model_commit', 'model_code_sha256', 'conditioning', 'period', 'extra_time_policy'];
  const byForecast = new Map(forecasts.map(forecast => [forecast.forecast_id, forecast]));
  const groups = new Map();
  for (const grade of grades) {
    const forecast = byForecast.get(grade.forecast_id);
    if (!forecast || identities.some(key => !isText(forecast[key])) || ['league', 'evidence_lane', 'event_id', 'player_id'].some(key => grade[key] !== forecast[key])) return fail('A grade lacks its matching forecast/model identity.');
    const key = JSON.stringify(identities.map(field => forecast[field]));
    if (!groups.has(key)) groups.set(key, {...Object.fromEntries(identities.map(field => [field, forecast[field]])), grade_count: 0, scored_count: 0, dnp_count: 0, unresolved_count: 0, rows: new Map()});
    const group = groups.get(key);
    group.grade_count++;
    if (grade.status === 'DNP_NOT_SCORED') {group.dnp_count++; continue;}
    if (grade.status === 'UNRESOLVED') {group.unresolved_count++; continue;}
    if (grade.status !== 'SCORED') return fail('Unsupported grade status in a research summary.');
    group.scored_count++;
    for (const category of grade.categories) {
      if (!group.rows.has(category.code)) group.rows.set(category.code, []);
      group.rows.get(category.code).push(category);
    }
  }
  return [...groups.values()].map(({rows, ...group}) => ({...group, categories: [...rows].map(([code, values]) => {
    const missingSupport = values.filter(row => row.log_loss_status === 'ZERO_SUPPORT').length;
    return {code, grade_count: values.length, mean_crps: values.reduce((sum, row) => sum + Number(row.crps), 0) / values.length,
      mean_log_loss: missingSupport ? null : values.reduce((sum, row) => sum + Number(row.log_loss), 0) / values.length,
      zero_support_count: missingSupport, mean_brier: ['DD', 'TD'].includes(code) ? values.reduce((sum, row) => sum + Number(row.brier), 0) / values.length : null};
  })}));
}

export function validateResearchGrade(record, forecast, generatedAt) {
  const names = ['schema_version', 'grade_id', 'forecast_id', 'outcome_id', 'id_namespace', 'league', 'event_id', 'player_id', 'graded_at', 'status', 'evidence_lane', 'categories', 'financial_settlement'];
  if (!fields(record, names) || record.schema_version !== 'nba-forecast-grade-v1' || !SHA.test(record.grade_id) || !SHA.test(record.outcome_id) || !forecast || record.forecast_id !== forecast.forecast_id || record.id_namespace !== forecast.id_namespace || record.league !== forecast.league || record.event_id !== forecast.event_id || record.player_id !== forecast.player_id || record.evidence_lane !== forecast.evidence_lane || record.financial_settlement !== 'NOT_EVALUATED' || !['SCORED', 'DNP_NOT_SCORED', 'UNRESOLVED'].includes(record.status)) return fail('Invalid typed forecast grade reference or settlement claim.');
  const graded = utcMicros(record.graded_at);
  if (graded < utcMicros(forecast.issued_at) || record.status !== 'UNRESOLVED' && graded < utcMicros(forecast.event_starts_at) || graded > utcMicros(generatedAt)) return fail('Invalid forecast grading clock.');
  if (!Array.isArray(record.categories)) return fail('Invalid forecast grade categories.');
  if (record.status !== 'SCORED') {
    if (record.categories.length) return fail('DNP or unresolved outcomes cannot be scored as zero.');
    return record;
  }
  if (record.categories.length !== ALL_NBA_CATEGORIES.length || new Set(record.categories.map(item => item.code)).size !== ALL_NBA_CATEGORIES.length) return fail('Scored grades require all fourteen categories.');
  for (const item of record.categories) {
    if (!fields(item, ['code', 'observed', 'crps', 'log_loss', 'log_loss_status', 'brier']) || !ALL_NBA_CATEGORIES.includes(item.code) || !Number.isSafeInteger(item.observed) || item.observed < 0 || ['DD', 'TD'].includes(item.code) && item.observed > 1) return fail('Invalid category grade.');
    const pmf = forecast.categories.find(category => category.code === item.code).pmf;
    const observedMass = Number(pmf.find(atom => atom.value === item.observed)?.probability || 0);
    let absolute = 0, halfPair = 0, cumulative = 0, weighted = 0;
    for (const atom of pmf) {
      const probability = Number(atom.probability);
      absolute += probability * Math.abs(atom.value - item.observed);
      halfPair += probability * (atom.value * cumulative - weighted);
      cumulative += probability; weighted += probability * atom.value;
    }
    if (Math.abs(decimal(item.crps, 'CRPS') - Math.max(0, absolute - halfPair)) > 1e-9) return fail('Grade CRPS does not match its forecast PMF.');
    if (observedMass === 0 ? item.log_loss !== null || item.log_loss_status !== 'ZERO_SUPPORT' : item.log_loss_status !== 'FINITE' || item.log_loss === null || Math.abs(decimal(item.log_loss, 'log loss') + Math.log(observedMass)) > 1e-9) return fail('Invalid zero-support or finite log loss.');
    if (['DD', 'TD'].includes(item.code)) {
      const positive = Number(pmf.find(atom => atom.value === 1)?.probability || 0);
      if (item.brier === null || Math.abs(decimal(item.brier, 'Brier score') - (positive - item.observed) ** 2) > 1e-9) return fail('Invalid binary Brier score.');
    } else if (item.brier !== null) return fail('A count grade cannot inherit a binary score.');
  }
  return record;
}

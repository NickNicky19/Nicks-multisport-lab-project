import {createHash} from 'node:crypto';
import {REQUIRED_MARKETS} from '../snapshot.mjs';
import {ALL_NBA_CATEGORIES, NBA_UNITS} from '../research.mjs';

export const canonical = value => value && typeof value === 'object' ? Array.isArray(value) ? `[${value.map(canonical).join(',')}]` : `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}` : JSON.stringify(value);
export const hash = value => createHash('sha256').update(typeof value === 'string' ? value : canonical(value)).digest('hex');
export const clock = '2000-01-01T00:00:00.000000Z';

export function fixture() {
  const sport = {schema_version: 1, league: 'NBA', generated_at: clock, evidence_lane: 'RECONSTRUCTED_RESEARCH', status: 'RESEARCH_ONLY', coverage: {forecast: 'UNVALIDATED', quotes: 'UNVERIFIED', settlement: 'UNVERIFIED', paper: 'NO_ACTION'}, markets: REQUIRED_MARKETS.map(code => ({code, name: code, requested: true, forecast_status: 'UNVALIDATED', quote_status: 'UNVERIFIED', settlement_status: 'UNVERIFIED'})), sources: [{id: 'test-source', name: 'Synthetic source fixture', status: 'UNVERIFIED', detail: 'Software test only.', observed_at: null}], events: [], offers: [], forecasts: [], candidates: [], tickets: [], performance: []};
  const sha256 = hash(sport);
  const reference = {league: 'NBA', path: `nba.${sha256}.json`, sha256, generated_at: clock, status: 'RESEARCH_ONLY', retained: false, error: null};
  const manifest = {schema_version: 1, build_commit: 'a'.repeat(40), published_at: clock, publication_status: 'RESEARCH_ONLY', supported_sports: ['NBA'], sports: [reference], errors: {}};
  manifest.snapshot_id = hash(manifest);
  return {sport, reference, manifest};
}

export function reseal(sport, manifest = fixture().manifest) {
  const sha256 = hash(sport);
  const reference = {league: sport.league, path: `${sport.league.toLowerCase()}.${sha256}.json`, sha256, generated_at: sport.generated_at, status: 'RESEARCH_ONLY', retained: false, error: null};
  const next = {...manifest, schema_version: sport.schema_version, sports: [reference]};
  delete next.snapshot_id; next.snapshot_id = hash(next);
  return {sport, manifest: next, reference};
}

export function typedFixture() {
  const {sport} = fixture();
  sport.schema_version = 2;
  sport.future_availability = {status: 'UNAVAILABLE', reasons: ['Synthetic fixture: no future capture receipts.']};
  sport.markets.push({code: 'PA', name: 'Optional Points + Assists', requested: false, forecast_status: 'UNVALIDATED', quote_status: 'UNVERIFIED', settlement_status: 'UNVERIFIED'});
  const event = {schema_version: 'nba-research-event-v1', id_namespace: 'espn', league: 'NBA', event_id: 'test-event', starts_at: '1999-12-01T20:00:00.000000Z', status: 'FINAL', team_ids: ['test-team', 'test-opponent'], label: 'Synthetic fixture event', schedule_basis: 'RETROSPECTIVE_ARCHIVE'};
  const values = {PTS: 12, PRA: 19, REB: 4, '3PM': 2, AST: 3, RA: 7, PR: 16, TOV: 1, TD: 0, DD: 0, BLK: 1, STL: 1, 'BLK+STL': 2, PA: 15};
  const forecast = {schema_version: 'nba-research-forecast-v1', id_namespace: 'espn', league: 'NBA', event_id: event.event_id, player_id: 'test-player', player_label: 'Synthetic fixture player', team_id: event.team_ids[0], opponent_id: event.team_ids[1], event_starts_at: event.starts_at, period: 'full_game', extra_time_policy: 'includes_overtime', model_version: 'synthetic-test-only', model_commit: 'a'.repeat(40), model_code_sha256: 'b'.repeat(64), input_sha256: 'c'.repeat(64), trained_through: '1999-11-30T23:00:00.000000Z', cutoff_at: '1999-12-01T18:30:00.000000Z', history_freeze: '1999-12-01T00:00:00.000000Z', issued_at: clock, conditioning: 'CONDITIONAL_ON_APPEARANCE', evidence_lane: 'RECONSTRUCTED_RESEARCH', availability_basis: 'RECONSTRUCTED_BOUND', input_capture_ids: [], joint_method: 'COMPLETE_LINE_EMPIRICAL', joint_sha256: 'd'.repeat(64), tail_policy: 'FINITE_EMPIRICAL_SUPPORT_NO_SMOOTHING', categories: ALL_NBA_CATEGORIES.map(code => ({code, units: NBA_UNITS[code], pmf: values[code] ? [{value: 0, probability: '0.5'}, {value: values[code], probability: '0.5'}] : [{value: 0, probability: '1'}], mean: String(values[code] / 2), interval80: [0, values[code]]})), qualification: 'UNAVAILABLE'};
  forecast.forecast_id = hash(forecast);
  const grade = {schema_version: 'nba-forecast-grade-v1', forecast_id: forecast.forecast_id, outcome_id: 'e'.repeat(64), id_namespace: 'espn', league: 'NBA', event_id: event.event_id, player_id: forecast.player_id, graded_at: clock, status: 'SCORED', evidence_lane: 'RECONSTRUCTED_RESEARCH', categories: ALL_NBA_CATEGORIES.map(code => ({code, observed: 0, crps: String(values[code] / 4), log_loss: values[code] ? String(Math.log(2)) : '0', log_loss_status: 'FINITE', brier: ['DD', 'TD'].includes(code) ? '0' : null})), financial_settlement: 'NOT_EVALUATED'};
  grade.grade_id = hash(grade);
  sport.events = [event]; sport.forecasts = [forecast]; sport.performance = [grade];
  return reseal(sport);
}

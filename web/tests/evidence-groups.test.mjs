import test from 'node:test';
import assert from 'node:assert/strict';
import {filterResearchForecasts, groupForecastGrades, isHistoryForecast} from '../research.mjs';
import {filterRowsByScope} from '../scope.mjs';
import {validateSport} from '../snapshot.mjs';
import {mixedEvidenceFixture, typedFixture} from './fixtures.mjs';

test('descriptive grades keep evidence lanes and model commits separate', () => {
  const {sport, reference} = mixedEvidenceFixture();
  validateSport(sport, reference);
  const before = structuredClone(sport);
  const groups = groupForecastGrades(sport.performance, sport.forecasts);
  assert.equal(groups.length, 3);
  const reconstructed = groups.find(group => group.evidence_lane === 'RECONSTRUCTED_RESEARCH');
  const captured = groups.find(group => group.evidence_lane === 'REAL_TIME_CAPTURED' && group.model_commit === 'a'.repeat(40));
  const revision = groups.find(group => group.model_commit === 'f'.repeat(40));
  assert.equal(reconstructed.scored_count, 2);
  assert.equal(reconstructed.categories.find(row => row.code === 'PTS').mean_crps, 3);
  assert.equal(captured.scored_count, 1);
  assert.equal(captured.categories.find(row => row.code === 'PTS').mean_crps, 4);
  assert.equal(captured.categories.find(row => row.code === 'PTS').mean_log_loss, null);
  assert.equal(captured.categories.find(row => row.code === 'PTS').zero_support_count, 1);
  assert.equal(reconstructed.categories.find(row => row.code === 'PTS').zero_support_count, 0);
  assert.equal(revision.categories.find(row => row.code === 'PTS').zero_support_count, 0);
  assert.deepEqual(sport, before);
});

test('version, full commit, code hash and target semantics each separate a cohort', () => {
  const {sport} = typedFixture();
  for (const changed of [{model_version: 'synthetic-other-version'}, {model_commit: 'f'.repeat(40)}, {model_code_sha256: 'f'.repeat(64)}, {conditioning: 'synthetic-other-conditioning'}, {period: 'synthetic-other-period'}, {extra_time_policy: 'synthetic-other-overtime'}, {league: 'WNBA'}]) {
    // Direct grouping fixtures exercise future identity distinctions, not admission.
    const other = {...sport.forecasts[0], ...changed, forecast_id: 'f'.repeat(64), player_id: 'synthetic-peer'};
    const grade = {...sport.performance[0], forecast_id: other.forecast_id, grade_id: 'f'.repeat(64), player_id: other.player_id, league: other.league};
    assert.equal(groupForecastGrades([...sport.performance, grade], [...sport.forecasts, other]).length, 2);
  }
});

test('DNP and unresolved grades retain counts but never become scored zeros', () => {
  const {sport} = typedFixture();
  const extras = ['DNP_NOT_SCORED', 'UNRESOLVED'].map((status, i) => ({...sport.performance[0], grade_id: String(i).repeat(64), status, categories: []}));
  const [group] = groupForecastGrades([...sport.performance, ...extras], sport.forecasts);
  assert.equal(group.grade_count, 3); assert.equal(group.scored_count, 1);
  assert.equal(group.dnp_count, 1); assert.equal(group.unresolved_count, 1);
  assert.equal(group.categories.find(row => row.code === 'PTS').grade_count, 1);
  assert.equal(group.categories.find(row => row.code === 'PTS').mean_crps, 3);
  const [unscored] = groupForecastGrades(extras, sport.forecasts);
  assert.deepEqual(unscored.categories, []);
});

test('missing or mismatched forecast references cannot enter a summary', () => {
  const {sport} = typedFixture();
  assert.throws(() => groupForecastGrades(sport.performance, []), /matching forecast/);
  assert.throws(() => groupForecastGrades([{...sport.performance[0], evidence_lane: 'REAL_TIME_CAPTURED'}], sport.forecasts), /matching forecast/);
});

test('History includes past captures without classifying them as reconstruction or completion', () => {
  const {sport} = mixedEvidenceFixture();
  const now = Date.parse('2000-01-02T19:00:00.000000Z');
  const captured = sport.forecasts.find(row => row.evidence_lane === 'REAL_TIME_CAPTURED');
  const future = {...captured, forecast_id: 'f'.repeat(64), event_starts_at: '2000-01-02T20:00:00.000000Z', cutoff_at: '2000-01-02T18:30:00.000000Z', history_freeze: '2000-01-02T00:00:00.000000Z', issued_at: '2000-01-02T18:45:00.000000Z'};
  const rows = [...sport.forecasts, future];
  const history = filterResearchForecasts(rows, {view: 'history', category: 'REB', window: '24h'}, now);
  const upcoming = filterResearchForecasts(rows, {view: 'upcoming', category: 'REB', window: '24h'}, now);
  assert.equal(history.length, 4); assert.equal(upcoming.length, 1);
  assert.deepEqual(new Set(history.map(row => row.forecast.evidence_lane)), new Set(['RECONSTRUCTED_RESEARCH', 'REAL_TIME_CAPTURED']));
  assert.equal(upcoming[0].forecast.forecast_id, future.forecast_id);
  assert.equal(isHistoryForecast(future, now), false);
  assert.equal(isHistoryForecast(future, Date.parse(future.event_starts_at)), true);
  assert.equal(captured.evidence_lane, 'REAL_TIME_CAPTURED');
  assert.equal(sport.events.find(row => row.event_id === captured.event_id).status, 'SCHEDULED');
});

test('sport scope precedes mixed-lane History and grade grouping', () => {
  const {sport} = mixedEvidenceFixture();
  const scope = {mode: 'SELECTED', sports: ['WNBA']};
  assert.deepEqual(filterResearchForecasts(filterRowsByScope(sport.forecasts, scope, ['NBA', 'WNBA']), {view: 'history', category: 'ALL', window: 'upcoming'}), []);
  assert.deepEqual(groupForecastGrades(filterRowsByScope(sport.performance, scope, ['NBA', 'WNBA']), sport.forecasts), []);
});

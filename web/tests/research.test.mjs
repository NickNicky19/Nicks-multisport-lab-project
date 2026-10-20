import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {validateSport, loadSnapshot} from '../snapshot.mjs';
import {summarizePmf, utcMicros, filterResearchForecasts} from '../research.mjs';
import {fixture, typedFixture, reseal, canonical, hash} from './fixtures.mjs';

test('v2 displays coherent all-fourteen price-independent research with no quotes', async () => {
  const {sport, reference, manifest} = typedFixture();
  assert.equal(validateSport(sport, reference), sport);
  const result = await loadSnapshot(async url => new Response(canonical(url.endsWith('manifest.json') ? manifest : sport)), webcrypto);
  assert.equal(result.sports[0].forecasts[0].categories.length, 14);
  assert.equal(result.sports[0].offers.length, 0);
  assert.equal(result.sports[0].performance[0].financial_settlement, 'NOT_EVALUATED');
});

test('typed PMFs reject bad mass, nonfinite/number probabilities, support and inconsistent summaries', () => {
  for (const change of [record => record.pmf[0].probability = '0.6', record => record.pmf[0].probability = NaN, record => record.pmf[0].probability = 0.5, record => record.pmf[0].probability = '1e-1', record => record.pmf[0].probability = '0', record => record.pmf[0].value = -1, record => record.pmf[1].value = 1025, record => record.pmf.reverse(), record => record.mean = '100', record => record.interval80 = [0, 0]]) {
    const {sport, reference} = typedFixture(); change(sport.forecasts[0].categories[0]);
    assert.throws(() => validateSport(sport, reference));
  }
});

test('identity, common cutoff and unsupported qualification are enforced', () => {
  for (const change of [{event_id: 'absent'}, {player_id: ''}, {forecast_id: 'short'}, {model_commit: 'short'}, {qualification: 'QUALIFIED'}, {period: 'first_half'}, {extra_time_policy: 'excludes_overtime'}, {conditioning: 'UNCONDITIONAL'}, {cutoff_at: '1999-12-01T18:30:00.000001Z'}, {trained_through: '1999-12-01T00:00:00.000001Z'}, {issued_at: '1999-12-01T19:59:59.999999Z'}, {event_starts_at: '1999-12-01T20:00:00.000001Z'}]) {
    const {sport, reference} = typedFixture(); Object.assign(sport.forecasts[0], change); assert.throws(() => validateSport(sport, reference));
  }
  assert.equal(utcMicros('1999-12-01T18:30:00.000001Z') - utcMicros('1999-12-01T18:30:00.000000Z'), 1n);
  assert.throws(() => utcMicros('2000-02-30T00:00:00.000000Z'));
});

test('category and event identity errors cannot borrow another category or sport admission', () => {
  for (const change of [sport => sport.forecasts[0].categories.pop(), sport => sport.forecasts[0].categories[0].units = 'rebounds', sport => sport.forecasts[0].categories[0].code = 'UNKNOWN', sport => sport.events[0].team_ids = ['other', 'test-opponent'], sport => sport.forecasts[0].league = 'WNBA', sport => sport.candidates = [{}], sport => sport.future_availability.status = 'AVAILABLE']) {
    const {sport, reference} = typedFixture(); change(sport); assert.throws(() => validateSport(sport, reference));
  }
});

test('DD and TD cannot exceed the necessary component threshold bounds', () => {
  const {sport, reference} = typedFixture();
  const dd = sport.forecasts[0].categories.find(item => item.code === 'DD');
  Object.assign(dd, {pmf: [{value: 0, probability: '0.5'}, {value: 1, probability: '0.5'}], mean: '0.5', interval80: [0, 1]});
  assert.throws(() => validateSport(sport, reference), /threshold/);
});

test('historical reconstruction cannot become a genuinely captured future forecast', () => {
  const {sport, reference} = typedFixture();
  sport.forecasts[0].evidence_lane = 'REAL_TIME_CAPTURED';
  assert.throws(() => validateSport(sport, reference));
  assert.equal(filterResearchForecasts(typedFixture().sport.forecasts, {view: 'upcoming', category: 'ALL', window: 'upcoming'}).length, 0);
  assert.equal(filterResearchForecasts(typedFixture().sport.forecasts, {view: 'history', category: 'ALL', window: 'upcoming'}).length, 14);
  assert.equal(filterResearchForecasts(typedFixture().sport.forecasts, {view: 'history', category: 'REB', window: '24h'}).length, 1);
});

test('PMF summaries expose actual finite support, zero mass and distributional interval', () => {
  const pmf = [{value: 0, probability: '0.5'}, {value: 4, probability: '0.48'}, {value: 12, probability: '0.02'}];
  assert.deepEqual(summarizePmf(pmf), {mean: 2.16, interval80: [0, 4], zero: 0.5, support: [0, 12], upper95: 4, tail: 0.02});
});

test('grade references, scores and settlement claims fail closed', () => {
  for (const change of [grade => grade.forecast_id = 'f'.repeat(64), grade => grade.player_id = 'other', grade => grade.graded_at = '1999-12-31T23:59:59.999999Z', grade => grade.categories[0].crps = '999', grade => grade.categories[0].log_loss = null, grade => grade.categories[0].brier = '1', grade => grade.financial_settlement = 'WON', grade => grade.status = 'DNP_NOT_SCORED']) {
    const {sport, reference} = typedFixture(); change(sport.performance[0]); assert.throws(() => validateSport(sport, reference));
  }
  const {sport, reference} = typedFixture(); sport.performance[0].status = 'DNP_NOT_SCORED'; sport.performance[0].categories = [];
  assert.equal(validateSport(sport, reference), sport);
});

test('typed record hashes are checked in addition to outer asset hashes', async () => {
  const {sport} = typedFixture(); sport.forecasts[0].player_label = 'Changed after receipt';
  const {manifest} = reseal(sport);
  const result = await loadSnapshot(async url => new Response(canonical(url.endsWith('manifest.json') ? manifest : sport)), webcrypto);
  assert.equal(result.sports.length, 0); assert.match(result.errors[0].message, /checksum/);
});

test('zero-support graded outcomes preserve infinite log loss rather than dropping the row', () => {
  const {sport, reference} = typedFixture();
  for (const [code, crps] of [['PTS', '4'], ['PR', '4'], ['PA', '3.75'], ['PRA', '4.75']]) {
    const grade = sport.performance[0].categories.find(item => item.code === code);
    Object.assign(grade, {observed: 13, crps, log_loss: null, log_loss_status: 'ZERO_SUPPORT'});
  }
  assert.equal(validateSport(sport, reference), sport);
  assert.equal(sport.performance[0].categories.filter(item => item.log_loss_status === 'ZERO_SUPPORT').length, 4);
});

test('a failed second sport does not erase a retained typed NBA forecast', async () => {
  const {sport, manifest} = typedFixture();
  const wnba = fixture().sport; wnba.league = 'WNBA';
  const wnbaHash = hash(wnba);
  manifest.supported_sports.push('WNBA');
  manifest.sports.push({league: 'WNBA', path: `wnba.${wnbaHash}.json`, sha256: wnbaHash, generated_at: wnba.generated_at, status: 'RESEARCH_ONLY', retained: false, error: null});
  manifest.sports[0].retained = true; manifest.sports[0].error = 'Update rejected; retained original record';
  manifest.errors = {NBA: 'Update rejected; retained original record'};
  delete manifest.snapshot_id; manifest.snapshot_id = hash(manifest);
  const result = await loadSnapshot(async url => new Response(canonical(url.endsWith('manifest.json') ? manifest : url.includes('wnba.') ? {...wnba, status: 'CORRUPTED'} : sport)), webcrypto);
  assert.equal(result.sports.length, 1); assert.equal(result.sports[0].league, 'NBA');
  assert.equal(result.sports[0].forecasts[0].issued_at, sport.forecasts[0].issued_at);
  assert.equal(result.manifest.sports[0].retained, true);
  assert.equal(result.errors[0].league, 'WNBA');
});

test('pending grades do not become results after start or borrow another forecast identity', async () => {
  const {forecastGradeState} = await import('../research.mjs');
  const {sport} = typedFixture();
  const forecast = sport.forecasts[0], grade = sport.performance[0];
  assert.deepEqual(forecastGradeState(forecast, []), {pending: true, record_count: 0, statuses: []});
  assert.deepEqual(forecastGradeState(forecast, [{...grade, forecast_id: 'f'.repeat(64)}]), {pending: true, record_count: 0, statuses: []});
  assert.deepEqual(forecastGradeState(forecast, [grade]), {pending: false, record_count: 1, statuses: ['SCORED']});
  assert.deepEqual(forecastGradeState(forecast, [{...grade, status: 'UNRESOLVED'}]), {pending: false, record_count: 1, statuses: ['UNRESOLVED']});
  assert.throws(() => forecastGradeState(forecast, [{...grade, player_id: 'another-player'}]), /conflicting/);
});

test('empty Upcoming distinguishes missing issuance, current filters and an elapsed captured event', async () => {
  const {upcomingEmptyReasons} = await import('../research.mjs');
  const {sport} = typedFixture();
  assert.deepEqual(upcomingEmptyReasons([sport]), sport.future_availability.reasons);
  const captured = {...sport.forecasts[0], evidence_lane: 'REAL_TIME_CAPTURED', event_starts_at: '2000-01-02T00:00:00.000000Z'};
  sport.forecasts.push(captured);
  sport.future_availability = {status: 'AVAILABLE', reasons: []};
  assert.match(upcomingEmptyReasons([sport], Date.parse('2000-01-01T00:00:00Z'))[0], /filters exclude/);
  assert.match(upcomingEmptyReasons([sport], Date.parse('2000-01-02T00:00:00Z'))[0], /current viewing time/);
  assert.match(upcomingEmptyReasons([sport], Date.parse('2000-01-02T00:00:00Z'))[0], /does not establish its outcome/);
});

test('prospective v2 validates bounded source capture and actual generation clocks without a grade', async () => {
  const {prospectiveFixture} = await import('./fixtures.mjs');
  const {sport, reference, manifest} = prospectiveFixture();
  assert.equal(validateSport(sport, reference), sport);
  assert.equal(sport.performance.length, 0);
  assert.equal(filterResearchForecasts(sport.forecasts, {view: 'upcoming', category: 'ALL', window: 'upcoming'}, Date.parse(sport.generated_at)).length, 14);
  const result = await loadSnapshot(async url => new Response(canonical(url.endsWith('manifest.json') ? manifest : sport)), webcrypto);
  assert.equal(result.errors.length, 0);
  assert.equal(result.sports[0].forecasts[0].schema_version, 'nba-research-forecast-v2');
});

test('prospective v2 rejects stale sources, late imports, unsupported revisions and fabricated latency', async () => {
  const {prospectiveFixture} = await import('./fixtures.mjs');
  for (const change of [{source_observed_min_at: '1999-12-31T23:19:59.999999Z'}, {source_observed_max_at: '1999-12-31T23:30:00.000001Z'}, {imported_at: '1999-12-31T23:30:00.000001Z'}, {generation_started_at: '1999-12-31T23:29:59.999999Z'}, {generation_completed_at: '1999-12-31T23:30:29.999999Z'}, {history_latest_event_at: '1999-12-31T00:00:00.000000Z'}, {history_rows: 100001}, {history_rows: true}, {source_pack_record_id: '5'.repeat(64)}, {producer_version: 'not-admitted'}]) {
    const {sport, reference} = prospectiveFixture(); Object.assign(sport.forecasts[0].prospective, change);
    assert.throws(() => validateSport(sport, reference));
  }
  const {sport, reference} = prospectiveFixture();
  const forecast = sport.forecasts[0]; forecast.issued_at = forecast.prospective.generation_completed_at = '1999-12-31T23:32:00.000001Z';
  assert.throws(() => validateSport(sport, reference), /latency/);
  forecast.prospective.generation_started_at = '1999-12-31T23:34:00.000000Z';
  forecast.issued_at = forecast.prospective.generation_completed_at = '1999-12-31T23:35:00.000001Z';
  assert.throws(() => validateSport(sport, reference), /bounds/);
});

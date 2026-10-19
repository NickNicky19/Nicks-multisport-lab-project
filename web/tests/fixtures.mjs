import {createHash} from 'node:crypto';
import {REQUIRED_MARKETS} from '../snapshot.mjs';

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

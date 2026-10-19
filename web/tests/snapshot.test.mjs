import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {loadSnapshot, validateManifest, validateSport} from '../snapshot.mjs';
import {fixture, canonical, hash} from './fixtures.mjs';

test('v1 accepts only complete empty research snapshots', () => {
  const {manifest, sport, reference} = fixture();
  assert.equal(validateManifest(manifest), manifest);
  assert.equal(validateSport(sport, reference), sport);
  assert.equal(sport.markets.length, 13);
  assert.equal(sport.coverage.paper, 'NO_ACTION');
});

test('incompatible schemas and unknown admission claims fail closed', () => {
  for (const change of [{schema_version: 2}, {publication_status: 'QUALIFIED'}, {build_commit: 'short'}, {published_at: '2099-01-01T00:00:00Z'}, {unexpected: true}, {errors: []}]) assert.throws(() => validateManifest({...fixture().manifest, ...change}));
  const {sport, reference} = fixture();
  for (const change of [{schema_version: 2}, {status: 'QUALIFIED'}, {league: 'WNBA'}, {generated_at: '1999-01-01T00:00:00Z'}, {unexpected: true}, {coverage: {...sport.coverage, forecast: 'VALIDATED'}}]) assert.throws(() => validateSport({...sport, ...change}, reference));
});

test('sport references cannot redirect requests or silently change scope', () => {
  for (const path of ['../nba.json', '/data/nba.json', 'https://example.com/nba.json', '%2e%2e/nba.json', 'nba.json', `nba.${'b'.repeat(64)}.json`]) {
    const {manifest} = fixture(); manifest.sports[0].path = path;
    assert.throws(() => validateManifest(manifest));
  }
  const {manifest} = fixture(); manifest.supported_sports.push('WNBA');
  assert.throws(() => validateManifest(manifest));
});

test('all thirteen categories are mandatory and do not inherit qualification', () => {
  const {sport, reference} = fixture();
  for (let index = 0; index < 13; index++) assert.throws(() => validateSport({...sport, markets: sport.markets.filter((_, i) => i !== index)}, reference));
  assert.throws(() => validateSport({...sport, markets: [...sport.markets, sport.markets[0]]}, reference));
  assert.throws(() => validateSport({...sport, markets: sport.markets.map(m => ({...m, forecast_status: 'VALIDATED'}))}, reference));
});

test('populated observations and future source clocks are unavailable in research schema', () => {
  const {sport, reference} = fixture();
  for (const key of ['events', 'offers', 'forecasts', 'candidates', 'tickets', 'performance']) assert.throws(() => validateSport({...sport, [key]: [{}]}, reference));
  assert.throws(() => validateSport({...sport, sources: [{...sport.sources[0], observed_at: '2000-01-02T00:00:00Z'}]}, reference));
  assert.throws(() => validateSport({...sport, sources: [...sport.sources, sport.sources[0]]}, reference));
});

test('loader verifies manifest and sport hashes using repository-relative paths', async () => {
  const {manifest, sport, reference} = fixture(); const urls = [];
  const fetcher = async url => {urls.push(url); return new Response(canonical(url.endsWith('manifest.json') ? manifest : sport));};
  const snapshot = await loadSnapshot(fetcher, webcrypto);
  assert.deepEqual(urls, ['./data/manifest.json', `./data/${reference.path}`]);
  assert.equal(snapshot.sports.length, 1); assert.deepEqual(snapshot.errors, []);
});

test('corrupted sport bytes are isolated; manifest corruption rejects the publication', async () => {
  const {manifest, sport} = fixture();
  const result = await loadSnapshot(async url => new Response(canonical(url.endsWith('manifest.json') ? manifest : {...sport, status: 'CHANGED'})), webcrypto);
  assert.equal(result.sports.length, 0); assert.match(result.errors[0].message, /hash/);
  const tampered = {...manifest, build_commit: 'b'.repeat(40)};
  await assert.rejects(loadSnapshot(async () => new Response(canonical(tampered)), webcrypto), /checksum/);
});

test('retained publication preserves original generation time and failure metadata', async () => {
  const {manifest, sport} = fixture();
  manifest.published_at = '2000-02-01T00:00:00Z'; manifest.sports[0].retained = true; manifest.sports[0].error = 'Sport update rejected'; manifest.errors = {NBA: 'Sport update rejected'};
  delete manifest.snapshot_id; manifest.snapshot_id = hash(manifest);
  const result = await loadSnapshot(async url => new Response(canonical(url.endsWith('manifest.json') ? manifest : sport)), webcrypto);
  assert.equal(result.sports[0].generated_at, sport.generated_at);
  assert.equal(result.manifest.sports[0].retained, true); assert.equal(result.manifest.errors.NBA, 'Sport update rejected');
});

test('HTTP failure and oversized publication are errors rather than empty boards', async () => {
  await assert.rejects(loadSnapshot(async () => new Response('', {status: 503}), webcrypto), /HTTP 503/);
  await assert.rejects(loadSnapshot(async () => new Response(' '.repeat(512 * 1024 + 1)), webcrypto), /byte budget/);
});

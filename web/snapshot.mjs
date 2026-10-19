export const REQUIRED_MARKETS = ['PTS', 'PRA', 'REB', '3PM', 'AST', 'RA', 'PR', 'TOV', 'TD', 'DD', 'BLK', 'STL', 'BLK+STL'];
const COLLECTIONS = ['events', 'offers', 'forecasts', 'candidates', 'tickets', 'performance'];
const SHA256 = /^[a-f0-9]{64}$/;
const COMMIT = /^[a-f0-9]{40}$/;
const MAX_BYTES = 512 * 1024;
const utc = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/.test(value) && Number.isFinite(Date.parse(value));
const text = value => typeof value === 'string' && value.trim() === value && value.length > 0;
const keys = (value, fields) => value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).sort().join(',') === [...fields].sort().join(',');
const canonical = value => value && typeof value === 'object' ? Array.isArray(value) ? `[${value.map(canonical).join(',')}]` : `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}` : JSON.stringify(value);

async function sha256(bytes, cryptoProvider) {
  if (!cryptoProvider?.subtle) throw new Error('Snapshot integrity verification requires a secure browser context.');
  const digest = await cryptoProvider.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('');
}

async function boundedBytes(response) {
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength > MAX_BYTES) throw new Error('Publication asset exceeds its byte budget.');
  return bytes;
}

export function validateManifest(value) {
  if (!keys(value, ['schema_version', 'snapshot_id', 'build_commit', 'published_at', 'publication_status', 'supported_sports', 'sports', 'errors']) || value.schema_version !== 1 || value.publication_status !== 'RESEARCH_ONLY') throw new Error('Unsupported publication schema or status.');
  if (!SHA256.test(value.snapshot_id) || !COMMIT.test(value.build_commit) || !utc(value.published_at) || Date.parse(value.published_at) > Date.now()) throw new Error('Incomplete publication identity or invalid clock.');
  if (!Array.isArray(value.supported_sports) || !value.supported_sports.length || value.supported_sports.some(s => typeof s !== 'string' || !/^[A-Z]+$/.test(s)) || new Set(value.supported_sports).size !== value.supported_sports.length) throw new Error('Invalid sport coverage.');
  if (!value.errors || typeof value.errors !== 'object' || Array.isArray(value.errors) || Object.entries(value.errors).some(([league, error]) => !/^[A-Z]+$/.test(league) || !text(error))) throw new Error('Invalid publication errors.');
  if (!Array.isArray(value.sports) || value.sports.length !== value.supported_sports.length) throw new Error('Missing sport snapshots.');
  const seen = new Set();
  for (const sport of value.sports) {
    if (!keys(sport, ['league', 'path', 'sha256', 'generated_at', 'status', 'retained', 'error']) || !value.supported_sports.includes(sport.league) || seen.has(sport.league)) throw new Error('Inconsistent sport references.');
    if (sport.status !== 'RESEARCH_ONLY' || !SHA256.test(sport.sha256) || !utc(sport.generated_at) || Date.parse(sport.generated_at) > Date.parse(value.published_at) || typeof sport.retained !== 'boolean' || !(sport.error === null || text(sport.error))) throw new Error('Invalid sport metadata.');
    // Reject parent paths, absolute URLs, encoded paths and queries; keep every request in data/.
    if (sport.path !== `${sport.league.toLowerCase()}.${sport.sha256}.json`) throw new Error('Unsafe or unversioned sport asset path.');
    seen.add(sport.league);
  }
  return value;
}

export function validateSport(value, reference) {
  if (!keys(value, ['schema_version', 'league', 'generated_at', 'evidence_lane', 'status', 'coverage', 'markets', 'sources', ...COLLECTIONS]) || value.schema_version !== 1 || value.league !== reference.league || value.status !== 'RESEARCH_ONLY' || value.evidence_lane !== 'RECONSTRUCTED_RESEARCH' || value.generated_at !== reference.generated_at || !utc(value.generated_at)) throw new Error('Incompatible sport snapshot.');
  const coverage = value.coverage;
  if (!keys(coverage, ['forecast', 'quotes', 'settlement', 'paper']) || coverage.forecast !== 'UNVALIDATED' || coverage.quotes !== 'UNVERIFIED' || coverage.settlement !== 'UNVERIFIED' || coverage.paper !== 'NO_ACTION') throw new Error('Unsupported admission state.');
  if (!Array.isArray(value.markets)) throw new Error('Missing category inventory.');
  const codes = new Set();
  for (const market of value.markets) {
    if (!keys(market, ['code', 'name', 'requested', 'forecast_status', 'quote_status', 'settlement_status']) || !text(market.code) || codes.has(market.code) || !text(market.name) || typeof market.requested !== 'boolean' || market.forecast_status !== 'UNVALIDATED' || market.quote_status !== 'UNVERIFIED' || market.settlement_status !== 'UNVERIFIED') throw new Error('Invalid category record.');
    codes.add(market.code);
  }
  if (value.league === 'NBA' && (REQUIRED_MARKETS.some(code => !codes.has(code) || !value.markets.find(m => m.code === code).requested) || value.markets.some(market => !REQUIRED_MARKETS.includes(market.code) && (market.code !== 'PA' || market.requested)))) throw new Error('Incomplete or unsupported NBA category inventory.');
  if (!Array.isArray(value.sources) || value.sources.some(source => !keys(source, ['id', 'name', 'status', 'detail', 'observed_at']) || !['id', 'name', 'status', 'detail'].every(key => text(source[key])) || !(source.observed_at === null || utc(source.observed_at) && Date.parse(source.observed_at) <= Date.parse(value.generated_at))) || new Set(value.sources.map(source => source.id)).size !== value.sources.length) throw new Error('Invalid source status.');
  // v1 is a research inventory publication. New populated row types require their own validation and UI.
  if (COLLECTIONS.some(key => !Array.isArray(value[key]) || value[key].length !== 0)) throw new Error('This client does not support populated research row collections.');
  return value;
}

export async function loadSnapshot(fetcher = fetch, cryptoProvider = globalThis.crypto) {
  const response = await fetcher('./data/manifest.json', {cache: 'no-store', signal: AbortSignal.timeout(12000)});
  if (!response.ok) throw new Error(`Publication manifest unavailable (HTTP ${response.status}).`);
  const manifest = validateManifest(JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(await boundedBytes(response))));
  const {snapshot_id, ...unsignedManifest} = manifest;
  if (await sha256(new TextEncoder().encode(canonical(unsignedManifest)), cryptoProvider) !== snapshot_id) throw new Error('Manifest content checksum does not match.');
  const results = await Promise.allSettled(manifest.sports.map(async reference => {
    const result = await fetcher(`./data/${reference.path}`, {cache: 'no-store', signal: AbortSignal.timeout(12000)});
    if (!result.ok) throw new Error(`Sport asset unavailable (HTTP ${result.status}).`);
    const bytes = await boundedBytes(result);
    const hash = await sha256(bytes, cryptoProvider);
    if (hash !== reference.sha256) throw new Error('Sport snapshot content hash does not match.');
    return validateSport(JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes)), reference);
  }));
  return {manifest, sports: results.flatMap(result => result.status === 'fulfilled' ? [result.value] : []), errors: results.flatMap((result, index) => result.status === 'rejected' ? [{league: manifest.sports[index].league, message: result.reason.message}] : [])};
}

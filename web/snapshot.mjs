import {validatePros004Descriptor, validatePros004Index, validatePros004Page, validatePros004Forecast, validatePros004Grade, PROS004_MAX_TOTAL, pros004Original, validatePros004AdmissionContext} from './pros004.mjs';
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
  if (!keys(value, ['schema_version', 'snapshot_id', 'build_commit', 'published_at', 'publication_status', 'supported_sports', 'sports', 'errors', ...(value?.schema_version === 3 ? ['pros004', 'pros004_error'] : [])]) || ![1, 2, 3].includes(value.schema_version) || value.publication_status !== 'RESEARCH_ONLY') throw new Error('Unsupported publication schema or status.');
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
  if (value.schema_version === 3) {
    if (!(value.pros004_error === null || text(value.pros004_error))) throw new Error('Invalid PROS004 publication error.');
    if (value.pros004 === null) {if (!text(value.pros004_error)) throw new Error('Missing PROS004 collection needs an explicit error.');}
    else validatePros004Descriptor(value.pros004, value.published_at);
  }
  return value;
}

export function validateSport(value, reference) {
  const version = value?.schema_version;
  if (!keys(value, ['schema_version', 'league', 'generated_at', 'evidence_lane', 'status', 'coverage', 'markets', 'sources', ...COLLECTIONS, ...(version === 2 ? ['future_availability'] : [])]) || ![1, 2].includes(version) || value.league !== reference.league || value.status !== 'RESEARCH_ONLY' || !(value.evidence_lane === 'RECONSTRUCTED_RESEARCH' || version === 2 && value.evidence_lane === 'RESEARCH_COLLECTION') || value.generated_at !== reference.generated_at || !utc(value.generated_at)) throw new Error('Incompatible sport snapshot.');
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
  if (COLLECTIONS.some(key => !Array.isArray(value[key]))) throw new Error('Invalid observation collection.');
  if (version === 1) {
    if (COLLECTIONS.some(key => value[key].length !== 0)) throw new Error('The v1 client contract rejects populated research row collections.');
    return value;
  }
  if (value.league !== 'NBA' || value.forecasts.length > 32 || value.events.length > 32 || value.performance.length > 64) throw new Error('Typed sport or collection budget is unsupported.');
  if (['offers', 'candidates', 'tickets'].some(key => value[key].length)) throw new Error('Quotes, candidates and tickets remain unadmitted under research v2.');
  if (!keys(value.future_availability, ['status', 'reasons']) || !['UNAVAILABLE', 'AVAILABLE'].includes(value.future_availability.status) || !Array.isArray(value.future_availability.reasons) || value.future_availability.reasons.some(reason => !text(reason)) || value.future_availability.status === 'UNAVAILABLE' && !value.future_availability.reasons.length) throw new Error('Invalid future availability reasons.');
  const events = new Map();
  for (const event of value.events) {
    validateResearchEvent(event);
    if (event.league !== value.league || events.has(event.event_id)) throw new Error('Duplicate or cross-sport event.');
    events.set(event.event_id, event);
  }
  const forecasts = new Map(), forecastTargets = new Set();
  for (const forecast of value.forecasts) {
    validateResearchForecast(forecast, events.get(forecast.event_id), value.generated_at);
    const target = JSON.stringify([forecast.event_id, forecast.player_id, forecast.model_version, forecast.cutoff_at]);
    if (forecasts.has(forecast.forecast_id) || forecastTargets.has(target)) throw new Error('Duplicate forecast identity or original issue revision.');
    if (new TextEncoder().encode(canonical(forecast)).byteLength > 128 * 1024) throw new Error('Forecast exceeds its byte budget.');
    forecasts.set(forecast.forecast_id, forecast);
    forecastTargets.add(target);
  }
  const collectionLane = value.forecasts.some(forecast => forecast.evidence_lane === 'REAL_TIME_CAPTURED') ? 'RESEARCH_COLLECTION' : 'RECONSTRUCTED_RESEARCH';
  if (value.evidence_lane !== collectionLane) throw new Error('Collection evidence label must retain individual forecast lanes.');
  const grades = new Set();
  for (const grade of value.performance) {
    validateResearchGrade(grade, forecasts.get(grade.forecast_id), value.generated_at);
    if (grades.has(grade.grade_id)) throw new Error('Duplicate grade identity.');
    grades.add(grade.grade_id);
  }
  const hasFuture = value.forecasts.some(forecast => forecast.evidence_lane === 'REAL_TIME_CAPTURED' && utcMicros(forecast.event_starts_at) > utcMicros(value.generated_at));
  if ((value.future_availability.status === 'AVAILABLE') !== hasFuture) throw new Error('Future availability must match genuinely captured upcoming forecasts.');
  return value;
}

async function loadPros004(descriptor, fetcher, cryptoProvider) {
  const fetchAsset = async (reference) => {
    const response = await fetcher(`./data/${reference.path}`, {cache:'no-store', signal:AbortSignal.timeout(12000)});
    if (!response.ok) throw new Error(`PROS004 asset unavailable (HTTP ${response.status}).`);
    const raw = await boundedBytes(response);
    if (reference.encoded_bytes !== undefined && raw.byteLength !== reference.encoded_bytes || await sha256(raw, cryptoProvider) !== reference.sha256) throw new Error('PROS004 asset byte/hash mismatch.');
    return {size:raw.byteLength, value:JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw))};
  };
  const root = await fetchAsset(descriptor), index = await validatePros004Index(root.value, descriptor, cryptoProvider);
  const pages = []; let total = root.size;
  // A bounded batch reads every declared page. No first-page-only truncation.
  for (let offset=0; offset<index.pages.length; offset+=8) {
    const batch = await Promise.all(index.pages.slice(offset,offset+8).map(async reference => {
      const raw=await fetchAsset(reference); total+=raw.size;
      if(total>PROS004_MAX_TOTAL) throw new Error('PROS004 complete assets exceed byte budget.');
      return validatePros004Page(raw.value,reference,index);
    }));
    pages.push(...batch);
  }
  const forecasts=pages.filter(page=>page.kind==='forecasts').flatMap(page=>page.records), grades=pages.filter(page=>page.kind==='grades').flatMap(page=>page.records), originals=new Map(), gradeIds=new Set(), targets=new Set(), gradedForecasts=new Set(), subjectOutcomes=new Map(), outcomeSubjects=new Map();
  for(const row of forecasts) {
    await validatePros004Forecast(row,index.generated_at,cryptoProvider);
    validatePros004AdmissionContext(row,index);
    if(originals.has(row.original_id)) throw new Error('Duplicate PROS004 original across pages.');
    const record=pros004Original(row), target=JSON.stringify(['event_id','event_version','player_id','model_key','cutoff_at'].map(k=>record[k]));
    if(targets.has(target)) throw new Error('Duplicate PROS004 original target/model.');
    targets.add(target); originals.set(row.original_id,row);
  }
  for(const row of grades) {
    await validatePros004Grade(row,originals,index.generated_at,cryptoProvider);
    if(gradeIds.has(row.original_id)) throw new Error('Duplicate PROS004 active grade across pages.');
    const grade=pros004Original(row), forecastId=grade.forecast_id, subject=JSON.stringify([grade.event_id,grade.event_version,grade.player_id]);
    if(subjectOutcomes.has(subject)&&subjectOutcomes.get(subject)!==grade.outcome_id || outcomeSubjects.has(grade.outcome_id)&&outcomeSubjects.get(grade.outcome_id)!==subject) throw new Error('PROS004 paired shared-outcome identity conflict.');
    subjectOutcomes.set(subject,grade.outcome_id);outcomeSubjects.set(grade.outcome_id,subject);
    if(gradedForecasts.has(forecastId)) throw new Error('Multiple active PROS004 grades for one original.');
    gradeIds.add(row.original_id); gradedForecasts.add(forecastId);
  }
  return {index,forecasts,grades};
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
    const sport = validateSport(JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes)), reference);
    if (manifest.schema_version === 1 && sport.schema_version !== 1) throw new Error('Manifest version does not support typed research records.');
    for (const record of [...sport.forecasts, ...sport.performance]) {
      const idKey = record.forecast_id && ['nba-research-forecast-v1', 'nba-research-forecast-v2'].includes(record.schema_version) ? 'forecast_id' : 'grade_id';
      const {[idKey]: id, ...body} = record;
      if (await sha256(new TextEncoder().encode(canonical(body)), cryptoProvider) !== id) throw new Error('Typed research record checksum does not match.');
    }
    return sport;
  }));
  let pros004 = null, pros004Error = manifest.schema_version === 3 ? manifest.pros004_error : null;
  if (manifest.schema_version === 3 && manifest.pros004 !== null) {
    try {pros004 = await loadPros004(manifest.pros004, fetcher, cryptoProvider);} catch (error) {pros004Error = error.message || 'PROS004 recovery failed.';}
  }
  return {manifest, pros004, pros004Error, sports: results.flatMap(result => result.status === 'fulfilled' ? [result.value] : []), errors: results.flatMap((result, index) => result.status === 'rejected' ? [{league: manifest.sports[index].league, message: result.reason.message}] : [])};
}
import {validateResearchEvent, validateResearchForecast, validateResearchGrade, utcMicros} from './research.mjs';

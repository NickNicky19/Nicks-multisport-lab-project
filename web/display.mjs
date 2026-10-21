// Source-backed display facts. Research record bytes, clocks and probabilities stay unchanged.
import {utcMicros, isHistoryForecast} from './research.mjs';
const SHA=/^[a-f0-9]{64}$/;
const fields=(v,names)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join(',')===[...names].sort().join(',');
const text=v=>typeof v==='string'&&v.length>0&&v.length<=200&&v.trim()===v;
const require=(ok,message)=>{if(!ok)throw new Error(message);};
export const canonicalDisplay=v=>v&&typeof v==='object'?Array.isArray(v)?`[${v.map(canonicalDisplay).join(',')}]`:`{${Object.keys(v).sort().map(k=>`${JSON.stringify(k)}:${canonicalDisplay(v[k])}`).join(',')}}`:JSON.stringify(v);
const identity=(r,key)=>{require(r.league==='NBA'&&r.id_namespace==='espn'&&text(r[key]),'Unsupported display identity or namespace.');return JSON.stringify([r.league,r.id_namespace,r[key]]);};
export function validateDisplayDescriptor(d,publishedAt){
  require(fields(d,['path','sha256','generated_at','status','retained','error'])&&SHA.test(d.sha256)&&d.path===`display.${d.sha256}.json`&&d.status==='DISPLAY_METADATA_ONLY'&&typeof d.retained==='boolean'&&(d.error===null||text(d.error)),'Invalid display descriptor/path.');
  require(utcMicros(d.generated_at)<=utcMicros(publishedAt),'Display generation exceeds publication.');return d;
}
export function validateDisplayCatalog(catalog,now){
  require(fields(catalog,['schema_version','verified_at','sources','players','events','appearances','catalog_id'])&&catalog.schema_version==='nba-display-catalog-v1'&&SHA.test(catalog.catalog_id)&&utcMicros(catalog.verified_at)<=utcMicros(now),'Invalid display catalog identity or clock.');
  for(const [key,max] of [['sources',64],['players',128],['events',64],['appearances',256]])require(Array.isArray(catalog[key])&&catalog[key].length<=max,'Display catalog exceeds collection bounds.');
  const sources=new Map();
  for(const s of catalog.sources){
    require(fields(s,['source_id','league','id_namespace','event_id','source_url','kind','request_started_at','observed_at','source_updated_at','http_status','raw_sha256','raw_bytes','facts']),'Invalid display source.');
    identity(s,'event_id');
    require(text(s.source_id)&&!sources.has(s.source_id)&&s.kind==='ARCHIVED_EVENT_BOXSCORE'&&s.source_url===`https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=${s.event_id}`&&s.http_status===200&&Number.isSafeInteger(s.raw_bytes)&&s.raw_bytes>0&&s.raw_bytes<=3*1024*1024&&SHA.test(s.raw_sha256),'Invalid archived display evidence.');
    require(utcMicros(s.request_started_at)<=utcMicros(s.observed_at)&&utcMicros(s.observed_at)<=utcMicros(catalog.verified_at)&&(s.source_updated_at===null||utcMicros(s.source_updated_at)<=utcMicros(s.observed_at)),'Display source clocks conflict.');
    const f=s.facts;
    require(fields(f,['event_id','event_starts_at','status','teams','players'])&&f.event_id===s.event_id&&f.status==='FINAL'&&utcMicros(f.event_starts_at)<utcMicros(s.observed_at)&&Array.isArray(f.teams)&&f.teams.length===2&&Array.isArray(f.players)&&f.players.length>0&&f.players.length<=128,'Invalid archived source facts.');
    const teams=new Map(),players=new Map();
    for(const t of f.teams){require(fields(t,['team_id','display_name','abbreviation','home_away'])&&['team_id','display_name','abbreviation'].every(k=>text(t[k]))&&['home','away'].includes(t.home_away)&&!teams.has(t.team_id),'Invalid source team.');teams.set(t.team_id,t);}
    require(new Set([...teams.values()].map(t=>t.home_away)).size===2,'Historical home/away roles conflict.');
    for(const p of f.players){require(fields(p,['player_id','display_name','team_id'])&&text(p.player_id)&&text(p.display_name)&&teams.has(p.team_id)&&!players.has(p.player_id),'Invalid source player membership.');players.set(p.player_id,p);}
    sources.set(s.source_id,{source:s,teams,players});
  }
  const evidence=r=>{require(Array.isArray(r.source_ids)&&r.source_ids.length>0&&r.source_ids.length<=8&&new Set(r.source_ids).size===r.source_ids.length&&r.source_ids.every(i=>sources.has(i)),'Missing or duplicate display source reference.');return r.source_ids.map(i=>sources.get(i));};
  const players=new Map(),events=new Map(),appearances=new Set();
  for(const r of catalog.players){
    require(fields(r,['league','id_namespace','player_id','display_name','source_ids']),'Invalid display player.');const key=identity(r,'player_id');
    require(!players.has(key)&&text(r.display_name)&&evidence(r).every(s=>s.source.league===r.league&&s.source.id_namespace===r.id_namespace&&s.players.get(r.player_id)?.display_name===r.display_name),'Display name lacks matching namespaced source evidence.');players.set(key,r);
  }
  for(const r of catalog.events){
    require(fields(r,['league','id_namespace','event_id','event_starts_at','teams','source_ids']),'Invalid display event.');const key=identity(r,'event_id');
    require(!events.has(key)&&evidence(r).every(s=>identity(s.source,'event_id')===key&&s.source.facts.event_starts_at===r.event_starts_at&&canonicalDisplay(s.source.facts.teams)===canonicalDisplay(r.teams)),'Display event/date/matchup conflicts with source.');events.set(key,r);
  }
  for(const r of catalog.appearances){
    require(fields(r,['league','id_namespace','event_id','player_id','team_id','opponent_id','source_ids']),'Invalid historical appearance.');const event=identity(r,'event_id'),key=JSON.stringify([r.league,r.id_namespace,r.event_id,r.player_id]);
    require(!appearances.has(key)&&events.has(event)&&players.has(JSON.stringify([r.league,r.id_namespace,r.player_id]))&&evidence(r).every(s=>identity(s.source,'event_id')===event&&s.players.get(r.player_id)?.team_id===r.team_id&&s.teams.has(r.opponent_id)&&r.team_id!==r.opponent_id),'Historical appearance changes source membership.');appearances.add(key);
  }
  return catalog;
}
export function validateDisplayTargets(catalog,sports){
  for(const sport of sports)for(const f of sport.forecasts){
    const event=catalog.events.find(r=>['league','id_namespace','event_id'].every(k=>r[k]===f[k]));
    const appearance=catalog.appearances.find(r=>['league','id_namespace','event_id','player_id'].every(k=>r[k]===f[k]));
    if(event)require(event.event_starts_at===f.event_starts_at&&canonicalDisplay(event.teams.map(t=>t.team_id).sort())===canonicalDisplay([f.team_id,f.opponent_id].sort()),'Display metadata conflicts with immutable event identity.');
    if(appearance)require(appearance.team_id===f.team_id&&appearance.opponent_id===f.opponent_id,'Display metadata changes historical player membership.');
  }
}
export function validateDisplayMetadata(asset,sports,now){
  require(fields(asset,['schema_version','generated_at','catalog','status','metadata_id'])&&asset.schema_version==='multisport-display-metadata-v1'&&SHA.test(asset.metadata_id)&&utcMicros(asset.generated_at)<=utcMicros(now),'Invalid display asset.');
  validateDisplayCatalog(asset.catalog,asset.generated_at);validateDisplayTargets(asset.catalog,sports);
  const s=asset.status;
  require(fields(s,['schema_version','generated_at','counts','latest_retained_input_capture','last_genuine_issued_at'])&&s.schema_version==='multisport-display-status-v1'&&s.generated_at===asset.generated_at&&fields(s.counts,['forecasts','reconstructed_forecasts','captured_forecasts','upcoming_forecasts','forecast_grades','offers','qualified_tickets'])&&Object.values(s.counts).every(n=>Number.isSafeInteger(n)&&n>=0&&n<=512),'Invalid publication status counts.');
  const forecasts=sports.flatMap(s=>s.forecasts),captured=forecasts.filter(f=>f.evidence_lane==='REAL_TIME_CAPTURED');
  const expected={forecasts:forecasts.length,reconstructed_forecasts:forecasts.filter(f=>f.evidence_lane==='RECONSTRUCTED_RESEARCH').length,captured_forecasts:captured.length,upcoming_forecasts:captured.filter(f=>utcMicros(f.event_starts_at)>utcMicros(s.generated_at)).length,forecast_grades:sports.reduce((n,s)=>n+s.performance.length,0),offers:sports.reduce((n,s)=>n+s.offers.length,0),qualified_tickets:sports.reduce((n,s)=>n+s.tickets.length,0)};
  require(canonicalDisplay(s.counts)===canonicalDisplay(expected)&&s.last_genuine_issued_at===(captured.map(f=>f.issued_at).sort().at(-1)||null),'Display counts/genuine issue clock disagree with research records.');
  if(s.last_genuine_issued_at!==null)require(utcMicros(s.last_genuine_issued_at)<=utcMicros(asset.generated_at),'Genuine issue clock is in the future.');
  const c=s.latest_retained_input_capture;
  if(c!==null)require(fields(c,['observed_at','imported_at','record_ref','meaning'])&&fields(c.record_ref,['kind','record_id','payload_sha256'])&&c.record_ref.kind==='research_inputs'&&SHA.test(c.record_ref.record_id)&&SHA.test(c.record_ref.payload_sha256)&&c.meaning==='RETAINED_INPUT_PREPARATION_TIMELINESS_NOT_ESTABLISHED'&&utcMicros(c.observed_at)<=utcMicros(c.imported_at)&&utcMicros(c.imported_at)<=utcMicros(asset.generated_at),'Invalid retained capture clock or meaning.');
  return asset;
}
/** Resolve only exact namespaced identities; current rosters never supply historical teams. */
export function displayTarget(forecast,metadata){
  const catalog=metadata?.catalog;
  const player=catalog?.players.find(r=>['league','id_namespace','player_id'].every(k=>r[k]===forecast[k]));
  const event=catalog?.events.find(r=>['league','id_namespace','event_id'].every(k=>r[k]===forecast[k])&&r.event_starts_at===forecast.event_starts_at&&r.teams.some(t=>t.team_id===forecast.team_id)&&r.teams.some(t=>t.team_id===forecast.opponent_id));
  const retainedLabel=typeof forecast.player_label==='string'&&!/^ESPN player \S+$/.test(forecast.player_label);
  const playerName=player?.display_name||(retainedLabel?forecast.player_label:`Player ${forecast.player_id} · name unavailable`);
  const team=event?.teams.find(t=>t.team_id===forecast.team_id),opponent=event?.teams.find(t=>t.team_id===forecast.opponent_id),away=event?.teams.find(t=>t.home_away==='away'),home=event?.teams.find(t=>t.home_away==='home');
  return {playerName,teamName:team?.display_name||`Team ${forecast.team_id}`,opponentName:opponent?.display_name||`Team ${forecast.opponent_id}`,matchup:event?`${away.display_name} @ ${home.display_name}`:`Event ${forecast.event_id} · matchup names unavailable`,eventDate:forecast.event_starts_at,nameBasis:player?'SOURCE_VERIFIED_DISPLAY':retainedLabel?'ORIGINAL_RESEARCH_LABEL':'ID_FALLBACK',sourceIds:[...new Set([...(player?.source_ids||[]),...(event?.source_ids||[])])]};
}
/** Current viewing time affects Upcoming; no price or ticket test filters forecasts. */
export function researchAvailability(sports,now=Date.now()){
  const forecasts=sports.flatMap(s=>s.forecasts),history=forecasts.filter(f=>isHistoryForecast(f,now)),upcoming=forecasts.filter(f=>f.evidence_lane==='REAL_TIME_CAPTURED'&&!isHistoryForecast(f,now));
  return {forecasts:forecasts.length,history:history.length,upcoming:upcoming.length,offers:sports.reduce((n,s)=>n+s.offers.length,0),tickets:sports.reduce((n,s)=>n+s.tickets.length,0)};
}

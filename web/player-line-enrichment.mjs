// Private source-backed companion. This never changes or publicly admits v1 rows.
import {utcMicros} from './research.mjs';
import {canonicalPlayerLineReview,validatePlayerLineReview,verifyPlayerLineReviewHash} from './player-line-review.mjs';

export const PLAYER_LINE_ENRICHMENT_SCHEMA='nba-private-player-line-enrichment-v1';
export const ENRICHMENT_SOURCE_URLS=Object.freeze({catalogue:'https://api.sleeper.app/v1/players/nba',
  picks_rules:'https://support.sleeper.com/en/articles/9047931-sleeper-player-picks-rules',
  stats_rules:'https://support.sleeper.com/en/articles/6262990-sleeper-player-picks-stats-explained'});
export const RULE_WITNESSES=Object.freeze({
  general_overtime:{source:'picks_rules',text:'Overtime and extra innings count toward stats'},
  corrections_within_30_minutes:{source:'picks_rules',text:'Stat corrections made within 30 minutes of game end will trigger regrading'},
  corrections_after_30_minutes:{source:'picks_rules',text:'Corrections after 30 minutes will not affect contest results'},
  q1:{source:'stats_rules',text:"1st quarter projections will be graded based on the player's statistical totals at the end of the 1st quarter."},
  quarter_overtime:{source:'stats_rules',text:'Quarter Markets: Resulted on score for relevant quarter. Overtime does not count.'}});
const Q1=['first_qtr_points','first_qtr_rebounds','first_qtr_assists'];
const TOP=['schema_version','scope','source','base','generated_at','evidence_lane','sources','rule_witnesses','event_team_inventory','counts','observations','public_admission','ticket_eligibility','qualification','enrichment_id'];
const SOURCE=['source_url','raw_sha256','raw_bytes','metadata_sha256','request_started_at','observed_at','upstream_observed_at'];
const COUNTS=['catalogue_objects','catalogue_players','catalogue_team_entries','source_nba_rows','source_player_ids','name_resolved_player_ids','name_unresolved_player_ids','source_side_observations','q1_side_observations','displayed_observations'];
const ROW=['row_id','league','namespace','provider_player_id','provider_event_id','player_label','name_status','catalogue_pointer','catalogue_team','board_team','team_status','raw_stat_label','period','overtime','period_evidence','event_status','event_label','event_starts_at','settlement_status','forecast_match_status','ticket_eligible','missing_fields'];
const require=(ok,message)=>{if(!ok)throw new Error(message);};
const fields=(value,keys)=>value!==null&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).sort().join(',')===[...keys].sort().join(',');
const text=(v,max=200)=>typeof v==='string'&&v.length>0&&v.length<=max&&v.trim()===v;
const sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const same=(a,b)=>canonicalPlayerLineReview(a)===canonicalPlayerLineReview(b);
const clockNow=()=>new Date().toISOString().replace(/\.(\d{3})Z$/,(_,ms)=>`.${ms}000Z`);
const esc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label=value=>value.replace('T',' ').replace('Z',' UTC');
export const canonicalPlayerLineEnrichment=canonicalPlayerLineReview;

function expectedRow(original,player){
  const name=player?.name??null, catalogueTeam=player?.team??null, boardTeam=original.team_label;
  const teamStatus=catalogueTeam===null||boardTeam===null?'UNKNOWN':catalogueTeam===boardTeam?'CONSISTENT_LITERALS_EVENT_UNVERIFIED':'CONFLICT_UNVERIFIED';
  const q1=Q1.includes(original.raw_stat_label), missing=['native_event_mapping','event_start','product_variant','complete_settlement_contract'];
  if(name===null)missing.push('player_name');
  if(!q1)missing.push('period','overtime');
  if(teamStatus==='CONFLICT_UNVERIFIED')missing.push('team_conflict');
  return {row_id:original.row_id,league:'NBA',namespace:'sleeper',provider_player_id:original.provider_player_id,
    provider_event_id:original.provider_event_id,player_label:name,name_status:player?'VERIFIED_NATIVE_CATALOGUE':'UNVERIFIED_NOT_IN_CATALOGUE',
    catalogue_pointer:player?'/'+original.provider_player_id:null,catalogue_team:catalogueTeam,board_team:boardTeam,team_status:teamStatus,
    raw_stat_label:original.raw_stat_label,period:q1?'Q1':'UNKNOWN',overtime:q1?'OT_EXCLUDED':'UNKNOWN',period_evidence:q1?['q1','quarter_overtime']:[],
    event_status:'UNVERIFIED_NATIVE_ID',event_label:null,event_starts_at:null,settlement_status:'PARTIAL_GENERIC_RULES_ONLY',
    forecast_match_status:'NOT_MATCHED_UNVERIFIED_EVENT_PERIOD',ticket_eligible:false,missing_fields:missing};
}

export function validatePlayerLineEnrichment(enrichment,review,now=clockNow()){
  validatePlayerLineReview(review,now);
  require(fields(enrichment,TOP)&&enrichment.schema_version===PLAYER_LINE_ENRICHMENT_SCHEMA&&enrichment.scope==='LOCAL_REVIEW_ONLY'
    &&enrichment.source==='sleeper'&&enrichment.public_admission===false&&enrichment.ticket_eligibility===false
    &&enrichment.qualification==='UNAVAILABLE'&&enrichment.evidence_lane===review.evidence_lane&&sha(enrichment.enrichment_id),'Invalid private enrichment scope.');
  require(review.source_evidence.kind==='RAW_HTTP_BODY_REPLAYED'&&same(enrichment.base,{review_id:review.review_id,
    board_sha256:review.source_evidence.raw_source_sha256,board_bytes:review.source_evidence.raw_source_bytes,observed_at:review.observed_at}),'Enrichment base binding differs.');
  const generated=utcMicros(enrichment.generated_at);
  require(utcMicros(review.generated_at)<=generated&&generated<=utcMicros(now),'Invalid enrichment generation clock.');
  require(fields(enrichment.sources,Object.keys(ENRICHMENT_SOURCE_URLS)),'Exact enrichment sources required.');
  for(const[key,fact]of Object.entries(enrichment.sources))require(fields(fact,SOURCE)&&fact.source_url===ENRICHMENT_SOURCE_URLS[key]
    &&sha(fact.raw_sha256)&&sha(fact.metadata_sha256)&&Number.isSafeInteger(fact.raw_bytes)&&fact.raw_bytes>0&&fact.raw_bytes<=8*1024*1024
    &&fact.upstream_observed_at===null&&utcMicros(fact.request_started_at)<=utcMicros(fact.observed_at)&&utcMicros(fact.observed_at)<=generated,'Invalid enrichment source hash or clock.');
  require(same(enrichment.rule_witnesses,RULE_WITNESSES),'Official rule witnesses differ.');
  require(Array.isArray(enrichment.event_team_inventory)&&enrichment.event_team_inventory.length<=review.counts.nba_rows,'Invalid native event inventory.');
  const eventIds=[];
  for(const event of enrichment.event_team_inventory){
    require(fields(event,['provider_event_id','source_team_labels','status'])&&text(event.provider_event_id,600)
      &&Array.isArray(event.source_team_labels)&&event.source_team_labels.every(v=>text(v))
      &&same(event.source_team_labels,[...new Set(event.source_team_labels)].sort())
      &&event.status===(event.source_team_labels.length>2?'CONFLICT_UNVERIFIED':'UNVERIFIED_NATIVE_EVENT'),'Native event cannot be admitted from raw team labels.');
    eventIds.push(event.provider_event_id);
  }
  require(same(eventIds,[...new Set(eventIds)].sort()),'Duplicate/unordered native events.');
  const c=enrichment.counts;
  require(fields(c,COUNTS)&&Object.values(c).every(v=>Number.isSafeInteger(v)&&v>=0&&v<=20000)
    &&c.catalogue_objects===c.catalogue_players+c.catalogue_team_entries&&c.source_player_ids===c.name_resolved_player_ids+c.name_unresolved_player_ids
    &&c.source_player_ids<=c.source_nba_rows&&c.source_nba_rows===review.counts.nba_rows&&c.source_side_observations===review.counts.parsed_observations
    &&c.q1_side_observations<=c.source_side_observations&&Array.isArray(enrichment.observations)
    &&c.displayed_observations===enrichment.observations.length&&c.displayed_observations===review.observations.length,'Enrichment full-source counts differ.');
  for(const[rowIndex,row]of enrichment.observations.entries()){
    require(fields(row,ROW)&&(row.player_label===null||text(row.player_label))&&(row.catalogue_team===null||text(row.catalogue_team)),'Invalid enriched row.');
    const player=row.player_label===null?null:{name:row.player_label,team:row.catalogue_team};
    require(same(row,expectedRow(review.observations[rowIndex],player)),'Enrichment changes original identity or hides missing semantics.');
  }
  require(new TextEncoder().encode(canonicalPlayerLineEnrichment(enrichment)).byteLength<=256*1024,'Enrichment exceeds its byte ceiling.');
  return enrichment;
}

async function hash(raw,cryptoProvider){
  require(cryptoProvider?.subtle,'SHA-256 support required.');
  return Array.from(new Uint8Array(await cryptoProvider.subtle.digest('SHA-256',raw))).map(v=>v.toString(16).padStart(2,'0')).join('');
}
export async function verifyPlayerLineEnrichmentHash(enrichment,review,cryptoProvider=globalThis.crypto){
  validatePlayerLineEnrichment(enrichment,review);await verifyPlayerLineReviewHash(review,cryptoProvider);
  const unsigned=Object.fromEntries(Object.entries(enrichment).filter(([key])=>key!=='enrichment_id'));
  require(enrichment.enrichment_id===await hash(new TextEncoder().encode(canonicalPlayerLineEnrichment(unsigned)),cryptoProvider),'Private enrichment seal mismatch.');
  return enrichment;
}

const decode=raw=>new TextDecoder('utf-8',{fatal:true}).decode(raw);
// Adapted from the existing production original-record structural pass. Decode
// keys before comparing them: JSON.parse alone silently accepts duplicate and
// escaped-duplicate keys. These are retained bytes, never permissive live input.
function unambiguousJson(raw,maximum=8*1024*1024){
  require(typeof raw==='string'&&new TextEncoder().encode(raw).byteLength>0
    &&new TextEncoder().encode(raw).byteLength<=maximum,'Private source JSON exceeds its byte bound.');
  let at=0;
  const ws=()=>{while(at<raw.length&&/[ \t\r\n]/.test(raw[at]))at++;};
  const string=()=>{
    const start=at++;
    while(at<raw.length){const c=raw[at++];if(c==='\\'){at++;continue;}if(c==='"')return JSON.parse(raw.slice(start,at));}
    throw new Error('Unterminated private source JSON string.');
  };
  const value=depth=>{
    require(depth<=64,'Private source JSON exceeds its nesting bound.');ws();const c=raw[at];
    if(c==='"'){string();return;}
    if(c==='{'){
      at++;ws();const keys=new Set();if(raw[at]==='}'){at++;return;}
      while(at<raw.length){
        require(raw[at]==='"','Invalid private source JSON object key.');const key=string();
        require(!keys.has(key),'Duplicate private source JSON key.');keys.add(key);ws();
        require(raw[at++]===':','Invalid private source JSON object separator.');value(depth+1);ws();
        if(raw[at]==='}'){at++;return;}require(raw[at++]===',','Invalid private source JSON object delimiter.');ws();
      }
      throw new Error('Unterminated private source JSON object.');
    }
    if(c==='['){
      at++;ws();if(raw[at]===']'){at++;return;}
      while(at<raw.length){value(depth+1);ws();if(raw[at]===']'){at++;return;}
        require(raw[at++]===',','Invalid private source JSON array delimiter.');}
      throw new Error('Unterminated private source JSON array.');
    }
    const token=/^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(raw.slice(at));
    require(token,'Invalid private source JSON value.');at+=token[0].length;
  };
  value(0);ws();require(at===raw.length,'Trailing private source JSON data.');
  return JSON.parse(raw,(_key,item)=>{require(typeof item!=='number'||Number.isFinite(item),'Non-finite private source JSON number.');return item;});
}
function visible(raw){return decode(raw).replace(/<(head|script|style|template|noscript|iframe|object|svg|math|textarea)\b[^>]*>[\s\S]*?<\/\1\s*>/gi,'')
  .replace(/<\/?(?:address|article|aside|blockquote|br|caption|dd|details|dialog|div|dl|dt|fieldset|figcaption|figure|footer|form|h[1-6]|header|hgroup|hr|li|main|nav|ol|p|pre|section|summary|table|tbody|td|tfoot|th|thead|tr|ul)\b[^>]*>/gi,' ')
  .replace(/<!--[^]*?-->/g,'').replace(/<[^>]*>/g,'')
  .replace(/&#x([a-f0-9]+);/gi,(_,n)=>String.fromCodePoint(parseInt(n,16))).replace(/&#([0-9]+);/g,(_,n)=>String.fromCodePoint(Number(n)))
  .replace(/&(nbsp|apos|quot|amp|lt|gt);/g,(_,n)=>({nbsp:' ',apos:"'",quot:'"',amp:'&',lt:'<',gt:'>'}[n])).replace(/\s+/g,' ').trim();}

/** Replay retained raw hashes, source clocks, catalogue names and rule witnesses. */
export async function verifyPlayerLineEnrichmentSources(enrichment,review,assets,boardRaw,cryptoProvider=globalThis.crypto){
  await verifyPlayerLineEnrichmentHash(enrichment,review,cryptoProvider);
  require(fields(assets,Object.keys(ENRICHMENT_SOURCE_URLS)),'All retained enrichment originals required.');
  for(const[key,asset]of Object.entries(assets)){
    const fact=enrichment.sources[key],{raw,metadataRaw}=asset;
    require(raw instanceof Uint8Array&&raw.byteLength===fact.raw_bytes&&raw.byteLength<=8*1024*1024
      &&metadataRaw instanceof Uint8Array&&metadataRaw.byteLength<=256*1024,'Invalid retained source bytes.');
    require(await hash(raw,cryptoProvider)===fact.raw_sha256&&await hash(metadataRaw,cryptoProvider)===fact.metadata_sha256,'Retained source hash mismatch.');
    const meta=unambiguousJson(decode(metadataRaw),256*1024);
    require(meta.complete_body===true&&meta.http_status===200&&meta.url===fact.source_url&&meta.final_url===fact.source_url
      &&meta.raw_bytes===fact.raw_bytes&&meta.raw_sha256===fact.raw_sha256&&meta.observed_at===fact.observed_at
      &&meta.request_started_at===fact.request_started_at&&String(meta.content_type).toLowerCase().includes(key==='catalogue'?'json':'html'),'Retained source metadata differs.');
  }
  for(const witness of Object.values(RULE_WITNESSES))require(visible(assets[witness.source].raw).includes(witness.text),'Official rule witness absent from retained body.');
  const catalogue=unambiguousJson(decode(assets.catalogue.raw)),players=new Map();let teams=0;
  require(catalogue&&typeof catalogue==='object'&&!Array.isArray(catalogue)&&Object.keys(catalogue).length<=10000,'Invalid catalogue.');
  for(const[id,p]of Object.entries(catalogue)){
    require(p&&typeof p==='object'&&!Array.isArray(p)&&p.player_id===id&&p.sport==='nba','Conflicting catalogue key/player_id/sport.');
    if(p.position==='DEF'){require(/^[A-Z]{2,4}$/.test(id)&&p.team===id,'Unrecognized non-player subject.');teams++;continue;}
    require(/^[0-9]+$/.test(id)&&[p.first_name,p.last_name,p.full_name].every(v=>text(v))&&p.full_name===p.first_name+' '+p.last_name
      &&(p.team===null||p.team===undefined||text(p.team)),'Invalid catalogue player name.');
    players.set(id,{name:p.full_name,team:p.team??null});
  }
  require(boardRaw instanceof Uint8Array&&boardRaw.byteLength===enrichment.base.board_bytes
    &&await hash(boardRaw,cryptoProvider)===enrichment.base.board_sha256,'Original whole-board hash differs.');
  const board=unambiguousJson(decode(boardRaw));require(Array.isArray(board)&&board.length===review.counts.source_rows,'Whole board inventory differs.');
  const nba=board.filter(r=>r&&typeof r==='object'&&r.sport==='nba'),ids=new Set(nba.filter(r=>r.subject_type==='player').map(r=>String(r.subject_id)));
  const events=new Map();
  for(const row of nba.filter(r=>r.subject_type==='player')){
    require(text(row.game_id,600)&&Array.isArray(row.options),'Invalid native board event.');
    if(!events.has(row.game_id))events.set(row.game_id,new Set());
    for(const option of row.options)if(option&&typeof option==='object'&&option.subject_team!==undefined&&option.subject_team!==null){
      require(text(option.subject_team),'Invalid native board team label.');events.get(row.game_id).add(option.subject_team);
    }
  }
  require(same(enrichment.event_team_inventory,[...events].sort(([a],[b])=>a<b?-1:a>b?1:0).map(([id,teams])=>({provider_event_id:id,
    source_team_labels:[...teams].sort(),status:teams.size>2?'CONFLICT_UNVERIFIED':'UNVERIFIED_NATIVE_EVENT'}))),'Native event team inventory differs from original source.');
  const resolved=[...ids].filter(id=>players.has(id)).length;
  require(same(enrichment.counts,{catalogue_objects:Object.keys(catalogue).length,catalogue_players:players.size,catalogue_team_entries:teams,
    source_nba_rows:nba.length,source_player_ids:ids.size,name_resolved_player_ids:resolved,name_unresolved_player_ids:ids.size-resolved,
    source_side_observations:review.counts.parsed_observations,q1_side_observations:nba.filter(r=>r.subject_type==='player'&&Q1.includes(r.wager_type)).reduce((sum,r)=>sum+r.options.length,0),
    displayed_observations:review.observations.length}),'Enrichment source-wide counts differ from originals.');
  for(const[i,row]of enrichment.observations.entries())require(same(row,expectedRow(review.observations[i],players.get(row.provider_player_id))), 'Enriched player facts differ from catalogue.');
  return enrichment;
}

export function renderEnrichedPlayerLineReview(review,enrichment,{now=clockNow()}={}){
  validatePlayerLineEnrichment(enrichment,review,now);
  const c=enrichment.counts;
  const cards=review.observations.map((original,i)=>{const row=enrichment.observations[i];return `<article class="local-observation" data-review-state="PRIVATE_ENRICHED_THRESHOLD">
    <p class="review-eyebrow">Sleeper · private recorded player threshold</p><h2>${esc(row.player_label??'Unverified Sleeper player '+row.provider_player_id)}</h2>
    <p><strong>${esc(original.side.toUpperCase())} ${esc(original.line)} ${esc(original.stat??original.raw_stat_label)}</strong> · Price unavailable (PRICE_UNAVAILABLE).</p>
    <p>Matchup and game start unverified · Sleeper event ${esc(row.provider_event_id)}. No forecast match or qualified ticket.</p>
    <p>${row.period==='Q1'?'Verified period: first quarter (Q1). Overtime excluded.':'Period and overtime: UNKNOWN. An unprefixed market or normal variant does not establish full game.'}</p>
    <p>Original board team: ${esc(row.board_team??'not supplied')}; later catalogue team: ${esc(row.catalogue_team??'not supplied')}. ${row.team_status==='CONFLICT_UNVERIFIED'?'Team conflict remains unverified; original team preserved.':'Matching literal labels do not verify event participation or historical affiliation.'}</p>
    <p>Original board observed ${esc(label(review.observed_at))}; catalogue observed ${esc(label(enrichment.sources.catalogue.observed_at))}. Later enrichment does not refresh the line.</p>
    <details><summary>Source identities, clocks and unresolved fields</summary><p>NBA / sleeper namespace. Player ${esc(row.provider_player_id)}; event ${esc(row.provider_event_id)}; selection ${esc(original.provider_selection_id)}; row ${esc(row.row_id)}.</p>
    <p>Source statistic ${esc(original.raw_stat_label)}; variant ${esc(original.variant)}; exact threshold pointer ${esc(original.source_pointer)}; catalogue pointer ${esc(row.catalogue_pointer??'unavailable')}.</p>
    <p>${original.source_economics===null?'No source economics supplied.':`Observed pick’em side multiplier ${esc(original.source_economics.value)}×; not standalone sportsbook odds.`}</p>
    <p>Missing: ${row.missing_fields.map(v=>esc(v.replaceAll('_',' '))).join('; ')}. Complete settlement contract remains unverified.</p></details></article>`;}).join('');
  return `<section class="local-offer-review"><header><p class="review-eyebrow">Source-backed private enrichment · unpublished</p><h1>NBA player-line observations</h1>
    <p class="review-banner">LOCAL REVIEW ONLY. Names and explicit quarter rules are enriched from later source observations. Original records remain unchanged.</p>
    <p>${c.name_resolved_player_ids} of ${c.source_player_ids} source player IDs name-resolved; ${c.source_side_observations} parsed side options; ${c.q1_side_observations} explicit Q1 options; displaying ${c.displayed_observations}. 0 complete contracts.</p>
    <p>Board observed ${esc(label(review.observed_at))}; original import ${esc(label(review.imported_at))}; original review ${esc(label(review.generated_at))}; enrichment generated ${esc(label(enrichment.generated_at))}.</p>
    <p>No public admission, current-availability certification, complete game mapping or qualified ticket.</p></header>${cards}
    <section class="review-coverage"><h2>Full NBA category inventory</h2><p>Counts describe the original bounded sample, not permanent source coverage.</p><div class="review-table"><table><thead><tr><th scope="col">Category</th><th scope="col">Observed side options</th><th scope="col">Displayed</th></tr></thead><tbody>${Object.entries(review.category_coverage).map(([code,r])=>`<tr><th scope="row">${esc(code)}</th><td>${r.observed_side_options}</td><td>${r.displayed_side_options}</td></tr>`).join('')}</tbody></table></div></section>
    <details><summary>Unverified native-event source team labels</summary><p>This is a literal source inventory, not a verified matchup, start time or canonical game mapping. Conflicting inventories are ineligible for event admission.</p><ul>${enrichment.event_team_inventory.map(event=>`<li>Sleeper event ${esc(event.provider_event_id)}: ${event.source_team_labels.map(esc).join(', ')||'no team label supplied'}; ${esc(event.status)}.</li>`).join('')}</ul></details>
    <details><summary>Official generic rules and retained provenance</summary><p>These generic product rules do not establish an unprefixed market's period, event identity or complete entry economics.</p>
    <ul>${Object.values(enrichment.rule_witnesses).map(w=>`<li>${esc(w.text)} (source: ${esc(w.source)})</li>`).join('')}</ul>
    ${Object.entries(enrichment.sources).map(([key,f])=>`<p>${esc(key)}: ${esc(f.source_url)}. Observed ${esc(label(f.observed_at))}; upstream observation UNKNOWN. SHA-256 <code>${esc(f.raw_sha256)}</code>.</p>`).join('')}
    <p>Original review ${esc(review.review_id)}; whole board ${esc(enrichment.base.board_sha256)}; companion ${esc(enrichment.enrichment_id)}. Local original-byte replay does not establish durable remote archival or source admission.</p></details></section>`;
}

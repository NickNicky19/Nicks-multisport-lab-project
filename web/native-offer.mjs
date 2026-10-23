// Native DD/TD source semantics. No collector, pricing model or publication grant.
import {ALL_NBA_CATEGORIES,NBA_UNITS} from './research.mjs';
import {REVIEWED_NATIVE_OFFERS as PUBLIC_REVIEWED_OFFER_IDS} from './native-offer-admissions.mjs';

export const NATIVE_OFFER_SCHEMA='nba-native-player-offer-v2';
export const MAX_NATIVE_OFFER_BYTES=32*1024;
export const MAX_NATIVE_ASSET_BYTES=256*1024;
export const MAX_NATIVE_OFFERS=32;
// Reviewed exact record IDs only. An input flag or caller registry cannot grant publication.
const TOP='schema_version offer_id evidence_lane league source venue product original_review_id review_observation_index review_normalized_at normalized_at observed_at knowledge_observed_at publisher_server_time event category units player_name native_player_id canonical_player source_team_label selection predicate period overtime variant price price_changed_at market_polled_at source_pointer evidence rules category_inventory semantic_status availability public_admission ticket_eligible qualification'.split(' ');
const EVENT='id_namespace id event_version version_kind home away starts_at in_play source_pointer canonical_candidate start_difference_seconds forecast_match_status'.split(' ');
const EVIDENCE='url raw_sha256 raw_bytes metadata_sha256 request_started_at observed_at content_type retrieval_basis'.split(' ');
const URLS={catalog:'https://moviodds.com/catalog?sport=basketball',snapshot:'https://moviodds.com/snapshot?fi=',api:'https://moviodds.com/doc',sports:'https://moviodds.com/docs/sports/',rules:'https://help.bet365.com/s/en/sportsrules/basketball',roster:'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_rosters/rosters_2027.csv',schedule:'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_schedules/nba_schedule_2027.csv'};
const RULE_SCOPE='MoviOdds declares exclusively bet365 prices; ordinary full-game NBA DD/TD Yes/No, no quarter/first-basket/promotion exception applied.';
const RULES={
  period_overtime:'All pre-game bets include overtime unless otherwise stated.',
  player_overtime:'Overtime counts for any player props unless specified otherwise.',
  participation:'Relevant players (all quoted players in a multi-player market) must be dressed and see court-time for bets to have action (unless specified otherwise).',
  official_statistics_and_corrections:'Markets will be settled according to game stats from the respective official competition site published on the day of the game. Subsequent amendments do not affect settlement.',
  double_triple_double:'Double/Double, player must record 10 or more in two of the following 5 statistical categories. Triple/Double, player must record 10 or more in 3 of the following 5 statistical categories: Points, Rebounds, Assists, Blocked Shots, Steals.',
  push:'In 2-Way markets Push rules apply unless otherwise stated below. Stakes on single bets are returned, and in multiples/parlays the selection is treated as a non-runner.',
  scheduled_date:'All games must start on the scheduled date (local stadium time) for bets to have action.',
  interruption:'If a game is interrupted but subsequently resumed (from the point in the game at which it was interrupted) and played to a finish within 48 hours of the original scheduled game time, all bets will stand on the fixture.',
  abandonment:'Otherwise if the game is resumed but not finished within 48 hours of the original scheduled game time, this will be treated as an abandonment and bets on the original fixture will be void, except for those bets the outcome of which had already been determined, prior to the initial interruption in fixture.',
  minimum_duration:'There must be 5 minutes or less of scheduled game time left for bets to have action, unless the specific market outcome is already determined.',
  replayed:'If a game is interrupted for any reason, and is replayed in full, this will be treated as an abandonment and bets on the original fixture will be void, except for those bets the outcome of which had already been determined, prior to the initial interruption in fixture.'};
const require=(ok,message)=>{if(!ok)throw new Error(message);};
const fields=(v,names)=>v!==null&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join(',')===[...names].sort().join(',');
const text=(v,max=300)=>typeof v==='string'&&v.length>0&&v.length<=max&&v.trim()===v;
const sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const id=v=>text(v)&&/^[0-9]+$/.test(v);
const count=(v,max=10000)=>Number.isSafeInteger(v)&&v>=0&&v<=max;
const pointer=(v,kind,max)=>typeof v==='string'&&new RegExp('^/'+kind+'/(?:0|[1-9][0-9]*)$').test(v)&&Number(v.split('/').at(-1))<max;
const encode=v=>new TextEncoder().encode(v);
const same=(a,b)=>canonicalNativeOffer(a)===canonicalNativeOffer(b);
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label=v=>v.replace('T',' ').replace('Z',' UTC');
const decimalExceeds=(value,whole)=>{const[i,f='']=value.split('.'),n=BigInt(i),bound=BigInt(whole);return n>bound||(n===bound&&/[1-9]/.test(f));};

/** Separate local canonical JSON avoids a dependency cycle with public dispatch. */
export function canonicalNativeOffer(value){
  if(value===null||typeof value==='string'||typeof value==='boolean')return JSON.stringify(value);
  if(typeof value==='number'){require(Number.isSafeInteger(value),'Native record numbers must be bounded integers.');return JSON.stringify(value);}
  if(Array.isArray(value))return '['+value.map(canonicalNativeOffer).join(',')+']';
  require(value!==null&&typeof value==='object'&&Object.getPrototypeOf(value)===Object.prototype,'Invalid native record JSON value.');
  return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonicalNativeOffer(value[k])).join(',')+'}';
}

/** Source clocks retain nanoseconds; only the retained CSV may omit seconds. */
export function nativeOfferClock(value,{allowMinuteResolution=false}={}){
  require(typeof value==='string','Explicit UTC source clock required.');
  const m=/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?Z$/.exec(value);
  require(m&&(m[2]!==undefined||allowMinuteResolution),'Invalid source clock.');
  const whole=m[1]+':'+(m[2]??'00'),ms=Date.parse(whole+'Z');
  require(Number.isFinite(ms)&&new Date(ms).toISOString().slice(0,19)===whole,'Invalid source calendar clock.');
  return BigInt(ms)*1000000n+BigInt((m[3]??'').padEnd(9,'0')||'0');
}

export function validateNativeOffer(o,now=new Date().toISOString()){
  require(fields(o,TOP)&&o.schema_version===NATIVE_OFFER_SCHEMA&&['ACTUAL_SOURCE_REPLAY','SYNTHETIC_TEST'].includes(o.evidence_lane)
    &&o.league==='NBA'&&o.source==='MoviOdds'&&o.venue==='bet365'&&o.product==='standard basketball player markets'
    &&sha(o.original_review_id)&&sha(o.offer_id)&&count(o.review_observation_index,7)&&o.semantic_status==='COMPLETE_NATIVE_SOURCE_CONTRACT'
    &&o.availability==='OBSERVED_SNAPSHOT_NOT_CURRENT'&&o.public_admission===false&&o.ticket_eligible===false&&o.qualification==='UNAVAILABLE',
  'Unsupported native offer or self-granted eligibility.');
  const observed=nativeOfferClock(o.observed_at),knowledge=nativeOfferClock(o.knowledge_observed_at),server=nativeOfferClock(o.publisher_server_time);
  require(server<=observed&&observed<=knowledge&&knowledge<=nativeOfferClock(o.review_normalized_at)&&nativeOfferClock(o.review_normalized_at)<=nativeOfferClock(o.normalized_at)
    &&nativeOfferClock(o.normalized_at)<=nativeOfferClock(now),'Native offer clocks disagree.');
  const e=o.event;
  require(fields(e,EVENT)&&e.id_namespace==='moviodds'&&id(e.id)&&sha(e.event_version)&&e.version_kind==='OBSERVED_CATALOG_OBJECT_SHA256'
    &&text(e.home)&&text(e.away)&&e.home!==e.away&&e.in_play===false&&pointer(e.source_pointer,'fixtures',5000)&&observed<nativeOfferClock(e.starts_at),
  'Native event is missing or was not pregame at capture.');
  const c=e.canonical_candidate;
  require(fields(c,'namespace id starts_at home_id away_id roster_season source_pointer'.split(' '))&&c.namespace==='espn'
    &&[c.id,c.home_id,c.away_id].every(id)&&c.home_id!==c.away_id&&typeof c.roster_season==='string'&&/^20[0-9]{2}$/.test(c.roster_season)&&pointer(c.source_pointer,'csv/rows',5000),
  'Invalid separate canonical event candidate.');
  const deltaNs=nativeOfferClock(e.starts_at)-nativeOfferClock(c.starts_at,{allowMinuteResolution:true}),abs=deltaNs<0n?-deltaNs:deltaNs;
  const delta=deltaNs%1000000000n===0n?Number(deltaNs/1000000000n):`${deltaNs<0n?'-':''}${abs/1000000000n}.${String(abs%1000000000n).padStart(9,'0').replace(/0+$/,'')}`;
  require(same(e.start_difference_seconds,delta)&&c.starts_at.slice(0,10)===e.starts_at.slice(0,10)
    &&e.forecast_match_status===(deltaNs===0n?'CANONICAL_CANDIDATE_ONLY':'BLOCKED_EVENT_START_DISAGREEMENT'),
  'A native source contract cannot erase or resolve the canonical event conflict.');
  const p=o.canonical_player;
  require(o.native_player_id===null&&text(o.player_name)&&fields(p,'namespace id name team_id opponent_id source_pointer'.split(' '))&&p.namespace==='espn'
    &&p.name===o.player_name&&[p.id,p.team_id,p.opponent_id].every(id)&&p.team_id!==p.opponent_id
    &&same([p.team_id,p.opponent_id].sort(),[c.home_id,c.away_id].sort())&&pointer(p.source_pointer,'csv/rows',5000)
    &&o.source_team_label===(p.team_id===c.home_id?e.home:e.away),'Player identity/affiliation must retain its external canonical crosswalk.');
  const s=o.selection;
  require(['DD','TD'].includes(o.category)&&o.units===NBA_UNITS[o.category]&&fields(s,'group_id market_id selection_id label'.split(' '))
    &&[s.group_id,s.market_id,s.selection_id].every(id)&&s.group_id===(o.category==='DD'?'181463':'181464')&&['Yes','No'].includes(s.label)
    &&same(o.predicate,{kind:'BOOLEAN_STAT_ACHIEVEMENT',selection:s.label,at_least_ten_in_categories:o.category==='DD'?2:3,primitive_categories:['PTS','REB','AST','BLK','STL']})
    &&o.period==='full_game'&&o.overtime==='includes_overtime'&&o.variant==='standard_binary_player_achievement'&&pointer(o.source_pointer,'quotes',10000),
  'A native Boolean offer must not invent a numerical line or side.');
  const changed=nativeOfferClock(o.price_changed_at),confirmed=nativeOfferClock(o.market_polled_at);
  require(changed<=server&&confirmed<=server&&server-confirmed<=1800n*1000000000n,'Future or stale exact-market source clocks.');
  const price=o.price;
  require(fields(price,'kind value fractional_as_supplied status'.split(' '))&&price.kind==='sportsbook_decimal'
    &&(price.fractional_as_supplied===null||text(price.fractional_as_supplied,128)),'Invalid supplied price representation.');
  require(price.value===null||(typeof price.value==='string'&&price.value.length<=128&&/^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(price.value)
    &&!decimalExceeds(price.value,1000000)),'Invalid supplied decimal price; missing is not zero.');
  require(price.status===(price.value===null?'PRICE_UNAVAILABLE':decimalExceeds(price.value,1)?'OBSERVED_PRICE_NOT_QUALIFIED':'UNAVAILABLE_AT_CAPTURE'),
  'Source price status is not qualification.');
  require(fields(o.evidence,Object.keys(URLS)),'Exact seven original evidence references required.');
  let latest=0n;
  for(const[role,item]of Object.entries(o.evidence)){
    const release=['roster','schedule'].includes(role),media=release?['text/csv','application/octet-stream']:['catalog','snapshot'].includes(role)?['application/json']:['text/html'];
    require(fields(item,EVIDENCE)&&item.url===URLS[role]+(role==='snapshot'?e.id:'')&&sha(item.raw_sha256)&&sha(item.metadata_sha256)
      &&count(item.raw_bytes,2*1024*1024)&&item.raw_bytes>0&&media.includes(item.content_type)
      &&item.retrieval_basis===(release?'RETAINED_RELEASE_REDIRECT_CHAIN':'DIRECT_COMPLETE_HTTP_RESPONSE'),'Invalid original source binding.');
    const capture=nativeOfferClock(item.observed_at);require(nativeOfferClock(item.request_started_at)<=capture&&capture<=nativeOfferClock(o.review_normalized_at),'Original evidence clocks disagree.');
    if(capture>latest)latest=capture;
  }
  require(latest===knowledge&&o.evidence.snapshot.observed_at===o.observed_at,'Later supporting evidence cannot refresh capture.');
  const rules=o.rules;
  require(fields(rules,'extractor text_sha256 text_bytes passages applicability jurisdiction financial_settlement'.split(' '))&&rules.extractor==='bet365-static-rules-text-v1'
    &&sha(rules.text_sha256)&&count(rules.text_bytes,512*1024)&&rules.text_bytes>0&&rules.applicability===RULE_SCOPE&&rules.jurisdiction==='NOT_SUPPLIED_BY_FEED'
    &&rules.financial_settlement==='NOT_IMPLEMENTED_OR_QUALIFIED'&&fields(rules.passages,Object.keys(RULES)),'Incomplete or inapplicable rule set.');
  const spans=[];
  for(const[role,quote]of Object.entries(RULES)){
    const p=rules.passages[role];require(fields(p,['start','end','source_value'])&&count(p.start,rules.text_bytes)&&count(p.end,rules.text_bytes)
      &&p.source_value===quote&&p.end-p.start===encode(quote).byteLength,'Invalid exact rule passage binding.');spans.push([p.start,p.end]);
  }
  spans.sort((a,b)=>a[0]-b[0]);require(spans.every((s,i)=>i===0||spans[i-1][1]<=s[0]),'Rule passages overlap.');
  require(fields(o.category_inventory,ALL_NBA_CATEGORIES),'All thirteen categories plus PA must remain inventoried.');
  for(const[code,item]of Object.entries(o.category_inventory))require(fields(item,'observed parsed complete status'.split(' '))
    &&[item.observed,item.parsed,item.complete].every(v=>count(v))&&item.observed===item.parsed&&item.parsed>=item.complete
    &&(['DD','TD'].includes(code)||item.complete===0)&&item.status===(item.observed?'OBSERVED_IN_SAMPLE':'UNOBSERVED_IN_SAMPLE'),
  'Invalid full-category source inventory.');
  require(Object.values(o.category_inventory).reduce((a,b)=>a+b.observed,0)<=10000&&o.category_inventory[o.category].complete>0,'Source inventory cannot support this complete selection.');
  require(encode(canonicalNativeOffer(o)).byteLength<=MAX_NATIVE_OFFER_BYTES,'Native offer exceeds 32-KiB encoded ceiling.');
  return o;
}

export async function verifyNativeOfferHash(o,cryptoProvider=globalThis.crypto,now=new Date().toISOString()){
  validateNativeOffer(o,now);require(cryptoProvider?.subtle,'SHA-256 support required.');
  const unsigned=Object.fromEntries(Object.entries(o).filter(([key])=>key!=='offer_id'));
  const bytes=await cryptoProvider.subtle.digest('SHA-256',encode(canonicalNativeOffer(unsigned)));
  require(o.offer_id===Array.from(new Uint8Array(bytes),v=>v.toString(16).padStart(2,'0')).join(''),'Native offer digest mismatch.');return o;
}

export function validateNativeOffers(offers,now=new Date().toISOString()){
  require(Array.isArray(offers)&&offers.length<=MAX_NATIVE_OFFERS&&encode(canonicalNativeOffer(offers)).byteLength<=MAX_NATIVE_ASSET_BYTES,
    'Native offer asset exceeds 32-offer/256-KiB limits.');
  const ids=new Set(),selections=new Set();
  for(const o of offers){validateNativeOffer(o,now);const s=canonicalNativeOffer([o.source,o.event.id,o.selection.group_id,o.selection.market_id,o.selection.selection_id]);
    require(!ids.has(o.offer_id)&&!selections.has(s),'Duplicate native offer or selection identity.');ids.add(o.offer_id);selections.add(s);}
  return offers;
}

export function nativeOfferPubliclyAdmitted(o){
  return o!==null&&typeof o==='object'&&o.evidence_lane==='ACTUAL_SOURCE_REPLAY'&&Object.hasOwn(PUBLIC_REVIEWED_OFFER_IDS,o.offer_id);
}

export function renderNativeOffer(o,{now=new Date().toISOString(),published=false}={}){
  validateNativeOffer(o,now);const e=o.event,s=o.selection,p=o.canonical_player,synthetic=o.evidence_lane==='SYNTHETIC_TEST';
  require(typeof published==='boolean'&&(!published||!synthetic),'Development fixtures cannot render as published source contracts.');
  return `<article class="offer-card forecast-card native-offer local-observation" data-schema="${NATIVE_OFFER_SCHEMA}"><p class="review-eyebrow">${synthetic?'Fictional development example':'Recorded source contract'} · ${published?'published recorded snapshot':'unpublished snapshot'}</p>
    <h2>${esc(o.player_name)}</h2><p><strong>${esc(s.label)} — ${o.category==='DD'?'double-double':'triple-double'}</strong></p>
    <p>${esc(e.away)} at ${esc(e.home)} · source scheduled ${esc(label(e.starts_at))}.</p>
    <p>Full game, including overtime. Direct Boolean achievement: at least 10 in ${o.predicate.at_least_ten_in_categories} of PTS, REB, AST, BLK and STL. No numeric prop line is assigned.</p>
    <p>Independent publisher <strong>MoviOdds</strong>; venue declared by publisher <strong>bet365</strong>. Not affiliated with or endorsed by bet365. Snapshot evidence, not a live/current quote.</p>
    ${o.price.value===null?`<p><strong>Price unavailable (PRICE_UNAVAILABLE).</strong> Fractional field ${esc(o.price.fractional_as_supplied??'not supplied')} retained literally, without conversion.</p>`:`<p>Supplied standalone decimal: <strong>${esc(o.price.value)}</strong> · ${esc(o.price.status)}. Fractional source field ${esc(o.price.fractional_as_supplied??'not supplied')}. No executable price or EV is claimed.</p>`}
    <p>Captured ${esc(label(o.observed_at))}; latest supporting evidence ${esc(label(o.knowledge_observed_at))}; review normalized ${esc(label(o.review_normalized_at))}; offer normalized ${esc(label(o.normalized_at))}.</p>
    <p>Source price changed ${esc(label(o.price_changed_at))}; exact market confirmed ${esc(label(o.market_polled_at))}; publisher response ${esc(label(o.publisher_server_time))}.</p>
    <p>Forecast matching: <strong>${esc(e.forecast_match_status)}</strong>. Canonical candidate ESPN:${esc(e.canonical_candidate.id)} starts ${esc(label(e.canonical_candidate.starts_at))}; source minus candidate ${esc(e.start_difference_seconds)} seconds. This conflict does not invalidate the source-native contract, and it does not establish a forecast match.</p>
    <p>Player must be dressed and see court time. Venue settlement uses official competition statistics published on game day; later amendments do not change that settlement. DNP is not zero production. Statistical forecast grading and financial settlement are separate.</p>
    <p><strong>NO_ACTION.</strong> Qualification unavailable; ticket eligibility false. ${published?'Publication was checked separately; original observation and normalization clocks remain unchanged.':'Public admission is not granted by this record.'}</p>
    <details><summary>Source identities, rules and all category coverage</summary><p>Native event ${esc(e.id_namespace)}:${esc(e.id)}; event version ${esc(e.event_version)}. Canonical player ESPN:${esc(p.id)}, team ${esc(p.team_id)}, opponent ${esc(p.opponent_id)}; native permanent player ID not supplied. Source team ${esc(o.source_team_label)}.</p>
    <p>Native selection group ${esc(s.group_id)}, market ${esc(s.market_id)}, selection ${esc(s.selection_id)}, label ${esc(s.label)}; source pointer ${esc(o.source_pointer)}.</p>
    <p>Identity lookup: SportsDataverse sportsdataverse-data, ESPN-derived via hoopR, CC BY 4.0. NML normalized and filtered retained identity data; no direct ESPN access or endorsement is implied. Roster observed ${esc(label(o.evidence.roster.observed_at))}. Roster membership is not confirmed participation or estimated minutes.</p>
    <ul>${Object.entries(o.rules.passages).map(([key,p])=>`<li>${esc(key)}: ${esc(p.source_value)} (UTF-8 bytes ${p.start}–${p.end})</li>`).join('')}</ul>
    <p>Rules jurisdiction ${esc(o.rules.jurisdiction)}. Rules raw SHA-256 ${esc(o.evidence.rules.raw_sha256)}; extracted text ${esc(o.rules.text_sha256)}.</p>
    <table><thead><tr><th scope="col">Category</th><th scope="col">Observed</th><th scope="col">Complete</th></tr></thead><tbody>${ALL_NBA_CATEGORIES.map(c=>`<tr><th scope="row">${esc(c)}</th><td>${o.category_inventory[c].observed}</td><td>${o.category_inventory[c].complete}</td></tr>`).join('')}</tbody></table>
    ${Object.entries(o.evidence).map(([role,v])=>`<p>${esc(role)}: ${esc(v.url)} · observed ${esc(label(v.observed_at))}; ${v.raw_bytes} bytes; SHA-256 ${esc(v.raw_sha256)}; metadata ${esc(v.metadata_sha256)}.</p>`).join('')}
    <p>Original review ${esc(o.original_review_id)}, observation ${o.review_observation_index}; derived offer ${esc(o.offer_id)}. A digest is not source authentication or verified durable remote archival.</p></details></article>`;
}

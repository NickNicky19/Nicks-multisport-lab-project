// Private replay of MoviOdds observations. No live fetch, public admission or bet.
import {ALL_NBA_CATEGORIES,NBA_UNITS} from './research.mjs';
import {canonicalOffer} from './offers.mjs';

export const MOVIODDS_REVIEW_SCHEMA='nba-private-moviodds-offers-v1';
const TOP=['schema_version','scope','evidence_lane','source','venue_as_declared_by_source','product','normalized_at','observed_at','knowledge_observed_at','publisher_server_time','event','evidence','rules','counts','category_inventory','quarter_category_inventory','diagnostics','selection','observations','game_lines','limitations','public_admission','ticket_eligibility','qualification','review_id'];
const COUNTS=['source_selections','full_game_player_selections','parsed_player_selections','verified_player_selections','complete_local_contracts','displayed','game_selections','quarter_player_selections','other_selections'];
const ROW=['category','units','player_label','canonical_player','native_player_id','source_team_label','source_selection','predicate','period','overtime','variant','price','source_pointer','price_changed_at','market_polled_at','available_at_capture','gaps','semantic_status','ticket_eligible'];
const GROUPS={'181446':'PTS','181447':'AST','181448':'REB','181449':'3PM','181463':'DD','181464':'TD','182003':'PRA','182004':'PR','182005':'PA','182006':'RA','182007':'BLK+STL','182008':'BLK','182009':'STL'};
const URLS={catalog:'https://moviodds.com/catalog?sport=basketball',snapshot:'https://moviodds.com/snapshot?fi=',
  api:'https://moviodds.com/doc',sports:'https://moviodds.com/docs/sports/',rules:'https://help.bet365.com/s/en/sportsrules/basketball',
  roster:'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_rosters/rosters_2027.csv',
  schedule:'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_schedules/nba_schedule_2027.csv'};
// Versioned normative witnesses, shared in meaning with the offline producer.
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
const LIMITATIONS=['Snapshot only; not a current live board or installed collector.',
  'No native permanent player ID is supplied; canonical crosswalk uses retained SportsDataverse ESPN-derived roster.',
  'Numeric ladder labels alone do not establish >=, >, over/under or push semantics.',
  'Canonical schedule candidate and provider start remain separate; no fuzzy forecast match.',
  'Publisher invitation covers bounded private read/cache/replay; public derived-offer admission is separate.',
  'No executable quote, EV, minutes estimate, blowout probability or qualified ticket is created.'];
const require=(ok,message)=>{if(!ok)throw new Error(message);};
const fields=(v,names)=>v!==null&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join(',')===[...names].sort().join(',');
const text=(v,max=300)=>typeof v==='string'&&v.length>0&&v.length<=max&&v.trim()===v;
const sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const id=v=>text(v)&&/^[0-9]+$/.test(v);
const count=(v,max=10000)=>Number.isSafeInteger(v)&&v>=0&&v<=max;
const same=(a,b)=>canonicalOffer(a)===canonicalOffer(b);
const clockNow=()=>new Date().toISOString();
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label=v=>v.replace('T',' ').replace('Z',' UTC');
const nullableText=v=>v===null||text(v);
const decimal=v=>typeof v==='string'&&v.length<=128&&/^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(v)&&Number.isFinite(Number(v))&&Number(v)<=1000000;
const sourcePointer=v=>typeof v==='string'&&/^\/quotes\/(?:0|[1-9][0-9]*)$/.test(v);
const csvPointer=v=>typeof v==='string'&&/^\/csv\/rows\/(?:0|[1-9][0-9]*)$/.test(v)&&Number(v.split('/').at(-1))<5000;

/** Preserve source nanoseconds and the canonical schedule's declared resolution. */
export function movioddsClock(value,{allowMinuteResolution=false}={}){
  require(typeof value==='string','UTC source clock required.');
  const m=/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?Z$/.exec(value);
  require(m&&(m[2]!==undefined||allowMinuteResolution),'Invalid UTC source clock.');const seconds=m[1]+':'+(m[2]??'00');
  const ms=Date.parse(seconds+'Z');require(Number.isFinite(ms)&&new Date(ms).toISOString().slice(0,19)===seconds,'Invalid source calendar clock.');
  return BigInt(ms)*1000000n+BigInt((m[3]??'').padEnd(9,'0')||'0');
}

export const canonicalMovioddsReview=canonicalOffer;

export function validateMovioddsReview(review,now=clockNow()){
  require(fields(review,TOP)&&review.schema_version===MOVIODDS_REVIEW_SCHEMA&&review.scope==='LOCAL_REVIEW_ONLY'
    &&['ACTUAL_SOURCE_REPLAY','SYNTHETIC_TEST'].includes(review.evidence_lane)&&review.source==='MoviOdds'
    &&review.venue_as_declared_by_source==='bet365'&&review.product==='standard basketball player markets'
    &&review.public_admission===false&&review.ticket_eligibility===false&&review.qualification==='UNAVAILABLE'&&sha(review.review_id),'Invalid private MoviOdds scope.');
  const normalized=movioddsClock(review.normalized_at),observed=movioddsClock(review.observed_at),server=movioddsClock(review.publisher_server_time);
  require(server<=observed&&observed<=movioddsClock(review.knowledge_observed_at)&&movioddsClock(review.knowledge_observed_at)<=normalized&&normalized<=movioddsClock(now),'Private source/capture/normalization clocks disagree.');
  const event=review.event;
  require(fields(event,['id_namespace','id','event_version','version_kind','home','away','starts_at','in_play','source_pointer','canonical_candidate','start_difference_seconds','forecast_match_status'])
    &&event.id_namespace==='moviodds'&&id(event.id)&&sha(event.event_version)&&event.version_kind==='OBSERVED_CATALOG_OBJECT_SHA256'
    &&text(event.home)&&text(event.away)&&event.home!==event.away&&typeof event.in_play==='boolean'
    &&/^\/fixtures\/(?:0|[1-9][0-9]*)$/.test(event.source_pointer)&&Number(event.source_pointer.split('/').at(-1))<5000,'Invalid native source event.');
  const start=movioddsClock(event.starts_at),candidate=event.canonical_candidate;
  if(candidate===null)require(event.start_difference_seconds===null&&event.forecast_match_status==='NOT_MATCHED','Missing canonical event cannot be matched.');
  else{
    require(fields(candidate,['namespace','id','starts_at','home_id','away_id','roster_season','source_pointer'])&&candidate.namespace==='espn'
      &&[candidate.id,candidate.home_id,candidate.away_id].every(id)&&candidate.home_id!==candidate.away_id&&/^20[0-9]{2}$/.test(candidate.roster_season)
      &&csvPointer(candidate.source_pointer),'Invalid retained canonical event candidate.');
    const ns=start-movioddsClock(candidate.starts_at,{allowMinuteResolution:true}),absolute=ns<0n?-ns:ns;
    const delta=ns%1000000000n===0n?Number(ns/1000000000n):`${ns<0n?'-':''}${absolute/1000000000n}.${String(absolute%1000000000n).padStart(9,'0').replace(/0+$/,'')}`;
    require(candidate.starts_at.slice(0,10)===event.starts_at.slice(0,10)&&same(event.start_difference_seconds,delta)
      &&event.forecast_match_status===(ns===0n?'CANONICAL_CANDIDATE_ONLY':'BLOCKED_EVENT_START_DISAGREEMENT'),'Different event starts cannot produce a forecast match.');
  }
  require(fields(review.evidence,Object.keys(URLS)),'Exact seven retained evidence roles required.');
  let latest=0n;
  for(const[key,e]of Object.entries(review.evidence)){
    require(fields(e,['url','raw_sha256','raw_bytes','metadata_sha256','request_started_at','observed_at','content_type','retrieval_basis'])
      &&e.url===(key==='snapshot'?URLS[key]+event.id:URLS[key])&&sha(e.raw_sha256)&&sha(e.metadata_sha256)
      &&count(e.raw_bytes,2*1024*1024)&&e.raw_bytes>0&&text(e.content_type)
      &&e.retrieval_basis===(['roster','schedule'].includes(key)?'RETAINED_RELEASE_REDIRECT_CHAIN':'DIRECT_COMPLETE_HTTP_RESPONSE'),'Invalid retained source evidence.');
    const capture=movioddsClock(e.observed_at);require(movioddsClock(e.request_started_at)<=capture&&capture<=normalized,'Evidence capture clocks disagree.');
    if(capture>latest)latest=capture;
  }
  require(latest===movioddsClock(review.knowledge_observed_at)&&review.evidence.snapshot.observed_at===review.observed_at,'Later rule knowledge cannot refresh the original board observation.');
  const rules=review.rules;
  require(fields(rules,['extractor','text_sha256','text_bytes','passages','applicability','jurisdiction','financial_settlement'])
    &&rules.extractor==='bet365-static-rules-text-v1'&&sha(rules.text_sha256)&&count(rules.text_bytes,512*1024)&&rules.text_bytes>0
    &&rules.applicability==='MoviOdds declares exclusively bet365 prices; ordinary full-game NBA DD/TD Yes/No, no quarter/first-basket/promotion exception applied.'
    &&rules.jurisdiction==='NOT_SUPPLIED_BY_FEED'&&rules.financial_settlement==='NOT_IMPLEMENTED_OR_QUALIFIED'&&fields(rules.passages,Object.keys(RULES)),'Invalid rules applicability.');
  for(const[key,p]of Object.entries(rules.passages))require(fields(p,['start','end','source_value'])&&count(p.start,rules.text_bytes)&&count(p.end,rules.text_bytes)
    &&p.end>p.start&&p.source_value===RULES[key]&&new TextEncoder().encode(p.source_value).byteLength===p.end-p.start,'Invalid exact rule witness.');
  const c=review.counts;
  require(fields(c,COUNTS)&&Object.values(c).every(v=>count(v))&&c.source_selections===c.full_game_player_selections+c.game_selections+c.quarter_player_selections+c.other_selections
    &&c.parsed_player_selections===c.full_game_player_selections&&c.complete_local_contracts<=c.verified_player_selections&&c.verified_player_selections<=c.parsed_player_selections
    &&Array.isArray(review.observations)&&c.displayed===review.observations.length&&c.displayed===Math.min(8,c.parsed_player_selections)
    &&fields(review.selection,['limit','ordering'])&&review.selection.limit===8&&review.selection.ordering==='COMPLETE_FIRST_THEN_ORIGINAL_SOURCE_ORDER','Source selection inventory differs.');
  require(fields(review.category_inventory,ALL_NBA_CATEGORIES),'All thirteen NBA categories plus PA are required.');
  let full=0,complete=0;
  for(const[code,item]of Object.entries(review.category_inventory)){
    require(fields(item,['observed','parsed','complete','status'])&&[item.observed,item.parsed,item.complete].every(v=>count(v))
      &&item.parsed===item.observed&&item.complete<=item.parsed&&(['DD','TD'].includes(code)||item.complete===0)
      &&item.status===(item.observed?'OBSERVED_IN_SAMPLE':'UNOBSERVED_IN_SAMPLE'),'Invalid category support or contract counts.');
    full+=item.parsed;complete+=item.complete;
  }
  require(full===c.parsed_player_selections&&complete===c.complete_local_contracts&&review.category_inventory.TOV.observed===0,'Full inventory silently loses categories.');
  require(review.quarter_category_inventory&&typeof review.quarter_category_inventory==='object'&&!Array.isArray(review.quarter_category_inventory)
    &&Object.entries(review.quarter_category_inventory).every(([code,n])=>['PTS','REB','AST'].includes(code)&&count(n))
    &&Object.values(review.quarter_category_inventory).reduce((a,b)=>a+b,0)===c.quarter_player_selections,'Quarter inventory cannot be spliced into full-game support.');
  require(review.diagnostics&&typeof review.diagnostics==='object'&&!Array.isArray(review.diagnostics)
    &&Object.entries(review.diagnostics).every(([key,n])=>key==='OTHER_MARKET_GROUP'&&count(n))
    &&Object.values(review.diagnostics).reduce((a,b)=>a+b,0)===c.other_selections,'Unmapped source selections disappeared.');
  const selections=new Set(),pointers=new Set(),displayCounts={},completeCounts={};let selectedComplete=0,selectedCanonical=0,wasIncomplete=false,previous=[-1,-1];
  for(const row of review.observations){
    require(fields(row,ROW)&&ALL_NBA_CATEGORIES.includes(row.category)&&row.category!=='TOV'&&row.units===NBA_UNITS[row.category]
      &&text(row.player_label)&&row.native_player_id===null&&nullableText(row.source_team_label)&&row.period==='full_game'&&row.overtime==='includes_overtime'
      &&typeof row.available_at_capture==='boolean'&&row.ticket_eligible===false&&sourcePointer(row.source_pointer),'Invalid private player selection.');
    const s=row.source_selection;
    require(fields(s,['group_id','market_id','selection_id','label'])&&[s.group_id,s.market_id,s.selection_id].every(id)&&text(s.label)
      &&GROUPS[s.group_id]===row.category,'Native group/category or selection identity differs.');
    const identity=canonicalOffer([s.group_id,s.market_id,s.selection_id]);require(!selections.has(identity)&&!pointers.has(row.source_pointer),'Duplicate source selection.');
    selections.add(identity);pointers.add(row.source_pointer);
    const sourceIndex=Number(row.source_pointer.split('/').at(-1));require(sourceIndex<c.source_selections,'Source pointer exceeds whole snapshot.');
    const player=row.canonical_player;
    if(player!==null)require(candidate!==null&&fields(player,['namespace','id','name','team_id','opponent_id','source_pointer'])&&player.namespace==='espn'
      &&[player.id,player.team_id,player.opponent_id].every(id)&&player.name===row.player_label&&csvPointer(player.source_pointer)
      &&same([player.team_id,player.opponent_id].sort(),[candidate.home_id,candidate.away_id].sort())&&player.team_id!==player.opponent_id
      &&row.source_team_label===(player.team_id===candidate.home_id?event.home:event.away),'Canonical player/affiliation conflicts with retained identities.');
    if(player!==null)selectedCanonical++;
    const binary=['DD','TD'].includes(row.category)&&['Yes','No'].includes(s.label);
    require(binary?same(row.predicate,{kind:'BOOLEAN_STAT_ACHIEVEMENT',selection:s.label,at_least_ten_in_categories:row.category==='DD'?2:3,primitive_categories:['PTS','REB','AST','BLK','STL']})
      &&row.variant==='standard_binary_player_achievement':row.predicate===null&&row.variant==='numeric_ladder_operator_unverified','Do not invent a numeric threshold or operator for a Boolean/ladder selection.');
    const gap=[];if(player===null)gap.push('CANONICAL_PLAYER_AFFILIATION_UNVERIFIED');
    if(event.in_play||observed>=start)gap.push('NOT_A_VERIFIED_PREGAME_CAPTURE');
    if(!binary)gap.push('NUMERIC_SELECTION_OPERATOR_UNVERIFIED');if(!row.available_at_capture)gap.push('SUSPENDED_OR_UNCONFIRMED_MARKET');
    require(same(row.gaps,gap)&&row.semantic_status===(gap.length?'INCOMPLETE':'COMPLETE_LOCAL'),'Missing contract fields or pregame failure cannot be hidden.');
    const changed=movioddsClock(row.price_changed_at),confirmed=movioddsClock(row.market_polled_at);
    require(changed<=server&&confirmed<=server&&(!row.available_at_capture||server-confirmed<=1800n*1000000000n),'Future/stale market confirmation.');
    require(fields(row.price,['kind','value','fractional_as_supplied','status'])&&row.price.kind==='sportsbook_decimal'&&(row.price.value===null||decimal(row.price.value))
      &&(row.price.fractional_as_supplied===null||text(row.price.fractional_as_supplied,128))
      &&row.price.status===(row.price.value===null?'PRICE_UNAVAILABLE':row.available_at_capture&&Number(row.price.value)>1?'OBSERVED_PRICE_NOT_QUALIFIED':'UNAVAILABLE_AT_CAPTURE'),'Supplied price is not qualified economics.');
    const isComplete=gap.length===0,ordering=isComplete?0:1;require(!(wasIncomplete&&isComplete)&&sourceIndex>previous[ordering],'Preview ordering differs from the declared source-order rule.');
    previous[ordering]=sourceIndex;if(!isComplete)wasIncomplete=true;else{selectedComplete++;completeCounts[row.category]=(completeCounts[row.category]??0)+1;}
    displayCounts[row.category]=(displayCounts[row.category]??0)+1;
  }
  require(selectedComplete===Math.min(c.displayed,c.complete_local_contracts)&&selectedCanonical<=c.verified_player_selections,'Complete-first preview omits an example or exceeds verified-player counts.');
  for(const code of ALL_NBA_CATEGORIES)require((displayCounts[code]??0)<=review.category_inventory[code].parsed&&(completeCounts[code]??0)<=review.category_inventory[code].complete,'Selected category counts exceed complete-source inventory.');
  require(Array.isArray(review.game_lines)&&review.game_lines.length===c.game_selections,'Game lines silently truncated.');
  for(const row of review.game_lines){
    require(fields(row,['selection_id','market_id','market','side','label','handicap','odds_decimal_as_supplied','source_pointer','market_polled_at','available_at_capture'])
      &&id(row.selection_id)&&id(row.market_id)&&[row.market,row.side,row.label,row.handicap].every(nullableText)
      &&(row.odds_decimal_as_supplied===null||decimal(row.odds_decimal_as_supplied))&&sourcePointer(row.source_pointer)&&typeof row.available_at_capture==='boolean','Invalid literal game line.');
    const confirmed=movioddsClock(row.market_polled_at);require(confirmed<=server&&(!row.available_at_capture||server-confirmed<=1800n*1000000000n),'Unconfirmed game price.');
    const identity=canonicalOffer(['1453',row.market_id,row.selection_id]);require(!selections.has(identity),'Duplicate native game selection.');selections.add(identity);
    require(!pointers.has(row.source_pointer)&&Number(row.source_pointer.split('/').at(-1))<c.source_selections,'Game/source pointer conflict.');pointers.add(row.source_pointer);
  }
  require(same(review.limitations,LIMITATIONS)
    &&new TextEncoder().encode(canonicalOffer(review)).byteLength<=256*1024,'Missing limitations or encoded ceiling exceeded.');
  return review;
}

export async function verifyMovioddsReviewHash(review,cryptoProvider=globalThis.crypto){
  validateMovioddsReview(review);require(cryptoProvider?.subtle,'SHA-256 support required.');
  const unsigned=Object.fromEntries(Object.entries(review).filter(([key])=>key!=='review_id'));
  const bytes=await cryptoProvider.subtle.digest('SHA-256',new TextEncoder().encode(canonicalOffer(unsigned)));
  require(review.review_id===Array.from(new Uint8Array(bytes)).map(v=>v.toString(16).padStart(2,'0')).join(''),'Private MoviOdds review seal mismatch.');return review;
}

export function renderMovioddsReview(review,{now=clockNow()}={}){
  validateMovioddsReview(review,now);const e=review.event,c=review.counts,synthetic=review.evidence_lane==='SYNTHETIC_TEST';
  const cards=review.observations.map(row=>{const s=row.source_selection,p=row.predicate;return `<article class="local-observation" data-review-state="${row.semantic_status}">
    <p class="review-eyebrow">${row.semantic_status==='COMPLETE_LOCAL'?'Complete private semantic example':'Partial source observation'} · ${esc(row.category)}</p><h2>${esc(row.player_label)}</h2>
    <p><strong>${p?`${esc(p.selection)} — ${row.category==='DD'?'double-double':'triple-double'}`:`Source selection “${esc(s.label)}” · numeric operator UNKNOWN`}</strong></p>
    ${p?`<p>Direct Boolean achievement: at least 10 in ${p.at_least_ten_in_categories} of PTS, REB, AST, BLK and STL. This is a Yes/No selection; no numeric line is assigned.</p>`:'<p>The numeric ladder label alone does not establish OVER, UNDER, &gt;, ≥ or push meaning.</p>'}
    <p>Full game, including overtime. Source team: ${esc(row.source_team_label??'unverified')}. ${row.available_at_capture?'Source market confirmed/open at capture.':'Suspended or unconfirmed at capture.'} Current availability is unverified.</p>
    ${row.price.value===null?`<p><strong>Price unavailable (PRICE_UNAVAILABLE).</strong> Fractional field ${esc(row.price.fractional_as_supplied??'not supplied')} retained literally; no conversion or replacement price. No executable quote, EV or qualified ticket.</p>`:`<p>${row.price.status==='OBSERVED_PRICE_NOT_QUALIFIED'?'Supplied standalone decimal price':'Source decimal field, unavailable at capture'}: <strong>${esc(row.price.value)}</strong> (${esc(row.price.status)}). Literal source economics; no executable quote, EV or qualified ticket.</p>`}
    <p>Price last changed ${esc(label(row.price_changed_at))}. Exact market last confirmed ${esc(label(row.market_polled_at))}. An old change time does not itself mean stale.</p>
    <details><summary>Native/canonical identities and remaining gaps</summary><p>Native event moviodds:${esc(e.id)}; group ${esc(s.group_id)}; market ${esc(s.market_id)}; selection ${esc(s.selection_id)}; ${esc(row.source_pointer)}. Permanent native player ID: not supplied.</p>
    <p>${row.canonical_player?`Canonical player ESPN:${esc(row.canonical_player.id)}; team ${esc(row.canonical_player.team_id)}; opponent ${esc(row.canonical_player.opponent_id)}; roster ${esc(row.canonical_player.source_pointer)}.`:'Canonical player/affiliation unresolved.'}</p>
    <p>${row.gaps.length?'Remaining gaps: '+row.gaps.map(esc).join('; ')+'.':'Semantic example complete locally; event forecast matching and public admission remain separate.'}</p></details></article>`;}).join('');
  const candidate=e.canonical_candidate;
  return `<section class="local-offer-review"><header><p class="review-eyebrow">${synthetic?'SYNTHETIC DEVELOPMENT EXAMPLE':'Actual-source private replay'} · unpublished</p><h1>NBA recorded player props</h1>
    <p class="review-banner">PRIVATE SNAPSHOT — not a live/current feed, forecast or recommendation. ${synthetic?'Fictional test inputs; never an actual player offer.':''}</p>
    <p>Publisher: <strong>MoviOdds</strong>, an independent project. Source venue as declared by publisher: <strong>bet365</strong>. MoviOdds is not affiliated with or endorsed by bet365.</p>
    <h2>${esc(e.away)} at ${esc(e.home)}</h2><p>Native event ${esc(e.id)} · scheduled ${esc(label(e.starts_at))} · source in-play flag ${esc(e.in_play)}.</p>
    <p class="review-limit">Forecast matching: <strong>${esc(e.forecast_match_status)}</strong>. ${candidate?`Retained canonical candidate ESPN:${esc(candidate.id)} starts ${esc(label(candidate.starts_at))}; source minus candidate = ${esc(e.start_difference_seconds)} seconds. These starts are preserved separately; no fuzzy or automatic forecast match.`:'No canonical event candidate established.'}</p>
    <p>Original source capture: ${esc(label(review.observed_at))}. Publisher server: ${esc(label(review.publisher_server_time))}. Latest supporting evidence: ${esc(label(review.knowledge_observed_at))}. Normalized: ${esc(label(review.normalized_at))}.</p>
    <p>${c.source_selections} original selections; ${c.full_game_player_selections} full-game player selections; ${c.verified_player_selections} canonical player/affiliation matches; ${c.complete_local_contracts} complete private semantics; displaying ${c.displayed}. Quarter selections ${c.quarter_player_selections}; other selections ${c.other_selections}; game lines ${c.game_selections}.</p>
    <p>Identity lookup attribution: SportsDataverse <code>sportsdataverse-data</code> public NBA releases, ESPN-derived via hoopR, CC BY 4.0. NML normalized and filtered the retained lookup. This implies no endorsement or direct ESPN access grant. Retained roster capture ${esc(label(review.evidence.roster.observed_at))}; schedule capture ${esc(label(review.evidence.schedule.observed_at))}. These are identity evidence, not new live captures or confirmed participation.</p>
    <p><strong>NO_ACTION.</strong> Public admission false. Ticket eligibility false. Qualification unavailable. No financial settlement is implemented.</p></header>${cards}
    <section class="review-coverage"><h2>All 13 NBA categories plus PA</h2><p>Complete-source inventory. An unobserved category is not permanent source absence; numeric operator gaps remain unresolved.</p><div class="review-table"><table><thead><tr><th scope="col">Category</th><th scope="col">Observed</th><th scope="col">Parsed</th><th scope="col">Complete local</th><th scope="col">Sample state</th></tr></thead><tbody>${ALL_NBA_CATEGORIES.map(code=>{const r=review.category_inventory[code];return `<tr><th scope="row">${esc(code)}</th><td>${r.observed}</td><td>${r.parsed}</td><td>${r.complete}</td><td>${esc(r.status)}</td></tr>`;}).join('')}</tbody></table></div></section>
    <section class="review-coverage"><h2>Recorded game lines (${c.game_selections})</h2><p>Literal source fields; no estimated minutes or blowout probability is inferred.</p><div class="review-table"><table><thead><tr><th scope="col">Market</th><th scope="col">Side</th><th scope="col">Label / handicap</th><th scope="col">Supplied decimal</th><th scope="col">Selection / confirmation</th></tr></thead><tbody>${review.game_lines.map(r=>`<tr><th scope="row">${esc(r.market??'unsupplied')}</th><td>${esc(r.side??'unsupplied')}</td><td>${esc(r.label??'unsupplied')} / ${esc(r.handicap??'unsupplied')}</td><td>${r.odds_decimal_as_supplied===null?'Price unavailable (PRICE_UNAVAILABLE)':esc(r.odds_decimal_as_supplied)+' · unqualified'}</td><td>Market ${esc(r.market_id)} / selection ${esc(r.selection_id)} · ${esc(label(r.market_polled_at))} · ${r.available_at_capture?'confirmed/open at capture':'unavailable at capture'}</td></tr>`).join('')}</tbody></table></div></section>
    <details><summary>Rules, original sources and limitations</summary><p>Ordinary full-game player statistics include overtime; participation requires being dressed and seeing court time. Official competition statistics published on game day settle the market; subsequent amendments do not change its financial settlement. Push, postponement and interruption rules remain venue-specific. Jurisdiction is not supplied by the feed. These rules do not qualify a ticket or replace statistical forecast grading.</p>
    ${Object.entries(review.evidence).map(([key,v])=>`<p>${esc(key)}: ${esc(v.url)}; observed ${esc(label(v.observed_at))}; SHA-256 <code>${esc(v.raw_sha256)}</code> (${v.raw_bytes} bytes).</p>`).join('')}
    <ul>${review.limitations.map(v=>`<li>${esc(v)}</li>`).join('')}</ul><p>Review ${esc(review.review_id)}. Private original-byte replay is distinct from durable remote archival. No raw source feed is publicly published.</p></details></section>`;
}

// A view of independently validated publication records, never an issuance gate.
import {displayTarget} from './display.mjs';
import {isHistoryForecast,utcMicros} from './research.mjs';

const esc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const latest=values=>values.filter(Boolean).sort((a,b)=>utcMicros(a)<utcMicros(b)?-1:utcMicros(a)>utcMicros(b)?1:0).at(-1)??null;
const count=(n,word)=>`${n} ${word}${n===1?'':'s'}`;
const date=value=>new Intl.DateTimeFormat('en-GB',{dateStyle:'medium',timeStyle:'short',timeZone:'UTC'}).format(new Date(value))+' UTC';
const clock=(value,missing)=>value?`<time datetime="${esc(value)}" title="${esc(value)}">${esc(date(value))}</time>`:missing;

export function retainedProductionWarning(snapshot){
  const descriptor=snapshot?.manifest?.production_research;
  return snapshot?.productionResearch&&descriptor?.retained
    ?snapshot.manifest.production_research_error||descriptor.error||'The new recurring research update was not verified.'
    :null;
}

export function renderProductionPublicationNotice(snapshot){
  const error=snapshot?.productionResearchError||retainedProductionWarning(snapshot);
  if(!error)return '';
  const retained=Boolean(snapshot?.productionResearch&&snapshot.manifest?.production_research?.retained);
  return `<div class="notice warning"><strong>${retained?'Earlier verified NBA forecasts retained':'Recurring NBA research unavailable'}</strong><p>${esc(error)} ${retained?`Earlier research export generated ${clock(snapshot.manifest.production_research.generated_at,'at an unknown time')}. The new website publication does not refresh their source, issuance or result clocks.`:'Other verified publication channels remain available; no missing record is counted as issued.'}</p></div>`;
}

/** Counts refer to the loaded view. The production index also prevents a
 * different published date from being mistaken for no delivery anywhere.
 * Inputs here have already passed the snapshot's typed/hash validation.
 */
export function forecastDeliveryStatus(snapshot,{sports=snapshot?.sports??[],pairedForecasts=[],pairedGrades=[],now=Date.now()}={}){
  const nba=sports.filter(sport=>sport.league==='NBA');
  if(!snapshot||!nba.length)return null;
  const legacy=nba.flatMap(sport=>sport.forecasts);
  const captured=legacy.filter(f=>f.evidence_lane==='REAL_TIME_CAPTURED');
  const paired=pairedForecasts.filter(({row,forecast})=>row.admission.eligible&&forecast.mode==='REAL_TIME_CAPTURED'&&forecast.evidence_lane==='REAL_TIME_CAPTURED').map(({forecast})=>forecast);
  const daily=(snapshot.dailyResearch?.forecasts??[]).filter(row=>row.admission.eligible&&row.body.mode==='PROSPECTIVE_RESEARCH').map(row=>row.body);
  const recurring=(snapshot.productionResearch?.forecasts??[]).filter(row=>row.admission.eligible&&row.body.mode==='PROSPECTIVE_RESEARCH').map(row=>row.body);
  const genuine=[...new Map([...captured,...paired,...daily,...recurring].map(f=>[f.forecast_id,f])).values()];
  const upcoming=genuine.filter(f=>Date.parse(f.event_starts_at)>now).length;
  const historical=[...new Map([...legacy.filter(f=>isHistoryForecast(f,now)),...genuine.filter(f=>Date.parse(f.event_starts_at)<=now)].map(f=>[f.forecast_id,f])).values()];
  const historicalIds=new Set(historical.map(f=>f.forecast_id));
  const allGrades=[...nba.flatMap(sport=>sport.performance),...pairedGrades,...(snapshot.dailyResearch?.grades??[]).map(row=>row.body),...(snapshot.productionResearch?.grades??[]).map(row=>row.body)];
  const historicalGrades=new Set(allGrades.filter(g=>historicalIds.has(g.forecast_id)).map(g=>g.grade_id)).size;
  const index=snapshot.productionResearch?.index;
  const operations=index?.operations;
  const otherIndexedRecords=(index?.counts.genuine_forecasts??0)>recurring.length;
  const incomplete=Boolean(snapshot.productionResearchError||snapshot.dailyResearchError||snapshot.pairedResearchError||snapshot.errors?.some(e=>e.league==='NBA'));
  const reason=incomplete?'A forecast publication channel could not be verified. Available historical research remains accessible.'
    :operations?.reason||snapshot.dailyResearch?.reason||snapshot.pairedResearch?.reason||nba.flatMap(s=>s.future_availability?.reasons??[]).join(' ')
      ||'No timely pregame forecast with independently recovered records is present in this publication.';
  const captures=[operations?.last_source_capture_at,snapshot.pairedResearch?.clocks?.last_source_capture_at,
    ...(snapshot.dailyResearch?.inputs??[]).filter(input=>input.mode==='PROSPECTIVE_RESEARCH').flatMap(input=>input.sources.map(source=>source.retrieved_at)),
    ...captured.map(f=>f.prospective?.source_observed_max_at)];
  const sourceCaptureAt=latest(captures),issuedAt=latest([operations?.last_issued_at,...genuine.map(f=>f.issued_at)]);
  const neverDelivered=!incomplete&&genuine.length===0&&!otherIndexedRecords&&issuedAt===null;
  const next=incomplete?'Recover and verify the forecast publication before reporting its delivery status.'
    :otherIndexedRecords?'Select a published UTC game date in the recurring research panel to inspect other records. This summary covers the loaded view.'
      :sourceCaptureAt?'Publish timely pregame forecasts and their independent recovery evidence for an eligible upcoming game.'
        :'Capture and verify fresh inputs for an eligible upcoming game, then issue, recover and publish its research forecasts within the registered window.';
  const example=historical.filter(f=>f.evidence_lane==='RECONSTRUCTED_RESEARCH').map(f=>({forecast:f,display:displayTarget(f,snapshot.display)})).find(row=>row.display.nameBasis==='SOURCE_VERIFIED_DISPLAY')??null;
  return {upcoming,genuineLoaded:genuine.length,historical:historical.length,historicalGrades,neverDelivered,incomplete,otherIndexedRecords,reason,next,
    publicationAt:snapshot.manifest?.published_at??null,sourceCaptureAt,issuedAt,example,
    title:incomplete?'Forecast delivery status is incomplete':neverDelivered?'No live forecasts have been delivered':'No upcoming NBA forecasts in this view'};
}

export function renderForecastDelivery(snapshot,options={}){
  const status=forecastDeliveryStatus(snapshot,options);
  if(!status||status.upcoming>0)return '';
  const example=status.example;
  const historicalPreview=example?`<p class="delivery-example"><strong>Historical research example · ${esc(example.display.playerName)}</strong><br>${esc(example.display.matchup)} · ${esc(date(example.forecast.event_starts_at))}. Reconstructed research, not an upcoming prediction.</p>`:'';
  return `<section class="panel delivery-status" aria-label="NBA forecast delivery status"><div class="panel-heading"><h2>${esc(status.title)}</h2><span class="pill neutral">Research only</span></div>
    <p class="delivery-counts"><strong>${count(status.upcoming,'upcoming research forecast')}</strong> in the loaded NBA view. ${count(status.historical,'historical research bundle')} and ${count(status.historicalGrades,'historical statistical grade')} remain available.</p>
    ${status.historical?'<a class="button dark delivery-history-link" href="#/props/history">Open historical forecasts and grades <span aria-hidden="true">→</span></a>':''}
    ${historicalPreview}<p class="delivery-reason"><strong>Why Upcoming is empty:</strong> ${esc(status.reason)}</p><p><strong>Next required step:</strong> ${esc(status.next)}</p>
    <dl class="delivery-clocks"><div><dt>Website publication</dt><dd>${clock(status.publicationAt,'Unavailable')}</dd></div><div><dt>Last published forecast-input capture</dt><dd>${clock(status.sourceCaptureAt,'None recorded')}<span class="cell-sub">Historical preparation is separate; a capture is not issuance.</span></dd></div><div><dt>Last genuine forecast issuance</dt><dd>${clock(status.issuedAt,'None recorded')}</dd></div></dl>
    <p class="control-help">A configured schedule is not a successful run. Publishing the website does not create forecasts. Sportsbook offers, odds and paper-ticket qualification have separate requirements; missing odds do not block research forecasts.</p></section>`;
}

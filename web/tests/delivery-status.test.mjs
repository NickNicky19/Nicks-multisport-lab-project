// Invented publication shapes exercise display only; no generation or collection.
import test from 'node:test';
import assert from 'node:assert/strict';
import {forecastDeliveryStatus,renderForecastDelivery} from '../delivery-status.mjs';
import {typedFixture} from './fixtures.mjs';

const now=Date.parse('2000-01-02T00:00:00Z');
function fixture(){
  const {sport,manifest}=typedFixture();
  return {sports:[sport],manifest,errors:[],display:null,productionResearch:{forecasts:[],grades:[],index:{counts:{genuine_forecasts:0},operations:{reason:'The pregame window passed without verified forecast delivery. Missed records are not backfilled.',last_source_capture_at:null,last_issued_at:null}}}};
}
function row(id,{future=true,mode='PROSPECTIVE_RESEARCH',eligible=true}={}){
  return {admission:{eligible},body:{forecast_id:id,event_starts_at:future?'2000-01-03T00:00:00Z':'2000-01-01T00:00:00Z',issued_at:'1999-12-31T22:30:00Z',mode}};
}

test('zero delivery distinguishes publication, fresh capture and genuine issuance from historical preparation',()=>{
  const snapshot=fixture();snapshot.display={status:{latest_retained_input_capture:{observed_at:'1999-12-31T00:00:00Z'}},catalog:{players:[],events:[]}};
  const original=JSON.stringify(snapshot),status=forecastDeliveryStatus(snapshot,{now});
  assert.equal(status.upcoming,0);assert.equal(status.historical,1);assert.equal(status.historicalGrades,1);
  assert.equal(status.neverDelivered,true);assert.equal(status.sourceCaptureAt,null);assert.equal(status.issuedAt,null);
  assert.equal(status.publicationAt,snapshot.manifest.published_at);
  const html=renderForecastDelivery(snapshot,{now});
  assert.match(html,/No live forecasts have been delivered/);assert.match(html,/1 historical research bundle/);
  assert.match(html,/Why Upcoming is empty/);assert.match(html,/Missed records are not backfilled/);
  assert.match(html,/Capture and verify fresh inputs/);assert.match(html,/href="#\/props\/history"/);
  assert.match(html,/Last published forecast-input capture<\/dt><dd>None recorded/);
  assert.match(html,/Last genuine forecast issuance<\/dt><dd>None recorded/);
  assert.match(html,/A configured schedule is not a successful run/);assert.match(html,/missing odds do not block/);
  assert.equal(JSON.stringify(snapshot),original);
});

test('development and ineligible originals never produce genuine upcoming counts or issue clocks',()=>{
  const snapshot=fixture();snapshot.dailyResearch={forecasts:[row('dev',{mode:'DEVELOPMENT_ONLY'}),row('late',{eligible:false})],grades:[],inputs:[{mode:'DEVELOPMENT_ONLY',sources:[{retrieved_at:'2000-01-01T23:00:00Z'}]}]};
  snapshot.productionResearch.forecasts=[row('production-dev',{mode:'DEVELOPMENT_ONLY'}),row('production-late',{eligible:false})];
  const status=forecastDeliveryStatus(snapshot,{now,pairedForecasts:[{row:{admission:{eligible:false}},forecast:row('paired-late').body},{row:{admission:{eligible:true}},forecast:row('paired-dev',{mode:'DEVELOPMENT_ONLY'}).body}]});
  assert.equal(status.upcoming,0);assert.equal(status.genuineLoaded,0);assert.equal(status.issuedAt,null);assert.equal(status.sourceCaptureAt,null);
});

test('a genuine future delivery removes the empty banner without changing historical originals',()=>{
  const snapshot=fixture();snapshot.productionResearch.forecasts=[row('prospective')];snapshot.productionResearch.index.counts.genuine_forecasts=1;
  const before=JSON.stringify(snapshot);const status=forecastDeliveryStatus(snapshot,{now});
  assert.equal(status.upcoming,1);assert.equal(status.neverDelivered,false);assert.equal(renderForecastDelivery(snapshot,{now}),'');
  assert.equal(JSON.stringify(snapshot),before);
});

test('the existing paired channel keeps its actual REAL_TIME_CAPTURED mode and separate clocks',()=>{
  const snapshot=fixture(),forecast={...row('paired-genuine').body,mode:'REAL_TIME_CAPTURED',evidence_lane:'REAL_TIME_CAPTURED'};
  snapshot.pairedResearch={clocks:{last_source_capture_at:'1999-12-31T22:20:00Z'}};
  const options={now,pairedForecasts:[{row:{admission:{eligible:true}},forecast}]};
  const status=forecastDeliveryStatus(snapshot,options);assert.equal(status.upcoming,1);assert.equal(status.genuineLoaded,1);
  assert.equal(status.sourceCaptureAt,'1999-12-31T22:20:00Z');assert.equal(renderForecastDelivery(snapshot,options),'');
});

test('completed genuine forecasts and other indexed dates never become a never-delivered claim',()=>{
  const snapshot=fixture();snapshot.productionResearch.forecasts=[row('completed',{future:false})];snapshot.productionResearch.grades=[{body:{forecast_id:'completed',grade_id:'completed-grade'}}];snapshot.productionResearch.index.counts.genuine_forecasts=1;
  let status=forecastDeliveryStatus(snapshot,{now});assert.equal(status.upcoming,0);assert.equal(status.neverDelivered,false);assert.equal(status.historical,2);assert.equal(status.historicalGrades,2);
  assert.doesNotMatch(renderForecastDelivery(snapshot,{now}),/No live forecasts have been delivered/);
  snapshot.productionResearch.forecasts=[];status=forecastDeliveryStatus(snapshot,{now});
  assert.equal(status.otherIndexedRecords,true);assert.equal(status.neverDelivered,false);assert.match(status.next,/Select a published UTC game date/);
  snapshot.productionResearch.index.counts.genuine_forecasts=0;snapshot.productionResearch.index.operations.last_issued_at='2000-01-01T00:00:00Z';
  assert.equal(forecastDeliveryStatus(snapshot,{now}).neverDelivered,false);
});

test('channel recovery errors are unknown delivery status and hidden sport scopes stay hidden',()=>{
  const snapshot=fixture();snapshot.productionResearchError='A checksum did not verify.';
  const status=forecastDeliveryStatus(snapshot,{now});assert.equal(status.incomplete,true);assert.equal(status.neverDelivered,false);
  assert.match(renderForecastDelivery(snapshot,{now}),/Forecast delivery status is incomplete/);
  assert.doesNotMatch(renderForecastDelivery(snapshot,{now}),/No live forecasts have been delivered/);
  assert.equal(renderForecastDelivery(snapshot,{sports:[],now}),'');assert.equal(renderForecastDelivery(null,{now}),'');
});

test('source capture, actual issue and website clocks remain distinct and exact in markup',()=>{
  const snapshot=fixture();snapshot.productionResearch.index.operations.last_source_capture_at='2000-01-01T20:00:00Z';snapshot.productionResearch.index.operations.last_issued_at='2000-01-01T20:30:00Z';
  const status=forecastDeliveryStatus(snapshot,{now});assert.equal(status.sourceCaptureAt,'2000-01-01T20:00:00Z');assert.equal(status.issuedAt,'2000-01-01T20:30:00Z');assert.equal(status.publicationAt,'2000-01-01T00:00:00.000000Z');
  const html=renderForecastDelivery(snapshot,{now});for(const value of [status.sourceCaptureAt,status.issuedAt,status.publicationAt])assert.ok(html.includes(`datetime="${value}"`));
  assert.match(html,/Publish timely pregame forecasts/);
});

test('historical preview uses exact verified names and escapes untrusted status text',()=>{
  const snapshot=fixture(),f=snapshot.sports[0].forecasts[0];
  snapshot.display={catalog:{players:[{league:'NBA',id_namespace:f.id_namespace,player_id:f.player_id,display_name:'Verified <Centre>',source_ids:['retained-primary']}],events:[{league:'NBA',id_namespace:f.id_namespace,event_id:f.event_id,event_starts_at:f.event_starts_at,source_ids:['retained-event'],teams:[{team_id:f.team_id,display_name:'Old Home',home_away:'home'},{team_id:f.opponent_id,display_name:'Old Away',home_away:'away'}]}]}};
  snapshot.productionResearch.index.operations.reason='<script>invented status</script>';
  const html=renderForecastDelivery(snapshot,{now});assert.match(html,/Historical research example · Verified &lt;Centre&gt;/);assert.match(html,/Old Away @ Old Home/);assert.match(html,/Reconstructed research, not an upcoming prediction/);
  assert.match(html,/&lt;script&gt;invented status&lt;\/script&gt;/);assert.doesNotMatch(html,/<script>/);
  delete snapshot.display;assert.doesNotMatch(renderForecastDelivery(snapshot,{now}),/Historical research example/);
});

// Invented software-only originals adapted from the existing SDV validator
// fixtures. No source requests, genuine issuance, ledger write or admission.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
import {ALL_NBA_CATEGORIES, NBA_UNITS} from '../research.mjs';
import {verifyDailyHashes} from '../sdv-daily.mjs';
import {originalProduction, validateProductionCollection, verifyProductionHashes} from '../production.mjs';
import {offerResearchForecasts, matchResearchForecast, renderOffers} from '../offers.mjs';
import {typedFixture,hash} from './fixtures.mjs';
import {dailyFixtures, productionFixtures, contractFor, channelFixture} from './offer-research-fixtures.mjs';

test('price-free exact contract matching supports both independently validated SDV prospective lanes without changing originals',async()=>{
  for(const kind of ['daily','production']){
    const sample=channelFixture(kind),before=JSON.stringify(sample.raw),{body,input,at}=sample;
    if(kind==='daily')await verifyDailyHashes(sample.raw,webcrypto);
    else await verifyProductionHashes(sample.raw.index,sample.raw.pages,webcrypto);
    const views=await offerResearchForecasts(sample.channel,at,webcrypto),view=views.find(v=>v.original.forecast_id===body.forecast_id);
    assert.ok(view);assert.equal(view.original.evidence_lane,kind==='daily'?'DAILY_SNAPSHOT_PROSPECTIVE':'SDV_PRODUCTION_PROSPECTIVE');
    assert.equal(view.original.event_snapshot_id,input.event.event_snapshot_id);
    assert.equal(view.input.input_id,body.input_id);assert.equal(view.admission.eligible,true);
    assert.deepEqual(view.original,body);assert.equal(view.original.league,undefined);assert.equal(view.original.event_version,undefined);
    const offer=contractFor(body,input);
    for(const category of ALL_NBA_CATEGORIES){
      const result=matchResearchForecast({...offer,stat:category,units:NBA_UNITS[category]},view,at);
      assert.equal(result.status,'MATCHED_RESEARCH_ONLY',kind+' '+category);
      assert.equal(result.qualification,'UNAVAILABLE');assert.equal(result.ticket_eligible,false);assert.equal(result.ev,null);
    }
    assert.equal(JSON.stringify(sample.raw),before);
    assert.throws(()=>{view.original.evidence_lane='REAL_TIME_CAPTURED';},TypeError);
    assert.equal(matchResearchForecast(offer,structuredClone(view),at).status,'UNMATCHED');
    assert.equal(matchResearchForecast(offer,body,at).status,'UNMATCHED');
  }
});

test('SDV matching retains exact canonical namespaces, snapshot, subject, period, overtime and pregame clocks',async()=>{
  for(const kind of ['daily','production']){
    const {channel,body,input,at}=channelFixture(kind),view=(await offerResearchForecasts(channel,at,webcrypto))[0],offer=contractFor(body,input);
    for(const change of [{id_namespace:'sleeper'},{event_id:'999999'},{event_version:'f'.repeat(64)},
      {event_starts_at:'2026-10-30T00:00:00.000000Z'},{player_id:'999999'},{team_id:'999999'},
      {opponent_id:'999999'},{period:'first_quarter'},{extra_time_policy:'regulation_only'},
      {units:'rebounds'},{market_status:'IN_PLAY'},{evidence_lane:'RECONSTRUCTED_RESEARCH'},
      {observed_at:body.event_starts_at},{imported_at:body.event_starts_at}]){
      assert.equal(matchResearchForecast({...offer,...change},view,at).status,'UNMATCHED',kind+' '+JSON.stringify(change));
    }
    assert.equal(matchResearchForecast(offer,view,body.cutoff_at).status,'UNMATCHED');
    assert.equal(matchResearchForecast(offer,view,body.event_starts_at).status,'UNMATCHED');
  }
});

test('development previews and retained late or unacknowledged originals cannot match as admitted future forecasts',async()=>{
  assert.deepEqual(await offerResearchForecasts({daily:dailyFixtures.development()},'2026-10-23T00:10:00.000000Z',webcrypto),[]);
  const dev=productionFixtures.development();
  assert.deepEqual(await offerResearchForecasts({production:validateProductionCollection(dev.index,dev.pages)},dev.index.generated_at,webcrypto),[]);
  const daily=dailyFixtures.prospective(),dailyId=daily.forecasts[0].body.forecast_id;
  daily.generated_at='2026-10-23T00:06:00.000000Z';
  Object.assign(daily.forecasts[0].admission,{eligible:false,remote_recovery_completed_at:'2026-10-23T00:05:02.000000Z',reasons:['Actual recovery exceeded the allowed latency.']});
  daily.counts.eligible_forecasts=7;daily.status='PARTIAL';
  assert.equal((await offerResearchForecasts({daily:dailyFixtures.seal(daily,'asset_id')},daily.generated_at,webcrypto)).some(v=>v.original.forecast_id===dailyId),false);
  daily.forecasts[0].admission.remote_recovery_completed_at=null;
  assert.equal((await offerResearchForecasts({daily:dailyFixtures.seal(daily,'asset_id')},daily.generated_at,webcrypto)).some(v=>v.original.forecast_id===dailyId),false);
  const bundle=productionFixtures.prospective(),row=productionFixtures.of(bundle,'forecast')[0],productionId=row.original_id;
  Object.assign(row.admission,{eligible:false,remote_recovered_at:null,reasons:['Independent recovery remains unacknowledged.']});
  const repacked=productionFixtures.repack(bundle),collection=validateProductionCollection(repacked.index,repacked.pages);
  assert.equal((await offerResearchForecasts({production:collection},repacked.index.generated_at,webcrypto)).some(v=>v.original.forecast_id===productionId),false);
  row.admission.remote_recovered_at=productionFixtures.stamp(Date.parse(originalProduction(row).cutoff_at)+400000);
  const late=productionFixtures.repack(bundle,productionFixtures.all(bundle),productionFixtures.stamp(Date.parse(row.admission.remote_recovered_at)+1000));
  assert.equal((await offerResearchForecasts({production:validateProductionCollection(late.index,late.pages)},late.index.generated_at,webcrypto)).some(v=>v.original.forecast_id===productionId),false);
});

test('an eligible flag cannot bypass the original daily or production authority, input and persistence gates',async()=>{
  const daily=dailyFixtures.prospective();daily.forecasts[0].admission.remote_recovery_completed_at='2026-10-23T00:01:00.000000Z';
  for(const mutate of [a=>a.activation=null,a=>a.inputs[0].event.id_namespace='sleeper',a=>a.forecasts[0].body.event_snapshot_id='f'.repeat(64),
    a=>a.forecasts[0].admission.remote_recovery_completed_at=null,
    a=>{a.generated_at='2026-10-23T00:06:00.000000Z';a.forecasts[0].admission.remote_recovery_completed_at='2026-10-23T00:05:02.000000Z';}]){
    const changed=structuredClone(daily);mutate(changed);await assert.rejects(()=>offerResearchForecasts({daily:changed},changed.generated_at,webcrypto));
  }
  for(const mutate of [b=>{b.pages[0].records=b.pages[0].records.filter(r=>originalProduction(r).schema_version!=='nba-sdv-production-run-v1');},
    b=>{productionFixtures.of(b,'forecast')[0].admission.remote_recovered_at=null;},
    b=>{const r=productionFixtures.of(b,'forecast')[0];Object.assign(r,productionFixtures.wrap(r,{...originalProduction(r),event_snapshot_id:'f'.repeat(64)}));},
    b=>{const r=productionFixtures.of(b,'forecast')[0];r.admission.remote_recovered_at=productionFixtures.stamp(Date.parse(originalProduction(r).cutoff_at)+400000);b.index.generated_at=productionFixtures.stamp(Date.parse(r.admission.remote_recovered_at)+1000);}]){
    const bundle=productionFixtures.prospective();mutate(bundle);await assert.rejects(()=>offerResearchForecasts({production:{index:bundle.index,pages:bundle.pages}},bundle.index.generated_at,webcrypto));
  }
  const {channel,body,input,at}=channelFixture('production'),flat={...body,league:'NBA',id_namespace:'espn',event_version:body.event_snapshot_id};
  assert.equal(matchResearchForecast(contractFor(body,input),flat,at).status,'UNMATCHED');
  await assert.rejects(()=>offerResearchForecasts({production:{...channel.production,pages:undefined}},at,webcrypto));
});

test('matching views require original graph hashes as well as valid semantic contracts',async()=>{
  const daily=dailyFixtures.prospective();daily.asset_id='f'.repeat(64);
  await assert.rejects(()=>offerResearchForecasts({daily},daily.generated_at,webcrypto),/checksum/);
  const production=productionFixtures.prospective();
  production.index.pages[0].sha256='f'.repeat(64);
  production.index.pages[0].path=`sdv-production-page.${'f'.repeat(64)}.json`;
  const {index_id,...unsigned}=production.index;production.index={...unsigned,index_id:hash(unsigned)};
  await assert.rejects(()=>offerResearchForecasts({production:{...production,loaded_game_date:null}},production.index.generated_at,webcrypto),/hash|checksum/i);
});

test('later recovered views cannot match before required local, remote and publication availability',async()=>{
  for(const kind of ['daily','production']){
    const {channel,body,input,at}=channelFixture(kind),view=(await offerResearchForecasts(channel,at,webcrypto))[0],offer=contractFor(body,input);
    const local=view.admission.local_persistence_completed_at??view.admission.local_completed_at;
    const remote=view.admission.remote_recovery_completed_at??view.admission.remote_recovered_at;
    for(const decision of [body.issued_at,local,remote]){
      const result=matchResearchForecast(offer,view,decision);
      assert.equal(result.status,'UNMATCHED',kind+' '+decision);
      assert.match(result.reasons.join(' '),/publication or required durable recovery/);
    }
    assert.equal(matchResearchForecast(offer,view,at).status,'MATCHED_RESEARCH_ONLY');
  }
});

test('verification snapshots both source graphs before awaits and never changes caller-owned originals',async()=>{
  const daily=dailyFixtures.prospective(),production=productionFixtures.prospective(),beforeDaily=JSON.stringify(daily),beforeProduction=JSON.stringify(production);
  const at=production.index.generated_at;
  const checking=offerResearchForecasts({daily,production:{...production,loaded_game_date:null}},at,webcrypto);
  daily.asset_id='f'.repeat(64);daily.forecasts[0].body.player_label='Changed after the verification call';
  production.pages[0].records[0].record_json='{}';production.index.pages[0].sha256='f'.repeat(64);
  const views=await checking;
  assert.equal(views.length,10);assert.equal(views.some(v=>v.original.player_label==='Changed after the verification call'),false);
  assert.equal(JSON.stringify(daily)===beforeDaily,false);assert.equal(JSON.stringify(production)===beforeProduction,false);
  const intact=channelFixture('production'),before=JSON.stringify(intact.raw);
  await offerResearchForecasts(intact.channel,intact.at,webcrypto);
  assert.equal(JSON.stringify(intact.raw),before);
});

async function renderActualProps(snapshot,at){
  const names=['document','window','location','crypto','Date'],previous=new Map(names.map(name=>[name,Object.getOwnPropertyDescriptor(globalThis,name)]));
  const elements=new Map(['#main','#navigation','#breadcrumb'].map(id=>[id,{innerHTML:'',textContent:'',focus(){}}]));
  const NativeDate=Date;
  class FixedDate extends NativeDate {constructor(...args){super(...(args.length?args:[at]));}static now(){return NativeDate.parse(at);}}
  try{
    Object.defineProperty(globalThis,'Date',{value:FixedDate,configurable:true});
    Object.defineProperty(globalThis,'document',{value:{querySelector:id=>elements.get(id)??null,querySelectorAll:()=>[],title:''},configurable:true});
    Object.defineProperty(globalThis,'window',{value:{addEventListener(){},scrollTo(){}},configurable:true});
    Object.defineProperty(globalThis,'location',{value:{hash:'#/props/upcoming'},configurable:true});
    Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});
    const mock=`export async function loadSnapshot(){return ${JSON.stringify(snapshot)}};export async function loadProductionDate(){throw new Error('No request allowed in this render test')}`;
    const snapshotUrl='data:text/javascript;base64,'+Buffer.from(mock).toString('base64');
    const source=readFileSync(new URL('../app.mjs',import.meta.url),'utf8').replace(/(['"])\.\/([^'"]+\.mjs)\1/g,(_match,quote,name)=>quote+(name==='snapshot.mjs'?snapshotUrl:new URL('../'+name,import.meta.url).href)+quote);
    await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
    return elements.get('#main').innerHTML;
  }finally{for(const name of names){const descriptor=previous.get(name);if(descriptor)Object.defineProperty(globalThis,name,descriptor);else delete globalThis[name];}}
}

test('the actual Props renderer supplies eligible daily and production models to price-free offer cards',async()=>{
  for(const kind of ['daily','production']){
    const sample=channelFixture(kind),offer=contractFor(sample.body,sample.input),{sport,manifest}=typedFixture();
    manifest.published_at=sample.at;
    const snapshot={manifest,sports:[sport],errors:[],offers:{offers:[offer],unavailable_reasons:[]},
      dailyResearch:sample.channel.daily??null,productionResearch:sample.channel.production??null};
    const before=JSON.stringify(sample.raw),html=await renderActualProps(snapshot,sample.at);
    assert.match(html,/Synthetic Test Venue \/ Synthetic Test Product/);assert.match(html,/Price unavailable/);
    assert.match(html,/2 matching research forecasts/);assert.match(html,/Conditional on/);assert.match(html,/NO_ACTION/);
    assert.equal(JSON.stringify(sample.raw),before);
    const views=await offerResearchForecasts(sample.channel,sample.at,webcrypto);
    assert.match(renderOffers({offers:[offer]},{forecasts:views,now:sample.at}),/2 matching research forecasts/);
  }
});

test('a failed channel match proof stays visible without hiding offers or another verified channel',async()=>{
  const sample=channelFixture('production'),daily=dailyFixtures.prospective(),offer=contractFor(sample.body,sample.input),{sport,manifest}=typedFixture();
  daily.asset_id='f'.repeat(64);manifest.published_at=sample.at;
  const html=await renderActualProps({manifest,sports:[sport],errors:[],offers:{offers:[offer],unavailable_reasons:[]},dailyResearch:daily,productionResearch:sample.channel.production},sample.at);
  assert.match(html,/Some research line matches could not be verified/);assert.match(html,/Daily-snapshot matches unavailable/);
  assert.match(html,/2 matching research forecasts/);assert.match(html,/Synthetic Test Venue \/ Synthetic Test Product/);
  assert.match(html,/Price unavailable/);assert.match(html,/NO_ACTION/);
});

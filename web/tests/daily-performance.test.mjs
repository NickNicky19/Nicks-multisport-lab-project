import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {ALL_NBA_CATEGORIES} from '../research.mjs';
import {activeDailyGrades,renderDailyResearch} from '../sdv-daily.mjs';
import {DAILY_CALIBRATION_QUANTILES,summarizeDailyPerformance,renderDailyPerformance} from '../daily-performance.mjs';

// Invented metric inputs only. These are not issued records, evaluation data or
// fixtures for source/activation admission. Marginals share one synthetic law.
const categoryValues = i => ({PTS:3*i,PRA:23*i,REB:10*i,'3PM':i,AST:10*i,RA:20*i,PR:13*i,
  TOV:i,TD:0,DD:Number(i>0),BLK:i,STL:i,'BLK+STL':2*i,PA:13*i});
const law = [{i:0,p:.05},{i:1,p:.8},{i:2,p:.15}];
const close = (actual, expected) => assert.ok(Math.abs(actual-expected)<1e-12,`${actual} ≠ ${expected}`);
function categories() {
  return ALL_NBA_CATEGORIES.map(code=>{
    const atoms=new Map();
    for(const {i,p} of law){const value=categoryValues(i)[code];atoms.set(value,(atoms.get(value)||0)+p);}
    const pmf=[...atoms].map(([value,probability])=>({value,probability:String(probability)}));
    const q=tau=>{let p=0;return pmf.find(atom=>(p+=Number(atom.probability))>=tau).value;};
    return {code,pmf,mean:String(law.reduce((sum,{i,p})=>sum+categoryValues(i)[code]*p,0)),interval80:[q(.1),q(.9)]};
  });
}
function forecast(id,{model='R0',start='2026-10-24T03:00:00.000000Z',lead=120,mode='PROSPECTIVE_RESEARCH',eligible=true,commit='a'.repeat(40),label='Invented Player'}={}) {
  return {reference:{record_id:'forecast-'+id},admission:{eligible},body:{forecast_id:id,event_id:'event-'+id,
    event_snapshot_id:'event-version-'+id,player_id:'player-'+id,team_id:'home',opponent_id:'away',
    event_starts_at:start,issued_at:new Date(Date.parse(start)-lead*60000).toISOString().replace('Z','000Z'),mode,
    evidence_lane:mode==='PROSPECTIVE_RESEARCH'?'DAILY_SNAPSHOT_PROSPECTIVE':'DEVELOPMENT_ONLY',
    model_key:model,model_version:'invented-'+model,producer_version:'invented-producer-v1',
    producer_binding:{commit},history_panel_sha256:'b'.repeat(64),history_panel_cutoff:'2026-01-01T00:00:00Z',
    conditioning:'CONDITIONAL_ON_APPEARANCE',player_label:label,matchup:'Invented away @ Invented home',categories:categories()}};
}
function grade(row,{status='SCORED',id='grade-'+row.body.forecast_id,zero=false,observedIndex=1}={}) {
  const f=row.body,actual=categoryValues(observedIndex);
  return {reference:{record_id:id},body:{grade_id:id,forecast_id:f.forecast_id,outcome_id:'outcome-'+f.forecast_id,
    status,graded_at:'2026-10-25T05:00:00Z',categories:status==='SCORED'?f.categories.map(c=>{
      const observed=actual[c.code],probability=Number(c.pmf.find(a=>a.value===observed)?.probability||0);
      let crps=0;
      for(let value=0;value<Math.max(observed,c.pmf.at(-1).value);value++){
        const cdf=c.pmf.filter(a=>a.value<=value).reduce((sum,a)=>sum+Number(a.probability),0);
        crps+=(cdf-Number(observed<=value))**2;
      }
      return {code:c.code,observed,crps:String(crps),log_loss:zero?null:String(-Math.log(probability)),
        log_loss_status:zero?'ZERO_SUPPORT':'FINITE',brier:['DD','TD'].includes(c.code)?String((Number(c.mean)-observed)**2):null};
    }):[]}};
}
const asset = (forecasts,grades=[],outcomes=[],corrections=[]) => ({forecasts,grades,outcomes,corrections});
const summarize = (a,options={}) => summarizeDailyPerformance(a,activeDailyGrades(a),options);
const metric = (summary,code='PTS',index=0) => summary.groups[index].categories.find(row=>row.code===code);

test('descriptive category scores use unchanged coherent originals and separate R0/K0 revisions',()=>{
  const rows=[forecast('r0'),forecast('k0',{model:'K0'})],a=asset(rows,rows.map(row=>grade(row))),original=JSON.stringify(a);
  const summary=summarize(a);
  assert.deepEqual(summary.groups.map(g=>g.model_key),['K0','R0']);
  for(const group of summary.groups){
    assert.deepEqual(group.categories.map(c=>c.code),ALL_NBA_CATEGORIES);
    const pts=group.categories.find(c=>c.code==='PTS');
    close(pts.mae,.3);close(pts.bias,.3);close(pts.mean_crps,.075);close(pts.mean_log_loss,-Math.log(.8));
    assert.equal(pts.interval80_coverage,1);assert.equal(pts.mean_brier,null);
    close(group.categories.find(c=>c.code==='DD').mean_brier,.0025);
    assert.equal(group.categories.find(c=>c.code==='TD').mean_brier,0);
  }
  assert.equal(JSON.stringify(a),original,'Display summaries must not rewrite marginal laws or original records.');
  const other=forecast('r0-revision',{commit:'c'.repeat(40)});a.forecasts.push(other);a.grades.push(grade(other));
  assert.equal(summarize(a).groups.length,3,'Exact producer revisions must not be pooled.');
});

test('development, historical lanes and ineligible originals are excluded without zeroing unresolved subjects',()=>{
  const rows=[forecast('score'),forecast('dnp'),forecast('missing'),forecast('postponed'),forecast('cancelled'),forecast('nonfinal'),forecast('pending'),forecast('dev',{mode:'DEVELOPMENT_ONLY'}),forecast('late',{eligible:false}),forecast('history')];
  rows.at(-1).body.evidence_lane='RECONSTRUCTED_RESEARCH';
  const grades=[grade(rows[0]),grade(rows[1],{status:'DNP_NOT_SCORED'}),grade(rows[2],{status:'MISSING'}),grade(rows[3],{status:'POSTPONED'}),grade(rows[4],{status:'CANCELLED'}),grade(rows[5],{status:'NONFINAL'}),grade(rows[7]),grade(rows[8]),grade(rows[9])];
  const summary=summarize(asset(rows,grades));
  assert.deepEqual(summary.counts,{eligible:7,distinct_players:7,distinct_events:7,scored:1,dnp:1,pending:5,excluded_development:1,excluded_ineligible:1,excluded_other_lanes:1});
  assert.equal(metric(summary).n,1);assert.equal(summary.statuses.PENDING,1);
  const html=renderDailyPerformance(asset(rows,grades),grades);
  assert.match(html,/DNP is not zero/);assert.match(html,/Paired model records are not independent trials/);
  assert.doesNotMatch(html,/winning model<\/|qualified ticket<\//);
});

test('paired models do not double distinct players/events and namespaces keep unrelated IDs separate',()=>{
  const rows=[forecast('shared-r0'),forecast('shared-k0',{model:'K0'}),forecast('other-event'),forecast('other-namespace')];
  for(const row of rows){row.body.player_id='one-player';row.body.event_id='one-event';}
  rows[2].body.event_id='another-event';rows[3].body.player_id_namespace='invented-other';rows[3].body.event_id_namespace='invented-other';
  const a=asset(rows,rows.map(row=>grade(row))),summary=summarize(a);
  assert.equal(summary.counts.eligible,4);assert.equal(summary.counts.distinct_players,2);assert.equal(summary.counts.distinct_events,3);
  const k0=summary.groups.find(group=>group.model_key==='K0'),r0=summary.groups.find(group=>group.model_key==='R0');
  assert.equal(k0.counts.distinct_players,1);assert.equal(k0.counts.distinct_events,1);
  assert.equal(r0.counts.distinct_players,2);assert.equal(r0.counts.distinct_events,3);
  const html=renderDailyPerformance(a,activeDailyGrades(a));assert.match(html,/4 eligible prospective research bundles in these filters · 2 distinct players · 3 distinct events/);
});

test('corrections retain originals and only active replacement grades enter metrics',()=>{
  const row=forecast('corrected'),before=grade(row),replacement=grade(row,{id:'replacement',observedIndex:2});
  const a=asset([row],[before,replacement],[],[{original_ref:before.reference,replacement_ref:replacement.reference}]);
  assert.equal(activeDailyGrades(a).length,1);close(metric(summarize(a)).bias,-2.7);
  assert.equal(a.grades.length,2);
  const originalOutcome={reference:{record_id:'original-outcome'},body:{...row.body,outcome_id:before.body.outcome_id,status:'DNP'}};
  const correctedOutcome={reference:{record_id:'corrected-outcome'},body:{...row.body,outcome_id:'corrected-outcome-id',status:'NONFINAL'}};
  a.outcomes=[originalOutcome,correctedOutcome];a.grades=[before];a.corrections=[{original_ref:originalOutcome.reference,replacement_ref:correctedOutcome.reference}];
  const summary=summarize(a);assert.equal(summary.counts.scored,0);assert.equal(summary.counts.pending,1);
  assert.equal(summary.statuses.NONFINAL,1);assert.deepEqual(summary.groups[0].categories,[]);
});

test('model/category/UTC-date and actual issue lead-time filters respect inclusive boundaries',()=>{
  const rows=[forecast('under',{lead:89.999}),forecast('ninety',{lead:90}),forecast('one-eighty',{lead:180,model:'K0'}),forecast('next-date',{start:'2026-10-25T00:00:00.000000Z',lead:60})];
  rows[0].body.issued_at='2026-10-24T01:30:00.000001Z';
  const a=asset(rows,rows.map(row=>grade(row)));
  assert.equal(summarize(a,{leadTime:'UNDER_90'}).counts.eligible,2);
  assert.equal(summarize(a,{leadTime:'90_TO_180'}).counts.eligible,1);
  assert.equal(summarize(a,{leadTime:'180_PLUS'}).counts.eligible,1);
  const filtered=summarize(a,{model:'K0',category:'REB',dateFrom:'2026-10-24',dateTo:'2026-10-24'});
  assert.equal(filtered.counts.eligible,1);assert.deepEqual(filtered.groups[0].categories.map(c=>c.code),['REB']);
  assert.equal(summarize(a,{dateTo:'2026-10-24'}).counts.eligible,3);
  assert.equal(summarize(a,{dateFrom:'2026-10-25'}).counts.eligible,1);
  assert.equal(summarize(a,{dateFrom:'2026-02-30'}).valid,false);
  assert.equal(summarize(a,{dateFrom:'2026-10-25',dateTo:'2026-10-24'}).valid,false);
  assert.match(renderDailyPerformance(a,activeDailyGrades(a),{dateFrom:'2026-10-25',dateTo:'2026-10-24'}),/UTC start date must not follow/);
  rows[0].body.issued_at=rows[0].body.event_starts_at;
  assert.throws(()=>summarize(a),/issuance lead time/);
});

test('any zero-support observation keeps aggregate log loss infinite and reports its count',()=>{
  const rows=[forecast('supported'),forecast('zero')],a=asset(rows,[grade(rows[0]),grade(rows[1],{zero:true})]),summary=summarize(a);
  const pts=metric(summary);assert.equal(pts.n,2);assert.equal(pts.mean_log_loss,Infinity);assert.equal(pts.zero_support_count,1);
  assert.match(renderDailyPerformance(a,activeDailyGrades(a)),/∞ · 1 zero-support/);
  assert.throws(()=>summarizeDailyPerformance(a,[a.grades[0],a.grades[0]]),/Duplicate active daily grades/);
});

test('fixed quantile calibration compares observed CDF with exact tied forecast CDF rather than nominal tau',()=>{
  const row=forecast('calibration'),a=asset([row],[grade(row)]),calibration=metric(summarize(a)).calibration;
  assert.deepEqual(calibration.map(row=>row.quantile),DAILY_CALIBRATION_QUANTILES);
  close(calibration[0].mean_predicted_cdf,.85);close(calibration[1].mean_predicted_cdf,.85);close(calibration[2].mean_predicted_cdf,1);
  assert.deepEqual(calibration.map(row=>row.observed_fraction),[1,1,1]);
  assert.equal(metric(summarize(a),'TD').calibration[0].mean_predicted_cdf,1,'Degenerate binary ties use CDF 1.');
  // The median lands exactly on the second atom's decimal cumulative mass.
  row.body.categories[0].pmf=[{value:0,probability:'0.1'},{value:1,probability:'0.4'},{value:2,probability:'0.5'}];
  assert.equal(metric(summarize(a)).calibration[1].mean_predicted_cdf,.5);
});

test('rendered controls and identities escape text and preserve honest empty daily state',()=>{
  const row=forecast('escape',{label:'<script>bad & "name"</script>'}),a=asset([row]);
  const html=renderDailyPerformance(a,[]);
  assert.match(html,/&lt;script&gt;bad &amp; &quot;name&quot;&lt;\/script&gt;/);assert.doesNotMatch(html,/<script>/);
  for(const key of ['dailyModel','category','dailyLead','dailyDateFrom','dailyDateTo'])assert.match(html,new RegExp(`data-filter="${key}"`));
  assert.match(html,/No statistical grades are published for this daily-source cycle/);assert.match(html,/1 eligible prospective research bundles/);
  const malicious=renderDailyPerformance(a,[],{dateFrom:'" onfocus="alert(1)'});
  assert.doesNotMatch(malicious,/value="" onfocus=/);assert.match(malicious,/&quot; onfocus=&quot;/);
  const fixture=JSON.parse(readFileSync(new URL('../../tests/fixtures/sdv-daily-synthetic.json',import.meta.url),'utf8'));
  const preview=renderDailyResearch(fixture,{performance:true});
  assert.match(preview,/8 development bundles/);assert.match(preview,/0 eligible prospective research bundles/);assert.doesNotMatch(preview,/<th scope="col">MAE/);
  assert.equal(renderDailyResearch(fixture,{performance:true,nbaSelected:false}),'');
});

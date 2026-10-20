#!/usr/bin/env python3
"""Independent DEV005 receipt replay; no model fitting or forecast generation.

This verifier deliberately imports no multisport_lab code. It checks receipt
integrity, causal metadata and joint arithmetic, then recomputes aggregate scores,
whole-week bootstrap intervals and prespecified guards from retained score rows.
It verifies numerical-bound declarations, not a floating-point interval certificate
or the original upstream source's authenticity/historical publication clocks.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import random

MARKETS = ('PTS','PRA','REB','3PM','AST','RA','PR','TOV','TD','DD','BLK','STL','BLK+STL','PA')
MODELS = ('R0','K0','S0')
LEVELS = ('0.5','0.8','0.95')
SCALARS = ('observed','mean','median','crps','mean_absolute_error','mean_squared_error',
           'log_loss','observed_probability','zero_probability',
           'probability_above_upper95','observed_above_upper95')
INTERVALS = ('lower','upper','predicted_mass','covered','width')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate receipt key')
        result[key] = value
    return result


def load_receipt(path):
    raw = Path(path).read_bytes()
    if len(raw) > 16*1024*1024:
        raise ValueError('verification input exceeds 16MiB')
    envelope = json.loads(raw, object_pairs_hook=_pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    assert set(envelope) == {'schema_version','hash_format','payload_sha256','payload'}
    assert envelope['schema_version'] == 'decoded-json-receipt-v1'
    assert envelope['hash_format'] == 'sha256-canonical-decoded-json-v1'
    assert envelope['payload_sha256'] == fingerprint(envelope['payload'])
    return envelope['payload'], hashlib.sha256(raw).hexdigest()


def moment(values):
    values = list(values)
    assert values
    return math.fsum(values)/len(values)


def quantile(values, probability):
    ordered = sorted(values)
    fractional = probability*(len(ordered)-1)
    lower, remainder = divmod(fractional, 1)
    lower = int(lower)
    return ordered[lower]*(1-remainder)+ordered[min(lower+1,len(ordered)-1)]*remainder


class Checks:
    def __init__(self):
        self.count = 0
        self.maximum_absolute_difference = 0.0

    def same(self, actual, expected, where=''):
        if isinstance(expected, dict):
            for key, value in expected.items():
                assert key in actual, (where, key, 'missing')
                self.same(actual[key], value, where+'/'+str(key))
        elif isinstance(expected, (list,tuple)):
            assert len(actual) == len(expected), where
            for index,(a,b) in enumerate(zip(actual,expected)):
                self.same(a,b,where+'/'+str(index))
        elif isinstance(expected, float):
            assert isinstance(actual,(float,int)) and math.isfinite(actual), (where,actual)
            delta = abs(actual-expected)
            self.maximum_absolute_difference = max(self.maximum_absolute_difference,delta)
            assert math.isclose(actual,expected,rel_tol=1e-10,abs_tol=1e-9), (where,actual,expected)
            self.count += 1
        else:
            assert actual == expected, (where,actual,expected)
            self.count += 1


def decode(row, model, market):
    scalar, intervals, binary = row['categories'][model][market]
    result = dict(zip(SCALARS,scalar,strict=True))
    result['intervals'] = {level:dict(zip(INTERVALS,values,strict=True))
                           for level,values in zip(LEVELS,intervals,strict=True)}
    if market in ('DD','TD'):
        result['probability'],result['brier'] = binary
    else:
        assert binary is None
    return result


def interval_summary(rows):
    return {level:{'observed_coverage':moment(r[level]['covered'] for r in rows),
                   'mean_predicted_mass':moment(r[level]['predicted_mass'] for r in rows),
                   'mean_width':moment(r[level]['width'] for r in rows)} for level in LEVELS}


def aggregate(rows, model):
    categories = {}
    for market in MARKETS:
        scores = [decode(row,model,market) for row in rows]
        finite = [score['log_loss'] for score in scores if score['log_loss'] is not None]
        unsupported = len(scores)-len(finite)
        value = {'scored_count':len(scores),'mean_crps_rps':moment(s['crps'] for s in scores),
            'mean_absolute_error_of_mean':moment(s['mean_absolute_error'] for s in scores),
            'rmse_of_mean':math.sqrt(moment(s['mean_squared_error'] for s in scores)),
            'mean_absolute_error_of_median':moment(abs(s['median']-s['observed']) for s in scores),
            'mean_log_loss':None if unsupported else moment(finite),
            'log_loss_status':'INFINITE_ZERO_SUPPORT' if unsupported else 'FINITE',
            'zero_support_log_loss_count':unsupported,'finite_log_loss_count':len(finite),
            'finite_log_loss_sum':math.fsum(finite),
            'observed_zero_rate':moment(s['observed']==0 for s in scores),
            'mean_predicted_zero_probability':moment(s['zero_probability'] for s in scores),
            'observed_above_upper95_rate':moment(s['observed_above_upper95'] for s in scores),
            'mean_predicted_probability_above_upper95':moment(s['probability_above_upper95'] for s in scores),
            'intervals':interval_summary([s['intervals'] for s in scores])}
        if market in ('DD','TD'):
            value.update(mean_brier=moment(s['brier'] for s in scores),
                         observed_event_rate=moment(s['observed'] for s in scores),
                         mean_predicted_probability=moment(s['probability'] for s in scores))
        categories[market] = value
    minutes = [row['reported_minutes'][model]['diagnostics'] for row in rows]
    return {'categories':categories,'minutes':{
        'mean_crps':moment(m['crps'] for m in minutes),
        'mean_absolute_error_of_mean':moment(m['mean_absolute_error'] for m in minutes),
        'rmse_of_mean':math.sqrt(moment(m['mean_squared_error'] for m in minutes)),
        'intervals':interval_summary([m['intervals'] for m in minutes])}}


def clustered(values_by_week, counts, adjusted=False):
    generator = random.Random(20261020005)
    draws = []
    for _ in range(2000):
        # random.choices is intentionally not used: its RNG path differs.
        selected = [generator.randrange(8) for _ in range(8)]
        draws.append(math.fsum(values_by_week[i] for i in selected)/sum(counts[i] for i in selected))
    result = {'cluster_percentile95_lower':quantile(draws,.025),
              'cluster_percentile95_upper':quantile(draws,.975)}
    if adjusted:
        result['one_sided_Bonferroni14_upper'] = quantile(draws,1-.05/14)
    return math.fsum(values_by_week)/sum(counts),result


def verify(result, protocol, root):
    checks = Checks()
    checks.same(result['protocol_payload_sha256'],fingerprint(protocol))
    checks.same(result['implementation_source_sha256'],protocol['implementation_source_sha256'])
    for name,expected in protocol['implementation_source_sha256'].items():
        checks.same(hashlib.sha256((root/name).read_bytes()).hexdigest(),expected,'source/'+name)
    checks.same(result['inventory'],protocol['inventory'],'inventory')
    checks.same(result['post_score_exclusions'],0)
    rows = result['row_records']
    checks.same(len(rows),protocol['inventory']['selected_appearances'])
    checks.same(result['scored_appearances_per_model'],len(rows))
    weeks = [w['week_start'] for w in protocol['inventory']['weekly_inventory']]
    checks.same(len(weeks),8)
    counts = [sum(r['week']==week for r in rows) for week in weeks]
    checks.same(result['bootstrap']['week_counts'],counts)
    checks.same(len({r['event_id'] for r in rows}),16)
    checks.same(len({(r['event_id'],r['player_id']) for r in rows}),len(rows))
    for week in protocol['inventory']['weekly_inventory']:
        for game in week['games']:
            checks.same(sum(r['event_id']==game['event_id'] for r in rows),game['appearances'])
            selection = f"NBA-ALL13-JOINT-DEV-005|20261020005|{week['week_start']}|{game['event_id']}"
            checks.same(hashlib.sha256(selection.encode()).hexdigest(),game['selection_sha256'])
    cohort = [{'week':r['week'],'event':r['event_id'],'player':r['player_id'],'start':r['event_start']} for r in rows]
    checks.same(fingerprint(cohort),protocol['inventory']['selected_cohort_identity_sha256'])
    start = datetime.fromisoformat(result['run_started_at'].replace('Z','+00:00'))
    finish = datetime.fromisoformat(result['run_finished_at'].replace('Z','+00:00'))
    for row in rows:
        event = datetime.fromisoformat(row['event_start'].replace('Z','+00:00'))
        cutoff = datetime.fromisoformat(row['cutoff'].replace('Z','+00:00'))
        freeze = datetime.fromisoformat(row['history_freeze'].replace('Z','+00:00'))
        trained = datetime.fromisoformat(row['trained_through'].replace('Z','+00:00'))
        assert cutoff == event-timedelta(minutes=90)
        assert freeze == cutoff.replace(hour=0,minute=0,second=0,microsecond=0)
        assert trained <= freeze
        for clock in row['generation_clocks'].values():
            assert start <= datetime.fromisoformat(clock.replace('Z','+00:00')) <= finish
        checks.same(row['reported_minutes']['S0'],row['reported_minutes']['K0'],'row/minutes')
        fitted = row['S0_fitting_metadata']
        for name,mu in fitted['generator_primitive_means'].items():
            expected = (fitted['effective_sample_size']*fitted['empirical_primitive_means'][name]+.5)/(fitted['effective_sample_size']+.5)
            checks.same(mu,expected,'row/mu')
            assert mu > 0
        for market,diagnostic in row['S0_numerical_diagnostics'].items():
            assert diagnostic['renormalized'] is False
            assert diagnostic['crps_omission_upper_bound'] <= 1e-9
            assert abs(diagnostic['generator_mass_residual']) <= diagnostic['generator_omitted_mass_upper_bound']+1e-10
        assert row['S0_dependence_diagnostics']['score_omission_upper_bound'] <= 1e-9
        for model in MODELS:
            decoded = {m:decode(row,model,m) for m in MARKETS}
            for column in ('observed','mean'):
                values = {m:d[column] for m,d in decoded.items()}
                for total,components in [('PRA',('PTS','REB','AST')),('RA',('REB','AST')),
                    ('PR',('PTS','REB')),('PA',('PTS','AST')),('BLK+STL',('BLK','STL'))]:
                    checks.same(values[total],math.fsum(values[c] for c in components),'row/coherence')
                assert values['TD'] <= values['DD']+1e-12
            for market in ('DD','TD'):
                score = decoded[market]
                checks.same(score['brier'],(score['probability']-score['observed'])**2,'row/brier')
                checks.same(score['crps'],score['brier'],'row/binary_rps')
            if model == 'S0':
                assert all(math.isfinite(d['log_loss']) for d in decoded.values())
    aggregates = {}
    for model in MODELS:
        aggregates[model] = aggregate(rows,model)
        checks.same(result['models'][model],aggregates[model],'aggregate/'+model)
        for market in MARKETS:
            checks.same(result['models'][model]['categories'][market]['finite_probability_underflow_count'],
                sum(decode(r,model,market)['observed_probability'] is None and
                    decode(r,model,market)['log_loss'] is not None for r in rows),'underflow/'+model+'/'+market)
        checks.same(result['models'][model]['primitive_variogram_power1_mean'],
                    moment(r['primitive_variogram_power1'][model] for r in rows))
        for week in weeks:
            checks.same(result['weekly_metrics'][model][week],aggregate([r for r in rows if r['week']==week],model),
                        'weekly/'+model+'/'+week)
    for first,second in [('S0','K0'),('S0','R0'),('K0','R0')]:
        label = first+'_minus_'+second
        for market in MARKETS:
            sums = [math.fsum(decode(r,first,market)['crps']-decode(r,second,market)['crps']
                for r in rows if r['week']==week) for week in weeks]
            mean,bounds = clustered(sums,counts,True)
            bounds['mean_difference_'+label] = mean
            checks.same(result['paired_per_category_crps'][label][market],bounds,'bootstrap/'+label+'/'+market)
        sums = [math.fsum(r['primitive_variogram_power1'][first]-r['primitive_variogram_power1'][second]
                for r in rows if r['week']==week) for week in weeks]
        mean,bounds = clustered(sums,counts)
        bounds['mean'] = mean
        checks.same(result['primitive_variogram_paired_week_cluster_uncertainty'][label],bounds,'variogram/'+label)
    for market in ('DD','TD'):
        binary = result['DD_TD_week_cluster_uncertainty'][market]
        sums = [math.fsum(decode(r,'R0',market)['observed'] for r in rows if r['week']==w) for w in weeks]
        mean,bounds = clustered(sums,counts)
        bounds['mean'] = mean
        checks.same(binary['observed_event_rate'],bounds,'binary/observed/'+market)
        for model in MODELS:
            sums = [math.fsum(decode(r,model,market)['probability'] for r in rows if r['week']==w) for w in weeks]
            mean,bounds = clustered(sums,counts)
            bounds['mean'] = mean
            checks.same(binary['predicted_probability'][model],bounds,'binary/predicted/'+market+'/'+model)
    k95 = aggregates['K0']['minutes']['intervals']['0.95']
    r95 = aggregates['R0']['minutes']['intervals']['0.95']
    common = []
    if abs(k95['observed_coverage']-k95['mean_predicted_mass']) > .03:
        common.append('COMMON_K0_WORKLOAD95_CALIBRATION_GAP_GT0.03')
    if k95['observed_coverage'] < r95['observed_coverage']-.01:
        common.append('COMMON_K0_WORKLOAD95_COVERAGE_GT0.01_BELOW_R0')
    checks.same(result['common_workload_guard']['failed_requirements'],common)
    for market in MARKETS:
        c = aggregates['S0']['categories'][market]
        failures = list(common)
        if result['paired_per_category_crps']['S0_minus_K0'][market]['one_sided_Bonferroni14_upper'] >= 0:
            failures.append('PRIMARY_ADJUSTED_UPPER_NOT_NEGATIVE')
        if c['zero_support_log_loss_count']:
            failures.append('NONFINITE_LIKELIHOOD')
        if abs(c['observed_zero_rate']-c['mean_predicted_zero_probability']) > .05:
            failures.append('ZERO_CALIBRATION_GAP_GT0.05')
        if any(abs(i['observed_coverage']-i['mean_predicted_mass']) > .05 for i in c['intervals'].values()):
            failures.append('INTERVAL_CALIBRATION_GAP_GT0.05')
        if c['observed_above_upper95_rate']-c['mean_predicted_probability_above_upper95'] > .02:
            failures.append('UPPER95_TAIL_GAP_GT0.02')
        observed = [decode(r,'S0',market)['observed'] for r in rows]
        if market in ('DD','TD') and min(sum(observed),len(observed)-sum(observed)) < 20:
            failures.append('RARE_BINARY_COUNTS_LT20_POSITIVE_OR_NEGATIVE')
        if market == 'BLK' and sum(v != 0 for v in observed) < 20:
            failures.append('BLK_NONZERO_COUNT_LT20')
        checks.same(result['category_exploratory_requirements'][market],{
            'failed_requirements':failures,'all_exploratory_requirements_met':not failures,
            'observed_positive_count':sum(v>0 for v in observed),
            'observed_zero_count':sum(v==0 for v in observed)},'guards/'+market)
    assert result['runtime_wall_seconds'] <= 900
    assert result['process_peak_rss_linux_kib'] <= 512*1024
    return {'status':'PASS_INDEPENDENT_REPLAY','checked_values':checks.count,
            'maximum_absolute_numeric_difference':checks.maximum_absolute_difference,
            'rows':len(rows),'games':16,'week_clusters':8,'categories':list(MARKETS),
            'model_fitting_or_forecast_generation':False,
            'upstream_authenticity_or_historical_asof_claim':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result,result_sha = load_receipt(args.result)
    protocol,protocol_sha = load_receipt(args.protocol)
    report = verify(result,protocol,args.root)
    report.update(result_raw_sha256=result_sha,protocol_raw_sha256=protocol_sha,
                  verified_at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'))
    print(json.dumps(report,sort_keys=True,allow_nan=False))


if __name__ == '__main__':
    main()

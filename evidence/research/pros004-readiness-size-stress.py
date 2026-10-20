"""Size/integrity-only synthetic stress using retained non-issuance PMFs.
No capture, fit, issuance, actual outcome, comparative result or publication.
"""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

from multisport_lab import baseline, pros004_producer as prod, pros004_records as rec
from multisport_lab.integrity import canonical, digest, read_receipt, stamp, write_receipt, IntegrityError
from multisport_lab.ledger import LedgerRef
from multisport_lab.nba_data import NBAPlayerGame, COUNT_FIELDS
from multisport_lab.pros004_readiness import _synthetic_clock

REPO=Path('/workspace/nml-pros004-readiness')
SOURCE=Path('/tmp/nml-pros004-final-store')
SOURCE_REPORT=Path('/tmp/nml-pros004-final-report.json')
TARGET=Path('/tmp/nml-pros004-full-pmf-size-store-v2')
RECOVERY=Path('/tmp/nml-pros004-full-pmf-size-readback-v2')
OUTPUT=Path('/tmp/nml-pros004-full-pmf-size-diagnostic.json')

def require(condition,message):
    if not condition: raise IntegrityError(message)

def files(root):
    return {str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((root/'records').glob('*/*.json'))}

def refuse_fit(*args,**kwargs):
    raise IntegrityError('Size stress must never fit or regenerate a model')

actual_started=datetime.now(timezone.utc)
source_before=files(SOURCE)
require(len(source_before)==31,'Expected exact finalized31-record diagnostic source')
report_raw_before=hashlib.sha256(SOURCE_REPORT.read_bytes()).hexdigest()
report=read_receipt(SOURCE_REPORT)
for name,sha in report['source_sha256'].items():
    require(hashlib.sha256((REPO/name).read_bytes()).hexdigest()==sha,'Final diagnostic source bytes changed: '+name)
require(not TARGET.exists() and not RECOVERY.exists() and not OUTPUT.exists(),'Refuse preexisting stress/recovery/report destinations')
shutil.copytree(SOURCE/'records',TARGET/'records')
forecast_pairs={}
for path in (TARGET/'records'/'forecasts').glob('*.json'):
    payload=read_receipt(path)
    body=payload['data'].get('pros004',{})
    if body.get('schema_version')=='nba-pros004-forecast-v1':
        require(body['mode'] in rec.DIAGNOSTIC_MODES,'Retained PMFs must be explicitly non-issuance')
        forecast_pairs.setdefault(body['player_id'],{})[body['model_key']]=LedgerRef('forecasts',path.stem,digest(payload))
require(len(forecast_pairs)==4 and all(set(pair)=={'R0','K0'} for pair in forecast_pairs.values()),'Expected four diagnostic paired subjects')
player=min(forecast_pairs,key=int)
refs=[forecast_pairs[player][key] for key in ('R0','K0')]
retained=read_receipt(TARGET/'records'/'forecasts'/f'{refs[0].record_id}.json')['data']['pros004']
require(retained['event_id']=='999000004','Only the invented diagnostic event is admitted')
event_start=datetime.fromisoformat(retained['event_starts_at'].replace('Z','+00:00'))
observed=event_start+timedelta(hours=4)
normalized=observed+timedelta(seconds=10)
synthetic_line={'test_only':True,'evidence':'EXPLICITLY_INVENTED_COUNTS_NOT_OBSERVED',
                'event_id':'999000004','player_id':player,'primitive_counts':dict.fromkeys(COUNT_FIELDS,0),
                'minutes':0,'minutes_precision':'rounded_whole_minutes'}
source_raw=canonical(synthetic_line)
row=NBAPlayerGame(id_namespace='espn',event_id='999000004',player_id=player,
    team_id=retained['team_id'],opponent_id=retained['opponent_id'],season_ending_year=2027,
    season_type='2',event_start=event_start,participation='APPEARED',minutes=0,
    minutes_precision='rounded_whole_minutes',final_status='FINAL',final_periods=4,
    **dict.fromkeys(COUNT_FIELDS,0))

with ExitStack() as stack:
    stack.enter_context(_synthetic_clock(normalized))
    for module,name in ((prod,'_fit_laws'),(prod,'generate_forecast'),(prod,'forecast_reference'),(baseline,'forecast_reference')):
        stack.enter_context(patch.object(module,name,side_effect=refuse_fit))
    store=rec.Pros004Store(TARGET,diagnostic=True)
    before=store.capacity_report()
    all_forecasts_before={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in (TARGET/'records'/'forecasts').glob('*.json')}
    outcome=rec.outcome_from_normalized(row,event_version=retained['event_version'],mode=retained['mode'],
        source_raw_sha256=hashlib.sha256(source_raw).hexdigest(),source_observed_at=observed,normalized_at=normalized)
    outcome_ref=store.append_outcome(outcome,refs)
    grade_refs=[store.grade_forecast(ref,outcome_ref) for ref in refs]
    from dataclasses import replace
    revised_row=replace(row,points=2,fgm=1,fga=1,fg2m=1)
    revised_line={**synthetic_line,'invented_correction':True,'points':2,'fgm':1,'fg2m':1,'fga':1}
    revised_raw=canonical(revised_line)
    revised=rec.outcome_from_normalized(revised_row,event_version=retained['event_version'],mode=retained['mode'],
        source_raw_sha256=hashlib.sha256(revised_raw).hexdigest(),source_observed_at=observed,normalized_at=normalized)
    revised_ref=store.append_outcome(revised,refs,correction_reason='NON_ISSUANCE SYNTHETIC size stress: invented count correction; no actual source outcome')
    regrade_refs=[store.grade_forecast(ref,revised_ref) for ref in refs]
    require(store.ledger.latest(outcome_ref)==revised_ref,'Outcome correction linkage missing')
    require(all(store.ledger.latest(old)==new for old,new in zip(grade_refs,regrade_refs)),'Separate grade corrections missing')
    require(store.append_outcome(revised,refs,correction_reason='Retained synthetic correction')==revised_ref,'Outcome retry created an original')
    require([store.grade_forecast(ref,revised_ref) for ref in refs]==regrade_refs,'Grade retry changed original clocks')
    require({path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in (TARGET/'records'/'forecasts').glob('*.json')}==all_forecasts_before,'Forecast original bytes changed')
    after=store.capacity_report()
    require(after['actual_records']==40 and after['used_correction_failure_reserve']==6,'Unexpected synthetic record/reserve counts')
    shutil.copytree(TARGET/'records',RECOVERY/'records')
    recovered=rec.Pros004Store(RECOVERY,diagnostic=True)
    _,typed=recovered._inventory()
    for ref in [*refs,outcome_ref,*grade_refs,revised_ref,*regrade_refs]: recovered.read(ref)
    require(files(TARGET)==files(RECOVERY),'Independent readback changed any receipt bytes')
    require(recovered.ledger.latest(outcome_ref)==revised_ref,'Recovered outcome correction missing')
    require(all(recovered.ledger.latest(old)==new for old,new in zip(grade_refs,regrade_refs)),'Recovered grade corrections missing')
    maxima=after['maximum_measured_envelope_bytes']
    correction_sizes=[path.stat().st_size for path in (TARGET/'records'/'corrections').glob('*.json')
                      if read_receipt(path)['data']['reason'].startswith(('NON_ISSUANCE SYNTHETIC','Statistical regrade'))]
    require(len(correction_sizes)==3 and max(correction_sizes)<=8192,'Synthetic correction metadata exceeded its ceiling')
    measurement={
        'claim':maxima['nba-pros004-event-claim-v1'],
        'manifest':maxima['nba-pros004-study-manifest-v1'],
        'shared_outcome':maxima['nba-pros004-outcome-v1'],
        'separate_statistical_grade':maxima['nba-pros004-grade-v1'],
        'correction_link':max(correction_sizes),
        'retained_forecast':maxima['nba-pros004-forecast-v1'],
        'shared_history':maxima['nba-pros004-history-v1'],
        'event_pack':maxima['nba-pros004-event-v1']}
    summary={
        'schema_version':'nba-pros004-full-pmf-size-diagnostic-v1',
        'evidence_lane':'SYNTHETIC_CONTRACT_STRESS_NON_ISSUANCE_NOT_MODEL_EVALUATION',
        'actual_started_at':stamp(actual_started),'actual_completed_at':stamp(datetime.now(timezone.utc)),
        'source_report_raw_sha256':report_raw_before,'source_report_payload_sha256':digest(report),
        'source_record_manifest_sha256':digest(source_before),'source_records':len(source_before),
        'prior_stress_preparation_attempt':{'path':'/tmp/nml-pros004-full-pmf-size-store','result':'STOPPED_AT_EXACT_MODE_CHECK_BEFORE_ANY_NEW_RECORD','new_records':0},
        'selected_subject_basis':'LOWEST_NUMERIC_PLAYER_IN_INVENTED_DIAGNOSTIC_EVENT_ONLY',
        'synthetic_event_id':'999000004','synthetic_player_id':player,
        'simulated_source_observed_at':stamp(observed),'simulated_normalized_and_graded_at':stamp(normalized),
        'source_evidence_claim':'NONE_EXPLICITLY_INVENTED_COUNTS_NOT_OBSERVED',
        'synthetic_outcome_revisions':2,'synthetic_individual_grades':4,'synthetic_correction_links':3,
        'new_model_fits':0,'new_forecast_generation':0,'genuine_issuance':0,
        'actual_observed_outcomes':0,'reserved_comparative_aggregate_results':0,
        'financial_settlements':0,'qualified_tickets':0,
        'before_records':before['actual_records'],'after_records':after['actual_records'],
        'after_encoded_bytes':after['actual_bytes'],'used_correction_failure_reserve':after['used_correction_failure_reserve'],
        'complete_encoded_envelope_maxima_bytes':measurement,
        'full_study_capacity':rec.full_study_capacity(),
        'integrity':{'original_source_store_unchanged':True,'original_source_report_unchanged':True,
            'all_original_forecast_bytes_unchanged':True,'separate_restart_and_copied_readback':'PASS',
            'outcome_and_both_grade_correction_links':'PASS','idempotent_retries_preserve_originals':'PASS',
            'per_record_and_global_capacity':'PASS','no_metric_values_or_comparisons_exported':True},
        'final_record_manifest_sha256':digest(files(TARGET)),
        'runnable_command':'PYTHONPATH=/workspace/nml-pros004-readiness python3 /tmp/nml-pros004-size-stress.py',
        'rerun_policy':'Fresh versioned TARGET/RECOVERY/OUTPUT paths are required; script refuses existing paths',
        'qualification':'UNAVAILABLE','activation':'INACTIVE'}
require(files(SOURCE)==source_before,'Final source31-record store changed')
require(hashlib.sha256(SOURCE_REPORT.read_bytes()).hexdigest()==report_raw_before,'Final source diagnostic report changed')
for name,sha in report['source_sha256'].items():
    require(hashlib.sha256((REPO/name).read_bytes()).hexdigest()==sha,'Executed source bytes changed during stress: '+name)
write_receipt(OUTPUT,summary)
print(json.dumps({'attestation':str(OUTPUT),'records_before':summary['before_records'],'records_after':summary['after_records'],
                  'complete_encoded_envelope_maxima_bytes':measurement,'source_store_unchanged':True,
                  'original_forecast_bytes_unchanged':True,'restart_readback':'PASS',
                  'genuine_issuance':0,'actual_observed_outcomes':0,'metric_values_exported':0},sort_keys=True))

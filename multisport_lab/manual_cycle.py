"""Manual guard for one pinned NBA research cycle; no capture or scheduler.

Preparation/recovery are read-only. Binding freezes one timely input reference;
issuance delegates only to the exact reviewed producer after scanning originals
across all model and input references. No caller-supplied clock is supported.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from . import prospective as producer
from .integrity import IntegrityError, canonical, digest, read_receipt, stamp, utc, write_receipt
from .ledger import Ledger, LedgerRef, MAX_RECORD_BYTES
from .pregame_sources import binding_view, validate_pack


ROOT=Path(__file__).resolve().parents[1]
DEFAULT_PLAN=ROOT/'evidence/cycles/2026-10-20-nba-401909088-plan.json'
PRODUCER_COMMIT='58530309cf384425e15f02fd9fa980899a4dc0bc'
PREPARATION_COMMIT='c19bcd67d4fefe7f818fed569c683db9cc5ab9fc'
CYCLE_ID='nba-20261020-401909088-t90-r1'
HISTORY_RECORD_ID='dfa1c4345495eb3aa6b203f2e8309c89c112b6b78a36cd3d2c603d390776b6fc'
PLAYERS=['2596112','2990962','3195','4251']
MAX_METADATA_BYTES=64*1024
_PLAN_FIELDS={'schema_version','cycle_id','producer_commit','preparation_commit','model_version',
              'event_id','event_version','selection_sha256','selected_player_ids','history_input_record_id',
              'capture_opens_at','capture_closes_at','issuance_opens_at','issuance_closes_at','created_at',
              'model_files_sha256','original_records_sha256'}
_BINDING_FIELDS={'schema_version','cycle_id','plan_sha256','producer_commit','input_reference','bound_at'}


def _now():
    return datetime.now(timezone.utc)


def _hash(value,label):
    if type(value) is not str or not re.fullmatch(r'[0-9a-f]{64}',value):
        raise IntegrityError(f'{label} requires an exact SHA256')
    return value


def _clock(value,label):
    if type(value) is not str or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z',value):
        raise IntegrityError(f'{label} requires microsecond UTC')
    return utc(value)


def load_plan(path=DEFAULT_PLAN):
    plan=read_receipt(path,max_bytes=MAX_METADATA_BYTES)
    if type(plan) is not dict or set(plan)!=_PLAN_FIELDS:
        raise IntegrityError('manual cycle plan has missing or unexpected fields')
    fixed={'schema_version':'nba-manual-cycle-plan-v1','cycle_id':CYCLE_ID,
           'producer_commit':PRODUCER_COMMIT,'preparation_commit':PREPARATION_COMMIT,
           'model_version':producer.MODEL_VERSION,'event_id':'401909088',
           'event_version':producer.PILOT_EVENT_VERSION,'selection_sha256':producer.PILOT_SELECTION_SHA256,
           'selected_player_ids':PLAYERS,'history_input_record_id':HISTORY_RECORD_ID,
           'capture_opens_at':'2026-10-20T17:20:00.000000Z','capture_closes_at':'2026-10-20T17:30:00.000000Z',
           'issuance_opens_at':'2026-10-20T17:30:00.000000Z','issuance_closes_at':'2026-10-20T17:35:00.000000Z'}
    if any(plan[key]!=value for key,value in fixed.items()):
        raise IntegrityError('plan changes the reviewed producer, cycle, selection or operating window')
    if _clock(plan['created_at'],'plan creation')>_now():
        raise IntegrityError('plan creation is in the future')
    models=plan['model_files_sha256']
    if type(models) is not dict or set(models)!=set(producer.MODEL_FILES):
        raise IntegrityError('plan must pin exactly all nine reviewed model files')
    for name,value in models.items():_hash(value,f'model hash {name}')
    originals=plan['original_records_sha256']
    if type(originals) is not dict or len(originals)!=19:
        raise IntegrityError('plan must pin the nineteen original record files')
    for name,value in originals.items():
        if type(name) is not str or not re.fullmatch(r'records/(?:forecasts|outcomes|grades|research_inputs)/[0-9a-f]{64}\.json',name):
            raise IntegrityError('original record path is outside the bounded research ledger')
        _hash(value,f'original hash {name}')
    return plan


def _git_bytes(root,commit,name):
    return subprocess.check_output(['git','show',f'{commit}:{name}'],cwd=root,stderr=subprocess.PIPE)


def _check_reviewed_files(plan,root):
    producer.require_committed_model(root,plan['producer_commit'])
    for name in producer.MODEL_FILES:
        expected=hashlib.sha256(_git_bytes(root,plan['producer_commit'],name)).hexdigest()
        if plan['model_files_sha256'][name]!=expected or hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:
            raise IntegrityError(f'reviewed model pin or executed source changed: {name}')
        module_name=name[:-3].replace('/','.')
        module=sys.modules.get(module_name)
        if module is not None and Path(module.__file__).resolve()!=(root/name).resolve():
            raise IntegrityError(f'imported model module is outside this repository: {name}')
    names=subprocess.check_output(['git','ls-tree','-r','--name-only',plan['preparation_commit'],'--','records'],cwd=root,text=True).splitlines()
    names=[name for name in names if re.fullmatch(r'records/(?:forecasts|outcomes|grades|research_inputs)/[0-9a-f]{64}\.json',name)]
    if set(names)!=set(plan['original_records_sha256']):
        raise IntegrityError('original record inventory differs from reviewed preparation commit')
    for name,expected in plan['original_records_sha256'].items():
        if hashlib.sha256(_git_bytes(root,plan['preparation_commit'],name)).hexdigest()!=expected:
            raise IntegrityError(f'original record plan hash differs from preparation commit: {name}')
        path=root/name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise IntegrityError(f'original record bytes changed: {name}')


def _binding_path(root,plan):
    path=root/'evidence/cycles'/f"{plan['cycle_id']}-binding.json"
    for parent in [root,root/'evidence',path.parent]:
        if parent.is_symlink():raise IntegrityError('cycle metadata directories must not be symlinks')
    return path


def _input(store,record_id):
    _hash(record_id,'fresh input record ID')
    payload=read_receipt(store._path('research_inputs',record_id),max_bytes=MAX_RECORD_BYTES)
    reference=LedgerRef('research_inputs',record_id,digest(payload))
    return reference,store.read(reference)


def _validate_input(plan,store,reference,payload):
    if reference.record_id==plan['history_input_record_id']:
        raise IntegrityError('early preparation input cannot be the fresh capture binding')
    pack=validate_pack(payload['data']['source_pack'])
    view=binding_view(pack)
    if (view['event']['event_id']!=plan['event_id'] or view['event']['event_version']!=plan['event_version']
            or view['selection_sha256']!=plan['selection_sha256']
            or [p['player_id'] for p in view['candidates']]!=plan['selected_player_ids']):
        raise IntegrityError('fresh input event/version or fixed selected cohort differs from plan')
    target=producer.ForecastTarget(plan['event_id'],plan['selected_player_ids'][0],utc(view['event']['event_starts_at']))
    producer._check_pilot_history(pack,view)
    producer._check_capture_window(view,target)
    received=_clock(payload['received_at'],'input receipt')
    if not _clock(view['imported_at'],'input import')<=received<=_clock(plan['capture_closes_at'],'capture cutoff'):
        raise IntegrityError('fresh input receipt was not completed by cutoff')
    return pack,view


def _load_binding(plan,store):
    path=_binding_path(store.root,plan)
    if not path.exists() and not path.is_symlink():return None
    binding=read_receipt(path,max_bytes=MAX_METADATA_BYTES)
    if type(binding) is not dict or set(binding)!=_BINDING_FIELDS:
        raise IntegrityError('invalid immutable cycle binding schema')
    fixed={'schema_version':'nba-manual-cycle-binding-v1','cycle_id':plan['cycle_id'],
           'plan_sha256':digest(plan),'producer_commit':plan['producer_commit']}
    if any(binding[key]!=value for key,value in fixed.items()):
        raise IntegrityError('cycle binding changes the original plan or producer')
    reference=LedgerRef.from_record(binding['input_reference'])
    if reference.kind!='research_inputs':raise IntegrityError('binding requires one research input reference')
    payload=store.read(reference)
    _validate_input(plan,store,reference,payload)
    bound=_clock(binding['bound_at'],'original binding clock')
    if not _clock(payload['received_at'],'input receipt')<=bound<=_clock(plan['capture_closes_at'],'cutoff') or bound>_now():
        raise IntegrityError('original binding did not finish by cutoff')
    return binding


def _original_subjects(plan,store,binding):
    """Inspect ALL original selected-event subjects before producer/input filters."""
    snapshot=store.scan()
    subjects={}
    for record_id,payload in snapshot['forecasts'].items():
        bundle=payload['data'].get('bundle',{})
        if bundle.get('event_id')!=plan['event_id']:continue
        player=bundle.get('player_id')
        if player not in plan['selected_player_ids'] and bundle.get('model_version')!=plan['model_version']:continue
        if player not in plan['selected_player_ids']:
            raise IntegrityError('an original R1 forecast for this event is outside the frozen cohort')
        if (bundle.get('model_version')!=plan['model_version'] or bundle.get('model_commit')!=plan['producer_commit']
                or bundle.get('evidence_lane')!='REAL_TIME_CAPTURED'):
            raise IntegrityError('an original selected-event forecast uses a different model or producer revision')
        if binding is None:raise IntegrityError('original cycle forecasts exist without the immutable input binding')
        reference=LedgerRef.from_record(binding['input_reference'])
        if (bundle.get('prospective',{}).get('source_pack_record_id')!=reference.record_id
                or payload['references']!=[reference.to_record()]):
            raise IntegrityError('an original selected-event forecast uses a different input binding')
        if player in subjects:raise IntegrityError('duplicate original forecast subject in this cycle')
        subjects[player]={'reference':LedgerRef('forecasts',record_id,digest(payload)).to_record(),
                          'forecast_id':bundle['forecast_id'],'issued_at':bundle['issued_at'],
                          'received_at':payload['received_at']}
    return subjects,snapshot


def _report(plan,store,binding,subjects,snapshot):
    actual=_now()
    phase=('CAPTURE_NOT_YET_OPEN' if actual<_clock(plan['capture_opens_at'],'capture open') else
           'CAPTURE_WINDOW' if actual<_clock(plan['capture_closes_at'],'capture close') else
           'ISSUANCE_WINDOW' if actual<=_clock(plan['issuance_closes_at'],'issue close') else
           'ISSUANCE_WINDOW_CLOSED')
    missing=[p for p in plan['selected_player_ids'] if p not in subjects]
    grade_forecasts={grade['forecast_id'] for grade in store.iter_active_grades()
                     if grade['status'] in {'SCORED','DNP_NOT_SCORED'}}
    clocks=None
    if binding is not None:
        input_ref=LedgerRef.from_record(binding['input_reference'])
        payload=store.read(input_ref);view=binding_view(payload['data']['source_pack'])
        clocks={'bound_at':binding['bound_at'],'input_received_at':payload['received_at'],
                **{key:view[key] for key in ['source_observed_min_at','source_observed_max_at','imported_at',
                                            'history_source_observed_max_at','history_rows','history_latest_event_at']}}
    return {'schema_version':'nba-manual-cycle-status-v1','cycle_id':plan['cycle_id'],
            'producer_commit':plan['producer_commit'],'plan_sha256':digest(plan),'checked_at':stamp(actual),'phase':phase,
            **{key:plan[key] for key in ['capture_opens_at','capture_closes_at','issuance_opens_at','issuance_closes_at']},
            'status':'NOT_READY' if binding is None else 'BOUND_PENDING' if not subjects else 'PARTIAL' if missing else 'COMPLETE',
            'input_reference':binding['input_reference'] if binding else None,'clocks':clocks,
            'selected_player_ids':plan['selected_player_ids'],'selected_forecasts_retained':len(subjects),
            'missing_player_ids':missing,'forecast_records':subjects,
            'pending_statistical_grades':sum(s['forecast_id'] not in grade_forecasts for s in subjects.values()),
            'provider_requests':0,'forecasts_generated':0,'qualification':'UNAVAILABLE','financial_settlement':'NOT_EVALUATED'}


def recover(plan_path=DEFAULT_PLAN,*,repository_root=None):
    """Read-only after any interruption or window; never fill missing subjects."""
    plan=load_plan(plan_path);store=Ledger(repository_root)
    _check_reviewed_files(plan,store.root)
    binding=_load_binding(plan,store)
    subjects,snapshot=_original_subjects(plan,store,binding)
    return _report(plan,store,binding,subjects,snapshot)


def preflight(plan_path=DEFAULT_PLAN,*,repository_root=None,require_capture_window=False):
    result=recover(plan_path,repository_root=repository_root)
    if require_capture_window:
        plan=load_plan(plan_path)
        if not _clock(plan['capture_opens_at'],'capture open')<=_now()<_clock(plan['capture_closes_at'],'capture close'):
            raise IntegrityError('manual capture window is not open; no provider request is authorized by this command')
        if result['input_reference'] is not None:
            raise IntegrityError('cycle already has an immutable input binding; recover it instead of capturing replacement inputs')
    return result


def bind(input_record_id,plan_path=DEFAULT_PLAN,*,repository_root=None):
    plan=load_plan(plan_path);store=Ledger(repository_root)
    _check_reviewed_files(plan,store.root)
    reference,payload=_input(store,input_record_id)
    _validate_input(plan,store,reference,payload)
    existing=_load_binding(plan,store)
    if existing is not None:
        if existing['input_reference']!=reference.to_record():
            raise IntegrityError('this cycle is already bound to a different input; never rebind')
        _original_subjects(plan,store,existing)
        return existing
    _original_subjects(plan,store,None)
    actual=_now()
    if not _clock(payload['received_at'],'input receipt')<=actual<=_clock(plan['capture_closes_at'],'cutoff'):
        raise IntegrityError('new input binding must finish by cutoff')
    binding={'schema_version':'nba-manual-cycle-binding-v1','cycle_id':plan['cycle_id'],'plan_sha256':digest(plan),
             'producer_commit':plan['producer_commit'],'input_reference':reference.to_record(),'bound_at':stamp(actual)}
    write_receipt(_binding_path(store.root,plan),binding,max_bytes=MAX_METADATA_BYTES)
    return binding


def issue(input_record_id,model_commit,plan_path=DEFAULT_PLAN,*,repository_root=None):
    plan=load_plan(plan_path);store=Ledger(repository_root)
    _check_reviewed_files(plan,store.root)
    if model_commit!=plan['producer_commit']:
        raise IntegrityError('issuance must use the exact pinned producer; HEAD is not the policy')
    binding=_load_binding(plan,store)
    if binding is None:raise IntegrityError('fresh input must be immutably bound before issuance')
    input_ref=LedgerRef.from_record(binding['input_reference'])
    if input_record_id!=input_ref.record_id:
        raise IntegrityError('issuance/retry input differs from the immutable cycle binding')
    subjects,snapshot=_original_subjects(plan,store,binding)
    if len(subjects)<len(plan['selected_player_ids']) and not _clock(plan['issuance_opens_at'],'issue open')<=_now()<=_clock(plan['issuance_closes_at'],'issue close'):
        raise IntegrityError('missing subjects cannot issue outside the window; run read-only recover to retain the partial result')
    try:
        producer.issue_cohort(store,input_ref,model_commit=plan['producer_commit'])
    except (OSError,ValueError,subprocess.CalledProcessError) as error:
        raise IntegrityError(f'issuance interrupted or blocked; originals remain intact; run read-only recover: {error}') from error
    result=recover(plan_path,repository_root=store.root)
    if result['status']!='COMPLETE':
        raise IntegrityError('issuance left a partial cohort; run read-only recover; do not report complete')
    result['forecasts_generated']=len(plan['selected_player_ids'])-len(subjects)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ['preflight','recover','bind','issue']:
        command=sub.add_parser(name)
        command.add_argument('--plan',type=Path,default=DEFAULT_PLAN)
        if name=='preflight':command.add_argument('--require-capture-window',action='store_true')
        if name in {'bind','issue'}:command.add_argument('--input-record-id',required=True)
        if name=='issue':command.add_argument('--model-commit',required=True)
    args=parser.parse_args()
    try:
        if args.command=='bind':result=bind(args.input_record_id,args.plan)
        elif args.command=='issue':result=issue(args.input_record_id,args.model_commit,args.plan)
        elif args.command=='preflight':result=preflight(args.plan,require_capture_window=args.require_capture_window)
        else:result=recover(args.plan)
    except (OSError,ValueError,subprocess.CalledProcessError) as error:
        parser.error(str(error))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()

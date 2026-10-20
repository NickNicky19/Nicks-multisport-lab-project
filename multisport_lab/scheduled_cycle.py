"""One bounded October 20 NBA pilot runner, outside the pinned model files.

No scheduler, clock override, Git operation or publication occurs here. The
caller supplies a synchronous remote checkpoint; its failure stops generation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import time

from . import manual_cycle as guard
from .integrity import IntegrityError, digest, read_receipt, stamp, utc, write_receipt
from .ledger import Ledger, LedgerRef
from .pregame_sources import (MAX_PACK_BYTES, capture_espn, history_from_input_record,
                              load_pack, make_pack)


PLAN_SHA256='22ae8db607374486ebee6eb569d236a3d27aedc8535c3085a6b6858226921908'
PREPARATION_START=utc('2026-10-20T17:15:00.000000Z')
PLAN_PATH=Path('evidence/cycles/2026-10-20-nba-401909088-plan.json')
SELECTION_PATH=Path('evidence/data/2026-10-20-pregame-cycle-cohort.json')


def _now():
    return datetime.now(timezone.utc)


def _sleep(seconds):
    time.sleep(seconds)


def _wait_until(target):
    """At most 31 short waits; only within this day's preparation period."""
    target=utc(target)
    for _ in range(31):
        actual=_now()
        if actual>=target:return
        if (actual.date()!=PREPARATION_START.date() or actual<PREPARATION_START
                or target>utc('2026-10-20T17:30:00.000000Z')
                or target-actual>timedelta(minutes=15)):
            raise IntegrityError('refusing a wait outside the bounded preparation period')
        _sleep(min(30.0,(target-actual).total_seconds()))
    raise IntegrityError('actual clock did not reach the phase within its bounded wait')


def _phase_info(plan,phase,**details):
    return {'schema_version':'nba-scheduled-cycle-checkpoint-v1','cycle_id':plan['cycle_id'],
            'producer_commit':plan['producer_commit'],'phase':phase,'checked_at':stamp(_now()),**details}


def run_cycle(*,root,checkpoint):
    """Run once, returning factual nonzero failures and read-only recovery.

    ``checkpoint(info)`` must synchronously commit, push and independently read
    back the relevant records before returning. It may raise on any failure.
    This function never retries a failed checkpoint or refreshes a bound input.
    """
    root=Path(root).absolute()
    plan_path=root/PLAN_PATH
    report={'schema_version':'nba-scheduled-cycle-report-v1','started_at':stamp(_now()),
            'cycle_id':guard.CYCLE_ID,'producer_commit':guard.PRODUCER_COMMIT,
            'plan_sha256':PLAN_SHA256,'status':'NOT_STARTED','exit_code':1,'errors':[],
            'source_capture_attempted':False,'checkpoints':[],'recovery':None,
            'qualification':'UNAVAILABLE','financial_settlement':'NOT_EVALUATED'}
    plan=None

    def journal(info):
        entry={'phase':info['phase'],'checked_at':info['checked_at'],'status':'PENDING'}
        report['checkpoints'].append(entry)
        try:
            checkpoint(info)
        except Exception:
            entry['status']='FAILED'
            raise
        entry.update(status='SUCCESS',completed_at=stamp(_now()))

    def recover():
        try:
            report['recovery']=guard.recover(plan_path,repository_root=root)
        except Exception as error:
            report['recovery_error']=f'{type(error).__name__}: {error}'
        return report['recovery']

    try:
        if not callable(checkpoint):raise IntegrityError('a synchronous durable checkpoint is required')
        plan=guard.load_plan(plan_path)
        if digest(plan)!=PLAN_SHA256:
            raise IntegrityError('one-shot runner requires the exact reviewed cycle plan')
        current=recover()
        if current is None or 'recovery_error' in report:
            raise IntegrityError('existing cycle recovery failed before any source request')
        actual=_now()
        if actual.date()!=PREPARATION_START.date():
            report['status']='EXPIRED_WRONG_DATE'
            raise IntegrityError('one-shot pilot only operates on October 20, 2026 UTC')
        if actual<PREPARATION_START:
            report['status']='EARLY_NO_ACTION'
            raise IntegrityError('preparation does not open until 17:15 UTC; no long wait or source request')
        close=utc(plan['issuance_closes_at'])
        if current['status']=='COMPLETE':
            report.update(status='COMPLETE_RECOVERED',exit_code=0)
        elif actual>close:
            report['status']='EXPIRED_INCOMPLETE'
            raise IntegrityError('issuance window expired; retained partial records remain pending')
        else:
            binding=current['input_reference']
            if binding is None:
                if actual>=utc(plan['capture_closes_at']):
                    report['status']='MISSED_CAPTURE_WINDOW'
                    raise IntegrityError('no bound timely capture exists; never capture after cutoff')
                _wait_until(plan['capture_opens_at'])
                guard.preflight(plan_path,repository_root=root,require_capture_window=True)
                local=root/'.local-data/pregame-cycle'/plan['cycle_id']
                pack_path=local/'sourcepack.json'
                if pack_path.exists() or pack_path.is_symlink():
                    pack=load_pack(pack_path)
                else:
                    history,provenance=history_from_input_record(plan['history_input_record_id'],repository_root=root)
                    selection=read_receipt(root/SELECTION_PATH)
                    if digest(selection)!=plan['selection_sha256']:
                        raise IntegrityError('selected cohort receipt differs from the reviewed plan')
                    if not utc(plan['capture_opens_at'])<=_now()<utc(plan['capture_closes_at']):
                        report['status']='MISSED_CAPTURE_WINDOW'
                        raise IntegrityError('history recovery did not finish before the capture deadline')
                    journal(_phase_info(plan,'CAPTURE_STARTED',input_reference=None,
                                        history_input_record_id=plan['history_input_record_id'],
                                        event_id=plan['event_id'],
                                        sourcepack_path=str(pack_path.relative_to(root))))
                    if not utc(plan['capture_opens_at'])<=_now()<utc(plan['capture_closes_at']):
                        report['status']='MISSED_CAPTURE_WINDOW'
                        raise IntegrityError('remote capture intent did not finish before cutoff; no source request')
                    report['source_capture_attempted']=True
                    event,rosters,sources=capture_espn(plan['event_id'],'20261020',local/'raw')
                    pack=make_pack(event,rosters,sources,selection,history,provenance)
                    write_receipt(pack_path,pack,max_bytes=MAX_PACK_BYTES)
                store=Ledger(root)
                input_ref=store.record_research_inputs(pack)
                report['retained_input_reference']=input_ref.to_record()
                if _now()>utc(plan['capture_closes_at']):
                    report['status']='REJECTED_LATE_INPUT'
                    raise IntegrityError('late input retained diagnostically with original clocks; never bound or issued')
                binding_record=guard.bind(input_ref.record_id,plan_path,repository_root=root)
                binding=binding_record['input_reference']
            else:
                binding_record=read_receipt(root/'evidence/cycles'/f"{plan['cycle_id']}-binding.json")
            # A recovered local partial may include an original whose previous
            # push failed. The synchronous input checkpoint retains those bytes
            # before the reviewed helper can consider any missing subject.
            journal(_phase_info(plan,'INPUT_BOUND',input_reference=binding,
                                binding_path=f"evidence/cycles/{plan['cycle_id']}-binding.json",
                                bound_at=binding_record['bound_at'],
                                retained_forecast_references=[s['reference'] for s in current['forecast_records'].values()]))
            _wait_until(plan['issuance_opens_at'])
            if _now()>close:
                report['status']='EXPIRED_INCOMPLETE'
                raise IntegrityError('remote input checkpoint did not finish within the issuance window')
            base=guard.Ledger
            base_generate=guard.producer.generate

            def checkpoint_generation(pack,player_id,*,input_record_id,model_commit):
                if input_record_id!=binding['record_id'] or model_commit!=plan['producer_commit']:
                    raise IntegrityError('generation intent differs from the immutable input/producer binding')
                journal(_phase_info(plan,'GENERATION_STARTED',input_reference=binding,
                                    player_id=player_id,model_version=plan['model_version']))
                return base_generate(pack,player_id,input_record_id=input_record_id,model_commit=model_commit)

            class CheckpointLedger(base):
                def issue_prospective(self,bundle,*,reference,input_ref):
                    saved=super().issue_prospective(bundle,reference=reference,input_ref=input_ref)
                    payload=self.read(saved)
                    journal(_phase_info(plan,'FORECAST_RETAINED',input_reference=input_ref.to_record(),
                                        forecast_reference=saved.to_record(),player_id=bundle['player_id'],
                                        issued_at=bundle['issued_at'],received_at=payload['received_at']))
                    return saved

            # One executor/one writer only. This narrow runtime journal hook
            # changes neither generation nor the reviewed persistence semantics.
            try:
                guard.Ledger=CheckpointLedger
                guard.producer.generate=checkpoint_generation
                guard.issue(binding['record_id'],plan['producer_commit'],plan_path,repository_root=root)
            finally:
                guard.Ledger=base
                guard.producer.generate=base_generate
            current=recover()
            if current is None or current['status']!='COMPLETE':
                raise IntegrityError('runner ended with an incomplete cohort; do not claim complete issuance')
            report.update(status='COMPLETE',exit_code=0)
    except Exception as error:
        if report['status']=='NOT_STARTED':report['status']='FAILED'
        report['errors'].append(f'{type(error).__name__}: {error}')
        recover()
    report['completed_at']=stamp(_now())
    return report

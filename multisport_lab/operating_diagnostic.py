"""One explicit full-cohort OP002 software diagnostic; never real issuance.

The four source responses and event/rosters are invented. Only the complete
26,645-row retained history is real. Advancing simulated clocks retain every
elapsed second; actual UTC/CPU/wall/RSS evidence remains separate. No outcomes,
grades, provider requests, scheduler or activation are implemented here.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import resource
import subprocess
import tempfile
import time
from unittest.mock import patch

from . import baseline, ledger, operational_pilot as op, pregame_sources
from . import pros004_inputs
from .integrity import IntegrityError, canonical, digest, stamp, write_receipt
from .ledger import Ledger, LedgerRef
from .operational_remote import OperatingDiagnosticWriter, DIAGNOSTIC_BRANCH

SCHEMA='nba-op002-hosted-operating-diagnostic-v2'
MODE='SOFTWARE_DIAGNOSTIC_NON_ISSUANCE'
INPUT_CLOCK=datetime(2026,10,21,22,45,tzinfo=timezone.utc)
CUTOFF=datetime(2026,10,21,23,0,tzinfo=timezone.utc)
EVENT_START=CUTOFF+timedelta(minutes=90)
EVENT_ID='999002001'
MAX_WALL_SECONDS=900
MAX_RSS_KIB=512*1024


def actual_now():
    return datetime.now(timezone.utc)


class AdvancingClock:
    def __init__(self,start):
        self.start=start;self.observed=time.monotonic()

    def now(self):
        elapsed=time.monotonic()-self.observed
        op.require(elapsed >= 0,'actual diagnostic monotonic clock moved backwards')
        return self.start+timedelta(seconds=elapsed)


@contextmanager
def diagnostic_clock(clock):
    # Transport's actual timing telemetry and datetime.now are never patched.
    with ExitStack() as stack:
        for module in (op,ledger,baseline,pregame_sources,pros004_inputs):
            stack.enter_context(patch.object(module,'_now',side_effect=clock.now))
        yield


def _git(args,root):
    result=subprocess.run(['git',*args],cwd=root,capture_output=True,text=True,check=False,timeout=60)
    op.require(result.returncode == 0,'isolated diagnostic Git command failed: '+args[0])
    return result.stdout.strip()


def synthetic_sources(player_ids):
    """Explicitly invented bytes, never an assertion about an NBA roster."""
    op.require(len(player_ids) == 4 and len(set(player_ids)) == 4,'four diagnostic identities required')
    status={'type':{'name':'STATUS_SCHEDULED','state':'pre','completed':False}}
    event={'id':EVENT_ID,'uid':'s:40~l:46~e:'+EVENT_ID,'date':stamp(EVENT_START),'timeValid':True,
        'season':{'year':2027,'type':2},'status':status,'competitions':[{'id':EVENT_ID,
        'date':stamp(EVENT_START),'timeValid':True,'status':status,'competitors':[
            {'id':'8','homeAway':'home','team':{'id':'8'}},
            {'id':'2','homeAway':'away','team':{'id':'2'}}]}]}
    board={'leagues':[{'id':'46','abbreviation':'NBA'}],'events':[event]}
    base=pros004_inputs.BASE
    values=[('scoreboard',base+'/scoreboard?dates=20261022',board),
            ('summary',base+'/summary?event='+EVENT_ID,{'header':event})]
    for team,ids in (('8',player_ids[:2]),('2',player_ids[2:])):
        values.append(('roster-'+team,base+'/teams/'+team+'/roster',{'team':{'id':team},
            'season':{'year':2027,'type':2},'athletes':[{'id':pid,'displayName':'DIAGNOSTIC subject '+pid,
                'status':{'type':'active'}} for pid in ids]}))
    observations=[]
    for source_id,url,value in values:
        raw=canonical(value);observed=INPUT_CLOCK-timedelta(seconds=1)
        metadata={'source_id':source_id,'source_url':url,'request_started_at':stamp(observed-timedelta(seconds=1)),
            'observed_at':stamp(observed),'response_completed_at':stamp(observed),'source_updated_at':None,
            'source_response_generated_at':None,'raw_sha256':hashlib.sha256(raw).hexdigest(),'raw_bytes':len(raw),
            'http_status':200,'http_date':None,'etag':None,'last_modified':None}
        observations.append({'source_id':source_id,'raw':raw,'metadata':metadata})
    normalized=pregame_sources.normalize_event(observations[0]['raw'],observations[1]['raw'],EVENT_ID)
    rosters={team:pregame_sources.normalize_roster(next(o['raw'] for o in observations if o['source_id']=='roster-'+team),
        team,season_ending_year=2027) for team in ('8','2')}
    selection=pregame_sources.freeze_selection(normalized,rosters)
    return normalized,selection['players'],observations


def _check_source_pin(root,commit):
    if commit is None:return
    op.sha(commit,40)
    for name in op.SOURCE_FILES:
        result=subprocess.run(['git','show',commit+':'+name],cwd=root,capture_output=True,check=False,timeout=60)
        op.require(result.returncode == 0 and result.stdout == (root/name).read_bytes(),
                   'diagnostic executed source differs from exact pinned commit: '+name)


def _copy_baseline(code,destination):
    op.require(not destination.exists(),'retain existing diagnostic states; never replace or reuse them')
    destination.mkdir(parents=True,mode=0o700)
    expected={}
    for path in sorted((code/'records').glob('*/*.json')):
        raw=path.read_bytes();relative=path.relative_to(code);target=destination/relative
        op.require(not path.is_symlink(),'baseline original cannot be symlinked')
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        expected[relative.as_posix()]=hashlib.sha256(raw).hexdigest()
    op.require(bool(expected),'actual retained baseline is absent')
    return expected


def _baseline_unchanged(root,expected):
    op.require(all((root/name).is_file() and not (root/name).is_symlink() and
        hashlib.sha256((root/name).read_bytes()).hexdigest() == raw_sha for name,raw_sha in expected.items()),
        'diagnostic changed original baseline bytes')


def independent_checkout(writer,destination):
    op.require(not destination.exists(),'independent readback destination must be new')
    destination.mkdir(parents=True)
    _git(['init','--quiet'],destination)
    _git(['remote','add','origin',writer.remote_url],destination)
    _git(['fetch','--no-tags','--depth=1','origin','refs/heads/'+writer.branch],destination)
    commit=_git(['rev-parse','FETCH_HEAD'],destination)
    _git(['checkout','--quiet','--detach','FETCH_HEAD'],destination)
    return commit


def completion_failures(*,restart,exact_remote,cohort_seconds,total_seconds,peak_rss_kib):
    """Admission depends on completed operations, never retained counts alone."""
    failures=[]
    if restart is None or not exact_remote or restart['retained_originals'] != 8 or restart['eligible_originals'] != 8:
        failures.append('All eight originals and their original timely required acknowledgments were not independently recovered.')
    if cohort_seconds is None or cohort_seconds+5 > 300:
        failures.append('Complete cohort including last proof persistence and independent retention/readback exceeded T90+300 seconds.')
    if total_seconds > MAX_WALL_SECONDS:failures.append('Actual diagnostic wall time exceeded 900 seconds.')
    if peak_rss_kib > MAX_RSS_KIB:failures.append('Actual peak process RSS exceeded 512 MiB.')
    return failures


def run_diagnostic(*,output,store_root,writer_root,producer_commit=None,
                   authorize_diagnostic_push=False,local_test_remote=None):
    """Run once only after explicit diagnostic publication authorization."""
    code=Path(__file__).resolve().parents[1]
    op.require(authorize_diagnostic_push is True,'explicit one-off diagnostic push authorization is required')
    if local_test_remote is None:op.require(producer_commit is not None,'hosted diagnostic needs exact executed source pin')
    _check_source_pin(code,producer_commit)
    before={name:hashlib.sha256((code/name).read_bytes()).hexdigest() for name in op.SOURCE_FILES}
    output=Path(output);op.require(not output.exists(),'retain prior diagnostic receipt')
    started=actual_now();wall=time.perf_counter();cpu=time.process_time()
    root=Path(store_root).absolute();expected=_copy_baseline(code,root)
    store=op.OperationalStore(root,diagnostic=True)
    original_payload=next(payload for payload in store.ledger.scan()['research_inputs'].values()
                          if payload['record_id'] == op.ORIGINAL_HISTORY_ID)
    original=LedgerRef('research_inputs',original_payload['record_id'],digest(original_payload))
    binding=op.make_source_binding(diagnostic=True)
    history=op.make_history_body(original,root=root,mode='SYNTHETIC_DIAGNOSTIC')
    rows=op.history_rows(history,root)
    players=sorted({row.player_id for row in rows},key=int)[:4]
    input_clock=AdvancingClock(INPUT_CLOCK)
    with diagnostic_clock(input_clock):
        event,candidates,observations=synthetic_sources(players)
        plan=op.make_plan(event,candidates,registered_at=INPUT_CLOCK-timedelta(days=1))
    # Original invented bytes are durably retained without pretending they came
    # from a provider. This generic diagnostic receipt uses the actual UTC clock.
    fixture=store.ledger.append('input_captures','operational002:diagnostic:invented-source-bytes',{
        'schema_version':'nba-op002-diagnostic-fixtures-v1','mode':MODE,'real_source_capture':False,
        'sources':[{'source_id':o['source_id'],'raw_utf8':o['raw'].decode(),'metadata':o['metadata']} for o in observations]})
    planned_capacity=op.capacity_report(root)
    kwargs={'base_commit':producer_commit or _git(['rev-parse','HEAD'],code)}
    if local_test_remote is not None:kwargs.update(remote_url=str(local_test_remote),allow_local_test_remote=True)
    writer=OperatingDiagnosticWriter(root,writer_root,**kwargs);writer.prepare()
    phases=[];failure=None;recovery=None;remote_commit=None;final_retention=None;cohort_seconds=None
    pair_timings=[]
    original_prepare_pair=op.prepare_pair
    def timed_prepare_pair(*args,**kwargs):
        began=time.perf_counter();cpu_began=time.process_time()
        try:return original_prepare_pair(*args,**kwargs)
        finally:pair_timings.append({'player_id':kwargs.get('player_id'),
            'wall_seconds':time.perf_counter()-began,'process_cpu_seconds':time.process_time()-cpu_began})
    phase_started=time.perf_counter()
    try:
        with diagnostic_clock(input_clock):
            history_ref=store.persist(history,references=(original,))
            event_body=op.make_event_body(plan,history_ref,observations,mode='SYNTHETIC_DIAGNOSTIC')
            event_ref=store.persist(event_body,references=(history_ref,))
            store.checkpoint(event_ref,writer.checkpoint)
            store.finalize_checkpoint(writer.final_checkpoint)
            op.require(store.admission(event_ref)['eligible'],'input persistence/readback missed actual diagnostic capture phase')
        phases.append({'phase':'INPUT_PERSIST_CHECKPOINT_FINAL_PREFIX','wall_seconds':time.perf_counter()-phase_started})
        generation_clock=AdvancingClock(CUTOFF+timedelta(seconds=5))
        phase_started=time.perf_counter()
        with diagnostic_clock(generation_clock),patch.object(op,'prepare_pair',side_effect=timed_prepare_pair):
            try:
                recovery=op.issue_pair(store,event_ref,binding,checkpoint=writer.checkpoint,
                    checkpoint_many=writer.checkpoint_many,final_checkpoint=writer.final_checkpoint)
            except (IntegrityError,OSError) as error:
                failure={'phase':'GENERATION_OR_REQUIRED_PERSISTENCE','type':type(error).__name__,'message':str(error)}
                recovery=store.recover(replay=False)
            # No new original or completion is created here. Push/read back the
            # final actual proof (or partial journal) after its local persistence.
            final_retention=writer.final_checkpoint(hashlib.sha256(store._journal_path().read_bytes()).hexdigest())
            remote_commit=final_retention['remote_commit']
        cohort_seconds=time.perf_counter()-phase_started
        phases.append({'phase':'EIGHT_ORIGINALS_AND_REQUIRED_ACK_PREFIXES','wall_seconds':cohort_seconds})
    except (IntegrityError,OSError) as error:
        if failure is None:failure={'phase':'INPUT_OR_PARTIAL_RETENTION','type':type(error).__name__,'message':str(error)}
        # Retain actual partial state even if admission is unavailable. This
        # never retries a missing model or manufactures a local completion.
        clock=locals().get('generation_clock',input_clock)
        with diagnostic_clock(clock):
            recovery=store.recover(replay=False)
            try:
                final_retention=writer.final_checkpoint(hashlib.sha256(store._journal_path().read_bytes()).hexdigest())
                remote_commit=final_retention['remote_commit']
            except (IntegrityError,OSError) as retain_error:
                failure['partial_remote_retention_error']={'type':type(retain_error).__name__,'message':str(retain_error)}
    restarted=None;exact_remote=False;restart_seconds=None
    if remote_commit is not None:
        replay_clock=locals().get('generation_clock',input_clock)
        restart_started=time.perf_counter()
        with tempfile.TemporaryDirectory(prefix='nml-op002-final-restart-') as directory,diagnostic_clock(replay_clock):
            fetched=Path(directory)/'fetched';fetched_commit=independent_checkout(writer,fetched)
            op.require(fetched_commit == remote_commit,'final independent recovery commit changed')
            verified=op.verify_store(fetched,replay=True)
            exact_remote=verified['snapshot'] == op.snapshot_manifest(root)
            _baseline_unchanged(fetched,expected)
            restarted={'remote_commit':fetched_commit,'snapshot_id':verified['snapshot']['snapshot_id'],
                'retained_originals':verified['retained_originals'],'eligible_originals':verified['eligible_originals'],
                'genuine_issued':verified['genuine_issued'],'missing_peers':verified['missing_peers'],
                'full_joint_laws_replayed':verified['replayed_complete_laws']}
        restart_seconds=time.perf_counter()-restart_started
    _baseline_unchanged(code,expected);_baseline_unchanged(root,expected)
    op.require(before == {name:hashlib.sha256((code/name).read_bytes()).hexdigest() for name in op.SOURCE_FILES},
               'operating producer/transport source changed during diagnostic')
    total_seconds=time.perf_counter()-wall;peak_rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    failures=completion_failures(restart=restarted,exact_remote=exact_remote,cohort_seconds=cohort_seconds,
        total_seconds=total_seconds,peak_rss_kib=peak_rss)
    complete=failure is None and not failures
    with diagnostic_clock(locals().get('generation_clock',input_clock)):
        manifest=op.snapshot_manifest(root)
    report={'schema_version':SCHEMA,'mode':MODE,'status':'PASS_FULL_COHORT_OPERATIONAL_DIAGNOSTIC' if complete else 'PARTIAL_OR_FAILED_DIAGNOSTIC',
        'actual_started_at':stamp(started),'actual_completed_at':stamp(actual_now()),
        'source_commit':producer_commit,'source_sha256':before,'producer_binding':binding,
        'clock_harness':{'mode':'ADVANCING_SIMULATED_NON_ISSUANCE','input_clock':stamp(INPUT_CLOCK),
            'generation_clock':stamp(CUTOFF+timedelta(seconds=5)),'each_elapsed_second_retained':True,
            'clock_phase_changes':1,'proves_real_capture_or_issuance_timeliness':False,
            'required_before_each_original_deadline':'Generation, verification, local persistence, typed remote readback and first covering final-prefix proof; <=120 seconds and T90+300.',
            'postrun_whole_law_replay':'Independent software diagnostic after original completion; cannot grant or repair admission.'},
        'evidence':{'live_source_captures':0,'genuine_issuance':0,'outcomes':0,'statistical_grades':0,
            'comparative_study_evaluations':0,'activation':False,'qualified_tickets':0,'financial_settlements':0},
        'history':{'original_ref':original.to_record(),'rows':len(rows),'panel_sha256':op.PANEL_SHA256,
            'rows_dropped':0,'original_provenance_preserved':True},
        'synthetic_event':{'event_id':EVENT_ID,'player_ids':players,'real_event_or_roster_claim':False,
            'selection_rule':'Four lowest numeric identities in complete retained history; invented two-per-team rosters',
            'source_fixture_ref':fixture.to_record(),'categories':list(baseline.MARKETS)},
        'failure':failure,'completion_failures':failures,'independent_restart':restarted,'exact_remote_snapshot':exact_remote,
        'transport':{'type':'ISOLATED_LOCAL_BARE_GIT' if local_test_remote is not None else 'GITHUB_NORMAL_PUSH_AND_FRESH_FETCH',
            'repository':op.REPOSITORY,'branch':DIAGNOSTIC_BRANCH,'final_retention':final_retention,
            'original_checkpoint_strategy':'ONE_FULL_STRICT_TRANSFER_PER_EXISTING_SAME_SUBJECT_PAIR',
            'atomic_pair_issuance':False,'operations':writer.operations},
        'retention':{'actual_file_count':manifest['file_count'],'actual_encoded_bytes':manifest['total_bytes'],
            'source_snapshot':manifest,'planned_one_event_capacity':planned_capacity,
            'pros004_maximum_512_record_timing':'NOT_MEASURED_NOT_ACTIVATED'},
        'performance':{'phases':phases,'paired_generation_and_verification':pair_timings,
            'cohort_including_last_retention_seconds':cohort_seconds,
            'independent_full_replay_restart_seconds':restart_seconds,
            'total_wall_seconds':total_seconds,'total_process_cpu_seconds':time.process_time()-cpu,
            'peak_process_rss_kib':peak_rss,'wall_limit_seconds':MAX_WALL_SECONDS,'rss_limit_kib':MAX_RSS_KIB},
        'qualification':'UNAVAILABLE','deployment':False}
    write_receipt(output,report,max_bytes=1024*1024)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--store-root',type=Path,required=True)
    parser.add_argument('--writer-root',type=Path,required=True)
    parser.add_argument('--producer-commit',required=True)
    parser.add_argument('--authorize-diagnostic-push',action='store_true')
    args=parser.parse_args()
    try:report=run_diagnostic(**vars(args))
    except (IntegrityError,OSError,KeyError,TypeError,ValueError) as error:
        # Even an unreadable/interrupted store retains a factual receipt and
        # its exact files for diagnosis; this never declares valid recovery.
        if not args.output.exists():
            retained=[]
            if args.store_root.exists():
                for path in sorted(args.store_root.rglob('*')):
                    if path.is_file() and not path.is_symlink() and '.git' not in path.parts:
                        raw=path.read_bytes()
                        retained.append({'path':path.relative_to(args.store_root).as_posix(),
                            'bytes':len(raw),'raw_sha256':hashlib.sha256(raw).hexdigest()})
                        if len(retained)>512:break
            write_receipt(args.output,{'schema_version':SCHEMA,'mode':MODE,'status':'UNACKNOWLEDGED_PARTIAL_DIAGNOSTIC',
                'actual_observed_at':stamp(actual_now()),'source_commit':args.producer_commit,
                'failure':{'type':type(error).__name__,'message':str(error)[:2048]},
                'unverified_retained_files':retained,'recovery_admitted':False,'genuine_issuance':0,
                'activation':False,'qualification':'UNAVAILABLE','deployment':False},max_bytes=1024*1024)
        raise SystemExit('OP002 NON_ISSUANCE DIAGNOSTIC FAILED: '+str(error)) from error
    print(canonical({'status':report['status'],'output':str(args.output),'payload_sha256':digest(report),
        'genuine_issuance':0,'activation':False}).decode())
    if report['status'] != 'PASS_FULL_COHORT_OPERATIONAL_DIAGNOSTIC':raise SystemExit(2)


if __name__=='__main__':main()

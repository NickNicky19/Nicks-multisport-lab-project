"""Non-issuance PROS004 full-history resource/recovery diagnostic.

This command has no source client, activation flag, scheduler, outcome or score.
It runs fictitious ESPN-shaped source bytes and explicitly simulated clocks in
an isolated diagnostic store. Actual UTC and monotonic resource clocks are kept
outside that harness. Passing this diagnostic does not establish actual capture,
prospective issuance, GitHub recovery, maximum-ledger timing, or activation.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import resource
import subprocess
import tempfile
import time
from unittest.mock import patch

from . import baseline, ledger, pregame_sources, pros004_inputs as inputs
from . import pros004_producer as producer, pros004_records as records
from . import pros004_snapshot as snapshots, pros004_remote as remote
from .integrity import IntegrityError, canonical, digest, stamp, write_receipt
from .ledger import Ledger, LedgerRef, KINDS

SCHEMA = "nba-pros004-readiness-report-v3"
MODE = "READINESS_DIAGNOSTIC_NON_ISSUANCE"
EVENT_ID = "999000004"
INPUT_CLOCK = datetime(2026, 10, 21, 22, 45, tzinfo=timezone.utc)
GENERATION_CLOCK = datetime(2026, 10, 21, 23, 0, 5, tzinfo=timezone.utc)
EVENT_START = datetime(2026, 10, 22, 0, 30, tzinfo=timezone.utc)
DRIVER_SOURCE = "multisport_lab/pros004_readiness.py"
SNAPSHOT_SOURCE = "multisport_lab/pros004_snapshot.py"
VERIFIER_SOURCE = "scripts/verify_pros004_readiness.py"
DIAGNOSTIC_SOURCE_FILES = (DRIVER_SOURCE,SNAPSHOT_SOURCE,VERIFIER_SOURCE)


def _actual_now():
    return datetime.now(timezone.utc)


@contextmanager
def _synthetic_clock(clock):
    """Explicit test harness only; does not modify actual resource/UTC clocks."""
    with ExitStack() as stack:
        for module in (inputs, producer, records, ledger, baseline):
            stack.enter_context(patch.object(module, "_now", return_value=clock))
        yield


class AdvancingDiagnosticClock:
    """Fictitious UTC phase with every real elapsed second retained.

    Phase changes are explicit preparation/generation boundaries. Within either
    phase a slow write, Git command or verification advances the logical clock;
    the harness cannot make a late operation timely by holding time constant.
    This is software timing evidence, never evidence of actual future issuance.
    """
    def __init__(self, logical_start, *, monotonic=None):
        self._monotonic = monotonic or time.monotonic
        self.logical_start = logical_start
        self.started = self._monotonic()

    def now(self):
        elapsed = self._monotonic()-self.started
        if elapsed < 0:
            raise IntegrityError("diagnostic monotonic clock moved backwards")
        return self.logical_start+timedelta(seconds=elapsed)


@contextmanager
def _advancing_clock(clock):
    """Patch only the isolated software diagnostic, including its local ACK."""
    with ExitStack() as stack:
        for module in (inputs,producer,records,ledger,baseline,remote):
            stack.enter_context(patch.object(module,"_now",side_effect=clock.now))
        yield


def _git(args, *, cwd=None):
    completed = subprocess.run(["git",*args],cwd=cwd,capture_output=True,text=True,
                               check=False,timeout=60)
    if completed.returncode:
        raise IntegrityError("isolated diagnostic Git command failed: "+args[0])
    return completed.stdout.strip()


def _local_checkpoint_writer(store, root, workspace, *, base_commit=None):
    """Seed an isolated bare repository from the exact local source commit.

    No GitHub contact or credential is used. The writer then exercises the same
    normal-push/fresh-fetch adapter as the separately authorized remote probe.
    """
    workspace = Path(workspace)
    bare = workspace/"remote.git"
    bare.mkdir()
    _git(["init","--quiet","--bare"],cwd=bare)
    base_commit = base_commit or _git(["rev-parse","HEAD"],cwd=root)
    _git(["fetch","--no-tags",str(root),base_commit],cwd=bare)
    _git(["update-ref","refs/heads/main",base_commit],cwd=bare)
    writer = remote.GitCheckpointWriter(store.root,workspace/"writer",base_commit=base_commit,
        remote_url=str(bare),allow_local_test_remote=True)
    preparation = writer.prepare()
    return writer,{"transport":"ISOLATED_LOCAL_BARE_GIT","github_contact":False,
        "bare_repository":str(bare),"base_commit":base_commit,"preparation":preparation}


def _fresh_remote_checkout(writer, destination):
    """Independent new object database; not a copy of retained writer files."""
    destination = Path(destination)
    destination.mkdir()
    _git(["init","--quiet"],cwd=destination)
    _git(["remote","add","origin",writer.remote_url],cwd=destination)
    _git(["fetch","--no-tags","--depth=1","origin","refs/heads/"+writer.branch],cwd=destination)
    commit = _git(["rev-parse","FETCH_HEAD"],cwd=destination)
    _git(["checkout","--quiet","--detach","FETCH_HEAD"],cwd=destination)
    return commit


def _recovery_content(recovery):
    """Readback has its own observation time and optional transport witness."""
    return {key:value for key,value in recovery.items()
            if key not in ("recovered_at","final_checkpoint")}


def _fake_observation(name, url, value):
    raw = canonical(value)
    observed = INPUT_CLOCK-timedelta(minutes=1)
    return {"raw":raw,"source":{"source_id":name,"source_url":url,
        "request_started_at":stamp(observed-timedelta(seconds=1)),
        "observed_at":stamp(observed),"response_completed_at":stamp(observed),
        "source_updated_at":None,"source_response_generated_at":None,
        "raw_sha256":hashlib.sha256(raw).hexdigest(),"raw_bytes":len(raw),
        "http_status":200,"http_date":None,"etag":None,"last_modified":None}}


def _fake_event():
    status = {"type":{"name":"STATUS_SCHEDULED","state":"pre","completed":False}}
    return {"id":EVENT_ID,"uid":"s:40~l:46~e:"+EVENT_ID,
        "date":stamp(EVENT_START),"timeValid":True,"season":{"year":2027,"type":2},
        "status":status,"competitions":[{"id":EVENT_ID,"date":stamp(EVENT_START),
        "timeValid":True,"status":deepcopy(status),"competitors":[
            {"id":"8","homeAway":"home","team":{"id":"8"}},
            {"id":"2","homeAway":"away","team":{"id":"2"}}]}]}


def _fake_board(events):
    return {"leagues":[{"id":"46","abbreviation":"NBA"}],
        "events":deepcopy(events),"pagination":{"page":1,"pageCount":1,
            "totalCount":len(events),"pageSize":1000}}


def synthetic_event_pack(history_ref, player_ids, *, clock=None):
    """Construct invented source bytes, never an assertion about an NBA roster."""
    if (type(player_ids) is not list or len(player_ids) != 4
            or any(type(pid) is not str or not pid.isdecimal() or int(pid) <= 0 for pid in player_ids)
            or player_ids != sorted(set(player_ids), key=int)):
        raise IntegrityError("diagnostic cohort requires four unique sorted numeric retained identities")
    event = _fake_event()
    observations = []
    for day in ("20261021", "20261022", "20261023"):
        observations.append(_fake_observation("schedule-"+day,
            f"{inputs.BASE}/scoreboard?dates={day}&limit=1000",
            _fake_board([event] if day == "20261022" else [])))
    current = {
        "scoreboard":_fake_observation("scoreboard",f"{inputs.BASE}/scoreboard?dates=20261022",_fake_board([event])),
        "summary":_fake_observation("summary",f"{inputs.BASE}/summary?event={EVENT_ID}",{"header":deepcopy(event)})}
    for team, ids in (("8",player_ids[:2]),("2",player_ids[2:])):
        body = {"team":{"id":team},"season":{"year":2027,"type":2},
            "athletes":[{"id":pid,"displayName":"DIAGNOSTIC subject "+pid,
                         "status":{"type":"active"}} for pid in ids]}
        key = "roster-"+team
        current[key] = _fake_observation(key,f"{inputs.BASE}/teams/{team}/roster",body)
    with _advancing_clock(clock) if clock is not None else _synthetic_clock(INPUT_CLOCK):
        schedule = inputs.make_schedule("2026-10-22",observations,mode="SYNTHETIC_DIAGNOSTIC")
        selection = inputs.make_selection(schedule,current)
        event_body = inputs.make_event_body(history_ref,schedule,selection,current,mode="SYNTHETIC_DIAGNOSTIC")
    return event_body


def _existing_inventory(root):
    store = Ledger(root)
    index = store.scan()
    counts = {kind:len(index[kind]) for kind in KINDS}
    files = [path for kind in KINDS for path in (Path(root)/"records"/kind).glob("*.json")]
    return {"records":sum(counts.values()),"encoded_bytes":sum(p.stat().st_size for p in files),
            "records_by_kind":counts,
            "record_file_sha256":{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(files)}}


def _source_binding(model_commit, root):
    binding = producer.make_source_binding(model_commit,diagnostic=model_commit is None,root=root)
    source_hashes = dict(binding["source_sha256"])
    for name in DIAGNOSTIC_SOURCE_FILES:
        source_hashes[name] = hashlib.sha256((root/name).read_bytes()).hexdigest()
        if model_commit is not None:
            completed = subprocess.run(["git","show",f"{model_commit}:{name}"],cwd=root,
                                       capture_output=True,check=False)
            if completed.returncode or hashlib.sha256(completed.stdout).hexdigest() != source_hashes[name]:
                raise IntegrityError("executed readiness driver or snapshot adapter differs from pinned producer commit")
    return binding,source_hashes


def _new_store_root(root):
    """Never reuse, erase or silently recover a previous diagnostic invocation."""
    root = Path(root).resolve()
    if root.exists():
        raise IntegrityError("readiness diagnostic requires a new nonexistent store root")
    store = records.Pros004Store(root,diagnostic=True)
    return store


def _verify_baseline_files(root, inventory):
    """Verify unchanged original bytes without relabeling legacy evidence."""
    root = Path(root)
    for name,expected in inventory["record_file_sha256"].items():
        path = root/name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise IntegrityError("original baseline receipt changed during diagnostic copy/readback")
    return {"original_records":inventory["records"],"original_encoded_bytes":inventory["encoded_bytes"],
            "all_original_bytes_preserved":True,"original_evidence_lanes_unchanged":True}


def _copy_baseline(source_root, store, inventory, snapshot_root):
    """Retain the exact current ledger before adding any synthetic record."""
    manifest = snapshots.export_snapshot(source_root,snapshot_root)
    observed = {entry["path"]:entry["raw_sha256"] for entry in manifest["entries"]}
    if (observed != inventory["record_file_sha256"] or manifest["record_count"] != inventory["records"]
            or manifest["encoded_bytes"] != inventory["encoded_bytes"]):
        raise IntegrityError("existing ledger changed between admission and baseline snapshot")
    acknowledgement = snapshots.recover_snapshot(snapshot_root,store.root)
    preserved = _verify_baseline_files(store.root,inventory)
    if acknowledgement["record_count"] != inventory["records"] or not acknowledgement["all_original_bytes_preserved"]:
        raise IntegrityError("baseline snapshot independent readback did not preserve exact originals")
    return {"manifest_id":manifest["manifest_id"],"readback":acknowledgement,**preserved}


def _encoded_size(store, reference):
    return store.ledger._path(reference.kind,reference.record_id).stat().st_size


def run_diagnostic(*, output, store_root=None, producer_commit=None):
    """Measure a complete synthetic cohort; never execute real study issuance."""
    actual_started = _actual_now()
    monotonic_started = time.perf_counter()
    root = Path(__file__).resolve().parents[1]
    binding,source_hashes = _source_binding(producer_commit,root)
    existing = _existing_inventory(root)
    history_started = time.perf_counter()
    history,provenance = pregame_sources.history_from_input_record(inputs.INPUT_RECORD_ID,repository_root=root)
    # This repacking clock is actual, preserving the original source clocks and
    # reconstructed-history limitations. It is not a new source observation.
    history_body = inputs.make_history_body(history,provenance,mode="SYNTHETIC_DIAGNOSTIC")
    rows = inputs.history_rows(history_body)
    player_ids = sorted({row.player_id for row in rows},key=int)[:4]
    if len(player_ids) != 4:
        raise IntegrityError("fixed history lacks four identities for the invented diagnostic")
    history_seconds = time.perf_counter()-history_started
    with ExitStack() as stack:
        retained = store_root is not None
        if store_root is None:
            store_root = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="nml-pros004-diagnostic-")))/"store"
        store = _new_store_root(store_root)
        baseline_started = time.perf_counter()
        baseline_snapshot = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="nml-pros004-baseline-")))/"snapshot"
        baseline_copy = _copy_baseline(root,store,existing,baseline_snapshot)
        baseline_seconds = time.perf_counter()-baseline_started
        writer_workspace = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="nml-pros004-local-remote-")))
        writer,transport = _local_checkpoint_writer(store,root,writer_workspace,base_commit=producer_commit)
        acknowledgments = []
        def checkpoint(reference):
            began = time.perf_counter()
            acknowledgment = writer.checkpoint(reference)
            acknowledgments.append({"reference":reference.to_record(),
                "actual_elapsed_seconds":time.perf_counter()-began,"acknowledgment":acknowledgment})
            return acknowledgment
        input_started = time.perf_counter()
        input_clock = AdvancingDiagnosticClock(INPUT_CLOCK)
        with _advancing_clock(input_clock):
            history_ref = store.store_history(history_body)
            event_body = synthetic_event_pack(history_ref,player_ids,clock=input_clock)
            event_ref = store.store_event(event_body,history_ref)
            store.store_manifest()
            store.complete_checkpoint(event_ref,checkpoint)
            input_final_checkpoint = store.finalize_checkpoint((event_ref,),checkpoint)
            if type(input_final_checkpoint) is not dict or input_final_checkpoint.get("timely") is not True:
                raise IntegrityError("event-input proof publication missed selection close; retained input cannot start generation")
            admission_ref,_=store.claim_event(event_ref,binding,input_final_checkpoint=input_final_checkpoint)
            store.complete_checkpoint(admission_ref,checkpoint)
            admission_final_checkpoint=store.finalize_checkpoint((admission_ref,),checkpoint)
            if admission_final_checkpoint["timely"] is not True:
                raise IntegrityError("durable input admission publication missed selection close; generation remains disabled")
        input_seconds = time.perf_counter()-input_started
        generation_seconds = []
        original_generate = producer.generate_forecast
        def timed_generate(*args,**kwargs):
            started = time.perf_counter()
            result = original_generate(*args,**kwargs)
            generation_seconds.append({"player_id":kwargs["player_id"],"model_key":kwargs["model_key"],
                                       "actual_elapsed_seconds":time.perf_counter()-started})
            return result
        cohort_started = time.perf_counter()
        generation_clock = AdvancingDiagnosticClock(GENERATION_CLOCK)
        operation_failure = None
        with _advancing_clock(generation_clock), patch.object(producer,"generate_forecast",side_effect=timed_generate):
            try:
                result = producer.issue_pair(store,event_ref,binding,checkpoint=checkpoint)
            except (IntegrityError,OSError) as error:
                # The retained actual partial state is diagnostic evidence. Do
                # not replace originals or hold the clock still to make it pass.
                operation_failure = {"type":type(error).__name__,"message":str(error)}
                result = store.recover_event(event_ref,binding)
            recovery = store.recover_event(event_ref,binding)
            final_checkpoint = result.get("final_checkpoint")
        cohort_seconds = time.perf_counter()-cohort_started
        originals = []
        with _advancing_clock(generation_clock):
            for subject in recovery["subjects"]:
                for model in ("R0","K0"):
                    original = subject["forecasts"][model]
                    if original is None:
                        continue
                    ref = LedgerRef.from_record(original)
                    body = store.body(ref)
                    if body["joint_recipe"]["support_atom_count"] != inputs.PANEL_ROWS:
                        raise IntegrityError("diagnostic omitted full retained history atoms")
                    originals.append({"reference":ref.to_record(),"model_key":model,
                        "player_id":subject["player_id"],"encoded_envelope_bytes":_encoded_size(store,ref),
                        "original_body_sha256":digest(body),"joint_sha256":body["joint_recipe"]["joint_sha256"]})
            capacity = store.capacity_report()
        # Recovery starts with an actual independent fetch from the isolated
        # bare remote, including the final ACK-journal publication. A local file
        # copy cannot establish this transport/restart check.
        recovery_started = time.perf_counter()
        readback_root = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="nml-pros004-readback-")))
        copied = readback_root/"git-readback"
        remote_commit = _fresh_remote_checkout(writer,copied)
        diagnostics = {}
        replay_timings = []
        with _advancing_clock(generation_clock):
            snapshot = snapshots.snapshot_manifest(store.root)
            remote_snapshot = snapshots.snapshot_manifest(copied)
            exact_remote = remote_snapshot == snapshot
            if operation_failure is None and not exact_remote:
                raise IntegrityError("final Git readback did not retain the complete ACK journal")
            _verify_baseline_files(copied,existing)
            # A recovered operational store must remain outside Git. Recovering
            # from fetched bytes is independent of the retained local writer.
            snapshots.export_snapshot(copied,readback_root/"snapshot")
            readback = snapshots.recover_snapshot(readback_root/"snapshot",readback_root/"reopened")
            restored = records.Pros004Store(readback_root/"reopened",diagnostic=True)
            reread = restored.recover_event(event_ref,binding)
            restored_admission=restored.lookup_claim(event_ref,binding)
            input_admission_recovered=(restored_admission==admission_ref and
                restored.body(restored_admission)["schema_version"]=="nba-pros004-event-claim-v2" and
                restored.body(restored_admission)["input_final_checkpoint"]==input_final_checkpoint and
                restored.admission_status(restored_admission)["timing_complete"])
            if not input_admission_recovered:
                raise IntegrityError("independent restart did not recover the original durable input admission")
            if operation_failure is None and _recovery_content(reread) != _recovery_content(recovery):
                raise IntegrityError("independent Git restart changed original recovery metadata")
            for item in originals:
                ref = LedgerRef.from_record(item["reference"])
                if restored.lookup_forecast(event_ref,item["player_id"],item["model_key"]) is None:
                    continue
                body = restored.body(ref)
                if digest(body) != item["original_body_sha256"]:
                    raise IntegrityError("remote restart changed original probabilities or clocks")
                model = item["model_key"]
                if model not in diagnostics:
                    began = time.perf_counter()
                    verified = producer.verify_replay(body,restored.body(event_ref),restored.body(history_ref))
                    replay_timings.append({"model_key":model,"actual_elapsed_seconds":time.perf_counter()-began})
                    diagnostics[model] = {
                        "forecast_envelope_bytes":max(v["encoded_envelope_bytes"] for v in originals if v["model_key"] == model),
                        "support_count":body["joint_recipe"]["support_atom_count"],
                        "restored_support_count":verified["verified_atom_count"],
                        "category_count":len(body["categories"]),"joint_sha256":item["joint_sha256"],
                        "restored_joint_sha256":verified["joint_sha256"],
                        "replayed_player_id":item["player_id"],"model_version":body["model_version"],
                        "producer_version":body["producer_version"],
                        "all_original_marginal_probabilities_exact":verified["all_original_marginal_probabilities_exact"]}
        recovery_seconds = time.perf_counter()-recovery_started
        complete = (operation_failure is None and recovery["retained_models"] == 8
                    and recovery["timing_complete_models"] == 8 and recovery["eligible_models"] == 0
                    and reread["timing_complete_models"] == 8 and exact_remote
                    and type(final_checkpoint) is dict and final_checkpoint.get("timely") is True)
        plan = records.full_study_capacity()
        metadata_records = (plan["full_study_records_before_reserve"]-474+records.RESERVE_RECORDS)
        report = {"schema_version":SCHEMA,"mode":MODE,
            "actual_started_at":stamp(actual_started),"actual_completed_at":stamp(_actual_now()),
            "evidence":{"live_source_captures":0,"genuine_issuance":0,"statistical_grades":0,
                        "aggregate_comparison_executions":0,"activation":False,
                        "qualified_tickets":0,"financial_settlements":0},
            "source_sha256":source_hashes,"producer_binding":binding,
            "diagnostic_status":"PASS" if complete else "PARTIAL_OR_FAILED_TIMING",
            "operation_failure":operation_failure,
            "clock_harness":{"mode":"EXPLICITLY_SIMULATED_ADVANCING_NON_ISSUANCE",
                "input_clock":stamp(INPUT_CLOCK),"generation_clock":stamp(GENERATION_CLOCK),
                "actual_timing_uses":"time.perf_counter and actual UTC outside the simulated clock harness",
                "logical_time_advances_by":"actual time.monotonic elapsed seconds within each phase",
                "clock_phase_changes":"One explicit preparation-to-generation boundary; no resets within a phase",
                "remote_acknowledgment_clocks":"SIMULATED_ADVANCING_LOCAL_BARE_GIT_ONLY",
                "proves_real_capture_or_issuance_timeliness":False},
            "synthetic_event":{"event_id":EVENT_ID,"event_starts_at":stamp(EVENT_START),
                "real_event_or_roster_claim":False,"selection_rule":"Four lowest numeric identities in retained history; invented two-per-team rosters",
                "player_ids":player_ids,"model_records":len(originals),"observed_outcomes":0},
            "history":{"retained_input_record_id":inputs.INPUT_RECORD_ID,"rows":len(rows),
                "events":len({r.event_id for r in rows}),"normalized_bytes":inputs.PANEL_BYTES,
                "sha256":inputs.PANEL_SHA256,"encoded_envelope_bytes":_encoded_size(store,history_ref),
                "history_ref":history_ref.to_record(),"recovered_history_actual_seconds":history_seconds,
                "reconstructed_history_limitations_unchanged":True,"rows_dropped":0},
            "event_input":{"encoded_envelope_bytes":_encoded_size(store,event_ref),"event_ref":event_ref.to_record(),
                "final_checkpoint":input_final_checkpoint,"admission_ref":admission_ref.to_record(),
                "admission_encoded_envelope_bytes":_encoded_size(store,admission_ref),
                "admission_final_checkpoint":admission_final_checkpoint},
            "retention":{"max_records":plan["global_record_limit"],"max_bytes":plan["global_byte_limit"],
                "comparison_records":442,"baseline_and_pilot_records":32,"metadata_records":metadata_records,
                "projected_records":plan["maximum_records_including_reserve"],
                "projected_bytes":plan["maximum_planned_bytes"],
                "metadata_encoded_ceiling_bytes":plan["metadata_envelope_ceiling_bytes"]+plan["correction_failure_reserve_ceiling_bytes"],
                "plan":plan,"actual_existing_repository":existing,
                "baseline_copy":baseline_copy,
                "measured_diagnostic_store":capacity},
            "diagnostics":diagnostics,"all_original_forecasts":originals,
            "performance":{"baseline_copy_and_readback_actual_seconds":baseline_seconds,
                "input_persist_checkpoint_finalize_actual_seconds":input_seconds,
                "cohort_generate_verify_persist_actual_seconds":cohort_seconds,
                "forecast_generation_actual_seconds":generation_seconds,
                "git_checkpoint_actual_seconds":acknowledgments,
                "copy_restart_replay_actual_seconds":recovery_seconds,
                "joint_replay_actual_seconds":replay_timings,
                "total_actual_elapsed_seconds":time.perf_counter()-monotonic_started,
                "peak_process_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},
            "recovery":{"status":"PASS_LOCAL_BARE_GIT_RESTART_AND_COMPLETE_JOINT_REPLAY" if complete else "PARTIAL_OR_FAILED_TIMING",
                "original_records_recovered":reread["retained_models"],"full_joint_replays":len(diagnostics),
                "retained_models":reread["retained_models"],"timing_complete_models":reread["timing_complete_models"],
                "eligible_models":reread["eligible_models"],"remote_recovery":exact_remote,
                "input_admission_recovered":bool(input_admission_recovered),
                "transport":transport,"github_recovery":False,"remote_commit":remote_commit,
                "final_checkpoint":final_checkpoint,
                "snapshot_manifest_id":snapshot["manifest_id"],"snapshot_readback":readback,
                "existing_baseline_records_preserved":existing["records"],
                "store_root":str(store.root),"store_retained_after_command":retained,
                "original_probabilities_and_clocks_preserved":True},
            "maximum_study_timing":{"status":"NOT_MEASURED_AT_MAXIMUM_LEDGER_LOAD",
                "measured_ledger_records":capacity["actual_records"],
                "planned_records_including_reserve":plan["maximum_records_including_reserve"],
                "limitation":"This complete-history cohort starts with the actual retained baseline, not a full-study sized ledger. Capacity ceilings alone do not establish worst-case operational timing."},
            "activation":"INACTIVE_READINESS_ONLY","qualification":"UNAVAILABLE"}
        # Detect concurrent dependency edits rather than retain an ambiguous run.
        producer.validate_source_binding(binding,check_current=True)
        for name in DIAGNOSTIC_SOURCE_FILES:
            if hashlib.sha256((root/name).read_bytes()).hexdigest() != source_hashes[name]:
                raise IntegrityError("readiness diagnostic driver or snapshot adapter changed during execution")
        _verify_baseline_files(root,existing)
        _verify_baseline_files(store.root,existing)
        write_receipt(output,report,max_bytes=1024*1024)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True,help="Create-only non-issuance diagnostic receipt")
    parser.add_argument("--store-root",type=Path,help="New nonexistent isolated directory outside any Git worktree; retain diagnostic receipts")
    parser.add_argument("--producer-commit",help="Optional exact reviewed source commit; omitted means local diagnostic source only")
    args = parser.parse_args()
    try:
        report = run_diagnostic(output=args.output,store_root=args.store_root,producer_commit=args.producer_commit)
    except (IntegrityError,OSError,KeyError,TypeError) as error:
        raise SystemExit("PROS004 READINESS DIAGNOSTIC FAILED: "+str(error))
    print(canonical({"report":str(args.output),"payload_sha256":digest(report),
        "genuine_issuance":0,"activation":False,
        "diagnostic_status":report["diagnostic_status"],
        "diagnostic_forecasts":report["synthetic_event"]["model_records"],
        "actual_elapsed_seconds":report["performance"]["total_actual_elapsed_seconds"]}).decode())


if __name__ == "__main__":
    main()

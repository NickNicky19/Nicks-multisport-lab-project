"""Non-issuance PROS004 full-history resource/recovery diagnostic.

This command has no source client, activation flag, scheduler, outcome or score.
It runs fictitious ESPN-shaped source bytes and explicitly simulated clocks in
an isolated diagnostic store. Actual UTC and monotonic resource clocks are kept
outside that harness. Passing this diagnostic does not establish capture,
issuance timeliness, remote recovery, or study activation.
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
from . import pros004_snapshot as snapshots
from .integrity import IntegrityError, canonical, digest, stamp, write_receipt
from .ledger import Ledger, LedgerRef, KINDS

SCHEMA = "nba-pros004-readiness-report-v1"
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


def synthetic_event_pack(history_ref, player_ids):
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
    with _synthetic_clock(INPUT_CLOCK):
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
        with _synthetic_clock(INPUT_CLOCK):
            history_ref = store.store_history(history_body)
            event_body = synthetic_event_pack(history_ref,player_ids)
            event_ref = store.store_event(event_body,history_ref)
            store.store_manifest()
        generation_seconds = []
        original_generate = producer.generate_forecast
        def timed_generate(*args,**kwargs):
            started = time.perf_counter()
            result = original_generate(*args,**kwargs)
            generation_seconds.append({"player_id":kwargs["player_id"],"model_key":kwargs["model_key"],
                                       "actual_elapsed_seconds":time.perf_counter()-started})
            return result
        cohort_started = time.perf_counter()
        with _synthetic_clock(GENERATION_CLOCK), patch.object(producer,"generate_forecast",side_effect=timed_generate):
            recovery = producer.issue_pair(store,event_ref,binding)
        cohort_seconds = time.perf_counter()-cohort_started
        if recovery["issued_models"] != 8:
            raise IntegrityError("synthetic diagnostic did not retain all eight original model records")
        originals = []
        with _synthetic_clock(GENERATION_CLOCK):
            for subject in recovery["subjects"]:
                for model in ("R0","K0"):
                    ref = LedgerRef.from_record(subject["forecasts"][model])
                    body = store.body(ref)
                    if body["joint_recipe"]["support_atom_count"] != inputs.PANEL_ROWS:
                        raise IntegrityError("diagnostic omitted full retained history atoms")
                    originals.append({"reference":ref.to_record(),"model_key":model,
                        "player_id":subject["player_id"],"encoded_envelope_bytes":_encoded_size(store,ref),
                        "original_body_sha256":digest(body),"joint_sha256":body["joint_recipe"]["joint_sha256"]})
            capacity = store.capacity_report()
        # Independently reopened copied receipts exercise local durable recovery.
        # No remote readback or activation evidence is claimed by this copy.
        recovery_started = time.perf_counter()
        readback_root = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="nml-pros004-readback-")))
        snapshot = snapshots.export_snapshot(store.root,readback_root/"snapshot")
        copied = readback_root/"copy"
        readback = snapshots.recover_snapshot(readback_root/"snapshot",copied)
        _verify_baseline_files(copied,existing)
        restored = records.Pros004Store(copied,diagnostic=True)
        diagnostics = {}
        replay_timings = []
        with _synthetic_clock(GENERATION_CLOCK):
            reread = restored.recover_event(event_ref,binding)
            if reread != recovery:
                raise IntegrityError("copied complete retained snapshot changed recovery metadata")
            for item in originals:
                ref = LedgerRef.from_record(item["reference"])
                body = restored.body(ref)
                if digest(body) != item["original_body_sha256"]:
                    raise IntegrityError("copy/restart changed original probabilities or clocks")
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
        plan = records.full_study_capacity()
        metadata_records = (plan["full_study_records_before_reserve"]-474+records.RESERVE_RECORDS)
        report = {"schema_version":SCHEMA,"mode":MODE,
            "actual_started_at":stamp(actual_started),"actual_completed_at":stamp(_actual_now()),
            "evidence":{"live_source_captures":0,"genuine_issuance":0,"statistical_grades":0,
                        "aggregate_comparison_executions":0,"activation":False,
                        "qualified_tickets":0,"financial_settlements":0},
            "source_sha256":source_hashes,"producer_binding":binding,
            "clock_harness":{"mode":"EXPLICITLY_SIMULATED_NON_ISSUANCE",
                "input_clock":stamp(INPUT_CLOCK),"generation_clock":stamp(GENERATION_CLOCK),
                "actual_timing_uses":"time.perf_counter outside the simulated clock harness",
                "proves_real_capture_or_issuance_timeliness":False},
            "synthetic_event":{"event_id":EVENT_ID,"event_starts_at":stamp(EVENT_START),
                "real_event_or_roster_claim":False,"selection_rule":"Four lowest numeric identities in retained history; invented two-per-team rosters",
                "player_ids":player_ids,"model_records":8,"observed_outcomes":0},
            "history":{"retained_input_record_id":inputs.INPUT_RECORD_ID,"rows":len(rows),
                "events":len({r.event_id for r in rows}),"normalized_bytes":inputs.PANEL_BYTES,
                "sha256":inputs.PANEL_SHA256,"encoded_envelope_bytes":_encoded_size(store,history_ref),
                "history_ref":history_ref.to_record(),"recovered_history_actual_seconds":history_seconds,
                "reconstructed_history_limitations_unchanged":True,"rows_dropped":0},
            "event_input":{"encoded_envelope_bytes":_encoded_size(store,event_ref),"event_ref":event_ref.to_record()},
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
                "cohort_generate_verify_persist_actual_seconds":cohort_seconds,
                "forecast_generation_actual_seconds":generation_seconds,
                "copy_restart_replay_actual_seconds":recovery_seconds,
                "joint_replay_actual_seconds":replay_timings,
                "total_actual_elapsed_seconds":time.perf_counter()-monotonic_started,
                "peak_process_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},
            "recovery":{"status":"PASS_LOCAL_COPY_RESTART_AND_COMPLETE_JOINT_REPLAY",
                "original_records_recovered":8,"full_joint_replays":2,"remote_recovery":False,
                "snapshot_manifest_id":snapshot["manifest_id"],"snapshot_readback":readback,
                "existing_baseline_records_preserved":existing["records"],
                "store_root":str(store.root),"store_retained_after_command":retained,
                "original_probabilities_and_clocks_preserved":True},
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
        "diagnostic_forecasts":8,"actual_elapsed_seconds":report["performance"]["total_actual_elapsed_seconds"]}).decode())


if __name__ == "__main__":
    main()

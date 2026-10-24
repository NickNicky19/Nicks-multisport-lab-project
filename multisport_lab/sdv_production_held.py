"""Bounded held execution inside the existing, globally serialized coordinator.

Only the capture process writes the index or collects source bytes. A waiting
shard recovers its immutable original input and uses the existing phase engine.
Clock ticks do not make HTTP requests. No timer or scheduler is installed here.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import shutil
import time

from .integrity import IntegrityError, canonical, digest, stamp
from . import sdv_production_common as common
from . import sdv_production_inputs as inputs
from . import sdv_production_coordinator as engine
from . import sdv_production_runner as runner

HOLD_SCHEMA="nba-sdv-production-held-task-v1"
MAX_HOLD_BYTES=4096
HOLD_FIELDS={"schema_version","protocol_id","mode","policy_id","plan_ref","plan_id","plan_source_pack_ref",
    "event_id","event_snapshot_id","event_starts_at","branch","cycle_id","shard_index","player_ids",
    "cohort_sha256","producer_binding_id","capture_opens_at","cutoff_at","issuance_closes_at",
    "created_at","expires_at","input_already_bound","hold_id"}
HOLD_DESCRIPTOR_FIELDS={"action","task_ref","branch","cycle_id","shard_index","final_source_pack_ref"}


def validate_hold(body,plan=None):
    common.exact(body,HOLD_FIELDS,"held worker task")
    common.require(len(canonical(body)) <= MAX_HOLD_BYTES,"Held original exceeds its four-KiB metadata budget")
    common.require(body["schema_version"] == HOLD_SCHEMA and body["protocol_id"] == common.PROTOCOL_ID
        and body["mode"] in inputs.MODES,"Wrong held worker scope")
    policy=common.policy_for_id(body["policy_id"])
    common.require(policy.get("held_runtime_maximum_seconds") and type(body["input_already_bound"]) is bool,
        "Held work needs its separately registered policy")
    for key in ("plan_ref","plan_source_pack_ref"):common.archive_ref(body[key])
    for key in ("plan_id","event_snapshot_id","cohort_sha256","producer_binding_id"):common.sha(body[key])
    common.require(type(body["shard_index"]) is int and body["branch"] == common.shard_branch(body["cycle_id"],body["shard_index"]),"Held shard identity differs")
    ids=body["player_ids"]
    common.require(type(ids) is list and 0 < len(ids) <= policy["players_per_shard"]
        and len(set(ids)) == len(ids) and all(type(pid) is str and pid.isascii() and pid.isdigit() and int(pid)>0 for pid in ids),"Held player identities differ")
    created=common.clock(body["created_at"]);start=common.clock(body["event_starts_at"])
    opens=common.clock(body["capture_opens_at"]);cutoff=common.clock(body["cutoff_at"])
    closes=common.clock(body["issuance_closes_at"]);expires=common.clock(body["expires_at"])
    common.require(created <= common.now() and created < cutoff and expires == closes
        and opens == start-timedelta(minutes=150) and cutoff == start-timedelta(minutes=90)
        and closes == cutoff+timedelta(seconds=policy["generation_window_seconds"])
        and expires-created <= timedelta(seconds=policy["held_runtime_maximum_seconds"]),"Held horizon or original event windows differ")
    if not body["input_already_bound"]:
        common.require(created <= opens-timedelta(seconds=policy["held_minimum_prepare_seconds"]),"Held task was admitted too late to prepare its capture")
    common.require(start.date() >= common.clock(policy["enabled_after"]).date(),"Held task precedes future policy activation")
    if plan is not None:
        inputs.validate_plan(plan)
        selected=[event for event in plan["events"] if event["cycle_id"] == body["cycle_id"]]
        common.require(len(selected) == 1,"Held event is absent from the original plan")
        event=selected[0]
        common.require(0 <= body["shard_index"] < len(event["shards"]),"Held shard is outside the complete original cohort")
        common.require(body["mode"] == plan["mode"] and body["plan_id"] == plan["plan_id"] and body["policy_id"] == plan["policy"]["policy_id"]
            and body["producer_binding_id"] == plan["producer_binding"]["binding_id"]
            and body["cohort_sha256"] == digest(event["candidates"])
            and body["player_ids"] == event["shards"][body["shard_index"]]
            and all(body[key] == event[key] for key in ("capture_opens_at","cutoff_at","issuance_closes_at"))
            and all(body[key] == event["event"][key] for key in ("event_id","event_snapshot_id","event_starts_at")),"Held task changed its exact plan/cohort/producer")
    common.check_seal(body,"hold_id");return body


def _descriptor(reference,body):
    return {"action":"HOLD","task_ref":reference,"branch":body["branch"],"cycle_id":body["cycle_id"],
        "shard_index":body["shard_index"],"final_source_pack_ref":None}


def _held(coordinator,descriptor):
    common.exact(descriptor,HOLD_DESCRIPTOR_FIELDS,"held descriptor")
    common.require(descriptor["action"] == "HOLD" and descriptor["final_source_pack_ref"] is None,"Held descriptor cannot inject a final source")
    body=validate_hold(coordinator.archive.get_json(descriptor["task_ref"]))
    common.require(body["mode"] == coordinator.mode and body["policy_id"] == coordinator.policy["policy_id"]
        and all(body[key] == descriptor[key] for key in ("branch","cycle_id","shard_index")),"Held descriptor changed its original task")
    plan=coordinator.archive.get_json(body["plan_ref"]);validate_hold(body,plan)
    registered=[(day,row) for day in coordinator.registry["days"] for row in day["shards"] if row["branch"] == body["branch"]]
    common.require(len(registered) == 1,"Held worker has no unique original registry shard")
    day,row=registered[0]
    common.require(day["plan_id"] == body["plan_id"] and day["plan_ref"] == body["plan_ref"]
        and day["source_pack_ref"] == body["plan_source_pack_ref"]
        and {"branch":body["branch"],"hold_ref":descriptor["task_ref"]} in day.get("held_tasks",[]),"Held worker was not durably registered")
    return body,plan,row


def prepare_holds(coordinator,tasks):
    """Persist complete-event HOLD inventories before GitHub receives its matrix.

    Selection uses event times and fixed cohorts, never forecast values. Events
    outside the horizon or complete-slot budget remain explicit exclusions.
    """
    policy=coordinator.policy
    if not policy.get("held_runtime_maximum_seconds"):return list(tasks),[]
    coordinator._authority();now=common.now();held=[];exclusions=[];covered=set()
    # An existing immediate ISSUE/GRADE path is not duplicated by a held writer.
    immediate={row["branch"] for row in tasks if row["action"] != "PREPARE"}
    available=max(0,policy["held_maximum_tasks"]-sum(row["action"] != "GRADE" for row in tasks if row["action"] != "PREPARE"))
    inventory=[]
    for day in coordinator.registry["days"]:
        plan=coordinator.archive.get_json(day["plan_ref"]);inputs.validate_plan(plan)
        if plan["policy"]["policy_id"] != policy["policy_id"]:continue
        for event in plan["events"]:inventory.append((common.clock(event["event"]["event_starts_at"]),day,plan,event))
    for _,day,plan,event in sorted(inventory,key=lambda item:(item[0],item[3]["event"]["event_id"])):
        rows=[row for row in day["shards"] if row["cycle_id"] == event["cycle_id"]]
        if not rows or any(row["branch"] in immediate for row in rows):continue
        if all(row["input_task_ref"] is not None and row["issued_input_task_ref"] == row["input_task_ref"] for row in rows):continue
        closes=common.clock(event["issuance_closes_at"]);cutoff=common.clock(event["cutoff_at"])
        bound=all(row["input_task_ref"] is not None for row in rows)
        reason=("ISSUANCE_ALREADY_OPEN_OR_CLOSED" if now >= cutoff else
            "OUTSIDE_HELD_HORIZON" if closes-now > timedelta(seconds=policy["held_runtime_maximum_seconds"]) else
            "CAPTURE_PREPARATION_MARGIN_MISSED" if not bound and now > common.clock(event["capture_opens_at"])-timedelta(seconds=policy["held_minimum_prepare_seconds"]) else
            "COMPLETE_EVENT_HELD_CAPACITY_UNAVAILABLE" if len(rows)>available else None)
        if reason:
            exclusions.append({"event_id":event["event"]["event_id"],"cycle_id":event["cycle_id"],"reason":reason,"shards":len(rows)})
            continue
        common.require(day["schema_version"] == runner.HELD_DAY_SCHEMA,"V2 held plan lacks its versioned registry inventory")
        for row in rows:
            prior=next((item for item in day["held_tasks"] if item["branch"] == row["branch"]),None)
            if prior is not None:
                reference=prior["hold_ref"];body=validate_hold(coordinator.archive.get_json(reference),plan)
            else:
                body=common.seal({"schema_version":HOLD_SCHEMA,"protocol_id":common.PROTOCOL_ID,"mode":plan["mode"],"policy_id":policy["policy_id"],
                    "plan_ref":day["plan_ref"],"plan_id":plan["plan_id"],"plan_source_pack_ref":day["source_pack_ref"],
                    **{key:event["event"][key] for key in ("event_id","event_snapshot_id","event_starts_at")},
                    "branch":row["branch"],"cycle_id":row["cycle_id"],"shard_index":row["shard_index"],"player_ids":event["shards"][row["shard_index"]],
                    "cohort_sha256":digest(event["candidates"]),"producer_binding_id":plan["producer_binding"]["binding_id"],
                    **{key:event[key] for key in ("capture_opens_at","cutoff_at","issuance_closes_at")},"created_at":stamp(now),
                    "expires_at":event["issuance_closes_at"],"input_already_bound":bound},"hold_id")
                validate_hold(body,plan);reference=coordinator.archive.put_json(body,tag=coordinator.tag)
                common.require(coordinator.archive.fresh_reader().get_json(reference) == body,"Held original independent readback differs")
                day["held_tasks"].append({"branch":row["branch"],"hold_ref":reference})
            held.append(_descriptor(reference,body));covered.add(row["branch"])
        available-=len(rows)
    coordinator._save("HELD_TASKS_READY",{"held_tasks":len(held),"coverage_exclusions":exclusions})
    return [row for row in tasks if row["branch"] not in covered]+held,exclusions


class RegistryReader:
    """Bounded cold readbacks; unchanged heads never fetch an archive object."""
    def __init__(self,source_root,root,archive,policy):
        self.source_root=Path(source_root);self.root=Path(root);self.archive=archive;self.policy=policy
        self.head=None;self.probes=0;self.readbacks=0

    def __call__(self):
        common.require(self.probes < self.policy["held_registry_maximum_probes"],"Held registry head-probe budget exhausted")
        self.probes+=1
        raw=runner._git(self.source_root,"ls-remote","--heads",common.REMOTE_URL,"refs/heads/"+runner.INDEX_BRANCH).stdout.decode().strip().splitlines()
        common.require(len(raw) == 1,"Held registry branch missing or ambiguous")
        fields=raw[0].split();common.require(len(fields) == 2 and fields[1] == "refs/heads/"+runner.INDEX_BRANCH,"Held registry remote identity differs")
        head=common.sha(fields[0],40)
        if head == self.head:return None
        common.require(self.readbacks < self.policy["held_registry_maximum_readbacks"],"Held registry full-readback budget exhausted")
        self.readbacks+=1;folder=self.root/str(self.readbacks)
        writer=runner.RegistryWriter(folder,archive=self.archive)
        body=writer.prepare(commit=head)
        self.head=head
        # These are independently recovered read-only caches, never originals.
        shutil.rmtree(folder)
        return body


def _runtime(coordinator,sleep,monotonic):
    if coordinator.mode == "PROSPECTIVE_RESEARCH":
        common.require(sleep is None and monotonic is None,"Genuine held execution cannot replace its clocks or sleeper")
    return sleep or time.sleep,monotonic or time.monotonic


def _wait(coordinator,target,deadline,sleep,monotonic,started,last):
    now=common.now()
    common.require(now >= last,"Actual held clock moved backwards")
    common.require(now <= deadline and monotonic()-started <= coordinator.policy["held_runtime_maximum_seconds"],"Held runtime expired")
    if now < target:
        sleep(min(coordinator.policy["held_runtime_poll_seconds"],(target-now).total_seconds(),(deadline-now).total_seconds()))
    return now


def run_worker(coordinator,descriptor,*,read_registry,sleep=None,monotonic=None):
    """Read-only input recovery, original PREPARE, actual T90, original ISSUE."""
    coordinator._authority();sleep,monotonic=_runtime(coordinator,sleep,monotonic)
    if coordinator.mode == "PROSPECTIVE_RESEARCH":common.require(type(read_registry) is RegistryReader,"Genuine held worker needs the bounded official read-only registry transport")
    body,plan,row=_held(coordinator,descriptor);policy=coordinator.policy
    started=monotonic();last=common.now();deadline=common.clock(body["expires_at"])
    report={"action":"HOLD","branch":body["branch"],"cycle_id":body["cycle_id"],"status":"HELD_WAITING_FOR_INPUT",
        "hold_ref":descriptor["task_ref"],"task_ref":None,"phases":[],"registry_probes":0,"registry_readbacks":0,"genuine_issued":0}
    # Long idle waits are local only. The fresh input normally binds at T150.
    probe_at=common.clock(body["capture_opens_at"])+timedelta(minutes=15)
    cutoff=common.clock(body["cutoff_at"])
    while row["input_task_ref"] is None:
        now=common.now()
        common.require(now < cutoff,"Held worker has no exact input recovered before T90")
        last=_wait(coordinator,probe_at,deadline,sleep,monotonic,started,last)
        if common.now() < probe_at:continue
        common.require(report["registry_probes"] < policy["held_registry_maximum_probes"],"Held registry head-probe budget exhausted")
        report["registry_probes"]+=1
        current=read_registry()
        if current is not None:
            report["registry_readbacks"]+=1
            common.require(report["registry_readbacks"] <= policy["held_registry_maximum_readbacks"],"Held registry full-readback budget exhausted")
            coordinator.registry=runner.validate_registry(deepcopy(current))
            _,_,row=_held(coordinator,descriptor)
        probe_at=common.now()+timedelta(seconds=policy["held_registry_poll_seconds"])
    # Retain this exact input across both phases. A later projection cannot rebind it.
    task_ref=deepcopy(row["input_task_ref"]);task=engine.validate_task(coordinator.archive.get_json(task_ref))
    common.require(task["player_ids"] == body["player_ids"] and task["plan_ref"] == body["plan_ref"]
        and task["plan_source_pack_ref"] == body["plan_source_pack_ref"],"Held input task changed its original cohort or plan")
    actual={"action":"PREPARE","task_ref":task_ref,"branch":body["branch"],"cycle_id":body["cycle_id"],"shard_index":body["shard_index"],"final_source_pack_ref":None}
    common.require(common.now() < cutoff,"Held input recovery completed too late for intent preparation")
    result=coordinator.work(actual);report["phases"].append(result);report["task_ref"]=task_ref
    common.require(result["status"] == "PREPARED" and not result.get("durability_error") and not result.get("status_retention_error"),"Held preparation remains failed or unacknowledged")
    while common.now() < cutoff:last=_wait(coordinator,cutoff,deadline,sleep,monotonic,started,last)
    _wait(coordinator,common.now(),deadline,sleep,monotonic,started,last)
    actual["action"]="ISSUE";result=coordinator.work(actual);report["phases"].append(result)
    report.update(status=result["status"],genuine_issued=result.get("genuine_issued",0))
    for key in ("error","durability_error","status_retention_error","attempt_closure_error"):
        if result.get(key):report[key]=result[key]
    return report


def run_capturer(coordinator,descriptors,*,sleep=None,monotonic=None,publish=None):
    """The sole mutable registry owner while the peer shard workers wait."""
    coordinator._authority();sleep,monotonic=_runtime(coordinator,sleep,monotonic)
    common.require(type(descriptors) is list and 0 < len(descriptors) <= coordinator.policy["held_maximum_tasks"],"Invalid complete held batch")
    if coordinator.mode == "PROSPECTIVE_RESEARCH":common.require(publish is None,"Genuine held publication cannot replace the existing verifier")
    bodies=[_held(coordinator,descriptor)[0] for descriptor in descriptors]
    common.require(len({body["branch"] for body in bodies}) == len(bodies),"Duplicate held writers")
    cycles={body["cycle_id"] for body in bodies};policy=coordinator.policy
    started=monotonic();last=common.now();deadline=min(max(common.clock(body["expires_at"]) for body in bodies),last+timedelta(seconds=policy["held_runtime_maximum_seconds"]))
    common.require(last < deadline,"Held capture batch expired before this actual process started")
    attempted=set();recoveries=0;refreshes=checks=0;next_refresh=last;next_publication=last;pending=set()
    report={"action":"CAPTURE_HELD","status":"HELD_CAPTURE_COMPLETE","source_cycles_attempted":[],"refreshes":0,"publication_checks":0,"phase_errors":[]}
    def missing_inputs():
        return {cycle for cycle in cycles if any(row["input_task_ref"] is None for day in coordinator.registry["days"] for row in day["shards"] if row["cycle_id"] == cycle)}
    def recoverable_inputs():
        missing=missing_inputs();result=set()
        for day in coordinator.registry["days"]:
            result.update(row["cycle_id"] for row in day["pending_inputs"] if row["cycle_id"] in missing)
            if day["status"] != "INPUT_UNAVAILABLE":
                result.update(cycle for cycle in missing if any(attempt["phase"] == "INPUT" and attempt["status"] == "CAPTURED"
                    and attempt["source_pack_ref"] is not None and cycle in attempt["scope"] for attempt in coordinator.registry["attempts"]))
        return result
    # A late host cannot turn the already-closed new-capture gate into a
    # successful empty operating pass. Exact already captured bytes may recover.
    lost={body["cycle_id"] for body in bodies if last > common.clock(body["cutoff_at"])-timedelta(minutes=15)} & missing_inputs()-recoverable_inputs()
    if lost:
        report.update(status="PARTIAL_OR_FAILED",missing_input_cycles=sorted(lost),error="New capture window already closed without retained original input bytes")
        coordinator._save("HELD_CAPTURE_PARTIAL",{"reason":"HELD_INPUT_UNAVAILABLE","affected_cycles":sorted(lost)})
        return report
    while common.now() < deadline:
        now=common.now();last=_wait(coordinator,now,deadline,sleep,monotonic,started,last)
        due={body["cycle_id"] for body in bodies if common.clock(body["capture_opens_at"]) <= now <= common.clock(body["cutoff_at"])-timedelta(minutes=15)}-attempted
        # Mark before collection; failure never turns the local clock tick into
        # an automatic retry of the source request.
        if due:
            attempted.update(due)
            try:coordinator._new_inputs(cycle_ids=due)
            except (IntegrityError,OSError,ValueError) as error:report["phase_errors"].append({"phase":"INPUT","error":engine._error(error)})
        pending=recoverable_inputs()
        if pending and recoveries < policy["held_input_recovery_maximum_attempts"]:
            recoveries+=1
            try:coordinator._new_inputs(cycle_ids=pending)
            except (IntegrityError,OSError,ValueError) as error:report["phase_errors"].append({"phase":"INPUT_RECOVERY","error":engine._error(error)})
        boundaries=[common.clock(body[key]) for body in bodies for key in ("capture_opens_at","cutoff_at") if common.clock(body[key]) > common.now()]
        slack=not boundaries or min(boundaries)-common.now()>timedelta(seconds=policy["held_minimum_prepare_seconds"])
        if slack and common.now() >= next_refresh and refreshes < policy["held_capture_maximum_refreshes"]:
            refreshes+=1;next_refresh=common.now()+timedelta(seconds=policy["held_capture_refresh_seconds"])
            try:
                coordinator._final_sources()
                recovered=coordinator.refresh()
                if any(row.get("status") == "RECOVERY_FAILED" for row in recovered):
                    report["phase_errors"].append({"phase":"REFRESH","error":"One or more actual shard original readbacks failed; no completion is inferred"})
            except (IntegrityError,OSError,ValueError) as error:report["phase_errors"].append({"phase":"REFRESH","error":engine._error(error)})
        if slack and common.now() >= next_publication and checks < policy["held_publication_maximum_checks"]:
            checks+=1;next_publication=common.now()+timedelta(seconds=policy["held_publication_check_seconds"])
            try:
                if publish is not None:publish(coordinator)
                elif coordinator.mode == "PROSPECTIVE_RESEARCH":
                    coordinator.registry=runner.reconcile_publication(coordinator.registry,coordinator.writer,coordinator.archive)
            except (IntegrityError,OSError,ValueError) as error:report["phase_errors"].append({"phase":"PUBLICATION","error":engine._error(error)})
        target=min(deadline,common.now()+timedelta(seconds=policy["held_runtime_poll_seconds"]))
        last=_wait(coordinator,target,deadline,sleep,monotonic,started,last)
    report.update(source_cycles_attempted=sorted(attempted),input_recovery_attempts=recoveries,refreshes=refreshes,publication_checks=checks)
    if pending and recoveries >= policy["held_input_recovery_maximum_attempts"]:
        report["phase_errors"].append({"phase":"INPUT_RECOVERY","error":"Exact-input recovery attempt budget exhausted; retained partial binding is unchanged"})
    report["phase_errors"].extend(coordinator.reports)
    report["missing_input_cycles"]=sorted(missing_inputs())
    if report["phase_errors"] or report["missing_input_cycles"]:
        report["status"]="PARTIAL_OR_FAILED"
        coordinator._save("HELD_CAPTURE_PARTIAL",{"reason":"HELD_INPUT_OR_PUBLICATION_UNAVAILABLE",
            "affected_cycles":report["missing_input_cycles"],"phase_failures":len(report["phase_errors"])})
    return report

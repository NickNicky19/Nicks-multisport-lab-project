"""One bounded production coordinator in the existing NBA operations workflow.

Scheduled authority is authenticated from the actual main GitHub run. No caller
clock or developer dictionary grants prospective authority. The registry is a
recoverable projection; source and ledger originals live in immutable archives.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import fcntl
from functools import wraps
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

from .integrity import IntegrityError, canonical, digest, stamp, utc, _bounded_bytes, _decode
from .ledger import LedgerRef
from . import sdv_production_common as common

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_SCHEMA = "nba-sdv-production-registry-v1"
SOURCE_PACK_SCHEMA = "nba-sdv-production-source-pack-v1"
DAY_SCHEMA = "nba-sdv-production-day-v1"
INDEX_BRANCH = "records/sdv-production-index"
INDEX_PATH = "registry.json"
MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_ACTIVE_DAYS = 10
MAX_ARCHIVED_DAYS = 4096
_CAPABILITIES = {}


def _integrity_validation(function):
    @wraps(function)
    def checked(*args,**kwargs):
        try:return function(*args,**kwargs)
        except IntegrityError:raise
        except (KeyError,TypeError,ValueError,AttributeError,IndexError,OverflowError) as exc:
            raise IntegrityError("Malformed production evidence in "+function.__name__) from exc
    return checked


def _git(root, *args, check=True):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=60, check=False)
    common.require(not check or result.returncode == 0, "Production Git operation failed: " + args[0])
    return result


def _read_run(run_id):
    result = subprocess.run(["gh", "api", "repos/"+common.REPOSITORY+"/actions/runs/"+str(run_id)],
        capture_output=True, timeout=30, check=False)
    common.require(result.returncode == 0 and 0 < len(result.stdout) <= 384*1024,
        "Cannot authenticate the actual production workflow run")
    return result.stdout


def _encoded(raw):
    return {"base64":base64.b64encode(raw).decode(),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}


def _original(body, maximum):
    common.exact(body,{"base64","bytes","sha256"},"run original")
    try:raw=base64.b64decode(body["base64"],validate=True)
    except (ValueError,TypeError) as exc:raise IntegrityError("Invalid production original encoding") from exc
    common.require(type(body["bytes"]) is int and 0 < len(raw) == body["bytes"] <= maximum
        and hashlib.sha256(raw).hexdigest() == body["sha256"],"Production original bytes/hash differ")
    return _decode(raw)


@_integrity_validation
def validate_authorization(body):
    common.exact(body,{"schema_version","protocol_id","repository","workflow_path","event","actor",
        "run_id","run_attempt","head_sha","run_started_at","verified_at","event_original","run_original",
        "executed_files","authorization_id"},"authorization")
    common.require(body["schema_version"] == common.AUTH_SCHEMA and body["protocol_id"] == common.PROTOCOL_ID
        and body["repository"] == common.REPOSITORY and body["workflow_path"] == common.WORKFLOW
        and body["event"] in {"schedule","workflow_dispatch"},"Wrong production hosted authority")
    common.text(body["actor"]);common.sha(body["head_sha"],40)
    common.require(type(body["run_id"]) is int and body["run_id"] > 0
        and type(body["run_attempt"]) is int and body["run_attempt"] > 0,"Invalid production run identity")
    started=common.clock(body["run_started_at"]);verified=common.clock(body["verified_at"])
    common.require(started <= verified <= common.now(),"Production run clocks differ")
    event=_original(body["event_original"],32*1024);run=_original(body["run_original"],384*1024)
    common.require(type(event) is dict and event.get("repository",{}).get("full_name") == common.REPOSITORY,
        "Production event original repository differs")
    if body["event"] == "schedule":
        common.require(event.get("schedule") == common.CRON,"Unregistered production schedule")
    else:
        common.require(body["actor"] == common.OWNER and event.get("sender",{}).get("login") == common.OWNER
            and event.get("inputs",{}).get("mode","operate") == "operate","Owner production catch-up required")
    expected={"id":body["run_id"],"run_attempt":body["run_attempt"],"event":body["event"],
        "head_sha":body["head_sha"],"head_branch":"main","path":common.WORKFLOW,"status":"in_progress","conclusion":None}
    common.require(type(run) is dict and all(run.get(k) == v and type(run.get(k)) is type(v) for k,v in expected.items())
        and run.get("repository",{}).get("full_name") == common.REPOSITORY
        and run.get("actor",{}).get("login") == body["actor"]
        and stamp(utc(run.get("run_started_at"))) == body["run_started_at"],"Actual production run metadata differs")
    triggering=run.get("triggering_actor",{}).get("login")
    common.require(type(triggering) is str and triggering and (triggering == body["actor"]
        or body["run_attempt"] > 1 and triggering == common.OWNER),"Production rerun authority differs")
    if body["event"] == "workflow_dispatch":
        common.require(run.get("triggering_actor",{}).get("login") == common.OWNER,"Catch-up rerun owner differs")
    common.require(type(body["executed_files"]) is dict and 1 <= len(body["executed_files"]) <= 128,"Missing executed source inventory")
    for name, value in body["executed_files"].items():
        common.require(type(name) is str and name.startswith(("multisport_lab/","config/",".github/workflows/"))
            and ".." not in name.split("/"),"Unsafe production source path")
        common.sha(value)
    common.check_seal(body,"authorization_id")
    return body


def authorize_current_run():
    """One current-run metadata GET; the returned object is also process-bound."""
    env=os.environ
    common.require(env.get("GITHUB_ACTIONS") == "true" and env.get("GITHUB_REPOSITORY") == common.REPOSITORY
        and env.get("GITHUB_REF") == "refs/heads/main"
        and env.get("GITHUB_WORKFLOW_REF") == common.REPOSITORY+"/"+common.WORKFLOW+"@refs/heads/main",
        "Production requires the actual trusted main coordinator")
    event_name=env.get("GITHUB_EVENT_NAME");actor=env.get("GITHUB_ACTOR")
    common.require(event_name in {"schedule","workflow_dispatch"} and type(actor) is str and actor,
        "Missing actual production event/actor")
    run_id,attempt=env.get("GITHUB_RUN_ID",""),env.get("GITHUB_RUN_ATTEMPT","")
    common.require(re.fullmatch(r"[1-9][0-9]*",run_id) and re.fullmatch(r"[1-9][0-9]*",attempt),"Missing hosted run/attempt")
    event_raw=_bounded_bytes(Path(env.get("GITHUB_EVENT_PATH","")),32*1024)
    run_raw=_read_run(int(run_id));run=_decode(run_raw)
    common.require(type(run) is dict and type(run.get("triggering_actor")) is dict
        and run["triggering_actor"].get("login") == env.get("GITHUB_TRIGGERING_ACTOR",actor),"Actual triggering actor differs")
    head=_git(ROOT,"rev-parse","HEAD").stdout.decode().strip()
    common.require(env.get("GITHUB_SHA") == head,"Hosted checkout differs from executing revision")
    from .sdv_production_forecasts import make_source_binding
    binding=make_source_binding(head)
    body=common.seal({"schema_version":common.AUTH_SCHEMA,"protocol_id":common.PROTOCOL_ID,
        "repository":common.REPOSITORY,"workflow_path":common.WORKFLOW,"event":event_name,"actor":actor,
        "run_id":int(run_id),"run_attempt":int(attempt),"head_sha":head,
        "run_started_at":stamp(utc(run.get("run_started_at"))),"verified_at":stamp(common.now()),
        "event_original":_encoded(event_raw),"run_original":_encoded(run_raw),"executed_files":binding["files"]},"authorization_id")
    validate_authorization(body)
    _CAPABILITIES[body["authorization_id"]]=head
    return body


def require_execution_context(authorization,input_body,binding,*,phase="ISSUE"):
    require_current_authority(authorization)
    from .sdv_production_forecasts import validate_binding
    validate_binding(binding,current=True)
    common.require(authorization["executed_files"] == binding["files"]
        and input_body["producer_binding"] == binding and input_body["mode"] == "PROSPECTIVE_RESEARCH",
        "Executing source bytes or exact admitted input differs")
    start=common.clock(input_body["event"]["event_starts_at"]);actual=common.now()
    cutoff=start-timedelta(minutes=90)
    common.require(phase in {"PREPARE","ISSUE"},"Unknown production operating phase")
    opens,closes=(cutoff-timedelta(seconds=common.make_policy()["capture_lookback_seconds"]),cutoff) if phase == "PREPARE" else (cutoff,cutoff+timedelta(seconds=common.make_policy()["generation_window_seconds"]))
    common.require(opens <= actual <= closes and actual < start,"Production "+phase+" window is closed")
    return True


def require_current_authority(authorization):
    validate_authorization(authorization)
    common.require(_CAPABILITIES.get(authorization["authorization_id"]) == authorization["head_sha"],
        "Recovered authority is evidence, not a new issuance capability")
    common.require(os.environ.get("GITHUB_RUN_ID",str(authorization["run_id"])) == str(authorization["run_id"]),
        "Actual executing run changed")
    return authorization


@_integrity_validation
def validate_body(body):
    schema=body.get("schema_version")
    if schema == common.AUTH_SCHEMA:return validate_authorization(body)
    if schema == common.STATUS_SCHEMA:
        common.exact(body,{"schema_version","protocol_id","plan_id","cycle_id","phase","status","details","observed_at","run_id","status_id"},"status")
        common.require(body["protocol_id"] == common.PROTOCOL_ID,"Wrong production status protocol")
        for key in ("phase","status"):common.text(body[key],128)
        common.require(type(body["details"]) is dict and len(canonical(body["details"])) <= 4096,"Unbounded production failure details")
        common.require(common.clock(body["observed_at"]) <= common.now(),"Production status is future-dated")
        common.require(type(body["run_id"]) is int and body["run_id"] >= 0,"Invalid status run")
        common.sha(body["plan_id"])
        common.require(type(body["cycle_id"]) is str and re.fullmatch(r"prod-[0-9]{8}-[1-9][0-9]*-[a-f0-9]{12}",body["cycle_id"]),"Invalid status cycle identity")
        if body["status"] in {ISSUE_OPEN,ISSUE_CLOSED}:
            common.require(body["phase"] == "ISSUE","Issuance guard cannot represent another operating phase")
            details=body["details"];common.exact(details,{"task_id","shard_index","player_ids","error","final_source_pack_ref","processing_complete","issuance_attempt"},"issuance attempt details")
            common.sha(details["task_id"])
            common.require(type(details["shard_index"]) is int and 0 <= details["shard_index"] <= 3
                and type(details["player_ids"]) is list and 0 < len(details["player_ids"]) <= 16
                and len(set(details["player_ids"])) == len(details["player_ids"])
                and all(type(pid) is str and re.fullmatch(r"[1-9][0-9]*",pid) for pid in details["player_ids"])
                and details["processing_complete"] is False and details["final_source_pack_ref"] is None,
                "Issuance guard changed its exact shard or completion meaning")
            common.require(details["error"] is None or type(details["error"]) is str and len(details["error"]) <= 1000,"Unbounded issuance error")
            attempt=details["issuance_attempt"];common.exact(attempt,ISSUE_ATTEMPT_FIELDS,"issuance attempt")
            common.require(type(attempt["attempt_number"]) is int and attempt["attempt_number"] >= 1
                and type(attempt["run_attempt"]) is int and attempt["run_attempt"] >= 1
                and common.clock(attempt["opened_at"]) <= common.clock(body["observed_at"]),"Issuance attempt clocks differ")
            expected=digest({key:details[key] for key in ("task_id","shard_index","player_ids")}|{
                "run_id":body["run_id"],"run_attempt":attempt["run_attempt"],"opened_at":attempt["opened_at"],"attempt_number":attempt["attempt_number"]})
            common.require(attempt["attempt_id"] == expected,"Issuance attempt identity differs")
            if body["status"] == ISSUE_OPEN:
                common.require(body["observed_at"] == attempt["opened_at"] and all(attempt[key] is None for key in (
                    "open_status_id","footprint_snapshot_ref","footprint_snapshot_id","footprint_recovered_at")),"Open issuance attempt invents closure")
            else:
                common.sha(attempt["open_status_id"]);common.sha(attempt["footprint_snapshot_id"]);common.archive_ref(attempt["footprint_snapshot_ref"],diagnostic=True)
                common.require(common.clock(attempt["opened_at"]) <= common.clock(attempt["footprint_recovered_at"])
                    <= common.clock(body["observed_at"]),"Issuance closure precedes its independently recovered footprint")
        common.check_seal(body,"status_id");return body
    raise IntegrityError("Unsupported production runner record")


ISSUE_OPEN="ISSUANCE_ATTEMPT_OPEN"
ISSUE_CLOSED="ISSUANCE_ATTEMPT_CLOSED"
ISSUE_ATTEMPT_FIELDS={"attempt_id","attempt_number","run_attempt","opened_at","open_status_id","footprint_snapshot_ref","footprint_snapshot_id","footprint_recovered_at"}


ARCHIVE_BUDGET_SCHEMA="nba-sdv-production-global-archive-budget-v1"


def archive_object_liability(capacity):
    from .sdv_production_store import validate_capacity
    validate_capacity(capacity)
    return 2*(capacity["remaining_records"]+capacity["remaining_forensic_files"])+1


def shared_source_object_liability():
    policy=common.make_policy()
    chunks=(policy["maximum_csv_bytes"]+policy["archive_chunk_bytes"]-1)//policy["archive_chunk_bytes"]
    return policy["correction_capture_days"]*policy["maximum_final_captures_per_day"]*(2*chunks+6)


def make_archive_budget(rows,*,at=None):
    from .sdv_production_store import archive_liability
    policy=common.make_policy()
    rows=sorted(deepcopy(rows),key=lambda row:row["branch"])
    shared=(policy["correction_capture_days"]*policy["maximum_final_captures_per_day"]*
        (2*policy["maximum_csv_bytes"]+2*policy["maximum_metadata_bytes"])) if rows else 0
    parallel=policy["maximum_parallel_shards"]*policy["archive_object_bytes"] if rows else 0
    body=common.seal({"schema_version":ARCHIVE_BUDGET_SCHEMA,"protocol_id":common.PROTOCOL_ID,"policy_id":policy["policy_id"],
        "observed_at":stamp(at or common.now()),"shards":rows,"shared_source_bytes":shared,"parallel_headroom_bytes":parallel,
        "shared_metadata_bytes":512*1024*1024,"shared_source_objects":shared_source_object_liability() if rows else 0,
        "shared_metadata_objects":4096,"parallel_headroom_objects":256 if rows else 0,
        "reserved_objects":sum(archive_object_liability(row["capacity"]) for row in rows)+(shared_source_object_liability()+256 if rows else 0)+4096,
        "reserved_bytes":sum(archive_liability(row["capacity"]) for row in rows)+shared+parallel+512*1024*1024},"budget_id")
    return validate_archive_budget(body)


@_integrity_validation
def validate_archive_budget(body,*,registry=None):
    from .sdv_production_store import archive_liability,validate_capacity,empty_capacity
    common.exact(body,{"schema_version","protocol_id","policy_id","observed_at","shards","shared_source_bytes",
        "parallel_headroom_bytes","shared_metadata_bytes","reserved_bytes","shared_source_objects","shared_metadata_objects",
        "parallel_headroom_objects","reserved_objects","budget_id"},"global archive budget")
    policy=common.make_policy()
    common.require(body["schema_version"] == ARCHIVE_BUDGET_SCHEMA and body["protocol_id"] == common.PROTOCOL_ID
        and body["policy_id"] == policy["policy_id"] and common.clock(body["observed_at"]) <= common.now(),"Wrong/future global archive budget")
    common.require(type(body["shards"]) is list and len(body["shards"]) <= 128*MAX_ACTIVE_DAYS,"Unbounded global archive reservation")
    branches=[]
    for row in body["shards"]:
        common.exact(row,{"branch","snapshot_ref","capacity"},"archive budget shard")
        common.require(type(row["branch"]) is str and re.fullmatch(r"records/sdv-prod-[0-9]{8}-[1-9][0-9]*-[a-f0-9]{12}-s[0-3]",row["branch"]),"Invalid archive budget branch")
        validate_capacity(row["capacity"])
        if row["snapshot_ref"] is not None:common.archive_ref(row["snapshot_ref"])
        else:common.require(row["capacity"] == empty_capacity(),"An unopened shard must retain every fixed role reserve")
        branches.append(row["branch"])
    common.require(branches == sorted(set(branches)),"Duplicate or unordered global archive reservation")
    shared=(policy["correction_capture_days"]*policy["maximum_final_captures_per_day"]*
        (2*policy["maximum_csv_bytes"]+2*policy["maximum_metadata_bytes"])) if branches else 0
    parallel=policy["maximum_parallel_shards"]*policy["archive_object_bytes"] if branches else 0
    common.require(all(type(body[key]) is int for key in ("shared_source_bytes","parallel_headroom_bytes","shared_metadata_bytes","reserved_bytes"))
        and body["shared_source_bytes"] == shared and body["parallel_headroom_bytes"] == parallel
        and body["shared_metadata_bytes"] == 512*1024*1024
        and body["reserved_bytes"] == shared+parallel+512*1024*1024+sum(archive_liability(row["capacity"]) for row in body["shards"]),
        "Global archive reservation omits outstanding sources, roles or concurrent upload headroom")
    common.require(all(type(body[key]) is int for key in ("shared_source_objects","shared_metadata_objects","parallel_headroom_objects","reserved_objects"))
        and body["shared_source_objects"] == (shared_source_object_liability() if branches else 0)
        and body["shared_metadata_objects"] == 4096 and body["parallel_headroom_objects"] == (256 if branches else 0)
        and body["reserved_objects"] == sum(archive_object_liability(row["capacity"]) for row in body["shards"])+4096
            +(shared_source_object_liability()+256 if branches else 0),"Global archive reservation omits future immutable object counts")
    if registry is not None:
        actual={row["branch"]:row["snapshot_ref"] for day in registry["days"] for row in day["shards"]}
        common.require({row["branch"]:row["snapshot_ref"] for row in body["shards"]} == actual,
            "Global archive reservation does not cover every actual registered shard/snapshot")
        common.require(common.clock(body["observed_at"]) <= common.clock(registry["updated_at"]),"Archive reservation follows its registry")
    common.check_seal(body,"budget_id");return body


def empty_registry(at=None):
    return common.seal({"schema_version":REGISTRY_SCHEMA,"protocol_id":common.PROTOCOL_ID,
        "policy_id":common.make_policy()["policy_id"],"updated_at":stamp(at or common.now()),
        "last_run":None,"status":"NOT_STARTED","days":[],"archived_days":[],"attempts":[],"archived_attempts":[],"publication":None,"archive_budget":None},"registry_id")


@_integrity_validation
def validate_registry(body):
    common.exact(body,{"schema_version","protocol_id","policy_id","updated_at","last_run","status","days","archived_days","attempts","archived_attempts","publication","archive_budget","registry_id"},"registry")
    common.require(body["schema_version"] == REGISTRY_SCHEMA and body["protocol_id"] == common.PROTOCOL_ID
        and body["policy_id"] == common.make_policy()["policy_id"],"Wrong production registry policy")
    updated=common.clock(body["updated_at"])
    common.require(updated <= common.now(),"Production registry is future-dated")
    common.text(body["status"])
    common.require(type(body["days"]) is list and len(body["days"]) <= MAX_ACTIVE_DAYS
        and type(body["archived_days"]) is list and len(body["archived_days"]) <= MAX_ARCHIVED_DAYS,
        "Production registry capacity exhausted; retain originals and stop new issuance")
    seen=set()
    for day in body["days"]:
        validate_day(day);common.require(day["game_date"] not in seen,"Duplicate production day")
        seen.add(day["game_date"])
    for old in body["archived_days"]:
        common.exact(old,{"game_date","archive_ref"},"archived day")
        common.require(re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}",old["game_date"]),"Invalid archived day")
        common.archive_ref(old["archive_ref"])
    common.require(len({row["game_date"] for row in body["archived_days"]}) == len(body["archived_days"]),"Duplicate archived day pointer")
    common.require(type(body["attempts"]) is list and len(body["attempts"]) <= 512
        and type(body["archived_attempts"]) is list and len(body["archived_attempts"]) <= MAX_ARCHIVED_DAYS,
        "Production attempt inventory exhausted")
    ids=set()
    for attempt in body["attempts"]:
        validate_attempt(attempt)
        common.require(common.clock(attempt["started_at"]) <= updated and attempt["attempt_id"] not in ids,
            "Production reservation follows its registry or duplicates an original")
        ids.add(attempt["attempt_id"])
    for ref in body["archived_attempts"]:common.archive_ref(ref)
    if body["last_run"] is not None:
        common.exact(body["last_run"],{"run_id","run_attempt","observed_at","status","details"},"last run")
        common.require(type(body["last_run"]["run_id"]) is int and body["last_run"]["run_id"] > 0
            and type(body["last_run"]["run_attempt"]) is int and body["last_run"]["run_attempt"] > 0,"Invalid registry last run")
        common.clock(body["last_run"]["observed_at"]);common.text(body["last_run"]["status"])
        common.require(type(body["last_run"]["details"]) is dict and len(canonical(body["last_run"]["details"])) <= 8192,"Unbounded registry status details")
    if body["archive_budget"] is None:
        common.require(not any(day["shards"] for day in body["days"]),"Active shards require a closed global archive reservation")
    else:validate_archive_budget(body["archive_budget"],registry=body)
    common.require(len(canonical(body)) <= MAX_INDEX_BYTES,"Production index exceeds explicit capacity")
    common.check_seal(body,"registry_id");return body


@_integrity_validation
def validate_day(day):
    common.exact(day,{"schema_version","game_date","plan_ref","source_pack_ref","plan_id","shards","attempts","pending_inputs","status"},"registry day")
    common.require(day["schema_version"] == DAY_SCHEMA and type(day["game_date"]) is str
        and re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}",day["game_date"]),"Invalid registry game date")
    common.sha(day["plan_id"]);common.archive_ref(day["plan_ref"]);common.archive_ref(day["source_pack_ref"])
    common.require(type(day["shards"]) is list and len(day["shards"]) <= 128 and type(day["attempts"]) is list
        and len(day["attempts"]) <= 256,"Unbounded production day inventory")
    seen=set()
    for row in day["shards"]:
        common.exact(row,{"branch","cycle_id","event_id","shard_index","plan_id","latest_commit","snapshot_ref","input_task_ref","final_source_pack_ref",
            "prepared_input_task_ref","issued_input_task_ref","graded_source_pack_ref"},"registry shard")
        common.require(row["branch"] == common.shard_branch(row["cycle_id"],row["shard_index"])
            and row["cycle_id"].startswith("prod-"+day["game_date"].replace("-","")+"-"+row["event_id"]+"-")
            and row["plan_id"] == day["plan_id"] and row["branch"] not in seen,"Registry shard identity differs")
        seen.add(row["branch"])
        if row["latest_commit"] is not None:common.sha(row["latest_commit"],40)
        if row["snapshot_ref"] is not None:common.archive_ref(row["snapshot_ref"])
        for key in ("input_task_ref","final_source_pack_ref","prepared_input_task_ref","issued_input_task_ref","graded_source_pack_ref"):
            if row[key] is not None:common.archive_ref(row[key])
        for key in ("prepared_input_task_ref","issued_input_task_ref"):
            common.require(row[key] is None or row[key] == row["input_task_ref"],"Shard acknowledgment changed its immutable input task")
    for attempt in day["attempts"]:validate_attempt(attempt)
    common.require(type(day["pending_inputs"]) is list and len(day["pending_inputs"]) <= 32,"Unbounded pending shared-input binding")
    pending=set()
    for row in day["pending_inputs"]:
        common.exact(row,{"cycle_id","input_ref","input_source_pack_ref"},"pending shared input")
        common.require(row["cycle_id"] in {shard["cycle_id"] for shard in day["shards"]}
            and row["cycle_id"] not in pending,"Pending input changed the registered cycle")
        pending.add(row["cycle_id"]);common.archive_ref(row["input_ref"]);common.archive_ref(row["input_source_pack_ref"])
    common.text(day["status"]);return day


@_integrity_validation
def validate_attempt(body):
    common.exact(body,{"attempt_id","phase","scope","started_at","reserved_gets","used_gets","status","source_pack_ref"},"capture attempt")
    common.sha(body["attempt_id"])
    common.require(common.clock(body["started_at"]) <= common.now(),"Production capture reservation is future-dated")
    common.require(body["phase"] in {"PLAN","INPUT","FINAL"} and type(body["scope"]) is list
        and all(type(x) is str and len(x) < 256 for x in body["scope"])
        and body["reserved_gets"] == common.make_policy()["source_gets_per_capture"]
        and type(body["reserved_gets"]) is int,"Invalid capture reservation")
    common.require(body["used_gets"] is None or type(body["used_gets"]) is int and 0 <= body["used_gets"] <= body["reserved_gets"],"Invalid actual source GET count")
    common.require(body["status"] in {"RESERVED","CAPTURED","FAILED"},"Invalid capture status")
    common.require(body["attempt_id"] == digest({key:body[key] for key in ("phase","scope","started_at")}),"Capture reservation identity differs from original clocks/scope")
    common.require(body["scope"] and len(body["scope"]) == len(set(body["scope"])) <= 128,"Duplicate or empty capture scope")
    if body["status"] == "CAPTURED":
        common.require(body["source_pack_ref"] is not None and type(body["used_gets"]) is int and 4 <= body["used_gets"] <= 6,"Completed capture lacks its exact request/source evidence")
    if body["source_pack_ref"] is not None:common.archive_ref(body["source_pack_ref"])
    return body


@contextmanager
def retained_lock(root):
    root=Path(root).absolute()
    common.require(not any(p.is_symlink() for p in (root,*root.parents)),"Production work root traverses symlink")
    root.mkdir(parents=True,exist_ok=True)
    with (root/"coordinator.lock").open("a+b") as handle:
        try:fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise IntegrityError("Another production coordinator writer is active") from exc
        try:yield root
        finally:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


INDEX_POINTER_SCHEMA="nba-sdv-production-registry-pointer-v1"
MAX_INDEX_POINTER_BYTES=4096
REGISTRY_METADATA_RUN_BYTES=128*1024*1024


def _registry_content(body):
    # Run identity/check clocks are volatile. New missed-window facts and errors
    # remain operational changes even when no source request was possible.
    result={key:value for key,value in body.items() if key not in {"registry_id","updated_at","last_run"}}
    last=body.get("last_run")
    if last is not None:
        keys={"reason","missed_planning_dates","unacknowledged_issuance_shards","affected_game_dates","affected_branches","recent_errors"}
        facts={key:value for key,value in last["details"].items() if key in keys}
        if facts:result["recorded_operating_facts"]=facts
    return result


def validate_index_pointer(body):
    common.exact(body,{"schema_version","protocol_id","registry_id","raw_sha256","raw_bytes","chunks","pointer_id"},"registry archive pointer")
    common.require(body["schema_version"] == INDEX_POINTER_SCHEMA and body["protocol_id"] == common.PROTOCOL_ID,
        "Wrong registry archive pointer")
    common.sha(body["registry_id"]);common.sha(body["raw_sha256"])
    common.require(type(body["raw_bytes"]) is int and 0 < body["raw_bytes"] <= MAX_INDEX_BYTES
        and type(body["chunks"]) is list and len(body["chunks"]) == (body["raw_bytes"]+1024*1024-1)//(1024*1024),"Registry archive chunks differ from exact bounded body")
    for ref in body["chunks"]:common.archive_ref(ref)
    common.require(len(canonical(body)) <= MAX_INDEX_POINTER_BYTES,"Registry Git pointer exceeds four KiB")
    common.check_seal(body,"pointer_id");return body


class RegistryWriter:
    """Small derived pointer branch; normal forward Git pushes, never a reset."""
    def __init__(self,root,*,archive=None,remote_url=common.REMOTE_URL,allow_local_test_remote=False):
        self.root=Path(root).absolute();self.remote_url=str(remote_url);self.archive=archive
        self._metadata_bytes_reserved=0;self._metadata_objects_reserved=0
        if allow_local_test_remote:
            common.require(Path(self.remote_url).absolute().is_relative_to(Path(tempfile.gettempdir())),"Test registry remote must be temporary")
        else:common.require(self.remote_url == common.REMOTE_URL,"Registry must use this existing repository")
        self.commit=None
        self._last_registry=None

    def prepare(self,*,commit=None):
        common.require(not self.root.exists(),"Registry checkout must be independently initialized")
        self.root.mkdir(parents=True)
        _git(self.root,"init","--quiet");_git(self.root,"remote","add","origin",self.remote_url)
        probe=_git(self.root,"ls-remote","--heads","origin","refs/heads/"+INDEX_BRANCH).stdout.decode().strip().splitlines()
        common.require(len(probe) <= 1,"Ambiguous production index branch")
        if not probe:
            common.require(commit is None,"Requested production index commit has no published branch")
            _git(self.root,"checkout","--orphan",INDEX_BRANCH)
            self._last_registry=empty_registry();return deepcopy(self._last_registry)
        fields=probe[0].split();common.require(len(fields) == 2 and fields[1] == "refs/heads/"+INDEX_BRANCH,"Registry remote identity differs")
        _git(self.root,"fetch","--no-tags","origin","refs/heads/"+INDEX_BRANCH)
        head=_git(self.root,"rev-parse","FETCH_HEAD").stdout.decode().strip()
        common.require(head == fields[0],"Registry advanced during readback; retry read-only")
        chosen=head
        if commit is not None:
            common.sha(commit,40)
            common.require(_git(self.root,"merge-base","--is-ancestor",commit,head,check=False).returncode == 0,
                "Requested production index is not in independently recovered bounded branch history")
            chosen=commit
        _git(self.root,"checkout","--quiet","-b",INDEX_BRANCH,chosen);self.commit=chosen
        self._read_only=commit is not None
        paths=_git(self.root,"ls-tree","-r","--name-only","HEAD").stdout.decode().splitlines()
        common.require(paths == [INDEX_PATH],"Registry branch contains unrelated files")
        stored=_decode(_bounded_bytes(self.root/INDEX_PATH,MAX_INDEX_BYTES))
        if stored.get("schema_version") == INDEX_POINTER_SCHEMA:
            pointer=validate_index_pointer(stored)
            common.require(self.archive is not None,"Registry pointer recovery requires the existing exact-byte archive")
            chunks=[self.archive.get(ref,max_raw_bytes=1024*1024) for ref in pointer["chunks"]]
            raw=b"".join(chunks)
            common.require(len(raw) == pointer["raw_bytes"] and hashlib.sha256(raw).hexdigest() == pointer["raw_sha256"],"Registry original bytes differ from archived pointer")
            stored=_decode(raw)
            common.require(canonical(stored) == raw and stored.get("registry_id") == pointer["registry_id"],"Registry original identity/canonical bytes differ")
        self._last_registry=validate_registry(stored)
        return deepcopy(self._last_registry)

    def write(self,body):
        common.require(not getattr(self,"_read_only",False),"Exact historical registry readback is read-only")
        body={k:v for k,v in deepcopy(body).items() if k != "registry_id"}
        body["updated_at"]=stamp(common.now());body=common.seal(body,"registry_id");validate_registry(body)
        if self._last_registry is not None:
            by_id={row["attempt_id"]:row for row in body["attempts"]}
            for original in self._last_registry["attempts"]:
                current=by_id.get(original["attempt_id"])
                if current is None:
                    common.require(common.clock(original["started_at"]).date() < common.now().date()-timedelta(days=8)
                        and body["archived_attempts"] != self._last_registry["archived_attempts"],"Cannot erase a source reservation to reset its budget")
                    continue
                immutable=("attempt_id","phase","scope","started_at","reserved_gets")
                common.require(all(current[key] == original[key] for key in immutable),"Cannot change an original source reservation")
                if original["status"] in {"CAPTURED","FAILED"}:
                    common.require(current == original,"Cannot replace a completed or failed source observation")
            old_budget=self._last_registry.get("archive_budget")
            if old_budget is not None:
                old_rows={row["branch"]:row for row in old_budget["shards"]}
                for row in (body["archive_budget"] or {"shards":[]})["shards"]:
                    previous=old_rows.get(row["branch"])
                    if previous is not None and previous["snapshot_ref"] == row["snapshot_ref"]:
                        common.require(previous["capacity"] == row["capacity"],"Cannot reduce a retained immutable snapshot's future archive liabilities")
            days={day["game_date"]:day for day in body["days"]}
            archived={day["game_date"] for day in body["archived_days"]}
            for original in self._last_registry["days"]:
                current=days.get(original["game_date"])
                if current is None:
                    common.require(original["game_date"] in archived,"Cannot drop a retained day without its immutable archive pointer")
                else:
                    common.require(all(current[key] == original[key] for key in ("plan_id","plan_ref","source_pack_ref"))
                        and [row["branch"] for row in current["shards"]] == [row["branch"] for row in original["shards"]],
                        "Cannot replace a frozen daily plan or cohort")
        if self.commit is not None and self._last_registry is not None and _registry_content(body) == _registry_content(self._last_registry):
            # Return the actual retained original; do not claim a fresh durable
            # check clock without a new operational record.
            return deepcopy(self._last_registry)
        common.require(self.archive is not None,"Registry writes require the existing durable byte archive")
        raw=canonical(body);tag=common.archive_month(common.now());chunks=[]
        from .sdv_production_archive import _wire
        for offset in range(0,len(raw),1024*1024):
            chunk=raw[offset:offset+1024*1024]
            wire,_=_wire(chunk,tag,False)
            common.require(self._metadata_bytes_reserved+len(wire) <= REGISTRY_METADATA_RUN_BYTES,
                "One coordinator run exhausted its explicit registry metadata write budget")
            common.require(self._metadata_objects_reserved+1 <= 512,"One coordinator run exhausted its explicit registry metadata object budget")
            self._metadata_bytes_reserved+=len(wire);self._metadata_objects_reserved+=1
            chunks.append(self.archive.put(chunk,tag=tag))
        pointer=common.seal({"schema_version":INDEX_POINTER_SCHEMA,"protocol_id":common.PROTOCOL_ID,"registry_id":body["registry_id"],
            "raw_sha256":hashlib.sha256(raw).hexdigest(),"raw_bytes":len(raw),"chunks":chunks},"pointer_id")
        validate_index_pointer(pointer)
        from .sdv_daily_runner import _write_json
        _write_json(self.root/INDEX_PATH,pointer);_git(self.root,"add","--",INDEX_PATH)
        if _git(self.root,"diff","--cached","--quiet",check=False).returncode:
            _git(self.root,"-c","user.name=Nick's Multisport Lab","-c","user.email=research@users.noreply.github.com",
                "commit","--quiet","-m","Retain NBA production registry checkpoint")
        commit=_git(self.root,"rev-parse","HEAD").stdout.decode().strip()
        _git(self.root,"push","origin","HEAD:refs/heads/"+INDEX_BRANCH)
        with tempfile.TemporaryDirectory(prefix="nml-production-registry-readback-") as folder:
            other=RegistryWriter(Path(folder)/"fresh",archive=self.archive.fresh_reader(),remote_url=self.remote_url,
                allow_local_test_remote=self.remote_url != common.REMOTE_URL)
            observed=other.prepare()
            common.require(other.commit == commit and observed == body,"Independent registry recovery differs")
        self.commit=commit
        self._last_registry=deepcopy(body)
        return body


def source_routes(season,*,final=False):
    common.require(type(season) is int and 2000 <= season <= 2100,"Invalid production season")
    roles=[("schedule","espn_nba_schedules","nba_schedule_"+str(season)+".csv")]
    roles.append(("boxscore","espn_nba_player_boxscores","player_box_"+str(season)+".csv") if final
        else ("roster","espn_nba_rosters","rosters_"+str(season)+".csv"))
    return [{"role":role,"release_tag":tag,"asset_name":name,
        "metadata_url":"https://api.github.com/repos/sportsdataverse/sportsdataverse-data/releases/tags/"+tag,
        "asset_url":"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"+tag+"/"+name}
        for role,tag,name in roles]


def reserve_capture(registry,writer,*,phase,scope,at=None):
    """Reserve every possible GET durably BEFORE the first request starts."""
    at=at or common.now();policy=common.make_policy()
    attempts=registry["attempts"]
    today=[x for x in attempts if common.clock(x["started_at"]).date() == at.date()]
    hour=[x for x in today if common.clock(x["started_at"]).replace(minute=0,second=0,microsecond=0) == at.replace(minute=0,second=0,microsecond=0)]
    common.require(sum(x["reserved_gets"] for x in today)+6 <= policy["maximum_source_gets_per_utc_day"]
        and sum(x["reserved_gets"] for x in hour)+6 <= policy["maximum_source_gets_per_hour"],"Production source GET budget exhausted")
    limit=policy["maximum_final_captures_per_day"] if phase == "FINAL" else policy["maximum_plan_capture_attempts"] if phase == "PLAN" else policy["maximum_event_capture_attempts"]
    for event in scope:
        previous=[x for x in (today if phase == "FINAL" else attempts) if x["phase"] == phase and event in x["scope"]]
        common.require(len(previous) < limit,"Capture attempt limit reached; do not silently recapture")
    row={"attempt_id":digest({"phase":phase,"scope":scope,"started_at":stamp(at)}),"phase":phase,"scope":scope,
        "started_at":stamp(at),"reserved_gets":6,"used_gets":None,"status":"RESERVED","source_pack_ref":None}
    return row


def collect_sources(root,archive,*,season,tag,opens_at,closes_at,final=False,authorization=None):
    """Exactly two licensed publisher files, six GETs including redirects, no retries."""
    require_current_authority(authorization)
    from .sdv_daily_runner import BoundedCapture
    from .sdv_production_inputs import source_metadata
    policy=common.make_policy();capture=BoundedCapture(root,opens_at=opens_at,closes_at=closes_at)
    sources=[]
    for route in source_routes(season,final=final):
        metadata_raw,meta_receipt,_=capture.get(route["metadata_url"],limit=policy["maximum_metadata_bytes"],label=route["role"]+"_metadata")
        common.require(meta_receipt["status"] == 200,"Production publisher metadata failed")
        raw,receipt,location=capture.get(route["asset_url"],limit=policy["maximum_csv_bytes"],label=route["role"]+"_asset")
        started=receipt["retrieval_started_at"]
        if receipt["status"] == 302:
            common.require(type(location) is str,"Publisher asset redirect missing")
            raw,receipt,_=capture.get(location,limit=policy["maximum_csv_bytes"],label=route["role"]+"_redirect",redirect=True)
        common.require(receipt["status"] == 200,"Production publisher asset failed")
        clocks={"retrieval_started_at":started,"retrieved_at":receipt["retrieved_at"],
            "metadata_retrieval_started_at":meta_receipt["retrieval_started_at"],"metadata_retrieved_at":meta_receipt["retrieved_at"]}
        if route["role"] == "boxscore":
            metadata=final_metadata(raw,metadata_raw,route,**clocks)
        else:metadata=source_metadata(raw,metadata_raw,route,**clocks)
        sources.append({"role":route["role"],"metadata":metadata,
            "source_ref":archive.retain_source(raw,metadata,metadata_raw,tag=tag)})
    pack={"schema_version":SOURCE_PACK_SCHEMA,"protocol_id":common.PROTOCOL_ID,"sources":sources,
        "requests":capture.requests,"captured_at":stamp(common.now()),"attribution":source_attribution(),
        "authorization":authorization}
    pack=common.seal(pack,"source_pack_id")
    return archive.put_json(pack,tag=tag),pack


def source_attribution():
    return ["SportsDataverse sportsdataverse-data; publisher-stated CC BY 4.0; https://creativecommons.org/licenses/by/4.0/",
        "ESPN-derived via hoopR. No direct ESPN access authority or endorsement is inferred.",
        "Nick's Multisport Lab normalizes release CSVs and computes research distributions; exact originals and clocks retained."]


def final_metadata(raw,metadata_raw,route,**clocks):
    """Same publisher-byte binding for the separately admitted final CSV family."""
    from .sdv_production_inputs import source_metadata
    return source_metadata(raw,metadata_raw,route,**clocks)


@_integrity_validation
def recover_source_pack(ref,archive):
    pack=archive.get_json(ref)
    common.exact(pack,{"schema_version","protocol_id","sources","requests","captured_at","attribution","authorization","source_pack_id"},"source pack")
    common.require(pack["schema_version"] == SOURCE_PACK_SCHEMA and pack["protocol_id"] == common.PROTOCOL_ID
        and pack["attribution"] == source_attribution() and type(pack["sources"]) is list and len(pack["sources"]) == 2,
        "Wrong production source pack")
    common.check_seal(pack,"source_pack_id");captured=common.clock(pack["captured_at"])
    authorization=validate_authorization(pack["authorization"])
    verified=common.clock(authorization["verified_at"])
    common.require(verified <= captured <= common.now(),"Source capture precedes actual run verification")
    result={}
    for item in pack["sources"]:
        common.exact(item,{"role","metadata","source_ref"},"source pack item")
        common.require(item["role"] not in result,"Duplicate source role")
        recovered=archive.recover_source(item["source_ref"])
        raw,meta,original=recovered
        from .sdv_production_inputs import source_metadata
        common.require(meta == item["metadata"],"Recovered source pack metadata differs")
        clocks={k:meta[k] for k in ("retrieval_started_at","retrieved_at","metadata_retrieval_started_at","metadata_retrieved_at")}
        route=next(r for r in source_routes(int(re.search(r"(20[0-9]{2})\.csv$",meta["asset_name"]).group(1)),final=item["role"] == "boxscore") if r["role"] == item["role"])
        expected=final_metadata(raw,original,route,**clocks) if item["role"] == "boxscore" else source_metadata(raw,original,route,**clocks)
        common.require(expected == meta,"Recovered source metadata differs from original publisher bytes")
        result[item["role"]]=(raw,meta,original)
    common.require(type(pack["requests"]) is list and 4 <= len(pack["requests"]) <= 6,"Source pack request budget differs")
    previous=verified
    for number,row in enumerate(pack["requests"],1):
        common.require(type(row) is dict and row.get("request_number") == number and type(row.get("request_number")) is int
            and row.get("automatic_retries") == 0 and row.get("automatic_redirects") is False
            and row.get("status") in {200,302},"Invalid source request receipt")
        started=common.clock(row["retrieval_started_at"]);ended=common.clock(row["retrieved_at"])
        common.require(previous <= started <= ended <= captured,"Source request clocks conflict")
        previous=ended
        route=urllib.parse.urlsplit(row["route"])
        common.require(route.scheme == "https" and route.hostname in {"api.github.com","github.com","release-assets.githubusercontent.com"}
            and not route.query and not route.fragment and not route.username and not route.password,"Unsafe retained source request route")
        common.sha(row["sha256"])
    for role,(_,meta,_) in result.items():
        common.require(verified <= common.clock(meta["metadata_retrieval_started_at"]) <= common.clock(meta["retrieved_at"]) <= captured,
            "Source metadata is outside its actual authorized capture")
    # Authenticate the request chain, not merely its host and checksum shape.
    # No unrelated request may be substituted for either exact release body or
    # CSV. A 302 response is an observation, not the final asset's byte hash.
    cursor=0
    for item in pack["sources"]:
        role=item["role"];meta=item["metadata"]
        expected_route=next(r for r in source_routes(int(re.search(r"(20[0-9]{2})\.csv$",meta["asset_name"]).group(1)),final=role == "boxscore") if r["role"] == role)
        common.require(cursor+2 <= len(pack["requests"]),"Incomplete source request chain")
        metadata_row=pack["requests"][cursor];asset_row=pack["requests"][cursor+1];cursor+=2
        common.require(metadata_row["route"] == expected_route["metadata_url"] and metadata_row["status"] == 200
            and metadata_row["sha256"] == meta["metadata_sha256"] and metadata_row["bytes"] == meta["metadata_bytes"]
            and metadata_row["retrieval_started_at"] == meta["metadata_retrieval_started_at"]
            and metadata_row["retrieved_at"] == meta["metadata_retrieved_at"]
            and metadata_row["response_limit_bytes"] == common.make_policy()["maximum_metadata_bytes"],
            "Source metadata request differs from consumed original")
        common.require(asset_row["route"] == expected_route["asset_url"]
            and asset_row["retrieval_started_at"] == meta["retrieval_started_at"]
            and asset_row["response_limit_bytes"] == common.make_policy()["maximum_csv_bytes"],
            "Source asset request differs from canonical route/start")
        if asset_row["status"] == 302:
            common.require(cursor < len(pack["requests"]),"Source asset redirect observation is missing")
            asset_row=pack["requests"][cursor];cursor+=1
            common.require(urllib.parse.urlsplit(asset_row["route"]).hostname == "release-assets.githubusercontent.com"
                and asset_row["response_limit_bytes"] == common.make_policy()["maximum_csv_bytes"],"Source redirect did not reach admitted release host")
        common.require(asset_row["status"] == 200 and asset_row["sha256"] == meta["asset_sha256"]
            and asset_row["bytes"] == meta["asset_bytes"] and asset_row["retrieved_at"] == meta["retrieved_at"],
            "Source final response differs from consumed CSV bytes/clocks")
    common.require(cursor == len(pack["requests"]),"Unconsumed or unrelated source requests in capture pack")
    return pack,result


def preserve_failed_capture(root,archive,*,tag,authorization,error):
    """Keep actual bounded failure bytes; never call this an admitted input."""
    from .sdv_postgame_runner import safe_error
    root=Path(root);rows=[]
    path=root/"requests.json"
    if path.exists():
        rows=_decode(_bounded_bytes(path,64*1024))
    common.require(type(rows) is list and len(rows) <= 6,"Unbounded failed capture inventory")
    originals=[]
    for number,row in enumerate(rows,1):
        path=root/("request-%02d.body" % number)
        if not path.exists():continue
        if row.get("status") != 200:
            originals.append({"request_number":number,"bytes":row.get("bytes"),"sha256":row.get("sha256"),
                "raw_disposition":"ERROR_OR_REDIRECT_NOT_PUBLICLY_ARCHIVED"})
            continue
        raw=_bounded_bytes(path,common.make_policy()["maximum_csv_bytes"])
        common.require(len(raw) == row.get("bytes") and hashlib.sha256(raw).hexdigest() == row.get("sha256"),
            "Failed capture retained body differs from request evidence")
        refs=[archive.put(raw[offset:offset+1024*1024],tag=tag) for offset in range(0,len(raw),1024*1024)]
        originals.append({"request_number":number,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),
            "complete_within_response_bound":True,"chunk_refs":refs})
    body=common.seal({"schema_version":"nba-sdv-production-capture-failure-v1","protocol_id":common.PROTOCOL_ID,
        "authorization":authorization,"requests":rows,"retained_originals":originals,
        "recorded_at":stamp(common.now()),"status":"FAILED_NOT_ADMITTED","error":safe_error(error)},"failure_id")
    return archive.put_json(body,tag=tag)


def _public_get(path,limit):
    common.require(type(path) is str and re.fullmatch(r"[A-Za-z0-9_.-]+\.json",path),"Unsafe public data path")
    request=urllib.request.Request("https://nicknicky19.github.io/Nicks-multisport-lab-project/data/"+path,
        headers={"User-Agent":"NicksMultisportLab/publication-verification","Cache-Control":"no-cache"})
    with urllib.request.urlopen(request,timeout=25) as response:
        common.require(response.code == 200,"Public research data was not served successfully")
        raw=response.read(limit+1)
    common.require(0 < len(raw) <= limit,"Public research data exceeds publication budget")
    return raw


def verify_publication(expected_registry_id):
    """Verify actually served data and every referenced production page."""
    from . import sdv_production_publication as publication
    actual=common.now();manifest_raw=_public_get("manifest.json",2*1024*1024)
    manifest=_decode(manifest_raw);descriptor=manifest.get("production_research")
    common.require(descriptor is not None,"Actual public manifest has no production channel")
    publication.validate_descriptor(descriptor,now=actual)
    with tempfile.TemporaryDirectory(prefix="nml-production-public-readback-") as directory:
        root=Path(directory)
        index_raw=_public_get(descriptor["path"],1024*1024)
        common.require(hashlib.sha256(index_raw).hexdigest() == descriptor["sha256"],"Served production index hash differs")
        index=_decode(index_raw);publication.validate_index(index,now=actual)
        common.require(index["operations"]["registry_id"] == expected_registry_id,"Public production state is still an earlier registry")
        (root/descriptor["path"]).write_bytes(index_raw)
        total=len(index_raw);assets=[]
        for page in index["pages"]:
            raw=_public_get(page["path"],1024*1024);total+=len(raw)
            common.require(total <= common.make_policy()["public_maximum_bytes"],"Actual served production pages exceed total budget")
            common.require(hashlib.sha256(raw).hexdigest() == page["sha256"],"Served production page hash differs")
            (root/page["path"]).write_bytes(raw)
            assets.append({"path":page["path"],"bytes":len(raw),"sha256":page["sha256"]})
        publication.read_publication(root,descriptor,now=actual,allow_development=False)
    return {"schema_version":"nba-sdv-production-public-verification-v1","verified_at":stamp(common.now()),
        "registry_id":expected_registry_id,"served_build_commit":manifest["build_commit"],
        "manifest_sha256":hashlib.sha256(manifest_raw).hexdigest(),"index_sha256":descriptor["sha256"],
        "assets":assets,"counts":index["counts"]}


def reconcile_publication(registry,writer,archive):
    """No long polling: verify a pending dispatch on a subsequent coordinator."""
    from .sdv_postgame_runner import safe_error
    from .sdv_production_publication import publication_content_identity
    identity=publication_content_identity(registry);content=identity["content_id"]
    previous=registry.get("publication")
    if previous and previous.get("state") == "DISPATCH_REQUESTED":
        try:
            proof=verify_publication(previous["registry_id"])
            proof_ref=archive.put_json(proof,tag=common.archive_month(common.now()))
            registry["publication"]={**previous,"state":"PUBLICATION_VERIFIED","verified_at":proof["verified_at"],
                "served_build_commit":proof["served_build_commit"],"proof_ref":proof_ref,"error":None}
            return writer.write(registry)
        except (IntegrityError,OSError,ValueError) as exc:
            previous={**previous,"error":safe_error(exc)}
            registry["publication"]=previous
            # GitHub/Pages may need more than one quarter-hour. No repeated
            # dispatch while the previous request still has time to complete.
            if common.now()-common.clock(previous["requested_at"]) < timedelta(hours=1):
                return writer.write(registry)
            previous={**previous,"state":"PUBLICATION_FAILED_OR_UNOBSERVED"};registry["publication"]=previous
    if previous and previous.get("content_id") == content:
        if previous.get("state") == "PUBLICATION_VERIFIED" or previous.get("dispatch_attempts",0) >= 2:
            return registry
    # A plan alone is not a user-visible forecast; do not deploy unchanged or
    # empty content merely because a configured coordinator ran.
    if (not identity["has_operational_failure"] and not any(s["snapshot_ref"] is not None for day in registry["days"] for s in day["shards"])
            and not (previous and previous.get("content_id") != content)):
        return registry
    registry=writer.write(registry);state_commit=writer.commit
    requested=common.now()
    result=subprocess.run(["gh","workflow","run","pages.yml","--repo",common.REPOSITORY,"--ref","main",
        "-f","production_state_commit="+state_commit],capture_output=True,timeout=30,check=False)
    common.require(result.returncode == 0,"Production Pages dispatch rejected; originals remain durably recoverable")
    registry["publication"]={"content_id":content,"state":"DISPATCH_REQUESTED","requested_at":stamp(requested),
        "state_commit":state_commit,"registry_id":registry["registry_id"],"workflow_run_id":None,"verified_at":None,
        "served_build_commit":None,"proof_ref":None,"error":None,
        "dispatch_attempts":previous.get("dispatch_attempts",0)+1 if previous and previous.get("content_id") == content else 1}
    return writer.write(registry)


def failure_alert(report,work):
    """One project issue per UTC day; no messages outside the authorized repo."""
    from .sdv_postgame_runner import safe_error
    day=common.now().date().isoformat();title="NBA production operations failure "+day
    found=subprocess.run(["gh","issue","list","--repo",common.REPOSITORY,"--state","open","--search",title,"--json","number,title"],
        capture_output=True,timeout=30,check=False)
    common.require(found.returncode == 0,"Cannot inspect the existing production failure issue")
    rows=_decode(found.stdout)
    if any(row.get("title") == title for row in rows):return {"status":"EXISTING_DAILY_ALERT"}
    path=Path(work)/"issue-body.txt"
    path.write_text("A bounded NBA operations phase failed or remained partial. Original records are retained; no late replacement is authorized.\n\n"
        +"Run: "+str(report.get("run_id"))+"\nStatus: "+str(report.get("status"))+"\nReason: "+safe_error(report.get("error","See factual run artifact."))+"\n",encoding="utf-8")
    created=subprocess.run(["gh","issue","create","--repo",common.REPOSITORY,"--title",title,"--body-file",str(path)],
        capture_output=True,timeout=30,check=False)
    common.require(created.returncode == 0,"Production failure alert rejected; retained report remains available")
    return {"status":"CREATED","url":created.stdout.decode().strip()}


def execute(action,*,work_root,task=None):
    from .sdv_production_archive import GitHubReleaseArchive
    from .sdv_production_coordinator import Coordinator
    from .sdv_daily_runner import _write_json
    from .sdv_postgame_runner import safe_error
    report={"schema_version":"nba-sdv-production-execution-report-v1","protocol_id":common.PROTOCOL_ID,
        "action":action,"started_at":stamp(common.now()),"status":"STARTED","genuine_issued":0,
        "qualified_tickets":0,"financial_settlements":0,"run_id":int(os.environ.get("GITHUB_RUN_ID","0"))}
    with retained_lock(work_root) as work:
        writer=archive=authority=registry=None
        try:
            authority=authorize_current_run();archive=GitHubReleaseArchive(write_budget_bytes=REGISTRY_METADATA_RUN_BYTES,write_budget_objects=512)
            writer=RegistryWriter(work/"registry",archive=archive);registry=writer.prepare()
            coordinator=Coordinator(registry,writer,archive,authority,work/"phases")
            if action == "prepare":
                tasks=coordinator.prepare_tasks()
                common.require(type(tasks) is list,"Invalid production task inventory")
                urgent=[row for row in tasks if row["action"] != "GRADE"]
                grades=[row for row in tasks if row["action"] == "GRADE"]
                common.require(len(urgent) <= 128,"Complete due pregame inventory exceeds the registered 128-shard date budget")
                selected_grades=grades[:128]
                report.update(status="DUE_PHASES_PREPARED" if tasks else "NO_DUE_PHASE",tasks=urgent+selected_grades,
                    grading_tasks_deferred=len(grades)-len(selected_grades),phase_errors=coordinator.reports)
                output=os.environ.get("GITHUB_OUTPUT")
                if output:
                    with Path(output).open("a",encoding="utf-8") as handle:
                        handle.write("has_tasks="+("true" if urgent else "false")+"\n")
                        handle.write("has_grade_tasks="+("true" if selected_grades else "false")+"\n")
                        handle.write("has_failures="+("true" if coordinator.reports else "false")+"\n")
                        handle.write("matrix="+canonical({"include":[{"task":row} for row in urgent]}).decode()+"\n")
                        handle.write("grade_matrix="+canonical({"include":[{"task":row} for row in selected_grades]}).decode()+"\n")
            elif action == "work":
                common.require(type(task) is dict,"A production worker requires its exact archived task")
                report.update(coordinator.work(task))
            elif action == "finish":
                if hasattr(coordinator,"refresh"):
                    coordinator.refresh()
                registry=coordinator.registry
                registry=reconcile_publication(registry,writer,archive)
                report.update(status="REGISTRY_RECOVERED",publication=registry.get("publication"))
                failed=os.environ.get("PRODUCTION_PREPARE_HAS_FAILURES") == "true" or any(
                    os.environ.get(key) in {"failure","cancelled"} for key in ("PRODUCTION_PREGAME_RESULT","PRODUCTION_GRADE_RESULT"))
                if failed:
                    report.update(status="PARTIAL_OR_FAILED",error="One or more actual hosted phases failed; see exact run jobs and retained originals.")
                    registry["status"]="HOSTED_PHASES_PARTIAL_OR_FAILED"
                    registry["last_run"]={"run_id":authority["run_id"],"run_attempt":authority["run_attempt"],
                        "observed_at":stamp(common.now()),"status":registry["status"],"details":{
                            key:os.environ.get(key,"UNKNOWN") for key in ("PRODUCTION_PREPARE_HAS_FAILURES","PRODUCTION_PREGAME_RESULT","PRODUCTION_GRADE_RESULT")}}
                    writer.write(registry)
                    report["alert"]=failure_alert(report,work)
            else:raise IntegrityError("Unknown production action")
        except (IntegrityError,OSError,ValueError,subprocess.SubprocessError) as exc:
            report.update(status="PARTIAL_OR_FAILED",error=safe_error(exc))
            if authority is not None and action != "work":
                try:report["alert"]=failure_alert(report,work)
                except (IntegrityError,OSError,subprocess.SubprocessError) as alert_error:report["alert_error"]=safe_error(alert_error)
        finally:
            interrupted=sys.exc_info()[1]
            if interrupted is not None and report["status"] == "STARTED":
                report.update(status="PARTIAL_OR_FAILED",error=type(interrupted).__name__+": "+safe_error(interrupted))
            report["completed_at"]=stamp(common.now());_write_json(work/"execution-report.json",report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("prepare","work","finish"));parser.add_argument("--work-root",required=True)
    args=parser.parse_args(argv)
    task=_decode(os.environ.get("PRODUCTION_TASK_JSON","null").encode()) if args.action == "work" else None
    report=execute(args.action,work_root=args.work_root,task=task)
    print(canonical(report).decode())
    return 1 if report["status"] in {"PARTIAL_OR_FAILED","FAILED_OR_PARTIAL"} or report.get("durability_error") or report.get("status_retention_error") else 0


if __name__ == "__main__":raise SystemExit(main())

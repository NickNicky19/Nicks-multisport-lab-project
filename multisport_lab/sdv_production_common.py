"""Shared production identities and explicit budgets; frozen pilots stay separate."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re

from .integrity import IntegrityError, canonical, digest, stamp, utc
from .sdv_daily_producer import HISTORY_ID, HISTORY_ROWS, HISTORY_SHA256
from .pros004_producer import MODEL_VERSIONS, LAW_SHA256

PROTOCOL_ID = "NBA-SDV-PRODUCTION-001"
POLICY_SCHEMA = "nba-sdv-production-policy-v1"
POLICY_SCHEMA_V2 = "nba-sdv-production-policy-v2"
PLAN_SCHEMA = "nba-sdv-production-plan-v1"
INPUT_SCHEMA = "nba-sdv-production-input-v1"
FORECAST_SCHEMA = "nba-sdv-production-forecast-v1"
OUTCOME_SCHEMA = "nba-sdv-production-outcome-v1"
GRADE_SCHEMA = "nba-sdv-production-grade-v1"
COMPLETION_SCHEMA = "nba-sdv-production-completion-v1"
LOCAL_COMPLETION_SCHEMA = "nba-sdv-production-local-completion-v1"
AUTH_SCHEMA = "nba-sdv-production-run-v1"
INTENT_SCHEMA = "nba-sdv-production-intent-v1"
STATUS_SCHEMA = "nba-sdv-production-status-v1"
COLLECTION_SCHEMA = "nba-sdv-production-collection-v1"
CRON = "2,17,32,47 * * * *"
WORKFLOW = ".github/workflows/nba-operations.yml"
REPOSITORY = "NickNicky19/Nicks-multisport-lab-project"
REMOTE_URL = "https://github.com/" + REPOSITORY + ".git"
OWNER = "NickNicky19"
KINDS = {PLAN_SCHEMA:"input_captures", INPUT_SCHEMA:"input_captures",
         FORECAST_SCHEMA:"forecasts", OUTCOME_SCHEMA:"outcomes", GRADE_SCHEMA:"grades",
         COMPLETION_SCHEMA:"input_captures", LOCAL_COMPLETION_SCHEMA:"input_captures", AUTH_SCHEMA:"input_captures",
         INTENT_SCHEMA:"input_captures", STATUS_SCHEMA:"input_captures"}
ID_KEYS = {PLAN_SCHEMA:"plan_id", INPUT_SCHEMA:"input_id", FORECAST_SCHEMA:"forecast_id",
           OUTCOME_SCHEMA:"outcome_id", GRADE_SCHEMA:"grade_id", COMPLETION_SCHEMA:"completion_id",
           AUTH_SCHEMA:"authorization_id", INTENT_SCHEMA:"intent_id", STATUS_SCHEMA:"status_id",
           LOCAL_COMPLETION_SCHEMA:"completion_id"}

_POLICY = {
    "schema_version":POLICY_SCHEMA, "protocol_id":PROTOCOL_ID,
    "enabled_after":"2026-10-24T00:00:00.000000Z",
    "publisher_max_age_seconds":129600, "capture_lookback_seconds":3600,
    "generation_window_seconds":900, "original_latency_seconds":300,
    "cron":CRON, "planning_hour_utc":13, "planning_day_offset":-1,
    "planning_window_seconds":3600, "maximum_plan_capture_attempts":2,
    "selection":"ALL_VALID_SCHEDULED_NBA_EVENTS_AND_ACTIVE_SOURCE_ROSTER_MEMBERS",
    "maximum_events_per_game_date":32, "maximum_players_per_event":64,
    "players_per_shard":16, "maximum_source_rows":100000,
    "maximum_csv_bytes":64*1024*1024, "maximum_metadata_bytes":1024*1024,
    "source_gets_per_capture":6, "source_http_retries":0,
    "maximum_source_gets_per_utc_day":256, "maximum_source_gets_per_hour":24,
    "maximum_event_capture_attempts":2, "maximum_final_captures_per_day":2,
    "maximum_automatic_outcome_versions":2, "correction_capture_days":7,
    "runtime_ledger_records":512, "runtime_ledger_bytes":32*1024*1024,
    "archive_object_bytes":16*1024*1024, "archive_chunk_bytes":1024*1024,
    "archive_month_bytes":32*1024*1024*1024, "archive_total_bytes":64*1024*1024*1024,
    "runtime_disk_bytes":2*1024*1024*1024, "maximum_model_workers":2,
    "maximum_parallel_shards":16,
    "public_full_record_days":7, "public_page_bytes":1024*1024,
    "public_maximum_pages":1024, "public_maximum_bytes":512*1024*1024,
    "public_client_maximum_bytes":64*1024*1024,
    "remote_checkpoint_seconds":60, "github_transport_attempts":2, "checkpoint_subjects":4,
    "timely_admission":"ORIGINAL_AND_LOCAL_MARKER_INDEPENDENT_REMOTE_READBACK",
    "proof_retention":"REQUIRED_BEFORE_PUBLIC_ADMISSION_NONRECURSIVE_METADATA",
    "history_record_id":HISTORY_ID, "history_rows":HISTORY_ROWS,
    "history_panel_sha256":HISTORY_SHA256, "model_versions":MODEL_VERSIONS,
    "law_sha256":LAW_SHA256, "qualification":"UNAVAILABLE",
    "participation":"CONDITIONAL_ON_APPEARANCE",
    "upstream_observation":"UNKNOWN_UNLESS_SUPPLIED",
    "rationale":"Daily publisher cadence plus twelve hours of delay tolerance; quarter-hour hosted checks. "
        "Production CSVs use bounded exact chunks and immutable GitHub Release archives. "
        "These versioned future budgets do not change the original pilot limits. "
        "Quotas reserve outstanding grading liabilities and stop new issuance before exhaustion; evidence is never deleted.",
}

# Version 1 remains the exact historical registration, including its immutable
# identity. Version 2 is a separately registered future operating policy. Storage,
# source, statistical and settlement limits are inherited without modification.
_POLICY_V2 = {
    **deepcopy(_POLICY),
    "schema_version":POLICY_SCHEMA_V2,
    "enabled_after":"2026-10-25T00:00:00.000000Z",
    "planning_hour_utc":0,
    "planning_window_seconds":77400,
    "planning_close_exclusive":True,
    "held_runtime_maximum_seconds":21000,
    "held_runtime_poll_seconds":30,
    "held_registry_poll_seconds":30,
    "held_registry_maximum_probes":96,
    "held_registry_maximum_readbacks":16,
    "held_capture_refresh_seconds":300,
    "held_capture_maximum_refreshes":72,
    "held_publication_check_seconds":900,
    "held_publication_maximum_checks":24,
    "held_minimum_prepare_seconds":300,
    "held_maximum_tasks":16,
    "held_input_recovery_maximum_attempts":16,
    "final_capture_minimum_game_age_seconds":14400,
    "final_capture_minimum_interval_seconds":36000,
    "final_capture_window_seconds":86400,
    "rationale":"Future operating repair, effective only for UTC game dates from October 25, 2026. "
        "Planning runs on the prior UTC date from 00:00 strictly before 21:30. "
        "Held runners use registered bounded polling and metadata actions; original capture, cutoff, "
        "issuance, latency, publisher freshness, complete population, fixed history, laws and all storage/source limits remain unchanged. "
        "Full-day final-source checks retain the two-capture daily ceiling, require four hours of event age and ten hours between captures. "
        "This registration neither repairs the missed October 24 cycle nor activates collection or issuance.",
}


def now():
    return datetime.now(timezone.utc)


def require(ok, message):
    if not ok:
        raise IntegrityError(message)


def exact(value, fields, label):
    require(type(value) is dict and set(value) == set(fields), "Invalid production " + label)


def sha(value, length=64):
    require(type(value) is str and re.fullmatch(r"[a-f0-9]{"+str(length)+"}", value), "Invalid production hash")
    return value


def text(value, maximum=2048):
    require(type(value) is str and 0 < len(value) <= maximum and value.strip() == value, "Invalid production text")
    return value


def clock(value):
    try:
        require(type(value) is str and stamp(utc(value)) == value, "Production clocks require precise UTC")
        return utc(value)
    except (TypeError, ValueError) as exc:
        raise IntegrityError("Invalid production clock") from exc


def seal(body, key):
    return {**body, key:digest(body)}


def check_seal(body, key):
    require(body.get(key) == digest({k:v for k,v in body.items() if k != key}), "Production record checksum differs")


def make_policy(version="v1"):
    require(type(version) is str and version in {"v1","v2"},"Unknown registered production policy version")
    return seal(deepcopy(_POLICY if version == "v1" else _POLICY_V2), "policy_id")


def validate_policy(body):
    require(type(body) is dict and type(body.get("schema_version")) is str
        and body["schema_version"] in {POLICY_SCHEMA,POLICY_SCHEMA_V2},
        "Production policy differs from registered version")
    version="v1" if body["schema_version"] == POLICY_SCHEMA else "v2"
    require(canonical(body) == canonical(make_policy(version)), "Production policy differs from registered version")
    return body


def policy_for_id(policy_id):
    """Resolve a complete registered policy without changing the v1 default."""
    sha(policy_id)
    for version in ("v1","v2"):
        policy=make_policy(version)
        if policy["policy_id"] == policy_id:return policy
    raise IntegrityError("Unknown registered production policy identity")


def archive_ref(value, *, diagnostic=False):
    exact(value, {"tag", "name", "sha256", "bytes"}, "archive reference")
    tag_pattern = r"nml-nba-records-v1-[0-9]{6}"
    if diagnostic:
        tag_pattern = r"(?:nml-nba-records-v1-[0-9]{6}|diagnostics-nml-nba-[a-z0-9-]{1,64})"
    require(type(value["tag"]) is str and re.fullmatch(tag_pattern,value["tag"]), "Unregistered archive tag")
    if value["tag"].startswith("nml-nba-records-v1-"):
        require(1 <= int(value["tag"][-2:]) <= 12 and int(value["tag"][-6:-2]) > 0,"Invalid archive calendar month")
    sha(value["sha256"])
    require(value["name"] == "object-"+value["sha256"]+".z", "Archive name must bind exact uploaded bytes")
    require(type(value["bytes"]) is int and 0 < value["bytes"] <= _POLICY["archive_object_bytes"], "Archive object exceeds limit")
    return value


def archive_month(at):
    return "nml-nba-records-v1-"+utc(at).strftime("%Y%m")


def cycle_id(game_date, event_id, plan_id):
    require(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",game_date) and re.fullmatch(r"[1-9][0-9]*",event_id), "Invalid production cycle identity")
    return "prod-"+game_date.replace("-","")+"-"+event_id+"-"+sha(plan_id)[:12]


def shard_branch(cycle, index):
    require(re.fullmatch(r"prod-[0-9]{8}-[1-9][0-9]*-[a-f0-9]{12}",cycle), "Invalid production cycle")
    require(type(index) is int and 0 <= index < 4, "Production shard exceeds complete event cohort ceiling")
    return "records/sdv-"+cycle+"-s"+str(index)


def validate_body(body):
    require(type(body) is dict and body.get("protocol_id") == PROTOCOL_ID, "Wrong production record protocol")
    schema=body.get("schema_version")
    require(schema in KINDS, "Unsupported production record type")
    check_seal(body,ID_KEYS[schema])
    if schema in {PLAN_SCHEMA,INPUT_SCHEMA}:
        from . import sdv_production_inputs as inputs
        return (inputs.validate_plan if schema == PLAN_SCHEMA else inputs.validate_input)(body)
    if schema in {FORECAST_SCHEMA,OUTCOME_SCHEMA,GRADE_SCHEMA,INTENT_SCHEMA}:
        from . import sdv_production_forecasts as forecasts
        return forecasts.validate_body(body)
    if schema == COMPLETION_SCHEMA:
        exact(body,{"schema_version","protocol_id","target","local_completed_at","remote_recovered_at",
            "archive_ref","eligible","reasons","completion_id"},"completion")
        text(body["target"]); archive_ref(body["archive_ref"],diagnostic=True)
        local=clock(body["local_completed_at"]);remote=clock(body["remote_recovered_at"])
        require(local <= remote <= now() and type(body["eligible"]) is bool and type(body["reasons"]) is list
            and all(type(x) is str for x in body["reasons"]),"Production completion clocks/reasons differ")
        require(body["eligible"] == (not body["reasons"]),"Production admission must explain ineligibility")
        return body
    if schema == LOCAL_COMPLETION_SCHEMA:
        from .sdv_production_store import validate_local_completion
        return validate_local_completion(body)
    from . import sdv_production_runner as runner
    return runner.validate_body(body)

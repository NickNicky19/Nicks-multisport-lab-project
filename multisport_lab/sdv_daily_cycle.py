"""One declared daily-source cycle and authenticated owner manual-dispatch proof.

Nothing in this module schedules or activates a run. The online authorization
entrypoint is usable only in this repository's owner-dispatched main workflow.
An offline authorization validator checks retained evidence; a caller-created
dictionary is never a substitute for the entrypoint's actual GitHub query.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request

from .integrity import IntegrityError, _bounded_bytes, _decode, digest, load_json, stamp, utc
from .sdv_daily_inputs import INPUT_SCHEMA, PROTOCOL_ID, SELECTION_RULE, make_policy

REPOSITORY = "NickNicky19/Nicks-multisport-lab-project"
OWNER = "NickNicky19"
WORKFLOW_PATH = ".github/workflows/sdv-daily.yml"
CYCLE_SCHEMA = "nba-sdv-daily-cycle-v1"
AUTHORIZATION_SCHEMA = "nba-sdv-daily-authorization-v1"
BINDING_SCHEMA = "nba-sdv-daily-producer-binding-v1"
MAX_RUN_BYTES = 128 * 1024
MAX_EVENT_BYTES = 32 * 1024
MAX_AUTHORIZATION_BYTES = 256 * 1024
MODEL_VERSIONS = {"R0": "nba_joint_empirical_r0_v1",
                  "K0": "nba_joint_lagged_workload_prior_k0_v1"}
PRODUCER_VERSIONS = {key: "sdv-daily-" + key.lower() + "-producer-v1"
                     for key in MODEL_VERSIONS}
LAW_SHA256 = {"R0": "2a217b021ae25041920d14db6fbb1a14197ef4593b2b59965bbdef6f01304689",
              "K0": "282bb23a570bc6aaa217ab7f65ba223613c805801d8c479bc51aef0291b72be7"}
CYCLE_ID = "NBA-SDV-DAILY-001-20261023-401909094"
HISTORY_RECORD_ID = "dfa1c4345495eb3aa6b203f2e8309c89c112b6b78a36cd3d2c603d390776b6fc"
HISTORY_PANEL_SHA256 = "489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c"
HISTORY_ROWS = 26645
SOURCE_ASSETS = [
    {"role": "schedule", "release_tag": "espn_nba_schedules",
     "asset_name": "nba_schedule_2027.csv",
     "metadata_url": "https://api.github.com/repos/sportsdataverse/sportsdataverse-data/releases/tags/espn_nba_schedules",
     "asset_url": "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_schedules/nba_schedule_2027.csv"},
    {"role": "roster", "release_tag": "espn_nba_rosters",
     "asset_name": "rosters_2027.csv",
     "metadata_url": "https://api.github.com/repos/sportsdataverse/sportsdataverse-data/releases/tags/espn_nba_rosters",
     "asset_url": "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_rosters/rosters_2027.csv"},
]
EVENT = {"event_id": "401909094", "event_starts_at": "2026-10-23T01:30:00.000000Z",
         "home_team_id": "25", "away_team_id": "7"}
CANDIDATES = [
    {"player_id": "2991350", "player_label": "Alex Caruso", "team_id": "25", "opponent_id": "7"},
    {"player_id": "3133626", "player_label": "Kenrich Williams", "team_id": "25", "opponent_id": "7"},
    {"player_id": "3978", "player_label": "DeMar DeRozan", "team_id": "7", "opponent_id": "25"},
    {"player_id": "3064290", "player_label": "Aaron Gordon", "team_id": "7", "opponent_id": "25"},
]
CYCLE_FIELDS = {"schema_version", "protocol_id", "cycle_id", "registered_at", "event",
                "candidates", "selection_rule", "policy_id", "history_record_id",
                "history_rows", "history_panel_sha256", "source_schema_version",
                "producer_versions", "model_versions", "source_assets",
                "runner_start_earliest_at", "activation_deadline", "retrieval_opens_at",
                "cutoff_at", "issuance_closes_at", "records_branch", "qualification",
                "purpose", "cycle_digest"}
AUTHORIZATION_FIELDS = {"schema_version", "protocol_id", "cycle_id", "cycle_digest",
                        "policy_id", "producer_commit", "producer_binding_id", "repository",
                        "workflow_path", "workflow_run_id", "run_attempt", "actor",
                        "run_head_sha", "run_started_at", "checked_at", "confirmation",
                        "event_payload_sha256", "event_payload_base64", "run_metadata_base64",
                        "run_metadata_sha256", "executed_file_sha256", "authorization_id"}
INPUT_FIELDS = {"cycle_id", "producer_commit", "confirmation"}
_AUTHORIZATION_CONTEXTS = {}
DECLARED_CONFIG_PATHS = {"config/sdv_daily_cycle_v1.json", WORKFLOW_PATH}


def _now():
    return datetime.now(timezone.utc)


def _require(condition, message):
    if not condition:
        raise IntegrityError(message)


def _exact(value, fields, label):
    _require(type(value) is dict and set(value) == set(fields), "Invalid daily " + label)


def _sha(value, label, size=64):
    _require(type(value) is str and re.fullmatch(r"[a-f0-9]{" + str(size) + "}", value),
             "Invalid daily " + label)
    return value


def _clock(value, label):
    _require(type(value) is str and re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z", value),
        "Daily " + label + " requires precise UTC")
    try:
        return utc(value)
    except (TypeError, ValueError) as exc:
        raise IntegrityError("Invalid daily " + label) from exc


def _seal(value, key):
    return {**value, key: digest(value)}


def _check_seal(value, key):
    _require(value.get(key) == digest({k: v for k, v in value.items() if k != key}),
             "Daily " + key + " checksum mismatch")


def make_cycle(*, registered_at=None):
    """Prepare this one named proposal before generating any cycle outputs."""
    start = _clock(EVENT["event_starts_at"], "event start")
    cutoff = start - timedelta(minutes=90)
    body = {"schema_version": CYCLE_SCHEMA, "protocol_id": PROTOCOL_ID,
            "cycle_id": CYCLE_ID, "registered_at": stamp(registered_at or _now()),
            "event": deepcopy(EVENT), "candidates": deepcopy(CANDIDATES),
            "selection_rule": SELECTION_RULE, "policy_id": make_policy()["policy_id"],
            "history_record_id": HISTORY_RECORD_ID, "history_rows": HISTORY_ROWS,
            "history_panel_sha256": HISTORY_PANEL_SHA256, "source_schema_version": INPUT_SCHEMA,
            "producer_versions": deepcopy(PRODUCER_VERSIONS), "model_versions": deepcopy(MODEL_VERSIONS),
            "source_assets": deepcopy(SOURCE_ASSETS),
            "runner_start_earliest_at": stamp(start - timedelta(minutes=210)),
            "activation_deadline": stamp(start - timedelta(minutes=180)),
            "retrieval_opens_at": stamp(cutoff - timedelta(hours=1)),
            "cutoff_at": stamp(cutoff), "issuance_closes_at": stamp(cutoff + timedelta(minutes=15)),
            "records_branch": "records/sdv-daily-001-20261023-401909094",
            "qualification": "UNAVAILABLE", "purpose": "OPERATIONAL_RESEARCH_NO_ACCURACY_CLAIM"}
    return validate_cycle(_seal(body, "cycle_digest"))


def validate_cycle(cycle):
    """Validate the reserved identity and windows; this never activates it."""
    _exact(cycle, CYCLE_FIELDS, "cycle")
    _require(cycle["schema_version"] == CYCLE_SCHEMA and cycle["protocol_id"] == PROTOCOL_ID
             and cycle["cycle_id"] == CYCLE_ID and cycle["event"] == EVENT
             and cycle["candidates"] == CANDIDATES and cycle["selection_rule"] == SELECTION_RULE,
             "Daily cycle event/cohort differs from the declared reservation")
    _require(cycle["source_schema_version"] == INPUT_SCHEMA
             and cycle["policy_id"] == make_policy()["policy_id"]
             and cycle["history_record_id"] == HISTORY_RECORD_ID
             and type(cycle["history_rows"]) is int and cycle["history_rows"] == HISTORY_ROWS
             and cycle["history_panel_sha256"] == HISTORY_PANEL_SHA256
             and cycle["model_versions"] == MODEL_VERSIONS
             and cycle["producer_versions"] == PRODUCER_VERSIONS
             and cycle["source_assets"] == SOURCE_ASSETS,
             "Daily policy, history, producers or asset identities changed")
    _require(cycle["records_branch"] == "records/sdv-daily-001-20261023-401909094"
             and cycle["qualification"] == "UNAVAILABLE"
             and cycle["purpose"] == "OPERATIONAL_RESEARCH_NO_ACCURACY_CLAIM",
             "Daily destination or research scope changed")
    start = _clock(cycle["event"]["event_starts_at"], "event start")
    expected = {"runner_start_earliest_at": start - timedelta(minutes=210),
                "activation_deadline": start - timedelta(minutes=180),
                "retrieval_opens_at": start - timedelta(minutes=150),
                "cutoff_at": start - timedelta(minutes=90),
                "issuance_closes_at": start - timedelta(minutes=75)}
    for key, value in expected.items():
        _require(_clock(cycle[key], key) == value, "Daily reserved operating window changed")
    _require(_clock(cycle["registered_at"], "registration") <= _now()
             and _clock(cycle["registered_at"], "registration") < expected["activation_deadline"],
             "Daily cycle registration is future-dated or missed its deadline")
    _check_seal(cycle, "cycle_digest")
    return cycle


def load_cycle(path=None):
    path = Path(path) if path is not None else Path(__file__).resolve().parents[1] / "config/sdv_daily_cycle_v1.json"
    return validate_cycle(load_json(path, max_bytes=32 * 1024))


def _binding(binding):
    _exact(binding, {"schema_version", "commit", "files", "law_sha256", "binding_id"}, "producer binding")
    _require(binding["schema_version"] == BINDING_SCHEMA and binding["law_sha256"] == LAW_SHA256,
             "Wrong daily binding or changed model laws")
    _sha(binding["commit"], "reviewed producer commit", 40)
    _require(type(binding["files"]) is dict and 1 <= len(binding["files"]) <= 64,
             "Daily executed source-file inventory is missing or oversized")
    for path, sha in binding["files"].items():
        _require(type(path) is str and (path.startswith(("multisport_lab/", "scripts/"))
                 or path in DECLARED_CONFIG_PATHS)
                 and not any(part in {"", ".", ".."} for part in path.split("/"))
                 and len(path) <= 256, "Unsafe daily source path")
        _sha(sha, "executed source hash")
    _require(binding["files"].get("multisport_lab/baseline.py") == LAW_SHA256["R0"]
             and binding["files"].get("multisport_lab/development_003.py") == LAW_SHA256["K0"],
             "Daily binding omits or changes either frozen law")
    _check_seal(binding, "binding_id")
    return binding


def _raw_json(encoded, sha, maximum, label):
    _sha(sha, label + " hash")
    _require(type(encoded) is str and len(encoded) <= 4 * ((maximum + 2) // 3),
             "Oversized daily " + label)
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise IntegrityError("Invalid daily " + label + " encoding") from exc
    _require(0 < len(raw) <= maximum and base64.b64encode(raw).decode("ascii") == encoded
             and hashlib.sha256(raw).hexdigest() == sha, "Daily " + label + " bytes differ")
    value = _decode(raw)
    _require(type(value) is dict, "Invalid daily " + label)
    return value


def _run_identity(run, authorization):
    _require(run.get("id") == authorization["workflow_run_id"]
             and type(run.get("id")) is int
             and run.get("run_attempt") == authorization["run_attempt"]
             and type(run.get("run_attempt")) is int
             and run.get("event") == "workflow_dispatch" and run.get("path") == WORKFLOW_PATH
             and run.get("status") == "in_progress" and run.get("conclusion") is None
             and run.get("head_branch") == "main"
             and run.get("head_sha") == authorization["run_head_sha"]
             and type(run.get("actor")) is dict and run["actor"].get("login") == OWNER
             and type(run.get("repository")) is dict
             and run["repository"].get("full_name") == REPOSITORY,
             "GitHub run is not the exact owner-dispatched daily main workflow")
    triggering = run.get("triggering_actor")
    _require(triggering is None or type(triggering) is dict and triggering.get("login") == OWNER,
             "Daily workflow rerun was triggered by another actor")
    try:
        started = utc(run.get("run_started_at"))
    except (TypeError, ValueError) as exc:
        raise IntegrityError("GitHub run lacks a valid actual start") from exc
    _require(stamp(started) == authorization["run_started_at"], "GitHub run-start clock changed")


def validate_authorization(body, *, cycle=None, producer_binding=None, now=None):
    """Check retained authenticated-run evidence, without admitting a new call."""
    from .integrity import canonical
    _exact(body, AUTHORIZATION_FIELDS, "authorization")
    _require(len(canonical(body)) <= MAX_AUTHORIZATION_BYTES, "Oversized daily authorization")
    cycle = load_cycle() if cycle is None else validate_cycle(cycle)
    _require(body["schema_version"] == AUTHORIZATION_SCHEMA and body["protocol_id"] == PROTOCOL_ID
             and body["cycle_id"] == cycle["cycle_id"] and body["cycle_digest"] == cycle["cycle_digest"]
             and body["policy_id"] == cycle["policy_id"] and body["repository"] == REPOSITORY
             and body["workflow_path"] == WORKFLOW_PATH and body["actor"] == OWNER,
             "Daily authorization has another cycle, source policy or authority")
    _sha(body["producer_commit"], "authorized producer commit", 40)
    _sha(body["run_head_sha"], "workflow run commit", 40)
    _sha(body["producer_binding_id"], "authorized producer binding")
    _require(type(body["workflow_run_id"]) is int and body["workflow_run_id"] > 0
             and type(body["run_attempt"]) is int and body["run_attempt"] > 0,
             "Invalid daily workflow run/attempt")
    expected = "APPROVE " + cycle["cycle_id"] + " " + body["producer_commit"]
    _require(body["confirmation"] == expected, "Daily owner confirmation is not exact")
    started = _clock(body["run_started_at"], "workflow start")
    checked = _clock(body["checked_at"], "authorization check")
    _require(_clock(cycle["runner_start_earliest_at"], "earliest runner start") <= started <= checked
             < _clock(cycle["activation_deadline"], "activation deadline")
             and _clock(cycle["registered_at"], "registration") <= started
             and checked <= utc(now or _now()),
             "Daily owner dispatch missed its activation window or is future-dated")
    files = body["executed_file_sha256"]
    _require(type(files) is dict and 1 <= len(files) <= 64, "Missing daily executed source inventory")
    for name, value in files.items():
        _require(type(name) is str and (name.startswith(("multisport_lab/", "scripts/"))
                 or name in DECLARED_CONFIG_PATHS)
                 and not any(part in {"", ".", ".."} for part in name.split("/"))
                 and len(name) <= 256, "Unsafe authorized source path")
        _sha(value, "authorized source hash")
    _require(files.get("multisport_lab/baseline.py") == LAW_SHA256["R0"]
             and files.get("multisport_lab/development_003.py") == LAW_SHA256["K0"],
             "Authorized daily laws differ")
    _binding({"schema_version": BINDING_SCHEMA, "commit": body["producer_commit"],
              "files": files, "law_sha256": LAW_SHA256,
              "binding_id": body["producer_binding_id"]})
    if producer_binding is not None:
        binding = _binding(producer_binding)
        _require(body["producer_commit"] == binding["commit"]
                 and body["producer_binding_id"] == binding["binding_id"]
                 and files == binding["files"], "Daily authorization binds another producer")
    run = _raw_json(body["run_metadata_base64"], body["run_metadata_sha256"], MAX_RUN_BYTES, "run metadata")
    _run_identity(run, body)
    event = _raw_json(body["event_payload_base64"], body["event_payload_sha256"], MAX_EVENT_BYTES, "dispatch event")
    _require(type(event.get("repository")) is dict and event["repository"].get("full_name") == REPOSITORY
             and type(event.get("sender")) is dict and event["sender"].get("login") == OWNER
             and type(event.get("ref")) is str
             and event.get("ref") in {"main", "refs/heads/main"}, "Daily dispatch event authority/ref differs")
    inputs = event.get("inputs")
    _exact(inputs, INPUT_FIELDS, "dispatch inputs")
    _require(inputs == {"cycle_id": cycle["cycle_id"], "producer_commit": body["producer_commit"],
                        "confirmation": expected}, "Daily retained dispatch inputs differ")
    _check_seal(body, "authorization_id")
    return body


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch_run_metadata(run_id, token):
    """One authenticated GitHub administration GET, never a provider-data read."""
    request = urllib.request.Request(
        "https://api.github.com/repos/" + REPOSITORY + "/actions/runs/" + str(run_id),
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "NicksMultisportLab-daily-owner-dispatch"})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=20) as response:
            _require(response.status == 200, "GitHub owner-dispatch metadata was unavailable")
            raw = response.read(MAX_RUN_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise IntegrityError("GitHub owner-dispatch verification returned HTTP " + str(exc.code)) from None
    except urllib.error.URLError as exc:
        raise IntegrityError("GitHub owner-dispatch verification could not reach the existing API") from None
    _require(0 < len(raw) <= MAX_RUN_BYTES, "GitHub owner-dispatch metadata exceeded its bound")
    return raw


def _git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            check=False, timeout=15)
    _require(result.returncode == 0, "Daily source Git verification failed")
    return result.stdout


def _verify_executed_source(root, binding, run_head):
    root = Path(root).absolute()
    _require(not root.is_symlink() and _git(root, "rev-parse", "HEAD").decode().strip() == run_head,
             "Daily runtime checkout is not the authenticated workflow commit")
    _git(root, "merge-base", "--is-ancestor", binding["commit"], run_head)
    for relative, expected in binding["files"].items():
        path = root / relative
        _require(path.is_file() and not path.is_symlink()
                 and all(not parent.is_symlink() for parent in path.parents),
                 "Daily source inventory traverses a missing file or symlink")
        versions = [path.read_bytes(), _git(root, "show", binding["commit"] + ":" + relative),
                    _git(root, "show", run_head + ":" + relative)]
        _require(all(hashlib.sha256(raw).hexdigest() == expected for raw in versions),
                 "Daily executed, reviewed and workflow source bytes differ")


def _runtime_context():
    """Check the current runner, never a caller-provided environment dictionary."""
    _require(os.environ.get("GITHUB_ACTIONS") == "true"
             and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
             and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
             and os.environ.get("GITHUB_ACTOR") == OWNER
             and os.environ.get("GITHUB_TRIGGERING_ACTOR", OWNER) == OWNER
             and os.environ.get("GITHUB_REF") == "refs/heads/main",
             "Daily genuine operation requires the existing owner manual main workflow")
    workflow_ref = os.environ.get("GITHUB_WORKFLOW_REF", "")
    _require(workflow_ref == REPOSITORY + "/" + WORKFLOW_PATH + "@refs/heads/main",
             "Daily invocation did not use the reviewed manual workflow path")
    run_text, attempt_text = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    _require(re.fullmatch(r"[1-9][0-9]*", run_text) and re.fullmatch(r"[1-9][0-9]*", attempt_text),
             "Daily runtime lacks an actual GitHub run identity")
    event_path = Path(os.environ.get("GITHUB_EVENT_PATH", ""))
    _require(event_path.is_file() and not event_path.is_symlink(), "Daily dispatch event is missing")
    event_raw = _bounded_bytes(event_path, MAX_EVENT_BYTES)
    _require(bool(event_raw), "Daily dispatch event is empty")
    event = _decode(event_raw)
    _require(type(event) is dict, "Daily dispatch event is not an object")
    _require(type(event.get("repository")) is dict and event["repository"].get("full_name") == REPOSITORY
             and type(event.get("sender")) is dict and event["sender"].get("login") == OWNER
             and type(event.get("ref")) is str
             and event.get("ref") in {"main", "refs/heads/main"},
             "Daily dispatch event authority/ref differs")
    _exact(event.get("inputs"), INPUT_FIELDS, "dispatch inputs")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    _require(type(token) is str and bool(token), "Existing GitHub Actions authentication is unavailable")
    return {"run_id": int(run_text), "run_attempt": int(attempt_text),
            "token": token, "event": event, "event_raw": event_raw,
            "event_sha256": hashlib.sha256(event_raw).hexdigest(),
            "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest()}


def _matches_retained_context(context, body):
    _require(context["run_id"] == body["workflow_run_id"]
             and context["run_attempt"] == body["run_attempt"]
             and context["event_sha256"] == body["event_payload_sha256"],
             "Daily restart is not the original authorized workflow run, attempt and event")


def _cache_context(body, binding, context, root):
    _AUTHORIZATION_CONTEXTS[body["authorization_id"]] = {
        "run_id": context["run_id"], "run_attempt": context["run_attempt"],
        "event_sha256": context["event_sha256"], "token_sha256": context["token_sha256"],
        "binding_id": binding["binding_id"], "root": Path(root).absolute()}


def require_dispatch_context(authorization, binding):
    """Recheck a privately authenticated current-run context before new issuance.

    Retained proof alone cannot seed this process-local authority. Initial entry
    or a fresh-process restart must first authenticate the actual GitHub run.
    Repeated checks perform no HTTP request and never alter original proof.
    """
    cycle = load_cycle()
    binding = _binding(binding)
    validate_authorization(authorization, cycle=cycle, producer_binding=binding)
    context = _runtime_context()
    _matches_retained_context(context, authorization)
    cached = _AUTHORIZATION_CONTEXTS.get(authorization["authorization_id"])
    _require(cached is not None and all(cached[key] == context[key]
             for key in ("run_id", "run_attempt", "event_sha256", "token_sha256"))
             and cached["binding_id"] == binding["binding_id"],
             "Daily current run has not authenticated this retained authorization")
    _require(_clock(authorization["checked_at"], "original authorization") <= _now()
             <= _clock(cycle["issuance_closes_at"], "issuance close"),
             "Daily new issuance is outside the authorized operating window")
    _verify_executed_source(cached["root"], binding, authorization["run_head_sha"])
    _require(_now() <= _clock(cycle["issuance_closes_at"], "issuance close"),
             "Daily source verification completed after issuance closed")
    return authorization


def authenticate_retained_dispatch(authorization, binding, *, repository_root=None):
    """Authenticate one same-run restart without replacing its original approval.

    This performs one current-run GitHub GET. It admits no new authorization,
    rerun attempt, producer, input, start time or late generation. Read-only
    recovery remains possible after close without invoking this entrypoint.
    """
    cycle = load_cycle()
    binding = _binding(binding)
    validate_authorization(authorization, cycle=cycle, producer_binding=binding)
    _require(_clock(authorization["checked_at"], "original authorization") <= _now()
             <= _clock(cycle["issuance_closes_at"], "issuance close"),
             "Daily authorized restart missed its issuance window")
    context = _runtime_context()
    _matches_retained_context(context, authorization)
    live = _decode(_fetch_run_metadata(context["run_id"], context["token"]))
    _require(type(live) is dict, "Invalid current daily GitHub run")
    _run_identity(live, authorization)
    root = Path(repository_root) if repository_root is not None else Path(__file__).resolve().parents[1]
    _verify_executed_source(root, binding, authorization["run_head_sha"])
    _require(_now() <= _clock(cycle["issuance_closes_at"], "issuance close"),
             "Daily restart authentication completed after issuance closed")
    _cache_context(authorization, binding, context, root)
    return authorization


def authorize_owner_dispatch(cycle, producer_binding, *, repository_root=None):
    """Obtain authorization from the actual current owner-dispatched Actions run.

    No supplied authorization object or local `--approve` flag is accepted.
    Tests may patch private clock/transport boundaries; genuine callers cannot
    supply clocks, API bodies, another event file or an environment dictionary.
    """
    cycle = validate_cycle(cycle)
    binding = _binding(producer_binding)
    context = _runtime_context()
    start = _now()
    _require(_clock(cycle["runner_start_earliest_at"], "earliest runner start") <= start
             < _clock(cycle["activation_deadline"], "activation deadline"),
             "Daily activation is too early or its deadline has passed")
    confirmation = "APPROVE " + cycle["cycle_id"] + " " + binding["commit"]
    _require(context["event"]["inputs"] == {"cycle_id": cycle["cycle_id"], "producer_commit": binding["commit"],
              "confirmation": confirmation}, "Daily owner dispatch inputs are not exact")
    run_raw = _fetch_run_metadata(context["run_id"], context["token"])
    run = _decode(run_raw)
    _require(type(run) is dict and run.get("status") == "in_progress" and run.get("conclusion") is None,
             "Daily owner-dispatch run is not currently executing")
    run_head = run.get("head_sha")
    _sha(run_head, "workflow run commit", 40)
    try:
        run_started = stamp(utc(run.get("run_started_at")))
    except (TypeError, ValueError) as exc:
        raise IntegrityError("GitHub owner-dispatch run lacks its actual start") from exc
    provisional = {"workflow_run_id": context["run_id"], "run_attempt": context["run_attempt"],
                   "run_head_sha": run_head, "run_started_at": run_started}
    _run_identity(run, provisional)
    root = Path(repository_root) if repository_root is not None else Path(__file__).resolve().parents[1]
    _verify_executed_source(root, binding, run_head)
    checked = _now()  # after API response AND actual source-byte verification
    body = {"schema_version": AUTHORIZATION_SCHEMA, "protocol_id": PROTOCOL_ID,
            "cycle_id": cycle["cycle_id"], "cycle_digest": cycle["cycle_digest"],
            "policy_id": cycle["policy_id"], "producer_commit": binding["commit"],
            "producer_binding_id": binding["binding_id"], "repository": REPOSITORY,
            "workflow_path": WORKFLOW_PATH, "workflow_run_id": context["run_id"],
            "run_attempt": context["run_attempt"], "actor": OWNER, "run_head_sha": run_head,
            "run_started_at": run_started, "checked_at": stamp(checked), "confirmation": confirmation,
            "event_payload_sha256": context["event_sha256"],
            "event_payload_base64": base64.b64encode(context["event_raw"]).decode("ascii"),
            "run_metadata_base64": base64.b64encode(run_raw).decode("ascii"),
            "run_metadata_sha256": hashlib.sha256(run_raw).hexdigest(),
            "executed_file_sha256": deepcopy(binding["files"])}
    body = validate_authorization(_seal(body, "authorization_id"), cycle=cycle,
                                  producer_binding=binding, now=checked)
    _cache_context(body, binding, context, root)
    return body

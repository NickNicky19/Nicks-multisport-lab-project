"""One additive first-cycle grading coordinator; never a forecast producer.

Scheduled and owner-manual authority are checked against the current main run.
Recurring pregame issuance is NOT_IMPLEMENTED. No old producer is dispatched.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from .integrity import IntegrityError, _bounded_bytes, _decode, canonical, digest, stamp, utc
from .ledger import LedgerRef
from . import sdv_daily_cycle as cycles
from . import sdv_daily_producer as producer
from . import sdv_daily_runner as prior
from . import sdv_daily_grading as grading
from .sdv_daily_store import DailyStore, OUTCOME_EVIDENCE_SCHEMA
from .sdv_daily_remote import DailyGitCheckpointWriter, REMOTE_URL
from . import sdv_daily_publication as public

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ".github/workflows/nba-operations.yml"
CRON = "17 13 * * *"
PRODUCTION_CRON = "2,17,32,47 * * * *"
BRANCH = "records/sdv-daily-001-20261023-401909094"
FIRST_DAY, LAST_DAY = "2026-10-23", "2026-10-30"
AUTH_KIND = "Project-authored postgame run proof v1"
PARTIAL_KIND = "Project-authored postgame partial HTTP original v1"
PHASE = "POSTGAME_"
AUTH_BYTES = 384 * 1024
MAX_STARTED_CAPTURES = 2
PUBLIC_ROOT = "https://nicknicky19.github.io/Nicks-multisport-lab-project/data/"
MAX_PUBLIC_POLLS = 20


def _now():
    return datetime.now(timezone.utc)


def require(ok, message):
    if not ok:
        raise IntegrityError(message)


def safe_error(error):
    text = re.sub(r"[\x00-\x1f\x7f]", " ", str(error))
    # Redirect query strings can contain time-limited access material; neither
    # reports nor alerts need them. Original response bodies are retained apart.
    return re.sub(r"(https?://[^\s?#]+)[?#][^\s]*", r"\1", text)[:1200]


def operating_window(now):
    now = utc(now)
    day = now.date().isoformat()
    if day < FIRST_DAY:
        return "BEFORE_POSTGAME_WINDOW"
    if day > LAST_DAY:
        return "POSTGAME_RESERVATION_EXPIRED"
    opens = now.replace(hour=13, minute=0, second=0, microsecond=0)
    closes = now.replace(hour=14, minute=30, second=0, microsecond=0)
    return "OPEN" if opens <= now <= closes else "OUTSIDE_DAILY_POSTGAME_WINDOW"


def _git(root, *args, check=True):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True,
        text=True, check=False, timeout=60)
    require(not check or result.returncode == 0, "Postgame Git operation failed: " + args[0])
    return result


def authorize_current_run():
    """One real GitHub run GET; no supplied approval dictionary or fake actor."""
    event_name = os.environ.get("GITHUB_EVENT_NAME")
    actor = os.environ.get("GITHUB_ACTOR")
    require(os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("GITHUB_REPOSITORY") == cycles.REPOSITORY
        and os.environ.get("GITHUB_REF") == "refs/heads/main"
        and os.environ.get("GITHUB_WORKFLOW_REF") == cycles.REPOSITORY + "/" + WORKFLOW + "@refs/heads/main"
        and event_name in {"schedule", "workflow_dispatch"}
        and type(actor) is str and bool(actor), "Postgame requires its actual trusted main workflow")
    require(event_name != "workflow_dispatch" or actor == cycles.OWNER,
        "Manual postgame dispatch requires the repository owner")
    run_id, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    require(re.fullmatch(r"[1-9][0-9]*", run_id) and re.fullmatch(r"[1-9][0-9]*", attempt),
        "Postgame run/attempt identity missing")
    path = Path(os.environ.get("GITHUB_EVENT_PATH", ""))
    event_raw = _bounded_bytes(path, 32 * 1024)
    event = _decode(event_raw)
    require(type(event) is dict and type(event.get("repository")) is dict
        and event["repository"].get("full_name") == cycles.REPOSITORY,
        "Postgame event repository differs")
    if event_name == "schedule":
        require(event.get("schedule") in {CRON, PRODUCTION_CRON}, "Unregistered hosted schedule")
    else:
        require(event.get("inputs") in ({"cycle_id": cycles.CYCLE_ID},
                {"cycle_id": cycles.CYCLE_ID, "mode": "operate"})
            and type(event.get("sender")) is dict and event["sender"].get("login") == cycles.OWNER,
            "Postgame manual event is not the exact owner/cycle")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    require(type(token) is str and bool(token), "Existing GitHub workflow access unavailable")
    run_raw = cycles._fetch_run_metadata(int(run_id), token)
    run = _decode(run_raw)
    head = _git(ROOT, "rev-parse", "HEAD").stdout.strip()
    require(type(run) is dict and type(run.get("id")) is int and run["id"] == int(run_id)
        and run.get("run_attempt") == int(attempt) and type(run.get("run_attempt")) is int
        and run.get("event") == event_name and run.get("path") == WORKFLOW
        and run.get("head_branch") == "main" and run.get("head_sha") == head
        and os.environ.get("GITHUB_SHA") == head and run.get("status") == "in_progress"
        and run.get("conclusion") is None and type(run.get("repository")) is dict
        and run["repository"].get("full_name") == cycles.REPOSITORY
        and type(run.get("actor")) is dict and run["actor"].get("login") == actor,
        "Current GitHub postgame run proof differs from execution")
    triggering = os.environ.get("GITHUB_TRIGGERING_ACTOR", actor)
    require(type(run.get("triggering_actor")) is dict
        and run["triggering_actor"].get("login") == triggering
        and (event_name != "workflow_dispatch" or triggering == cycles.OWNER),
        "Postgame rerun actor differs")
    started = utc(run.get("run_started_at"))
    require(started <= _now() and started.date() == _now().date(), "Postgame run clocks conflict")
    frozen = producer.make_source_binding(grading.FIRST_PRODUCER)
    files = {}
    for name in ("multisport_lab/sdv_postgame_runner.py", "multisport_lab/sdv_daily_grading.py",
                 WORKFLOW, grading.DEFAULT_CONFIG_PATH):
        raw = _bounded_bytes(ROOT / name, 384 * 1024)
        stored = subprocess.run(["git", "show", head + ":" + name], cwd=ROOT,
            capture_output=True, timeout=20, check=False)
        require(stored.returncode == 0 and stored.stdout == raw,
            "Executed postgame source differs from trusted workflow commit")
        files[name] = hashlib.sha256(raw).hexdigest()
    require(operating_window(_now()) == "OPEN", "Postgame authorization completed outside its window")
    return {"schema_version": "nba-sdv-postgame-run-proof-v1", "cycle_id": cycles.CYCLE_ID,
        "repository": cycles.REPOSITORY, "workflow_path": WORKFLOW, "event": event_name,
        "actor": actor, "workflow_run_id": int(run_id), "run_attempt": int(attempt),
        "head_sha": head, "run_started_at": stamp(started), "verified_at": stamp(_now()),
        "frozen_producer_binding_id": frozen["binding_id"], "executed_file_sha256": files,
        "event_original_base64": base64.b64encode(event_raw).decode(),
        "event_original_sha256": hashlib.sha256(event_raw).hexdigest(),
        "run_original_base64": base64.b64encode(run_raw).decode(),
        "run_original_sha256": hashlib.sha256(run_raw).hexdigest()}


@contextmanager
def retained_lock(work):
    work = Path(work).absolute()
    require(not any(p.is_symlink() for p in (work, *work.parents)), "Postgame work root traverses symlink")
    work.mkdir(parents=True, exist_ok=True)
    with (work / "postgame.lock").open("a+b") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise IntegrityError("Another retained postgame writer is active") from exc
        try:
            yield work
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def fetch_existing_branch(destination):
    """Fresh object database and fixed branch; never executes fetched code."""
    destination = Path(destination)
    require(not destination.exists(), "Postgame independent readback must be new")
    destination.mkdir(parents=True)
    _git(destination, "init", "--quiet")
    _git(destination, "remote", "add", "origin", REMOTE_URL)
    probe = _git(destination, "ls-remote", "--exit-code", "--heads", "origin", "refs/heads/" + BRANCH, check=False)
    if probe.returncode == 2 and not probe.stdout.strip():
        return None
    require(probe.returncode == 0, "Postgame cannot inspect fixed remote records branch")
    fields = probe.stdout.strip().split()
    require(len(fields) == 2 and re.fullmatch(r"[a-f0-9]{40}", fields[0])
        and fields[1] == "refs/heads/" + BRANCH, "Ambiguous postgame records branch")
    _git(destination, "fetch", "--no-tags", "--depth=1", "origin", "refs/heads/" + BRANCH)
    head = _git(destination, "rev-parse", "FETCH_HEAD").stdout.strip()
    require(head == fields[0], "Postgame branch changed during independent fetch; retry read-only")
    _git(destination, "checkout", "--quiet", "--detach", "FETCH_HEAD")
    DailyStore(destination).recover()
    return {"commit": head, "branch": BRANCH}


def _eligible(store):
    recovered = store.recover()
    return [(ref, body) for ref, body in recovered["forecasts"]
        if body["cycle_id"] == cycles.CYCLE_ID and body["mode"] == "PROSPECTIVE_RESEARCH"
        and body["producer_binding"]["commit"] == grading.FIRST_PRODUCER
        and store.admission(ref)["eligible"]]


def _operations(store):
    return [(ref, body) for ref, body in store.records()
        if body["schema_version"] == prior.OPERATION_SCHEMA and body["phase"].startswith(PHASE)]


def capacity_preflight(store):
    inventory = store.capacity(planned_forecasts=8)
    records = store.records()
    operations = [body for _, body in _operations(store)]
    started = {body["phase"][len(PHASE):] for body in operations
        if body["status"] == "POSTGAME_CAPTURE_STARTED"}
    closed = {body["phase"][len(PHASE):] for body in operations
        if re.fullmatch(r"POSTGAME_\d{4}-\d{2}-\d{2}", body["phase"])
        and body["status"] != "POSTGAME_CAPTURE_STARTED"}
    raw = {}
    authorities = outcomes = grades = 0
    for _, body in records:
        schema = body["schema_version"]
        if schema == producer.OUTCOME_SCHEMA: outcomes += 1
        elif schema == producer.GRADE_SCHEMA: grades += 1
        if schema != OUTCOME_EVIDENCE_SCHEMA:
            continue
        metadata = body["metadata"]; kind = metadata["source_kind"]
        if kind == AUTH_KIND:
            authorities += 1
            continue
        if kind == grading.PROOF_KIND: ceiling, tag = grading.MAX_PROOF_ENVELOPE, "proof"
        elif kind in {"SportsDataverse NBA schedule CSV", "SportsDataverse NBA player boxscore CSV"}:
            ceiling, tag = grading.MAX_CSV_ENVELOPE, kind
        elif kind == PARTIAL_KIND:
            ceiling, tag = (AUTH_BYTES if metadata["source_url"].startswith("https://api.github.com/")
                else grading.MAX_CSV_ENVELOPE), "partial"
        else:
            continue
        day = metadata["retrieved_at"][:10]
        raw.setdefault(day, []).append((ceiling, tag))
    started |= set(raw)
    require(len(started) <= MAX_STARTED_CAPTURES, "Retained source attempts exceed the registered two-attempt bound")
    # Exact-original dedup keeps an interrupted proof/CSV plus missing raw
    # source bodies within the same 7.5-MiB capture envelope as success.
    partial_per_attempt = 2 * AUTH_BYTES + 2 * grading.MAX_CSV_ENVELOPE
    complete_per_attempt = grading.MAX_PROOF_ENVELOPE + 2 * grading.MAX_CSV_ENVELOPE
    per_attempt = max(partial_per_attempt, complete_per_attempt)
    future_attempts = MAX_STARTED_CAPTURES - len(started)
    raw_bytes, raw_records = future_attempts * per_attempt, future_attempts * 4
    for day in started:
        retained = raw.get(day, [])
        tags = {tag for _, tag in retained}
        complete = {"proof", "SportsDataverse NBA schedule CSV", "SportsDataverse NBA player boxscore CSV"} <= tags
        if day in closed or complete:
            continue
        require(len(retained) <= 4 and sum(size for size, _ in retained) <= per_attempt,
            "Interrupted source retention exceeded its per-attempt reserve")
        raw_bytes += per_attempt - sum(size for size, _ in retained)
        raw_records += 4 - len(retained)
    corrections = len(store.corrections())
    used = {"authorities": authorities, "reports": len(operations), "outcomes": outcomes,
        "grades": grades, "corrections": corrections}
    slots = {"authorities": (8, AUTH_BYTES), "reports": (24, 8 * 1024),
        "outcomes": (8, 32 * 1024), "grades": (16, 32 * 1024), "corrections": (12, 8 * 1024)}
    require(all(used[key] <= maximum for key, (maximum, _) in slots.items()),
        "Postgame retained metadata/statistical records exceed registered role ceilings")
    reserved_records = raw_records + sum(maximum - used[key] for key, (maximum, _) in slots.items())
    reserved_bytes = raw_bytes + sum((maximum - used[key]) * size for key, (maximum, size) in slots.items())
    result = {"existing_records": inventory["existing_records"], "existing_bytes": inventory["existing_bytes"],
        "reserved_records": reserved_records, "reserved_bytes": reserved_bytes,
        "maximum_records": inventory["maximum_records"], "maximum_bytes": inventory["maximum_bytes"],
        "future_capture_attempts": future_attempts, "remaining_slot_policy": "ACTUAL_RETAINED_BYTES_PLUS_UNUSED_ROLE_CEILINGS"}
    result["static_full_planned_capacity"] = {"basis": "REVIEWED_PLAN_NOT_CURRENT_INVENTORY",
        "original_records": 19, "original_encoded_bytes": 1817800,
        "first_cycle_records": 60, "first_cycle_reserved_bytes": 9658368,
        "postgame_records": 76, "postgame_reserved_bytes": 19955712,
        "total_records": 155, "total_reserved_bytes": 31431880,
        "maximum_records": 512, "maximum_bytes": 33554432}
    result["fits"] = (result["existing_records"] + reserved_records <= result["maximum_records"]
        and result["existing_bytes"] + reserved_bytes <= result["maximum_bytes"])
    require(result["fits"], "Combined first-cycle grading, partial-original and metadata reserve exceeds unchanged ledger limits")
    return result


def _authority_record(store, authority, day):
    old = [(ref, body) for ref, body in store.records() if body["schema_version"] == OUTCOME_EVIDENCE_SCHEMA
        and body["metadata"]["source_kind"] == AUTH_KIND
        and body["metadata"]["retrieved_at"].startswith(day)]
    require(len(old) <= 1, "Duplicate postgame authority originals for UTC day")
    if old:
        return old[0][0]
    raw = canonical(authority)
    require(len(raw) + 8192 <= AUTH_BYTES * 3 // 4, "Postgame run proof exceeds encoded reserve")
    at = authority["verified_at"]
    return store.retain_outcome_evidence(raw, {"source_kind": AUTH_KIND,
        "source_url": "https://api.github.com/repos/" + cycles.REPOSITORY + "/actions/runs/" + str(authority["workflow_run_id"]),
        "source_observed_at": at, "retrieval_started_at": at, "retrieved_at": at,
        "content_type": "application/json", "source_use_basis": "Project-authored current trusted workflow proof; no provider or issuance authority inferred"})


def _operation(store, report, requests, authority_ref, *, slot):
    phase = PHASE + report["day"]
    old = [(ref, body) for ref, body in _operations(store)
        if body["phase"] == phase and (body["status"] == "POSTGAME_CAPTURE_STARTED") == (slot == "start")]
    require(len(old) <= 1, "Duplicate immutable postgame report slot")
    if old:
        return old[0][0]
    body = producer.seal({"schema_version": prior.OPERATION_SCHEMA, "protocol_id": producer.PROTOCOL_ID,
        "cycle_id": cycles.CYCLE_ID, "mode": "PROSPECTIVE_RESEARCH", "phase": phase,
        "status": "POSTGAME_CAPTURE_STARTED" if slot == "start" else report["status"], "recorded_at": stamp(_now()),
        "source_requests": requests, "input_ref": report.get("input_ref"),
        "forecast_ids": report.get("forecast_ids", []), "genuine_issued": report.get("genuine_issued", 0),
        "error": report.get("error")}, "operation_id")
    return store.append_body("input_captures", body, references=(authority_ref,),
        logical_id="daily-postgame:" + report["day"] + ":" + slot)


def collect_final(capture, config, *, preflight):
    result = {}
    for role in ("schedule", "boxscore"):
        source = config["roles"][role]
        preflight()
        metadata_raw, meta, _ = capture.get(source["metadata_url"], limit=config["max_metadata_bytes"], label=role + "_metadata")
        require(meta["status"] == 200, "Postgame publisher metadata was not successful")
        preflight()
        raw, receipt, location = capture.get(source["asset_url"], limit=source["max_asset_bytes"], label=role + "_asset")
        asset_started = receipt["retrieval_started_at"]
        if receipt["status"] == 302:
            require(type(location) is str, "Postgame redirect lacks destination")
            preflight()
            raw, receipt, _ = capture.get(location, limit=source["max_asset_bytes"], label=role + "_asset_redirect", redirect=True)
        require(receipt["status"] == 200, "Postgame CSV response was not successful")
        result[role] = (raw, metadata_raw, {"metadata_retrieval_started_at": meta["retrieval_started_at"],
            "metadata_retrieved_at": meta["retrieved_at"], "asset_retrieval_started_at": asset_started,
            "asset_retrieved_at": receipt["retrieved_at"]})
    return result


def _retained_sources(store):
    found = []
    for ref, body in store.records():
        if body["schema_version"] == OUTCOME_EVIDENCE_SCHEMA and body["metadata"]["source_kind"] == grading.PROOF_KIND:
            found.append((ref, _decode(store.read_outcome_evidence(ref)[0])))
    return sorted(found, key=lambda item: item[1]["created_at"])


class IncompleteRetainedObservation(IntegrityError):
    """Original bytes remain incomplete; never recapture or manufacture them."""


def _proven_http_record(store, row, raw, *, retain_missing):
    """Recover exact metadata, or the canonical CSV record for an existing proof.

    This retains raw evidence only. Outcomes and statistical grades still require
    the separate full admission graph. No source clock or original is replaced.
    """
    with getattr(store.ledger, "validation_scope", nullcontext)():
        return _proven_http_record_scoped(store, row, raw, retain_missing=retain_missing)


def _proven_http_record_scoped(store, row, raw, *, retain_missing):
    keys = ("route", "sha256", "bytes", "retrieval_started_at", "retrieved_at")
    for proof_ref, _ in _retained_sources(store):
        proof, config, _ = grading._validated_proof(store, proof_ref)
        if not any(all(old.get(key) == row.get(key) for key in keys)
                and old.get("status") == 200 for old in proof["requests"]):
            continue
        for source in proof["sources"]:
            role = source["role"]
            if row["label"] == role + "_metadata":
                original = grading.decode64(source["metadata_original_base64"], config["max_metadata_bytes"])
                if original == raw and row["sha256"] == source["metadata_original_sha256"]:
                    return proof_ref
            if not row["label"].startswith(role + "_asset") or grading.sha(raw) != source["asset_sha256"]:
                continue
            metadata_raw = grading.decode64(source["metadata_original_base64"], config["max_metadata_bytes"])
            expected, _ = grading._source(raw, metadata_raw,
                {key: source[key] for key in grading.CLOCK_FIELDS}, role, config)
            require(expected == source, "Retained raw asset differs from original proof")
            basis = "Separate final-source review " + config["source_review_receipt_sha256"] + "; config " + config["config_id"]
            body = grading._retained_body(raw, grading._meta(config["roles"][role]["source_kind"],
                source["asset_url"], source["asset_retrieved_at"], basis,
                started=source["asset_retrieval_started_at"]))
            for ref, existing in store.records():
                if existing == body and store.ledger.read(ref)["references"] == [proof_ref.to_record()]:
                    return ref
            if retain_missing:
                require(len(canonical(body)) + 4096 <= grading.MAX_CSV_ENVELOPE,
                    "Proof-linked partial CSV exceeds unchanged role reserve")
                return store.append_body("research_inputs", body, references=(proof_ref,))
    return None


def recover_source_refs(store, proof_ref, proof):
    """Fill missing proof-linked CSVs from exact durable partial bodies, no GET."""
    validated, config, _ = grading._validated_proof(store, proof_ref)
    require(validated == proof, "Recovery proof differs from retained original")
    try:
        return grading._recover_source_refs(store, proof_ref)
    except IntegrityError:
        pass
    for source in proof["sources"]:
        rows = [row for row in proof["requests"] if row.get("status") == 200
            and row.get("sha256") == source["asset_sha256"]
            and row.get("label", "").startswith(source["role"] + "_asset")]
        require(len(rows) == 1, "Incomplete proof has ambiguous asset request")
        row = rows[0]
        candidates = []
        for ref, body in store.records():
            if body["schema_version"] != OUTCOME_EVIDENCE_SCHEMA or body.get("raw_sha256") != row["sha256"]:
                continue
            raw, meta = store.read_outcome_evidence(ref)
            if (meta["source_kind"] == PARTIAL_KIND and meta["source_url"] == row["route"]
                    and meta["retrieval_started_at"] == row["retrieval_started_at"]
                    and meta["retrieved_at"] == row["retrieved_at"]):
                candidates.append(raw)
            elif (meta["source_kind"] == config["roles"][source["role"]]["source_kind"]
                    and meta["source_url"] == source["asset_url"]
                    and meta["retrieval_started_at"] == source["asset_retrieval_started_at"]
                    and meta["retrieved_at"] == source["asset_retrieved_at"]):
                candidates.append(raw)
        if not candidates:
            raise IncompleteRetainedObservation("Exact missing CSV body was not durably recovered; retain partial proof without claiming completion")
        require(all(raw == candidates[0] for raw in candidates), "Conflicting raw bytes for original asset hash")
        require(_proven_http_record(store, row, candidates[0], retain_missing=True) is not None,
            "Missing CSV cannot be linked to its original admitted proof")
    return grading._recover_source_refs(store, proof_ref)


def _preserve_partial(store, directory, requests, authority_ref):
    refs = []
    for row in requests:
        # Non-200 bodies can contain signed redirect URLs or error HTML outside
        # the admitted redistribution scope. Preserve only their safe ledger
        # observations in Git; raw diagnostics remain a 14-day artifact.
        if row.get("status") != 200:
            continue
        path = Path(directory) / ("request-%02d.body" % row["request_number"])
        if not path.exists():
            continue
        raw = _bounded_bytes(path, row["response_limit_bytes"])
        require(len(raw) == row.get("bytes") and hashlib.sha256(raw).hexdigest() == row.get("sha256"),
            "Partial postgame original differs from its factual request receipt")
        if raw.lstrip().startswith(b"<"):
            # A successful transport can still serve error HTML. Its hash,
            # size and clocks remain in the request ledger, not public raw Git.
            continue
        existing = _proven_http_record(store, row, raw, retain_missing=True)
        if existing is not None:
            refs.append(existing)
            continue
        at = row["retrieved_at"]
        refs.append(store.retain_outcome_evidence(raw, {"source_kind": PARTIAL_KIND,
            "source_url": row["route"], "source_observed_at": at,
            "retrieval_started_at": row["retrieval_started_at"], "retrieved_at": at,
            "content_type": "application/octet-stream", "source_use_basis": "Admitted bounded postgame attempt; partial original only, never a complete contract or grading admission"}))
    return refs


def failure_alert(report):
    """One bounded idempotent repository issue, never email or external chat."""
    title = "NBA research operational failure [" + cycles.CYCLE_ID + "]"
    args = ["gh", "issue", "list", "--repo", cycles.REPOSITORY, "--state", "open", "--limit", "100",
        "--search", cycles.CYCLE_ID + " in:title", "--json", "title,url"]
    result = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
    require(result.returncode == 0, "GitHub failure-alert lookup unavailable; original report retained")
    rows = _decode(result.stdout.encode())
    require(type(rows) is list and len(rows) < 100, "Failure-alert inventory ambiguous")
    matches = [row for row in rows if type(row) is dict and row.get("title") == title]
    require(len(matches) <= 1, "Multiple matching open failure alerts")
    if matches:
        return {"status": "EXISTING_OPEN_ALERT", "url": matches[0]["url"]}
    body = ("First-cycle postgame coordinator observed `" + report["status"] + "`.\n\n"
        "Cause: " + safe_error(report.get("error") or report.get("durability_or_publication_error")
            or report.get("publication_verification_error") or report.get("records_pr_error")
            or "No eligible originals were independently recovered; the original execution cause is unknown.")
        + "\n\nActual observation: " + report["recorded_at"] + ". Genuine eligible forecasts: "
        + str(report.get("genuine_issued", 0)) + ". Source GETs: " + str(report.get("source_requests", 0))
        + ". Report SHA256: `" + digest(report) + "`.\n\n"
        "Workflow run: https://github.com/" + cycles.REPOSITORY + "/actions/runs/" + os.environ.get("GITHUB_RUN_ID", "UNKNOWN")
        + ". The workflow artifact retains exact factual reports for 14 days; that artifact is not a permanent archive. "
        "Original records, when present, remain on `" + BRANCH + "`. No replacement issuance, financial settlement or qualified ticket is claimed.")
    with tempfile.TemporaryDirectory(prefix="nml-postgame-alert-") as temporary:
        path = Path(temporary) / "body.txt"
        path.write_text(body, encoding="utf-8")
        created = subprocess.run(["gh", "issue", "create", "--repo", cycles.REPOSITORY,
            "--title", title, "--body-file", str(path)], capture_output=True, text=True, timeout=30, check=False)
    require(created.returncode == 0, "GitHub rejected failure alert; report retained, alert access unresolved")
    return {"status": "CREATED", "url": created.stdout.strip()}


def _public_get(url, maximum):
    require(url.startswith(PUBLIC_ROOT) and "?" not in url and "#" not in url,
        "Publication readback URL is outside this site's fixed data route")
    request = urllib.request.Request(url, headers={"User-Agent": "NicksMultisportLab/public-readback",
        "Cache-Control": "no-cache"})
    with urllib.request.build_opener(prior._NoRedirect()).open(request, timeout=20) as response:
        require(response.status == 200, "Public research data is unavailable")
        raw = response.read(maximum + 1)
    require(0 < len(raw) <= maximum, "Public research data exceeds unchanged bound")
    return raw


def _expected_public(store):
    result = {"forecasts": {}, "outcomes": {}, "grades": {}}
    for ref, body in store.records():
        if ref.kind not in result:
            continue
        if ref.kind != "forecasts" and store.ledger.latest(ref) != ref:
            continue
        row = {"reference": ref.to_record(), "body": body}
        if ref.kind == "forecasts":
            row["admission"] = store.admission(ref)
        result[ref.kind][ref.record_id] = row
    active_outcomes = {row["body"]["outcome_id"] for row in result["outcomes"].values()}
    result["grades"] = {key: row for key, row in result["grades"].items()
        if row["body"]["outcome_id"] in active_outcomes}
    return result


def verify_publication(store, expected_build):
    """Two bounded TLS GETs; compare typed public originals with exact recovery."""
    try:
        from . import publication
        raw = _public_get(PUBLIC_ROOT + "manifest.json", 1024 * 1024)
        manifest = _decode(raw)
        version = manifest.get("schema_version") if type(manifest) is dict else None
        fields = {"schema_version", "snapshot_id", "build_commit", "published_at", "publication_status",
            "supported_sports", "sports", "errors"}
        fields |= {field for channel in publication._channel_names(version)
            for field in (channel, channel + "_error")}
        require(type(manifest) is dict and set(manifest) == fields and version == 6
            and manifest["publication_status"] == "RESEARCH_ONLY"
            and manifest["snapshot_id"] == digest({k: v for k, v in manifest.items() if k != "snapshot_id"})
            and utc(manifest["published_at"]) <= _now(), "Public manifest meaning or checksum invalid")
        require(type(manifest["sports"]) is list and bool(manifest["sports"])
            and type(manifest["supported_sports"]) is list and type(manifest["errors"]) is dict,
            "Public manifest collections invalid")
        leagues = []
        for entry in manifest["sports"]:
            require(type(entry) is dict and set(entry) == {"league", "path", "sha256", "generated_at", "status", "retained", "error"}
                and type(entry["league"]) is str and re.fullmatch(r"[A-Z]+", entry["league"])
                and type(entry["sha256"]) is str and re.fullmatch(r"[a-f0-9]{64}", entry["sha256"])
                and entry["path"] == entry["league"].lower() + "." + entry["sha256"] + ".json"
                and type(entry["retained"]) is bool and entry["status"] == "RESEARCH_ONLY"
                and utc(entry["generated_at"]) <= utc(manifest["published_at"]), "Public sport descriptor invalid")
            leagues.append(entry["league"])
        require(len(set(leagues)) == len(leagues) and sorted(leagues) == manifest["supported_sports"],
            "Public manifest sport scope differs from its references")
        require(manifest["build_commit"] == expected_build,
            "Public website does not yet serve the current trusted workflow commit")
        descriptor = manifest["daily_research"]
        require(manifest["daily_research_error"] is None and type(descriptor) is dict
            and set(descriptor) == {"path", "sha256", "generated_at", "status", "retained", "error"}
            and re.fullmatch(r"[a-f0-9]{64}", descriptor["sha256"] or "")
            and descriptor["path"] == "sdv-daily." + descriptor["sha256"] + ".json"
            and descriptor["status"] == "DAILY_SNAPSHOT_RESEARCH" and descriptor["error"] is None,
            "Public daily descriptor invalid or unavailable")
        asset_raw = _public_get(PUBLIC_ROOT + descriptor["path"], public.MAX_ASSET_BYTES)
        asset = _decode(asset_raw)
        require(hashlib.sha256(asset_raw).hexdigest() == descriptor["sha256"]
            and asset_raw == canonical(asset) and asset["generated_at"] == descriptor["generated_at"]
            and utc(asset["generated_at"]) <= utc(manifest["published_at"]), "Public daily bytes or clocks differ")
        public.validate_asset(asset, now=_now())
        superseded = {row["original_ref"]["record_id"] for row in asset["corrections"]}
        actual = {"forecasts": {row["reference"]["record_id"]: row for row in asset["forecasts"]},
            "outcomes": {row["reference"]["record_id"]: row for row in asset["outcomes"]
                if row["reference"]["record_id"] not in superseded},
            "grades": {row["reference"]["record_id"]: row for row in public.active_grades(asset)}}
        expected = _expected_public(store)
        require(actual == expected, "Public active originals/outcomes/grades differ from independently recovered records")
        return {"status": "PUBLICATION_VERIFIED", "verified_at": stamp(_now()),
            "build_commit": expected_build, "manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "daily_asset_sha256": descriptor["sha256"], "expected_records_sha256": digest(expected),
            "outcome_records": len(expected["outcomes"]), "statistical_grades": len(expected["grades"])}
    except (IntegrityError, OSError, ValueError, TypeError, KeyError, urllib.error.URLError) as error:
        return {"status": "PUBLICATION_UNVERIFIED", "reason": safe_error(error)}


def reconcile_publication(store, commit, expected_build):
    """The public site is the idempotent readback; an accepted request is not it."""
    observed = verify_publication(store, expected_build)
    if observed["status"] == "PUBLICATION_VERIFIED":
        return observed
    # The protected first-cycle helper dispatches ref=main. Do not knowingly
    # request a different build than this authenticated run can verify.
    require(current_main_head() == expected_build,
        "Main advanced after this postgame run started; retained records are safe. Retry publication from the newer reviewed main rather than dispatching a known mismatched build.")
    request = prior._publish_records(commit)
    # At most one poll per minute for twenty minutes. No provider capture,
    # probability calculation or statistical write occurs in this retry path.
    for _ in range(MAX_PUBLIC_POLLS):
        time.sleep(60)
        observed = verify_publication(store, expected_build)
        if observed["status"] == "PUBLICATION_VERIFIED":
            return {**observed, "request": request}
    return {"status": "PUBLICATION_REQUESTED_UNVERIFIED", "request": request, "last_readback": observed}


def current_main_head():
    result = _git(ROOT, "ls-remote", "--exit-code", "--heads", REMOTE_URL, "refs/heads/main")
    fields = result.stdout.strip().split()
    require(len(fields) == 2 and re.fullmatch(r"[a-f0-9]{40}", fields[0])
        and fields[1] == "refs/heads/main", "Cannot identify current trusted main for publication")
    return fields[0]


def _publication_ack(store, report, authority_ref):
    phase = "POSTGAME_PUBLICATION_" + report["day"]
    prior_ack = [(ref, body) for ref, body in _operations(store) if body["phase"] == phase]
    if prior_ack:
        return prior_ack[0][0]
    body = producer.seal({"schema_version": prior.OPERATION_SCHEMA, "protocol_id": producer.PROTOCOL_ID,
        "cycle_id": cycles.CYCLE_ID, "mode": "PROSPECTIVE_RESEARCH", "phase": phase,
        "status": "PUBLICATION_VERIFIED", "recorded_at": report["publication"]["verified_at"],
        "source_requests": [], "input_ref": report.get("input_ref"), "forecast_ids": report["forecast_ids"],
        "genuine_issued": report["genuine_issued"], "error": None}, "operation_id")
    return store.append_body("input_captures", body, references=(authority_ref,),
        logical_id="daily-postgame-publication:" + report["day"])


def run(*, work_root):
    now = _now()
    report = {"schema_version": "nba-sdv-postgame-execution-v1", "cycle_id": cycles.CYCLE_ID,
        "day": now.date().isoformat(), "recorded_at": stamp(now), "status": operating_window(now),
        "genuine_issued": 0, "forecast_ids": [], "source_requests": 0, "error": None,
        "recurring_pregame_issuance": "NOT_IMPLEMENTED", "publication": "NOT_REQUESTED"}
    with retained_lock(work_root) as work:
        path = work / "execution-report.json"
        if report["status"] != "OPEN":
            prior._write_json(path, report)
            return report
        store = writer = authority_ref = None
        capture = None
        capture_retained = False
        try:
            authority = authorize_current_run()
            report["authority"] = authority
            with tempfile.TemporaryDirectory(prefix="nml-postgame-fetch-", dir=work) as temporary:
                checkout = Path(temporary) / "independent"
                remote = fetch_existing_branch(checkout)
                if remote is None:
                    report["status"] = "NO_ELIGIBLE_ORIGINALS"
                    report["error"] = "Fixed original records branch is absent; original execution cause cannot be established from an absent run or branch."
                    return _finish(report, path, alert=True)
                prior.copy_records(checkout, work / "state")
            store = DailyStore(work / "state")
            originals = _eligible(store)
            report.update(genuine_issued=len(originals), forecast_ids=[body["forecast_id"] for _, body in originals])
            if originals:
                report["input_ref"] = originals[0][1]["input_ref"]
            writer = DailyGitCheckpointWriter(store.project_root, work / "writer",
                base_commit=grading.FIRST_PRODUCER, branch=BRANCH)
            report["writer"] = writer.prepare()
            capacity_preflight(store)
            authority_ref = _authority_record(store, authority, report["day"])
            if not originals:
                report["status"] = "NO_ELIGIBLE_ORIGINALS"
                report["error"] = "No timely admitted original forecasts recovered; original execution cause remains unknown without its retained report."
            else:
                refs = tuple(ref for ref, _ in originals)
                # Catch up already retained complete observations without GETs.
                complete_days = set()
                for proof_ref, proof in _retained_sources(store):
                    require(operating_window(_now()) == "OPEN", "Postgame catch-up grading window closed")
                    try:
                        sr, br = recover_source_refs(store, proof_ref, proof)
                    except IncompleteRetainedObservation as incomplete:
                        report.setdefault("incomplete_observations", []).append({"proof_id": proof["proof_id"],
                            "reason": safe_error(incomplete)})
                        continue
                    grading.normalize_and_grade(store, refs, sr, br)
                    complete_days.add(proof["created_at"][:10])
                captures = [(ref, body) for ref, body in _operations(store) if body["status"] == "POSTGAME_CAPTURE_STARTED"]
                source_days = {proof["created_at"][:10] for _, proof in _retained_sources(store)}
                attempt_days = source_days | {body["recorded_at"][:10] for _, body in captures}
                same_day = report["day"] in attempt_days
                if same_day:
                    completed_today = report["day"] in complete_days
                    report["status"] = "RECOVERED_SAME_DAY_OBSERVATION" if completed_today else "INTERRUPTED_CAPTURE_NO_RECAPTURE"
                    if not completed_today:
                        report["error"] = "Recovered interrupted UTC-day capture marker; original request count may be unknown. No recapture or request-budget reset."
                elif len(attempt_days) >= MAX_STARTED_CAPTURES:
                    report["status"] = "POSTGAME_OBSERVATION_BUDGET_EXHAUSTED"
                else:
                    config = grading.load_config()
                    _operation(store, report, [], authority_ref, slot="start")
                    report["capture_marker_checkpoint"] = writer.flush()
                    day_root = work / "originals" / report["day"]
                    opens = now.replace(hour=13, minute=0, second=0, microsecond=0)
                    closes = now.replace(hour=14, minute=30, second=0, microsecond=0)
                    capture = prior.BoundedCapture(day_root, opens_at=opens, closes_at=closes)
                    def preflight():
                        require(operating_window(_now()) == "OPEN", "Postgame source window closed")
                        capacity_preflight(store)
                    captured = collect_final(capture, config, preflight=preflight)
                    report["source_requests"] = len(capture.requests)
                    require(operating_window(_now()) == "OPEN", "Postgame source completion missed window")
                    sr, br = grading.retain_source_with_proof(store, refs,
                        schedule=captured["schedule"], boxscore=captured["boxscore"], requests=capture.requests)
                    capture_retained = True
                    report["source_checkpoint"] = writer.flush()
                    require(operating_window(_now()) == "OPEN", "Postgame grading window closed after durable source recovery")
                    result = grading.normalize_and_grade(store, refs, sr, br)
                    report.update(status="STATISTICAL_GRADING_RETAINED", pending_players=result["pending"],
                        outcome_records=len(result["outcomes"]), statistical_grades=len(result["grades"]),
                        correction_links=len(result["corrections"]))
                    if result.get("unresolved_event_state"):
                        report.update(status="UNRESOLVED_FINAL_EVENT", error=result["unresolved_event_state"])
            grading.validate_stored_admissions(store)
        except (IntegrityError, OSError, ValueError, subprocess.SubprocessError) as error:
            report.update(status="PARTIAL_OR_FAILED_POSTGAME", error=safe_error(error))
            if capture is not None:
                report["source_requests"] = len(capture.requests)
                if store is not None and authority_ref is not None:
                    try:
                        # Successful completed captures already have proof/CSV
                        # originals. Archive partial response bytes only otherwise.
                        if not capture_retained:
                            _preserve_partial(store, capture.root, capture.requests, authority_ref)
                    except (IntegrityError, OSError) as retain_error:
                        report["partial_retention_error"] = safe_error(retain_error)
        finally:
            if store is not None and writer is not None and authority_ref is not None:
                try:
                    requests = capture.requests if capture is not None else []
                    _operation(store, report, requests, authority_ref, slot="final")
                    report["final_checkpoint"] = writer.flush()
                except (IntegrityError, OSError, subprocess.SubprocessError) as preserve_error:
                    report["durability_or_publication_error"] = safe_error(preserve_error)
                if "final_checkpoint" in report:
                    # A draft PR and website publication are independently useful.
                    try:
                        report["records_pr"] = prior._records_pr(writer, report, report_path=path)
                    except (IntegrityError, OSError, subprocess.SubprocessError) as pr_error:
                        report["records_pr_error"] = safe_error(pr_error)
                    if report["genuine_issued"]:
                        try:
                            report["publication"] = reconcile_publication(store,
                                report["final_checkpoint"]["commit"], report["authority"]["head_sha"])
                            if report["publication"]["status"] == "PUBLICATION_VERIFIED":
                                # Import has completed before advancing the fixed
                                # records head with a factual acknowledgment.
                                _publication_ack(store, report, authority_ref)
                                report["publication_ack_checkpoint"] = writer.flush()
                            else:
                                report["publication_verification_error"] = "Pages request accepted but bounded public readback did not verify current build and exact active records."
                        except (IntegrityError, OSError, subprocess.SubprocessError) as publish_error:
                            report["durability_or_publication_error"] = safe_error(publish_error)
        return _finish(report, path, alert="authority" in report and (report["status"] in {
            "NO_ELIGIBLE_ORIGINALS", "PARTIAL_OR_FAILED_POSTGAME", "INTERRUPTED_CAPTURE_NO_RECAPTURE"}
            or any(key in report for key in ("durability_or_publication_error", "publication_verification_error", "records_pr_error"))))


def _finish(report, path, *, alert):
    report["recorded_at"] = stamp(_now())
    if alert:
        try:
            report["failure_alert"] = failure_alert(report)
        except (IntegrityError, OSError, subprocess.SubprocessError) as error:
            report["failure_alert"] = {"status": "UNAVAILABLE", "reason": safe_error(error)}
    prior._write_json(path, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--work-root", required=True)
    args = parser.parse_args()
    report = run(work_root=args.work_root)
    print(canonical({key: value for key, value in report.items() if key != "authority"}).decode())
    if report["status"] in {"NO_ELIGIBLE_ORIGINALS", "PARTIAL_OR_FAILED_POSTGAME"} or any(key in report
            for key in ("durability_or_publication_error", "publication_verification_error", "records_pr_error")):
        raise SystemExit(2)


if __name__ == "__main__":
    main()

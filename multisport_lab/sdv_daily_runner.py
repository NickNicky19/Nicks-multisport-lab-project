"""One owner-dispatched daily cycle, plus strictly non-issuing local previews.

There is no scheduler. The genuine entrypoint authenticates the existing manual
workflow before any collection and retains a single state/writer across phases.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from .integrity import IntegrityError, _bounded_bytes, _decode, canonical, digest, stamp, utc
from .ledger import LedgerRef
from . import sdv_daily_inputs as inputs
from . import sdv_daily_cycle as cycles
from . import sdv_daily_producer as producer
from .sdv_daily_store import ASSET_SCHEMA, DailyStore

MAX_SOURCE_REQUESTS = 6
MAX_METADATA_BYTES = 256 * 1024
MAX_ASSET_BYTES = 2 * 1024 * 1024
MAX_HTTP_SECONDS = 25
OPERATION_SCHEMA = "nba-sdv-daily-operation-v1"


def _now():
    return datetime.now(timezone.utc)


def require(value, message):
    if not value:
        raise IntegrityError(message)


def _write_json(path, body):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    require(not path.is_symlink() and not temporary.is_symlink(), "Runner report path is a symlink")
    with temporary.open("wb") as handle:
        handle.write(canonical(body) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _retain(path, raw):
    path = Path(path)
    require(not any(parent.is_symlink() for parent in (path, *path.parents)),
            "Runner retention cannot traverse a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(path.read_bytes() == raw, "Runner cannot replace original retained bytes")
        return
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def copy_records(source, destination):
    """Preserve parent and daily originals exactly; conflicting bytes fail closed."""
    source, destination = Path(source), Path(destination)
    for prefix in ("records", "daily/records"):
        folder = source / prefix
        if not folder.exists():
            continue
        require(not folder.is_symlink(), "Runner original records are a symlink")
        for path in sorted(folder.rglob("*.json")):
            _retain(destination / path.relative_to(source), _bounded_bytes(path, 8 * 1024 * 1024))


def source_metadata(raw, metadata_raw, source, *, retrieval_started_at, retrieved_at):
    """Bind an exact CSV to the actual publisher release body, never a revision guess."""
    require(len(metadata_raw) <= MAX_METADATA_BYTES, "Daily publisher metadata exceeds 256 KiB")
    release = _decode(metadata_raw)
    require(type(release) is dict and release.get("tag_name") == source["release_tag"]
            and type(release.get("assets")) is list, "Daily publisher release identity differs")
    matches = [asset for asset in release["assets"] if type(asset) is dict
               and asset.get("name") == source["asset_name"]]
    require(len(matches) == 1, "Daily publisher asset is missing or ambiguous")
    asset = matches[0]
    sha = hashlib.sha256(raw).hexdigest()
    require(asset.get("browser_download_url") == source["asset_url"]
            and asset.get("size") == len(raw) and asset.get("digest") == "sha256:" + sha,
            "Daily CSV differs from the actual publisher release bytes")
    metadata = {"role": source["role"], "publisher": "SportsDataverse",
        "release_tag": source["release_tag"], "asset_name": source["asset_name"],
        "asset_url": source["asset_url"], "asset_id": asset.get("id"),
        "asset_bytes": len(raw), "asset_sha256": sha,
        "publisher_updated_at": stamp(utc(asset.get("updated_at"))),
        "upstream_observed_at": None, "upstream_observation_status": "UNKNOWN",
        "retrieval_started_at": stamp(utc(retrieval_started_at)), "retrieved_at": stamp(utc(retrieved_at)),
        "metadata_sha256": hashlib.sha256(metadata_raw).hexdigest(), "metadata_bytes": len(metadata_raw)}
    inputs.validate_source_metadata(metadata, raw=raw)
    return metadata


def retained_samples(sample_root, cycle):
    """Read only the previously inspected two CSVs and their exact release bodies."""
    root = Path(sample_root)
    requests = _decode(_bounded_bytes(root / "requests.json", 64 * 1024))
    require(type(requests) is list, "Retained sample request inventory is missing")
    indexed = {row.get("request_number"): row for row in requests if type(row) is dict}
    require(len(indexed) == len(requests), "Retained sample request numbers conflict")
    result = []
    for source, number, metadata_name in ((cycle["source_assets"][0], 3, "schedule-release-metadata.json"),
                                          (cycle["source_assets"][1], 5, "request-01.body")):
        row = indexed.get(number)
        require(type(row) is dict and row.get("status") == 200, "Retained successful CSV receipt is missing")
        raw = _bounded_bytes(root / ("request-%02d.body" % number), MAX_ASSET_BYTES)
        require(len(raw) == row.get("bytes") and hashlib.sha256(raw).hexdigest() == row.get("sha256"),
                "Retained sample CSV receipt differs from original bytes")
        metadata_raw = _bounded_bytes(root / metadata_name, MAX_METADATA_BYTES)
        metadata = source_metadata(raw, metadata_raw, source,
            retrieval_started_at=row["request_started_at"], retrieved_at=row["observed_at"])
        result.append((raw, metadata, metadata_raw))
    return result


def _summary(store):
    report = store.recover()
    return {"daily_records": len(report["records"]), "forecast_records": len(report["forecasts"]),
            "input_records": len(report["inputs"]), "genuine_issued": report["genuine_issued"],
            "admissions": report["admissions"], "pending_forecasts": len(report["forecasts"]),
            "public_publication": False, "financial_settlements": 0, "qualified_tickets": 0}


def _intent_ready(store, intent_ref, *, cutoff):
    stages = {body["stage"]: body for _, body in store.records()
        if body["schema_version"] == "nba-sdv-daily-completion-v1"
        and body["reference"] == intent_ref.to_record()}
    if set(stages) != {"LOCAL_PERSISTENCE", "REMOTE_CHECKPOINT", "FINAL_RECOVERY"}:
        return False
    local, remote, final = [stages[key] for key in ("LOCAL_PERSISTENCE", "REMOTE_CHECKPOINT", "FINAL_RECOVERY")]
    require(utc(local["completed_at"]) <= utc(remote["completed_at"]) <= utc(final["completed_at"])
            <= utc(cutoff) and remote["remote_commit"] == final["remote_commit"],
            "Original daily generation intent missed durable pre-cutoff recovery")
    return True


def preview(store_root, sample_root, *, producer_commit=None, cycle_path=None):
    """Exercise exact retained inputs through all eight non-issuance forecasts."""
    repository = Path(__file__).resolve().parents[1]
    root = Path(store_root).absolute()
    require(root != repository and not repository.is_relative_to(root),
            "Development preview must use an isolated store")
    copy_records(repository, root)
    store = DailyStore(root)
    cycle = cycles.load_cycle(cycle_path)
    binding = producer.make_source_binding(producer_commit)
    retained = retained_samples(sample_root, cycle)
    existing = store.recover()["inputs"]
    if existing:
        require(len(existing) == 1 and existing[0][1]["mode"] == "DEVELOPMENT_ONLY",
                "Preview cannot borrow genuine or multiple input records")
        input_ref, body = existing[0]
        inputs.verify_input_sources(body, retained[0][0], retained[1][0], retained[0][1], retained[1][1])
    else:
        body = inputs.normalize_inputs(retained[0][0], retained[1][0], retained[0][1], retained[1][1],
            event_id=cycle["event"]["event_id"], expected_candidates=cycle["candidates"])
        asset_refs = [store.retain_asset(raw, metadata, original) for raw, metadata, original in retained]
        input_ref = store.persist_input(body, asset_refs)
    producer.issue_cycle(store, input_ref, cycle, binding)
    return {"status": "DEVELOPMENT_ONLY", "cycle_id": cycle["cycle_id"], **_summary(store)}


def recover(store_root):
    """Strict recovery only: no source reads, generation or clock rewriting."""
    return {"status": "READ_ONLY_RECOVERY", **_summary(DailyStore(store_root))}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class BoundedCapture:
    """Six total source GETs, counting redirects; no retries or credentials."""
    def __init__(self, root, *, opens_at=None, closes_at=None):
        self.root = Path(root)
        self.requests = []
        require((opens_at is None) == (closes_at is None), "Capture needs both operating bounds")
        self.opens_at = utc(opens_at) if opens_at is not None else None
        self.closes_at = utc(closes_at) if closes_at is not None else None
        require(self.opens_at is None or self.opens_at < self.closes_at, "Capture operating bounds conflict")
        require(not (self.root / "requests.json").exists(),
                "An existing capture attempt must be recovered, never silently recaptured")
        self.opener = urllib.request.build_opener(_NoRedirect())

    def get(self, url, *, limit, label, redirect=False):
        if self.opens_at is not None:
            require(self.opens_at <= _now() <= self.closes_at,
                    "Daily source request is outside the registered capture window")
        require(len(self.requests) < MAX_SOURCE_REQUESTS, "Daily source request budget exhausted")
        parsed = urllib.parse.urlsplit(url)
        allowed = {"api.github.com", "github.com"} if not redirect else {"release-assets.githubusercontent.com"}
        require(parsed.scheme == "https" and parsed.hostname in allowed and not parsed.username
                and not parsed.password and parsed.port in {None, 443}, "Daily capture URL is outside the admitted route")
        row = {"request_number": len(self.requests) + 1, "label": label,
            "route": parsed.scheme + "://" + parsed.netloc + parsed.path,
            "retrieval_started_at": stamp(_now()), "response_limit_bytes": limit,
            "automatic_redirects": False, "automatic_retries": 0}
        self.requests.append(row)
        _write_json(self.root / "requests.json", self.requests)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "NicksMultisportLab/daily-research",
                                                          "Accept": "application/json, text/csv, */*"})
            try:
                response = self.opener.open(request, timeout=MAX_HTTP_SECONDS)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                status = response.code
                raw = response.read(limit + 1)
                location = response.headers.get("Location")
            row.update(status=status, response_read_completed_at=stamp(_now()),
                       bytes_read=len(raw), response_exceeded_limit=len(raw) > limit)
            require(len(raw) <= limit, "Daily response exceeds its exact size limit; no truncation")
            row.update(status=status, retrieved_at=stamp(_now()), bytes=len(raw),
                       sha256=hashlib.sha256(raw).hexdigest())
            _retain(self.root / ("request-%02d.body" % row["request_number"]), raw)
            _write_json(self.root / "requests.json", self.requests)
            return raw, row, location
        except Exception:
            row.update(failed_at=stamp(_now()), status=row.get("status", "UNOBSERVED"))
            _write_json(self.root / "requests.json", self.requests)
            raise

    def collect(self, cycle, *, on_asset=None):
        result = []
        for source in cycle["source_assets"]:
            metadata_raw, meta_receipt, _ = self.get(source["metadata_url"], limit=MAX_METADATA_BYTES,
                                                    label=source["role"] + "_publisher_metadata")
            require(meta_receipt["status"] == 200, "Daily publisher metadata was not successful")
            raw, receipt, location = self.get(source["asset_url"], limit=MAX_ASSET_BYTES,
                                               label=source["role"] + "_canonical_asset")
            started = receipt["retrieval_started_at"]
            if receipt["status"] == 302:
                require(type(location) is str, "Daily asset redirect lacks its location")
                raw, receipt, _ = self.get(location, limit=MAX_ASSET_BYTES,
                    label=source["role"] + "_asset_redirect", redirect=True)
            require(receipt["status"] == 200, "Daily asset was not successful")
            metadata = source_metadata(raw, metadata_raw, source,
                retrieval_started_at=started, retrieved_at=receipt["retrieved_at"])
            result.append((raw, metadata, metadata_raw))
            if on_asset is not None:
                on_asset(raw, metadata, metadata_raw)
        return result


def wait_until(target, *, deadline):
    target, deadline = utc(target), utc(deadline)
    while True:
        actual = _now()
        require(actual <= deadline, "Daily operating deadline was missed")
        if actual >= target:
            return
        time.sleep(min(30, (target - actual).total_seconds()))


def _records_pr(writer, report, *, report_path):
    """Prepare one draft for later review; never merge, deploy or approve it."""
    body = ("Retain the actual single daily-snapshot NBA research cycle.\n\n"
            "This draft preserves original inputs, pending research forecasts and factual failure/partial evidence. "
            "It does not authorize activation, merge, deployment, financial settlement or qualified tickets.\n\n"
            "Cycle: `" + report["cycle_id"] + "`\n"
            "Outcome: `" + report["status"] + "`\n"
            "Genuine timely durable forecasts: " + str(report.get("genuine_issued", 0)) + "\n")
    body_path = Path(report_path).with_name("records-pr-body.txt")
    body_path.write_text(body, encoding="utf-8")
    existing = subprocess.run(["gh", "pr", "list", "--repo", cycles.REPOSITORY,
        "--head", writer.branch, "--state", "open", "--json", "number,url,isDraft"],
        capture_output=True, text=True, timeout=30, check=False)
    require(existing.returncode == 0, "Cannot inspect the existing draft records PR")
    rows = _decode(existing.stdout.encode())
    require(type(rows) is list and len(rows) <= 1, "Ambiguous daily records PR")
    if rows:
        require(rows[0].get("isDraft") is True, "Existing records PR is no longer draft; owner review required")
        return rows[0]["url"]
    created = subprocess.run(["gh", "pr", "create", "--repo", cycles.REPOSITORY,
        "--base", "main", "--head", writer.branch, "--draft",
        "--title", "Retain one daily-snapshot NBA research cycle", "--body-file", str(body_path)],
        capture_output=True, text=True, timeout=30, check=False)
    require(created.returncode == 0, "Could not create draft records PR; originals remain durably retained")
    return created.stdout.strip()


def validate_operation(body):
    """Bounded factual operating evidence; never an activation or issuance grant."""
    required = {"schema_version", "protocol_id", "cycle_id", "mode", "phase", "status", "recorded_at",
        "source_requests", "input_ref", "forecast_ids", "genuine_issued", "error", "operation_id"}
    require(type(body) is dict and set(body) == required and body["schema_version"] == OPERATION_SCHEMA
            and body["protocol_id"] == inputs.PROTOCOL_ID and body["cycle_id"] == cycles.CYCLE_ID
            and body["mode"] == "PROSPECTIVE_RESEARCH", "Invalid daily operation evidence contract")
    for key in ("phase", "status"):
        require(type(body[key]) is str and 0 < len(body[key]) <= 64, "Invalid daily operation status")
    recorded = producer.clock(body["recorded_at"])
    require(recorded <= _now(), "Future daily operation report")
    require(body["error"] is None or type(body["error"]) is str and len(body["error"]) <= 1500,
            "Invalid daily operation error")
    if body["input_ref"] is not None:
        require(LedgerRef.from_record(body["input_ref"]).kind == "research_inputs", "Invalid operation input reference")
    forecasts = body["forecast_ids"]
    require(type(forecasts) is list and len(forecasts) <= 8
            and all(type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) for value in forecasts)
            and len(set(forecasts)) == len(forecasts),
            "Invalid operation forecast inventory")
    require(type(body["genuine_issued"]) is int and 0 <= body["genuine_issued"] <= len(forecasts),
            "Invalid operation genuine count")
    requests = body["source_requests"]
    require(type(requests) is list and len(requests) <= MAX_SOURCE_REQUESTS, "Operation source request budget exceeded")
    base = {"request_number", "label", "route", "retrieval_started_at", "response_limit_bytes",
            "automatic_redirects", "automatic_retries"}
    optional = {"status", "response_read_completed_at", "bytes_read", "response_exceeded_limit",
                "retrieved_at", "bytes", "sha256", "failed_at"}
    for number, row in enumerate(requests, 1):
        require(type(row) is dict and base <= set(row) <= base | optional and row["request_number"] == number
            and type(row["request_number"]) is int and row["automatic_redirects"] is False
            and type(row["automatic_retries"]) is int and row["automatic_retries"] == 0
            and type(row["response_limit_bytes"]) is int
            and row["response_limit_bytes"] in {MAX_METADATA_BYTES, MAX_ASSET_BYTES}, "Invalid operation request ledger")
        require(type(row["label"]) is str and 0 < len(row["label"]) <= 64
                and type(row["route"]) is str, "Invalid operation request identity")
        route = urllib.parse.urlsplit(row["route"])
        require(route.scheme == "https" and route.hostname in {"api.github.com", "github.com",
            "release-assets.githubusercontent.com"} and not route.query and not route.fragment
            and not route.username and not route.password, "Operation request route contains unadmitted/private detail")
        started = producer.clock(row["retrieval_started_at"])
        require(started <= recorded, "Future operation request")
        for key in ("response_read_completed_at", "retrieved_at", "failed_at"):
            if key in row:
                require(started <= producer.clock(row[key]) <= recorded, "Operation request clocks conflict")
        if "status" in row:
            require(row["status"] == "UNOBSERVED" or type(row["status"]) is int and 100 <= row["status"] <= 599,
                    "Invalid observed request status")
        if "bytes_read" in row:
            require(type(row["bytes_read"]) is int and 0 <= row["bytes_read"] <= row["response_limit_bytes"] + 1
                    and type(row.get("response_exceeded_limit")) is bool
                    and row["response_exceeded_limit"] == (row["bytes_read"] > row["response_limit_bytes"]),
                    "Invalid bounded request byte observation")
        if "sha256" in row or "bytes" in row or "retrieved_at" in row:
            require(all(key in row for key in ("sha256", "bytes", "retrieved_at", "bytes_read"))
                    and type(row["sha256"]) is str and re.fullmatch(r"[a-f0-9]{64}", row["sha256"])
                    and type(row["bytes"]) is int and row["bytes"] == row["bytes_read"]
                    and not row["response_exceeded_limit"], "Incomplete response was promoted to an original")
    require(body["operation_id"] == digest({key: value for key, value in body.items() if key != "operation_id"}),
            "Daily operation checksum mismatch")
    return body


def _persist_operation(store, cycle, report, work, input_ref, asset_refs):
    prior = [body for _, body in store.records() if body["schema_version"] == OPERATION_SCHEMA]
    require(len(prior) < 8, "Daily cycle exhausted its eight bounded operating reports")
    requests = _request_inventory(store, work)
    recovered = store.recover()
    forecast_refs = [ref for ref, _ in recovered["forecasts"]]
    body = producer.seal({"schema_version": OPERATION_SCHEMA, "protocol_id": inputs.PROTOCOL_ID,
        "cycle_id": cycle["cycle_id"], "mode": "PROSPECTIVE_RESEARCH", "phase": report["phase"],
        "status": report["status"], "recorded_at": stamp(_now()), "source_requests": requests,
        "input_ref": input_ref.to_record() if input_ref else None,
        "forecast_ids": sorted(body["forecast_id"] for _, body in recovered["forecasts"]),
        "genuine_issued": recovered["genuine_issued"], "error": report["error"]}, "operation_id")
    validate_operation(body)
    references = list(asset_refs) + ([input_ref] if input_ref else []) + forecast_refs
    return store.append_body("input_captures", body, references=tuple(dict.fromkeys(references)))


def _request_inventory(store, work):
    request_file = work / "originals/requests.json"
    if request_file.exists():
        return _decode(_bounded_bytes(request_file, 64 * 1024))
    retained = [body["source_requests"] for _, body in store.records()
                if body["schema_version"] == OPERATION_SCHEMA and body["source_requests"]]
    return max(retained, key=len, default=[])


def _require_unstarted_capture(store):
    """A fresh host must not turn an interrupted capture into another six GETs."""
    records = store.records()
    prior = [body for _, body in records if body["schema_version"] == OPERATION_SCHEMA]
    require(not any(body["schema_version"] == ASSET_SCHEMA for _, body in records)
        and not any(body["status"] == "CAPTURE_STARTED" or body["source_requests"] for body in prior),
        "Original daily capture already started without a complete retained input; preserve partial evidence, "
        "the interrupted request count may be unknown, and do not recapture")
    require(len(prior) <= 6, "Daily capture needs room for its marker and final report within the eight-report budget")


def _publish_records(commit):
    require(type(commit) is str and re.fullmatch(r"[a-f0-9]{40}", commit), "Invalid exact publication records commit")
    result = subprocess.run(["gh", "workflow", "run", "pages.yml", "--repo", cycles.REPOSITORY,
        "--ref", "main", "-f", "daily_records_commit=" + commit], capture_output=True, text=True,
        timeout=30, check=False)
    require(result.returncode == 0, "Genuine records are retained; existing Pages dispatch failed")
    return {"workflow": "pages.yml", "ref": "main", "daily_records_commit": commit,
            "requested_at": stamp(_now()), "status": "DISPATCH_REQUEST_ACCEPTED_NOT_DEPLOYMENT_VERIFIED"}


def run(*, work_root, producer_commit, records_branch, cycle_path=None):
    """Actual clocks and authenticated owner dispatch; this function is not called by preview."""
    from .sdv_daily_remote import DailyGitCheckpointWriter
    repository = Path(__file__).resolve().parents[1]
    work = Path(work_root).absolute()
    require(not any(parent.is_symlink() for parent in (work, *work.parents)), "Daily work root is a symlink")
    work.mkdir(parents=True, exist_ok=True)
    report_path = work / "execution-report.json"
    report = {"schema_version": "nba-sdv-daily-execution-report-v1", "started_at": stamp(_now()),
        "status": "STARTED", "phase": "AUTHORIZATION", "source_requests": 0,
        "genuine_issued": 0, "public_publication": False, "error": None}
    writer = store = cycle = input_ref = None
    observed_asset_refs = []
    failure = None
    authority_verified = False
    with (work / ".runner.lock").open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise IntegrityError("The single retained daily writer is already running") from exc
        try:
            cycle = cycles.load_cycle(cycle_path)
            report["cycle_id"] = cycle["cycle_id"]
            require(records_branch == cycle["records_branch"], "Daily records destination differs from reservation")
            binding = producer.make_source_binding(producer_commit)
            # This preliminary guard permits only read-only remote recovery.
            # It is not operating authority; the authenticated check below is mandatory.
            expected_environment = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": cycles.REPOSITORY,
                "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_ACTOR": cycles.OWNER,
                "GITHUB_REF": "refs/heads/main", "GITHUB_WORKFLOW_REF": cycles.REPOSITORY + "/"
                + cycles.WORKFLOW_PATH + "@refs/heads/main"}
            require(all(os.environ.get(key) == value for key, value in expected_environment.items()),
                    "Daily genuine runner requires the exact owner manual main workflow")
            state = work / "state"
            copy_records(repository, state)
            store = DailyStore(state)
            writer = DailyGitCheckpointWriter(state, work / "writer", base_commit=producer_commit,
                                               branch=records_branch)
            report["writer"] = writer.prepare()
            copy_records(writer.root, state)
            # Initial/restart authorization precedes every source request or remote write.
            retained_auth = [(ref, body) for ref, body in store.records()
                if body["schema_version"] == cycles.AUTHORIZATION_SCHEMA]
            if retained_auth:
                require(len(retained_auth) == 1, "Ambiguous retained daily authorization")
                authorization_ref, authorization = retained_auth[0]
                cycles.validate_authorization(authorization, cycle=cycle, producer_binding=binding)
                cycles.authenticate_retained_dispatch(authorization, binding, repository_root=repository)
            else:
                authorization = cycles.authorize_owner_dispatch(cycle, binding, repository_root=repository)
                store.append_body("input_captures", cycle)
                authorization_ref = store.append_body("input_captures", authorization)
            report["authorization_id"] = authorization["authorization_id"]
            authority_verified = True
            retained_inputs = store.recover()["inputs"]
            if retained_inputs:
                require(len(retained_inputs) == 1 and retained_inputs[0][1]["mode"] == "PROSPECTIVE_RESEARCH",
                        "Daily recovery has multiple or development input records")
                input_ref, body = retained_inputs[0]
            else:
                _require_unstarted_capture(store)
                report["phase"] = "WAIT_FOR_CAPTURE"
                _write_json(report_path, report)
                wait_until(cycle["retrieval_opens_at"], deadline=cycle["cutoff_at"])
                report["phase"] = "CAPTURE"
                marker = _persist_operation(store, cycle, {**report, "status": "CAPTURE_STARTED"},
                                            work, None, ())
                report["capture_marker_ref"] = marker.to_record()
                report["capture_marker_checkpoint"] = writer.flush()
                capture = BoundedCapture(work / "originals", opens_at=cycle["retrieval_opens_at"],
                                         closes_at=cycle["cutoff_at"])
                def persist_complete_asset(raw, metadata, original):
                    observed_asset_refs.append(store.retain_asset(raw, metadata, original))
                retained = capture.collect(cycle, on_asset=persist_complete_asset)
                report["source_requests"] = len(capture.requests)
                body = inputs.normalize_inputs(retained[0][0], retained[1][0], retained[0][1], retained[1][1],
                    event_id=cycle["event"]["event_id"], expected_candidates=cycle["candidates"],
                    mode="PROSPECTIVE_RESEARCH")
                require(_now() <= utc(cycle["cutoff_at"]), "Daily normalization missed cutoff")
                started = _now()
                input_ref = store.persist_input(body, observed_asset_refs)
                store.record_completion(input_ref, started_at=started)
            report["phase"] = "INPUT_RECOVERY"
            report["input_ref"] = input_ref.to_record()
            if not store.admission(input_ref)["eligible"]:
                report["input_checkpoint"] = writer.checkpoint(input_ref)
            require(store.admission(input_ref)["eligible"], "Daily input failed timely remote admission")
            intent_ref = producer.prepare_intent(store, input_ref, cycle, binding, authorization_ref=authorization_ref)
            if not _intent_ready(store, intent_ref, cutoff=cycle["cutoff_at"]):
                require(_now() <= utc(cycle["cutoff_at"]), "Unacknowledged generation intent missed cutoff")
                intent = store.ledger.read(intent_ref)["data"]["daily"]
                store.record_completion(intent_ref, started_at=utc(intent["created_at"]))
                report["intent_checkpoint"] = writer.checkpoint(intent_ref)
            require(_intent_ready(store, intent_ref, cutoff=cycle["cutoff_at"]),
                    "Generation intent lacks original durable pre-cutoff recovery")
            report["phase"] = "WAIT_FOR_ISSUANCE"
            _write_json(report_path, report)
            wait_until(cycle["cutoff_at"], deadline=cycle["issuance_closes_at"])
            report["phase"] = "ISSUANCE"
            producer.issue_cycle(store, input_ref, cycle, binding, authorization_ref=authorization_ref,
                                 checkpoint=writer.checkpoint)
            report.update(_summary(store))
            report["status"] = "ISSUED_PENDING_OUTCOMES" if report["genuine_issued"] == 8 else "PARTIAL"
        except Exception as exc:
            failure = exc
            report.update(status="FAILED_OR_PARTIAL", error=(type(exc).__name__ + ": " + str(exc))[:1500])
            if store is not None and cycle is not None:
                try:
                    current = store.recover()
                    requests = _request_inventory(store, work)
                    reason = (report["error"][:800] + "; retained_request_inventory_count=" + str(len(requests))
                              + "; retained_complete_assets=" + str(len(observed_asset_refs)))
                    body = producer.seal({"schema_version": "nba-sdv-daily-failure-v1",
                        "protocol_id": inputs.PROTOCOL_ID, "cycle_id": cycle["cycle_id"],
                        "mode": "PROSPECTIVE_RESEARCH", "phase": report["phase"],
                        "recorded_at": stamp(_now()), "reason": reason,
                        "input_ref": input_ref.to_record() if input_ref else None,
                        "retained_forecast_ids": sorted(body["forecast_id"] for _, body in current["forecasts"])},
                        "failure_id")
                    store.append_body("input_captures", body, references=tuple(observed_asset_refs))
                except Exception as evidence_error:
                    report["failure_retention_error"] = type(evidence_error).__name__ + ": " + str(evidence_error)[:500]
        finally:
            if store is not None:
                try:
                    report.update(_summary(store))
                except Exception as recovery_error:
                    report["recovery_error"] = type(recovery_error).__name__ + ": " + str(recovery_error)[:500]
            if store is not None:
                report["source_requests"] = len(_request_inventory(store, work))
                if "Original daily capture already started" in (report["error"] or ""):
                    report["source_request_count_status"] = "RETAINED_INVENTORY_ONLY_INTERRUPTED_TOTAL_MAY_BE_UNKNOWN"
            if authority_verified and writer is not None and writer._head is not None:
                try:
                    report["operation_ref"] = _persist_operation(store, cycle, report, work, input_ref,
                                                                 observed_asset_refs).to_record()
                    report["final_checkpoint"] = writer.flush()
                    try:
                        report["records_pr"] = _records_pr(writer, report, report_path=report_path)
                    except Exception as pr_error:
                        report["records_pr_error"] = type(pr_error).__name__ + ": " + str(pr_error)[:500]
                    if report.get("genuine_issued", 0) > 0:
                        report["publication_dispatch"] = _publish_records(report["final_checkpoint"]["commit"])
                except Exception as checkpoint_error:
                    report["final_checkpoint_error"] = type(checkpoint_error).__name__ + ": " + str(checkpoint_error)[:500]
                    failure = failure or checkpoint_error
            report["completed_at"] = stamp(_now())
            _write_json(report_path, report)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    if failure is not None:
        raise IntegrityError("Daily cycle failed or remained partial; see retained execution-report.json") from failure
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("preview")
    p.add_argument("--store-root", required=True)
    p.add_argument("--sample-root", required=True)
    p.add_argument("--producer-commit")
    p.add_argument("--cycle", dest="cycle_path")
    r = commands.add_parser("recover")
    r.add_argument("--store-root", required=True)
    p = commands.add_parser("run")
    p.add_argument("--mode", required=True, choices=["prospective"])
    p.add_argument("--producer-commit", required=True)
    p.add_argument("--records-branch", required=True)
    p.add_argument("--work-root", required=True)
    p.add_argument("--cycle", dest="cycle_path")
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    args.pop("mode", None)
    result = {"preview": preview, "recover": recover, "run": run}[command](**args)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

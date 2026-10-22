"""Bounded, independent publication of recovered production research originals.

The old daily pilot remains a separate frozen channel.  This publisher never
collects sports data, issues a forecast, grants authority or edits an original.
Exact raw CSVs and runtime receipts stay in the durable project archive.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from .integrity import IntegrityError, canonical, digest, load_json, read_receipt, stamp, utc
from .ledger import LedgerRef
from . import sdv_production_common as common

INDEX_SCHEMA = "nba-sdv-production-public-index-v1"
PAGE_SCHEMA = "nba-sdv-production-public-page-v1"
ENCODING = "CANONICAL_ORIGINAL_BODY_WITHOUT_ID"
STATUS = "PRODUCTION_RESEARCH"
MAX_ASSET_BYTES = 1024 * 1024
MAX_PAGES = 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_CLIENT_BYTES = 64 * 1024 * 1024
ROLLING_DAYS = 7
STATE_PATH = Path("production/publication-state.json")
PUBLIC_SCHEMAS = {common.PLAN_SCHEMA, common.INPUT_SCHEMA, common.AUTH_SCHEMA,
                  common.FORECAST_SCHEMA, common.OUTCOME_SCHEMA, common.GRADE_SCHEMA,
                  common.STATUS_SCHEMA}
COUNT_FIELDS = {"forecasts", "genuine_forecasts", "eligible_forecasts", "development_forecasts",
                "outcomes", "grades", "active_grades", "scored_grades", "dnp_grades",
                "pending_grades", "players", "events"}
OPERATION_FIELDS = {"registry_id", "registry_updated_at", "last_run_at", "last_run_status",
                    "last_run_id", "last_source_capture_at", "last_issued_at",
                    "next_configured_check_at", "next_check_basis", "publication_verified_at", "reason"}
INDEX_FIELDS = {"schema_version", "protocol_id", "generated_at", "policy", "operations", "coverage",
                "counts", "dates", "pages", "qualification", "financial_settlement", "index_id"}


def _date(value):
    common.require(type(value) is str and re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", value),
                   "Invalid public production date")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise IntegrityError("Invalid public production date") from exc


def original_record(row):
    """Hash the original numeric spelling before parsing it for display."""
    common.exact(row, {"reference", "record_encoding", "original_id", "record_json", "admission"},
                 "public original projection")
    reference = LedgerRef.from_record(row["reference"])
    common.sha(row["original_id"])
    common.require(row["record_encoding"] == ENCODING and type(row["record_json"]) is str,
                   "Invalid public original encoding")
    raw = row["record_json"].encode("utf-8")
    common.require(0 < len(raw) <= MAX_ASSET_BYTES and hashlib.sha256(raw).hexdigest() == row["original_id"],
                   "Public original byte hash differs")
    try:
        body = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise IntegrityError("Invalid encoded public original") from exc
    schema = body.get("schema_version") if type(body) is dict else None
    common.require(schema in PUBLIC_SCHEMAS and canonical(body) == raw
                   and common.ID_KEYS[schema] not in body and reference.kind == common.KINDS[schema],
                   "Unknown, noncanonical or wrong-kind public original")
    return {**body, common.ID_KEYS[schema]: row["original_id"]}


def project_original(reference, body, admission=None):
    common.require(isinstance(reference, LedgerRef) and body.get("schema_version") in PUBLIC_SCHEMAS,
                   "Unsupported production publication original")
    key = common.ID_KEYS[body["schema_version"]]
    return {"reference": reference.to_record(), "record_encoding": ENCODING,
            "original_id": body[key],
            "record_json": canonical({k: v for k, v in body.items() if k != key}).decode("utf-8"),
            "admission": admission}


def active_grades(records):
    bodies = [original_record(row) for row in records]
    old_outcomes = {body["previous_outcome_id"] for body in bodies
                    if body["schema_version"] == common.OUTCOME_SCHEMA and body["previous_outcome_id"] is not None}
    old_grades = {body["previous_grade_id"] for body in bodies
                  if body["schema_version"] == common.GRADE_SCHEMA and body["previous_grade_id"] is not None}
    return [body for body in bodies if body["schema_version"] == common.GRADE_SCHEMA
            and body["grade_id"] not in old_grades and body["outcome_id"] not in old_outcomes]


def unresolved_grading(records):
    """A newer failed run cannot erase a known later-statistics conflict."""
    latest, task_bindings, shard_tasks = {}, {}, {}
    bodies = [original_record(row) for row in records]
    inputs = {body["input_id"]: body for body in bodies if body["schema_version"] == common.INPUT_SCHEMA}
    for body in bodies:
        if body["schema_version"] != common.STATUS_SCHEMA or body["phase"] != "GRADE":
            continue
        detail = body["details"]
        common.sha(detail.get("task_id"))
        matching = [value for value in inputs.values()
                    if value["plan_id"] == body["plan_id"] and value["cycle_id"] == body["cycle_id"]]
        index = detail.get("shard_index")
        common.require(len(matching) == 1 and type(index) is int and 0 <= index < len(matching[0]["shards"])
                       and detail.get("player_ids") == matching[0]["shards"][index],
                       "Public grading task lacks its exact input shard/cohort")
        identity = (body["plan_id"], body["cycle_id"], index)
        binding = (*identity, matching[0]["input_id"], tuple(detail["player_ids"]))
        common.require(detail["task_id"] not in task_bindings or task_bindings[detail["task_id"]] == binding,
                       "Public grading task changed its bound input shard")
        common.require(identity not in shard_tasks or shard_tasks[identity] == detail["task_id"],
                       "Public grading shard changed its immutable task")
        task_bindings[detail["task_id"]], shard_tasks[identity] = binding, detail["task_id"]
        if detail.get("processing_complete") is not True or type(detail.get("grading")) is not dict:
            continue
        grading = detail["grading"]
        common.exact(grading, {"outcomes", "grades", "pending", "correction_quota_exhausted",
                               "unscored_originals", "unscored_reason"}, "completed grading status")
        common.require(all(type(grading[key]) is int and grading[key] >= 0 for key in ("outcomes", "grades")),
                       "Invalid public completed grading counters")
        for key in ("pending", "correction_quota_exhausted"):
            ids = grading[key]
            common.require(type(ids) is list and len(ids) == len(set(ids))
                and all(type(pid) is str and re.fullmatch(r"[1-9][0-9]*", pid)
                        and pid in detail["player_ids"] for pid in ids),
                "Invalid public unresolved grading identity")
        unscored = grading["unscored_originals"]
        common.require(type(unscored) is list and len(unscored) == len(set(unscored))
            and all(type(value) is str and re.fullmatch(r"[1-9][0-9]*:(R0|K0)", value)
                    and value.split(":")[0] in detail["player_ids"] for value in unscored)
            and grading["unscored_reason"] == "ORIGINAL_NOT_TIMELY_ADMITTED",
            "Invalid public unscored original identity or reason")
        old = latest.get(identity)
        if old is None or common.clock(body["observed_at"]) > common.clock(old["observed_at"]):
            latest[identity] = body
        elif common.clock(body["observed_at"]) == common.clock(old["observed_at"]):
            common.require(grading == old["details"]["grading"], "Conflicting simultaneous completed grading statuses")
    result = {}
    for body in bodies:
        if body["schema_version"] != common.FORECAST_SCHEMA:
            continue
        linked = inputs.get(body["input_id"])
        common.require(linked is not None, "Public grading forecast lacks its exact input")
        shards = [index for index, player_ids in enumerate(linked["shards"]) if body["player_id"] in player_ids]
        common.require(len(shards) == 1, "Public grading forecast lacks its exact input shard")
        status = latest.get((body["plan_id"], body["cycle_id"], shards[0]))
        if status is None:
            continue
        grading = status["details"]["grading"]
        if body["player_id"] in grading["correction_quota_exhausted"]:
            result[body["forecast_id"]] = "UNRESOLVED_LATER_CORRECTION"
        elif body["player_id"] in grading["pending"]:
            result[body["forecast_id"]] = "PENDING_FINAL_EVIDENCE"
    return result


def counts(records):
    unique = {}
    for row in records:
        body = original_record(row)
        unique[(body["schema_version"], row["original_id"])] = (row, body)
    forecasts = [(row, body) for row, body in unique.values() if body["schema_version"] == common.FORECAST_SCHEMA]
    eligible = [body for row, body in forecasts if row["admission"]["eligible"]]
    eligible_ids = {body["forecast_id"] for body in eligible}
    unresolved = unresolved_grading(records)
    grades = [body for body in active_grades([row for row, _ in unique.values()])
              if body["forecast_id"] in eligible_ids and body["forecast_id"] not in unresolved]
    final = {body["forecast_id"] for body in grades if body["status"] in {"SCORED", "DNP_NOT_SCORED"}}
    return {"forecasts": len(forecasts),
            "genuine_forecasts": len(eligible),
            "eligible_forecasts": len(eligible),
            "development_forecasts": sum(body["mode"] == "DEVELOPMENT_ONLY" for _, body in forecasts),
            "outcomes": sum(body["schema_version"] == common.OUTCOME_SCHEMA for _, body in unique.values()),
            "grades": sum(body["schema_version"] == common.GRADE_SCHEMA for _, body in unique.values()),
            "active_grades": len(grades), "scored_grades": sum(body["status"] == "SCORED" for body in grades),
            "dnp_grades": sum(body["status"] == "DNP_NOT_SCORED" for body in grades),
            "pending_grades": sum(body["forecast_id"] not in final for body in eligible),
            "players": len({("NBA", "espn", body["player_id"]) for body in eligible}),
            "events": len({("NBA", "espn", body["event_id"]) for body in eligible})}


def _admission(value, body, input_body, generated):
    from .sdv_production_inputs import freshness
    common.exact(value, {"eligible", "local_completed_at", "remote_recovered_at", "reasons", "archive_ref"},
                 "public completion admission")
    common.require(type(value["eligible"]) is bool and type(value["reasons"]) is list
                   and len(value["reasons"]) <= 64 and all(type(item) is str and 0 < len(item) <= 2048
                                                         for item in value["reasons"]),
                   "Invalid public production admission reasons")
    verified = common.clock(body["verified_at"])
    local, remote = value["local_completed_at"], value["remote_recovered_at"]
    if local is not None:
        common.require(verified <= common.clock(local) <= generated, "Public local completion clock differs")
    if remote is not None:
        common.require(local is not None and common.clock(local) <= common.clock(remote) <= generated,
                       "Public remote recovery clock differs")
    if value["archive_ref"] is not None:
        common.archive_ref(value["archive_ref"], diagnostic=body["mode"] == "DEVELOPMENT_ONLY")
    common.require(value["eligible"] == (not value["reasons"]), "Public admission must explain ineligibility")
    if value["eligible"]:
        policy = input_body["policy"]
        common.require(body["mode"] == "PROSPECTIVE_RESEARCH" and local is not None and remote is not None
                       and value["archive_ref"] is not None and body["issued_at"] is not None,
                       "Public eligibility lacks genuine original recovery")
        done = common.clock(remote)
        common.require(done <= common.clock(body["cutoff_at"]) + timedelta(seconds=policy["generation_window_seconds"])
                       and (done - common.clock(body["generation_started_at"])).total_seconds()
                       <= policy["original_latency_seconds"], "Public production original completed late")
        freshness(input_body, at=done, require_retrieval_window=True)
    else:
        common.require(body["mode"] != "DEVELOPMENT_ONLY" or body["issued_at"] is None,
                       "Development preview has an issuance clock")


def validate_records(records, *, generated_at, allow_development=True):
    """Validate typed meanings and complete cross-record relationships."""
    from . import sdv_production_inputs as inputs
    from . import sdv_production_forecasts as forecasts
    generated = common.clock(generated_at)
    common.require(type(records) is list, "Public production records must be a list")
    unique, refs = {}, {}
    for row in records:
        body = original_record(row)
        key = (body["schema_version"], row["original_id"])
        if key in unique:
            common.require(unique[key][1] == body and (body["schema_version"] != common.FORECAST_SCHEMA
                or unique[key][0]["admission"] == row["admission"]), "Conflicting duplicate public original/admission")
        else:
            unique[key] = (row, body)
        ref_key = digest(row["reference"])
        common.require(ref_key not in refs or refs[ref_key] == body, "Public reference changed its original")
        refs[ref_key] = body
        common.validate_body(body)
        for clock_key in ("planned_at", "normalized_at", "verified_at", "issued_at", "source_observed_at",
                          "graded_at", "observed_at", "run_started_at"):
            if body.get(clock_key) is not None:
                common.require(common.clock(body[clock_key]) <= generated, "Public original follows publication")
        if body.get("mode") == "DEVELOPMENT_ONLY":
            common.require(allow_development, "Development records cannot enter public production output")
        if body["schema_version"] != common.FORECAST_SCHEMA:
            common.require(row["admission"] is None, "Only forecast projections carry completion admission")
    plans = {body["plan_id"]: body for _, body in unique.values() if body["schema_version"] == common.PLAN_SCHEMA}
    normalized = {body["input_id"]: body for _, body in unique.values() if body["schema_version"] == common.INPUT_SCHEMA}
    original_forecasts = {body["forecast_id"]: body for _, body in unique.values() if body["schema_version"] == common.FORECAST_SCHEMA}
    outcomes = {body["outcome_id"]: body for _, body in unique.values() if body["schema_version"] == common.OUTCOME_SCHEMA}
    grades = {body["grade_id"]: body for _, body in unique.values() if body["schema_version"] == common.GRADE_SCHEMA}
    authorities = [body for _, body in unique.values() if body["schema_version"] == common.AUTH_SCHEMA]
    for body in normalized.values():
        common.require(body["plan_id"] in plans, "Public input lacks its exact registered plan")
        inputs.validate_input(body, plans[body["plan_id"]])
    subjects = set()
    for row, body in unique.values():
        if body["schema_version"] != common.FORECAST_SCHEMA:
            continue
        input_body = normalized.get(body["input_id"])
        common.require(input_body is not None and refs.get(digest(body["input_ref"])) == input_body,
                       "Public forecast lacks its exact original input reference")
        forecasts.validate_forecast(body, input_body, now=generated)
        key = tuple(body[k] for k in ("protocol_id", "cycle_id", "event_id", "player_id", "model_key"))
        common.require(key not in subjects, "Duplicate original public production subject/model")
        subjects.add(key)
        _admission(row["admission"], body, input_body, generated)
        if body["mode"] == "PROSPECTIVE_RESEARCH":
            common.require(any(auth["executed_files"] == body["producer_binding"]["files"]
                and common.clock(auth["verified_at"]) <= common.clock(body["generation_started_at"])
                for auth in authorities), "Public genuine forecast lacks its authenticated executing source")
    for body in outcomes.values():
        previous = outcomes.get(body["previous_outcome_id"])
        common.require(body["correction_revision"] == 1 or previous is not None,
                       "Public outcome correction lost its original")
        forecasts.validate_outcome(body, previous=previous)
        common.require(any(all(body[k] == forecast[k] for k in (*forecasts.SUBJECT_FIELDS, "event_starts_at"))
            and all(body[key] == normalized[forecast["input_id"]]["event"][key]
                    for key in ("season_ending_year", "season_type"))
            and common.clock(forecast["issued_at"] or forecast["verified_at"]) <= common.clock(body["source_observed_at"])
            for forecast in original_forecasts.values()), "Public outcome has no exact original subject")
    for body in grades.values():
        forecast, outcome = original_forecasts.get(body["forecast_id"]), outcomes.get(body["outcome_id"])
        previous = grades.get(body["previous_grade_id"])
        common.require(forecast is not None and outcome is not None
                       and (body["correction_revision"] == 1 or previous is not None),
                       "Public statistical grade lost its original forecast/outcome/correction")
        if body["mode"] == "PROSPECTIVE_RESEARCH":
            common.require(unique[(common.FORECAST_SCHEMA, body["forecast_id"])][0]["admission"]["eligible"],
                           "Public genuine grade cannot score an ineligible original")
        forecasts.validate_grade(body, forecast, outcome, previous=previous)
    for collection, previous_key in ((outcomes, "previous_outcome_id"), (grades, "previous_grade_id")):
        successors = [body[previous_key] for body in collection.values() if body[previous_key] is not None]
        common.require(len(successors) == len(set(successors)), "Public correction history forks")
    replaced = {body["previous_outcome_id"] for body in outcomes.values() if body["previous_outcome_id"] is not None}
    current_subjects = [tuple(body[key] for key in ("protocol_id", *forecasts.SUBJECT_FIELDS, "event_starts_at"))
                        for body in outcomes.values() if body["outcome_id"] not in replaced]
    common.require(len(current_subjects) == len(set(current_subjects)), "Multiple active public outcomes for one subject")
    active = active_grades(records)
    common.require(len({body["forecast_id"] for body in active}) == len(active),
                   "Multiple active public statistical grades for an original")
    unresolved_grading(records)
    return records


def _next_check(at):
    actual = utc(at)
    candidate = actual.replace(second=0, microsecond=0)
    for _ in range(61):
        if candidate > actual and candidate.minute in {2, 17, 32, 47}:
            return stamp(candidate)
        candidate += timedelta(minutes=1)
    raise IntegrityError("Cannot establish configured production check time")


def _operational_facts(registry):
    """Retain meaningful failures, without treating a routine tick as news."""
    latest = {}
    attempts = [*registry.get("attempts", []),
                *(row for day in registry.get("days", []) for row in day.get("attempts", []))]
    for row in attempts:
        if row["status"] not in {"CAPTURED", "FAILED"}:
            continue
        key = (row["phase"], tuple(sorted(row["scope"])))
        previous = latest.get(key)
        if previous is None or (row["started_at"], row["attempt_id"]) > (previous["started_at"], previous["attempt_id"]):
            latest[key] = row
    captures = [{key: row.get(key) for key in ("attempt_id", "phase", "scope", "status", "source_pack_ref")}
                for row in sorted(latest.values(), key=lambda item: (item["started_at"], item["attempt_id"]))]
    run = registry.get("last_run") or {}
    details = run.get("details") or {}
    # Factual job IDs and observation clocks remain in the original registry.
    # The public update identity needs only the failure meaning, not a fresh
    # digest for every hosted check that observes the same state.
    def errors(value):
        if type(value) is int:
            return value
        if type(value) is not list:
            return []
        allowed = {"phase", "name", "status", "conclusion", "error", "branch", "cycle_id", "event_id"}
        return [{key: re.sub(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9:.]+Z", "<observation-time>", item[key])
                 if type(item[key]) is str else item[key]
                 for key in sorted(allowed & set(item))}
                for item in value if type(item) is dict]
    facts = {"reason": details.get("reason"),
             "missed_planning_dates": details.get("missed_planning_dates", 0),
             "unacknowledged_issuance_shards": details.get("unacknowledged_issuance_shards", 0),
             "affected_game_dates": details.get("affected_game_dates", []),
             "affected_branches": details.get("affected_branches", []),
             "failures": errors(details.get("failures", [])),
             "recent_errors": errors(details.get("recent_errors", [])), "captures": captures}
    failed = any(row["status"] == "FAILED" for row in captures)
    failed = failed or facts["reason"] == "INCOMPLETE_OR_UNOBSERVED_WINDOW" or bool(facts["failures"] or facts["recent_errors"])
    return facts, failed


def publication_content_identity(registry):
    """Fingerprint actual delivery/failure facts independently of run clocks."""
    facts, failed = _operational_facts(registry)
    content = {"days": [{"game_date": day["game_date"], "plan_id": day["plan_id"],
        "plan_ref": day["plan_ref"], "source_pack_ref": day["source_pack_ref"],
        "shards": [{key: shard.get(key) for key in ("branch", "snapshot_ref", "input_task_ref",
            "prepared_input_task_ref", "issued_input_task_ref", "final_source_pack_ref", "graded_source_pack_ref")}
            for shard in sorted(day["shards"], key=lambda item: item["branch"])]}
        for day in sorted(registry.get("days", []), key=lambda item: item["game_date"])],
        "archived_days": registry.get("archived_days", []),
        "archived_attempts": registry.get("archived_attempts", []), "operating_facts": facts}
    return {"content_id": digest(content), "has_operational_failure": failed}


def make_operations(registry, records, *, now):
    bodies = [original_record(row) for row in records]
    run = registry.get("last_run") if registry else None
    run = run if type(run) is dict else {}
    captures = [s["retrieved_at"] for body in bodies if body["schema_version"] == common.INPUT_SCHEMA for s in body["sources"]]
    issued = [body["issued_at"] for row, body in ((row, original_record(row)) for row in records)
              if body["schema_version"] == common.FORECAST_SCHEMA and row["admission"]["eligible"]]
    publication = registry.get("publication") if registry else None
    publication = publication if type(publication) is dict else {}
    run_details = run.get("details")
    run_details = run_details if type(run_details) is dict else {}
    reason = ("Configured hosted checks do not guarantee execution. No run evidence is available." if not run
              else "Observed coordinator state is separate from source capture, timely forecast issuance and public delivery.")
    if run_details.get("reason") == "INCOMPLETE_OR_UNOBSERVED_WINDOW":
        reason = ("A preparation or issuance window passed without a complete admitted cycle. "
                  "Retained partial records remain available; missed forecasts are not backfilled.")
    elif registry:
        facts, _ = _operational_facts(registry)
        failed = [row for row in facts["captures"] if row["status"] == "FAILED"]
        if failed:
            phase = {"PLAN": "schedule and roster planning", "INPUT": "pregame inputs", "FINAL": "final statistics"}[failed[-1]["phase"]]
            reason = ("A source capture for "+phase+" failed. No new input or forecast is admitted from that failed capture; "
                      "retained records remain available.")
        elif facts["failures"] or facts["recent_errors"]:
            reason = ("A hosted preparation, issuance or recovery step failed or remains incomplete. Retained records remain "
                      "available; successful execution and timely durable recovery are still required.")
    return {"registry_id": registry["registry_id"] if registry else None,
            "registry_updated_at": registry["updated_at"] if registry else None,
            "last_run_at": run.get("observed_at") or run.get("recorded_at") or run.get("started_at"),
            "last_run_status": str(run.get("status") or (registry["status"] if registry else "NOT_STARTED")),
            "last_run_id": run.get("run_id"), "last_source_capture_at": max(captures, default=None),
            "last_issued_at": max(issued, default=None), "next_configured_check_at": _next_check(now),
            "next_check_basis": "CONFIGURED_CRON_NOT_GUARANTEED",
            "publication_verified_at": publication.get("verified_at"),
            "reason": reason}


def validate_index(index, *, now):
    common.exact(index, INDEX_FIELDS, "public index")
    common.require(index["schema_version"] == INDEX_SCHEMA and index["protocol_id"] == common.PROTOCOL_ID
                   and index["qualification"] == "UNAVAILABLE" and index["financial_settlement"] == "NOT_EVALUATED",
                   "Wrong production publication scope")
    generated = common.clock(index["generated_at"])
    common.require(generated <= utc(now), "Production publication is future-dated")
    common.validate_policy(index["policy"])
    common.exact(index["operations"], OPERATION_FIELDS, "public operating status")
    operations = index["operations"]
    for key in ("registry_updated_at", "last_run_at", "last_source_capture_at", "last_issued_at", "publication_verified_at"):
        if operations[key] is not None:
            common.require(common.clock(operations[key]) <= generated, "Public operating clock follows publication")
    if operations["registry_id"] is not None:
        common.sha(operations["registry_id"])
    common.require(operations["last_run_id"] is None or type(operations["last_run_id"]) is int and operations["last_run_id"] > 0,
                   "Invalid public operating run identity")
    common.text(operations["last_run_status"]); common.text(operations["reason"])
    common.require(operations["next_check_basis"] == "CONFIGURED_CRON_NOT_GUARANTEED"
                   and operations["next_configured_check_at"] == _next_check(generated),
                   "Public next check differs from registered schedule")
    common.exact(index["coverage"], {"from_game_date", "to_game_date", "rolling_days", "archived_days"}, "public date coverage")
    coverage = index["coverage"]
    common.require(coverage["rolling_days"] == ROLLING_DAYS and _date(coverage["to_game_date"]) >= generated.date()
                   and _date(coverage["from_game_date"]) == generated.date() - timedelta(days=ROLLING_DAYS-1),
                   "Production display date coverage differs")
    common.require(type(coverage["archived_days"]) is list and len(coverage["archived_days"]) <= 4096,
                   "Public archive inventory exceeds its bound")
    dates = set()
    for day in coverage["archived_days"]:
        common.exact(day, {"game_date", "archive_ref"}, "public archived day")
        common.require(_date(day["game_date"]) < _date(coverage["from_game_date"])
                       and day["game_date"] not in dates, "Public archived date conflicts with rolling coverage")
        dates.add(day["game_date"]); common.archive_ref(day["archive_ref"])
    common.exact(index["counts"], COUNT_FIELDS, "public counts")
    common.require(all(type(n) is int and n >= 0 for n in index["counts"].values()), "Invalid public production count")
    common.require(type(index["pages"]) is list and len(index["pages"]) <= MAX_PAGES,
                   "Production public page ceiling exceeded")
    seen = set()
    for page in index["pages"]:
        common.exact(page, {"path", "sha256", "generated_at", "record_count", "game_date"}, "public page descriptor")
        common.sha(page["sha256"])
        common.require(page["path"] == "sdv-production-page."+page["sha256"]+".json"
                       and page["path"] not in seen and page["generated_at"] == index["generated_at"]
                       and type(page["record_count"]) is int and 0 < page["record_count"] <= 4096,
                       "Invalid production public page path/count/clock")
        seen.add(page["path"])
        common.require(_date(coverage["from_game_date"]) <= _date(page["game_date"]) <= _date(coverage["to_game_date"]),
                       "Public page lies outside declared date coverage")
    common.require(type(index["dates"]) is list and len(index["dates"]) <= ROLLING_DAYS+2,
                   "Production date partition count exceeds its bound")
    dates = []
    for day in index["dates"]:
        common.exact(day, {"game_date", "counts", "first_event_starts_at", "last_event_starts_at"}, "public date partition")
        _date(day["game_date"]); common.exact(day["counts"], COUNT_FIELDS, "date counts")
        common.require(all(type(n) is int and n >= 0 for n in day["counts"].values()), "Invalid date counts")
        first, last = day["first_event_starts_at"], day["last_event_starts_at"]
        common.require((first is None and last is None) or first is not None and last is not None
            and common.clock(first) <= common.clock(last) and first[:10] == last[:10] == day["game_date"],
            "Public date forecast interval differs")
        dates.append(day["game_date"])
    common.require(dates == sorted(set(dates)) and set(dates) == {row["game_date"] for row in index["pages"]},
                   "Public date partitions differ from exact page inventory")
    common.check_seal(index, "index_id")
    common.require(len(canonical(index)) <= MAX_ASSET_BYTES, "Production public index exceeds 1 MiB")
    return index


def validate_page(page, *, generated_at, game_date=None):
    common.exact(page, {"schema_version", "protocol_id", "generated_at", "game_date", "records", "page_id"}, "public page")
    common.require(page["schema_version"] == PAGE_SCHEMA and page["protocol_id"] == common.PROTOCOL_ID
                   and page["generated_at"] == generated_at and type(page["records"]) is list
                   and 0 < len(page["records"]) <= 4096, "Invalid production public page")
    _date(page["game_date"])
    common.require(game_date is None or page["game_date"] == game_date, "Public page date differs from its descriptor")
    for row in page["records"]:
        original_record(row)
    common.check_seal(page, "page_id")
    common.require(len(canonical(page)) <= MAX_ASSET_BYTES, "Production public page exceeds 1 MiB")
    return page


def _coverage(index, records):
    first, last = (_date(index["coverage"][key]) for key in ("from_game_date", "to_game_date"))
    for row in records:
        body = original_record(row)
        day = body.get("game_date")
        if day is None:
            event = body.get("event")
            event_at = body.get("event_starts_at") or (event.get("event_starts_at") if type(event) is dict else None)
            day = event_at[:10] if event_at is not None else None
        if day is not None:
            common.require(first <= _date(day) <= last,
                           "Public original lies outside explicitly displayed date coverage")


def _partition(records):
    bodies = [(row, original_record(row)) for row in records]
    plans = {body["plan_id"]: body["game_date"] for _, body in bodies if body["schema_version"] == common.PLAN_SCHEMA}
    forecasts = {body["forecast_id"]: body["event_starts_at"][:10] for _, body in bodies if body["schema_version"] == common.FORECAST_SCHEMA}
    groups, shared = {}, []
    for row, body in bodies:
        day = body.get("game_date")
        event = body.get("event")
        event_at = body.get("event_starts_at") or (event.get("event_starts_at") if type(event) is dict else None)
        if day is None and event_at is not None:
            day = event_at[:10]
        if day is None and body["schema_version"] == common.GRADE_SCHEMA:
            day = forecasts[body["forecast_id"]]
        if day is None and body["schema_version"] == common.STATUS_SCHEMA:
            day = plans.get(body["plan_id"])
        if day is None:
            shared.append(row)
        else:
            groups.setdefault(day, []).append(row)
    return {day: [*rows, *shared] for day, rows in sorted(groups.items())}


def make_publication(records, *, now, registry=None, archived_days=(), allow_development=False):
    generated = stamp(now)
    records = sorted(records, key=lambda row: (original_record(row)["schema_version"], row["original_id"], digest(row["reference"])))
    validate_records(records, generated_at=generated, allow_development=allow_development)
    pages, descriptors, dates = [], [], []
    for day, day_records in _partition(records).items():
        chunk, day_pages = [], []
        for row in day_records:
            trial = common.seal({"schema_version": PAGE_SCHEMA, "protocol_id": common.PROTOCOL_ID, "game_date": day,
                                "generated_at": generated, "records": [*chunk, row]}, "page_id")
            if len(canonical(trial)) > MAX_ASSET_BYTES:
                common.require(bool(chunk), "One complete public original exceeds page budget; no truncation")
                day_pages.append(common.seal({"schema_version": PAGE_SCHEMA, "protocol_id": common.PROTOCOL_ID, "game_date": day,
                                             "generated_at": generated, "records": chunk}, "page_id"))
                chunk = [row]
            else:
                chunk.append(row)
        if chunk:
            day_pages.append(common.seal({"schema_version": PAGE_SCHEMA, "protocol_id": common.PROTOCOL_ID, "game_date": day,
                                         "generated_at": generated, "records": chunk}, "page_id"))
        for page in day_pages:
            sha = hashlib.sha256(canonical(page)).hexdigest()
            descriptors.append({"path": "sdv-production-page."+sha+".json", "sha256": sha,
                "generated_at": generated, "record_count": len(page["records"]), "game_date": day})
        pages.extend(day_pages)
        starts = [original_record(row)["event_starts_at"] for row in day_records
                  if original_record(row)["schema_version"] == common.FORECAST_SCHEMA and row["admission"]["eligible"]]
        dates.append({"game_date": day, "counts": counts(day_records),
                      "first_event_starts_at": min(starts, default=None), "last_event_starts_at": max(starts, default=None)})
    future_dates = [_date(original_record(row)["game_date"]) for row in records
                    if original_record(row)["schema_version"] == common.PLAN_SCHEMA]
    future_dates += [_date(day["game_date"]) for day in registry["days"]] if registry else []
    index = common.seal({"schema_version": INDEX_SCHEMA, "protocol_id": common.PROTOCOL_ID,
        "generated_at": generated, "policy": common.make_policy(), "operations": make_operations(registry, records, now=now),
        "coverage": {"from_game_date": (utc(now).date()-timedelta(days=ROLLING_DAYS-1)).isoformat(),
                     "to_game_date": max([utc(now).date(), *future_dates]).isoformat(), "rolling_days": ROLLING_DAYS,
                     "archived_days": list(archived_days)}, "counts": counts(records), "dates": dates, "pages": descriptors,
        "qualification": "UNAVAILABLE", "financial_settlement": "NOT_EVALUATED"}, "index_id")
    validate_index(index, now=now)
    _coverage(index, records)
    for page in pages:
        validate_page(page, generated_at=generated)
    common.require(sum(len(canonical(page)) for page in pages)+len(canonical(index)) <= MAX_TOTAL_BYTES,
                   "Production public projection exceeds 512 MiB; capture/grading archives remain separate")
    return index, pages


def validate_descriptor(value, *, now):
    common.exact(value, {"path", "sha256", "generated_at", "status", "retained", "error"}, "publication descriptor")
    common.sha(value["sha256"])
    common.require(value["path"] == "sdv-production."+value["sha256"]+".json" and value["status"] == STATUS
                   and type(value["retained"]) is bool and common.clock(value["generated_at"]) <= utc(now),
                   "Invalid production publication descriptor")
    if value["error"] is not None:
        common.text(value["error"])
    return value


def read_publication(data_dir, descriptor, *, now, allow_development=False):
    validate_descriptor(descriptor, now=now)
    root = Path(data_dir)
    index = load_json(root/descriptor["path"], max_bytes=MAX_ASSET_BYTES)
    common.require(canonical(index) == (root/descriptor["path"]).read_bytes()
                   and hashlib.sha256(canonical(index)).hexdigest() == descriptor["sha256"]
                   and index["generated_at"] == descriptor["generated_at"], "Production index bytes/clock differ")
    validate_index(index, now=now)
    records, pages, total = [], [], len(canonical(index))
    for page_descriptor in index["pages"]:
        path = root/page_descriptor["path"]
        page = load_json(path, max_bytes=MAX_ASSET_BYTES); raw = path.read_bytes()
        common.require(raw == canonical(page) and hashlib.sha256(raw).hexdigest() == page_descriptor["sha256"],
                       "Production public page hash/bytes differ")
        validate_page(page, generated_at=index["generated_at"], game_date=page_descriptor["game_date"])
        common.require(len(page["records"]) == page_descriptor["record_count"], "Production page count differs")
        total += len(raw); common.require(total <= MAX_TOTAL_BYTES, "Production public collection exceeds byte budget")
        records.extend(page["records"])
        pages.append(page)
    validate_records(records, generated_at=index["generated_at"], allow_development=allow_development)
    _coverage(index, records)
    common.require(counts(records) == index["counts"], "Production public counts differ from exact originals")
    for day in index["dates"]:
        rows = [row for reference, page in zip(index["pages"], pages)
                if reference["game_date"] == day["game_date"] for row in page["records"]]
        common.require(counts(rows) == day["counts"], "Production date counts differ from exact originals")
    return {"index": index, "records": records}


def publication_asset_paths(data_dir, descriptor, *, now, allow_development=False):
    recovered = read_publication(data_dir, descriptor, now=now, allow_development=allow_development)
    return [descriptor["path"], *(page["path"] for page in recovered["index"]["pages"])]


def _disk_guard(paths, *, additional=0):
    total = additional
    limit = common.make_policy()["runtime_disk_bytes"]
    for root in paths:
        if not Path(root).exists():
            continue
        for path in Path(root).rglob("*"):
            common.require(not path.is_symlink(), "Public runtime state traverses a symlink")
            if path.is_file():
                total += path.stat().st_size
                common.require(total <= limit, "Production public runtime exceeds 2-GiB disk budget")
    common.require(total <= limit, "Production public runtime exceeds 2-GiB disk budget")
    return total


def emit_publication(data_dir, root, *, now, allow_development=False, archive=None, existing_artifact_bytes=0):
    """Export already recovered archive snapshots; no source-data HTTP here."""
    from .publication import _write_atomic, _emit_asset
    root, data_dir = Path(root), Path(data_dir)
    common.require(not any(path.is_symlink() for path in (root, *root.parents, root/"production", root/STATE_PATH)),
                   "Production public source state traverses a symlink")
    state_path = root/STATE_PATH
    records, registry, archived = [], None, []
    if state_path.exists():
        state = load_json(state_path, max_bytes=4*1024*1024)
        common.exact(state, {"schema_version", "registry", "shards", "archived_days"}, "prepared publication state")
        common.require(state["schema_version"] == "nba-sdv-production-prepared-publication-v1", "Wrong prepared publication state")
        registry, archived = state["registry"], state["archived_days"]
        from .sdv_production_runner import validate_registry
        from .sdv_production_archive import GitHubReleaseArchive, recover_snapshot
        validate_registry(registry)
        expected_shards, expected_archived = _state_parts(registry, now=now)
        common.require(state["shards"] == expected_shards and archived == expected_archived,
                       "Prepared publication differs from the exact registered shard/archive inventory")
        common.require(type(state["shards"]) is list and len(state["shards"]) <= 1024, "Prepared shard inventory exceeds limit")
        archive = archive or GitHubReleaseArchive()
        with tempfile.TemporaryDirectory(prefix="nml-production-publication-recovery-") as temporary:
            for index, shard in enumerate(state["shards"]):
                _disk_guard((root/"production", data_dir.parent), additional=existing_artifact_bytes+common.make_policy()["runtime_ledger_bytes"])
                # Only a fresh read-only recovery is temporary. The worker's
                # state, unacknowledged originals and remote archives are never
                # touched. Each verified shard is removed before the next one.
                with tempfile.TemporaryDirectory(prefix="shard-", dir=temporary) as shard_root:
                    store = recover_snapshot(shard["snapshot_ref"], archive, Path(shard_root),
                                             source_root=root, independent=False)
                    recovered = store.recover()
                    if not allow_development or any(body.get("mode") == "PROSPECTIVE_RESEARCH"
                                                    for _, body in recovered["records"]):
                        _validate_registered_snapshot(store, recovered, shard, registry, archive, root)
                    for ref, body in recovered["records"]:
                        if body["schema_version"] in PUBLIC_SCHEMAS:
                            admission = recovered["admissions"][ref.record_id] if body["schema_version"] == common.FORECAST_SCHEMA else None
                            records.append(project_original(ref, body, admission))
    # Shared plan/input originals are not repeated when shards contain the same
    # reference; distinct receipt references retain their own original identity.
    records = list({digest(row): row for row in records}.values())
    index, pages = make_publication(records, now=now, registry=registry, archived_days=archived,
                                    allow_development=allow_development)
    _disk_guard((root/"production", data_dir.parent), additional=existing_artifact_bytes
                +len(canonical(index))+sum(len(canonical(page)) for page in pages))
    for descriptor, page in zip(index["pages"], pages):
        _write_atomic(data_dir/descriptor["path"], canonical(page))
    return _emit_asset(data_dir, index, prefix="sdv-production", status=STATUS)


def _validate_registered_snapshot(store, recovered, shard, registry, archive, root):
    """Bind each shard to the actual authorized source-capture originals."""
    from . import sdv_production_runner as runner
    from . import sdv_production_inputs as inputs
    from .sdv_production_coordinator import validate_task
    days = [day for day in registry["days"] if any(row["branch"] == shard["branch"] for row in day["shards"])]
    common.require(len(days) == 1, "Recovered production shard has no unique registered day")
    day = days[0]
    plan_pack, plan_sources = runner.recover_source_pack(day["source_pack_ref"], archive)
    common.require(set(plan_sources) == {"schedule", "roster"}, "Planning source pack role mismatch")
    plan = archive.get_json(day["plan_ref"])
    inputs.verify_plan_sources(plan, plan_sources["schedule"][0], plan_sources["roster"][0],
        plan_sources["schedule"][1], plan_sources["roster"][1],
        source_originals={role: values[2] for role, values in plan_sources.items()})
    common.require(plan["plan_id"] == day["plan_id"] == shard["plan_id"], "Published plan differs from registered originals")
    originals = recovered["records"]
    plans = [body for _, body in originals if body["schema_version"] == common.PLAN_SCHEMA]
    common.require(all(body == plan for body in plans), "Shard plan differs from its exact original archive")
    task_ref = shard["input_task_ref"]
    material = [body for _, body in originals if body["schema_version"] in
                {common.INPUT_SCHEMA, common.FORECAST_SCHEMA, common.OUTCOME_SCHEMA, common.GRADE_SCHEMA}]
    if task_ref is None:
        common.require(not material, "Published shard material lacks its immutable source task")
        return
    task = validate_task(archive.get_json(task_ref))
    common.require(task["plan_ref"] == day["plan_ref"] and task["plan_source_pack_ref"] == day["source_pack_ref"]
                   and all(task[key] == shard[key] for key in ("branch", "cycle_id", "event_id", "shard_index")),
                   "Publication task changed its source plan or registered shard")
    input_pack, input_sources = runner.recover_source_pack(task["input_source_pack_ref"], archive)
    common.require(set(input_sources) == {"schedule", "roster"}, "Fresh source pack role mismatch")
    input_body = archive.get_json(task["input_ref"])
    inputs.verify_input_sources(input_body, input_sources["schedule"][0], input_sources["roster"][0],
        input_sources["schedule"][1], input_sources["roster"][1],
        source_originals={role: values[2] for role, values in input_sources.items()}, plan=plan)
    common.require(input_body["cycle_id"] == task["cycle_id"]
                   and input_body["shards"][task["shard_index"]] == task["player_ids"],
                   "Published input differs from immutable complete-cohort task")
    source_inputs = [body for _, body in originals if body["schema_version"] == common.INPUT_SCHEMA]
    common.require(all(body == input_body for body in source_inputs), "Shard input differs from its exact archived original")
    role_refs = lambda pack, roles: [next(item["source_ref"] for item in pack["sources"] if item["role"] == role) for role in roles]
    for ref, body in originals:
        if body["schema_version"] in {common.PLAN_SCHEMA, common.INPUT_SCHEMA}:
            expected = role_refs(plan_pack if body["schema_version"] == common.PLAN_SCHEMA else input_pack, ("schedule", "roster"))
            payload = read_receipt(store.root/"records"/ref.kind/(ref.record_id+".json"), max_bytes=2*1024*1024)
            common.require(digest(payload) == ref.payload_sha256 and payload["data"]["archive_refs"] == expected,
                           "Shard source references differ from authenticated capture pack")
        elif body["schema_version"] == common.FORECAST_SCHEMA:
            common.require(body["player_id"] in task["player_ids"], "Public forecast is outside its registered shard")
        elif body["schema_version"] == common.STATUS_SCHEMA and body["phase"] in {"PREPARE", "ISSUE", "GRADE"}:
            common.require(body["plan_id"] == plan["plan_id"] and body["cycle_id"] == task["cycle_id"]
                and all(body["details"].get(key) == task[key] for key in ("task_id", "shard_index", "player_ids")),
                "Public worker status differs from its authenticated immutable task")
    outcomes = [body for _, body in originals if body["schema_version"] == common.OUTCOME_SCHEMA]
    if outcomes:
        pack_refs = [shard.get(key) for key in ("final_source_pack_ref", "graded_source_pack_ref")]
        pack_refs += [attempt["source_pack_ref"] for attempt in [*day["attempts"], *registry.get("attempts", [])]
                      if attempt["phase"] == "FINAL" and attempt["source_pack_ref"] is not None]
        packs = {}
        for reference in pack_refs:
            if reference is not None and digest(reference) not in packs:
                pack, _ = runner.recover_source_pack(reference, archive)
                common.require({item["role"] for item in pack["sources"]} == {"schedule", "boxscore"},
                               "Statistical outcome capture pack has wrong roles")
                packs[digest(reference)] = pack
        for body in outcomes:
            common.require(any(body["source_archive_refs"] == role_refs(pack, ("schedule", "boxscore"))
                               for pack in packs.values()), "Public outcome lacks its authenticated final capture pack")
    # A reviewed producer may be followed by documentation-only main commits.
    # Authenticate the actual original source commit, rather than relabeling it
    # to the newer workflow head or comparing it with changed release code.
    authorities = [body for _, body in originals if body["schema_version"] == common.AUTH_SCHEMA]
    checked = set()
    for _, body in recovered["forecasts"]:
        if body["mode"] != "PROSPECTIVE_RESEARCH":
            continue
        binding = body["producer_binding"]
        if binding["binding_id"] in checked:
            continue
        matched = [auth for auth in authorities if auth["executed_files"] == binding["files"]]
        common.require(bool(matched), "Public forecast lost its authenticated executing source")
        commit = common.sha(binding["commit"], 40)
        for name, expected in binding["files"].items():
            result = subprocess.run(["git", "show", commit+":"+name], cwd=root,
                                    capture_output=True, check=False, timeout=30)
            common.require(result.returncode == 0 and len(result.stdout) <= 2*1024*1024
                           and hashlib.sha256(result.stdout).hexdigest() == expected,
                           "Reviewed production commit does not contain the original executed source")
        common.require(any(subprocess.run(["git", "merge-base", "--is-ancestor", commit, auth["head_sha"]],
                            cwd=root, capture_output=True, check=False, timeout=30).returncode == 0 for auth in matched),
                       "Reviewed production source is not an ancestor of its authenticated workflow head")
        checked.add(binding["binding_id"])


def _state_parts(registry, *, now):
    """Select an explicit rolling view without deleting or hiding originals."""
    first = utc(now).date()-timedelta(days=ROLLING_DAYS-1)
    archived = [day for day in registry["archived_days"] if _date(day["game_date"]) < first]
    shards = []
    for day in registry["days"]:
        if _date(day["game_date"]) < first:
            common.require(any(old["game_date"] == day["game_date"] for old in archived),
                           "Expired production day lacks its durable archived-day pointer")
            continue
        shards.extend(shard for shard in day["shards"] if shard["snapshot_ref"] is not None)
    return shards, archived


def prepare_published_records(root, commit=None, *, now=None):
    """Read the one registered pointer branch; never execute fetched code."""
    from .sdv_production_runner import RegistryWriter, validate_registry
    from .sdv_production_archive import GitHubReleaseArchive
    from .publication import _write_atomic
    root = Path(root)
    actual = utc(now or datetime.now(timezone.utc))
    if commit is not None:
        common.sha(commit, 40)
    with tempfile.TemporaryDirectory(prefix="nml-production-registry-readback-") as temporary:
        writer = RegistryWriter(Path(temporary)/"registry", archive=GitHubReleaseArchive())
        registry = writer.prepare(commit=commit)
        validate_registry(registry)
        if writer.commit is None:
            return {"status": "NO_RECORDS", "commit": None, "shards": 0}
        shards, archived = _state_parts(registry, now=actual)
        # Archived day metadata remains accessible; do not fetch old complete
        # source packs or repeatedly recalculate historical score summaries.
        state = {"schema_version": "nba-sdv-production-prepared-publication-v1", "registry": registry,
                 "shards": shards, "archived_days": archived}
        _write_atomic(root/STATE_PATH, canonical(state))
        return {"status": "PREPARED", "commit": writer.commit, "shards": len(shards)}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Independently recover the registered production publication index")
    parser.add_argument("--state-commit")
    args = parser.parse_args()
    print(prepare_published_records(Path(__file__).resolve().parents[1], args.state_commit))


if __name__ == "__main__":
    main()

"""Bounded, paginated public PROS004 research projections; never activation.

Only already-retained REAL_TIME_CAPTURED originals can enter these assets.
Diagnostics remain excluded, originals lacking completion stay explicitly
unadmitted, and no study aggregates or ticket candidates are produced. Full
history, raw provider bodies, and operational journal contents stay out of Pages.
"""
from __future__ import annotations

from datetime import timedelta
import hashlib
import math
import json
from pathlib import Path
import re

from .baseline import MARKETS, ForecastTarget
from .forecast_contract import (FORECAST_SCHEMA, UNITS, number, quantile,
                                validate_forecast)
from .integrity import IntegrityError, canonical, digest, load_json, stamp, utc
from .ledger import LedgerRef, validate_grade

STUDY_ID = "NBA-ALL13-JOINT-PROS-004"
INDEX_SCHEMA = "nba-pros004-public-index-v1"
PAGE_SCHEMA = "nba-pros004-public-page-v1"
FORECAST_SCHEMA_PUBLIC = "nba-pros004-public-forecast-v1"
GRADE_SCHEMA_PUBLIC = "nba-pros004-public-grade-v1"
RECORD_ENCODING = "CANONICAL_ORIGINAL_BODY_WITHOUT_ID"
PAGE_SIZE = 4
MAX_ASSET_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 24 * 1024 * 1024
MAX_FORECASTS = MAX_GRADES = 168
MAX_PAGES = 84
EVALUATION_NOT_BEFORE = "2026-11-25T00:00:00.000000Z"
SHA = re.compile(r"[a-f0-9]{64}")
MODELS = {"R0": "nba_joint_empirical_r0_v1", "K0": "nba_joint_lagged_workload_prior_k0_v1"}


def _require(condition, message):
    if not condition:
        raise IntegrityError(message)


def _exact(value, fields, label):
    _require(type(value) is dict and set(value) == set(fields), "Invalid public PROS004 "+label)


def _text(value):
    return type(value) is str and 0 < len(value) <= 2048 and value.strip() == value


def _hash(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def _clock(value):
    _require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", value),
             "Public PROS004 clocks require microsecond UTC")
    return utc(value)


def _sealed(body, id_key="projection_id"):
    return {**body, id_key: digest(body)}


def _verify_seal(body, key="projection_id"):
    _require(_hash(body.get(key)) and body[key] == digest({k: v for k, v in body.items() if k != key}),
             "Public PROS004 content checksum mismatch")


def original_record(row):
    """Recover source numeric spelling through the retained canonical JSON text.

    Python source floats such as 0.0 must never be rehashed as JavaScript's 0.
    The unsigned original is one exact byte string, not a lossy PMF projection.
    """
    _require(row.get("record_encoding") == RECORD_ENCODING and type(row.get("record_json")) is str
             and _hash(row.get("original_id")), "Invalid exact-original record encoding")
    raw = row["record_json"].encode("utf-8")
    _require(hashlib.sha256(raw).hexdigest() == row["original_id"], "Original public record checksum mismatch")
    try:
        record = json.loads(row["record_json"], parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (ValueError, TypeError) as exc:
        raise IntegrityError("Invalid original record JSON") from exc
    _require(type(record) is dict and canonical(record) == raw, "Original record JSON is not canonical or has duplicate keys")
    key = "forecast_id" if row.get("schema_version") == FORECAST_SCHEMA_PUBLIC else "grade_id"
    _require(key not in record, "Encoded original cannot replace its identity")
    return {**record, key: row["original_id"]}


def project_original(record, source_record, *, admission=None, model_version=None):
    """Wrap only a retained forecast/grade; source recovery happens separately."""
    forecast = record.get("schema_version") == "nba-pros004-forecast-v1"
    id_key = "forecast_id" if forecast else "grade_id"
    body = {"schema_version": FORECAST_SCHEMA_PUBLIC if forecast else GRADE_SCHEMA_PUBLIC,
        "study_id": STUDY_ID, "evidence_lane": "REAL_TIME_CAPTURED", "source_record": source_record,
        "record_encoding": RECORD_ENCODING, "original_id": record[id_key],
        "record_json": canonical({k:v for k,v in record.items() if k != id_key}).decode("utf-8")}
    body.update({"admission": admission} if forecast else {"model_version": model_version})
    return _sealed(body)


def _validation_forecast(record):
    """Internal validation view only; never publish a relabelled legacy record."""
    body = {"schema_version": FORECAST_SCHEMA,
        **{key: record[key] for key in ("id_namespace", "league", "event_id", "player_id", "player_label",
            "team_id", "opponent_id", "event_starts_at", "model_version", "trained_through", "cutoff_at",
            "history_freeze", "issued_at", "conditioning", "categories", "qualification")},
        "period": "full_game", "extra_time_policy": "includes_overtime",
        "model_commit": record["producer_binding"]["model_commit"],
        "model_code_sha256": record["producer_binding"]["law_sha256"][record["model_key"]],
        "input_sha256": record["joint_recipe"]["input_sha256"], "evidence_lane": "REAL_TIME_CAPTURED",
        "availability_basis": "OBSERVED_INPUT_CAPTURE",
        "input_capture_ids": [record["event_ref"]["record_id"], record["history_ref"]["record_id"]],
        "joint_method": "COMPLETE_LINE_EMPIRICAL", "joint_sha256": record["joint_recipe"]["joint_sha256"],
        "tail_policy": "FINITE_EMPIRICAL_SUPPORT_NO_SMOOTHING"}
    return _sealed(body, "forecast_id")


def _validate_minutes(distribution):
    _exact(distribution, {"pmf", "mean", "interval80", "precision"}, "reported-minute distribution")
    _require(distribution["precision"] == "reported_source_precision_not_exact_workload", "Changed workload meaning")
    pmf = distribution["pmf"]
    _require(type(pmf) is list and 0 < len(pmf) <= 1025, "Invalid complete reported-minute PMF")
    previous = -1
    probabilities = []
    for item in pmf:
        _exact(item, {"value", "probability"}, "minute atom")
        value = item["value"]
        _require(type(value) in {int, float} and math.isfinite(value) and value >= 0 and previous < value,
                 "Invalid ordered reported-minute support")
        probability = number(item["probability"], maximum=1)
        _require(probability > 0, "Zero reported-minute support atom")
        previous = value; probabilities.append(probability)
    _require(math.isclose(math.fsum(probabilities), 1, rel_tol=0, abs_tol=1e-12), "Incomplete minute probability mass")
    mean = math.fsum(item["value"] * p for item, p in zip(pmf, probabilities))
    _require(abs(number(distribution["mean"]) - mean) <= 1e-10 and distribution["interval80"] == [quantile(pmf, .1), quantile(pmf, .9)],
             "Reported-minute summary differs from original PMF")


def validate_forecast_projection(row, *, now):
    from .pros004_producer import validate_source_binding
    fields = {"schema_version", "study_id", "evidence_lane", "source_record", "record_encoding", "record_json", "original_id", "admission", "projection_id"}
    _exact(row, fields, "forecast projection")
    _require(row["schema_version"] == FORECAST_SCHEMA_PUBLIC and row["study_id"] == STUDY_ID
             and row["evidence_lane"] == "REAL_TIME_CAPTURED", "Diagnostic or unsupported public forecast lane")
    _verify_seal(row)
    ref = LedgerRef.from_record(row["source_record"])
    _require(ref.kind == "forecasts", "Public forecast must reference its original receipt")
    record = original_record(row)
    fields = {"schema_version", "study_id", "mode", "id_namespace", "league", "model_key", "model_version",
        "producer_version", "producer_binding", "history_ref", "event_ref", "event_id", "event_version",
        "event_starts_at", "player_id", "player_label", "team_id", "opponent_id", "cutoff_at", "history_freeze",
        "trained_through", "conditioning", "qualification", "generation_started_at", "generation_completed_at",
        "verified_at", "issued_at", "categories", "reported_minutes", "joint_recipe", "forecast_id"}
    _exact(record, fields, "original forecast")
    _require(record["schema_version"] == "nba-pros004-forecast-v1" and record["study_id"] == STUDY_ID
             and record["mode"] == "REAL_TIME_CAPTURED" and record["model_key"] in MODELS
             and record["model_version"] == MODELS[record["model_key"]]
             and record["producer_version"] in {f"pros004-{record['model_key'].lower()}-producer-v1", f"pros004-{record['model_key'].lower()}-producer-v2", f"pros004-{record['model_key'].lower()}-producer-v3"},
             "Original public model/lane/version mismatch")
    _verify_seal(record, "forecast_id")
    validate_source_binding(record["producer_binding"])
    _require(record["producer_binding"]["verification"] == "VERIFIED_COMMIT", "Public source commit is unverified")
    _require(record["producer_binding"]["schema_version"] == "nba-pros004-source-binding-" + record["producer_version"].rsplit("-", 1)[1], "Public producer/source versions disagree")
    _require(_hash(record["event_version"]), "Invalid original event version")
    _require(LedgerRef.from_record(record["history_ref"]).kind == "research_inputs"
             and LedgerRef.from_record(record["event_ref"]).kind == "research_inputs", "Changed public input reference")
    validate_forecast(_validation_forecast(record), now=now)
    cutoff = _clock(record["cutoff_at"])
    clocks = [_clock(record[k]) for k in ("generation_started_at", "generation_completed_at", "verified_at", "issued_at")]
    _require(cutoff <= clocks[0] <= clocks[1] <= clocks[2] == clocks[3] <= cutoff + timedelta(minutes=5)
             and clocks[3] - clocks[0] <= timedelta(seconds=120), "Original generation window is invalid")
    recipe = record["joint_recipe"]
    _exact(recipe, {"schema_version", "algorithm", "history_ref", "event_ref", "target", "support_atom_count", "atom_order",
        "joint_sha256", "input_sha256", "pool_history_count", "player_history_count", "fallback", "encoding", "omitted_atoms"}, "joint replay recipe")
    _require(recipe["schema_version"] == "nba-pros004-complete-joint-replay-v1"
             and recipe["algorithm"] == record["model_version"]
             and recipe["target"] == ForecastTarget(record["event_id"], record["player_id"], utc(record["event_starts_at"])).to_record()
             and recipe["atom_order"] == "frozen_algorithm_order_no_sampling_or_truncation"
             and recipe["encoding"] == "COMPLETE_SOURCE_BOUND_REPLAY_PLUS_ALL_ORIGINAL_MARGINALS"
             and _hash(recipe["input_sha256"]), "Changed complete joint recipe identity")
    _require(type(recipe) is dict and recipe.get("history_ref") == record["history_ref"]
             and recipe.get("event_ref") == record["event_ref"] and recipe.get("omitted_atoms") == 0
             and type(recipe.get("support_atom_count")) is int and recipe["support_atom_count"] > 0
             and recipe.get("pool_history_count") == recipe["support_atom_count"]
             and _hash(recipe.get("joint_sha256")), "Incomplete public joint-law reference")
    _validate_minutes(record["reported_minutes"])
    admission = row["admission"]
    _exact(admission, {"retained", "local_persistence_completed_at", "remote_checkpoint_completed_at",
                       "eligible_for_comparison", "reasons"}, "admission proof")
    _require(admission["retained"] is True and type(admission["eligible_for_comparison"]) is bool
             and type(admission["reasons"]) is list and len(admission["reasons"]) <= 16
             and all(_text(reason) for reason in admission["reasons"]), "Invalid public admission explanation")
    local = _clock(admission["local_persistence_completed_at"]) if admission["local_persistence_completed_at"] is not None else None
    remote = _clock(admission["remote_checkpoint_completed_at"]) if admission["remote_checkpoint_completed_at"] is not None else None
    _require((local is None or clocks[-1] <= local <= utc(now)) and (remote is None or local is not None and local <= remote <= utc(now)),
             "Persistence/remote completion order conflicts")
    if admission["eligible_for_comparison"]:
        _require(local is not None and remote is not None and remote <= cutoff + timedelta(minutes=5)
                 and remote - clocks[0] <= timedelta(seconds=120) and not admission["reasons"],
                 "Prospective comparison eligibility lacks timely completion")
    else:
        _require(bool(admission["reasons"]), "Unadmitted originals need a specific reason")
    _require(len(canonical(row)) <= 96 * 1024, "Public forecast exceeds complete projection budget")
    return row


def validate_grade_projection(row, forecasts, *, now):
    _exact(row, {"schema_version", "study_id", "evidence_lane", "source_record", "record_encoding", "record_json", "original_id", "model_version", "projection_id"}, "grade projection")
    _require(row["schema_version"] == GRADE_SCHEMA_PUBLIC and row["study_id"] == STUDY_ID
             and row["evidence_lane"] == "REAL_TIME_CAPTURED" and LedgerRef.from_record(row["source_record"]).kind == "grades", "Invalid public grade lane/reference")
    _verify_seal(row)
    grade = original_record(row)
    fields = {"schema_version", "study_id", "mode", "event_id", "event_version", "event_starts_at", "player_id", "team_id", "opponent_id",
              "model_key", "forecast_id", "outcome_id", "graded_at", "status", "categories", "reported_minutes", "financial_settlement", "qualification", "grade_id"}
    _exact(grade, fields, "original grade")
    _verify_seal(grade, "grade_id")
    forecast = forecasts.get(grade["forecast_id"])
    _require(forecast is not None, "Public grade references an unpublished original forecast")
    record = original_record(forecast)
    _require(grade["schema_version"] == "nba-pros004-grade-v1" and grade["study_id"] == STUDY_ID and grade["mode"] == "REAL_TIME_CAPTURED"
             and grade["status"] in {"SCORED", "DNP_NOT_SCORED", "MISSING", "POSTPONED", "NONFINAL", "UNRESOLVED"}
             and grade["financial_settlement"] == "NOT_EVALUATED" and grade["qualification"] == "UNAVAILABLE"
             and row["model_version"] == record["model_version"]
             and all(grade[k] == record[k] for k in ("event_id", "event_version", "event_starts_at", "player_id", "team_id", "opponent_id", "model_key")),
             "Public grade changed the original identity/model/status")
    _require(_clock(grade["graded_at"]) <= utc(now), "Future public grade clock")
    converted_forecast = _validation_forecast(record)
    converted = {"schema_version": "nba-forecast-grade-v1", "forecast_id": converted_forecast["forecast_id"],
        "outcome_id": grade["outcome_id"], "id_namespace": "espn", "league": "NBA", "event_id": grade["event_id"],
        "player_id": grade["player_id"], "graded_at": grade["graded_at"],
        "status": grade["status"] if grade["status"] in {"SCORED", "DNP_NOT_SCORED"} else "UNRESOLVED",
        "evidence_lane": "REAL_TIME_CAPTURED", "categories": grade["categories"], "financial_settlement": "NOT_EVALUATED"}
    validate_grade(_sealed(converted, "grade_id"), forecast=converted_forecast)
    _require((grade["status"] == "SCORED") == (grade["reported_minutes"] is not None), "Nonappearance grades cannot manufacture workload scores")
    if grade["status"] == "SCORED":
        from .pros004_records import _score_reported_minutes
        minutes = grade["reported_minutes"]
        _require(type(minutes) is dict and type(minutes.get("observed")) in {int, float}
                 and math.isfinite(minutes["observed"]) and minutes["observed"] >= 0
                 and minutes.get("observed_precision") in {"seconds", "rounded_whole_minutes"}
                 and (minutes["observed"] > 0 or minutes["observed_precision"] == "rounded_whole_minutes")
                 and (minutes["observed_precision"] != "rounded_whole_minutes" or float(minutes["observed"]).is_integer()), "Invalid observed workload score")
        expected = _score_reported_minutes(record, {"minutes": minutes["observed"], "minutes_precision": minutes["observed_precision"]})
        _require(minutes == expected, "Workload scores differ from original complete PMF")
    _require(len(canonical(row)) <= 24 * 1024, "Public grade exceeds projection budget")
    return row


def collect_public_records(root: Path, *, now):
    """Read all strict originals; never generate, score an aggregate or activate."""
    from .pros004_records import Pros004Store
    from .publication_ledger import CompositeEnvelopeLedger
    store = Pros004Store(root)
    store.ledger = CompositeEnvelopeLedger(root)
    index, _ = store._inventory()
    corrections = store.ledger._correction_map(index)
    forecasts = []
    grades = []
    excluded = {"diagnostic_forecasts": 0, "diagnostic_grades": 0, "superseded_grades": 0}
    for record_id, payload in index["forecasts"].items():
        record = payload["data"].get("pros004")
        if record is None:
            continue
        ref = LedgerRef("forecasts", record_id, digest(payload))
        record = store.body(ref)
        if record["mode"] != "REAL_TIME_CAPTURED":
            excluded["diagnostic_forecasts"] += 1
            continue
        status = store.admission_status(ref) if hasattr(store, "admission_status") else {}
        admission = {"retained": True,
            "local_persistence_completed_at": status.get("local_persistence_completed_at"),
            "remote_checkpoint_completed_at": status.get("remote_checkpoint_completed_at"),
            "eligible_for_comparison": status.get("eligible_for_comparison", False),
            "reasons": list(status.get("reasons", ["No durable completion/admission evidence is available for this original."]))}
        row = project_original(record, ref.to_record(), admission=admission)
        validate_forecast_projection(row, now=now)
        forecasts.append(row)
    by_id = {row["original_id"]: row for row in forecasts}
    for record_id, payload in index["grades"].items():
        record = payload["data"].get("pros004")
        if record is None:
            continue
        ref = LedgerRef("grades", record_id, digest(payload))
        record = store.body(ref)
        if record["mode"] != "REAL_TIME_CAPTURED":
            excluded["diagnostic_grades"] += 1
            continue
        if ref in corrections or any(LedgerRef.from_record(item) in corrections for item in payload["references"]):
            excluded["superseded_grades"] += 1
            continue
        forecast = by_id.get(record["forecast_id"])
        _require(forecast is not None, "An active grade has no retained original forecast")
        row = project_original(record, ref.to_record(), model_version=original_record(forecast)["model_version"])
        validate_grade_projection(row, by_id, now=now)
        grades.append(row)
    forecasts.sort(key=lambda row: (original_record(row)["event_starts_at"], original_record(row)["event_id"], original_record(row)["player_id"], original_record(row)["model_key"]))
    grades.sort(key=lambda row: (original_record(row)["graded_at"], row["original_id"]))
    return forecasts, grades, excluded


def _validate_shared_outcomes(grades):
    subjects = {}
    outcomes = {}
    for row in grades:
        grade = original_record(row)
        subject = tuple(grade[k] for k in ("event_id", "event_version", "player_id"))
        outcome = grade["outcome_id"]
        _require(subject not in subjects or subjects[subject] == outcome, "Paired active grades require one shared verified outcome")
        _require(outcome not in outcomes or outcomes[outcome] == subject, "Shared outcome conflicts with another subject identity")
        subjects[subject] = outcome
        outcomes[outcome] = subject


def make_assets(forecasts, grades, *, now, excluded=None):
    """Pure bounded wire assembly; callers must first use strict source recovery."""
    _require(type(forecasts) is list and len(forecasts) <= MAX_FORECASTS and type(grades) is list and len(grades) <= MAX_GRADES,
             "Complete PROS004 public inventory exceeds its registered bounds")
    seen = set()
    targets = set()
    for row in forecasts:
        validate_forecast_projection(row, now=now)
        _require(row["admission"]["eligible_for_comparison"] is False, "Inactive PROS004 collection cannot admit comparison eligibility")
        _require(row["original_id"] not in seen, "Duplicate original public forecast")
        seen.add(row["original_id"])
        record = original_record(row)
        target = tuple(record[k] for k in ("event_id", "event_version", "player_id", "model_key", "cutoff_at"))
        _require(target not in targets, "Duplicate original PROS004 target/model")
        targets.add(target)
    by_id = {row["original_id"]: row for row in forecasts}
    grade_ids = set()
    graded_forecasts = set()
    for row in grades:
        validate_grade_projection(row, by_id, now=now)
        _require(row["original_id"] not in grade_ids, "Duplicate active public grade")
        grade_ids.add(row["original_id"])
        forecast_id = original_record(row)["forecast_id"]
        _require(forecast_id not in graded_forecasts, "Multiple active PROS004 grades for one original")
        graded_forecasts.add(forecast_id)
    _validate_shared_outcomes(grades)
    excluded = excluded or {"diagnostic_forecasts": 0, "diagnostic_grades": 0, "superseded_grades": 0}
    _exact(excluded, {"diagnostic_forecasts", "diagnostic_grades", "superseded_grades"}, "exclusion accounting")
    _require(all(type(value) is int and value >= 0 for value in excluded.values()), "Invalid public exclusion counts")
    assets = {}
    pages = []
    for kind, rows in (("forecasts", forecasts), ("grades", grades)):
        for offset in range(0, len(rows), PAGE_SIZE):
            page = {"schema_version": PAGE_SCHEMA, "study_id": STUDY_ID, "league": "NBA", "kind": kind,
                "page_number": offset // PAGE_SIZE, "page_size": PAGE_SIZE, "total_records": len(rows),
                "generated_at": stamp(utc(now)), "records": rows[offset:offset + PAGE_SIZE]}
            raw = canonical(page)
            _require(len(raw) <= MAX_ASSET_BYTES, "Complete PROS004 page exceeds byte budget; no records may be truncated")
            sha = hashlib.sha256(raw).hexdigest()
            path = f"pros004.{kind}.{sha}.json"
            assets[path] = raw
            pages.append({"kind": kind, "page_number": page["page_number"], "path": path, "sha256": sha,
                          "encoded_bytes": len(raw), "records": len(page["records"])})
    index = {"schema_version": INDEX_SCHEMA, "study_id": STUDY_ID, "league": "NBA", "generated_at": stamp(utc(now)),
        "status": "RESEARCH_ONLY", "activation": "INACTIVE", "qualification": "UNAVAILABLE", "financial_settlement": "NOT_EVALUATED",
        "categories": list(MARKETS), "page_size": PAGE_SIZE, "totals": {"forecasts": len(forecasts), "grades": len(grades)},
        "excluded": excluded, "grade_visibility": "LATEST_ACTIVE_WITH_SOURCE_LEDGER_REFERENCES_SUPERSEDED_COUNTED",
        "aggregate_evaluation": {"status": "NOT_RUN", "not_before": EVALUATION_NOT_BEFORE},
        "future_availability": {"status": "UNAVAILABLE", "reasons": [
            "PROS004 remains inactive; no reviewed source-bound activation is admitted.",
            "Complete permitted UTC-day inventory and actual first-cutoff evidence remain an admission requirement.",
            "Retained originals without timely local persistence and independent remote completion remain unadmitted."]},
        "pages": pages}
    index["index_id"] = digest(index)
    raw = canonical(index)
    sha = hashlib.sha256(raw).hexdigest()
    path = f"pros004.index.{sha}.json"
    assets[path] = raw
    _require(len(pages) <= MAX_PAGES and sum(map(len, assets.values())) <= MAX_TOTAL_BYTES, "Complete PROS004 export exceeds total budget")
    descriptor = {"path": path, "sha256": sha, "generated_at": index["generated_at"], "status": "RESEARCH_ONLY", "retained": False, "error": None}
    return descriptor, index, assets


def validate_index(index, descriptor, *, now):
    fields = {"schema_version", "study_id", "league", "generated_at", "status", "activation", "qualification", "financial_settlement",
              "categories", "page_size", "totals", "excluded", "grade_visibility", "aggregate_evaluation", "future_availability", "pages", "index_id"}
    _exact(index, fields, "index")
    _verify_seal(index, "index_id")
    _require(index["schema_version"] == INDEX_SCHEMA and index["study_id"] == STUDY_ID and index["league"] == "NBA"
             and index["generated_at"] == descriptor["generated_at"] and _clock(index["generated_at"]) <= utc(now)
             and index["status"] == "RESEARCH_ONLY" and index["activation"] == "INACTIVE"
             and index["qualification"] == "UNAVAILABLE" and index["financial_settlement"] == "NOT_EVALUATED"
             and index["categories"] == list(MARKETS) and index["page_size"] == PAGE_SIZE, "Unsupported PROS004 public index meaning")
    _exact(index["totals"], {"forecasts", "grades"}, "totals")
    _require(all(type(value) is int and 0 <= value <= MAX_FORECASTS for value in index["totals"].values()), "Invalid public totals")
    _exact(index["excluded"], {"diagnostic_forecasts", "diagnostic_grades", "superseded_grades"}, "excluded counts")
    _require(all(type(value) is int and value >= 0 for value in index["excluded"].values())
             and index["grade_visibility"] == "LATEST_ACTIVE_WITH_SOURCE_LEDGER_REFERENCES_SUPERSEDED_COUNTED"
             and index["aggregate_evaluation"] == {"status": "NOT_RUN", "not_before": EVALUATION_NOT_BEFORE}, "Changed public exclusion/evaluation semantics")
    availability = index["future_availability"]
    _exact(availability, {"status", "reasons"}, "availability")
    _require(availability["status"] == "UNAVAILABLE" and type(availability["reasons"]) is list and availability["reasons"]
             and all(_text(reason) for reason in availability["reasons"]), "Inactive comparison cannot expose actionable future availability")
    _require(type(index["pages"]) is list and len(index["pages"]) <= MAX_PAGES, "Invalid public page budget")
    observed = {"forecasts": 0, "grades": 0}
    page_numbers = {"forecasts": 0, "grades": 0}
    total_bytes = len(canonical(index))
    for page in index["pages"]:
        _exact(page, {"kind", "page_number", "path", "sha256", "encoded_bytes", "records"}, "page descriptor")
        kind = page["kind"]
        _require(kind in observed and type(page["page_number"]) is int and page["page_number"] == page_numbers[kind]
                 and _hash(page["sha256"]) and page["path"] == f"pros004.{kind}.{page['sha256']}.json"
                 and type(page["encoded_bytes"]) is int and 0 < page["encoded_bytes"] <= MAX_ASSET_BYTES
                 and type(page["records"]) is int and 0 < page["records"] <= PAGE_SIZE, "Unsafe, missing or out-of-order public page")
        observed[kind] += page["records"]; page_numbers[kind] += 1; total_bytes += page["encoded_bytes"]
    _require(observed == index["totals"] and total_bytes <= MAX_TOTAL_BYTES, "Public pages silently omit records or exceed complete budget")
    return index


def read_publication(data_dir: Path, descriptor, *, now):
    _exact(descriptor, {"path", "sha256", "generated_at", "status", "retained", "error"}, "descriptor")
    _require(_hash(descriptor["sha256"]) and descriptor["path"] == f"pros004.index.{descriptor['sha256']}.json"
             and descriptor["status"] == "RESEARCH_ONLY" and type(descriptor["retained"]) is bool
             and (descriptor["error"] is None or _text(descriptor["error"])), "Unsafe or unsupported public index descriptor")
    path = data_dir / descriptor["path"]
    _require(not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == descriptor["sha256"], "Public index byte hash changed")
    index = validate_index(load_json(path, max_bytes=MAX_ASSET_BYTES), descriptor, now=now)
    rows = {"forecasts": [], "grades": []}
    for reference in index["pages"]:
        path = data_dir / reference["path"]
        _require(not path.is_symlink() and path.stat().st_size == reference["encoded_bytes"]
                 and hashlib.sha256(path.read_bytes()).hexdigest() == reference["sha256"], "Public page bytes/hash mismatch")
        page = load_json(path, max_bytes=MAX_ASSET_BYTES)
        _exact(page, {"schema_version", "study_id", "league", "kind", "page_number", "page_size", "total_records", "generated_at", "records"}, "page")
        _require(page["schema_version"] == PAGE_SCHEMA and page["study_id"] == STUDY_ID and page["league"] == "NBA"
                 and page["kind"] == reference["kind"] and page["page_number"] == reference["page_number"]
                 and page["page_size"] == PAGE_SIZE and page["total_records"] == index["totals"][page["kind"]]
                 and page["generated_at"] == index["generated_at"] and type(page["records"]) is list
                 and len(page["records"]) == reference["records"], "Public page inventory/metadata mismatch")
        rows[page["kind"]].extend(page["records"])
    ids = {}
    targets = set()
    for row in rows["forecasts"]:
        validate_forecast_projection(row, now=now)
        _require(row["admission"]["eligible_for_comparison"] is False, "Inactive PROS004 collection cannot admit comparison eligibility")
        key = row["original_id"]
        _require(key not in ids, "Duplicated public original across pages")
        ids[key] = row
        record = original_record(row)
        target = tuple(record[k] for k in ("event_id", "event_version", "player_id", "model_key", "cutoff_at"))
        _require(target not in targets, "Duplicate original PROS004 target/model across pages")
        targets.add(target)
    grades = set()
    graded_forecasts = set()
    for row in rows["grades"]:
        validate_grade_projection(row, ids, now=now)
        _require(row["original_id"] not in grades, "Duplicated public grade across pages")
        grades.add(row["original_id"])
        forecast_id = original_record(row)["forecast_id"]
        _require(forecast_id not in graded_forecasts, "Multiple active PROS004 grades across pages")
        graded_forecasts.add(forecast_id)
    _validate_shared_outcomes(rows["grades"])
    return {"index": index, **rows}


def publication_asset_paths(data_dir: Path, descriptor, *, now):
    result = read_publication(data_dir, descriptor, now=now)
    return [descriptor["path"], *(item["path"] for item in result["index"]["pages"])]


def emit_publication(data_dir: Path, root: Path, *, now):
    from .publication import _write_atomic
    forecasts, grades, excluded = collect_public_records(root, now=now)
    descriptor, _, assets = make_assets(forecasts, grades, now=now, excluded=excluded)
    for name, raw in assets.items():
        _write_atomic(data_dir / name, raw)
    read_publication(data_dir, descriptor, now=now)
    return descriptor

"""PROS004 paired R0/K0 producer controls, inactive pending reviewed activation.

The two mathematical laws are reused byte-for-byte. This readiness package
cannot authorize genuine issuance: its live-admission guard always rejects.
Synthetic controls operate only in explicitly diagnostic temporary stores.
Complete marginal probabilities are retained alongside a source-bound, full-input
joint replay recipe. No empirical probability atom is dropped or sampled.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import math
from pathlib import Path
import platform
import re
import subprocess
import sys

from .baseline import (MARKETS, MODEL_VERSION as R0_VERSION, ForecastTarget,
                       HistoricalAppearance, forecast_reference)
from .development_003 import KERNEL_VERSION, WorkloadPrior
from .forecast_contract import UNITS, _wire_pmf, decimal_text, number, quantile
from .integrity import IntegrityError, canonical, digest, stamp, utc
from .ledger import LedgerRef

STUDY_ID = "NBA-ALL13-JOINT-PROS-004"
SCHEMA = "nba-pros004-forecast-v1"
BINDING_SCHEMA = "nba-pros004-source-binding-v3"
JOINT_SCHEMA = "nba-pros004-complete-joint-replay-v1"
MODEL_VERSIONS = {"R0": R0_VERSION, "K0": KERNEL_VERSION}
PRODUCER_VERSIONS = {"R0": "pros004-r0-producer-v3", "K0": "pros004-k0-producer-v3"}
PRIOR_PRODUCER_VERSIONS = {"R0": "pros004-r0-producer-v2", "K0": "pros004-k0-producer-v2"}
LEGACY_PRODUCER_VERSIONS = {"R0": "pros004-r0-producer-v1", "K0": "pros004-k0-producer-v1"}
DIAGNOSTIC_MODES = {"READINESS_DIAGNOSTIC", "SYNTHETIC_DIAGNOSTIC"}
LAW_SHA256 = {"R0": "2a217b021ae25041920d14db6fbb1a14197ef4593b2b59965bbdef6f01304689",
              "K0": "282bb23a570bc6aaa217ab7f65ba223613c805801d8c479bc51aef0291b72be7"}
LEGACY_SOURCE_FILES = ("multisport_lab/pros004_producer.py", "multisport_lab/pros004_inputs.py",
    "multisport_lab/pros004_records.py", "multisport_lab/baseline.py",
    "multisport_lab/development_003.py", "multisport_lab/development_002.py",
    "multisport_lab/research_pilot.py", "multisport_lab/nba_data.py",
    "multisport_lab/basketball.py", "multisport_lab/integrity.py",
    "multisport_lab/ledger.py", "multisport_lab/forecast_contract.py",
    "multisport_lab/pregame_sources.py")
SOURCE_FILES = LEGACY_SOURCE_FILES + ("multisport_lab/pros004_completion.py", "multisport_lab/pros004_activation.py",
    "multisport_lab/pros004_remote.py", "multisport_lab/pros004_raw.py",
    "multisport_lab/pros004_snapshot.py", "scripts/verify_pros004_readiness.py")
MAX_FORECAST_BODY_BYTES = 62*1024  # Complete ledger envelope independently <=64KiB.
MAX_GENERATION_SECONDS = 120
GENERATION_WINDOW_SECONDS = 300
INPUT_FRESHNESS_SECONDS = 1200


def _now():
    return datetime.now(timezone.utc)


def _root():
    return Path(__file__).resolve().parents[1]


def _sha(value, name):
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise IntegrityError(f"invalid {name} SHA256")
    return value


def _exact(body, fields, name):
    if type(body) is not dict or set(body) != set(fields):
        raise IntegrityError(f"invalid {name} schema")


def _runtime():
    return {"python": sys.version, "implementation": platform.python_implementation(),
            "libc": list(platform.libc_ver()), "machine": platform.machine(),
            "float_mantissa_bits": sys.float_info.mant_dig}


def source_hashes(root=None):
    root = Path(root) if root is not None else _root()
    return {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def make_source_binding(model_commit=None, *, diagnostic=False, root=None):
    """Pin actual executed bytes; a diagnostic never invents a committed version."""
    root = Path(root) if root is not None else _root()
    hashes = source_hashes(root)
    if hashes["multisport_lab/baseline.py"] != LAW_SHA256["R0"] or hashes["multisport_lab/development_003.py"] != LAW_SHA256["K0"]:
        raise IntegrityError("PROS004 frozen R0/K0 mathematical source changed")
    if model_commit is None:
        if not diagnostic:
            raise IntegrityError("prospective producers require an explicit reviewed source commit")
        status = "LOCAL_DIAGNOSTIC_SOURCE"
    else:
        if type(model_commit) is not str or re.fullmatch(r"[a-f0-9]{40}", model_commit) is None:
            raise IntegrityError("producer source binding requires a full commit SHA")
        for name, expected in hashes.items():
            completed = subprocess.run(["git", "show", f"{model_commit}:{name}"], cwd=root,
                capture_output=True, check=False)
            if completed.returncode or hashlib.sha256(completed.stdout).hexdigest() != expected:
                raise IntegrityError(f"executed producer source differs from reviewed commit: {name}")
        status = "VERIFIED_COMMIT"
    return {"schema_version": BINDING_SCHEMA, "model_commit": model_commit,
            "verification": status, "source_sha256": hashes,
            "law_sha256": dict(LAW_SHA256), "runtime": _runtime()}


def validate_source_binding(binding, *, check_current=False):
    _exact(binding, {"schema_version", "model_commit", "verification", "source_sha256", "law_sha256", "runtime"}, "producer source binding")
    legacy=binding["schema_version"]=="nba-pros004-source-binding-v1"
    if binding["schema_version"] not in {BINDING_SCHEMA,"nba-pros004-source-binding-v2","nba-pros004-source-binding-v1"} or binding["law_sha256"] != LAW_SHA256:
        raise IntegrityError("producer mathematical law/source identity changed")
    if type(binding["source_sha256"]) is not dict or set(binding["source_sha256"]) != set(LEGACY_SOURCE_FILES if legacy else SOURCE_FILES):
        raise IntegrityError("producer dependency fingerprint inventory changed")
    for name, value in binding["source_sha256"].items():
        _sha(value, name)
    if binding["source_sha256"]["multisport_lab/baseline.py"] != LAW_SHA256["R0"] or binding["source_sha256"]["multisport_lab/development_003.py"] != LAW_SHA256["K0"]:
        raise IntegrityError("source binding contradicts frozen mathematical law bytes")
    if binding["verification"] == "LOCAL_DIAGNOSTIC_SOURCE":
        if binding["model_commit"] is not None:
            raise IntegrityError("uncommitted diagnostic binding cannot claim a reviewed commit")
    elif binding["verification"] == "VERIFIED_COMMIT":
        if type(binding["model_commit"]) is not str or re.fullmatch(r"[a-f0-9]{40}", binding["model_commit"]) is None:
            raise IntegrityError("committed producer binding lacks full commit identity")
    else:
        raise IntegrityError("unsupported source verification declaration")
    runtime = binding["runtime"]
    _exact(runtime, {"python", "implementation", "libc", "machine", "float_mantissa_bits"}, "producer runtime")
    if (any(type(runtime[k]) is not str or not runtime[k] for k in ("python", "implementation", "machine"))
            or type(runtime["libc"]) is not list or len(runtime["libc"]) != 2
            or any(type(x) is not str for x in runtime["libc"])
            or type(runtime["float_mantissa_bits"]) is not int or runtime["float_mantissa_bits"] < 1):
        raise IntegrityError("producer runtime fingerprint is malformed")
    if check_current:
        if binding["schema_version"]!=BINDING_SCHEMA:
            raise IntegrityError("legacy producer cannot be reused as the new durable-input producer")
        expected = make_source_binding(binding["model_commit"], diagnostic=binding["verification"] == "LOCAL_DIAGNOSTIC_SOURCE")
        if expected != binding:
            raise IntegrityError("source/runtime changed; original forecast must not be regenerated or replaced")
    return binding


def validate_activation_binding(activation, *, producer_binding, event_body):
    """Fail closed: this implementation package has no genuine-write admission.

    Neither a caller flag, a checksum, synthetic tests nor a fabricated activation
    object can enable prospective collection/issuance. A separately reviewed
    activation verifier and actual remote activation evidence are still required.
    """
    raise IntegrityError("PROS004 READINESS_ONLY: reviewed activation and remote recovery are not admitted; genuine issuance disabled")


def _event_target(event_body, player_id):
    event = event_body["event"]
    rows = [p for p in event_body["candidates"] if p["player_id"] == player_id]
    if len(rows) != 1:
        raise IntegrityError("player is outside the frozen PROS004 cohort")
    return ForecastTarget(event["event_id"], player_id, utc(event["event_starts_at"])), rows[0]


def _window(target, clock, *, started=None):
    if not target.cutoff <= clock <= target.cutoff+timedelta(seconds=GENERATION_WINDOW_SECONDS):
        raise IntegrityError("generation/issuance is outside the common T90 to T90+5 window")
    if started is not None and (clock < started or (clock-started).total_seconds() > MAX_GENERATION_SECONDS):
        raise IntegrityError("actual generation/verification exceeded its 120-second latency")


def _history_source_gate(history_body, target):
    receipts = history_body["history_provenance"]["source_receipts"]
    if any(utc(r["observed_at"]) > target.history_freeze for r in receipts):
        raise IntegrityError("fixed history observations exceed shared midnight information freeze")


def _input_gate(event_body, history_body, *, now=None):
    from .pros004_inputs import validate_event, validate_history, validate_input_lanes
    actual = _now() if now is None else now
    validate_event(event_body, now=actual)
    validate_history(history_body)
    validate_input_lanes(event_body, history_body)
    if event_body["study_id"] != STUDY_ID:
        raise IntegrityError("event belongs to another study")
    if event_body["event"]["status"] != "PRE_GAME":
        raise IntegrityError("event is no longer PRE_GAME")
    first = event_body["candidates"][0]["player_id"]
    target, _ = _event_target(event_body, first)
    _history_source_gate(history_body, target)
    return target


def preflight(event_body, history_body, producer_binding):
    """Check both producers before any generation; this is not timely issuance."""
    target = _input_gate(event_body, history_body)
    validate_source_binding(producer_binding, check_current=True)
    if event_body["mode"] == "REAL_TIME_CAPTURED":
        validate_activation_binding(None, producer_binding=producer_binding, event_body=event_body)
    elif event_body["mode"] not in DIAGNOSTIC_MODES:
        raise IntegrityError("unknown diagnostic/issuance evidence mode")
    return {"schema_version": "nba-pros004-preflight-v1", "study_id": STUDY_ID,
            "checked_at": stamp(_now()), "model_keys": ["R0", "K0"],
            "common_cutoff_at": stamp(target.cutoff), "history_freeze": stamp(target.history_freeze),
            "source_binding_sha256": digest(producer_binding),
            "event_sourcepack_id": event_body["sourcepack_id"],
            "history_id": history_body["history_id"], "future_issuance_admitted": False,
            "activation": "INACTIVE_READINESS_ONLY", "qualification": "UNAVAILABLE"}


def _fit_laws(history, target, *, need_kernel=True):
    reference = forecast_reference(history, target)
    result = {"R0": reference}
    if need_kernel:
        result["K0"] = WorkloadPrior(history).forecast(target, reference)
    return result


def joint_fingerprint(reference):
    """Same canonical digest as digest(all atom records), without a large copy."""
    hash_state = hashlib.sha256()
    hash_state.update(b"[")
    for index, atom in enumerate(reference.support):
        if index:
            hash_state.update(b",")
        hash_state.update(canonical(atom.to_record()))
    hash_state.update(b"]")
    return hash_state.hexdigest()


def _minutes(reference):
    grouped = defaultdict(list)
    for atom in reference.support:
        grouped[atom.line.minutes].append(atom.weight)
    marginal = {value: math.fsum(weights) for value, weights in sorted(grouped.items())}
    pmf = _wire_pmf(marginal)
    return {"pmf": pmf, "mean": decimal_text(math.fsum(a["value"]*number(a["probability"]) for a in pmf)),
            "interval80": [quantile(pmf, .1), quantile(pmf, .9)],
            "precision": "reported_source_precision_not_exact_workload"}


def _categories(reference):
    result = []
    for code in MARKETS:
        pmf = _wire_pmf(reference.marginal(code))
        result.append({"code": code, "units": UNITS[code], "pmf": pmf,
            "mean": decimal_text(math.fsum(a["value"]*number(a["probability"]) for a in pmf)),
            "interval80": [quantile(pmf, .1), quantile(pmf, .9)]})
    return result


def diagnostic_distributions(history, target):
    """Fit unchanged laws for an invented, already-eligible target; never issue.

    The diagnostic is deliberately outside any source-capture/record path. It
    takes no observed outcome and produces no score or prospective receipt.
    Actual clocks stay actual; callers cannot supply/backdate an issuance clock.
    """
    if not isinstance(target, ForecastTarget) or not target.event_id.startswith("DIAGNOSTIC_"):
        raise IntegrityError("non-issuance diagnostic requires an explicitly invented event ID")
    if any(not isinstance(row, HistoricalAppearance) for row in history):
        raise IntegrityError("diagnostic requires normalized historical appearances")
    laws = _fit_laws(history, target)
    return {"schema_version": "nba-pros004-law-diagnostic-v1", "mode": "READINESS_DIAGNOSTIC",
            "issued_forecasts": 0, "statistical_scores": 0, "generated_at": stamp(_now()),
            "target": target.to_record(), "model_versions": MODEL_VERSIONS,
            "laws": {key: {"input_sha256": law.input_sha256,
                 "joint_sha256": joint_fingerprint(law), "support_atom_count": len(law.support),
                 "categories": _categories(law), "reported_minutes": _minutes(law)}
                for key, law in laws.items()}}


def generate_forecast(event_body, history_body, *, event_ref, history_ref, player_id,
                      model_key, producer_binding):
    """Actual-clock synthetic-control producer; genuine writes remain disabled."""
    if model_key not in MODEL_VERSIONS:
        raise IntegrityError("PROS004 admits only unchanged R0 and K0, never S0")
    preflight(event_body, history_body, producer_binding)
    if LedgerRef.from_record(event_body["history_ref"]) != history_ref:
        raise IntegrityError("event and producer do not share exact retained history")
    target, candidate = _event_target(event_body, player_id)
    started = _now()
    _window(target, started)
    from .pros004_inputs import history_rows
    history = history_rows(history_body)
    laws = _fit_laws(history, target, need_kernel=model_key == "K0")
    reference = laws[model_key]
    categories, minutes = _categories(reference), _minutes(reference)
    joint_hash = joint_fingerprint(reference)
    completed = _now()
    _window(target, completed, started=started)
    recipe = {"schema_version": JOINT_SCHEMA, "algorithm": MODEL_VERSIONS[model_key],
        "history_ref": history_ref.to_record(), "event_ref": event_ref.to_record(),
        "target": target.to_record(), "support_atom_count": len(reference.support),
        "atom_order": "frozen_algorithm_order_no_sampling_or_truncation",
        "joint_sha256": joint_hash, "input_sha256": reference.input_sha256,
        "pool_history_count": reference.pool_history_count,
        "player_history_count": reference.player_history_count,
        "fallback": getattr(reference, "fallback", None),
        "encoding": "COMPLETE_SOURCE_BOUND_REPLAY_PLUS_ALL_ORIGINAL_MARGINALS",
        "omitted_atoms": 0}
    body = {"schema_version": SCHEMA, "study_id": STUDY_ID, "mode": event_body["mode"],
        "id_namespace": "espn", "league": "NBA", "model_key": model_key,
        "model_version": MODEL_VERSIONS[model_key], "producer_version": PRODUCER_VERSIONS[model_key],
        "producer_binding": producer_binding, "history_ref": history_ref.to_record(),
        "event_ref": event_ref.to_record(), "event_id": target.event_id,
        "event_version": event_body["event"]["event_version"],
        "event_starts_at": stamp(target.event_start), "player_id": player_id,
        "player_label": candidate["player_label"], "team_id": candidate["team_id"],
        "opponent_id": candidate["opponent_id"], "cutoff_at": stamp(target.cutoff),
        "history_freeze": stamp(target.history_freeze), "trained_through": stamp(reference.trained_through),
        "conditioning": "CONDITIONAL_ON_APPEARANCE", "qualification": "UNAVAILABLE",
        "generation_started_at": stamp(started), "generation_completed_at": stamp(completed),
        "verified_at": stamp(completed), "issued_at": stamp(completed),
        "categories": categories, "reported_minutes": minutes, "joint_recipe": recipe}
    body["forecast_id"] = digest(body)
    validate_forecast_record(body, event_body, history_body)
    # Exact in-memory producer comparison is distinct from independent restart.
    verify_reference_record(body, reference)
    verified = _now()
    _window(target, verified, started=started)
    body["verified_at"] = stamp(verified)
    body["issued_at"] = stamp(verified)
    body["forecast_id"] = digest({k:v for k,v in body.items() if k != "forecast_id"})
    validate_forecast_record(body, event_body, history_body)
    if len(canonical(body)) > MAX_FORECAST_BODY_BYTES:
        raise IntegrityError("complete forecast exceeds its 62KiB body reserve; no probability atoms may be dropped")
    return body, reference


def _validate_pmf(pmf, *, count=True):
    if type(pmf) is not list or not pmf or len(pmf) > 1025:
        raise IntegrityError("invalid complete probability support")
    previous, probabilities = -1, []
    for atom in pmf:
        _exact(atom, {"value", "probability"}, "probability atom")
        value = atom["value"]
        if (type(value) not in ((int,) if count else (int, float)) or not math.isfinite(value)
                or value < 0 or value <= previous):
            raise IntegrityError("probability support must be unique sorted nonnegative values")
        previous = value
        probability = number(atom["probability"], maximum=1)
        if probability <= 0:
            raise IntegrityError("all retained atoms need their actual positive probability")
        probabilities.append(probability)
    if not math.isclose(math.fsum(probabilities), 1, rel_tol=0, abs_tol=1e-12):
        raise IntegrityError("complete PMF must sum to one without renormalization")
    return math.fsum(a["value"]*p for a,p in zip(pmf, probabilities))


def validate_forecast_record(body, event_body, history_body):
    """Strict, optimization-safe structural/input verification; never issue/refit."""
    fields = {"schema_version", "study_id", "mode", "id_namespace", "league", "model_key", "model_version",
        "producer_version", "producer_binding", "history_ref", "event_ref", "event_id", "event_version",
        "event_starts_at", "player_id", "player_label", "team_id", "opponent_id", "cutoff_at", "history_freeze",
        "trained_through", "conditioning", "qualification", "generation_started_at", "generation_completed_at",
        "verified_at", "issued_at", "categories", "reported_minutes", "joint_recipe", "forecast_id"}
    _exact(body, fields, "PROS004 forecast")
    if (body["schema_version"] != SCHEMA or body["study_id"] != STUDY_ID
            or body["model_key"] not in MODEL_VERSIONS or body["id_namespace"] != "espn"
            or body["league"] != "NBA" or body["conditioning"] != "CONDITIONAL_ON_APPEARANCE"
            or body["qualification"] != "UNAVAILABLE"):
        raise IntegrityError("unsupported PROS004 forecast/model meaning")
    model = body["model_key"]
    if body["model_version"] != MODEL_VERSIONS[model] or body["producer_version"] not in {PRODUCER_VERSIONS[model],PRIOR_PRODUCER_VERSIONS[model],LEGACY_PRODUCER_VERSIONS[model]}:
        raise IntegrityError("mathematical model and operational producer identities disagree")
    expected_schema={LEGACY_PRODUCER_VERSIONS[model]:"nba-pros004-source-binding-v1",
        PRIOR_PRODUCER_VERSIONS[model]:"nba-pros004-source-binding-v2",PRODUCER_VERSIONS[model]:BINDING_SCHEMA}
    if body["producer_binding"].get("schema_version")!=expected_schema[body["producer_version"]]:
        raise IntegrityError("operational producer version conflicts with its source binding")
    validate_source_binding(body["producer_binding"])
    target = _input_gate(event_body, history_body)
    target, candidate = _event_target(event_body, body["player_id"])
    if body["mode"] != event_body["mode"] or body["mode"] not in DIAGNOSTIC_MODES | {"REAL_TIME_CAPTURED"}:
        raise IntegrityError("diagnostic evidence cannot be relabeled as prospective")
    if body["mode"] == "REAL_TIME_CAPTURED" and body["producer_binding"]["verification"] != "VERIFIED_COMMIT":
        raise IntegrityError("real-time records require committed source bindings")
    if LedgerRef.from_record(body["event_ref"]).kind != "research_inputs":
        raise IntegrityError("forecast requires its exact retained event input record")
    if body["history_ref"] != event_body["history_ref"]:
        raise IntegrityError("forecast references changed history")
    LedgerRef.from_record(body["history_ref"])
    expected = {"event_id": target.event_id, "event_version": event_body["event"]["event_version"],
        "event_starts_at": stamp(target.event_start), "player_label": candidate["player_label"],
        "team_id": candidate["team_id"], "opponent_id": candidate["opponent_id"],
        "cutoff_at": stamp(target.cutoff), "history_freeze": stamp(target.history_freeze)}
    if any(body[key] != value for key, value in expected.items()):
        raise IntegrityError("forecast target/event/version/cutoff differs from frozen selected input")
    clocks = {key:utc(body[key]) for key in ("generation_started_at", "generation_completed_at", "verified_at", "issued_at")}
    if not (target.cutoff <= clocks["generation_started_at"] <= clocks["generation_completed_at"]
            <= clocks["verified_at"] == clocks["issued_at"] <= target.cutoff+timedelta(seconds=300)):
        raise IntegrityError("original generation/verification/issuance clocks violate paired window")
    if (clocks["issued_at"]-clocks["generation_started_at"]).total_seconds() > MAX_GENERATION_SECONDS:
        raise IntegrityError("generation/verification latency exceeds 120 seconds")
    if utc(body["trained_through"]) > target.history_freeze:
        raise IntegrityError("training exceeded the causal daily history freeze")
    if clocks["issued_at"] > _now():
        raise IntegrityError("original forecast issue clock is in the future")
    if type(body["categories"]) is not list or len(body["categories"]) != len(MARKETS):
        raise IntegrityError("PROS004 requires all13 categories plus PA")
    means, seen = {}, set()
    for category in body["categories"]:
        _exact(category, {"code", "units", "pmf", "mean", "interval80"}, "category")
        code = category["code"]
        if code not in MARKETS or code in seen or category["units"] != UNITS[code]:
            raise IntegrityError("category identity/units are changed or duplicated")
        seen.add(code)
        mean = _validate_pmf(category["pmf"])
        if not math.isclose(number(category["mean"]), mean, rel_tol=0, abs_tol=1e-10):
            raise IntegrityError("category mean does not match its original probabilities")
        if category["interval80"] != [quantile(category["pmf"], .1), quantile(category["pmf"], .9)]:
            raise IntegrityError("category intervals do not match original probabilities")
        if code in {"DD", "TD"} and any(a["value"] not in (0,1) for a in category["pmf"]):
            raise IntegrityError("DD/TD support must be binary")
        means[code] = mean
    for target_code, pieces in {"PRA":("PTS","REB","AST"),"PR":("PTS","REB"),
            "RA":("REB","AST"),"PA":("PTS","AST"),"BLK+STL":("BLK","STL")}.items():
        if not math.isclose(means[target_code], math.fsum(means[p] for p in pieces), rel_tol=0, abs_tol=1e-10):
            raise IntegrityError("derived market means violate same-joint arithmetic")
    if means["TD"] > means["DD"]+1e-12 or means["PTS"]+1e-10 < 3*means["3PM"]:
        raise IntegrityError("joint scoring or TD<=DD constraint failed")
    minutes = body["reported_minutes"]
    _exact(minutes, {"pmf", "mean", "interval80", "precision"}, "reported-minute distribution")
    calculated = _validate_pmf(minutes["pmf"], count=False)
    if (minutes["precision"] != "reported_source_precision_not_exact_workload"
            or not math.isclose(number(minutes["mean"]), calculated, rel_tol=0, abs_tol=1e-10)
            or minutes["interval80"] != [quantile(minutes["pmf"], .1), quantile(minutes["pmf"], .9)]):
        raise IntegrityError("reported-minute mean/interval/precision mismatch")
    recipe = body["joint_recipe"]
    _exact(recipe, {"schema_version", "algorithm", "history_ref", "event_ref", "target", "support_atom_count",
        "atom_order", "joint_sha256", "input_sha256", "pool_history_count", "player_history_count", "fallback",
        "encoding", "omitted_atoms"}, "complete joint replay recipe")
    if (recipe["schema_version"] != JOINT_SCHEMA or recipe["algorithm"] != MODEL_VERSIONS[model]
            or recipe["history_ref"] != body["history_ref"] or recipe["event_ref"] != body["event_ref"]
            or recipe["target"] != target.to_record()
            or type(recipe["support_atom_count"]) is not int or recipe["support_atom_count"] <= 0
            or recipe["support_atom_count"] != recipe["pool_history_count"]
            or recipe["omitted_atoms"] != 0
            or recipe["atom_order"] != "frozen_algorithm_order_no_sampling_or_truncation"
            or recipe["encoding"] != "COMPLETE_SOURCE_BOUND_REPLAY_PLUS_ALL_ORIGINAL_MARGINALS"):
        raise IntegrityError("full-joint recipe dropped atoms, changed target or changed input")
    _sha(recipe["joint_sha256"], "joint")
    _sha(recipe["input_sha256"], "feature")
    if body["forecast_id"] != digest({k:v for k,v in body.items() if k != "forecast_id"}):
        raise IntegrityError("forecast immutable content checksum mismatch")
    if len(canonical(body)) > MAX_FORECAST_BODY_BYTES:
        raise IntegrityError("complete forecast body exceeds fixed retention reserve")
    return body


def verify_reference_record(body, reference):
    expected = {"joint_sha256": joint_fingerprint(reference), "input_sha256": reference.input_sha256,
                "support_atom_count": len(reference.support), "pool_history_count": reference.pool_history_count,
                "player_history_count": reference.player_history_count, "fallback":getattr(reference,"fallback",None)}
    if any(body["joint_recipe"][key] != value for key,value in expected.items()):
        raise IntegrityError("complete atom identities/lines/weights differ from original joint recipe")
    if body["categories"] != _categories(reference) or body["reported_minutes"] != _minutes(reference):
        raise IntegrityError("original marginal probabilities/minutes differ from complete joint law")
    if body["trained_through"] != stamp(reference.trained_through):
        raise IntegrityError("original trained-through clock differs from eligible history")
    return {"schema_version":"nba-pros004-joint-verification-v1", "forecast_id":body["forecast_id"],
            "joint_sha256":expected["joint_sha256"], "verified_atom_count":expected["support_atom_count"],
            "all_original_marginal_probabilities_exact":True, "qualification":"UNAVAILABLE"}


def verify_replay(body, event_body, history_body):
    """Independently recover the same full law without changing original clocks.

    This is reconstruction for integrity, never a new issued forecast or an
    outcome-based evaluation. Compatible source/runtime is required; otherwise
    read-only original receipts survive and replay fails explicitly.
    """
    validate_forecast_record(body, event_body, history_body)
    validate_source_binding(body["producer_binding"], check_current=True)
    from .pros004_inputs import history_rows
    target, _ = _event_target(event_body, body["player_id"])
    law = _fit_laws(history_rows(history_body), target, need_kernel=body["model_key"] == "K0")[body["model_key"]]
    return verify_reference_record(body, law)


def issue_pair(store, event_ref, producer_binding, *, player_id=None, checkpoint=None,
               input_final_checkpoint=None):
    """Exercise paired controls in a diagnostic store; recover originals first.

    A checkpoint exception stops subsequent generation and preserves every
    already-linked local original. No atomic paired success is asserted. Genuine
    operation is hard disabled until a later reviewed activation package.
    """
    if not getattr(store, "diagnostic", False):
        validate_activation_binding(getattr(store,"activation",None), producer_binding=producer_binding,
                                    event_body=store.body(event_ref))
    with store.writer_lock():
        event = store.body(event_ref)
        history_ref = LedgerRef.from_record(event["history_ref"])
        history = store.body(history_ref)
        preflight(event, history, producer_binding)  # Both producers before first.
        recovery = store.recover_event(event_ref, producer_binding)
        subjects = recovery["subjects"]
        if player_id is not None:
            subjects = [s for s in subjects if s["player_id"] == player_id]
            if not subjects:
                raise IntegrityError("requested paired subject is outside frozen selection")
        if not any(s["missing_models"] for s in subjects) and all(
                status is None or status["timing_complete"] for subject in subjects for status in subject["admission"].values()):
            if checkpoint is not None:
                refs=tuple(LedgerRef.from_record(ref) for subject in subjects for ref in subject["forecasts"].values() if ref)
                finalized=store.finalize_checkpoint(refs,checkpoint)
                return {**recovery,"final_checkpoint":finalized,
                    "metadata_publication_status":finalized["metadata_publication_status"]}
            return recovery
        target, _ = _event_target(event, subjects[0]["player_id"])
        actual = _now()
        if actual < target.cutoff:
            return {**recovery, "status":"ISSUANCE_NOT_YET_OPEN", "generation_attempted":False}
        if actual > target.cutoff+timedelta(seconds=GENERATION_WINDOW_SECONDS):
            # Readback is permitted after the window; no missing peer is created.
            status = "PARTIAL_WINDOW_CLOSED" if recovery["retained_models"] else "NOT_ISSUED_WINDOW_CLOSED"
            return {**recovery, "status":status, "generation_attempted":False}
        if checkpoint is None:
            return {**recovery,"status":"REMOTE_CHECKPOINT_REQUIRED","generation_attempted":False}
        claim_ref=LedgerRef.from_record(recovery["claim_ref"]) if recovery["claim_ref"] else None
        if claim_ref is None:
            return {**recovery,"status":"DURABLE_INPUT_ADMISSION_REQUIRED","generation_attempted":False}
        claim=store.body(claim_ref)
        if claim["schema_version"]!="nba-pros004-event-claim-v2":
            raise IntegrityError("legacy admission lacks durable input-phase proof; originals remain unadmitted")
        retained_input=claim["input_final_checkpoint"]
        if input_final_checkpoint is not None and input_final_checkpoint!=retained_input:
            raise IntegrityError("caller input-phase proof differs from the immutable admission")
        store.validate_input_checkpoint(event_ref,retained_input)
        if not store.admission_status(claim_ref)["timing_complete"]:
            raise IntegrityError("durable input admission lacks timely local/remote completion")
        if not store.admission_status(event_ref)["timing_complete"]:
            raise IntegrityError("event input lacks timely local/remote completion before selection closed")
        # Recover and acknowledge retained originals before any new generation.
        # A missing proof is never repaired by replacing probabilities or clocks.
        for subject in subjects:
            for model_key,original in subject["forecasts"].items():
                if original is None:continue
                record=LedgerRef.from_record(original)
                status=store.admission_status(record)
                if not status["local_timely"]:
                    raise IntegrityError("retained original lacks timely local completion; no replacement generation is permitted")
                if not status["remote_timely"]:
                    store.complete_checkpoint(record,checkpoint)
        for subject in subjects:
            for model_key in ("R0", "K0"):
                if model_key not in subject["missing_models"]:
                    continue
                _window(target, _now())
                body, reference = generate_forecast(event, history, event_ref=event_ref,
                    history_ref=history_ref, player_id=subject["player_id"], model_key=model_key,
                    producer_binding=producer_binding)
                verify_reference_record(body, reference)
                _window(target, _now(), started=utc(body["generation_started_at"]))
                record = store.persist_forecast(body,event_ref=event_ref,history_ref=history_ref,intent_ref=claim_ref)
                store.complete_checkpoint(record,checkpoint)
        recovery=store.recover_event(event_ref,producer_binding)
        # The final original's acknowledgment was appended after its own push.
        # Publish that complete metadata prefix once without renewing originals.
        refs=tuple(store.lookup_forecast(event_ref,subject["player_id"],model)
            for subject in subjects for model in ("R0","K0"))
        finalized=store.finalize_checkpoint(refs,checkpoint)
        return {**recovery,"final_checkpoint":finalized,
            "metadata_publication_status":finalized["metadata_publication_status"]}

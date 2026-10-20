"""Bounded, actual-clock pregame research issuance, separate from frozen R0.

R1 reuses R0's complete-line formula. It changes the operational input and
issuance semantics, not the statistical model's qualifications. No clock flag,
offline readiness result, price, or event outcome can admit a forecast here.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess

from .baseline import (COUNT_FIELDS, MARKETS, MODEL_VERSION as BASE_MODEL_VERSION,
                       PROTOCOL_ID, ForecastTarget, HistoricalAppearance,
                       JointForecast, forecast_reference)
from .forecast_contract import (FORECAST_SCHEMA_V2, UNITS, _wire_pmf,
                                decimal_text, number, quantile, validate_forecast)
from .integrity import IntegrityError, digest, stamp, utc

MODEL_VERSION = "nba_joint_empirical_pregame_r1_v1"
PRODUCER_VERSION = "nba-pregame-r1-v1"
BASE_CODE_SHA256 = "2a217b021ae25041920d14db6fbb1a14197ef4593b2b59965bbdef6f01304689"
PILOT_PANEL_SHA256 = "489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c"
PILOT_HISTORY_ROWS = 26_645
PILOT_EVENT_VERSION = "10579839a07f7b146eb82e9f9cd905bdc6d68198f396ff5fd0670a16410466b7"
PILOT_SELECTION_SHA256 = "8dd4a0c284e97abd92ccb2e9094e4eb50994ab7bad6ae18a50d0d27aeb4db17a"
MODEL_FILES = ("multisport_lab/prospective.py", "multisport_lab/baseline.py",
               "multisport_lab/forecast_contract.py", "multisport_lab/pregame_sources.py",
               "multisport_lab/ledger.py", "multisport_lab/basketball.py",
               "multisport_lab/integrity.py", "multisport_lab/nba_data.py",
               "scripts/prepare_nba_panel.py")


def _now():
    return datetime.now(timezone.utc)


def _code_hash(name="prospective.py"):
    return hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()


def _history(pack):
    from .pregame_sources import unpack_history
    rows = unpack_history(pack)
    history = [HistoricalAppearance(
        event_id=row.event_id, player_id=row.player_id, team_id=row.team_id,
        opponent_id=row.opponent_id, event_start=row.event_start,
        outcome_available_at=row.event_start + timedelta(hours=24),
        minutes=row.minutes, minutes_precision=row.minutes_precision,
        id_namespace=row.id_namespace, game_duration_minutes=row.game_duration_minutes,
        **{key: getattr(row, key) for key in COUNT_FIELDS}) for row in rows]
    return sorted(history, key=lambda row: (row.event_start, row.event_id, row.player_id))


def _view(pack):
    from .pregame_sources import binding_view, validate_pack
    validate_pack(pack)
    return binding_view(pack)


def _target(view, player_id):
    event = view["event"]
    candidates = [row for row in view["candidates"] if row["player_id"] == player_id]
    if len(candidates) != 1:
        raise IntegrityError("player is outside the frozen selected cohort")
    return ForecastTarget(event["event_id"], player_id, utc(event["event_starts_at"])), candidates[0]


def _eligible(history, target):
    return [row for row in history if row.event_id != target.event_id
            and row.event_start < target.history_freeze
            and row.outcome_available_at <= target.history_freeze]


def _input_hash(history, target):
    # Exact frozen R0 feature identity, distinct from the retained source pack.
    return digest({"protocol_id": PROTOCOL_ID, "model_version": BASE_MODEL_VERSION,
                   "target": target.to_record(), "history_freeze": stamp(target.history_freeze),
                   "rows": [row.to_record() for row in history]})


def preparation_status(pack, *, now=None):
    """Diagnostic only; successful preparation creates no forecast or admission."""
    view = _view(pack)
    start = utc(view["event"]["event_starts_at"])
    cutoff = start - timedelta(minutes=90)
    actual = utc(now) if now is not None else _now()
    phase = ("CAPTURE_NOT_YET_OPEN" if actual < cutoff-timedelta(minutes=10) else
             "CAPTURE_WINDOW" if actual < cutoff else
             "ISSUANCE_WINDOW" if actual <= cutoff+timedelta(minutes=5) else
             "ISSUANCE_WINDOW_CLOSED")
    return {"schema_version": "nba-pregame-status-v1", "checked_at": stamp(actual),
            "event_id": view["event"]["event_id"], "phase": phase,
            "capture_opens_at": stamp(cutoff-timedelta(minutes=10)),
            "capture_closes_at": stamp(cutoff), "issuance_opens_at": stamp(cutoff),
            "issuance_closes_at": stamp(cutoff+timedelta(minutes=5)),
            "selected_player_ids": [row["player_id"] for row in view["candidates"]],
            "history_rows": view["history_rows"], "history_latest_event_at": view["history_latest_event_at"],
            "future_issuance_admitted": False, "qualification": "UNAVAILABLE"}


def _check_capture_window(view, target):
    minimum, maximum = utc(view["source_observed_min_at"]), utc(view["source_observed_max_at"])
    imported = utc(view["imported_at"])
    if not target.cutoff-timedelta(minutes=10) <= minimum <= maximum <= imported <= target.cutoff:
        raise IntegrityError("event/player source capture and import must finish in the ten minutes before T90")
    if utc(view["history_source_observed_max_at"]) > target.history_freeze:
        raise IntegrityError("retained statistical inputs were observed after the midnight history freeze")


def _check_pilot_history(pack, view):
    if (view["history_rows"] != PILOT_HISTORY_ROWS
            or pack["history_provenance"]["normalized_panel_sha256"] != PILOT_PANEL_SHA256):
        raise IntegrityError("R1 pilot requires the exact full frozen 26,645-row history cohort")
    if (view["event"]["event_version"] != PILOT_EVENT_VERSION
            or view["selection_sha256"] != PILOT_SELECTION_SHA256):
        raise IntegrityError("R1 pilot event version or frozen selected cohort changed; declare a new cycle")


def validate_input_binding(bundle, pack, *, input_record_id):
    """Recover exact input identity/timing without generating or grading a model."""
    validate_forecast(bundle)
    if bundle["schema_version"] != FORECAST_SCHEMA_V2 or bundle["model_version"] != MODEL_VERSION:
        raise IntegrityError("captured inputs require the separately versioned R1 producer")
    view = _view(pack)
    _check_pilot_history(pack, view)
    target, candidate = _target(view, bundle["player_id"])
    _check_capture_window(view, target)
    expected = {"event_id": target.event_id, "event_starts_at": stamp(target.event_start),
                "team_id": candidate["team_id"], "opponent_id": candidate["opponent_id"],
                "player_label": candidate["player_label"]}
    if any(bundle[key] != value for key, value in expected.items()):
        raise IntegrityError("forecast identity differs from normalized current source selection")
    metadata = bundle["prospective"]
    details = {"producer_version": PRODUCER_VERSION, "event_version": view["event"]["event_version"],
               "selection_sha256": view["selection_sha256"], "source_pack_sha256": view["pack_sha256"],
               "source_pack_record_id": input_record_id,
               **{key: view[key] for key in ("source_observed_min_at", "source_observed_max_at",
                    "imported_at", "history_rows", "history_latest_event_at")},
               "base_model_version": BASE_MODEL_VERSION, "base_model_code_sha256": BASE_CODE_SHA256}
    if any(metadata[key] != value for key, value in details.items()):
        raise IntegrityError("prospective metadata differs from the referenced source package")
    history = _eligible(_history(pack), target)
    if len(history) != view["history_rows"] or not history:
        raise IntegrityError("declared full history contains ineligible or missing rows")
    if (bundle["input_sha256"] != _input_hash(history, target)
            or bundle["trained_through"] != stamp(max(row.outcome_available_at for row in history))):
        raise IntegrityError("forecast feature digest/training bound differs from retained full history")
    return view


def generate(pack, player_id, *, input_record_id, model_commit):
    """Generate after T90 with actual clocks; no caller-supplied issuance time."""
    started = _now()
    view = _view(pack)
    _check_pilot_history(pack, view)
    target, candidate = _target(view, player_id)
    if not target.cutoff <= started <= target.cutoff+timedelta(minutes=5):
        raise IntegrityError("generation is outside the T90 to T90+5 issuance window")
    _check_capture_window(view, target)
    if _code_hash("baseline.py") != BASE_CODE_SHA256:
        raise IntegrityError("the frozen underlying R0 implementation changed")
    history = _eligible(_history(pack), target)
    if len(history) != view["history_rows"]:
        raise IntegrityError("the full declared history cannot be silently truncated")
    reference = forecast_reference(history, target)
    categories = []
    for code in MARKETS:
        pmf = _wire_pmf(reference.marginal(code))
        categories.append({"code": code, "units": UNITS[code], "pmf": pmf,
                           "mean": decimal_text(math.fsum(atom["value"]*number(atom["probability"]) for atom in pmf)),
                           "interval80": [quantile(pmf, 0.1), quantile(pmf, 0.9)]})
    completed = _now()
    if completed < started or completed-started > timedelta(seconds=120) or completed > target.cutoff+timedelta(minutes=5):
        raise IntegrityError("generation exceeded its actual-clock latency/window budget")
    reference = replace(reference, issued_at=completed)
    bundle = {"schema_version": FORECAST_SCHEMA_V2, "id_namespace": "espn", "league": "NBA",
              "period": "full_game", "extra_time_policy": "includes_overtime",
              "event_id": target.event_id, "player_id": player_id,
              "player_label": candidate["player_label"], "team_id": candidate["team_id"],
              "opponent_id": candidate["opponent_id"], "event_starts_at": stamp(target.event_start),
              "model_version": MODEL_VERSION, "model_commit": model_commit,
              "model_code_sha256": _code_hash(), "input_sha256": reference.input_sha256,
              "trained_through": stamp(reference.trained_through), "cutoff_at": stamp(target.cutoff),
              "history_freeze": stamp(target.history_freeze), "issued_at": stamp(completed),
              "conditioning": "CONDITIONAL_ON_APPEARANCE", "evidence_lane": "REAL_TIME_CAPTURED",
              "availability_basis": "OBSERVED_INPUT_CAPTURE", "input_capture_ids": [input_record_id],
              "joint_method": "COMPLETE_LINE_EMPIRICAL", "joint_sha256": digest([row.to_record() for row in reference.support]),
              "tail_policy": "FINITE_EMPIRICAL_SUPPORT_NO_SMOOTHING", "categories": categories,
              "qualification": "UNAVAILABLE", "prospective": {
                  "producer_version": PRODUCER_VERSION, "event_version": view["event"]["event_version"],
                  "selection_sha256": view["selection_sha256"], "source_pack_sha256": view["pack_sha256"],
                  "source_pack_record_id": input_record_id, "generation_started_at": stamp(started),
                  "generation_completed_at": stamp(completed),
                  **{key: view[key] for key in ("source_observed_min_at", "source_observed_max_at",
                     "imported_at", "history_rows", "history_latest_event_at")},
                  "base_model_version": BASE_MODEL_VERSION, "base_model_code_sha256": BASE_CODE_SHA256}}
    bundle["forecast_id"] = digest(bundle)
    validate_input_binding(bundle, pack, input_record_id=input_record_id)
    return bundle, reference


def verify_prospective(bundle, reference, pack, *, input_record_id):
    """Bind all marginals and complete-line support to the current-clock producer."""
    validate_input_binding(bundle, pack, input_record_id=input_record_id)
    if not isinstance(reference, JointForecast):
        raise IntegrityError("a coherent actual generator reference is required")
    expected = {"event_id": reference.target.event_id, "player_id": reference.target.player_id,
                "id_namespace": reference.target.id_namespace,
                "event_starts_at": stamp(reference.target.event_start),
                "trained_through": stamp(reference.trained_through),
                "cutoff_at": stamp(reference.target.cutoff),
                "history_freeze": stamp(reference.target.history_freeze),
                "issued_at": stamp(reference.issued_at), "input_sha256": reference.input_sha256,
                "joint_sha256": digest([row.to_record() for row in reference.support]),
                "model_code_sha256": _code_hash()}
    if any(bundle[key] != value for key, value in expected.items()) or any(
            category["pmf"] != _wire_pmf(reference.marginal(category["code"])) for category in bundle["categories"]):
        raise IntegrityError("captured forecast differs from its coherent producer")
    return {"schema_version": "nba-pregame-r1-attestation-v1",
            **{key: bundle[key] for key in ("forecast_id", "joint_sha256", "input_sha256",
                "model_version", "model_commit", "model_code_sha256")},
            "categories_sha256": digest(bundle["categories"]), "verified_at": stamp(_now()),
            "source_pack_sha256": bundle["prospective"]["source_pack_sha256"],
            "source_pack_record_id": input_record_id,
            "scope": "EXACT_CAPTURED_REFERENCE_COMPARISON_NOT_QUALIFICATION"}


def require_committed_model(root, commit):
    """The saved model commit must contain the code actually executed by the CLI."""
    from .forecast_contract import COMMIT
    if not COMMIT.fullmatch(commit):
        raise IntegrityError("a full model commit is required")
    for name in MODEL_FILES:
        committed = subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=root, stderr=subprocess.PIPE)
        if committed != (Path(root)/name).read_bytes():
            raise IntegrityError(f"uncommitted/different model source: {name}")


def issue_cohort(store, input_ref, *, model_commit):
    """Recover completed subjects and append only missing subjects while timely.

    A crash can leave a partial cohort. Original records remain authoritative;
    retries never regenerate them or pretend a partial cohort is complete.
    """
    pack = store.read(input_ref)["data"]["source_pack"]
    view = _view(pack)
    existing = {}
    for payload in store.scan()["forecasts"].values():
        bundle = payload["data"].get("bundle", {})
        if (bundle.get("model_commit") == model_commit and bundle.get("model_version") == MODEL_VERSION
                and bundle.get("prospective", {}).get("source_pack_record_id") == input_ref.record_id):
            player = bundle["player_id"]
            if player in existing:
                raise IntegrityError("multiple initial forecasts exist for one selected subject")
            from .ledger import LedgerRef
            existing[player] = LedgerRef("forecasts", payload["record_id"], digest(payload))
    refs = []
    for candidate in view["candidates"]:
        player = candidate["player_id"]
        if player in existing:
            refs.append(existing[player])
            continue
        bundle, reference = generate(pack, player, input_record_id=input_ref.record_id, model_commit=model_commit)
        refs.append(store.issue_prospective(bundle, reference=reference, input_ref=input_ref))
    return refs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("persist", "status"):
        p = sub.add_parser(name)
        p.add_argument("--pack", type=Path, required=True)
    p = sub.add_parser("issue")
    p.add_argument("--input-record-id", required=True)
    p.add_argument("--model-commit", required=True)
    args = parser.parse_args()
    from .ledger import Ledger, LedgerRef
    from .pregame_sources import load_pack
    store = Ledger()
    try:
        if args.command in {"persist", "status"}:
            pack = load_pack(args.pack)
            result = preparation_status(pack)
            if args.command == "persist":
                ref = store.record_research_inputs(pack)
                result["input_reference"] = ref.to_record()
                result["persistence_status"] = "LOCAL_RECEIPT_ONLY_REQUIRES_COMMIT_PUSH_READBACK"
        else:
            path = store._path("research_inputs", args.input_record_id)
            from .integrity import read_receipt
            payload = read_receipt(path, max_bytes=4*1024*1024)
            input_ref = LedgerRef("research_inputs", args.input_record_id, digest(payload))
            require_committed_model(store.root, args.model_commit)
            refs = issue_cohort(store, input_ref, model_commit=args.model_commit)
            result = {"schema_version": "nba-pregame-issuance-report-v1",
                      "forecast_references": [ref.to_record() for ref in refs],
                      "selected_forecasts_retained": len(refs), "qualification": "UNAVAILABLE",
                      "persistence_status": "LOCAL_RECEIPT_ONLY_REQUIRES_COMMIT_PUSH_READBACK",
                      "financial_settlement": "NOT_EVALUATED"}
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

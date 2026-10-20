"""Versioned price-independent NBA research distributions; no qualification.

Only compact marginal PMFs leave the joint empirical forecaster. The public
record retains the joint construction/hash without publishing raw support rows.
All real-valued wire numbers are fixed-point strings for cross-language hashes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import math
from pathlib import Path
import re

from .baseline import MARKETS, JointForecast, HistoricalAppearance
from .integrity import IntegrityError, canonical, digest, stamp, utc

FORECAST_SCHEMA = "nba-research-forecast-v1"
FORECAST_SCHEMA_V2 = "nba-research-forecast-v2"
EVENT_SCHEMA = "nba-research-event-v1"
UNITS = {"PTS": "points", "PRA": "stat_sum", "REB": "rebounds",
         "3PM": "made_three_point_field_goals", "AST": "assists", "RA": "stat_sum",
         "PR": "stat_sum", "PA": "stat_sum", "TOV": "turnovers", "TD": "indicator_0_or_1",
         "DD": "indicator_0_or_1", "BLK": "blocks", "STL": "steals", "BLK+STL": "stat_sum"}
SHA = re.compile(r"[a-f0-9]{64}")
COMMIT = re.compile(r"[a-f0-9]{40}")
DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
FIELDS = {"schema_version", "forecast_id", "id_namespace", "league", "event_id", "player_id", "period", "extra_time_policy",
          "player_label", "team_id", "opponent_id", "event_starts_at", "model_version",
          "model_commit", "model_code_sha256", "input_sha256", "trained_through", "cutoff_at",
          "history_freeze", "issued_at", "conditioning", "evidence_lane", "availability_basis",
          "input_capture_ids", "joint_method", "joint_sha256", "tail_policy", "categories", "qualification"}


PROSPECTIVE_FIELDS = {"producer_version", "event_version", "selection_sha256",
                      "source_pack_sha256", "source_pack_record_id", "generation_started_at",
                      "generation_completed_at", "source_observed_min_at", "source_observed_max_at",
                      "imported_at", "base_model_version", "base_model_code_sha256",
                      "history_rows", "history_latest_event_at"}
FIELDS_V2 = FIELDS | {"prospective"}


def _validate_prospective(bundle: dict, clocks: dict) -> None:
    """Strict wire timing for the separately admitted pregame producer.

    Receipt recovery additionally verifies source bytes/references and producer
    attestation; these supplied clocks alone cannot establish genuine issuance.
    """
    details = bundle["prospective"]
    if (type(details) is not dict or set(details) != PROSPECTIVE_FIELDS
            or bundle["evidence_lane"] != "REAL_TIME_CAPTURED"
            or bundle["model_version"] != "nba_joint_empirical_pregame_r1_v1"
            or details["producer_version"] != "nba-pregame-r1-v1"
            or details["base_model_version"] != "nba_joint_empirical_r0_v1"):
        raise IntegrityError("Unsupported prospective producer contract")
    for name in ("event_version", "selection_sha256", "source_pack_sha256",
                 "source_pack_record_id", "base_model_code_sha256"):
        if type(details[name]) is not str or not SHA.fullmatch(details[name]):
            raise IntegrityError(f"Invalid prospective {name}")
    if (type(details["history_rows"]) is not int
            or not 1 <= details["history_rows"] <= 100000
            or bundle["input_capture_ids"] != [details["source_pack_record_id"]]):
        raise IntegrityError("Invalid prospective history budget or source-pack reference")
    times = {name: _time(details[name]) for name in
             ("generation_started_at", "generation_completed_at", "source_observed_min_at",
              "source_observed_max_at", "imported_at", "history_latest_event_at")}
    cutoff = clocks["cutoff_at"]
    if not (cutoff - timedelta(minutes=10) <= times["source_observed_min_at"]
            <= times["source_observed_max_at"] <= times["imported_at"] <= cutoff
            <= times["generation_started_at"] <= times["generation_completed_at"]
            == clocks["issued_at"] <= cutoff + timedelta(minutes=5)):
        raise IntegrityError("Prospective capture, import or issuance window violated")
    if (times["generation_completed_at"] - times["generation_started_at"] > timedelta(seconds=120)
            or times["history_latest_event_at"] >= clocks["history_freeze"]):
        raise IntegrityError("Prospective generation latency or history freeze violated")


def decimal_text(value) -> str:
    """Finite nonnegative fixed-point text, never a floating JSON identity."""
    if isinstance(value, bool):
        raise IntegrityError("Boolean is not a research number")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise IntegrityError("Invalid research number") from None
    if not number.is_finite() or number < 0:
        raise IntegrityError("Research number must be finite and nonnegative")
    if number.is_zero():
        return "0"
    result = format(number, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def number(value, *, maximum=None) -> float:
    if type(value) is not str or len(value) > 128 or not DECIMAL.fullmatch(value):
        raise IntegrityError("Research numbers require nonnegative fixed-point strings")
    result = float(value)
    if not math.isfinite(result) or (maximum is not None and result > maximum):
        raise IntegrityError("Research number exceeds its range")
    return result


def _text(value, name):
    if type(value) is not str or not value or value.strip() != value or len(value) > 200:
        raise IntegrityError(f"Invalid {name}")


def _time(value):
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", value):
        raise IntegrityError("Research clocks require full microsecond UTC timestamps")
    return utc(value)


def quantile(pmf: list[dict], q: float) -> int:
    cumulative = 0.0
    for item in pmf:
        cumulative += number(item["probability"], maximum=1)
        if cumulative >= q:
            return item["value"]
    return pmf[-1]["value"]


def validate_forecast(bundle: dict, *, now=None) -> dict:
    if type(bundle) is not dict:
        raise IntegrityError("Unsupported research forecast schema")
    version = bundle.get("schema_version")
    if not ((version == FORECAST_SCHEMA and set(bundle) == FIELDS)
            or (version == FORECAST_SCHEMA_V2 and set(bundle) == FIELDS_V2)):
        raise IntegrityError("Unsupported research forecast schema")
    for field in ("event_id", "player_id", "player_label", "team_id", "opponent_id", "model_version"):
        _text(bundle[field], field)
    if (bundle["league"] != "NBA" or bundle["id_namespace"] != "espn"
            or bundle["team_id"] == bundle["opponent_id"]
            or bundle["conditioning"] != "CONDITIONAL_ON_APPEARANCE"
            or bundle["period"] != "full_game" or bundle["extra_time_policy"] != "includes_overtime"
            or bundle["qualification"] != "UNAVAILABLE"
            or bundle["joint_method"] != "COMPLETE_LINE_EMPIRICAL"
            or bundle["tail_policy"] != "FINITE_EMPIRICAL_SUPPORT_NO_SMOOTHING"):
        raise IntegrityError("Unsupported forecast meaning or qualification")
    for field in ("forecast_id", "model_code_sha256", "input_sha256", "joint_sha256"):
        if type(bundle[field]) is not str or not SHA.fullmatch(bundle[field]):
            raise IntegrityError(f"Invalid {field}")
    if type(bundle["model_commit"]) is not str or not COMMIT.fullmatch(bundle["model_commit"]):
        raise IntegrityError("Full model commit SHA required")
    clocks = {key: _time(bundle[key]) for key in ("event_starts_at", "trained_through", "cutoff_at", "history_freeze", "issued_at")}
    if clocks["issued_at"] > utc(now if now is not None else datetime.now(timezone.utc)):
        raise IntegrityError("Forecast issue clock is in the future")
    cutoff = clocks["event_starts_at"] - timedelta(minutes=90)
    freeze = cutoff.replace(hour=0, minute=0, second=0, microsecond=0)
    if (clocks["cutoff_at"] != cutoff or clocks["history_freeze"] != freeze
            or clocks["trained_through"] > freeze):
        raise IntegrityError("Forecast training or input cutoff violates T90 daily freeze")
    ids = bundle["input_capture_ids"]
    if type(ids) is not list or any(type(x) is not str or not SHA.fullmatch(x) for x in ids) or len(set(ids)) != len(ids):
        raise IntegrityError("Invalid input capture references")
    if bundle["evidence_lane"] == "RECONSTRUCTED_RESEARCH":
        if bundle["availability_basis"] != "RECONSTRUCTED_BOUND" or ids or clocks["issued_at"] < clocks["event_starts_at"]:
            raise IntegrityError("Historical reconstruction cannot imply pregame issuance")
    elif bundle["evidence_lane"] == "REAL_TIME_CAPTURED":
        if (bundle["availability_basis"] != "OBSERVED_INPUT_CAPTURE" or not ids
                or not cutoff <= clocks["issued_at"] < clocks["event_starts_at"]):
            raise IntegrityError("Real-time forecasts require observed inputs and pregame issuance")
        # The ledger verifies that these captured input receipts really exist.
    else:
        raise IntegrityError("Unsupported forecast evidence lane")
    if version == FORECAST_SCHEMA_V2:
        _validate_prospective(bundle, clocks)
    categories = bundle["categories"]
    if type(categories) is not list or len(categories) != len(MARKETS):
        raise IntegrityError("Every forecast must contain all 13 categories plus PA")
    by_code = {}
    for category in categories:
        if type(category) is not dict or set(category) != {"code", "units", "pmf", "mean", "interval80"}:
            raise IntegrityError("Invalid category distribution")
        code = category["code"]
        if code not in UNITS or code in by_code or category["units"] != UNITS[code]:
            raise IntegrityError("Duplicate or unknown category/units")
        pmf = category["pmf"]
        if type(pmf) is not list or not 1 <= len(pmf) <= 1025:
            raise IntegrityError("PMF support exceeds its budget")
        previous = -1
        probabilities = []
        for item in pmf:
            if (type(item) is not dict or set(item) != {"value", "probability"}
                    or type(item["value"]) is not int or not previous < item["value"] <= 1024
                    or (code in {"DD", "TD"} and item["value"] not in {0, 1})):
                raise IntegrityError("PMF values must be unique sorted nonnegative integers")
            previous = item["value"]
            p = number(item["probability"], maximum=1)
            if p <= 0:
                raise IntegrityError("PMF support must have positive mass")
            probabilities.append(p)
        if not math.isclose(math.fsum(probabilities), 1, rel_tol=0, abs_tol=1e-12):
            raise IntegrityError("PMF mass must sum to one; never renormalized")
        mean = number(category["mean"])
        calculated = math.fsum(item["value"] * p for item, p in zip(pmf, probabilities))
        if not math.isclose(mean, calculated, rel_tol=0, abs_tol=1e-10):
            raise IntegrityError("Forecast mean conflicts with its PMF")
        interval = category["interval80"]
        if (type(interval) is not list or len(interval) != 2 or any(type(x) is not int for x in interval)
                or interval != [quantile(pmf, 0.1), quantile(pmf, 0.9)]):
            raise IntegrityError("Forecast interval conflicts with its PMF")
        by_code[code] = category
    if set(by_code) != set(MARKETS):
        raise IntegrityError("Missing mandatory NBA forecast category")
    means = {code: number(c["mean"]) for code, c in by_code.items()}
    for target, pieces in {"PRA": ["PTS", "REB", "AST"], "PR": ["PTS", "REB"], "RA": ["REB", "AST"], "PA": ["PTS", "AST"], "BLK+STL": ["BLK", "STL"]}.items():
        if not math.isclose(means[target], math.fsum(means[p] for p in pieces), rel_tol=0, abs_tol=1e-10):
            raise IntegrityError("Derived forecast means violate same-outcome identities")
    if means["TD"] > means["DD"] + 1e-12 or means["PTS"] + 1e-10 < 3 * means["3PM"]:
        raise IntegrityError("Forecast violates scoring/DD/TD constraints")
    # Necessary marginal constraints; these alone do not prove a joint law.
    tails = sorted((math.fsum(number(atom["probability"]) for atom in by_code[code]["pmf"]
                              if atom["value"] >= 10)
                    for code in ("PTS", "REB", "AST", "STL", "BLK")), reverse=True)
    for code, k in (("DD", 2), ("TD", 3)):
        lower = max(0.0, *( (math.fsum(tails[:m])-(k-1))/(m-k+1) for m in range(k, 6)))
        upper = min(1.0, *(math.fsum(tails[j:])/(k-j) for j in range(k)))
        if means[code] < lower-1e-12 or means[code] > upper+1e-12:
            raise IntegrityError("DD/TD probability violates component threshold bounds")
    if bundle["forecast_id"] != digest({k: v for k, v in bundle.items() if k != "forecast_id"}):
        raise IntegrityError("Forecast identity checksum mismatch")
    if len(canonical(bundle)) > 128 * 1024:
        raise IntegrityError("Forecast exceeds byte budget")
    return bundle


def verify_reference(bundle: dict, reference: JointForecast) -> dict:
    """Verify issuer input against the actual coherent in-memory measure.

    An immutable attestation records that this check ran; it is not a signature,
    upstream authenticity proof, or a replacement for statistical evaluation.
    Raw empirical support is deliberately absent from the retained attestation.
    This producer remains reconstructed-only; future inputs need a separately
    admitted observed-input producer rather than a lane toggle.
    """
    validate_forecast(bundle, now=datetime.now(timezone.utc))
    if not isinstance(reference, JointForecast) or bundle["evidence_lane"] != "RECONSTRUCTED_RESEARCH":
        raise IntegrityError("Current R0 issuer supports reconstructed reference objects only")
    expected = {"event_id": reference.target.event_id, "player_id": reference.target.player_id,
                "event_starts_at": stamp(reference.target.event_start),
                "id_namespace": reference.target.id_namespace,
                "input_sha256": reference.input_sha256, "trained_through": stamp(reference.trained_through),
                "cutoff_at": stamp(reference.target.cutoff), "history_freeze": stamp(reference.target.history_freeze),
                "issued_at": stamp(reference.issued_at),
                "model_version": "nba_joint_empirical_r0_v1",
                "model_code_sha256": hashlib.sha256(Path(__file__).with_name("baseline.py").read_bytes()).hexdigest(),
                "joint_sha256": digest([atom.to_record() for atom in reference.support])}
    if any(bundle[field] != value for field, value in expected.items()):
        raise IntegrityError("Forecast metadata differs from coherent producer input")
    for category in bundle["categories"]:
        pmf = _wire_pmf(reference.marginal(category["code"]))
        if category["pmf"] != pmf:
            raise IntegrityError("Forecast marginal differs from coherent producer input")
    return {"schema_version": "nba-r0-joint-attestation-v1", "forecast_id": bundle["forecast_id"],
            "joint_sha256": bundle["joint_sha256"], "input_sha256": bundle["input_sha256"],
            "model_version": bundle["model_version"], "model_commit": bundle["model_commit"],
            "model_code_sha256": bundle["model_code_sha256"],
            "categories_sha256": digest(bundle["categories"]),
            "verified_at": stamp(datetime.now(timezone.utc)),
            "scope": "EXACT_REFERENCE_COMPARISON_NOT_STATISTICAL_QUALIFICATION"}


def _wire_pmf(marginal: dict[int, float]) -> list[dict]:
    # One-atom empirical distributions are mathematically certain. Floating
    # summation can produce1+epsilon; serialize that degenerate law as exactly1.
    # General supplied PMFs are never normalized or repaired by validation.
    if len(marginal) == 1:
        value, probability = next(iter(marginal.items()))
        if not math.isclose(probability, 1, rel_tol=0, abs_tol=1e-12):
            raise IntegrityError("Invalid one-atom reference probability")
        return [{"value": value, "probability": "1"}]
    return [{"value": value, "probability": decimal_text(p)} for value, p in marginal.items()]


def from_reference(forecast: JointForecast, observed: HistoricalAppearance, *, model_commit: str,
                   player_label: str | None = None) -> dict:
    """Export a freshly issued historical reference, not a replayed issue clock.

    ``observed`` supplies retrospective participant/team identity only; the
    forecaster has already excluded its production from the input pool.
    """
    if (forecast.target.event_id, forecast.target.player_id, forecast.target.event_start) != (observed.event_id, observed.player_id, observed.event_start):
        raise IntegrityError("Forecast target differs from retrospective identity row")
    categories = []
    for code in MARKETS:
        marginal = forecast.marginal(code)
        pmf = _wire_pmf(marginal)
        categories.append({"code": code, "units": UNITS[code], "pmf": pmf,
                           "mean": decimal_text(math.fsum(atom["value"] * number(atom["probability"]) for atom in pmf)),
                           "interval80": [quantile(pmf, 0.1), quantile(pmf, 0.9)]})
    bundle = {"schema_version": FORECAST_SCHEMA, "id_namespace": observed.id_namespace, "league": "NBA",
              "period": "full_game", "extra_time_policy": "includes_overtime",
              "event_id": observed.event_id, "player_id": observed.player_id,
              "player_label": player_label or f"ESPN player {observed.player_id}",
              "team_id": observed.team_id, "opponent_id": observed.opponent_id,
              "event_starts_at": stamp(observed.event_start), "model_version": "nba_joint_empirical_r0_v1",
              "model_commit": model_commit,
              "model_code_sha256": hashlib.sha256(Path(__file__).with_name("baseline.py").read_bytes()).hexdigest(),
              "input_sha256": forecast.input_sha256, "trained_through": stamp(forecast.trained_through),
              "cutoff_at": stamp(forecast.target.cutoff), "history_freeze": stamp(forecast.target.history_freeze),
              "issued_at": stamp(forecast.issued_at), "conditioning": "CONDITIONAL_ON_APPEARANCE",
              "evidence_lane": "RECONSTRUCTED_RESEARCH", "availability_basis": "RECONSTRUCTED_BOUND",
              "input_capture_ids": [], "joint_method": "COMPLETE_LINE_EMPIRICAL",
              "joint_sha256": digest([item.to_record() for item in forecast.support]),
              "tail_policy": "FINITE_EMPIRICAL_SUPPORT_NO_SMOOTHING", "categories": categories,
              "qualification": "UNAVAILABLE"}
    bundle["forecast_id"] = digest(bundle)
    return validate_forecast(bundle, now=datetime.now(timezone.utc))


def validate_event(event: dict) -> dict:
    fields = {"schema_version", "id_namespace", "league", "event_id", "starts_at", "status", "team_ids", "label", "schedule_basis"}
    if (type(event) is not dict or set(event) != fields or event["schema_version"] != EVENT_SCHEMA
            or event["id_namespace"] != "espn" or event["league"] != "NBA"):
        raise IntegrityError("Invalid research event schema")
    for field in ("event_id", "label"):
        _text(event[field], field)
    _time(event["starts_at"])
    teams = event["team_ids"]
    if type(teams) is not list or len(teams) != 2 or teams[0] == teams[1]:
        raise IntegrityError("Event requires two distinct teams")
    for team in teams:
        _text(team, "team_id")
    if (event["status"], event["schedule_basis"]) not in {("FINAL", "RETROSPECTIVE_ARCHIVE"), ("SCHEDULED", "OBSERVED_CAPTURE")}:
        raise IntegrityError("Event status and schedule provenance disagree")
    return event

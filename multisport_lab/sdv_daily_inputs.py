"""Bounded SportsDataverse daily CSV inputs, distinct from fresh ESPN protocols.

Publisher asset updates, upstream observations and our retrievals have different
meanings. This module performs no HTTP requests, model fitting or issuance.
"""
from __future__ import annotations

from copy import deepcopy
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import re

from .integrity import IntegrityError, digest, stamp, utc

PROTOCOL_ID = "NBA-SDV-DAILY-001"
INPUT_SCHEMA = "nba-sdv-daily-input-v1"
POLICY_SCHEMA = "nba-sdv-daily-policy-v1"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_SOURCE_ROWS = 5000
SELECTION_RULE = "two_lowest_numeric_active_ids_per_current_event_team_v1"
MODES = {"DEVELOPMENT_ONLY", "PROSPECTIVE_RESEARCH"}
MISSING_INFORMATION = ["UPSTREAM_OBSERVATION_CLOCK", "INJURIES", "STARTING_LINEUP",
                       "CONFIRMED_PARTICIPATION"]
_POLICY = {
    "schema_version": POLICY_SCHEMA, "protocol_id": PROTOCOL_ID,
    "schedule_max_age_seconds": 129600, "roster_max_age_seconds": 129600,
    "retrieval_lookback_seconds": 3600, "issuance_open_minutes_before_start": 90,
    "issuance_window_seconds": 900, "maximum_original_latency_seconds": 300,
    "participation": "CONDITIONAL_ON_APPEARANCE",
    "upstream_observation": "UNKNOWN_UNLESS_SUPPLIED",
    "rationale": ("Initial research operating policy: one documented daily publication "
                  "interval (24 hours) plus 12 hours of publication-delay tolerance. "
                  "Retrieve and normalize within one hour before T90; allow fifteen "
                  "minutes after T90 for bounded generation and durable recovery. "
                  "These are operational limits, not scientifically optimal thresholds "
                  "or the original fresh-input T90 protocol."),
}
SOURCE_FIELDS = {"role", "publisher", "release_tag", "asset_name", "asset_url", "asset_id",
                 "asset_bytes", "asset_sha256", "publisher_updated_at", "upstream_observed_at",
                 "upstream_observation_status", "retrieval_started_at", "retrieved_at",
                 "metadata_sha256", "metadata_bytes"}
EVENT_FIELDS = {"event_id", "id_namespace", "league", "season_ending_year", "season_type",
                "home_team_id", "home_team_name", "away_team_id", "away_team_name",
                "event_starts_at", "status", "event_snapshot_id", "provider_event_revision"}
INPUT_FIELDS = {"schema_version", "protocol_id", "mode", "policy", "event", "candidates",
                "sources", "selection_rule", "normalized_at", "missing_information",
                "qualification", "input_id"}


def _now():
    return datetime.now(timezone.utc)


def _require(ok, message):
    if not ok:
        raise IntegrityError(message)


def _exact(value, fields, label):
    _require(type(value) is dict and set(value) == set(fields), "Invalid daily " + label)


def _text(value, label):
    _require(type(value) is str and 0 < len(value) <= 256 and value.strip() == value,
             "Invalid daily " + label)
    return value


def _id(value, label):
    _require(type(value) is str and re.fullmatch(r"[1-9][0-9]*", value),
             "Invalid daily " + label)
    return value


def _sha(value, label):
    _require(type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value),
             "Invalid daily " + label)
    return value


def _clock(value, label):
    _require(type(value) is str and re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z", value),
        "Daily " + label + " requires precise UTC")
    try:
        return utc(value)
    except (ValueError, TypeError) as exc:
        raise IntegrityError("Invalid daily " + label) from exc


def _source_time(value, label):
    _text(value, label)
    try:
        return utc(value)
    except (ValueError, TypeError) as exc:
        raise IntegrityError("Invalid source " + label) from exc


def _seal(body, key):
    return {**body, key: digest(body)}


def _check_seal(body, key):
    _require(body.get(key) == digest({k: v for k, v in body.items() if k != key}),
             "Daily " + key + " checksum mismatch")


def make_policy():
    return _seal(deepcopy(_POLICY), "policy_id")


def validate_policy(policy):
    _exact(policy, {*_POLICY, "policy_id"}, "freshness policy")
    _require(all(type(policy[key]) is type(value) and policy[key] == value
                 for key, value in _POLICY.items()),
             "Daily policy values changed; a new reviewed version is required")
    _check_seal(policy, "policy_id")
    return policy


def validate_source_metadata(source, *, role=None, raw=None, normalized_at=None):
    """Check exact public asset identity and clocks without inventing upstream age."""
    _exact(source, SOURCE_FIELDS, "asset metadata")
    actual_role = source["role"]
    _require(actual_role in {"schedule", "roster"} and (role is None or actual_role == role),
             "Daily source role conflict")
    tag = "espn_nba_schedules" if actual_role == "schedule" else "espn_nba_rosters"
    prefix = "nba_schedule_" if actual_role == "schedule" else "rosters_"
    name = source["asset_name"]
    _require(type(name) is str and re.fullmatch(prefix + r"20[0-9]{2}\.csv", name),
             "Unsupported daily CSV asset")
    _require(source["publisher"] == "SportsDataverse" and source["release_tag"] == tag
             and source["asset_url"] == ("https://github.com/sportsdataverse/"
                 "sportsdataverse-data/releases/download/" + tag + "/" + name),
             "Daily asset publisher/URL/release conflict")
    _require(type(source["asset_id"]) is int and 0 < source["asset_id"] < 2**63,
             "Daily GitHub asset ID is absent")
    for field in ("asset_bytes", "metadata_bytes"):
        _require(type(source[field]) is int and 0 < source[field] <= MAX_SOURCE_BYTES,
                 "Daily source exceeds unchanged byte limit")
    for field in ("asset_sha256", "metadata_sha256"):
        _sha(source[field], field)
    updated = _clock(source["publisher_updated_at"], "publisher update")
    started = _clock(source["retrieval_started_at"], "retrieval start")
    retrieved = _clock(source["retrieved_at"], "retrieval completion")
    _require(updated <= started <= retrieved, "Daily publisher/retrieval clocks conflict")
    if normalized_at is not None:
        _require(retrieved <= utc(normalized_at), "Daily asset retrieved after normalization")
    # This version reads GitHub release-asset metadata, which has no mapped
    # upstream-observation field. An uploaded_at/updated_at value cannot fill it.
    _require(source["upstream_observation_status"] == "UNKNOWN"
             and source["upstream_observed_at"] is None,
             "Daily v1 upstream observation must remain UNKNOWN/null")
    if raw is not None:
        _require(type(raw) is bytes and len(raw) == source["asset_bytes"]
                 and hashlib.sha256(raw).hexdigest() == source["asset_sha256"],
                 "Daily metadata does not bind exact source bytes")
    return source


def _table(raw, fields, label):
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_SOURCE_BYTES,
             "Daily " + label + " source exceeds byte limit")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        names = reader.fieldnames
        _require(names is not None and len(names) == len(set(names)) and set(fields) <= set(names)
                 and all(type(name) is str and name for name in names),
                 "Missing/duplicate daily " + label + " columns")
        rows = []
        for row in reader:
            _require(len(rows) < MAX_SOURCE_ROWS, "Daily source row ceiling exceeded; no truncation")
            _require(None not in row and all(type(value) is str for value in row.values()),
                     "Malformed daily CSV row")
            rows.append(row)
    except (UnicodeError, csv.Error) as exc:
        raise IntegrityError("Invalid daily " + label + " CSV") from exc
    _require(bool(rows), "Empty daily " + label + " CSV")
    return rows


def _candidates(value, event):
    _require(type(value) is list and len(value) == 4, "Daily cycle requires four fixed subjects")
    seen = set()
    for candidate in value:
        _exact(candidate, {"player_id", "player_label", "team_id", "opponent_id"}, "candidate")
        pid = _id(candidate["player_id"], "player ID")
        _text(candidate["player_label"], "player label")
        team = _id(candidate["team_id"], "candidate team")
        opponent = _id(candidate["opponent_id"], "candidate opponent")
        _require({team, opponent} == {event["home_team_id"], event["away_team_id"]}
                 and team != opponent and pid not in seen, "Daily candidate identity conflict")
        seen.add(pid)
    _require(all(sum(c["team_id"] == team for c in value) == 2
                 for team in (event["home_team_id"], event["away_team_id"])),
             "Daily cohort must retain two subjects per event team")


def normalize_inputs(schedule_raw, roster_raw, schedule_metadata, roster_metadata, *,
                     event_id, expected_candidates, mode="DEVELOPMENT_ONLY", policy=None,
                     normalized_at=None):
    """Normalize two actual publisher files; never synthesize ESPN responses.

    Explicit development clocks support bounded synthetic tests. Prospective
    normalization always records the actual completion clock.
    """
    _require(mode in MODES, "Invalid daily input evidence lane")
    _require(normalized_at is None or mode == "DEVELOPMENT_ONLY",
             "Prospective normalization cannot accept a supplied completion clock")
    _id(event_id, "event ID")
    chosen_policy = make_policy() if policy is None else deepcopy(validate_policy(policy))
    schedule = _table(schedule_raw, {"id", "uid", "game_id", "season", "season_type", "date",
        "start_date", "game_date_time", "home_id", "home_display_name", "away_id",
        "away_display_name", "status_type_name", "status_type_state", "status_type_completed",
        "time_valid"}, "schedule")
    roster = _table(roster_raw, {"season", "athlete_id", "uid", "team_id", "team_display_name",
        "display_name", "status_type", "status_name", "status_id"}, "roster")
    seen = set()
    for row in schedule:
        value = _id(row["id"], "schedule event ID")
        _require(value not in seen and row["game_id"] == value
                 and row["uid"] == "s:40~l:46~e:" + value + "~c:" + value,
                 "Duplicate/conflicting daily event identity")
        seen.add(value)
    selected = [row for row in schedule if row["id"] == event_id]
    _require(len(selected) == 1, "Selected daily event is missing")
    row = selected[0]
    _require(re.fullmatch(r"20[0-9]{2}", row["season"]) is not None
             and row["season_type"] in {"1", "2", "3"}, "Invalid daily event season")
    season = int(row["season"])
    _require(all(item["season"] == row["season"] for item in schedule),
             "Daily schedule contains another season")
    home, away = _id(row["home_id"], "home team"), _id(row["away_id"], "away team")
    _require(home != away and row["status_type_name"] == "STATUS_SCHEDULED"
             and row["status_type_state"] == "pre" and row["status_type_completed"] == "false"
             and row["time_valid"] == "true", "Daily event is not scheduled with a valid start")
    starts = _source_time(row["date"], "scheduled start")
    _require(starts == _source_time(row["start_date"], "start_date")
             == _source_time(row["game_date_time"], "game_date_time"),
             "Daily scheduled start fields conflict")
    event = {"event_id": event_id, "id_namespace": "espn", "league": "NBA",
        "season_ending_year": season, "season_type": row["season_type"],
        "home_team_id": home, "home_team_name": _text(row["home_display_name"], "home name"),
        "away_team_id": away, "away_team_name": _text(row["away_display_name"], "away name"),
        "event_starts_at": stamp(starts), "status": "SCHEDULED", "provider_event_revision": None}
    event = _seal(event, "event_snapshot_id")
    _candidates(expected_candidates, event)
    seen, team_names = set(), {}
    for item in roster:
        pid, team = _id(item["athlete_id"], "roster player"), _id(item["team_id"], "roster team")
        _require(pid not in seen and item["uid"] == "s:40~l:46~a:" + pid,
                 "Duplicate/conflicting daily roster player identity")
        seen.add(pid)
        _require(item["season"] == str(season), "Daily roster season differs from event")
        _text(item["display_name"], "roster player name")
        team_name = _text(item["team_display_name"], "roster team name")
        _require(team not in team_names or team_names[team] == team_name,
                 "Daily roster team labels conflict")
        team_names[team] = team_name
        _text(item["status_type"], "roster status type")
        _text(item["status_name"], "roster status name")
        _text(item["status_id"], "roster status ID")
        if item["status_type"] == "active":
            _require(item["status_name"] == "Active" and item["status_id"] == "1",
                     "Conflicting active roster status")
    candidates = []
    for team, opponent, name in ((home, away, event["home_team_name"]),
                                 (away, home, event["away_team_name"])):
        _require(team_names.get(team) == name, "Roster and event team identities differ")
        eligible = sorted((item for item in roster if item["team_id"] == team
            and item["status_type"] == "active"), key=lambda item: int(item["athlete_id"]))[:2]
        _require(len(eligible) == 2, "Daily event team lacks two eligible roster subjects")
        candidates.extend({"player_id": item["athlete_id"], "player_label": item["display_name"],
            "team_id": team, "opponent_id": opponent} for item in eligible)
    _require(candidates == expected_candidates, "Fixed daily cohort changed; no replacement subjects")
    completed = utc(normalized_at) if normalized_at is not None else _now()
    _require(completed < starts, "Daily normalization is at or after game start")
    sources = []
    for role, raw, metadata, wanted_name in (
        ("schedule", schedule_raw, schedule_metadata, "nba_schedule_" + str(season) + ".csv"),
        ("roster", roster_raw, roster_metadata, "rosters_" + str(season) + ".csv")):
        validate_source_metadata(metadata, role=role, raw=raw, normalized_at=completed)
        _require(metadata["asset_name"] == wanted_name, "Daily source asset season differs")
        sources.append(deepcopy(metadata))
    missing = MISSING_INFORMATION if any(s["upstream_observation_status"] == "UNKNOWN" for s in sources) else MISSING_INFORMATION[1:]
    body = _seal({"schema_version": INPUT_SCHEMA, "protocol_id": PROTOCOL_ID, "mode": mode,
        "policy": chosen_policy, "event": event, "candidates": candidates, "sources": sources,
        "selection_rule": SELECTION_RULE, "normalized_at": stamp(completed),
        "missing_information": list(missing), "qualification": "UNAVAILABLE"}, "input_id")
    validate_input(body)
    freshness(body, at=completed)
    return body


def verify_input_sources(body, schedule_raw, roster_raw, schedule_metadata, roster_metadata):
    """Read-only replay of retained semantics, with no new capture/issuance claim.

    A prospective original's normalization clock cannot be supplied to the live
    producer.  Replay therefore uses the development-only normalizer and compares
    every semantic field before returning the untouched original.
    """
    validate_input(body)
    replay = normalize_inputs(schedule_raw, roster_raw, schedule_metadata, roster_metadata,
        event_id=body["event"]["event_id"], expected_candidates=body["candidates"],
        mode="DEVELOPMENT_ONLY", policy=body["policy"], normalized_at=body["normalized_at"])
    original_semantics = {key: value for key, value in body.items() if key not in {"mode", "input_id"}}
    replay_semantics = {key: value for key, value in replay.items() if key not in {"mode", "input_id"}}
    _require(original_semantics == replay_semantics,
             "Daily retained input semantics differ from exact source replay")
    return body


def validate_input(body):
    """Structural recovery validation; current age is checked separately at use."""
    _exact(body, INPUT_FIELDS, "normalized input")
    _require(body["schema_version"] == INPUT_SCHEMA and body["protocol_id"] == PROTOCOL_ID
             and body["mode"] in MODES and body["selection_rule"] == SELECTION_RULE
             and body["qualification"] == "UNAVAILABLE", "Unknown daily input contract")
    validate_policy(body["policy"])
    event = body["event"]
    _exact(event, EVENT_FIELDS, "event")
    for key in ("event_id", "home_team_id", "away_team_id"):
        _id(event[key], key)
    for key in ("home_team_name", "away_team_name"):
        _text(event[key], key)
    _require(event["id_namespace"] == "espn" and event["league"] == "NBA"
             and event["home_team_id"] != event["away_team_id"]
             and type(event["season_ending_year"]) is int and 2000 <= event["season_ending_year"] <= 2099
             and event["season_type"] in {"1", "2", "3"} and event["status"] == "SCHEDULED"
             and event["provider_event_revision"] is None, "Invalid daily event semantics")
    _check_seal(event, "event_snapshot_id")
    normalized = _clock(body["normalized_at"], "normalization completion")
    _require(normalized <= _now() and normalized < _clock(event["event_starts_at"], "game start"),
             "Daily normalization completion is future-dated or post-start")
    _candidates(body["candidates"], event)
    _require(type(body["sources"]) is list and len(body["sources"]) == 2
             and [source.get("role") for source in body["sources"] if type(source) is dict]
             == ["schedule", "roster"], "Daily exact source inventory is missing or duplicated")
    for source in body["sources"]:
        validate_source_metadata(source, normalized_at=normalized)
        wanted = ("nba_schedule_" if source["role"] == "schedule" else "rosters_") + str(event["season_ending_year"]) + ".csv"
        _require(source["asset_name"] == wanted, "Daily source and event seasons differ")
    missing = MISSING_INFORMATION if any(source["upstream_observation_status"] == "UNKNOWN" for source in body["sources"]) else MISSING_INFORMATION[1:]
    _require(body["missing_information"] == missing, "Daily missing information was hidden or invented")
    _check_seal(body, "input_id")
    return body


def freshness(body, *, at, require_retrieval_window=False):
    """Admission at a stated clock, separate from immutable input interpretation."""
    validate_input(body)
    _require(type(require_retrieval_window) is bool, "Invalid daily retrieval-window control")
    actual = utc(at)
    normalized = _clock(body["normalized_at"], "normalization completion")
    starts = _clock(body["event"]["event_starts_at"], "game start")
    policy = body["policy"]
    cutoff = starts - timedelta(minutes=policy["issuance_open_minutes_before_start"])
    _require(normalized <= actual < starts, "Daily input is future-dated or game has started")
    ages = {}
    for source in body["sources"]:
        updated = _clock(source["publisher_updated_at"], "publisher update")
        retrieved = _clock(source["retrieved_at"], "retrieval completion")
        _require(updated <= retrieved <= actual, "Future daily publisher/retrieval clock")
        age = (actual - updated).total_seconds()
        _require(age <= policy[source["role"] + "_max_age_seconds"],
                 "Daily " + source["role"] + " publisher asset is stale")
        upstream = source["upstream_observed_at"]
        ages[source["role"]] = {"publisher_age_seconds": age,
            "retrieval_age_seconds": (actual - retrieved).total_seconds(),
            "upstream_age_seconds": None if upstream is None else (actual - _clock(upstream, "upstream observation")).total_seconds(),
            "upstream_observation_status": source["upstream_observation_status"]}
    if require_retrieval_window:
        lower = cutoff - timedelta(seconds=policy["retrieval_lookback_seconds"])
        _require(cutoff <= actual <= cutoff + timedelta(seconds=policy["issuance_window_seconds"]),
                 "Daily issuance window is not open or has closed")
        _require(lower <= normalized <= cutoff, "Daily input normalization missed pre-cutoff window")
        for source in body["sources"]:
            _require(lower <= _clock(source["retrieval_started_at"], "retrieval start")
                     <= _clock(source["retrieved_at"], "retrieval completion") <= cutoff,
                     "Daily actual retrieval missed pre-cutoff window")
    return {"policy_id": policy["policy_id"], "cutoff_at": stamp(cutoff),
            "forecast_horizon_seconds": (starts - actual).total_seconds(), "sources": ages}

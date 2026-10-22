"""Bounded recurring NBA planning, with no collection or forecast issuance.

The unchanged daily-v1 normalizer is a source-interpretation codec only. Its
DEVELOPMENT_ONLY bodies never carry v1 activation or prospective authority.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import re

from .integrity import IntegrityError, canonical, digest, stamp, utc
from . import sdv_daily_inputs as inputs
from . import sdv_daily_cycle as first
from .sdv_daily_runner import source_metadata

PROTOCOL_ID = "NBA-SDV-DAILY-002"
RESERVATION_SCHEMA = "nba-sdv-recurring-reservation-v1"
PLAN_SCHEMA = "nba-sdv-recurring-plan-v1"
EVENT_INPUT_SCHEMA = "nba-sdv-recurring-event-input-v1"
FIRST_EFFECTIVE_DATE = date(2026, 10, 24)
PLANNING_WINDOW_SECONDS = 1800
MAX_PLAN_BYTES = 512 * 1024
SELECTION_RULE = "first_two_chronological_eligible_events_per_utc_game_date_v1"
SCHEDULE_FIELDS = {"id", "uid", "game_id", "season", "season_type", "date", "start_date", "game_date_time",
    "home_id", "home_display_name", "away_id", "away_display_name", "status_type_name", "status_type_state",
    "status_type_completed", "time_valid"}
ROSTER_FIELDS = {"season", "athlete_id", "uid", "team_id", "team_display_name", "display_name", "status_type", "status_name", "status_id"}
RESERVATION_FIELDS = {"schema_version", "protocol_id", "registered_at", "first_game_date", "last_game_date", "game_dates",
    "planning_time_utc", "planning_day_offset", "planning_window_seconds", "max_events_per_day", "subject_selection_rule",
    "event_selection_rule", "source_policy_id", "source_interpretation_schema", "history_record_id", "history_rows",
    "history_panel_sha256", "model_versions", "issuance_authority", "qualification", "reservation_id"}
PLAN_FIELDS = {"schema_version", "protocol_id", "reservation", "game_date", "planning_started_at", "planned_at", "planning_opens_at", "planning_closes_at",
    "sources", "source_schedule_rows", "outside_game_date_rows", "inventory", "selected_events", "subject_count", "unique_player_count",
    "status", "issuance_authority", "qualification", "plan_id"}
EVENT_FIELDS = {"event", "candidates", "source_interpretation", "selection_rank", "retrieval_opens_at", "cutoff_at", "issuance_closes_at", "event_plan_id"}
INVENTORY_FIELDS = {"event_id", "event_starts_at", "home_team_id", "away_team_id", "status_type_name", "status_type_state",
    "status_type_completed", "time_valid", "eligibility", "exclusion_reasons", "selected"}
EVENT_INPUT_FIELDS = {"schema_version", "protocol_id", "plan_id", "reservation_id", "event_plan_id", "validation_started_at", "validated_at", "source_interpretation",
    "status", "issuance_authority", "qualification", "event_input_id"}
REASONS = {"NOT_SCHEDULED", "INVALID_START_FLAG", "NOT_FUTURE", "INSUFFICIENT_ACTIVE_COHORT", "DAILY_EVENT_LIMIT"}


def _now():
    return datetime.now(timezone.utc)


def require(ok, message):
    if not ok:
        raise IntegrityError(message)


def _exact(body, fields, label):
    require(type(body) is dict and set(body) == fields, "Invalid recurring " + label + " fields")


def _seal(body, key):
    return {**body, key: digest(body)}


def _sealed(body, key):
    require(body.get(key) == digest({k: v for k, v in body.items() if k != key}), "Recurring checksum mismatch: " + key)


def _date(value):
    require(type(value) is str and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value), "Recurring game date must be an exact UTC date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise IntegrityError("Invalid recurring game date") from exc


def _clock(value):
    try:
        require(type(value) is str and stamp(utc(value)) == value, "Recurring clock needs precise UTC")
        return utc(value)
    except (TypeError, ValueError) as exc:
        raise IntegrityError("Invalid recurring clock") from exc


def planning_window(game_date):
    day = _date(game_date) - timedelta(days=1)
    opens = datetime.combine(day, datetime.min.time(), timezone.utc).replace(hour=13, minute=17)
    return opens, opens + timedelta(seconds=PLANNING_WINDOW_SECONDS)


def make_reservation(*, first_game_date="2026-10-24"):
    day = _date(first_game_date)
    dates = [(day + timedelta(days=index)).isoformat() for index in range(7)]
    body = {"schema_version": RESERVATION_SCHEMA, "protocol_id": PROTOCOL_ID, "registered_at": stamp(_now()),
        "first_game_date": dates[0], "last_game_date": dates[-1], "game_dates": dates,
        "planning_time_utc": "13:17", "planning_day_offset": -1, "planning_window_seconds": PLANNING_WINDOW_SECONDS,
        "max_events_per_day": 2, "subject_selection_rule": inputs.SELECTION_RULE, "event_selection_rule": SELECTION_RULE,
        "source_policy_id": inputs.make_policy()["policy_id"], "source_interpretation_schema": inputs.INPUT_SCHEMA,
        "history_record_id": first.HISTORY_RECORD_ID, "history_rows": first.HISTORY_ROWS,
        "history_panel_sha256": first.HISTORY_PANEL_SHA256, "model_versions": deepcopy(first.MODEL_VERSIONS),
        "issuance_authority": "NONE_PLANNING_ONLY", "qualification": "UNAVAILABLE"}
    return validate_reservation(_seal(body, "reservation_id"))


def validate_reservation(body):
    _exact(body, RESERVATION_FIELDS, "reservation")
    day = _date(body["first_game_date"])
    dates = [(day + timedelta(days=index)).isoformat() for index in range(7)]
    registered = _clock(body["registered_at"])
    require(body["schema_version"] == RESERVATION_SCHEMA and body["protocol_id"] == PROTOCOL_ID
        and day == FIRST_EFFECTIVE_DATE and body["game_dates"] == dates and body["last_game_date"] == dates[-1]
        and registered <= _now() and registered < planning_window(dates[0])[0],
        "Recurring reservation must precede its seven-day future planning window")
    require(body["planning_time_utc"] == "13:17" and body["planning_day_offset"] == -1
        and type(body["planning_day_offset"]) is int and body["planning_window_seconds"] == PLANNING_WINDOW_SECONDS
        and type(body["planning_window_seconds"]) is int and body["max_events_per_day"] == 2
        and type(body["max_events_per_day"]) is int and body["subject_selection_rule"] == inputs.SELECTION_RULE
        and body["event_selection_rule"] == SELECTION_RULE and body["source_policy_id"] == inputs.make_policy()["policy_id"]
        and body["source_interpretation_schema"] == inputs.INPUT_SCHEMA
        and body["history_record_id"] == first.HISTORY_RECORD_ID and body["history_rows"] == first.HISTORY_ROWS
        and type(body["history_rows"]) is int and body["history_panel_sha256"] == first.HISTORY_PANEL_SHA256
        and body["model_versions"] == first.MODEL_VERSIONS and body["issuance_authority"] == "NONE_PLANNING_ONLY"
        and body["qualification"] == "UNAVAILABLE", "Recurring reservation changed its registered limits or semantics")
    _sealed(body, "reservation_id")
    return body


def _sources(schedule_raw, roster_raw, schedule_metadata, roster_metadata, source_originals, *, at):
    require(type(source_originals) is dict and set(source_originals) == {"schedule", "roster"}, "Both exact publisher release originals are required")
    result = []
    for role, raw, metadata in (("schedule", schedule_raw, schedule_metadata), ("roster", roster_raw, roster_metadata)):
        inputs.validate_source_metadata(metadata, role=role, raw=raw, normalized_at=at)
        original = source_originals[role]
        require(type(original) is bytes and 0 < len(original) <= 256 * 1024, "Publisher original exceeds existing 256-KiB bound")
        expected = source_metadata(raw, original, metadata, retrieval_started_at=metadata["retrieval_started_at"], retrieved_at=metadata["retrieved_at"])
        require(expected == metadata, "Publisher original does not authenticate the supplied asset metadata")
        require((at - _clock(metadata["publisher_updated_at"])).total_seconds() <= 129600, "Recurring publisher asset is stale")
        result.append(deepcopy(metadata))
    return result


def _tables(schedule_raw, roster_raw):
    schedule = inputs._table(schedule_raw, SCHEDULE_FIELDS, "schedule")
    roster = inputs._table(roster_raw, ROSTER_FIELDS, "roster")
    seen, seasons = set(), set()
    for row in schedule:
        eid = inputs._id(row["id"], "schedule event ID")
        require(eid not in seen and row["game_id"] == eid and row["uid"] == "s:40~l:46~e:" + eid + "~c:" + eid,
            "Duplicate/conflicting recurring schedule identity")
        seen.add(eid); seasons.add(row["season"])
        require(re.fullmatch(r"20[0-9]{2}", row["season"]) is not None and row["season_type"] in {"1", "2", "3"}, "Invalid recurring event season")
        home, away = inputs._id(row["home_id"], "home team"), inputs._id(row["away_id"], "away team")
        require(home != away, "Recurring event teams conflict")
        for field in ("home_display_name", "away_display_name", "status_type_name", "status_type_state"):
            inputs._text(row[field], field)
        require(row["status_type_completed"] in {"true", "false"} and row["time_valid"] in {"true", "false"}, "Missing/invalid recurring event state")
        start = inputs._source_time(row["date"], "scheduled start")
        require(start == inputs._source_time(row["start_date"], "start_date") == inputs._source_time(row["game_date_time"], "game_date_time"),
            "Recurring event start clocks conflict; UTC inventory cannot be established")
    require(len(seasons) == 1, "Recurring schedule mixes seasons")
    seen, names = set(), {}
    for row in roster:
        pid, team = inputs._id(row["athlete_id"], "roster player"), inputs._id(row["team_id"], "roster team")
        require(pid not in seen and row["uid"] == "s:40~l:46~a:" + pid and row["season"] in seasons, "Duplicate/conflicting recurring roster identity or season")
        seen.add(pid)
        for field in ("display_name", "team_display_name", "status_type", "status_name", "status_id"):
            inputs._text(row[field], field)
        require(team not in names or names[team] == row["team_display_name"], "Recurring roster team labels conflict")
        names[team] = row["team_display_name"]
        if row["status_type"] == "active":
            require(row["status_name"] == "Active" and row["status_id"] == "1", "Conflicting recurring active roster status")
    return schedule, roster


def _cohort(row, roster):
    result = []
    for team, opponent, label in ((row["home_id"], row["away_id"], row["home_display_name"]),
                                 (row["away_id"], row["home_id"], row["away_display_name"])):
        selected = sorted((player for player in roster if player["team_id"] == team and player["status_type"] == "active"),
            key=lambda player: int(player["athlete_id"]))[:2]
        if len(selected) != 2:
            return None
        require(all(player["team_display_name"] == label for player in selected), "Recurring source team labels conflict")
        result.extend({"player_id": player["athlete_id"], "player_label": player["display_name"], "team_id": team, "opponent_id": opponent} for player in selected)
    return result


def _build_plan(schedule_raw, roster_raw, schedule_metadata, roster_metadata, *, source_originals, reservation, game_date, at, started_at=None):
    validate_reservation(reservation)
    require(game_date in reservation["game_dates"], "Game date is outside the registered seven-day reservation")
    opens, closes = planning_window(game_date)
    require(opens <= at <= closes, "Recurring daily planning window is not open or was missed")
    sources = _sources(schedule_raw, roster_raw, schedule_metadata, roster_metadata, source_originals, at=at)
    schedule, roster = _tables(schedule_raw, roster_raw)
    season = schedule[0]["season"]  # _tables requires one complete-table season.
    require(all(source["asset_name"] == (("nba_schedule_" if source["role"] == "schedule" else "rosters_") + season + ".csv")
        for source in sources), "Recurring publisher asset year differs from complete CSV table season")
    inventory, selected_events = [], []
    for row in sorted(schedule, key=lambda item: (inputs._source_time(item["date"], "scheduled start"), int(item["id"]))):
        start = inputs._source_time(row["date"], "scheduled start")
        if start.date().isoformat() != game_date:
            continue
        reasons = []
        if (row["status_type_name"], row["status_type_state"], row["status_type_completed"]) != ("STATUS_SCHEDULED", "pre", "false"):
            reasons.append("NOT_SCHEDULED")
        if row["time_valid"] != "true": reasons.append("INVALID_START_FLAG")
        if start <= at: reasons.append("NOT_FUTURE")
        cohort = _cohort(row, roster)
        if cohort is None: reasons.append("INSUFFICIENT_ACTIVE_COHORT")
        eligible = not reasons
        selected = eligible and len(selected_events) < 2
        if eligible and not selected: reasons.append("DAILY_EVENT_LIMIT")
        inventory.append({"event_id": row["id"], "event_starts_at": stamp(start), "home_team_id": row["home_id"], "away_team_id": row["away_id"],
            **{key: row[key] for key in ("status_type_name", "status_type_state", "status_type_completed", "time_valid")},
            "eligibility": "ELIGIBLE" if eligible else "EXCLUDED", "exclusion_reasons": reasons, "selected": selected})
        if not selected: continue
        interpreted = inputs.normalize_inputs(schedule_raw, roster_raw, schedule_metadata, roster_metadata,
            event_id=row["id"], expected_candidates=cohort, mode="DEVELOPMENT_ONLY", normalized_at=at)
        cutoff = start - timedelta(minutes=90)
        event_plan = {"event": interpreted["event"], "candidates": interpreted["candidates"], "source_interpretation": interpreted,
            "selection_rank": len(selected_events) + 1, "retrieval_opens_at": stamp(cutoff - timedelta(hours=1)),
            "cutoff_at": stamp(cutoff), "issuance_closes_at": stamp(cutoff + timedelta(minutes=15))}
        selected_events.append(_seal(event_plan, "event_plan_id"))
    subjects = [(candidate["player_id"], event["event"]["event_id"]) for event in selected_events for candidate in event["candidates"]]
    body = {"schema_version": PLAN_SCHEMA, "protocol_id": PROTOCOL_ID, "reservation": deepcopy(reservation), "game_date": game_date,
        "planning_started_at": stamp(started_at or at), "planned_at": stamp(at), "planning_opens_at": stamp(opens), "planning_closes_at": stamp(closes), "sources": sources,
        "source_schedule_rows": len(schedule), "outside_game_date_rows": len(schedule) - len(inventory), "inventory": inventory,
        "selected_events": selected_events, "subject_count": len(subjects), "unique_player_count": len({pid for pid, _ in subjects}),
        "status": "PLANNED" if selected_events else "NO_ELIGIBLE_EVENTS", "issuance_authority": "NONE_PLANNING_ONLY", "qualification": "UNAVAILABLE"}
    result = _seal(body, "plan_id")
    require(len(canonical(result)) <= MAX_PLAN_BYTES, "Complete recurring plan exceeds 512-KiB bound; no inventory truncation")
    return validate_plan(result)


def plan_day(schedule_raw, roster_raw, schedule_metadata, roster_metadata, *, source_originals, reservation, game_date):
    """Freeze the complete UTC-date inventory before generation, at the actual clock."""
    started = _now()
    original = _build_plan(schedule_raw, roster_raw, schedule_metadata, roster_metadata, source_originals=source_originals,
        reservation=reservation, game_date=game_date, at=started)
    # Only now have the source originals, complete inventory and all selected
    # normalized subjects passed. Reclock the interpreted completion, never the
    # publisher observations, and refuse completion outside the original window.
    completed = _now(); opens, closes = planning_window(game_date)
    require(opens <= started <= completed <= closes, "Recurring daily planning completion missed its window")
    body = {key: deepcopy(value) for key, value in original.items() if key != "plan_id"}
    body["planned_at"] = stamp(completed)
    events = []
    for selected in body["selected_events"]:
        event = {key: value for key, value in selected.items() if key != "event_plan_id"}
        interpreted = {key: value for key, value in event["source_interpretation"].items() if key != "input_id"}
        interpreted["normalized_at"] = stamp(completed)
        event["source_interpretation"] = _seal(interpreted, "input_id")
        events.append(_seal(event, "event_plan_id"))
    body["selected_events"] = events
    result = validate_plan(_seal(body, "plan_id"))
    require(_now() <= closes, "Recurring daily planning admission missed its window")
    return result


def validate_plan(body):
    _exact(body, PLAN_FIELDS, "plan")
    require(body["schema_version"] == PLAN_SCHEMA and body["protocol_id"] == PROTOCOL_ID
        and body["issuance_authority"] == "NONE_PLANNING_ONLY" and body["qualification"] == "UNAVAILABLE", "Wrong recurring plan authority or protocol")
    reservation = validate_reservation(body["reservation"])
    require(body["game_date"] in reservation["game_dates"], "Recurring plan date was not reserved")
    opens, closes = planning_window(body["game_date"]); at = _clock(body["planned_at"]); started = _clock(body["planning_started_at"])
    require(body["planning_opens_at"] == stamp(opens) and body["planning_closes_at"] == stamp(closes)
        and opens <= started <= at <= closes and at <= _now(), "Recurring plan clock/window differs")
    require(type(body["sources"]) is list and len(body["sources"]) == 2, "Recurring plan source inventory differs")
    for role, source in zip(("schedule", "roster"), body["sources"]):
        inputs.validate_source_metadata(source, role=role, normalized_at=at)
        require((at - _clock(source["publisher_updated_at"])).total_seconds() <= 129600, "Recurring planning source is stale")
    inventory = body["inventory"]
    require(type(inventory) is list and len(inventory) <= inputs.MAX_SOURCE_ROWS and type(body["source_schedule_rows"]) is int
        and 0 < body["source_schedule_rows"] <= inputs.MAX_SOURCE_ROWS and type(body["outside_game_date_rows"]) is int
        and body["outside_game_date_rows"] >= 0 and len(inventory) + body["outside_game_date_rows"] == body["source_schedule_rows"], "Recurring complete inventory counts differ")
    keys, eligible = [], []
    for item in inventory:
        _exact(item, INVENTORY_FIELDS, "inventory row")
        eid = inputs._id(item["event_id"], "event ID"); start = _clock(item["event_starts_at"])
        require(start.date().isoformat() == body["game_date"] and item["eligibility"] in {"ELIGIBLE", "EXCLUDED"}
            and type(item["selected"]) is bool and type(item["exclusion_reasons"]) is list
            and all(type(reason) is str for reason in item["exclusion_reasons"])
            and len(item["exclusion_reasons"]) == len(set(item["exclusion_reasons"]))
            and set(item["exclusion_reasons"]) <= REASONS, "Recurring inventory status or date invalid")
        for key in ("home_team_id", "away_team_id"): inputs._id(item[key], key)
        require(item["home_team_id"] != item["away_team_id"], "Recurring inventory teams conflict")
        for key in ("status_type_name", "status_type_state"): inputs._text(item[key], key)
        require(item["status_type_completed"] in {"true", "false"} and item["time_valid"] in {"true", "false"}, "Recurring inventory state is invalid")
        reasons = []
        if (item["status_type_name"], item["status_type_state"], item["status_type_completed"]) != ("STATUS_SCHEDULED", "pre", "false"): reasons.append("NOT_SCHEDULED")
        if item["time_valid"] != "true": reasons.append("INVALID_START_FLAG")
        if start <= at: reasons.append("NOT_FUTURE")
        actual_reasons = [reason for reason in item["exclusion_reasons"] if reason != "DAILY_EVENT_LIMIT"]
        require(actual_reasons in (reasons, reasons + ["INSUFFICIENT_ACTIVE_COHORT"])
            and (item["eligibility"] == "ELIGIBLE") == (not actual_reasons), "Recurring inventory eligibility contradicts observed event facts")
        keys.append((start, int(eid)))
        if item["eligibility"] == "ELIGIBLE":
            eligible.append(eid)
            require(item["exclusion_reasons"] == ([] if len(eligible) <= 2 else ["DAILY_EVENT_LIMIT"])
                and item["selected"] == (len(eligible) <= 2), "Recurring selection is not the first two consecutive eligible events")
        else:
            require(bool(item["exclusion_reasons"]) and "DAILY_EVENT_LIMIT" not in item["exclusion_reasons"] and not item["selected"], "Excluded recurring event was silently selected")
    require(keys == sorted(keys) and len({eid for _, eid in keys}) == len(keys), "Recurring inventory ordering or identities differ")
    events = body["selected_events"]
    require(type(events) is list and len(events) <= 2, "Recurring selected-event inventory differs")
    for event in events:
        _exact(event, EVENT_FIELDS, "selected event")
        require(type(event["event"]) is dict and type(event["event"].get("event_id")) is str, "Invalid recurring selected-event identity")
    require([row["event"]["event_id"] for row in events] == eligible[:2], "Recurring selected-event inventory differs")
    subjects = []
    for rank, event in enumerate(events, 1):
        _exact(event, EVENT_FIELDS, "selected event"); _sealed(event, "event_plan_id")
        interpreted = inputs.validate_input(event["source_interpretation"])
        require(interpreted["mode"] == "DEVELOPMENT_ONLY" and interpreted["event"] == event["event"]
            and interpreted["candidates"] == event["candidates"] and interpreted["sources"] == body["sources"]
            and interpreted["normalized_at"] == body["planned_at"] and event["selection_rank"] == rank
            and type(event["selection_rank"]) is int, "Recurring source interpretation was changed or promoted")
        selected = next(item for item in inventory if item["event_id"] == event["event"]["event_id"])
        require(selected["event_starts_at"] == event["event"]["event_starts_at"]
            and selected["home_team_id"] == event["event"]["home_team_id"]
            and selected["away_team_id"] == event["event"]["away_team_id"], "Recurring selected event differs from its complete inventory")
        start = _clock(event["event"]["event_starts_at"]); cutoff = start - timedelta(minutes=90)
        require(event["retrieval_opens_at"] == stamp(cutoff - timedelta(hours=1)) and event["cutoff_at"] == stamp(cutoff)
            and event["issuance_closes_at"] == stamp(cutoff + timedelta(minutes=15)), "Recurring per-event operating window changed")
        subjects.extend((row["player_id"], event["event"]["event_id"]) for row in event["candidates"])
    require(body["subject_count"] == len(subjects) and type(body["subject_count"]) is int and body["subject_count"] <= 8
        and body["unique_player_count"] == len({pid for pid, _ in subjects}) and type(body["unique_player_count"]) is int
        and body["status"] == ("PLANNED" if events else "NO_ELIGIBLE_EVENTS"), "Recurring subject counts/status differ")
    _sealed(body, "plan_id")
    require(len(canonical(body)) <= MAX_PLAN_BYTES, "Complete recurring plan exceeds encoded bound")
    return body


def verify_plan_sources(body, schedule_raw, roster_raw, schedule_metadata, roster_metadata, *, source_originals):
    """Read-only original-clock replay; never grants issuance or refreshes age."""
    validate_plan(body)
    replay = _build_plan(schedule_raw, roster_raw, schedule_metadata, roster_metadata, source_originals=source_originals,
        reservation=body["reservation"], game_date=body["game_date"], at=_clock(body["planned_at"]), started_at=_clock(body["planning_started_at"]))
    require(replay == body, "Recurring retained plan differs from exact original source replay")
    return body


def revalidate_event(plan, event_id, schedule_raw, roster_raw, schedule_metadata, roster_metadata, *, source_originals):
    """Bind a fresh per-event input; preparation snapshots cannot pass this gate."""
    validate_plan(plan)
    selected = [event for event in plan["selected_events"] if event["event"]["event_id"] == event_id]
    require(len(selected) == 1, "Event is outside the frozen daily selection; no replacements")
    event = selected[0]; started = _now(); cutoff = _clock(event["cutoff_at"])
    require(_clock(event["retrieval_opens_at"]) <= started <= cutoff, "Fresh recurring input missed its registered retrieval window")
    _sources(schedule_raw, roster_raw, schedule_metadata, roster_metadata, source_originals, at=started)
    interpreted = inputs.normalize_inputs(schedule_raw, roster_raw, schedule_metadata, roster_metadata,
        event_id=event_id, expected_candidates=event["candidates"], mode="DEVELOPMENT_ONLY", normalized_at=started)
    require(interpreted["event"] == event["event"], "Fresh event identity/version changed; no shifted windows or replacement")
    for source in interpreted["sources"]:
        require(_clock(event["retrieval_opens_at"]) <= _clock(source["retrieval_started_at"])
            <= _clock(source["retrieved_at"]) <= started <= cutoff, "Preparation or late source observations cannot become fresh issuance inputs")
    completed = _now()
    require(started <= completed <= cutoff, "Fresh recurring input completion missed its registered retrieval window")
    interpreted = {key: value for key, value in interpreted.items() if key != "input_id"}
    interpreted["normalized_at"] = stamp(completed)
    interpreted = _seal(interpreted, "input_id")
    body = {"schema_version": EVENT_INPUT_SCHEMA, "protocol_id": PROTOCOL_ID, "plan_id": plan["plan_id"],
        "reservation_id": plan["reservation"]["reservation_id"], "event_plan_id": event["event_plan_id"], "validation_started_at": stamp(started), "validated_at": stamp(completed),
        "source_interpretation": interpreted, "status": "FRESH_INPUT_CANDIDATE_NOT_ISSUED", "issuance_authority": "NONE_PLANNING_ONLY", "qualification": "UNAVAILABLE"}
    result = validate_event_input(_seal(body, "event_input_id"), plan)
    require(_now() <= cutoff, "Fresh recurring input admission missed its registered retrieval window")
    return result


def validate_event_input(body, plan):
    """Recover a fresh-input candidate without implying operating authority."""
    validate_plan(plan)
    _exact(body, EVENT_INPUT_FIELDS, "event-input candidate")
    require(body["schema_version"] == EVENT_INPUT_SCHEMA and body["protocol_id"] == PROTOCOL_ID
        and body["plan_id"] == plan["plan_id"] and body["reservation_id"] == plan["reservation"]["reservation_id"]
        and body["status"] == "FRESH_INPUT_CANDIDATE_NOT_ISSUED" and body["issuance_authority"] == "NONE_PLANNING_ONLY"
        and body["qualification"] == "UNAVAILABLE", "Recurring event input claims unsupported identity or authority")
    events = [event for event in plan["selected_events"] if event["event_plan_id"] == body["event_plan_id"]]
    require(len(events) == 1, "Recurring event input changed its frozen event")
    event = events[0]; at = _clock(body["validated_at"]); started = _clock(body["validation_started_at"])
    interpreted = inputs.validate_input(body["source_interpretation"])
    require(interpreted["mode"] == "DEVELOPMENT_ONLY" and interpreted["normalized_at"] == body["validated_at"]
        and interpreted["event"] == event["event"] and interpreted["candidates"] == event["candidates"]
        and _clock(event["retrieval_opens_at"]) <= started <= at <= _clock(event["cutoff_at"]) and at <= _now(),
        "Recurring event input changed the registered cohort, identity or clock")
    inputs.freshness(interpreted, at=at)
    for source in interpreted["sources"]:
        require(_clock(event["retrieval_opens_at"]) <= _clock(source["retrieval_started_at"])
            <= _clock(source["retrieved_at"]) <= started, "Recurring event input reused preparation observations")
    _sealed(body, "event_input_id")
    return body


def verify_event_input_sources(body, plan, schedule_raw, roster_raw, schedule_metadata, roster_metadata, *, source_originals):
    """Read-only exact-byte replay of the separately captured per-event input."""
    validate_event_input(body, plan)
    _sources(schedule_raw, roster_raw, schedule_metadata, roster_metadata, source_originals, at=_clock(body["validated_at"]))
    require(body["source_interpretation"]["sources"] == [schedule_metadata, roster_metadata], "Recurring fresh-input asset identities changed")
    inputs.verify_input_sources(body["source_interpretation"], schedule_raw, roster_raw, schedule_metadata, roster_metadata)
    return body

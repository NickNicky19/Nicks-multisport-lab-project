"""Offline final-evidence normalization; no collector and no venue settlement.

The original schedule and box-score CSV are retained separately. An absent row
is MISSING, never DNP or zero. This route does not grant collection permission.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import re

from .integrity import IntegrityError, stamp, utc
from .nba_data import normalize_sdv_row, with_sdv_schedule, SDV_FIELDS
from .ledger import _outcome_categories
from . import sdv_daily_producer as producer

VERSION = "sdv-daily-final-csv-normalizer-v1"


def _now():return datetime.now(timezone.utc)


def _rows(raw):
    producer.require(type(raw) is bytes and len(raw) <= 2*1024*1024, "Outcome source exceeds bounded bytes")
    reader=csv.DictReader(io.StringIO(raw.decode("utf-8-sig"),newline=""))
    producer.require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)), "Duplicate outcome CSV fields")
    result=[]
    for row in reader:
        producer.require(len(result) < 40000 and None not in row and all(v is not None for v in row.values()), "Malformed or excessive outcome rows")
        result.append(row)
    return result


def _boolean(value):
    if value in ("true","TRUE","True"):return True
    if value in ("false","FALSE","False"):return False
    if value in (None, "", "NA"):return None
    raise IntegrityError("Unrecognized explicit outcome Boolean")


def _count(value):
    if value in (None,"","NA"):return None
    producer.require(type(value) is str and re.fullmatch(r"\d+",value), "Invalid supplied outcome count")
    return int(value)


def _normalize(store,forecast,*,schedule_ref,boxscore_ref,normalized_at):
    schedule_raw,sm=store.read_outcome_evidence(schedule_ref)
    box_raw,bm=store.read_outcome_evidence(boxscore_ref)
    producer.require(sm["source_kind"] == "SportsDataverse NBA schedule CSV"
        and bm["source_kind"] == "SportsDataverse NBA player boxscore CSV", "Wrong final-source schema")
    schedules=[r for r in _rows(schedule_raw) if r.get("game_id") == forecast["event_id"]]
    producer.require(len(schedules) == 1,"Missing or duplicate final event")
    event=schedules[0]
    producer.require({event.get("home_id"),event.get("away_id")} == {forecast["team_id"],forecast["opponent_id"]}
        and utc(event.get("game_date_time")) == utc(forecast["event_starts_at"]),"Final event identity/version differs; preserve unresolved")
    rows=[r for r in _rows(box_raw) if r.get("game_id") == forecast["event_id"] and r.get("athlete_id") == forecast["player_id"]]
    producer.require(len(rows) <= 1,"Duplicate final player row")
    status="NONFINAL";line=None
    if event.get("status_type_name") == "STATUS_POSTPONED":status="POSTPONED"
    elif _boolean(event.get("status_type_completed")) is True:
        producer.require(event.get("status_type_name") == "STATUS_FINAL" and event.get("status_type_state") == "post", "Contradictory final status")
        status="MISSING"
        if rows:
            row=rows[0].copy()
            row["season"]=_count(row.get("season"));row["did_not_play"]=_boolean(row.get("did_not_play"))
            for field in SDV_FIELDS.values():row[field]=_count(row.get(field))
            value=row.get("minutes")
            producer.require(value in (None,"","NA") or re.fullmatch(r"\d+(?:\.\d+)?",value),"Invalid reported minutes")
            row["minutes"]=None if value in (None,"","NA") else float(value)
            line=normalize_sdv_row(row)
            schedule=event.copy();schedule["season"]=_count(schedule.get("season"))
            schedule["status_type_completed"]=_boolean(schedule.get("status_type_completed"))
            line=with_sdv_schedule(line,schedule,standard_team_ids=frozenset())
            producer.require(line.team_id == forecast["team_id"] and line.opponent_id == forecast["opponent_id"],"Final subject team identity differs")
            status={"APPEARED":"APPEARED","DNP":"DNP","UNKNOWN":"UNRESOLVED"}[line.participation]
    primitives=None;minutes=None;precision=None;categories=[]
    if status == "APPEARED":
        primitives={key:getattr(line,field) for key,field in {"FGM":"fgm","FG2M":"fg2m","FG3M":"fg3m","FTM":"ftm","PTS":"points","REB":"rebounds","AST":"assists","TOV":"turnovers","BLK":"blocks","STL":"steals"}.items()}
        categories=_outcome_categories(primitives);minutes=line.minutes;precision=line.minutes_precision
        if minutes is not None and float(minutes).is_integer():minutes=int(minutes)
    observed=max(utc(sm["retrieved_at"]),utc(bm["retrieved_at"]))
    body={"schema_version":producer.OUTCOME_SCHEMA,"protocol_id":producer.PROTOCOL_ID,
        **{key:forecast[key] for key in ("cycle_id","mode","event_id","event_snapshot_id","event_starts_at","player_id","team_id","opponent_id")},
        "status":status,"source_refs":[schedule_ref.to_record(),boxscore_ref.to_record()],
        "source_observed_at":stamp(observed),"normalized_at":normalized_at,
        "normalizer_version":VERSION,"primitives":primitives,"minutes":minutes,"minutes_precision":precision,"categories":categories}
    body=producer.seal(body,"outcome_id");producer.validate_outcome(body)
    return body


def normalize_outcome(store,forecast,*,schedule_ref,boxscore_ref):
    """Append a development-only outcome replayed from retained final CSVs.

    Genuine final-source admission must be reviewed when final evidence exists;
    this offline entrypoint does not manufacture an advance permission receipt.
    """
    producer.validate_forecast(forecast)
    producer.require(forecast["mode"] == "DEVELOPMENT_ONLY", "Genuine final-source admission must be reviewed before outcome collection/import")
    body=_normalize(store,forecast,schedule_ref=schedule_ref,boxscore_ref=boxscore_ref,
        normalized_at=stamp(_now()))
    return store.append_body("outcomes",body,references=(schedule_ref,boxscore_ref)),body


def verify_outcome_sources(store,body):
    """Read-only semantic replay using the original normalization clock."""
    from .ledger import LedgerRef
    producer.validate_outcome(body)
    producer.require(len(body["source_refs"]) == 2 and body["normalizer_version"] == VERSION,
        "Outcome requires this exact separately versioned final-source normalizer")
    expected=_normalize(store,body,schedule_ref=LedgerRef.from_record(body["source_refs"][0]),
        boxscore_ref=LedgerRef.from_record(body["source_refs"][1]),normalized_at=body["normalized_at"])
    producer.require(expected == body,"Outcome meaning differs from original source bytes")
    return body


def grade_pair(store,outcome_ref):
    """Separate statistical grades, linked to the same original outcome."""
    outcome=store.ledger.read(outcome_ref)["data"]["daily"];producer.validate_outcome(outcome)
    refs=[]
    for ref,forecast in store.records():
        if forecast["schema_version"] != producer.FORECAST_SCHEMA or any(forecast[k] != outcome[k] for k in ("cycle_id","mode","event_id","player_id")):continue
        grade=producer.make_grade(forecast,outcome)
        refs.append(store.append_body("grades",grade,references=(ref,outcome_ref)))
    return refs

"""Native production NBA source contracts; no collector, issuance or admission.

Every valid scheduled event and all active source-roster members are retained.
The larger explicit production policy does not alter either frozen pilot.
"""
from __future__ import annotations

from copy import deepcopy
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import re

from .integrity import IntegrityError, canonical, digest, stamp, utc, _decode
from . import sdv_production_common as common
from .sdv_daily_inputs import SOURCE_FIELDS as LEGACY_SOURCE_FIELDS, EVENT_FIELDS, MISSING_INFORMATION
from .sdv_recurring_plan import SCHEDULE_FIELDS, ROSTER_FIELDS

SOURCE_FIELDS = LEGACY_SOURCE_FIELDS | {"metadata_retrieval_started_at", "metadata_retrieved_at", "metadata_observation_status"}
BINDING_SCHEMA = "nba-sdv-production-producer-binding-v1"
BINDING_SCHEMA_V2 = "nba-sdv-production-producer-binding-v2"
BINDING_FIELDS = {"schema_version", "commit", "files", "law_sha256", "binding_id"}
PLAN_FIELDS = {"schema_version", "protocol_id", "mode", "policy", "game_date", "planning_started_at", "planned_at", "plan_seed",
    "sources", "inventory", "events", "exclusions", "source_schedule_rows", "outside_game_date_rows", "producer_binding",
    "history_record_id", "history_rows", "history_panel_sha256", "missing_information", "qualification", "plan_id"}
INPUT_FIELDS = {"schema_version", "protocol_id", "mode", "policy", "plan_id", "plan_seed", "cycle_id", "event", "candidates", "shards",
    "sources", "producer_binding", "history_record_id", "history_rows", "history_panel_sha256", "normalization_started_at", "normalized_at",
    "missing_information", "qualification", "input_id"}
PLAN_EVENT_FIELDS = {"event", "candidates", "shards", "cycle_id", "cutoff_at", "capture_opens_at", "issuance_closes_at"}
CANDIDATE_FIELDS = {"player_id", "player_label", "team_id", "opponent_id"}
INVENTORY_FIELDS = {"event_id", "event_starts_at", "home_team_id", "away_team_id", "status_type_name", "status_type_state", "status_type_completed",
    "time_valid", "eligible", "exclusion_reasons"}
MODES = {"DEVELOPMENT_ONLY", "PROSPECTIVE_RESEARCH"}
EXCLUSION_REASONS = {"NOT_SCHEDULED", "INVALID_START_FLAG", "NOT_FUTURE", "NO_ACTIVE_TEAM_ROSTER"}


def _policy(policy=None):
    return common.make_policy() if policy is None else common.validate_policy(policy)


def _id(value, label="identity"):
    common.require(type(value) is str and re.fullmatch(r"[1-9][0-9]*", value), "Invalid production " + label)
    return value


def _date(value):
    common.require(type(value) is str and re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", value), "Production game date must be an exact UTC date")
    try:return date.fromisoformat(value)
    except ValueError as exc:raise IntegrityError("Invalid production game date") from exc


def _source_clock(value):
    try:return utc(value)
    except (TypeError,ValueError) as exc:raise IntegrityError("Invalid publisher source clock") from exc


def validate_binding(body, *, prospective=False):
    common.exact(body, BINDING_FIELDS, "input producer binding")
    common.require(type(body["schema_version"]) is str and body["schema_version"] in {BINDING_SCHEMA,BINDING_SCHEMA_V2}
        and body["law_sha256"] == common.LAW_SHA256, "Production producer changed frozen model laws")
    if body["commit"] is not None:common.sha(body["commit"],40)
    common.require(not prospective or body["commit"] is not None,"Prospective production input requires a frozen producer commit")
    common.require(type(body["files"]) is dict and 1 <= len(body["files"]) <= 128, "Invalid production source-file inventory")
    for path, value in body["files"].items():
        common.require(type(path) is str and path.startswith(("multisport_lab/", "scripts/", "config/", ".github/workflows/"))
            and len(path) <= 256 and not any(part in {"", ".", ".."} for part in path.split("/")), "Unsafe production bound source path")
        common.sha(value)
    common.require(body["files"].get("multisport_lab/baseline.py") == common.LAW_SHA256["R0"]
        and body["files"].get("multisport_lab/development_003.py") == common.LAW_SHA256["K0"], "Production binding omits either frozen law")
    common.check_seal(body,"binding_id")
    return body


def source_metadata(raw, metadata_raw, source, *, retrieval_started_at, retrieved_at,
                    metadata_retrieval_started_at=None, metadata_retrieved_at=None, policy=None):
    """Bind bounded exact bytes to the actual publisher release, without GETs."""
    common.require(type(source) is dict,"Invalid production source descriptor")
    policy=_policy(policy); role=source.get("role")
    common.require(type(role) is str and role in {"schedule","roster","boxscore"}, "Unsupported production source role")
    common.require(type(raw) is bytes and 0 < len(raw) <= policy["maximum_csv_bytes"]
        and type(metadata_raw) is bytes and 0 < len(metadata_raw) <= policy["maximum_metadata_bytes"], "Production source exceeds its explicit byte ceiling")
    release=_decode(metadata_raw)
    common.require(type(release) is dict and release.get("tag_name") == source.get("release_tag") and type(release.get("assets")) is list, "Wrong production publisher release")
    assets=[row for row in release["assets"] if type(row) is dict and row.get("name") == source.get("asset_name")]
    common.require(len(assets) == 1, "Missing/duplicate production publisher asset")
    asset=assets[0]; raw_sha=hashlib.sha256(raw).hexdigest()
    common.require(asset.get("size") == len(raw) and type(asset.get("size")) is int
        and asset.get("browser_download_url") == source.get("asset_url") and asset.get("digest") == "sha256:"+raw_sha,
        "Production original bytes differ from publisher asset facts")
    known=metadata_retrieval_started_at is not None and metadata_retrieved_at is not None
    common.require(known or metadata_retrieval_started_at is None and metadata_retrieved_at is None, "Partial publisher metadata observation clock")
    body={"role":role,"publisher":"SportsDataverse","release_tag":source["release_tag"],"asset_name":source["asset_name"],"asset_url":source["asset_url"],
        "asset_id":asset.get("id"),"asset_bytes":len(raw),"asset_sha256":raw_sha,"publisher_updated_at":stamp(_source_clock(asset.get("updated_at"))),
        "upstream_observed_at":None,"upstream_observation_status":"UNKNOWN","retrieval_started_at":stamp(_source_clock(retrieval_started_at)),
        "retrieved_at":stamp(_source_clock(retrieved_at)),"metadata_sha256":hashlib.sha256(metadata_raw).hexdigest(),"metadata_bytes":len(metadata_raw),
        "metadata_retrieval_started_at":None if not known else stamp(_source_clock(metadata_retrieval_started_at)),
        "metadata_retrieved_at":None if not known else stamp(_source_clock(metadata_retrieved_at)),"metadata_observation_status":"OBSERVED" if known else "UNKNOWN"}
    return validate_source_metadata(body,raw=raw,policy=policy)


def validate_source_metadata(body, *, raw=None, role=None, at=None, prospective=False, policy=None):
    common.exact(body,SOURCE_FIELDS,"source metadata"); policy=_policy(policy)
    actual_role=body["role"]
    common.require(type(actual_role) is str and actual_role in {"schedule","roster","boxscore"} and (role is None or role == actual_role) and body["publisher"] == "SportsDataverse", "Production source role/publisher differs")
    tag={"schedule":"espn_nba_schedules","roster":"espn_nba_rosters","boxscore":"espn_nba_player_boxscores"}[actual_role]
    prefix={"schedule":"nba_schedule_","roster":"rosters_","boxscore":"player_box_"}[actual_role]
    common.require(body["release_tag"] == tag and type(body["asset_name"]) is str and re.fullmatch(prefix+r"20[0-9]{2}\.csv",body["asset_name"])
        and body["asset_url"] == "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"+tag+"/"+body["asset_name"], "Production source route/family differs")
    common.require(type(body["asset_id"]) is int and 0 < body["asset_id"] < 2**63, "Missing stable publisher asset ID")
    for key, maximum in (("asset_bytes",policy["maximum_csv_bytes"]),("metadata_bytes",policy["maximum_metadata_bytes"])):
        common.require(type(body[key]) is int and 0 < body[key] <= maximum, "Production source size exceeds explicit limit")
    common.sha(body["asset_sha256"]); common.sha(body["metadata_sha256"])
    updated,start,end=(common.clock(body[key]) for key in ("publisher_updated_at","retrieval_started_at","retrieved_at"))
    common.require(updated <= end and start <= end, "Production asset observation clocks conflict")
    common.require(body["upstream_observation_status"] in {"UNKNOWN","OBSERVED"}, "Invalid upstream observation status")
    if body["upstream_observation_status"] == "UNKNOWN":common.require(body["upstream_observed_at"] is None,"Unknown upstream time was invented")
    else:common.require(common.clock(body["upstream_observed_at"]) <= end,"Future upstream observation")
    if body["metadata_observation_status"] == "UNKNOWN":
        common.require(body["metadata_retrieval_started_at"] is None and body["metadata_retrieved_at"] is None and not prospective, "Prospective publisher metadata needs actual capture clocks")
    else:
        common.require(body["metadata_observation_status"] == "OBSERVED", "Invalid publisher observation status")
        meta_start,meta_end=(common.clock(body[key]) for key in ("metadata_retrieval_started_at","metadata_retrieved_at"))
        common.require(meta_start <= meta_end <= start and updated <= meta_end,"Publisher metadata/asset clocks conflict")
    if raw is not None:
        common.require(type(raw) is bytes and len(raw) == body["asset_bytes"] and hashlib.sha256(raw).hexdigest() == body["asset_sha256"],"Production raw source hash/size differs")
    if at is not None:
        actual=_source_clock(at)
        common.require(end <= actual and updated <= actual and (actual-updated).total_seconds() <= policy["publisher_max_age_seconds"],"Production publisher input is stale or future-dated")
    return body


def validate_source(raw,metadata,metadata_raw,role,season,*,policy=None):
    """Authenticate exact release originals; final-state admission remains separate."""
    policy=_policy(policy);validate_source_metadata(metadata,raw=raw,role=role,policy=policy)
    prefix={"schedule":"nba_schedule_","roster":"rosters_","boxscore":"player_box_"}[role]
    common.require(type(season) is int and 2000 <= season <= 2099 and metadata["asset_name"] == prefix+str(season)+".csv", "Production source asset/table season conflicts")
    expected=source_metadata(raw,metadata_raw,metadata,retrieval_started_at=metadata["retrieval_started_at"],retrieved_at=metadata["retrieved_at"],
        metadata_retrieval_started_at=metadata["metadata_retrieval_started_at"],metadata_retrieved_at=metadata["metadata_retrieved_at"],policy=policy)
    common.require(expected == metadata,"Exact original publisher source metadata differs")
    return metadata


def _table(raw, fields, label, policy=None):
    policy=_policy(policy)
    common.require(type(raw) is bytes and 0 < len(raw) <= policy["maximum_csv_bytes"],"Production CSV exceeds explicit size limit")
    try:
        reader=csv.DictReader(io.StringIO(raw.decode("utf-8-sig"),newline="")); names=reader.fieldnames
        common.require(names is not None and len(names) == len(set(names)) and set(fields) <= set(names)
            and all(type(name) is str and name for name in names),"Missing/duplicate production "+label+" columns")
        rows=[]
        for row in reader:
            common.require(len(rows) < policy["maximum_source_rows"],"Production source row ceiling exceeded; no truncation")
            common.require(None not in row and all(type(value) is str for value in row.values()),"Malformed production CSV row")
            rows.append(row)
    except (UnicodeError,csv.Error) as exc:raise IntegrityError("Invalid production CSV encoding") from exc
    common.require(bool(rows),"Empty production "+label+" CSV")
    return rows


def _tables(schedule_raw,roster_raw,policy=None):
    policy=_policy(policy)
    schedule=_table(schedule_raw,SCHEDULE_FIELDS,"schedule",policy); roster=_table(roster_raw,ROSTER_FIELDS,"roster",policy)
    seen,seasons=set(),set()
    for row in schedule:
        eid=_id(row["id"],"schedule event ID")
        common.require(eid not in seen and row["game_id"] == eid and row["uid"] == "s:40~l:46~e:"+eid+"~c:"+eid,"Duplicate/conflicting production event identity")
        seen.add(eid);seasons.add(row["season"])
        common.require(re.fullmatch(r"20[0-9]{2}",row["season"]) and row["season_type"] in {"1","2","3"},"Invalid production event season")
        home,away=_id(row["home_id"]),_id(row["away_id"])
        common.require(home != away,"Production event teams conflict")
        for key in ("home_display_name","away_display_name","status_type_name","status_type_state"):common.text(row[key])
        common.require(row["status_type_completed"] in {"true","false"} and row["time_valid"] in {"true","false"},"Missing/invalid production event state")
        starts=[_source_clock(row[key]) for key in ("date","start_date","game_date_time")]
        common.require(starts[0] == starts[1] == starts[2],"Production event starts conflict; complete UTC inventory unavailable")
    common.require(len(seasons) == 1,"Production schedule mixes seasons")
    seen,names=set(),{}
    for row in roster:
        pid,team=_id(row["athlete_id"]),_id(row["team_id"])
        common.require(pid not in seen and row["uid"] == "s:40~l:46~a:"+pid and row["season"] in seasons,"Duplicate/conflicting production roster identity or season")
        seen.add(pid)
        for key in ("display_name","team_display_name","status_type","status_name","status_id"):common.text(row[key])
        common.require(team not in names or names[team] == row["team_display_name"],"Production roster team labels conflict")
        names[team]=row["team_display_name"]
        if row["status_type"] == "active":common.require(row["status_name"] == "Active" and row["status_id"] == "1","Conflicting active roster status")
    return schedule,roster


def _sources(raws,metas,originals,*,at,mode,policy=None):
    policy=_policy(policy)
    common.require(type(originals) is dict and set(originals) == {"schedule","roster"},"Both exact release metadata originals are required")
    result=[]
    for role,raw,meta in zip(("schedule","roster"),raws,metas):
        validate_source_metadata(meta,raw=raw,role=role,at=at,prospective=mode == "PROSPECTIVE_RESEARCH",policy=policy)
        expected=source_metadata(raw,originals[role],meta,retrieval_started_at=meta["retrieval_started_at"],retrieved_at=meta["retrieved_at"],
            metadata_retrieval_started_at=meta["metadata_retrieval_started_at"],metadata_retrieved_at=meta["metadata_retrieved_at"],policy=policy)
        common.require(expected == meta,"Original publisher metadata differs from supplied source binding")
        result.append(deepcopy(meta))
    return result


def _event(row):
    return common.seal({"event_id":row["id"],"id_namespace":"espn","league":"NBA","season_ending_year":int(row["season"]),"season_type":row["season_type"],
        "home_team_id":row["home_id"],"home_team_name":row["home_display_name"],"away_team_id":row["away_id"],"away_team_name":row["away_display_name"],
        "event_starts_at":stamp(_source_clock(row["date"])),"status":"SCHEDULED","provider_event_revision":None},"event_snapshot_id")


def _cohort(row,roster):
    candidates=[];excluded=[]
    for team,opponent,label in ((row["home_id"],row["away_id"],row["home_display_name"]),(row["away_id"],row["home_id"],row["away_display_name"])):
        members=sorted((player for player in roster if player["team_id"] == team),key=lambda player:int(player["athlete_id"]))
        common.require(all(player["team_display_name"] == label for player in members),"Production schedule/roster team labels conflict")
        for player in members:
            if player["status_type"] != "active":
                excluded.append({"event_id":row["id"],"player_id":player["athlete_id"],"team_id":team,"reason":"SOURCE_ROSTER_NOT_ACTIVE"});continue
            candidates.append({"player_id":player["athlete_id"],"player_label":player["display_name"],"team_id":team,"opponent_id":opponent})
    return candidates,excluded


def _missing(sources):
    result=list(MISSING_INFORMATION if any(source["upstream_observation_status"] == "UNKNOWN" for source in sources) else MISSING_INFORMATION[1:])
    if any(source["metadata_observation_status"] == "UNKNOWN" for source in sources):result.append("PUBLISHER_METADATA_OBSERVATION_CLOCK")
    return result


def _history():
    return {"history_record_id":common.HISTORY_ID,"history_rows":common.HISTORY_ROWS,"history_panel_sha256":common.HISTORY_SHA256}


def _planning_window(game_date,policy=None):
    policy=_policy(policy);day=_date(game_date)+timedelta(days=policy["planning_day_offset"])
    opens=datetime.combine(day,datetime.min.time(),timezone.utc).replace(hour=policy["planning_hour_utc"])
    return opens,opens+timedelta(seconds=policy["planning_window_seconds"])


def _event_plan(row,candidates,seed,policy=None):
    policy=_policy(policy)
    event=_event(row);start=common.clock(event["event_starts_at"]); cutoff=start-timedelta(minutes=90)
    size=policy["players_per_shard"]
    return {"event":event,"candidates":candidates,"shards":[[player["player_id"] for player in candidates[index:index+size]] for index in range(0,len(candidates),size)],
        "cycle_id":common.cycle_id(start.date().isoformat(),event["event_id"],seed),"cutoff_at":stamp(cutoff),"capture_opens_at":stamp(cutoff-timedelta(seconds=policy["capture_lookback_seconds"])),
        "issuance_closes_at":stamp(cutoff+timedelta(seconds=policy["generation_window_seconds"]))}


def _seed(game_date,sources,binding,events,policy=None):
    policy=_policy(policy)
    return digest({"protocol_id":common.PROTOCOL_ID,"policy_id":policy["policy_id"],"game_date":game_date,"sources":sources,
        "producer_binding":binding,"events":[{key:row[key] for key in ("event","candidates","shards")} for row in events]})


def _build_plan(schedule_raw,roster_raw,schedule_meta,roster_meta,*,source_originals,game_date,producer_binding,started,completed,mode,policy=None):
    common.require(type(mode) is str and mode in MODES,"Unknown production input mode"); validate_binding(producer_binding,prospective=mode == "PROSPECTIVE_RESEARCH"); day=_date(game_date)
    policy=deepcopy(_policy(policy)); sources=_sources((schedule_raw,roster_raw),(schedule_meta,roster_meta),source_originals,at=completed,mode=mode,policy=policy)
    schedule,roster=_tables(schedule_raw,roster_raw,policy);season=schedule[0]["season"]
    common.require(all(source["asset_name"] == ("nba_schedule_" if source["role"] == "schedule" else "rosters_")+season+".csv" for source in sources),"Production asset year differs from complete CSV season")
    inventory=[];provisional=[];excluded=[]
    for row in sorted(schedule,key=lambda value:(_source_clock(value["date"]),int(value["id"]))):
        start=_source_clock(row["date"])
        if start.date() != day:continue
        reasons=[]
        if (row["status_type_name"],row["status_type_state"],row["status_type_completed"]) != ("STATUS_SCHEDULED","pre","false"):reasons.append("NOT_SCHEDULED")
        if row["time_valid"] != "true":reasons.append("INVALID_START_FLAG")
        if start <= completed:reasons.append("NOT_FUTURE")
        candidates,player_exclusions=_cohort(row,roster)
        if not all(any(player["team_id"] == team for player in candidates) for team in (row["home_id"],row["away_id"])):reasons.append("NO_ACTIVE_TEAM_ROSTER")
        inventory.append({"event_id":row["id"],"event_starts_at":stamp(start),"home_team_id":row["home_id"],"away_team_id":row["away_id"],
            **{key:row[key] for key in ("status_type_name","status_type_state","status_type_completed","time_valid")},"eligible":not reasons,"exclusion_reasons":reasons})
        excluded.extend(player_exclusions)
        if reasons:
            excluded.append({"event_id":row["id"],"reason":"EVENT_EXCLUDED","reasons":reasons});continue
        common.require(len(candidates) <= policy["maximum_players_per_event"],"Complete event roster exceeds registered production ceiling; no player truncation")
        provisional.append(_event_plan(row,candidates,"0"*64,policy))
    common.require(len(provisional) <= policy["maximum_events_per_game_date"],"Complete daily event inventory exceeds production ceiling; no event truncation")
    seed=_seed(game_date,sources,producer_binding,provisional,policy)
    for event in provisional:event["cycle_id"]=common.cycle_id(game_date,event["event"]["event_id"],seed)
    body={"schema_version":common.PLAN_SCHEMA,"protocol_id":common.PROTOCOL_ID,"mode":mode,"policy":policy,"game_date":game_date,
        "planning_started_at":stamp(started),"planned_at":stamp(completed),"plan_seed":seed,"sources":sources,"inventory":inventory,"events":provisional,
        "exclusions":excluded,"source_schedule_rows":len(schedule),"outside_game_date_rows":len(schedule)-len(inventory),"producer_binding":deepcopy(producer_binding),
        **_history(),"missing_information":_missing(sources),"qualification":"UNAVAILABLE"}
    return validate_plan(common.seal(body,"plan_id"))


def make_plan(schedule_raw,roster_raw,schedule_meta,roster_meta,*,source_originals,game_date,producer_binding,at=None,mode="DEVELOPMENT_ONLY",policy=None):
    common.require(at is None or mode == "DEVELOPMENT_ONLY","Prospective planning cannot accept a supplied clock")
    policy=deepcopy(_policy(policy));started=_source_clock(at) if at is not None else common.now()
    result=_build_plan(schedule_raw,roster_raw,schedule_meta,roster_meta,source_originals=source_originals,game_date=game_date,producer_binding=producer_binding,
        started=started,completed=started,mode=mode,policy=policy)
    completed=started if at is not None else common.now()
    result["planned_at"]=stamp(completed); result=common.seal({key:value for key,value in result.items() if key != "plan_id"},"plan_id")
    validate_plan(result)
    if mode == "PROSPECTIVE_RESEARCH":
        actual=common.now();opens,closes=_planning_window(game_date,policy)
        common.require(opens <= actual and (actual < closes if policy.get("planning_close_exclusive",False) else actual <= closes),
            "Production plan admission missed its planning window")
    return result


def _validate_event(event):
    common.exact(event,EVENT_FIELDS,"normalized event")
    for key in ("event_id","home_team_id","away_team_id"):_id(event[key])
    for key in ("home_team_name","away_team_name"):common.text(event[key])
    common.require(event["id_namespace"] == "espn" and event["league"] == "NBA" and event["home_team_id"] != event["away_team_id"]
        and type(event["season_ending_year"]) is int and 2000 <= event["season_ending_year"] <= 2099 and event["season_type"] in {"1","2","3"}
        and event["status"] == "SCHEDULED" and event["provider_event_revision"] is None,"Wrong production event semantics")
    common.clock(event["event_starts_at"]);common.check_seal(event,"event_snapshot_id")


def _validate_candidates(candidates,event,policy=None):
    policy=_policy(policy);common.require(type(candidates) is list and 1 <= len(candidates) <= policy["maximum_players_per_event"],"Invalid complete production cohort")
    seen=set();ordering=[]
    for candidate in candidates:
        common.exact(candidate,CANDIDATE_FIELDS,"candidate");pid=_id(candidate["player_id"]);common.text(candidate["player_label"])
        team,opponent=_id(candidate["team_id"]),_id(candidate["opponent_id"])
        common.require(pid not in seen and team != opponent and {team,opponent} == {event["home_team_id"],event["away_team_id"]},"Production candidate identity conflicts")
        seen.add(pid); ordering.append((0 if team == event["home_team_id"] else 1,int(pid)))
    common.require(ordering == sorted(ordering) and all(any(player["team_id"] == team for player in candidates) for team in (event["home_team_id"],event["away_team_id"])),"Production full cohort order/team coverage differs")


def _validate_shards(shards,candidates,policy=None):
    size=_policy(policy)["players_per_shard"];ids=[row["player_id"] for row in candidates]
    common.require(type(shards) is list and shards == [ids[index:index+size] for index in range(0,len(ids),size)],"Production shards must cover every candidate exactly once in deterministic order")


def _common(body):
    common.require(body["protocol_id"] == common.PROTOCOL_ID and type(body["mode"]) is str and body["mode"] in MODES and body["qualification"] == "UNAVAILABLE","Wrong production input scope")
    common.validate_policy(body["policy"]);validate_binding(body["producer_binding"],prospective=body["mode"] == "PROSPECTIVE_RESEARCH")
    common.require(all(body[key] == value and type(body[key]) is type(value) for key,value in _history().items()),"Production fixed history changed")
    common.require(type(body["sources"]) is list and len(body["sources"]) == 2,"Production source inventory differs")
    for role,source in zip(("schedule","roster"),body["sources"]):validate_source_metadata(source,role=role,prospective=body["mode"] == "PROSPECTIVE_RESEARCH",policy=body["policy"])
    common.require(body["missing_information"] == _missing(body["sources"]),"Production missing information was hidden")


def validate_plan(body):
    common.exact(body,PLAN_FIELDS,"plan");_common(body);day=_date(body["game_date"])
    common.require(body["schema_version"] == common.PLAN_SCHEMA,"Wrong production plan type")
    started,completed=(common.clock(body[key]) for key in ("planning_started_at","planned_at"))
    common.require(started <= completed <= common.now(),"Production planning completion clocks conflict")
    policy=body["policy"]
    if policy["schema_version"] == common.POLICY_SCHEMA_V2:
        common.require(day >= common.clock(policy["enabled_after"]).date(),"Production v2 game date precedes its future-only effective date")
    if body["mode"] == "PROSPECTIVE_RESEARCH":
        opens,closes=_planning_window(body["game_date"],policy)
        closing_ok=completed < closes if policy.get("planning_close_exclusive",False) else completed <= closes
        common.require(opens <= started <= completed and closing_ok and day >= common.clock(policy["enabled_after"]).date(),"Production plan missed its declared daily window/effective date")
        if policy.get("planning_close_exclusive",False):
            for source in body["sources"]:
                common.require(opens <= common.clock(source["metadata_retrieval_started_at"])
                    <= common.clock(source["metadata_retrieved_at"]) <= common.clock(source["retrieval_started_at"])
                    <= common.clock(source["retrieved_at"]) <= started,
                    "Production v2 planning sources missed the actual planning capture window")
    for source in body["sources"]:validate_source_metadata(source,at=completed,prospective=body["mode"] == "PROSPECTIVE_RESEARCH",policy=policy)
    inventory=body["inventory"]
    common.require(type(inventory) is list and len(inventory) <= body["policy"]["maximum_source_rows"]
        and type(body["source_schedule_rows"]) is int and 0 < body["source_schedule_rows"] <= body["policy"]["maximum_source_rows"]
        and type(body["outside_game_date_rows"]) is int and body["outside_game_date_rows"] >= 0
        and len(inventory)+body["outside_game_date_rows"] == body["source_schedule_rows"],"Production full-inventory counts differ")
    ordering=[];eligible=[]
    for row in inventory:
        common.exact(row,INVENTORY_FIELDS,"inventory row");eid=_id(row["event_id"]);start=common.clock(row["event_starts_at"])
        common.require(start.date() == day and type(row["eligible"]) is bool and type(row["exclusion_reasons"]) is list
            and all(type(reason) is str and reason in EXCLUSION_REASONS for reason in row["exclusion_reasons"])
            and len(row["exclusion_reasons"]) == len(set(row["exclusion_reasons"])),"Invalid production event exclusions")
        _id(row["home_team_id"]);_id(row["away_team_id"]);common.require(row["home_team_id"] != row["away_team_id"],"Inventory team identities conflict")
        for key in ("status_type_name","status_type_state"):common.text(row[key])
        common.require(row["time_valid"] in {"true","false"} and row["status_type_completed"] in {"true","false"},"Invalid inventory event state")
        reasons=[]
        if (row["status_type_name"],row["status_type_state"],row["status_type_completed"]) != ("STATUS_SCHEDULED","pre","false"):reasons.append("NOT_SCHEDULED")
        if row["time_valid"] != "true":reasons.append("INVALID_START_FLAG")
        if start <= completed:reasons.append("NOT_FUTURE")
        common.require(row["exclusion_reasons"] in (reasons,reasons+["NO_ACTIVE_TEAM_ROSTER"])
            and row["eligible"] == (not row["exclusion_reasons"]),"Production inventory facts contradict exclusions")
        ordering.append((start,int(eid)))
        if row["eligible"]:eligible.append(eid)
    common.require(ordering == sorted(ordering) and len({eid for _,eid in ordering}) == len(ordering),"Production complete inventory order/identities differ")
    events=body["events"]
    common.require(type(events) is list and len(events) <= body["policy"]["maximum_events_per_game_date"],"Production event ceiling exceeded")
    for event in events:common.exact(event,PLAN_EVENT_FIELDS,"planned event");_validate_event(event["event"])
    common.require([row["event"]["event_id"] for row in events] == eligible,"Production plan omitted a valid eligible event")
    for selected in events:
        event=selected["event"];_validate_candidates(selected["candidates"],event,policy);_validate_shards(selected["shards"],selected["candidates"],policy)
        row=next(item for item in inventory if item["event_id"] == event["event_id"])
        common.require(all(event[key] == row[key] for key in ("event_id","event_starts_at","home_team_id","away_team_id")),"Planned event differs from complete inventory")
        cutoff=common.clock(event["event_starts_at"])-timedelta(minutes=90)
        common.require(selected["cutoff_at"] == stamp(cutoff) and selected["capture_opens_at"] == stamp(cutoff-timedelta(seconds=policy["capture_lookback_seconds"]))
            and selected["issuance_closes_at"] == stamp(cutoff+timedelta(seconds=body["policy"]["generation_window_seconds"]))
            and selected["cycle_id"] == common.cycle_id(body["game_date"],event["event_id"],body["plan_seed"]),"Production event windows/cycle identity changed")
    common.require(body["plan_seed"] == _seed(body["game_date"],body["sources"],body["producer_binding"],events,policy),"Production immutable plan seed changed")
    common.require(type(body["exclusions"]) is list and all(type(row) is dict for row in body["exclusions"]),"Invalid production exclusions inventory")
    excluded_events=[];excluded_players=set()
    for exclusion in body["exclusions"]:
        common.require(exclusion.get("reason") in {"EVENT_EXCLUDED","SOURCE_ROSTER_NOT_ACTIVE"},"Unknown production exclusion reason")
        rows=[row for row in inventory if row["event_id"] == exclusion.get("event_id")]
        common.require(len(rows) == 1,"Production exclusion is outside the complete game-date inventory")
        row=rows[0]
        if exclusion["reason"] == "EVENT_EXCLUDED":
            common.exact(exclusion,{"event_id","reason","reasons"},"excluded event")
            common.require(not row["eligible"] and exclusion["reasons"] == row["exclusion_reasons"],"Production excluded-event meaning differs")
            excluded_events.append(exclusion["event_id"])
        else:
            common.exact(exclusion,{"event_id","player_id","team_id","reason"},"excluded player")
            _id(exclusion["player_id"]);_id(exclusion["team_id"])
            key=(exclusion["event_id"],exclusion["player_id"])
            common.require(key not in excluded_players and exclusion["team_id"] in {row["home_team_id"],row["away_team_id"]}
                and not any(player["player_id"] == exclusion["player_id"] for event in events if event["event"]["event_id"] == exclusion["event_id"] for player in event["candidates"]),
                "Production excluded-player identity conflicts with the admitted active cohort")
            excluded_players.add(key)
    common.require(excluded_events == [row["event_id"] for row in inventory if not row["eligible"]],"Production plan dropped or duplicated event exclusions")
    common.check_seal(body,"plan_id");return body


def make_input(plan,event_id,schedule_raw,roster_raw,schedule_meta,roster_meta,*,source_originals,at=None,mode="DEVELOPMENT_ONLY"):
    common.require(at is None or mode == "DEVELOPMENT_ONLY","Prospective normalization cannot accept a supplied clock")
    validate_plan(plan);common.require(mode == plan["mode"],"Production input changed its plan evidence lane")
    selected=[row for row in plan["events"] if row["event"]["event_id"] == event_id]
    common.require(len(selected) == 1,"Event is outside the fixed full daily plan; no replacements")
    original=selected[0]; started=_source_clock(at) if at is not None else common.now()
    policy=plan["policy"]
    _sources((schedule_raw,roster_raw),(schedule_meta,roster_meta),source_originals,at=started,mode=mode,policy=policy)
    schedule,roster=_tables(schedule_raw,roster_raw,policy); season=schedule[0]["season"]
    common.require(schedule_meta["asset_name"] == "nba_schedule_"+season+".csv" and roster_meta["asset_name"] == "rosters_"+season+".csv","Fresh production asset/table season conflicts")
    rows=[row for row in schedule if row["id"] == event_id];common.require(len(rows) == 1,"Fresh selected event is absent")
    row=rows[0];common.require((row["status_type_name"],row["status_type_state"],row["status_type_completed"],row["time_valid"]) == ("STATUS_SCHEDULED","pre","false","true"),"Fresh production event is not scheduled")
    candidates,_=_cohort(row,roster)
    common.require(_event(row) == original["event"] and candidates == original["candidates"],"Fresh event version/cohort changed; no replacement subjects or shifted windows")
    completed=started if at is not None else common.now()
    body={"schema_version":common.INPUT_SCHEMA,"protocol_id":common.PROTOCOL_ID,"mode":mode,"policy":deepcopy(plan["policy"]),
        "plan_id":plan["plan_id"],"plan_seed":plan["plan_seed"],"cycle_id":original["cycle_id"],"event":deepcopy(original["event"]),
        "candidates":deepcopy(candidates),"shards":deepcopy(original["shards"]),"sources":[deepcopy(schedule_meta),deepcopy(roster_meta)],"producer_binding":deepcopy(plan["producer_binding"]),
        **_history(),"normalization_started_at":stamp(started),"normalized_at":stamp(completed),"missing_information":_missing((schedule_meta,roster_meta)),"qualification":"UNAVAILABLE"}
    result=validate_input(common.seal(body,"input_id"),plan)
    if mode == "PROSPECTIVE_RESEARCH":common.require(common.now() <= common.clock(original["cutoff_at"]),"Production input admission completed after cutoff")
    return result


def validate_input(body,plan=None):
    common.exact(body,INPUT_FIELDS,"input");_common(body)
    common.require(body["schema_version"] == common.INPUT_SCHEMA,"Wrong production input type")
    for key in ("plan_id","plan_seed"):common.sha(body[key])
    policy=body["policy"]
    _validate_event(body["event"]);_validate_candidates(body["candidates"],body["event"],policy);_validate_shards(body["shards"],body["candidates"],policy)
    event=body["event"];start=common.clock(event["event_starts_at"]);cutoff=start-timedelta(minutes=90)
    if policy["schema_version"] == common.POLICY_SCHEMA_V2:
        common.require(start.date() >= common.clock(policy["enabled_after"]).date(),
            "Production v2 input precedes its future-only effective date")
    begun,completed=(common.clock(body[key]) for key in ("normalization_started_at","normalized_at"))
    common.require(begun <= completed <= common.now() and completed < start,"Production actual normalization clocks conflict or are post-start")
    common.require(body["cycle_id"] == common.cycle_id(start.date().isoformat(),event["event_id"],body["plan_seed"]),"Production event cycle identity differs")
    for source in body["sources"]:
        validate_source_metadata(source,at=completed,prospective=body["mode"] == "PROSPECTIVE_RESEARCH",policy=policy)
        common.require(source["asset_name"] == ("nba_schedule_" if source["role"] == "schedule" else "rosters_")+str(event["season_ending_year"])+".csv","Production input asset season differs")
        if body["mode"] == "PROSPECTIVE_RESEARCH":
            lower=cutoff-timedelta(seconds=body["policy"]["capture_lookback_seconds"])
            common.require(lower <= common.clock(source["metadata_retrieval_started_at"]) <= common.clock(source["metadata_retrieved_at"])
                <= common.clock(source["retrieval_started_at"]) <= common.clock(source["retrieved_at"]) <= begun <= completed <= cutoff,
                "Production actual fresh input missed pre-cutoff capture/normalization window")
    if plan is not None:
        validate_plan(plan)
        selected=[row for row in plan["events"] if row["cycle_id"] == body["cycle_id"]]
        common.require(len(selected) == 1 and body["plan_id"] == plan["plan_id"] and body["plan_seed"] == plan["plan_seed"]
            and body["mode"] == plan["mode"] and body["policy"] == plan["policy"] and body["producer_binding"] == plan["producer_binding"]
            and all(body[key] == selected[0][key] for key in ("event","candidates","shards")),"Production input differs from its frozen plan/cohort/producer")
    common.check_seal(body,"input_id");return body


def freshness(body,*,at,require_retrieval_window=False):
    validate_input(body);actual=_source_clock(at);start=common.clock(body["event"]["event_starts_at"]);cutoff=start-timedelta(minutes=90)
    common.require(type(require_retrieval_window) is bool,"Invalid production freshness control")
    common.require(common.clock(body["normalized_at"]) <= actual < start,"Production source input is future-dated or game has started")
    ages={}
    for source in body["sources"]:
        validate_source_metadata(source,at=actual,prospective=body["mode"] == "PROSPECTIVE_RESEARCH",policy=body["policy"])
        ages[source["role"]]={"publisher_age_seconds":(actual-common.clock(source["publisher_updated_at"])).total_seconds(),
            "retrieval_age_seconds":(actual-common.clock(source["retrieved_at"])).total_seconds(),"upstream_observation_status":source["upstream_observation_status"],
            "upstream_age_seconds":None if source["upstream_observed_at"] is None else (actual-common.clock(source["upstream_observed_at"])).total_seconds()}
    if require_retrieval_window:
        common.require(body["mode"] == "PROSPECTIVE_RESEARCH" and cutoff <= actual <= cutoff+timedelta(seconds=body["policy"]["generation_window_seconds"]),"Production generation window is not open or has closed")
    return {"policy_id":body["policy"]["policy_id"],"cutoff_at":stamp(cutoff),"forecast_horizon_seconds":(start-actual).total_seconds(),"sources":ages}


def verify_plan_sources(body,schedule_raw,roster_raw,schedule_meta,roster_meta,*,source_originals):
    """Read-only complete-byte replay; original completion clocks never change."""
    validate_plan(body)
    replay=_build_plan(schedule_raw,roster_raw,schedule_meta,roster_meta,source_originals=source_originals,game_date=body["game_date"],producer_binding=body["producer_binding"],
        started=common.clock(body["planning_started_at"]),completed=common.clock(body["planned_at"]),mode=body["mode"],policy=body["policy"])
    common.require(replay == body,"Production plan differs from exact source replay")
    return body


def verify_input_sources(body,schedule_raw,roster_raw,schedule_meta,roster_meta,*,source_originals,plan=None):
    validate_input(body,plan)
    _sources((schedule_raw,roster_raw),(schedule_meta,roster_meta),source_originals,at=common.clock(body["normalized_at"]),mode=body["mode"],policy=body["policy"])
    common.require(body["sources"] == [schedule_meta,roster_meta],"Production input original source metadata changed")
    schedule,roster=_tables(schedule_raw,roster_raw,body["policy"])
    selected=[row for row in schedule if row["id"] == body["event"]["event_id"]]
    common.require(len(selected) == 1 and _event(selected[0]) == body["event"] and _cohort(selected[0],roster)[0] == body["candidates"],"Production input semantics differ from original source replay")
    row=selected[0]
    common.require((row["status_type_name"],row["status_type_state"],row["status_type_completed"],row["time_valid"]) == ("STATUS_SCHEDULED","pre","false","true"),"Recovered production event was not scheduled")
    return body

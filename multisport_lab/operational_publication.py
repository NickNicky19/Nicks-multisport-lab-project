"""Separate OP002 publication of retained originals; no activation or scores aggregate."""
from __future__ import annotations

from datetime import timedelta
import hashlib
import json
from pathlib import Path
import re

from .integrity import IntegrityError, canonical, digest, load_json, stamp, utc
from .ledger import LedgerRef
from . import operational_pilot as pilot

SCHEMA = "nba-operational-paired-publication-v1"
MAX_ASSET_BYTES = 1024 * 1024
ENCODING = "CANONICAL_ORIGINAL_BODY_WITHOUT_ID"
COUNTS = {"forecasts","eligible_forecasts","outcomes","grades","pending_grades","missing_peers"}
CLOCKS = {"last_source_capture_at","last_issuance_at","last_grade_at"}


def original_record(row):
    pilot.exact(row,{"kind","source_record","record_encoding","original_id","record_json","admission"},"public original")
    kind=row["kind"]
    pilot.require(kind in {"event","forecast","outcome","grade"} and row["record_encoding"] == ENCODING
        and type(row["record_json"]) is str,"invalid public original encoding")
    raw=row["record_json"].encode("utf-8");pilot.sha(row["original_id"])
    pilot.require(hashlib.sha256(raw).hexdigest() == row["original_id"],"public original hash mismatch")
    try: body=json.loads(raw)
    except (ValueError,UnicodeDecodeError) as exc: raise IntegrityError("invalid public original JSON") from exc
    id_key="event_input_id" if kind == "event" else kind+"_id"
    pilot.require(type(body) is dict and canonical(body) == raw and id_key not in body,
        "public original is not canonical or contains a replacement identity")
    ref=LedgerRef.from_record(row["source_record"])
    pilot.require(ref.kind == pilot.KIND[kind],"public original receipt kind conflict")
    return {**body,id_key:row["original_id"]}


def _project(ref,body,admission=None):
    kind=next(name for name in ("event","forecast","outcome","grade") if body["schema_version"] == pilot._schema(name))
    id_key="event_input_id" if kind == "event" else kind+"_id"
    return {"kind":kind,"source_record":ref.to_record(),"record_encoding":ENCODING,
        "original_id":body[id_key],"record_json":canonical({k:v for k,v in body.items() if k != id_key}).decode("utf-8"),
        "admission":admission}


def active_grades(asset):
    superseded={row["original_id"] for row in asset["corrections"] if row["kind"] == "grade"}
    old_outcomes={row["original_id"] for row in asset["corrections"] if row["kind"] == "outcome"}
    return [row for row in asset["grades"] if row["original_id"] not in superseded
        and original_record(row)["outcome_id"] not in old_outcomes]


def _validate_admission(value,body,now):
    pilot.exact(value,{"retained","eligible","local_persistence_completed_at","remote_checkpoint_completed_at",
        "final_recovery_completed_at","reasons"},"public admission")
    pilot.require(value["retained"] is True and type(value["eligible"]) is bool and type(value["reasons"]) is list
        and len(value["reasons"]) <= 16,"invalid public admission status")
    for reason in value["reasons"]:pilot.text(reason)
    is_input=body["schema_version"] == pilot._schema("event")
    started=None if is_input else pilot.clock(body["generation_started_at"])
    issued=pilot.clock(body["imported_at"] if is_input else body["issued_at"])
    values=[]
    for key in ("local_persistence_completed_at","remote_checkpoint_completed_at","final_recovery_completed_at"):
        current=value[key]
        if current is None:values.append(None)
        else:
            actual=pilot.clock(current);pilot.require(issued <= actual <= utc(now),"public persistence clock conflict");values.append(actual)
    if values[1] is not None:pilot.require(values[0] is not None and values[0] <= values[1],"remote completion precedes local completion")
    if values[2] is not None:pilot.require(values[1] is not None and values[1] <= values[2],"final recovery precedes remote completion")
    if value["eligible"]:
        deadline=pilot.clock(body["event"]["event_starts_at"])-timedelta(minutes=100) if is_input else pilot.clock(body["cutoff_at"])+timedelta(seconds=300)
        pilot.require(all(item is not None for item in values) and not value["reasons"]
            and values[-1] <= deadline and (started is None or values[-1]-started <= timedelta(seconds=120)),
            "public eligibility lacks timely actual completion")
    else:pilot.require(bool(value["reasons"]),"unadmitted original lacks an explanation")


def validate_asset(asset,*,now):
    pilot.exact(asset,{"schema_version","protocol_id","generated_at","status","reason","counts","clocks",
        "inputs","forecasts","outcomes","grades","corrections","missing_peers","qualification","financial_settlement","asset_id"},"public asset")
    pilot.require(asset["schema_version"] == SCHEMA and asset["protocol_id"] == pilot.PROTOCOL_ID
        and asset["status"] in {"INACTIVE","ISSUED","PARTIAL","COMPLETED"}
        and asset["qualification"] == "UNAVAILABLE" and asset["financial_settlement"] == "NOT_EVALUATED",
        "wrong OP002 public scope/status")
    pilot.text(asset["reason"]);generated=pilot.clock(asset["generated_at"])
    pilot.require(generated <= utc(now),"future public generation clock")
    pilot.exact(asset["counts"],COUNTS,"public counts");pilot.exact(asset["clocks"],CLOCKS,"public clocks")
    pilot.require(all(type(value) is int and value >= 0 for value in asset["counts"].values()),"invalid public counts")
    for value in asset["clocks"].values():
        if value is not None:pilot.require(pilot.clock(value) <= generated,"public evidence clock follows publication")
    forecasts={};outcomes={};grades={};subjects=set();inputs={}
    pilot.require(type(asset["inputs"]) is list and len(asset["inputs"]) <= 1,"one exact compact public input required")
    observations=[]
    for row in asset["inputs"]:
        body=original_record(row);pilot.require(row["kind"] == "event" and body["mode"] == "REAL_TIME_CAPTURED", "diagnostic public input")
        pilot.validate_event(body);_validate_admission(row["admission"],body,now)
        pilot.require(not row["admission"]["eligible"],"OP002 activation is not installed")
        inputs[digest(row["source_record"])]=body;observations.extend(source["observed_at"] for source in body["sources"])
    for plural,limit,index in (("forecasts",8,forecasts),("outcomes",32,outcomes),("grades",32,grades)):
        rows=asset[plural];pilot.require(type(rows) is list and len(rows) <= limit,"public record capacity exceeded")
        for row in rows:
            body=original_record(row);kind=plural[:-1]
            pilot.require(row["kind"] == kind and body.get("schema_version") == pilot._schema(kind)
                and body.get("protocol_id") == pilot.PROTOCOL_ID and body.get("mode") == "REAL_TIME_CAPTURED",
                "diagnostic/other-study records cannot be public prospective outputs")
            key=body[kind+"_id"];pilot.require(key not in index,"duplicate public original");index[key]=(row,body)
            if kind == "forecast":
                pilot.validate_forecast_record(body);pilot.require(body["producer_binding"]["verification"] == "VERIFIED_COMMIT",
                    "public producer source commit was not verified")
                event=inputs.get(digest(body["event_ref"]));pilot.require(event is not None,"public forecast lacks exact compact input evidence")
                pilot.validate_forecast_record(body,event)
                _validate_admission(row["admission"],body,now)
                subject=(body["event_id"],body["player_id"],body["model_key"])
                pilot.require(subject not in subjects,"duplicate original subject/model");subjects.add(subject)
            else:pilot.require(row["admission"] is None,"outcomes/grades cannot replace issuance admission")
            if kind == "outcome":pilot.validate_outcome(body)
    for _,grade in grades.values():
        pilot.require(grade.get("forecast_id") in forecasts and grade.get("outcome_id") in outcomes,"public grade has missing original evidence")
        forecast=forecasts[grade["forecast_id"]][1];outcome=outcomes[grade["outcome_id"]][1]
        pilot.require(grade == pilot.make_grade(forecast,outcome,graded_at=grade["graded_at"]),"public grade is statistically inconsistent")
    for _,outcome in outcomes.values():
        pilot.require(any(all(outcome[key] == forecast[key] for key in
            ("event_id","event_version","event_starts_at","player_id","team_id","opponent_id","mode"))
            and pilot.clock(forecast["issued_at"]) <= pilot.clock(outcome["source_observed_at"])
            for _,forecast in forecasts.values()),"ungraded public outcome differs from every retained original")
    pilot.require(not any(row["admission"]["eligible"] for row,_ in forecasts.values()),
        "OP002 readiness revision has no installed reviewed activation; public eligibility is unavailable")
    corrections=asset["corrections"];pilot.require(type(corrections) is list and len(corrections) <= 16,"public correction budget exceeded")
    graph={};targets={}
    for correction in corrections:
        pilot.exact(correction,{"kind","original_id","replacement_id","reason","source_record"},"public correction")
        pilot.require(correction["kind"] in {"outcome","grade"},"only statistical evidence can be corrected")
        for key in ("original_id","replacement_id"):pilot.sha(correction[key])
        pilot.text(correction["reason"])
        pilot.require(LedgerRef.from_record(correction["source_record"]).kind == "corrections","correction source kind differs")
        index=grades if correction["kind"] == "grade" else outcomes
        before=index.get(correction["original_id"]);after=index.get(correction["replacement_id"])
        pilot.require(before is not None and after is not None and correction["original_id"] != correction["replacement_id"]
            and correction["original_id"] not in graph,"missing/conflicting correction originals")
        pilot.require(pilot._identity(before[1]) == pilot._identity(after[1]) and before[1]["mode"] == after[1]["mode"],
            "public correction changes original subject")
        if correction["kind"] == "grade":pilot.require(before[1]["forecast_id"] == after[1]["forecast_id"],"grade correction changes forecast")
        graph[correction["original_id"]]=correction["replacement_id"]
    for key in graph:
        seen=set();cursor=key
        while cursor in graph:
            pilot.require(cursor not in seen,"public correction cycle");seen.add(cursor);cursor=graph[cursor]
    identities={(body["event_id"],body["event_version"],body["event_starts_at"],body["plan_id"],digest(body["producer_binding"]),digest(body["event_ref"]))
        for _,body in forecasts.values()}
    pilot.require(len(identities) <= 1,"public paired originals disagree on fixed event/input/source")
    missing=asset["missing_peers"];pilot.require(type(missing) is list and len(missing) <= 8,"invalid public missing peers")
    missingkeys=set()
    for peer in missing:
        pilot.exact(peer,{"player_id","model_key"},"missing peer")
        pilot.text(peer["player_id"]);pilot.require(peer["model_key"] in pilot.MODEL_VERSIONS,"unknown missing peer model")
        key=(peer["player_id"],peer["model_key"]);pilot.require(key not in missingkeys,"duplicate missing peer");missingkeys.add(key)
        pilot.require(not any(body["player_id"] == key[0] and body["model_key"] == key[1] for _,body in forecasts.values()),
            "retained model cannot also be missing")
    retained_peers={(body["player_id"],body["model_key"]) for _,body in forecasts.values()}
    registered_peers={(candidate["player_id"],model) for event in inputs.values()
        for candidate in event["candidates"] for model in pilot.MODEL_VERSIONS}
    pilot.require(missingkeys == registered_peers-retained_peers,
        "public missing peers differ from exact fixed input cohort minus retained originals")
    active=active_grades(asset)
    active_forecasts=set()
    for row in active:
        grade=original_record(row)
        pilot.require(grade["forecast_id"] not in active_forecasts,"multiple uncorrected active grades for one forecast")
        active_forecasts.add(grade["forecast_id"])
        pilot.require(grade["outcome_id"] not in graph,"active grade references a superseded outcome; append its correction before publication")
    scored={original_record(row)["forecast_id"] for row in active if original_record(row)["status"] in {"SCORED","DNP_NOT_SCORED"}}
    expected={"forecasts":len(forecasts),"eligible_forecasts":sum(row["admission"]["eligible"] for row,_ in forecasts.values()),
        "outcomes":len(outcomes),"grades":len(grades),"pending_grades":len(set(forecasts)-scored),"missing_peers":len(missing)}
    pilot.require(asset["counts"] == expected,"public counts differ from exact records")
    clocks={"last_source_capture_at":max(observations,default=None),
        "last_issuance_at":max((body["issued_at"] for _,body in forecasts.values()),default=None),
        "last_grade_at":max((body["graded_at"] for _,body in grades.values()),default=None)}
    pilot.require(asset["clocks"] == clocks,"public summary clocks differ from original records")
    if not forecasts:pilot.require(asset["status"] == "INACTIVE","empty public asset cannot claim issuance")
    elif len(forecasts) < 8 or expected["eligible_forecasts"] < 8:pilot.require(asset["status"] == "PARTIAL","partial records cannot claim full completion")
    elif expected["pending_grades"]:pilot.require(asset["status"] == "ISSUED","ungraded originals must remain pending")
    else:pilot.require(asset["status"] == "COMPLETED","completed statistical records have wrong state")
    pilot.check_seal(asset,"asset_id")
    pilot.require(len(canonical(asset)) <= MAX_ASSET_BYTES,"complete OP002 asset exceeds 1-MiB publication budget")
    return asset


def make_asset(root,*,now):
    store=pilot.OperationalStore(root);recovery=store.recover(replay=False)
    forecasts=[];outcomes=[];grades=[];sources=[];corrections=[];inputs=[]
    for ref,body in recovery["records"]:
        if body["mode"] != "REAL_TIME_CAPTURED":continue
        schema=body["schema_version"]
        if schema == pilot._schema("forecast"):forecasts.append(_project(ref,body,store.admission(ref)))
        elif schema == pilot._schema("outcome"):outcomes.append(_project(ref,body))
        elif schema == pilot._schema("grade"):grades.append(_project(ref,body))
        elif schema == pilot._schema("event"):
            inputs.append(_project(ref,body,store.admission(ref)));sources.extend(row["observed_at"] for row in body["sources"])
    for rows in (forecasts,outcomes,grades):rows.sort(key=lambda row:row["original_id"])
    index=store.ledger.scan()
    for payload in index["corrections"].values():
        old_ref=LedgerRef.from_record(payload["supersedes"]);new_ref=LedgerRef.from_record(payload["data"]["replacement"])
        old=index[old_ref.kind][old_ref.record_id]["data"].get("operational")
        if old is None or old["mode"] != "REAL_TIME_CAPTURED":continue
        new=index[new_ref.kind][new_ref.record_id]["data"]["operational"];kind="grade" if old_ref.kind == "grades" else "outcome"
        corrections.append({"kind":kind,"original_id":old[kind+"_id"],"replacement_id":new[kind+"_id"],
            "reason":payload["data"]["reason"],"source_record":LedgerRef("corrections",payload["record_id"],digest(payload)).to_record()})
    corrections.sort(key=lambda row:row["original_id"])
    final={original_record(row)["forecast_id"] for row in active_grades({"grades":grades,"corrections":corrections})
        if original_record(row)["status"] in {"SCORED","DNP_NOT_SCORED"}}
    counts={"forecasts":len(forecasts),"eligible_forecasts":sum(row["admission"]["eligible"] for row in forecasts),
        "outcomes":len(outcomes),"grades":len(grades),"pending_grades":len(forecasts)-len(final),
        "missing_peers":len(recovery["missing"]) if inputs else 0}
    status="INACTIVE" if not forecasts else "PARTIAL" if len(forecasts) < 8 or counts["eligible_forecasts"] < 8 else "ISSUED" if counts["pending_grades"] else "COMPLETED"
    reasons={"INACTIVE":"This one-game research pilot is prepared but inactive. No genuinely issued forecasts have been retained for it.",
        "PARTIAL":"Only part of the fixed paired cohort was retained on time. Originals remain visible; missing or late peers are not replaced.",
        "ISSUED":"Pregame research originals are retained. Verified final player results and statistical grades are still pending.",
        "COMPLETED":"Original pregame research forecasts and their verified individual statistical grades are retained. This is not betting qualification."}
    def latest(rows,key):return max((original_record(row)[key] for row in rows),default=None)
    asset=pilot.seal({"schema_version":SCHEMA,"protocol_id":pilot.PROTOCOL_ID,"generated_at":stamp(now),"status":status,
        "reason":reasons[status],"counts":counts,"clocks":{"last_source_capture_at":max(sources,default=None),
            "last_issuance_at":latest(forecasts,"issued_at"),"last_grade_at":latest(grades,"graded_at")},
        "inputs":inputs,"forecasts":forecasts,"outcomes":outcomes,"grades":grades,"corrections":corrections,"missing_peers":recovery["missing"] if inputs else [],
        "qualification":"UNAVAILABLE","financial_settlement":"NOT_EVALUATED"},"asset_id")
    return validate_asset(asset,now=now)


def emit_publication(data_dir,root,*,now):
    asset=make_asset(root,now=now);raw=canonical(asset);checksum=hashlib.sha256(raw).hexdigest()
    directory=Path(data_dir);directory.mkdir(parents=True,exist_ok=True)
    filename="paired-research."+checksum+".json";path=directory/filename
    if path.exists():pilot.require(path.read_bytes() == raw,"conflicting immutable paired asset")
    else:path.write_bytes(raw)
    return {"path":filename,"sha256":checksum,"generated_at":stamp(now),"status":"RESEARCH_ONLY","retained":False,"error":None}


def read_asset(data_dir,descriptor,*,now):
    pilot.exact(descriptor,{"path","sha256","generated_at","status","retained","error"},"public descriptor")
    pilot.sha(descriptor["sha256"])
    pilot.require(descriptor["path"] == "paired-research."+descriptor["sha256"]+".json"
        and descriptor["status"] == "RESEARCH_ONLY" and type(descriptor["retained"]) is bool
        and (descriptor["error"] is None or type(descriptor["error"]) is str and 0 < len(descriptor["error"]) <= 2048
            and descriptor["error"].strip() == descriptor["error"]),"invalid paired asset descriptor")
    pilot.require(pilot.clock(descriptor["generated_at"]) <= utc(now),"future paired descriptor clock")
    path=Path(data_dir)/descriptor["path"]
    pilot.require(not path.is_symlink() and path.stat().st_size <= MAX_ASSET_BYTES,"invalid paired asset file")
    raw=path.read_bytes();pilot.require(hashlib.sha256(raw).hexdigest() == descriptor["sha256"],"paired asset bytes changed")
    asset=load_json(path,max_bytes=MAX_ASSET_BYTES)
    pilot.require(canonical(asset) == raw and asset["generated_at"] == descriptor["generated_at"],"paired asset publication metadata differs")
    return validate_asset(asset,now=now)

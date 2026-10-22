"""First-cycle genuine statistical grading over separately admitted final CSVs.

No collector, scheduler, trading or forecast generator lives here. Original
probabilities and producer files are untouched. Project-authored proof receipts
retain the actual publisher/review/config bytes and separate source clocks.
"""
from __future__ import annotations

import base64
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import subprocess

from .integrity import IntegrityError, canonical, digest, stamp, utc, _decode
from .integrity import RECEIPT_SCHEMA, HASH_FORMAT
from .ledger import LedgerRef
from . import sdv_daily_cycle as cycles
from . import sdv_daily_producer as producer
from . import sdv_daily_outcomes as outcomes
from . import sdv_daily_store as storage
from . import sdv_daily_runner as runner
from .nba_data import normalize_sdv_row, with_sdv_schedule

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH="config/sdv_final_admission_v1.json"
CONFIG_SCHEMA="nba-sdv-final-admission-config-v1"
PROOF_SCHEMA="nba-sdv-final-source-proof-v1"
PROOF_KIND="Project-authored SDV final-source proof v1"
FIRST_PRODUCER="0c37b30060c2dffb20226bd3efbedc65a75d04e3"
MAX_PROOF_RAW=1024*1024
MAX_PROOF_ENVELOPE=1536*1024
MAX_CSV_ENVELOPE=3*1024*1024
TERMINAL={"APPEARED","DNP"}
CONFIG_FIELDS={"schema_version","protocol_id","cycle_id","admission","season_ending_year",
    "supported_producer_commit","source_review_receipt_path","source_review_receipt_sha256",
    "source_review_payload_sha256","attribution","roles","max_metadata_bytes",
    "max_capture_requests","max_captures","config_id"}
ROLE_FIELDS={"release_tag","metadata_url","asset_name","asset_url","source_kind",
             "required_headers","max_asset_bytes"}
CLOCK_FIELDS={"metadata_retrieval_started_at","metadata_retrieved_at",
              "asset_retrieval_started_at","asset_retrieved_at"}
PROOF_FIELDS={"schema_version","protocol_id","cycle_id","reviewed_commit","config_original_base64",
    "config_original_sha256","review_original_base64","review_original_sha256","config_id",
    "input_ref","forecast_refs","event_id","event_snapshot_id","created_at","sources",
    "requests","proof_id"}
SOURCE_FIELDS={"role","metadata_original_base64","metadata_original_sha256","metadata_original_bytes",
    "asset_url","asset_id","asset_name","asset_bytes","asset_sha256","publisher_updated_at",
    "upstream_observed_at","upstream_observation_status",*CLOCK_FIELDS}


def _now():return datetime.now(timezone.utc)


def require(ok,message):
    if not ok:raise IntegrityError(message)


def _clock(value):
    try:return producer.clock(value)
    except (TypeError,ValueError) as exc:raise IntegrityError("Invalid final-source UTC clock") from exc


def _time(value):
    try:return utc(value)
    except (TypeError,ValueError) as exc:raise IntegrityError("Invalid final-source publisher/event time") from exc


def sha(raw):return hashlib.sha256(raw).hexdigest()


def sealed(body,key):return {**body,key:digest(body)}


def check_seal(body,key):
    require(body.get(key) == digest({k:v for k,v in body.items() if k != key}),"Grading proof checksum differs")


def decode64(value,maximum):
    require(type(value) is str and len(value) <= 4*((maximum+2)//3),"Oversized grading proof original")
    try:raw=base64.b64decode(value,validate=True)
    except (ValueError,TypeError) as exc:raise IntegrityError("Invalid grading proof original encoding") from exc
    require(len(raw) <= maximum,"Oversized grading proof original")
    return raw


def _review(raw,config):
    doc=_decode(raw)
    require(type(doc) is dict and set(doc) == {"schema_version","hash_format","payload_sha256","payload"}
        and doc["schema_version"] == RECEIPT_SCHEMA and doc["hash_format"] == HASH_FORMAT
        and doc["payload_sha256"] == digest(doc["payload"]),"Invalid retained source-use review receipt")
    require(sha(raw) == config["source_review_receipt_sha256"]
        and doc["payload_sha256"] == config["source_review_payload_sha256"]
        and doc["payload"].get("review_status") == "ADMITTED_FINAL_STATISTICAL_GRADING",
        "Final-source review does not admit statistical grading")
    return doc["payload"]


def validate_config(body):
    require(type(body) is dict and set(body) == CONFIG_FIELDS,"Invalid final admission config")
    require(body["schema_version"] == CONFIG_SCHEMA and body["protocol_id"] == producer.PROTOCOL_ID
        and body["cycle_id"] == cycles.CYCLE_ID and body["admission"] == "ADMITTED_FINAL_STATISTICAL_GRADING"
        and body["supported_producer_commit"] == FIRST_PRODUCER and body["season_ending_year"] == 2027,
        "Final grading scope differs from the first approved daily cycle")
    require(body["max_metadata_bytes"] == 262144 and body["max_capture_requests"] == 6
        and type(body["max_captures"]) is int and body["max_captures"] == 2,
        "Final grading operation limits changed")
    path=body["source_review_receipt_path"]
    require(type(path) is str and path.startswith("evidence/data/") and path.endswith(".json")
        and not any(part in {"", ".", ".."} for part in path.split("/")),"Invalid final review path")
    for key in ("source_review_receipt_sha256","source_review_payload_sha256"):producer.sha(body[key])
    require(type(body["attribution"]) is list and body["attribution"]
        and all(type(v) is str and 0 < len(v) <= 2048 for v in body["attribution"]),"Missing final-source attribution")
    require(type(body["roles"]) is dict and set(body["roles"]) == {"schedule","boxscore"},"Wrong final-source roles")
    for role,value in body["roles"].items():
        require(type(value) is dict and set(value) == ROLE_FIELDS,"Invalid final-source role contract")
        tag="espn_nba_schedules" if role == "schedule" else "espn_nba_player_boxscores"
        filename="nba_schedule_2027.csv" if role == "schedule" else "player_box_2027.csv"
        require(value["release_tag"] == tag and value["asset_name"] == filename
            and value["metadata_url"] == "https://api.github.com/repos/sportsdataverse/sportsdataverse-data/releases/tags/"+tag
            and value["asset_url"] == "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"+tag+"/"+filename
            and value["source_kind"] == ("SportsDataverse NBA schedule CSV" if role == "schedule" else "SportsDataverse NBA player boxscore CSV")
            and value["max_asset_bytes"] == storage.MAX_SOURCE_BYTES,"Unadmitted final-source route or bound")
        require(type(value["required_headers"]) is list and len(value["required_headers"]) == len(set(value["required_headers"]))
            and all(type(v) is str and v for v in value["required_headers"]),"Invalid final required columns")
        minimum={"game_id","season","season_type","game_date_time"}
        minimum|={"home_id","away_id","home_score","away_score","status_type_completed","status_type_name","status_type_state"} if role == "schedule" else {
            "athlete_id","team_id","opponent_team_id","did_not_play","minutes","points","team_score","opponent_team_score",*outcomes.SDV_FIELDS.values()}
        require(minimum <= set(value["required_headers"]),"Final role omits required semantic columns")
    check_seal(body,"config_id");return body


def _git_bytes(commit,path):
    result=subprocess.run(["git","show",commit+":"+path],cwd=ROOT,capture_output=True,check=False,timeout=20)
    require(result.returncode == 0,"Reviewed final-source config/review bytes are unavailable")
    return result.stdout


def _trusted_materials(commit=None):
    if commit is None:
        result=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,capture_output=True,text=True,check=False,timeout=20)
        require(result.returncode == 0,"Cannot identify the reviewed grading source")
        commit=result.stdout.strip()
    producer.sha(commit,size=40)
    ancestor=subprocess.run(["git","merge-base","--is-ancestor",commit,"HEAD"],cwd=ROOT,capture_output=True,check=False,timeout=20)
    require(ancestor.returncode == 0,"Final-source review commit is not retained in this source ancestry")
    config_raw=_git_bytes(commit,DEFAULT_CONFIG_PATH)
    require(len(config_raw) <= 32*1024,"Final-source config exceeds bound")
    config=validate_config(_decode(config_raw))
    review_raw=_git_bytes(commit,config["source_review_receipt_path"])
    require(len(review_raw) <= 32*1024,"Final-source admission review exceeds bound")
    _review(review_raw,config)
    return config,config_raw,review_raw,commit


def load_config():return _trusted_materials()[0]


def _source(raw,metadata_raw,clocks,role,config):
    rule=config["roles"][role]
    require(type(raw) is bytes and 0 < len(raw) <= rule["max_asset_bytes"]
        and type(metadata_raw) is bytes and 0 < len(metadata_raw) <= config["max_metadata_bytes"],"Final source exceeds unchanged bounds")
    require(type(clocks) is dict and set(clocks) == CLOCK_FIELDS,"Missing distinct final capture clocks")
    times=[_clock(clocks[key]) for key in ("metadata_retrieval_started_at","metadata_retrieved_at","asset_retrieval_started_at","asset_retrieved_at")]
    require(times == sorted(times) and times[-1] <= _now(),"Final source capture clocks conflict")
    release=_decode(metadata_raw)
    require(type(release) is dict and release.get("tag_name") == rule["release_tag"]
        and type(release.get("assets")) is list,"Wrong final publisher release")
    assets=[row for row in release["assets"] if type(row) is dict and row.get("name") == rule["asset_name"]]
    require(len(assets) == 1,"Missing or duplicate final publisher asset")
    asset=assets[0]
    require(type(asset.get("id")) is int and asset["id"] > 0 and asset.get("size") == len(raw)
        and asset.get("browser_download_url") == rule["asset_url"] and asset.get("digest") == "sha256:"+sha(raw),
        "Final CSV bytes differ from publisher asset identity/hash")
    updated=_time(asset.get("updated_at"))
    require(updated <= times[1],"Final publisher update follows its metadata observation")
    try:rows=outcomes._rows(raw)
    except (UnicodeError,ValueError) as exc:raise IntegrityError("Invalid final-source CSV encoding") from exc
    import csv,io
    fields=csv.DictReader(io.StringIO(raw.decode("utf-8-sig"),newline="")).fieldnames
    require(set(rule["required_headers"]) <= set(fields or []),"Missing admitted final CSV fields")
    return {"role":role,"metadata_original_base64":base64.b64encode(metadata_raw).decode(),
        "metadata_original_sha256":sha(metadata_raw),"metadata_original_bytes":len(metadata_raw),
        "asset_url":rule["asset_url"],"asset_id":asset["id"],"asset_name":asset["name"],
        "asset_bytes":len(raw),"asset_sha256":sha(raw),"publisher_updated_at":stamp(updated),
        "upstream_observed_at":None,"upstream_observation_status":"UNKNOWN",**clocks},rows


def _requests(requests,proof,config):
    operation=producer.seal({"schema_version":runner.OPERATION_SCHEMA,"protocol_id":producer.PROTOCOL_ID,
        "cycle_id":cycles.CYCLE_ID,"mode":"PROSPECTIVE_RESEARCH","phase":"FINAL_GRADING_CAPTURE",
        "status":"CAPTURED","recorded_at":proof["created_at"],"source_requests":requests,
        "input_ref":proof["input_ref"],"forecast_ids":[ref["record_id"] for ref in proof["forecast_refs"]],
        "genuine_issued":len(proof["forecast_refs"]),"error":None},"operation_id")
    runner.validate_operation(operation)
    admitted_rows=set()
    for source in proof["sources"]:
        role=source["role"];rule=config["roles"][role]
        meta=[row for row in requests if row["label"] == role+"_metadata" and row.get("status") == 200]
        final=[row for row in requests if row["label"].startswith(role+"_asset") and row.get("status") == 200]
        require(len(meta) == len(final) == 1,"Final source lacks an exact successful request receipt")
        m,a=meta[0],final[0]
        canonical_rows=[row for row in requests if row["label"] == role+"_asset"]
        require(len(canonical_rows) == 1,"Final asset lacks its canonical request receipt")
        initial=canonical_rows[0]
        require(m["route"] == rule["metadata_url"] and initial["route"] == rule["asset_url"]
            and initial["retrieval_started_at"] == source["asset_retrieval_started_at"]
            and m["response_limit_bytes"] == config["max_metadata_bytes"]
            and initial["response_limit_bytes"] == rule["max_asset_bytes"]
            and a["response_limit_bytes"] == rule["max_asset_bytes"]
            and m["request_number"] < initial["request_number"]
            and _clock(m["retrieved_at"]) <= _clock(initial["retrieval_started_at"]),
                "Final request route or canonical asset clock is not admitted")
        admitted_rows.update((m["request_number"],initial["request_number"]))
        if initial is not a:
            from urllib.parse import urlsplit
            target=urlsplit(a["route"])
            require(initial.get("status") in {301,302,303,307,308}
                and target.hostname == "release-assets.githubusercontent.com"
                and a["label"] in {role+"_asset_redirect",role+"_asset_redirect1"}
                and a["request_number"] == initial["request_number"]+1
                and _clock(initial.get("response_read_completed_at",initial["retrieval_started_at"])) <= _clock(a["retrieval_started_at"]),
                    "Final asset redirect lacks one permitted canonical predecessor")
            admitted_rows.add(a["request_number"])
        require(m.get("sha256") == source["metadata_original_sha256"] and m.get("bytes") == source["metadata_original_bytes"]
            and m["retrieval_started_at"] == source["metadata_retrieval_started_at"] and m.get("retrieved_at") == source["metadata_retrieved_at"]
            and a.get("sha256") == source["asset_sha256"] and a.get("bytes") == source["asset_bytes"]
            and a.get("retrieved_at") == source["asset_retrieved_at"],"Final capture request hashes/clocks differ")
    require(admitted_rows == set(range(1,len(requests)+1)),"Unrelated requests cannot be admitted as final-source capture")


def _originals(store,forecast_refs,config):
    refs=tuple(sorted(forecast_refs,key=lambda ref:ref.record_id))
    require(0 < len(refs) <= 8 and len(set(refs)) == len(refs),"Invalid final original forecast inventory")
    pairs=[]
    for ref in refs:
        require(isinstance(ref,LedgerRef) and ref.kind == "forecasts","Grading requires exact original forecast references")
        body=store.ledger.read(ref)["data"]["daily"];producer.validate_forecast(body)
        require(body["mode"] == "PROSPECTIVE_RESEARCH" and body["cycle_id"] == config["cycle_id"]
            and body["producer_binding"]["commit"] == config["supported_producer_commit"]
            and store.admission(ref)["eligible"],"Original forecast is not eligible genuine first-cycle research")
        pairs.append((ref,body))
    first=pairs[0][1]
    require(all(all(body[k] == first[k] for k in ("cycle_id","event_id","event_snapshot_id","event_starts_at","input_ref","input_id")) for _,body in pairs),
        "Final source crosses original event/input identities")
    source=store.ledger.read(LedgerRef.from_record(first["input_ref"]))["data"]["daily"]
    require(source["input_id"] == first["input_id"] and source["event"]["event_snapshot_id"] == first["event_snapshot_id"],"Final proof input reference differs")
    return pairs


def _retained_body(raw,metadata):
    return storage._sealed({"schema_version":storage.OUTCOME_EVIDENCE_SCHEMA,"protocol_id":producer.PROTOCOL_ID,
        "metadata":metadata,"raw_base64":storage._encode(raw),"raw_bytes":len(raw),"raw_sha256":sha(raw),
        "source_use_status":"REQUIRES_SEPARATE_ADMISSION"},"evidence_id")


def _meta(kind,url,at,basis,*,started=None):
    return {"source_kind":kind,"source_url":url,"source_observed_at":at,
        "retrieval_started_at":started or at,"retrieved_at":at,
        "content_type":"application/json" if kind == PROOF_KIND else "text/csv","source_use_basis":basis}


def _retain_source_with_proof(store,forecast_refs,*,schedule,boxscore,requests):
    """Retain already-captured originals; performs no source requests or issuance.

    Each source argument is (exact_csv_bytes, exact_release_json_bytes, clocks).
    Only genuine eligible original forecasts may be bound to this first-cycle
    final-source contract; a permitted source-use decision must already exist.
    """
    config,config_raw,review_raw,commit=_trusted_materials()
    pairs=_originals(store,forecast_refs,config);first=pairs[0][1]
    sources=[]
    for role,triple in (("schedule",schedule),("boxscore",boxscore)):
        require(type(triple) in (tuple,list) and len(triple) == 3,"Incomplete final source capture")
        source,_=_source(*triple,role,config);sources.append(source)
    proof=sealed({"schema_version":PROOF_SCHEMA,"protocol_id":producer.PROTOCOL_ID,"cycle_id":config["cycle_id"],
        "reviewed_commit":commit,"config_original_base64":base64.b64encode(config_raw).decode(),
        "config_original_sha256":sha(config_raw),"review_original_base64":base64.b64encode(review_raw).decode(),
        "review_original_sha256":sha(review_raw),"config_id":config["config_id"],"input_ref":first["input_ref"],
        "forecast_refs":[ref.to_record() for ref,_ in pairs],"event_id":first["event_id"],
        "event_snapshot_id":first["event_snapshot_id"],"created_at":stamp(_now()),"sources":sources,
        "requests":deepcopy(requests)},"proof_id")
    require(all(_clock(source["asset_retrieved_at"]) >= _clock(first["event_starts_at"]) for source in sources),
        "Final-source observations precede the original game start")
    _requests(requests,proof,config);raw=canonical(proof)
    require(len(raw) <= MAX_PROOF_RAW,"Complete final proof exceeds 1-MiB limit")
    # Retry recovers the prior proof clock and raw originals for this exact
    # capture; it cannot mint another receipt merely because the process restarted.
    prior=[];proof_ref=None
    for ref,body in store.records():
        if body["schema_version"] != storage.OUTCOME_EVIDENCE_SCHEMA or body["metadata"]["source_kind"] != PROOF_KIND:continue
        old=_decode(store.read_outcome_evidence(ref)[0]);prior.append((ref,old))
        if old["sources"] == sources and old["forecast_refs"] == proof["forecast_refs"] and old["config_id"] == proof["config_id"]:
            require(proof_ref is None,"Duplicate original proofs for one captured observation")
            proof_ref=ref;proof=old;raw=canonical(old)
    basis="Separate final-source review "+config["source_review_receipt_sha256"]+"; config "+config["config_id"]
    if proof_ref is None:
        require(len(prior) < config["max_captures"],"Final source capture/revision budget exhausted; retain pending state")
        require(grading_capacity(store)["fits"],"Bounded final-source retention budget unavailable")
        source_url="https://github.com/"+cycles.REPOSITORY+"/blob/"+commit+"/"+DEFAULT_CONFIG_PATH
        proof_body=_retained_body(raw,_meta(PROOF_KIND,source_url,proof["created_at"],basis))
        require(len(canonical(proof_body))+4096 <= MAX_PROOF_ENVELOPE,"Final proof encoded envelope exceeds 1.5 MiB")
        proof_ref=store.append_body("research_inputs",proof_body,references=(LedgerRef.from_record(first["input_ref"]),))
    refs=[]
    for role,triple,source in zip(("schedule","boxscore"),(schedule,boxscore),sources):
        body=_retained_body(triple[0],_meta(config["roles"][role]["source_kind"],source["asset_url"],
            source["asset_retrieved_at"],basis,started=source["asset_retrieval_started_at"]))
        require(len(canonical(body))+4096 <= MAX_CSV_ENVELOPE,"Final CSV encoded envelope exceeds 3 MiB")
        refs.append(store.append_body("research_inputs",body,references=(proof_ref,)))
    return tuple(refs)


def _recover_source_refs(store,proof_ref):
    found={}
    for ref,body in store.records():
        if body["schema_version"] != storage.OUTCOME_EVIDENCE_SCHEMA:continue
        payload=store.ledger.read(ref)
        if payload["references"] != [proof_ref.to_record()]:continue
        kind=body["metadata"]["source_kind"]
        role="schedule" if kind == "SportsDataverse NBA schedule CSV" else "boxscore" if kind == "SportsDataverse NBA player boxscore CSV" else None
        if role:require(role not in found,"Conflicting retained CSVs for one final proof");found[role]=ref
    require(set(found) == {"schedule","boxscore"},"Interrupted final capture lacks one original CSV; retry same captured originals")
    return found["schedule"],found["boxscore"]


def _validated_proof(store,ref):
    raw,meta=store.read_outcome_evidence(ref)
    require(meta["source_kind"] == PROOF_KIND and len(raw) <= MAX_PROOF_RAW,"Wrong final source proof identity")
    proof=_decode(raw)
    require(type(proof) is dict and set(proof) == PROOF_FIELDS,"Invalid final-source proof fields")
    check_seal(proof,"proof_id")
    config,config_raw,review_raw,commit=_trusted_materials(proof["reviewed_commit"])
    require(decode64(proof["config_original_base64"],32*1024) == config_raw and sha(config_raw) == proof["config_original_sha256"]
        and decode64(proof["review_original_base64"],32*1024) == review_raw and sha(review_raw) == proof["review_original_sha256"]
        and proof["config_id"] == config["config_id"],"Final admission originals differ from reviewed committed bytes")
    require(proof["schema_version"] == PROOF_SCHEMA and proof["protocol_id"] == producer.PROTOCOL_ID
        and proof["cycle_id"] == config["cycle_id"] and _clock(proof["created_at"]) <= _now(),"Wrong final proof scope or clock")
    expected_url="https://github.com/"+cycles.REPOSITORY+"/blob/"+commit+"/"+DEFAULT_CONFIG_PATH
    require(meta["source_url"] == expected_url and all(meta[key] == proof["created_at"]
        for key in ("source_observed_at","retrieval_started_at","retrieved_at")),
            "Project proof retention clocks or identity differ from actual creation")
    forecast_refs=tuple(LedgerRef.from_record(row) for row in proof["forecast_refs"])
    pairs=_originals(store,forecast_refs,config);first=pairs[0][1]
    require(store.ledger.read(ref)["references"] == [proof["input_ref"]]
        and proof["input_ref"] == first["input_ref"] and proof["event_id"] == first["event_id"]
        and proof["event_snapshot_id"] == first["event_snapshot_id"],"Final admission forecast/input graph differs")
    require(type(proof["sources"]) is list and len(proof["sources"]) == 2,"Final source role inventory differs")
    for role,source in zip(("schedule","boxscore"),proof["sources"]):
        require(type(source) is dict and set(source) == SOURCE_FIELDS and source["role"] == role
            and source["upstream_observed_at"] is None and source["upstream_observation_status"] == "UNKNOWN",
            "Final source invents an upstream observation clock")
        original=decode64(source["metadata_original_base64"],config["max_metadata_bytes"])
        require(len(original) == source["metadata_original_bytes"] and sha(original) == source["metadata_original_sha256"],
                "Partial proof publisher original bytes changed")
        release=_decode(original);rule=config["roles"][role]
        require(type(release) is dict and release.get("tag_name") == rule["release_tag"]
            and type(release.get("assets")) is list,"Wrong partial proof publisher release")
        matches=[row for row in release["assets"] if type(row) is dict and row.get("name") == rule["asset_name"]]
        require(len(matches) == 1,"Partial proof asset identity is absent or ambiguous")
        asset=matches[0]
        require(source["asset_url"] == rule["asset_url"] == asset.get("browser_download_url")
            and type(asset.get("id")) is int and asset["id"] > 0 and source["asset_id"] == asset["id"]
            and source["asset_name"] == asset.get("name") and source["asset_bytes"] == asset.get("size")
            and type(source["asset_bytes"]) is int and 0 < source["asset_bytes"] <= rule["max_asset_bytes"]
            and asset.get("digest") == "sha256:"+source["asset_sha256"]
            and _time(asset.get("updated_at")) == _clock(source["publisher_updated_at"]),
                "Partial proof asset facts differ from original publisher metadata")
        times=[_clock(source[key]) for key in ("metadata_retrieval_started_at","metadata_retrieved_at","asset_retrieval_started_at","asset_retrieved_at")]
        require(times == sorted(times) and _clock(source["publisher_updated_at"]) <= times[1]
            and _clock(first["event_starts_at"]) <= times[-1] <= _clock(proof["created_at"]),
                "Partial proof source clocks conflict")
    _requests(proof["requests"],proof,config)
    return proof,config,pairs


def _proof_inventory(store):
    rows=[(ref,body) for ref,body in store.records() if body["schema_version"] == storage.OUTCOME_EVIDENCE_SCHEMA
          and body["metadata"]["source_kind"] == PROOF_KIND]
    if not rows:return []
    require(len(rows) <= _trusted_materials()[0]["max_captures"],
            "Retained final-source proof inventory exceeds two-capture admission budget")
    return [(ref,_validated_proof(store,ref)[0]) for ref,_ in rows]


def _proof_for_sources(store,schedule_ref,boxscore_ref):
    originals=[store.ledger.read(ref) for ref in (schedule_ref,boxscore_ref)]
    refs=[row["references"] for row in originals]
    require(len(refs[0]) == 1 and refs[0] == refs[1],"Final CSVs do not reference one shared admission proof")
    ref=LedgerRef.from_record(refs[0][0])
    proof,config,pairs=_validated_proof(store,ref)
    rows={}
    for role,original,source in zip(("schedule","boxscore"),originals,proof["sources"]):
        require(type(source) is dict and set(source) == SOURCE_FIELDS and source["role"] == role
            and source["upstream_observed_at"] is None and source["upstream_observation_status"] == "UNKNOWN",
            "Final source invents an upstream observation clock")
        raw,meta=store.read_outcome_evidence(LedgerRef(original["kind"],original["record_id"],digest(original)))
        metadata_raw=decode64(source["metadata_original_base64"],config["max_metadata_bytes"])
        expected,table=_source(raw,metadata_raw,{key:source[key] for key in CLOCK_FIELDS},role,config)
        require(expected == source and meta["source_kind"] == config["roles"][role]["source_kind"]
            and meta["source_url"] == source["asset_url"] and meta["retrieved_at"] == source["asset_retrieved_at"]
            and meta["retrieval_started_at"] == source["asset_retrieval_started_at"]
            and _clock(source["asset_retrieved_at"]) <= _clock(proof["created_at"]),"Final source facts or clocks changed")
        rows[role]=table
    return proof,config,pairs,rows


class FinalEvidencePending(IntegrityError):
    """A valid final event has no published player boxscore evidence yet."""


def _complete_event(rows,forecast,config):
    events=rows["schedule"]
    require(len({row["game_id"] for row in events}) == len(events),"Duplicate final schedule event IDs")
    selected=[row for row in events if row["game_id"] == forecast["event_id"]]
    require(len(selected) == 1,"Final event missing from schedule")
    event=selected[0]
    require({event["home_id"],event["away_id"]} == {forecast["team_id"],forecast["opponent_id"]}
        and _time(event["game_date_time"]) == _time(forecast["event_starts_at"])
        and outcomes._count(event["season"]) == config["season_ending_year"],"Final event identity/version conflicts with original")
    all_rows=rows["boxscore"]
    keys=[(row["game_id"],row["athlete_id"]) for row in all_rows]
    require(len(keys) == len(set(keys)) and all(re.fullmatch(r"[0-9]+",g) and re.fullmatch(r"[0-9]+",p) for g,p in keys),"Duplicate/invalid final player identities")
    if event["status_type_name"] in {"STATUS_CANCELED","STATUS_CANCELLED"}:
        return "CANCELLED_UNSUPPORTED_BY_V1_OUTCOME"
    if outcomes._boolean(event["status_type_completed"]) is not True:
        if event["status_type_name"] == "STATUS_POSTPONED":return "POSTPONED"
        if event["status_type_state"] in {"pre","in"} and event["status_type_name"] in {"STATUS_SCHEDULED","STATUS_IN_PROGRESS","STATUS_HALFTIME","STATUS_END_PERIOD","STATUS_DELAYED"}:return "NONFINAL"
        return "UNRESOLVED_EVENT_STATE_UNSUPPORTED_BY_V1_OUTCOME"
    require(event["status_type_name"] == "STATUS_FINAL" and event["status_type_state"] == "post","Contradictory final schedule state")
    scores={event["home_id"]:outcomes._count(event["home_score"]),event["away_id"]:outcomes._count(event["away_score"])}
    require(all(type(v) is int and v >= 0 for v in scores.values()),"Missing final schedule scores")
    if not any(row["game_id"] == forecast["event_id"] for row in all_rows):
        raise FinalEvidencePending("Final schedule event has no target-event player boxscore rows; retain pending state")
    totals={team:0 for team in scores};seen=set()
    schedule=event.copy();schedule["season"]=outcomes._count(event["season"]);schedule["status_type_completed"]=True
    for original in all_rows:
        if original["game_id"] != forecast["event_id"]:continue
        row=original.copy();team=row["team_id"];opponent=row["opponent_team_id"]
        require(team in scores and opponent in scores and team != opponent
            and outcomes._count(row["team_score"]) == scores[team]
            and outcomes._count(row["opponent_team_score"]) == scores[opponent],"Player row score/team identity conflicts with final event")
        row["season"]=outcomes._count(row["season"]);row["did_not_play"]=outcomes._boolean(row["did_not_play"])
        for field in outcomes.SDV_FIELDS.values():row[field]=outcomes._count(row.get(field))
        minutes=row.get("minutes")
        require(minutes in (None,"","NA") or type(minutes) is str and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?",minutes),"Invalid final reported minutes")
        row["minutes"]=None if minutes in (None,"","NA") else float(minutes)
        line=with_sdv_schedule(normalize_sdv_row(row),schedule,standard_team_ids=frozenset())
        require(line.participation in {"APPEARED","DNP"},"Final player row has unresolved participation")
        if line.participation == "APPEARED":totals[team]+=line.points
        seen.add(team)
    require(seen == set(scores) and totals == scores,"Final player PTS totals do not match both final team scores")


def _validate_admission_graph(store,outcome):
    producer.validate_outcome(outcome)
    require(outcome["mode"] == "PROSPECTIVE_RESEARCH","Final admission applies to genuine originals only")
    require(len(outcome["source_refs"]) == 2,"Final outcome needs both admitted CSVs")
    schedule_ref,boxscore_ref=(LedgerRef.from_record(row) for row in outcome["source_refs"])
    proof,config,pairs,rows=_proof_for_sources(store,schedule_ref,boxscore_ref)
    matching=[body for _,body in pairs if all(body[key] == outcome[key] for key in ("cycle_id","mode","event_id","event_snapshot_id","event_starts_at","player_id","team_id","opponent_id"))]
    require(matching,"Outcome is outside proof's eligible original forecast subjects")
    state=_complete_event(rows,matching[0],config)
    require(state not in {"CANCELLED_UNSUPPORTED_BY_V1_OUTCOME","UNRESOLVED_EVENT_STATE_UNSUPPORTED_BY_V1_OUTCOME"},
            "Unsupported event state cannot be admitted as a v1 normalized outcome")
    if outcome["status"] in TERMINAL:
        require(all(_clock(source["publisher_updated_at"]) >= _clock(outcome["event_starts_at"])
                    for source in proof["sources"]),"Final publisher assets predate the actual event")
    outcomes.verify_outcome_sources(store,outcome)
    return {"proof_id":proof["proof_id"],"config_id":config["config_id"],"reviewed_commit":proof["reviewed_commit"],"admitted":True}


def _semantic(body):
    return {key:value for key,value in body.items() if key not in {"outcome_id","normalized_at","source_refs","source_observed_at"}}


def _normalize_and_grade(store,forecast_refs,schedule_ref,boxscore_ref):
    """Recover originals first, append only changed outcomes and missing grades."""
    config=_trusted_materials()[0]
    pairs=_originals(store,forecast_refs,config)
    proof,_,admitted,rows=_proof_for_sources(store,schedule_ref,boxscore_ref)
    require({ref for ref,_ in pairs} <= {ref for ref,_ in admitted},"Grading originals differ from source proof")
    result={"outcomes":[],"grades":[],"corrections":[],"pending":[]}
    with store.lock():
        by_player={body["player_id"]:body for _,body in pairs}
        for player,forecast in by_player.items():
            try:state=_complete_event(rows,forecast,config)
            except FinalEvidencePending:
                result["pending"].append(player)
                result["unresolved_event_state"]="FINAL_BOXSCORE_UNAVAILABLE"
                continue
            if state in {"CANCELLED_UNSUPPORTED_BY_V1_OUTCOME","UNRESOLVED_EVENT_STATE_UNSUPPORTED_BY_V1_OUTCOME"}:
                result["pending"].append(player);result["unresolved_event_state"]=state;continue
            retained=[(ref,body) for ref,body in store.records() if body["schema_version"] == producer.OUTCOME_SCHEMA
                and all(body[key] == forecast[key] for key in ("cycle_id","mode","event_id","event_snapshot_id","player_id"))]
            current=[pair for pair in retained if pair[1]["source_refs"] == [schedule_ref.to_record(),boxscore_ref.to_record()]]
            require(len(current) <= 1,"Multiple outcomes for the same exact source observation")
            active=[pair for pair in retained if store.ledger.latest(pair[0]) == pair[0]]
            if current:
                outcome_ref,body=current[0]
                newest=store.ledger.latest(outcome_ref)
                if newest != outcome_ref:
                    outcome_ref=newest;body=store.ledger.read(newest)["data"]["daily"]
                previous=[pair for pair in active if pair[0] != outcome_ref]
                require(len(previous) <= 1,"Multiple active preceding outcomes")
                if previous:
                    require(_clock(body["source_observed_at"]) >= _clock(previous[0][1]["source_observed_at"]),"Stale source cannot replace a later outcome")
                    result["corrections"].append(store.ledger.correct(previous[0][0],outcome_ref,reason="Verified later final-source evidence; original forecast unchanged"))
            else:
                require(len(active) <= 1,"Multiple active outcomes for one original subject")
                prior=active[0] if active else None
                probe_clock=prior[1]["normalized_at"] if prior else stamp(_now())
                if prior:
                    newest=max(_clock(source["asset_retrieved_at"]) for source in proof["sources"])
                    probe_clock=stamp(max(_clock(probe_clock),newest))
                body=outcomes._normalize(store,forecast,schedule_ref=schedule_ref,boxscore_ref=boxscore_ref,normalized_at=probe_clock)
                if prior and _semantic(prior[1]) == _semantic(body):
                    outcome_ref,body=prior
                else:
                    require(prior is None or _clock(body["source_observed_at"]) >= _clock(prior[1]["source_observed_at"]),"Stale source cannot replace a later outcome")
                    body=outcomes._normalize(store,forecast,schedule_ref=schedule_ref,boxscore_ref=boxscore_ref,normalized_at=stamp(_now()))
                    validate_admission_graph(store,body)
                    logical="daily-final-outcome:"+forecast["cycle_id"]+":"+player+":"+proof["proof_id"]
                    outcome_ref=store.append_body("outcomes",body,references=(schedule_ref,boxscore_ref),logical_id=logical)
                    if prior:
                        result["corrections"].append(store.ledger.correct(prior[0],outcome_ref,reason="Verified later final-source evidence; original forecast unchanged"))
            result["outcomes"].append(outcome_ref)
            if body["status"] not in TERMINAL:
                result["pending"].append(player);continue
            validate_admission_graph(store,body)
            for forecast_ref,original in pairs:
                if original["player_id"] != player:continue
                existing=[(ref,grade) for ref,grade in store.records() if grade["schema_version"] == producer.GRADE_SCHEMA
                    and grade["forecast_id"] == original["forecast_id"] and grade["outcome_id"] == body["outcome_id"]]
                require(len(existing) <= 1,"Duplicate statistical grades for exact original/outcome pair")
                if existing:grade_ref,grade=existing[0]
                else:
                    grade=producer.make_grade(original,body)
                    grade_ref=store.append_body("grades",grade,references=(forecast_ref,outcome_ref),
                        logical_id="daily-final-grade:"+original["forecast_id"]+":"+body["outcome_id"])
                previous=[(ref,g) for ref,g in store.records() if g["schema_version"] == producer.GRADE_SCHEMA
                    and g["forecast_id"] == original["forecast_id"] and g["outcome_id"] != body["outcome_id"]
                    and store.ledger.latest(ref) == ref]
                require(len(previous) <= 1,"Multiple active prior grades for one original")
                if previous:result["corrections"].append(store.ledger.correct(previous[0][0],grade_ref,reason="Statistical grade follows appended outcome correction"))
                result["grades"].append(grade_ref)
    return result


def grading_capacity(store):
    """Use the coordinator's one remaining-slot policy, never add it twice.

    The import is deliberately local: the coordinator uses this offline grader,
    but neither module runs a request or operation merely by being imported.
    """
    from .sdv_postgame_runner import capacity_preflight
    report=deepcopy(capacity_preflight(store))
    report["grading_evidence"]={"proof_records":2,"proof_max_raw_bytes":MAX_PROOF_RAW,
        "proof_max_encoded_bytes":MAX_PROOF_ENVELOPE,"csv_records":4,"csv_max_encoded_bytes":MAX_CSV_ENVELOPE}
    return report


def _validate_stored_admissions(root_or_store):
    """Publication hook: existing forecast-only and DEV channels stay independent."""
    store=root_or_store if hasattr(root_or_store,"records") else storage.DailyStore(root_or_store)
    _proof_inventory(store)  # Includes valid partial proofs with no CSV/outcome yet.
    records=store.records()
    actual=[(ref,body) for ref,body in records if body["schema_version"] == producer.OUTCOME_SCHEMA and body["mode"] == "PROSPECTIVE_RESEARCH"]
    genuine_grades=[body for _,body in records if body["schema_version"] == producer.GRADE_SCHEMA and body["mode"] == "PROSPECTIVE_RESEARCH"]
    if not actual:
        require(not genuine_grades,"Genuine grade lacks an admitted outcome")
        return {"genuine_outcomes":0,"genuine_grades":0,"proof_ids":[]}
    proofs={validate_admission_graph(store,body)["proof_id"] for _,body in actual}
    outcomes_by_id={body["outcome_id"]:body for _,body in actual}
    forecasts_by_id={body["forecast_id"]:(ref,body) for ref,body in records if body["schema_version"] == producer.FORECAST_SCHEMA}
    count=0
    for ref,grade in records:
        if grade["schema_version"] != producer.GRADE_SCHEMA or grade["mode"] != "PROSPECTIVE_RESEARCH":continue
        require(grade["outcome_id"] in outcomes_by_id and grade["forecast_id"] in forecasts_by_id,"Genuine grade lacks admitted originals")
        forecast_ref,forecast=forecasts_by_id[grade["forecast_id"]]
        require(store.admission(forecast_ref)["eligible"] and outcomes_by_id[grade["outcome_id"]]["status"] in TERMINAL,
                "Genuine grade cannot score unadmitted or unresolved evidence")
        producer.validate_grade(grade,forecast,outcomes_by_id[grade["outcome_id"]]);count+=1
    return {"genuine_outcomes":len(actual),"genuine_grades":count,"proof_ids":sorted(proofs)}


def _scope(store):
    method=getattr(store.ledger,"validation_scope",None)
    return method() if callable(method) else nullcontext()


def retain_source_with_proof(store,forecast_refs,*,schedule,boxscore,requests):
    with store.lock(),_scope(store):
        return _retain_source_with_proof(store,forecast_refs,schedule=schedule,boxscore=boxscore,requests=requests)


def validate_admission_graph(store,outcome):
    with _scope(store):return _validate_admission_graph(store,outcome)


def normalize_and_grade(store,forecast_refs,schedule_ref,boxscore_ref):
    with _scope(store):return _normalize_and_grade(store,forecast_refs,schedule_ref,boxscore_ref)


def validate_stored_admissions(root_or_store):
    store=root_or_store if hasattr(root_or_store,"records") else storage.DailyStore(root_or_store)
    with _scope(store):return _validate_stored_admissions(store)

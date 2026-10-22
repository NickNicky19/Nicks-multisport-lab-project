"""Unchanged R0/K0 laws over a separately admitted daily-source input.

Development records have no issue time and never become prospective originals.
No statistical comparison, source client, ticket eligibility or scheduler lives here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import math
from pathlib import Path
import re
import subprocess

from .baseline import ForecastTarget, MARKETS
from .forecast_contract import UNITS, number, quantile
from .integrity import IntegrityError, canonical, digest, stamp, utc
from .ledger import Ledger, LedgerRef, _outcome_categories, _score_categories
from . import pregame_sources
from .pros004_producer import (_fit_laws, _categories, _minutes, joint_fingerprint,
                              MODEL_VERSIONS, LAW_SHA256, _validate_pmf)
from . import sdv_daily_inputs as inputs

PROTOCOL_ID = inputs.PROTOCOL_ID
FORECAST_SCHEMA = "nba-sdv-daily-forecast-v1"
BINDING_SCHEMA = "nba-sdv-daily-producer-binding-v1"
INTENT_SCHEMA = "nba-sdv-daily-intent-v1"
OUTCOME_SCHEMA = "nba-sdv-daily-outcome-v1"
GRADE_SCHEMA = "nba-sdv-daily-grade-v1"
HISTORY_ID = "dfa1c4345495eb3aa6b203f2e8309c89c112b6b78a36cd3d2c603d390776b6fc"
HISTORY_ROWS = 26645
HISTORY_SHA256 = pregame_sources.PANEL_SHA
HISTORY_AVAILABILITY = "RECONSTRUCTED_COMPLETION_BOUND"
PRODUCERS = {key: "sdv-daily-"+key.lower()+"-producer-v1" for key in MODEL_VERSIONS}
SOURCE_FILES = (
    "multisport_lab/sdv_daily_inputs.py", "multisport_lab/sdv_daily_store.py",
    "multisport_lab/sdv_daily_producer.py", "multisport_lab/sdv_daily_cycle.py",
    "multisport_lab/sdv_daily_runner.py", "multisport_lab/sdv_daily_remote.py",
    "multisport_lab/sdv_daily_outcomes.py", "multisport_lab/sdv_daily_publication.py",
    "multisport_lab/pros004_remote.py", "config/sdv_daily_cycle_v1.json",
    ".github/workflows/sdv-daily.yml",
    "multisport_lab/baseline.py", "multisport_lab/development_003.py",
    "multisport_lab/development_002.py", "multisport_lab/research_pilot.py",
    "multisport_lab/pros004_producer.py", "multisport_lab/pros004_inputs.py",
    "multisport_lab/pregame_sources.py", "multisport_lab/nba_data.py",
    "multisport_lab/basketball.py", "multisport_lab/ledger.py",
    "multisport_lab/forecast_contract.py", "multisport_lab/integrity.py",
)
FORECAST_FIELDS = {
    "schema_version", "protocol_id", "cycle_id", "mode", "evidence_lane", "model_key",
    "model_version", "producer_version", "producer_binding", "history_ref", "history_rows",
    "history_panel_sha256", "history_panel_cutoff", "history_availability", "input_ref", "input_id",
    "event_snapshot_id", "event_id", "event_starts_at", "player_id", "player_label", "team_id",
    "opponent_id", "matchup", "cutoff_at", "history_freeze", "trained_through", "conditioning",
    "period", "extra_time_policy", "qualification", "generation_started_at", "generation_completed_at",
    "verified_at", "issued_at", "categories", "reported_minutes", "joint_recipe", "forecast_id",
}
OUTCOME_FIELDS = {"schema_version", "protocol_id", "cycle_id", "mode", "event_id", "event_snapshot_id",
    "event_starts_at", "player_id", "team_id", "opponent_id", "status", "source_refs", "source_observed_at",
    "normalized_at", "normalizer_version", "primitives", "minutes", "minutes_precision", "categories", "outcome_id"}
GRADE_FIELDS = {"schema_version", "protocol_id", "cycle_id", "mode", "event_id", "event_snapshot_id",
    "player_id", "team_id", "opponent_id", "model_key", "forecast_id", "outcome_id", "graded_at",
    "status", "categories", "financial_settlement", "qualification", "grade_id"}
OUTCOME_STATUSES = {"APPEARED", "DNP", "MISSING", "POSTPONED", "NONFINAL", "UNRESOLVED"}


def _now():
    return datetime.now(timezone.utc)


def require(ok, message):
    if not ok:
        raise IntegrityError(message)


def exact(value, fields, name):
    require(type(value) is dict and set(value) == set(fields), "Invalid daily "+name)


def clock(value):
    require(type(value) is str and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z", value),
            "Daily clocks require microsecond UTC")
    return utc(value)


def sha(value, size=64):
    require(type(value) is str and re.fullmatch(r"[a-f0-9]{"+str(size)+"}", value), "Invalid daily hash")
    return value


def text(value):
    require(type(value) is str and 0 < len(value) <= 2048 and value.strip() == value, "Invalid daily text")
    return value


def seal(body, key):
    return {**body, key: digest(body)}


def check_seal(body, key):
    require(body.get(key) == digest({k:v for k,v in body.items() if k != key}), "Daily original checksum mismatch")


def make_source_binding(commit=None, *, root=None):
    root = Path(root or Path(__file__).resolve().parents[1])
    files = {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in SOURCE_FILES}
    require(files["multisport_lab/baseline.py"] == LAW_SHA256["R0"]
        and files["multisport_lab/development_003.py"] == LAW_SHA256["K0"], "Frozen R0/K0 source bytes changed")
    if commit is not None:
        sha(commit,40)
        for name, expected in files.items():
            result = subprocess.run(["git","show",commit+":"+name],cwd=root,capture_output=True,check=False)
            require(result.returncode == 0 and hashlib.sha256(result.stdout).hexdigest() == expected,
                    "Executed daily source differs from reviewed commit: "+name)
    return seal({"schema_version":BINDING_SCHEMA,"commit":commit,"files":files,
                 "law_sha256":LAW_SHA256},"binding_id")


def validate_binding(binding, *, current=False):
    exact(binding,{"schema_version","commit","files","law_sha256","binding_id"},"producer binding")
    require(binding["schema_version"] == BINDING_SCHEMA and type(binding["files"]) is dict
        and set(binding["files"]) == set(SOURCE_FILES) and binding["law_sha256"] == LAW_SHA256,
        "Daily producer source inventory or law changed")
    for value in binding["files"].values():sha(value)
    if binding["commit"] is not None:sha(binding["commit"],40)
    require(binding["files"]["multisport_lab/baseline.py"] == LAW_SHA256["R0"]
        and binding["files"]["multisport_lab/development_003.py"] == LAW_SHA256["K0"],"Wrong daily law source")
    check_seal(binding,"binding_id")
    if current:require(binding == make_source_binding(binding["commit"]),"Daily executed source differs from binding")
    return binding


def validate_cycle(body):
    from .sdv_daily_cycle import validate_cycle as validate
    return validate(body)


def validate_authorization(body, *, cycle=None, producer_binding=None, now=None):
    from .sdv_daily_cycle import validate_authorization as validate
    return validate(body,cycle=cycle,producer_binding=producer_binding,now=now)


@lru_cache(maxsize=2)
def _history(root_string, payload_hash):
    root=Path(root_string)
    ref=LedgerRef("research_inputs",HISTORY_ID,payload_hash)
    Ledger(root).read(ref)
    history,provenance=pregame_sources.history_from_input_record(HISTORY_ID,repository_root=root)
    require(provenance["normalized_panel_sha256"] == HISTORY_SHA256
        and provenance["normalized_panel_rows"] == HISTORY_ROWS,"Daily history panel changed")
    from .pros004_inputs import _historical_appearances
    rows=list(_historical_appearances(canonical(history),HISTORY_SHA256,
        provenance["normalized_panel_bytes"],HISTORY_ROWS))
    require(len(rows) == HISTORY_ROWS,"Daily history cannot be truncated")
    return rows,provenance


def retained_history(root):
    from .integrity import read_receipt
    payload=read_receipt(Path(root)/"records/research_inputs"/(HISTORY_ID+".json"),max_bytes=4*1024*1024)
    ref=LedgerRef("research_inputs",HISTORY_ID,digest(payload))
    # Always authenticate current original bytes, even when target-neutral parsing is cached.
    Ledger(root).read(ref)
    rows,provenance=_history(str(Path(root).resolve()),ref.payload_sha256)
    return ref,rows,provenance


def validate_intent(body):
    exact(body,{"schema_version","protocol_id","cycle_id","mode","input_ref","input_id",
        "producer_binding_id","history_ref","created_at","intent_id"},"intent")
    require(body["schema_version"] == INTENT_SCHEMA and body["protocol_id"] == PROTOCOL_ID
        and body["mode"] in inputs.MODES,"Invalid daily intent scope")
    text(body["cycle_id"]);sha(body["input_id"]);sha(body["producer_binding_id"])
    require(LedgerRef.from_record(body["input_ref"]).kind == "research_inputs"
        and LedgerRef.from_record(body["history_ref"]).record_id == HISTORY_ID,"Wrong daily intent inputs")
    clock(body["created_at"]);check_seal(body,"intent_id");return body


def _categories_valid(categories):
    require(type(categories) is list and len(categories) == 14,"Daily output must preserve all 13 categories plus PA")
    by_code={}
    for row in categories:
        exact(row,{"code","units","pmf","mean","interval80"},"category")
        code=row["code"]
        require(code in MARKETS and code not in by_code and row["units"] == UNITS[code],"Daily category identity changed")
        _validate_pmf(row["pmf"])
        if code in {"DD","TD"}:require(all(a["value"] in {0,1} for a in row["pmf"]),"Indicator has count outcomes")
        mean=math.fsum(a["value"]*number(a["probability"]) for a in row["pmf"])
        require(math.isclose(number(row["mean"]),mean,abs_tol=1e-10,rel_tol=0)
            and row["interval80"] == [quantile(row["pmf"],.1),quantile(row["pmf"],.9)],"Daily PMF summaries changed")
        by_code[code]=row
    means={key:number(row["mean"]) for key,row in by_code.items()}
    for total,parts in {"PRA":["PTS","REB","AST"],"PR":["PTS","REB"],"RA":["REB","AST"],
                        "PA":["PTS","AST"],"BLK+STL":["BLK","STL"]}.items():
        require(math.isclose(means[total],math.fsum(means[x] for x in parts),abs_tol=1e-10,rel_tol=0),"Daily derived outcomes are incoherent")
    require(means["TD"] <= means["DD"]+1e-12 and means["PTS"]+1e-10 >= 3*means["3PM"],"Daily scoring/DD/TD are incoherent")
    tails=sorted((math.fsum(number(a["probability"]) for a in by_code[code]["pmf"] if a["value"] >= 10)
                  for code in ("PTS","REB","AST","STL","BLK")),reverse=True)
    for code,count in (("DD",2),("TD",3)):
        lower=max([0]+[(math.fsum(tails[:m])-(count-1))/(m-count+1) for m in range(count,6)])
        upper=min([1]+[math.fsum(tails[j:])/(count-j) for j in range(count)])
        require(lower-1e-12 <= means[code] <= upper+1e-12,"Daily achievement probability conflicts with primitive tails")


def validate_forecast(body, input_body=None, *, now=None):
    exact(body,FORECAST_FIELDS,"forecast")
    require(body["schema_version"] == FORECAST_SCHEMA and body["protocol_id"] == PROTOCOL_ID
        and body["mode"] in inputs.MODES and body["model_key"] in MODEL_VERSIONS,"Wrong daily forecast scope")
    model=body["model_key"]
    require(body["model_version"] == MODEL_VERSIONS[model] and body["producer_version"] == PRODUCERS[model]
        and body["conditioning"] == "CONDITIONAL_ON_APPEARANCE" and body["period"] == "full_game"
        and body["extra_time_policy"] == "includes_overtime" and body["qualification"] == "UNAVAILABLE",
        "Wrong daily model or participation meaning")
    for field in ("cycle_id","event_id","player_id","player_label","team_id","opponent_id","matchup"):text(body[field])
    require(body["team_id"] != body["opponent_id"],"Daily team/opponent conflict")
    validate_binding(body["producer_binding"])
    for key in ("input_id","event_snapshot_id","history_panel_sha256"):sha(body[key])
    require(body["history_rows"] == HISTORY_ROWS and body["history_panel_sha256"] == HISTORY_SHA256
        and body["history_availability"] == HISTORY_AVAILABILITY,"Daily historical panel or availability changed")
    require(LedgerRef.from_record(body["history_ref"]).record_id == HISTORY_ID
        and LedgerRef.from_record(body["input_ref"]).kind == "research_inputs","Wrong daily retained references")
    start=clock(body["event_starts_at"]);cutoff=clock(body["cutoff_at"]);freeze=clock(body["history_freeze"])
    require(cutoff == start-timedelta(minutes=90) and freeze == cutoff.replace(hour=0,minute=0,second=0,microsecond=0)
        and clock(body["trained_through"]) <= freeze and clock(body["history_panel_cutoff"]) <= freeze,
        "Daily causal history cutoff changed")
    started,completed,verified=(clock(body[k]) for k in ("generation_started_at","generation_completed_at","verified_at"))
    actual=utc(now or _now())
    require(started <= completed <= verified <= actual,"Daily actual generation clocks conflict")
    if body["mode"] == "DEVELOPMENT_ONLY":
        require(body["evidence_lane"] == "DEVELOPMENT_ONLY" and body["issued_at"] is None,"Development became genuine issuance")
    else:
        require(body["evidence_lane"] == "DAILY_SNAPSHOT_PROSPECTIVE" and body["producer_binding"]["commit"] is not None
            and body["issued_at"] == body["verified_at"] and cutoff <= started <= verified <= cutoff+timedelta(seconds=900)
            and (verified-started).total_seconds() <= 300 and verified < start,"Daily actual issuance window violated")
    _categories_valid(body["categories"])
    minutes=body["reported_minutes"]
    exact(minutes,{"pmf","mean","interval80","precision"},"reported minutes")
    _validate_pmf(minutes["pmf"],count=False)
    require(minutes["precision"] == "reported_source_precision_not_exact_workload"
        and minutes["interval80"] == [quantile(minutes["pmf"],.1),quantile(minutes["pmf"],.9)]
        and math.isclose(number(minutes["mean"]),math.fsum(a["value"]*number(a["probability"]) for a in minutes["pmf"]),abs_tol=1e-10),
        "Reported minutes distribution changed")
    recipe=body["joint_recipe"]
    exact(recipe,{"algorithm","input_sha256","joint_sha256","support_atom_count","player_history_count","pool_history_count","omitted_atoms"},"complete joint recipe")
    require(recipe["algorithm"] == MODEL_VERSIONS[model] and recipe["omitted_atoms"] == 0
        and type(recipe["support_atom_count"]) is int and 0 < recipe["support_atom_count"] <= HISTORY_ROWS
        and recipe["pool_history_count"] == recipe["support_atom_count"]
        and type(recipe["player_history_count"]) is int and 0 <= recipe["player_history_count"] <= recipe["pool_history_count"],
        "Daily complete joint law was truncated or changed")
    sha(recipe["input_sha256"]);sha(recipe["joint_sha256"])
    if input_body is not None:
        inputs.validate_input(input_body)
        require(body["input_id"] == input_body["input_id"] and body["mode"] == input_body["mode"]
            and all(body[k] == input_body["event"][k] for k in ("event_id","event_snapshot_id","event_starts_at")),"Daily forecast/input differ")
        require(any(all(body[k] == candidate[k] for k in ("player_id","player_label","team_id","opponent_id"))
            for candidate in input_body["candidates"]),"Daily forecast is outside the admitted cohort")
        require(clock(input_body["normalized_at"]) <= started,"Daily generation preceded input normalization")
        inputs.freshness(input_body,at=verified,require_retrieval_window=body["mode"] == "PROSPECTIVE_RESEARCH")
        event=input_body["event"]
        require(body["matchup"] == event["away_team_name"]+" @ "+event["home_team_name"],"Daily matchup differs from source input")
    check_seal(body,"forecast_id")
    require(len(canonical(body)) <= 62*1024,"Complete daily forecast exceeds encoded reserve; no atom omission")
    return body


def validate_body(body, input_body=None):
    schema=body.get("schema_version") if type(body) is dict else None
    if schema == FORECAST_SCHEMA:return validate_forecast(body,input_body)
    if schema == INTENT_SCHEMA:return validate_intent(body)
    if schema == OUTCOME_SCHEMA:return validate_outcome(body)
    if schema == GRADE_SCHEMA:return validate_grade(body)
    if schema == "nba-sdv-daily-cycle-v1":return validate_cycle(body)
    if schema == "nba-sdv-daily-authorization-v1":return validate_authorization(body)
    if schema == "nba-sdv-daily-failure-v1":return validate_failure(body)
    if schema == "nba-sdv-daily-operation-v1":return validate_operation(body)
    raise IntegrityError("Unknown daily producer body contract")


def validate_operation(body):
    from .sdv_daily_runner import validate_operation as validate
    return validate(body)


def validate_failure(body):
    exact(body,{"schema_version","protocol_id","cycle_id","mode","phase","recorded_at",
        "reason","input_ref","retained_forecast_ids","failure_id"},"failure")
    require(body["schema_version"] == "nba-sdv-daily-failure-v1" and body["protocol_id"] == PROTOCOL_ID
        and body["mode"] in inputs.MODES,"Invalid daily failure scope")
    for key in ("cycle_id","phase","reason"):text(body[key])
    require(clock(body["recorded_at"]) <= _now(),"Future operational failure")
    if body["input_ref"] is not None:require(LedgerRef.from_record(body["input_ref"]).kind == "research_inputs","Wrong failed input reference")
    require(type(body["retained_forecast_ids"]) is list and len(body["retained_forecast_ids"]) <= 8
        and len(set(body["retained_forecast_ids"])) == len(body["retained_forecast_ids"]),"Invalid partial inventory")
    for value in body["retained_forecast_ids"]:sha(value)
    check_seal(body,"failure_id");return body


def prepare_intent(store, input_ref, cycle, binding, *, authorization_ref=None):
    validate_cycle(cycle);validate_binding(binding,current=True)
    body=store.ledger.read(input_ref)["data"]["daily"];inputs.validate_input(body)
    require(body["policy"]["policy_id"] == cycle["policy_id"] and body["candidates"] == cycle["candidates"]
        and all(body["event"][k] == cycle["event"][k] for k in ("event_id","event_starts_at","home_team_id","away_team_id")),
        "Daily source differs from registered cycle")
    history_ref,_,_=retained_history(store.project_root)
    cycle_ref=store.append_body("input_captures",cycle)
    refs=[input_ref,cycle_ref]
    if body["mode"] == "PROSPECTIVE_RESEARCH":
        require(authorization_ref is not None,"Genuine daily intent lacks owner-dispatch authorization")
        authorization=store.ledger.read(authorization_ref)["data"]["daily"]
        validate_authorization(authorization,cycle=cycle,producer_binding=binding)
        refs.append(authorization_ref)
    else:require(authorization_ref is None,"Development cannot borrow a genuine authorization")
    # A retry reuses the ORIGINAL intent rather than changing created_at.
    for ref,existing in store.records():
        if existing["schema_version"] == INTENT_SCHEMA and existing["cycle_id"] == cycle["cycle_id"]:
            require(existing["input_ref"] == input_ref.to_record() and existing["producer_binding_id"] == binding["binding_id"]
                and existing["history_ref"] == history_ref.to_record() and existing["mode"] == body["mode"],
                "Daily recovery attempted a different input or producer revision")
            return ref
    intent=seal({"schema_version":INTENT_SCHEMA,"protocol_id":PROTOCOL_ID,"cycle_id":cycle["cycle_id"],
        "mode":body["mode"],"input_ref":input_ref.to_record(),"input_id":body["input_id"],
        "producer_binding_id":binding["binding_id"],"history_ref":history_ref.to_record(),"created_at":stamp(_now())},"intent_id")
    return store.append_body("input_captures",intent,references=tuple(refs),logical_id="daily-intent:"+cycle["cycle_id"])


def _development_laws(history,target):
    """Pure non-issuance calculation of the frozen laws for an early preview.

    The R0 calculation below preserves baseline.forecast_reference's exact
    eligibility, ordering, arithmetic and input recipe. It does not call or
    bypass its genuine T90 execution guard. No JointForecast.to_record() from
    this path is issued; the wrapper only permits DEVELOPMENT_ONLY records with
    null issued_at. Tiny synthetic equivalence tests compare both calculations.
    """
    from .baseline import (HistoricalAppearance, HALF_LIFE_DAYS, PRIOR_APPEARANCES,
                           WeightedOutcome, JointForecast, PROTOCOL_ID as R0_PROTOCOL,
                           MODEL_VERSION as R0_VERSION)
    from .development_003 import WorkloadPrior
    eligible=[];identities=set();event_starts={}
    for row in history:
        require(isinstance(row,HistoricalAppearance),"Development history must contain resolved appearances")
        identity=(row.id_namespace,row.event_id,row.player_id)
        require(identity not in identities and row.id_namespace == target.id_namespace,"Duplicate or foreign development identity")
        identities.add(identity)
        require(row.event_id not in event_starts or event_starts[row.event_id] == row.event_start,"Conflicting development event clocks")
        event_starts[row.event_id]=row.event_start
        if row.event_id != target.event_id and row.event_start < target.history_freeze and row.outcome_available_at <= target.history_freeze:
            eligible.append(row)
    eligible.sort(key=lambda row:(row.event_start,row.event_id,row.player_id))
    require(bool(eligible),"No eligible completed development history")
    latest=max(row.event_start for row in eligible)
    pool_weights=[2**(-(latest-row.event_start).total_seconds()/86400/HALF_LIFE_DAYS) for row in eligible]
    pool_total=math.fsum(pool_weights)
    own_weights=[2**(-(target.cutoff-row.event_start).total_seconds()/86400/HALF_LIFE_DAYS)
                 if row.player_id == target.player_id else 0.0 for row in eligible]
    denominator=PRIOR_APPEARANCES+math.fsum(own_weights)
    support=tuple(WeightedOutcome(source_event_id=row.event_id,source_player_id=row.player_id,
        line=row.primitive_line(),weight=(own+PRIOR_APPEARANCES*pool/pool_total)/denominator)
        for row,own,pool in zip(eligible,own_weights,pool_weights) if own+pool > 0)
    reference=JointForecast(target=target,issued_at=_now(),
        trained_through=max(row.outcome_available_at for row in eligible),
        input_sha256=digest({"protocol_id":R0_PROTOCOL,"model_version":R0_VERSION,
            "target":target.to_record(),"history_freeze":stamp(target.history_freeze),"rows":[row.to_record() for row in eligible]}),
        support=support,player_history_count=sum(row.player_id == target.player_id for row in eligible),pool_history_count=len(eligible))
    return {"R0":reference,"K0":WorkloadPrior(history).forecast(target,reference)}


def generate_pair(input_body, input_ref, cycle, binding, history_ref, history, *, player_id):
    """Compute both unchanged complete laws before persisting either model."""
    inputs.validate_input(input_body);validate_binding(binding,current=True);validate_cycle(cycle)
    require(input_body["policy"]["policy_id"] == cycle["policy_id"] and input_body["candidates"] == cycle["candidates"]
        and all(input_body["event"][key] == cycle["event"][key] for key in cycle["event"]),
        "Daily generation input differs from the registered cycle")
    candidates=[row for row in input_body["candidates"] if row["player_id"] == player_id]
    require(len(candidates) == 1,"Daily subject not in fixed cohort")
    candidate=candidates[0];target=ForecastTarget(input_body["event"]["event_id"],player_id,clock(input_body["event"]["event_starts_at"]))
    started=_now();inputs.freshness(input_body,at=started,require_retrieval_window=input_body["mode"] == "PROSPECTIVE_RESEARCH")
    require(len(history) == HISTORY_ROWS,"Daily generation requires the complete fixed history")
    laws=(_development_laws if input_body["mode"] == "DEVELOPMENT_ONLY" else _fit_laws)(history,target)
    result=[]
    for key in MODEL_VERSIONS:
        reference=laws[key]
        categories,minutes=_categories(reference),_minutes(reference)
        # Integral reported minutes have one JSON representation in Python and
        # JavaScript. This changes wire encoding only, never the fitted law.
        for atom in minutes["pmf"]:
            if float(atom["value"]).is_integer():atom["value"]=int(atom["value"])
        minutes["interval80"]=[int(v) if float(v).is_integer() else v for v in minutes["interval80"]]
        joint_sha=joint_fingerprint(reference);completed=_now()
        body={"schema_version":FORECAST_SCHEMA,"protocol_id":PROTOCOL_ID,"cycle_id":cycle["cycle_id"],
            "mode":input_body["mode"],"evidence_lane":"DEVELOPMENT_ONLY" if input_body["mode"] == "DEVELOPMENT_ONLY" else "DAILY_SNAPSHOT_PROSPECTIVE",
            "model_key":key,"model_version":MODEL_VERSIONS[key],"producer_version":PRODUCERS[key],"producer_binding":binding,
            "history_ref":history_ref.to_record(),"history_rows":HISTORY_ROWS,"history_panel_sha256":HISTORY_SHA256,
            "history_panel_cutoff":stamp(max(row.outcome_available_at for row in history)),"history_availability":HISTORY_AVAILABILITY,
            "input_ref":input_ref.to_record(),"input_id":input_body["input_id"],
            "event_snapshot_id":input_body["event"]["event_snapshot_id"],"event_id":target.event_id,
            "event_starts_at":stamp(target.event_start),**candidate,
            "matchup":input_body["event"]["away_team_name"]+" @ "+input_body["event"]["home_team_name"],
            "cutoff_at":stamp(target.cutoff),"history_freeze":stamp(target.history_freeze),"trained_through":stamp(reference.trained_through),
            "conditioning":"CONDITIONAL_ON_APPEARANCE","period":"full_game","extra_time_policy":"includes_overtime",
            "qualification":"UNAVAILABLE","generation_started_at":stamp(started),"generation_completed_at":stamp(completed),
            "verified_at":stamp(completed),"issued_at":None if input_body["mode"] == "DEVELOPMENT_ONLY" else stamp(completed),
            "categories":categories,"reported_minutes":minutes,
            "joint_recipe":{"algorithm":MODEL_VERSIONS[key],"input_sha256":reference.input_sha256,"joint_sha256":joint_sha,
                "support_atom_count":len(reference.support),"player_history_count":reference.player_history_count,
                "pool_history_count":reference.pool_history_count,"omitted_atoms":0}}
        # Same source-bound complete law supplies every primitive, sum and DD/TD.
        require({row["code"] for row in categories} == set(MARKETS) and reference.target == target,"Wrong complete daily law")
        verified=_now();body["verified_at"]=stamp(verified)
        if body["mode"] == "PROSPECTIVE_RESEARCH":body["issued_at"]=stamp(verified)
        body=seal(body,"forecast_id");validate_forecast(body,input_body)
        result.append(body)
    return result


def issue_cycle(store, input_ref, cycle, binding, *, authorization_ref=None, checkpoint=None):
    """One writer; recover originals first, preserve partial peers and actual clocks."""
    with store.lock():
        intent_ref=prepare_intent(store,input_ref,cycle,binding,authorization_ref=authorization_ref)
        input_body=store.ledger.read(input_ref)["data"]["daily"]
        if input_body["mode"] == "PROSPECTIVE_RESEARCH":
            from .sdv_daily_cycle import require_dispatch_context
            authorization=store.ledger.read(authorization_ref)["data"]["daily"]
            require_dispatch_context(authorization,binding)
            require(store.admission(input_ref)["eligible"],"Daily input lacks timely durable remote recovery")
        history_ref,history,_=retained_history(store.project_root)
        retained={(body["player_id"],body["model_key"]):(ref,body) for ref,body in store.records()
                  if body["schema_version"] == FORECAST_SCHEMA and body["cycle_id"] == cycle["cycle_id"]}
        for candidate in input_body["candidates"]:
            pid=candidate["player_id"]
            for key in MODEL_VERSIONS:
                if (pid,key) in retained:
                    original=retained[(pid,key)][1]
                    require(original["input_ref"] == input_ref.to_record() and original["producer_binding"] == binding,
                            "Daily original recovery changed its input or producer")
            missing=[key for key in MODEL_VERSIONS if (pid,key) not in retained]
            if not missing:continue
            pair=generate_pair(input_body,input_ref,cycle,binding,history_ref,history,player_id=pid)
            written=[]
            for body in pair:
                key=body["model_key"]
                if key not in missing:continue
                if body["mode"] == "PROSPECTIVE_RESEARCH":
                    # A pending pair may finish after a deadline; preserve any original already written.
                    inputs.freshness(input_body,at=_now(),require_retrieval_window=True)
                references=(input_ref,intent_ref)
                if body["mode"] == "PROSPECTIVE_RESEARCH":
                    with store._verified_forecast_write(body,references):
                        ref=store.append_body("forecasts",body,references=references)
                else:ref=store.append_body("forecasts",body,references=references)
                store.record_completion(ref,started_at=clock(body["generation_started_at"]))
                retained[(pid,key)]=(ref,body);written.append(ref)
            if checkpoint is not None and written:checkpoint(tuple(written))
        return store.recover()


def validate_outcome(body):
    exact(body,OUTCOME_FIELDS,"outcome")
    require(body["schema_version"] == OUTCOME_SCHEMA and body["protocol_id"] == PROTOCOL_ID
        and body["mode"] in inputs.MODES and body["status"] in OUTCOME_STATUSES,"Wrong daily outcome scope")
    for key in ("cycle_id","event_id","player_id","team_id","opponent_id","normalizer_version"):text(body[key])
    sha(body["event_snapshot_id"]);require(body["team_id"] != body["opponent_id"],"Outcome subject conflict")
    require(type(body["source_refs"]) is list and len(body["source_refs"]) in {1,2}
        and all(LedgerRef.from_record(ref).kind == "research_inputs" for ref in body["source_refs"]),"Daily outcome lacks original source evidence")
    observed,normalized=clock(body["source_observed_at"]),clock(body["normalized_at"])
    require(observed <= normalized <= _now(),"Daily outcome evidence clocks conflict")
    if body["status"] in {"APPEARED","DNP"}:require(observed >= clock(body["event_starts_at"]),"Outcome precedes event")
    if body["status"] == "APPEARED":
        require(body["categories"] == _outcome_categories(body["primitives"]),"Contradictory daily outcome counts")
        mapping={"fg2m":"FG2M","fg3m":"FG3M","ftm":"FTM","rebounds":"REB","assists":"AST","turnovers":"TOV","blocks":"BLK","steals":"STL"}
        from .baseline import PrimitiveLine
        PrimitiveLine(minutes=body["minutes"],minutes_precision=body["minutes_precision"],**{key:body["primitives"][value] for key,value in mapping.items()})
    else:require(body["primitives"] is None and body["minutes"] is None and body["minutes_precision"] is None and body["categories"] == [],"DNP/unresolved cannot become zero")
    check_seal(body,"outcome_id");return body


def make_grade(forecast,outcome,*,graded_at=None):
    validate_forecast(forecast);validate_outcome(outcome)
    for key in ("cycle_id","mode","event_id","event_snapshot_id","player_id","team_id","opponent_id"):
        require(forecast[key] == outcome[key],"Daily grade subject differs from original")
    at=utc(graded_at or _now())
    require(clock(outcome["normalized_at"]) <= at <= _now(),"Grade precedes outcome or is future-dated")
    status="SCORED" if outcome["status"] == "APPEARED" else "DNP_NOT_SCORED" if outcome["status"] == "DNP" else outcome["status"]
    body={"schema_version":GRADE_SCHEMA,"protocol_id":PROTOCOL_ID,
        **{key:forecast[key] for key in ("cycle_id","mode","event_id","event_snapshot_id","player_id","team_id","opponent_id","model_key")},
        "forecast_id":forecast["forecast_id"],"outcome_id":outcome["outcome_id"],"graded_at":stamp(at),"status":status,
        "categories":_score_categories(forecast,outcome) if status == "SCORED" else [],
        "financial_settlement":"NOT_EVALUATED","qualification":"UNAVAILABLE"}
    return seal(body,"grade_id")


def validate_grade(body,forecast=None,outcome=None):
    exact(body,GRADE_FIELDS,"grade")
    require(body["schema_version"] == GRADE_SCHEMA and body["protocol_id"] == PROTOCOL_ID
        and body["mode"] in inputs.MODES and body["model_key"] in MODEL_VERSIONS
        and body["status"] in OUTCOME_STATUSES-{"APPEARED","DNP"}|{"SCORED","DNP_NOT_SCORED"}
        and body["financial_settlement"] == "NOT_EVALUATED" and body["qualification"] == "UNAVAILABLE","Wrong daily grade meaning")
    for key in ("forecast_id","outcome_id","event_snapshot_id"):sha(body[key])
    require(clock(body["graded_at"]) <= _now(),"Future daily grade")
    if body["status"] != "SCORED":require(body["categories"] == [],"Unresolved grade contains scores")
    else:require(type(body["categories"]) is list and {row.get("code") for row in body["categories"]} == set(MARKETS),"Missing daily category grades")
    if forecast is not None and outcome is not None:
        require(body == make_grade(forecast,outcome,graded_at=body["graded_at"]),"Daily statistical grade is inconsistent")
    check_seal(body,"grade_id");return body

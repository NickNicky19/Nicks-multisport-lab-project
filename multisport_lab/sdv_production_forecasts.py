"""Production wrappers over the unchanged complete R0/K0 laws.

This module has no HTTP client or comparative evaluation. Actual issuance clocks
come from the process clock; development bodies never become genuine originals.
Statistical outcomes/grades remain separate from financial settlement.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import csv
import hashlib
import io
import math
from pathlib import Path
import re
import subprocess

from .baseline import (ForecastTarget, PrimitiveLine, MARKETS, HistoricalAppearance, WeightedOutcome,
    JointForecast, HALF_LIFE_DAYS, PRIOR_APPEARANCES, PROTOCOL_ID as R0_PROTOCOL, MODEL_VERSION as R0_VERSION)
from .development_003 import WorkloadPrior
from .forecast_contract import number, quantile
from .integrity import IntegrityError, canonical, digest, stamp, utc, _decode
from .ledger import LedgerRef, _outcome_categories, _score_categories, _decimal_score
from .nba_data import normalize_sdv_row, with_sdv_schedule, SDV_FIELDS
from .pros004_producer import _fit_laws, _categories, _minutes, joint_fingerprint, _validate_pmf
from .sdv_daily_producer import (SOURCE_FILES as FROZEN_SOURCE_FILES, HISTORY_AVAILABILITY,
    retained_history, _development_laws, _categories_valid, _DevelopmentDistribution)
from . import sdv_production_common as common

PROTOCOL_ID = common.PROTOCOL_ID
FORECAST_SCHEMA, INTENT_SCHEMA = common.FORECAST_SCHEMA, common.INTENT_SCHEMA
OUTCOME_SCHEMA, GRADE_SCHEMA = common.OUTCOME_SCHEMA, common.GRADE_SCHEMA
LEGACY_BINDING_SCHEMA = "nba-sdv-production-producer-binding-v1"
BINDING_SCHEMA = "nba-sdv-production-producer-binding-v2"
PRODUCERS = {key:"production-"+key.lower()+"-v1" for key in common.MODEL_VERSIONS}
MODES = {"DEVELOPMENT_ONLY", "PROSPECTIVE_RESEARCH"}
EVIDENCE_LANE = "SDV_PRODUCTION_PROSPECTIVE"
OUTCOME_STATUSES = {"APPEARED", "DNP", "MISSING", "POSTPONED", "CANCELLED", "NONFINAL", "UNRESOLVED"}
PRODUCTION_SOURCE_FILES = ("multisport_lab/sdv_production_common.py", "multisport_lab/sdv_production_inputs.py",
    "multisport_lab/sdv_production_forecasts.py", "multisport_lab/sdv_production_store.py",
    "multisport_lab/sdv_production_archive.py", "multisport_lab/sdv_production_runner.py",
    "multisport_lab/sdv_production_publication.py", "multisport_lab/sdv_production_remote.py",
    "multisport_lab/sdv_production_coordinator.py",
    "config/sdv_production_policy_v1.json", ".github/workflows/nba-operations.yml")
LEGACY_SOURCE_FILES = tuple(dict.fromkeys((*FROZEN_SOURCE_FILES, *PRODUCTION_SOURCE_FILES)))
# Operating repairs are explicitly pinned too. Legacy originals retain their
# original inventory and can be recovered without claiming those bytes execute
# the new held coordinator.
SOURCE_FILES = (*LEGACY_SOURCE_FILES, "multisport_lab/sdv_production_held.py",
                "config/sdv_production_policy_v2.json")
FORECAST_FIELDS = {"schema_version", "protocol_id", "plan_id", "cycle_id", "mode", "evidence_lane", "model_key",
    "model_version", "producer_version", "producer_binding", "history_ref", "history_rows", "history_panel_sha256",
    "history_panel_cutoff", "history_availability", "input_ref", "input_id", "event_snapshot_id", "event_id",
    "event_starts_at", "player_id", "player_label", "team_id", "opponent_id", "matchup", "cutoff_at", "history_freeze",
    "trained_through", "conditioning", "period", "extra_time_policy", "qualification", "generation_started_at",
    "generation_completed_at", "verified_at", "issued_at", "categories", "reported_minutes", "joint_recipe", "forecast_id"}
INTENT_FIELDS = {"schema_version", "protocol_id", "plan_id", "cycle_id", "mode", "input_ref", "input_id",
    "producer_binding_id", "history_ref", "player_ids", "created_at", "intent_id"}
SUBJECT_FIELDS = ("plan_id", "cycle_id", "mode", "event_id", "event_snapshot_id", "player_id", "team_id", "opponent_id")
OUTCOME_FIELDS = {"schema_version", "protocol_id", *SUBJECT_FIELDS, "event_starts_at", "season_ending_year", "season_type",
    "status", "source_archive_refs", "source_observed_at", "normalized_at", "normalizer_version", "primitives", "minutes",
    "minutes_precision", "categories", "correction_revision", "previous_outcome_id", "outcome_id"}
GRADE_FIELDS = {"schema_version", "protocol_id", *SUBJECT_FIELDS, "model_key", "forecast_id", "outcome_id", "graded_at",
    "status", "categories", "financial_settlement", "qualification", "correction_revision", "previous_grade_id", "grade_id"}
NORMALIZER_VERSION = "sdv-production-final-csv-v1"
require, exact, sha, text, clock = common.require, common.exact, common.sha, common.text, common.clock
seal, check_seal = common.seal, common.check_seal


def _now():
    return common.now()


def _inputs():
    from . import sdv_production_inputs
    return sdv_production_inputs


def make_source_binding(commit=None, *, root=None):
    """Pin executable bytes once, independently of later documentation commits."""
    root = Path(root or Path(__file__).resolve().parents[1])
    files = {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in SOURCE_FILES}
    require(files["multisport_lab/baseline.py"] == common.LAW_SHA256["R0"]
        and files["multisport_lab/development_003.py"] == common.LAW_SHA256["K0"], "Frozen production mathematical law changed")
    if commit is not None:
        sha(commit, 40)
        for name, expected in files.items():
            result = subprocess.run(["git", "show", commit+":"+name], cwd=root, capture_output=True, check=False, timeout=30)
            require(result.returncode == 0 and hashlib.sha256(result.stdout).hexdigest() == expected,
                "Executed production source differs from frozen commit: "+name)
    return seal({"schema_version":BINDING_SCHEMA, "commit":commit, "files":files,
        "law_sha256":dict(common.LAW_SHA256)}, "binding_id")


def validate_binding(body, *, current=False, root=None):
    exact(body, {"schema_version", "commit", "files", "law_sha256", "binding_id"}, "producer binding")
    inventory = {LEGACY_BINDING_SCHEMA: LEGACY_SOURCE_FILES, BINDING_SCHEMA: SOURCE_FILES}.get(body["schema_version"])
    require(inventory is not None and type(body["files"]) is dict
        and set(body["files"]) == set(inventory) and body["law_sha256"] == common.LAW_SHA256,
        "Production producer source inventory/law differs")
    for value in body["files"].values():sha(value)
    require(body["files"]["multisport_lab/baseline.py"] == common.LAW_SHA256["R0"]
        and body["files"]["multisport_lab/development_003.py"] == common.LAW_SHA256["K0"], "Wrong frozen production law bytes")
    if body["commit"] is not None:sha(body["commit"], 40)
    check_seal(body, "binding_id")
    if current:require(body == make_source_binding(body["commit"], root=root), "Current executed production source differs from binding")
    return body


def validate_intent(body):
    exact(body, INTENT_FIELDS, "intent")
    require(body["schema_version"] == INTENT_SCHEMA and body["protocol_id"] == PROTOCOL_ID and body["mode"] in MODES,
        "Wrong production intent scope")
    text(body["cycle_id"])
    for key in ("plan_id", "input_id", "producer_binding_id"):sha(body[key])
    require(LedgerRef.from_record(body["input_ref"]).kind == "input_captures"
        and LedgerRef.from_record(body["history_ref"]).kind == "research_inputs"
        and LedgerRef.from_record(body["history_ref"]).record_id == common.HISTORY_ID, "Wrong production intent references")
    ids=body["player_ids"]
    require(type(ids) is list and 0 < len(ids) <= common.make_policy()["players_per_shard"]
        and len(set(ids)) == len(ids) and all(type(pid) is str and re.fullmatch(r"[1-9][0-9]*", pid) for pid in ids), "Invalid production shard cohort")
    require(clock(body["created_at"]) <= _now(), "Future production intent")
    check_seal(body, "intent_id")
    return body


def _window(body, at, *, started=None):
    cutoff=clock(body["event_starts_at"])-timedelta(minutes=90)
    policy=common.make_policy()
    require(cutoff <= at <= cutoff+timedelta(seconds=policy["generation_window_seconds"]), "Outside production T90..T75 issuance window")
    if started is not None:
        require(started <= at and (at-started).total_seconds() <= policy["original_latency_seconds"], "Production generation/verification exceeds latency")


def validate_forecast(body, input_body=None, *, now=None):
    exact(body, FORECAST_FIELDS, "forecast")
    require(body["schema_version"] == FORECAST_SCHEMA and body["protocol_id"] == PROTOCOL_ID
        and body["mode"] in MODES and body["model_key"] in common.MODEL_VERSIONS, "Wrong production forecast scope")
    model=body["model_key"]
    require(body["model_version"] == common.MODEL_VERSIONS[model] and body["producer_version"] == PRODUCERS[model]
        and body["conditioning"] == "CONDITIONAL_ON_APPEARANCE" and body["period"] == "full_game"
        and body["extra_time_policy"] == "includes_overtime" and body["qualification"] == "UNAVAILABLE", "Wrong production model/participation semantics")
    for key in ("cycle_id", "event_id", "player_id", "player_label", "team_id", "opponent_id", "matchup"):text(body[key])
    require(body["team_id"] != body["opponent_id"], "Production team/opponent conflict")
    for key in ("plan_id", "input_id", "event_snapshot_id"):sha(body[key])
    validate_binding(body["producer_binding"])
    require(body["history_rows"] == common.HISTORY_ROWS and body["history_panel_sha256"] == common.HISTORY_SHA256
        and body["history_availability"] == HISTORY_AVAILABILITY, "Production fixed history changed")
    history_ref=LedgerRef.from_record(body["history_ref"])
    require(history_ref.kind == "research_inputs" and history_ref.record_id == common.HISTORY_ID
        and LedgerRef.from_record(body["input_ref"]).kind == "input_captures", "Wrong production input/history references")
    start=clock(body["event_starts_at"]);cutoff=clock(body["cutoff_at"]);freeze=clock(body["history_freeze"])
    require(cutoff == start-timedelta(minutes=90) and freeze == cutoff.replace(hour=0,minute=0,second=0,microsecond=0)
        and clock(body["trained_through"]) <= freeze and clock(body["history_panel_cutoff"]) <= freeze, "Production causal cutoff changed")
    started,completed,verified=(clock(body[key]) for key in ("generation_started_at", "generation_completed_at", "verified_at"))
    require(started <= completed <= verified <= utc(now or _now()), "Production generation clocks conflict")
    if body["mode"] == "DEVELOPMENT_ONLY":
        require(body["evidence_lane"] == "DEVELOPMENT_ONLY" and body["issued_at"] is None, "Development became production issuance")
    else:
        require(body["evidence_lane"] == EVIDENCE_LANE and body["producer_binding"]["commit"] is not None
            and body["issued_at"] == body["verified_at"], "Production original lacks exact producer/actual issuance")
        _window(body, verified, started=started)
    _categories_valid(body["categories"])
    minutes=body["reported_minutes"]
    exact(minutes, {"pmf", "mean", "interval80", "precision"}, "reported minutes")
    _validate_pmf(minutes["pmf"], count=False)
    require(minutes["precision"] == "reported_source_precision_not_exact_workload"
        and minutes["interval80"] == [quantile(minutes["pmf"],.1), quantile(minutes["pmf"],.9)]
        and math.isclose(number(minutes["mean"]),math.fsum(a["value"]*number(a["probability"]) for a in minutes["pmf"]),abs_tol=1e-10), "Production minute distribution differs")
    recipe=body["joint_recipe"]
    exact(recipe, {"algorithm", "input_sha256", "joint_sha256", "support_atom_count", "player_history_count", "pool_history_count", "omitted_atoms"}, "joint recipe")
    require(recipe["algorithm"] == common.MODEL_VERSIONS[model] and recipe["omitted_atoms"] == 0
        and type(recipe["support_atom_count"]) is int and 0 < recipe["support_atom_count"] <= common.HISTORY_ROWS
        and recipe["pool_history_count"] == recipe["support_atom_count"] and type(recipe["player_history_count"]) is int
        and 0 <= recipe["player_history_count"] <= recipe["pool_history_count"], "Complete production joint law omitted atoms")
    sha(recipe["input_sha256"]);sha(recipe["joint_sha256"])
    if input_body is not None:
        _inputs().validate_input(input_body)
        require(body["plan_id"] == input_body["plan_id"] and body["cycle_id"] == input_body["cycle_id"]
            and body["input_id"] == input_body["input_id"] and body["mode"] == input_body["mode"]
            and body["producer_binding"] == input_body["producer_binding"]
            and all(body[key] == input_body["event"][key] for key in ("event_id", "event_snapshot_id", "event_starts_at")), "Production forecast/input identity differs")
        require(any(all(body[key] == candidate[key] for key in ("player_id", "player_label", "team_id", "opponent_id")) for candidate in input_body["candidates"]), "Production player is outside admitted cohort")
        require(clock(input_body["normalized_at"]) <= started, "Production generation preceded input normalization")
        _inputs().freshness(input_body, at=verified, require_retrieval_window=body["mode"] == "PROSPECTIVE_RESEARCH")
        require(body["matchup"] == input_body["event"]["away_team_name"]+" @ "+input_body["event"]["home_team_name"], "Production matchup differs")
    check_seal(body, "forecast_id")
    require(len(canonical(body)) <= 62*1024, "Complete production forecast exceeds encoded reserve")
    return body


class PreparedLaws:
    """Prepare the unchanged history/pool/context once for a same-event shard.

    Per-player personal weights and complete joint atoms still follow R0's exact
    arithmetic/order. K0 is the original WorkloadPrior with its normal caches.
    This is execution reuse; no parameters, causal rows or probability change.
    """
    def __init__(self,history,target,*,mode):
        self.started_at=_now()
        require(mode in MODES,"Invalid prepared production mode")
        eligible=[];identities=set();event_starts={}
        for row in history:
            require(isinstance(row,HistoricalAppearance),"Prepared production history must contain resolved appearances")
            identity=(row.id_namespace,row.event_id,row.player_id)
            require(identity not in identities and row.id_namespace == target.id_namespace,"Duplicate/foreign prepared history identity")
            identities.add(identity)
            require(row.event_id not in event_starts or event_starts[row.event_id] == row.event_start,"Prepared history event clocks conflict")
            event_starts[row.event_id]=row.event_start
            if row.event_id != target.event_id and row.event_start < target.history_freeze and row.outcome_available_at <= target.history_freeze:eligible.append(row)
        eligible.sort(key=lambda row:(row.event_start,row.event_id,row.player_id))
        require(bool(eligible),"INSUFFICIENT_CAUSAL_HISTORY: no eligible completed production history")
        self.rows=eligible;self.target=target;self.mode=mode
        latest=max(row.event_start for row in eligible)
        self.pool=[2**(-(latest-row.event_start).total_seconds()/86400/HALF_LIFE_DAYS) for row in eligible]
        self.pool_total=math.fsum(self.pool);self.lines=[row.primitive_line() for row in eligible]
        self.own=[2**(-(target.cutoff-row.event_start).total_seconds()/86400/HALF_LIFE_DAYS) for row in eligible]
        self.trained=max(row.outcome_available_at for row in eligible)
        # Canonical key order exactly matches baseline.digest(payload). Rows are
        # encoded/hashed once; the final target object is the only changing part.
        prefix=(b'{"history_freeze":'+canonical(stamp(target.history_freeze))+b',"model_version":'+canonical(R0_VERSION)
            +b',"protocol_id":'+canonical(R0_PROTOCOL)+b',"rows":'+canonical([row.to_record() for row in eligible])+b',"target":')
        self.input_hash=hashlib.sha256(prefix)
        self.kernel=WorkloadPrior(history)

    def for_target(self,target):
        require(target.event_id == self.target.event_id and target.event_start == self.target.event_start
            and target.id_namespace == self.target.id_namespace,"Prepared law cannot cross event/cutoff")
        own=[weight if row.player_id == target.player_id else 0.0 for row,weight in zip(self.rows,self.own)]
        denominator=PRIOR_APPEARANCES+math.fsum(own)
        atoms=tuple(WeightedOutcome(source_event_id=row.event_id,source_player_id=row.player_id,line=line,
            weight=(personal+PRIOR_APPEARANCES*pool/self.pool_total)/denominator)
            for row,line,personal,pool in zip(self.rows,self.lines,own,self.pool) if personal+pool > 0)
        source=self.input_hash.copy();source.update(canonical(target.to_record()));source.update(b"}")
        carrier=_DevelopmentDistribution if self.mode == "DEVELOPMENT_ONLY" else JointForecast
        reference=carrier(target=target,issued_at=None if self.mode == "DEVELOPMENT_ONLY" else _now(),trained_through=self.trained,
            input_sha256=source.hexdigest(),support=atoms,player_history_count=sum(row.player_id == target.player_id for row in self.rows),pool_history_count=len(self.rows))
        return {"R0":reference,"K0":self.kernel.forecast(target,reference)}


def generate_pair(input_body, input_ref, binding, history_ref, history, *, player_id, mode, prepared=None):
    """Both complete laws are verified before either original may be written."""
    _inputs().validate_input(input_body);validate_binding(binding,current=True)
    require(mode in MODES and input_body["mode"] == mode and input_body["producer_binding"] == binding,
        "Production mode/input/producer differs")
    require(isinstance(input_ref,LedgerRef) and input_ref.kind == "input_captures"
        and isinstance(history_ref,LedgerRef) and history_ref.kind == "research_inputs" and history_ref.record_id == common.HISTORY_ID,
        "Wrong production retained references")
    require(len(history) == common.HISTORY_ROWS, "Production generation requires all 26,645 retained history rows")
    candidates=[row for row in input_body["candidates"] if row["player_id"] == player_id]
    require(len(candidates) == 1, "Production player is outside selected source roster")
    candidate=candidates[0];event=input_body["event"]
    target=ForecastTarget(event["event_id"],player_id,clock(event["event_starts_at"]))
    started=prepared.started_at if prepared is not None else _now()
    _inputs().freshness(input_body,at=started,require_retrieval_window=mode == "PROSPECTIVE_RESEARCH")
    if mode == "PROSPECTIVE_RESEARCH":
        require(binding["commit"] is not None, "Genuine production requires a committed producer")
        _window(event,started)
    laws=prepared.for_target(target) if prepared is not None else (_development_laws if mode == "DEVELOPMENT_ONLY" else _fit_laws)(history,target)
    require(set(laws) == set(common.MODEL_VERSIONS), "Both unchanged production laws must preflight")
    pair=[]
    for key in common.MODEL_VERSIONS:
        law=laws[key];categories,minutes=_categories(law),_minutes(law)
        for atom in minutes["pmf"]:
            if float(atom["value"]).is_integer():atom["value"]=int(atom["value"])
        minutes["interval80"]=[int(v) if float(v).is_integer() else v for v in minutes["interval80"]]
        joint_sha=joint_fingerprint(law);completed=_now()
        require(law.target == target and {row["code"] for row in categories} == set(MARKETS), "Production joint law/target differs")
        body={"schema_version":FORECAST_SCHEMA,"protocol_id":PROTOCOL_ID,"plan_id":input_body["plan_id"],"cycle_id":input_body["cycle_id"],
            "mode":mode,"evidence_lane":"DEVELOPMENT_ONLY" if mode == "DEVELOPMENT_ONLY" else EVIDENCE_LANE,
            "model_key":key,"model_version":common.MODEL_VERSIONS[key],"producer_version":PRODUCERS[key],"producer_binding":binding,
            "history_ref":history_ref.to_record(),"history_rows":common.HISTORY_ROWS,"history_panel_sha256":common.HISTORY_SHA256,
            "history_panel_cutoff":stamp(max(row.outcome_available_at for row in history)),"history_availability":HISTORY_AVAILABILITY,
            "input_ref":input_ref.to_record(),"input_id":input_body["input_id"],"event_snapshot_id":event["event_snapshot_id"],
            "event_id":target.event_id,"event_starts_at":stamp(target.event_start),**candidate,
            "matchup":event["away_team_name"]+" @ "+event["home_team_name"],"cutoff_at":stamp(target.cutoff),
            "history_freeze":stamp(target.history_freeze),"trained_through":stamp(law.trained_through),
            "conditioning":"CONDITIONAL_ON_APPEARANCE","period":"full_game","extra_time_policy":"includes_overtime",
            "qualification":"UNAVAILABLE","generation_started_at":stamp(started),"generation_completed_at":stamp(completed),
            "verified_at":stamp(completed),"issued_at":None if mode == "DEVELOPMENT_ONLY" else stamp(completed),
            "categories":categories,"reported_minutes":minutes,"joint_recipe":{"algorithm":common.MODEL_VERSIONS[key],
                "input_sha256":law.input_sha256,"joint_sha256":joint_sha,"support_atom_count":len(law.support),
                "player_history_count":law.player_history_count,"pool_history_count":law.pool_history_count,"omitted_atoms":0}}
        # All category/minute checks finish before the actual verification clock.
        validate_forecast(seal(body,"forecast_id"),input_body)
        verified=_now();body["verified_at"]=stamp(verified)
        if mode == "PROSPECTIVE_RESEARCH":
            body["issued_at"]=stamp(verified);_window(event,verified,started=started)
            _inputs().freshness(input_body,at=verified,require_retrieval_window=True)
        pair.append(seal(body,"forecast_id"))
    # Pair preflight includes the slower peer's completion, never atomic claims.
    if mode == "PROSPECTIVE_RESEARCH":
        _inputs().freshness(input_body,at=_now(),require_retrieval_window=True)
        _window(event,_now(),started=started)
    return pair


def _intent_for(store,input_ref,body,binding,history_ref,player_ids,refs,*,allow_create):
    intents=[(ref,record) for ref,record in store.records() if record["schema_version"] == INTENT_SCHEMA
        and record["cycle_id"] == body["cycle_id"] and record["player_ids"] == list(player_ids)]
    require(len(intents) <= 1,"Duplicate production shard intents")
    if intents:
        ref,intent=intents[0]
        require(intent["input_ref"] == input_ref.to_record() and intent["producer_binding_id"] == binding["binding_id"]
            and intent["history_ref"] == history_ref.to_record() and intent["mode"] == body["mode"],"Recovery attempted a different production input/producer")
        return ref
    require(allow_create,"Genuine production requires an original intent recovered before T90")
    if body["mode"] == "PROSPECTIVE_RESEARCH":
        require(_now() <= clock(body["event"]["event_starts_at"])-timedelta(minutes=90),"Production intent creation missed T90")
    intent=seal({"schema_version":INTENT_SCHEMA,"protocol_id":PROTOCOL_ID,"plan_id":body["plan_id"],"cycle_id":body["cycle_id"],
        "mode":body["mode"],"input_ref":input_ref.to_record(),"input_id":body["input_id"],"producer_binding_id":binding["binding_id"],
        "history_ref":history_ref.to_record(),"player_ids":list(player_ids),"created_at":stamp(_now())},"intent_id")
    return store.append_body(intent,references=tuple(refs),logical_id="production-intent:"+body["cycle_id"]+":"+digest(list(player_ids)))


def prepare_intent(store,input_ref,binding,player_ids,*,plan_ref,authorization_ref=None,checkpoint=None,mode=None):
    """Capture-phase original intent and remote acknowledgment, before T90."""
    with store.lock():
        body=store.read_body(input_ref);_inputs().validate_input(body);validate_binding(binding,current=True)
        require(mode is None or mode == body["mode"],"Production intent mode differs")
        require(binding == body["producer_binding"] and list(player_ids) in body["shards"],"Production intent shard/input differs")
        require(store.read_body(plan_ref)["plan_id"] == body["plan_id"],"Production intent plan differs")
        refs=[input_ref,plan_ref]
        if body["mode"] == "PROSPECTIVE_RESEARCH":
            from .sdv_production_runner import require_execution_context
            require(authorization_ref is not None and callable(checkpoint),"Production intent requires actual authorization/checkpoint")
            require_execution_context(store.read_body(authorization_ref),body,binding,phase="PREPARE")
            require(store.admission(input_ref)["eligible"],"Production intent input has no timely independent recovery")
            refs.append(authorization_ref)
        else:require(authorization_ref is None,"Development cannot borrow genuine intent authority")
        history_ref,_,_=retained_history(getattr(store,"source_root",getattr(store,"project_root",None)))
        ref=_intent_for(store,input_ref,body,binding,history_ref,player_ids,refs,allow_create=True)
        if checkpoint is not None:checkpoint((ref,))
        if body["mode"] == "PROSPECTIVE_RESEARCH":
            require(store.admission(ref)["eligible"],"Production intent remote completion missed T90 or remains unacknowledged")
        return ref


def issue_shard(store, input_ref, binding, player_ids, *, plan_ref, authorization_ref=None, checkpoint=None, mode=None):
    """Recover first; persist missing peers only while their original gates hold."""
    with store.lock():
        body=store.read_body(input_ref);_inputs().validate_input(body);validate_binding(binding,current=True)
        mode=body["mode"] if mode is None else mode
        require(mode == body["mode"] and binding == body["producer_binding"] and list(player_ids) in body["shards"], "Production shard/input binding differs")
        require(isinstance(plan_ref,LedgerRef) and store.read_body(plan_ref)["plan_id"] == body["plan_id"], "Wrong production plan reference")
        refs=[input_ref,plan_ref]
        if mode == "PROSPECTIVE_RESEARCH":
            from .sdv_production_runner import require_execution_context
            require(authorization_ref is not None and callable(checkpoint), "Production issuance requires actual runner authorization and remote checkpoint")
            require_execution_context(store.read_body(authorization_ref),body,binding)
            require(store.admission(input_ref)["eligible"], "Production input has no timely independent durable recovery")
            refs.append(authorization_ref)
        else:require(authorization_ref is None, "Development cannot borrow genuine authorization")
        root=getattr(store,"source_root",getattr(store,"project_root",None))
        history_ref,history,_=retained_history(root)
        intent_ref=_intent_for(store,input_ref,body,binding,history_ref,player_ids,refs,allow_create=mode == "DEVELOPMENT_ONLY")
        if mode == "PROSPECTIVE_RESEARCH":require(store.admission(intent_ref)["eligible"],"Production intent has no timely independent durable recovery")
        retained={}
        for ref,record in store.records():
            if record["schema_version"] != FORECAST_SCHEMA or record["cycle_id"] != body["cycle_id"]:continue
            key=(record["player_id"],record["model_key"])
            require(key not in retained, "Duplicate production original")
            require(record["input_ref"] == input_ref.to_record() and record["producer_binding"] == binding and record["mode"] == mode,
                "Original production input/producer/mode changed")
            retained[key]=(ref,record)
        checkpoint_subjects=common.make_policy()["checkpoint_subjects"]
        require(checkpoint_subjects == 4,"Production checkpoint batch differs from registered four-subject policy")
        pending=[];subjects_since_checkpoint=0;prepared=None
        def flush_pending():
            if checkpoint is None:return
            while pending:
                selected=tuple(pending[:2*checkpoint_subjects])
                checkpoint(selected)
                if mode == "PROSPECTIVE_RESEARCH":
                    require(all(store.admission(ref).get("remote_recovered_at") is not None for ref in selected),
                        "Production checkpoint returned without original-target readback acknowledgment")
                del pending[:len(selected)]
        # A crash may leave original bytes without an acknowledged readback.
        # Recover those exact originals before generating any missing subject.
        for (pid,_),(ref,original) in retained.items():
            if pid in player_ids and store.admission(ref).get("remote_recovered_at") is None:pending.append(ref)
        try:
            if pending and mode == "PROSPECTIVE_RESEARCH":
                _inputs().freshness(body,at=_now(),require_retrieval_window=True)
                for ref in pending:
                    original=next(value[1] for value in retained.values() if value[0] == ref)
                    _window(body["event"],_now(),started=clock(original["generation_started_at"]))
            flush_pending()
            for pid in player_ids:
                missing=[key for key in common.MODEL_VERSIONS if (pid,key) not in retained]
                if not missing:continue
                if prepared is None:
                    if mode == "PROSPECTIVE_RESEARCH":
                        _inputs().freshness(body,at=_now(),require_retrieval_window=True);_window(body["event"],_now())
                    prepared=PreparedLaws(history,ForecastTarget(body["event"]["event_id"],pid,clock(body["event"]["event_starts_at"])),mode=mode)
                pair=generate_pair(body,input_ref,binding,history_ref,history,player_id=pid,mode=mode,prepared=prepared)
                wrote=False
                for forecast in pair:
                    if forecast["model_key"] not in missing:continue
                    if mode == "PROSPECTIVE_RESEARCH":
                        _inputs().freshness(body,at=_now(),require_retrieval_window=True)
                        _window(body["event"],_now(),started=clock(forecast["generation_started_at"]))
                        with store._verified_forecast_write(forecast,(input_ref,intent_ref)):
                            ref=store.append_body(forecast,references=(input_ref,intent_ref))
                    else:ref=store.append_body(forecast,references=(input_ref,intent_ref))
                    retained[(pid,forecast["model_key"])]=(ref,forecast);pending.append(ref);wrote=True
                if wrote:subjects_since_checkpoint+=1
                if subjects_since_checkpoint >= checkpoint_subjects:
                    flush_pending();subjects_since_checkpoint=0
            flush_pending()
        except BaseException as error:
            # Even a late or interrupted original remains evidence. A recovery
            # checkpoint cannot change its actual clocks or force eligibility.
            try:flush_pending()
            except BaseException as recovery_error:
                if hasattr(error,"add_note"):error.add_note("Best-effort original retention also failed: "+str(recovery_error))
            raise
        return store.recover()


def _revision(body, previous, *, field, identity):
    require(type(body["correction_revision"]) is int and body["correction_revision"] in {1,2}, "Automatic production correction exceeds two versions")
    prior=body[field]
    require((body["correction_revision"] == 1 and prior is None) or (body["correction_revision"] == 2 and sha(prior)), "Production correction predecessor differs")
    if previous is not None:
        require(body["correction_revision"] == previous["correction_revision"]+1 and prior == previous[identity]
            and all(body[key] == previous[key] for key in SUBJECT_FIELDS), "Production correction changed original subject/chain")


def validate_outcome(body, *, previous=None):
    exact(body,OUTCOME_FIELDS,"outcome")
    require(body["schema_version"] == OUTCOME_SCHEMA and body["protocol_id"] == PROTOCOL_ID and body["mode"] in MODES
        and body["status"] in OUTCOME_STATUSES and body["normalizer_version"] == NORMALIZER_VERSION, "Wrong production outcome meaning")
    for key in ("cycle_id","event_id","player_id","team_id","opponent_id"):text(body[key])
    for key in ("plan_id","event_snapshot_id"):sha(body[key])
    require(body["team_id"] != body["opponent_id"] and type(body["season_ending_year"]) is int and 2000 <= body["season_ending_year"] <= 2100
        and body["season_type"] in {"1","2","3"}, "Production outcome identity differs")
    require(type(body["source_archive_refs"]) is list and len(body["source_archive_refs"]) == 2, "Production final outcome needs both exact raw archives")
    for ref in body["source_archive_refs"]:common.archive_ref(ref,diagnostic=body["mode"] == "DEVELOPMENT_ONLY")
    require(body["source_archive_refs"][0] != body["source_archive_refs"][1], "Production outcome archives cannot alias")
    observed,normalized=clock(body["source_observed_at"]),clock(body["normalized_at"])
    require(observed <= normalized <= _now(), "Production outcome clocks conflict")
    require(observed <= clock(body["event_starts_at"])+timedelta(days=common.make_policy()["correction_capture_days"]),
        "Production final source observation exceeds its capture window")
    if body["status"] in {"APPEARED","DNP"}:require(observed >= clock(body["event_starts_at"]), "Production outcome precedes event")
    else:clock(body["event_starts_at"])
    if body["status"] == "APPEARED":
        require(body["categories"] == _outcome_categories(body["primitives"]), "Production outcome counts conflict")
        mapping={"fg2m":"FG2M","fg3m":"FG3M","ftm":"FTM","rebounds":"REB","assists":"AST","turnovers":"TOV","blocks":"BLK","steals":"STL"}
        PrimitiveLine(minutes=body["minutes"],minutes_precision=body["minutes_precision"],**{key:body["primitives"][value] for key,value in mapping.items()})
    else:require(body["primitives"] is None and body["minutes"] is None and body["minutes_precision"] is None and body["categories"] == [], "DNP/missing/nonfinal is not zero production")
    _revision(body,previous,field="previous_outcome_id",identity="outcome_id")
    if previous is not None:
        require(clock(previous["source_observed_at"]) <= observed and clock(previous["normalized_at"]) <= normalized
            and body["event_starts_at"] == previous["event_starts_at"] and body["season_ending_year"] == previous["season_ending_year"]
            and body["season_type"] == previous["season_type"], "Production outcome correction clocks/season differ")
    check_seal(body,"outcome_id");return body


def make_grade(forecast,outcome,*,previous=None,graded_at=None):
    validate_forecast(forecast);validate_outcome(outcome)
    require(all(forecast[key] == outcome[key] for key in SUBJECT_FIELDS), "Production grade subject differs")
    at=_now() if graded_at is None else clock(graded_at)
    require(clock(outcome["normalized_at"]) <= at <= _now()
        and (forecast["issued_at"] is None or clock(forecast["issued_at"]) <= at), "Production grade clock precedes evidence")
    status="SCORED" if outcome["status"] == "APPEARED" else "DNP_NOT_SCORED" if outcome["status"] == "DNP" else outcome["status"]
    if previous is not None:
        validate_grade(previous)
        require(previous["forecast_id"] == forecast["forecast_id"] and clock(previous["graded_at"]) <= at, "Production grade correction changes forecast/clock")
    body={"schema_version":GRADE_SCHEMA,"protocol_id":PROTOCOL_ID,**{key:forecast[key] for key in SUBJECT_FIELDS},
        "model_key":forecast["model_key"],"forecast_id":forecast["forecast_id"],"outcome_id":outcome["outcome_id"],"graded_at":stamp(at),
        "status":status,"categories":_score_categories(forecast,outcome) if status == "SCORED" else [],
        "financial_settlement":"NOT_EVALUATED","qualification":"UNAVAILABLE","correction_revision":1 if previous is None else previous["correction_revision"]+1,
        "previous_grade_id":None if previous is None else previous["grade_id"]}
    result=seal(body,"grade_id");validate_grade(result,previous=previous);return result


def validate_grade(body,forecast=None,outcome=None,*,previous=None):
    exact(body,GRADE_FIELDS,"grade")
    require(body["schema_version"] == GRADE_SCHEMA and body["protocol_id"] == PROTOCOL_ID and body["mode"] in MODES
        and body["model_key"] in common.MODEL_VERSIONS and body["status"] in OUTCOME_STATUSES-{"APPEARED","DNP"}|{"SCORED","DNP_NOT_SCORED"}
        and body["financial_settlement"] == "NOT_EVALUATED" and body["qualification"] == "UNAVAILABLE", "Wrong production grade semantics")
    for key in ("plan_id","event_snapshot_id","forecast_id","outcome_id"):sha(body[key])
    for key in ("cycle_id","event_id","player_id","team_id","opponent_id"):text(body[key])
    require(body["team_id"] != body["opponent_id"] and clock(body["graded_at"]) <= _now(), "Production grade identity/clock differs")
    if body["status"] != "SCORED":require(body["categories"] == [], "Unscored production grade has numerical scores")
    else:
        require(type(body["categories"]) is list and len(body["categories"]) == 14
            and {row.get("code") for row in body["categories"]} == set(MARKETS), "Production grade needs all14 categories")
        for row in body["categories"]:
            exact(row,{"code","observed","crps","log_loss","log_loss_status","brier"},"category grade")
            require(type(row["observed"]) is int and row["observed"] >= 0 and (row["code"] not in {"DD","TD"} or row["observed"] in {0,1}), "Invalid production grade observation")
            _decimal_score(row["crps"])
            if row["log_loss_status"] == "ZERO_SUPPORT":require(row["log_loss"] is None,"Zero-support grade must retain infinite log loss")
            else:
                require(row["log_loss_status"] == "FINITE","Unknown production log-loss status");_decimal_score(row["log_loss"])
            if row["code"] in {"DD","TD"}:require(Decimal(0) <= _decimal_score(row["brier"]) <= Decimal(1),"Invalid production binary Brier")
            else:require(row["brier"] is None,"Nonbinary production grade has Brier")
    _revision(body,previous,field="previous_grade_id",identity="grade_id")
    if previous is not None:require(body["forecast_id"] == previous["forecast_id"] and clock(previous["graded_at"]) <= clock(body["graded_at"]),"Production grade correction changes forecast/clock")
    if (forecast is None) != (outcome is None):raise IntegrityError("Production grade replay needs both original forecast and outcome")
    if forecast is not None:
        expected=make_grade(forecast,outcome,previous=previous,graded_at=body["graded_at"])
        require(body == expected,"Production statistical grade differs from original probabilities/outcome")
    check_seal(body,"grade_id");return body


def validate_body(body,input_body=None):
    require(type(body) is dict,"Production record is not an object")
    validators={FORECAST_SCHEMA:lambda value:validate_forecast(value,input_body),INTENT_SCHEMA:validate_intent,
        OUTCOME_SCHEMA:validate_outcome,GRADE_SCHEMA:validate_grade}
    require(body.get("schema_version") in validators,"Unknown production forecast record schema")
    return validators[body["schema_version"]](body)


def _rows(raw):
    require(type(raw) is bytes and 0 < len(raw) <= common.make_policy()["maximum_csv_bytes"], "Production CSV exceeds bounded original bytes")
    try:
        reader=csv.DictReader(io.StringIO(raw.decode("utf-8-sig"),newline=""),strict=True)
        require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)), "Production CSV has missing/duplicate headers")
        rows=[]
        for row in reader:
            require(len(rows) < common.make_policy()["maximum_source_rows"] and None not in row
                and all(value is not None for value in row.values()), "Production CSV rows exceed bound or are malformed")
            rows.append(row)
        return rows
    except (UnicodeError,csv.Error) as exc:raise IntegrityError("Production CSV encoding/structure is invalid") from exc


def _bool(value):
    if value in ("true","TRUE","True"):return True
    if value in ("false","FALSE","False"):return False
    if value in (None,"","NA"):return None
    raise IntegrityError("Invalid production source Boolean")


def _count(value):
    if value in (None,"","NA"):return None
    require(type(value) is str and re.fullmatch(r"[0-9]+",value), "Invalid production source count")
    return int(value)


def _line(original,event):
    """An explicit DNP may contain empty/zero placeholders, never production."""
    row=original.copy();row["season"]=_count(row.get("season"));row["did_not_play"]=_bool(row.get("did_not_play"))
    for field in SDV_FIELDS.values():row[field]=_count(row.get(field))
    value=row.get("minutes")
    require(value in (None,"","NA") or type(value) is str and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?",value), "Invalid production final minutes")
    row["minutes"]=None if value in (None,"","NA") else float(value)
    if row["did_not_play"] is True:
        require(row["minutes"] in (None,0) and all(row[field] in (None,0) for field in SDV_FIELDS.values()), "DNP contradicts supplied production")
        row["minutes"]=None
        for field in SDV_FIELDS.values():row[field]=None
    line=normalize_sdv_row(row)
    for field in ("two_point_field_goals_made","field_goals_two_point_made","FG2M"):
        if field in original and original[field] not in (None,"","NA"):
            supplied=_count(original[field])
            require(line.participation == "DNP" and supplied == 0 or supplied == line.fg2m,
                "Supplied FGM contradicts FG2M + FG3M")
    schedule=event.copy();schedule["season"]=_count(event.get("season"));schedule["status_type_completed"]=_bool(event.get("status_type_completed"))
    return with_sdv_schedule(line,schedule,standard_team_ids=frozenset())


def _event_result(schedule_rows,box_rows,forecast,season,season_type):
    ids=[row.get("game_id") for row in schedule_rows]
    require(all(type(value) is str and re.fullmatch(r"[1-9][0-9]*",value) for value in ids) and len(ids) == len(set(ids)), "Duplicate/invalid production final schedule identity")
    events=[row for row in schedule_rows if row["game_id"] == forecast["event_id"]]
    require(len(events) == 1,"Production final event missing from exact schedule")
    event=events[0]
    require({event.get("home_id"),event.get("away_id")} == {forecast["team_id"],forecast["opponent_id"]}
        and utc(event.get("game_date_time")) == clock(forecast["event_starts_at"])
        and _count(event.get("season")) == season and event.get("season_type") == season_type, "Production final event identity/start/season differs")
    keys=[(row.get("game_id"),row.get("athlete_id")) for row in box_rows]
    require(len(keys) == len(set(keys)) and all(type(g) is str and type(p) is str and re.fullmatch(r"[1-9][0-9]*",g)
        and re.fullmatch(r"[1-9][0-9]*",p) for g,p in keys), "Duplicate/invalid production final player identity")
    completed=_bool(event.get("status_type_completed"));name=event.get("status_type_name");state=event.get("status_type_state")
    require(completed is not None,"Production final event completion flag missing")
    if name in {"STATUS_CANCELED","STATUS_CANCELLED"}:
        require(not completed,"Cancelled event cannot be completed");return "CANCELLED",None
    if not completed:
        if name == "STATUS_POSTPONED":return "POSTPONED",None
        if state in {"pre","in"} and name in {"STATUS_SCHEDULED","STATUS_IN_PROGRESS","STATUS_HALFTIME","STATUS_END_PERIOD","STATUS_DELAYED"}:return "NONFINAL",None
        return "UNRESOLVED",None
    require(name == "STATUS_FINAL" and state == "post","Production final schedule status contradicts completion")
    scores={event.get("home_id"):_count(event.get("home_score")),event.get("away_id"):_count(event.get("away_score"))}
    require(all(type(value) is int for value in scores.values()),"Production final schedule scores missing")
    rows=[row for row in box_rows if row["game_id"] == forecast["event_id"]]
    if not rows:return "MISSING",None
    totals={team:0 for team in scores};seen=set();selected=None;unresolved=False
    for raw in rows:
        team,opponent=raw.get("team_id"),raw.get("opponent_team_id")
        require(team in scores and opponent in scores and team != opponent and _count(raw.get("team_score")) == scores[team]
            and _count(raw.get("opponent_team_score")) == scores[opponent], "Production player row conflicts with final team score/identity")
        line=_line(raw,event)
        if line.participation == "UNKNOWN":unresolved=True
        elif line.participation == "APPEARED":
            require(all(getattr(line,key) is not None for key in ("points","fgm","fg2m","fg3m","ftm","rebounds","assists","turnovers","blocks","steals"))
                and line.minutes is not None,"Production final appearance lacks complete counts/minutes")
            totals[team]+=line.points
        seen.add(team)
        if raw["athlete_id"] == forecast["player_id"]:
            require(team == forecast["team_id"] and opponent == forecast["opponent_id"],"Production final player changed original team")
            selected=line
    if unresolved:return "UNRESOLVED",None
    require(seen == set(scores) and totals == scores,"Production player PTS totals do not reconcile both final team scores")
    if selected is None:return "MISSING",None
    return {"APPEARED":"APPEARED","DNP":"DNP","UNKNOWN":"UNRESOLVED"}[selected.participation],selected


def _normalize_sources(forecast,*,schedule_raw,boxscore_raw,schedule_metadata,boxscore_metadata,
        source_originals,source_archive_refs,season,season_type,normalized_at,previous=None):
    validate_forecast(forecast)
    require(type(source_originals) is dict and set(source_originals) == {"schedule","boxscore"}, "Production final proof lacks exact publisher metadata originals")
    for role,raw,metadata in (("schedule",schedule_raw,schedule_metadata),("boxscore",boxscore_raw,boxscore_metadata)):
        _inputs().validate_source(raw,metadata,source_originals[role],role,season)
    deadline=clock(forecast["event_starts_at"])+timedelta(days=common.make_policy()["correction_capture_days"])
    require(all(clock(metadata["retrieval_started_at"]) <= clock(metadata["retrieved_at"]) <= deadline
        for metadata in (schedule_metadata,boxscore_metadata)), "Production final source retrieval exceeded its capture window")
    status,line=_event_result(_rows(schedule_raw),_rows(boxscore_raw),forecast,season,season_type)
    observed=max(clock(metadata["retrieved_at"]) for metadata in (schedule_metadata,boxscore_metadata))
    if status in {"APPEARED","DNP"}:
        require(all(clock(metadata["publisher_updated_at"]) >= clock(forecast["event_starts_at"])
            for metadata in (schedule_metadata,boxscore_metadata)), "Final publisher assets precede actual event")
    primitives=None;minutes=None;precision=None;categories=[]
    if status == "APPEARED":
        mapping={"FGM":"fgm","FG2M":"fg2m","FG3M":"fg3m","FTM":"ftm","PTS":"points","REB":"rebounds","AST":"assists","TOV":"turnovers","BLK":"blocks","STL":"steals"}
        primitives={key:getattr(line,field) for key,field in mapping.items()};categories=_outcome_categories(primitives)
        minutes=line.minutes;precision=line.minutes_precision
        if float(minutes).is_integer():minutes=int(minutes)
    result=seal({"schema_version":OUTCOME_SCHEMA,"protocol_id":PROTOCOL_ID,**{key:forecast[key] for key in SUBJECT_FIELDS},
        "event_starts_at":forecast["event_starts_at"],"season_ending_year":season,"season_type":season_type,"status":status,
        "source_archive_refs":list(source_archive_refs),"source_observed_at":stamp(observed),"normalized_at":normalized_at,
        "normalizer_version":NORMALIZER_VERSION,"primitives":primitives,"minutes":minutes,"minutes_precision":precision,"categories":categories,
        "correction_revision":1 if previous is None else previous["correction_revision"]+1,
        "previous_outcome_id":None if previous is None else previous["outcome_id"]},"outcome_id")
    validate_outcome(result,previous=previous);return result


def normalize_outcome(forecast,input_body,*,archive,schedule_ref,boxscore_ref,previous=None):
    """Normalize exact independently recoverable final originals; never collect."""
    validate_forecast(forecast,input_body)
    if previous is not None:validate_outcome(previous)
    schedule_raw,sm,smraw=archive.recover_source(schedule_ref)
    box_raw,bm,bmraw=archive.recover_source(boxscore_ref)
    return _normalize_sources(forecast,schedule_raw=schedule_raw,boxscore_raw=box_raw,schedule_metadata=sm,boxscore_metadata=bm,
        source_originals={"schedule":smraw,"boxscore":bmraw},source_archive_refs=[schedule_ref,boxscore_ref],
        season=input_body["event"]["season_ending_year"],season_type=input_body["event"]["season_type"],normalized_at=stamp(_now()),previous=previous)


def verify_outcome_sources(body,schedule_raw,boxscore_raw,schedule_metadata,boxscore_metadata,*,source_originals,forecasts,input_body=None):
    """Independent semantic replay keeps the original normalization/source clocks."""
    validate_outcome(body)
    require(0 < len(forecasts) <= 2 and len({row["model_key"] for row in forecasts}) == len(forecasts), "Production outcome replay requires retained original peer(s)")
    for forecast in forecasts:
        validate_forecast(forecast)
        require(all(body[key] == forecast[key] for key in SUBJECT_FIELDS),"Production outcome replay references another original subject")
    if input_body is not None:
        validate_forecast(forecasts[0],input_body)
        require(body["season_ending_year"] == input_body["event"]["season_ending_year"]
            and body["season_type"] == input_body["event"]["season_type"],"Production final season differs from admitted pregame input")
    # The prior ID/revision is carried exactly; source meaning is reconstructed
    # independently and never needs replacement forecast generation.
    replay=_normalize_sources(forecasts[0],schedule_raw=schedule_raw,boxscore_raw=boxscore_raw,schedule_metadata=schedule_metadata,
        boxscore_metadata=boxscore_metadata,source_originals=source_originals,source_archive_refs=body["source_archive_refs"],
        season=body["season_ending_year"],season_type=body["season_type"],normalized_at=body["normalized_at"])
    semantic_keys=set(OUTCOME_FIELDS)-{"outcome_id","previous_outcome_id","correction_revision"}
    require(all(body[key] == replay[key] for key in semantic_keys), "Production outcome differs from original archived source bytes")
    return body

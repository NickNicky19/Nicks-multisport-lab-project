"""One named-game paired operational readiness, independent of PROS004.

This module does not change either model law and contains no scheduler, provider
request, automatic activation, ticket selection or comparative study evaluator.
Originals survive failed persistence/acknowledgment and are never regenerated.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from . import baseline, pregame_sources
from .baseline import ForecastTarget, HistoricalAppearance, MARKETS
from .forecast_contract import FORECAST_SCHEMA, validate_forecast
from .integrity import (HASH_FORMAT, RECEIPT_SCHEMA, IntegrityError, canonical,
                        digest, read_receipt, stamp, utc)
from .ledger import (Ledger, LedgerRef, KINDS, MAX_LEDGER_BYTES, MAX_LEDGER_RECORDS,
                     _outcome_categories, _score_categories)
from .pros004_producer import (_fit_laws, _categories, _minutes, joint_fingerprint,
                              LAW_SHA256, MODEL_VERSIONS)
from .publication_ledger import CompositeEnvelopeLedger

PROTOCOL_ID = "NBA-PAIRED-OPS-002"
PREFIX = "nba-operational002-"
MODES = {"REAL_TIME_CAPTURED", "SYNTHETIC_DIAGNOSTIC", "READINESS_DIAGNOSTIC"}
PRODUCERS = {key: "operational002-"+key.lower()+"-producer-v1" for key in ("R0", "K0")}
ORIGINAL_HISTORY_ID = "dfa1c4345495eb3aa6b203f2e8309c89c112b6b78a36cd3d2c603d390776b6fc"
PANEL_ROWS, PANEL_BYTES = 26645, 14720351
PANEL_SHA256 = pregame_sources.PANEL_SHA
REPOSITORY = "NickNicky19/Nicks-multisport-lab-project"
JOURNAL = "evidence/operational002/completions.jsonl"
PROOF = "evidence/operational002/remote-recovery.json"
MAX_JOURNAL_BYTES = 256 * 1024
MAX_JOURNAL_ENTRIES = 128
MAX_PROOF_BYTES = 8 * 1024
CEILINGS = {"history": 8*1024, "event": 32*1024, "forecast": 64*1024,
            "outcome": 8*1024, "grade": 16*1024, "failure": 8*1024}
KIND = {"history": "research_inputs", "event": "research_inputs", "forecast": "forecasts",
        "outcome": "outcomes", "grade": "grades", "failure": "input_captures"}
OUTCOME_STATUSES = {"APPEARED", "DNP", "MISSING", "POSTPONED", "NONFINAL", "UNRESOLVED"}
SOURCE_FILES = ("multisport_lab/operational_pilot.py", "multisport_lab/operational_publication.py",
    "multisport_lab/operational_remote.py", "multisport_lab/operating_diagnostic.py",
    "multisport_lab/publication_ledger.py", "multisport_lab/operational_preflight.py",
    "multisport_lab/operational_raw.py", "multisport_lab/prospective_outcomes.py",
    "multisport_lab/offer_publication.py",
    "multisport_lab/pros004_records.py", "multisport_lab/pros004_completion.py",
    "multisport_lab/pros004_remote.py", "multisport_lab/pros004_snapshot.py",
    "multisport_lab/baseline.py", "multisport_lab/development_003.py",
    "multisport_lab/development_002.py", "multisport_lab/research_pilot.py",
    "multisport_lab/pros004_producer.py", "multisport_lab/pros004_inputs.py",
    "multisport_lab/pros004_publication.py", "multisport_lab/nba_data.py",
    "multisport_lab/basketball.py", "multisport_lab/integrity.py", "multisport_lab/ledger.py",
    "multisport_lab/forecast_contract.py", "multisport_lab/pregame_sources.py",
    "scripts/verify_pros004_readiness.py")


def _now():
    return datetime.now(timezone.utc)


def require(condition, message):
    if not condition:
        raise IntegrityError(message)


def exact(value, fields, label):
    require(type(value) is dict and set(value) == set(fields), "invalid OP002 "+label)


def clock(value):
    require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", value),
            "OP002 clocks require precise UTC")
    return utc(value)


def sha(value, size=64):
    require(type(value) is str and re.fullmatch(r"[a-f0-9]{"+str(size)+"}", value), "invalid OP002 hash")
    return value


def text(value):
    require(type(value) is str and 0 < len(value) <= 2048 and value.strip() == value, "invalid OP002 text")
    return value


def seal(body, key):
    return {**body, key: digest(body)}


def check_seal(body, key):
    require(body.get(key) == digest({k:v for k,v in body.items() if k != key}), "OP002 original checksum mismatch")


def _schema(name):
    return PREFIX+name+"-v1"


def make_plan(event, candidates, *, registered_at=None):
    """Freeze the named event and cohort before examining operational outputs."""
    body = {"schema_version": _schema("plan"), "protocol_id": PROTOCOL_ID,
        "registered_at": stamp(registered_at or _now()), "event": event,
        "candidates": candidates, "selection_rule": pregame_sources.RULE,
        "model_versions": MODEL_VERSIONS, "producer_versions": PRODUCERS,
        "history_record_id": ORIGINAL_HISTORY_ID, "history_rows": PANEL_ROWS,
        "history_panel_sha256": PANEL_SHA256, "categories": list(MARKETS),
        "purpose": "ONE_NAMED_GAME_OPERATIONAL_DESCRIPTIVE_NOT_ACCURACY_COMPARISON",
        "capture_minutes_before_t90": [20,10], "issuance_seconds_after_t90": [0,300],
        "maximum_original_latency_seconds": 120, "maximum_source_age_seconds": 1200,
        "qualification": "UNAVAILABLE"}
    return validate_plan(seal(body, "plan_id"))


def validate_plan(plan):
    exact(plan, {"schema_version","protocol_id","registered_at","event","candidates","selection_rule",
        "model_versions","producer_versions","history_record_id","history_rows","history_panel_sha256",
        "categories","purpose","capture_minutes_before_t90","issuance_seconds_after_t90",
        "maximum_original_latency_seconds","maximum_source_age_seconds","qualification","plan_id"}, "plan")
    require(plan["schema_version"] == _schema("plan") and plan["protocol_id"] == PROTOCOL_ID,
            "another study cannot be relabelled OP002")
    event = plan["event"]
    exact(event, {"id_namespace","league","event_id","event_starts_at","home_team_id","away_team_id",
        "status","season_ending_year","season_type","event_version"}, "named event")
    require(event["id_namespace"] == "espn" and event["league"] == "NBA" and event["status"] == "PRE_GAME"
        and event["season_type"] == "2" and type(event["season_ending_year"]) is int
        and event["season_ending_year"] >= 2026, "unsupported named event meaning")
    for key in ("event_id","home_team_id","away_team_id"):
        require(type(event[key]) is str and re.fullmatch(r"[1-9][0-9]{0,19}", event[key]), "invalid event identity")
    require(event["home_team_id"] != event["away_team_id"], "same home and away team")
    require(event["event_version"] == digest({k:v for k,v in event.items() if k != "event_version"}),
            "event version is not bound to the frozen facts")
    candidates = plan["candidates"]
    require(type(candidates) is list and len(candidates) == 4, "exactly four fixed players required")
    seen = set()
    for candidate in candidates:
        exact(candidate, {"player_id","player_label","team_id","opponent_id"}, "candidate")
        require(type(candidate["player_id"]) is str and re.fullmatch(r"[1-9][0-9]{0,19}",candidate["player_id"])
            and candidate["player_id"] not in seen, "invalid/duplicate selected player")
        seen.add(candidate["player_id"]); text(candidate["player_label"])
        require({candidate["team_id"],candidate["opponent_id"]} == {event["home_team_id"],event["away_team_id"]},
                "candidate team/opponent is not the named matchup")
    require(all(sum(c["team_id"] == team for c in candidates) == 2
        for team in (event["home_team_id"],event["away_team_id"])), "two players per team required")
    require(plan["selection_rule"] == pregame_sources.RULE and plan["model_versions"] == MODEL_VERSIONS
        and plan["producer_versions"] == PRODUCERS and plan["history_record_id"] == ORIGINAL_HISTORY_ID
        and plan["history_rows"] == PANEL_ROWS and plan["history_panel_sha256"] == PANEL_SHA256
        and plan["categories"] == list(MARKETS) and plan["qualification"] == "UNAVAILABLE"
        and plan["purpose"] == "ONE_NAMED_GAME_OPERATIONAL_DESCRIPTIVE_NOT_ACCURACY_COMPARISON"
        and plan["capture_minutes_before_t90"] == [20,10] and plan["issuance_seconds_after_t90"] == [0,300]
        and plan["maximum_original_latency_seconds"] == 120 and plan["maximum_source_age_seconds"] == 1200,
        "registered OP002 laws, scope, history or timing changed")
    require(clock(plan["registered_at"]) < clock(event["event_starts_at"])-timedelta(minutes=110),
            "plan must precede the capture window")
    check_seal(plan,"plan_id")
    return plan


def make_source_binding(commit=None, *, diagnostic=False, root=None):
    root = Path(root or Path(__file__).resolve().parents[1])
    files = {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in SOURCE_FILES}
    require(files["multisport_lab/baseline.py"] == LAW_SHA256["R0"]
        and files["multisport_lab/development_003.py"] == LAW_SHA256["K0"], "frozen R0/K0 law changed")
    if diagnostic:
        require(commit is None, "diagnostic binding cannot claim a reviewed commit")
    else:
        sha(commit,40)
        for name, expected in files.items():
            result = subprocess.run(["git","-C",str(root),"show",commit+":"+name],capture_output=True,check=False)
            require(result.returncode == 0 and hashlib.sha256(result.stdout).hexdigest() == expected,
                    "executed OP002 bytes differ from reviewed commit: "+name)
    return seal({"schema_version": _schema("source-binding"), "protocol_id":PROTOCOL_ID,
        "commit":commit, "files":files, "law_sha256":LAW_SHA256,
        "model_versions":MODEL_VERSIONS, "producer_versions":PRODUCERS,
        "verification":"LOCAL_DIAGNOSTIC_SOURCE" if diagnostic else "VERIFIED_COMMIT"},"binding_id")


def validate_source_binding(binding, *, check_current=False):
    exact(binding,{"schema_version","protocol_id","commit","files","law_sha256","model_versions",
        "producer_versions","verification","binding_id"},"source binding")
    require(binding["schema_version"] == _schema("source-binding") and binding["protocol_id"] == PROTOCOL_ID
        and binding["law_sha256"] == LAW_SHA256 and binding["model_versions"] == MODEL_VERSIONS
        and binding["producer_versions"] == PRODUCERS and set(binding["files"]) == set(SOURCE_FILES),
        "wrong producer/source identities")
    for value in binding["files"].values(): sha(value)
    require(binding["files"]["multisport_lab/baseline.py"] == LAW_SHA256["R0"]
        and binding["files"]["multisport_lab/development_003.py"] == LAW_SHA256["K0"],"changed law bytes")
    if binding["verification"] == "VERIFIED_COMMIT": sha(binding["commit"],40)
    else: require(binding["verification"] == "LOCAL_DIAGNOSTIC_SOURCE" and binding["commit"] is None,
                  "unverified producer commit")
    check_seal(binding,"binding_id")
    if check_current:
        expected = make_source_binding(binding["commit"], diagnostic=binding["commit"] is None)
        require(expected == binding,"source binding differs from actual executed files")
    return binding


def validate_activation_candidate(activation, plan, binding):
    """Shape/source binding of a proposal only; never an activation admission.

    Evidence hashes alone cannot prove source permission, retention admission,
    actual review, hosted timing or independent recovery. Their referenced typed
    artifacts require a separately reviewed admission integration.
    """
    require(type(activation) is dict,"OP002 inactive: reviewed activation evidence is required")
    exact(activation,{"schema_version","protocol_id","plan_id","producer_binding_id","reviewed_commit",
        "reviewed_at","status","approval_evidence_sha256","source_admission_sha256",
        "retention_admission_sha256","hosted_diagnostic_sha256","remote_recovery_sha256","activation_id"},"activation")
    require(activation["schema_version"] == _schema("activation") and activation["protocol_id"] == PROTOCOL_ID
        and activation["plan_id"] == plan["plan_id"] and activation["producer_binding_id"] == binding["binding_id"]
        and activation["status"] == "REVIEWED_READY" and binding["verification"] == "VERIFIED_COMMIT"
        and activation["reviewed_commit"] == binding["commit"],"activation is not the exact reviewed source/plan")
    for key in ("approval_evidence_sha256","source_admission_sha256","retention_admission_sha256",
                "hosted_diagnostic_sha256","remote_recovery_sha256"): sha(activation[key])
    require(clock(plan["registered_at"]) <= clock(activation["reviewed_at"]) <
        clock(plan["event"]["event_starts_at"])-timedelta(minutes=110),"activation missed capture-open deadline")
    check_seal(activation,"activation_id")
    return activation


def require_activation(activation=None, plan=None, binding=None):
    """Hard closed in this readiness revision, including caller-crafted hashes."""
    raise IntegrityError("NO_REVIEWED_ACTIVATION_INSTALLED: OP002 genuine writes remain inactive")


def _target(event, player_id):
    return ForecastTarget(event["event_id"],player_id,clock(event["event_starts_at"]))


def _window(target, actual, started=None):
    require(target.cutoff <= actual <= target.cutoff+timedelta(seconds=300),"OP002 issuance window missed")
    if started is not None:
        require(started <= actual and actual-started <= timedelta(seconds=120),"OP002 original exceeded 120 seconds")


def make_history_body(original_ref, *, root=None, mode="READINESS_DIAGNOSTIC"):
    require(isinstance(original_ref,LedgerRef) and original_ref.kind == "research_inputs"
        and original_ref.record_id == ORIGINAL_HISTORY_ID,"exact original retained history required")
    history, provenance = pregame_sources.history_from_input_record(original_ref.record_id,repository_root=root)
    actual = Ledger(root).read(original_ref)
    require(digest(actual) == original_ref.payload_sha256,"original history reference mismatch")
    rows = pregame_sources.unpack_history({"history":history})
    require(len(rows) == PANEL_ROWS and provenance["normalized_panel_sha256"] == PANEL_SHA256
        and provenance["normalized_panel_bytes"] == PANEL_BYTES,"complete fixed history required; no truncation")
    return seal({"schema_version":_schema("history"),"protocol_id":PROTOCOL_ID,"mode":mode,
        "original_ref":original_ref.to_record(),"history_rows":PANEL_ROWS,"panel_bytes":PANEL_BYTES,
        "panel_sha256":PANEL_SHA256,"provenance_sha256":digest(provenance),"provenance":provenance,
        "history_encoding":"ONE_ORIGINAL_RETAINED_PACK_REFERENCED_NOT_REPEATED",
        "availability":"RECONSTRUCTED_COMPLETION_BOUND_NOT_OBSERVED_HISTORICAL_AVAILABILITY",
        "imported_at":stamp(_now())},"history_id")


def validate_history(body):
    exact(body,{"schema_version","protocol_id","mode","original_ref","history_rows","panel_bytes",
        "panel_sha256","provenance_sha256","provenance","history_encoding","availability","imported_at","history_id"},"history")
    ref=LedgerRef.from_record(body["original_ref"])
    require(body["schema_version"] == _schema("history") and body["protocol_id"] == PROTOCOL_ID
        and body["mode"] in MODES and ref.kind == "research_inputs" and ref.record_id == ORIGINAL_HISTORY_ID
        and body["history_rows"] == PANEL_ROWS and body["panel_bytes"] == PANEL_BYTES and body["panel_sha256"] == PANEL_SHA256
        and body["provenance_sha256"] == digest(body["provenance"])
        and body["history_encoding"] == "ONE_ORIGINAL_RETAINED_PACK_REFERENCED_NOT_REPEATED"
        and body["availability"] == "RECONSTRUCTED_COMPLETION_BOUND_NOT_OBSERVED_HISTORICAL_AVAILABILITY",
        "history identity, provenance or complete cohort changed")
    provenance=body["provenance"]
    exact(provenance,pregame_sources._HISTORY_PROVENANCE_KEYS,"original history provenance")
    require((provenance["normalized_panel_rows"],provenance["normalized_panel_bytes"],provenance["normalized_panel_sha256"])
        == (PANEL_ROWS,PANEL_BYTES,PANEL_SHA256),"historical provenance pins conflict")
    require(clock(body["imported_at"]) <= _now(),"future history import")
    check_seal(body,"history_id");return body


def history_rows(body, root):
    validate_history(body)
    history, provenance = pregame_sources.history_from_input_record(ORIGINAL_HISTORY_ID,repository_root=root)
    require(digest(provenance) == body["provenance_sha256"],"retained history provenance differs")
    rows=pregame_sources.unpack_history({"history":history})
    require(len(rows) == PANEL_ROWS,"full history recovery did not return 26645 rows")
    from .pros004_inputs import _historical_appearances
    return list(_historical_appearances(canonical(history),PANEL_SHA256,PANEL_BYTES,PANEL_ROWS))


def make_event_body(plan, history_ref, observations, *, mode="READINESS_DIAGNOSTIC"):
    """Normalize retained actual bytes; this function performs no provider request."""
    validate_plan(plan)
    require(type(observations) is list and len(observations) == 4,"four actual source responses required")
    sources={item["source_id"]:item for item in observations}
    event=plan["event"]
    expected={"scoreboard","summary","roster-"+event["home_team_id"],"roster-"+event["away_team_id"]}
    require(set(sources) == expected,"source response inventory differs from named event")
    imported=_now();metadata=[]
    from .pros004_inputs import _source_check
    for name in sorted(sources):
        source=sources[name]
        exact(source,{"source_id","raw","metadata"},"raw observation")
        require(type(source["raw"]) is bytes and 0 < len(source["raw"]) <= pregame_sources.MAX_SOURCE_BYTES,
                "source bytes are absent or exceed their bound")
        _source_check(source["metadata"],raw=source["raw"],imported_at=imported)
        require(source["metadata"]["source_id"] == name,"source metadata identity conflict")
        metadata.append(source["metadata"])
    current=pregame_sources.normalize_event(sources["scoreboard"]["raw"],sources["summary"]["raw"],event["event_id"])
    require(current == event,"named event version/status/start/teams changed; no replacement")
    rosters={team:pregame_sources.normalize_roster(sources["roster-"+team]["raw"],team,
        season_ending_year=event["season_ending_year"]) for team in (event["home_team_id"],event["away_team_id"])}
    selection=pregame_sources.freeze_selection(current,rosters)
    require(selection["players"] == plan["candidates"],"fixed selected players changed; no replacement")
    imported=_now()  # actual normalization/selection completion, after all work
    body=seal({"schema_version":_schema("event"),"protocol_id":PROTOCOL_ID,"mode":mode,
        "plan":plan,"history_ref":history_ref.to_record(),"event":current,"selection":selection,
        "candidates":selection["players"],"sources":metadata,"imported_at":stamp(imported),
        "raw_retention":"REQUIRES_SEPARATE_ADMITTED_IMMUTABLE_RAW_EVIDENCE"},"event_input_id")
    return validate_event(body)


def validate_event(body):
    exact(body,{"schema_version","protocol_id","mode","plan","history_ref","event","selection","candidates",
        "sources","imported_at","raw_retention","event_input_id"},"event input")
    require(body["schema_version"] == _schema("event") and body["protocol_id"] == PROTOCOL_ID
        and body["mode"] in MODES,"invalid event schema/lane")
    plan=validate_plan(body["plan"]);require(body["event"] == plan["event"] and body["candidates"] == plan["candidates"],
        "event input differs from predeclared named event/cohort")
    require(LedgerRef.from_record(body["history_ref"]).kind == "research_inputs","event lacks exact shared history")
    selection=body["selection"]
    exact(selection,{"schema_version","declared_at","event_id","rule","players"},"source selection")
    require(selection["schema_version"] == "nba-pregame-selected-cohort-v1"
        and selection["rule"] == pregame_sources.RULE and selection["event_id"] == body["event"]["event_id"]
        and selection["players"] == body["candidates"],"selected cohort differs")
    cutoff=clock(body["event"]["event_starts_at"])-timedelta(minutes=90)
    opens, closes=cutoff-timedelta(minutes=20),cutoff-timedelta(minutes=10)
    imported=clock(body["imported_at"])
    require(opens <= clock(selection["declared_at"]) <= imported <= closes and imported <= _now(),
            "event normalization/selection missed capture window")
    from .pros004_inputs import _source_check
    require(type(body["sources"]) is list and len(body["sources"]) == 4,"incomplete source evidence")
    seen=set()
    for source in body["sources"]:
        _source_check(source,imported_at=imported)
        require(source["source_id"] not in seen,"duplicate source observation");seen.add(source["source_id"])
        require(opens <= clock(source["request_started_at"]) <= clock(source["observed_at"])
            <= clock(source["response_completed_at"]) <= imported <= closes,"actual capture window violated")
        require(cutoff-clock(source["observed_at"]) <= timedelta(seconds=1200),"source exceeds freshness limit")
    event=body["event"]
    require(seen == {"scoreboard","summary","roster-"+event["home_team_id"],"roster-"+event["away_team_id"]},
            "wrong source observation inventory")
    require(body["raw_retention"] == "REQUIRES_SEPARATE_ADMITTED_IMMUTABLE_RAW_EVIDENCE","changed raw retention meaning")
    check_seal(body,"event_input_id");return body


def _validation_forecast(body):
    """Temporary standard distribution-validation view; never issued or exported."""
    binding=body["producer_binding"];recipe=body["joint_recipe"]
    value={"schema_version":FORECAST_SCHEMA,
        **{key:body[key] for key in ("id_namespace","league","event_id","player_id","player_label","team_id",
            "opponent_id","event_starts_at","model_version","trained_through","cutoff_at","history_freeze",
            "issued_at","conditioning","categories","qualification")},
        "period":"full_game","extra_time_policy":"includes_overtime","model_commit":binding["commit"] or "0"*40,
        "model_code_sha256":LAW_SHA256[body["model_key"]],"input_sha256":recipe["input_sha256"],
        "joint_sha256":recipe["joint_sha256"],"evidence_lane":"REAL_TIME_CAPTURED",
        "availability_basis":"OBSERVED_INPUT_CAPTURE","input_capture_ids":[body["event_ref"]["record_id"],body["history_ref"]["record_id"]],
        "joint_method":"COMPLETE_LINE_EMPIRICAL","tail_policy":"FINITE_EMPIRICAL_SUPPORT_NO_SMOOTHING"}
    return seal(value,"forecast_id")


def validate_forecast_record(body, event=None):
    exact(body,{"schema_version","protocol_id","plan_id","mode","evidence_lane","period","extra_time_policy","id_namespace","league","model_key","model_version",
        "producer_version","producer_binding","history_ref","event_ref","event_id","event_version","event_starts_at",
        "player_id","player_label","team_id","opponent_id","cutoff_at","history_freeze","trained_through","conditioning",
        "qualification","generation_started_at","generation_completed_at","verified_at","issued_at","categories",
        "reported_minutes","joint_recipe","forecast_id"},"forecast")
    key=body["model_key"]
    require(body["schema_version"] == _schema("forecast") and body["protocol_id"] == PROTOCOL_ID
        and body["mode"] in MODES and key in MODEL_VERSIONS and body["model_version"] == MODEL_VERSIONS[key]
        and body["producer_version"] == PRODUCERS[key] and body["evidence_lane"] == body["mode"]
        and body["period"] == "full_game" and body["extra_time_policy"] == "includes_overtime", "wrong operational producer/model/lane")
    validate_source_binding(body["producer_binding"]);sha(body["plan_id"]);sha(body["event_version"])
    refs=[LedgerRef.from_record(body[name]) for name in ("event_ref","history_ref")]
    require(all(ref.kind == "research_inputs" for ref in refs),"wrong forecast input kind")
    validate_forecast(_validation_forecast(body),now=_now())
    target=_target(body,body["player_id"])
    clocks=[clock(body[name]) for name in ("generation_started_at","generation_completed_at","verified_at","issued_at")]
    require(clocks[0] <= clocks[1] <= clocks[2] == clocks[3] <= _now(),"generation/verification clocks conflict")
    _window(target,clocks[-1],clocks[0])
    recipe=body["joint_recipe"]
    exact(recipe,{"schema_version","algorithm","history_ref","event_ref","target","support_atom_count","atom_order",
        "joint_sha256","input_sha256","pool_history_count","player_history_count","fallback","encoding","omitted_atoms"},"complete law replay")
    require(recipe["schema_version"] == _schema("complete-joint-replay") and recipe["algorithm"] == MODEL_VERSIONS[key]
        and recipe["history_ref"] == body["history_ref"] and recipe["event_ref"] == body["event_ref"]
        and recipe["target"] == target.to_record() and recipe["omitted_atoms"] == 0
        and recipe["atom_order"] == "frozen_algorithm_order_no_sampling_or_truncation"
        and recipe["encoding"] == "COMPLETE_SOURCE_BOUND_REPLAY_PLUS_ALL_ORIGINAL_MARGINALS"
        and type(recipe["support_atom_count"]) is int and recipe["support_atom_count"] > 0
        and recipe["pool_history_count"] == recipe["support_atom_count"]
        and type(recipe["player_history_count"]) is int and 0 <= recipe["player_history_count"] <= recipe["pool_history_count"],
        "incomplete/changed joint law recipe")
    sha(recipe["joint_sha256"]);sha(recipe["input_sha256"])
    from .pros004_publication import _validate_minutes
    _validate_minutes(body["reported_minutes"])
    if event is not None:
        validate_event(event)
        candidate=next((row for row in event["candidates"] if row["player_id"] == body["player_id"]),None)
        require(candidate is not None and all(body[name] == candidate[name] for name in candidate)
            and all(body[name] == event["event"][name] for name in ("event_id","event_version","event_starts_at"))
            and body["plan_id"] == event["plan"]["plan_id"] and body["history_ref"] == event["history_ref"]
            and body["mode"] == event["mode"],"forecast differs from exact fixed inputs")
    check_seal(body,"forecast_id");return body


def _assemble_forecast(event, history_body, rows, *, event_ref, history_ref, player_id, model_key,
                       producer_binding, reference, started):
    validate_event(event);validate_history(history_body);validate_source_binding(producer_binding,check_current=True)
    require(model_key in MODEL_VERSIONS,"S0 and other revised laws are not admitted")
    require(event["history_ref"] == history_ref.to_record() and history_body["mode"] == event["mode"],"shared inputs differ")
    candidate=next((row for row in event["candidates"] if row["player_id"] == player_id),None)
    require(candidate is not None,"player outside fixed cohort")
    require(len(rows) == PANEL_ROWS and all(isinstance(row,HistoricalAppearance) for row in rows),"complete normalized fixed history required")
    target=_target(event["event"],player_id);_window(target,started)
    categories,minutes=_categories(reference),_minutes(reference)
    recipe={"schema_version":_schema("complete-joint-replay"),"algorithm":MODEL_VERSIONS[model_key],
        "history_ref":history_ref.to_record(),"event_ref":event_ref.to_record(),"target":target.to_record(),
        "support_atom_count":len(reference.support),"atom_order":"frozen_algorithm_order_no_sampling_or_truncation",
        "joint_sha256":joint_fingerprint(reference),"input_sha256":reference.input_sha256,
        "pool_history_count":reference.pool_history_count,"player_history_count":reference.player_history_count,
        "fallback":getattr(reference,"fallback",None),"encoding":"COMPLETE_SOURCE_BOUND_REPLAY_PLUS_ALL_ORIGINAL_MARGINALS","omitted_atoms":0}
    completed=_now();_window(target,completed,started)
    body={"schema_version":_schema("forecast"),"protocol_id":PROTOCOL_ID,"plan_id":event["plan"]["plan_id"],
        "mode":event["mode"],"evidence_lane":event["mode"],"period":"full_game","extra_time_policy":"includes_overtime",
        "id_namespace":"espn","league":"NBA","model_key":model_key,
        "model_version":MODEL_VERSIONS[model_key],"producer_version":PRODUCERS[model_key],"producer_binding":producer_binding,
        "history_ref":history_ref.to_record(),"event_ref":event_ref.to_record(),**{name:event["event"][name]
            for name in ("event_id","event_version","event_starts_at")},**candidate,"cutoff_at":stamp(target.cutoff),
        "history_freeze":stamp(target.history_freeze),"trained_through":stamp(reference.trained_through),
        "conditioning":"CONDITIONAL_ON_APPEARANCE","qualification":"UNAVAILABLE","generation_started_at":stamp(started),
        "generation_completed_at":stamp(completed),"verified_at":stamp(completed),"issued_at":stamp(completed),
        "categories":categories,"reported_minutes":minutes,"joint_recipe":recipe}
    body=seal(body,"forecast_id");validate_forecast_record(body,event)
    require(body["categories"] == _categories(reference) and body["reported_minutes"] == _minutes(reference)
        and body["joint_recipe"]["joint_sha256"] == joint_fingerprint(reference),"producer verification differs from exact law")
    verified=_now();_window(target,verified,started)
    body["verified_at"]=body["issued_at"]=stamp(verified)
    body["forecast_id"]=digest({k:v for k,v in body.items() if k != "forecast_id"})
    return validate_forecast_record(body,event)


def generate_forecast(event, history_body, rows, *, event_ref, history_ref, player_id, model_key, producer_binding):
    """Single diagnostic original; the guarded operating path preflights pairs."""
    require(model_key in MODEL_VERSIONS,"unknown model")
    started=_now();target=_target(event["event"],player_id);_window(target,started)
    reference=_fit_laws(rows,target,need_kernel=model_key == "K0")[model_key]
    return _assemble_forecast(event,history_body,rows,event_ref=event_ref,history_ref=history_ref,
        player_id=player_id,model_key=model_key,producer_binding=producer_binding,reference=reference,started=started)


def prepare_pair(event,history_body,rows,*,event_ref,history_ref,player_id,producer_binding):
    """Actually fit/verify both unchanged laws before either original is written.

    Both generation clocks begin before the shared fit. Preflight work is not
    hidden outside their120-second latency and never establishes issuance.
    """
    validate_event(event);validate_history(history_body);validate_source_binding(producer_binding,check_current=True)
    target=_target(event["event"],player_id);started=_now();_window(target,started)
    laws=_fit_laws(rows,target)
    prepared={}
    for model in MODEL_VERSIONS:
        body=_assemble_forecast(event,history_body,rows,event_ref=event_ref,history_ref=history_ref,
            player_id=player_id,model_key=model,producer_binding=producer_binding,reference=laws[model],started=started)
        require(len(canonical(body)) <= CEILINGS["forecast"]-2048,"paired preflight exceeds complete forecast envelope ceiling")
        prepared[model]=body
    verified=_now();_window(target,verified,started)
    for body in prepared.values():
        body["verified_at"]=body["issued_at"]=stamp(verified)
        body["forecast_id"]=digest({key:value for key,value in body.items() if key != "forecast_id"})
        validate_forecast_record(body,event)
    return prepared


def _identity(body):
    identity={"protocol_id":PROTOCOL_ID}
    for key in ("plan_id","event_id","event_version","event_starts_at","player_id","team_id","opponent_id","model_key"):
        if key in body: identity[key]=body[key]
    return identity


class _OperationalLedger(CompositeEnvelopeLedger):
    def _validate_payload(self,payload, *, kind, record_id):
        data=payload.get("data") if type(payload) is dict else None
        if kind != "research_inputs" or type(data) is not dict or "operational" not in data:
            return super()._validate_payload(payload,kind=kind,record_id=record_id)
        exact(payload,{"schema_version","kind","record_id","logical_id","received_at","data","references",
            "supersedes","persistence_status"},"ledger envelope")
        from .ledger import SCHEMA, _now as ledger_now
        require(payload["schema_version"] == SCHEMA and payload["kind"] == kind and payload["record_id"] == record_id
            and record_id == digest({"kind":kind,"logical_id":text(payload["logical_id"])})
            and clock(payload["received_at"]) <= ledger_now() and payload["supersedes"] is None
            and payload["persistence_status"] == "LOCAL_RECEIPT_ONLY","invalid operational input envelope")
        exact(data,{"identity","operational"},"ledger data")
        require(type(payload["references"]) is list,"invalid ledger references")
        refs=[LedgerRef.from_record(value) for value in payload["references"]]
        require(len(refs) == len(set(refs)),"duplicate references")


class OperationalStore:
    """One writer, create-only originals, separate actual completion evidence."""
    def __init__(self,root=None,*,diagnostic=False,activation=None):
        require(type(diagnostic) is bool,"diagnostic mode must be explicit")
        self.ledger=_OperationalLedger(root);self.root=self.ledger.root
        self.diagnostic=diagnostic;self.activation=activation
        if diagnostic:
            probe=self.root
            while not probe.exists():probe=probe.parent
            result=subprocess.run(["git","-C",str(probe),"rev-parse","--show-toplevel"],capture_output=True,check=False)
            require(result.returncode != 0,"diagnostics require a separate root outside every Git worktree")

    @contextmanager
    def single_writer(self):
        path=self.root/".local-data"/"operational002.lock";path.parent.mkdir(parents=True,exist_ok=True)
        require(not path.is_symlink() and not path.parent.is_symlink(),"writer state cannot be symlinked")
        with path.open("a+b") as handle:
            try: fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc: raise IntegrityError("another OP002 writer is active") from exc
            try:
                for kind in KINDS:
                    require(not list((self.root/"records"/kind).glob(".receipt-*")),"interrupted unpublished receipt requires diagnosis")
                yield
            finally: fcntl.flock(handle.fileno(),fcntl.LOCK_UN)

    def _journal_path(self):
        path=self.root/JOURNAL
        require(not any(parent.is_symlink() for parent in (path,*path.parents)),"journal cannot traverse symlinks")
        return path

    def journal(self):
        path=self._journal_path();raw=path.read_bytes() if path.exists() else b""
        require(len(raw) <= MAX_JOURNAL_BYTES and (not raw or raw.endswith(b"\n")),"oversized/interrupted completion journal")
        result=[];previous="0"*64;seen=set();last=None
        prefix_bytes=b"";prefixes={hashlib.sha256(prefix_bytes).hexdigest():0};remote_groups={}
        for line in raw.splitlines():
            try: entry=json.loads(line)
            except (ValueError,UnicodeDecodeError) as exc: raise IntegrityError("invalid completion JSON") from exc
            exact(entry,{"schema_version","sequence","previous_sha256","kind","reference","raw_sha256","completed_at",
                "operation_started_at","acknowledgment","entry_id"},"completion entry")
            require(canonical(entry) == line and entry["schema_version"] == _schema("completion")
                and entry["sequence"] == len(result)+1 and len(result) < MAX_JOURNAL_ENTRIES
                and entry["previous_sha256"] == previous and entry["kind"] in {"LOCAL","REMOTE","PROOF_LOCAL"},"invalid completion chain")
            ref=LedgerRef.from_record(entry["reference"]);sha(entry["raw_sha256"])
            observed=clock(entry["completed_at"])
            require(observed <= _now() and (last is None or last <= observed),"completion clocks conflict")
            proof_id=entry["acknowledgment"].get("proof_id") if entry["kind"] == "PROOF_LOCAL" and type(entry["acknowledgment"]) is dict else None
            key=(entry["kind"],ref.kind,ref.record_id,proof_id);require(key not in seen,"duplicate completion attempt")
            if entry["kind"] == "LOCAL":
                require(entry["acknowledgment"] is None and entry["operation_started_at"] is None,"local completion cannot claim remote")
            elif entry["kind"] == "REMOTE":
                ack=entry["acknowledgment"]
                self._validate_ack(ack,ref,entry["raw_sha256"],entry["operation_started_at"],entry["completed_at"])
                prefix_count=prefixes.get(ack["journal_prefix_sha256"])
                require(prefix_count is not None,"remote acknowledgment names no earlier complete journal prefix")
                local=next((row for row in result[:prefix_count] if row["kind"] == "LOCAL"
                    and row["reference"] == ref.to_record() and row["raw_sha256"] == entry["raw_sha256"]),None)
                require(local is not None,"remote readback prefix does not cover the exact original LOCAL witness")
                require(clock(local["completed_at"]) <= clock(entry["operation_started_at"]),
                    "remote operation began before original local persistence completed")
                group=remote_groups.setdefault(ack["journal_prefix_sha256"],[])
                if group:
                    require(len(group) == 1,"one remote readback prefix supports at most two paired originals")
                    self._paired_references((LedgerRef.from_record(group[0]["reference"]),ref))
                    common=("remote_repository","remote_branch","remote_commit","snapshot_sha256",
                            "journal_prefix_sha256","remote_completed_at")
                    require(all(group[0]["acknowledgment"][key] == ack[key] for key in common),
                        "paired remote witnesses disagree on their common independent readback")
                    require(group[0]["operation_started_at"] == entry["operation_started_at"],
                        "paired remote witnesses disagree on their common operation start")
                group.append(entry)
            else:
                exact(entry["acknowledgment"],{"proof_id","proof_raw_sha256"},"proof local completion")
                sha(proof_id);sha(entry["acknowledgment"]["proof_raw_sha256"])
                require(entry["operation_started_at"] is None,"proof completion is a local post-fsync observation")
                proof_paths=[self.root/PROOF,*((self.root/PROOF).parent.glob("remote-recovery.*.json"))]
                matches=[json.loads(path.read_bytes()) for path in proof_paths if path.is_file()
                    and hashlib.sha256(path.read_bytes()).hexdigest() == entry["acknowledgment"]["proof_raw_sha256"]]
                require(any(proof.get("proof_id") == proof_id and clock(proof["completed_at"]) <= observed for proof in matches),
                    "post-fsync proof witness has no retained exact proof")
            require(hashlib.sha256(self.ledger._path(ref.kind,ref.record_id).read_bytes()).hexdigest() == entry["raw_sha256"],
                    "completion references changed original bytes")
            self.ledger.read(ref);check_seal(entry,"entry_id")
            seen.add(key);result.append(entry);previous=entry["entry_id"];last=observed
            prefix_bytes+=line+b"\n";prefixes[hashlib.sha256(prefix_bytes).hexdigest()]=len(result)
        return result

    def _append_completion(self,reference,*,completed_at,acknowledgment=None,started_at=None,proof=None):
        entries=self.journal();kind="PROOF_LOCAL" if proof is not None else "REMOTE" if acknowledgment is not None else "LOCAL"
        require(not any(row["kind"] == kind and row["reference"] == reference.to_record()
            and (proof is None or row["acknowledgment"]["proof_id"] == proof["proof_id"]) for row in entries),
                "original completion cannot be replaced")
        raw=self.ledger._path(reference.kind,reference.record_id).read_bytes();raw_sha=hashlib.sha256(raw).hexdigest()
        if acknowledgment is not None:
            self._validate_ack(acknowledgment,reference,raw_sha,stamp(started_at),stamp(completed_at))
        if proof is not None:
            acknowledgment={"proof_id":proof["proof_id"],"proof_raw_sha256":hashlib.sha256((self.root/PROOF).read_bytes()).hexdigest()}
        entry=seal({"schema_version":_schema("completion"),"sequence":len(entries)+1,
            "previous_sha256":entries[-1]["entry_id"] if entries else "0"*64,"kind":kind,
            "reference":reference.to_record(),"raw_sha256":raw_sha,"completed_at":stamp(completed_at),
            "operation_started_at":stamp(started_at) if started_at is not None else None,
            "acknowledgment":acknowledgment},"entry_id")
        path=self._journal_path();path.parent.mkdir(parents=True,exist_ok=True)
        data=canonical(entry)+b"\n"
        require(len(entries) < MAX_JOURNAL_ENTRIES and len(data)+(path.stat().st_size if path.exists() else 0) <= MAX_JOURNAL_BYTES,
                "completion metadata budget exceeded")
        self._check_budget(extra_files=int(not path.exists()),extra_bytes=len(data))
        descriptor=os.open(path,os.O_CREAT|os.O_APPEND|os.O_WRONLY|getattr(os,"O_NOFOLLOW",0),0o600)
        try:
            require(os.write(descriptor,data) == len(data),"interrupted completion write")
            os.fsync(descriptor)
        finally: os.close(descriptor)
        directory=os.open(path.parent,os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
        require(self.journal()[-1] == entry,"completion readback differs")
        return entry

    def _validate_ack(self,ack,ref,raw_sha,started_at,completed_at):
        exact(ack,{"schema_version","reference","remote_repository","remote_branch","remote_commit",
            "snapshot_sha256","readback_raw_sha256","journal_prefix_sha256","remote_completed_at"},"remote acknowledgment")
        require(ack["schema_version"] == _schema("remote-checkpoint") and ack["reference"] == ref.to_record()
            and ack["remote_repository"] == REPOSITORY and ack["readback_raw_sha256"] == raw_sha,
            "remote acknowledgment differs from original bytes/identity")
        text(ack["remote_branch"]);sha(ack["remote_commit"],40);sha(ack["snapshot_sha256"]);sha(ack["journal_prefix_sha256"])
        require(clock(started_at) <= clock(ack["remote_completed_at"]) <= clock(completed_at),"remote clock outside actual operation")

    def _check_budget(self,*,extra_files=0,extra_bytes=0):
        _,count,total=self.ledger._inventory()
        metadata=metadata_inventory(self.root)
        count+=metadata["file_count"];total+=metadata["total_bytes"]
        require(count+extra_files <= MAX_LEDGER_RECORDS and total+extra_bytes <= MAX_LEDGER_BYTES,
                "OP002 exceeds unchanged shared ledger limits")

    def _logical(self,body):
        name=body["schema_version"][len(PREFIX):-3]
        if name == "history":return "operational002:history:fixed"
        if name == "event":return "operational002:event:one-named-game"
        if name == "forecast":return f"operational002:forecast:{body['event_id']}:{body['player_id']}:{body['model_key']}"
        return "operational002:"+name+":"+digest(body)

    def _validate(self,body,refs):
        require(type(body) is dict and body.get("protocol_id") == PROTOCOL_ID,"not an OP002 record")
        schema=body.get("schema_version");name=next((key for key in KIND if schema == _schema(key)),None)
        require(name is not None and body.get("mode") in MODES,"unsupported OP002 record type/lane")
        if name == "history":
            validate_history(body);require(refs == (LedgerRef.from_record(body["original_ref"]),),"history lacks original reference")
        elif name == "event":
            validate_event(body);require(refs == (LedgerRef.from_record(body["history_ref"]),),"event history reference differs")
            require(self.body(refs[0])["mode"] == body["mode"],"history/event lane conflict")
        elif name == "forecast":
            require(refs == tuple(LedgerRef.from_record(body[k]) for k in ("event_ref","history_ref")),"forecast references differ")
            validate_forecast_record(body,self.body(refs[0]))
        elif name == "outcome":
            validate_outcome(body)
            require(1 <= len(refs) <= 2 and all(ref.kind == "forecasts" for ref in refs),"one shared outcome requires original model references")
            models=set()
            for ref in refs:
                forecast=self.body(ref)
                require(forecast["model_key"] not in models,"duplicate outcome model");models.add(forecast["model_key"])
                require(all(body[key] == forecast[key] for key in ("event_id","event_version","event_starts_at","player_id","team_id","opponent_id","mode")),
                    "outcome identity differs from original")
                require(clock(forecast["issued_at"]) <= clock(body["source_observed_at"]),"outcome observed before original forecast")
        elif name == "grade":
            require(len(refs) == 2 and refs[0].kind == "forecasts" and refs[1].kind == "outcomes","grade references differ")
            require(refs[0].to_record() in self.ledger.read(refs[1])["references"],"grade not linked by shared outcome")
            require(body == make_grade(self.body(refs[0]),self.body(refs[1]),graded_at=body["graded_at"]),
                    "grade differs from original probabilities/outcome")
        elif name == "failure":
            exact(body,{"schema_version","protocol_id","mode","recorded_at","event_ref","status","reason","player_id","model_key","failure_id"},"failure")
            require(refs == (LedgerRef.from_record(body["event_ref"]),) and body["status"] in
                {"PARTIAL","MISSING_PEER","LATE_COMPLETION","UNACKNOWLEDGED","SOURCE_FAILURE","BUDGET_FAILURE"},"invalid failure metadata")
            text(body["reason"]);require(clock(body["recorded_at"]) <= _now(),"future failure clock")
            require(body["player_id"] is None or body["player_id"] in {row["player_id"] for row in self.body(refs[0])["candidates"]},"foreign failure subject")
            require(body["model_key"] is None or body["model_key"] in MODEL_VERSIONS,"foreign failure model")
            check_seal(body,"failure_id")
        require(len(canonical(body)) <= CEILINGS[name]-2048,"OP002 body exceeds encoded envelope allowance")
        return name

    def read(self,reference):
        payload=self.ledger.read(reference)
        body=payload["data"].get("operational")
        require(body is not None,"reference is not OP002")
        exact(payload["data"],{"identity","operational"},"record data")
        refs=tuple(LedgerRef.from_record(item) for item in payload["references"])
        name=self._validate(body,refs)
        require(reference.kind == KIND[name] and payload["logical_id"] == self._logical(body)
            and payload["data"]["identity"] == _identity(body),"OP002 logical/subject identity differs")
        received=clock(payload["received_at"])
        observation=body.get("issued_at",body.get("normalized_at",body.get("graded_at",body.get("imported_at",body.get("recorded_at")))))
        require(observation is not None and clock(observation) <= received,"record observation follows receipt")
        require(self.ledger._path(reference.kind,reference.record_id).stat().st_size <= CEILINGS[name],"encoded record exceeds ceiling")
        return payload

    def body(self,reference): return self.read(reference)["data"]["operational"]

    def persist(self,body,*,references=()):
        refs=tuple(references);name=self._validate(body,refs)
        if body["mode"] == "REAL_TIME_CAPTURED":
            require_activation()
            event=body if name == "event" else self.body(refs[0]) if name == "forecast" else None
            if event is not None:
                binding=body["producer_binding"] if name == "forecast" else self.activation.get("producer_binding") if type(self.activation) is dict else None
                require(binding is not None,"OP002 inactive: reviewed producer binding missing")
                require_activation(self.activation.get("evidence"),event["plan"],binding)
            else: require(self.activation is not None,"OP002 inactive: genuine writes require reviewed activation")
            require(not self.diagnostic,"diagnostic root cannot claim genuine capture")
        else: require(self.diagnostic,"diagnostics cannot enter the actual records store")
        logical=self._logical(body);record_id=digest({"kind":KIND[name],"logical_id":logical})
        existing=self.ledger._path(KIND[name],record_id).exists()
        self._check_type_limits(extra=None if existing else name)
        self._check_budget(extra_files=int(not existing),extra_bytes=0 if existing else CEILINGS[name])
        reference=self.ledger.append(KIND[name],logical,{"identity":_identity(body),"operational":body},references=refs)
        if not existing:
            # Actual return from immutable fsynced write/readback, never the
            # frozen ledger's pre-write received_at assignment.
            completed=_now();self._append_completion(reference,completed_at=completed)
        self.read(reference)
        return reference

    def _check_type_limits(self,*,extra=None):
        counts={name:0 for name in KIND};corrections=0
        inventory,_,_=self.ledger._inventory()
        for kind,values in inventory.items():
            for path,_ in values:
                payload=read_receipt(path,max_bytes=4*1024*1024)
                body=payload["data"].get("operational")
                if body is not None:
                    name=next((name for name in KIND if body.get("schema_version") == _schema(name)),None)
                    require(name is not None,"unrecognized operational type in capacity inventory")
                    counts[name]+=1
                if kind == "corrections":
                    target=LedgerRef.from_record(payload["supersedes"])
                    original=read_receipt(self.ledger._path(target.kind,target.record_id),max_bytes=4*1024*1024)
                    corrections+=int("operational" in original["data"])
        if extra is not None:counts[extra]+=1
        require(counts["history"] <= 1 and counts["event"] <= 1 and counts["forecast"] <= 8
            and counts["outcome"] <= 12 and counts["grade"] <= 16 and counts["outcome"]+counts["grade"] <= 20
            and counts["failure"] <= 8 and corrections <= 8,"OP002 typed receipt/correction reserve exceeded")

    def record_failure(self,event_ref,*,status,reason,player_id=None,model_key=None):
        event=self.body(event_ref)
        body=seal({"schema_version":_schema("failure"),"protocol_id":PROTOCOL_ID,"mode":event["mode"],
            "recorded_at":stamp(_now()),"event_ref":event_ref.to_record(),"status":status,"reason":text(reason)[:2048],
            "player_id":player_id,"model_key":model_key},"failure_id")
        return self.persist(body,references=(event_ref,))

    def checkpoint(self,reference,callback):
        self.read(reference);entries=self.journal()
        existing=[row for row in entries if row["kind"] == "REMOTE" and row["reference"] == reference.to_record()]
        if existing:return existing[0]
        require(any(row["kind"] == "LOCAL" and row["reference"] == reference.to_record() for row in entries),
                "original local completion is unacknowledged; cannot manufacture it on restart")
        prefix=hashlib.sha256(self._journal_path().read_bytes()).hexdigest();started=_now()
        ack=callback(reference)
        completed=_now();require(ack.get("journal_prefix_sha256") == prefix,"remote readback did not retain exact local journal prefix")
        return self._append_completion(reference,completed_at=completed,acknowledgment=ack,started_at=started)

    def _paired_references(self,references):
        refs=tuple(references)
        require(1 <= len(refs) <= 2 and all(isinstance(ref,LedgerRef) and ref.kind == "forecasts" for ref in refs)
            and len(set(refs)) == len(refs),"paired checkpoint requires one or two distinct original forecasts")
        bodies=[self.body(ref) for ref in refs]
        require(all(body["schema_version"] == _schema("forecast") for body in bodies),"paired checkpoint references another typed contract")
        if len(bodies) == 2:
            common=("protocol_id","plan_id","mode","event_id","event_version","event_starts_at","player_id",
                "team_id","opponent_id","cutoff_at","history_ref","event_ref","producer_binding")
            require({body["model_key"] for body in bodies} == set(MODEL_VERSIONS)
                and all(bodies[0][key] == bodies[1][key] for key in common),
                "paired checkpoint originals differ on their fixed subject, inputs or producer")
        return refs

    def checkpoint_many(self,references,callback):
        """One fresh readback, two separately retained original acknowledgments.

        Both ACKs name the actual common pre-callback LOCAL prefix. Nothing
        claims that this fetch contained subsequently appended REMOTE witnesses.
        All returned meanings are checked before either witness is appended;
        interrupted journal writes can still leave an honest one-witness state.
        """
        refs=self._paired_references(references);entries=self.journal()
        retained={row["reference"]["record_id"]:row for row in entries if row["kind"] == "REMOTE"}
        for ref in refs:
            require(any(row["kind"] == "LOCAL" and row["reference"] == ref.to_record() for row in entries),
                "original local completion is unacknowledged; cannot manufacture it on restart")
        pending=tuple(ref for ref in refs if ref.record_id not in retained)
        if not pending:return tuple(retained[ref.record_id] for ref in refs)
        prefix=hashlib.sha256(self._journal_path().read_bytes()).hexdigest();started=_now()
        acknowledgments=callback(pending);returned=_now()
        require(type(acknowledgments) in (tuple,list) and len(acknowledgments) == len(pending),
                "paired callback must acknowledge every requested original separately")
        common=("remote_repository","remote_branch","remote_commit","snapshot_sha256",
                "journal_prefix_sha256","remote_completed_at")
        for ref,ack in zip(pending,acknowledgments,strict=True):
            raw_sha=hashlib.sha256(self.ledger._path(ref.kind,ref.record_id).read_bytes()).hexdigest()
            self._validate_ack(ack,ref,raw_sha,stamp(started),stamp(returned))
            require(ack["journal_prefix_sha256"] == prefix,"paired readback did not retain its common original LOCAL prefix")
            require(all(ack[key] == acknowledgments[0][key] for key in common),
                    "paired acknowledgments disagree on their common independent readback")
        require(hashlib.sha256(self._journal_path().read_bytes()).hexdigest() == prefix,
                "source journal changed during paired remote readback")
        checked=_now();require(started <= returned <= checked,"paired remote validation clock moved backwards")
        for ref,ack in zip(pending,acknowledgments,strict=True):
            completed=_now();require(checked <= completed,"paired remote witness clock moved backwards")
            retained[ref.record_id]=self._append_completion(ref,completed_at=completed,
                acknowledgment=ack,started_at=started)
        return tuple(retained[ref.record_id] for ref in refs)

    def finalize_checkpoint(self,callback):
        """Independently recover all originals and this exact journal prefix."""
        entries=self.journal();require(bool(entries),"no retained completion prefix")
        prefix=hashlib.sha256(self._journal_path().read_bytes()).hexdigest();started=_now()
        report=callback(prefix)
        callback_returned=_now()
        exact(report,{"schema_version","protocol_id","remote_repository","remote_branch","remote_commit",
            "snapshot_sha256","journal_sha256","independent_recovery_completed_at"},"final independent recovery")
        require(report["schema_version"] == _schema("remote-recovery") and report["protocol_id"] == PROTOCOL_ID
            and report["remote_repository"] == REPOSITORY and report["journal_sha256"] == prefix,
            "independent recovery differs from exact final journal prefix")
        text(report["remote_branch"]);sha(report["remote_commit"],40);sha(report["snapshot_sha256"])
        require(started <= clock(report["independent_recovery_completed_at"]) <= callback_returned,"recovery clock outside actual operation")
        completed=_now()  # after strict report/hash/source-prefix validation
        require(callback_returned <= completed,"recovery verification clock moved backwards")
        proof=seal({**report,"operation_started_at":stamp(started),"completed_at":stamp(completed)},"proof_id")
        path=self.root/PROOF;path.parent.mkdir(parents=True,exist_ok=True)
        require(not path.is_symlink(),"recovery proof cannot be symlinked")
        if path.exists():
            # New prefix requires a new remote recovery evidence revision, never
            # overwriting a previous independently observed completion clock.
            previous=path.read_bytes();archive=path.with_name("remote-recovery."+hashlib.sha256(previous).hexdigest()+".json")
            require(not archive.exists() or archive.read_bytes() == previous,"conflicting recovery evidence revision")
            if not archive.exists():
                self._check_budget(extra_files=1,extra_bytes=len(previous))
                descriptor=os.open(archive,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                try: os.write(descriptor,previous);os.fsync(descriptor)
                finally: os.close(descriptor)
            # The current pointer is replaceable metadata; all observed proof
            # revisions remain immutable beside it and count against capacity.
        raw=canonical(proof);require(len(raw) <= MAX_PROOF_BYTES,"recovery proof exceeds ceiling")
        self._check_budget(extra_files=int(not path.exists()),extra_bytes=len(raw))
        temporary=path.with_name(".remote-recovery.tmp")
        require(not temporary.exists(),"interrupted recovery proof publication needs diagnosis")
        descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try: require(os.write(descriptor,raw) == len(raw),"interrupted proof write");os.fsync(descriptor)
        finally: os.close(descriptor)
        os.replace(temporary,path)
        descriptor=os.open(path.parent,os.O_RDONLY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
        recovered=self.recovery_proof()
        persisted=_now()  # actual proof file fsync, replacement and strict readback finished
        require(persisted >= completed,"proof local persistence clock moved backwards")
        last_remote=next((entry for entry in reversed(entries) if entry["kind"] == "REMOTE"),None)
        require(last_remote is not None,"proof must recover at least one retained remote acknowledgment")
        self._append_completion(LedgerRef.from_record(last_remote["reference"]),completed_at=persisted,proof=recovered)
        return recovered

    def _read_recovery_proof(self,path):
        if not path.exists():return None
        require(not path.is_symlink() and path.stat().st_size <= MAX_PROOF_BYTES,"invalid recovery proof file")
        raw=path.read_bytes()
        try: proof=json.loads(raw)
        except ValueError as exc: raise IntegrityError("invalid recovery proof JSON") from exc
        exact(proof,{"schema_version","protocol_id","remote_repository","remote_branch","remote_commit","snapshot_sha256",
            "journal_sha256","independent_recovery_completed_at","operation_started_at","completed_at","proof_id"},"recovery proof")
        require(canonical(proof) == raw and proof["schema_version"] == _schema("remote-recovery")
            and proof["protocol_id"] == PROTOCOL_ID and proof["remote_repository"] == REPOSITORY,"invalid independent recovery proof")
        text(proof["remote_branch"]);sha(proof["remote_commit"],40);sha(proof["snapshot_sha256"]);sha(proof["journal_sha256"])
        require(clock(proof["operation_started_at"]) <= clock(proof["independent_recovery_completed_at"])
            <= clock(proof["completed_at"]) <= _now(),"independent recovery clocks conflict")
        check_seal(proof,"proof_id");self.journal()
        # Later appends do not invalidate original proof; it covers the exact
        # retained prefix ending at a complete entry, never invented metadata.
        raw_journal=self._journal_path().read_bytes();prefix=b"";covered=False
        for line in raw_journal.splitlines(keepends=True):
            prefix+=line
            if hashlib.sha256(prefix).hexdigest() == proof["journal_sha256"]:covered=True;break
        require(covered,"remote proof references no retained complete journal prefix")
        return proof

    def recovery_proof(self):
        return self._read_recovery_proof(self.root/PROOF)

    def recovery_proofs(self):
        directory=(self.root/PROOF).parent
        paths=sorted(directory.glob("remote-recovery.*.json")) if directory.exists() else []
        if (self.root/PROOF).exists():paths.append(self.root/PROOF)
        require(len(paths) <= 32,"too many independent recovery proof revisions")
        return [self._read_recovery_proof(path) for path in paths]

    def admission(self,reference):
        body=self.body(reference);entries=self.journal();proofs=self.recovery_proofs();proof=None
        local=next((r for r in entries if r["kind"] == "LOCAL" and r["reference"] == reference.to_record()),None)
        remote=next((r for r in entries if r["kind"] == "REMOTE" and r["reference"] == reference.to_record()),None)
        reasons=[]
        if body["mode"] == "REAL_TIME_CAPTURED":
            reasons.append("No reviewed OP002 activation is installed; retained real-time-labelled evidence is unadmitted.")
        if local is None:reasons.append("Original post-write local completion was not retained.")
        if remote is None:reasons.append("Independent remote original readback was not acknowledged.")
        covered=False
        if remote is not None:
            for candidate_proof in sorted(proofs,key=lambda candidate:clock(candidate["completed_at"])):
                if not any(row["kind"] == "PROOF_LOCAL" and row["acknowledgment"]["proof_id"] == candidate_proof["proof_id"]
                    for row in entries):continue
                prefix=b""
                for row in entries:
                    prefix+=canonical(row)+b"\n"
                    if hashlib.sha256(prefix).hexdigest() == candidate_proof["journal_sha256"]:
                        if remote["sequence"] <= row["sequence"]:
                            proof=candidate_proof;covered=True
                        break
                if covered:break
        if not covered:reasons.append("Final independent recovery has not covered the remote acknowledgment.")
        proof_local=None
        if proof is not None:
            proof_local=next((row for row in entries if row["kind"] == "PROOF_LOCAL"
                and row["acknowledgment"]["proof_id"] == proof["proof_id"]),None)
        if covered and proof_local is None:reasons.append("Final recovery proof local persistence/readback was not acknowledged.")
        cutoff=clock(body.get("cutoff_at",body.get("event",{}).get("event_starts_at",body.get("event_starts_at"))))
        if body["schema_version"] == _schema("event"):cutoff-=timedelta(minutes=90)
        deadline=cutoff+timedelta(seconds=300) if body["schema_version"] == _schema("forecast") else cutoff-timedelta(minutes=10)
        started=clock(body["generation_started_at"]) if body["schema_version"] == _schema("forecast") else None
        completed=[clock(row["completed_at"]) for row in (local,remote) if row is not None]
        if proof is not None and covered:completed.append(clock(proof["completed_at"]))
        if proof_local is not None:completed.append(clock(proof_local["completed_at"]))
        if any(value > deadline or started is not None and value-started > timedelta(seconds=120) for value in completed):
            reasons.append("Actual persistence or required independent recovery completed after its registered deadline.")
        if local is not None and clock(local["completed_at"]) < clock(self.read(reference)["received_at"]):
            reasons.append("Local completion precedes original receipt.")
        if remote is not None and local is not None and clock(remote["completed_at"]) < clock(local["completed_at"]):
            reasons.append("Remote completion precedes local completion.")
        return {"retained":True,"eligible":not reasons,"local_persistence_completed_at":local["completed_at"] if local else None,
            "remote_checkpoint_completed_at":remote["completed_at"] if remote else None,
            "final_recovery_completed_at":proof_local["completed_at"] if proof_local is not None else None,"reasons":reasons}

    def recover(self,*,replay=True):
        index=self.ledger.scan();records=[];forecast_keys=set();event=None;binding=None;rows=None;fitted={}
        for kind,values in index.items():
            for payload in values.values():
                if "operational" not in payload["data"]:continue
                ref=LedgerRef(kind,payload["record_id"],digest(payload));body=self.body(ref)
                if body["schema_version"] == _schema("event"):event=body
                if body["schema_version"] == _schema("forecast"):
                    key=(body["event_id"],body["player_id"],body["model_key"])
                    require(key not in forecast_keys,"duplicate original model subject");forecast_keys.add(key)
                    if binding is None:binding=body["producer_binding"]
                    require(binding == body["producer_binding"],"existing cycle uses a different producer revision")
                    if replay:
                        if rows is None:rows=history_rows(self.body(LedgerRef.from_record(body["history_ref"])),self.root)
                        target=_target(body,body["player_id"])
                        if body["player_id"] not in fitted:fitted[body["player_id"]]=_fit_laws(rows,target)
                        law=fitted[body["player_id"]][body["model_key"]]
                        require(body["categories"] == _categories(law) and body["reported_minutes"] == _minutes(law)
                            and body["joint_recipe"]["joint_sha256"] == joint_fingerprint(law)
                            and body["joint_recipe"]["input_sha256"] == law.input_sha256,"recovery does not reproduce original law")
                records.append((ref,body))
        for payload in index["corrections"].values():
            target=LedgerRef.from_record(payload["supersedes"])
            old=index[target.kind][target.record_id]
            if "operational" not in old["data"]:continue
            replacement=LedgerRef.from_record(payload["data"]["replacement"])
            new=index[replacement.kind][replacement.record_id]
            require(target.kind in {"outcomes","grades"} and "operational" in new["data"],
                "OP002 corrections may revise outcomes or grades, never original forecasts")
            before,after=old["data"]["operational"],new["data"]["operational"]
            require(_identity(before) == _identity(after) and before["mode"] == after["mode"]
                and before["schema_version"] == after["schema_version"],"correction changes original subject/lane/type")
            if target.kind == "grades":require(before["forecast_id"] == after["forecast_id"],"grade correction changes original forecast")
        self.journal();self.recovery_proofs();self._check_budget();self._check_type_limits()
        forecasts=[(ref,body,self.admission(ref)) for ref,body in records if body["schema_version"] == _schema("forecast")]
        missing=[]
        if event is not None:
            for player in event["candidates"]:
                for model in MODEL_VERSIONS:
                    if (event["event"]["event_id"],player["player_id"],model) not in forecast_keys:
                        missing.append({"player_id":player["player_id"],"model_key":model})
        return {"schema_version":_schema("recovery"),"protocol_id":PROTOCOL_ID,"records":records,
            "forecasts":forecasts,"missing":missing,"genuine_issued":sum(body["mode"] == "REAL_TIME_CAPTURED" and admission["eligible"]
                for _,body,admission in forecasts),"retained_realtime_originals":sum(body["mode"] == "REAL_TIME_CAPTURED"
                for _,body,_ in forecasts),"eligible_originals":sum(admission["eligible"] for _,_,admission in forecasts),
            "statistical_comparative_evaluation":"NOT_IMPLEMENTED_NOT_AUTHORIZED","qualification":"UNAVAILABLE"}

    def correct(self,original,replacement,*,reason):
        before,after=self.body(original),self.body(replacement)
        require(original.kind in {"outcomes","grades"} and replacement.kind == original.kind
            and _identity(before) == _identity(after) and before["mode"] == after["mode"]
            and before["schema_version"] == after["schema_version"],"only same-subject outcome/grade corrections are allowed")
        if original.kind == "grades":require(before["forecast_id"] == after["forecast_id"],"correction changes original forecast")
        if before["mode"] == "REAL_TIME_CAPTURED":require_activation()
        else:require(self.diagnostic,"diagnostics cannot correct real records")
        result=self.ledger.correct(original,replacement,reason=reason)
        self._check_budget();self.recover(replay=False)
        return result


def metadata_inventory(root):
    """Bound every retained completion/proof revision in the shared limits."""
    root=Path(root).absolute();files=[];directory=root/"evidence"/"operational002"
    if directory.exists():
        require(not directory.is_symlink(),"metadata directory cannot be symlinked")
        paths=list(directory.iterdir());require(len(paths) <= 33,"operational recovery revision reserve exceeded")
        for path in paths:
            require(path.is_file() and not path.is_symlink(),"invalid operational metadata file")
            if path.name == "completions.jsonl":limit=MAX_JOURNAL_BYTES
            else:
                require(path.name == "remote-recovery.json" or re.fullmatch(r"remote-recovery\.[a-f0-9]{64}\.json",path.name),
                    "unrecognized operational metadata")
                limit=MAX_PROOF_BYTES
            raw=path.read_bytes();require(len(raw) <= limit,"operational metadata file exceeds individual ceiling")
            files.append({"path":path.relative_to(root).as_posix(),"bytes":len(raw),"raw_sha256":hashlib.sha256(raw).hexdigest()})
    legacy=root/"evidence"/"pros004"/"completion-journal.jsonl"
    if legacy.exists():
        from .pros004_completion import load_journal, MAX_JOURNAL_BYTES as legacy_limit
        require(legacy.is_file() and not legacy.is_symlink() and legacy.stat().st_size <= legacy_limit,"invalid legacy completion metadata")
        load_journal(root);raw=legacy.read_bytes()
        files.append({"path":legacy.relative_to(root).as_posix(),"bytes":len(raw),"raw_sha256":hashlib.sha256(raw).hexdigest()})
    files.sort(key=lambda item:item["path"])
    return {"files":files,"file_count":len(files),"total_bytes":sum(item["bytes"] for item in files)}


def snapshot_manifest(root):
    """Read-only exact byte inventory; no source request, write or regeneration."""
    store=OperationalStore(root);inventory,_,_=store.ledger._inventory();files=[]
    for kind,values in inventory.items():
        for path,_ in values:
            raw=path.read_bytes();files.append({"path":path.relative_to(store.root).as_posix(),"bytes":len(raw),
                "raw_sha256":hashlib.sha256(raw).hexdigest()})
    files.extend(metadata_inventory(store.root)["files"])
    files.sort(key=lambda item:item["path"])
    require(len(files) <= MAX_LEDGER_RECORDS and sum(item["bytes"] for item in files) <= MAX_LEDGER_BYTES,
            "snapshot exceeds unchanged receipt/byte limits")
    return seal({"schema_version":_schema("snapshot"),"protocol_id":PROTOCOL_ID,"files":files,
        "file_count":len(files),"total_bytes":sum(item["bytes"] for item in files)},"snapshot_id")


def verify_store(root,*,replay=True,allow_synthetic_foreign=False,raw_reader=None):
    """Full typed/replayed independent recovery without any write or generation."""
    store=OperationalStore(root);before=snapshot_manifest(root);recovered=store.recover(replay=replay)
    # A full remote acknowledgment is stronger than an independent publication
    # channel. Every known retained typed lane must be semantically valid even
    # when it is unrelated to OP002 and excluded from its own export.
    from .pros004_records import Pros004Store
    foreign=Pros004Store(root);foreign.ledger=CompositeEnvelopeLedger(root)
    index=store.ledger.scan()
    has_offers=False
    for kind,values in index.items():
        for payload in values.values():
            data=payload["data"];reference=LedgerRef(kind,payload["record_id"],digest(payload))
            if "pros004" in data:foreign.read(reference)
            if "offer_raw_capture" in data:
                from .offer_publication import validate_raw_capture
                require(allow_synthetic_foreign is True,"synthetic offer raw evidence requires explicit diagnostic recovery policy")
                exact(data,{"offer_raw_capture"},"foreign offer raw capture")
                validate_raw_capture(data["offer_raw_capture"])
            if "offer_capture" in data:has_offers=True
    if has_offers:
        from .offer_publication import OfferStore
        OfferStore(root,allow_synthetic=allow_synthetic_foreign,raw_reader=raw_reader).active()
    after=snapshot_manifest(root)
    require(before == after,"store changed during independent typed recovery")
    return seal({"schema_version":_schema("verified-snapshot"),"protocol_id":PROTOCOL_ID,
        "verified_at":stamp(_now()),"snapshot":after,"replayed_complete_laws":bool(replay),
        "genuine_issued":recovered["genuine_issued"],"eligible_originals":recovered["eligible_originals"],
        "retained_originals":len(recovered["forecasts"]),"missing_peers":recovered["missing"],
        "statistical_scores_computed":0,"qualification":"UNAVAILABLE"},"verification_id")


def issue_pair(store,event_ref,producer_binding,*,checkpoint,final_checkpoint,checkpoint_many=None):
    """Recover before generating; interruption never erases an original peer."""
    with store.single_writer():
        recovered=store.recover(replay=True);event=store.body(event_ref)
        validate_source_binding(producer_binding,check_current=True)
        require(all(body["event_ref"] == event_ref.to_record() and body["producer_binding"] == producer_binding
            for _,body,_ in recovered["forecasts"]),"recovery intended: use original event/input/producer, never a new cohort")
        if event["mode"] == "REAL_TIME_CAPTURED":
            require_activation(store.activation.get("evidence") if type(store.activation) is dict else None,event["plan"],producer_binding)
        require(store.admission(event_ref)["eligible"],"fresh event input lacks timely local/remote/final-prefix admission")
        history_ref=LedgerRef.from_record(event["history_ref"]);history=store.body(history_ref);rows=history_rows(history,store.root)
        existing={(body["player_id"],body["model_key"]):(ref,body) for ref,body,_ in recovered["forecasts"]}
        for player in event["candidates"]:
            complete=all((player["player_id"],model) in existing for model in MODEL_VERSIONS)
            if complete and (checkpoint_many is None or all(store.admission(existing[(player["player_id"],model)][0])["eligible"]
                for model in MODEL_VERSIONS)):continue
            target=_target(event["event"],player["player_id"]);_window(target,_now())
            prepared={} if complete else prepare_pair(event,history,rows,event_ref=event_ref,history_ref=history_ref,
                player_id=player["player_id"],producer_binding=producer_binding)
            if checkpoint_many is not None:
                active_model=None
                try:
                    pair_refs=[]
                    for model in MODEL_VERSIONS:
                        key=(player["player_id"],model)
                        if key not in existing:
                            active_model=model;body=prepared[model]
                            # Generation preflight is not a persistence permit:
                            # each later immutable write has its own actual gate.
                            _window(target,_now(),clock(body["generation_started_at"]))
                            ref=store.persist(body,references=(event_ref,history_ref))
                            existing[key]=(ref,body)
                        pair_refs.append(existing[key][0])
                    active_model=None
                    store.checkpoint_many(tuple(pair_refs),checkpoint_many)
                    store.finalize_checkpoint(final_checkpoint)
                    admissions=[store.admission(ref) for ref in pair_refs]
                    require(all(item["eligible"] for item in admissions),
                        "retained paired originals include late/unacknowledged evidence; individual eligibility remains separate")
                except Exception as error:
                    try:store.record_failure(event_ref,status="PARTIAL",reason=type(error).__name__+": "+str(error),
                        player_id=player["player_id"],model_key=active_model)
                    except Exception as metadata_error:
                        raise IntegrityError("originals retained if written; paired failure metadata also blocked: "+str(metadata_error)) from error
                    raise
                continue
            for model in MODEL_VERSIONS:
                key=(player["player_id"],model)
                if key in existing:continue
                body=prepared[model]
                try:
                    _window(target,_now(),clock(body["generation_started_at"]))
                    ref=store.persist(body,references=(event_ref,history_ref))
                    store.checkpoint(ref,checkpoint)
                    # Final proof per original makes a completed R0 durable even
                    # if its K0 peer never finishes. Earlier proofs are retained.
                    store.finalize_checkpoint(final_checkpoint)
                    admission=store.admission(ref)
                    require(admission["eligible"],"retained original is late/unacknowledged and cannot count as timely issuance")
                    existing[key]=(ref,body)
                except Exception as error:
                    # Factual operational metadata has an actual later clock;
                    # it cannot repair admission or stand in for a missing peer.
                    try:store.record_failure(event_ref,status="PARTIAL",reason=type(error).__name__+": "+str(error),
                        player_id=player["player_id"],model_key=model)
                    except Exception as metadata_error:
                        raise IntegrityError("original retained if written; failure metadata also blocked: "+str(metadata_error)) from error
                    raise
        return store.recover(replay=True)


def validate_outcome(body):
    exact(body,{"schema_version","protocol_id","mode","event_id","event_version","event_starts_at","player_id",
        "team_id","opponent_id","status","source_observed_at","source_updated_at","normalized_at","source_raw_sha256",
        "raw_evidence_ref","normalizer_version","primitives","minutes","minutes_precision","categories","outcome_id"},"outcome")
    require(body["schema_version"] == _schema("outcome") and body["protocol_id"] == PROTOCOL_ID
        and body["mode"] in MODES and body["status"] in OUTCOME_STATUSES,"invalid outcome status/lane")
    for key in ("event_id","player_id","team_id","opponent_id","normalizer_version"):text(body[key])
    require(body["team_id"] != body["opponent_id"],"outcome identity conflict")
    sha(body["event_version"]);sha(body["source_raw_sha256"])
    observed,normalized,start=clock(body["source_observed_at"]),clock(body["normalized_at"]),clock(body["event_starts_at"])
    _validate_raw_outcome_evidence(body["raw_evidence_ref"],body)
    require(observed <= normalized <= _now() and (body["source_updated_at"] is None or clock(body["source_updated_at"]) <= observed),
            "outcome clocks conflict")
    if body["status"] in {"APPEARED","DNP"}:require(observed >= start,"final result observed before event")
    if body["status"] == "APPEARED":
        require(body["categories"] == _outcome_categories(body["primitives"]),"outcome violates scoring identities")
        mapping={"fg2m":"FG2M","fg3m":"FG3M","ftm":"FTM","rebounds":"REB","assists":"AST",
                 "turnovers":"TOV","blocks":"BLK","steals":"STL"}
        baseline.PrimitiveLine(minutes=body["minutes"],minutes_precision=body["minutes_precision"],
            **{key:body["primitives"][wire] for key,wire in mapping.items()})
    else:require(body["primitives"] is None and body["minutes"] is None and body["minutes_precision"] is None
        and body["categories"] == [],"pending/DNP is not a fabricated zero outcome")
    check_seal(body,"outcome_id");return body


def _validate_raw_outcome_evidence(evidence,outcome=None):
    """Bind interpreted clocks/identity to retained encrypted capture metadata."""
    from . import operational_raw as raw_contract
    exact(evidence,{"reference","metadata"},"outcome raw evidence")
    reference,metadata=evidence["reference"],evidence["metadata"]
    exact(reference,raw_contract._REF_FIELDS,"encrypted raw reference")
    exact(metadata,raw_contract._FIELDS,"encrypted raw metadata")
    require(reference["schema_version"] == raw_contract.REF_SCHEMA and metadata["schema_version"] == raw_contract.SCHEMA
        and metadata["pilot_id"] == PROTOCOL_ID and metadata["mode"] in MODES
        and metadata["encryption"] == raw_contract.ENCRYPTION and raw_contract._reference(metadata) == reference,
        "outcome raw reference/metadata identity conflict")
    for key in ("raw_sha256","cipher_sha256","recipient_certificate_sha256","capture_id"):sha(metadata[key])
    require(type(metadata["raw_bytes"]) is int and type(metadata["cipher_bytes"]) is int
        and 0 < metadata["raw_bytes"] < metadata["cipher_bytes"] <= raw_contract.MAX_OBJECT_BYTES
        and metadata["cipher_bytes"]-metadata["raw_bytes"] <= raw_contract.MAX_CMS_OVERHEAD_BYTES,
        "raw outcome encoded byte bounds conflict")
    identity={key:value for key,value in metadata.items() if key not in raw_contract._IDENTITY_EXCLUDED}
    require(digest(identity) == metadata["capture_id"],"raw capture identity changed")
    clocks=[clock(metadata[key]) for key in ("request_started_at","source_observed_at","imported_at",
        "encryption_completed_at","cipher_persistence_completed_at","manifest_prepared_at")]
    require(clocks == sorted(clocks) and clocks[-1] <= _now(),"raw source/persistence clocks conflict")
    if metadata["source_updated_at"] is not None:require(clock(metadata["source_updated_at"]) <= clocks[1],"raw update clock exceeds observation")
    if metadata["mode"] == "REAL_TIME_CAPTURED":sha(metadata["admission_sha256"])
    else:require(metadata["admission_sha256"] is None,"diagnostic raw cannot claim genuine source admission")
    if metadata["supersedes"] is None:require(metadata["correction_reason"] is None,"raw correction lacks original")
    else:text(metadata["correction_reason"])
    if outcome is not None:
        require(all(outcome[key] == metadata[key] for key in ("event_id","mode","source_observed_at","source_updated_at"))
            and outcome["source_raw_sha256"] == reference["raw_sha256"]
            and clocks[-1] <= clock(outcome["normalized_at"]),"outcome differs from original raw capture clocks/subject")
        from urllib.parse import parse_qs, urlsplit
        url=urlsplit(metadata["source_url"])
        require(url.scheme == "https" and url.netloc == "site.api.espn.com"
            and url.path == "/apis/site/v2/sports/basketball/nba/summary"
            and parse_qs(url.query) == {"event":[outcome["event_id"]]} and not url.fragment,
            "outcome raw source is not its exact NBA summary route")
    return evidence


def normalize_outcome_bytes(event_body,raw_reference,*,resolver):
    """Authenticate/read retained bytes, then normalize one shared player outcome.

    The supplied resolver must be the reviewed read-only encrypted archive's
    authenticated read method. This path never obtains a clock from a caller or
    fetches a future result, and it does not emit forecasts or financial grades.
    """
    validate_event(event_body)
    require(callable(resolver),"authenticated read-only raw resolver is required")
    metadata,raw=resolver(raw_reference)
    evidence={"reference":raw_reference,"metadata":metadata};_validate_raw_outcome_evidence(evidence)
    require(type(raw) is bytes and len(raw) == raw_reference["raw_bytes"]
        and hashlib.sha256(raw).hexdigest() == raw_reference["raw_sha256"],"authenticated raw readback bytes changed")
    require(metadata["event_id"] == event_body["event"]["event_id"] and metadata["mode"] == event_body["mode"],"raw capture belongs to another event/lane")
    from .prospective_outcomes import normalize_summary
    normalized=normalize_summary(raw,event_body["event"],event_body["candidates"],observed_at=clock(metadata["source_observed_at"]))
    source=json.loads(raw);competition=source["header"]["competitions"][0]
    state=competition.get("status",source["header"].get("status",{})).get("type",{}).get("name")
    result={}
    for candidate in event_body["candidates"]:
        row=normalized["rows"].get(candidate["player_id"])
        primitives=minutes=precision=None;categories=[]
        if row is not None:
            status="DNP" if row.participation == "DNP" else "APPEARED"
            if status == "APPEARED":
                mapping={"FGM":"fgm","FG2M":"fg2m","FG3M":"fg3m","FTM":"ftm","PTS":"points",
                    "REB":"rebounds","AST":"assists","TOV":"turnovers","BLK":"blocks","STL":"steals"}
                primitives={key:getattr(row,value) for key,value in mapping.items()};categories=_outcome_categories(primitives)
                minutes,precision=row.minutes,row.minutes_precision
        elif normalized["status"].startswith("FINAL"):
            pending=next(item for item in normalized["pending"] if item["player_id"] == candidate["player_id"])
            status="MISSING" if pending["reason"] == "SELECTED_ATHLETE_MISSING_FROM_FINAL_BOXSCORE" else "UNRESOLVED"
        else:status="POSTPONED" if state == "STATUS_POSTPONED" else "NONFINAL"
        body=seal({"schema_version":_schema("outcome"),"protocol_id":PROTOCOL_ID,"mode":event_body["mode"],
            **{key:event_body["event"][key] for key in ("event_id","event_version","event_starts_at")},
            **{key:candidate[key] for key in ("player_id","team_id","opponent_id")},"status":status,
            "source_observed_at":metadata["source_observed_at"],"source_updated_at":metadata["source_updated_at"],
            "normalized_at":stamp(_now()),"source_raw_sha256":raw_reference["raw_sha256"],"raw_evidence_ref":evidence,
            "normalizer_version":"operational002-espn-outcomes-v1","primitives":primitives,"minutes":minutes,
            "minutes_precision":precision,"categories":categories},"outcome_id")
        result[candidate["player_id"]]=validate_outcome(body)
    return result


def make_grade(forecast,outcome,*,graded_at=None):
    validate_forecast_record(forecast);validate_outcome(outcome)
    require(all(forecast[key] == outcome[key] for key in ("event_id","event_version","event_starts_at","player_id","team_id","opponent_id","mode")),
            "grade target differs from original outcome")
    graded_at=stamp(_now()) if graded_at is None else graded_at
    require(clock(outcome["normalized_at"]) <= clock(graded_at) <= _now(),"grade clock precedes evidence or is future")
    scored=outcome["status"] == "APPEARED"
    body={"schema_version":_schema("grade"),"protocol_id":PROTOCOL_ID,"mode":forecast["mode"],
        **{key:forecast[key] for key in ("event_id","event_version","event_starts_at","player_id","team_id","opponent_id","model_key")},
        "forecast_id":forecast["forecast_id"],"outcome_id":outcome["outcome_id"],"graded_at":graded_at,
        "status":"SCORED" if scored else "DNP_NOT_SCORED" if outcome["status"] == "DNP" else outcome["status"],
        "categories":_score_categories(_validation_forecast(forecast),outcome) if scored else [],
        "financial_settlement":"NOT_EVALUATED","qualification":"UNAVAILABLE"}
    return seal(body,"grade_id")


def capacity_report(root=None):
    """Bound complete one-event operation, corrections and metadata, not a study."""
    ledger=_OperationalLedger(root);_,existing_count,existing_bytes=ledger._inventory()
    # Existing ledger includes the original complete history once. New receipts
    # reserve a pointer, event, 8 originals, 4 shared outcomes, 8 grades, 8 failure
    # diagnostics, plus 8 replacements and 8 traceable correction links.
    planned={"history":1,"event":1,"forecast":8,"outcome":4,"grade":8,"failure":8}
    replacements=8;correction_links=8;metadata_files=33
    planned_records=sum(planned.values())+replacements+correction_links+metadata_files
    planned_bytes=sum(CEILINGS[key]*count for key,count in planned.items())+replacements*16*1024+correction_links*8*1024+MAX_JOURNAL_BYTES+32*MAX_PROOF_BYTES
    actual_metadata_count=actual_metadata_bytes=0
    directory=Path(ledger.root)/"evidence"/"operational002"
    if directory.exists():
        for path in directory.iterdir():
            if path.is_file():actual_metadata_count+=1;actual_metadata_bytes+=path.stat().st_size
    require(existing_count+planned_records+actual_metadata_count <= MAX_LEDGER_RECORDS
        and existing_bytes+planned_bytes+actual_metadata_bytes <= MAX_LEDGER_BYTES,"complete OP002 capacity does not fit unchanged limits")
    return {"schema_version":_schema("capacity"),"protocol_id":PROTOCOL_ID,"existing_records":existing_count,
        "existing_bytes":existing_bytes,"planned_record_counts":planned,"correction_replacement_records":replacements,
        "correction_link_records":correction_links,"metadata_file_reserve":metadata_files,
        "maximum_records":existing_count+planned_records+actual_metadata_count,
        "maximum_bytes":existing_bytes+planned_bytes+actual_metadata_bytes,"global_record_limit":MAX_LEDGER_RECORDS,
        "global_byte_limit":MAX_LEDGER_BYTES,"complete_history_rows":PANEL_ROWS,"history_repeated_per_event":False,
        "qualification":"UNAVAILABLE","activation":"INACTIVE"}

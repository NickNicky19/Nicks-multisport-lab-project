"""Bounded, restart-safe PROS004 records over the unchanged shared ledger.

This separate contract does not admit the reserved comparison. Diagnostic records
are explicitly non-issuance and may only be written to a separate diagnostic root.
Original source/issuance bodies remain immutable; corrections append links.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import fcntl
import hashlib
import math
from pathlib import Path
import re
import subprocess

from .integrity import (HASH_FORMAT, RECEIPT_SCHEMA, IntegrityError, canonical,
                        digest, stamp, utc)
from . import ledger as frozen_ledger
from . import pros004_completion as completion
from .ledger import (Ledger, LedgerRef, SCHEMA as LEDGER_SCHEMA, KINDS,
                     MAX_LEDGER_RECORDS, MAX_LEDGER_BYTES, _outcome_categories,
                     _score_categories, _number_text)

STUDY_ID = "NBA-ALL13-JOINT-PROS-004"
MODEL_KEYS = ("R0", "K0")
RESERVE_RECORDS = 13
DIAGNOSTIC_MODES = {"READINESS_DIAGNOSTIC", "SYNTHETIC_DIAGNOSTIC"}
MODES = DIAGNOSTIC_MODES | {"REAL_TIME_CAPTURED"}
EVALUATION_NOT_BEFORE = datetime(2026, 11, 25, tzinfo=timezone.utc)
CEILINGS = {"nba-pros004-history-v1": 2*1024*1024,
            "nba-pros004-event-v1": 32*1024,
            "nba-pros004-date-status-v1": 32*1024,
            "nba-pros004-forecast-v1": 64*1024,
            "nba-pros004-outcome-v1": 8*1024,
            "nba-pros004-grade-v1": 16*1024,
            "nba-pros004-event-claim-v1": 8*1024,
            "nba-pros004-study-manifest-v1": 8*1024,
            "nba-pros004-failure-v1": 8*1024}
SCHEMA_KINDS = {"nba-pros004-history-v1": "research_inputs",
                "nba-pros004-event-v1": "research_inputs",
                "nba-pros004-date-status-v1": "research_inputs",
                "nba-pros004-forecast-v1": "forecasts",
                "nba-pros004-outcome-v1": "outcomes",
                "nba-pros004-grade-v1": "grades",
                "nba-pros004-event-claim-v1": "input_captures",
                "nba-pros004-study-manifest-v1": "input_captures",
                "nba-pros004-failure-v1": "input_captures"}
OUTCOME_STATUSES = {"APPEARED", "DNP", "MISSING", "POSTPONED", "NONFINAL", "UNRESOLVED"}


def _now():
    return datetime.now(timezone.utc)


def _text(value, name):
    if type(value) is not str or not value or value.strip() != value:
        raise IntegrityError(f"{name} must be a nonempty trimmed string")
    return value


def _hash(value, name):
    if type(value) is not str or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise IntegrityError(f"{name} requires a SHA256")
    return value


def _time(value, name):
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", value):
        raise IntegrityError(f"{name} requires an actual microsecond UTC clock")
    return utc(value)


def _event(body):
    return body.get("event", body)


def _identity(body):
    schema = body.get("schema_version")
    event = _event(body)
    identity = {"study_id": STUDY_ID, "id_namespace": "espn", "league": "NBA"}
    if schema == "nba-pros004-failure-v1":
        identity["event_input_record_id"]=LedgerRef.from_record(body["event_ref"]).record_id
        if body["subject_id"] is not None:identity["player_id"]=body["subject_id"]
    if schema == "nba-pros004-history-v1":
        identity["history"] = "FIXED_FULL_26645_ROW_HISTORY"
    elif "event_id" in event:
        identity.update(event_id=_text(event["event_id"], "event_id"),
                        event_starts_at=stamp(utc(event["event_starts_at"])))
    if "player_id" in body:
        identity["player_id"] = _text(body["player_id"], "player_id")
    if "model_key" in body:
        if body["model_key"] not in MODEL_KEYS:
            raise IntegrityError("PROS004 excludes unregistered models")
        identity["model_key"] = body["model_key"]
    return identity


def encoded_envelope_size(kind, logical_id, data, *, references=(), received_at=None):
    """Exact complete on-disk envelope size, including ledger/reference overhead."""
    record_id = digest({"kind": kind, "logical_id": logical_id})
    payload = {"schema_version": LEDGER_SCHEMA, "kind": kind, "record_id": record_id,
               "logical_id": logical_id, "received_at": received_at or stamp(_now()),
               "data": data, "references": [r.to_record() for r in references],
               "supersedes": None, "persistence_status": "LOCAL_RECEIPT_ONLY"}
    return len(canonical({"schema_version": RECEIPT_SCHEMA, "hash_format": HASH_FORMAT,
                          "payload_sha256": digest(payload), "payload": payload}))


def _study_capacity(*, completion_journal):
    """Frozen ceilings, corrected pilot allowance, and explicit metadata reserve."""
    counts = {"forecasts": 168, "outcomes": 84, "grades": 168,
              "event_inputs": 21, "shared_history": 1,
              "old_historical_records": 18, "full_pilot_allowance": 14,
              "study_manifest": 1, "event_admission_claims": 21,
              "future_activation_readback_evaluation_metadata": 2 if completion_journal else 3,
              "correction_or_failure_reserve": RESERVE_RECORDS}
    if completion_journal:
        counts["completion_journal_files"]=1
    comparison = 168*64*1024+84*8*1024+168*16*1024+21*32*1024+2*1024*1024
    baseline = 4*1024*1024
    metadata = (24*8*1024+completion.MAX_JOURNAL_BYTES) if completion_journal else 25*8*1024
    # The largest possible new record is64KiB; this deliberately over-reserves
    # the correction/failure allowance instead of counting only a small link.
    reserve = RESERVE_RECORDS*64*1024
    total = comparison+baseline+metadata+reserve
    records = sum(counts.values())
    if MAX_LEDGER_RECORDS != 512 or MAX_LEDGER_BYTES != 32*1024*1024:
        raise IntegrityError("shared ledger limits changed; capacity needs renewed review")
    if records > MAX_LEDGER_RECORDS or total > MAX_LEDGER_BYTES:
        raise IntegrityError("full planned PROS004 comparison exceeds shared ledger limits")
    return {"schema_version": "nba-pros004-capacity-v2" if completion_journal else "nba-pros004-capacity-v1", "counts": counts,
            "comparison_records": 442, "full_study_records_before_reserve": records-RESERVE_RECORDS,
            "maximum_records_including_reserve": records,
            "remaining_record_slots_after_reserve": MAX_LEDGER_RECORDS-records,
            "comparison_envelope_ceiling_bytes": comparison,
            "existing_plus_full_pilot_ceiling_bytes": baseline,
            "metadata_envelope_ceiling_bytes": metadata,
            "correction_failure_reserve_ceiling_bytes": reserve,
            "maximum_planned_bytes": total,
            "remaining_bytes_after_reserve": MAX_LEDGER_BYTES-total,
            "global_record_limit": MAX_LEDGER_RECORDS, "global_byte_limit": MAX_LEDGER_BYTES,
            "qualification": "UNAVAILABLE", "activation": "INACTIVE"}


def full_study_capacity():
    """Reserve one bounded completion journal within the original metadata slots."""
    return _study_capacity(completion_journal=True)


def _logical(body):
    schema = body["schema_version"]
    if schema == "nba-pros004-history-v1":
        return "pros004:history:fixed"
    if schema == "nba-pros004-study-manifest-v1":
        return "pros004:manifest"
    if schema == "nba-pros004-date-status-v1":
        return f"pros004:event:{body['event_date']}"
    if schema == "nba-pros004-failure-v1":
        return "pros004:failure:"+digest(body)
    event = _event(body)
    day = utc(event["event_starts_at"]).date().isoformat()
    if schema == "nba-pros004-event-v1":
        # One selected event per registered date; changed event cannot create
        # another original event after a recovery/selection failure.
        return f"pros004:event:{day}"
    if schema == "nba-pros004-event-claim-v1":
        return f"pros004:event-admission:{day}"
    if schema == "nba-pros004-forecast-v1":
        return f"pros004:forecast:{day}:{event['event_id']}:{body['player_id']}:{body['model_key']}:{body['cutoff_at']}"
    if schema in {"nba-pros004-outcome-v1", "nba-pros004-grade-v1"}:
        suffix = "outcome" if schema.endswith("outcome-v1") else "grade"
        content = digest({k: v for k, v in body.items() if k not in {"outcome_id", "grade_id"}})
        return f"pros004:{suffix}:{content}"
    raise IntegrityError("unknown PROS004 record schema")


def validate_outcome_body(body):
    fields = {"schema_version", "study_id", "mode", "event_id", "event_version",
              "event_starts_at", "player_id", "team_id", "opponent_id", "status",
              "source_observed_at", "source_updated_at", "normalized_at", "source_raw_sha256",
              "normalizer_version", "primitives", "minutes", "minutes_precision", "categories", "outcome_id"}
    if type(body) is not dict or set(body) != fields or body["schema_version"] != "nba-pros004-outcome-v1":
        raise IntegrityError("invalid shared PROS004 outcome schema")
    if body["study_id"] != STUDY_ID or body["mode"] not in MODES or body["status"] not in OUTCOME_STATUSES:
        raise IntegrityError("invalid shared PROS004 outcome meaning")
    for key in ("event_id", "player_id", "team_id", "opponent_id", "normalizer_version"):
        _text(body[key], key)
    if body["team_id"] == body["opponent_id"]:
        raise IntegrityError("outcome team and opponent conflict")
    _hash(body["event_version"], "event_version")
    _hash(body["source_raw_sha256"], "source_raw_sha256")
    observed, normalized = _time(body["source_observed_at"], "source_observed_at"), _time(body["normalized_at"], "normalized_at")
    start = _time(body["event_starts_at"], "event_starts_at")
    if observed > normalized or normalized > _now():
        raise IntegrityError("outcome observation/import clocks are inconsistent")
    if body["source_updated_at"] is not None and _time(body["source_updated_at"], "source_updated_at") > observed:
        raise IntegrityError("source update clock exceeds its actual observation")
    if body["status"] in {"APPEARED", "DNP"} and observed < start:
        raise IntegrityError("verified final outcome precedes event")
    if body["status"] == "APPEARED":
        if body["categories"] != _outcome_categories(body["primitives"]):
            raise IntegrityError("shared outcome violates coherent count identities")
        if (type(body["minutes"]) not in (int,float) or not math.isfinite(body["minutes"]) or body["minutes"] < 0
                or body["minutes_precision"] not in {"seconds", "rounded_whole_minutes"}
                or body["minutes"] == 0 and body["minutes_precision"] != "rounded_whole_minutes"):
            raise IntegrityError("appearance minute precision is invalid; DNP is not zero")
    elif body["primitives"] is not None or body["minutes"] is not None or body["minutes_precision"] is not None or body["categories"]:
        raise IntegrityError("nonappearance/pending states cannot contain statistical zero outcomes")
    if body["outcome_id"] != digest({k:v for k,v in body.items() if k != "outcome_id"}):
        raise IntegrityError("shared outcome checksum mismatch")
    return body


def _score_reported_minutes(forecast,outcome):
    """Individual workload diagnostics; never aggregate the reserved comparison."""
    from .pros004_producer import quantile
    distribution=forecast["reported_minutes"]
    pmf={Decimal(str(row["value"])):Decimal(row["probability"]) for row in distribution["pmf"]}
    observed=Decimal(str(outcome["minutes"]))
    with localcontext() as context:
        context.prec=50
        absolute=sum((weight*abs(value-observed) for value,weight in pmf.items()),Decimal(0))
        cumulative=moment=pair_half=Decimal(0)
        for value,weight in sorted(pmf.items()):
            pair_half+=weight*(value*cumulative-moment)
            cumulative+=weight;moment+=weight*value
        mass=pmf.get(observed,Decimal(0))
        intervals=[]
        for level in (.5,.8,.95):
            lower=quantile(distribution["pmf"],(1-level)/2)
            upper=quantile(distribution["pmf"],1-(1-level)/2)
            predicted=sum((weight for value,weight in pmf.items() if Decimal(str(lower))<=value<=Decimal(str(upper))),Decimal(0))
            intervals.append({"nominal":str(level),"lower":lower,"upper":upper,
                "covered":lower<=outcome["minutes"]<=upper,"predicted_mass":_number_text(predicted)})
        return {"observed":outcome["minutes"],"observed_precision":outcome["minutes_precision"],
            "forecast_precision":distribution["precision"],
            "crps":_number_text(max(Decimal(0),absolute-pair_half)),
            "absolute_mean_error":_number_text(abs(Decimal(distribution["mean"])-observed)),
            "log_loss":_number_text(-mass.ln()) if mass else None,
            "log_loss_status":"FINITE" if mass else "ZERO_SUPPORT","intervals":intervals}


class _Pros004Ledger(Ledger):
    """Versioned research-input extension without changing frozen R1 behavior.

    The original class deliberately accepts only a combined legacy source_pack.
    This subclass preserves its generic envelopes and global budgets while the
    facade verifies separate shared-history/event contracts. Every old record
    and every other kind still uses the exact frozen validator.
    """
    def __init__(self,root=None):
        super().__init__(root)
        # Cache only successful, self-contained legacy source-pack semantics.
        # No decoded object, receipt bytes, reference result or clock is cached.
        # New compact PROS004 inputs avoid an otherwise redundant large digest.
        self._legacy_source_validations={}

    def _validate_payload(self,payload, *, kind, record_id):
        data=payload.get('data') if type(payload) is dict else None
        legacy_source=(kind=="research_inputs" and type(data) is dict
                       and "source_pack" in data and "pros004" not in data)
        if not legacy_source:
            return self._validate_uncached_payload(payload,kind=kind,record_id=record_id)
        # Read/scan callers still read and verify the actual receipt first. A
        # backwards clock must fail even when these exact bytes were valid in
        # an earlier read. Source clocks were proved <=received_at on the miss.
        if _time(payload.get("received_at"),"received_at")>frozen_ledger._now():
            raise IntegrityError("ledger receipt creation clock is in the future")
        key=(kind,record_id,digest(payload))
        if key in self._legacy_source_validations:
            return
        self._validate_uncached_payload(payload,kind=kind,record_id=record_id)
        if _time(payload["received_at"],"received_at")>frozen_ledger._now():
            raise IntegrityError("ledger receipt creation clock is in the future")
        if len(self._legacy_source_validations)>=MAX_LEDGER_RECORDS:
            self._legacy_source_validations.pop(next(iter(self._legacy_source_validations)))
        self._legacy_source_validations[key]=None

    @staticmethod
    def _validate_uncached_payload(payload, *, kind, record_id):
        data=payload.get('data') if type(payload) is dict else None
        body=data.get("pros004") if type(data) is dict else None
        if kind!="research_inputs" or body is None:
            return Ledger._validate_payload(payload,kind=kind,record_id=record_id)
        fields={"schema_version","kind","record_id","logical_id","received_at","data","references","supersedes","persistence_status"}
        if set(payload)!=fields or payload["schema_version"]!=LEDGER_SCHEMA or payload["kind"]!=kind:
            raise IntegrityError("invalid versioned PROS004 ledger envelope")
        if payload["record_id"]!=record_id or record_id!=digest({"kind":kind,"logical_id":payload["logical_id"]}):
            raise IntegrityError("versioned PROS004 logical record hash mismatch")
        _text(payload["logical_id"],"logical_id")
        if _time(payload["received_at"],"received_at")>frozen_ledger._now() or payload["persistence_status"]!="LOCAL_RECEIPT_ONLY":
            raise IntegrityError("versioned PROS004 receipt clock/status conflicts")
        if set(payload["data"])!={"identity","pros004"} or type(body) is not dict or body.get("schema_version") not in {
                "nba-pros004-history-v1","nba-pros004-event-v1","nba-pros004-date-status-v1"}:
            raise IntegrityError("unsupported separate PROS004 input body")
        if type(payload["references"]) is not list or payload["supersedes"] is not None:
            raise IntegrityError("invalid separate-input references/correction status")
        refs=[LedgerRef.from_record(r) for r in payload["references"]]
        if len(set(refs))!=len(refs):
            raise IntegrityError("duplicate separate-input references")


class Pros004Store:
    """One ledger namespace with explicit schemas, original clocks and limits."""
    def __init__(self, root=None, *, diagnostic=False, activation=None):
        self.ledger = _Pros004Ledger(root)
        self.root = self.ledger.root
        self.diagnostic = bool(diagnostic)
        self.activation = activation
        if type(diagnostic) is not bool:
            raise IntegrityError("diagnostic mode must be explicit")
        if diagnostic:
            existing=self.root.resolve()
            while not existing.exists():existing=existing.parent
            probe=subprocess.run(["git","-C",str(existing),"rev-parse","--show-toplevel"],capture_output=True,text=True,check=False)
            if probe.returncode==0:
                raise IntegrityError("diagnostic records require a separate root outside every Git worktree")
        self._validated = set()
        self._validating = set()
        full_study_capacity()

    @contextmanager
    def single_writer(self):
        """Process lock outside records; durable originals stay in the ledger."""
        self.root.mkdir(parents=True, exist_ok=True)
        local = self.root/".local-data"
        if local.is_symlink():
            raise IntegrityError("writer state directory cannot be symlinked")
        local.mkdir(exist_ok=True)
        path = local/"pros004-writer.lock"
        if path.is_symlink():
            raise IntegrityError("writer lock cannot be symlinked")
        with path.open("a+b") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise IntegrityError("another PROS004 writer is active") from error
            try:
                self.reject_ambiguous_temporary_records()
                self._inventory()
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    writer_lock = single_writer

    def _check_mode(self, body, *, writing=False):
        mode = body.get("mode")
        if mode is None and body["schema_version"] in {"nba-pros004-event-claim-v1", "nba-pros004-study-manifest-v1"}:
            if writing and not self.diagnostic:
                raise IntegrityError("PROS004 readiness-only: new metadata writes require a diagnostic store")
            return
        if mode not in MODES:
            raise IntegrityError("unknown PROS004 evidence mode")
        if writing and mode == "REAL_TIME_CAPTURED":
            raise IntegrityError("PROS004 readiness-only: genuine writes require a separately reviewed activation package")
        if writing and mode in DIAGNOSTIC_MODES and not self.diagnostic:
            raise IntegrityError("non-issuance diagnostics cannot write to the actual records store")

    def _validate(self, body, refs):
        schema = body.get("schema_version")
        if schema not in CEILINGS or body.get("study_id", STUDY_ID) != STUDY_ID:
            raise IntegrityError("unsupported PROS004 typed record")
        self._check_mode(body)
        if schema == "nba-pros004-history-v1":
            from .pros004_inputs import validate_history_body
            validate_history_body(body)
        elif schema == "nba-pros004-event-v1":
            from .pros004_inputs import validate_event_body, validate_input_lanes
            validate_event_body(body)
            history = LedgerRef.from_record(body["history_ref"])
            if refs != (history,):
                raise IntegrityError("event pack must reference exactly its shared history")
            validate_input_lanes(body,self.body(history))
        elif schema == "nba-pros004-date-status-v1":
            fields={"schema_version","study_id","mode","event_date","status","reason","recorded_at","schedule"}
            if set(body)!=fields or body["status"] not in {"VALID_EMPTY","SOURCE_FAILURE"}:
                raise IntegrityError("invalid retained calendar-date state")
            day=datetime.fromisoformat(body["event_date"]).date()
            if day.isoformat()!=body["event_date"] or not datetime(2026,10,21).date()<=day<=datetime(2026,11,10).date():
                raise IntegrityError("calendar-date state lies outside reserved window")
            _text(body["reason"],"calendar-state reason")
            if len(body["reason"])>2048 or _time(body["recorded_at"],"recorded_at")>_now() or refs:
                raise IntegrityError("calendar-state reason/clock/reference budget conflicts")
            if body["status"]=="VALID_EMPTY":
                from .pros004_inputs import validate_schedule
                validate_schedule(body["schedule"])
                if body["schedule"]["study_date"]!=body["event_date"] or body["schedule"]["events"]:
                    raise IntegrityError("valid-empty state needs exact complete empty date evidence")
            elif body["schedule"] is not None:
                raise IntegrityError("source-failure is not complete schedule evidence")
        elif schema == "nba-pros004-forecast-v1":
            from .pros004_producer import validate_forecast_record
            event_ref, history_ref = LedgerRef.from_record(body["event_ref"]), LedgerRef.from_record(body["history_ref"])
            if len(refs) != 3 or refs[:2] != (event_ref,history_ref):
                raise IntegrityError("forecast requires exact event/history/admission references")
            event, history = self.body(event_ref), self.body(history_ref)
            validate_forecast_record(body, event, history)
            claim = self.body(refs[2])
            if claim["schema_version"] != "nba-pros004-event-claim-v1" or claim["event_ref"] != event_ref.to_record() or claim["producer_identity"] != body["producer_binding"]:
                raise IntegrityError("forecast differs from its original admitted producer/input")
        elif schema == "nba-pros004-event-claim-v1":
            fields={"schema_version","study_id","event_id","event_starts_at","event_ref","history_ref",
                    "players","producer_identity","claimed_at","mode","record_basis"}
            if set(body)!=fields:
                raise IntegrityError("invalid event admission fields")
            event_ref = LedgerRef.from_record(body["event_ref"])
            if refs != (event_ref,) or body.get("record_basis") != "INPUT_ADMISSION_NOT_GENERATION_INTENT":
                raise IntegrityError("invalid event admission journal")
            event = self.body(event_ref)
            if (body["history_ref"] != event["history_ref"] or body["players"] != event["selection"]["players"]
                    or any(body[key]!=event['event'][key] for key in ('event_id','event_starts_at'))
                    or body['mode']!=event['mode']):
                raise IntegrityError("event admission differs from immutable cohort/input")
            from .pros004_producer import validate_source_binding
            validate_source_binding(body['producer_identity'])
            claimed=_time(body["claimed_at"],"claimed_at")
            if not utc(self.read(event_ref)["received_at"])<=claimed<=_now():
                raise IntegrityError("event admission clock precedes its retained input or is in future")
        elif schema == "nba-pros004-outcome-v1":
            validate_outcome_body(body)
            if not refs or any(r.kind != "forecasts" for r in refs) or len(refs) > 2:
                raise IntegrityError("one shared outcome links the issued one or two models")
            models = set()
            for ref in refs:
                forecast = self.body(ref)
                if forecast["model_key"] in models:
                    raise IntegrityError("shared outcome duplicates a forecast model")
                models.add(forecast["model_key"])
                for key in ("event_id", "event_version", "event_starts_at", "player_id", "team_id", "opponent_id", "mode"):
                    if body[key] != forecast[key]:
                        raise IntegrityError("shared outcome differs from original forecast identity")
                if utc(forecast["issued_at"]) > utc(body["source_observed_at"]):
                    raise IntegrityError("outcome observation precedes original issuance")
        elif schema == "nba-pros004-grade-v1":
            if len(refs) != 2 or refs[0].kind != "forecasts" or refs[1].kind != "outcomes":
                raise IntegrityError("statistical grade needs exact forecast/shared outcome")
            forecast, outcome = self.body(refs[0]), self.body(refs[1])
            if refs[0].to_record() not in self.read(refs[1])["references"]:
                raise IntegrityError("statistical grade forecast is not linked by its shared outcome")
            expected = self._grade(forecast,outcome,body["graded_at"])
            if body != expected:
                raise IntegrityError("statistical grade conflicts with immutable probabilities/outcome")
        elif schema == "nba-pros004-study-manifest-v1":
            if (set(body)!={"schema_version","study_id","status","recorded_at","capacity"}
                    or _time(body['recorded_at'],'recorded_at')>_now()
                    or body.get("status") != "INACTIVE_READINESS_ONLY" or body.get("capacity") not in
                    (full_study_capacity(),_study_capacity(completion_journal=False)) or refs):
                raise IntegrityError("readiness manifest cannot activate the study")
        elif schema == "nba-pros004-failure-v1":
            fields={"schema_version","study_id","mode","status","reason","recorded_at",
                    "event_ref","subject_id","operation","original_reference"}
            if set(body)!=fields or body.get("status") not in {"SOURCE_FAILURE","PARTIAL","MISSING_PEER","BUDGET_FAILURE","UNACKNOWLEDGED","LATE_COMPLETION"}:
                raise IntegrityError("invalid retained failure/coverage state")
            reason=_text(body["reason"],"failure reason")
            if len(reason)>2048 or _time(body["recorded_at"],"recorded_at")>_now():
                raise IntegrityError("failure reason or observation clock is invalid")
            if body["operation"] not in {"CAPTURE","INPUT_PERSISTENCE","GENERATION","FORECAST_PERSISTENCE","REMOTE_CHECKPOINT","RECOVERY","BUDGET"}:
                raise IntegrityError("unknown operational failure phase")
            event_ref=LedgerRef.from_record(body["event_ref"])
            event=self.body(event_ref)
            if event["schema_version"]!="nba-pros004-event-v1" or event["mode"]!=body["mode"]:
                raise IntegrityError("failure changes the frozen event or evidence lane")
            if body["subject_id"] is not None and body["subject_id"] not in {p["player_id"] for p in event["candidates"]}:
                raise IntegrityError("failure subject is outside the frozen cohort")
            expected=[event_ref]
            if body["original_reference"] is not None:
                original=LedgerRef.from_record(body["original_reference"]);original_body=self.body(original)
                if original_body.get("event_ref")!=event_ref.to_record() or (body["subject_id"] is not None and original_body.get("player_id")!=body["subject_id"]):
                    raise IntegrityError("failure original changes the admitted event/subject")
                expected.append(original)
            if refs!=tuple(expected):
                raise IntegrityError("failure requires exact event/original references")

    def read(self, reference):
        payload = self.ledger.read(reference)
        body = payload["data"].get("pros004")
        if body is None:
            raise IntegrityError("reference is not a typed PROS004 record")
        if set(payload["data"]) != {"identity","pros004"} or payload["data"]["identity"] != _identity(body):
            raise IntegrityError("PROS004 envelope subject differs from its typed body")
        if payload["kind"] != SCHEMA_KINDS.get(body.get("schema_version")):
            raise IntegrityError("PROS004 record is stored under the wrong kind")
        if payload["logical_id"] != _logical(body):
            raise IntegrityError("PROS004 logical identity is inconsistent")
        if self.ledger._path(reference.kind,reference.record_id).stat().st_size > CEILINGS[body["schema_version"]]:
            raise IntegrityError("PROS004 record exceeds its individual encoded-envelope ceiling")
        self._validate_receipt_clocks(payload,body)
        for item in payload["references"]:
            parent=self.ledger.read(LedgerRef.from_record(item))
            if utc(parent["received_at"])>utc(payload["received_at"]):
                raise IntegrityError("PROS004 reference receipt occurs after its child receipt")
        if reference in self._validating:
            raise IntegrityError("cyclic PROS004 reference graph")
        if reference not in self._validated:
            self._validating.add(reference)
            try:
                self._validate(body,tuple(LedgerRef.from_record(x) for x in payload["references"]))
                self._validated.add(reference)
            finally:
                self._validating.remove(reference)
        return payload

    @staticmethod
    def _validate_receipt_clocks(payload,body):
        received=utc(payload["received_at"])
        schema=body["schema_version"]
        if schema=="nba-pros004-event-v1":
            close=utc(body["event"]["event_starts_at"])-timedelta(minutes=100)
            if not utc(body["imported_at"])<=received<=close:
                raise IntegrityError("event input was not immutably persisted before selection closed")
        elif schema=="nba-pros004-forecast-v1":
            cutoff=utc(body["cutoff_at"])
            if not cutoff<=utc(body["issued_at"])<=received<=cutoff+timedelta(minutes=5):
                raise IntegrityError("forecast receipt clock violates actual T90 window")
            if (received-utc(body["generation_started_at"])).total_seconds()>120:
                raise IntegrityError("forecast receipt exceeds permitted generation/persistence latency")
        elif schema=="nba-pros004-outcome-v1" and utc(body["normalized_at"])>received:
            raise IntegrityError("outcome normalization occurs after its receipt")
        elif schema=="nba-pros004-grade-v1" and utc(body["graded_at"])>received:
            raise IntegrityError("statistical grading occurs after its receipt")
        elif schema=="nba-pros004-history-v1" and utc(body["imported_at"])>received:
            raise IntegrityError("history import occurs after its receipt")
        elif schema=="nba-pros004-event-claim-v1" and utc(body["claimed_at"])>received:
            raise IntegrityError("event admission observation occurs after its receipt")
        elif schema in {"nba-pros004-date-status-v1","nba-pros004-study-manifest-v1"} and utc(body["recorded_at"])>received:
            raise IntegrityError("operational metadata observation occurs after its receipt")
        elif schema=="nba-pros004-failure-v1" and utc(body["recorded_at"])>received:
            raise IntegrityError("operational failure observation occurs after its receipt")

    def body(self, reference):
        return self.read(reference)["data"]["pros004"]

    def _inventory(self):
        index = self.ledger.scan()
        typed = []
        for kind,records in index.items():
            for payload in records.values():
                if "pros004" in payload["data"]:
                    ref = LedgerRef(kind,payload["record_id"],digest(payload))
                    self.read(ref)
                    typed.append((ref,payload))
        return index,typed

    def capacity_report(self):
        plan = full_study_capacity()
        index,typed = self._inventory()
        journal=completion.journal_inventory(self.root)
        all_count = sum(len(values) for values in index.values())+journal["files"]
        actual = sum(path.stat().st_size for kind in KINDS for path in (self.root/"records"/kind).glob("*.json"))+journal["bytes"]
        if all_count>MAX_LEDGER_RECORDS or actual>MAX_LEDGER_BYTES:
            raise IntegrityError("ledger plus completion journal exceeds unchanged shared limits")
        def is_study_correction(payload):
            if payload["kind"]!="corrections":return False
            original=LedgerRef.from_record(payload["supersedes"])
            target=index[original.kind].get(original.record_id)
            return target is not None and "pros004" in target["data"]
        study_corrections=[p for p in index["corrections"].values() if is_study_correction(p)]
        external = [(kind,p) for kind,values in index.items() for p in values.values()
                    if "pros004" not in p["data"] and not is_study_correction(p)]
        external_bytes = sum(self.ledger._path(kind,p["record_id"]).stat().st_size for kind,p in external)
        if len(external) > 32 or external_bytes > 4*1024*1024:
            raise IntegrityError("existing/pilot records exceed PROS004 reserved allowance")
        counts = {schema:0 for schema in CEILINGS}
        maxima = {schema:0 for schema in CEILINGS}
        for ref,payload in typed:
            schema = payload["data"]["pros004"]["schema_version"]
            counts[schema] += 1
            maxima[schema] = max(maxima[schema],self.ledger._path(ref.kind,ref.record_id).stat().st_size)
        limits = {"nba-pros004-history-v1":1,"nba-pros004-event-v1":21,
                  "nba-pros004-forecast-v1":168,"nba-pros004-outcome-v1":84,
                  "nba-pros004-grade-v1":168,"nba-pros004-event-claim-v1":21,
                  "nba-pros004-study-manifest-v1":1}
        counts["nba-pros004-event-v1"]+=counts["nba-pros004-date-status-v1"]
        # Revisions and correction links consume the13-record residual reserve;
        # they never steal slots from unissued registered subjects.
        subject_keys={schema:[] for schema in ("nba-pros004-outcome-v1","nba-pros004-grade-v1")}
        for ref,payload in typed:
            schema=payload["data"]["pros004"]["schema_version"]
            if schema in subject_keys:
                subject_keys[schema].append(digest(payload["data"]["identity"]))
        revisions={schema:len(keys)-len(set(keys)) for schema,keys in subject_keys.items()}
        overages=sum(max(0,counts[schema]-limit,revisions.get(schema,0)) for schema,limit in limits.items())
        extras = counts["nba-pros004-failure-v1"]+len(study_corrections)+overages
        if extras > RESERVE_RECORDS:
            raise IntegrityError("correction/failure metadata exhausts the full-study reserve")
        return {**plan,"actual_records":all_count,"actual_bytes":actual,
                "completion_journal":journal,
                "existing_or_pilot_records":len(external),"existing_or_pilot_bytes":external_bytes,
                "pros004_schema_counts":counts,"maximum_measured_envelope_bytes":maxima,
                "used_correction_failure_reserve":extras,
                "original_subject_identity_sha256":{schema:sorted(set(keys)) for schema,keys in subject_keys.items()}}

    def _append(self, body, *, references=()):
        self._check_mode(body,writing=True)
        kind = SCHEMA_KINDS.get(body.get("schema_version"))
        if kind is None:
            raise IntegrityError("unsupported PROS004 record kind")
        logical = _logical(body)
        refs = tuple(references)
        self._validate(body,refs)
        data = {"identity":_identity(body),"pros004":body}
        size = encoded_envelope_size(kind,logical,data,references=refs)
        if size > CEILINGS[body["schema_version"]]:
            raise IntegrityError("PROS004 record exceeds individual encoded-envelope ceiling")
        existing = self.ledger._existing(kind,logical)
        if existing is not None:
            current = self.read(existing)
            if current["data"] != data or current["references"] != [r.to_record() for r in refs]:
                raise IntegrityError("existing PROS004 cycle uses different inputs/producer/content")
            return existing
        report = self.capacity_report()
        schema = body["schema_version"]
        counts = report["pros004_schema_counts"]
        capacity_schema="nba-pros004-event-v1" if schema=="nba-pros004-date-status-v1" else schema
        limit = {"nba-pros004-history-v1":1,"nba-pros004-event-v1":21,
                 "nba-pros004-forecast-v1":168,"nba-pros004-outcome-v1":84,
                 "nba-pros004-grade-v1":168,"nba-pros004-event-claim-v1":21,
                 "nba-pros004-study-manifest-v1":1}.get(capacity_schema,0)
        new_reserve = int(limit == 0 or counts.get(capacity_schema,0) >= limit
            or digest(data["identity"]) in report["original_subject_identity_sha256"].get(schema,[]))
        if report["used_correction_failure_reserve"]+new_reserve > RESERVE_RECORDS:
            raise IntegrityError("append would consume reserved capacity for the complete comparison")
        if report["actual_records"]+1+int(report["completion_journal"]["files"]==0)>MAX_LEDGER_RECORDS:
            raise IntegrityError("original plus completion journal would exceed shared record limit")
        self._validate_receipt_clocks({"received_at":stamp(_now())},body)
        reference = self.ledger.append(kind,logical,data,references=refs)
        self.read(reference)
        raw_sha=self._raw_sha256(reference)
        completed=_now()  # AFTER actual write/fsync and verified original readback.
        completion.append_completion(self.root,reference,mode=body.get("mode","READINESS_DIAGNOSTIC"),
            raw_sha256=raw_sha,completed_at=completed,recorded_at=_now())
        return reference

    def store_history(self, body):
        return self._append(body)

    def _raw_sha256(self,reference):
        path=self.ledger._path(reference.kind,reference.record_id)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def admission_status(self,reference):
        """Read original completion evidence without issuing, repairing or fitting.

        received_at is an immutable pre-write clock. Only separately retained
        post-operation observations can establish local/remote completion.
        """
        payload=self.read(reference);body=payload["data"]["pros004"]
        entries=completion.load_journal(self.root)
        observed=[entry for entry in entries if entry["reference"]==reference.to_record()]
        raw_sha=self._raw_sha256(reference);reasons=[]
        for entry in observed:
            if entry["record_raw_sha256"]!=raw_sha or entry["mode"]!=body.get("mode","READINESS_DIAGNOSTIC"):
                raise IntegrityError("completion evidence changes original bytes or evidence lane")
            if utc(entry["recorded_at"])>_now():
                raise IntegrityError("completion evidence observation clock is in the future")
        local=next((entry for entry in observed if entry["kind"]=="LOCAL_PERSISTENCE_COMPLETED"),None)
        remote=next((entry for entry in observed if entry["kind"]=="REMOTE_CHECKPOINT_COMPLETED"),None)
        local_clock=utc(local["completed_at"]) if local else None
        remote_clock=utc(remote["completed_at"]) if remote else None
        schema=body["schema_version"];deadline=None;start=None
        if schema=="nba-pros004-event-v1":
            deadline=utc(body["event"]["event_starts_at"])-timedelta(minutes=100)
            start=utc(body["imported_at"])
        elif schema=="nba-pros004-forecast-v1":
            deadline=utc(body["cutoff_at"])+timedelta(minutes=5)
            start=utc(body["generation_started_at"])
        elif schema=="nba-pros004-event-claim-v1":
            deadline=utc(body["event_starts_at"])-timedelta(minutes=85)
            start=utc(body["claimed_at"])
        local_timely=bool(local_clock is not None and utc(payload["received_at"])<=local_clock
            and (start is None or start<=local_clock) and (deadline is None or local_clock<=deadline))
        if schema=="nba-pros004-forecast-v1" and local_clock is not None:
            local_timely=local_timely and (local_clock-start).total_seconds()<=120
        remote_timely=bool(local_timely and remote_clock is not None and local_clock<=utc(remote["operation_started_at"])<=remote_clock
            and (deadline is None or remote_clock<=deadline))
        if schema=="nba-pros004-forecast-v1" and remote_clock is not None:
            remote_timely=remote_timely and (remote_clock-start).total_seconds()<=120
        if local is None:reasons.append("LOCAL_COMPLETION_UNOBSERVED")
        elif not local_timely:reasons.append("LOCAL_COMPLETION_LATE_OR_INVALID")
        if remote is None:reasons.append("REMOTE_CHECKPOINT_UNACKNOWLEDGED")
        elif not remote_timely:reasons.append("REMOTE_COMPLETION_LATE_OR_INVALID")
        input_status=None
        timing_complete=bool(local_timely and remote_timely)
        if schema=="nba-pros004-forecast-v1":
            input_status=self.admission_status(LedgerRef.from_record(body["event_ref"]))
            if not input_status["timing_complete"]:
                reasons.append("EVENT_INPUT_COMPLETION_NOT_ADMITTED")
            timing_complete=timing_complete and input_status["timing_complete"]
            if body["producer_version"].endswith("-v1"):
                reasons.append("LEGACY_PRODUCER_WITHOUT_COMPLETION_POLICY")
                timing_complete=False
        eligible=False
        if body.get("mode")!="REAL_TIME_CAPTURED":reasons.append("DIAGNOSTIC_NON_ISSUANCE")
        elif timing_complete:
            # The reviewed activation path remains separately disabled. A caller
            # flag or a completion journal cannot activate this reservation.
            from .pros004_producer import validate_activation_binding
            try:
                validate_activation_binding(self.activation,producer_binding=body.get("producer_binding",{}),
                    event_body=self.body(LedgerRef.from_record(body["event_ref"])) if schema=="nba-pros004-forecast-v1" else body)
            except IntegrityError:
                reasons.append("STUDY_NOT_ACTIVATED")
            else:eligible=True
        return {"schema_version":"nba-pros004-admission-status-v2","reference":reference.to_record(),
            "retained":True,"received_at_prewrite":payload["received_at"],
            "generation_completed_at":body.get("generation_completed_at"),"verified_at":body.get("verified_at"),
            "local_persistence_completed_at":local["completed_at"] if local else None,
            "remote_checkpoint_completed_at":remote["completed_at"] if remote else None,
            "local_timely":bool(local_timely),"remote_timely":bool(remote_timely),
            "timing_complete":bool(timing_complete),"eligible_for_comparison":bool(eligible),
            "status":"ELIGIBLE_RESEARCH_ONLY" if eligible else "RETAINED_UNADMITTED",
            "metadata_publication_status":"NOT_ESTABLISHED_BY_LOCAL_JOURNAL",
            "reasons":reasons,"event_input_status":input_status,"qualification":"UNAVAILABLE"}

    def complete_checkpoint(self,reference,checkpoint):
        """Observe structured remote readback completion after the actual call."""
        status=self.admission_status(reference)
        if status["remote_checkpoint_completed_at"] is not None:
            if not status["remote_timely"]:
                raise IntegrityError("retained remote checkpoint completed late; original remains unadmitted")
            return status
        if not status["local_timely"]:
            raise IntegrityError("original lacks timely local persistence completion; retain it unadmitted")
        from .pros004_snapshot import snapshot_manifest
        expected_snapshot=digest(snapshot_manifest(self.root))
        started=_now()
        acknowledgment=checkpoint(reference)
        # The callback must publish the actual current prefix, and cannot mutate
        # the original retained state while claiming an unrelated snapshot.
        if digest(snapshot_manifest(self.root))!=expected_snapshot:
            raise IntegrityError("checkpoint mutated the retained local snapshot")
        completed=_now()  # callback and local verification have completed.
        raw_sha=self._raw_sha256(reference)
        completion.validate_acknowledgment(acknowledgment,reference,started_at=stamp(started),
            completed_at=stamp(completed),raw_sha256=raw_sha)
        if acknowledgment["snapshot_sha256"]!=expected_snapshot:
            raise IntegrityError("checkpoint acknowledgment differs from the exact retained snapshot prefix")
        body=self.body(reference)
        completion.append_completion(self.root,reference,mode=body.get("mode","READINESS_DIAGNOSTIC"),
            raw_sha256=raw_sha,completed_at=completed,recorded_at=_now(),started_at=started,acknowledgment=acknowledgment)
        status=self.admission_status(reference)
        if not status["remote_timely"]:
            raise IntegrityError("remote checkpoint completed late; immutable original retained unadmitted")
        return status

    def finalize_checkpoint(self,references,checkpoint):
        """Publish the final original-acknowledgment prefix without recursion.

        Original remote observations remain unchanged. This operation copies
        their already-retained journal evidence; it creates no renewed issuance
        clock or new journal acknowledgment. A fresh remote snapshot contains
        the full prefix, which can independently be recovered. Publication must
        finish by selection close for inputs or T90+5 for forecast cohorts.
        The original per-forecast 120-second limit remains on each original ACK.
        """
        refs=tuple(references)
        if not refs or len(set(refs))!=len(refs):
            raise IntegrityError("final evidence publication needs unique original references")
        statuses=[self.admission_status(reference) for reference in refs]
        if not all(status["timing_complete"] for status in statuses):
            raise IntegrityError("cannot finalize evidence for unacknowledged or late originals")
        from .pros004_snapshot import snapshot_manifest
        expected=digest(snapshot_manifest(self.root))
        prefix=completion.journal_inventory(self.root)["raw_sha256"]
        started=_now();acknowledgment=checkpoint(refs[-1])
        if digest(snapshot_manifest(self.root))!=expected:
            raise IntegrityError("final checkpoint mutated the retained local snapshot")
        completed=_now()
        completion.validate_acknowledgment(acknowledgment,refs[-1],started_at=stamp(started),
            completed_at=stamp(completed),raw_sha256=self._raw_sha256(refs[-1]))
        if acknowledgment["snapshot_sha256"]!=expected:
            raise IntegrityError("final checkpoint differs from the exact completion-journal prefix")
        deadlines=[]
        for reference in refs:
            body=self.body(reference);schema=body["schema_version"]
            if schema=="nba-pros004-event-v1":
                deadlines.append(utc(body["event"]["event_starts_at"])-timedelta(minutes=100))
            elif schema=="nba-pros004-forecast-v1":
                deadlines.append(utc(body["cutoff_at"])+timedelta(minutes=5))
            else:
                raise IntegrityError("final publication supports only event inputs and original forecasts")
        timely=all(completed<=deadline for deadline in deadlines)
        return {"schema_version":"nba-pros004-final-checkpoint-v1",
            "references":[reference.to_record() for reference in refs],
            "operation_started_at":stamp(started),"completed_at":stamp(completed),
            "snapshot_sha256":expected,"journal_raw_sha256":prefix,
            "acknowledgment":acknowledgment,"timely":timely,
            "metadata_publication_status":"INDEPENDENTLY_RECOVERED_CURRENT_PREFIX" if timely else "LATE_METADATA_PUBLICATION",
            "original_acknowledgments_unchanged":True,"qualification":"UNAVAILABLE"}

    def validate_input_checkpoint(self,event_ref,report):
        """Validate the original phase receipt before any missing generation.

        The receipt is not a caller permission flag: its exact input, retained
        journal prefix, immutable record subset, snapshot and operation clocks
        must agree. A caller must independently recover the original receipt on
        restart. This readiness package does not install that future operating
        state retention; absent or ambiguous evidence fails closed.
        """
        fields={"schema_version","references","operation_started_at","completed_at",
            "snapshot_sha256","journal_raw_sha256","acknowledgment","timely",
            "metadata_publication_status","original_acknowledgments_unchanged","qualification"}
        if type(report) is not dict or set(report)!=fields or report["schema_version"]!="nba-pros004-final-checkpoint-v1":
            raise IntegrityError("input phase needs its exact typed final checkpoint receipt")
        event=self.body(event_ref)
        if event["schema_version"]!="nba-pros004-event-v1" or report["references"]!=[event_ref.to_record()]:
            raise IntegrityError("input final checkpoint changes the original event/input identity")
        started=_time(report["operation_started_at"],"input checkpoint start")
        completed=_time(report["completed_at"],"input checkpoint completion")
        close=utc(event["event"]["event_starts_at"])-timedelta(minutes=100)
        if not started<=completed<=min(close,_now()) or report["timely"] is not True:
            raise IntegrityError("input final checkpoint did not complete before selection closed")
        if (report["metadata_publication_status"]!="INDEPENDENTLY_RECOVERED_CURRENT_PREFIX"
                or report["original_acknowledgments_unchanged"] is not True or report["qualification"]!="UNAVAILABLE"):
            raise IntegrityError("input final checkpoint cannot change original admission meaning")
        _hash(report["snapshot_sha256"],"input checkpoint snapshot")
        _hash(report["journal_raw_sha256"],"input checkpoint journal prefix")
        completion.validate_acknowledgment(report["acknowledgment"],event_ref,
            started_at=report["operation_started_at"],completed_at=report["completed_at"],
            raw_sha256=self._raw_sha256(event_ref))
        if report["acknowledgment"]["snapshot_sha256"]!=report["snapshot_sha256"]:
            raise IntegrityError("input checkpoint snapshot contradicts its actual acknowledgment")
        journal=completion.load_journal(self.root)
        prefix=bytearray();prefix_entries=[];matched=False
        for entry in journal:
            prefix.extend(canonical(entry)+b"\n");prefix_entries.append(entry)
            if hashlib.sha256(prefix).hexdigest()==report["journal_raw_sha256"]:
                matched=True;break
        if not matched or any(utc(entry["recorded_at"])>started for entry in prefix_entries):
            raise IntegrityError("input checkpoint journal is not its exact previously retained prefix")
        observed={entry["kind"] for entry in prefix_entries if entry["reference"]==event_ref.to_record()}
        if observed!={"LOCAL_PERSISTENCE_COMPLETED","REMOTE_CHECKPOINT_COMPLETED"}:
            raise IntegrityError("input checkpoint prefix lacks original local/remote completion evidence")
        if not self.admission_status(event_ref)["timing_complete"]:
            raise IntegrityError("input checkpoint original local/remote completion is unadmitted")
        # Reconstruct exactly the snapshot that existed when this operation
        # began. A later receipt with a tied clock is deliberately included;
        # if that makes the original hash ambiguous, reject instead of guessing.
        from .pros004_snapshot import snapshot_manifest
        full=snapshot_manifest(self.root);entries=[];ledger_count=0
        for entry in full["entries"]:
            if entry["entry_type"]=="COMPLETION_JOURNAL":
                entries.append({**entry,"encoded_bytes":len(prefix),
                    "raw_sha256":report["journal_raw_sha256"],"payload_sha256":digest(prefix_entries)})
                continue
            path=Path(entry["path"]);kind=path.parts[1];record_id=path.stem
            payload=self.ledger.read(LedgerRef(kind,record_id,entry["payload_sha256"]))
            if utc(payload["received_at"])<=started:
                entries.append(entry);ledger_count+=1
        body={key:value for key,value in full.items() if key!="manifest_id"}
        body.update(entries=entries,record_count=len(entries),ledger_record_count=ledger_count,
            encoded_bytes=sum(entry["encoded_bytes"] for entry in entries))
        expected={**body,"manifest_id":digest(body)}
        if digest(expected)!=report["snapshot_sha256"]:
            raise IntegrityError("input checkpoint exact record subset/prefix cannot be recovered unambiguously")
        return report

    def store_event(self, body, history_ref):
        ref=self._append(body,references=(history_ref,))
        if not self.admission_status(ref)["local_timely"]:
            raise IntegrityError("event input local persistence did not complete before selection closed; original retained unadmitted")
        return ref

    def store_failure(self,event_ref,*,status,reason,operation,subject_id=None,original_reference=None):
        event=self.body(event_ref)
        refs=(event_ref,)+( (original_reference,) if original_reference is not None else () )
        return self._append({"schema_version":"nba-pros004-failure-v1","study_id":STUDY_ID,
            "mode":event["mode"],"status":status,"reason":reason,"operation":operation,
            "recorded_at":stamp(_now()),"event_ref":event_ref.to_record(),"subject_id":subject_id,
            "original_reference":original_reference.to_record() if original_reference else None},references=refs)

    def store_date_status(self,event_date,*,status,reason,schedule=None,mode="READINESS_DIAGNOSTIC"):
        return self._append({"schema_version":"nba-pros004-date-status-v1","study_id":STUDY_ID,
            "mode":mode,"event_date":event_date,"status":status,"reason":reason,
            "recorded_at":stamp(_now()),"schedule":schedule})

    def store_manifest(self, *, recorded_at=None):
        return self._append({"schema_version":"nba-pros004-study-manifest-v1", "study_id":STUDY_ID,
            "status":"INACTIVE_READINESS_ONLY","recorded_at":recorded_at or stamp(_now()),
            "capacity":full_study_capacity()})

    def claim_event(self,event_ref,producer_identity):
        event = self.body(event_ref)
        body = {"schema_version":"nba-pros004-event-claim-v1","study_id":STUDY_ID,
                "event_id":event["event"]["event_id"],"event_starts_at":event["event"]["event_starts_at"],
                "event_ref":event_ref.to_record(),"history_ref":event["history_ref"],
                "players":event["selection"]["players"],"producer_identity":producer_identity,
                "claimed_at":stamp(_now()),"mode":event["mode"],
                "record_basis":"INPUT_ADMISSION_NOT_GENERATION_INTENT"}
        existing = self.ledger._existing("input_captures",_logical(body))
        if existing is not None:
            original = self.body(existing)
            if {k:v for k,v in original.items() if k != "claimed_at"} != {k:v for k,v in body.items() if k != "claimed_at"}:
                raise IntegrityError("event already admitted under different input/cohort/producer")
            return existing,False
        return self._append(body,references=(event_ref,)),True

    def lookup_forecast(self,event_ref,player_id,model):
        event = self.body(event_ref)
        if model not in MODEL_KEYS:
            raise IntegrityError("unregistered PROS004 peer model")
        event_facts = event["event"]
        cutoff = stamp(utc(event_facts["event_starts_at"])-timedelta(minutes=90))
        body = {"schema_version":"nba-pros004-forecast-v1",**event_facts,
                "player_id":player_id,"model_key":model,"cutoff_at":cutoff}
        ref = self.ledger._existing("forecasts",_logical(body))
        if ref is not None and self.body(ref)["event_ref"] != event_ref.to_record():
            raise IntegrityError("existing original forecast is bound to another input")
        return ref

    def recover_event(self,event_ref,producer_identity):
        self.reject_ambiguous_temporary_records()
        self._inventory()
        event = self.body(event_ref)
        facts=event["event"]
        claim_body={"schema_version":"nba-pros004-event-claim-v1",**facts}
        claim_ref=self.ledger._existing("input_captures",_logical(claim_body))
        if claim_ref is not None:
            claim=self.body(claim_ref)
            if claim["event_ref"] != event_ref.to_record() or claim["producer_identity"] != producer_identity:
                raise IntegrityError("recovery cannot change producer revision or admitted inputs")
        subjects=[]
        for player in event["selection"]["players"]:
            peers={model:self.lookup_forecast(event_ref,player["player_id"],model) for model in MODEL_KEYS}
            admission={model:self.admission_status(ref) if ref else None for model,ref in peers.items()}
            subjects.append({"player_id":player["player_id"],
                "forecasts":{m:r.to_record() if r else None for m,r in peers.items()},
                "missing_models":[m for m,r in peers.items() if r is None],"admission":admission})
        retained=sum(r is not None for subject in subjects for r in subject["forecasts"].values())
        statuses=[status for subject in subjects for status in subject["admission"].values() if status is not None]
        issued=sum(status["eligible_for_comparison"] for status in statuses)
        local=sum(status["local_timely"] for status in statuses)
        remote=sum(status["remote_timely"] for status in statuses)
        timing=sum(status["timing_complete"] for status in statuses)
        return {"schema_version":"nba-pros004-recovery-v1","event_ref":event_ref.to_record(),
            "claim_ref":claim_ref.to_record() if claim_ref else None,
            "subjects":subjects,"issued_models":issued,"eligible_models":issued,"retained_models":retained,
            "local_timely_models":local,"remote_timely_models":remote,"timing_complete_models":timing,
            "status":"COMPLETE" if issued==8 else "RETAINED_UNADMITTED" if retained and not issued else "PARTIAL_MISSING_PEERS" if issued else "NOT_ISSUED",
            "metadata_publication_status":"NOT_ESTABLISHED_BY_LOCAL_JOURNAL",
            "recovered_at":stamp(_now()),"original_content_and_clocks_preserved":True,
            "financial_settlement":"NOT_EVALUATED","qualification":"UNAVAILABLE"}

    def reject_ambiguous_temporary_records(self):
        for kind in KINDS:
            if any((self.root/"records"/kind).glob(".receipt-*")):
                raise IntegrityError("interrupted unpublished receipt is ambiguous; recover exact bytes before retry")

    def persist_forecast(self,body,event_ref,history_ref,intent_ref):
        existing=self.lookup_forecast(event_ref,body["player_id"],body["model_key"])
        if existing is not None:
            if self.body(existing)!=body:
                raise IntegrityError("original forecast exists; recover it without new generation")
            return existing
        self.reject_ambiguous_temporary_records()
        event=self.body(event_ref)
        if body["mode"]=="REAL_TIME_CAPTURED":
            if self.activation is None:
                raise IntegrityError("PROS004 remains inactive; reviewed remote activation evidence is required")
            from .pros004_producer import validate_activation_binding
            validate_activation_binding(self.activation,producer_binding=body["producer_binding"],event_body=event)
        now=_now();cutoff=utc(body["cutoff_at"])
        if not cutoff<=now<=cutoff+timedelta(minutes=5):
            raise IntegrityError("new forecast receipt is outside actual T90 issuance window")
        if not utc(body["issued_at"])<=now or (now-utc(body["generation_started_at"])).total_seconds()>120:
            raise IntegrityError("forecast receipt exceeds original generation latency")
        if body["event_ref"]!=event_ref.to_record() or body["history_ref"]!=history_ref.to_record():
            raise IntegrityError("forecast input references disagree")
        ref=self._append(body,references=(event_ref,history_ref,intent_ref))
        if not self.admission_status(ref)["local_timely"]:
            raise IntegrityError("forecast local persistence completed late; immutable original retained unadmitted")
        return ref

    def append_outcome(self,body,forecast_refs,*,correction_reason=None):
        validate_outcome_body(body)
        refs=tuple(sorted(forecast_refs,key=lambda r:self.body(r)["model_key"]))
        self._validate(body,refs)
        first=self.body(refs[0]);event_ref=LedgerRef.from_record(first["event_ref"])
        expected={ref for model in MODEL_KEYS if (ref:=self.lookup_forecast(event_ref,body["player_id"],model)) is not None}
        if set(refs)!=expected:
            raise IntegrityError("shared outcome must link every actually issued peer, preserving missing peers")
        index,_=self._inventory();superseded=self.ledger._correction_map(index)
        matching,differing=[],[]
        semantics=lambda b:(b['status'],b['primitives'],b['minutes'],b['minutes_precision'])
        for payload in index["outcomes"].values():
            old_body=payload["data"].get("pros004")
            if old_body is None or _identity(old_body)!=_identity(body):continue
            ref=LedgerRef("outcomes",payload["record_id"],digest(payload))
            if ref not in superseded:
                (matching if semantics(old_body)==semantics(body) else differing).append(ref)
        if len(matching)>1 or len(differing)>1:
            raise IntegrityError("ambiguous active shared outcomes")
        if differing and not correction_reason:
            raise IntegrityError("changed shared outcome requires a traceable correction reason")
        if differing:
            # Reserve every remaining revision/link before beginning a complete
            # paired correction. Crash recovery may find the replacement body
            # already written; count only its still-missing records. This is a
            # budget check, not a claim of atomic multi-record publication.
            existing_replacement=matching[0] if matching else None
            required=int(existing_replacement is None)+1
            active_grades=[p for p in index['grades'].values()
                if LedgerRef('grades',p['record_id'],digest(p)) not in superseded]
            for forecast in refs:
                prior=[p for p in active_grades if p['references'][0]==forecast.to_record()]
                if prior:
                    new_grade=any(p['references'][1]==existing_replacement.to_record()
                        for p in prior) if existing_replacement else False
                    # Existing older grades need one new revision and link;
                    # an already-written new grade only needs its missing link.
                    old_grade=any(p['references'][1]!=existing_replacement.to_record()
                        for p in prior) if existing_replacement else True
                    required+=int(not new_grade)+int(old_grade)
            report=self.capacity_report()
            if report['used_correction_failure_reserve']+required>RESERVE_RECORDS:
                raise IntegrityError("paired correction would consume reserved capacity for the complete comparison")
        ref=matching[0] if matching else self._append(body,references=refs)
        if differing:self.correct(differing[0],ref,reason=correction_reason)
        return ref

    def correct(self,original,replacement,*,reason):
        if type(reason) is not str or not reason.strip() or len(reason)>2048:
            raise IntegrityError("correction reason needs bounded explicit text")
        old,new=self.read(original),self.read(replacement)
        if original.kind not in {"outcomes","grades"}:
            raise IntegrityError("original forecast probabilities and issuance clocks cannot be corrected/replaced")
        if old["data"]["identity"]!=new["data"]["identity"]:
            raise IntegrityError("correction changes the subject/model identity")
        oldbody,newbody=old['data']['pros004'],new['data']['pros004']
        protected=('event_id','event_version','event_starts_at','player_id','team_id','opponent_id','mode')
        if any(oldbody[key]!=newbody[key] for key in protected) or (
                original.kind=='grades' and oldbody['forecast_id']!=newbody['forecast_id']):
            raise IntegrityError("correction changes the original event/player/forecast identity")
        report=self.capacity_report()
        existing=self.ledger._existing("corrections",f"supersedes:{original.kind}:{original.record_id}")
        if existing is None and report["used_correction_failure_reserve"]>=RESERVE_RECORDS:
            raise IntegrityError("correction/failure reserve exhausted")
        correction_logical=f"supersedes:{original.kind}:{original.record_id}"
        correction_data={"reason":reason,"replacement":replacement.to_record()}
        size=encoded_envelope_size("corrections",correction_logical,correction_data,references=(original,replacement))
        if size>8*1024:
            raise IntegrityError("correction link exceeds declared metadata envelope ceiling")
        return self.ledger.correct(original,replacement,reason=reason)

    @staticmethod
    def _grade(forecast,outcome,graded_at):
        validate_outcome_body(outcome)
        if any(forecast[k]!=outcome[k] for k in ('event_id','event_version','event_starts_at','player_id','team_id','opponent_id','mode')):
            raise IntegrityError("statistical grade forecast/outcome identity mismatch")
        if utc(graded_at)<max(utc(forecast['issued_at']),utc(outcome['source_observed_at'])) or utc(graded_at)>_now():
            raise IntegrityError("statistical grade clock precedes evidence or is in future")
        status='SCORED' if outcome['status']=='APPEARED' else 'DNP_NOT_SCORED' if outcome['status']=='DNP' else outcome['status']
        body={'schema_version':'nba-pros004-grade-v1','study_id':STUDY_ID,'mode':forecast['mode'],
            'event_id':forecast['event_id'],'event_version':forecast['event_version'],
            'event_starts_at':forecast['event_starts_at'],'player_id':forecast['player_id'],
            'team_id':forecast['team_id'],'opponent_id':forecast['opponent_id'],
            'model_key':forecast['model_key'],'forecast_id':forecast['forecast_id'],
            'outcome_id':outcome['outcome_id'],'graded_at':graded_at,'status':status,
            'categories':_score_categories(forecast,outcome) if status=='SCORED' else [],
            'reported_minutes':_score_reported_minutes(forecast,outcome) if status=='SCORED' else None,
            'financial_settlement':'NOT_EVALUATED','qualification':'UNAVAILABLE'}
        return {'grade_id':digest(body),**body}

    def grade_forecast(self,forecast_ref,outcome_ref):
        forecast,outcome=self.body(forecast_ref),self.body(outcome_ref)
        index,_=self._inventory()
        found=[]
        for payload in index['grades'].values():
            if payload['references']==[forecast_ref.to_record(),outcome_ref.to_record()]:
                found.append(LedgerRef('grades',payload['record_id'],digest(payload)))
        if len(found)>1:raise IntegrityError("duplicate original statistical grades")
        if found:
            ref=found[0];self.read(ref)
        else:
            body=self._grade(forecast,outcome,stamp(_now()))
            ref=self._append(body,references=(forecast_ref,outcome_ref))
        mapping=self.ledger._correction_map(index)
        # Also finish a correction link after an interrupted already-written new
        # grade. An idempotent retry must not return before this reconciliation.
        for payload in index['grades'].values():
            oldbody=payload['data'].get('pros004')
            oldref=LedgerRef('grades',payload['record_id'],digest(payload))
            if oldref==ref or oldref in mapping or oldbody is None or _identity(oldbody)!=_identity(self.body(ref)):
                continue
            oldrefs=[LedgerRef.from_record(x) for x in payload['references']]
            if len(oldrefs)==2 and oldrefs[0]==forecast_ref and oldrefs[1]!=outcome_ref and self.ledger.latest(oldrefs[1])==outcome_ref:
                self.correct(oldref,ref,reason='Statistical regrade after traceable shared outcome correction')
        return ref

    def require_evaluation_window(self):
        if _now()<EVALUATION_NOT_BEFORE:
            raise IntegrityError("reserved comparative aggregate evaluation is unavailable before 2026-11-25T00:00:00Z")
        return {'evaluation_not_before':stamp(EVALUATION_NOT_BEFORE),'status':'TIME_GATE_ONLY_NOT_SCORING_AUTHORIZATION'}


def outcome_from_normalized(row,*,event_version,mode,source_raw_sha256,source_observed_at,
                            normalized_at,source_updated_at=None):
    """Use an already verified offline primary normalizer result; never capture."""
    if row.final_status!='FINAL' or row.participation not in {'APPEARED','DNP'}:
        raise IntegrityError('verified shared final outcome requires explicit FINAL and appearance/DNP')
    appeared=row.participation=='APPEARED'
    primitives=None
    if appeared:
        primitives={'FGM':row.fgm,'FG2M':row.fg2m,'FG3M':row.fg3m,'FTM':row.ftm,
                    'PTS':row.points,'REB':row.rebounds,'AST':row.assists,'TOV':row.turnovers,
                    'BLK':row.blocks,'STL':row.steals}
    body={'schema_version':'nba-pros004-outcome-v1','study_id':STUDY_ID,'mode':mode,
        'event_id':row.event_id,'event_version':event_version,'event_starts_at':stamp(row.event_start),
        'player_id':row.player_id,'team_id':row.team_id,'opponent_id':row.opponent_id,
        'status':'APPEARED' if appeared else 'DNP','source_observed_at':stamp(utc(source_observed_at)),
        'source_updated_at':stamp(utc(source_updated_at)) if source_updated_at is not None else None,
        'normalized_at':stamp(utc(normalized_at)),'source_raw_sha256':source_raw_sha256,
        'normalizer_version':'espn-nba-selected-outcomes-v1','primitives':primitives,
        'minutes':row.minutes if appeared else None,'minutes_precision':row.minutes_precision if appeared else None,
        'categories':_outcome_categories(primitives) if appeared else []}
    result={'outcome_id':digest(body),**body};validate_outcome_body(result);return result


def pending_outcome(forecast,*,status,source_raw_sha256,source_observed_at,normalized_at,
                    source_updated_at=None):
    if status not in OUTCOME_STATUSES-{'APPEARED','DNP'}:
        raise IntegrityError('pending outcome must preserve a nonfinal/missing status')
    body={'schema_version':'nba-pros004-outcome-v1','study_id':STUDY_ID,
        **{key:forecast[key] for key in ('mode','event_id','event_version','event_starts_at','player_id','team_id','opponent_id')},
        'status':status,'source_observed_at':stamp(utc(source_observed_at)),
        'source_updated_at':stamp(utc(source_updated_at)) if source_updated_at is not None else None,
        'normalized_at':stamp(utc(normalized_at)),'source_raw_sha256':source_raw_sha256,
        'normalizer_version':'espn-nba-selected-outcomes-v1','primitives':None,'minutes':None,
        'minutes_precision':None,'categories':[]}
    result={'outcome_id':digest(body),**body};validate_outcome_body(result);return result


def normalize_outcome_bytes(raw,event_body,*,observed_at):
    """Parse already retained offline evidence; this function makes no capture.

    The original primary normalizer checks the exact source bytes against the
    admitted event/teams, full-game period meaning and coherent player counts.
    Its source-observation/import clocks survive the typed conversion. The raw
    artifact still needs independent durable retention before activation; its
    hash alone does not establish upstream authenticity or permission.
    """
    from .pros004_inputs import validate_event_body
    from .prospective_outcomes import normalize_summary
    from .nba_data import _strict_json
    validate_event_body(event_body)
    normalized=normalize_summary(raw,event_body['event'],event_body['candidates'],observed_at=observed_at)
    document=_strict_json(raw.decode('utf-8'))
    competition=document['header']['competitions'][0]
    status=competition.get('status',document['header'].get('status',{}))['type']
    nonfinal='POSTPONED' if status.get('name')=='STATUS_POSTPONED' else 'NONFINAL'
    outcomes={}
    for candidate in event_body['candidates']:
        player=candidate['player_id']
        clocks={key:normalized[key] for key in ('source_raw_sha256','source_observed_at','source_updated_at','normalized_at')}
        if player in normalized['rows']:
            outcomes[player]=outcome_from_normalized(normalized['rows'][player],
                event_version=event_body['event']['event_version'],mode=event_body['mode'],**clocks)
        else:
            reason=next(row['reason'] for row in normalized['pending'] if row['player_id']==player)
            state=nonfinal if reason=='EVENT_NOT_VERIFIED_FINAL' else (
                'MISSING' if reason=='SELECTED_ATHLETE_MISSING_FROM_FINAL_BOXSCORE' else 'UNRESOLVED')
            subject={'mode':event_body['mode'],**event_body['event'],**candidate}
            outcomes[player]=pending_outcome(subject,status=state,**clocks)
    return {'schema_version':'nba-pros004-outcome-normalization-v1','study_id':STUDY_ID,
        'mode':event_body['mode'],'event_id':event_body['event']['event_id'],
        'event_version':event_body['event']['event_version'],'normalizer_version':normalized['normalizer_version'],
        'source_raw_sha256':normalized['source_raw_sha256'],'source_raw_bytes':len(raw),
        'source_observed_at':normalized['source_observed_at'],'source_updated_at':normalized['source_updated_at'],
        'normalized_at':normalized['normalized_at'],'source_status':normalized['status'],
        'pending_reasons':normalized['pending'],'outcomes':outcomes,
        'raw_retention_status':'EXTERNAL_RAW_ARTIFACT_REQUIRED',
        'financial_settlement':'NOT_EVALUATED','qualification':'UNAVAILABLE'}

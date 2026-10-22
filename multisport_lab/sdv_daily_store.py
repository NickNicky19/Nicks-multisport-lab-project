"""Exact publisher-release retention using the existing create-only ledger.

The versioned daily namespace shares the repository's record/byte budget with
the original ledger. Publicly licensed CSV and metadata bytes are losslessly
compressed here; no operational encryption key or browser storage is involved.
Local persistence, remote checkpointing and final independent readback remain
separate evidence. Recovery never turns an unacknowledged original into timely
issuance and never generates a missing forecast.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import zlib

from .integrity import (IntegrityError, canonical, digest, stamp, utc, _decode,
                        RECEIPT_SCHEMA, HASH_FORMAT)
from .ledger import (Ledger, LedgerRef, KINDS, SCHEMA, MAX_LEDGER_BYTES,
                     MAX_LEDGER_RECORDS, MAX_RECORD_BYTES)

PROTOCOL_ID = "NBA-SDV-DAILY-001"
ASSET_SCHEMA = "nba-sdv-daily-asset-v1"
COMPLETION_SCHEMA = "nba-sdv-daily-completion-v1"
OUTCOME_EVIDENCE_SCHEMA = "nba-sdv-daily-outcome-evidence-v1"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_FORECAST_BYTES = 64 * 1024
STAGES = {"LOCAL_PERSISTENCE", "REMOTE_CHECKPOINT", "FINAL_RECOVERY"}
KINDS_BY_SCHEMA = {
    ASSET_SCHEMA: "research_inputs", OUTCOME_EVIDENCE_SCHEMA:"research_inputs", "nba-sdv-daily-input-v1": "research_inputs",
    "nba-sdv-daily-cycle-v1": "input_captures",
    "nba-sdv-daily-authorization-v1": "input_captures",
    "nba-sdv-daily-intent-v1": "input_captures",
    "nba-sdv-daily-forecast-v1": "forecasts",
    "nba-sdv-daily-outcome-v1": "outcomes", "nba-sdv-daily-grade-v1": "grades",
    COMPLETION_SCHEMA: "input_captures", "nba-sdv-daily-failure-v1": "input_captures",
    "nba-sdv-daily-operation-v1":"input_captures",
}
ID_KEYS = {ASSET_SCHEMA: "asset_id", OUTCOME_EVIDENCE_SCHEMA:"evidence_id", COMPLETION_SCHEMA: "completion_id",
    "nba-sdv-daily-input-v1": "input_id", "nba-sdv-daily-cycle-v1": "cycle_digest",
    "nba-sdv-daily-authorization-v1": "authorization_id",
    "nba-sdv-daily-intent-v1": "intent_id",
    "nba-sdv-daily-forecast-v1": "forecast_id", "nba-sdv-daily-outcome-v1": "outcome_id",
    "nba-sdv-daily-grade-v1": "grade_id", "nba-sdv-daily-failure-v1": "failure_id",
    "nba-sdv-daily-operation-v1":"operation_id"}
CEILINGS = {ASSET_SCHEMA:MAX_RECORD_BYTES, OUTCOME_EVIDENCE_SCHEMA:MAX_RECORD_BYTES, "nba-sdv-daily-input-v1":64*1024,
    "nba-sdv-daily-cycle-v1":32*1024, "nba-sdv-daily-authorization-v1":256*1024,
    "nba-sdv-daily-intent-v1":8*1024, "nba-sdv-daily-forecast-v1":MAX_FORECAST_BYTES,
    "nba-sdv-daily-outcome-v1":32*1024, "nba-sdv-daily-grade-v1":32*1024,
    COMPLETION_SCHEMA:8*1024, "nba-sdv-daily-failure-v1":8*1024,
    "nba-sdv-daily-operation-v1":8*1024}


def _now():
    return datetime.now(timezone.utc)


def require(value, message):
    if not value:
        raise IntegrityError(message)


def clock(value):
    require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", value),
            "daily records require precise UTC clocks")
    try:return utc(value)
    except (TypeError,ValueError) as exc:raise IntegrityError("invalid daily UTC clock") from exc


def _hash(value):
    require(type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value), "invalid daily hash")
    return value


def _sealed(body, key):
    return {**body, key: digest(body)}


def _check_seal(body):
    schema=body.get("schema_version");key=ID_KEYS.get(schema)
    require(key is not None and body.get(key) == digest({k:v for k,v in body.items() if k != key}),
            "daily record checksum or schema mismatch")


def _identity(body):
    return {key:body[key] for key in ("protocol_id", "cycle_id", "mode", "event_id", "event_snapshot_id", "player_id", "team_id", "opponent_id", "model_key")
            if key in body}


def _encode(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_SOURCE_BYTES, "daily source exceeds its exact byte limit")
    return base64.b64encode(zlib.compress(raw, 9)).decode("ascii")


def _decode_source(value, expected_bytes, expected_sha):
    require(type(value) is str and len(value) <= MAX_RECORD_BYTES and type(expected_bytes) is int
            and 0 < expected_bytes <= MAX_SOURCE_BYTES, "invalid retained daily source bounds")
    _hash(expected_sha)
    try:
        packed=base64.b64decode(value, validate=True)
        decoder=zlib.decompressobj();raw=decoder.decompress(packed, MAX_SOURCE_BYTES+1)
        require(decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data,
                "retained source is truncated, oversized or has trailing content")
    except (ValueError, zlib.error) as exc:
        raise IntegrityError("invalid retained daily source encoding") from exc
    require(len(raw) == expected_bytes and hashlib.sha256(raw).hexdigest() == expected_sha,
            "retained daily original bytes changed")
    return raw


def _validate_asset(body):
    fields={"schema_version", "protocol_id", "metadata", "encoding", "raw_base64",
            "metadata_raw_base64", "metadata_raw_bytes", "metadata_raw_sha256", "asset_id"}
    require(set(body) == fields and body["encoding"] == "ZLIB_BASE64_EXACT_ORIGINAL_BYTES",
            "invalid daily asset contract")
    metadata=body["metadata"]
    require(type(metadata) is dict and metadata.get("role") in {"schedule", "roster"}
            and metadata.get("publisher") == "SportsDataverse", "wrong retained source identity")
    raw=_decode_source(body["raw_base64"], metadata.get("asset_bytes"), metadata.get("asset_sha256"))
    original=_decode_source(body["metadata_raw_base64"], body["metadata_raw_bytes"], body["metadata_raw_sha256"])
    from .sdv_daily_inputs import validate_source_metadata
    validate_source_metadata(metadata, raw=raw)
    require(metadata.get("metadata_bytes") == len(original)
            and metadata.get("metadata_sha256") == body["metadata_raw_sha256"], "metadata witness differs")
    release=_decode(original)
    require(type(release) is dict and type(release.get("assets")) is list
            and release.get("tag_name") == metadata.get("release_tag"), "wrong publisher release body")
    matches=[row for row in release["assets"] if type(row) is dict and row.get("id") == metadata.get("asset_id")]
    require(len(matches) == 1, "retained publisher asset ID is absent or ambiguous")
    asset=matches[0]
    require(asset.get("name") == metadata.get("asset_name") and asset.get("size") == len(raw)
            and asset.get("browser_download_url") == metadata.get("asset_url")
            and asset.get("digest") == "sha256:"+metadata["asset_sha256"]
            and utc(asset.get("updated_at")) == clock(metadata.get("publisher_updated_at")),
            "CSV bytes or metadata do not match the exact publisher asset")
    require(clock(metadata["retrieval_started_at"]) <= clock(metadata["retrieved_at"]) <= _now()
            and clock(metadata["publisher_updated_at"]) <= clock(metadata["retrieved_at"]),
            "retained asset observation/update clocks conflict")
    return raw, metadata, original


def _validate_outcome_evidence(body):
    fields={"schema_version","protocol_id","metadata","raw_base64","raw_bytes","raw_sha256",
            "source_use_status","evidence_id"}
    require(set(body) == fields and body["source_use_status"] == "REQUIRES_SEPARATE_ADMISSION",
            "raw retention cannot grant outcome collection or publication admission")
    meta=body["metadata"]
    require(type(meta) is dict and set(meta) == {"source_kind","source_url","source_observed_at",
        "retrieval_started_at","retrieved_at","content_type","source_use_basis"},
        "invalid raw outcome evidence metadata")
    require(all(type(meta[key]) is str and 0 < len(meta[key]) <= 2048 and meta[key].strip() == meta[key]
        for key in ("source_kind","source_url","content_type","source_use_basis")),
        "outcome evidence source identity is missing")
    require(meta["source_url"].startswith("https://") and "@" not in meta["source_url"],
            "outcome evidence requires a public source URL without credentials")
    require(clock(meta["source_observed_at"]) <= clock(meta["retrieved_at"]) <= _now()
        and clock(meta["retrieval_started_at"]) <= clock(meta["retrieved_at"]),
        "outcome evidence clocks conflict")
    return _decode_source(body["raw_base64"],body["raw_bytes"],body["raw_sha256"]),meta


def _validate_completion(body):
    fields={"schema_version", "protocol_id", "stage", "reference", "operation_started_at",
            "completed_at", "remote_commit", "completion_id"}
    require(set(body) == fields and body["stage"] in STAGES, "invalid daily completion contract")
    LedgerRef.from_record(body["reference"])
    require(clock(body["operation_started_at"]) <= clock(body["completed_at"]) <= _now(),
            "completion clocks conflict")
    if body["stage"] == "LOCAL_PERSISTENCE":
        require(body["remote_commit"] is None, "local persistence cannot claim remote recovery")
    else:
        require(type(body["remote_commit"]) is str and re.fullmatch(r"[a-f0-9]{40}", body["remote_commit"]),
                "remote completion lacks exact Git commit")


def validate_body(body, *, kind=None):
    require(type(body) is dict and body.get("protocol_id") == PROTOCOL_ID, "wrong daily protocol")
    schema=body.get("schema_version")
    require(schema in KINDS_BY_SCHEMA and (kind is None or kind == KINDS_BY_SCHEMA[schema]),
            "unsupported daily schema or record kind")
    _check_seal(body)
    if schema == ASSET_SCHEMA:
        _validate_asset(body)
    elif schema == OUTCOME_EVIDENCE_SCHEMA:
        _validate_outcome_evidence(body)
    elif schema == "nba-sdv-daily-operation-v1":
        from .sdv_daily_runner import validate_operation
        validate_operation(body)
    elif schema == COMPLETION_SCHEMA:
        _validate_completion(body)
    elif schema == "nba-sdv-daily-input-v1":
        from .sdv_daily_inputs import validate_input
        validate_input(body)
    else:
        from . import sdv_daily_producer as producer
        dispatcher=getattr(producer,"validate_body",None)
        if callable(dispatcher):
            dispatcher(body)
            return body
        name={"nba-sdv-daily-cycle-v1":"validate_cycle", "nba-sdv-daily-authorization-v1":"validate_authorization",
              "nba-sdv-daily-intent-v1":"validate_intent",
              "nba-sdv-daily-forecast-v1":"validate_forecast", "nba-sdv-daily-outcome-v1":"validate_outcome",
              "nba-sdv-daily-grade-v1":"validate_grade", "nba-sdv-daily-failure-v1":"validate_failure",
              "nba-sdv-daily-operation-v1":"validate_operation"}[schema]
        validator=getattr(producer,name,None)
        require(callable(validator), "daily typed validator is not installed: "+name)
        validator(body)
    return body


class DailyLedger(Ledger):
    """Known daily envelopes under a separate namespace, original code unchanged."""
    def __init__(self, project_root):
        self.project_root=Path(project_root).absolute()
        require(not any(parent.is_symlink() for parent in (self.project_root, *self.project_root.parents)),
                "daily store cannot traverse a symlink")
        super().__init__(self.project_root/"daily")
        self._verified_daily_forecast = None
        self._verified_daily_completion = None
        self._verified_remote_stage = None

    def append(self,kind,logical_id,data,*,references=(),supersedes=None):
        rid=digest({"kind":kind,"logical_id":logical_id})
        body=data.get("daily",{}) if type(data) is dict else {}
        if kind == "forecasts" and body.get("mode") == "PROSPECTIVE_RESEARCH" and not self._path(kind,rid).exists():
            permit=(rid,digest({"data":data,"references":[ref.to_record() for ref in references]}))
            require(self._verified_daily_forecast == permit,
                    "new daily prospective originals require the verified producer entrypoint")
        if body.get("schema_version") == COMPLETION_SCHEMA and not self._path(kind,rid).exists():
            original=self.read(LedgerRef.from_record(body["reference"]))["data"]["daily"]
            if original.get("mode") == "PROSPECTIVE_RESEARCH":
                permit=(rid,digest({"data":data,"references":[ref.to_record() for ref in references]}))
                require(self._verified_daily_completion == permit,
                        "new genuine completion requires actual post-action clock capture")
        return super().append(kind,logical_id,data,references=references,supersedes=supersedes)

    def _inventory(self):
        inventory, count, size=super()._inventory()
        _, parent_count, parent_size=Ledger(self.project_root)._inventory()
        require(count+parent_count <= MAX_LEDGER_RECORDS and size+parent_size <= MAX_LEDGER_BYTES,
                "shared original/daily ledger budget exceeded")
        return inventory, count+parent_count, size+parent_size

    def _check_append_budget(self,payload):
        _,count,size=self._inventory()
        encoded=len(canonical({"schema_version":RECEIPT_SCHEMA,"hash_format":HASH_FORMAT,
            "payload_sha256":digest(payload),"payload":payload}))+1
        schema=payload["data"].get("daily",{}).get("schema_version")
        maximum=CEILINGS.get(schema,8*1024 if payload["kind"] == "corrections" else 0)
        require(encoded <= maximum,"daily encoded record exceeds its individual envelope ceiling")
        require(count+1 <= MAX_LEDGER_RECORDS and size+encoded <= MAX_LEDGER_BYTES,
                "daily append exceeds the shared record/byte budget")

    def _validate_payload(self, payload, *, kind, record_id):
        if kind == "corrections":
            return Ledger._validate_payload(payload,kind=kind,record_id=record_id)
        fields={"schema_version", "kind", "record_id", "logical_id", "received_at", "data",
                "references", "supersedes", "persistence_status"}
        require(type(payload) is dict and set(payload) == fields and payload["schema_version"] == SCHEMA
                and payload["kind"] == kind and payload["record_id"] == record_id
                and payload["persistence_status"] == "LOCAL_RECEIPT_ONLY" and payload["supersedes"] is None,
                "invalid daily ledger envelope")
        require(type(payload["logical_id"]) is str and payload["logical_id"]
                and record_id == digest({"kind":kind,"logical_id":payload["logical_id"]}),
                "daily logical identity differs")
        require(clock(payload["received_at"]) <= _now(), "future daily receipt")
        require(type(payload["references"]) is list, "invalid daily references")
        refs=[LedgerRef.from_record(row) for row in payload["references"]]
        require(len(refs) == len(set(refs)), "duplicate daily references")
        data=payload["data"]
        require(type(data) is dict and set(data) == {"identity","daily"}, "invalid daily wrapper")
        body=validate_body(data["daily"],kind=kind)
        require(data["identity"] == _identity(body), "daily subject identity changed")
        if body["schema_version"] == "nba-sdv-daily-forecast-v1":
            require(payload["logical_id"] == "daily-original:"+":".join(body[k] for k in ("cycle_id","player_id","model_key")),
                    "daily original identity is not canonical")
        elif body["schema_version"] in {"nba-sdv-daily-cycle-v1","nba-sdv-daily-authorization-v1","nba-sdv-daily-intent-v1"}:
            label={"nba-sdv-daily-cycle-v1":"cycle","nba-sdv-daily-authorization-v1":"authorization",
                   "nba-sdv-daily-intent-v1":"intent"}[body["schema_version"]]
            require(payload["logical_id"] == "daily-"+label+":"+body["cycle_id"],"daily cycle identity is not canonical")
        encoded=len(canonical({"schema_version":RECEIPT_SCHEMA,"hash_format":HASH_FORMAT,
            "payload_sha256":digest(payload),"payload":payload}))+1
        require(encoded <= CEILINGS[body["schema_version"]], "retained daily envelope exceeds its individual ceiling")
        if body["schema_version"] == COMPLETION_SCHEMA:
            require(LedgerRef.from_record(body["reference"]) in refs
                    and clock(body["completed_at"]) <= clock(payload["received_at"]),
                    "completion lacks original reference or post-write chronology")

    def _validate_typed_references(self,payload):
        if payload["kind"] == "corrections":
            return
        body=payload["data"]["daily"]
        refs=[LedgerRef.from_record(row) for row in payload["references"]]
        if body["schema_version"] in {"nba-sdv-daily-intent-v1","nba-sdv-daily-forecast-v1"}:
            history=LedgerRef.from_record(body["history_ref"])
            require(history.kind == "research_inputs","daily producer history reference kind differs")
            try:Ledger(self.project_root).read(history)
            except OSError as exc:raise IntegrityError("daily retained parent history is missing") from exc
        if body["schema_version"] == "nba-sdv-daily-input-v1":
            require(len(refs) == 2 and all(ref.kind == "research_inputs" for ref in refs),
                    "daily input requires the two retained original assets")
            originals=[_validate_asset(self.read(ref)["data"]["daily"]) for ref in refs]
            by_role={metadata["role"]:(raw,metadata) for raw,metadata,_ in originals}
            require(set(by_role) == {"schedule","roster"}, "daily input source inventory differs")
            from .sdv_daily_inputs import verify_input_sources
            verify_input_sources(body,by_role["schedule"][0],by_role["roster"][0],
                by_role["schedule"][1],by_role["roster"][1])
        elif body["schema_version"] == "nba-sdv-daily-forecast-v1":
            ref=LedgerRef.from_record(body["input_ref"])
            require(ref in refs, "daily forecast lacks its exact input reference")
            input_body=self.read(ref)["data"]["daily"]
            from .sdv_daily_producer import validate_forecast
            validate_forecast(body,input_body)
            require(len(refs) == 2,"daily forecast requires exactly its input and generation intent")
            intent_ref=next(item for item in refs if item != ref)
            intent_payload=self.read(intent_ref);intent=intent_payload["data"]["daily"]
            require(intent["schema_version"] == "nba-sdv-daily-intent-v1",
                    "daily forecast lacks its unique generation intent")
            for peer in intent_payload["references"]:
                auth=self.read(LedgerRef.from_record(peer))["data"]["daily"]
                if auth["schema_version"] == "nba-sdv-daily-authorization-v1":
                    from .sdv_daily_cycle import validate_authorization
                    validate_authorization(auth,producer_binding=body["producer_binding"])
            require(all(intent[key] == body[key] for key in ("cycle_id","mode","input_ref","input_id","history_ref"))
                    and intent["producer_binding_id"] == body["producer_binding"]["binding_id"],
                    "daily original differs from its input/source generation intent")
        elif body["schema_version"] == "nba-sdv-daily-intent-v1":
            original=LedgerRef.from_record(body["input_ref"])
            require(original in refs,"generation intent lacks its exact shared input")
            input_body=self.read(original)["data"]["daily"]
            require(input_body["input_id"] == body["input_id"] and input_body["mode"] == body["mode"],
                    "generation intent input/mode conflict")
            peers=[self.read(ref)["data"]["daily"] for ref in refs if ref != original]
            cycles=[row for row in peers if row["schema_version"] == "nba-sdv-daily-cycle-v1"]
            require(len(cycles) == 1 and cycles[0]["cycle_id"] == body["cycle_id"],
                    "generation intent lacks its predeclared cycle")
            cycle=cycles[0]
            require(input_body["policy"]["policy_id"] == cycle["policy_id"]
                and input_body["candidates"] == cycle["candidates"]
                and all(input_body["event"][key] == cycle["event"][key]
                        for key in ("event_id","event_starts_at","home_team_id","away_team_id")),
                    "daily input and registered cycle differ")
            auth=[row for row in peers if row["schema_version"] == "nba-sdv-daily-authorization-v1"]
            require(len(refs) == (3 if body["mode"] == "PROSPECTIVE_RESEARCH" else 2),
                    "generation intent reference inventory differs")
            if body["mode"] == "PROSPECTIVE_RESEARCH":
                require(len(auth) == 1 and auth[0]["cycle_id"] == body["cycle_id"],
                        "prospective generation intent lacks owner authorization")
                from .sdv_daily_cycle import validate_authorization
                validate_authorization(auth[0],cycle=cycles[0])
                require(auth[0]["producer_binding_id"] == body["producer_binding_id"],
                        "authorization and generation intent source binding differ")
            else:
                require(not auth,"development intent cannot carry genuine authorization")
        elif body["schema_version"] == "nba-sdv-daily-outcome-v1":
            source_refs=[LedgerRef.from_record(row) for row in body["source_refs"]]
            require(set(source_refs) == set(refs), "daily outcome sources differ from retained references")
            for ref in source_refs:
                require(self.read(ref)["data"]["daily"]["schema_version"] == OUTCOME_EVIDENCE_SCHEMA,
                        "daily outcome requires retained original source bytes")
            from .sdv_daily_outcomes import verify_outcome_sources
            verify_outcome_sources(DailyStore(self.project_root),body)
        elif body["schema_version"] == "nba-sdv-daily-grade-v1":
            require(len(refs) == 2 and {ref.kind for ref in refs} == {"forecasts","outcomes"},
                    "daily grade requires the original forecast and shared outcome")
            targets={ref.kind:self.read(ref)["data"]["daily"] for ref in refs}
            from .sdv_daily_producer import validate_grade
            validate_grade(body, targets["forecasts"], targets["outcomes"])
        elif body["schema_version"] == COMPLETION_SCHEMA:
            ref=LedgerRef.from_record(body["reference"])
            target=self.read(ref)
            require(clock(target["received_at"]) <= clock(body["completed_at"]),
                    "completion precedes its retained original receipt")


class DailyStore:
    def __init__(self, project_root):
        self.project_root=Path(project_root).absolute()
        self.root=self.project_root
        self.ledger=DailyLedger(self.project_root)

    @contextmanager
    def lock(self):
        directory=self.project_root/"daily"
        require(not self.project_root.is_symlink() and not directory.is_symlink(), "daily writer cannot traverse a symlink")
        directory.mkdir(parents=True,exist_ok=True)
        path=directory/".writer.lock"
        require(not path.is_symlink(), "daily writer lock is a symlink")
        with path.open("a+") as handle:
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)

    def retain_asset(self, raw, metadata, metadata_raw):
        body=_sealed({"schema_version":ASSET_SCHEMA,"protocol_id":PROTOCOL_ID,"metadata":metadata,
            "encoding":"ZLIB_BASE64_EXACT_ORIGINAL_BYTES","raw_base64":_encode(raw),
            "metadata_raw_base64":_encode(metadata_raw),"metadata_raw_bytes":len(metadata_raw),
            "metadata_raw_sha256":hashlib.sha256(metadata_raw).hexdigest()},"asset_id")
        return self.append_body("research_inputs",body)

    def retain_outcome_evidence(self,raw,metadata):
        body=_sealed({"schema_version":OUTCOME_EVIDENCE_SCHEMA,"protocol_id":PROTOCOL_ID,
            "metadata":metadata,"raw_base64":_encode(raw),"raw_bytes":len(raw),
            "raw_sha256":hashlib.sha256(raw).hexdigest(),
            "source_use_status":"REQUIRES_SEPARATE_ADMISSION"},"evidence_id")
        return self.append_body("research_inputs",body)

    def read_outcome_evidence(self,ref):
        body=self.ledger.read(ref)["data"]["daily"]
        require(body["schema_version"] == OUTCOME_EVIDENCE_SCHEMA,"reference is not original outcome evidence")
        return _validate_outcome_evidence(body)

    @contextmanager
    def _verified_forecast_write(self,body,references):
        """Internal producer boundary; not a signature or source-use grant."""
        logical="daily-original:"+":".join(body[k] for k in ("cycle_id","player_id","model_key"))
        old=self.ledger._verified_daily_forecast
        self.ledger._verified_daily_forecast=(digest({"kind":"forecasts","logical_id":logical}),
            digest({"data":{"identity":_identity(body),"daily":body},
                    "references":[ref.to_record() for ref in references]}))
        try:yield
        finally:self.ledger._verified_daily_forecast=old

    def read_asset(self, ref):
        body=self.ledger.read(ref)["data"]["daily"]
        require(body["schema_version"] == ASSET_SCHEMA, "reference is not a retained source asset")
        return _validate_asset(body)

    def persist_input(self, body, asset_refs):
        return self.append_body("research_inputs",body,references=tuple(asset_refs))

    def append_body(self,kind,body,*,references=(),logical_id=None):
        validate_body(body,kind=kind)
        schema=body["schema_version"]
        if schema == "nba-sdv-daily-forecast-v1":
            expected="daily-original:"+":".join(body[k] for k in ("cycle_id","player_id","model_key"))
            require(logical_id in {None,expected},"cannot replace the canonical daily original identity")
        elif schema in {"nba-sdv-daily-cycle-v1","nba-sdv-daily-authorization-v1","nba-sdv-daily-intent-v1"}:
            label={"nba-sdv-daily-cycle-v1":"cycle","nba-sdv-daily-authorization-v1":"authorization",
                   "nba-sdv-daily-intent-v1":"intent"}[schema]
            require(logical_id in {None,"daily-"+label+":"+body["cycle_id"]},
                    "cannot replace the canonical daily cycle identity")
        if logical_id is None:
            if schema == "nba-sdv-daily-forecast-v1":
                logical_id="daily-original:"+":".join(body[k] for k in ("cycle_id","player_id","model_key"))
            elif schema in {"nba-sdv-daily-cycle-v1","nba-sdv-daily-authorization-v1","nba-sdv-daily-intent-v1"}:
                label={"nba-sdv-daily-cycle-v1":"cycle", "nba-sdv-daily-authorization-v1":"authorization",
                       "nba-sdv-daily-intent-v1":"intent"}[schema]
                logical_id="daily-"+label+":"+body["cycle_id"]
            elif schema == COMPLETION_SCHEMA:
                ref=LedgerRef.from_record(body["reference"])
                logical_id="daily-completion:"+ref.kind+":"+ref.record_id+":"+body["stage"]
            else:
                logical_id="daily:"+schema+":"+body[ID_KEYS[schema]]
        return self.ledger.append(kind,logical_id,{"identity":_identity(body),"daily":body},references=tuple(references))

    @contextmanager
    def _verified_remote_completion(self,ref,stage,remote_commit):
        """Internal writer boundary after actual push/fresh readback, not a signature."""
        old=self.ledger._verified_remote_stage
        self.ledger._verified_remote_stage=(ref,stage,remote_commit)
        try:yield
        finally:self.ledger._verified_remote_stage=old

    def record_completion(self,ref,*,started_at,completed_at=None,stage="LOCAL_PERSISTENCE",remote_commit=None):
        original=self.ledger.read(ref)["data"]["daily"]
        require(original.get("mode") != "PROSPECTIVE_RESEARCH" or completed_at is None,
                "genuine completion cannot accept a caller-supplied clock")
        logical="daily-completion:"+ref.kind+":"+ref.record_id+":"+stage
        rid=digest({"kind":"input_captures","logical_id":logical})
        path=self.ledger._path("input_captures",rid)
        if path.exists():
            from .integrity import read_receipt
            payload=read_receipt(path);old=payload["data"]["daily"]
            require(old["reference"] == ref.to_record() and old["stage"] == stage
                    and old["operation_started_at"] == stamp(utc(started_at)) and old["remote_commit"] == remote_commit,
                    "completion retry changed its original operation")
            self.ledger.read(LedgerRef("input_captures",rid,digest(payload)))
            return LedgerRef("input_captures",rid,digest(payload))
        if original.get("mode") == "PROSPECTIVE_RESEARCH" and stage != "LOCAL_PERSISTENCE":
            require(self.ledger._verified_remote_stage == (ref,stage,remote_commit),
                    "genuine remote completion requires actual checkpoint writer proof")
        body=_sealed({"schema_version":COMPLETION_SCHEMA,"protocol_id":PROTOCOL_ID,"stage":stage,
            "reference":ref.to_record(),"operation_started_at":stamp(utc(started_at)),
            "completed_at":stamp(utc(completed_at) if completed_at is not None else _now()),
            "remote_commit":remote_commit},"completion_id")
        old=self.ledger._verified_daily_completion
        self.ledger._verified_daily_completion=(rid,digest({"data":{"identity":_identity(body),"daily":body},
            "references":[ref.to_record()]}))
        try:return self.append_body("input_captures",body,references=(ref,),logical_id=logical)
        finally:self.ledger._verified_daily_completion=old

    def records(self):
        index=self.ledger.scan()
        return [(LedgerRef(kind,rid,digest(payload)),payload["data"]["daily"])
                for kind in KINDS for rid,payload in sorted(index[kind].items()) if kind != "corrections"]

    def corrections(self):
        index=self.ledger.scan()
        return [{"reference":LedgerRef("corrections",rid,digest(payload)).to_record(),
                 "original_ref":payload["supersedes"],"replacement_ref":payload["data"]["replacement"],
                 "reason":payload["data"]["reason"]}
                for rid,payload in sorted(index["corrections"].items())]

    def admission(self,ref):
        return self._admission(ref,self.records())

    def _admission(self,ref,records):
        indexed={item:body for item,body in records}
        require(ref in indexed,"admission reference is not present in the recovered ledger")
        body=indexed[ref]
        stages={row["stage"]:row for _,row in records
            if row["schema_version"] == COMPLETION_SCHEMA and row["reference"] == ref.to_record()}
        local=stages.get("LOCAL_PERSISTENCE");remote=stages.get("REMOTE_CHECKPOINT");final=stages.get("FINAL_RECOVERY")
        reasons=[]
        if body.get("mode") != "PROSPECTIVE_RESEARCH":reasons.append("DEVELOPMENT_ONLY_NOT_GENUINE_ISSUANCE")
        for name,value in (("LOCAL_PERSISTENCE",local),("REMOTE_CHECKPOINT",remote),("FINAL_RECOVERY",final)):
            if value is None:reasons.append(name+"_UNACKNOWLEDGED")
        if local and remote and clock(local["completed_at"]) > clock(remote["completed_at"]):reasons.append("REMOTE_PRECEDES_LOCAL")
        if remote and final and (clock(remote["completed_at"]) > clock(final["completed_at"])
                                or remote["remote_commit"] != final["remote_commit"]):reasons.append("FINAL_RECOVERY_CONFLICT")
        if body["schema_version"] == "nba-sdv-daily-forecast-v1":
            input_ref=LedgerRef.from_record(body["input_ref"])
            input_body=indexed[input_ref]
            input_admission=self._admission(input_ref,records)
            reasons.extend("INPUT_"+reason for reason in input_admission["reasons"])
            # This relationship is in the immutable ledger envelope, not copied
            # into public forecast probabilities or an assumed caller state.
            original=self.ledger.read(ref)
            intent_refs=[LedgerRef.from_record(row) for row in original["references"]
                         if LedgerRef.from_record(row) != input_ref]
            require(len(intent_refs) == 1,"forecast admission lacks exact generation intent")
            intent_admission=self._admission(intent_refs[0],records)
            reasons.extend("INTENT_"+reason for reason in intent_admission["reasons"])
            policy=input_body["policy"]
            if final:
                from .sdv_daily_inputs import freshness
                try:freshness(input_body,at=clock(final["completed_at"]),require_retrieval_window=True)
                except IntegrityError:reasons.append("INPUT_FRESHNESS_FAILED_AT_FINAL_RECOVERY")
            start=clock(body["generation_started_at"])
            deadline=clock(body["event_starts_at"])-timedelta(minutes=policy["issuance_open_minutes_before_start"])+timedelta(seconds=policy["issuance_window_seconds"])
            for name,value in (("LOCAL_PERSISTENCE",local),("REMOTE_CHECKPOINT",remote),("FINAL_RECOVERY",final)):
                if value and (clock(value["completed_at"]) > deadline
                              or (clock(value["completed_at"])-start).total_seconds() > policy["maximum_original_latency_seconds"]):
                    reasons.append(name+"_LATE")
        elif body["schema_version"] in {"nba-sdv-daily-input-v1","nba-sdv-daily-intent-v1"}:
            input_body=body if body["schema_version"] == "nba-sdv-daily-input-v1" else indexed[LedgerRef.from_record(body["input_ref"])]
            cutoff=clock(input_body["event"]["event_starts_at"])-timedelta(minutes=input_body["policy"]["issuance_open_minutes_before_start"])
            if any(value and clock(value["completed_at"]) > cutoff for value in (local,remote,final)):
                reasons.append("INPUT_PERSISTENCE_OR_RECOVERY_AFTER_CUTOFF")
        else:
            reasons.append("NOT_AN_ISSUANCE_OR_INPUT_RECORD")
        return {"eligible":not reasons,"local_persistence_completed_at":local["completed_at"] if local else None,
                "remote_recovery_completed_at":final["completed_at"] if final else None,"reasons":reasons}

    def recover(self):
        records=self.records()
        forecasts=[(ref,body) for ref,body in records if body["schema_version"] == "nba-sdv-daily-forecast-v1"]
        inputs=[(ref,body) for ref,body in records if body["schema_version"] == "nba-sdv-daily-input-v1"]
        admissions={ref.record_id:self._admission(ref,records) for ref,_ in forecasts+inputs}
        return {"records":records,"forecasts":forecasts,"inputs":inputs,
                "corrections":self.corrections(),
                "completions":[(ref,body) for ref,body in records if body["schema_version"] == COMPLETION_SCHEMA],
                "admissions":admissions,
                "genuine_issued":sum(admissions[ref.record_id]["eligible"] for ref,_ in forecasts)}

    def capacity(self,*,planned_forecasts=8):
        require(type(planned_forecasts) is int and 1 <= planned_forecasts <= 32, "invalid daily planned cohort budget")
        _,count,size=self.ledger._inventory()
        # Two bounded originals+metadata, one input/cycle/activation, three
        # completion stages per input/forecast, outcomes, grades and revisions.
        slots={"source_assets":(2,MAX_RECORD_BYTES),"shared_input":(1,64*1024),
            "cycle":(1,32*1024),"authorization":(1,256*1024),"generation_intent":(1,8*1024),
            "forecasts":(planned_forecasts,64*1024),"input_completions":(3,8*1024),
            "intent_completions":(3,8*1024),
            "forecast_completions":(3*planned_forecasts,8*1024),
            "outcome_evidence_and_revisions":(4,MAX_RECORD_BYTES),
            "outcomes_and_revisions":(2*planned_forecasts,32*1024),
            "grades_and_revisions":(2*planned_forecasts,32*1024),
            "correction_links":(2*planned_forecasts,8*1024),"failure_metadata":(8,8*1024),
            "operation_reports":(8,8*1024)}
        reserved_records=sum(n for n,_ in slots.values())
        reserved_bytes=sum(n*limit for n,limit in slots.values())
        return {"existing_records":count,"existing_bytes":size,"reserved_records":reserved_records,
                "reserved_bytes":reserved_bytes,"maximum_records":MAX_LEDGER_RECORDS,
                "maximum_bytes":MAX_LEDGER_BYTES,"slots":{k:{"records":n,"max_encoded_record_bytes":limit}
                    for k,(n,limit) in slots.items()},"fits":count+reserved_records <= MAX_LEDGER_RECORDS
                    and size+reserved_bytes <= MAX_LEDGER_BYTES}

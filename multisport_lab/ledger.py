"""Create-only local research records, recoverable without an in-memory index.

Local checksums and creation clocks do not prove remote durability or upstream
availability. Git commit/push and independent remote readback are separate checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

from .integrity import (HASH_FORMAT, RECEIPT_SCHEMA, IntegrityError, canonical,
                        digest, read_receipt, stamp, utc, write_receipt)


SCHEMA = "multisport-research-ledger-v1"
KINDS = ("forecasts", "outcomes", "grades", "corrections", "input_captures", "research_inputs")
MAX_RECORD_BYTES = 4 * 1024 * 1024
MAX_LEDGER_RECORDS = 512
MAX_LEDGER_BYTES = 32 * 1024 * 1024
FINANCIAL_STATUS = "UNSETTLED_FINANCIAL_NOT_IMPLEMENTED"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: Any, field: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise IntegrityError(f"{field} must be a nonempty trimmed string")
    return value


def _hash(value: Any, field: str) -> str:
    if type(value) is not str or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise IntegrityError(f"invalid {field}")
    return value


def _wire_time(value: Any) -> datetime:
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", value):
        raise IntegrityError("ledger wire clocks require microsecond UTC timestamps")
    return utc(value)


@dataclass(frozen=True, slots=True)
class LedgerRef:
    kind: str
    record_id: str
    payload_sha256: str

    def __post_init__(self):
        if self.kind not in KINDS:
            raise IntegrityError("unsupported record kind")
        _hash(self.record_id, "record_id")
        _hash(self.payload_sha256, "payload_sha256")

    def to_record(self) -> dict:
        return {"kind": self.kind, "record_id": self.record_id, "payload_sha256": self.payload_sha256}

    @classmethod
    def from_record(cls, record: dict) -> LedgerRef:
        if type(record) is not dict or set(record) != {"kind", "record_id", "payload_sha256"}:
            raise IntegrityError("invalid ledger reference schema")
        return cls(**record)


class Ledger:
    """A repository records/ store; retries never replace an original timestamp.

    Tests may supply a temporary root. The default is this package's repository,
    not a process-local temporary directory or a browser's storage.
    """

    def __init__(self, repository_root: Path | str | None = None):
        self.root = Path(repository_root) if repository_root is not None else Path(__file__).resolve().parents[1]
        self.root = self.root.absolute()
        # An internal admission boundary, not a signature or access-control
        # mechanism: new R1 writes must pass the actual coherent producer API.
        self._verified_prospective_append: tuple[str, str] | None = None

    def _path(self, kind: str, record_id: str) -> Path:
        if kind not in KINDS:
            raise IntegrityError("unsupported record kind")
        _hash(record_id, "record_id")
        path = self.root / "records" / kind / f"{record_id}.json"
        # A symlinked records directory would move writes outside the chosen store.
        for parent in (self.root, self.root / "records", path.parent):
            if parent.is_symlink():
                raise IntegrityError("ledger directories must not be symlinks")
        return path

    def _inventory(self) -> tuple[dict[str, list[tuple[Path, int]]], int, int]:
        """Bound all receipt counts/bytes before decoding any records."""
        result = {kind: [] for kind in KINDS}
        count = total_bytes = 0
        for kind in KINDS:
            directory = self._path(kind, "0" * 64).parent
            if not directory.exists():
                continue
            with os.scandir(directory) as entries:
                for entry in entries:
                    unpublished = entry.name.startswith(".receipt-")
                    if not unpublished and not re.fullmatch(r"[a-f0-9]{64}\.json", entry.name):
                        raise IntegrityError("unrecognized file in ledger record directory")
                    info = entry.stat(follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode):
                        raise IntegrityError("ledger receipts must be regular files, not symlinks")
                    if info.st_size > MAX_RECORD_BYTES:
                        raise IntegrityError("ledger record exceeds its byte budget")
                    count += 1
                    total_bytes += info.st_size
                    if count > MAX_LEDGER_RECORDS:
                        raise IntegrityError("ledger exceeds its total receipt count budget")
                    if total_bytes > MAX_LEDGER_BYTES:
                        raise IntegrityError("ledger exceeds its total receipt byte budget")
                    if not unpublished:
                        result[kind].append((Path(entry.path), info.st_size))
        return result, count, total_bytes

    def _check_append_budget(self, payload: dict) -> None:
        _, count, total_bytes = self._inventory()
        envelope = {"schema_version": RECEIPT_SCHEMA, "hash_format": HASH_FORMAT,
                    "payload_sha256": digest(payload), "payload": payload}
        size = len(canonical(envelope))
        if size > MAX_RECORD_BYTES:
            raise IntegrityError("ledger record exceeds its byte budget")
        if count + 1 > MAX_LEDGER_RECORDS:
            raise IntegrityError("new record would exceed the total receipt count budget")
        if total_bytes + size > MAX_LEDGER_BYTES:
            raise IntegrityError("new record would exceed the total receipt byte budget")

    @staticmethod
    def _validate_payload(payload: dict, *, kind: str, record_id: str) -> None:
        fields = {"schema_version", "kind", "record_id", "logical_id", "received_at",
                  "data", "references", "supersedes", "persistence_status"}
        if type(payload) is not dict or set(payload) != fields:
            raise IntegrityError("invalid ledger record schema")
        if (payload["schema_version"] != SCHEMA or payload["kind"] != kind
                or payload["record_id"] != record_id
                or payload["persistence_status"] != "LOCAL_RECEIPT_ONLY"):
            raise IntegrityError("ledger record identity or status mismatch")
        _text(payload["logical_id"], "logical_id")
        if record_id != digest({"kind": kind, "logical_id": payload["logical_id"]}):
            raise IntegrityError("logical identity hash mismatch")
        if _wire_time(payload["received_at"]) > _now():
            raise IntegrityError("ledger receipt creation clock is in the future")
        if type(payload["data"]) is not dict or type(payload["references"]) is not list:
            raise IntegrityError("data must be an object and references a list")
        refs = [LedgerRef.from_record(item) for item in payload["references"]]
        if len(set(refs)) != len(refs):
            raise IntegrityError("duplicate ledger references")
        supersedes = payload["supersedes"]
        if supersedes is not None:
            target = LedgerRef.from_record(supersedes)
            if kind != "corrections" or target not in refs:
                raise IntegrityError("only a referenced correction may supersede a record")
            data = payload["data"]
            if set(data) != {"reason", "replacement"}:
                raise IntegrityError("invalid correction schema")
            _text(data["reason"], "correction reason")
            replacement = LedgerRef.from_record(data["replacement"])
            if (replacement not in refs or replacement.kind != target.kind
                    or replacement == target or target.kind == "corrections"):
                raise IntegrityError("invalid correction replacement")
            if payload["logical_id"] != f"supersedes:{target.kind}:{target.record_id}":
                raise IntegrityError("correction logical identity must be canonical for its superseded record")
        elif kind == "corrections":
            raise IntegrityError("correction requires an explicit superseded record")
        typed_keys = {"bundle": "forecasts", "outcome": "outcomes", "grade": "grades",
                      "capture": "input_captures", "source_pack": "research_inputs"}
        if any(key in payload["data"] and kind != expected for key, expected in typed_keys.items()):
            raise IntegrityError("typed evidence is stored under the wrong record kind")
        if kind == "forecasts" and "bundle" in payload["data"]:
            from .forecast_contract import validate_forecast
            data = payload["data"]
            if set(data) != {"identity", "bundle", "producer_verification"}:
                raise IntegrityError("forecast issuance requires a producer verification record")
            bundle, verification = data["bundle"], data["producer_verification"]
            validate_forecast(bundle, now=utc(payload["received_at"]))
            if (data["identity"] != _nba_identity(bundle)
                    or payload["logical_id"] != "forecast:" + bundle["forecast_id"]):
                raise IntegrityError("forecast logical or subject identity is inconsistent")
            prospective = bundle["evidence_lane"] == "REAL_TIME_CAPTURED"
            expected = {"schema_version": ("nba-pregame-r1-verification-envelope-v1" if prospective
                                           else "nba-r0-verification-envelope-v1"),
                        "forecast_id": bundle["forecast_id"], "forecast_sha256": digest(bundle),
                        "joint_sha256": bundle["joint_sha256"], "model_version": bundle["model_version"]}
            if (type(verification) is not dict or set(verification) != {*expected, "verified_at", "producer_check"}
                    or any(verification[key] != value for key, value in expected.items())
                    or type(verification["producer_check"]) is not dict or not verification["producer_check"]
                    or utc(verification["verified_at"]) > utc(payload["received_at"])):
                raise IntegrityError("forecast producer verification is missing, changed or misbound")
            check = verification["producer_check"]
            check_expected = {"schema_version": ("nba-pregame-r1-attestation-v1" if prospective
                                                else "nba-r0-joint-attestation-v1"),
                              **{key: bundle[key] for key in ("forecast_id", "joint_sha256", "input_sha256",
                                 "model_version", "model_commit", "model_code_sha256")},
                              "categories_sha256": digest(bundle["categories"]),
                              "scope": ("EXACT_CAPTURED_REFERENCE_COMPARISON_NOT_QUALIFICATION" if prospective
                                        else "EXACT_REFERENCE_COMPARISON_NOT_STATISTICAL_QUALIFICATION")}
            if prospective:
                metadata = bundle.get("prospective", {})
                if (bundle["schema_version"] != "nba-research-forecast-v2"
                        or bundle["model_version"] != "nba_joint_empirical_pregame_r1_v1"
                        or len(refs) != 1 or refs[0].kind != "research_inputs"
                        or bundle["input_capture_ids"] != [refs[0].record_id]
                        or metadata.get("source_pack_record_id") != refs[0].record_id):
                    raise IntegrityError("prospective forecast requires the exact versioned input package")
                check_expected.update(source_pack_sha256=metadata["source_pack_sha256"],
                                      source_pack_record_id=refs[0].record_id)
                if not (utc(bundle["issued_at"]) <= utc(verification["verified_at"])
                        <= utc(payload["received_at"])
                        <= utc(bundle["cutoff_at"]) + timedelta(minutes=5)):
                    raise IntegrityError("prospective receipt or verification exceeds its issuance window")
            if (set(check) != {*check_expected, "verified_at"}
                    or any(check[key] != value for key, value in check_expected.items())
                    or utc(check["verified_at"]) > utc(payload["received_at"])):
                raise IntegrityError("producer attestation does not bind the exact forecast/joint categories")
            if prospective and not (utc(bundle["issued_at"]) <= _wire_time(check["verified_at"])
                                    <= _wire_time(verification["verified_at"])):
                raise IntegrityError("prospective attestation or verification precedes original generation")
        if kind == "research_inputs":
            from .pregame_sources import validate_pack
            if set(payload["data"]) != {"source_pack"} or refs:
                raise IntegrityError("research inputs require one standalone normalized source package")
            pack = validate_pack(payload["data"]["source_pack"])
            if (payload["logical_id"] != "research-inputs:" + digest(pack)
                    or _wire_time(pack["imported_at"]) > utc(payload["received_at"])):
                raise IntegrityError("research input identity or import clock exceeds actual receipt")
        if kind == "outcomes" and "outcome" in payload["data"]:
            data = payload["data"]
            if set(data) != {"identity", "outcome"}:
                raise IntegrityError("invalid typed outcome record schema")
            outcome = validate_outcome(data["outcome"])
            if (data["identity"] != _nba_identity(outcome)
                    or payload["logical_id"] != "outcome:" + outcome["outcome_id"]
                    or utc(outcome["observed_at"]) > utc(payload["received_at"])):
                raise IntegrityError("outcome identity or source observation exceeds its receipt")
        if kind == "grades" and "grade" in payload["data"]:
            data = payload["data"]
            if set(data) != {"identity", "grade", "financial_status"} or data["financial_status"] != FINANCIAL_STATUS:
                raise IntegrityError("invalid typed grade record schema or financial claim")
            grade = validate_grade(data["grade"])
            expected_refs = {"forecasts": digest({"kind": "forecasts", "logical_id": "forecast:" + grade["forecast_id"]}),
                             "outcomes": digest({"kind": "outcomes", "logical_id": "outcome:" + grade["outcome_id"]})}
            if (len(refs) != 2 or {ref.kind: ref.record_id for ref in refs} != expected_refs
                    or utc(grade["graded_at"]) > utc(payload["received_at"])):
                raise IntegrityError("grade requires exact forecast/outcome references available at receipt")
            if payload["logical_id"] != f"forecast-grade:{expected_refs['forecasts']}:{expected_refs['outcomes']}":
                raise IntegrityError("grade logical identity does not match its evidence references")
        if kind == "input_captures" and "capture" in payload["data"]:
            data = payload["data"]
            if set(data) != {"identity", "capture"}:
                raise IntegrityError("invalid typed input capture record schema")
            capture = validate_capture(data["capture"], received_at=utc(payload["received_at"]))
            metadata = {k: v for k, v in capture.items() if k not in {"schema_version", "capture_id", "observed_at"}}
            if (data["identity"] != _nba_identity(capture)
                    or payload["logical_id"] != "input-capture:" + digest(metadata)):
                raise IntegrityError("input capture identity does not bind its metadata")

    def _validate_typed_references(self, payload: dict) -> None:
        if (payload["kind"] == "forecasts" and "bundle" in payload["data"]
                and payload["data"]["bundle"]["evidence_lane"] == "REAL_TIME_CAPTURED"):
            from .prospective import validate_input_binding
            bundle = payload["data"]["bundle"]
            refs = [LedgerRef.from_record(item) for item in payload["references"]]
            if len(refs) != 1 or refs[0].kind != "research_inputs":
                raise IntegrityError("prospective issuance requires one research input reference")
            source_payload = self.read(refs[0])
            if utc(source_payload["received_at"]) > utc(bundle["cutoff_at"]):
                raise IntegrityError("prospective inputs were not durably recorded by the cutoff")
            validate_input_binding(bundle, source_payload["data"]["source_pack"],
                                   input_record_id=refs[0].record_id)
            return
        if payload["kind"] != "grades" or "grade" not in payload["data"]:
            return
        refs = {item["kind"]: LedgerRef.from_record(item) for item in payload["references"]}
        forecast_data = self.read(refs["forecasts"])["data"]
        outcome_data = self.read(refs["outcomes"])["data"]
        if "bundle" not in forecast_data or "outcome" not in outcome_data:
            raise IntegrityError("grade references must identify typed forecast and outcome evidence")
        validate_grade(payload["data"]["grade"], forecast_data["bundle"], outcome_data["outcome"])
        if payload["data"]["identity"] != _nba_identity(forecast_data["bundle"]):
            raise IntegrityError("grade stored subject differs from its exact forecast target")

    def read(self, reference: LedgerRef) -> dict:
        if not isinstance(reference, LedgerRef):
            raise IntegrityError("a complete ledger reference is required")
        payload = read_receipt(self._path(reference.kind, reference.record_id), max_bytes=MAX_RECORD_BYTES)
        self._validate_payload(payload, kind=reference.kind, record_id=reference.record_id)
        if digest(payload) != reference.payload_sha256:
            raise IntegrityError("referenced payload hash mismatch")
        self._validate_typed_references(payload)
        return payload

    def append(self, kind: str, logical_id: str, data: dict, *,
               references: tuple[LedgerRef, ...] = (), supersedes: LedgerRef | None = None) -> LedgerRef:
        """Create or idempotently read the identical request; never rewrite bytes.

        Caller-supplied data must include its own original issued/captured clocks.
        received_at is generated here only on the first successful creation.
        """
        _text(logical_id, "logical_id")
        if type(data) is not dict:
            raise IntegrityError("record data must be an object")
        data = json.loads(canonical(data))  # Deep-copy without weakening strict JSON.
        refs = tuple(references)
        if any(not isinstance(ref, LedgerRef) for ref in refs) or len(set(refs)) != len(refs):
            raise IntegrityError("unique complete ledger references are required")
        if supersedes is not None and not isinstance(supersedes, LedgerRef):
            raise IntegrityError("invalid superseded reference")
        record_id = digest({"kind": kind, "logical_id": logical_id})
        path = self._path(kind, record_id)
        request = {"schema_version": SCHEMA, "kind": kind, "record_id": record_id,
                   "logical_id": logical_id, "data": data,
                   "references": [ref.to_record() for ref in refs],
                   "supersedes": supersedes.to_record() if supersedes is not None else None,
                   "persistence_status": "LOCAL_RECEIPT_ONLY"}
        for ref in refs:
            self.read(ref)
        if kind == "corrections":
            self._validate_payload({**request, "received_at": stamp(_now())}, kind=kind, record_id=record_id)
            old = self.read(supersedes)
            new = self.read(LedgerRef.from_record(data["replacement"]))
            if ("identity" not in old["data"] or
                    old["data"]["identity"] != new["data"].get("identity")):
                raise IntegrityError("replacement must preserve the subject identity")
        if path.exists() or path.is_symlink():
            existing = read_receipt(path, max_bytes=MAX_RECORD_BYTES)
            self._validate_payload(existing, kind=kind, record_id=record_id)
            if {k: v for k, v in existing.items() if k != "received_at"} != request:
                raise IntegrityError("conflicting logical record; append a traceable correction")
            self._validate_typed_references(existing)
            return LedgerRef(kind, record_id, digest(existing))
        if (kind == "forecasts" and type(data.get("bundle")) is dict
                and data["bundle"].get("evidence_lane") == "REAL_TIME_CAPTURED"):
            permit = (record_id, digest({"data": data, "references": request["references"]}))
            if self._verified_prospective_append != permit:
                raise IntegrityError("new prospective forecasts require the verified issue_prospective API")
        payload = {**request, "received_at": stamp(_now())}
        self._validate_payload(payload, kind=kind, record_id=record_id)
        self._validate_typed_references(payload)
        if any(utc(self.read(ref)["received_at"]) > utc(payload["received_at"]) for ref in refs):
            raise IntegrityError("a reference was received after this record's creation clock")
        if kind == "corrections":
            prospective = self.scan()
            prospective["corrections"][record_id] = payload
            self._correction_map(prospective)
        self._check_append_budget(payload)
        try:
            write_receipt(path, payload, max_bytes=MAX_RECORD_BYTES)
        except IntegrityError:
            # Another process may have created this same request with its own real
            # received clock. Read its original instead of retrying with a new one.
            if not path.exists():
                raise
            existing = read_receipt(path, max_bytes=MAX_RECORD_BYTES)
            self._validate_payload(existing, kind=kind, record_id=record_id)
            if {k: v for k, v in existing.items() if k != "received_at"} != request:
                raise
            payload = existing
        self._validate_typed_references(payload)
        return LedgerRef(kind, record_id, digest(payload))

    def scan(self) -> dict[str, dict[str, dict]]:
        """Rebuild an index from disk, checking every checksum and exact reference."""
        result = {kind: {} for kind in KINDS}
        inventory, _, _ = self._inventory()
        for kind in KINDS:
            for path, _ in sorted(inventory[kind]):
                payload = read_receipt(path, max_bytes=MAX_RECORD_BYTES)
                self._validate_payload(payload, kind=kind, record_id=path.stem)
                result[kind][path.stem] = payload
        for records in result.values():
            for payload in records.values():
                for item in payload["references"]:
                    ref = LedgerRef.from_record(item)
                    target = result[ref.kind].get(ref.record_id)
                    if target is None or digest(target) != ref.payload_sha256:
                        raise IntegrityError("missing or changed referenced ledger record")
                    if utc(target["received_at"]) > utc(payload["received_at"]):
                        raise IntegrityError("reference chronology is inconsistent")
                self._validate_typed_references(payload)
        self._correction_map(result)
        return result

    @staticmethod
    def _correction_map(index: dict) -> dict[LedgerRef, LedgerRef]:
        mapping = {}
        for payload in index["corrections"].values():
            data = payload["data"]
            if set(data) != {"reason", "replacement"}:
                raise IntegrityError("invalid correction schema")
            _text(data["reason"], "correction reason")
            old = LedgerRef.from_record(payload["supersedes"])
            new = LedgerRef.from_record(data["replacement"])
            if new.to_record() not in payload["references"] or old.kind != new.kind or old == new:
                raise IntegrityError("invalid replacement reference")
            old_payload = index[old.kind].get(old.record_id)
            new_payload = index[new.kind].get(new.record_id)
            if (old_payload is None or new_payload is None or "identity" not in old_payload["data"]
                    or old_payload["data"]["identity"] != new_payload["data"].get("identity")):
                raise IntegrityError("correction changes subject identity")
            if old in mapping:
                raise IntegrityError("conflicting correction branches")
            mapping[old] = new
        for start in mapping:
            seen = set()
            cursor = start
            while cursor in mapping:
                if cursor in seen:
                    raise IntegrityError("correction cycle")
                seen.add(cursor)
                cursor = mapping[cursor]
        return mapping

    def correct(self, original: LedgerRef, replacement: LedgerRef, *, reason: str) -> LedgerRef:
        """Append a link; original and replacement evidence both remain unchanged."""
        _text(reason, "correction reason")
        old, new = self.read(original), self.read(replacement)
        if (original.kind == "corrections" or original.kind != replacement.kind
                or original == replacement):
            raise IntegrityError("a correction needs distinct records of the same evidence kind")
        if "identity" not in old["data"] or old["data"]["identity"] != new["data"].get("identity"):
            raise IntegrityError("replacement must preserve the subject identity")
        index = self.scan()
        mapping = self._correction_map(index)
        cursor = replacement
        while cursor in mapping:
            cursor = mapping[cursor]
            if cursor == original:
                raise IntegrityError("correction would create a cycle")
        if cursor == original:
            raise IntegrityError("correction would create a cycle")
        return self.append("corrections", f"supersedes:{original.kind}:{original.record_id}",
                           {"reason": reason, "replacement": replacement.to_record()},
                           references=(original, replacement), supersedes=original)

    def latest(self, reference: LedgerRef) -> LedgerRef:
        self.read(reference)
        mapping = self._correction_map(self.scan())
        while reference in mapping:
            reference = mapping[reference]
        return reference

    def _existing(self, kind: str, logical_id: str) -> LedgerRef | None:
        record_id = digest({"kind": kind, "logical_id": logical_id})
        path = self._path(kind, record_id)
        if not path.exists() and not path.is_symlink():
            return None
        payload = read_receipt(path, max_bytes=MAX_RECORD_BYTES)
        ref = LedgerRef(kind, record_id, digest(payload))
        self.read(ref)
        return ref

    def record_input_capture(self, metadata: dict) -> LedgerRef:
        """Record an actual local input observation clock; never caller-backdate it.

        Source-access basis and content hashes remain explicit supplied assertions.
        This small metadata record contains no raw provider response for publication.
        """
        fields = {"id_namespace", "league", "event_id", "player_id", "event_starts_at",
                  "input_sha256", "source_version", "source_evidence_sha256", "access_basis"}
        if type(metadata) is not dict or set(metadata) != fields:
            raise IntegrityError("invalid input capture metadata schema")
        _nba_identity(metadata)
        for name in ("source_version", "access_basis"):
            _text(metadata[name], name)
        for name in ("input_sha256", "source_evidence_sha256"):
            _hash(metadata[name], name)
        logical = "input-capture:" + digest(metadata)
        existing = self._existing("input_captures", logical)
        if existing is not None:
            return existing
        if _now() >= utc(metadata["event_starts_at"]):
            raise IntegrityError("new real-time input capture must precede the event")
        capture = {"schema_version": "nba-input-capture-v1", **metadata,
                   "observed_at": stamp(_now())}
        capture = {"capture_id": digest(capture), **capture}
        return self.append("input_captures", logical,
                           {"identity": _nba_identity(metadata), "capture": capture})

    def record_research_inputs(self, pack: dict) -> LedgerRef:
        """Retain a normalized source package with an actual local receipt clock.

        Preparation packages may be recorded early. Only a fresh package received
        by T90 can support the separately versioned prospective issuer; this write
        alone never admits a forecast or establishes remote retention.
        """
        from .pregame_sources import validate_pack
        validate_pack(pack)
        return self.append("research_inputs", "research-inputs:" + digest(pack),
                           {"source_pack": pack})

    def issue_prospective(self, bundle: dict, *, reference, input_ref: LedgerRef) -> LedgerRef:
        """Persist a verified R1 pregame forecast, without loosening the R0 API.

        Original issued bodies remain recoverable and idempotent after the issue
        window. A new append must finish by T90+5 minutes and use normalized input
        evidence already received by T90. Actual event outcomes remain separate.
        """
        from .forecast_contract import validate_forecast
        from .prospective import verify_prospective
        now = _now()
        validate_forecast(bundle, now=now)
        if (bundle["schema_version"] != "nba-research-forecast-v2"
                or bundle["evidence_lane"] != "REAL_TIME_CAPTURED"
                or bundle["model_version"] != "nba_joint_empirical_pregame_r1_v1"):
            raise IntegrityError("prospective issuer requires its separately versioned R1 forecast")
        if reference is None:
            raise IntegrityError("the coherent prospective generator reference is required")
        if not isinstance(input_ref, LedgerRef) or input_ref.kind != "research_inputs":
            raise IntegrityError("prospective issuer requires an exact research input reference")
        source_payload = self.read(input_ref)
        pack = source_payload["data"]["source_pack"]
        producer_check = verify_prospective(bundle, reference, pack,
                                            input_record_id=input_ref.record_id)
        logical = "forecast:" + bundle["forecast_id"]
        existing = self._existing("forecasts", logical)
        if existing is not None:
            payload = self.read(existing)
            if (canonical(payload["data"]["bundle"]) != canonical(bundle)
                    or payload["references"] != [input_ref.to_record()]):
                raise IntegrityError("conflicting original prospective forecast body or inputs")
            return existing
        cutoff = utc(bundle["cutoff_at"])
        if not cutoff <= now <= cutoff + timedelta(minutes=5):
            raise IntegrityError("new prospective issuance is outside the T90 to T90+5 window")
        if utc(source_payload["received_at"]) > cutoff:
            raise IntegrityError("prospective inputs were not durably recorded by the cutoff")
        verification = {"schema_version": "nba-pregame-r1-verification-envelope-v1",
                        "forecast_id": bundle["forecast_id"], "forecast_sha256": digest(bundle),
                        "joint_sha256": bundle["joint_sha256"], "model_version": bundle["model_version"],
                        "verified_at": stamp(_now()), "producer_check": producer_check}
        data = {"identity": _nba_identity(bundle), "bundle": bundle,
                "producer_verification": verification}
        record_id = digest({"kind": "forecasts", "logical_id": logical})
        if self._verified_prospective_append is not None:
            raise IntegrityError("overlapping prospective writers are not supported")
        self._verified_prospective_append = (
            record_id, digest({"data": data, "references": [input_ref.to_record()]}))
        try:
            return self.append("forecasts", logical, data, references=(input_ref,))
        finally:
            self._verified_prospective_append = None

    def issue_forecast(self, bundle: dict, *, reference=None) -> LedgerRef:
        """Persist an already generated typed forecast with its original issuance.

        The current R0 producer supports reconstructed research only. Input capture
        metadata groundwork does not license relabeling this producer as real time.
        """
        from .forecast_contract import validate_forecast, verify_reference
        now = _now()
        validate_forecast(bundle, now=now)
        if reference is None:
            raise IntegrityError("the coherent generator reference is required for issuance")
        if bundle["evidence_lane"] != "RECONSTRUCTED_RESEARCH":
            raise IntegrityError("current R0 producer does not support REAL_TIME_CAPTURED issuance")
        producer_check = verify_reference(bundle, reference)
        logical = "forecast:" + bundle["forecast_id"]
        existing = self._existing("forecasts", logical)
        if existing is not None:
            self.scan()
            if canonical(self.read(existing)["data"]["bundle"]) != canonical(bundle):
                raise IntegrityError("conflicting original forecast body")
            return existing
        verification = {"schema_version": "nba-r0-verification-envelope-v1",
                        "forecast_id": bundle["forecast_id"], "forecast_sha256": digest(bundle),
                        "joint_sha256": bundle["joint_sha256"], "model_version": bundle["model_version"],
                        "verified_at": stamp(now), "producer_check": producer_check}
        return self.append("forecasts", logical,
                           {"identity": _nba_identity(bundle), "bundle": bundle,
                            "producer_verification": verification})

    def record_outcome(self, row, *, source_evidence_sha256: str,
                       source_observed_at: datetime) -> LedgerRef:
        """Normalize a retained source outcome without inventing a historical clock."""
        from .nba_data import NBAPlayerGame, audit_rows
        if not isinstance(row, NBAPlayerGame):
            raise IntegrityError("outcome requires a validated NBAPlayerGame")
        if row.id_namespace != "espn":
            raise IntegrityError("outcome requires explicit ESPN identities; crosswalk other sources first")
        if audit_rows([row])["identity_failures"]:
            raise IntegrityError("outcome line fails scoring/rebound/attempt reconciliation")
        _hash(source_evidence_sha256, "source_evidence_sha256")
        observed_at = utc(source_observed_at)
        if observed_at > _now():
            raise IntegrityError("source observation cannot be in the future")
        identity = {"id_namespace": row.id_namespace, "league": "NBA", "event_id": row.event_id,
                    "player_id": row.player_id, "event_starts_at": stamp(row.event_start)}
        primitives = None
        status = "UNRESOLVED"
        if row.final_status == "FINAL":
            if observed_at < row.event_start:
                raise IntegrityError("a final outcome cannot be observed before the event")
            if row.participation == "DNP":
                status = "DNP"
            elif row.participation == "APPEARED":
                fields = {"FGM": "fgm", "FG2M": "fg2m", "FG3M": "fg3m", "FTM": "ftm",
                          "PTS": "points", "REB": "rebounds", "AST": "assists", "TOV": "turnovers",
                          "BLK": "blocks", "STL": "steals"}
                candidate = {key: getattr(row, value) for key, value in fields.items()}
                if all(type(value) is int and value >= 0 for value in candidate.values()):
                    primitives, status = candidate, "FINAL_APPEARANCE"
        outcome = {"schema_version": "nba-research-outcome-v1", **identity,
                   "team_id": row.team_id, "opponent_id": row.opponent_id,
                   "period": "full_game", "extra_time_policy": "includes_overtime",
                   "observed_at": stamp(observed_at), "source_evidence_sha256": source_evidence_sha256,
                   "status": status, "primitives": primitives,
                   "categories": _outcome_categories(primitives) if primitives is not None else []}
        outcome = {"outcome_id": digest(outcome), **outcome}
        validate_outcome(outcome)
        return self.append("outcomes", "outcome:" + outcome["outcome_id"],
                           {"identity": _nba_identity(identity), "outcome": outcome})

    def grade_forecast(self, forecast_ref: LedgerRef, outcome_ref: LedgerRef) -> LedgerRef:
        if forecast_ref.kind != "forecasts" or outcome_ref.kind != "outcomes":
            raise IntegrityError("grading requires exact forecast and outcome references")
        forecast = self.read(forecast_ref)["data"]["bundle"]
        outcome = self.read(outcome_ref)["data"]["outcome"]
        logical = f"forecast-grade:{forecast_ref.record_id}:{outcome_ref.record_id}"
        existing = self._existing("grades", logical)
        if existing is not None:
            validate_grade(self.read(existing)["data"]["grade"], forecast, outcome)
            return existing
        grade = _grade_body(forecast, outcome, stamp(_now()))
        validate_grade(grade, forecast, outcome)
        return self.append("grades", logical,
                           {"identity": _nba_identity(forecast), "grade": grade,
                            "financial_status": FINANCIAL_STATUS},
                           references=(forecast_ref, outcome_ref))

    def iter_forecasts(self):
        for payload in self.scan()["forecasts"].values():
            if "bundle" in payload["data"]:
                yield payload["data"]["bundle"]

    def iter_grades(self):
        for payload in self.scan()["grades"].values():
            if "grade" in payload["data"]:
                yield payload["data"]["grade"]

    def iter_active_forecasts(self):
        """Publication view: preserve history on disk, omit superseded forecasts."""
        index = self.scan()
        superseded = self._correction_map(index)
        for record_id, payload in index["forecasts"].items():
            ref = LedgerRef("forecasts", record_id, digest(payload))
            if ref not in superseded and "bundle" in payload["data"]:
                yield payload["data"]["bundle"]

    def iter_active_grades(self):
        """Omit superseded grades and scores depending on replaced evidence.

        An outcome or forecast correction makes its old score historical until a
        new grade is explicitly appended. No implicit in-place regrading occurs.
        """
        index = self.scan()
        superseded = self._correction_map(index)
        for record_id, payload in index["grades"].items():
            ref = LedgerRef("grades", record_id, digest(payload))
            dependencies = [LedgerRef.from_record(item) for item in payload["references"]]
            if (ref not in superseded and not any(item in superseded for item in dependencies)
                    and "grade" in payload["data"]):
                yield payload["data"]["grade"]


def _nba_identity(body: dict) -> dict:
    if body.get("id_namespace") != "espn" or body.get("league") != "NBA":
        raise IntegrityError("explicit ESPN NBA identity is required")
    for name in ("event_id", "player_id"):
        _text(body.get(name), name)
    return {"id_namespace": "espn", "league": "NBA", "event_id": body["event_id"],
            "player_id": body["player_id"], "event_starts_at": stamp(utc(body["event_starts_at"]))}


def _outcome_categories(primitives: dict) -> list[dict]:
    from .basketball import BasketballDraw
    from .forecast_contract import UNITS
    expected = {"FGM", "FG2M", "FG3M", "FTM", "PTS", "REB", "AST", "TOV", "BLK", "STL"}
    if (type(primitives) is not dict or set(primitives) != expected
            or any(type(value) is not int or value < 0 for value in primitives.values())
            or primitives["FGM"] != primitives["FG2M"] + primitives["FG3M"]
            or primitives["PTS"] != 2*primitives["FG2M"] + 3*primitives["FG3M"] + primitives["FTM"]):
        raise IntegrityError("outcome requires a coherent nonnegative scoring primitive line")
    values = BasketballDraw(points=primitives["PTS"], rebounds=primitives["REB"],
                            assists=primitives["AST"], threes_made=primitives["FG3M"],
                            turnovers=primitives["TOV"], blocks=primitives["BLK"],
                            steals=primitives["STL"]).market_values()
    return [{"code": code, "units": UNITS[code], "observed": value} for code, value in values.items()]


def validate_capture(body: dict, *, received_at: datetime) -> dict:
    fields = {"schema_version", "capture_id", "id_namespace", "league", "event_id", "player_id",
              "event_starts_at", "input_sha256", "source_version", "source_evidence_sha256",
              "access_basis", "observed_at"}
    if type(body) is not dict or set(body) != fields or body["schema_version"] != "nba-input-capture-v1":
        raise IntegrityError("invalid input capture schema")
    _nba_identity(body)
    for name in ("source_version", "access_basis"):
        _text(body[name], name)
    for name in ("capture_id", "input_sha256", "source_evidence_sha256"):
        _hash(body[name], name)
    if body["capture_id"] != digest({k: v for k, v in body.items() if k != "capture_id"}):
        raise IntegrityError("input capture hash mismatch")
    observed, start = _wire_time(body["observed_at"]), _wire_time(body["event_starts_at"])
    if not timedelta(0) <= utc(received_at)-observed <= timedelta(seconds=2) or observed >= start:
        raise IntegrityError("input capture observation must bind actual receipt creation before the event")
    return body


def validate_outcome(body: dict) -> dict:
    fields = {"schema_version", "outcome_id", "id_namespace", "league", "event_id", "player_id",
              "event_starts_at", "team_id", "opponent_id", "period", "extra_time_policy", "observed_at",
              "source_evidence_sha256", "status", "primitives", "categories"}
    if type(body) is not dict or set(body) != fields or body["schema_version"] != "nba-research-outcome-v1":
        raise IntegrityError("invalid outcome schema")
    _nba_identity(body)
    for name in ("team_id", "opponent_id"):
        _text(body[name], name)
    if (body["team_id"] == body["opponent_id"] or body["period"] != "full_game"
            or body["extra_time_policy"] != "includes_overtime"):
        raise IntegrityError("unsupported outcome identity or period")
    _hash(body["outcome_id"], "outcome_id")
    _hash(body["source_evidence_sha256"], "source_evidence_sha256")
    if body["outcome_id"] != digest({k: v for k, v in body.items() if k != "outcome_id"}):
        raise IntegrityError("outcome content hash mismatch")
    _wire_time(body["event_starts_at"])
    observed = _wire_time(body["observed_at"])
    if observed > _now():
        raise IntegrityError("outcome observation is in the future")
    if body["status"] not in {"FINAL_APPEARANCE", "DNP", "UNRESOLVED"}:
        raise IntegrityError("unsupported outcome status")
    if body["status"] != "UNRESOLVED" and observed < utc(body["event_starts_at"]):
        raise IntegrityError("final outcome observation precedes event")
    if body["status"] == "FINAL_APPEARANCE":
        if body["categories"] != _outcome_categories(body["primitives"]):
            raise IntegrityError("outcome categories do not match the primitive line")
    elif body["primitives"] is not None or body["categories"] != []:
        raise IntegrityError("DNP/unresolved cannot be statistical zero outcomes")
    return body


def _number_text(number: Decimal) -> str:
    if not number.is_finite() or number < 0:
        raise IntegrityError("grade scores must be finite and nonnegative")
    if number == 0:
        return "0"
    return format(number, "f").rstrip("0").rstrip(".") if number.as_tuple().exponent < 0 else format(number, "f")


def _decimal_score(value: Any) -> Decimal:
    if type(value) is not str or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value):
        raise IntegrityError("score must be a nonnegative fixed-point decimal string")
    result = Decimal(value)
    if not result.is_finite():
        raise IntegrityError("score must be finite")
    return result


def _score_categories(forecast: dict, outcome: dict) -> list[dict]:
    actual = {item["code"]: item for item in outcome["categories"]}
    result = []
    with localcontext() as context:
        context.prec = 50
        for category in forecast["categories"]:
            code = category["code"]
            if actual[code]["units"] != category["units"]:
                raise IntegrityError("forecast and outcome units differ")
            observed = actual[code]["observed"]
            pmf = {item["value"]: Decimal(item["probability"]) for item in category["pmf"]}
            absolute = sum((p*abs(value-observed) for value, p in pmf.items()), Decimal(0))
            cumulative = moment = pair_half = Decimal(0)
            for value, probability in sorted(pmf.items()):
                pair_half += probability*(value*cumulative-moment)
                cumulative += probability
                moment += value*probability
            crps = max(Decimal(0), absolute-pair_half)
            mass = pmf.get(observed, Decimal(0))
            brier = (pmf.get(1, Decimal(0))-observed)**2 if code in {"DD", "TD"} else None
            result.append({"code": code, "observed": observed, "crps": _number_text(crps),
                           "log_loss": _number_text(-mass.ln()) if mass else None,
                           "log_loss_status": "FINITE" if mass else "ZERO_SUPPORT",
                           "brier": _number_text(brier) if brier is not None else None})
    return result


def _grade_body(forecast: dict, outcome: dict, graded_at: str) -> dict:
    from .forecast_contract import validate_forecast
    validate_forecast(forecast)
    validate_outcome(outcome)
    if (_nba_identity(forecast) != _nba_identity(outcome)
            or forecast["team_id"] != outcome["team_id"]
            or forecast["opponent_id"] != outcome["opponent_id"]):
        raise IntegrityError("forecast and outcome target identity mismatch")
    if utc(graded_at) < max(utc(forecast["issued_at"]), utc(outcome["observed_at"])):
        raise IntegrityError("grade cannot precede forecast issuance or observed outcome")
    status = {"FINAL_APPEARANCE": "SCORED", "DNP": "DNP_NOT_SCORED", "UNRESOLVED": "UNRESOLVED"}[outcome["status"]]
    grade = {"schema_version": "nba-forecast-grade-v1", "forecast_id": forecast["forecast_id"],
             "outcome_id": outcome["outcome_id"], **{k: forecast[k] for k in (
                 "id_namespace", "league", "event_id", "player_id")},
             "graded_at": graded_at, "status": status, "evidence_lane": forecast["evidence_lane"],
             "categories": _score_categories(forecast, outcome) if status == "SCORED" else [],
             "financial_settlement": "NOT_EVALUATED"}
    return {"grade_id": digest(grade), **grade}


def validate_grade(body: dict, forecast: dict | None = None, outcome: dict | None = None) -> dict:
    """Validate public grade identity/hash/clocks; recompute when evidence supplied."""
    from .forecast_contract import UNITS, validate_forecast
    fields = {"schema_version", "grade_id", "forecast_id", "outcome_id", "id_namespace", "league",
              "event_id", "player_id", "graded_at", "status", "evidence_lane", "categories", "financial_settlement"}
    if type(body) is not dict or set(body) != fields or body["schema_version"] != "nba-forecast-grade-v1":
        raise IntegrityError("invalid grade schema")
    for name in ("grade_id", "forecast_id", "outcome_id"):
        _hash(body[name], name)
    for name in ("event_id", "player_id"):
        _text(body[name], name)
    if (body["id_namespace"] != "espn" or body["league"] != "NBA"
            or body["financial_settlement"] != "NOT_EVALUATED"
            or body["evidence_lane"] not in {"RECONSTRUCTED_RESEARCH", "REAL_TIME_CAPTURED"}
            or body["status"] not in {"SCORED", "DNP_NOT_SCORED", "UNRESOLVED"}):
        raise IntegrityError("unsupported grade identity/status")
    if body["grade_id"] != digest({k: v for k, v in body.items() if k != "grade_id"}):
        raise IntegrityError("grade content hash mismatch")
    if _wire_time(body["graded_at"]) > _now():
        raise IntegrityError("grade clock is in the future")
    if type(body["categories"]) is not list:
        raise IntegrityError("grade categories must be a list")
    if body["status"] != "SCORED":
        if body["categories"]:
            raise IntegrityError("DNP/unresolved grade cannot contain statistical scores")
    else:
        codes = []
        for row in body["categories"]:
            if type(row) is not dict or set(row) != {"code", "observed", "crps", "log_loss", "log_loss_status", "brier"}:
                raise IntegrityError("invalid grade category schema")
            code = row["code"]
            codes.append(code)
            if (code not in UNITS or type(row["observed"]) is not int or row["observed"] < 0
                    or code in {"DD", "TD"} and row["observed"] not in {0, 1}):
                raise IntegrityError("invalid grade target/observation")
            _decimal_score(row["crps"])
            if row["log_loss_status"] == "FINITE":
                _decimal_score(row["log_loss"])
            elif row["log_loss_status"] != "ZERO_SUPPORT" or row["log_loss"] is not None:
                raise IntegrityError("invalid log-loss status")
            if code in {"DD", "TD"}:
                if _decimal_score(row["brier"]) > 1:
                    raise IntegrityError("binary Brier score outside [0,1]")
            elif row["brier"] is not None:
                raise IntegrityError("count category has no declared binary threshold Brier score")
        if len(codes) != len(UNITS) or set(codes) != set(UNITS):
            raise IntegrityError("scored grade requires every category exactly once")
    if forecast is not None:
        validate_forecast(forecast, now=_now())
        if (body["forecast_id"] != forecast["forecast_id"]
                or any(body[name] != forecast[name] for name in ("id_namespace", "league", "event_id", "player_id", "evidence_lane"))
                or utc(body["graded_at"]) < utc(forecast["issued_at"])):
            raise IntegrityError("grade forecast identity or issuance mismatch")
        if body["status"] != "UNRESOLVED" and utc(body["graded_at"]) < utc(forecast["event_starts_at"]):
            raise IntegrityError("final grade precedes the event")
        if body["status"] == "SCORED":
            observed = {"categories": [{"code": row["code"], "units": UNITS[row["code"]],
                                         "observed": row["observed"]} for row in body["categories"]]}
            calculated = {row["code"]: row for row in _score_categories(forecast, observed)}
            for supplied in body["categories"]:
                expected = calculated[supplied["code"]]
                if supplied["log_loss_status"] != expected["log_loss_status"]:
                    raise IntegrityError("grade log-loss status does not match its forecast PMF")
                for field in ("crps", "log_loss", "brier"):
                    if expected[field] is None:
                        if supplied[field] is not None:
                            raise IntegrityError("grade score does not match its forecast PMF")
                    elif (supplied[field] is None or
                          abs(_decimal_score(supplied[field]) - Decimal(expected[field])) > Decimal("0.000000001")):
                        raise IntegrityError("grade score does not match its forecast PMF")
    if outcome is not None:
        validate_outcome(outcome)
        expected_status = {"FINAL_APPEARANCE": "SCORED", "DNP": "DNP_NOT_SCORED", "UNRESOLVED": "UNRESOLVED"}[outcome["status"]]
        if (body["outcome_id"] != outcome["outcome_id"] or body["status"] != expected_status
                or any(body[name] != outcome[name] for name in ("id_namespace", "league", "event_id", "player_id"))
                or utc(body["graded_at"]) < utc(outcome["observed_at"])):
            raise IntegrityError("grade outcome identity, status or observation clock mismatch")
    if forecast is not None and outcome is not None:
        if canonical(body) != canonical(_grade_body(forecast, outcome, body["graded_at"])):
            raise IntegrityError("grade does not reproduce from the exact forecast/outcome evidence")
    return body

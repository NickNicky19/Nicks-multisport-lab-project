"""Create-only storage for bounded daily planning, never forecast issuance.

The generic ledger supplies immutable receipts and reference checks.  This
adapter separately validates every supported body and replays plans against the
retained publisher bytes.  Its shared planning pool protects the complete first
cycle's existing reservation; another namespace does not reset project limits.
No HTTP requests, models, schedulers or prospective writes are implemented here.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat
import zlib

from .integrity import (HASH_FORMAT, RECEIPT_SCHEMA, IntegrityError, canonical,
                        digest, stamp, utc)
from .ledger import Ledger, LedgerRef, KINDS, SCHEMA, MAX_RECORD_BYTES
from . import sdv_recurring_plan as planning
from .sdv_daily_store import _validate_asset

PROTOCOL_ID = planning.PROTOCOL_ID
SOURCE_SCHEMA = "nba-sdv-recurring-source-pack-v1"
BUDGET_SCHEMA = "nba-sdv-recurring-retention-budget-v1"
MAX_LEDGER_RECORDS = 512
MAX_LEDGER_BYTES = 32 * 1024 * 1024
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_METADATA_BYTES = 256 * 1024
MAX_PLANNING_RECORDS = 64
MAX_PLANNING_BYTES = 2 * 1024 * 1024
PROTECTED_FIRST_RECORDS = 155
PROTECTED_FIRST_BYTES = 31_431_880
MAX_RESERVATION_BYTES = 8 * 1024
MAX_PLAN_BYTES = 512 * 1024


def _now():
    return datetime.now(timezone.utc)


def require(ok, message):
    if not ok:
        raise IntegrityError(message)


def _seal(body, key):
    return {**body, key: digest(body)}


def _checked(function, *args, **kwargs):
    """Turn malformed external contracts into explicit integrity failures."""
    try:
        return function(*args, **kwargs)
    except IntegrityError:
        raise
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, OverflowError, OSError) as exc:
        raise IntegrityError("Malformed recurring typed contract") from exc


def _budget():
    return _seal({"schema_version": BUDGET_SCHEMA, "protocol_id": PROTOCOL_ID,
        "scope": "PLANNING_ONLY_SHARED_POOL", "maximum_records": MAX_PLANNING_RECORDS,
        "maximum_encoded_bytes": MAX_PLANNING_BYTES,
        "protected_first_cycle_records": PROTECTED_FIRST_RECORDS,
        "protected_first_cycle_bytes": PROTECTED_FIRST_BYTES,
        "global_maximum_records": MAX_LEDGER_RECORDS,
        "global_maximum_bytes": MAX_LEDGER_BYTES,
        "issuance_authority": "NONE_PLANNING_ONLY"}, "budget_id")


def _path(root):
    root = Path(root).absolute()
    for item in (root, *root.parents):
        require(not item.is_symlink(), "Recurring storage cannot traverse symlinks")
    return root


def _inventory(root):
    """Count receipts, including interrupted unpublished files, before decoding."""
    count = size = 0
    records = root / "records"
    require(not records.is_symlink(), "Recurring inventory directory is a symlink")
    if not records.exists():
        return count, size
    require(records.is_dir(), "Recurring records path is not a directory")
    require(set(item.name for item in records.iterdir()) <= {*KINDS, "README.md"},
            "Unrecognized recurring ledger directory")
    notice = records / "README.md"
    if notice.exists() or notice.is_symlink():
        require(not notice.is_symlink() and notice.is_file(), "Unsafe ledger documentation path")
    for kind in KINDS:
        directory = records / kind
        require(not directory.is_symlink(), "Recurring inventory kind is a symlink")
        if not directory.exists():
            continue
        require(directory.is_dir(), "Recurring inventory kind is not a directory")
        with os.scandir(directory) as entries:
            for item in entries:
                require(re.fullmatch(r"[a-f0-9]{64}\.json", item.name) is not None
                        or item.name.startswith(".receipt-"),
                        "Unrecognized file in recurring ledger inventory")
                info = item.stat(follow_symlinks=False)
                require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= MAX_RECORD_BYTES,
                        "Recurring inventory contains an unsafe or oversized receipt")
                count += 1
                size += info.st_size
                require(count <= MAX_LEDGER_RECORDS and size <= MAX_LEDGER_BYTES,
                        "Recurring inventory exceeds the unchanged ledger limits")
    return count, size


def _encoded_size(kind, logical_id, data, references):
    payload = {"schema_version": SCHEMA, "kind": kind,
        "record_id": digest({"kind": kind, "logical_id": logical_id}),
        "logical_id": logical_id, "received_at": stamp(_now()), "data": data,
        "references": [ref.to_record() for ref in references], "supersedes": None,
        "persistence_status": "LOCAL_RECEIPT_ONLY"}
    envelope = {"schema_version": RECEIPT_SCHEMA, "hash_format": HASH_FORMAT,
        "payload_sha256": digest(payload), "payload": payload}
    return len(canonical(envelope))


def _source_logical(body):
    metadata = body["metadata"]
    return ("sdv-recurring-source:" + metadata["role"] + ":"
            + str(metadata["asset_id"]) + ":" + metadata["asset_sha256"])


def _identity(body):
    schema = body["schema_version"]
    if schema == SOURCE_SCHEMA:
        metadata = body["metadata"]
        return {"protocol_id": PROTOCOL_ID, "role": metadata["role"],
                "provider_asset_id": metadata["asset_id"],
                "asset_sha256": metadata["asset_sha256"]}
    if schema == planning.RESERVATION_SCHEMA:
        return {"protocol_id": PROTOCOL_ID, "first_game_date": body["first_game_date"]}
    return {"protocol_id": PROTOCOL_ID, "game_date": body["game_date"]}


class RecurringStore:
    """One seven-day planning reservation and its exact originals, bounded anew.

    Only this adapter grants typed planning validity.  Generic Ledger records are
    not prospective forecasts and cannot bypass its closed schema registry.
    """

    def __init__(self, project_root):
        self.project_root = _path(project_root)
        self.root = _path(self.project_root / "recurring")
        self.ledger = Ledger(self.root)
        self.parent = Ledger(self.project_root)

    @contextmanager
    def lock(self):
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / ".writer.lock"
        require(not lock_path.is_symlink(), "Recurring writer lock is a symlink")
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def capacity(self):
        original_count, original_size = _inventory(self.project_root)
        daily_count, daily_size = _inventory(_path(self.project_root / "daily"))
        count, size = _inventory(self.root)
        protected_count = max(original_count + daily_count, PROTECTED_FIRST_RECORDS)
        protected_size = max(original_size + daily_size, PROTECTED_FIRST_BYTES)
        remaining_count = MAX_PLANNING_RECORDS - count
        remaining_size = MAX_PLANNING_BYTES - size
        projected_count = protected_count + count + max(0, remaining_count)
        projected_size = protected_size + size + max(0, remaining_size)
        return {"schema_version": "nba-sdv-recurring-capacity-v1",
            "scope": "PLANNING_ONLY_NO_FORECAST_RESERVE", "budget": _budget(),
            "existing_records": original_count + daily_count + count,
            "existing_bytes": original_size + daily_size + size,
            "protected_existing_records": original_count + daily_count,
            "protected_existing_bytes": original_size + daily_size,
            "protected_reserved_records": protected_count, "protected_reserved_bytes": protected_size,
            "planning_records": count, "planning_bytes": size,
            "remaining_records": max(0, remaining_count), "remaining_bytes": max(0, remaining_size),
            "maximum_projected_records": projected_count,
            "maximum_projected_bytes": projected_size,
            "maximum_records": MAX_LEDGER_RECORDS, "maximum_bytes": MAX_LEDGER_BYTES,
            "fits": remaining_count >= 0 and remaining_size >= 0
                and projected_count <= MAX_LEDGER_RECORDS and projected_size <= MAX_LEDGER_BYTES}

    def _require_capacity(self, *, additional_count=0, additional_bytes=0):
        report = self.capacity()
        require(report["fits"] and additional_count <= report["remaining_records"]
                and additional_bytes <= report["remaining_bytes"],
                "Recurring planning pool or protected combined ledger budget is exhausted")
        return report

    def _load(self):
        self._require_capacity()
        index = self.ledger.scan()
        payloads = [payload for rows in index.values() for payload in rows.values()]
        by_ref = {LedgerRef(payload["kind"], payload["record_id"], digest(payload)): payload
                  for payload in payloads}
        reservations = []
        for payload in payloads:
            data = payload["data"]
            require(type(data) is dict and type(data.get("sdv_recurring")) is dict,
                    "Unknown generic record cannot establish recurring planning validity")
            body = data["sdv_recurring"]
            require(body.get("protocol_id") == PROTOCOL_ID
                    and body.get("schema_version") in {SOURCE_SCHEMA,
                        planning.RESERVATION_SCHEMA, planning.PLAN_SCHEMA},
                    "Recurring store admits only reservation, source pack and plan bodies")
            if body["schema_version"] == planning.RESERVATION_SCHEMA:
                _checked(planning.validate_reservation, body)
            elif body["schema_version"] == planning.PLAN_SCHEMA:
                _checked(planning.validate_plan, body)
            else:
                _checked(_validate_asset, body)
            require(data.get("identity") == _identity(body), "Recurring record identity differs")
            if body["schema_version"] == planning.RESERVATION_SCHEMA:
                require(set(data) == {"identity", "sdv_recurring", "history_ref", "retention_budget"}
                        and data["retention_budget"] == _budget(),
                        "Recurring reservation retention budget changed")
                history = LedgerRef.from_record(data["history_ref"])
                require(history.kind == "research_inputs" and history.record_id == body["history_record_id"],
                        "Recurring reservation changed the fixed parent history reference")
                retained = self.parent.read(history)
                require(utc(retained["received_at"]) <= utc(body["registered_at"]),
                        "Recurring history was not retained before its reservation")
                require(payload["kind"] == "input_captures" and not payload["references"]
                        and payload["logical_id"] == "sdv-recurring-reservation:" + PROTOCOL_ID
                            + ":" + body["first_game_date"], "Recurring reservation identity differs")
                require(utc(body["registered_at"]) <= utc(payload["received_at"])
                        < planning.planning_window(body["first_game_date"])[0],
                        "Recurring reservation was not retained before planning opened")
                reservations.append((LedgerRef(payload["kind"], payload["record_id"], digest(payload)), body))
            else:
                require(set(data) == {"identity", "sdv_recurring"}, "Unknown recurring wrapper fields")
        require(len(reservations) <= 1, "This bounded store supports one planning reservation")
        require(not payloads or len(reservations) == 1, "Recurring records lack their original reservation")
        reservation_ref, reservation = reservations[0] if reservations else (None, None)
        sources, plans = [], []
        for ref, payload in by_ref.items():
            body = payload["data"]["sdv_recurring"]
            schema = body["schema_version"]
            references = [LedgerRef.from_record(item) for item in payload["references"]]
            if schema == SOURCE_SCHEMA:
                require(payload["kind"] == "input_captures" and references == [reservation_ref]
                        and payload["logical_id"] == _source_logical(body),
                        "Recurring source pack reference or logical identity differs")
                require(body.get("asset_id") == digest({k: v for k, v in body.items() if k != "asset_id"}),
                        "Recurring source pack checksum differs")
                _, metadata, metadata_raw = _checked(_validate_asset, body)
                require(len(metadata_raw) <= MAX_METADATA_BYTES
                        and utc(metadata["retrieved_at"]) <= utc(payload["received_at"]),
                        "Recurring source original exceeds metadata bound or postdates retention")
                sources.append((ref, body))
            elif schema == planning.PLAN_SCHEMA:
                require(payload["kind"] == "input_captures" and len(references) == 3
                        and references[0] == reservation_ref
                        and payload["logical_id"] == "sdv-recurring-plan:" + PROTOCOL_ID
                            + ":" + body["game_date"], "Recurring plan references or date identity differ")
                require(body["reservation"] == reservation
                        and utc(body["planned_at"]) <= utc(payload["received_at"]),
                        "Recurring plan differs from retained reservation or persistence clock")
                raw_sources = []
                for target in references[1:]:
                    original = by_ref.get(target)
                    require(original is not None and original["data"]["sdv_recurring"]["schema_version"] == SOURCE_SCHEMA,
                            "Recurring plan lacks an authenticated source pack")
                    raw_sources.append(_checked(_validate_asset, original["data"]["sdv_recurring"]))
                require([row[1]["role"] for row in raw_sources] == ["schedule", "roster"],
                        "Recurring plan source roles are missing or reordered")
                _checked(planning.verify_plan_sources, body, raw_sources[0][0], raw_sources[1][0],
                    raw_sources[0][1], raw_sources[1][1], source_originals={
                        "schedule": raw_sources[0][2], "roster": raw_sources[1][2]})
                plans.append((ref, body))
            ceiling = (MAX_RESERVATION_BYTES if schema == planning.RESERVATION_SCHEMA
                       else MAX_PLAN_BYTES if schema == planning.PLAN_SCHEMA else MAX_RECORD_BYTES)
            path = self.root / "records" / ref.kind / (ref.record_id + ".json")
            require(path.stat().st_size <= ceiling, "Recurring encoded envelope exceeds its typed ceiling")
        return {"reservation": reservations[0] if reservations else None,
                "source_packs": sources, "plans": plans, "records": [
                    (ref, payload["data"]["sdv_recurring"]) for ref, payload in by_ref.items()],
                "capacity": self.capacity(), "genuine_forecasts": 0,
                "local_persistence_completion": "NOT_ESTABLISHED_BY_RECEIPT_CLOCK",
                "prospective_admission": False}

    def recover(self):
        with self.lock():
            return _checked(self._load)

    def records(self):
        return self.recover()["records"]

    def _append(self, kind, logical_id, data, *, references=(), ceiling):
        # Existing originals are read through append's byte/semantic comparison,
        # so exact retries do not require another reserved record or new clock.
        target = self.root / "records" / kind / (digest({"kind": kind, "logical_id": logical_id}) + ".json")
        size = _encoded_size(kind, logical_id, data, references)
        require(size <= ceiling, "Recurring encoded envelope exceeds its typed ceiling")
        self._require_capacity(additional_count=0 if target.exists() else 1,
                               additional_bytes=0 if target.exists() else size)
        ref = self.ledger.append(kind, logical_id, data, references=tuple(references))
        self._load()
        return ref

    def persist_reservation(self, body, history_ref):
        _checked(planning.validate_reservation, body)
        require(isinstance(history_ref, LedgerRef) and history_ref.kind == "research_inputs"
                and history_ref.record_id == body["history_record_id"],
                "Recurring reservation requires the exact original parent history")
        retained = _checked(self.parent.read, history_ref)
        require(utc(retained["received_at"]) <= utc(body["registered_at"]),
                "Recurring history was not retained before its reservation")
        with self.lock():
            current = self._load()["reservation"]
            require(current is None or current[1] == body,
                    "This bounded store already retains a different planning reservation")
            require(current is not None or utc(body["registered_at"]) <= _now()
                    < planning.planning_window(body["first_game_date"])[0],
                    "Recurring reservation must be retained before planning opens")
            return self._append("input_captures", "sdv-recurring-reservation:" + PROTOCOL_ID
                + ":" + body["first_game_date"], {"identity": _identity(body),
                    "sdv_recurring": body, "history_ref": history_ref.to_record(),
                    "retention_budget": _budget()}, ceiling=MAX_RESERVATION_BYTES)

    def retain_source_pack(self, raw, metadata, metadata_raw):
        require(type(raw) is bytes and 0 < len(raw) <= MAX_SOURCE_BYTES,
                "Recurring raw source exceeds unchanged 2-MiB limit")
        require(type(metadata_raw) is bytes and 0 < len(metadata_raw) <= MAX_METADATA_BYTES,
                "Recurring publisher metadata exceeds unchanged 256-KiB limit")
        body = _seal({"schema_version": SOURCE_SCHEMA, "protocol_id": PROTOCOL_ID,
            "metadata": metadata, "encoding": "ZLIB_BASE64_EXACT_ORIGINAL_BYTES",
            "raw_base64": base64.b64encode(zlib.compress(raw, 9)).decode("ascii"),
            "metadata_raw_base64": base64.b64encode(zlib.compress(metadata_raw, 9)).decode("ascii"),
            "metadata_raw_bytes": len(metadata_raw),
            "metadata_raw_sha256": hashlib.sha256(metadata_raw).hexdigest()}, "asset_id")
        _checked(_validate_asset, body)
        with self.lock():
            reservation = self._load()["reservation"]
            require(reservation is not None, "Retain the planning reservation before source packs")
            return self._append("input_captures", _source_logical(body),
                {"identity": _identity(body), "sdv_recurring": body},
                references=(reservation[0],), ceiling=MAX_RECORD_BYTES)

    def read_source_pack(self, reference):
        require(isinstance(reference, LedgerRef), "Recurring source needs a complete ledger reference")
        with self.lock():
            candidates = {ref: body for ref, body in self._load()["source_packs"]}
            require(reference in candidates, "Missing or changed recurring source pack")
            return _checked(_validate_asset, candidates[reference])

    def persist_plan(self, body, source_refs):
        _checked(planning.validate_plan, body)
        require(type(source_refs) in {tuple, list}, "Recurring plan source references must be a bounded sequence")
        refs = tuple(source_refs)
        require(len(refs) == 2 and all(isinstance(ref, LedgerRef) for ref in refs)
                and len(set(refs)) == 2, "Recurring plan requires two exact source references")
        with self.lock():
            current = self._load()
            reservation = current["reservation"]
            require(reservation is not None and reservation[1] == body["reservation"],
                    "Recurring plan requires its retained original reservation")
            candidates = dict(current["source_packs"])
            require(all(ref in candidates for ref in refs), "Recurring plan source reference is missing or changed")
            originals = [_checked(_validate_asset, candidates[ref]) for ref in refs]
            require([row[1]["role"] for row in originals] == ["schedule", "roster"],
                    "Recurring plan source roles differ")
            _checked(planning.verify_plan_sources, body, originals[0][0], originals[1][0],
                originals[0][1], originals[1][1], source_originals={
                    "schedule": originals[0][2], "roster": originals[1][2]})
            return self._append("input_captures", "sdv-recurring-plan:" + PROTOCOL_ID
                + ":" + body["game_date"], {"identity": _identity(body), "sdv_recurring": body},
                references=(reservation[0], *refs), ceiling=MAX_PLAN_BYTES)

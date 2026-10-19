"""Small, provider-independent decoded-JSON integrity and receipt primitives.

The hash format fingerprints canonical decoded JSON, not raw HTTP wire bytes.
A matching hash proves neither upstream authenticity nor pregame availability.
There are no providers, sports, models, schedules or prospective labels here.

Generic helpers were adapted from Nick's authored NFL reliability additions.
See docs/REUSE_PROVENANCE.md for pinned source and the deliberate hardening.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile
from typing import Any

HASH_FORMAT = "sha256-canonical-decoded-json-v1"
RECEIPT_SCHEMA = "decoded-json-receipt-v1"
MAX_RECEIPT_BYTES = 8 * 1024 * 1024


class IntegrityError(ValueError):
    """Malformed, ambiguous, conflicting or corrupted local evidence."""


def utc(value: str | datetime) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise IntegrityError("An explicit timezone is required")
    return value.astimezone(timezone.utc)


def stamp(value: datetime) -> str:
    return utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _require_json(value: Any) -> None:
    """Reject silent key coercion and non-finite numeric values recursively."""
    kind = type(value)
    if value is None or kind in (str, bool, int):
        return
    if kind is float:
        if not math.isfinite(value):
            raise IntegrityError("Non-finite JSON value")
        return
    if kind is list:
        for item in value:
            _require_json(item)
        return
    if kind is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise IntegrityError("JSON object keys must be strings")
            _require_json(item)
        return
    raise IntegrityError(f"Unsupported JSON value type: {kind.__name__}")


def canonical(value: Any) -> bytes:
    _require_json(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    """SHA-256 of canonical decoded JSON under HASH_FORMAT."""
    return hashlib.sha256(canonical(value)).hexdigest()


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise IntegrityError(f"Duplicate JSON key: {key}")
        out[key] = value
    return out


def _decode(raw: bytes) -> Any:
    def invalid(value):
        raise IntegrityError(f"Non-finite JSON value: {value}")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=invalid)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IntegrityError("Invalid UTF-8 JSON") from error
    # parse_constant does not catch an overflowing exponent such as 1e999.
    _require_json(value)
    return value


def _bounded_bytes(path: Path, max_bytes: int) -> bytes:
    if type(max_bytes) is not int or max_bytes <= 0:
        raise IntegrityError("A positive integer byte limit is required")
    if not stat.S_ISREG(path.lstat().st_mode):
        raise IntegrityError("Receipt input must be a regular file, not a symlink")
    with path.open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise IntegrityError("JSON input exceeds its byte limit")
    return raw


def load_json(path: Path | str, *, max_bytes: int = MAX_RECEIPT_BYTES) -> Any:
    """Read bounded UTF-8 JSON; duplicate keys and all non-finite values fail."""
    return _decode(_bounded_bytes(Path(path), max_bytes))


def read_receipt(path: Path | str, *, max_bytes: int = MAX_RECEIPT_BYTES) -> Any:
    """Verify a local envelope and return its payload without upgrading evidence."""
    envelope = load_json(path, max_bytes=max_bytes)
    fields = {"schema_version", "hash_format", "payload_sha256", "payload"}
    if (type(envelope) is not dict or set(envelope) != fields
            or envelope["schema_version"] != RECEIPT_SCHEMA
            or envelope["hash_format"] != HASH_FORMAT):
        raise IntegrityError("Unsupported receipt envelope or hash format")
    if envelope["payload_sha256"] != digest(envelope["payload"]):
        raise IntegrityError("Receipt payload checksum mismatch")
    return envelope["payload"]


def write_receipt(path: Path | str, payload: Any, *, max_bytes: int = MAX_RECEIPT_BYTES) -> bool:
    """Atomically create a receipt; return False only for an identical full payload.

    The destination is never replaced. Every payload field participates in the
    identity comparison, including rows, capture clocks and source/code metadata.
    Callers own their paths, clock provenance and source-access policy.
    """
    if type(max_bytes) is not int or max_bytes <= 0:
        raise IntegrityError("A positive integer byte limit is required")
    path = Path(path)
    envelope = {"schema_version": RECEIPT_SCHEMA, "hash_format": HASH_FORMAT,
                "payload_sha256": digest(payload), "payload": payload}
    raw = canonical(envelope)
    if len(raw) > max_bytes:
        raise IntegrityError("Receipt exceeds its byte limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".receipt-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            # Same-directory hard-link creation is atomic and cannot replace
            # another writer's destination. An existing corrupt file also fails.
            os.link(temporary, path)
        except FileExistsError:
            existing = read_receipt(path, max_bytes=max_bytes)
            if canonical(existing) != canonical(payload):
                raise IntegrityError("Conflicting receipt already exists")
            return False
    finally:
        Path(temporary).unlink(missing_ok=True)
    return True

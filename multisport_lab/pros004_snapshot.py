"""Offline, verified PROS004 diagnostic snapshots; never live admission.

The manifest binds exact receipt bytes and full retained references. A snapshot
may later be read from a separately fetched immutable Git tree, but this module
does not fetch, publish, issue, repair partial peers or assert remote durability.
Its output roots must be new directories outside Git worktrees. Interrupted
copies are retained and cannot be acknowledged or silently reused.

The zero genuine-issuance counter describes new issuance by this adapter.
Unrelated original records retain their own evidence lanes and original bytes;
copying them never reclassifies their original issuance or grading evidence.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess

from .integrity import IntegrityError, canonical, digest, read_receipt, write_receipt
from scripts.verify_pros004_readiness import (
    KINDS, MAX_BYTES, MAX_RECORDS, VerificationError, load_receipt, verify_store,
)

SCHEMA = "nba-pros004-diagnostic-snapshot-v1"
MODE = "READINESS_DIAGNOSTIC_NON_ISSUANCE"
MANIFEST = "pros004-snapshot.json"
MAX_MANIFEST_BYTES = 256*1024


class SnapshotError(IntegrityError):
    """A diagnostic copy cannot establish intact independent readback."""


def _require(condition, message):
    if not condition:
        raise SnapshotError(message)


def _path_root(value):
    path = Path(value).absolute()
    for ancestor in (path, *path.parents):
        _require(not ancestor.is_symlink(), "snapshot paths must not traverse symlinks")
    return path


def _new_root(value):
    path = _path_root(value)
    _require(not path.exists(), "snapshot/readback requires a new destination; retain interrupted copies")
    parent = path.parent
    while not parent.exists():
        parent = parent.parent
    result = subprocess.run(["git", "-C", str(parent), "rev-parse", "--show-toplevel"],
                            capture_output=True, text=True, check=False)
    _require(result.returncode != 0, "diagnostic snapshot output must be outside every Git worktree")
    path.mkdir(parents=True, mode=0o700)
    return path


def _strict_layout(root):
    root = _path_root(root)
    _require(root.is_dir(), "snapshot source must be an existing directory")
    folder = root/"records"
    _require(folder.is_dir() and not folder.is_symlink(), "snapshot source needs a regular records directory")
    for entry in folder.iterdir():
        if entry.name == "README.md":
            _require(stat.S_ISREG(entry.lstat().st_mode) and entry.stat().st_size <= 64*1024,
                     "ledger README must be bounded regular documentation")
            continue
        _require(entry.name in KINDS and entry.is_dir() and not entry.is_symlink(),
                 "unrecognized or symlinked ledger directory")
    files = []
    count = total = 0
    for kind in KINDS:
        directory = folder/kind
        if not directory.exists():
            continue
        for path in directory.iterdir():
            _require(stat.S_ISREG(path.lstat().st_mode), "snapshot records must be regular files")
            _require(re.fullmatch(r"[a-f0-9]{64}\.json", path.name) is not None,
                     "interrupted or unrecognized record cannot be acknowledged")
            count += 1
            total += path.stat().st_size
            _require(count <= MAX_RECORDS and total <= MAX_BYTES, "snapshot exceeds unchanged ledger capacity")
            files.append(path)
    return sorted(files)


def snapshot_manifest(source_root):
    """Independently validate every receipt, reference, clock and new forecast.

    No clocks are rewritten, and a missing model peer is preserved as missing.
    The independent checker admits only diagnostic new PROS004 records and
    counts unrelated original records without relabeling them.
    """
    root = _path_root(source_root)
    files = _strict_layout(root)
    try:
        verified = verify_store(root)
        entries = []
        for path in files:
            payload, raw_sha, size = load_receipt(path, maximum=4*1024*1024)
            entries.append({"path":path.relative_to(root).as_posix(),
                            "encoded_bytes":size,"raw_sha256":raw_sha,
                            "payload_sha256":digest(payload)})
    except (VerificationError, OSError, KeyError, TypeError) as error:
        raise SnapshotError("independent diagnostic snapshot verification failed: "+str(error)) from error
    _require(verified["records"] == len(entries) and
             verified["encoded_bytes"] == sum(item["encoded_bytes"] for item in entries),
             "source inventory changed during snapshot validation")
    body = {"schema_version":SCHEMA,"mode":MODE,"record_count":len(entries),
            "encoded_bytes":sum(item["encoded_bytes"] for item in entries),
            "global_record_limit":MAX_RECORDS,"global_byte_limit":MAX_BYTES,
            "entries":entries,"activation":False,"genuine_issuance":0,
            "remote_durability_established":False}
    return {**body,"manifest_id":digest(body)}


def _validate_manifest(body):
    fields = {"schema_version","mode","record_count","encoded_bytes","global_record_limit",
              "global_byte_limit","entries","activation","genuine_issuance",
              "remote_durability_established","manifest_id"}
    _require(type(body) is dict and set(body) == fields, "invalid diagnostic snapshot manifest")
    _require(body["schema_version"] == SCHEMA and body["mode"] == MODE and
             body["activation"] is False and type(body["genuine_issuance"]) is int and
             body["genuine_issuance"] == 0 and body["remote_durability_established"] is False,
             "snapshot cannot claim genuine issuance, activation or remote durability")
    _require(body["global_record_limit"] == MAX_RECORDS and body["global_byte_limit"] == MAX_BYTES,
             "snapshot ledger limits changed")
    entries = body["entries"]
    _require(type(entries) is list and len(entries) <= MAX_RECORDS, "invalid snapshot entry budget")
    previous = ""
    total = 0
    for entry in entries:
        _require(type(entry) is dict and set(entry) == {"path","encoded_bytes","raw_sha256","payload_sha256"},
                 "invalid snapshot entry")
        path = entry["path"]
        _require(type(path) is str and re.fullmatch(
            r"records/(?:"+"|".join(KINDS)+r")/[a-f0-9]{64}\.json", path) is not None and path > previous,
            "snapshot entries must have unique sorted safe ledger paths")
        previous = path
        _require(type(entry["encoded_bytes"]) is int and 0 < entry["encoded_bytes"] <= 4*1024*1024,
                 "invalid snapshot record size")
        for key in ("raw_sha256","payload_sha256"):
            _require(type(entry[key]) is str and re.fullmatch(r"[a-f0-9]{64}",entry[key]) is not None,
                     "invalid snapshot hash")
        total += entry["encoded_bytes"]
    _require(type(body["record_count"]) is int and body["record_count"] == len(entries) and
             type(body["encoded_bytes"]) is int and body["encoded_bytes"] == total <= MAX_BYTES,
             "snapshot count/byte totals conflict")
    _require(body["manifest_id"] == digest({k:v for k,v in body.items() if k != "manifest_id"}),
             "snapshot manifest identity changed")
    return body


def _copy_record(source, destination, entry):
    raw = source.read_bytes()
    _require(len(raw) == entry["encoded_bytes"] and
             hashlib.sha256(raw).hexdigest() == entry["raw_sha256"],
             "record changed while copying snapshot")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    # The fresh directory is owned by this one diagnostic writer. A failed copy
    # never obtains a complete manifest/readback acknowledgment.
    descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def export_snapshot(source_root, snapshot_root):
    """Create a fresh verified snapshot; retain any interrupted destination."""
    source = _path_root(source_root)
    manifest = snapshot_manifest(source)
    target = _path_root(snapshot_root)
    _require(not target.is_relative_to(source), "snapshot destination must not be inside source")
    target = _new_root(target)
    (target/"records").mkdir(exist_ok=True)
    for entry in manifest["entries"]:
        _copy_record(source/entry["path"], target/entry["path"], entry)
    _require(snapshot_manifest(target) == manifest and snapshot_manifest(source) == manifest,
             "source or copied diagnostic snapshot changed")
    write_receipt(target/MANIFEST, manifest, max_bytes=MAX_MANIFEST_BYTES)
    return manifest


def recover_snapshot(snapshot_root, destination_root):
    """Reopen exact originals into a fresh diagnostic root before acknowledgment.

    This is an offline copy/readback checkpoint. It never completes a missing
    model or admits live writes. A later remote adapter must verify its actual
    Git source commit and independent fetch separately.
    """
    source = _path_root(snapshot_root)
    _require(source.is_dir(), "snapshot directory is missing")
    _require({p.name for p in source.iterdir()} == {"records",MANIFEST},
             "snapshot is interrupted or has unrecognized entries")
    try:
        manifest = _validate_manifest(read_receipt(source/MANIFEST,max_bytes=MAX_MANIFEST_BYTES))
    except (IntegrityError, OSError, KeyError, TypeError) as error:
        raise SnapshotError("invalid or incomplete diagnostic snapshot: "+str(error)) from error
    _require(snapshot_manifest(source) == manifest, "snapshot bytes or retained inventory changed")
    target = _path_root(destination_root)
    _require(not target.is_relative_to(source), "readback destination must not be inside snapshot")
    target = _new_root(target)
    (target/"records").mkdir(exist_ok=True)
    for entry in manifest["entries"]:
        _copy_record(source/entry["path"], target/entry["path"], entry)
    _require(snapshot_manifest(target) == manifest and snapshot_manifest(source) == manifest,
             "readback bytes or retained inventory changed")
    ack = {"schema_version":"nba-pros004-diagnostic-readback-v1",
           "status":"PASS_VERIFIED_DIAGNOSTIC_READBACK","manifest_id":manifest["manifest_id"],
           "record_count":manifest["record_count"],"encoded_bytes":manifest["encoded_bytes"],
           "all_original_bytes_preserved":True,"activation":False,"genuine_issuance":0,
           "remote_durability_established":False,"missing_peers_repaired":False}
    write_receipt(target/"pros004-readback.json",ack,max_bytes=8192)
    return ack

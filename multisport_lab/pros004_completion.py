"""Append-only completion evidence for unchanged immutable ledger originals.

The journal occupies one explicitly budgeted metadata file. Its clocks observe
completed original persistence/readback operations; a pre-write received_at is
never evidence of completion. Missing or interrupted evidence fails closed.
Appending metadata is not itself an original forecast issuance or an activation.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from .integrity import IntegrityError, canonical, digest, stamp, utc
from .ledger import LedgerRef

JOURNAL_RELATIVE_PATH = "evidence/pros004/completion-journal.jsonl"
MAX_JOURNAL_BYTES = 2*1024*1024
MAX_JOURNAL_ENTRIES = 1024
MAX_ENTRY_BYTES = 2048
SCHEMA = "nba-pros004-completion-entry-v1"
ACK_SCHEMA = "nba-pros004-remote-checkpoint-v1"
KINDS = {"LOCAL_PERSISTENCE_COMPLETED", "REMOTE_CHECKPOINT_COMPLETED"}
MODES = {"REAL_TIME_CAPTURED", "READINESS_DIAGNOSTIC", "SYNTHETIC_DIAGNOSTIC"}
REPOSITORY = "NickNicky19/Nicks-multisport-lab-project"


def _require(condition, message):
    if not condition:
        raise IntegrityError(message)


def _clock(value):
    _require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z",value) is not None,
             "completion clocks require precise UTC timestamps")
    return utc(value)


def _sha(value, size=64):
    _require(type(value) is str and re.fullmatch(r"[a-f0-9]{"+str(size)+"}",value) is not None,
             "completion evidence hash is malformed")


def journal_path(root):
    path=Path(root).absolute()/JOURNAL_RELATIVE_PATH
    for parent in (path,*path.parents):
        _require(not parent.is_symlink(),"completion journal cannot traverse symlinks")
    return path


def validate_acknowledgment(ack, reference, *, started_at, completed_at, raw_sha256):
    fields={"schema_version","reference","remote_repository","remote_branch","remote_commit",
            "snapshot_sha256","readback_raw_sha256","remote_completed_at"}
    _require(type(ack) is dict and set(ack)==fields and ack["schema_version"]==ACK_SCHEMA,
             "checkpoint requires a structured independent readback acknowledgment")
    _require(ack["reference"]==reference.to_record(),"checkpoint acknowledgment references another original")
    _require(ack["remote_repository"]==REPOSITORY,"checkpoint acknowledgment uses another repository")
    branch=ack["remote_branch"]
    _require(type(branch) is str and re.fullmatch(r"[A-Za-z0-9._/-]{1,160}",branch) is not None,
             "checkpoint acknowledgment branch is invalid")
    _sha(ack["remote_commit"],40);_sha(ack["snapshot_sha256"]);_sha(ack["readback_raw_sha256"])
    _require(ack["readback_raw_sha256"]==raw_sha256,"checkpoint readback bytes differ from the original receipt")
    _require(_clock(started_at)<=_clock(ack["remote_completed_at"])<=_clock(completed_at),
             "checkpoint readback completion clock is outside its actual operation")
    return ack


def _validate_entries(raw):
    _require(len(raw)<=MAX_JOURNAL_BYTES,"completion journal exceeds its byte budget")
    if not raw:return []
    _require(raw.endswith(b"\n"),"interrupted completion journal is ambiguous; no repair or truncation is allowed")
    entries=[];previous="0"*64;seen=set();last=None
    def pairs(items):
        value={}
        for key,item in items:
            _require(key not in value,"duplicate completion JSON key")
            value[key]=item
        return value
    try:
        for line in raw.splitlines():
            _require(bool(line),"empty completion journal entry")
            _require(len(line)+1<=MAX_ENTRY_BYTES,"completion entry exceeds its bounded encoded line size")
            body=json.loads(line,object_pairs_hook=pairs)
            _require(canonical(body)==line,"completion journal entries require exact canonical bytes")
            fields={"schema_version","sequence","previous_sha256","kind","reference","mode",
                    "record_raw_sha256","completed_at","recorded_at","operation_started_at",
                    "acknowledgment","entry_sha256"}
            _require(type(body) is dict and set(body)==fields and body["schema_version"]==SCHEMA,
                     "invalid completion journal contract")
            _require(type(body["sequence"]) is int and body["sequence"]==len(entries)+1 and len(entries)<MAX_JOURNAL_ENTRIES,
                     "completion journal sequence or entry budget conflicts")
            _require(body["previous_sha256"]==previous and body["kind"] in KINDS and body["mode"] in MODES,
                     "completion journal chain or evidence lane conflicts")
            ref=LedgerRef.from_record(body["reference"])
            _sha(body["record_raw_sha256"])
            completed,recorded=_clock(body["completed_at"]),_clock(body["recorded_at"])
            _require(completed<=recorded and (last is None or last<=recorded),"completion journal clocks are inconsistent")
            if body["kind"]=="LOCAL_PERSISTENCE_COMPLETED":
                _require(body["operation_started_at"] is None and body["acknowledgment"] is None,
                         "local persistence evidence cannot claim a remote acknowledgment")
            else:
                validate_acknowledgment(body["acknowledgment"],ref,started_at=body["operation_started_at"],
                    completed_at=body["completed_at"],raw_sha256=body["record_raw_sha256"])
            key=(body["kind"],ref.kind,ref.record_id)
            _require(key not in seen,"completion journal cannot replace an original observation")
            seen.add(key)
            _require(body["entry_sha256"]==digest({k:v for k,v in body.items() if k!="entry_sha256"}),
                     "completion journal entry hash mismatch")
            previous=body["entry_sha256"];last=recorded;entries.append(body)
    except (ValueError,TypeError,KeyError,UnicodeDecodeError) as error:
        if isinstance(error,IntegrityError):raise
        raise IntegrityError("invalid completion journal encoding: "+str(error)) from error
    return entries


def load_journal(root):
    path=journal_path(root)
    if not path.exists():return []
    info=path.stat(follow_symlinks=False)
    _require(stat.S_ISREG(info.st_mode) and info.st_size<=MAX_JOURNAL_BYTES,"completion journal is not a bounded regular file")
    return _validate_entries(path.read_bytes())


def journal_inventory(root):
    path=journal_path(root);entries=load_journal(root)
    raw=path.read_bytes() if path.exists() else b""
    return {"path":JOURNAL_RELATIVE_PATH,"files":int(path.exists()),"bytes":len(raw),
            "raw_sha256":hashlib.sha256(raw).hexdigest() if path.exists() else None,
            "entries":len(entries),"last_entry_sha256":entries[-1]["entry_sha256"] if entries else None}


def append_completion(root, reference, *, mode, raw_sha256, completed_at, recorded_at,
                      started_at=None, acknowledgment=None):
    """Append once, fsync, and re-read; never rewrite an earlier observation.

    completed_at was observed after the original I/O operation. recorded_at is
    the later metadata observation; metadata latency cannot backdate the original.
    An interruption without this evidence leaves the original unadmitted.
    """
    path=journal_path(root);path.parent.mkdir(parents=True,exist_ok=True)
    flags=os.O_RDWR|os.O_CREAT|os.O_APPEND|getattr(os,"O_NOFOLLOW",0)
    descriptor=os.open(path,flags,0o600)
    try:
        fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with os.fdopen(os.dup(descriptor),"rb") as handle:raw=handle.read(MAX_JOURNAL_BYTES+1)
        entries=_validate_entries(raw)
        kind="REMOTE_CHECKPOINT_COMPLETED" if acknowledgment is not None else "LOCAL_PERSISTENCE_COMPLETED"
        value={"schema_version":SCHEMA,"sequence":len(entries)+1,
            "previous_sha256":entries[-1]["entry_sha256"] if entries else "0"*64,
            "kind":kind,"reference":reference.to_record(),"mode":mode,"record_raw_sha256":raw_sha256,
            "completed_at":stamp(utc(completed_at)),"recorded_at":stamp(utc(recorded_at)),
            "operation_started_at":stamp(utc(started_at)) if started_at is not None else None,
            "acknowledgment":acknowledgment}
        existing=[entry for entry in entries if entry["kind"]==kind and entry["reference"]==reference.to_record()]
        if existing:
            original=existing[0]
            stable={"kind","reference","mode","record_raw_sha256"}
            _require(all(original[key]==value[key] for key in stable),"completion evidence changed the original identity or bytes")
            return original
        value["entry_sha256"]=digest(value)
        line=canonical(value)+b"\n"
        _validate_entries(raw+line)
        view=memoryview(line)
        while view:
            written=os.write(descriptor,view)
            _require(written>0,"completion journal append did not advance")
            view=view[written:]
        os.fsync(descriptor)
        parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(parent)
        finally:os.close(parent)
        with os.fdopen(os.dup(descriptor),"rb") as handle:
            handle.seek(0);after=handle.read(MAX_JOURNAL_BYTES+1)
        _require(after==raw+line,"completion journal readback differs from appended evidence")
        return value
    except BlockingIOError as error:
        raise IntegrityError("another completion journal writer is active") from error
    finally:
        os.close(descriptor)

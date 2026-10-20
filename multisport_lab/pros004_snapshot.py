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

from .integrity import IntegrityError, canonical, digest, read_receipt, write_receipt, utc
from .pros004_completion import (JOURNAL_RELATIVE_PATH, MAX_JOURNAL_BYTES,
    journal_inventory, load_journal)
from scripts.verify_pros004_readiness import (
    KINDS, MAX_BYTES, MAX_RECORDS, VerificationError, load_receipt, verify_store,
    _verify_corrections, _verify_original_bytes,
)

SCHEMA = "nba-pros004-diagnostic-snapshot-v2"
LEGACY_SCHEMA = "nba-pros004-diagnostic-snapshot-v1"
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


def _manifest_for_schema(source_root, schema=SCHEMA):
    """Validate full meanings before constructing a deterministic byte inventory."""
    root = _path_root(source_root)
    files = _strict_layout(root)
    try:
        verified = verify_store(root)
        journal=journal_inventory(root)
        _require(journal==verified['completion_journal'],
                 "completion journal changed after its semantic verification")
        _require(schema!=LEGACY_SCHEMA or journal['files']==0,
                 "legacy snapshot cannot omit a completion journal")
        entries = []
        for path in files:
            payload, raw_sha, size = load_receipt(path, maximum=4*1024*1024)
            key=path.parent.name+':'+path.stem
            _require(verified['record_file_sha256'].get(key)==raw_sha,
                     "original receipt bytes changed after semantic verification")
            entry={"path":path.relative_to(root).as_posix(),"encoded_bytes":size,
                   "raw_sha256":raw_sha,"payload_sha256":digest(payload)}
            if schema==SCHEMA:entry['entry_type']='LEDGER_RECEIPT'
            entries.append(entry)
        if journal['files']:
            entries.append({'entry_type':'COMPLETION_JOURNAL','path':JOURNAL_RELATIVE_PATH,
                'encoded_bytes':journal['bytes'],'raw_sha256':journal['raw_sha256'],
                'payload_sha256':digest(load_journal(root))})
            _require(journal_inventory(root)==journal,
                     "completion journal changed during snapshot inventory")
        entries.sort(key=lambda item:item['path'])
    except (VerificationError, IntegrityError, OSError, KeyError, TypeError) as error:
        if isinstance(error,SnapshotError):raise
        raise SnapshotError("independent diagnostic snapshot verification failed: "+str(error)) from error
    _require(verified["records"] == len(entries) and
             verified["encoded_bytes"] == sum(item["encoded_bytes"] for item in entries),
             "source inventory changed during snapshot validation")
    _require(len(entries)<=MAX_RECORDS and sum(item['encoded_bytes'] for item in entries)<=MAX_BYTES,
             "ledger plus completion journal exceeds unchanged snapshot capacity")
    body = {"schema_version":schema,"mode":MODE,"record_count":len(entries),
            "encoded_bytes":sum(item["encoded_bytes"] for item in entries),
            "global_record_limit":MAX_RECORDS,"global_byte_limit":MAX_BYTES,
            "entries":entries,"activation":False,"genuine_issuance":0,
            "remote_durability_established":False}
    if schema==SCHEMA:
        body.update(ledger_record_count=len(files),completion_journal_count=journal['files'],
                    typed_semantics_validated=True)
    return {**body,"manifest_id":digest(body)}


def snapshot_manifest(source_root):
    """Verify bytes and every typed relationship, without granting eligibility.

    The exact bounded completion journal is part of the snapshot when present.
    A missing legacy journal remains missing; recovery never manufactures proof.
    """
    return _manifest_for_schema(source_root)


def recover_manifest_prefix(source_root, journal_raw_sha256, operation_started_at):
    """Reconstruct the byte identity of an earlier already-validated snapshot.

    This raw-only helper does not call typed recovery, grant admission or produce
    an acknowledgment. It avoids recursion when a typed admission validates its
    original input-phase proof. The returned identity includes the original
    manifest's semantic-validation field; that is not a new semantic claim by
    this helper. The enclosing strict facade must still validate typed meanings.

    Equal receipt clocks are included deliberately. If a later record tied an
    earlier operation's clock, its reconstructed digest differs from the retained
    original proof; callers must reject the ambiguity instead of guessing.
    """
    root=_path_root(source_root)
    _require(type(journal_raw_sha256) is str and re.fullmatch('[a-f0-9]{64}',journal_raw_sha256) is not None,
             'invalid original journal-prefix hash')
    _require(type(operation_started_at) is str and re.fullmatch(
        r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z',operation_started_at) is not None,
        'original snapshot operation needs a precise UTC clock')
    try:
        started=utc(operation_started_at)
        files=_strict_layout(root)
        current_journal=journal_inventory(root);journal=load_journal(root)
        _require(len(files)+current_journal['files']<=MAX_RECORDS and
                 sum(p.stat().st_size for p in files)+current_journal['bytes']<=MAX_BYTES,
                 'prefix source exceeds unchanged ledger capacity')
        records={};hashes={};raw_hashes={};sizes={};entries=[]
        for path in files:
            payload,raw_sha,size=load_receipt(path,maximum=4*1024*1024)
            kind=path.parent.name;key=(kind,path.stem)
            fields={'schema_version','kind','record_id','logical_id','received_at','data','references',
                    'supersedes','persistence_status'}
            _require(type(payload) is dict and set(payload)==fields and
                payload['schema_version']=='multisport-research-ledger-v1' and payload['kind']==kind and
                payload['record_id']==path.stem and payload['persistence_status']=='LOCAL_RECEIPT_ONLY',
                'original prefix ledger envelope changed')
            _require(type(payload['logical_id']) is str and bool(payload['logical_id'].strip()) and
                payload['record_id']==digest({'kind':kind,'logical_id':payload['logical_id']}) and
                type(payload['data']) is dict and type(payload['references']) is list,
                'original prefix logical identity/data changed')
            received=payload['received_at']
            _require(type(received) is str and re.fullmatch(
                r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z',received) is not None,
                'original prefix receipt clock is malformed')
            raw_hashes[key]=raw_sha;sizes[key]=size
            if utc(received)>started:
                continue
            records[key]=payload;hashes[key]=digest(payload)
            entries.append({'entry_type':'LEDGER_RECEIPT','path':path.relative_to(root).as_posix(),
                'encoded_bytes':size,'raw_sha256':raw_sha,'payload_sha256':hashes[key]})
        for payload in records.values():
            observed=[]
            for ref in payload['references']:
                _require(type(ref) is dict and set(ref)=={'kind','record_id','payload_sha256'} and
                    ref['kind'] in KINDS and type(ref['record_id']) is str and
                    re.fullmatch('[a-f0-9]{64}',ref['record_id']) is not None,
                    'original prefix reference is malformed')
                key=(ref['kind'],ref['record_id'])
                _require(key in records and hashes[key]==ref['payload_sha256'] and
                    utc(records[key]['received_at'])<=utc(payload['received_at']),
                    'original prefix reference content/clock is unavailable or changed')
                observed.append(key)
            _require(len(set(observed))==len(observed),'original prefix duplicates references')
        _verify_corrections(records,hashes)
        prefix=bytearray();prefix_entries=[];matched=False
        for entry in journal:
            prefix.extend(canonical(entry)+b'\n');prefix_entries.append(entry)
            if hashlib.sha256(prefix).hexdigest()==journal_raw_sha256:
                matched=True;break
        _require(matched,'original journal prefix is unavailable or changed')
        for entry in prefix_entries:
            ref=entry['reference'];key=(ref['kind'],ref['record_id'])
            _require(key in records and hashes[key]==ref['payload_sha256'] and
                raw_hashes[key]==entry['record_raw_sha256'] and
                utc(records[key]['received_at'])<=utc(entry['completed_at']) and
                utc(entry['recorded_at'])<=started,
                'original journal prefix changes its record identity/bytes/clocks')
        entries.append({'entry_type':'COMPLETION_JOURNAL','path':JOURNAL_RELATIVE_PATH,
            'encoded_bytes':len(prefix),'raw_sha256':journal_raw_sha256,
            'payload_sha256':digest(prefix_entries)})
        entries.sort(key=lambda entry:entry['path'])
        body={'schema_version':SCHEMA,'mode':MODE,'record_count':len(entries),
            'encoded_bytes':sum(entry['encoded_bytes'] for entry in entries),
            'global_record_limit':MAX_RECORDS,'global_byte_limit':MAX_BYTES,'entries':entries,
            'activation':False,'genuine_issuance':0,'remote_durability_established':False,
            'ledger_record_count':len(records),'completion_journal_count':1,'typed_semantics_validated':True}
        _verify_original_bytes(root,raw_hashes,sizes)
        _require(journal_inventory(root)==current_journal,'source journal changed during prefix reconstruction')
        return {**body,'manifest_id':digest(body)}
    except (IntegrityError,VerificationError,ValueError,OSError,KeyError,TypeError) as error:
        if isinstance(error,SnapshotError):raise
        raise SnapshotError('original raw-prefix reconstruction failed: '+str(error)) from error


def _validate_manifest(body):
    common = {"schema_version","mode","record_count","encoded_bytes","global_record_limit",
              "global_byte_limit","entries","activation","genuine_issuance",
              "remote_durability_established","manifest_id"}
    _require(type(body) is dict and body.get('schema_version') in {SCHEMA,LEGACY_SCHEMA},
             "invalid diagnostic snapshot manifest")
    version2=body['schema_version']==SCHEMA
    fields=common|({'ledger_record_count','completion_journal_count','typed_semantics_validated'} if version2 else set())
    _require(set(body)==fields,"invalid diagnostic snapshot manifest fields")
    _require(body["mode"] == MODE and body["activation"] is False and type(body["genuine_issuance"]) is int and
             body["genuine_issuance"] == 0 and body["remote_durability_established"] is False,
             "snapshot cannot claim genuine issuance, activation or remote durability")
    _require(body["global_record_limit"] == MAX_RECORDS and body["global_byte_limit"] == MAX_BYTES,
             "snapshot ledger limits changed")
    entries = body["entries"]
    _require(type(entries) is list and len(entries) <= MAX_RECORDS, "invalid snapshot entry budget")
    previous = "";total = ledger_count = journal_count = 0
    for entry in entries:
        entry_fields={'path','encoded_bytes','raw_sha256','payload_sha256'}|({'entry_type'} if version2 else set())
        _require(type(entry) is dict and set(entry)==entry_fields,"invalid snapshot entry")
        path = entry["path"]
        _require(type(path) is str and path>previous,"snapshot entries must have unique sorted safe paths")
        is_journal=version2 and entry['entry_type']=='COMPLETION_JOURNAL'
        if is_journal:
            _require(path==JOURNAL_RELATIVE_PATH,"invalid completion journal snapshot path")
            journal_count+=1
            _require(journal_count==1,"snapshot duplicates its completion journal")
            cap=MAX_JOURNAL_BYTES
        else:
            _require(not version2 or entry['entry_type']=='LEDGER_RECEIPT',"unknown snapshot entry type")
            _require(re.fullmatch(r"records/(?:"+"|".join(KINDS)+r")/[a-f0-9]{64}\.json",path) is not None,
                     "invalid safe ledger snapshot path")
            ledger_count+=1;cap=4*1024*1024
        previous = path
        _require(type(entry["encoded_bytes"]) is int and 0<=entry["encoded_bytes"]<=cap and
                 (is_journal or entry['encoded_bytes']>0),"invalid snapshot record size")
        for key in ("raw_sha256","payload_sha256"):
            _require(type(entry[key]) is str and re.fullmatch(r"[a-f0-9]{64}",entry[key]) is not None,
                     "invalid snapshot hash")
        total += entry["encoded_bytes"]
    _require(type(body["record_count"]) is int and body["record_count"] == len(entries) and
             type(body["encoded_bytes"]) is int and body["encoded_bytes"] == total <= MAX_BYTES,
             "snapshot count/byte totals conflict")
    if version2:
        _require(type(body['ledger_record_count']) is int and body['ledger_record_count']==ledger_count and
                 type(body['completion_journal_count']) is int and body['completion_journal_count']==journal_count and
                 body['typed_semantics_validated'] is True,"snapshot semantic/journal counts conflict")
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
    try:
        manifest = _validate_manifest(read_receipt(source/MANIFEST,max_bytes=MAX_MANIFEST_BYTES))
    except (IntegrityError, OSError, KeyError, TypeError) as error:
        raise SnapshotError("invalid or incomplete diagnostic snapshot: "+str(error)) from error
    expected_top={'records',MANIFEST}|({'evidence'} if manifest.get('completion_journal_count',0) else set())
    _require({p.name for p in source.iterdir()}==expected_top,"snapshot is interrupted or has unrecognized entries")
    if 'evidence' in expected_top:
        _require({p.relative_to(source).as_posix() for p in (source/'evidence').rglob('*')}==
                 {'evidence/pros004',JOURNAL_RELATIVE_PATH},"snapshot contains unrecognized evidence files")
    _require(_manifest_for_schema(source,manifest['schema_version']) == manifest,
             "snapshot bytes or retained inventory changed")
    target = _path_root(destination_root)
    _require(not target.is_relative_to(source), "readback destination must not be inside snapshot")
    target = _new_root(target)
    (target/"records").mkdir(exist_ok=True)
    for entry in manifest["entries"]:
        _copy_record(source/entry["path"], target/entry["path"], entry)
    _require(_manifest_for_schema(target,manifest['schema_version']) == manifest and
             _manifest_for_schema(source,manifest['schema_version']) == manifest,
             "readback bytes or retained inventory changed")
    ack = {"schema_version":"nba-pros004-diagnostic-readback-v2",
           "status":"PASS_VERIFIED_DIAGNOSTIC_READBACK","manifest_id":manifest["manifest_id"],
           "record_count":manifest["record_count"],"encoded_bytes":manifest["encoded_bytes"],
           "all_original_bytes_preserved":True,"activation":False,"genuine_issuance":0,
           "remote_durability_established":False,"missing_peers_repaired":False,
           "typed_semantics_validated":True,"prospective_eligibility":"NOT_ESTABLISHED_BY_SNAPSHOT",
           "completion_journal_copied":bool(manifest.get("completion_journal_count",0))}
    write_receipt(target/"pros004-readback.json",ack,max_bytes=8192)
    return ack

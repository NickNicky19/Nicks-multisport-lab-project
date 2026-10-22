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
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from datetime import datetime, timezone

from .integrity import IntegrityError, canonical, digest, read_receipt, write_receipt, utc
from .pros004_completion import (JOURNAL_RELATIVE_PATH, MAX_JOURNAL_BYTES,
    journal_inventory, load_journal)
from scripts.verify_pros004_readiness import (
    KINDS, MAX_BYTES, MAX_RECORDS, VerificationError, load_receipt, verify_store,
    _verify_corrections, _verify_original_bytes, _verify_completion_journal,
)

SCHEMA = "nba-pros004-diagnostic-snapshot-v2"
LEGACY_SCHEMA = "nba-pros004-diagnostic-snapshot-v1"
MODE = "READINESS_DIAGNOSTIC_NON_ISSUANCE"
MANIFEST = "pros004-snapshot.json"
MAX_MANIFEST_BYTES = 256*1024
_CALLBACK_PROOF_KEY = object()
_TRANSFER_PROOF_KEY = object()


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


def _callback_context(root):
    """Bind the actual data directories and the reviewed validation code bytes."""
    from .pros004_producer import source_hashes
    root=_path_root(root)
    _require(root.is_dir() and (root/'records').is_dir(),"callback proof needs an existing records root")
    directories=[]
    for path in (root,root/'records'):
        _require(not path.is_symlink(),"callback proof cannot traverse replaced/symlinked directories")
        info=path.stat()
        directories.append([info.st_dev,info.st_ino])
    return digest({'root':str(root),'directories':directories,'schema':SCHEMA,'mode':MODE,
        'record_limit':MAX_RECORDS,'byte_limit':MAX_BYTES,'journal_path':JOURNAL_RELATIVE_PATH,
        'journal_byte_limit':MAX_JOURNAL_BYTES,'source_sha256':source_hashes()})


def _fresh_identical_snapshot(root,expected,clock,*,_diagnostic_transport=False):
    """Recheck bytes, canonical hashes, references and clocks after a callback.

    Only pure typed semantics for exactly identical bytes are reused. No current
    timing, completion, durability or admission result is retained by this path.
    The remote writer still performs its own fresh complete strict verification.
    """
    _validate_manifest(expected)
    _require(expected['schema_version']==SCHEMA,"callback proof requires the current snapshot contract")
    files=_strict_layout(root)
    original={entry['path']:entry for entry in expected['entries']}
    ledger_entries={name:entry for name,entry in original.items() if entry['entry_type']=='LEDGER_RECEIPT'}
    _require({path.relative_to(root).as_posix() for path in files}==set(ledger_entries),
             "callback changed the retained receipt inventory")
    observed_at=utc(clock())
    records={};hashes={};encoded={};sizes={}
    for path in files:
        entry=ledger_entries[path.relative_to(root).as_posix()]
        # load_receipt freshly decodes strict finite JSON and recomputes the
        # canonical payload checksum. Exact raw identity also binds that checked
        # payload hash to the original strictly validated envelope.
        payload,raw_sha,size=load_receipt(path,maximum=4*1024*1024)
        _require(raw_sha==entry['raw_sha256'] and size==entry['encoded_bytes'],
                 "callback changed original receipt bytes")
        kind=path.parent.name;key=(kind,path.stem)
        _require(payload['kind']==kind and payload['record_id']==path.stem,
                 "callback receipt identity changed")
        received=payload['received_at']
        _require(type(received) is str and re.fullmatch(
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z',received) is not None,
            "callback receipt clock is malformed")
        records[key]=payload;hashes[key]=entry['payload_sha256'];encoded[key]=raw_sha;sizes[key]=size
    for (kind,_),payload in records.items():
        # The independent verifier explicitly permits simulated PROS004 clocks
        # in diagnostic stores. Transport must preserve that policy, without
        # treating a simulation as an actual capture or persistence clock. The
        # existing callback proof retains its stricter actual-clock policy.
        simulated=_diagnostic_transport and 'pros004' in payload['data']
        if _diagnostic_transport and kind=='corrections':
            targets=[payload['supersedes'],payload['data']['replacement']]
            simulated=all(records[(r['kind'],r['record_id'])]['data'].get('pros004',{}).get('mode')
                          in {'READINESS_DIAGNOSTIC','SYNTHETIC_DIAGNOSTIC'} for r in targets)
        _require(simulated or utc(payload['received_at'])<=observed_at,
                 "callback receipt clock exceeds the actual reread clock")
    for payload in records.values():
        seen=set()
        for reference in payload['references']:
            _require(type(reference) is dict and set(reference)=={'kind','record_id','payload_sha256'},
                     "callback reference contract changed")
            key=(reference['kind'],reference['record_id'])
            _require(key not in seen and key in records and hashes[key]==reference['payload_sha256'] and
                utc(records[key]['received_at'])<=utc(payload['received_at']),
                "callback reference identity/hash/chronology changed")
            seen.add(key)
    _verify_corrections(records,hashes)
    journal=_verify_completion_journal(root,records,encoded,hashes)
    expected_journals=[entry for entry in original.values() if entry['entry_type']=='COMPLETION_JOURNAL']
    _require(journal['files']==len(expected_journals),"callback changed the completion-journal inventory")
    if expected_journals:
        entry=expected_journals[0]
        _require(journal['raw_sha256']==entry['raw_sha256'] and journal['bytes']==entry['encoded_bytes'],
                 "callback changed original completion-journal bytes")
        for observation in load_journal(root):
            _require(_diagnostic_transport or utc(observation['recorded_at'])<=observed_at,
                     "callback completion observation exceeds the actual reread clock")
    _require(len(records)+journal['files']<=MAX_RECORDS and sum(sizes.values())+journal['bytes']<=MAX_BYTES,
             "callback proof exceeds unchanged ledger limits")
    _verify_original_bytes(root,encoded,sizes)
    _require(journal_inventory(root)==journal,"completion journal changed during callback verification")
    _require(_strict_layout(root)==files,"receipt layout changed during callback verification")
    _require(utc(clock())>=observed_at,"actual callback verification clock moved backwards")
    return records


class _CallbackVerification:
    """An opaque, single-use semantic proof for one bounded callback operation."""
    __slots__=('__root','__context','__manifest_bytes','__used')

    def __init__(self,root,manifest,context,*,_key=None):
        _require(_key is _CALLBACK_PROOF_KEY,"callback proofs must originate from strict verification")
        self.__root=root;self.__context=context;self.__used=False
        self.__manifest_bytes=canonical(manifest)
        _require(len(self.__manifest_bytes)<=MAX_MANIFEST_BYTES,"callback proof manifest exceeds its memory bound")

    @property
    def manifest(self):
        return json.loads(self.__manifest_bytes)

    def verify_unchanged(self,*,clock):
        _require(not self.__used,"callback verification proof has already been consumed")
        self.__used=True  # A failed/interrupted proof cannot be retried as success.
        try:
            _require(callable(clock),"callback verification requires the actual clock reader")
            _require(_callback_context(self.__root)==self.__context,
                     "callback root/schema/source context changed")
            expected=json.loads(self.__manifest_bytes)
            _fresh_identical_snapshot(self.__root,expected,clock)
            _require(_callback_context(self.__root)==self.__context,
                     "callback root/schema/source context changed during verification")
            return json.loads(self.__manifest_bytes)
        except (IntegrityError,VerificationError,OSError,KeyError,TypeError,ValueError) as error:
            if isinstance(error,SnapshotError):raise
            raise SnapshotError('callback snapshot verification rejected: '+str(error)) from error


def begin_callback_verification(source_root):
    """Run complete strict verification before creating a one-operation proof.

    This factory accepts no caller-supplied manifest or cached admission result.
    A proof cannot be transferred to another root or reused by another callback.
    """
    root=_path_root(source_root);context=_callback_context(root)
    manifest=snapshot_manifest(root)
    _require(_callback_context(root)==context,"root/source context changed during strict callback verification")
    return _CallbackVerification(root,manifest,context,_key=_CALLBACK_PROOF_KEY)


def _transport_now():
    return datetime.now(timezone.utc)


class _ExactTransfer:
    """One source verification and bounded, single-use local copy checks.

    This object is private to one checkpoint operation. Only exactly identical
    bytes reuse pure typed meanings. Every root gets fresh JSON/checksum,
    reference, clock, correction, journal, inventory and final-byte checks.
    Nothing here supplies admission, completion times or remote durability;
    independent Git readback must still perform a full typed verification.
    """
    __slots__=('__source','__context','__manifest_bytes','__phase','__target','__writer','__last_clock',
               '__source_clocks')

    def __init__(self,source,manifest,context,*,_key=None):
        _require(_key is _TRANSFER_PROOF_KEY,"transfer proofs must originate from strict verification")
        self.__source=source;self.__context=context;self.__phase='NEW'
        self.__target=None;self.__writer=None
        self.__source_clocks={}
        self.__last_clock=utc(_transport_now())
        self.__manifest_bytes=canonical(manifest)
        _require(len(self.__manifest_bytes)<=MAX_MANIFEST_BYTES,"transfer proof exceeds its memory bound")

    @property
    def manifest(self):
        return json.loads(self.__manifest_bytes)

    def _clock(self):
        observed=utc(_transport_now())
        _require(observed>=self.__last_clock,"actual transfer verification clock moved backwards")
        self.__last_clock=observed
        return observed

    def _check(self,root,manifest,context):
        try:
            _require(_callback_context(self.__source)==self.__context,"transfer source context changed")
            _require(_callback_context(root)==context,"transfer destination context changed")
            records=_fresh_identical_snapshot(root,manifest,self._clock,_diagnostic_transport=True)
            _require(_callback_context(root)==context,"transfer destination changed during verification")
            _require(_callback_context(self.__source)==self.__context,"transfer source changed during verification")
            return records
        except (IntegrityError,VerificationError,OSError,KeyError,TypeError,ValueError) as error:
            if isinstance(error,SnapshotError):raise
            raise SnapshotError('exact transfer verification rejected: '+str(error)) from error

    def export(self,snapshot_root):
        _require(self.__phase=='NEW',"transfer export proof has already been consumed")
        self.__phase='FAILED'
        target=_path_root(snapshot_root)
        _require(not target.is_relative_to(self.__source),"snapshot destination must not be inside source")
        target=_new_root(target);(target/'records').mkdir(exist_ok=True)
        context=_callback_context(target);manifest=self.manifest
        for entry in manifest['entries']:
            _copy_record(self.__source/entry['path'],target/entry['path'],entry)
        self._check(target,manifest,context)
        source_records=self._check(self.__source,manifest,self.__context)
        self.__source_clocks={f'records/{kind}/{identifier}.json':payload['received_at']
                              for (kind,identifier),payload in source_records.items()}
        write_receipt(target/MANIFEST,manifest,max_bytes=MAX_MANIFEST_BYTES)
        self.__target=(target,context);self.__phase='EXPORTED'
        return manifest

    def preserve_writer(self,writer_root):
        """Check the retained writer's exact closed subset and journal prefix."""
        _require(self.__phase=='EXPORTED',"transfer writer proof has already been consumed")
        self.__phase='FAILED'
        root=_path_root(writer_root)
        _require(root!=self.__source and not root.is_relative_to(self.__source) and
                 not self.__source.is_relative_to(root),"transfer writer and source roots overlap")
        (root/'records').mkdir(exist_ok=True)
        context=_callback_context(root);manifest=self.manifest
        current={entry['path']:entry for entry in manifest['entries']}
        retained=[]
        for path in _strict_layout(root):
            relative=path.relative_to(root).as_posix()
            _require(relative in current,"checkpoint source is missing a retained remote original")
            retained.append(current[relative])
        journal=journal_inventory(root)
        if journal['files']:
            _require(JOURNAL_RELATIVE_PATH in current,"completion journal cannot truncate an acknowledged prefix")
            old=(root/JOURNAL_RELATIVE_PATH).read_bytes()
            source=self.__target[0]/JOURNAL_RELATIVE_PATH
            _require(source.read_bytes().startswith(old),
                     "completion journal cannot truncate or replace an acknowledged prefix")
            retained.append({'entry_type':'COMPLETION_JOURNAL','path':JOURNAL_RELATIVE_PATH,
                'encoded_bytes':journal['bytes'],'raw_sha256':journal['raw_sha256'],
                'payload_sha256':digest(load_journal(root))})
        retained.sort(key=lambda entry:entry['path'])
        body={k:v for k,v in manifest.items() if k!='manifest_id'}
        body.update(entries=retained,record_count=len(retained),
            ledger_record_count=len(retained)-journal['files'],completion_journal_count=journal['files'],
            encoded_bytes=sum(entry['encoded_bytes'] for entry in retained))
        # This transient inventory is derived solely from the full strict source
        # proof. It is never published as an independently typed subset snapshot.
        subset={**body,'manifest_id':digest(body)}
        records=self._check(root,subset,context)
        # An unreferenced original can still belong to a durable admission's
        # older input snapshot. Full strict SOURCE verification already checked
        # that prefix; exact retained bytes must keep its complete membership.
        retained_paths={entry['path'] for entry in retained}
        prefix_hashes=set();prefix=hashlib.sha256()
        for entry in load_journal(root):
            prefix.update(canonical(entry)+b'\n');prefix_hashes.add(prefix.hexdigest())
        for payload in records.values():
            body=payload['data'].get('pros004',{})
            if body.get('schema_version')!='nba-pros004-event-claim-v2':continue
            original=body['input_final_checkpoint'];started=utc(original['operation_started_at'])
            required={path for path,clock in self.__source_clocks.items() if utc(clock)<=started}
            _require(required<=retained_paths and original['journal_raw_sha256'] in prefix_hashes,
                     "retained input-admission snapshot prefix is incomplete; do not repair originals")
        self.__writer=(root,context);self.__phase='WRITER_BOUND'

    def verify_writer(self,writer_root):
        _require(self.__phase=='WRITER_BOUND',"transfer completion proof has already been consumed")
        self.__phase='FAILED'
        root=_path_root(writer_root)
        _require(root==self.__writer[0],"transfer completion belongs to another writer")
        # Recheck the exported raw source as well as the final writer. This also
        # rejects changes between export and the writer's actual copy operation.
        self._check(self.__target[0],self.manifest,self.__target[1])
        self._check(root,self.manifest,self.__writer[1])
        self.__phase='COMPLETE'
        return self.manifest


def _begin_exact_transfer(source_root):
    """No caller manifest: every operation starts with a fresh full typed pass."""
    root=_path_root(source_root);context=_callback_context(root)
    manifest=snapshot_manifest(root)
    _require(_callback_context(root)==context,"root/source changed during strict transfer verification")
    return _ExactTransfer(root,manifest,context,_key=_TRANSFER_PROOF_KEY)


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
    return _begin_exact_transfer(source_root).export(snapshot_root)


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

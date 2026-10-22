"""Bounded normal Git checkpoints for this separately admitted daily protocol.

Uses the existing repository and generic Git/path patterns from pros004_remote;
no scheduler, activation, source requests or provider credentials are introduced.
Every returned recovery follows a fresh object database and strict typed replay.
Completion receipts record the action's actual clock, then a second checkpoint
retains those receipts without claiming recursive acknowledgment of metadata.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from .integrity import IntegrityError, digest, stamp, utc
from .ledger import Ledger, LedgerRef
from .sdv_daily_store import DailyStore, COMPLETION_SCHEMA
from .pros004_remote import _safe_root

REPOSITORY="NickNicky19/Nicks-multisport-lab-project"
REMOTE_URL="https://github.com/"+REPOSITORY+".git"
MAX_COMMAND_SECONDS=60


def _now():return datetime.now(timezone.utc)


def require(ok,message):
    if not ok:raise IntegrityError(message)


def _sha(value):
    require(type(value) is str and re.fullmatch(r"[a-f0-9]{40}",value),"invalid daily remote commit")
    return value


def snapshot_manifest(root,*,store=None):
    """Validate before returning exact retained bytes; never trusts a hash alone."""
    root=_safe_root(root)
    store=DailyStore(root) if store is None else store
    require(store.project_root == root,"snapshot verifier store root differs")
    with store.ledger.validation_scope():
        store.recover();store.ledger.parent.scan()
        old,_,_=store.ledger.parent._inventory();new,_,_=store.ledger._inventory()
        entries=[]
        for prefix,inventory in ((Path("records"),old),(Path("daily/records"),new)):
            for kind,files in inventory.items():
                for path,size in files:
                    raw=path.read_bytes()
                    require(len(raw) == size,"daily snapshot changed while reading")
                    entries.append({"path":str(prefix/kind/path.name),"bytes":size,
                        "sha256":hashlib.sha256(raw).hexdigest()})
        return {"schema_version":"nba-sdv-daily-snapshot-v1","entries":sorted(entries,key=lambda row:row["path"])}


class DailyGitCheckpointWriter:
    def __init__(self,source_root,writer_root,*,base_commit,branch,remote_url=REMOTE_URL,
                 allow_local_test_remote=False,command_seconds=60):
        self.source_root=_safe_root(source_root);self.root=_safe_root(writer_root)
        self.base_commit=_sha(base_commit);self.branch=branch;self.remote_url=str(remote_url)
        require(type(branch) is str and re.fullmatch(r"(?:records|diagnostics)/sdv-daily-[a-z0-9-]{1,80}",branch),
                "daily checkpoint destination is not an isolated daily branch")
        require(type(command_seconds) is int and 1 <= command_seconds <= MAX_COMMAND_SECONDS,
                "daily remote command budget exceeds 60 seconds")
        self.command_seconds=command_seconds;self._deadline=None;self._head=None
        require(not self.root.is_relative_to(self.source_root) and not self.source_root.is_relative_to(self.root),
                "daily writer and retained source must be separate working states")
        if allow_local_test_remote:
            remote=_safe_root(self.remote_url)
            require(remote.is_relative_to(Path(tempfile.gettempdir())) and remote.is_dir(),
                    "local test remote must be an existing isolated temporary repository")
            result=subprocess.run(["git","-C",str(remote),"rev-parse","--is-bare-repository"],
                capture_output=True,text=True,timeout=command_seconds,check=False)
            require(result.returncode == 0 and result.stdout.strip() == "true","local test remote is not bare")
        else:
            require(self.remote_url in {REMOTE_URL,REMOTE_URL[:-4],"git@github.com:"+REPOSITORY+".git"},
                    "daily checkpoint must use the existing authorized repository")

    def _git(self,*args,cwd=None,check=True):
        remaining=self.command_seconds if self._deadline is None else self._deadline-time.monotonic()
        require(remaining > 0,"daily remote checkpoint exceeded its operation budget")
        try:
            result=subprocess.run(["git",*args],cwd=cwd or self.root,capture_output=True,
                text=True,timeout=remaining,check=False)
        except subprocess.TimeoutExpired as exc:
            raise IntegrityError("daily remote command timed out; retain the current writer state") from exc
        if check:require(result.returncode == 0,"daily Git checkpoint command failed: "+args[0])
        return result

    def _remote_head(self):
        lines=self._git("ls-remote","--heads","origin","refs/heads/"+self.branch).stdout.strip().splitlines()
        require(len(lines) <= 1,"ambiguous daily remote branch")
        if not lines:return None
        fields=lines[0].split()
        require(len(fields) == 2 and fields[1] == "refs/heads/"+self.branch,"daily remote branch identity changed")
        return _sha(fields[0])

    def prepare(self):
        if not self.root.exists():
            self.root.mkdir(parents=True,mode=0o700)
            self._git("init","--quiet");self._git("remote","add","origin",self.remote_url)
            target="refs/heads/"+self.branch if self._remote_head() else self.base_commit
            self._git("fetch","--no-tags","origin",target)
            self._git("checkout","--quiet","-b",self.branch,"FETCH_HEAD")
        require(self._git("remote","get-url","origin").stdout.strip() == self.remote_url,"daily writer origin changed")
        require(self._git("branch","--show-current").stdout.strip() == self.branch,"daily writer branch changed")
        self._head=_sha(self._git("rev-parse","HEAD").stdout.strip())
        remote=self._remote_head()
        if remote is not None and remote != self._head:
            self._git("fetch","--no-tags","origin","refs/heads/"+self.branch)
            require(self._git("merge-base","--is-ancestor",remote,self._head,check=False).returncode == 0,
                    "daily remote contains newer independent work; do not overwrite it")
        return {"repository":REPOSITORY,"branch":self.branch,"local_head":self._head,"remote_head":remote}

    def _preserve(self,manifest):
        # A retained destination may contain a previous original. Missing source
        # records are not deletion authority and different bytes are never replaced.
        existing=snapshot_manifest(self.root)
        expected={row["path"]:row for row in manifest["entries"]}
        require(all(expected.get(row["path"]) == row for row in existing["entries"]),
                "daily writer contains originals absent or different in retained source")
        for row in manifest["entries"]:
            source=self.source_root/row["path"];target=self.root/row["path"]
            raw=source.read_bytes()
            require(len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"],
                    "retained daily source changed during checkpoint")
            for parent in (target,*target.parents):require(not parent.is_symlink(),"daily checkpoint cannot traverse symlinks")
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                require(target.read_bytes() == raw,"daily checkpoint cannot overwrite an original")
                continue
            # Copy to a bounded private staging file, then publish a complete
            # immutable file atomically. An interruption cannot expose half of
            # an original in the retained writer's records namespace.
            descriptor,staging=tempfile.mkstemp(prefix="sdv-daily-copy-",dir=self.root/".git")
            try:
                with os.fdopen(descriptor,"wb") as handle:
                    handle.write(raw);handle.flush();os.fsync(handle.fileno())
                try:os.link(staging,target)
                except FileExistsError:require(target.read_bytes() == raw,"concurrent daily original differs")
            finally:Path(staging).unlink(missing_ok=True)
        require(snapshot_manifest(self.root) == manifest,"daily writer snapshot differs after exact copy")

    @contextmanager
    def _writer_lock(self):
        git_dir=self.root/".git"
        require(git_dir.is_dir() and not git_dir.is_symlink(),"daily retained writer needs its own Git directory")
        path=git_dir/"sdv-daily-writer.lock"
        require(not path.is_symlink(),"daily remote writer lock is a symlink")
        with path.open("a+b") as handle:
            try:fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc:raise IntegrityError("another daily remote writer is active") from exc
            try:yield
            finally:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)

    def _push(self):
        require(self._git("rev-parse","HEAD").stdout.strip() == self._head,"daily retained writer commit changed")
        changed=self._git("status","--porcelain","--untracked-files=all").stdout.splitlines()
        require(all(row[3:].startswith(("records/","daily/records/")) for row in changed),
                "daily writer has unrelated interrupted work")
        manifest=snapshot_manifest(self.source_root);self._preserve(manifest)
        paths=[entry["path"] for entry in manifest["entries"]]
        if paths:self._git("add","--",*paths)
        if self._git("diff","--cached","--quiet",check=False).returncode:
            self._git("-c","user.name=Nick's Multisport Lab","-c","user.email=research@users.noreply.github.com",
                "commit","--quiet","-m","Retain bounded SDV daily research records")
        commit=_sha(self._git("rev-parse","HEAD").stdout.strip());self._head=commit
        self._git("push","origin","HEAD:refs/heads/"+self.branch)
        return commit,manifest,_now()

    def _readback(self,commit,*,manifest=None,references=()):
        # Fresh repository, no alternates, shared object database or copied index.
        with tempfile.TemporaryDirectory(prefix="nml-sdv-daily-readback-") as folder:
            root=Path(folder)/"recovered";root.mkdir()
            self._git("init","--quiet",cwd=root)
            self._git("remote","add","origin",self.remote_url,cwd=root)
            self._git("fetch","--no-tags","--depth=1","origin",commit,cwd=root)
            require(self._git("rev-parse","FETCH_HEAD",cwd=root).stdout.strip() == commit,
                    "independent daily fetched commit differs")
            self._git("checkout","--quiet","--detach","FETCH_HEAD",cwd=root)
            recovered=DailyStore(root)
            with recovered.ledger.validation_scope():
                actual=snapshot_manifest(root,store=recovered)
                if manifest is not None:require(actual == manifest,"independent daily snapshot differs")
                for ref in references:recovered.ledger.read(ref)
                report=recovered.recover()
                return {"snapshot_sha256":digest(actual),"recovered_records":len(report["records"]),
                        "recovery_completed_at":stamp(_now())}

    def flush(self):
        """Preserve partial/failure metadata without inventing issuance acks."""
        require(self._head is not None,"prepare the daily retained writer before flushing")
        self._deadline=time.monotonic()+self.command_seconds
        try:
            with self._writer_lock():
                commit,manifest,pushed=self._push()
                recovered=self._readback(commit,manifest=manifest)
                return {"repository":REPOSITORY,"branch":self.branch,"commit":commit,
                    "remote_checkpoint_completed_at":stamp(pushed),**recovered,
                    "issuance_acknowledgments_added":0}
        finally:self._deadline=None

    def checkpoint(self,references):
        require(self._head is not None,"prepare the daily retained writer before checkpoint")
        with self._writer_lock():return self._checkpoint_locked(references)

    def _checkpoint_locked(self,references):
        refs=(references,) if isinstance(references,LedgerRef) else tuple(references)
        require(refs and len(refs) <= 32 and len(set(refs)) == len(refs)
                and all(isinstance(ref,LedgerRef) for ref in refs),"daily checkpoint requires unique exact references")
        require(self._head is not None,"prepare the daily retained writer before checkpoint")
        self._deadline=time.monotonic()+self.command_seconds
        try:
            store=DailyStore(self.source_root)
            for ref in refs:store.ledger.read(ref)
            started=_now();commit,manifest,pushed=self._push()
            prior={}
            for _,body in store.records():
                if body["schema_version"] == COMPLETION_SCHEMA:
                    prior[(LedgerRef.from_record(body["reference"]),body["stage"])]=body
            for ref in refs:
                if (ref,"REMOTE_CHECKPOINT") not in prior:
                    with store._verified_remote_completion(ref,"REMOTE_CHECKPOINT",commit):
                        store.record_completion(ref,started_at=started,stage="REMOTE_CHECKPOINT",remote_commit=commit)
            first=self._readback(commit,manifest=manifest,references=refs)
            remote_rows={LedgerRef.from_record(body["reference"]):body for _,body in store.records()
                if body["schema_version"] == COMPLETION_SCHEMA and body["stage"] == "REMOTE_CHECKPOINT"}
            for ref in refs:
                if (ref,"FINAL_RECOVERY") in prior:continue
                remote=remote_rows[ref]
                if remote["remote_commit"] != commit:
                    self._readback(remote["remote_commit"],references=(ref,))
                with store._verified_remote_completion(ref,"FINAL_RECOVERY",remote["remote_commit"]):
                    store.record_completion(ref,started_at=utc(remote["operation_started_at"]),
                        stage="FINAL_RECOVERY",remote_commit=remote["remote_commit"])
            # The first proof concerns the original records. This second push
            # durably retains that proof, not an infinite sequence of self-acks.
            proof_commit,proof_manifest,_=self._push()
            proof=self._readback(proof_commit,manifest=proof_manifest,references=refs)
            require(time.monotonic() <= self._deadline,"daily remote completion exceeded operation budget")
            return {"repository":REPOSITORY,"branch":self.branch,"originals_commit":commit,
                "commit":proof_commit,"remote_checkpoint_completed_at":stamp(pushed),
                **first,"proof_recovery_completed_at":proof["recovery_completed_at"],
                "proof_snapshot_sha256":proof["snapshot_sha256"],"proof_recovered_records":proof["recovered_records"],
                "metadata_acknowledgment_recursive":False}
        finally:self._deadline=None

    __call__=checkpoint

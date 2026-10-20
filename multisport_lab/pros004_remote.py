"""Bounded Git checkpoint/readback for inactive PROS004 readiness.

This module has no source client, model producer, scheduler or activation switch.
The only enabled writer is a separately authorized diagnostic branch in the
existing repository. Normal pushes preserve history; every acknowledgment follows
a fresh independent fetch and complete snapshot verification. An interrupted
push/readback retains its actual commit and never regenerates a forecast.
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

from .integrity import IntegrityError, digest, read_receipt, stamp
from .ledger import LedgerRef
from . import pros004_snapshot as snapshots

REPOSITORY = "NickNicky19/Nicks-multisport-lab-project"
REMOTE_URL = "https://github.com/"+REPOSITORY+".git"
DIAGNOSTIC_BRANCH = "diagnostics/pros004-checkpoint-20261020"
PILOT_BRANCH = "records/nba-20261020-401909088-t90"
ACK_SCHEMA = "nba-pros004-remote-checkpoint-v1"
MAX_COMMAND_SECONDS = 60


class RemoteCheckpointError(IntegrityError):
    """Remote preservation/readback did not establish a complete checkpoint."""


def _require(condition, message):
    if not condition:
        raise RemoteCheckpointError(message)


def _now():
    return datetime.now(timezone.utc)


def _sha(value, name, width=64):
    _require(type(value) is str and re.fullmatch("[a-f0-9]{"+str(width)+"}", value) is not None,
             "invalid "+name)
    return value


def _safe_root(value):
    root = Path(value).absolute()
    for path in (root, *root.parents):
        _require(not path.is_symlink(), "checkpoint paths cannot traverse symlinks")
    return root


def validate_remote_plan(*, branch, remote_url=REMOTE_URL):
    """Validate a candidate destination without admitting operational writes."""
    _require(remote_url in (REMOTE_URL, REMOTE_URL[:-4], "git@github.com:"+REPOSITORY+".git"),
             "remote is not the existing authorized repository")
    _require(type(branch) is str and branch != PILOT_BRANCH and
             (branch == DIAGNOSTIC_BRANCH or re.fullmatch(r"records/pros004-[a-z0-9-]{1,80}", branch) is not None),
             "remote branch is not an isolated PROS004 destination")
    return {"repository": REPOSITORY, "branch": branch,
            "activation": "INACTIVE", "operational_writes_admitted": False}


class GitCheckpointWriter:
    """One retained writer checkout and independent fetch per checkpoint.

    Construction is read-only. ``prepare`` performs Git reads and creates only
    the explicitly supplied new/retained local writer checkout. ``checkpoint``
    pushes only the enabled diagnostic branch. Callers must obtain authorization
    for that concrete diagnostic mutation before invoking it against GitHub.
    Local bare remotes are accepted only by the explicit isolated-test option.
    """
    def __init__(self, source_root, writer_root, *, base_commit, branch=DIAGNOSTIC_BRANCH,
                 remote_url=REMOTE_URL, diagnostic=True, allow_local_test_remote=False,
                 command_seconds=MAX_COMMAND_SECONDS):
        self.source_root = _safe_root(source_root)
        self.root = _safe_root(writer_root)
        self.base_commit = _sha(base_commit, "base commit", 40)
        self.branch, self.remote_url = branch, str(remote_url)
        _require(type(diagnostic) is bool and diagnostic, "genuine remote writes remain INACTIVE")
        _require(branch == DIAGNOSTIC_BRANCH, "only the explicitly isolated diagnostic writer is enabled")
        _require(type(command_seconds) is int and 1 <= command_seconds <= MAX_COMMAND_SECONDS,
                 "remote command budget must be between 1 and 60 seconds")
        self.command_seconds = command_seconds
        self._deadline = None
        self._head = None
        self._local_remote = bool(allow_local_test_remote)
        if self._local_remote:
            candidate = _safe_root(self.remote_url)
            _require(candidate.is_dir() and candidate.is_relative_to(Path(tempfile.gettempdir())),
                     "test remote must be an existing isolated temporary bare repository")
            probe = subprocess.run(["git", "-C", str(candidate), "rev-parse", "--is-bare-repository"],
                                   capture_output=True, text=True, check=False, timeout=command_seconds)
            _require(probe.returncode == 0 and probe.stdout.strip() == "true", "test remote is not bare")
        else:
            validate_remote_plan(branch=branch, remote_url=self.remote_url)
        _require(not self.root.is_relative_to(self.source_root) and not self.source_root.is_relative_to(self.root),
                 "writer and source roots must be separate retained states")

    def _command(self, args, *, cwd=None, check=True):
        remaining = self.command_seconds if self._deadline is None else self._deadline-time.monotonic()
        _require(remaining > 0, "remote checkpoint exceeded its completion budget")
        try:
            result = subprocess.run(args, cwd=cwd or self.root, capture_output=True, text=True,
                                    check=False, timeout=remaining)
        except subprocess.TimeoutExpired as error:
            raise RemoteCheckpointError("remote checkpoint command timed out; preserve retained state") from error
        if check and result.returncode:
            # Do not include environment, remote credential values or full command output.
            raise RemoteCheckpointError(args[0]+" checkpoint command failed ("+str(result.returncode)+")")
        return result

    def _git(self, *args, cwd=None, check=True):
        return self._command(["git", *args], cwd=cwd, check=check)

    def _remote_head(self):
        value = self._git("ls-remote", "--heads", "origin", "refs/heads/"+self.branch).stdout.strip()
        if not value:
            return None
        fields = value.split()
        _require(len(fields) == 2 and fields[1] == "refs/heads/"+self.branch,
                 "remote returned an ambiguous branch identity")
        return _sha(fields[0], "remote commit", 40)

    @contextmanager
    def _writer_lock(self):
        git_dir = self.root/".git"
        _require(git_dir.is_dir() and not git_dir.is_symlink(), "retained writer needs its own Git directory")
        path = git_dir/"pros004-checkpoint.lock"
        _require(not path.is_symlink(), "writer lock cannot be symlinked")
        with path.open("a+b") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RemoteCheckpointError("another remote checkpoint writer is active") from error
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def prepare(self):
        """Recover the same local branch or establish a new isolated checkout."""
        if not self.root.exists():
            self.root.mkdir(parents=True, mode=0o700)
            self._git("init", "--quiet")
            self._git("remote", "add", "origin", self.remote_url)
            remote = self._remote_head()
            target = "refs/heads/"+self.branch if remote is not None else self.base_commit
            self._git("fetch", "--no-tags", "--depth=1", "origin", target)
            self._git("checkout", "--quiet", "-b", self.branch, "FETCH_HEAD")
        _require(self._git("remote", "get-url", "origin").stdout.strip() == self.remote_url,
                 "retained writer origin changed")
        _require(self._git("branch", "--show-current").stdout.strip() == self.branch,
                 "retained writer branch changed")
        _require(not self._git("status", "--porcelain").stdout.strip(),
                 "retained writer has interrupted/uncommitted work; recover exact state before retry")
        self._head = _sha(self._git("rev-parse", "HEAD").stdout.strip(), "writer commit", 40)
        remote = self._remote_head()
        if remote is not None and remote != self._head:
            # A local descendant may be an interrupted normal push. Keep it;
            # remote foreign work cannot be overwritten or silently merged.
            self._git("fetch", "--no-tags", "origin", "refs/heads/"+self.branch)
            ancestor = self._git("merge-base", "--is-ancestor", remote, self._head, check=False)
            _require(ancestor.returncode == 0,
                     "remote writer advanced independently; do not overwrite newer work")
        return {"repository": REPOSITORY, "branch": self.branch, "local_head": self._head,
                "remote_head": remote, "genuine_issuance": 0, "activation": False}

    @staticmethod
    def _entries(manifest):
        return {entry["path"]:entry for entry in manifest["entries"]}

    def _preserve_originals(self, source_manifest):
        if not (self.root/"records").exists():
            return
        retained = snapshots.snapshot_manifest(self.root)
        current = self._entries(source_manifest)
        for path, entry in self._entries(retained).items():
            _require(path in current, "checkpoint source is missing a retained remote original")
            if entry.get("entry_type") == "COMPLETION_JOURNAL" or path.endswith("completion-journal.jsonl"):
                old = (self.root/path).read_bytes()
                _require((self.source_root/path).read_bytes().startswith(old),
                         "completion journal cannot truncate or replace an acknowledged prefix")
            else:
                _require(entry["raw_sha256"] == current[path]["raw_sha256"],
                         "checkpoint would replace a retained original receipt")

    def _readback(self, expected, manifest, reference):
        """Fresh Git initialization/fetch; no shared local object store or cache."""
        with tempfile.TemporaryDirectory(prefix="nml-pros004-independent-checkpoint-") as folder:
            root = Path(folder)/"readback"
            root.mkdir()
            self._git("init", "--quiet", cwd=root)
            self._git("remote", "add", "origin", self.remote_url, cwd=root)
            self._git("fetch", "--no-tags", "--depth=1", "origin", "refs/heads/"+self.branch, cwd=root)
            actual = self._git("rev-parse", "FETCH_HEAD", cwd=root).stdout.strip()
            _require(actual == expected, "independent remote readback commit changed")
            self._git("checkout", "--quiet", "--detach", "FETCH_HEAD", cwd=root)
            _require(snapshots.snapshot_manifest(root) == manifest,
                     "independent remote snapshot differs from original checkpoint")
            path = root/"records"/reference.kind/(reference.record_id+".json")
            body = read_receipt(path, max_bytes=4*1024*1024)
            _require(digest(body) == reference.payload_sha256, "independent reference payload changed")
            raw_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            _require(self._remote_head() == expected, "remote changed during independent checkpoint readback")
            return raw_sha

    def checkpoint(self, reference):
        """Commit/push/read back an exact retained snapshot, then return actual clocks."""
        _require(isinstance(reference, LedgerRef), "checkpoint requires an exact LedgerRef")
        _require(self._head is not None, "prepare the retained writer before checkpointing")
        self._deadline = time.monotonic()+self.command_seconds
        try:
            with self._writer_lock():
                _require(not self._git("status", "--porcelain").stdout.strip(),
                         "interrupted writer state must be recovered without replacing originals")
                local = self._git("rev-parse", "HEAD").stdout.strip()
                _require(local == self._head, "retained writer commit changed")
                remote = self._remote_head()
                if remote is not None and remote != local:
                    self._git("fetch", "--no-tags", "origin", "refs/heads/"+self.branch)
                    _require(self._git("merge-base", "--is-ancestor", remote, local, check=False).returncode == 0,
                             "another writer advanced remote state")
                with tempfile.TemporaryDirectory(prefix="nml-pros004-checkpoint-export-") as folder:
                    snapshot_root = Path(folder)/"snapshot"
                    manifest = snapshots.export_snapshot(self.source_root, snapshot_root)
                    source_path = self.source_root/"records"/reference.kind/(reference.record_id+".json")
                    _require(source_path.is_file() and not source_path.is_symlink(),
                             "checkpoint reference is missing from the retained source")
                    _require(digest(read_receipt(source_path, max_bytes=4*1024*1024)) == reference.payload_sha256,
                             "checkpoint reference differs from retained source bytes")
                    self._preserve_originals(manifest)
                    for entry in manifest["entries"]:
                        path = self.root/entry["path"]
                        path.parent.mkdir(parents=True, exist_ok=True)
                        _require(not path.is_symlink(), "checkpoint cannot replace a symlink")
                        raw = (snapshot_root/entry["path"]).read_bytes()
                        if path.exists() and path.read_bytes() == raw:
                            continue
                        with path.open("wb") as handle:
                            handle.write(raw);handle.flush();os.fsync(handle.fileno())
                    _require(snapshots.snapshot_manifest(self.root) == manifest,
                             "writer snapshot did not preserve the admitted source")
                    self._git("add", "--", *[entry["path"] for entry in manifest["entries"]])
                    if self._git("diff", "--cached", "--quiet", check=False).returncode:
                        self._git("-c", "user.name=Nick's Multisport Lab", "-c", "user.email=research@users.noreply.github.com",
                                  "commit", "--quiet", "-m", "Retain non-issuance PROS004 checkpoint")
                    commit = _sha(self._git("rev-parse", "HEAD").stdout.strip(), "checkpoint commit", 40)
                    self._head = commit  # Retain an interrupted local commit for exact retry.
                    self._git("push", "origin", "HEAD:refs/heads/"+self.branch)
                    raw_sha = self._readback(commit, manifest, reference)
                    completed = _now()
                    _require(time.monotonic() <= self._deadline, "remote readback completed outside its operation budget")
                    return {"schema_version": ACK_SCHEMA, "reference": reference.to_record(),
                            "remote_repository": REPOSITORY, "remote_branch": self.branch,
                            "remote_commit": commit, "snapshot_sha256": digest(manifest),
                            "readback_raw_sha256": raw_sha, "remote_completed_at": stamp(completed)}
        finally:
            self._deadline = None

    __call__ = checkpoint

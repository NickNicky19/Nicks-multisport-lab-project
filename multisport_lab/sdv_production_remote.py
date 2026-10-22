"""Small normal-Git snapshot pointers; original evidence lives in immutable packs.

The first pointer is independently fetched and every new archive pack is read
and typed before a completion clock is captured. A second pointer retains that
proof without claiming recursive self-acknowledgment. No scheduler lives here.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from .integrity import IntegrityError, _decode, canonical, digest, stamp
from .ledger import LedgerRef
from . import sdv_production_common as common
from .sdv_production_archive import archive_snapshot, recover_snapshot, _safe, _file

POINTER_SCHEMA = "nba-sdv-production-pointer-v1"


def validate_pointer(body, *, branch=None, allow_diagnostics=False):
    common.exact(body, {"schema_version", "protocol_id", "branch", "sequence", "snapshot_ref", "snapshot_id",
        "archive_snapshot_id", "previous_pointer_id", "pointer_id"}, "Git archive pointer")
    common.require(body["schema_version"] == POINTER_SCHEMA and body["protocol_id"] == common.PROTOCOL_ID,
                   "Wrong production pointer protocol")
    common.require(type(body["branch"]) is str and (branch is None or body["branch"] == branch)
        and type(body["sequence"]) is int and 1 <= body["sequence"] <= 1000000, "Invalid production pointer identity")
    common.archive_ref(body["snapshot_ref"], diagnostic=allow_diagnostics)
    for key in ("snapshot_id", "archive_snapshot_id"):
        common.sha(body[key])
    common.require(body["previous_pointer_id"] is None if body["sequence"] == 1
        else type(body["previous_pointer_id"]) is str, "Production pointer history is missing")
    if body["previous_pointer_id"] is not None:
        common.sha(body["previous_pointer_id"])
    common.check_seal(body, "pointer_id")
    return body


class ProductionGitCheckpointWriter:
    def __init__(self, repository_root, writer_root, *, base_commit, branch, archive, tag,
                 remote_url=common.REMOTE_URL, allow_local_test_remote=False, command_seconds=60,
                 allow_diagnostics=False):
        self.repository_root, self.root = _safe(repository_root), _safe(writer_root)
        common.require(not self.root.is_relative_to(self.repository_root)
            and not self.repository_root.is_relative_to(self.root), "Production writer must be isolated from source/history")
        common.sha(base_commit, 40)
        self.diagnostic = bool(archive.allow_diagnostics and tag.startswith("diagnostics-"))
        common.require(not self.diagnostic or allow_diagnostics is True,
                       "Diagnostic Git pointer requires an explicit caller scope")
        diagnostic_branch = r"diagnostics/sdv-production-load-[0-9]{8}[Tt][0-9]{6}"
        pattern = diagnostic_branch if self.diagnostic else r"records/sdv-prod-[0-9]{8}-[1-9][0-9]*-[a-f0-9]{12}-s[0-3]"
        common.require(type(branch) is str and re.fullmatch(pattern, branch),
                       "Production pointer branch differs from a bounded event shard")
        common.require(type(command_seconds) is int and 1 <= command_seconds <= (300 if self.diagnostic else 60),
                       "Invalid production remote operation budget")
        self.base_commit, self.branch, self.archive, self.tag = base_commit, branch, archive, tag
        self.remote_url, self.command_seconds = str(remote_url), command_seconds
        self._deadline, self._head = None, None
        self.reader = archive.fresh_reader()
        if allow_local_test_remote:
            remote = _safe(remote_url)
            common.require(remote.is_relative_to(Path(tempfile.gettempdir())) and remote.is_dir(),
                           "Local synthetic remote must be an existing temporary bare repository")
            result = subprocess.run(["git", "-C", str(remote), "rev-parse", "--is-bare-repository"],
                                    capture_output=True, timeout=30, check=False)
            common.require(result.returncode == 0 and result.stdout.strip() == b"true", "Synthetic remote is not bare")
        else:
            common.require(self.remote_url in {common.REMOTE_URL, common.REMOTE_URL[:-4],
                "git@github.com:" + common.REPOSITORY + ".git"}, "Production archive pointer must use this project repository")

    def _git(self, *args, cwd=None, check=True):
        remaining = self.command_seconds if self._deadline is None else self._deadline - time.monotonic()
        common.require(remaining > 0, "Production checkpoint exhausted its actual operation budget")
        env = os.environ.copy()
        for name in ("GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_OBJECT_DIRECTORY", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
            env.pop(name, None)
        try:
            result = subprocess.run(["git", *args], cwd=cwd or self.root, env=env, capture_output=True,
                                    timeout=remaining, check=False)
        except subprocess.TimeoutExpired as exc:
            raise IntegrityError("Production Git operation timed out; retained originals remain unchanged") from exc
        if check:
            common.require(result.returncode == 0, "Production normal-Git checkpoint failed: " + args[0])
        return result

    def _remote_head(self):
        lines = self._git("ls-remote", "--heads", self.remote_url, "refs/heads/" + self.branch).stdout.splitlines()
        common.require(len(lines) <= 1, "Ambiguous production records branch")
        if not lines:
            return None
        fields = lines[0].decode().split()
        common.require(len(fields) == 2 and fields[1] == "refs/heads/" + self.branch, "Production branch reference differs")
        return common.sha(fields[0], 40)

    def prepare(self):
        if not (self.root / ".git").exists():
            self.root.mkdir(parents=True, exist_ok=True)
            common.require(not any(self.root.iterdir()), "New production writer directory is not empty")
            self._git("init", "--quiet")
            self._git("remote", "add", "origin", self.remote_url)
            target = "refs/heads/" + self.branch if self._remote_head() else self.base_commit
            self._git("fetch", "--no-tags", "origin", target)
            self._git("checkout", "--quiet", "-b", self.branch, "FETCH_HEAD")
        common.require(self._git("remote", "get-url", "origin").stdout.decode().strip() == self.remote_url
            and self._git("branch", "--show-current").stdout.decode().strip() == self.branch,
            "Production writer repository/branch changed")
        self._head = common.sha(self._git("rev-parse", "HEAD").stdout.decode().strip(), 40)
        remote = self._remote_head()
        if remote and remote != self._head:
            self._git("fetch", "--no-tags", "origin", "refs/heads/" + self.branch)
            common.require(self._git("merge-base", "--is-ancestor", remote, self._head, check=False).returncode == 0,
                           "Production remote contains newer legitimate work; do not overwrite")
        return {"branch": self.branch, "local_head": self._head, "remote_head": remote}

    def _pointer(self, root=None):
        root = Path(root or self.root)
        latest = root / "latest.json"
        if not latest.exists():
            return None
        body = validate_pointer(_decode(_file(latest, 64 * 1024)), branch=self.branch, allow_diagnostics=self.diagnostic)
        current, visited = body, set()
        while True:
            common.require(current["pointer_id"] not in visited, "Production pointer history cycles")
            visited.add(current["pointer_id"])
            path = root / "history" / (current["pointer_id"] + ".json")
            common.require(_decode(_file(path, 64 * 1024)) == current, "Immutable production pointer history differs")
            previous = current["previous_pointer_id"]
            if previous is None:
                break
            current = validate_pointer(_decode(_file(root / "history" / (previous + ".json"), 64 * 1024)), branch=self.branch,
                                       allow_diagnostics=self.diagnostic)
            common.require(current["sequence"] == body["sequence"] - len(visited), "Production pointer sequence is incomplete")
        return body

    def _publish(self, ref, snapshot):
        previous = self._pointer()
        if previous and previous["snapshot_ref"] == ref:
            # A process can stop after creating exact pointer files but before
            # committing them. Resume that retained write; never include other
            # staged or working-tree changes in an archive-pointer commit.
            self._commit_pointer(previous)
            self._git("push", "origin", "HEAD:refs/heads/" + self.branch)
            return self._head, previous
        body = common.seal({"schema_version": POINTER_SCHEMA, "protocol_id": common.PROTOCOL_ID,
            "branch": self.branch, "sequence": previous["sequence"] + 1 if previous else 1,
            "snapshot_ref": ref, "snapshot_id": snapshot["ledger_snapshot"]["snapshot_id"],
            "archive_snapshot_id": snapshot["archive_snapshot_id"],
            "previous_pointer_id": previous["pointer_id"] if previous else None}, "pointer_id")
        validate_pointer(body, branch=self.branch, allow_diagnostics=self.diagnostic)
        history = _safe(self.root / "history" / (body["pointer_id"] + ".json"))
        history.parent.mkdir(exist_ok=True)
        encoded = canonical(body) + b"\n"
        if history.exists():
            common.require(_file(history, 64 * 1024) == encoded, "Cannot replace immutable pointer history")
        else:
            with history.open("xb") as handle:
                handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
        latest = _safe(self.root / "latest.json")
        temporary = self.root / "latest.json.tmp"
        common.require(not temporary.is_symlink(), "Pointer staging path is a symlink")
        with temporary.open("wb") as handle:
            handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, latest)
        self._commit_pointer(body)
        self._git("push", "origin", "HEAD:refs/heads/" + self.branch)
        return self._head, body

    def _commit_pointer(self, body):
        allowed = {"latest.json", "history/" + body["pointer_id"] + ".json"}
        paths = self._git("status", "--porcelain=v1", "-z", "--untracked-files=all").stdout.split(b"\0")
        for row in paths:
            if row:
                common.require(row[:2] not in {b"R ",b" R",b"C ",b" C"}
                    and row[3:].decode() in allowed,
                    "Production writer contains unrelated work; do not commit or overwrite it")
        self._git("add", "--", "latest.json", "history/" + body["pointer_id"] + ".json")
        if self._git("diff", "--cached", "--quiet", check=False).returncode:
            self._git("-c", "user.name=Nick's Multisport Lab", "-c", "user.email=research@users.noreply.github.com",
                      "commit", "--quiet", "-m", "Retain production research archive pointer")
        self._head = common.sha(self._git("rev-parse", "HEAD").stdout.decode().strip(), 40)

    def _readback(self, commit, expected, references=()):
        with tempfile.TemporaryDirectory(prefix="nml-production-pointer-readback-") as folder:
            root = Path(folder) / "git"
            root.mkdir()
            self._git("init", "--quiet", cwd=root)
            self._git("fetch", "--no-tags", "--depth=1", self.remote_url, commit, cwd=root)
            common.require(self._git("rev-parse", "FETCH_HEAD", cwd=root).stdout.decode().strip() == commit,
                           "Independent production fetched commit differs")
            self._git("checkout", "--quiet", "--detach", "FETCH_HEAD", cwd=root)
            common.require(not (root / ".git/objects/info/alternates").exists(), "Production readback has alternates")
            pointer = self._pointer(root)
            common.require(pointer == expected, "Independent production pointer differs")
            recovered = recover_snapshot(pointer["snapshot_ref"], self.reader, Path(folder) / "state",
                                         source_root=self.repository_root, independent=False)
            snapshot = recovered.snapshot_manifest()
            common.require(snapshot["snapshot_id"] == pointer["snapshot_id"], "Pointer and recovered typed inventory differ")
            for ref in references:
                recovered.ledger.read(ref)
            return {"remote_recovered_at": stamp(common.now()), "snapshot_id": snapshot["snapshot_id"],
                "snapshot_ref": pointer["snapshot_ref"], "recovered_records": snapshot["records"],
                "recovered_bytes": snapshot["bytes"],
                "recovered_unpublished_files": len(snapshot["unpublished_entries"]),
                "recovered_unpublished_bytes": sum(row["bytes"] for row in snapshot["unpublished_entries"]),
                "pointer_id": pointer["pointer_id"], "commit": commit}

    def restore(self, store):
        common.require(self._head is not None, "Prepare the production records writer first")
        self._bind_resolvers(store)
        pointer = self._pointer()
        if pointer is None:
            return store
        with tempfile.TemporaryDirectory(prefix="nml-production-restore-") as folder:
            recovered = recover_snapshot(pointer["snapshot_ref"], self.reader, folder,
                                         source_root=self.repository_root, independent=False)
            manifest = recovered.snapshot_manifest()
            for row in manifest["entries"] + manifest["unpublished_entries"]:
                source, target = Path(folder) / row["path"], _safe(Path(store.root) / row["path"])
                raw = _file(source, 16 * 1024 * 1024)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    common.require(_file(target, 16 * 1024 * 1024) == raw, "Remote restore cannot replace retained originals")
                else:
                    with target.open("xb") as handle:
                        handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        store.recover()
        return store

    def inspect(self):
        """Read-only independent current-pointer recovery, without new receipts."""
        common.require(self._head is not None, "Prepare the production records writer first")
        pointer = self._pointer()
        if pointer is None:
            return {"branch": self.branch, "commit": self._head, "snapshot_ref": None,
                    "recovered_records": 0, "recovered_bytes": 0,
                    "recovered_unpublished_files": 0, "recovered_unpublished_bytes": 0}
        return {"branch": self.branch, **self._readback(self._head, pointer)}

    def _bind_resolvers(self, store):
        if store.source_resolver is None:
            store.source_resolver = self.archive.recover_source
        if store.snapshot_resolver is None:
            store.snapshot_resolver = lambda ref: self.archive.get_json(ref)["ledger_snapshot"]

    def checkpoint(self, store, references=()):
        refs = (references,) if isinstance(references, LedgerRef) else tuple(references)
        common.require(self._head is not None and len(refs) <= 64 and len(set(refs)) == len(refs)
                       and all(isinstance(ref, LedgerRef) for ref in refs), "Invalid production checkpoint references")
        self._deadline = time.monotonic() + self.command_seconds
        try:
            self._bind_resolvers(store)
            previous = self._pointer()
            ref = archive_snapshot(store, self.archive, tag=self.tag,
                                   previous=previous["snapshot_ref"] if previous else None)
            snapshot = self.archive.get_json(ref)
            commit, pointer = self._publish(ref, snapshot)
            original = self._readback(commit, pointer, refs)
            common.require(time.monotonic() <= self._deadline, "Actual production original readback exceeded operation budget")
            existing = {body["target"] for _, body in store.records()
                        if body["schema_version"] == common.COMPLETION_SCHEMA}
            pending = tuple(target for target in refs if target.record_id not in existing)
            if pending:
                with store._verified_remote_completion(pending, ref, original["remote_recovered_at"]):
                    for target in pending:
                        local = store.local_completion(target)
                        store.record_completion(target, local["local_completed_at"], original["remote_recovered_at"], ref)
                final_ref = archive_snapshot(store, self.archive, tag=self.tag, previous=ref)
                commit, pointer = self._publish(final_ref, self.archive.get_json(final_ref))
                proof = self._readback(commit, pointer, refs)
            else:
                proof = original
            common.require(time.monotonic() <= self._deadline, "Production proof retention exceeded operation budget")
            return {"branch": self.branch, **proof, "original_recovery": original,
                    "original_records_recovered_at": original["remote_recovered_at"],
                    "proof_metadata_recovered_at": proof["remote_recovered_at"],
                    "metadata_acknowledgment_recursive": False,
                    "archive_transport": self.archive.request_metrics(), "readback_transport": self.reader.request_metrics()}
        finally:
            self._deadline = None

    def flush(self, store):
        return self.checkpoint(store)


ProductionGitWriter = ProductionGitCheckpointWriter

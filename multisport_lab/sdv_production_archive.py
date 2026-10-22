"""Content-addressed original-byte archives in this repository's GitHub Releases.

No source provider is contacted. Objects are create-only; collisions, changed
bytes, quota exhaustion and ambiguous write results fail closed. FileArchive is
an explicit persistent offline test backend, never evidence of hosted recovery.
"""
from __future__ import annotations

from contextlib import contextmanager
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import urllib.parse
import urllib.request
import urllib.error
import zlib

from .integrity import IntegrityError, _decode, canonical, digest
from . import sdv_production_common as common

SOURCE_SCHEMA = "nba-sdv-production-source-archive-v1"
SNAPSHOT_SCHEMA = "nba-sdv-production-archive-snapshot-v1"
PACK_SCHEMA = "nba-sdv-production-receipt-pack-v1"
MAX_RAW = 64 * 1024 * 1024
MAX_JSON = 1024 * 1024
MAX_WIRE = 16 * 1024 * 1024
CHUNK = 1024 * 1024
SNAPSHOT_MAX_WIRE = 128 * 1024


class ArchiveHTTPError(IntegrityError):
    def __init__(self, status, message=None):
        self.http_status, self.api_message = status, message
        detail = "HTTP " + str(status) if status is not None else "HTTP status unknown"
        if message:
            detail += ": " + message
        super().__init__("GitHub archive API request failed (" + detail + "); retain state and do not change transports")


def _safe_api_error(raw):
    try:
        body = _decode(raw)
        message = body.get("message") if type(body) is dict else None
    except IntegrityError:
        return None
    if type(message) is not str:
        return None
    message = re.sub(r"https?://\S+", "[URL]", message)
    message = re.sub(r"(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)", "[REDACTED]", message)
    message = re.sub(r"(?i)(authorization|token|sig|jwt|password)\s*[:=]\s*\S+", r"\1=[REDACTED]", message)
    return message.replace("\n", " ")[:240]


def require(value, message):
    if not value:
        raise IntegrityError(message)


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _safe(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Archive path traverses a symlink")
    return path


def _file(path, limit):
    path = _safe(path)
    require(stat.S_ISREG(path.stat().st_mode), "Archive input is not a regular file")
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    require(len(raw) <= limit, "Archive input exceeds its byte limit")
    return raw


def _tag(tag, diagnostics):
    common.archive_ref({"tag": tag, "name": "object-" + "0" * 64 + ".z", "sha256": "0" * 64, "bytes": 1},
                       diagnostic=diagnostics)
    return tag


def _wire(raw, tag, diagnostics):
    require(type(raw) is bytes and len(raw) <= MAX_RAW, "Archive raw object exceeds 64 MiB")
    _tag(tag, diagnostics)
    packed = zlib.compress(raw, 9)
    require(0 < len(packed) <= MAX_WIRE, "Archive encoded object exceeds 16 MiB; split it explicitly")
    sha = _hash(packed)
    return packed, {"tag": tag, "name": "object-" + sha + ".z", "sha256": sha, "bytes": len(packed)}


def _unpack(packed, ref, maximum, diagnostics):
    common.archive_ref(ref, diagnostic=diagnostics)
    require(type(maximum) is int and 0 < maximum <= MAX_RAW, "Invalid archive decoded-byte limit")
    require(type(packed) is bytes and len(packed) == ref["bytes"] and _hash(packed) == ref["sha256"],
            "Archive exact wire bytes/hash differ")
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(packed, maximum + 1)
    except zlib.error as exc:
        raise IntegrityError("Invalid archived zlib object") from exc
    require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail and len(raw) <= maximum,
            "Archived object is truncated, oversized or has trailing members")
    return raw


def verify_source_bytes(raw, metadata, metadata_raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_RAW and type(metadata_raw) is bytes
            and 0 < len(metadata_raw) <= MAX_JSON and type(metadata) is dict, "Invalid source archive bytes")
    require(metadata.get("asset_bytes") == len(raw) and metadata.get("asset_sha256") == _hash(raw)
            and metadata.get("metadata_bytes") == len(metadata_raw)
            and metadata.get("metadata_sha256") == _hash(metadata_raw), "Source archive metadata does not bind originals")
    return raw, metadata, metadata_raw


class _Archive:
    allow_diagnostics = False

    def fresh_reader(self):
        raise NotImplementedError

    def request_metrics(self):
        return {"gh_api_actions": 0, "public_http_requests": 0,
                "write_budget_bytes": self.write_budget_bytes, "new_bytes_reserved": self.new_bytes_reserved,
                "reserved_objects": self.reserved_objects, "write_budget_objects": self.write_budget_objects,
                "new_objects_reserved": self.new_objects_reserved}

    def _reserve_new_bytes(self, additional):
        require(type(additional) is int and additional > 0 and type(self.new_bytes_reserved) is int
            and self.new_bytes_reserved >= 0 and (self.write_budget_bytes is None or
                type(self.write_budget_bytes) is int and self.write_budget_bytes >= 0),
            "Invalid per-run immutable archive write reserve")
        require(type(self.new_objects_reserved) is int and self.new_objects_reserved >= 0
            and (self.write_budget_objects is None or type(self.write_budget_objects) is int
                and self.write_budget_objects >= 0), "Invalid per-run immutable archive object reserve")
        require(self.write_budget_bytes is None or self.new_bytes_reserved + additional <= self.write_budget_bytes,
                "Per-run immutable archive write budget exhausted before mutation")
        require(self.write_budget_objects is None or self.new_objects_reserved + 1 <= self.write_budget_objects,
                "Per-run immutable archive object budget exhausted before mutation")
        # An ambiguous write may have completed remotely. Never refund it or
        # reset this action counter in an idempotent retry on the same writer.
        self.new_bytes_reserved += additional
        self.new_objects_reserved += 1

    def put_json(self, body, *, tag):
        return self.put(canonical(body), tag=tag)

    def get_json(self, ref, *, max_raw_bytes=MAX_JSON):
        return _decode(self.get(ref, max_raw_bytes=max_raw_bytes))

    def retain_source(self, raw, metadata, metadata_raw, *, tag):
        verify_source_bytes(raw, metadata, metadata_raw)
        chunks = []
        for index, offset in enumerate(range(0, len(raw), CHUNK)):
            part = raw[offset:offset + CHUNK]
            chunks.append({"index": index, "raw_bytes": len(part), "raw_sha256": _hash(part),
                           "archive_ref": self.put(part, tag=tag)})
        body = common.seal({"schema_version": SOURCE_SCHEMA, "protocol_id": common.PROTOCOL_ID,
            "metadata": metadata, "asset_bytes": len(raw), "asset_sha256": _hash(raw),
            "asset_chunks": chunks, "metadata_bytes": len(metadata_raw), "metadata_sha256": _hash(metadata_raw),
            "metadata_ref": self.put(metadata_raw, tag=tag)}, "source_manifest_id")
        return self.put_json(body, tag=tag)

    def recover_source(self, ref):
        body = self.get_json(ref)
        common.exact(body, {"schema_version", "protocol_id", "metadata", "asset_bytes", "asset_sha256",
            "asset_chunks", "metadata_bytes", "metadata_sha256", "metadata_ref", "source_manifest_id"}, "source archive")
        require(body["schema_version"] == SOURCE_SCHEMA and body["protocol_id"] == common.PROTOCOL_ID,
                "Wrong source archive protocol")
        common.check_seal(body, "source_manifest_id")
        require(type(body["asset_bytes"]) is int and 0 < body["asset_bytes"] <= MAX_RAW
                and type(body["metadata_bytes"]) is int and 0 < body["metadata_bytes"] <= MAX_JSON,
                "Source archive exceeds decoded budget")
        chunks = body["asset_chunks"]
        require(type(chunks) is list and len(chunks) == (body["asset_bytes"] + CHUNK - 1) // CHUNK,
                "Source archive chunk inventory differs")
        raw = bytearray()
        for index, row in enumerate(chunks):
            common.exact(row, {"index", "raw_bytes", "raw_sha256", "archive_ref"}, "source chunk")
            expected = min(CHUNK, body["asset_bytes"] - index * CHUNK)
            require(type(row["index"]) is int and row["index"] == index and row["raw_bytes"] == expected,
                    "Source chunk order/length differs")
            part = self.get(row["archive_ref"], max_raw_bytes=CHUNK)
            require(len(part) == expected and _hash(part) == row["raw_sha256"], "Source chunk raw hash differs")
            raw.extend(part)
        metadata_raw = self.get(body["metadata_ref"], max_raw_bytes=MAX_JSON)
        require(len(raw) == body["asset_bytes"] and _hash(raw) == body["asset_sha256"]
                and len(metadata_raw) == body["metadata_bytes"] and _hash(metadata_raw) == body["metadata_sha256"],
                "Rebuilt source original differs")
        return verify_source_bytes(bytes(raw), body["metadata"], metadata_raw)

    def _quota(self, tag, inventory, additional=0, additional_objects=0):
        used = sum(size for current, _, size in inventory)
        month = sum(size for current, _, size in inventory if current == tag)
        require(type(self.reserved_bytes) is int and self.reserved_bytes >= 0, "Invalid outstanding grading reserve")
        require(type(self.reserved_objects) is int and self.reserved_objects >= 0
            and type(additional_objects) is int and additional_objects >= 0,
                "Invalid outstanding archive object reserve")
        policy = common.make_policy()
        return {"tag": tag, "tag_bytes": month, "total_bytes": used, "reserved_bytes": self.reserved_bytes,
            "additional_bytes": additional, "maximum_tag_bytes": policy["archive_month_bytes"],
            "maximum_total_bytes": policy["archive_total_bytes"],
            "total_objects": len(inventory), "reserved_objects": self.reserved_objects,
            "additional_objects": additional_objects, "maximum_total_objects": 100000,
            "fits": month + additional + self.reserved_bytes <= policy["archive_month_bytes"]
            and used + additional + self.reserved_bytes <= policy["archive_total_bytes"]
            and len(inventory) + self.reserved_objects + additional_objects <= 100000}


class FileArchive(_Archive):
    """Persistent explicit offline archive for synthetic/restart verification."""
    def __init__(self, root, *, allow_diagnostics=False, reserved_bytes=0, write_budget_bytes=None,
                 reserved_objects=0, write_budget_objects=None):
        self.root = _safe(root)
        self.root.mkdir(parents=True, exist_ok=True)
        require(type(allow_diagnostics) is bool, "Invalid diagnostic archive setting")
        self.allow_diagnostics, self.reserved_bytes = allow_diagnostics, reserved_bytes
        self.write_budget_bytes, self.new_bytes_reserved = write_budget_bytes, 0
        self.reserved_objects, self.write_budget_objects, self.new_objects_reserved = reserved_objects, write_budget_objects, 0

    def fresh_reader(self):
        return FileArchive(self.root, allow_diagnostics=self.allow_diagnostics, reserved_bytes=self.reserved_bytes,
                           reserved_objects=self.reserved_objects)

    def inventory(self):
        rows = []
        for directory in self.root.iterdir():
            if directory.name == ".writer.lock":
                continue
            require(directory.is_dir() and not directory.is_symlink(), "Unexpected local archive path")
            _tag(directory.name, True)
            for path in directory.iterdir():
                require(path.is_file() and not path.is_symlink() and re.fullmatch(r"object-[a-f0-9]{64}\.z", path.name),
                        "Unexpected local archive object")
                rows.append((directory.name, path.name, path.stat().st_size))
        return rows

    def quota(self, tag):
        return self._quota(_tag(tag, self.allow_diagnostics), self.inventory())

    def put(self, raw, tag):
        packed, ref = _wire(raw, tag, self.allow_diagnostics)
        with (self.root / ".writer.lock").open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            path = self.root / tag / ref["name"]
            if path.exists():
                require(_file(path, MAX_WIRE) == packed, "Immutable archive collision")
                return ref
            require(self._quota(tag, self.inventory(), len(packed), 1)["fits"], "Archive quota/reserved grading budget exhausted")
            self._reserve_new_bytes(len(packed))
            path.parent.mkdir(exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".object-", dir=self.root)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(packed); handle.flush(); os.fsync(handle.fileno())
                os.link(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
        return ref

    def get(self, ref, max_raw_bytes):
        common.archive_ref(ref, diagnostic=self.allow_diagnostics)
        return _unpack(_file(self.root / ref["tag"] / ref["name"], MAX_WIRE), ref,
                       max_raw_bytes, self.allow_diagnostics)


class GitHubReleaseArchive(_Archive):
    """Official own-repository release APIs through existing authenticated gh.

    No --clobber, PATCH or DELETE operation exists. An ambiguous upload is
    reconciled by exact content-addressed readback; it is never blindly retried.
    """
    def __init__(self, repository=common.REPOSITORY, *, allow_diagnostics=False, reserved_bytes=0,
                 command_seconds=30, write_budget_bytes=None, reserved_objects=0, write_budget_objects=None):
        require(repository == common.REPOSITORY, "Archive must use the existing project repository")
        require(type(allow_diagnostics) is bool and type(command_seconds) is int and 1 <= command_seconds <= 60,
                "Invalid GitHub archive command bounds")
        self.repository, self.allow_diagnostics, self.reserved_bytes = repository, allow_diagnostics, reserved_bytes
        self.command_seconds = command_seconds
        self.write_budget_bytes, self.new_bytes_reserved = write_budget_bytes, 0
        self.reserved_objects, self.write_budget_objects, self.new_objects_reserved = reserved_objects, write_budget_objects, 0
        self._release_cache, self._asset_cache, self._wire_cache = {}, {}, {}
        self._source_cache = {}
        self._inventory_cache = None
        self._gh_actions = self._public_requests = 0

    def fresh_reader(self):
        return GitHubReleaseArchive(self.repository, allow_diagnostics=self.allow_diagnostics,
            reserved_bytes=self.reserved_bytes, command_seconds=self.command_seconds,
            reserved_objects=self.reserved_objects)

    def request_metrics(self):
        return {"gh_api_actions": self._gh_actions, "public_http_requests": self._public_requests,
                "gh_internal_redirect_requests": "UNKNOWN_NOT_INSTRUMENTED", "automatic_write_retries": 0,
                "maximum_actions_per_client": 1000, "maximum_global_objects": 100000,
                "write_budget_bytes": self.write_budget_bytes, "new_bytes_reserved": self.new_bytes_reserved,
                "reserved_objects": self.reserved_objects, "write_budget_objects": self.write_budget_objects,
                "new_objects_reserved": self.new_objects_reserved,
                "known_inventory_objects": len(self._inventory_cache) if self._inventory_cache is not None else None}

    def _cache_wire(self, key, packed):
        if sum(len(value) for value in self._wire_cache.values()) + len(packed) > 128 * 1024 * 1024:
            self._wire_cache.clear()
        self._wire_cache[key] = packed

    def recover_source(self, ref):
        common.archive_ref(ref, diagnostic=self.allow_diagnostics)
        key = (ref["tag"], ref["name"], ref["sha256"], ref["bytes"])
        if key in self._source_cache:
            raw, metadata_raw_canonical, original = self._source_cache[key]
            return verify_source_bytes(raw, _decode(metadata_raw_canonical), original)
        raw, metadata, original = super().recover_source(ref)
        encoded_metadata = canonical(metadata)
        size = len(raw) + len(encoded_metadata) + len(original)
        if size <= MAX_RAW:
            if sum(len(r) + len(m) + len(o) for r, m, o in self._source_cache.values()) + size > MAX_RAW:
                self._source_cache.clear()
            self._source_cache[key] = (raw, encoded_metadata, original)
        return raw, metadata, original

    def _gh(self, args, *, input_bytes=None, maximum=MAX_WIRE, missing=False, reconcile=False):
        require(self._gh_actions + self._public_requests < 1000,
                "Archive action guard exhausted; retain originals without more transport")
        self._gh_actions += 1
        try:
            result = subprocess.run(["gh", "api", *args], input=input_bytes, capture_output=True,
                                    timeout=self.command_seconds, check=False)
        except subprocess.TimeoutExpired as exc:
            raise IntegrityError("GitHub archive transport timed out; no alternate transport") from exc
        require(len(result.stdout) <= maximum, "GitHub archive response exceeds bounded bytes")
        if result.returncode:
            # Never print credentials, signed download URLs or arbitrary CLI stderr.
            match = re.search(rb"HTTP ([0-9]{3})", result.stderr)
            status = int(match[1]) if match else None
            if missing and status == 404:
                return None
            if reconcile and status in {None, 422, 500, 502, 503, 504}:
                return None
            raise ArchiveHTTPError(status, _safe_api_error(result.stdout))
        return result.stdout

    def _json(self, endpoint, *, method="GET", body=None, missing=False, reconcile=False):
        args = [endpoint, "--method", method]
        if body is not None:
            args += ["--input", "-", "-H", "Content-Type: application/json"]
        raw = self._gh(args, input_bytes=canonical(body) if body is not None else None,
                       maximum=MAX_WIRE, missing=missing, reconcile=reconcile)
        return _decode(raw) if raw is not None else None

    def _release(self, tag, *, create=False):
        _tag(tag, self.allow_diagnostics)
        endpoint = "repos/" + self.repository + "/releases/tags/" + tag
        release = self._release_cache.get(tag)
        if release is None:
            release = self._json(endpoint, missing=True)
        if release is None and create:
            body = {"tag_name": tag, "name": tag, "draft": tag.startswith("diagnostics-"),
                    "prerelease": tag.startswith("diagnostics-"),
                    "body": "Immutable Nick's Multisport Lab research archive. Content-addressed objects; no trading or qualification."}
            release = self._json("repos/" + self.repository + "/releases", method="POST", body=body, reconcile=True)
            if release is None:
                # One read-only reconciliation handles a completed but unacknowledged create.
                release = self._json(endpoint, missing=True)
                require(release is not None, "Release creation unacknowledged; no blind retry")
        if release is not None:
            require(type(release) is dict and type(release.get("id")) is int and release.get("tag_name") == tag,
                    "GitHub archive release identity differs")
            require(not tag.startswith("diagnostics-") or release.get("draft") is True,
                    "Diagnostic release must remain draft")
            self._release_cache[tag] = release
        return release

    def _assets(self, release):
        if release["id"] in self._asset_cache:
            return self._asset_cache[release["id"]]
        rows = []
        for page in range(1, 1001):
            batch = self._json("repos/" + self.repository + "/releases/" + str(release["id"])
                               + "/assets?per_page=100&page=" + str(page))
            require(type(batch) is list and len(batch) <= 100, "Invalid GitHub archive asset inventory")
            rows.extend(batch)
            if len(batch) < 100:
                self._asset_cache[release["id"]] = rows
                return rows
        raise IntegrityError("GitHub archive inventory exceeds 100,000 objects; no unbounded pagination")

    def inventory(self):
        if self._inventory_cache is not None:
            return list(self._inventory_cache)
        rows = []
        for page in range(1, 13):
            releases = self._json("repos/" + self.repository + "/releases?per_page=100&page=" + str(page))
            require(type(releases) is list and len(releases) <= 100, "Invalid own-repository release inventory")
            for release in releases:
                tag = release.get("tag_name", "")
                if not (re.fullmatch(r"nml-nba-records-v1-[0-9]{6}", tag)
                        or re.fullmatch(r"diagnostics-nml-nba-[a-z0-9-]{1,64}", tag)):
                    continue
                for asset in self._assets(release):
                    require(type(asset.get("size")) is int and asset["size"] >= 0, "Invalid archived asset size")
                    rows.append((tag, asset.get("name"), asset["size"]))
                    require(len(rows) <= 100000, "Global archive inventory exceeds 100,000 objects")
            if len(releases) < 100:
                self._inventory_cache = rows
                return rows
        raise IntegrityError("Own-repository release inventory exceeds bounded pagination")

    def quota(self, tag):
        return self._quota(_tag(tag, self.allow_diagnostics), self.inventory())

    def _asset(self, release, name):
        matches = [asset for asset in self._assets(release) if asset.get("name") == name]
        require(len(matches) <= 1, "Ambiguous immutable archive name")
        return matches[0] if matches else None

    def put(self, raw, tag):
        packed, ref = _wire(raw, tag, self.allow_diagnostics)
        release = self._release(tag)
        asset = self._asset(release, ref["name"]) if release else None
        if asset is not None:
            require(self.get(ref, max_raw_bytes=max(1, len(raw))) == raw, "Existing immutable archive object differs")
            return ref
        inventory = self.inventory()
        require(len(inventory) < 100000, "Global archive object reserve exhausted; retain originals without more uploads")
        require(self._quota(tag, inventory, len(packed), 1)["fits"], "GitHub archive quota/reserved grading budget exhausted")
        self._reserve_new_bytes(len(packed))
        release = release or self._release(tag, create=True)
        endpoint = "https://uploads.github.com/repos/" + self.repository + "/releases/" + str(release["id"])
        endpoint += "/assets?name=" + urllib.parse.quote(ref["name"], safe="")
        # One upload, at most one read-only reconciliation; never clobber or delete.
        # gh sends stdin as chunked unless Content-Length is explicit. The
        # release-upload contract requires the exact encoded wire byte count.
        result = self._gh([endpoint, "--method", "POST", "--input", "-", "-H", "Content-Type: application/zlib",
                           "-H", "Content-Length: " + str(len(packed))],
                          input_bytes=packed, maximum=MAX_JSON, reconcile=True)
        if result is not None:
            asset = _decode(result)
            require(asset.get("name") == ref["name"] and asset.get("size") == len(packed),
                    "GitHub upload acknowledgment differs")
            self._asset_cache.setdefault(release["id"], []).append(asset)
        else:
            self._asset_cache.pop(release["id"], None)
        require(self.get(ref, max_raw_bytes=max(1, len(raw))) == raw,
                "GitHub upload lacks independent exact-byte recovery")
        if self._inventory_cache is not None:
            self._inventory_cache.append((tag, ref["name"], len(packed)))
        return ref

    def get(self, ref, max_raw_bytes):
        common.archive_ref(ref, diagnostic=self.allow_diagnostics)
        key = (ref["tag"], ref["name"], ref["sha256"], ref["bytes"])
        if key in self._wire_cache:
            return _unpack(self._wire_cache[key], ref, max_raw_bytes, self.allow_diagnostics)
        if not ref["tag"].startswith("diagnostics-"):
            packed = self._public_object(ref)
            raw = _unpack(packed, ref, max_raw_bytes, self.allow_diagnostics)
            self._cache_wire(key, packed)
            return raw
        release = self._release(ref["tag"])
        require(release is not None, "Archived release is missing")
        asset = self._asset(release, ref["name"])
        require(asset is not None and asset.get("size") == ref["bytes"] and type(asset.get("id")) is int,
                "Archived object identity/size differs")
        packed = self._gh(["repos/" + self.repository + "/releases/assets/" + str(asset["id"]),
                           "-H", "Accept: application/octet-stream"], maximum=MAX_WIRE)
        raw = _unpack(packed, ref, max_raw_bytes, self.allow_diagnostics)
        self._cache_wire(key, packed)
        return raw

    def _public_object(self, ref):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, response, code, message, headers, new_url):
                return None
        opener = urllib.request.build_opener(NoRedirect())
        url = "https://github.com/" + self.repository + "/releases/download/" + ref["tag"] + "/" + ref["name"]
        for attempt in range(2):
            require(self._gh_actions + self._public_requests < 1000, "Archive action guard exhausted")
            self._public_requests += 1
            request = urllib.request.Request(url, headers={"User-Agent": "NicksMultisportLab/archive-readback"})
            try:
                try:
                    response = opener.open(request, timeout=min(25, self.command_seconds))
                except urllib.error.HTTPError as exc:
                    response = exc
                with response:
                    status, location = response.code, response.headers.get("Location")
                    raw = response.read(MAX_WIRE + 1)
            except (OSError, ValueError) as exc:
                raise IntegrityError("Public archive read failed; no API fallback or alternate transport") from exc
            require(len(raw) <= MAX_WIRE, "Public archive object exceeds wire budget")
            if status == 200:
                return raw
            require(attempt == 0 and status in {302, 303, 307, 308} and type(location) is str,
                    "Public archive response failed; no retry or alternate transport")
            target = urllib.parse.urlsplit(location)
            require(target.scheme == "https" and target.hostname == "release-assets.githubusercontent.com"
                    and not target.username and not target.password and target.port in {None, 443},
                    "Public archive redirect is outside the allowed own-repository asset route")
            url = location
        raise IntegrityError("Public archive redirect budget exhausted")


def archive_snapshot(store, archive, *, tag, previous=None):
    snapshot = store.snapshot_manifest()
    from .sdv_production_store import validate_snapshot_manifest
    validate_snapshot_manifest(snapshot)
    entries = snapshot["entries"] + snapshot.get("unpublished_entries", [])
    retained = {}
    if previous is not None:
        prior = archive.get_json(previous)
        require(prior.get("schema_version") == SNAPSHOT_SCHEMA, "Wrong previous archive snapshot")
        common.check_seal(prior, "archive_snapshot_id")
        indexed = {row["path"]: row for row in entries}
        old = prior["ledger_snapshot"]
        require(all(indexed.get(row["path"]) == row for row in old["entries"] + old.get("unpublished_entries", [])),
                "Checkpoint would erase or replace an original")
        retained = {row["path"]: row for row in prior["objects"]}
    objects = []
    pending = []
    def publish_pack():
        if not pending:
            return
        pack = common.seal({"schema_version": PACK_SCHEMA, "protocol_id": common.PROTOCOL_ID,
                           "entries": list(pending)}, "pack_id")
        require(len(canonical(pack)) <= CHUNK, "Receipt pack exceeds exact one-MiB limit")
        ref = archive.put_json(pack, tag=tag)
        objects.extend({"path": row["path"], "archive_ref": ref, "index": index}
                       for index, row in enumerate(pending))
        pending.clear()
    for entry in entries:
        path = entry["path"]
        require(type(path) is str and re.fullmatch(
            r"records/[a-z_]+/(?:[a-f0-9]{64}\.json|\.receipt-[A-Za-z0-9_-]{1,128})", path),
                "Unsafe archived receipt path")
        if path in retained:
            objects.append(retained[path])
            continue
        raw = _file(Path(store.root) / path, MAX_WIRE)
        require(len(raw) == entry["bytes"] and _hash(raw) == entry["sha256"], "Snapshot receipt changed during retention")
        row = {**entry, "raw_base64": base64.b64encode(raw).decode("ascii")}
        candidate = {"schema_version": PACK_SCHEMA, "protocol_id": common.PROTOCOL_ID,
                     "entries": pending + [row], "pack_id": "0" * 64}
        if pending and len(canonical(candidate)) > CHUNK:
            publish_pack()
        pending.append(row)
    publish_pack()
    indexed_objects = {row["path"]: row for row in objects}
    require(len(indexed_objects) == len(entries), "Archive pack lost or duplicated a receipt")
    objects = [indexed_objects[row["path"]] for row in entries]
    body = common.seal({"schema_version": SNAPSHOT_SCHEMA, "protocol_id": common.PROTOCOL_ID,
        "ledger_snapshot": snapshot, "objects": objects}, "archive_snapshot_id")
    require(len(canonical(body)) <= MAX_JSON, "Full archive snapshot exceeds its decoded byte ceiling")
    require(len(zlib.compress(canonical(body), 9)) <= SNAPSHOT_MAX_WIRE,
            "Full archive snapshot exceeds its reserved 128-KiB encoded ceiling")
    return archive.put_json(body, tag=tag)


def recover_snapshot(ref, archive, destination, *, source_root, independent=True):
    """Independent reads rebuild exact original receipts, then strict typed replay."""
    if independent:
        archive = archive.fresh_reader()
    common.archive_ref(ref, diagnostic=archive.allow_diagnostics)
    require(ref.get("bytes", MAX_WIRE) <= SNAPSHOT_MAX_WIRE,
            "Archived full snapshot exceeds the reserved 128-KiB encoded ceiling")
    body = archive.get_json(ref)
    common.exact(body, {"schema_version", "protocol_id", "ledger_snapshot", "objects", "archive_snapshot_id"},
                 "archive snapshot")
    require(body["schema_version"] == SNAPSHOT_SCHEMA and body["protocol_id"] == common.PROTOCOL_ID,
            "Wrong archive snapshot protocol")
    common.check_seal(body, "archive_snapshot_id")
    snapshot = body["ledger_snapshot"]
    from .sdv_production_store import validate_snapshot_manifest
    validate_snapshot_manifest(snapshot)
    entries = snapshot["entries"] + snapshot["unpublished_entries"]
    require(len(entries) <= 512 and type(body["objects"]) is list and len(body["objects"]) == len(entries),
            "Archive snapshot inventory exceeds runtime limits")
    root = _safe(destination)
    root.mkdir(parents=True, exist_ok=True)
    seen, total = set(), 0
    for entry, item in zip(entries, body["objects"]):
        path = entry.get("path")
        require(type(path) is str and re.fullmatch(
            r"records/[a-z_]+/(?:[a-f0-9]{64}\.json|\.receipt-[A-Za-z0-9_-]{1,128})", path)
                and path not in seen and item.get("path") == path, "Archive receipt inventory/path differs")
        seen.add(path)
        pack = archive.get_json(item["archive_ref"], max_raw_bytes=CHUNK)
        common.exact(pack, {"schema_version", "protocol_id", "entries", "pack_id"}, "receipt pack")
        require(pack["schema_version"] == PACK_SCHEMA and pack["protocol_id"] == common.PROTOCOL_ID,
                "Wrong receipt pack protocol")
        common.check_seal(pack, "pack_id")
        index = item.get("index")
        require(type(index) is int and type(pack["entries"]) is list and 0 <= index < len(pack["entries"]),
                "Archive receipt pack index differs")
        row = pack["entries"][index]
        require({k: v for k, v in row.items() if k != "raw_base64"} == entry,
                "Archived receipt pack identity differs")
        try:
            raw = base64.b64decode(row["raw_base64"], validate=True)
        except (ValueError, TypeError) as exc:
            raise IntegrityError("Invalid receipt pack encoding") from exc
        require(len(raw) == entry.get("bytes") and _hash(raw) == entry.get("sha256"), "Archived receipt hash differs")
        total += len(raw)
        require(total <= 32 * 1024 * 1024, "Recovered runtime ledger exceeds byte budget")
        target = _safe(root / path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            require(_file(target, MAX_WIRE) == raw, "Recovery cannot replace an original receipt")
        else:
            with target.open("xb") as handle:
                handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    from .sdv_production_store import ProductionStore
    recovered = ProductionStore(root, source_root=source_root, source_resolver=archive.recover_source,
        snapshot_resolver=lambda value: archive.get_json(value)["ledger_snapshot"],
        **({"allow_diagnostics": True} if archive.allow_diagnostics else {}))
    recovered.recover()
    require(recovered.snapshot_manifest() == snapshot, "Independent typed ledger replay differs from archived snapshot")
    return recovered

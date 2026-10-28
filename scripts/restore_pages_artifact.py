"""Restore strictly verified, already published research data before a fresh build.

This reads this repository's existing Pages artifacts only. It never reads a
sports provider, issues forecasts, writes a ledger, or deploys a site. The normal
publication builder decides whether to retain these exact old bytes after a new
channel update fails; their original generation clocks are not refreshed here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from multisport_lab.integrity import IntegrityError, stamp, utc
from multisport_lab.publication import read_manifest
from multisport_lab import sdv_production_publication as production

REPOSITORY = "NickNicky19/Nicks-multisport-lab-project"
WORKFLOW = ".github/workflows/pages.yml"
MAX_RUNS = 16
MAX_CANDIDATES = 8
MAX_MEMBERS = 4096
MAX_METADATA_BYTES = 2 * 1024 * 1024
# These are ceilings for this read-only seed, not larger production budgets.
MAX_ARCHIVE_BYTES = production.MAX_TOTAL_BYTES
MAX_FILE_BYTES = production.MAX_ASSET_BYTES


def require(condition, message):
    if not condition:
        raise IntegrityError(message)


class GitHubArtifacts:
    """One bounded GET per operation through the already configured GitHub CLI."""

    def _get(self, endpoint, maximum, *, destination=None):
        command = ["gh", "api", "--method", "GET", endpoint]
        deadline = time.monotonic() + 60
        total, parts = 0, []
        # Do not echo CLI stderr, credentials or signed artifact redirect URLs.
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
            try:
                with selectors.DefaultSelector() as poller:
                    poller.register(process.stdout, selectors.EVENT_READ)
                    while poller.get_map():
                        remaining = deadline - time.monotonic()
                        require(remaining > 0, "Prior Pages artifact GET timed out")
                        ready = poller.select(remaining)
                        require(bool(ready), "Prior Pages artifact GET timed out")
                        chunk = os.read(process.stdout.fileno(), min(65536, maximum - total + 1))
                        if not chunk:
                            poller.unregister(process.stdout)
                            break
                        total += len(chunk)
                        require(total <= maximum, "Prior Pages artifact response exceeds byte limit")
                        if destination is None:
                            parts.append(chunk)
                        else:
                            destination.write(chunk)
                require(process.wait(timeout=max(0.1, deadline-time.monotonic())) == 0,
                        "Prior Pages artifact GET failed; no retry or alternate transport")
            except BaseException:
                process.kill()
                process.wait()
                raise
        return b"".join(parts) if destination is None else total

    def _json(self, endpoint):
        return json.loads(self._get(endpoint, MAX_METADATA_BYTES))

    def runs(self):
        response = self._json("repos/"+REPOSITORY+
            "/actions/workflows/pages.yml/runs?branch=main&status=success&per_page="+str(MAX_RUNS))
        rows = response.get("workflow_runs") if type(response) is dict else None
        require(type(rows) is list and len(rows) <= MAX_RUNS, "Invalid bounded prior Pages run inventory")
        return rows

    def artifacts(self, run_id):
        response = self._json("repos/"+REPOSITORY+"/actions/runs/"+str(run_id)+"/artifacts?per_page=8")
        rows = response.get("artifacts") if type(response) is dict else None
        require(type(rows) is list and len(rows) <= 8, "Invalid bounded Pages artifact inventory")
        return rows

    def download(self, artifact_id, target, maximum):
        with target.open("xb") as destination:
            return self._get("repos/"+REPOSITORY+"/actions/artifacts/"+str(artifact_id)+"/zip",
                             maximum, destination=destination)


def _candidate_run(row, now):
    require(type(row) is dict and type(row.get("id")) is int and row["id"] > 0,
            "Invalid prior Pages run identity")
    repository, head_repository = row.get("repository"), row.get("head_repository")
    require(row.get("head_branch") == "main" and row.get("path") == WORKFLOW
            and row.get("event") in {"push", "workflow_dispatch"}
            and row.get("status") == "completed" and row.get("conclusion") == "success"
            and re.fullmatch(r"[a-f0-9]{40}", row.get("head_sha", ""))
            and type(repository) is dict and repository.get("full_name") == REPOSITORY
            and type(head_repository) is dict and head_repository.get("full_name") == REPOSITORY,
            "Prior Pages run is outside the trusted own-main workflow")
    require(utc(row["created_at"]) <= utc(row["updated_at"]) <= now,
            "Prior Pages run clock is invalid")
    return row


def _extract_data(archive_path, folder):
    """Inspect every ZIP/TAR entry; extract only bounded ordinary data JSON."""
    with zipfile.ZipFile(archive_path) as zipped:
        entries = zipped.infolist()
        require(len(entries) == 1 and entries[0].filename == "artifact.tar"
                and not entries[0].is_dir() and not entries[0].flag_bits & 1
                and not stat.S_ISLNK(entries[0].external_attr >> 16)
                and entries[0].compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                and 0 < entries[0].file_size <= MAX_ARCHIVE_BYTES,
                "Unsupported or oversized Pages artifact ZIP")
        tar_path = folder/"artifact.tar"
        with zipped.open(entries[0]) as source, tar_path.open("xb") as destination:
            total = 0
            while chunk := source.read(65536):
                total += len(chunk)
                require(total <= MAX_ARCHIVE_BYTES, "Pages artifact TAR exceeds byte limit")
                destination.write(chunk)
        require(total == entries[0].file_size, "Pages artifact ZIP length differs")
    data_root = folder/"extracted"
    data_root.mkdir()
    seen, total = set(), 0
    with tarfile.open(tar_path, mode="r:") as archive:
        for number, member in enumerate(archive, 1):
            require(number <= MAX_MEMBERS, "Pages artifact member count exceeds limit")
            path = PurePosixPath(member.name)
            require(not path.is_absolute() and ".." not in path.parts and "\\" not in member.name
                    and "\0" not in member.name and len(member.name) <= 4096
                    and (member.isfile() or member.isdir()), "Unsafe Pages artifact member")
            name = str(path)
            require(name not in seen, "Duplicate Pages artifact member")
            seen.add(name)
            require(name in {".", "data"} and member.isdir() or member.isfile() and
                (len(path.parts) == 1 and path.suffix in {".html", ".css", ".js", ".mjs", ".svg", ".webmanifest"}
                 or len(path.parts) == 2 and path.parts[0] == "data"
                 and re.fullmatch(r"[A-Za-z0-9_.-]+\.json", path.name)),
                "Unknown Pages artifact path")
            if not member.isfile():
                continue
            require(0 <= member.size <= MAX_ARCHIVE_BYTES, "Pages artifact member exceeds byte limit")
            total += member.size
            require(total <= MAX_ARCHIVE_BYTES, "Pages artifact contents exceed byte limit")
            if len(path.parts) != 2:
                continue
            require(member.size <= MAX_FILE_BYTES, "Pages data asset exceeds existing per-file limit")
            target = data_root.joinpath(*path.parts)
            target.parent.mkdir(exist_ok=True)
            with archive.extractfile(member) as source, target.open("xb") as destination:
                body = source.read(MAX_FILE_BYTES+1)
                require(len(body) == member.size and len(body) <= MAX_FILE_BYTES,
                        "Pages data asset is truncated or oversized")
                destination.write(body)
    return data_root


def restore(output, *, now, reader=None):
    """Select the newest complete valid populated candidate within fixed bounds."""
    now, output = utc(now), Path(output)
    require(not output.is_symlink() and output.resolve() != ROOT and not ROOT.is_relative_to(output.resolve()),
            "Prior Pages output must be a separate non-symlink directory")
    if output.exists():
        return {"status": "EXISTING_OUTPUT_PRESERVED", "checked_at": stamp(now)}
    reader = reader or GitHubArtifacts()
    output.parent.mkdir(parents=True, exist_ok=True)
    rejected, examined = [], 0
    try:
        runs = reader.runs()
        require(type(runs) is list and len(runs) <= MAX_RUNS, "Unbounded prior Pages runs")
        runs = sorted(runs, key=lambda row: row.get("created_at")
            if type(row) is dict and type(row.get("created_at")) is str else "", reverse=True)
        for run in runs:
            try:
                _candidate_run(run, now)
                artifacts = reader.artifacts(run["id"])
                require(type(artifacts) is list and len(artifacts) <= 8
                        and all(type(row) is dict for row in artifacts), "Unbounded or invalid Pages artifacts")
                candidates = [row for row in artifacts if row.get("name") == "github-pages"]
                require(len(candidates) <= 1, "Ambiguous prior Pages artifact")
                if not candidates:
                    continue
                artifact = candidates[0]
                artifact_run = artifact.get("workflow_run")
                require(artifact.get("expired") is False and type(artifact.get("id")) is int
                        and artifact["id"] > 0 and type(artifact.get("size_in_bytes")) is int
                        and 0 < artifact["size_in_bytes"] <= MAX_ARCHIVE_BYTES
                        and type(artifact_run) is dict and artifact_run.get("id") == run["id"]
                        and artifact_run.get("head_sha") == run["head_sha"],
                        "Expired, oversized or unrelated Pages artifact")
                if examined >= MAX_CANDIDATES:
                    break
                examined += 1
                with tempfile.TemporaryDirectory(prefix=".nml-prior-pages-", dir=output.parent) as directory:
                    folder = Path(directory); packed = folder/"download.zip"
                    size = reader.download(artifact["id"], packed, artifact["size_in_bytes"])
                    require(size == artifact["size_in_bytes"] == packed.stat().st_size,
                            "Prior Pages artifact download size differs")
                    with packed.open("rb") as stream:
                        sha = hashlib.file_digest(stream, "sha256").hexdigest()
                    if artifact.get("digest") is not None:
                        require(artifact["digest"] == "sha256:"+sha, "Prior Pages artifact digest differs")
                    seed = _extract_data(packed, folder)
                    manifest = read_manifest(seed/"data", now=now, validate_auxiliary=False)
                    require(manifest["build_commit"] == run["head_sha"], "Prior artifact build differs from its run")
                    descriptor = manifest.get("production_research")
                    require(descriptor is not None, "Prior Pages production channel is unavailable")
                    paths = production.publication_asset_paths(seed/"data", descriptor, now=now)
                    recovered = production.read_publication(seed/"data", descriptor, now=now)
                    require(recovered["index"]["counts"]["genuine_forecasts"] > 0,
                            "Prior Pages artifact has no genuine production forecasts")
                    allowed = {"manifest.json", *(ref["path"] for ref in manifest["sports"]), *paths}
                    for path in (seed/"data").iterdir():
                        if path.name not in allowed:
                            path.unlink()
                    # The target is absent; do not overwrite another writer's work.
                    require(not output.exists() and not output.is_symlink(), "Prior Pages output appeared during recovery")
                    os.replace(seed, output)
                    return {"status": "RESTORED_VERIFIED_PRIOR_PRODUCTION", "checked_at": stamp(now),
                            "source_run_id": run["id"], "artifact_id": artifact["id"],
                            "artifact_sha256": sha, "build_commit": manifest["build_commit"],
                            "original_site_published_at": manifest["published_at"],
                            "original_production_generated_at": descriptor["generated_at"],
                            "counts": recovered["index"]["counts"], "examined": examined, "rejected": rejected}
            except (ValueError, KeyError, TypeError, OSError, EOFError,
                    zipfile.BadZipFile, tarfile.TarError, zlib.error) as error:
                rejected.append({"run_id": run.get("id") if type(run) is dict else None,
                                 "reason": type(error).__name__+": prior Pages artifact rejected"})
    except (ValueError, KeyError, TypeError, OSError) as error:
        return {"status": "PRIOR_PAGES_LOOKUP_UNAVAILABLE", "checked_at": stamp(now),
                "reason": type(error).__name__+": bounded prior artifact lookup unavailable",
                "examined": examined, "rejected": rejected}
    return {"status": "NO_VALID_PRIOR_PAGES_ARTIFACT", "checked_at": stamp(now),
            "examined": examined, "rejected": rejected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output"))
    arguments = parser.parse_args()
    print(json.dumps(restore(arguments.output, now=datetime.now(timezone.utc)), sort_keys=True))


if __name__ == "__main__":
    main()

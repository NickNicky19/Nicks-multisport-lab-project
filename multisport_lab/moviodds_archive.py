"""Private immutable recovery of one already-captured MoviOdds source package.

Only the existing own-repository GitHub object transport is reused. This module
does not use its SDV source manifest, contact a provider, refresh a capture,
generate a forecast, publish a release, or admit public offer display. The fixed
diagnostic tag must remain an authenticated draft before every transport access.
FileArchive is an explicitly offline test backend, never hosted evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import re

from .integrity import IntegrityError, _bounded_bytes, _decode, canonical, digest, stamp
from . import moviodds_offer as offers
from . import sdv_production_archive as transport
from .sdv_production_common import archive_ref

TAG = "diagnostics-nml-nba-moviodds-20261023"
SCHEMA = "nba-moviodds-private-archive-v1"
REF_SCHEMA = "nba-moviodds-private-archive-reference-v1"
RESULT_SCHEMA = "nba-moviodds-private-archive-result-v1"
NATIVE_REF_SCHEMA = "nba-moviodds-native-private-archive-v1"
MODE = "PRIVATE_SOURCE_REPLAY"
MAX_PACKAGE_BYTES = 32 * 1024 * 1024
MAX_PACKAGE_FILES = 512
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_METADATA_BYTES = 256 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
MAX_NEW_WIRE_BYTES = 8 * 1024 * 1024
MAX_NEW_OBJECTS = 32
FILENAMES = tuple(sorted([name + suffix for name in offers.URLS
                          for suffix in (".body", ".metadata.json")]
                         + ["review-intent.json", "review.json"]))
_SHA = re.compile(r"[a-f0-9]{64}\Z")


def require(condition, message):
    if not condition:
        raise IntegrityError(message)


def _strict(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except IntegrityError:
            raise
        except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError, OSError) as error:
            raise IntegrityError("Malformed or unavailable private archive evidence") from error
    return checked


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _fields(value, names, message):
    require(type(value) is dict and set(value) == set(names), message)


def _limit(name):
    require(name in FILENAMES, "Unexpected/protected private archive filename")
    return MAX_BODY_BYTES if name.endswith(".body") else MAX_METADATA_BYTES


def _safe(path):
    path = Path(os.path.abspath(path))
    require(not any(p.is_symlink() for p in (path, *path.parents)),
            "Private archive path traverses a symlink")
    return path


def _ref(value):
    archive_ref(value, diagnostic=True)
    require(value["tag"] == TAG and value["bytes"] <= MAX_NEW_WIRE_BYTES,
            "Private archive reference leaves its fixed draft/budget")
    return value


def _validate_files(files, *, now, allow_synthetic):
    """Validate memory originals without inventing a file, capture or clock."""
    _fields(files, FILENAMES, "Exactly sixteen original package files are required")
    for name, raw in files.items():
        require(type(raw) is bytes and 0 < len(raw) <= _limit(name),
                "Original package file exceeds its byte ceiling")
    require(len(files) <= MAX_PACKAGE_FILES
            and sum(map(len, files.values())) <= MAX_PACKAGE_BYTES,
            "Original package exceeds unchanged file/byte ceilings")
    assets = {key: {"raw": files[key + ".body"],
                    "metadata_raw": files[key + ".metadata.json"]} for key in offers.URLS}
    review, intent = _decode(files["review.json"]), _decode(files["review-intent.json"])
    signature = {key: {field: _hash(raw) for field, raw in value.items()}
                 for key, value in assets.items()}
    require(type(review) is dict and type(review.get("event")) is dict
            and intent == {"fixture": review["event"]["id"], "originals": signature,
                           "normalized_at": review["normalized_at"]},
            "Private archive intent, original bytes or normalization clock differs")
    replay = offers.replay_review(review, assets, now=now, allow_synthetic=allow_synthetic)
    return review, replay


def _load_files(directory, *, now, allow_synthetic):
    directory = _safe(directory)
    require(directory.is_dir(), "Original package directory is absent")
    entries = list(directory.iterdir())
    require(len(entries) <= MAX_PACKAGE_FILES
            and all(p.is_file() and not p.is_symlink() for p in entries)
            and sum(p.stat().st_size for p in entries) <= MAX_PACKAGE_BYTES,
            "Original directory exceeds unchanged bounds or contains unsafe files")
    # Preview HTML and other local products are deliberately never uploaded.
    files = {name: _bounded_bytes(directory / name, _limit(name)) for name in FILENAMES}
    review, replay = _validate_files(files, now=now, allow_synthetic=allow_synthetic)
    return files, review, replay


def _manifest(files, review):
    rows = {}
    for name in FILENAMES:
        _, ref = transport._wire(files[name], TAG, True)
        rows[name] = {"bytes": len(files[name]), "sha256": _hash(files[name]),
                      "archive_ref": ref}
    body = {"schema_version": SCHEMA, "mode": MODE,
            "source": "MoviOdds", "source_namespace": "moviodds",
            "source_schema": offers.SCHEMA,
            "adapter_source_sha256": _hash(Path(offers.__file__).read_bytes()),
            "archive_format": "fixed-sixteen-original-files-zlib-content-addressed-v1",
            "tag": TAG, "review_id": review["review_id"],
            "evidence_lane": review["evidence_lane"],
            "source_observed_at": review["observed_at"],
            "source_normalized_at": review["normalized_at"],
            "file_count": len(files), "total_bytes": sum(map(len, files.values())),
            "files": rows, "public_admission": False, "ticket_eligibility": False}
    body["manifest_id"] = digest(body)
    require(len(canonical(body)) <= MAX_MANIFEST_BYTES, "Private archive manifest exceeds ceiling")
    return body


@_strict
def _validate_manifest(body, *, reference=None):
    _fields(body, {"schema_version", "mode", "source", "source_namespace", "source_schema",
        "adapter_source_sha256", "archive_format", "tag", "review_id", "evidence_lane",
        "source_observed_at", "source_normalized_at", "file_count", "total_bytes", "files",
        "public_admission", "ticket_eligibility", "manifest_id"}, "Invalid private archive manifest fields")
    require(body["schema_version"] == SCHEMA and body["mode"] == MODE
            and body["source"] == "MoviOdds" and body["source_namespace"] == "moviodds"
            and body["source_schema"] == offers.SCHEMA
            and body["adapter_source_sha256"] == _hash(Path(offers.__file__).read_bytes())
            and body["archive_format"] == "fixed-sixteen-original-files-zlib-content-addressed-v1"
            and body["tag"] == TAG and body["public_admission"] is False
            and body["ticket_eligibility"] is False,
            "Private archive source/version/namespace or scope differs")
    require(type(body["manifest_id"]) is str and _SHA.fullmatch(body["manifest_id"])
            and body["manifest_id"] == digest({k: v for k, v in body.items() if k != "manifest_id"})
            and type(body["review_id"]) is str and _SHA.fullmatch(body["review_id"]),
            "Private archive manifest or review seal differs")
    require(body["evidence_lane"] in {"ACTUAL_SOURCE_REPLAY", "SYNTHETIC_TEST"}
            and offers._clock(body["source_observed_at"]) <= offers._clock(body["source_normalized_at"]),
            "Private archive source clocks or evidence lane differ")
    require(type(body["file_count"]) is int and body["file_count"] == len(FILENAMES)
            and type(body["total_bytes"]) is int and 0 < body["total_bytes"] <= MAX_PACKAGE_BYTES,
            "Private archive file/byte inventory differs")
    _fields(body["files"], FILENAMES, "Unexpected/protected archive file inventory")
    total = 0
    for name, row in body["files"].items():
        _fields(row, {"bytes", "sha256", "archive_ref"}, "Invalid private archive file entry")
        require(type(row["bytes"]) is int and 0 < row["bytes"] <= _limit(name)
                and type(row["sha256"]) is str and _SHA.fullmatch(row["sha256"]),
                "Private archive entry exceeds its type ceiling")
        _ref(row["archive_ref"])
        total += row["bytes"]
    require(total == body["total_bytes"], "Private archive total bytes differ")
    if reference is not None:
        _validate_reference(reference)
        require(reference["manifest_id"] == body["manifest_id"]
                and reference["review_id"] == body["review_id"],
                "Private archive reference identifies another manifest/review")
    return body


def _validate_reference(reference):
    _fields(reference, {"schema_version", "mode", "tag", "manifest_id", "review_id", "manifest_ref",
                        "public_admission"}, "Invalid private archive reference")
    require(reference["schema_version"] == REF_SCHEMA and reference["mode"] == MODE
            and reference["tag"] == TAG and reference["public_admission"] is False
            and all(type(reference[k]) is str and _SHA.fullmatch(reference[k])
                    for k in ("manifest_id", "review_id")), "Private archive reference scope differs")
    _ref(reference["manifest_ref"])
    return reference


def _wire_budget(manifest, reference):
    refs = [reference, *(row["archive_ref"] for row in manifest["files"].values())]
    unique = {}
    for ref in refs:
        _ref(ref)
        require(ref["name"] not in unique or unique[ref["name"]] == ref["bytes"],
                "Conflicting content-addressed wire inventory")
        unique[ref["name"]] = ref["bytes"]
    require(len(unique) <= MAX_NEW_OBJECTS and sum(unique.values()) <= MAX_NEW_WIRE_BYTES,
            "Private archive exceeds bounded wire/object reservation")
    return {"unique_objects": len(unique), "wire_bytes": sum(unique.values()),
            "maximum_objects": MAX_NEW_OBJECTS, "maximum_wire_bytes": MAX_NEW_WIRE_BYTES}


class GuardedGitHubReleaseArchive(transport.GitHubReleaseArchive):
    """Source-specific guards at the real object transport boundary.

    The reused transport has legitimate metadata/object caches. This private
    namespace also requires a fresh draft check after inventory/quota work and
    immediately before its actual POST or nested GET; an outer wrapper alone
    would check too early. No production transport implementation is changed.
    """
    def _private_gate(self):
        require(self.allow_diagnostics is True
                and self.repository == "NickNicky19/Nicks-multisport-lab-project",
                "Private object transport destination differs")
        self._release_cache.clear(); self._asset_cache.clear()
        self._wire_cache.clear(); self._source_cache.clear()
        release = self._json("repos/" + self.repository + "/releases/tags/" + TAG, missing=True)
        if release is None:
            release = self._listed_diagnostic_release(TAG)
        require(type(release) is dict and type(release.get("id")) is int
                and release["id"] > 0 and release.get("tag_name") == TAG
                and release.get("draft") is True,
                "Private object transport requires the current authenticated draft")
        self._release_cache[TAG] = release
        return release

    def _private_capacity(self, release, added_bytes):
        self._asset_cache.pop(release["id"], None)
        assets = self._assets(release)
        require(len(assets) < MAX_NEW_OBJECTS and all(type(a) is dict
            and type(a.get("size")) is int and a["size"] > 0
            and type(a.get("name")) is str
            and re.fullmatch(r"object-[a-f0-9]{64}\.z", a["name"]) for a in assets)
            and len({a["name"] for a in assets}) == len(assets)
            and sum(a["size"] for a in assets) + added_bytes <= MAX_NEW_WIRE_BYTES,
            "Private namespace exceeds its total wire/object ceiling")

    def _gh(self, args, **kwargs):
        endpoint = args[0] if type(args) is list and args else ""
        upload = re.fullmatch(r"https://uploads\.github\.com/repos/"
            + re.escape(self.repository) + r"/releases/([0-9]+)/assets\?name=object-[a-f0-9]{64}\.z", endpoint)
        download = re.fullmatch(r"repos/" + re.escape(self.repository)
                               + r"/releases/assets/[0-9]+", endpoint)
        if upload:
            require(type(kwargs.get("input_bytes")) is bytes and kwargs["input_bytes"],
                    "Private object upload lacks bounded original wire bytes")
            release = self._private_gate()
            require(str(release["id"]) == upload[1], "Private upload release identity changed")
            self._private_capacity(release, len(kwargs["input_bytes"]))
            # Asset-inventory work itself can take time. Recheck at the POST.
            current = self._private_gate()
            require(current["id"] == release["id"], "Private upload destination changed")
        elif download:
            self._private_gate()
        return super()._gh(args, **kwargs)

    def put(self, raw, tag):
        require(tag == TAG, "Private object writer leaves its source namespace")
        self._private_gate()
        return super().put(raw, tag)

    def get(self, ref, max_raw_bytes):
        _ref(ref)
        self._private_gate()  # Includes cache hits and put()'s nested readback.
        return super().get(ref, max_raw_bytes)

    def fresh_reader(self):
        return GuardedGitHubReleaseArchive(self.repository, allow_diagnostics=self.allow_diagnostics,
            reserved_bytes=self.reserved_bytes, command_seconds=self.command_seconds,
            reserved_objects=self.reserved_objects)


class PrivateMoviOddsArchive:
    """One writer, fixed private draft, independent fresh-reader semantic recovery."""
    def __init__(self, backend, *, allow_synthetic=False):
        require(isinstance(backend, (transport.FileArchive, transport.GitHubReleaseArchive))
                and backend.allow_diagnostics is True and type(allow_synthetic) is bool,
                "Explicit private/offline archive backend required")
        require(not isinstance(backend, transport.GitHubReleaseArchive)
                or isinstance(backend, GuardedGitHubReleaseArchive),
                "Private hosted archive requires guarded object transport")
        # Preserve existing ambiguous-write counters; never refund/restart them.
        for name, ceiling in (("write_budget_bytes", MAX_NEW_WIRE_BYTES),
                              ("write_budget_objects", MAX_NEW_OBJECTS)):
            value = getattr(backend, name)
            require(value is None or type(value) is int and 0 <= value <= ceiling,
                    "Private archive transport reserve exceeds its fixed bound")
            if value is None:
                setattr(backend, name, ceiling)
        self.backend, self.allow_synthetic = backend, allow_synthetic

    @property
    def hosted(self):
        return isinstance(self.backend, transport.GitHubReleaseArchive)

    def _draft(self, *, create=False):
        if not self.hosted:
            return "OFFLINE_FILE_TEST_NO_HOST_PRIVACY_CLAIM"
        backend = self.backend
        require(backend.repository == "NickNicky19/Nicks-multisport-lab-project",
                "Private archive destination is not the existing project")
        # A warm transport cache is not current evidence that a release is draft.
        backend._release_cache.clear()
        backend._asset_cache.clear()
        backend._wire_cache.clear()
        backend._source_cache.clear()
        release = backend._json("repos/" + backend.repository + "/releases/tags/" + TAG, missing=True)
        if release is None:
            release = backend._listed_diagnostic_release(TAG)
        if release is None and create:
            backend._release(TAG, create=True)
            # Confirm the newly created destination with an uncached read, too.
            return self._draft(create=False)
        require(type(release) is dict and type(release.get("id")) is int
                and release["id"] > 0 and release.get("tag_name") == TAG
                and release.get("draft") is True,
                "Private archive release is missing, published or misidentified")
        backend._release_cache[TAG] = release
        return "AUTHENTICATED_DRAFT_RELEASE"

    def _get(self, ref, maximum):
        _ref(ref)
        self._draft()
        return self.backend.get(ref, max_raw_bytes=maximum)

    def _put(self, raw):
        _, expected = transport._wire(raw, TAG, True)
        self._draft(create=True)
        if not self.hosted:
            inventory = [(name, size) for tag, name, size in self.backend.inventory() if tag == TAG]
            present = any(name == expected["name"] for name, _ in inventory)
            require(len(inventory) + (not present) <= MAX_NEW_OBJECTS
                    and sum(size for _, size in inventory) + (0 if present else expected["bytes"]) <= MAX_NEW_WIRE_BYTES,
                    "Private offline namespace exceeds its total wire/object ceiling")
        result = self.backend.put(raw, tag=TAG)
        require(result == expected, "Private archive write reference differs")
        self._draft()
        return result

    def fresh_reader(self):
        return PrivateMoviOddsArchive(self.backend.fresh_reader(), allow_synthetic=self.allow_synthetic)

    @_strict
    def _read(self, reference, *, now):
        reference = self._source_reference(reference)
        _validate_reference(reference)
        manifest = _decode(self._get(reference["manifest_ref"], MAX_MANIFEST_BYTES))
        _validate_manifest(manifest, reference=reference)
        budget = _wire_budget(manifest, reference["manifest_ref"])
        files = {}
        for name in FILENAMES:
            row = manifest["files"][name]
            raw = self._get(row["archive_ref"], _limit(name))
            require(len(raw) == row["bytes"] and _hash(raw) == row["sha256"],
                    "Private archive original bytes differ")
            files[name] = raw
        review, replay = _validate_files(files, now=now, allow_synthetic=self.allow_synthetic)
        require(manifest == _manifest(files, review), "Private archive metadata differs from original semantic replay")
        self._draft()
        return files, manifest, replay, budget

    def _source_reference(self, reference):
        if type(reference) is dict and set(reference) == {"manifest_ref", "manifest_id"}:
            _ref(reference["manifest_ref"])
            require(type(reference["manifest_id"]) is str and _SHA.fullmatch(reference["manifest_id"]),
                    "Invalid compact source archive manifest identity")
            manifest = _decode(self._get(reference["manifest_ref"], MAX_MANIFEST_BYTES))
            _validate_manifest(manifest)
            require(reference["manifest_id"] == manifest["manifest_id"], "Compact source manifest differs")
            return {"schema_version": REF_SCHEMA, "mode": MODE, "tag": TAG,
                    "manifest_id": manifest["manifest_id"], "review_id": manifest["review_id"],
                    "manifest_ref": reference["manifest_ref"], "public_admission": False}
        return _validate_reference(reference)

    @_strict
    def archive(self, directory, *, now):
        files, review, _ = _load_files(directory, now=now, allow_synthetic=self.allow_synthetic)
        manifest = _manifest(files, review)
        _, manifest_ref = transport._wire(canonical(manifest), TAG, True)
        budget = _wire_budget(manifest, manifest_ref)
        # All sources and reservations are checked before the first remote write.
        for name in FILENAMES:
            require(self._put(files[name]) == manifest["files"][name]["archive_ref"],
                    "Private archive object differs from preflight")
        require(self._put(canonical(manifest)) == manifest_ref, "Manifest write differs from preflight")
        reference = {"schema_version": REF_SCHEMA, "mode": MODE, "tag": TAG,
                     "manifest_id": manifest["manifest_id"], "review_id": review["review_id"],
                     "manifest_ref": manifest_ref, "public_admission": False}
        # A new client/object database must actually recover every original.
        recovered, observed, replay, _ = self.fresh_reader()._read(reference, now=now)
        require(recovered == files and observed == manifest, "Fresh private archive recovery differs")
        return self._result(reference, replay, budget, "ARCHIVED_AND_INDEPENDENTLY_RECOVERED")

    @_strict
    def recover(self, reference, destination, *, now):
        from .player_line_review import _create, _private_directory
        reference = self._source_reference(reference)
        files, manifest, replay, budget = self.fresh_reader()._read(reference, now=now)
        destination = _private_directory(Path(destination), Path(__file__).resolve().parents[1])
        entries = list(destination.iterdir())
        require(all(p.name in FILENAMES and p.is_file() and not p.is_symlink() for p in entries),
                "Recovery destination has unrelated/protected entries")
        for name in FILENAMES:
            _create(destination, name, files[name], maximum=_limit(name))
            fd = os.open(destination, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        proof = offers.verify_package(destination, now=now, allow_synthetic=self.allow_synthetic)
        require(proof["review_id"] == manifest["review_id"], "Recovered package identity differs")
        return self._result(reference, replay, budget, "RECOVERED_CREATE_ONLY")

    @_strict
    def load_recovered_assets(self, reference, *, now):
        reference = self._source_reference(reference)
        files, manifest, _, _ = self.fresh_reader()._read(reference, now=now)
        return {"assets": {k: {"raw": files[k + ".body"],
                              "metadata_raw": files[k + ".metadata.json"]} for k in offers.URLS},
                "review": _decode(files["review.json"]), "manifest": manifest,
                "manifest_ref": reference["manifest_ref"], "manifest_id": manifest["manifest_id"],
                "reference": reference}

    @_strict
    def archive_native_offer(self, source_reference, offer, *, now):
        from . import native_offer
        sources = self.load_recovered_assets(source_reference, now=now)
        native_offer.replay_native_offer(offer, sources["assets"], now=now, allow_synthetic=self.allow_synthetic)
        require(offer["original_review_id"] == sources["review"]["review_id"], "Native offer references another source review")
        raw = canonical(offer)
        require(0 < len(raw) <= native_offer.MAX_OFFER_BYTES, "Native offer exceeds its encoded byte ceiling")
        _, offer_ref = transport._wire(raw, TAG, True)
        descriptor = {"schema_version": NATIVE_REF_SCHEMA, "mode": MODE, "tag": TAG,
            "source_reference": sources["reference"], "offer_ref": offer_ref,
            "offer_id": offer["offer_id"], "offer_sha256": _hash(raw), "offer_bytes": len(raw),
            "offer_normalized_at": offer["normalized_at"],
            "native_adapter_source_sha256": _hash(Path(native_offer.__file__).read_bytes()),
            "public_admission": False, "ticket_eligibility": False}
        _, descriptor_ref = transport._wire(canonical(descriptor), TAG, True)
        # Both added objects share the same complete-package wire reservation.
        augmented = {"files": {**sources["manifest"]["files"],
            "native_offer": {"archive_ref": offer_ref}, "native_descriptor": {"archive_ref": descriptor_ref}}}
        budget = _wire_budget(augmented, sources["manifest_ref"])
        require(self._put(raw) == offer_ref and self._put(canonical(descriptor)) == descriptor_ref,
                "Native archive write differs from preflight")
        reference = {"descriptor_ref": descriptor_ref, "offer_id": offer["offer_id"]}
        recovered = self.fresh_reader().recover_native_offer(reference, now=now)
        require(canonical(recovered["offer"]) == raw, "Native independent recovery differs")
        return {"reference": reference, "source_reference": sources["reference"],
            "offer_id": offer["offer_id"], "budget": budget,
            "acknowledged_at": stamp(datetime.now(timezone.utc)),
            "durable_remote_archive_verified": self.hosted,
            "public_admission": False, "ticket_eligibility": False}

    @_strict
    def recover_native_offer(self, reference, *, now):
        from . import native_offer
        _fields(reference, {"descriptor_ref", "offer_id"}, "Invalid native archive reference")
        _ref(reference["descriptor_ref"])
        require(type(reference["offer_id"]) is str and _SHA.fullmatch(reference["offer_id"]), "Invalid native archive offer ID")
        # Always a cold client, including when called from a warm ledger reader.
        reader = self.fresh_reader()
        descriptor = _decode(reader._get(reference["descriptor_ref"], MAX_MANIFEST_BYTES))
        _fields(descriptor, {"schema_version", "mode", "tag", "source_reference", "offer_ref", "offer_id",
            "offer_sha256", "offer_bytes", "offer_normalized_at", "native_adapter_source_sha256",
            "public_admission", "ticket_eligibility"}, "Invalid native archive descriptor")
        require(descriptor["schema_version"] == NATIVE_REF_SCHEMA and descriptor["mode"] == MODE
            and descriptor["tag"] == TAG and descriptor["offer_id"] == reference["offer_id"]
            and descriptor["native_adapter_source_sha256"] == _hash(Path(native_offer.__file__).read_bytes())
            and type(descriptor["offer_sha256"]) is str and _SHA.fullmatch(descriptor["offer_sha256"])
            and type(descriptor["offer_bytes"]) is int and 0 < descriptor["offer_bytes"] <= native_offer.MAX_OFFER_BYTES
            and descriptor["public_admission"] is False and descriptor["ticket_eligibility"] is False,
            "Native archive descriptor identity/source/scope differs")
        sources = reader.load_recovered_assets(descriptor["source_reference"], now=now)
        budget = _wire_budget({"files": {**sources["manifest"]["files"],
            "native_offer": {"archive_ref": descriptor["offer_ref"]},
            "native_descriptor": {"archive_ref": reference["descriptor_ref"]}}}, sources["manifest_ref"])
        raw = reader._get(descriptor["offer_ref"], native_offer.MAX_OFFER_BYTES)
        require(len(raw) == descriptor["offer_bytes"] and _hash(raw) == descriptor["offer_sha256"], "Native archive original bytes differ")
        offer = _decode(raw)
        native_offer.replay_native_offer(offer, sources["assets"], now=now, allow_synthetic=self.allow_synthetic)
        require(canonical(offer) == raw and offer["offer_id"] == descriptor["offer_id"]
            and offer["normalized_at"] == descriptor["offer_normalized_at"]
            and offer["original_review_id"] == sources["review"]["review_id"], "Native archive source/normalization binding differs")
        reader._draft()
        return {**sources, "offer": offer, "native_reference": reference, "native_descriptor": descriptor,
            "budget": budget, "acknowledged_at": stamp(datetime.now(timezone.utc)),
            "durable_remote_archive_verified": self.hosted}

    def _result(self, reference, replay, budget, status):
        return {"schema_version": RESULT_SCHEMA, "mode": MODE, "status": status,
                "reference": reference, "review_id": replay["review_id"], "files": len(FILENAMES),
                "originals_replayed": replay["originals_replayed"], "budget": budget,
                "storage_backend": "AUTHENTICATED_DRAFT_RELEASE" if self.hosted else "OFFLINE_FILE_TEST",
                "durable_remote_archive_verified": self.hosted,
                "public_admission": False, "ticket_eligibility": False,
                "source_provider_requests": 0, "verified_at": stamp(datetime.now(timezone.utc))}


def validate_manifest(manifest, *, reference=None):
    return _validate_manifest(manifest, reference=reference)


def validate_reference(reference):
    return _validate_reference(reference)


def archive_package(directory, *, archive, now, allow_synthetic=False):
    return PrivateMoviOddsArchive(archive, allow_synthetic=allow_synthetic).archive(directory, now=now)


def recover_package(reference, destination, *, archive, now, allow_synthetic=False):
    return PrivateMoviOddsArchive(archive, allow_synthetic=allow_synthetic).recover(reference, destination, now=now)


def load_recovered_assets(reference, *, archive, now, allow_synthetic=False):
    return PrivateMoviOddsArchive(archive, allow_synthetic=allow_synthetic).load_recovered_assets(reference, now=now)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--archive", type=Path, metavar="EXISTING_PACKAGE",
                        help="Explicitly upload only the sixteen existing originals to the fixed private draft")
    action.add_argument("--recover", type=Path, metavar="MANIFEST_REFERENCE_JSON",
                        help="Read and independently recover a retained manifest-reference file")
    parser.add_argument("--output", type=Path, help="Create-only private recovery destination under .local-data")
    args = parser.parse_args(argv)
    require((args.recover is not None) == (args.output is not None),
            "Recovery requires --output; archiving prints public reference metadata only")
    client = PrivateMoviOddsArchive(GuardedGitHubReleaseArchive(allow_diagnostics=True,
        write_budget_bytes=MAX_NEW_WIRE_BYTES, write_budget_objects=MAX_NEW_OBJECTS))
    now = datetime.now(timezone.utc)
    if args.archive is not None:
        result = client.archive(args.archive, now=now)
    else:
        value = _decode(_bounded_bytes(args.recover, MAX_MANIFEST_BYTES))
        reference = value.get("reference") if type(value) is dict and value.get("schema_version") == RESULT_SCHEMA else value
        result = client.recover(reference, args.output, now=now)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

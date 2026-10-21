"""Candidate encrypted raw evidence for NBA-PAIRED-OPS-002, with no network I/O.

Only ciphertext and small receipts may enter the proposed records branch. A
separately held private key is required for authenticated independent readback.
The module does not grant source rights, review an admission, create a secret,
publish an artifact, or declare a prospective timing success. Genuine operation
requires the guarded runner to resolve the reviewed admission references.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
from urllib.parse import urlsplit

from .integrity import (IntegrityError, canonical, digest, read_receipt, stamp,
                        utc, write_receipt)

PILOT_ID = "NBA-PAIRED-OPS-002"
SCHEMA = "nba-op002-encrypted-raw-v1"
REF_SCHEMA = "nba-op002-encrypted-raw-reference-v1"
ADMISSION_SCHEMA = "nba-op002-encrypted-raw-admission-v1"
ENCRYPTION = "openssl-cms-authenveloped-aes256gcm-rsaoaep-sha256-v1"
MAX_OBJECT_BYTES = 8 * 1024 * 1024  # Includes CMS overhead, not just plaintext.
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024  # All ciphertext and receipt envelopes.
MAX_CAPTURES = 128
MAX_METADATA_BYTES = 16 * 1024
MAX_CMS_OVERHEAD_BYTES = 16 * 1024
MAX_CRYPTO_SECONDS = 30
MODES = {"SYNTHETIC_DIAGNOSTIC", "READINESS_DIAGNOSTIC", "REAL_TIME_CAPTURED"}
_SHA = re.compile(r"[a-f0-9]{64}")
_REF_FIELDS = {"schema_version", "capture_id", "manifest_payload_sha256",
               "cipher_sha256", "cipher_bytes", "raw_sha256", "raw_bytes",
               "recipient_certificate_sha256"}
_FIELDS = {"schema_version", "pilot_id", "mode", "event_id", "source_url", "request_started_at",
           "source_observed_at", "source_updated_at", "imported_at",
           "encryption_completed_at", "cipher_persistence_completed_at",
           "manifest_prepared_at", "encryption", "raw_sha256", "raw_bytes",
           "cipher_sha256", "cipher_bytes", "recipient_certificate_sha256",
           "admission_sha256", "supersedes", "correction_reason", "capture_id"}
_IDENTITY_EXCLUDED = {"capture_id", "imported_at", "encryption_completed_at",
                      "cipher_persistence_completed_at", "manifest_prepared_at",
                      "encryption", "cipher_sha256", "cipher_bytes"}


class RawRetentionError(IntegrityError):
    """Missing, invalid, conflicting, or unauthenticated raw evidence."""


def _require(condition, message):
    if not condition:
        raise RawRetentionError(message)


def _now():
    return datetime.now(timezone.utc)


def _hash(value, label):
    _require(type(value) is str and _SHA.fullmatch(value) is not None,
             "invalid " + label)
    return value


def _clock(value, label):
    _require(type(value) is str and re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", value) is not None,
        label + " requires an exact six-digit UTC clock")
    try:
        return utc(value)
    except ValueError as error:
        raise RawRetentionError("invalid " + label) from error


def _safe_path(value):
    path = Path(value).absolute()
    for part in (path, *path.parents):
        _require(not part.is_symlink(), "raw archive paths cannot traverse symlinks")
    _require(".git" not in path.parts and "output" not in path.parts,
             "raw archive cannot be Git internals or a public artifact directory")
    return path


def _regular(path, maximum, label):
    path = _safe_path(path)
    _require(path.exists() and stat.S_ISREG(path.lstat().st_mode),
             label + " must be a regular file")
    _require(0 < path.stat().st_size <= maximum, label + " exceeds its bound")
    return path


def _private_key(path):
    path = _regular(path, 64 * 1024, "private key")
    _require(stat.S_IMODE(path.stat().st_mode) & 0o077 == 0,
             "private key must have owner-only permissions")
    probe = subprocess.run(["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
                           capture_output=True, timeout=10, check=False)
    _require(probe.returncode != 0,
             "private keys must remain outside every Git worktree")
    return path


def _openssl(arguments, raw=b""):
    executable = shutil.which("openssl")
    _require(executable is not None, "OpenSSL CMS is required for raw retention")
    try:
        result = subprocess.run([executable, *arguments], input=raw,
                                capture_output=True, check=False,
                                timeout=MAX_CRYPTO_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RawRetentionError("bounded OpenSSL CMS operation failed") from error
    # Never include stderr/stdout in failures: decrypt output may contain raw
    # bytes even if an authentication check ultimately fails.
    _require(result.returncode == 0, "OpenSSL CMS authentication or operation failed")
    return result.stdout


def _certificate(path):
    path = _regular(path, 64 * 1024, "recipient certificate")
    raw = path.read_bytes()
    der = _openssl(["x509", "-in", str(path), "-outform", "DER"])
    _require(len(der) > 0, "recipient certificate is invalid")
    public = _openssl(["x509", "-in", str(path), "-pubkey", "-noout"])
    details = _openssl(["pkey", "-pubin", "-text", "-noout"], public)
    sizes = re.findall(rb"Public-Key: \((\d+) bit\)", details)
    _require(len(sizes) == 1 and int(sizes[0]) >= 3072 and b"Modulus:" in details,
             "recipient requires RSA of at least 3072 bits")
    return path, hashlib.sha256(raw).hexdigest()


def _inspect_cipher(raw):
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_OBJECT_BYTES,
             "encrypted object exceeds its encoded bound")
    printed = _openssl(["cms", "-cmsout", "-inform", "DER", "-print"], raw)
    # Inspect the actual CMS algorithm identifiers, not caller metadata. The
    # authenticated envelope is essential; a CBC envelope is never admitted.
    for marker in (b"contentType: id-smime-ct-authEnvelopedData (",
                   b"algorithm: aes-256-gcm (", b"algorithm: rsaesOaep (",
                   b"OBJECT            :sha256", b"OBJECT            :mgf1"):
        _require(marker in printed, "CMS object does not use the exact admitted encryption suite")
    objects = re.findall(rb"OBJECT\s+:([^\s]+)", printed)
    _require(objects == [b"sha256", b"mgf1", b"sha256"] and
             printed.count(b"algorithm: rsaesOaep (") == 1 and
             printed.count(b"d.ktri:") == 1,
             "CMS OAEP digests or recipient inventory differ from the exact suite")


def validate_admission(body, *, certificate_sha256=None):
    """Check typed references; external review/source evidence must be resolved.

    A caller-supplied dictionary is not an approval, source permission, secret
    availability proof, or successful remote readback. The guarded runner owns
    independently resolving these exact hashes against its reviewed activation.
    """
    fields = {"schema_version", "pilot_id", "repository", "records_branch",
              "private_key_secret", "recipient_certificate_sha256",
              "reviewed_source_commit", "review_evidence_sha256",
              "source_permission_sha256", "host_readback_sha256",
              "privacy", "retention_through", "state"}
    _require(type(body) is dict and set(body) == fields and
             body["schema_version"] == ADMISSION_SCHEMA and body["pilot_id"] == PILOT_ID,
             "invalid encrypted retention admission")
    _require(body["repository"] == "NickNicky19/Nicks-multisport-lab-project" and
             type(body["records_branch"]) is str and re.fullmatch(
                 r"records/nba-paired-ops-002(?:-[a-z0-9-]{1,64})?", body["records_branch"]) is not None,
             "encrypted backend changes the reviewed repository or branch namespace")
    _require(body["private_key_secret"] == "NML_OP002_RAW_PRIVATE_KEY" and
             body["state"] == "REVIEWED_EXACT_SOURCE_AND_BACKEND" and
             body["privacy"] == "ENCRYPTED_WITH_SEPARATE_PRIVATE_KEY" and
             body["retention_through"] == "INDEFINITE_REVIEWED",
             "private retention review or availability remains unresolved")
    _require(type(body["reviewed_source_commit"]) is str and re.fullmatch(
        r"[a-f0-9]{40}", body["reviewed_source_commit"]) is not None,
        "raw backend requires the exact reviewed source commit")
    for key in ("recipient_certificate_sha256", "review_evidence_sha256",
                "source_permission_sha256", "host_readback_sha256"):
        _hash(body[key], key)
    if certificate_sha256 is not None:
        _require(body["recipient_certificate_sha256"] == certificate_sha256,
                 "raw backend recipient differs from its reviewed admission")
    return body


def _reference(body):
    return {"schema_version": REF_SCHEMA, "capture_id": body["capture_id"],
            "manifest_payload_sha256": digest(body),
            **{key: body[key] for key in ("cipher_sha256", "cipher_bytes", "raw_sha256",
                                         "raw_bytes", "recipient_certificate_sha256")}}


class EncryptedRawArchive:
    """Append-only encrypted bytes; no network, secret creation, or timing grant."""

    def __init__(self, root, recipient_certificate, *, private_key=None, admission=None):
        self.root = _safe_path(root)
        self.certificate, self.certificate_sha256 = _certificate(recipient_certificate)
        self.private_key = _private_key(private_key) if private_key is not None else None
        self.admission = validate_admission(admission, certificate_sha256=self.certificate_sha256) if admission is not None else None

    def _verify_certificate(self):
        path = _regular(self.certificate, 64 * 1024, "recipient certificate")
        _require(hashlib.sha256(path.read_bytes()).hexdigest() == self.certificate_sha256,
                 "recipient certificate bytes changed after initialization")

    def _inventory(self):
        _safe_path(self.root)
        self._verify_certificate()
        if self.root.exists():
            _require(self.root.is_dir() and all(p.name in {"ciphertext", "captures"}
                     for p in self.root.iterdir()),
                     "unexpected archive content; never copy unreviewed plaintext to Git")
        count = total = cipher_count = 0
        for folder, suffix, maximum in (("ciphertext", ".cms", MAX_OBJECT_BYTES),
                                         ("captures", ".json", MAX_METADATA_BYTES)):
            directory = self.root / folder
            if not directory.exists():
                continue
            _require(not directory.is_symlink() and directory.is_dir(),
                     "unsafe encrypted archive directory")
            for path in directory.iterdir():
                _require(stat.S_ISREG(path.lstat().st_mode) and
                         re.fullmatch("[a-f0-9]{64}" + re.escape(suffix), path.name) is not None,
                         "interrupted or unexpected archive object; preserve it for diagnosis")
                size = path.stat().st_size
                _require(0 < size <= maximum, "encrypted archive object exceeds its bound")
                total += size
                if folder == "captures":
                    count += 1
                else:
                    cipher_count += 1
        _require(count <= MAX_CAPTURES and total <= MAX_ARCHIVE_BYTES,
                 "encrypted archive exceeds unchanged capacity")
        _require(cipher_count <= MAX_CAPTURES,
                 "orphan ciphertext inventory exceeds unchanged capture capacity")
        return count, total

    def _manifest(self, capture_id):
        return self.root / "captures" / (_hash(capture_id, "capture ID") + ".json")

    def _cipher(self, cipher_sha):
        return self.root / "ciphertext" / (_hash(cipher_sha, "cipher hash") + ".cms")

    def _validate(self, body, *, seen=None):
        _require(type(body) is dict and set(body) == _FIELDS and body["schema_version"] == SCHEMA and
                 body["pilot_id"] == PILOT_ID and body["encryption"] == ENCRYPTION,
                 "invalid encrypted raw capture contract")
        _require(type(body["event_id"]) is str and re.fullmatch(r"[1-9][0-9]{0,19}", body["event_id"]) is not None,
                 "invalid raw event identity")
        _require(type(body["mode"]) is str and body["mode"] in MODES, "invalid raw evidence lane")
        _require(type(body["source_url"]) is str and len(body["source_url"]) <= 2048,
                 "invalid raw source reference")
        try:
            url = urlsplit(body["source_url"])
            port = url.port
        except ValueError as error:
            raise RawRetentionError("invalid raw source URL") from error
        if url.scheme == "synthetic":
            _require(body["mode"] == "SYNTHETIC_DIAGNOSTIC" and url.netloc == "op002",
                     "synthetic source cannot become an actual observation")
        else:
            _require(url.scheme == "https" and url.hostname in {
                "site.api.espn.com", "sports.core.api.espn.com", "api.sleeper.app"} and
                url.username is None and url.password is None and port is None and not url.fragment,
                "raw source is outside the existing bounded route hosts")
        started = _clock(body["request_started_at"], "source request start")
        observed = _clock(body["source_observed_at"], "source observation")
        imported = _clock(body["imported_at"], "source import")
        encrypted = _clock(body["encryption_completed_at"], "encryption completion")
        persisted = _clock(body["cipher_persistence_completed_at"], "cipher persistence completion")
        prepared = _clock(body["manifest_prepared_at"], "manifest preparation")
        _require(started <= observed <= imported <= encrypted <= persisted <= prepared <= _now(),
                 "raw observation/import/encryption/persistence clocks conflict")
        if body["source_updated_at"] is not None:
            _require(_clock(body["source_updated_at"], "source update") <= observed,
                     "upstream update follows actual observation")
        for key in ("raw_sha256", "cipher_sha256", "recipient_certificate_sha256", "capture_id"):
            _hash(body[key], key)
        _require(body["recipient_certificate_sha256"] == self.certificate_sha256,
                 "raw recipient certificate identity changed")
        _require(type(body["raw_bytes"]) is int and type(body["cipher_bytes"]) is int and
                 0 < body["raw_bytes"] < body["cipher_bytes"] <= MAX_OBJECT_BYTES and
                 body["cipher_bytes"] - body["raw_bytes"] <= MAX_CMS_OVERHEAD_BYTES,
                 "invalid raw/cipher encoded byte count")
        if body["mode"] == "REAL_TIME_CAPTURED":
            _require(self.admission is not None and body["admission_sha256"] == digest(self.admission),
                     "RAW_BACKEND_UNADMITTED: resolve exact review, source permission and host recovery first")
        else:
            _require(body["admission_sha256"] is None,
                     "a diagnostic cannot claim genuine backend admission")
        identity = {key: value for key, value in body.items() if key not in _IDENTITY_EXCLUDED}
        _require(body["capture_id"] == digest(identity), "raw capture identity changed")
        seen = set() if seen is None else set(seen)
        _require(body["capture_id"] not in seen and len(seen) < MAX_CAPTURES,
                 "cyclic or excessive raw correction chain")
        seen.add(body["capture_id"])
        if body["supersedes"] is None:
            _require(body["correction_reason"] is None, "correction reason requires an original capture")
        else:
            _require(type(body["correction_reason"]) is str and 0 < len(body["correction_reason"].strip()) <= 2048,
                     "raw correction requires a bounded explicit reason")
            original, _ = self._read(body["supersedes"], decrypt=False, seen=seen)
            _require(all(body[key] == original[key] for key in ("event_id", "mode", "source_url")) and
                     observed >= _clock(original["source_observed_at"], "original observation"),
                     "raw correction changes its subject/source or precedes its original")
        return body

    def _read(self, reference, *, decrypt, private_key=None, seen=None):
        self._inventory()
        _require(type(reference) is dict and set(reference) == _REF_FIELDS and
                 reference["schema_version"] == REF_SCHEMA, "invalid encrypted raw reference")
        for key in _REF_FIELDS - {"schema_version", "cipher_bytes", "raw_bytes"}:
            _hash(reference[key], key)
        _require(type(reference["raw_bytes"]) is int and type(reference["cipher_bytes"]) is int and
                 0 < reference["raw_bytes"] < reference["cipher_bytes"] <= MAX_OBJECT_BYTES,
                 "encrypted reference requires integer encoded byte counts")
        body = read_receipt(self._manifest(reference["capture_id"]), max_bytes=MAX_METADATA_BYTES)
        self._validate(body, seen=seen)
        _require(_reference(body) == reference, "encrypted raw reference differs from original manifest")
        path = _regular(self._cipher(body["cipher_sha256"]), MAX_OBJECT_BYTES, "encrypted raw object")
        cipher = path.read_bytes()
        _require(len(cipher) == body["cipher_bytes"] and hashlib.sha256(cipher).hexdigest() == body["cipher_sha256"],
                 "encrypted raw ciphertext changed")
        _inspect_cipher(cipher)
        if not decrypt:
            return body, cipher
        key = _private_key(private_key) if private_key is not None else self.private_key
        _require(key is not None, "independent authenticated recovery requires the separate private key")
        raw = _openssl(["cms", "-decrypt", "-binary", "-inform", "DER", "-inkey", str(key),
                        "-recip", str(self.certificate)], cipher)
        self._verify_certificate()
        _require(len(raw) == body["raw_bytes"] and hashlib.sha256(raw).hexdigest() == body["raw_sha256"],
                 "decrypted source bytes differ from the original raw identity")
        return body, raw

    def read(self, reference, *, private_key=None):
        """Authenticate/decrypt exact bytes without changing clocks or records."""
        return self._read(reference, decrypt=True, private_key=private_key)

    def inspect(self, reference):
        """Check ciphertext/manifests only; this is not private-key recovery."""
        body, _ = self._read(reference, decrypt=False)
        return body

    def retain(self, raw, *, mode, event_id, source_url, observed_at, request_started_at=None,
               source_updated_at=None, supersedes=None, correction_reason=None):
        """Encrypt supplied bytes immutably, returning no timing/durability claim.

        Repeating an identical original preserves its first import/encryption and
        persistence clocks and ciphertext. An interruption may leave an orphan
        ciphertext; it is counted, never silently deleted or treated as a capture.
        """
        _require(type(raw) is bytes and 0 < len(raw) < MAX_OBJECT_BYTES,
                 "raw bytes exceed the encoded-object budget")
        _require(type(mode) is str and mode in MODES, "invalid raw evidence lane")
        count, total = self._inventory()
        if mode == "REAL_TIME_CAPTURED":
            _require(self.admission is not None,
                     "RAW_BACKEND_UNADMITTED: no reviewed source/backend admission")
        _require(request_started_at is not None or mode == "SYNTHETIC_DIAGNOSTIC",
                 "actual source bytes require their original request-start clock")
        imported = _now()
        identity = {"schema_version": SCHEMA, "pilot_id": PILOT_ID, "mode": mode,
                    "event_id": event_id, "source_url": source_url,
                    "request_started_at": stamp(utc(request_started_at)) if request_started_at is not None else stamp(utc(observed_at)),
                    "source_observed_at": stamp(utc(observed_at)),
                    "source_updated_at": stamp(utc(source_updated_at)) if source_updated_at is not None else None,
                    "raw_sha256": hashlib.sha256(raw).hexdigest(), "raw_bytes": len(raw),
                    "recipient_certificate_sha256": self.certificate_sha256,
                    "admission_sha256": digest(self.admission) if mode == "REAL_TIME_CAPTURED" else None,
                    "supersedes": supersedes, "correction_reason": correction_reason}
        capture_id = digest(identity)
        existing = self._manifest(capture_id)
        if existing.exists():
            body = read_receipt(existing, max_bytes=MAX_METADATA_BYTES)
            reference = _reference(body)
            self.inspect(reference)
            _require({key: body[key] for key in identity} == identity,
                     "raw capture retry conflicts with its original")
            if self.private_key is not None:
                _, original = self.read(reference)
                _require(original == raw, "raw original differs on authenticated readback")
            return reference
        # Reserve metadata and maximum expected CMS overhead before performing
        # crypto. The actual encoded size is enforced again before any write.
        _require(count + 1 <= MAX_CAPTURES and total + len(raw) + MAX_METADATA_BYTES <= MAX_ARCHIVE_BYTES,
                 "new raw capture would exceed unchanged archive capacity")
        cipher = _openssl(["cms", "-encrypt", "-binary", "-aes-256-gcm", "-outform", "DER",
                           "-recip", str(self.certificate), "-keyopt", "rsa_padding_mode:oaep",
                           "-keyopt", "rsa_oaep_md:sha256", "-keyopt", "rsa_mgf1_md:sha256"], raw)
        self._verify_certificate()
        encrypted = _now()
        _inspect_cipher(cipher)
        _require(total + len(cipher) + MAX_METADATA_BYTES <= MAX_ARCHIVE_BYTES,
                 "ciphertext and metadata exceed archive capacity")
        cipher_sha = hashlib.sha256(cipher).hexdigest()
        proposed = {**identity, "capture_id": capture_id, "encryption": ENCRYPTION,
                    "imported_at": stamp(imported), "encryption_completed_at": stamp(encrypted),
                    "cipher_persistence_completed_at": stamp(encrypted), "manifest_prepared_at": stamp(encrypted),
                    "cipher_sha256": cipher_sha, "cipher_bytes": len(cipher)}
        self._validate(proposed)
        destination = self._cipher(cipher_sha)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".cipher-", dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(cipher)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, destination)
            except FileExistsError:
                _require(destination.read_bytes() == cipher, "content-addressed ciphertext conflict")
        finally:
            Path(temporary).unlink(missing_ok=True)
        directory = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        _require(destination.read_bytes() == cipher, "cipher readback differs after fsync")
        persisted = _now()
        body = {**proposed, "cipher_persistence_completed_at": stamp(persisted),
                "manifest_prepared_at": stamp(_now())}
        self._validate(body)
        path = self._manifest(capture_id)
        write_receipt(path, body, max_bytes=MAX_METADATA_BYTES)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        reference = _reference(body)
        self.inspect(reference)
        if self.private_key is not None:
            _, original = self.read(reference)
            _require(original == raw, "authenticated post-persistence raw readback differs")
        return reference

    def recover(self, *, private_key=None):
        """Fresh authenticated readback of every original, retaining corrections."""
        self._inventory()
        references = []
        for path in sorted((self.root / "captures").glob("*.json")):
            body = read_receipt(path, max_bytes=MAX_METADATA_BYTES)
            reference = _reference(body)
            self.read(reference, private_key=private_key)
            references.append(reference)
        return references

    def inventory(self):
        count, total = self._inventory()
        return {"captures": count, "encoded_bytes": total,
                "max_captures": MAX_CAPTURES, "max_encoded_bytes": MAX_ARCHIVE_BYTES,
                "max_encoded_object_bytes": MAX_OBJECT_BYTES}

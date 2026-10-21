"""Offline, read-only verification of supplied original and restored OPS002 keys.

This checks local cryptographic recovery only. It does not generate a key,
install an Actions secret, authenticate a backup service, admit source use or
enable the operating pilot. No private-key bytes are returned or logged.
"""
from __future__ import annotations

import argparse
import base64
import binascii
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time

from .integrity import IntegrityError, stamp
from . import operational_raw as raw

SCHEMA = "nba-operational002-local-key-recovery-v1"
CANARY = b"Nick's Multisport Lab OPS002 private-key recovery canary v1\n"
MAX_CANARY_BYTES = 16 * 1024
MAX_KEY_BYTES = 64 * 1024
BACKUP_METHODS = {"UNSPECIFIED", "EXISTING_SECURE_FILE_MANAGER", "EXISTING_ENCRYPTED_OFFLINE_BACKUP"}


def _require(condition, message):
    if not condition:
        raise IntegrityError("OPS002 key recovery: " + message)


def _clock():
    return datetime.now(timezone.utc)


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_mode, info.st_uid)


def _open_regular(value, maximum, *, private=False):
    """Pin a bounded regular file through no-follow directory descriptors."""
    directory = descriptor = None
    try:
        path = Path(value).absolute()
        _require(path.anchor == "/" and ".." not in path.parts and
                 "\x00" not in str(path) and len(str(path)) <= 4096,
                 "invalid supplied file path")
        _require(hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"),
                 "this platform lacks required no-follow descriptors")
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        directory = os.open("/", directory_flags)
        for part in path.parts[1:-1]:
            child = os.open(part, directory_flags, dir_fd=directory)
            os.close(directory)
            directory = child
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(path.name, flags, dir_fd=directory)
        info = os.fstat(descriptor)
        _require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= maximum,
                 "supplied file is not regular or exceeds its bound")
        if private:
            _require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) & 0o077 == 0,
                     "private keys require current-owner-only permissions")
            _outside_git(path)
        result, descriptor = (path, descriptor, info), None
        return result
    except (OSError, TypeError, ValueError) as error:
        if isinstance(error, IntegrityError):
            raise
        raise IntegrityError("OPS002 key recovery: supplied file is missing, unsafe or unreadable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if directory is not None:
            os.close(directory)


def _outside_git(path):
    _require(".git" not in path.parts and shutil.which("git") is not None,
             "private keys must stay outside every Git worktree")
    try:
        probe = subprocess.run(["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
                               capture_output=True, check=False, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        raise IntegrityError("OPS002 key recovery: cannot verify private-key placement") from None
    _require(probe.returncode != 0 and b"not a git repository" in probe.stderr,
             "private keys must stay outside every Git worktree")


class _File:
    def __init__(self, value, maximum, *, private=False):
        self.path, self.fd, self.info = _open_regular(value, maximum, private=private)
        self.maximum, self.private = maximum, private

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        os.close(self.fd)

    @property
    def argument(self):
        # OpenSSL receives the pinned descriptor, never a path that it could
        # follow after a rename/symlink race. No private bytes enter argv.
        return "/proc/self/fd/" + str(self.fd)

    def bytes(self):
        _require(not self.private, "private-key bytes may not be read into the report process")
        encoded = os.pread(self.fd, self.maximum + 1, 0)
        _require(len(encoded) == self.info.st_size, "supplied public file changed while read")
        return encoded

    def stable(self):
        _require(_identity(os.fstat(self.fd)) == _identity(self.info),
                 "supplied file changed during recovery verification")
        _, fresh, info = _open_regular(self.path, self.maximum, private=self.private)
        try:
            _require(_identity(info) == _identity(self.info),
                     "supplied file was replaced during recovery verification")
        finally:
            os.close(fresh)


def _openssl(arguments, encoded=b"", *, files=()):
    executable = shutil.which("openssl")
    _require(executable is not None, "OpenSSL is required")
    try:
        result = subprocess.run([executable, *arguments], input=encoded,
                                capture_output=True, check=False,
                                pass_fds=tuple(item.fd for item in files),
                                timeout=raw.MAX_CRYPTO_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        raise IntegrityError("OPS002 key recovery: bounded cryptographic operation failed") from None
    # Even OpenSSL failure output can contain decrypted bytes or private paths.
    _require(result.returncode == 0, "cryptographic authentication or operation failed")
    return result.stdout


def verify_key_recovery(*, certificate, original_key, restored_key, canary,
                        backup_method="UNSPECIFIED"):
    """Verify two supplied key files against the certificate and known canary.

    Distinct regular inodes are required; a hard link to the original is not an
    independently restored copy. A successful local test does not prove where
    the restored file came from, backup durability, or hosted-secret recovery.
    """
    _require(type(backup_method) is str and backup_method in BACKUP_METHODS,
             "unknown declared existing backup method")
    started, wall = _clock(), time.perf_counter()
    with ExitStack() as stack:
        verifier = stack.enter_context(_File(__file__, 64 * 1024))
        verifier_bytes = verifier.bytes()
        cert = stack.enter_context(_File(certificate, MAX_KEY_BYTES))
        original = stack.enter_context(_File(original_key, MAX_KEY_BYTES, private=True))
        restored = stack.enter_context(_File(restored_key, MAX_KEY_BYTES, private=True))
        cipher = stack.enter_context(_File(canary, MAX_CANARY_BYTES))
        _require((original.info.st_dev, original.info.st_ino) !=
                 (restored.info.st_dev, restored.info.st_ino),
                 "restored key must be a distinct regular copy, not the original or a hard link")
        certificate_bytes = cert.bytes()
        pem = re.fullmatch(rb"\s*-----BEGIN CERTIFICATE-----\r?\n"
                           rb"([A-Za-z0-9+/=\r\n]+)-----END CERTIFICATE-----\s*",
                           certificate_bytes)
        _require(pem is not None,
                 "public certificate must contain exactly one PEM certificate and no key material")
        try:
            decoded_der = base64.b64decode(pem.group(1).replace(b"\r", b"").replace(b"\n", b""),
                                          validate=True)
        except (binascii.Error, ValueError):
            raise IntegrityError("OPS002 key recovery: invalid public certificate encoding") from None
        # OpenSSL can parse one X509 value and ignore further DER hidden inside
        # the same PEM base64. Every decoded byte must belong to this certificate.
        parsed_der = _openssl(["x509", "-in", cert.argument, "-outform", "DER"], files=(cert,))
        _require(decoded_der == parsed_der, "public certificate contains unparsed DER data")
        public_pem = _openssl(["x509", "-in", cert.argument, "-pubkey", "-noout"], files=(cert,))
        public_der = _openssl(["pkey", "-pubin", "-outform", "DER"], public_pem)
        details = _openssl(["pkey", "-pubin", "-text", "-noout"], public_pem)
        sizes = re.findall(rb"Public-Key: \((\d+) bit\)", details)
        _require(len(sizes) == 1 and int(sizes[0]) >= 3072 and b"Modulus:" in details,
                 "certificate requires RSA of at least 3072 bits")
        ciphertext = cipher.bytes()
        raw._inspect_cipher(ciphertext)
        for key in (original, restored):
            recovered_public = _openssl(["pkey", "-in", key.argument, "-passin", "pass:",
                                         "-pubout", "-outform", "DER"], files=(key,))
            _require(recovered_public == public_der,
                     "original or restored key differs from the reviewed certificate")
            recovered = _openssl(["cms", "-decrypt", "-binary", "-inform", "DER",
                                  "-recip", cert.argument, "-inkey", key.argument,
                                  "-passin", "pass:"], ciphertext, files=(cert, key))
            _require(recovered == CANARY, "authenticated plaintext is not the exact public recovery canary")
        _require(cert.bytes() == certificate_bytes, "certificate changed during recovery verification")
        _require(verifier.bytes() == verifier_bytes, "verifier source changed during recovery verification")
        for item in (verifier, cert, original, restored, cipher):
            item.stable()
        certificate_sha = hashlib.sha256(certificate_bytes).hexdigest()
    completed = _clock()
    _require(completed >= started, "actual recovery clock moved backwards")
    return {"schema_version": SCHEMA, "protocol_id": raw.PILOT_ID,
            "status": "VERIFIED_LOCAL_CANARY_ONLY", "activation": "NOT_ACTIVATED",
            "verifier": {"module": "multisport_lab.operational_key_recovery",
                         "source_sha256": hashlib.sha256(verifier_bytes).hexdigest(),
                         "binding": "LOCAL_FILE_BYTES_ONLY", "reviewed_commit": None},
            "started_at": stamp(started), "completed_at": stamp(completed),
            "elapsed_seconds": time.perf_counter() - wall,
            "recipient_certificate_sha256": certificate_sha,
            "public_key_spki_sha256": hashlib.sha256(public_der).hexdigest(),
            "canary_cipher_sha256": hashlib.sha256(ciphertext).hexdigest(),
            "canary_plaintext_sha256": hashlib.sha256(CANARY).hexdigest(),
            "encryption": raw.ENCRYPTION, "rsa_bits": int(sizes[0]),
            "declared_backup_method": backup_method, "distinct_restored_copy_verified": True,
            "local_authenticated_key_recovery_verified": True,
            "durable_backup_origin_verified": False, "hosted_secret_recovery_verified": False,
            "source_use_admitted": False, "genuine_operation_enabled": False,
            "meaning": "Verified only the supplied local original/restored key pair and public canary; "
                       "owner backup origin, durable custody, hosted recovery and operating admission remain separate."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("certificate", "original-key", "restored-key", "canary"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--backup-method", choices=sorted(BACKUP_METHODS), default="UNSPECIFIED")
    args = parser.parse_args(argv)
    try:
        report = verify_key_recovery(certificate=args.certificate, original_key=args.original_key,
            restored_key=args.restored_key, canary=args.canary, backup_method=args.backup_method)
    except IntegrityError as error:
        parser.exit(2, str(error) + "\n")
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Synthetic authenticated retention/restart tests; no provider or GitHub I/O."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from multisport_lab.integrity import digest, read_receipt, stamp, write_receipt
from multisport_lab import operational_raw as raw


class EncryptedRawTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("openssl") is None:
            raise unittest.SkipTest("OpenSSL CMS is required")
        cls.keys = tempfile.TemporaryDirectory(prefix="nml-op002-test-keys-")
        base = Path(cls.keys.name)
        cls.key = base / "private.pem"
        cls.cert = base / "recipient.pem"
        cls.other_key = base / "other.pem"
        cls.other_cert = base / "other-recipient.pem"
        for key, cert in ((cls.key, cls.cert), (cls.other_key, cls.other_cert)):
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:3072", "-sha256",
                            "-days", "1", "-nodes", "-keyout", str(key), "-out", str(cert),
                            "-subj", "/CN=NML OP002 synthetic test"],
                           capture_output=True, check=True, timeout=30)
            key.chmod(0o600)

    @classmethod
    def tearDownClass(cls):
        cls.keys.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="nml-op002-test-archive-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "encrypted"
        self.archive = raw.EncryptedRawArchive(self.root, self.cert, private_key=self.key)
        self.payload = b'{"synthetic":true,"event":"401999002","final":false}'
        self.observed = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.arguments = {"mode": "SYNTHETIC_DIAGNOSTIC", "event_id": "401999002",
                          "source_url": "synthetic://op002/outcome/401999002",
                          "observed_at": self.observed}

    def retain(self, **changes):
        return self.archive.retain(self.payload, **{**self.arguments, **changes})

    def _replace_cipher(self, reference, cipher):
        body = read_receipt(self.archive._manifest(reference["capture_id"]))
        body.update(cipher_sha256=hashlib.sha256(cipher).hexdigest(), cipher_bytes=len(cipher))
        self.archive._cipher(body["cipher_sha256"]).write_bytes(cipher)
        path = self.archive._manifest(reference["capture_id"])
        path.unlink()
        write_receipt(path, body, max_bytes=raw.MAX_METADATA_BYTES)
        return raw._reference(body)

    def test_authenticated_exact_bytes_restart_and_idempotent_original_clocks(self):
        reference = self.retain()
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        body, recovered = self.archive.read(reference)
        self.assertEqual(recovered, self.payload)
        self.assertEqual(body["source_observed_at"], stamp(self.observed))
        self.assertIsNone(body["source_updated_at"])
        self.assertEqual(self.retain(), reference)
        restarted = raw.EncryptedRawArchive(self.root, self.cert, private_key=self.key)
        self.assertEqual(restarted.recover(), [reference])
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes()
                                 for p in self.root.rglob("*") if p.is_file()})
        self.assertEqual(self.archive.inventory()["captures"], 1)
        self.assertGreater(self.archive.inventory()["encoded_bytes"], len(self.payload))

    def test_no_private_key_inspection_cannot_claim_authenticated_recovery(self):
        reference = self.retain()
        public_only = raw.EncryptedRawArchive(self.root, self.cert)
        self.assertEqual(public_only.inspect(reference)["raw_bytes"], len(self.payload))
        with self.assertRaisesRegex(raw.RawRetentionError, "separate private key"):
            public_only.recover()
        with self.assertRaisesRegex(raw.RawRetentionError, "integer encoded byte"):
            self.archive.read({**reference, "raw_bytes": float(reference["raw_bytes"])})

    def test_wrong_key_and_tampered_ciphertext_reject(self):
        reference = self.retain()
        with self.assertRaisesRegex(raw.RawRetentionError, "authentication or operation"):
            self.archive.read(reference, private_key=self.other_key)
        cipher_path = self.archive._cipher(reference["cipher_sha256"])
        cipher = bytearray(cipher_path.read_bytes())
        cipher[-1] ^= 1
        changed = self._replace_cipher(reference, bytes(cipher))
        with self.assertRaises(raw.RawRetentionError):
            self.archive.read(changed)

    def test_checksum_consistent_wrong_raw_identity_rejects_on_decrypt(self):
        reference = self.retain()
        body = read_receipt(self.archive._manifest(reference["capture_id"]))
        body["raw_sha256"] = "a" * 64
        body["capture_id"] = digest({k: v for k, v in body.items() if k not in raw._IDENTITY_EXCLUDED})
        write_receipt(self.archive._manifest(body["capture_id"]), body)
        changed = raw._reference(body)
        with self.assertRaisesRegex(raw.RawRetentionError, "original raw identity"):
            self.archive.read(changed)

    def test_cbc_or_wrong_oaep_digest_rejected_even_with_valid_receipt_hashes(self):
        reference = self.retain()
        cbc = raw._openssl(["cms", "-encrypt", "-binary", "-aes-256-cbc", "-outform", "DER",
                            "-recip", str(self.cert)], self.payload)
        changed = self._replace_cipher(reference, cbc)
        with self.assertRaisesRegex(raw.RawRetentionError, "exact admitted encryption suite"):
            self.archive.read(changed)
        wrong_mgf = raw._openssl(["cms", "-encrypt", "-binary", "-aes-256-gcm", "-outform", "DER",
                                  "-recip", str(self.cert), "-keyopt", "rsa_padding_mode:oaep",
                                  "-keyopt", "rsa_oaep_md:sha256", "-keyopt", "rsa_mgf1_md:sha1"], self.payload)
        changed = self._replace_cipher(reference, wrong_mgf)
        with self.assertRaisesRegex(raw.RawRetentionError, "CMS"):
            self.archive.read(changed)

    def test_future_update_and_observation_clocks_rejected_before_writes(self):
        with self.assertRaisesRegex(raw.RawRetentionError, "upstream update"):
            self.retain(source_updated_at=self.observed + timedelta(seconds=1))
        with self.assertRaisesRegex(raw.RawRetentionError, "clocks conflict"):
            self.retain(observed_at=datetime.now(timezone.utc) + timedelta(minutes=10))
        self.assertEqual(self.archive.inventory()["captures"], 0)
        self.assertFalse(self.root.exists())

    def test_request_start_and_original_certificate_bytes_are_required(self):
        with self.assertRaisesRegex(raw.RawRetentionError, "clocks conflict"):
            self.retain(request_started_at=self.observed + timedelta(seconds=1))
        with self.assertRaisesRegex(raw.RawRetentionError, "request-start clock"):
            self.retain(mode="READINESS_DIAGNOSTIC",
                        source_url="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401999002")
        cert = Path(self.tmp.name) / "recipient.pem"
        shutil.copy(self.cert, cert)
        archive = raw.EncryptedRawArchive(self.root, cert, private_key=self.key)
        shutil.copy(self.other_cert, cert)
        with self.assertRaisesRegex(raw.RawRetentionError, "certificate bytes changed"):
            archive.retain(self.payload, **self.arguments)

    def test_corrections_append_and_preserve_original_identity(self):
        original = self.retain()
        corrected = self.archive.retain(self.payload + b"\n", **self.arguments,
                                        supersedes=original, correction_reason="Synthetic formatting correction")
        self.assertNotEqual(original, corrected)
        body, recovered = self.archive.read(corrected)
        self.assertEqual(body["supersedes"], original)
        self.assertEqual(recovered, self.payload + b"\n")
        self.assertEqual(self.archive.read(original)[1], self.payload)
        self.assertEqual(len(self.archive.recover()), 2)
        with self.assertRaisesRegex(raw.RawRetentionError, "changes its subject/source"):
            self.retain(event_id="401999003", supersedes=original, correction_reason="Wrong event")

    def test_correction_needs_reason_and_same_original_source(self):
        original = self.retain()
        with self.assertRaisesRegex(raw.RawRetentionError, "explicit reason"):
            self.retain(supersedes=original)
        with self.assertRaisesRegex(raw.RawRetentionError, "changes its subject/source"):
            self.retain(source_url="synthetic://op002/other/401999002", supersedes=original,
                        correction_reason="Wrong route")

    def test_real_capture_requires_separate_reviewed_admission(self):
        with self.assertRaisesRegex(raw.RawRetentionError, "RAW_BACKEND_UNADMITTED"):
            self.retain(mode="REAL_TIME_CAPTURED",
                        source_url="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401999002")
        self.assertFalse(self.root.exists())

    def test_backend_admission_exact_fields_and_certificate_binding(self):
        admission = {"schema_version": raw.ADMISSION_SCHEMA, "pilot_id": raw.PILOT_ID,
                     "repository": "NickNicky19/Nicks-multisport-lab-project",
                     "records_branch": "records/nba-paired-ops-002",
                     "private_key_secret": "NML_OP002_RAW_PRIVATE_KEY",
                     "recipient_certificate_sha256": self.archive.certificate_sha256,
                     "reviewed_source_commit": "1" * 40, "review_evidence_sha256": "2" * 64,
                     "source_permission_sha256": "3" * 64, "host_readback_sha256": "4" * 64,
                     "privacy": "ENCRYPTED_WITH_SEPARATE_PRIVATE_KEY",
                     "retention_through": "INDEFINITE_REVIEWED",
                     "state": "REVIEWED_EXACT_SOURCE_AND_BACKEND"}
        self.assertEqual(raw.validate_admission(admission), admission)
        for key, bad in (("repository", "another/repo"), ("records_branch", "main"),
                         ("source_permission_sha256", None), ("retention_through", "ONE_WEEK"),
                         ("state", "HTTP_200")):
            changed = {**admission, key: bad}
            with self.subTest(key=key), self.assertRaises(raw.RawRetentionError):
                raw.validate_admission(changed)
        with self.assertRaisesRegex(raw.RawRetentionError, "recipient differs"):
            raw.validate_admission(admission, certificate_sha256="f" * 64)

    def test_capacity_counts_encoded_ciphertext_metadata_and_orphans(self):
        self.retain()
        total = self.archive.inventory()["encoded_bytes"]
        with mock.patch.object(raw, "MAX_CAPTURES", 1):
            with self.assertRaisesRegex(raw.RawRetentionError, "archive capacity"):
                self.retain(observed_at=self.observed + timedelta(microseconds=1))
        with mock.patch.object(raw, "MAX_ARCHIVE_BYTES", total + len(self.payload)):
            with self.assertRaisesRegex(raw.RawRetentionError, "archive capacity"):
                self.retain(observed_at=self.observed + timedelta(microseconds=2))
        with mock.patch.object(raw, "MAX_OBJECT_BYTES", 128):
            with self.assertRaises(raw.RawRetentionError):
                self.retain(observed_at=self.observed + timedelta(microseconds=3))

    def test_interrupted_manifest_keeps_ciphertext_without_inventing_capture(self):
        with mock.patch.object(raw, "write_receipt", side_effect=InterruptedError("synthetic interruption")):
            with self.assertRaises(InterruptedError):
                self.retain()
        orphan = list((self.root / "ciphertext").iterdir())
        self.assertEqual(len(orphan), 1)
        self.assertEqual(self.archive.recover(), [])
        reference = self.retain()
        self.assertTrue(orphan[0].exists())
        self.assertEqual(self.archive.recover(), [reference])
        self.assertEqual(len(list((self.root / "ciphertext").iterdir())), 2)

    def test_rejects_plaintext_files_symlinks_and_public_artifact_roots(self):
        self.root.mkdir()
        (self.root / "raw.json").write_bytes(self.payload)
        with self.assertRaisesRegex(raw.RawRetentionError, "unreviewed plaintext"):
            self.archive.inventory()
        with self.assertRaisesRegex(raw.RawRetentionError, "public artifact"):
            raw.EncryptedRawArchive(Path(self.tmp.name) / "output" / "encrypted", self.cert)
        link = Path(self.tmp.name) / "linked"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(raw.RawRetentionError, "symlinks"):
            raw.EncryptedRawArchive(link, self.cert)

    def test_private_key_rejects_public_permissions_and_git_worktree(self):
        copied = Path(self.tmp.name) / "key.pem"
        shutil.copy(self.key, copied)
        copied.chmod(0o644)
        with self.assertRaisesRegex(raw.RawRetentionError, "owner-only"):
            raw.EncryptedRawArchive(self.root, self.cert, private_key=copied)
        repo = Path(self.tmp.name) / "repo"
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
        key_in_git = repo / "key.pem"
        shutil.copy(self.key, key_in_git)
        key_in_git.chmod(0o600)
        with self.assertRaisesRegex(raw.RawRetentionError, "outside every Git worktree"):
            raw.EncryptedRawArchive(self.root, self.cert, private_key=key_in_git)

    def test_fresh_git_object_database_authenticates_only_encrypted_records(self):
        repo = Path(self.tmp.name) / "records"
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
        archive = raw.EncryptedRawArchive(repo / "encrypted", self.cert, private_key=self.key)
        reference = archive.retain(self.payload, **self.arguments)
        subprocess.run(["git", "-C", str(repo), "add", "encrypted"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=OP002 synthetic test",
                        "-c", "user.email=synthetic@example.invalid", "commit", "-qm", "Synthetic encrypted evidence"],
                       check=True, capture_output=True)
        clone = Path(self.tmp.name) / "independent"
        subprocess.run(["git", "clone", "--no-local", "-q", str(repo), str(clone)],
                       check=True, capture_output=True)
        independent = raw.EncryptedRawArchive(clone / "encrypted", self.cert, private_key=self.key)
        self.assertEqual(independent.recover(), [reference])
        self.assertEqual(independent.read(reference)[1], self.payload)
        tracked = subprocess.run(["git", "-C", str(clone), "ls-files"], text=True,
                                 capture_output=True, check=True).stdout.splitlines()
        self.assertEqual(len(tracked), 2)
        for name in tracked:
            retained = (clone / name).read_bytes()
            self.assertNotIn(self.payload, retained)
            self.assertNotIn(b"PRIVATE KEY", retained)


if __name__ == "__main__":
    unittest.main()

"""Local canary fixtures only; no operational keys, provider or GitHub I/O."""
from contextlib import redirect_stdout, redirect_stderr
from datetime import timedelta
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from multisport_lab import operational_key_recovery as recovery
from multisport_lab import operational_raw as raw
from multisport_lab.integrity import IntegrityError
import test_operational_raw as raw_fixtures


class OperationalKeyRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse the existing ephemeral encryption fixture. Nothing is installed
        # or copied to a real backup; these keys are destroyed after the tests.
        raw_fixtures.EncryptedRawTests.setUpClass()
        fixture = raw_fixtures.EncryptedRawTests
        cls.key, cls.cert = fixture.key, fixture.cert
        cls.wrong_key = fixture.other_key

    @classmethod
    def tearDownClass(cls):
        raw_fixtures.EncryptedRawTests.tearDownClass()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nml-local-key-recovery-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.restored = self.root / "restored-private.pem"
        shutil.copyfile(self.key, self.restored)
        self.restored.chmod(0o600)
        self.canary = self.root / "public-canary.cms"
        self.canary.write_bytes(self.encrypt(recovery.CANARY))

    def encrypt(self, value, *changes):
        suite = ["cms", "-encrypt", "-binary", "-aes-256-gcm", "-outform", "DER",
                 "-recip", str(self.cert), "-keyopt", "rsa_padding_mode:oaep",
                 "-keyopt", "rsa_oaep_md:sha256", "-keyopt", "rsa_mgf1_md:sha256"]
        return raw._openssl(list(changes) if changes else suite, value)

    def verify(self, **changes):
        return recovery.verify_key_recovery(**{"certificate": self.cert,
            "original_key": self.key, "restored_key": self.restored,
            "canary": self.canary, **changes})

    def test_actual_decryption_public_fingerprints_and_independent_copy_without_authority(self):
        originals = {p: p.read_bytes() for p in (self.key, self.cert, self.restored, self.canary)}
        report = self.verify(backup_method="EXISTING_ENCRYPTED_OFFLINE_BACKUP")
        self.assertEqual(report["status"], "VERIFIED_LOCAL_CANARY_ONLY")
        self.assertEqual(report["activation"], "NOT_ACTIVATED")
        self.assertTrue(report["distinct_restored_copy_verified"])
        self.assertTrue(report["local_authenticated_key_recovery_verified"])
        for field in ("durable_backup_origin_verified", "hosted_secret_recovery_verified",
                      "source_use_admitted", "genuine_operation_enabled"):
            self.assertIs(report[field], False)
        self.assertEqual(report["recipient_certificate_sha256"], hashlib.sha256(self.cert.read_bytes()).hexdigest())
        self.assertEqual(report["canary_plaintext_sha256"], hashlib.sha256(recovery.CANARY).hexdigest())
        self.assertEqual(report["verifier"], {
            "module": "multisport_lab.operational_key_recovery",
            "source_sha256": hashlib.sha256(Path(recovery.__file__).read_bytes()).hexdigest(),
            "binding": "LOCAL_FILE_BYTES_ONLY", "reviewed_commit": None})
        self.assertEqual(originals, {p: p.read_bytes() for p in originals})
        encoded = json.dumps(report)
        for p in (self.key, self.restored):
            self.assertNotIn(str(p), encoded)
            self.assertNotIn(p.read_text(), encoded)
        self.assertNotIn("PRIVATE KEY", encoded)

    def test_same_inode_or_hardlink_does_not_establish_restored_copy(self):
        with self.assertRaisesRegex(IntegrityError, "distinct regular copy"):
            self.verify(restored_key=self.key)
        self.restored.unlink()
        os.link(self.key, self.restored)
        with self.assertRaisesRegex(IntegrityError, "hard link"):
            self.verify()

    def test_changed_key_wrong_canary_or_tampered_ciphertext_rejects(self):
        with self.assertRaisesRegex(IntegrityError, "differs from the reviewed certificate"):
            self.verify(restored_key=self.wrong_key)
        self.canary.write_bytes(self.encrypt(b"A valid encrypted body is not the registered canary"))
        with self.assertRaisesRegex(IntegrityError, "exact public recovery canary"):
            self.verify()
        ciphertext = bytearray(self.encrypt(recovery.CANARY))
        ciphertext[-1] ^= 1
        self.canary.write_bytes(ciphertext)
        with self.assertRaises(IntegrityError):
            self.verify()

    def test_unadmitted_encryption_suite_cannot_pass_local_recovery(self):
        self.canary.write_bytes(self.encrypt(recovery.CANARY, "cms", "-encrypt", "-binary",
            "-aes-256-cbc", "-outform", "DER", "-recip", str(self.cert)))
        with self.assertRaisesRegex(IntegrityError, "exact admitted encryption suite"):
            self.verify()

    def test_public_certificate_cannot_hide_an_appended_private_key(self):
        bundle = self.root / "unsafe-certificate-bundle.pem"
        bundle.write_bytes(self.cert.read_bytes() + self.key.read_bytes())
        bundle.chmod(0o600)
        with self.assertRaisesRegex(IntegrityError, "no key material") as caught:
            self.verify(certificate=bundle)
        self.assertNotIn(self.key.read_text(), str(caught.exception))

    def test_same_pem_base64_cannot_hide_a_der_trailer_ignored_by_openssl(self):
        original_der = raw._openssl(["x509", "-in", str(self.cert), "-outform", "DER"])
        hidden = self.root / "hidden-certificate-trailer.pem"
        for trailer in (b"synthetic hidden trailing material", original_der):
            with self.subTest(trailer_bytes=len(trailer)):
                hidden.write_bytes(b"-----BEGIN CERTIFICATE-----\n" +
                    base64.encodebytes(original_der + trailer) + b"-----END CERTIFICATE-----\n")
                # Reproduce the permissive parser behavior before checking that
                # the key-recovery boundary rejects those very same bytes.
                self.assertEqual(raw._openssl(["x509", "-in", str(hidden), "-outform", "DER"]), original_der)
                with self.assertRaisesRegex(IntegrityError, "unparsed DER data"):
                    self.verify(certificate=hidden)

    def test_private_permissions_git_placement_and_symlinks_reject(self):
        self.restored.chmod(0o644)
        with self.assertRaisesRegex(IntegrityError, "owner-only"):
            self.verify()
        self.restored.chmod(0o600)
        alias = self.root / "alias.pem"
        alias.symlink_to(self.restored)
        with self.assertRaisesRegex(IntegrityError, "unsafe or unreadable"):
            self.verify(restored_key=alias)
        git_root = self.root / "worktree"
        git_root.mkdir()
        subprocess.run(["git", "init", "-q", str(git_root)], check=True, capture_output=True)
        git_key = git_root / "not-allowed.pem"
        shutil.copyfile(self.key, git_key)
        git_key.chmod(0o600)
        with self.assertRaisesRegex(IntegrityError, "outside every Git worktree"):
            self.verify(restored_key=git_key)

    def test_file_replacement_during_crypto_fails_before_success(self):
        real = recovery._openssl
        replaced = False

        def replace(arguments, *args, **kwargs):
            nonlocal replaced
            result = real(arguments, *args, **kwargs)
            if arguments[0] == "cms" and not replaced:
                replaced = True
                replacement = self.root / "different-inode.pem"
                shutil.copyfile(self.key, replacement)
                replacement.chmod(0o600)
                replacement.replace(self.restored)
            return result

        with mock.patch.object(recovery, "_openssl", side_effect=replace), \
             self.assertRaisesRegex(IntegrityError, "(changed|replaced) during recovery"):
            self.verify()
        self.assertTrue(replaced)

    def test_bounded_inputs_clock_regression_and_unknown_backup_method_reject(self):
        with self.assertRaisesRegex(IntegrityError, "unknown declared"):
            self.verify(backup_method="new-service")
        now = recovery._clock()
        with mock.patch.object(recovery, "_clock", side_effect=(now, now - timedelta(seconds=1))), \
             self.assertRaisesRegex(IntegrityError, "clock moved backwards"):
            self.verify()
        self.canary.write_bytes(b"x" * (recovery.MAX_CANARY_BYTES + 1))
        with self.assertRaisesRegex(IntegrityError, "exceeds its bound"):
            self.verify()

    def test_cli_emits_only_safe_report_and_crypto_errors_do_not_expose_output(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = recovery.main(["--certificate", str(self.cert), "--original-key", str(self.key),
                "--restored-key", str(self.restored), "--canary", str(self.canary)])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "VERIFIED_LOCAL_CANARY_ONLY")
        failure = subprocess.CompletedProcess([], 1, stdout=b"private plaintext", stderr=b"private key path")
        with mock.patch.object(recovery.subprocess, "run", return_value=failure), \
             self.assertRaisesRegex(IntegrityError, "cryptographic authentication") as caught:
            recovery._openssl(["pkey"])
        self.assertNotIn("private plaintext", str(caught.exception))
        self.assertNotIn("private key path", str(caught.exception))
        stderr = io.StringIO()
        self.restored.chmod(0o644)
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
            recovery.main(["--certificate", str(self.cert), "--original-key", str(self.key),
                "--restored-key", str(self.restored), "--canary", str(self.canary)])
        self.assertEqual(caught.exception.code, 2)
        self.assertNotIn(str(self.restored), stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

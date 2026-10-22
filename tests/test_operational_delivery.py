"""Actual encryption and isolated Git transport; no live inputs or model run."""
from copy import deepcopy
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import operational_delivery as delivery
from multisport_lab import operational_pilot as op
from multisport_lab import operational_raw as raw
from multisport_lab.integrity import IntegrityError, digest, read_receipt, write_receipt
from multisport_lab.operational_source_links import EncryptedSourceLinks
from test_operational_pilot import OperationalFixture
from test_pros004_inputs import NOW
from test_pros004_remote import RemoteFixture, git


class DeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys = tempfile.TemporaryDirectory(prefix="nml-delivery-fixture-keys-")
        folder = Path(cls.keys.name)
        cls.key, cls.cert = folder / "private.pem", folder / "recipient.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:3072", "-sha256",
                        "-days", "1", "-nodes", "-keyout", str(cls.key), "-out", str(cls.cert),
                        "-subj", "/CN=OP002 local encrypted delivery fixture"],
                       capture_output=True, check=True, timeout=30)
        cls.key.chmod(0o600)

    @classmethod
    def tearDownClass(cls):
        cls.keys.cleanup()

    def setUp(self):
        self.f = OperationalFixture(self, acknowledge_event=False)
        self.f.at(NOW)
        self.enterContext(patch.object(raw, "_now", side_effect=lambda: self.f.clock.return_value))
        self.archive = raw.EncryptedRawArchive(self.f.root / delivery.ARCHIVE_DIRECTORY,
                                                self.cert, private_key=self.key)
        self.links = EncryptedSourceLinks(self.f.root, self.archive, diagnostic=True)
        self.refs = []
        for observation in self.f.observations:
            source = observation["metadata"]
            ref = self.archive.retain(observation["raw"], mode="SYNTHETIC_DIAGNOSTIC",
                event_id=self.f.plan["event"]["event_id"], source_url=source["source_url"],
                request_started_at=source["request_started_at"], observed_at=source["observed_at"],
                source_updated_at=source["source_updated_at"])
            self.refs.append(self.links.link(ref, source))
        self.binding = self.links.bind_event(self.f.event_ref, self.refs)

    def writer(self, *, source_root=None):
        transport = RemoteFixture(self)
        writer = delivery.PreparedOperatingWriter(source_root or self.f.root, transport.root / "encrypted-writer",
            base_commit=transport.base, branch=delivery.LOCAL_BRANCH, plan=self.f.plan,
            certificate=self.cert, private_key=self.key, local_fixture=True,
            remote_url=str(transport.remote))
        writer.prepare()
        return transport, writer

    def encrypted_orphan(self):
        ciphertext = raw._openssl([
            "cms", "-encrypt", "-binary", "-aes-256-gcm", "-outform", "DER",
            "-recip", str(self.cert), "-keyopt", "rsa_padding_mode:oaep",
            "-keyopt", "rsa_oaep_md:sha256", "-keyopt", "rsa_mgf1_md:sha256"],
            b'{"synthetic":"interrupted before capture manifest"}')
        path = self.archive._cipher(hashlib.sha256(ciphertext).hexdigest())
        path.write_bytes(ciphertext)
        return path, ciphertext

    def test_authenticated_complete_checkpoint_replays_after_actual_fresh_git_fetch(self):
        before = delivery.verify_delivery(self.f.root, self.cert, self.key,
                                          plan=self.f.plan, diagnostic=True)
        self.assertEqual(before["authenticated_captures"], 4)
        self.assertEqual(before["source_links"], 4)
        self.assertEqual(before["bound_event_inputs"], 1)
        self.assertFalse(before["genuine_execution_enabled"])
        transport, writer = self.writer()
        with patch.object(delivery, "verify_delivery", wraps=delivery.verify_delivery) as verify:
            ack = writer.checkpoint(self.f.event_ref)
        roots = [Path(call.args[0]) for call in verify.call_args_list]
        self.assertTrue(any("op002-independent-" in str(root) for root in roots))
        self.assertEqual(ack["snapshot_sha256"], digest(before["snapshot"]))
        self.assertEqual(ack["remote_commit"], git(transport.remote, "rev-parse", "refs/heads/" + writer.branch))
        tracked = git(writer.root, "ls-files").splitlines()
        self.assertEqual(len([path for path in tracked if path.endswith(".cms")]), 4)
        self.assertFalse(any(path.endswith(".pem") for path in tracked))
        self.assertTrue(all(path == "README.md" or path.startswith(("records/", "evidence/operational002/",
                           delivery.ARCHIVE_DIRECTORY + "/")) for path in tracked))
        restarted = delivery.PreparedOperatingWriter(self.f.root, writer.root, base_commit=transport.base,
            branch=writer.branch, plan=self.f.plan, certificate=self.cert, private_key=self.key,
            local_fixture=True, remote_url=str(transport.remote))
        restarted.prepare()
        self.assertEqual(restarted.checkpoint(self.f.event_ref)["remote_commit"], ack["remote_commit"])

    def test_tampered_encrypted_source_rejects_before_checkpoint_acknowledgment(self):
        transport, writer = self.writer()
        source = self.links.read(self.refs[0])
        path = self.archive._cipher(source["body"]["raw_reference"]["cipher_sha256"])
        original = path.read_bytes()
        path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        with self.assertRaises(IntegrityError):
            writer.checkpoint(self.f.event_ref)
        self.assertEqual(git(transport.remote, "for-each-ref", "--format=%(refname)", "refs/heads/" + writer.branch), "")

    def test_unbound_event_is_not_a_complete_input_checkpoint(self):
        self.links.ledger._path(self.binding.kind, self.binding.record_id).unlink()
        with self.assertRaisesRegex(IntegrityError, "exact authenticated four-source binding"):
            delivery.verify_delivery(self.f.root, self.cert, self.key, diagnostic=True)

    def test_key_hash_only_inventory_and_wrong_evidence_lane_do_not_prove_recovery(self):
        snapshot = delivery.delivery_snapshot(self.f.root, self.cert)
        self.assertGreater(snapshot["archive_encoded_bytes"], 0)
        with self.assertRaises(IntegrityError):
            delivery.verify_delivery(self.f.root, self.cert, None, diagnostic=True)
        with self.assertRaisesRegex(IntegrityError, "evidence lane"):
            delivery.verify_delivery(self.f.root, self.cert, self.key)
        wrong = deepcopy(self.f.plan)
        wrong["event"]["event_id"] = "999999"
        with self.assertRaises(IntegrityError):
            delivery.verify_delivery(self.f.root, self.cert, self.key, plan=wrong, diagnostic=True)

    def test_plaintext_or_key_file_cannot_enter_managed_cipher_archive(self):
        (self.archive.root / "raw.json").write_text('{"not":"allowed"}')
        with self.assertRaisesRegex(IntegrityError, "unexpected archive content"):
            delivery.delivery_snapshot(self.f.root, self.cert)

    def test_misnamed_checksum_consistent_capture_manifest_cannot_count_as_recovered_capture(self):
        original = next((self.archive.root / "captures").glob("*.json"))
        duplicate = original.with_name("a" * 64 + ".json")
        self.assertNotEqual(duplicate, original)
        duplicate.write_bytes(original.read_bytes())
        with self.assertRaisesRegex(IntegrityError, "capture manifest.*identity"):
            delivery.verify_delivery(self.f.root, self.cert, self.key, diagnostic=True)
        self.assertEqual(duplicate.read_bytes(), original.read_bytes())

    def test_interrupted_readback_preserves_remote_commit_and_retry_originals(self):
        transport, writer = self.writer()
        before = delivery.delivery_snapshot(self.f.root, self.cert)
        with patch.object(writer, "_fresh_readback", side_effect=OSError("fixture readback interrupted")):
            with self.assertRaises(OSError):
                writer.checkpoint(self.f.event_ref)
        committed = git(transport.remote, "rev-parse", "refs/heads/" + writer.branch)
        self.assertEqual(writer.operations[-1]["status"], "UNACKNOWLEDGED_RETAINED_STATE")
        ack = writer.checkpoint(self.f.event_ref)
        self.assertEqual(ack["remote_commit"], committed)
        self.assertEqual(delivery.delivery_snapshot(self.f.root, self.cert), before)

    def test_production_guard_precedes_any_files_or_transport_and_local_cannot_use_github(self):
        destination = self.f.root.parent / (self.f.root.name + "-forbidden-writer")
        with patch.object(delivery.subprocess, "run", side_effect=AssertionError("unexpected subprocess")):
            with self.assertRaisesRegex(IntegrityError, "NO_REVIEWED_ACTIVATION_INSTALLED"):
                delivery.PreparedOperatingWriter(self.f.root, destination, base_commit="a" * 40,
                    branch="records/nba-paired-ops-002", certificate=self.cert, private_key=self.key)
        self.assertFalse(destination.exists())
        for branch in ("main", delivery.LOCAL_BRANCH, "records/nba-20261020-401909088-t90"):
            with self.assertRaises(IntegrityError):
                delivery.destination_plan(branch)
        with self.assertRaises(IntegrityError):
            delivery.PreparedOperatingWriter(self.f.root, destination, base_commit="a" * 40,
                branch=delivery.LOCAL_BRANCH, certificate=self.cert, private_key=self.key,
                local_fixture=True)

    def test_fetch_and_push_destinations_are_rechecked_before_prepare_and_checkpoint(self):
        transport, writer = self.writer()
        foreign = transport.root / "foreign.git"
        foreign.mkdir()
        git(foreign, "init", "--bare", "--quiet")
        for key in ("remote.origin.pushurl", "remote.origin.url"):
            with self.subTest(key=key):
                git(writer.root, "config", key, str(foreign))
                with self.assertRaisesRegex(IntegrityError, "origin"):
                    writer.prepare()
                with self.assertRaisesRegex(IntegrityError, "origin"):
                    writer.checkpoint(self.f.event_ref)
                self.assertEqual(git(foreign, "for-each-ref", "--format=%(refname)"), "")
                if key.endswith("pushurl"):
                    git(writer.root, "config", "--unset-all", key)
                else:
                    git(writer.root, "config", key, str(transport.remote))
        # A correct first push URL does not authorize a second push destination.
        git(writer.root, "config", "--add", "remote.origin.pushurl", str(transport.remote))
        git(writer.root, "config", "--add", "remote.origin.pushurl", str(foreign))
        with self.assertRaisesRegex(IntegrityError, "fetch/push origin"):
            writer.checkpoint(self.f.event_ref)
        self.assertEqual(git(foreign, "for-each-ref", "--format=%(refname)"), "")
        self.assertEqual(git(transport.remote, "rev-parse", "refs/heads/main"), transport.base)
        self.assertEqual(git(transport.remote, "for-each-ref", "--format=%(refname)",
                             "refs/heads/" + delivery.LOCAL_BRANCH), "")

    def test_mutated_fixture_policy_cannot_reach_main_records_or_another_remote(self):
        transport, writer = self.writer()
        changes = (("branch", "main"), ("branch", "records/nba-paired-ops-002"),
                   ("remote_url", str(transport.root / "different.git")),
                   ("diagnostic", False), ("_local_remote", False))
        for attribute, value in changes:
            with self.subTest(attribute=attribute, value=value):
                original = getattr(writer, attribute)
                setattr(writer, attribute, value)
                try:
                    with self.assertRaisesRegex(IntegrityError, "destination or branch changed"):
                        writer.prepare()
                    with self.assertRaisesRegex(IntegrityError, "destination or branch changed"):
                        writer.checkpoint(self.f.event_ref)
                finally:
                    setattr(writer, attribute, original)
        self.assertEqual(git(transport.remote, "rev-parse", "refs/heads/main"), transport.base)
        self.assertEqual(git(transport.remote, "for-each-ref", "--format=%(refname)"), "refs/heads/main")

    def test_url_rewrite_and_non_file_protocol_fail_before_any_network_transport(self):
        _, writer = self.writer()
        rewrite = "url.https://example.invalid/op002-local-fixture/.insteadOf"
        git(writer.root, "config", rewrite, writer.remote_url)
        with self.assertRaisesRegex(IntegrityError, "fetch/push origin"):
            writer.checkpoint(self.f.event_ref)
        git(writer.root, "config", "--unset-all", rewrite)
        # Even if a URL changes after the destination check, Git itself must
        # reject the protocol before DNS or a connection. This reserved host is
        # never contacted: the real Git result confirms its transport is denied.
        git(writer.root, "config", "protocol.https.allow", "always")
        result = writer._git("ls-remote", "https://example.invalid/op002-local-fixture", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("transport 'https' not allowed", result.stderr)

    def test_archive_only_restart_rejects_checksum_consistent_original_replacement(self):
        temporary = tempfile.TemporaryDirectory(prefix="nml-delivery-partial-source-")
        self.addCleanup(temporary.cleanup)
        source_root = Path(temporary.name) / "source"
        archive_root = source_root / delivery.ARCHIVE_DIRECTORY
        shutil.copytree(self.archive.root, archive_root)
        transport, writer = self.writer(source_root=source_root)
        before = delivery.verify_delivery(source_root, self.cert, self.key, diagnostic=True)
        self.assertEqual(before["snapshot"]["ledger_file_count"], 0)
        self.assertEqual(before["authenticated_captures"], 4)
        self.assertEqual(before["bound_event_inputs"], 0)
        prefix = hashlib.sha256(b"").hexdigest()
        first = writer.final_checkpoint(prefix)
        self.assertFalse((writer.root / "records").exists())
        manifest = next((archive_root / "captures").glob("*.json"))
        original_bytes = manifest.read_bytes()
        changed = read_receipt(manifest)
        self.assertNotEqual(changed["imported_at"], changed["source_observed_at"])
        changed["imported_at"] = changed["source_observed_at"]
        manifest.unlink()
        write_receipt(manifest, changed)
        # The altered receipt is checksum-consistent, decrypts correctly and
        # has valid clocks. Immutability, not malformed-source rejection, must
        # prevent it replacing the first archive-only checkpoint.
        delivery.verify_delivery(source_root, self.cert, self.key, diagnostic=True)
        restarted = delivery.PreparedOperatingWriter(source_root, writer.root, base_commit=transport.base,
            branch=writer.branch, plan=self.f.plan, certificate=self.cert, private_key=self.key,
            local_fixture=True, remote_url=str(transport.remote))
        restarted.prepare()
        with self.assertRaisesRegex(IntegrityError, "replace a retained encrypted or ledger original"):
            restarted.final_checkpoint(prefix)
        self.assertEqual(git(transport.remote, "rev-parse", "refs/heads/" + writer.branch), first["remote_commit"])
        relative = manifest.relative_to(source_root).as_posix()
        self.assertEqual((writer.root / relative).read_bytes(), original_bytes)
        self.assertEqual(git(transport.remote, "show", first["remote_commit"] + ":" + relative),
                         original_bytes.decode())
        self.assertEqual(read_receipt(manifest), changed)

    def test_invalid_orphan_envelopes_stay_local_and_block_before_push(self):
        transport, writer = self.writer()
        cbc = raw._openssl(["cms", "-encrypt", "-binary", "-aes-256-cbc", "-outform", "DER",
                            "-recip", str(self.cert)], b"synthetic wrong-suite orphan")
        for label, content in (("plaintext", b'{"unapproved":"plaintext"}'),
                               ("pem", b"-----BEGIN PRIVATE KEY-----\nfixture, not a key\n-----END PRIVATE KEY-----\n"),
                               ("cbc", cbc)):
            with self.subTest(label=label):
                path = self.archive._cipher(hashlib.sha256(content).hexdigest())
                path.write_bytes(content)
                self.assertEqual(self.archive.inventory()["captures"], 4)
                with patch.object(writer, "_git", wraps=writer._git) as commands:
                    with self.assertRaises(IntegrityError):
                        writer.checkpoint(self.f.event_ref)
                self.assertFalse(any(call.args[0] == "push" for call in commands.call_args_list))
                self.assertEqual(path.read_bytes(), content)
                self.assertFalse((writer.root / delivery.ARCHIVE_DIRECTORY).exists())
                self.assertEqual(git(transport.remote, "for-each-ref", "--format=%(refname)",
                                     "refs/heads/" + writer.branch), "")
                path.unlink()  # Only this invented invalid test object.

    def test_partial_archive_preserves_orphan_ciphertext_without_inventing_capture(self):
        # An encrypted orphan is counted and preserved, never authenticated as a
        # newly captured observation. Existing complete sources still replay.
        path, orphan = self.encrypted_orphan()
        report = delivery.verify_delivery(self.f.root, self.cert, self.key, diagnostic=True)
        self.assertEqual(report["authenticated_captures"], 4)
        self.assertEqual(report["snapshot"]["archive_file_count"], 9)
        transport, writer = self.writer()
        ack = writer.checkpoint(self.f.event_ref)
        relative = path.relative_to(self.f.root).as_posix()
        self.assertEqual((writer.root / relative).read_bytes(), orphan)
        fetched = subprocess.run(["git", "show", ack["remote_commit"] + ":" + relative],
                                 cwd=transport.remote, check=True, capture_output=True).stdout
        self.assertEqual(fetched, orphan)
        self.assertEqual(path.read_bytes(), orphan)


if __name__ == "__main__":
    unittest.main()

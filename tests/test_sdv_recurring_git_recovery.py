"""Independent Git transport of invented planning records; never live issuance."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from multisport_lab.sdv_recurring_store import RecurringStore
import test_sdv_recurring_store as fixtures


class RecurringGitRecoveryTests(unittest.TestCase):
    def test_fresh_git_object_database_recovers_original_plan_and_source_bytes(self):
        fixture = fixtures.RecurringStoreTests(
            "test_exact_sources_plan_and_restart_preserve_original_bytes")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        reference, body, source_refs = fixture.plan()
        original = {
            str(p.relative_to(fixture.root)): p.read_bytes()
            for prefix in ("records", "recurring/records")
            for p in (fixture.root / prefix).rglob("*.json")
        }

        def git(root, *args):
            return subprocess.run(["git", "-C", str(root), *args], check=True,
                                  capture_output=True, text=True, timeout=20).stdout.strip()

        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            remote, recovered = base / "remote.git", base / "recovered"
            remote.mkdir(); recovered.mkdir()
            git(remote, "init", "--quiet", "--bare")
            git(fixture.root, "init", "--quiet")
            git(fixture.root, "add", "records", "recurring/records")
            git(fixture.root, "-c", "user.name=Synthetic research test",
                "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m",
                "Retain invented planning evidence")
            head = git(fixture.root, "rev-parse", "HEAD")
            git(fixture.root, "push", str(remote), "HEAD:refs/heads/planning")
            git(recovered, "init", "--quiet")
            git(recovered, "remote", "add", "origin", str(remote))
            git(recovered, "fetch", "--quiet", "--no-tags", "--depth=1", "origin", head)
            git(recovered, "checkout", "--quiet", "--detach", "FETCH_HEAD")
            self.assertEqual(git(recovered, "rev-parse", "HEAD"), head)
            self.assertFalse((recovered / ".git/objects/info/alternates").exists())

            store = RecurringStore(recovered)
            state = store.recover()
            self.assertEqual(state["plans"], [(reference, body)])
            self.assertEqual(state["genuine_forecasts"], 0)
            self.assertFalse(state["prospective_admission"])
            self.assertEqual(state["local_persistence_completion"],
                             "NOT_ESTABLISHED_BY_RECEIPT_CLOCK")
            for path, raw in original.items():
                self.assertEqual((recovered / path).read_bytes(), raw)
            for ref, role in zip(source_refs, ("schedule", "roster")):
                raw, metadata, _ = store.read_source_pack(ref)
                self.assertEqual(metadata["role"], role)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), metadata["asset_sha256"])
            self.assertEqual(git(recovered, "status", "--porcelain"),
                             "?? recurring/.writer.lock")

"""Local bare-Git publication transport checks, never a live source or model run.

The typed snapshot admission helper is replaced with an explicit software fixture
to isolate exact Git selection, immutable import and rejection before copying.
Real typed contracts are covered by test_sdv_daily_publication and store tests.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import sdv_daily_publication as publication
from multisport_lab.integrity import IntegrityError, canonical, load_json
from multisport_lab.ledger import Ledger
from multisport_lab.sdv_daily_store import DailyStore


ROOT = Path(__file__).resolve().parents[1]


class DailyRemotePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.root = self.folder / "publication-root"
        self.root.mkdir()
        self.source = self.folder / "synthetic-records-writer"
        self.source.mkdir()
        self.remote = self.folder / "local-only.git"
        self.now = datetime.now(timezone.utc)
        self.fixture = load_json(ROOT / "tests/fixtures/sdv-daily-synthetic.json")
        self.branch = self.fixture["cycle"]["records_branch"]
        config = self.root / "config/sdv_daily_cycle_v1.json"
        config.parent.mkdir()
        config.write_bytes(canonical(self.fixture["cycle"]))
        # Nineteen small original receipts model the preservation boundary; they
        # contain no historical panel and do not stand in for actual research.
        ledger = Ledger(self.root)
        for index in range(19):
            ledger.append("input_captures", "synthetic-existing-" + str(index),
                          {"identity": {"software_fixture_original": index}})
        (self.root / "records/README.md").write_text("Local ledger documentation must remain unchanged.\n")
        shutil.copytree(self.root / "records", self.source / "records")
        (self.source / "records/README.md").write_text("Remote documentation is not an imported ledger record.\n")
        self.before = self.inventory(self.root / "records")
        self.git("init", "--quiet", cwd=self.source)
        self.git("config", "user.name", "Synthetic Publication Test", cwd=self.source)
        self.git("config", "user.email", "software-fixture@example.invalid", cwd=self.source)
        self.git("init", "--bare", "--quiet", str(self.remote), cwd=self.folder)
        self.git("remote", "add", "origin", str(self.remote), cwd=self.source)
        self.git("add", "records", cwd=self.source)
        self.git("commit", "--quiet", "-m", "Synthetic retained originals", cwd=self.source)
        self.main = self.git("rev-parse", "HEAD", cwd=self.source).stdout.strip()
        self.git("push", "--quiet", "origin", "HEAD:refs/heads/main", cwd=self.source)
        self.git("checkout", "--quiet", "-b", self.branch, cwd=self.source)
        # A valid retained proposal lets the final independent store scan run
        # for real. Only the mocked helper claims genuine admission in positives.
        store = DailyStore(self.source)
        cycle_ref = store.append_body("input_captures", self.fixture["cycle"])
        self.relative = Path("daily/records/input_captures") / (cycle_ref.record_id + ".json")
        # This file deliberately lies outside the permitted import namespace.
        (self.source / "never_execute_remote.py").write_text(
            "raise RuntimeError('A publication import must never execute remote source')\n")
        self.head = self.publish("Synthetic daily transport fixture")
        self.remote_patch = patch.object(publication, "REMOTE_URL", str(self.remote))
        self.remote_patch.start()
        self.addCleanup(self.remote_patch.stop)

    @staticmethod
    def inventory(root):
        return {path.relative_to(root): path.read_bytes()
                for path in root.rglob("*.json")} if root.exists() else {}

    def git(self, *args, cwd):
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                              check=True, timeout=30)

    def publish(self, message):
        self.git("add", "--all", cwd=self.source)
        self.git("commit", "--quiet", "-m", message, cwd=self.source)
        self.git("push", "--quiet", "origin", "HEAD:refs/heads/" + self.branch,
                 cwd=self.source)
        return self.git("rev-parse", "HEAD", cwd=self.source).stdout.strip()

    def admitted(self):
        """The mocked helper's explicit output, not real admission evidence."""
        asset = deepcopy(self.fixture)
        for row in asset["forecasts"]:
            row["body"]["mode"] = "PROSPECTIVE_RESEARCH"
            row["body"]["evidence_lane"] = "DAILY_SNAPSHOT_PROSPECTIVE"
            row["admission"]["eligible"] = True
            row["admission"]["reasons"] = []
        asset["counts"] = {"development_forecasts": 0, "genuine_forecasts": 8,
                           "eligible_forecasts": 8, "pending_grades": 8}
        asset["activation"] = {"explicit_software_fixture": "typed helper output only"}
        return asset

    def prepare(self, *, asset=None, commit=None):
        fixture = self.admitted() if asset is None else asset
        with patch.object(publication, "_validate_remote_records", return_value=fixture) as checked:
            result = publication.prepare_published_records(self.root, commit=commit, now=self.now)
        return result, checked

    def test_exact_branch_head_imports_only_immutable_records_and_retries_idempotently(self):
        expected = (self.source / self.relative).read_bytes()
        result, checked = self.prepare(commit=self.head)
        self.assertEqual(result["status"], "IMPORTED")
        self.assertEqual(result["commit"], self.head)
        self.assertGreater(result["records"], 0)
        self.assertEqual(result["eligible_forecasts"], 8)
        self.assertEqual(checked.call_count, 1)
        staged = Path(checked.call_args.args[0])
        self.assertNotEqual(staged, self.root)
        self.assertNotEqual(staged, self.source)
        self.assertEqual((self.root / self.relative).read_bytes(), expected)
        self.assertFalse((self.root / "never_execute_remote.py").exists())
        self.assertEqual((self.root / "records/README.md").read_text(),
                         "Local ledger documentation must remain unchanged.\n")
        self.assertEqual(self.inventory(self.root / "records"), self.before)
        first = self.inventory(self.root / "daily/records")
        recovered, _ = self.prepare(commit=self.head)
        self.assertEqual(recovered["commit"], self.head)
        self.assertEqual(self.inventory(self.root / "daily/records"), first)

    def test_omitted_commit_selects_actual_fixed_records_branch_head(self):
        result, _ = self.prepare()
        self.assertEqual(result["commit"], self.head)
        self.assertEqual((self.root / self.relative).read_bytes(),
                         (self.source / self.relative).read_bytes())

    def test_development_or_ineligible_helper_result_never_imports(self):
        for change in ("development", "no_eligible", "no_authorization", "foreign_cycle"):
            with self.subTest(change=change):
                asset = self.admitted()
                if change == "development":
                    asset["forecasts"][0]["body"]["mode"] = "DEVELOPMENT_ONLY"
                    asset["counts"]["development_forecasts"] = 1
                elif change == "no_eligible":
                    for row in asset["forecasts"]:
                        row["admission"]["eligible"] = False
                    asset["counts"]["eligible_forecasts"] = 0
                elif change == "no_authorization":
                    asset["activation"] = None
                else:
                    asset["cycle"]["records_branch"] = "records/unregistered-branch"
                with self.assertRaises(IntegrityError):
                    self.prepare(asset=asset)
                self.assertFalse((self.root / self.relative).exists())
                self.assertEqual(self.inventory(self.root / "records"), self.before)

    def test_partial_originals_can_publish_when_a_genuine_peer_is_eligible(self):
        asset = self.admitted()
        asset["forecasts"][0]["admission"]["eligible"] = False
        asset["forecasts"][0]["admission"]["reasons"] = ["Synthetic missing remote acknowledgment"]
        asset["counts"]["eligible_forecasts"] = 7
        result, _ = self.prepare(asset=asset)
        self.assertEqual(result["status"], "IMPORTED")
        self.assertEqual(result["eligible_forecasts"], 7)
        self.assertEqual((self.root / self.relative).read_bytes(),
                         (self.source / self.relative).read_bytes())

    def test_unknown_or_non_head_commit_cannot_substitute_another_branch(self):
        for commit in ("f" * 40, self.main):
            with self.subTest(commit=commit), self.assertRaises(IntegrityError):
                self.prepare(commit=commit)
        self.assertFalse((self.root / self.relative).exists())

    def test_missing_registered_branch_is_no_records_without_claiming_recovery(self):
        self.git("push", "--quiet", "origin", ":refs/heads/" + self.branch,
                 cwd=self.source)
        result, checked = self.prepare()
        self.assertEqual(result, {"status": "NO_RECORDS", "commit": None,
                                  "records": 0, "eligible_forecasts": 0})
        self.assertEqual(checked.call_count, 0)
        with self.assertRaises(IntegrityError):
            self.prepare(commit=self.head)
        self.assertFalse((self.root / self.relative).exists())

    def test_changed_parent_record_rejects_before_any_daily_copy(self):
        original = next((self.source / "records").rglob("*.json"))
        original.write_bytes(original.read_bytes() + b" ")
        self.head = self.publish("Synthetic forbidden parent original change")
        with self.assertRaises(IntegrityError):
            self.prepare()
        self.assertFalse((self.root / self.relative).exists())
        self.assertEqual(self.inventory(self.root / "records"), self.before)

    def test_existing_daily_original_is_never_overwritten(self):
        target = self.root / self.relative
        target.parent.mkdir(parents=True)
        original = b'{"explicit_software_fixture":"different retained original"}\n'
        target.write_bytes(original)
        with self.assertRaises(IntegrityError):
            self.prepare()
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(self.inventory(self.root / "records"), self.before)

    def test_typed_recovery_rejection_does_not_copy_any_remote_bytes(self):
        with patch.object(publication, "_validate_remote_records",
                          side_effect=IntegrityError("synthetic invalid typed original")):
            with self.assertRaisesRegex(IntegrityError, "invalid typed original"):
                publication.prepare_published_records(self.root, now=self.now)
        self.assertFalse((self.root / self.relative).exists())
        self.assertEqual(self.inventory(self.root / "records"), self.before)

    def test_actual_typed_boundary_rejects_unissued_cycle_without_fabricating_forecasts(self):
        # No semantic helper is mocked in this negative integration check.
        # The bare branch contains only the valid, unissued proposal above.
        with self.assertRaises(IntegrityError):
            publication.prepare_published_records(self.root, now=self.now)
        self.assertFalse((self.root / self.relative).exists())
        self.assertEqual(self.inventory(self.root / "records"), self.before)


if __name__ == "__main__":
    unittest.main()

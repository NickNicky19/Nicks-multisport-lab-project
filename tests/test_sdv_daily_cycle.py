"""Synthetic authorization proofs; these tests never dispatch or query GitHub."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import sdv_daily_cycle as daily
from multisport_lab.integrity import IntegrityError, canonical, digest, stamp, utc


REGISTERED = datetime(2026, 10, 22, 1, 0, tzinfo=timezone.utc)
CHECKED = datetime(2026, 10, 22, 22, 5, tzinfo=timezone.utc)
STARTED = CHECKED - timedelta(minutes=4)
SOURCE_COMMIT = "a" * 40
WORKFLOW_COMMIT = "b" * 40


def seal(body, field):
    return {**{key: value for key, value in body.items() if key != field},
            field: digest({key: value for key, value in body.items() if key != field})}


def binding():
    return seal({"schema_version": daily.BINDING_SCHEMA, "commit": SOURCE_COMMIT,
                 "files": {"multisport_lab/baseline.py": daily.LAW_SHA256["R0"],
                           "multisport_lab/development_003.py": daily.LAW_SHA256["K0"],
                           "multisport_lab/sdv_daily_cycle.py": "c" * 64},
                 "law_sha256": deepcopy(daily.LAW_SHA256)}, "binding_id")


def event(cycle, producer):
    return {"ref": "main", "repository": {"full_name": daily.REPOSITORY},
            "sender": {"login": daily.OWNER},
            "inputs": {"cycle_id": cycle["cycle_id"], "producer_commit": producer["commit"],
                       "confirmation": "APPROVE " + cycle["cycle_id"] + " " + producer["commit"]}}


def run_metadata():
    return {"id": 1234, "run_attempt": 1, "event": "workflow_dispatch", "path": daily.WORKFLOW_PATH,
            "head_branch": "main", "head_sha": WORKFLOW_COMMIT,
            "run_started_at": STARTED.isoformat().replace("+00:00", "Z"),
            "actor": {"login": daily.OWNER}, "triggering_actor": {"login": daily.OWNER},
            "repository": {"full_name": daily.REPOSITORY},
            "status": "in_progress", "conclusion": None}


def proof(cycle, producer):
    event_raw, run_raw = canonical(event(cycle, producer)), canonical(run_metadata())
    return seal({"schema_version": daily.AUTHORIZATION_SCHEMA, "protocol_id": daily.PROTOCOL_ID,
                 "cycle_id": cycle["cycle_id"], "cycle_digest": cycle["cycle_digest"],
                 "policy_id": cycle["policy_id"], "producer_commit": producer["commit"],
                 "producer_binding_id": producer["binding_id"], "repository": daily.REPOSITORY,
                 "workflow_path": daily.WORKFLOW_PATH, "workflow_run_id": 1234, "run_attempt": 1,
                 "actor": daily.OWNER, "run_head_sha": WORKFLOW_COMMIT,
                 "run_started_at": stamp(STARTED), "checked_at": stamp(CHECKED),
                 "confirmation": event(cycle, producer)["inputs"]["confirmation"],
                 "event_payload_sha256": hashlib.sha256(event_raw).hexdigest(),
                 "event_payload_base64": base64.b64encode(event_raw).decode(),
                 "run_metadata_base64": base64.b64encode(run_raw).decode(),
                 "run_metadata_sha256": hashlib.sha256(run_raw).hexdigest(),
                 "executed_file_sha256": deepcopy(producer["files"])}, "authorization_id")


def replace_original(body, key, value):
    body = deepcopy(body)
    raw = canonical(value)
    body[key + "_base64"] = base64.b64encode(raw).decode()
    body[key + "_sha256"] = hashlib.sha256(raw).hexdigest()
    return seal(body, "authorization_id")


class DailyCycleFixture(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(daily, "_now", return_value=CHECKED)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.cycle = daily.make_cycle(registered_at=REGISTERED)
        self.binding = binding()
        self.proof = proof(self.cycle, self.binding)
        cache = patch.dict(daily._AUTHORIZATION_CONTEXTS, {}, clear=True)
        cache.start()
        self.addCleanup(cache.stop)

    def validate(self, body=None, producer=None):
        return daily.validate_authorization(self.proof if body is None else body,
            cycle=self.cycle, producer_binding=self.binding if producer is None else producer,
            now=CHECKED)


class DailyCycleTests(DailyCycleFixture):
    def test_declaration_fixes_event_cohort_history_policy_and_daily_windows(self):
        self.assertEqual(self.cycle["event"]["event_id"], "401909094")
        self.assertEqual(len(self.cycle["candidates"]), 4)
        self.assertEqual(self.cycle["history_rows"], 26645)
        self.assertEqual(self.cycle["history_panel_sha256"], daily.HISTORY_PANEL_SHA256)
        self.assertEqual(self.cycle["runner_start_earliest_at"], "2026-10-22T22:00:00.000000Z")
        self.assertEqual(self.cycle["activation_deadline"], "2026-10-22T22:30:00.000000Z")
        self.assertEqual(self.cycle["retrieval_opens_at"], "2026-10-22T23:00:00.000000Z")
        self.assertEqual(self.cycle["cutoff_at"], "2026-10-23T00:00:00.000000Z")
        self.assertEqual(self.cycle["issuance_closes_at"], "2026-10-23T00:15:00.000000Z")
        self.assertNotIn("active", self.cycle)

    def test_resealed_changed_reservation_or_registration_rejected(self):
        changes = [("history_rows", 20000), ("cutoff_at", "2026-10-23T00:01:00.000000Z"),
                   ("registered_at", "2026-10-22T22:31:00.000000Z"),
                   ("history_panel_sha256", "0" * 64), ("qualification", "QUALIFIED")]
        for key, value in changes:
            with self.subTest(key=key), self.assertRaises(IntegrityError):
                body = deepcopy(self.cycle)
                body[key] = value
                daily.validate_cycle(seal(body, "cycle_digest"))
        changed = deepcopy(self.cycle)
        changed["candidates"][0]["player_id"] = "999"
        with self.assertRaises(IntegrityError):
            daily.validate_cycle(seal(changed, "cycle_digest"))

    def test_retained_proof_allows_distinct_reviewed_and_release_merge_commits(self):
        recovered = self.validate()
        self.assertEqual(recovered["producer_commit"], SOURCE_COMMIT)
        self.assertEqual(recovered["run_head_sha"], WORKFLOW_COMMIT)
        self.assertNotEqual(SOURCE_COMMIT, WORKFLOW_COMMIT)
        self.assertEqual(recovered["executed_file_sha256"], self.binding["files"])

    def test_complete_retained_binding_is_checked_without_optional_argument(self):
        self.assertEqual(daily.validate_authorization(self.proof, cycle=self.cycle,
            now=CHECKED), self.proof)
        changed = deepcopy(self.proof)
        changed["producer_binding_id"] = "0" * 64
        with self.assertRaises(IntegrityError):
            daily.validate_authorization(seal(changed, "authorization_id"), cycle=self.cycle,
                now=CHECKED)

    def test_proof_changes_fail_even_with_valid_checksums(self):
        for key, value in [("event", "schedule"), ("path", "another.yml"),
                           ("head_branch", "implementation/unreviewed"),
                           ("head_sha", "d" * 40), ("id", 999), ("run_attempt", 2),
                           ("actor", {"login": "someone-else"}),
                           ("triggering_actor", {"login": "someone-else"}),
                           ("repository", {"full_name": "other/repo"}),
                           ("status", "completed"), ("conclusion", "failure")]:
            with self.subTest(key=key), self.assertRaises(IntegrityError):
                run = run_metadata()
                run[key] = value
                self.validate(replace_original(self.proof, "run_metadata", run))

    def test_event_proof_binds_owner_source_and_exact_confirmation(self):
        for key, value in [("ref", "implementation/branch"), ("sender", {"login": "other"}),
                           ("repository", {"full_name": "other/repo"}),
                           ("inputs", {"cycle_id": self.cycle["cycle_id"],
                                       "producer_commit": SOURCE_COMMIT, "confirmation": "yes"})]:
            with self.subTest(key=key), self.assertRaises(IntegrityError):
                changed = event(self.cycle, self.binding)
                changed[key] = value
                self.validate(replace_original(self.proof, "event_payload", changed))

    def test_bare_approval_extra_fields_or_changed_source_cannot_grant_authority(self):
        for changes in [{"approved": True}, {"producer_commit": "d" * 40},
                        {"workflow_run_id": True}, {"executed_file_sha256": {}},
                        {"event_payload_sha256": "0" * 64}]:
            changed = {**deepcopy(self.proof), **changes}
            with self.subTest(changes=changes), self.assertRaises(IntegrityError):
                self.validate(seal(changed, "authorization_id"))
        with self.assertRaises(TypeError):
            daily.authorize_owner_dispatch(self.cycle, self.binding, approval=self.proof)

    def test_deadline_start_and_completion_clocks_are_strict(self):
        for field, value in [("run_started_at", "2026-10-22T21:59:59.000000Z"),
                             ("checked_at", "2026-10-22T22:30:00.000000Z"),
                             ("checked_at", "2026-10-22T22:00:00.000000Z"),
                             ("checked_at", "2026-10-22T22:05:00.000001Z")]:
            with self.subTest(field=field), self.assertRaises(IntegrityError):
                changed = deepcopy(self.proof)
                changed[field] = value
                self.validate(seal(changed, "authorization_id"))

    def test_proof_json_is_bounded_and_original_bytes_are_checked(self):
        changed = deepcopy(self.proof)
        changed["event_payload_base64"] = base64.b64encode(b"{}" * daily.MAX_EVENT_BYTES).decode()
        with self.assertRaises(IntegrityError):
            self.validate(seal(changed, "authorization_id"))
        raw = b'{"repository":{},"repository":{}}'
        changed = deepcopy(self.proof)
        changed["event_payload_base64"] = base64.b64encode(raw).decode()
        changed["event_payload_sha256"] = hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(IntegrityError, "Duplicate JSON"):
            self.validate(seal(changed, "authorization_id"))


class DailyOwnerRuntimeTests(DailyCycleFixture):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.event_path = Path(self.temp.name) / "dispatch.json"
        self.event_path.write_bytes(canonical(event(self.cycle, self.binding)))
        self.environment = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": daily.REPOSITORY,
            "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_ACTOR": daily.OWNER,
            "GITHUB_TRIGGERING_ACTOR": daily.OWNER, "GITHUB_REF": "refs/heads/main",
            "GITHUB_WORKFLOW_REF": daily.REPOSITORY + "/" + daily.WORKFLOW_PATH + "@refs/heads/main",
            "GITHUB_RUN_ID": "1234", "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_EVENT_PATH": str(self.event_path), "GH_TOKEN": "synthetic-test-token"}
        self.env = patch.dict(os.environ, self.environment, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        fetch_patch = patch.object(daily, "_fetch_run_metadata", return_value=canonical(run_metadata()))
        self.fetch = fetch_patch.start()
        self.addCleanup(fetch_patch.stop)
        source_patch = patch.object(daily, "_verify_executed_source")
        self.source = source_patch.start()
        self.addCleanup(source_patch.stop)
        cycle_patch = patch.object(daily, "load_cycle", return_value=self.cycle)
        cycle_patch.start()
        self.addCleanup(cycle_patch.stop)

    def test_actual_entrypoint_retains_complete_proof_after_transport_and_source_checks(self):
        result = daily.authorize_owner_dispatch(self.cycle, self.binding, repository_root=self.temp.name)
        self.assertEqual(result, self.proof)
        self.fetch.assert_called_once_with(1234, "synthetic-test-token")
        self.source.assert_called_once_with(Path(self.temp.name), self.binding, WORKFLOW_COMMIT)

    def test_untrusted_runtime_cannot_reach_api(self):
        for key, value in [("GITHUB_ACTIONS", "false"), ("GITHUB_ACTOR", "other"),
                           ("GITHUB_REF", "refs/heads/other"), ("GITHUB_EVENT_NAME", "push"),
                           ("GITHUB_REPOSITORY", "other/repo"), ("GITHUB_RUN_ID", ""),
                           ("GITHUB_WORKFLOW_REF", "other"), ("GH_TOKEN", "")]:
            with self.subTest(key=key), patch.dict(os.environ, {key: value}):
                with self.assertRaises(IntegrityError):
                    daily.authorize_owner_dispatch(self.cycle, self.binding)
        self.fetch.assert_not_called()

    def test_wrong_event_inputs_or_owner_reject_before_api(self):
        for change in [lambda v: v["inputs"].update(confirmation="approve"),
                       lambda v: v["inputs"].update(extra="unexpected"),
                       lambda v: v.update(sender={"login": "other"})]:
            body = event(self.cycle, self.binding)
            change(body)
            self.event_path.write_bytes(canonical(body))
            with self.assertRaises(IntegrityError):
                daily.authorize_owner_dispatch(self.cycle, self.binding)
        self.fetch.assert_not_called()

    def test_completion_after_deadline_rejected_even_when_query_started_timely(self):
        values = [CHECKED, CHECKED, utc(self.cycle["activation_deadline"]),
                  utc(self.cycle["activation_deadline"])]
        with patch.object(daily, "_now", side_effect=values), self.assertRaises(IntegrityError):
            daily.authorize_owner_dispatch(self.cycle, self.binding)
        self.fetch.assert_called_once()
        self.source.assert_called_once()

    def test_unreviewed_executed_source_or_changed_api_run_rejects(self):
        self.source.side_effect = IntegrityError("executed source differs")
        with self.assertRaisesRegex(IntegrityError, "source differs"):
            daily.authorize_owner_dispatch(self.cycle, self.binding)
        self.source.reset_mock(side_effect=True)
        run = run_metadata()
        run["actor"] = {"login": "other"}
        self.fetch.return_value = canonical(run)
        with self.assertRaises(IntegrityError):
            daily.authorize_owner_dispatch(self.cycle, self.binding)
        self.source.assert_not_called()

    def test_retained_offline_proof_cannot_grant_current_process_authority(self):
        with self.assertRaisesRegex(IntegrityError, "has not authenticated"):
            daily.require_dispatch_context(self.proof, self.binding)
        self.fetch.assert_not_called()

    def test_same_process_retries_recheck_runtime_and_source_without_new_http(self):
        original = daily.authorize_owner_dispatch(self.cycle, self.binding,
            repository_root=self.temp.name)
        self.fetch.reset_mock()
        self.source.reset_mock()
        self.assertEqual(daily.require_dispatch_context(original, self.binding), original)
        self.fetch.assert_not_called()
        self.source.assert_called_once()
        with patch.dict(os.environ, {"GH_TOKEN": "changed-context-token"}), self.assertRaises(IntegrityError):
            daily.require_dispatch_context(original, self.binding)

    def test_same_run_restart_after_activation_deadline_retains_original_authorization(self):
        now = utc("2026-10-23T00:01:00.000000Z")
        original_bytes = canonical(self.proof)
        with patch.object(daily, "_now", return_value=now):
            restored = daily.authenticate_retained_dispatch(self.proof, self.binding,
                repository_root=self.temp.name)
            self.assertEqual(canonical(restored), original_bytes)
            self.fetch.assert_called_once()
            self.fetch.reset_mock()
            self.assertEqual(daily.require_dispatch_context(restored, self.binding), self.proof)
            self.fetch.assert_not_called()

    def test_restart_changed_attempt_or_closed_window_cannot_reach_api(self):
        with patch.dict(os.environ, {"GITHUB_RUN_ATTEMPT": "2"}), self.assertRaises(IntegrityError):
            daily.authenticate_retained_dispatch(self.proof, self.binding)
        self.fetch.assert_not_called()
        now = utc(self.cycle["issuance_closes_at"]) + timedelta(microseconds=1)
        with patch.object(daily, "_now", return_value=now), self.assertRaises(IntegrityError):
            daily.authenticate_retained_dispatch(self.proof, self.binding)
        self.fetch.assert_not_called()

    def test_restart_authentication_finishing_late_does_not_seed_context(self):
        before = utc(self.cycle["issuance_closes_at"]) - timedelta(seconds=1)
        after = utc(self.cycle["issuance_closes_at"]) + timedelta(seconds=1)
        # Cycle validation, original proof validation and two pre-query bounds,
        # then actual completion after server and source checks.
        with patch.object(daily, "_now", side_effect=[before, before, before, after]), \
                self.assertRaises(IntegrityError):
            daily.authenticate_retained_dispatch(self.proof, self.binding)
        self.assertNotIn(self.proof["authorization_id"], daily._AUTHORIZATION_CONTEXTS)


class DailyExecutedSourceTests(unittest.TestCase):
    def test_release_descendant_requires_every_reviewed_file_byte_and_clean_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = Path(__file__).resolve().parents[1]
            files = {}
            for relative in ["multisport_lab/baseline.py", "multisport_lab/development_003.py"]:
                path = root / relative
                path.parent.mkdir(exist_ok=True)
                raw = (source_root / relative).read_bytes()
                path.write_bytes(raw)
                files[relative] = hashlib.sha256(raw).hexdigest()
            env = {**os.environ, "GIT_AUTHOR_NAME": "Synthetic", "GIT_AUTHOR_EMAIL": "synthetic@example.invalid",
                   "GIT_COMMITTER_NAME": "Synthetic", "GIT_COMMITTER_EMAIL": "synthetic@example.invalid"}
            def git(*args):
                return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                    check=True, env=env).stdout.decode().strip()
            git("init", "--quiet")
            git("add", ".")
            git("commit", "-qm", "Synthetic reviewed source")
            source_commit = git("rev-parse", "HEAD")
            producer = seal({"schema_version": daily.BINDING_SCHEMA, "commit": source_commit,
                "files": files, "law_sha256": daily.LAW_SHA256}, "binding_id")
            (root / "release.txt").write_text("Synthetic release metadata\n")
            git("add", "release.txt")
            git("commit", "-qm", "Synthetic release descendant")
            release_commit = git("rev-parse", "HEAD")
            self.assertNotEqual(source_commit, release_commit)
            daily._verify_executed_source(root, producer, release_commit)
            (root / "multisport_lab/baseline.py").write_bytes(b"unreviewed bytes")
            with self.assertRaisesRegex(IntegrityError, "bytes differ"):
                daily._verify_executed_source(root, producer, release_commit)
            with self.assertRaisesRegex(IntegrityError, "checkout"):
                daily._verify_executed_source(root, producer, source_commit)


if __name__ == "__main__":
    unittest.main()

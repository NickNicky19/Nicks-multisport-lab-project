"""Synthetic guarded-release contracts; never invoke Git, GitHub or a merge."""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("nml_github_release_test_target", ROOT / "scripts/github_release.py")
release = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release
SPEC.loader.exec_module(release)
PINNED_HELPERS = dict(release.HELPERS)
HEAD, EXECUTION, TREE, MERGE = "a" * 40, "b" * 40, "c" * 40, "d" * 40
DIGEST = "e" * 64
PR = 22


def request_data(action="plan"):
    ref = f"refs/heads/execution/guarded-pr-{PR}-{HEAD}"
    event = {"sender": {"login": release.OWNER},
             "repository": {"full_name": release.REPOSITORY},
             "inputs": {"release_action": action, "release_pr": str(PR),
                        "release_head": HEAD, "release_policy_digest": "",
                        "release_confirmation": ""}}
    if action == "land":
        event["inputs"].update(release_policy_digest=DIGEST,
            release_confirmation=release.confirmation(PR, HEAD))
    env = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
           "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REPOSITORY": release.REPOSITORY,
           "GITHUB_ACTOR": release.OWNER, "GITHUB_REF": ref,
           "GITHUB_WORKFLOW_REF": f"{release.REPOSITORY}/.github/workflows/pages.yml@{ref}",
           "GITHUB_SHA": EXECUTION, "GITHUB_RUN_ATTEMPT": "1"}
    return event, env


def pr_data(*, merged=False):
    return {"number": PR, "state": "closed" if merged else "open", "merged": merged,
            "head": {"sha": HEAD, "repo": {"full_name": release.REPOSITORY}},
            "base": {"ref": "main", "repo": {"full_name": release.REPOSITORY}},
            "merge_commit_sha": MERGE if merged else None}


def plan_data():
    return {"state": "confirmation_required", "requiresConfirmation": True,
            "repository": release.REPOSITORY, "headSha": HEAD, "pr": {"number": PR},
            "mode": "auto", "method": "merge", "readinessPolicy": {"checkPolicy": "all"},
            "readinessPolicyDigest": DIGEST}


class ReleaseIdentityTests(unittest.TestCase):
    def test_only_owner_dispatched_github_hosted_candidate_bound_workflow_is_accepted(self):
        event, env = request_data()
        self.assertEqual(release.parse_request(event, env), release.Request("plan", PR, HEAD, ""))
        changes = {"GITHUB_ACTIONS": "false", "RUNNER_ENVIRONMENT": "self-hosted",
                   "GITHUB_EVENT_NAME": "push", "GITHUB_REPOSITORY": "someone/fork",
                   "GITHUB_ACTOR": "another-user", "GITHUB_REF": "refs/heads/main",
                   "GITHUB_WORKFLOW_REF": f"{release.REPOSITORY}/.github/workflows/other.yml@{env['GITHUB_REF']}"}
        for key, value in changes.items():
            with self.subTest(key=key), self.assertRaises(release.ReleaseError):
                release.parse_request(event, {**env, key: value})
        for key, value in (("sender", {"login": "another-user"}),
                           ("repository", {"full_name": "someone/fork"})):
            changed = deepcopy(event); changed[key] = value
            with self.subTest(field=key), self.assertRaises(release.ReleaseError):
                release.parse_request(changed, env)

    def test_malformed_event_shapes_and_dispatch_fields_reject_explicitly(self):
        event, env = request_data()
        malformed = [None, [], {**event, "sender": None}, {**event, "repository": []},
                     {**event, "inputs": None}]
        for value in malformed:
            with self.subTest(value=value), self.assertRaises(release.ReleaseError):
                release.parse_request(value, env)
        for key, values in {"release_action": ("merge", [], None),
                            "release_pr": ("0", "022", "-1", "123456789", 22),
                            "release_head": ("A" * 40, "a" * 39, "a" * 41, None, []),
                            "release_policy_digest": (None, []),
                            "release_confirmation": (None, [])}.items():
            for value in values:
                changed = deepcopy(event); changed["inputs"][key] = value
                with self.subTest(field=key, value=value), self.assertRaises(release.ReleaseError):
                    release.parse_request(changed, env)

    def test_execution_sha_is_exact_and_distinct_from_the_candidate(self):
        event, env = request_data()
        for value in (HEAD, "b" * 39, "B" * 40, "", None):
            with self.subTest(value=value), self.assertRaises(release.ReleaseError):
                release.parse_request(event, {**env, "GITHUB_SHA": value})
        self.assertEqual(release.parse_request(event, env).head, HEAD)

    def test_landing_requires_exact_confirmation_digest_and_first_attempt(self):
        event, env = request_data("land")
        self.assertEqual(release.parse_request(event, env), release.Request("land", PR, HEAD, DIGEST))
        for value in ("", "approve", release.confirmation(PR + 1, HEAD),
                      release.confirmation(PR, EXECUTION), release.confirmation(PR, HEAD) + " "):
            changed = deepcopy(event); changed["inputs"]["release_confirmation"] = value
            with self.subTest(confirmation=value), self.assertRaises(release.ReleaseError):
                release.parse_request(changed, env)
        for value in ("", "e" * 63, "E" * 64, None):
            changed = deepcopy(event); changed["inputs"]["release_policy_digest"] = value
            with self.subTest(digest=value), self.assertRaises(release.ReleaseError):
                release.parse_request(changed, env)
        for attempt in ("2", "0", "", None):
            with self.subTest(attempt=attempt), self.assertRaises(release.ReleaseError):
                release.parse_request(event, {**env, "GITHUB_RUN_ATTEMPT": attempt})

    def test_planning_cannot_carry_a_confirmation_or_digest(self):
        event, env = request_data()
        for key, value in (("release_confirmation", release.confirmation(PR, HEAD)),
                           ("release_policy_digest", DIGEST)):
            changed = deepcopy(event); changed["inputs"][key] = value
            with self.subTest(field=key), self.assertRaises(release.ReleaseError):
                release.parse_request(changed, env)

    def test_checkout_requires_the_single_exact_parent_and_identical_tree(self):
        request = release.Request("plan", PR, HEAD, "")
        release.verify_checkout(request, EXECUTION, [HEAD], TREE, TREE, EXECUTION)
        bad = [(HEAD, [HEAD], TREE, TREE, EXECUTION),
               (EXECUTION, [], TREE, TREE, EXECUTION),
               (EXECUTION, [HEAD, HEAD], TREE, TREE, EXECUTION),
               (EXECUTION, [MERGE], TREE, TREE, EXECUTION),
               (EXECUTION, [HEAD], TREE, MERGE, EXECUTION),
               (EXECUTION, [HEAD], "not-a-tree", "not-a-tree", EXECUTION),
               (EXECUTION, [HEAD], None, None, EXECUTION)]
        for values in bad:
            with self.subTest(values=values), self.assertRaises(release.ReleaseError):
                release.verify_checkout(request, *values)

    def test_target_pr_cannot_change_head_fork_base_or_identity(self):
        request = release.Request("plan", PR, HEAD, "")
        release.verify_pr(request, pr_data())
        for path, value in (("number", PR + 1), ("number", float(PR)), ("state", "closed"),
                            ("merged", True), ("head.sha", EXECUTION),
                            ("head.repo.full_name", "someone/fork"),
                            ("base.repo.full_name", "someone/fork"), ("base.ref", "other"),
                            ("head", None)):
            body = pr_data(); target = body; parts = path.split(".")
            for key in parts[:-1]: target = target[key]
            target[parts[-1]] = value
            with self.subTest(field=path, value=value), self.assertRaises(release.ReleaseError):
                release.verify_pr(request, body)

    def test_canonical_plan_must_bind_exact_identity_all_checks_and_merge_method(self):
        request = release.Request("plan", PR, HEAD, "")
        release.verify_plan(request, plan_data())
        for path, value in (("state", "ready"), ("requiresConfirmation", 1),
                            ("repository", "someone/fork"), ("headSha", EXECUTION),
                            ("pr.number", PR + 1), ("pr.number", float(PR)),
                            ("mode", "queue"), ("method", "squash"),
                            ("readinessPolicy.checkPolicy", "required"),
                            ("readinessPolicyDigest", "e" * 63),
                            ("readinessPolicyDigest", None), ("readinessPolicy", [])):
            body = plan_data(); target = body; parts = path.split(".")
            for key in parts[:-1]: target = target[key]
            target[parts[-1]] = value
            with self.subTest(field=path, value=value), self.assertRaises(release.ReleaseError):
                release.verify_plan(request, body)


class ShippedHelperPinsTests(unittest.TestCase):
    def test_shipped_helpers_keep_the_reviewed_exact_source_bytes(self):
        expected = {"pr_land.py": "b2f4b23b35689e4dd7e03286f643e9f5c307ac763b507382a9357c9a0fe12f5f",
                    "pr_watch.py": "e6052992fb8d7b853e2401cc11ffec9a9052975e672fc5174629e415dec3f415"}
        self.assertEqual(PINNED_HELPERS, expected)
        for name, digest in expected.items():
            with self.subTest(helper=name):
                self.assertEqual(hashlib.sha256((ROOT / "tools/pr_completion" / name).read_bytes()).hexdigest(), digest)


class ReleaseExecutionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="nml-release-wrapper-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        helpers = self.root / "tools/pr_completion"; helpers.mkdir(parents=True)
        pins = {}
        for name in PINNED_HELPERS:
            content = ("synthetic helper fixture, never executed: " + name).encode()
            (helpers / name).write_bytes(content)
            pins[name] = hashlib.sha256(content).hexdigest()
        self.enterContext(patch.object(release, "HELPERS", pins))
        self.output = self.root / "output"; self.output.mkdir()
        self.event, self.env = request_data()
        self.calls = []; self.api_reads = 0
        self.readiness = {"state": "ready"}
        self.plan = plan_data()
        self.requested = {"state": "landing_requested", "requestedAt": "2026-10-24T00:00:00Z"}
        self.merged = {"state": "merged"}
        self.final_pr = pr_data(merged=True)
        self.main_ref = {"object": {"sha": MERGE}}
        self.main_relationship = "ahead"
        self.dispatch_error = False
        self.enterContext(patch.object(release, "_run", side_effect=self.run_command))
        self.enterContext(patch.object(release, "_json", side_effect=self.json_command))

    def run_command(self, args, root, destination=None):
        self.calls.append(("run", list(args)))
        if args == ["git", "rev-parse", "HEAD"]: return EXECUTION
        if args == ["git", "show", "-s", "--format=%P", "HEAD"]: return HEAD
        if args in (["git", "rev-parse", "HEAD^{tree}"], ["git", "rev-parse", HEAD + "^{tree}"]): return TREE
        if args[:2] == ["gh", "api"] and "/compare/" in args[2]: return self.main_relationship
        if args == ["gh", "workflow", "run", "pages.yml", "--repo", release.REPOSITORY, "--ref", "main"]:
            if self.dispatch_error: raise release.ReleaseError("Synthetic Pages dispatch failure")
            return ""
        raise AssertionError("Unexpected external command in synthetic release test: " + repr(args))

    def json_command(self, args, root, destination=None):
        self.calls.append(("json", list(args)))
        if args == ["gh", "api", f"repos/{release.REPOSITORY}/pulls/{PR}"]:
            self.api_reads += 1
            value = pr_data() if self.api_reads == 1 else self.final_pr
        elif args == ["gh", "api", f"repos/{release.REPOSITORY}/git/ref/heads/main"]:
            value = self.main_ref
        elif len(args) > 1 and Path(args[1]).name == "pr_watch.py":
            value = self.merged if "--await-merge" in args else self.readiness
        elif len(args) > 1 and Path(args[1]).name == "pr_land.py":
            value = self.requested if "--confirm" in args else self.plan
        else:
            raise AssertionError("Unexpected JSON command in synthetic release test: " + repr(args))
        if destination is not None: destination.write_text(json.dumps(value))
        return deepcopy(value)

    def execute(self, action="plan"):
        self.event, self.env = request_data(action)
        return release.execute(self.root, self.event, self.env, self.output)

    def dispatches(self):
        return [args for _, args in self.calls if args[:3] == ["gh", "workflow", "run"]]

    def confirmations(self):
        return [args for _, args in self.calls if "--confirm" in args]

    def test_plan_only_uses_read_only_helpers_and_never_confirms_or_dispatches(self):
        result = self.execute()
        self.assertEqual(result["state"], "confirmation_required")
        self.assertFalse(result["merge_verified"])
        self.assertFalse(result["deployment_requested"])
        self.assertEqual(result["head"], HEAD)
        self.assertEqual(result["execution_commit"], EXECUTION)
        self.assertEqual(self.confirmations(), [])
        self.assertEqual(self.dispatches(), [])
        for _, args in self.calls:
            self.assertNotIn("--admin", args)
            self.assertFalse(args[:3] == ["gh", "pr", "merge"])
        landing = [args for _, args in self.calls if len(args) > 1 and Path(args[1]).name == "pr_land.py"]
        self.assertEqual(len(landing), 1)
        self.assertEqual(landing[0][landing[0].index("--head") + 1], HEAD)
        self.assertEqual(landing[0][landing[0].index("--method") + 1], "merge")

    def test_changed_helper_bytes_stop_before_any_external_command(self):
        (self.root / "tools/pr_completion/pr_land.py").write_bytes(b"changed helper")
        with self.assertRaisesRegex(release.ReleaseError, "Shipped helper bytes changed"):
            self.execute("land")
        self.assertEqual(self.calls, [])

    def test_changed_plan_digest_stops_before_confirmation(self):
        self.plan["readinessPolicyDigest"] = "f" * 64
        with self.assertRaisesRegex(release.ReleaseError, "policy changed"):
            self.execute("land")
        self.assertEqual(self.confirmations(), [])
        self.assertEqual(self.dispatches(), [])

    def test_nonready_or_noncanonical_plan_never_requests_landing(self):
        for state in ("pending", "blocked", "actionable"):
            self.readiness = {"state": state}; self.calls.clear(); self.api_reads = 0
            with self.subTest(state=state), self.assertRaises(release.ReleaseError):
                self.execute("land")
            self.assertEqual(self.confirmations(), [])
            self.assertEqual(self.dispatches(), [])
        self.readiness = {"state": "ready"}; self.api_reads = 0
        self.plan["readinessPolicy"]["checkPolicy"] = "required"
        with self.assertRaisesRegex(release.ReleaseError, "all-check"):
            self.execute("land")
        self.assertEqual(self.confirmations(), [])

    def test_exact_head_land_uses_only_pinned_helper_then_exact_watcher_and_pages(self):
        result = self.execute("land")
        confirmed = self.confirmations()
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(Path(confirmed[0][1]), self.root / "tools/pr_completion/pr_land.py")
        self.assertEqual(confirmed[0][confirmed[0].index("--head") + 1], HEAD)
        self.assertEqual(confirmed[0][confirmed[0].index("--policy-digest") + 1], DIGEST)
        awaited = [args for _, args in self.calls if "--await-merge" in args]
        self.assertEqual(len(awaited), 1)
        self.assertEqual(Path(awaited[0][1]), self.root / "tools/pr_completion/pr_watch.py")
        self.assertEqual(awaited[0][awaited[0].index("--await-merge") + 1], HEAD)
        self.assertEqual(awaited[0][awaited[0].index("--await-merge-since") + 1], self.requested["requestedAt"])
        self.assertEqual(len(self.dispatches()), 1)
        commands = [args for _, args in self.calls]
        self.assertLess(commands.index(confirmed[0]), commands.index(awaited[0]))
        self.assertLess(commands.index(awaited[0]), commands.index(self.dispatches()[0]))
        self.assertTrue(result["merge_verified"])
        self.assertEqual(result["merge_commit"], MERGE)
        self.assertTrue(result["deployment_requested"])
        self.assertFalse(result["deployment_verified"])
        self.assertTrue(json.loads((self.output / "receipt.json").read_text())["merge_verified"])

    def test_unacknowledged_or_unproven_merge_cannot_dispatch_pages(self):
        for requested in ({"state": "ready"}, {"state": "landing_requested"}):
            self.requested = requested; self.calls.clear(); self.api_reads = 0
            with self.subTest(requested=requested), self.assertRaises(release.ReleaseError):
                self.execute("land")
            self.assertEqual(self.dispatches(), [])
        self.requested = {"state": "landing_requested", "requestedAt": "2026-10-24T00:00:00Z"}
        for state in ("pending", "awaiting_merge", "blocked", "timeout"):
            self.merged = {"state": state}; self.calls.clear(); self.api_reads = 0
            with self.subTest(merge_state=state), self.assertRaises(release.ReleaseError):
                self.execute("land")
            self.assertEqual(self.dispatches(), [])

    def test_wrong_final_head_or_missing_merge_commit_cannot_dispatch(self):
        for field, value in (("merged", False), ("merge_commit_sha", None), ("head", {"sha": EXECUTION})):
            self.final_pr = pr_data(merged=True); self.final_pr[field] = value
            self.calls.clear(); self.api_reads = 0
            with self.subTest(field=field), self.assertRaises(release.ReleaseError):
                self.execute("land")
            self.assertEqual(self.dispatches(), [])

    def test_newer_main_must_provably_retain_the_approved_merge_before_dispatch(self):
        newer_main = "f" * 40
        self.main_ref = {"object": {"sha": newer_main}}
        result = self.execute("land")
        self.assertEqual(result["publication_main_commit_observed"], newer_main)
        comparisons = [args for _, args in self.calls if args[:2] == ["gh", "api"] and "/compare/" in args[2]]
        self.assertEqual(comparisons, [["gh", "api", f"repos/{release.REPOSITORY}/compare/{MERGE}...{newer_main}", "--jq", ".status"]])
        self.assertEqual(len(self.dispatches()), 1)
        for relationship in ("behind", "diverged", "unknown"):
            self.main_relationship = relationship; self.calls.clear(); self.api_reads = 0
            with self.subTest(relationship=relationship), self.assertRaisesRegex(release.ReleaseError, "retain the verified merge"):
                self.execute("land")
            self.assertEqual(self.dispatches(), [])
            self.assertTrue(json.loads((self.output / "receipt.json").read_text())["merge_verified"])

    def test_missing_main_identity_preserves_merge_without_dispatch(self):
        self.main_ref = {"object": {"sha": None}}
        with self.assertRaisesRegex(release.ReleaseError, "main identity"):
            self.execute("land")
        self.assertEqual(self.dispatches(), [])
        self.assertTrue(json.loads((self.output / "receipt.json").read_text())["merge_verified"])

    def test_main_preserves_verified_merge_receipt_when_pages_request_fails(self):
        self.event, self.env = request_data("land")
        event_path = self.root / "event.json"; event_path.write_text(json.dumps(self.event))
        self.env.update(RUNNER_TEMP=str(self.root / "runtime"), GITHUB_EVENT_PATH=str(event_path))
        self.dispatch_error = True
        stdout = io.StringIO()
        with patch.dict(os.environ, self.env, clear=True), \
             patch.object(release, "__file__", str(self.root / "scripts/github_release.py")), \
             redirect_stdout(stdout):
            code = release.main()
        self.assertEqual(code, 20)
        result = json.loads((self.root / "runtime/nml-guarded-release/receipt.json").read_text())
        self.assertEqual(result["state"], "blocked")
        self.assertTrue(result["merge_verified"])
        self.assertEqual(result["merge_commit"], MERGE)
        self.assertEqual(result["head"], HEAD)
        self.assertFalse(result["deployment_requested"])
        self.assertFalse(result["deployment_verified"])
        self.assertEqual(result["deployment_request_state"], "INTENT_RETAINED")
        self.assertEqual(result["publication_main_commit_observed"], MERGE)
        self.assertIn("Synthetic Pages dispatch failure", result["error"])


class BoundedCommandReceiptTests(unittest.TestCase):
    def test_output_bounds_and_failure_messages_do_not_disclose_command_stderr(self):
        oversized = subprocess.CompletedProcess([], 0, stdout="é" * 9, stderr="")
        with patch.object(release, "MAX_RECEIPT_BYTES", 16), \
             patch.object(release.subprocess, "run", return_value=oversized), \
             self.assertRaisesRegex(release.ReleaseError, "bounded receipt limit"):
            release._run(["synthetic-command"], ROOT)
        failed = subprocess.CompletedProcess([], 9, stdout="", stderr="never-disclose-this-synthetic-value")
        with patch.object(release.subprocess, "run", return_value=failed), \
             self.assertRaises(release.ReleaseError) as caught:
            release._run(["synthetic-command"], ROOT)
        self.assertNotIn("never-disclose", str(caught.exception))

    def test_nonobject_command_receipt_cannot_be_admitted(self):
        with patch.object(release, "_run", return_value="[]"), \
             self.assertRaisesRegex(release.ReleaseError, "non-object"):
            release._json(["synthetic-command"], ROOT)


if __name__ == "__main__":
    unittest.main()

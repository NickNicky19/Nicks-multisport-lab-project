#!/usr/bin/env python3
"""Run the unchanged PR Completion helpers on a GitHub-hosted runner.

This wrapper never implements a merge command. Only the pinned pr_land.py may
request one. An identical-tree child ref keeps the runner's own pending check
off the candidate commit, without excluding any candidate check.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY = "NickNicky19/Nicks-multisport-lab-project"
OWNER = "NickNicky19"
HELPERS = {
    "pr_land.py": "b2f4b23b35689e4dd7e03286f643e9f5c307ac763b507382a9357c9a0fe12f5f",
    "pr_watch.py": "e6052992fb8d7b853e2401cc11ffec9a9052975e672fc5174629e415dec3f415",
}
MAX_RECEIPT_BYTES = 2 * 1024 * 1024
PUSH_ENVELOPE = "NML_GUARDED_RELEASE_V1\n"


class ReleaseError(RuntimeError):
    """An explicit fail-closed identity, approval or release-gate failure."""


@dataclass(frozen=True)
class Request:
    action: str
    pr: int
    head: str
    policy_digest: str


def confirmation(pr: int, head: str) -> str:
    return f"APPROVE PR {pr} HEAD {head} MERGE AND DEPLOY"


def _object(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def parse_request(event: dict, env: dict[str, str]) -> Request:
    event = _object(event)
    if (env.get("GITHUB_ACTIONS") != "true"
            or env.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or env.get("GITHUB_EVENT_NAME") not in {"workflow_dispatch", "push"}
            or env.get("GITHUB_REPOSITORY") != REPOSITORY
            or env.get("GITHUB_ACTOR") != OWNER
            or _object(event.get("sender")).get("login") != OWNER
            or _object(event.get("repository")).get("full_name") != REPOSITORY):
        raise ReleaseError("Requires an owner-authorized run in this repository on a GitHub-hosted runner")
    if env["GITHUB_EVENT_NAME"] == "push":
        commit = _object(event.get("head_commit"))
        if (event.get("forced") is not False or event.get("deleted") is not False
                or event.get("ref") != env.get("GITHUB_REF")
                or event.get("after") != env.get("GITHUB_SHA")
                or commit.get("id") != env.get("GITHUB_SHA")):
            raise ReleaseError("Push event is not an ordinary exact-ref/exact-commit owner update")
        message = commit.get("message")
        if not isinstance(message, str) or not message.startswith(PUSH_ENVELOPE):
            raise ReleaseError("Missing versioned release-intent commit envelope")
        def unique_fields(pairs: list[tuple[str, object]]) -> dict:
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ReleaseError("Duplicate release-intent field")
                result[key] = value
            return result
        try:
            inputs = json.loads(message[len(PUSH_ENVELOPE):], object_pairs_hook=unique_fields)
        except (ValueError, TypeError) as error:
            raise ReleaseError("Invalid release-intent JSON") from error
        expected = {"release_action", "release_pr", "release_head",
                    "release_policy_digest", "release_confirmation"}
        if not isinstance(inputs, dict) or set(inputs) != expected:
            raise ReleaseError("Release-intent envelope has missing or unknown fields")
    else:
        inputs = event.get("inputs", {})
    if not isinstance(inputs, dict):
        raise ReleaseError("Missing workflow-dispatch inputs")
    action = inputs.get("release_action")
    pr_text = inputs.get("release_pr", "")
    head = inputs.get("release_head", "")
    digest = inputs.get("release_policy_digest", "")
    approved = inputs.get("release_confirmation", "")
    if (not isinstance(action, str) or action not in {"plan", "land"} or not isinstance(pr_text, str)
            or not re.fullmatch(r"[1-9][0-9]{0,7}", pr_text)
            or not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40}", head)):
        raise ReleaseError("Invalid release action, PR number or exact head")
    if not isinstance(digest, str) or not isinstance(approved, str):
        raise ReleaseError("Readiness digest and confirmation must be explicit strings")
    pr = int(pr_text)
    expected_ref = f"refs/heads/execution/guarded-pr-{pr}-{head}" + ("-land" if action == "land" else "")
    if (env.get("GITHUB_REF") != expected_ref
            or env.get("GITHUB_WORKFLOW_REF") != f"{REPOSITORY}/.github/workflows/pages.yml@{expected_ref}"):
        raise ReleaseError("Execution ref or workflow identity differs from the candidate-bound release ref")
    if (not isinstance(env.get("GITHUB_SHA"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", env["GITHUB_SHA"])):
        raise ReleaseError("Missing exact execution commit")
    if env["GITHUB_SHA"] == head:
        raise ReleaseError("Run must not attach its own pending check to the candidate commit")
    if action == "plan":
        if digest or approved:
            raise ReleaseError("Read-only planning cannot carry a landing confirmation")
    elif (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or approved != confirmation(pr, head) or env.get("GITHUB_RUN_ATTEMPT") != "1"):
        raise ReleaseError("Landing requires the exact-head confirmation and plan digest; do not rerun a landing job")
    return Request(action, pr, head, digest)


def verify_checkout(request: Request, actual_head: str, parents: list[str],
                    actual_tree: str, candidate_tree: str, execution_sha: str) -> None:
    if (actual_head != execution_sha or parents != [request.head] or not isinstance(actual_tree, str)
            or actual_tree != candidate_tree or not re.fullmatch(r"[0-9a-f]{40}", actual_tree)):
        raise ReleaseError("Execution must be an identical-tree commit with the exact candidate as its sole parent")


def verify_pr(request: Request, pr: dict) -> None:
    pr = _object(pr)
    head, base = _object(pr.get("head")), _object(pr.get("base"))
    if (type(pr.get("number")) is not int or pr.get("number") != request.pr
            or pr.get("state") != "open" or pr.get("merged")
            or head.get("sha") != request.head
            or _object(head.get("repo")).get("full_name") != REPOSITORY
            or _object(base.get("repo")).get("full_name") != REPOSITORY
            or base.get("ref") != "main"):
        raise ReleaseError("Pull request identity/head/base changed; obtain a fresh exact-head decision")


def verify_plan(request: Request, plan: dict) -> None:
    plan = _object(plan)
    if (plan.get("state") != "confirmation_required" or plan.get("requiresConfirmation") is not True
            or plan.get("repository") != REPOSITORY or plan.get("headSha") != request.head
            or type(_object(plan.get("pr")).get("number")) is not int
            or _object(plan.get("pr")).get("number") != request.pr
            or plan.get("mode") != "auto" or plan.get("method") != "merge"
            or _object(plan.get("readinessPolicy")).get("checkPolicy") != "all"
            or not isinstance(plan.get("readinessPolicyDigest"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", plan["readinessPolicyDigest"])):
        raise ReleaseError("Canonical plan is not a current all-check, exact-head merge-commit plan")


def _run(args: list[str], root: Path, destination: Path | None = None) -> str:
    result = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=1200, check=False)
    if len(result.stdout.encode()) > MAX_RECEIPT_BYTES or len(result.stderr.encode()) > MAX_RECEIPT_BYTES:
        raise ReleaseError("Release command output exceeds the bounded receipt limit")
    if destination is not None:
        destination.write_text(result.stdout)
        destination.with_suffix(".stderr").write_text(result.stderr)
    if result.returncode:
        # Raw CI logs and environment contents are never collected here.
        raise ReleaseError(f"{Path(args[0]).name} release command failed ({result.returncode}); inspect its retained receipt")
    return result.stdout.strip()


def _json(args: list[str], root: Path, destination: Path | None = None) -> dict:
    value = json.loads(_run(args, root, destination))
    if not isinstance(value, dict):
        raise ReleaseError("Release command returned a non-object receipt")
    return value


def execute(root: Path, event: dict, env: dict[str, str], output: Path) -> dict:
    request = parse_request(event, env)
    helper_root = root / "tools/pr_completion"
    for name, digest in HELPERS.items():
        if hashlib.sha256((helper_root / name).read_bytes()).hexdigest() != digest:
            raise ReleaseError(f"Shipped helper bytes changed: {name}")
    actual_head = _run(["git", "rev-parse", "HEAD"], root)
    parents = _run(["git", "show", "-s", "--format=%P", "HEAD"], root).split()
    tree = _run(["git", "rev-parse", "HEAD^{tree}"], root)
    candidate_tree = _run(["git", "rev-parse", f"{request.head}^{{tree}}"], root)
    verify_checkout(request, actual_head, parents, tree, candidate_tree, env["GITHUB_SHA"])
    pr = _json(["gh", "api", f"repos/{REPOSITORY}/pulls/{request.pr}"], root)
    verify_pr(request, pr)
    watcher = [sys.executable, str(helper_root / "pr_watch.py"),
               "--target", f"{root}={request.pr}", "--mode", "until-actionable",
               "--timeout", "120", "--max-errors", "1",
               "--cursor", str(output / "cursor.json"),
               "--observations-file", str(output / "observations.ndjson")]
    snapshot = _json(watcher, root, output / "readiness.json")
    if snapshot.get("state") != "ready":
        raise ReleaseError(f"Readiness gate returned {snapshot.get('state')}")
    landing = [sys.executable, str(helper_root / "pr_land.py"),
               "--repo", str(root), "--pr", str(request.pr), "--head", request.head,
               "--mode", "auto", "--method", "merge"]
    plan = _json(landing, root, output / "plan.json")
    verify_plan(request, plan)
    receipt = {"schema_version": "github-guarded-release-v1", "action": request.action,
               "pr": request.pr, "head": request.head, "execution_commit": actual_head,
               "readiness_policy_digest": plan["readinessPolicyDigest"],
               "canonical_plan": plan,
               "helper_hashes": HELPERS, "state": "confirmation_required",
               "merge_verified": False, "deployment_requested": False, "deployment_verified": False}
    if request.action == "plan":
        return receipt
    if request.policy_digest != plan["readinessPolicyDigest"]:
        raise ReleaseError("Readiness policy changed after the approved plan")
    requested = _json(landing + ["--policy-digest", request.policy_digest, "--confirm"],
                      root, output / "landing-request.json")
    if requested.get("state") != "landing_requested" or not requested.get("requestedAt"):
        raise ReleaseError("The prescribed helper did not acknowledge a landing request")
    merged = _json(watcher + ["--await-merge", request.head, "--await-merge-mode", "auto",
                             "--await-merge-since", requested["requestedAt"]],
                   root, output / "merge-observation.json")
    if merged.get("state") != "merged":
        raise ReleaseError("Landing was requested but exact-head merging was not verified")
    current_pr = _json(["gh", "api", f"repos/{REPOSITORY}/pulls/{request.pr}"], root)
    if (current_pr.get("merged") is not True or _object(current_pr.get("head")).get("sha") != request.head
            or not isinstance(current_pr.get("merge_commit_sha"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", current_pr["merge_commit_sha"])):
        raise ReleaseError("Merged PR readback does not match the approved head")
    receipt.update(state="merged", merge_verified=True, merge_commit=current_pr["merge_commit_sha"],
                   landing_requested_at=requested["requestedAt"])
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    main_ref = _json(["gh", "api", f"repos/{REPOSITORY}/git/ref/heads/main"], root)
    main_sha = _object(main_ref.get("object")).get("sha")
    if not isinstance(main_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", main_sha):
        raise ReleaseError("Current main identity is unavailable after the verified merge")
    if main_sha != receipt["merge_commit"]:
        relation = _run(["gh", "api", f"repos/{REPOSITORY}/compare/{receipt['merge_commit']}...{main_sha}",
                         "--jq", ".status"], root)
        if relation not in {"ahead", "identical"}:
            raise ReleaseError("Current main does not retain the verified merge; do not dispatch a replacement build")
    receipt.update(publication_main_commit_observed=main_sha,
                   deployment_request_started_at=datetime.now(timezone.utc).isoformat(),
                   deployment_request_state="INTENT_RETAINED")
    # GITHUB_TOKEN merges do not trigger push workflows. Explicitly request the
    # existing main Pages workflow; dispatch acceptance is NOT deployment.
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    _run(["gh", "workflow", "run", "pages.yml", "--repo", REPOSITORY, "--ref", "main"], root)
    receipt["deployment_requested"] = True
    receipt["deployment_request_state"] = "REQUEST_ACKNOWLEDGED"
    return receipt


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    output = Path(os.environ["RUNNER_TEMP"]) / "nml-guarded-release"
    output.mkdir(parents=True, exist_ok=True)
    receipt: dict = {"schema_version": "github-guarded-release-v1", "state": "blocked",
                     "merge_verified": False, "deployment_requested": False, "deployment_verified": False}
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        receipt = execute(root, event, dict(os.environ), output)
        code = 0
    except (ReleaseError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        # Preserve a proven merge if a subsequent deployment request fails.
        original = output / "receipt.json"
        if original.exists():
            receipt = json.loads(original.read_text())
        receipt.update(state="blocked", error=str(error))
        code = 20
    receipt["observed_at"] = datetime.now(timezone.utc).isoformat()
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a") as stream:
            stream.write("## Guarded release result\n\n```json\n" + json.dumps(receipt, indent=2) + "\n```\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

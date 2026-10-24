# GitHub-hosted guarded release

GitHub Actions already runs the project checks, recurring NBA coordinator,
record recovery, statistical grading and Pages publication. The ChatGPT
development workspace is not a production dependency. This manual release
entrypoint moves the existing required PR Completion process to a healthy
GitHub-hosted runner too. It adds no scheduler or forecast producer.

The existing `pages.yml` workflow has three `release_action` values:

- `none` (default): unchanged ordinary checks and main-only site publication.
- `plan`: owner-dispatched, read-only permissions; actual readiness and canonical
  exact-head merge plan from the unchanged shipped helpers.
- `land`: owner-dispatched, exact-head confirmation and canonical policy digest;
  the same helper freshly rechecks all candidate checks/reviews/protections and
  requests a normal merge commit. No override or alternate merge API exists.

Release modes skip the ordinary build, operating diagnostic and deploy jobs.
They make no sports-source requests, generate no forecasts, and do not activate
OPS002, PROS004, S0 or any protected missed pilot. Candidate CI must independently
pass; a plan is neither permission to land nor evidence of deployment.

## Bootstrap and self-check isolation

An Actions run associated with a PR's own commit would see its own pending check
and could not satisfy the unchanged `all` check policy. Do not remove that check
or weaken the policy. Instead, create a new execution commit with the candidate
as its **sole parent and exactly the same tree**, on:

```text
execution/guarded-pr-<PR_NUMBER>-<FULL_CANDIDATE_HEAD_SHA>
```

The wrapper verifies the actual checkout/dispatch SHA, sole parent, equal trees,
repository, owner sender, hosted runner, exact workflow/ref, current target head,
same-repository PR and main base. Its own job is associated with the distinct
execution commit. The candidate's real CI stays visible and required.

Because `pages.yml` already exists on main, its manual dispatch can select that
execution branch before this feature is merged. There is no bootstrap merge,
recurring helper or second PR necessary. Do not mutate an existing execution ref
to substitute a different candidate or tree. Any changed candidate requires a
new execution ref, fresh checks/plan and new exact-head approval.

## Read-only plan

After ordinary candidate CI is green, dispatch existing `pages.yml` with the
execution branch as `ref` and these inputs:

```text
release_action: plan
release_pr: <PR_NUMBER>
release_head: <FULL_CANDIDATE_HEAD_SHA>
```

Keep confirmation and digest empty. The `guarded-release-plan-<run>-<attempt>`
artifact contains bounded readiness, canonical plan and receipt files for 14
days. Job summary distinguishes `confirmation_required` from a merge. This is
release metadata, not an archive of issued forecasts or full CI logs.

## Approved landing and actual publication

Only after explicit per-PR approval of the exact current head and applicable
operating scope, dispatch the same execution ref with:

```text
release_action: land
release_pr: <PR_NUMBER>
release_head: <FULL_CANDIDATE_HEAD_SHA>
release_policy_digest: <readinessPolicyDigest from the actual canonical plan>
release_confirmation: APPROVE PR <PR_NUMBER> HEAD <FULL_CANDIDATE_HEAD_SHA> MERGE AND DEPLOY
```

The owner's click or authorized dispatch is a one-time release action, not a
daily manual forecast requirement. No new token, provider key or phone/computer
uptime is required: jobs use their own scoped `GITHUB_TOKEN`.

The wrapper calls only the pinned `pr_land.py` with `--confirm` and the preserved
digest, then observes the exact approved head merging with `pr_watch.py` and its
original `requestedAt`. No accepted request is labeled merged before readback.
GitHub-token merges do not start push workflows, so a verified merge explicitly
dispatches the existing main `pages.yml`. Dispatch is labeled requested, not
deployed. Verify that new run's actual successful Pages deployment and served
manifest/build/asset hashes before declaring the website updated.
The receipt retains the actual observed main SHA and dispatch-intent time before
the request. If legitimate newer main work exists, it must contain the approved
merge; it is never reset. Main can still advance after that observation: verify
the actual workflow/deployment SHA rather than assuming it equals the merge SHA.
An interrupted acknowledgment remains an unresolved request, not proof that no
run started; inspect the workflow inventory after the retained intent time.

If a job stops after requesting landing, preserve its `landing-request.json`
and original `requestedAt`. Do not rerun a landing job: the wrapper rejects
landing attempts beyond attempt 1. Inspect actual PR state and use the unchanged
watcher's `--await-merge`, `--await-merge-mode auto` and `--await-merge-since` with
that retained timestamp. Pending/blocked state never permits a replacement head,
late forecast, altered policy or emergency merge. A successful merge survives a
later dispatch failure in the receipt; ordinary main publication can then be
reconciled under the existing approved release scope.

## Evidence boundaries

A green hosted plan proves the prescribed checks executed independently of the
ChatGPT workspace. It does not prove timely source capture, genuine issuance,
public forecast delivery, predictive accuracy or completed postgame grading.
Those remain separate actual executions under the production policy, clocks,
source admission and immutable input/forecast/outcome references.

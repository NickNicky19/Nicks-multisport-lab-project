# GitHub-hosted guarded release

GitHub Actions already runs the project checks, recurring NBA coordinator,
record recovery, statistical grading and Pages publication. The ChatGPT
development workspace is not a production dependency. This manual release
entrypoint moves the existing required PR Completion process to a healthy
GitHub-hosted runner too. It adds no scheduler or forecast producer.

The existing `pages.yml` workflow supports manual inputs and owner-pushed,
versioned release-intent envelopes. Both routes have three actions:

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
operating scope, dispatch a separately created identical-tree `-land` execution ref with:

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


## Preferred bootstrap without a development executor

The GitHub connector can create commits/refs even when the ChatGPT executor cannot
start. A normal owner-authorized ref update under
`execution/guarded-pr-*` triggers the same existing workflow. This is an on-demand
release event, not another scheduler. No HTTP dispatch client, new token or
running development workspace is required.

1. Finish candidate CI; preserve its exact reviewed head.
2. Create an execution commit with that candidate as its sole parent and exactly
   the same tree. Its message is the following versioned JSON envelope (all five
   fields are required, values are strings, duplicate/unknown fields reject).
3. Create the unique execution branch at the existing main ancestor, whose older
   workflow does not match execution refs; then fast-forward it to the execution
   commit through the authenticated GitHub connector. Do not create a push-check
   on the candidate itself, force-update, or reuse an execution branch.
4. Verify an actual `push` workflow run at the execution SHA, then its completed
   read-only plan/receipt. Missing runs remain unobserved, not a claimed success.

Read-only plan branch: `execution/guarded-pr-<PR>-<HEAD>`.

```text
NML_GUARDED_RELEASE_V1
{"release_action":"plan","release_pr":"<PR>","release_head":"<HEAD>","release_policy_digest":"","release_confirmation":""}
```

Only AFTER the required explicit exact-head approval, create a DIFFERENT
`execution/guarded-pr-<PR>-<HEAD>-land` ref/identical-tree child with this message:

```text
NML_GUARDED_RELEASE_V1
{"release_action":"land","release_pr":"<PR>","release_head":"<HEAD>","release_policy_digest":"<CANONICAL_DIGEST>","release_confirmation":"APPROVE PR <PR> HEAD <HEAD> MERGE AND DEPLOY"}
```

The wrapper checks GitHub's actual owner sender/actor, event ref/after/head
commit, nonforced/nondeleted state, exact workflow ref and hosted runner, then
the same parent/tree/PR/policy/approval gates. A plan envelope never becomes a
landing approval. The landing helper is still the only merge mutation surface.
All release jobs serialize repository-wide. Ordinary builds/diagnostics/deploys
skip execution refs; the plan job additionally executes the focused synthetic
guards under actual optimized Python. No producer or sports-source client runs.

The manual dispatch route remains available with the same checks and distinct
land ref. Publication dispatch happens on the healthy GitHub runner AFTER an
actual verified merge, not through the development executor.

## Evidence boundaries

A green hosted plan proves the prescribed checks executed independently of the
ChatGPT workspace. It does not prove timely source capture, genuine issuance,
public forecast delivery, predictive accuracy or completed postgame grading.
Those remain separate actual executions under the production policy, clocks,
source admission and immutable input/forecast/outcome references.

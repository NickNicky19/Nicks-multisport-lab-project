# One unattended October 20 NBA pilot

The user's October 19 instruction explicitly authorizes ONE unattended execution
of the existing fixed NBA pilot. It supersedes manual-only/no-scheduling wording
for this cycle only. It does not authorize recurring data collection, another
event/cohort, experiments, future grading, wagers or automatic PR landing.

The reviewed producer stays `58530309cf384425e15f02fd9fa980899a4dc0bc`. The existing
cycle plan, selection and all nine reviewed source files remain unchanged. New
operating code is `scheduled_cycle.py` and `pilot_github.py`, outside those files.

## Host and activation

Use the repository's existing GitHub Actions host, with the built-in GITHUB_TOKEN,
Python/Git/gh and the retained Git records. No personal computer or ChatGPT app
needs to remain running. The repository and Actions must remain enabled; external
source availability and timely GitHub dispatch cannot be guaranteed.

The workflow is `.github/workflows/nba-20261020-pilot.yml`. Its cron is
`15 17 20 10 *`, corresponding to **October 20, 2026 at 12:15 p.m. CDT / 17:15 UTC**.
GitHub cron has no year field or native single-use count. This workflow therefore
requires the actual date to be October 20, 2026 and disables ONLY its own verified
workflow before live work. It verifies the disabled state before source requests;
a failure stops the pilot. The already running job can continue while the workflow
is disabled. It never re-enables itself in live mode. One concurrency group and
an immutable run claim prevent competing writers or a second run from issuing.

A feature-branch workflow is **not an activated schedule**. Activation requires
review and explicit exact-head approval of the setup PR, normal merge to main,
then GitHub API readback of the workflow's active state and the exact default-
branch cron/code. Before confirming activation, reconcile the one records branch
with the exact merged main, preserving both factual handoff histories and
regenerating the manifest. Verify clean source integration/readback; do not leave
a predictable handoff/manifest merge conflict for the time-sensitive worker. No future run ID exists until GitHub queues the run; the workflow
ID is the scheduler registration ID. Report both this distinction and the actual
registered ID/state. Scheduling remains best effort: a delayed runner must obey
the original deadlines and may produce a failed/partial checkpoint.

The native Codex/ChatGPT Automations service accepted entry
`6ad6e46f754c81918f190eff2fdc248c`, but its immediate read-only diagnostic endpoint
returned HTTP 404 before invocation. That entry is confirmed **paused** and must
remain paused; it is not a second executor. Its saved schedule is not proof of a
working repository executor. An earlier immediate test containing the future
mutation instructions was rejected by automatic approval review; no pilot ran.
The restricted read-only alternative was not executed because of the missing
endpoint. GitHub runner verification is separate evidence.

## Exactly bounded phases

| Phase | America/Chicago (CDT) | UTC, October 20 |
| --- | --- | --- |
| Worker preparation | approximately 12:15 p.m. | approximately 17:15 |
| Capture, normalize, input persist and bind | 12:20–12:30 p.m. | 17:20–17:30 |
| Generate, verify and original forecast persist | 12:30–12:35 p.m. | 17:30–17:35 |

The worker checks the actual clock before every phase, waits in intervals no
longer than 30 seconds only during this short preparation period, and retains
all original timing/latency gates. The early preparation input supplies history
only. Fresh event/player facts must pass the unchanged source normalizer and
fixed-cohort guard. A changed event/version/team/player, blocked source or missed
window causes an actual failure/partial state; it never changes the plan or clock.

## Runner preflight now

Before activation, the same workflow's safe PR/manual-dispatch mode verifies:

- the nine producer files against the pinned commit, all 19 original records and
  complete 26,645-row history;
- actual runner access to the four existing ESPN routes: NBA scoreboard for
  20261020, event 401909088 summary, and team 8/team 2 rosters;
- normal push to the one records branch and independent exact remote readback;
- disable/readback/re-enable of ONLY this workflow in preflight mode;
- draft records-PR creation and validation-workflow dispatch without merging.

A probe batch makes at most four read-only GETs, each at most 2 MiB/30 seconds.
A completed batch is reused on ordinary CI reruns. Durable probe-start slots
limit interrupted setup retries to three batches total (at most 12 requests).
The actual pilot is a separate single four-request capture attempt in its window.
A source probe proves route reachability/status/hash/clock, not semantic roster
normalization or timely availability. It cannot become the pilot input. Upstream
update clocks stay unknown when absent. No raw response bodies are published.

The built-in token requests contents/pull-requests/actions write permissions only
for this workflow's job. If GitHub refuses PR creation, retain the body and compare
URL and report the actual error. The owner setting, if required, is Settings →
Actions → General → Workflow permissions → Allow GitHub Actions to create and
approve pull requests. Do not modify that setting or introduce a new credential
silently. Failure to create a PR must not erase remotely preserved pilot records.

The first actual hosted test received that creation-only HTTP 403. The existing
authorized integration session has therefore precreated ONE readiness-only draft
PR #8 from the fixed records branch. Test the runner's update of this existing
draft before activation; do not assume creation and update have the same policy.
Keep that draft open through the cycle. Record the actual operation as
UPDATED_EXISTING, separately from who originally created it. A verified update
path does not require enabling broader repository PR creation. If the draft is
closed/deleted, retain the actual failure/body/compare URL and records; never
introduce another credential. Explicit branch validation proceeds even if PR
creation/update is blocked. The records PR itself does not run another setup job.

Actual corrected run 39368941819 passed the existing-draft update and explicit
Pages branch validation 39369096848. The earlier owner-setting request is therefore
superseded; keep PR #8 open. A temporary managed-shell HTTP401 interruption recovered without a credential
change; the already connected app preserved the final feature tree meanwhile.
The app is not an alternative merge mechanism. Run the canonical watcher/landing
plan, obtain exact-head approval and verify main/records integration before
calling the cron active. No owner setting change or new key is required, and no
computer/app must run once GitHub Actions is actually armed.

## One state and interruption recovery

All work uses `records/nba-20261020-401909088-t90`. Its Git history includes the
reviewed implementation and deployment handoff. Existing legitimate branch work
is retained through ordinary fetch/merge; no reset or force push is allowed.
An immutable claim binds the actual GitHub run ID, cycle, workflow and producer.
A different run cannot take over. A rerun of the same logical run may recover,
but it never resets timing, source inputs or an original record.

The wrapper calls the existing guarded `manual_cycle` path. Its synchronous
operating hooks add remote journaling; they do not change the underlying source
normalization, probability formula, coherent stat outcomes or ledger validation:

1. A remotely acknowledged CAPTURE_STARTED intent precedes source requests.
2. The exact new input and create-only binding are committed/pushed/read back
   before generation starts.
3. A remotely acknowledged GENERATION_STARTED intent precedes each subject's
   unchanged producer call.
4. Each original forecast is committed/pushed/read back before the next subject.

Intent identities include the exact run/cycle, producer, bound input and subject.
Existing retained originals are recovered without generation. If an intent exists
but the original was lost with the worker, its state is **ambiguous**, and the
worker must stop rather than silently regenerate it. A retained local complete
source pack can be recovered unchanged; an acknowledged capture intent without
that pack or a binding cannot trigger another source attempt. Git push/readback
failure stops further generation. Finalization retries preserving exact local
originals, never reruns the model to make replacement records.

Valid late normalized inputs may be retained as explicitly rejected standalone
research inputs with their actual late clocks; they cannot bind or issue. Partial
source attempts retain safe capture metadata (URLs, hashes and actual clocks),
not raw provider bodies. The original 19 records, frozen experiments and previous
source clocks remain unchanged.

Commit/push and independent GitHub recovery are the primary durable record.
A 14-day Actions artifact containing normalized records and safe evidence is
emergency recovery only. It excludes raw `.local-data` responses and is not the
sole issuance store. A hard interruption can leave an ambiguous failed/partial
cycle; it must be reported accurately rather than replaced.

## Publication and sole-writer rule

Software/export checks run after the time-sensitive phases. The worker prepares
or updates ONE factual records PR; preflight leaves it draft and labels zero
issued forecasts accurately. A GITHUB_TOKEN push/PR event does not automatically
trigger ordinary downstream CI, so the worker explicitly dispatches the existing
Pages validation workflow for the exact records branch. That branch run cannot
deploy Pages. Any merge/deployment requires the existing separate per-PR exact-
head approval after records are safely remote.

Do not run manual capture/issuance while the scheduled workflow is armed, queued,
running or holding its claim. A disabled workflow may still have an active job.
Manual takeover requires disarming/cancelling, verifying there is no live writer,
and recovering the same branch/input/originals before any further action.
After a scheduled claim/intent, the older standalone manual_cycle recovery report
is diagnostic only: it does not clear pending transaction intents. Live recovery
must use the outer intent-aware runner under the original claim; an ambiguous
missing original stays blocked. Never use bare manual issue to bypass that state.
Read-only inspection is safe. No second worker, reminder automation or collector
should be installed for this cycle.

Outcomes remain pending until verified final evidence is available in a separate
later operation. No financial settlement, qualified ticket, predictive qualification,
K0 promotion or PROS004 activation follows from scheduling or timely issuance.

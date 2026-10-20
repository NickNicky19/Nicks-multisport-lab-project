# Implementation handoff status

Updated: October 20, 2026 (UTC).

## October 20, 20:07 UTC — completion fixes verified; full-history timing failed safely

Exact implementation source commit: `c18809f2fc7752d8f48c4749024623f5f4d73eb6`
on `implementation/pros004-paired-readiness`, draft PR #10. Source bindings cover
19 producer dependencies and the diagnostic adds its driver as the 20th pin.
Independent fresh GitHub recovery verified those exact bytes, all nine frozen
pilot files, unchanged R0/K0 laws/protocol and all original 19 receipts. Main
remains `735a464e9e8718303ef481abf711a8969de56694`; the pilot records branch/PR #8
remain `df446eee302fd6662ef82184e2c733f5d6e2d2dd`. PROS004/S0 remain inactive.

The persistence fixes preserve pre-write `received_at`, observe actual post-write
completion, require exact structured remote readback, publish the final original
ACK prefix, and distinguish timing, evidence publication and comparison admission.
Missing generation requires the original strict input-finalization report; its
genuine durable operating-state admission remains unresolved. Typed recovery now
validates every supported contract and relationship. Explicit integrity exceptions
survive optimized Python. The 20-case normal/optimized old/new reproduction receipt
preserves both reviewed c305 defects and the fixed behavior.

Actual final software commands at this source: `python3 -m unittest discover -s
tests -v` **416 PASS / 152.963s**; `python3 -O -m unittest discover -s tests -p
"test_pros004*.py" -v` **138 PASS / 127.721s**; `node --test
--test-isolation=none web/tests/*.test.mjs` **45 PASS**; `python3 -m
multisport_lab.demo` PASS. Earlier source-drift stops during coordinated editing
remain recorded separately. They were followed by these stable-source passes.

Actual GitHub diagnostic writer/readback succeeded at
`8684aed08382d6be6c7e83ff93ee833888608d55` on
`diagnostics/pros004-checkpoint-20261020`: **21 files (20 ledger + 1 journal),
1,820,865 bytes, 25.387s total**, with actual UTC clocks and fresh independent
fetches. The only new record is explicitly synthetic transport status, not an
actual study selection failure. All 19 original receipts remain byte-identical.
No provider request, forecast generation, activation or pilot mutation was involved.

The separate generic high-entropy load retained **499 synthetic receipts /
25,165,824 bytes**, local bare-Git push/fresh-fetch **5.763s**, total **6.666s**.
It verifies transport load, not full typed-study execution or GitHub latency.
The complete conservative study allocation remains **499 + 13 slots / 512**,
**24,576,000 bytes**, under unchanged 32-MiB limits. One 2-MiB journal replaces
one existing metadata slot; no per-forecast record or probability truncation.

The complete retained 26,645-row path ran with explicitly advancing synthetic
clocks and actual local Git checkpoints:

```bash
python3 -m multisport_lab.pros004_readiness \
  --output evidence/research/pros004-readiness-measurement-v2.json \
  --store-root /tmp/nml-pros004-diagnostic-c188 \
  --producer-commit c18809f2fc7752d8f48c4749024623f5f4d73eb6
```

**PARTIAL_OR_FAILED_TIMING**, actual 19:59:09.051962–20:07:01.835522 UTC.
Cohort generation/verification/persistence took **339.438s**; five model generations
used only **29.745s**. Required checkpoint completion crossed the 300-second gate.
Five original diagnostic forecasts survive, four have local timely original
completion proof, and **zero are comparison-eligible**. Three model peers remain
missing. The last ACK journal entry was not published after failure, so exact full
remote-prefix recovery is false; this is not a complete paired cycle. The fetched
prefix/readback retained five originals and explicit missing/unacknowledged state.
Two integrity replays recovered every **26,645** joint atom and all **14** original
category PMFs exactly; no outcomes or comparative scores were used. Local state is
29 files / **3,645,510 bytes**, fetched prefix 3,644,111 bytes, peak RSS **185,396 KiB**.
The create-only failed receipt is preserved unchanged, not replaced by old v1 timing.

Research UI/export implementation and synthetic desktop/mobile checks passed;
no website deployment occurred. No genuine prospective issuance, new real outcome
grading, reserved comparative evaluation, financial settlement or qualified ticket
was produced. Six historical forecast bundles/grades remain their original lane.

Evidence: `evidence/research/pros004-readiness-measurement-v2.json`,
`pros004-transport-load-20261020-v1.json`,
`pros004-actual-github-checkpoint-20261020-v2.json`,
`evidence/verification/pros004-software-checks-v2.json`,
`pros004-independent-review-v2.json`, and the dated completion reproduction.
Detailed new contracts are `docs/PROS004_COMPLETION.md` and
`docs/PROS004_PUBLIC_EXPORT.md`; source files/commands are recoverable from
`git show --stat c18809f2` and the receipts' exact source inventories.

Remaining activation dependencies: complete permitted first UTC-date inventory
(actual first T90 still unknown), source operational admission, private primary raw
outcome retention/permission/full raw budget/linkage, reviewed durable operating
phase-report admission, exact remotely recovered activation evidence, full typed
late-study/hosted timing and sufficient cohort latency. The original reservation
stays inactive and will not shift/backfill if its actual cutoff passes.

Next concrete task already in progress: one bounded content-verified validation
optimization, retaining all independent byte/hash/reference and typed checks,
followed by a new exact source pin and separately named non-issuance timing receipt.
R0/K0 mathematics, gates, capacities and all frozen experiments remain unchanged.

## October 20, 19:29–19:40 UTC — expired pilot audit and PR #10 corrections

This is a new checkpoint; earlier operating observations below remain unchanged.
Review starting point and remote PR #10 head are
`c305a6360c175413b5871170bcb23a1b7f7820ee` on
`implementation/pros004-paired-readiness`. Initial tree was clean; local/remote
branch matched and main remains `735a464e9e8718303ef481abf711a8969de56694`.
PR #10 remains draft. The current package authorizes fixes and inactive operating
preparation, not PROS004 activation, scheduling, genuine issuance, merge or deploy.

**Expired pilot: MISSED_OR_UNOBSERVED_EXECUTION; cause NOT_ESTABLISHED.** Fresh
read-only observations through **19:35:30 UTC** found 72 repository runs and
18 runs for workflow 390126745, with zero schedule-event runs in both inventories.
All 18 workflow runs were earlier PR setup activity; metadata/jobs and six actual
job-log archives were inspected. No execution log establishes a reason for the
unobserved scheduled run. Workflow metadata is still active, with its original
default-branch YAML; that state does not prove execution.

An independent records-branch clone remains clean at
`df446eee302fd6662ef82184e2c733f5d6e2d2dd`; PR #8 is still draft at that exact
head. All **19 original ledger records / 1,817,800 bytes** match the frozen plan.
No execution claim, capture/generation intent, fresh binding or execution report
was observed. The documented read-only `manual_cycle recover` returned closed
window / NOT_READY, no bound input, zero retained selected forecasts and all four
subjects missing. It made zero provider requests and generated zero forecasts.
The native task was observed disabled with no next run at 19:34:17–18 UTC and was
not changed. No dispatch, rerun, workflow-state write, capture, issue or rebind was
performed. Original pilot deadlines/identities and all earlier evidence survive.

Exact queries, response hashes, clocks, inventories and recovery output are in
`evidence/cycles/2026-10-20-pilot-operational-recovery.json` and
`docs/PILOT_OPERATIONAL_DIAGNOSIS.md`. The evidence receipt raw SHA-256 is
`1f0b6a609c3ad057e275c5ada6ffb43a90b134d2818bda7d77fb646925d4a760`.

Separately authorized current metadata inspection made exactly three bounded
ESPN scoreboard requests at **19:32:07.895099–19:32:08.968371 UTC**, receiving
HTTP 200 / 204,880 bytes, with 3/11/2 events in the adjacent routes. Six observed
events start on UTC October 21. All responses lack the registered pagination/count
proof; `UNKNOWN_SCHEDULE_COMPLETENESS` remains a blocker. The actual first T90 is
**unknown**. Candidate 401909090 would have T90 October 21 00:00 UTC if first and
unchanged, which is conditional rather than deadline proof. The theoretical
earliest October 20 22:30 UTC / 17:30 CDT is distinct. No selected-player capture,
model run or forecast followed. Safe evidence is in
`evidence/data/2026-10-20-pros004-current-schedule.json` and
`docs/PROS004_SCHEDULE_AUDIT.md`; raw response bodies remain outside Git/Pages.

Persistence completion and all-type semantic recovery corrections are in progress
on this same branch under one integration owner. Frozen `ledger.py`, pilot code,
R0/K0 laws, PR #9/DEV005 and original records are unchanged. The new completion
design retains originals even when late/unacknowledged and requires durable
post-operation clocks before admitting timing. A bounded shared journal uses one
already reserved metadata slot; no per-forecast ledger record is assumed to fit.
Final tests, revised source pins, measured capacity/timing and independent recovery
will be recorded as a separate completed implementation checkpoint.

## PROS004 paired readiness — isolated review package

Current integration owner works in `/workspace/nml-pros004-readiness`, branch
`implementation/pros004-paired-readiness`, based on current main
`735a464e9e8718303ef481abf711a8969de56694`. This supersedes the setup-pending
status below: PR #7 is merged and its one-time pilot remains armed. Read-only
GitHub checks on October 20 confirmed main unchanged, workflow 390126745 active,
draft PR #8 at `df446eee302fd6662ef82184e2c733f5d6e2d2dd`, and draft PR #9 at
`d68015778ab452c94db0385c471de663e830efec`. Their worktrees remain clean. No pilot
workflow, producer, original records or native task was altered or retriggered.
PR #9 / DEV005 is retained as completed frozen research; S0 remains inactive.

This separate package implements prospective wrappers for unchanged R0/K0,
full-history/shared-event input contracts, paired timing/recovery controls and
shared-outcome statistical grading. Genuine operation is deliberately disabled.
There are no live source captures, genuine forecasts, real statistical grades,
reserved aggregate comparisons, financial settlements or qualified tickets from
this package. No merge, deployment or PROS004 activation is authorized.

Independent row-lineage reproduction from the original local Parquet bytes
matches all 26,645 rows / 1,231 games / 14,720,351 bytes and original panel SHA-256,
including all 8,238 exclusions. Evidence is
`evidence/research/pros004-readiness-lineage.json`. A diagnostic source-drift stop
before forecasting is retained in `pros004-readiness-attempt-01.json`. Full-history
synthetic runtime and independent readback are recorded at the completed
readiness checkpoint below. The integrated local suite passed 338 Python tests
in 19.286s, 60 PROS004 tests under optimized Python in 7.667s, 35 frontend tests,
the demo and research artifact smoke check. No model evaluation is being rerun.

The first selected T90 remains **unknown**: retained October 20 local-date source
bytes do not prove complete UTC-October-21 schedule coverage. Midnight is not a
safe assumed deadline. The reservation permits a theoretical earliest T90 of
October 20 22:30 UTC / 17:30 CDT, without establishing an actual event. Complete
permitted current schedule evidence and source-bound remotely recovered activation
must precede the actual first cutoff. See `docs/PROS004_READINESS.md` for the
completed and unresolved activation checklist; the reservation remains inactive.

### Completed implementation and measured checkpoint

Draft [PR #10](https://github.com/NickNicky19/Nicks-multisport-lab-project/pull/10)
is open. Executed implementation commit is
**`6e08b405d79d0fe7fde7299b3407504b35ef128f`**, normally committed/pushed on this
branch. Subsequent evidence/documentation commits retain these same source bytes.
One integration owner coordinated input, producer, records, offline snapshot and
separate verification agents. No agent wrote to the protected pilot/DEV005 trees.

Implemented files:

- `multisport_lab/pros004_inputs.py`: versioned full-history and compact event
  packs, source-byte normalization, complete UTC-date inventory/selection,
  exact evidence lanes and observation/update/import/receipt clocks. Bounded
  content-addressed caches retain immutable rows while all dynamic clocks,
  checksums, provenance, source receipts and exclusions are revalidated.
- `multisport_lab/pros004_producer.py`: separate `pros004-r0-producer-v1` and
  `pros004-k0-producer-v1`; unchanged laws and causal contexts; all 14 complete
  PMFs plus reported minutes; full joint replay recipe/hash; common T90,
  five-minute window, 120-second latency gate, exact source/runtime/input pins,
  pair preflight, fixed original identities and timely missing-peer recovery.
- `multisport_lab/pros004_records.py`: new facade/private research-input validator
  extension over the unchanged ledger; 499+13 record budget, immutable originals,
  one writer, strict calendar/admission records, source-byte outcome normalization,
  one shared outcome, separate statistical grades and traceable corrections.
  A paired correction preflights all six needed revision/link slots and recovers
  interruptions without replacing original probabilities or clocks.
- `multisport_lab/pros004_snapshot.py`: deterministic bounded receipt manifests,
  verified fresh-root copy/readback, exact raw/payload hashes and references,
  interruption refusal and preservation of partial peers. This is offline
  recovery code, not a live GitHub checkpoint or activation proof.
- `multisport_lab/pros004_readiness.py`: source-pinned, explicitly non-issuance
  full-history diagnostic; copies all existing receipts before synthetic work,
  retains eight diagnostic forecasts and verifies baseline/snapshot/replay.
- `scripts/verify_pros004_readiness.py` and six `tests/test_pros004_*.py` modules:
  independent integrity, timing, identity, arithmetic, limit and recovery checks.
  All new integrity guards remain active under optimized Python. DEV005's
  original verifier is untouched.
- `docs/PROS004_READINESS.md`, `docs/DECISIONS.md`, `PROJECT_CONTEXT.md`, this
  handoff, `MANIFEST.sha256` and the `evidence/research/pros004-readiness-*`
  receipts record scope, source recovery, lineage, measurements and limitations.

Actual commands/results:

```bash
python3 -m unittest discover -s tests -v
# 338 tests PASS, 19.286 seconds
python3 -O -m unittest discover -s tests -p 'test_pros004*.py' -v
# 60 focused tests PASS, 7.667 seconds
python3 -m multisport_lab.demo
# PASS
node --test --test-isolation=none web/tests/*.test.mjs
# 35 tests PASS
python3 -m multisport_lab.publication --build-commit 735a464e9e8718303ef481abf711a8969de56694
node web/tests/site-smoke.mjs output
# PASS: bounded local research artifact, all-13 inventory and NO_ACTION
PYTHONPATH=/tmp/nml-nba-audit/deps python3 scripts/prepare_nba_panel.py \
  --players /tmp/nml-nba-audit/sdv_player_box_2026.parquet \
  --schedule /tmp/nml-nba-audit/sdv_schedule_2026.parquet \
  --output /tmp/nml-pros004-readiness/independent-renormalized.jsonl
# PASS: exact original 26,645 rows / 1,231 events / 14,720,351 bytes and exclusions
python3 -m multisport_lab.pros004_readiness \
  --producer-commit 6e08b405d79d0fe7fde7299b3407504b35ef128f \
  --store-root /tmp/nml-pros004-final-store \
  --output /tmp/nml-pros004-final-report.json
# PASS: explicit non-issuance diagnostic; actual clocks 12:16:53.909964–12:21:35.133660Z
git clone --single-branch --branch implementation/pros004-paired-readiness \
  https://github.com/NickNicky19/Nicks-multisport-lab-project.git \
  /tmp/nml-pros004-independent-remote
# PASS: independent exact source commit, clean tree, original 19 records
python3 scripts/verify_pros004_readiness.py \
  --report evidence/research/pros004-readiness-measurement.json --root .
# Independent equivalent from fresh GitHub clone, with --store-root, passes normal and -O
```

The measured ledger contains **31 records / 3,716,686 bytes**: original 19 retained
byte-for-byte plus 12 diagnostic records. History envelope is **1,639,440 bytes**;
event **10,972**; R0 maximum **30,347**; K0 **30,488**; event admission **3,774**;
manifest **1,616**. All are within registered complete-envelope ceilings.
Eight retained forecasts include every original category and minute probability.
One full **26,645-atom law per model** was regenerated for integrity only and
matched every original atom/weight hash and marginal exactly. No real outcome
entered this diagnostic and no predictive score or aggregate comparison was run.

Actual four-subject cohort generation/verification/persistence cost was
**196.303935 seconds**; complete diagnostic including baseline recovery and
replay **281.225514 seconds**; peak RSS **185,296 KiB**. These are measured local
resource results with explicitly simulated source/issuance clocks, not genuine
timeliness or hosted latency evidence. The maximum conservative full-study plan
is **512 records / 22,487,040 bytes**, including all 499 planned records and
13 correction/failure reserve slots. Byte headroom is 11,067,392; no record slots
remain outside the reserve. Bounds were not raised and no atoms/history dropped.

A further size-only synthetic stress used the retained full PMFs, with fitting
and forecast generation patched to raise. Exact executed command:
`PYTHONPATH=/workspace/nml-pros004-readiness python3 /tmp/nml-pros004-size-stress.py`.
The script is retained byte-for-byte in
`evidence/research/pros004-readiness-size-stress.py`; exact paths/rerun refusal are
in its adjacent `pros004-readiness-full-pmf-size.json` receipt. Two invented outcome
revisions, four synthetic individual grade contracts and three supersession links
expanded a separate copy from 31 to **40 records / 3,746,774 bytes**, consuming six
reserve slots. Maximum outcome was **2,649 bytes**, grade **5,164**, correction link
**1,406**. Restart/copied readback, idempotent retry and all 14 existing forecast
byte hashes passed. The original final 31-record store/report were unchanged.
No real outcome or comparative metric was inspected. A first stress preparation
rejected an incorrect diagnostic-lane expectation before appending; its actual
failure/copy was retained, and the fresh retry used the original exact lane.

Independent review fixed lane consistency, strict admission metadata, interrupted
correction linking/capacity and inclusion of the old ledger in the runtime path.
The independent verifier's initial K0 version spelling/fixture was corrected to
the unchanged law; no model source was changed. It then confirmed all 16 executed
source files, 12 frozen pins, 19 original receipts and all eight new diagnostic
contracts under normal and optimized Python. Final report raw SHA-256 is
`76cc9c0e9fb00d2786fc8cab7bfdb7dda79f5bf7c0953becab94dc55c175188c`.
`pros004-readiness-independent-verification.json` retains exact commands/results.
The initial source-drift stop, intermediate empty-ledger measurement and malformed
literal source-pin rejection remain separately retained; none is hidden or
relabeled as prospective evidence.

Activation remains **INACTIVE**. Still required: permitted complete current UTC
schedule evidence/actual first cutoff; actual fresh selection/input capture;
reviewed operational activation and GitHub writer/readback admission; new public
input/forecast/history pagination support for the full study; durable raw outcome
evidence; exact admission for unused private generic failure metadata. The current
genuine-write guard deliberately rejects all activation flags. The reserved
aggregate evaluation has not been executed or benchmarked; its original
November 25 gate and 900-second/512-MiB budget remain. The local tests and resource
measurements establish software behavior only. New genuine issuance, real grades,
financial settlements, qualified tickets, deployment and model evaluation are all
**zero** for this package. Existing historical records retain their original lane.

Next concrete task: review the draft implementation and resolve the explicit
source/operational/publication dependencies before any separately authorized
activation. If they cannot be completed before the actual first selected cutoff,
retain PROS004's original reservation as inactive. A later window needs a new
reservation; do not replace subjects, backfill or relax gates.

**Checkpoint: BOOTSTRAP complete; bounded Milestone 0 audit and full-category
reference implemented; early research website deployed and publicly verified.
Source/product and confirmation gates remain
open. This is a development checkpoint, not a completed validated model.**

## Current operating preparation — October 20, 2026 UTC

The user explicitly authorized ONE unattended execution of the existing October
20 pilot, superseding manual-only/no-scheduling wording for this cycle only.
Current integration branch is `automation/nba-20261020-pilot`, preserving main
`cde77cbaa0908c2ed49d26140110dea5493b54b7` and post-deployment documentation
`b498867a03b7c2d583383ff94d887ddd18cb2e42`. No reset or alternate repository.
The original producer remains `58530309cf384425e15f02fd9fa980899a4dc0bc`.

**Scheduling is not yet verified/activated.** Native automation entry
`6ad6e46f754c81918f190eff2fdc248c` accepted the exact one-time schedule but is
confirmed **paused**, with null next-run time. Its restricted read-only immediate
diagnostic returned HTTP 404 before invocation; no native worker was verified.
The earlier immediate full-prompt test was rejected by automatic approval review
because it could execute mutations outside the approved window. The paused entry
must remain paused so there is only one prospective executor.

The prepared alternative uses this repository's existing GitHub Actions host,
built-in token and ONE fixed records branch
`records/nba-20261020-401909088-t90`. A computer or ChatGPT app need not stay open.
Feature-branch cron alone is not a schedule: hosted runner capability verification,
exact-head setup-PR approval/merge, active default-branch workflow readback and
records-branch integration/readback are prerequisites. Start is October 20,
12:15 p.m. CDT / 17:15 UTC; unchanged capture is 17:20–17:30 UTC and issuance is
17:30–17:35 UTC. GitHub dispatch is best effort; late work must fail closed.

New files are `.github/workflows/nba-20261020-pilot.yml`,
`multisport_lab/scheduled_cycle.py`, `multisport_lab/pilot_github.py`, their two
focused test modules, `docs/SCHEDULED_PILOT.md` and
`evidence/cycles/2026-10-20-scheduling-preparation.json`. Runbook/decisions/context/
verification/handoff/manifest record this authorized exception. The wrapper calls
the unchanged guarded manual cycle, retains full history and the original cohort,
and remotely journals capture/input/generation/original checkpoints. Ambiguous
interruption cannot silently recapture or regenerate. The one workflow verifies
and disables only itself before live work, with an exact-date gate; a different
run cannot take over the immutable claim. Outcome grading remains a later task.

Actual local checks: `python3 -m unittest discover -s tests -v` passed
278 tests (13 phase-runner / 31 GitHub boundary tests); `python3 -m
multisport_lab.demo` passed; `node --test --test-isolation=none
web/tests/*.test.mjs` passed 35 tests. `python3 -m multisport_lab.publication
--build-commit b498867a03b7c2d583383ff94d887ddd18cb2e42` and
`node web/tests/site-smoke.mjs output` passed. YAML parsing and all three embedded
Bash blocks passed, as did Python compilation and `git diff --check`. These are
software/offline artifact checks, not hosted access or future evidence.
`python3 -m multisport_lab.manual_cycle preflight --plan
evidence/cycles/2026-10-20-nba-401909088-plan.json` actually reported
CAPTURE_NOT_YET_OPEN/NOT_READY at 04:09:40.000231Z, null binding and zero originals;
no provider request or model generation occurred. Native capability evidence is
in the preparation receipt. Independent preservation proof is
`evidence/cycles/2026-10-20-scheduled-preservation-audit.json`: all nine producer
files, 19 original records, 34 frozen references and exact plan passed; full
26,645-row/1,231-event/14,720,351-byte history and original clocks recovered with
16 capture/generation/write operations forbidden and zero such calls. Hosted
runner proof and the exact setup head will be added after the actual workflow.
Actual hosted setup run [39368387144](https://github.com/NickNicky19/Nicks-multisport-lab-project/actions/runs/39368387144)
on setup commit `3b81e958ca36a223907028d74ad1883402b64cf5` passed executor,
275 Python/35 frontend tests, demo/export/smoke and manifest steps. The four ESPN
routes returned HTTP 200 at 04:13:24.142112–04:13:24.712621Z (40,482 / 101,504 /
87,740 / 85,732 bytes). Workflow **390126745** verified its own disable/readback/
restore; normal records-branch push and fresh fetch/readback passed. These are
early setup observations with source update clocks unknown, not timely inputs.
First records checkpoint `31e46d0620c1f1dcaf4ef3ccd55cb02b0e02e657` independently
recovers the source/capability and actual 403 receipts. Native entry remains paused.

The run failed at draft creation: GitHub Actions cannot create/approve PRs under
the existing owner setting (HTTP 403). Using already authorized integration access,
we opened the ONE readiness-only draft [PR #8](https://github.com/NickNicky19/Nicks-multisport-lab-project/pull/8)
from the fixed records branch. Actual runner update of that existing draft and
Pages branch dispatch are being verified; no owner setting is presumed changed.
The next wrapper revision distinguishes CREATED from UPDATED_EXISTING, keeps the
original 403 and still runs validation after a blocked PR request. Opening the
records PR also triggered a redundant safe preflight; cancellation completed and workflow 390126745 remains active;
the workflow now excludes that fixed records PR from its setup job. It cannot
issue in PR mode. `evidence/cycles/2026-10-20-hosted-pilot-preflight.json` retains
exact source metadata, receipt hashes, run identity and draft origin. Scheduling
is not activated by the API's feature-workflow active state.

The corrected hosted run [39368941819](https://github.com/NickNicky19/Nicks-multisport-lab-project/actions/runs/39368941819)
**passed every step** on exact setup `86a79d520434647d3d7410269a7e745b100b88c2`:
277 Python tests, 35 frontend tests, demo/export/smoke, retained probe reuse,
normal source integration/push/fresh readback, and actual PR #8 PATCH. Publication
receipt payload `c1fc19fcea9570797d387ecaf0ea4e4ebec3dbda7e17db32a79de7b789e31886`
truthfully records UPDATED_EXISTING, not bot creation. The cancelled duplicate did write an earlier publication receipt incorrectly
labelled `pull_request_creation=VERIFIED` after updating the already open draft.
That original is retained; `evidence/cycles/2026-10-20-publication-proof-correction.json`
explicitly corrects its meaning to UPDATED_EXISTING and cross-references the
original hash and accurate later proof. It establishes no bot creation permission.
The built-in token dispatched
[Pages validation 39369096848](https://github.com/NickNicky19/Nicks-multisport-lab-project/actions/runs/39369096848)
on exact records head `783ac5622297a742e79ea539d885dade541744bd`; it passed and
deployment was skipped off main. **No owner permission setting change is needed
while the existing draft stays open.** The earlier request to enable PR creation
is superseded by this verified update path. Proof:
`evidence/cycles/2026-10-20-hosted-update-verification.json`. No second source probe
was needed; the original four actual route observations retain their own clocks.
The final expiry-only regression additionally ensures that bad producer/plan pins
still expire the trusted one-run workflow before stopping all branch/data work.
Local final full suite passed **278 tests in 8.713s**; the nine source files remain
unchanged. The final setup revision needs its own hosted checks before approval.

Final code commit **`2499a0075be6f854416d50b6c7b01f06bf1885f4`** was published
through the existing connected GitHub app as a normal fast-forward from 86a79d5,
with expected-parent and exact local/API tree SHA checks. Local Git recovered the
exact API commit object by its verified SHA and advanced by fast-forward; no reset
or history rewrite. Hosted setup workflow **39369616942** and Pages check
**39369616935** both passed. Actual logs show **278 Python tests** plus the
35 frontend tests, preflight and existing PR #8 update passed; exact records
`24e298cd62743153d8886dc6b73e0ebd798ac32f` passed explicitly dispatched branch
validation **39369740275** with no Pages deploy. Final adapter SHA256 is
`77bb01ca9463762d62cb73b3427217725f684ac2507231311a19fdc60814aab0`.
The remaining correction/documentation revision changes no operating code.
Final documentation head bd55a3620c6b8a0e16f01f106c4f5b77f822f719 also passed
setup workflow 39369906671 and Pages build 39369906881 (deployment skipped).
The current status-only follow-up records recovered CLI access; its fresh checks
will be observed before requesting exact-head activation approval.

**Temporary activation interruption (now recovered):** the managed shell's existing GH_TOKEN began
returning HTTP 401 (confirmed `gh auth status`, REST reads and Git fetch), while
the connected GitHub app still successfully reads/writes this repository. The
canonical watcher actually returned BLOCKED at 04:21:17.666993Z, not READY.
The final validated tree is being published through that already connected app
with a normal fast-forward and exact expected parent; no credential value is
copied/replaced and no new key/login is introduced. Existing CLI access subsequently recovered without any credential change: a fresh
repository REST read and `gh auth status` succeeded for NickNicky19. No owner
permission-setting change, restart, signup or new key was needed. The temporary
401 and blocked watcher remain historical evidence; current completion uses the
mandatory guarded helper, with no alternate merge REST/GraphQL call. Main remains
cde77cb, so **the cron is not armed**. After fresh readiness and exact-head user
approval, merge the
setup PR normally, verify the default-branch cron/active workflow, reconcile the
records branch with exact merged main and independently recover it. Only then
confirm the scheduled start. The native task must remain paused throughout.

Actual additional commands were `gh pr create --draft --head
records/nba-20261020-401909088-t90 --base main --body-file
/tmp/nml-pilot-records-draft-body.md`, `git fetch --no-tags origin
records/nba-20261020-401909088-t90`, `gh run view 39368387144 --log`, and the
canonical `pr_watch.py --target /workspace/Nicks-multisport-lab-project=7
--mode until-actionable`. After the 401, connected GitHub tools independently
read the corrected run/jobs/logs/receipts. No merge or deploy mutation occurred.
The exact final setup commit is the current PR #7 head; the two existing
implementation commits are 3b81e958ca36a223907028d74ad1883402b64cf5 and
86a79d520434647d3d7410269a7e745b100b88c2.

**New timely inputs/bindings/forecasts: 0; prospective grades: 0; financial
settlements: 0; qualified tickets: 0.** The 19 original records, nine producer
files, fixed plan and frozen experiments remain unchanged. NFL/MLB are untouched.
K0 and PROS004 remain separate. Next concrete task is actual hosted preflight and
guarded activation of the reviewable setup PR; do not describe it as armed yet.

## Prior deployment checkpoint — October 19, 2026 Central (October 20 UTC)

**PR #6 is merged and publicly deployed.** The user approved exact head
`0a20c2a752e6d5475e46feadee08c87e01846d6d` for a merge commit and the existing
Pages workflow. Fresh guarded verification at 03:19:17.153601 UTC found that head
ready/CLEAN/MERGEABLE, build passed, no pending/failed/unknown checks, no missing
required reviewers and zero unresolved threads. The canonical helper retained
policy digest `70b3b0605cddc6f2e6abe9331942e469e32758fbc1abb1474b3af09fdda825df`
and used the exact-head normal protected merge path; no admin, bypass or force.
Main merge **`cde77cbaa0908c2ed49d26140110dea5493b54b7`** occurred at GitHub
**2026-10-20T03:19:59Z** (October 19, 10:19:59 p.m. CDT). Its parents are the
prior main 58530309 and approved 0a20c2a; the merge/approved trees are identical,
`7b7979f10287ecf2181660c29f8c8698875efaa6`. Helper requestedAt
03:20:00.473480Z and merged watcher observation 03:20:10.883343Z are separate
receipt clocks, not replacements for GitHub mergedAt. Local main was advanced
by fast-forward; legitimate work and the carried PR #5 documentation are intact.

[Workflow 39363727977](https://github.com/NickNicky19/Nicks-multisport-lab-project/actions/runs/39363727977)
passed on exact main: build completed 03:20:31Z; Pages deploy completed
03:20:46Z. Actual main logs show **234 Python tests / 35 frontend tests PASS**,
including the two-pin provenance fetch, synthetic demo and artifact smoke.
Live site: https://nicknicky19.github.io/Nicks-multisport-lab-project/ .
The public manifest serves cde77cb above, published 03:20:21.017133Z. Snapshot:
`e2a64fdaf340c8798609b21c7242b70576bca1a68d5c0e7f463ef79b4a457de3`.
Manifest raw SHA256:
`30d00ee04c036eab3a29185057859d11243247ce064030a4d856589cf36150e5`.
The 151,194-byte NBA asset SHA256:
`1813fd774b36e9dca4c2aa7d64ab77f9e9c61b9d3d7adba6477f030c9237a4dc`.
System-verified HTTPS returned 200 for root/manifest/NBA and seven static assets;
all seven served static files match exact main. Original inputs/raw provider
bodies are excluded from Pages. Independent offline replay at the actual
publication clock reproduced the snapshot, manifest, NBA asset and static bytes
without source capture, model generation or ledger append.

Actual public Chromium 154 checks ran 03:22:04.491683–03:22:39.061976 UTC at
1440px desktop and 390/320px mobile. All seven routes/direct reloads, 14 category
filters, six original historical bundles/84 PMFs/six statistical grades, the
actual single R0 reconstruction group and neutral History wording passed.
There are no actual pending forecasts to invent. Upcoming retains three honest
missing-timely-capture/issuance and reconstructed-availability explanations.
All 45 scope × 2–6-leg size × direction combinations stayed NO_ACTION, zero
candidates and Not issued. Nine browser resources stayed within the exact
allowlist/prefix; no page/HTTP errors or synthetic injection. Chromium used only
the process-local configured-proxy CA SPKI pin; urllib independently verified
system TLS. No persistent trust or HOME settings changed.

**The pilot producer remains exactly
`58530309cf384425e15f02fd9fa980899a4dc0bc`; it is not the new main/build SHA.**
All nine reviewed source files, 19 original ledger records and 34 frozen/source
files remain byte-identical. Cycle plan payload
`22ae8db607374486ebee6eb569d236a3d27aedc8535c3085a6b6858226921908` is unchanged.
The actual post-merge preflight at 03:21:01.358349 UTC reported
`NOT_READY` / `CAPTURE_NOT_YET_OPEN`, null fresh input binding, all four subjects
missing and zero issued forecasts. Independent checks explicitly forbade provider
HTTP, generation, issue_cohort, ledger append and cycle writes. This deployment
performed no provider capture, input refresh/binding, model evaluation, genuine
issuance, outcome append or new grading. **Future forecasts 0; new prospective
grades 0; financial settlements 0; qualified tickets 0.** K0 and all prior
experiments remain frozen; PROS004 is not activated. NFL/MLB stayed untouched;
no service, signup, API key, scheduler or collector was introduced.

Deployment proof is `evidence/deployment/2026-10-20-pr6-pages.json`, payload SHA256
`c078c8eb1d28318fe3eda27ad322598f214fe5072071d47f7f6a54a2a3bbbd9a`.
Public browser aggregate SHA256:
`7eeb6185314df60c100897675d10554d217b0b118c20f6b506a340627a621303`.
Independent merge and static replay proof hashes are
`befdbe3bf58c149d21ecac330a797c727091b4ceacd4218564d7d328ecfb58b7` and
`273309aad30b134e385233ed5347763e7b81c0891faa675158d6200968caae35`.
Final independent signoff cross-checked all ten referenced helper/browser/CI/
replay artifacts and coherent merge/build/deploy/QA/readback clocks; no blocking
finding remains. Proof `/tmp/nml-independent-pr6-deployment-review.json`, raw SHA256
`092eb2bbdee9d5261d095880a6a8e980df11a0c8ebb7f7c7a8b1332befffb214`.
This post-deployment documentation is retained on `docs/pr6-deployment`, based
on exact main cde77cb, and changes only this handoff, PROJECT_CONTEXT.md,
docs/VERIFICATION.md, docs/UI_NOTES.md, MANIFEST.sha256 and that new receipt.
Resolve its exact commit with `git log -1 --format=%H docs/pr6-deployment`.
It is separate from both approved application merge and frozen pilot producer.
Earlier open-PR/not-deployed/main-585 statements below describe prior checkpoints.

Commands actually run (full public/hash/browser proofs retained in the receipt):

```bash
PATH=/tmp/nml-pr-completion/bin:$PATH python3 /tmp/nml-pr-completion/pr_watch.py --target /workspace/Nicks-multisport-lab-project=6 --mode until-actionable --interval 15 --timeout 180 --cursor /tmp/nml-pr-completion/pr6-cursor.json --observations-file /tmp/nml-pr-completion/pr6-observations.ndjson --pretty
PATH=/tmp/nml-pr-completion/bin:$PATH python3 /tmp/nml-pr-completion/pr_land.py --repo /workspace/Nicks-multisport-lab-project --pr 6 --head 0a20c2a752e6d5475e46feadee08c87e01846d6d --mode auto --method merge --pretty
PATH=/tmp/nml-pr-completion/bin:$PATH python3 /tmp/nml-pr-completion/pr_land.py --repo /workspace/Nicks-multisport-lab-project --pr 6 --head 0a20c2a752e6d5475e46feadee08c87e01846d6d --mode auto --method merge --policy-digest 70b3b0605cddc6f2e6abe9331942e469e32758fbc1abb1474b3af09fdda825df --confirm --pretty
PATH=/tmp/nml-pr-completion/bin:$PATH python3 /tmp/nml-pr-completion/pr_watch.py --target /workspace/Nicks-multisport-lab-project=6 --await-merge 0a20c2a752e6d5475e46feadee08c87e01846d6d --await-merge-mode auto --await-merge-since 2026-10-20T03:20:00.473480Z --interval 15 --timeout 180 --cursor /tmp/nml-pr-completion/pr6-cursor.json --observations-file /tmp/nml-pr-completion/pr6-observations.ndjson --pretty
git fetch origin
git switch main
git merge --ff-only origin/main
git switch -c docs/pr6-deployment
gh run watch 39363727977 --repo NickNicky19/Nicks-multisport-lab-project --exit-status
python3 -m multisport_lab.manual_cycle preflight --plan evidence/cycles/2026-10-20-nba-401909088-plan.json
python3 /tmp/nml-public-pr6-qa.py cde77cbaa0908c2ed49d26140110dea5493b54b7
sha256sum --check --quiet MANIFEST.sha256
git diff --check
```

At that deployment checkpoint the next operation was **manual**, Tuesday October 20: capture,
normalize, persist and bind during **12:20–12:30 p.m. CDT**, then generation,
verification and forecast persistence during **12:30–12:35 p.m. CDT**. Use the
complete runbook on the current tree and carry this deployment documentation
into the eventual records branch. The same exact pinned producer and single
fresh input binding must survive every retry/readback; the early input only
recovers retained history. Fresh source status/event/cohort changes or missed
windows must produce an honest failure/partial result, with no backdating or
silent replacement. Outcomes remain pending until independently verified final
source evidence; DNP, unresolved states and corrections retain their documented
meaning. April history staleness, finite support, DD/TD/BLK uncertainty, workload
limits and absent betting contracts/qualification remain. Publication alone does
not establish forecasting quality or future paper evidence.

## Prior preparation checkpoint — October 19, 2026 Central (October 20 UTC)

**Manual pilot preparation is verified; no timely input or genuine forecast has
been issued.** Current branch `preparation/pinned-pregame-cycle` preserves
post-deployment documentation commit `c19bcd67d4fefe7f818fed569c683db9cc5ab9fc`.
Fresh remote fetch confirmed deployed main remains
`58530309cf384425e15f02fd9fa980899a4dc0bc`; no reset or newer-work overwrite.
The reviewed producer is frozen to that **exact** 58530309 SHA for every operation
and retry, regardless of later documentation/records commits. Main/Pages has not
been changed by this preparation checkpoint.

The former `--model-commit "$(git rev-parse HEAD)"` was unsafe for recovery.
Independent isolated synthetic reproduction showed that a documentation-only
revision can pass the same source-byte checks yet cause legacy `issue_cohort` to
miss its original subject and create a second original. No real records were
corrupted or duplicated. The new bounded `multisport_lab.manual_cycle` guard is
outside `MODEL_FILES`, preserving all nine reviewed source bytes. It scans original
cycle subjects across all model/input revisions before generation, requires the
fixed producer, binds exactly one timely fresh input reference, rejects drift or
duplicate originals, and recovers partial/complete originals without regeneration.
Direct legacy API hardening remains a separately versioned follow-up; use the
guarded commands in `docs/PREGAME_RESEARCH_CYCLE.md` for this fixed cycle.

Create-only plan `evidence/cycles/2026-10-20-nba-401909088-plan.json`, payload SHA
`22ae8db607374486ebee6eb569d236a3d27aedc8535c3085a6b6858226921908`, freezes producer,
source hashes, event 401909088/version, the same four selected IDs, window bounds,
history-only preparation ID and all 19 original record hashes. The future binding
`evidence/cycles/nba-20261020-401909088-t90-r1-binding.json` **does not yet exist**.
It will retain the exact fresh LedgerRef and actual bound clock. The early
`dfa1c4345495eb3aa6b203f2e8309c89c112b6b78a36cd3d2c603d390776b6fc` record
is only a history recovery source, never the issuance input.

Actual local preflight/recovery at 03:08 UTC passed integrity checks and reported
`NOT_READY` / `CAPTURE_NOT_YET_OPEN`, null input binding, zero selected forecasts
and all four subjects missing. The capture-window gate and preparation-as-fresh
binding attempts each exited 2 with the expected explicit diagnostic and no write.
Independent verification forbade provider HTTP, producer generation/issue_cohort,
ledger append and cycle writes. It reproduced the full 26,645-row / 1,231-event /
14,720,351-byte history, SHA
`489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c`.
All 19 actual ledger records, 34 frozen/source files and nine producer files are
unchanged. No source requests, fresh input capture/binding, genuine issuance,
outcome append, new grade, model evaluation or financial settlement occurred.
K0/R0/DEV002/DEV003 remain frozen; PROS004 remains a separate inactive task.

Software checks: **234 Python tests / 35 frontend tests PASS**, including 13 new
synthetic guard regressions; demo, local artifact smoke, all ten runbook Bash
blocks' syntax and whitespace checks passed. Tests cover revision/input drift,
duplicate originals, interruption, late partial/complete readback, immutable
clocks/content, early preparation rejection and active corrected/DNP/unresolved
grade status. These are software checks, not forecasting accuracy or future
paper evidence. `.github/workflows/pages.yml` explicitly fetches only the two
frozen provenance commits for source-byte tests in shallow CI checkouts. It adds
no scheduled execution or provider collection.

Durable preparation evidence:
`evidence/cycles/2026-10-20-manual-pilot-preflight.json`, payload SHA
`5b05be9df05fc34426b8dd0b0d250e6af137e60f46f29130492abd6ed545ae55`.
It retains exact readback, independent synthetic defect/guard proof and software
log hashes. Changed files are that receipt and cycle plan, the new guard and its
tests, runbook, decisions, workflow, this handoff, context, verification log and
manifest. Carried PR #5 deployment documentation/receipt remains preserved.
Resolve this checkpoint's delivery revision with
`git log -1 --format=%H preparation/pinned-pregame-cycle`; it is never the model SHA.

Implementation and runbook commit **`f28911f74cb36fec3c6ae03dd0883177606d00d0`**
is pushed on `preparation/pinned-pregame-cycle` and opened as
[PR #6](https://github.com/NickNicky19/Nicks-multisport-lab-project/pull/6).
[Workflow 39363160886](https://github.com/NickNicky19/Nicks-multisport-lab-project/actions/runs/39363160886)
passed all 234 Python/35 frontend tests, the exact-pin fetch, demo and artifact
checks; deploy was correctly skipped on the PR. The guarded watcher at
03:14:11.137670 UTC found this head ready/CLEAN/MERGEABLE, build passed, zero
pending/failed/unknown checks and zero unresolved review threads. No new PR
landing is authorized by the completed PR #5 approval.

A fresh independent GitHub clone recovered exact implementation bytes, all
original records/frozen sources, the plan and preflight receipt. Read-only
preflight/recovery again passed, and 13 guard tests passed. A separate depth-1
clone initially lacked both provenance commits; the exact two-SHA CI fetch
restored them without changing HEAD and all 13 guard tests passed. Full history
recovery again retained 26,645 rows / 1,231 events / 14,720,351 bytes. The actual
source model identity stayed 58530309 despite the committed preparation HEAD.
Remote/shallow/CI/committed-head proofs are retained in
`evidence/cycles/2026-10-20-manual-pilot-preparation-delivery.json`.
A following documentation-only commit records this readback; its branch HEAD
is deliberately distinct from the frozen producer SHA and does not add issuance.
Main/Pages remains the deployed 58530309 checkpoint until a separately approved
PR lands. Final refreshed PR check state is reported with the exact delivery head.

Commands actually run (all preparation only):

```bash
git fetch origin
python3 -m unittest discover -s tests -v
python3 -m multisport_lab.demo
node --test --test-isolation=none web/tests/*.test.mjs
python3 -m multisport_lab.manual_cycle preflight --plan evidence/cycles/2026-10-20-nba-401909088-plan.json
python3 -m multisport_lab.manual_cycle recover --plan evidence/cycles/2026-10-20-nba-401909088-plan.json
python3 -m multisport_lab.manual_cycle preflight --plan evidence/cycles/2026-10-20-nba-401909088-plan.json --require-capture-window
python3 -m multisport_lab.manual_cycle bind --plan evidence/cycles/2026-10-20-nba-401909088-plan.json --input-record-id dfa1c4345495eb3aa6b203f2e8309c89c112b6b78a36cd3d2c603d390776b6fc
python3 -m multisport_lab.publication --build-commit 58530309cf384425e15f02fd9fa980899a4dc0bc --output .local-data/pinned-cycle-preflight-site
node web/tests/site-smoke.mjs .local-data/pinned-cycle-preflight-site
git diff --check
git push -u origin preparation/pinned-pregame-cycle
gh pr create --repo NickNicky19/Nicks-multisport-lab-project --base main --head preparation/pinned-pregame-cycle --title 'Pin manual NBA pilot producer and guard recovery' --body-file /tmp/nml-pinned-cycle-pr-body.md
PATH=/tmp/nml-pr-completion/bin:$PATH python3 /tmp/nml-pr-completion/pr_watch.py --target /workspace/Nicks-multisport-lab-project=6 --mode until-actionable --interval 15 --timeout 180 --cursor /tmp/nml-pr-completion/pr6-cursor.json --observations-file /tmp/nml-pr-completion/pr6-observations.ndjson --pretty
```

The two explicitly negative commands above returned 2, as intended; the remaining
checks passed. Local artifact construction reads retained historical records and
is not a new deployment. NFL/MLB remained untouched; no new service/signup/key,
collector, scheduler, wager or qualification was introduced.

Next concrete operation is manual, Tuesday **October 20, 12:20–12:30 p.m. CDT**
(17:20–17:30 UTC): phase-gated current event/cohort capture, normalization,
persistence and create-only fresh binding. At **12:30–12:35 p.m. CDT** use the
same fresh ID and explicit `--model-commit 58530309cf384425e15f02fd9fa980899a4dc0bc`
for guarded issuance/retries. Exact capture/persist/issue, lost-stdout recovery,
commit/push, independent remote recovery, publication and later grading commands
are in the runbook. Fresh changed event/cohort facts or missed windows cause the
actual cycle failure/partial state, not replacement or backdating. Later verified
final evidence is required for statistical grades; missing/nonfinal stays pending,
explicit DNP is not zero production, and corrections append traceable links.
History staleness, finite support, DD/TD/BLK and workload limitations remain.

## Prior deployment checkpoint — October 19, 2026 Central (October 20 UTC)

**PR #5 is merged and publicly deployed.** The user explicitly approved only
head `713716a17465c93d32795aabba9e0a8c9c3a5e8c`. Fresh guarded checks confirmed
that exact head ready, CLEAN/MERGEABLE, build passed, no pending/failed/unknown
checks, no missing required reviewers and zero unresolved review threads.
The canonical helper used the same policy digest
`70b3b0605cddc6f2e6abe9331942e469e32758fbc1abb1474b3af09fdda825df`,
normal merge method and exact-head guard; no admin, bypass or force-push.
Main merged **`58530309cf384425e15f02fd9fa980899a4dc0bc`** at
**2026-10-20T02:30:40Z** (October 19, 9:30:40 p.m. Central). Its tree exactly equals
the approved head; parents are prior main eca2a06 and that approved revision.
The requestedAt helper receipt 02:30:41.100803Z and merged watcher observation
02:30:54.412624Z remain separate clocks, not rewritten to match GitHub mergedAt.
Local main was fast-forwarded; newer legitimate work was preserved.

Live site: https://nicknicky19.github.io/Nicks-multisport-lab-project/ .
[Workflow 39359308833](https://github.com/NickNicky19/Nicks-multisport-lab-project/actions/runs/39359308833)
passed build and deploy on exact main: build completed 02:31:00Z and deploy
completed 02:31:22Z. Required 221 Python/35 frontend tests, synthetic demo and artifact
checks passed. System-verified HTTPS returned 200 for root, manifest, NBA data
and seven static assets. Served build commit is the exact 58530309 merge above.
Snapshot SHA256:
`db50ba5ab1ced15e694fe9ded143384f74ddbf3503d04aed168089f12fd424fe`.
Manifest raw SHA256:
`86e40c82b3b4ba9b491e693440704eef83ff6349f5978bbcadf4284cb46d24ff`.
NBA asset SHA256:
`8f7cc6766bab9c676362171377cfbdc42068c6d7c4aa603f2eb08aecec280112`.
All seven static assets matched exact main Git bytes. The complete normalized
history/preparation record is excluded from Pages, including an actual 404 check
of its exact record path; no raw sources were exported.

Public Chromium 154 verification ran 02:31:56.023463–02:32:27.219269 UTC, at 1440px
desktop and 390/320px mobile. All seven routes/direct reloads, fourteen category
filters, six original historical bundles/84 PMFs and six original statistical
grades passed with exact identities/clocks. Performance has one actual R0
reconstruction group; all six grades are scored and no pending forecast is falsely
claimed. History preserves its neutral past-event meaning. Upcoming has the three
accurate missing-timely-capture/issuance reasons. All 45 SINGLE/SELECTED/ALL × 2–6
size × OVER_ONLY/UNDER_ONLY/MIXED builder combinations stayed NO_ACTION, zero
candidates and Not issued. Nine browser assets stayed within the repository
prefix, with no page/HTTP errors or synthetic injection. Chromium used only the
process-local configured-proxy CA SPKI pin; urllib independently verified system
TLS. No persistent trust or HOME settings changed.

The approved implementation is now published, including forecast-v2 validation,
pending-grade rendering, source normalization, durable-input and future grading
code. **Publication is not genuine issuance.** All 19 ledger records are unchanged:
18 historical forecast/outcome/grade records and one early preparation input.
Original source clocks 01:51:42.675230–01:51:55.889290Z, normalization import
02:10:36.352647Z and input receipt 02:10:44.260387Z remain distinct. The six
forecasts are still historical reconstructions, actually issued October 20 for
November 24, 2025 events. R0/DEV002/DEV003 receipts/results remain frozen; K0 is
unpromoted and PROS004 is an inactive reservation. This deployment performed no
source collection, model evaluation, input refresh, forecast generation, outcome
append or grading. **Genuine future forecasts 0; new prospective grades 0; financial
settlements 0; qualified tickets 0.** NFL/MLB remained untouched; no paid service,
signup, API key or scheduler was introduced.

Independent offline replay at 02:34:33.690297 UTC rebuilt exact main at the
served publication clock 02:30:53.994845Z and reproduced the manifest, snapshot,
151,194-byte NBA asset and all seven static bytes. It validated the four guarded
helper and three browser artifact hashes, exact records and clock chronology;
no model generation or source request was used. No blocking finding remains.

Combined verification evidence:
`evidence/deployment/2026-10-20-pr5-pages.json`, payload SHA256
`dff05f5aa71460340b78c9ca7bdac101b5b61a9a833c690d83a6630f01a0bcb2`.
Independent replay proof is `/tmp/nml-independent-pr5-deployment-review.json`,
raw SHA256 e6d0c0a052c25df87e68bde15a7d82c2f7e109dda21ae827751c12c22081c28a.
This post-deployment checkpoint
is retained on `docs/pr5-deployment`, based on 58530309. It changes only this
handoff, PROJECT_CONTEXT.md, docs/VERIFICATION.md, docs/UI_NOTES.md,
MANIFEST.sha256 and that new receipt. Resolve the exact documentation commit
with `git log -1 --format=%H docs/pr5-deployment`; it is separate from the
approved application merge. Earlier branch-only/open-PR/deployed-eca2 statements
below describe prior checkpoints and are superseded here.

Commands actually run (full public/hash/browser proof is in the receipt):

```bash
PATH=/tmp/nml-pr-completion/bin:$PATH python3 /tmp/nml-pr-completion/pr_watch.py --target /workspace/Nicks-multisport-lab-project=5 --mode until-actionable --interval 15 --timeout 180 --cursor /tmp/nml-pr-completion/pr5-cursor.json --observations-file /tmp/nml-pr-completion/pr5-observations.ndjson --pretty
PATH=/tmp/nml-pr-completion/bin:$PATH python3 /tmp/nml-pr-completion/pr_land.py --repo /workspace/Nicks-multisport-lab-project --pr 5 --head 713716a17465c93d32795aabba9e0a8c9c3a5e8c --mode auto --method merge --pretty
PATH=/tmp/nml-pr-completion/bin:$PATH python3 /tmp/nml-pr-completion/pr_land.py --repo /workspace/Nicks-multisport-lab-project --pr 5 --head 713716a17465c93d32795aabba9e0a8c9c3a5e8c --mode auto --method merge --policy-digest 70b3b0605cddc6f2e6abe9331942e469e32758fbc1abb1474b3af09fdda825df --confirm --pretty
PATH=/tmp/nml-pr-completion/bin:$PATH python3 /tmp/nml-pr-completion/pr_watch.py --target /workspace/Nicks-multisport-lab-project=5 --await-merge 713716a17465c93d32795aabba9e0a8c9c3a5e8c --await-merge-mode auto --await-merge-since 2026-10-20T02:30:41.100803Z --interval 15 --timeout 180 --cursor /tmp/nml-pr-completion/pr5-cursor.json --observations-file /tmp/nml-pr-completion/pr5-observations.ndjson --pretty
gh run list --repo NickNicky19/Nicks-multisport-lab-project --commit 58530309cf384425e15f02fd9fa980899a4dc0bc --json databaseId,headSha,status,conclusion,name,url
python3 /tmp/nml-public-pr5-qa.py 58530309cf384425e15f02fd9fa980899a4dc0bc > /tmp/nml-public-pr5-qa.log 2>&1
sha256sum --check --quiet MANIFEST.sha256
git diff --check
```

Next concrete task is the existing **unscheduled** pilot: Tuesday October 20
capture **12:20–12:30 p.m. Central**, then generation/receipt **12:30–12:35 p.m.**
(17:20–17:30Z and 17:30–17:35Z). Use the exact capture/persist/issue commands in
`docs/PREGAME_RESEARCH_CYCLE.md` with retained history record
dfa1c4345495eb3aa6b203f2e8309c89c112b6b78a36cd3d2c603d390776b6fc.
Fresh exact-event/cohort status and source observations remain required; the
current early preparation input cannot be relabeled as timely. Changed event
version, team, selected-player status or missed timing blocks the cycle. Do not
backdate a record, refresh its old clocks or schedule a collector. Append actual
outcomes/statistical grades only after independently verified final source data;
keep later financial settlement separate. Current history staleness, finite
support, DD/TD/BLK uncertainty and PROS004 activation/export/retention dependencies
remain the documented limitations.

## Prior implementation checkpoint — pregame preparation, October 19 evening Central / October 20 UTC

Working branch: `implementation/pregame-research-cycle`, based on
`29253a3e3cdb3827a4cab905c2ff36bb772d9e92`, which carries the post-deployment
status over reviewed/deployed main `eca2a0679bd99eaff77c1c0785df13840fb99762`.
Fresh fetch found no newer main work and the initial tree was clean. No reset,
old ZIP, external NFL/MLB changes, new service/key or scheduler.

A bounded current-source path and separately versioned R1 producer/forecast v2,
input ledger, pending-grade UI and offer aliases are implemented. The actual
source/selection/history audit is in `evidence/data/2026-10-20-pregame-cycle-verification.json`;
policy, scope, exact clocks and runnable commands are in
`docs/PREGAME_RESEARCH_CYCLE.md` and `docs/PREGAME_SOURCES.md`.
The next consecutive model comparison is a reservation, not scoring authorization:
`docs/NBA_PROSPECTIVE_004.md`, protocol payload SHA256
`873cd140236253e995d759590c9237383ac5a2fc33f776f960446d793c70baee`.
K0 and all R0/DEV002/DEV003 executed results remain frozen and unpromoted.

Actual source observations show scheduled event401909088, Detroit8/Boston2,
October20 at2:00p.m. CDT (19:00UTC). Four selected IDs were fixed before forecasts
or outcomes and cross-checked by actual athlete profiles. Eight source requests /
337,357 bytes; all selected identity/team checks passed. Full original-source
normalization reproduced all26,645 rows/1,231 games and exact14,720,351-byte panel,
SHA489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c.
The1,636,253-byte compact history is lossless and preserves original source clocks;
no20k truncation or current-season history claim.

**Genuine issuance:0. New statistical grades:0. New financial settlements:0.**
The actual01:51UTC observations are preparation, outside the fixed late capture
window. Next eligible capture is October20 **12:20–12:30p.m. Central**, followed
by actual generation/receipt **12:30–12:35p.m.** (17:20–17:30Z and17:30–17:35Z).
Fresh exact-event/cohort capture and receipt by cutoff are required; no backdating.
The selected event/version/cohort change guards can block that cycle. Existing
six reconstructed bundles/six historical grades and18 original records remain.
Public main remains the verified eca2a06 site; branch changes are not deployed.

Source/producer implementation committed as
**`55547606e4fad6907f8fc06577976a83b3ed40a8`** before creating the final
preparation input. Final code then re-normalized the same four original response
bodies without network/model calls. New v3 import clock:02:10:36.352647UTC;
sourcepack SHAe89f19cca65d3a26e57038a54888baab5a734e61f42989fc901381f3ae61bd12.
The separately persisted preparation input reference is
**research_inputs/dfa1c4345495eb3aa6b203f2e8309c89c112b6b78a36cd3d2c603d390776b6fc**,
payload SHAbe1cf24531a241f1d2752cde3429414b9c6fc64491e99a8bffaf4695d8fa3659.
Its source observations remain01:51:42.675230–01:51:55.889290UTC, not the import
or receipt time. This early input cannot support the late T90 issuance window.

The full compact normalized statistics are retained in public Git under the
bounded publisher-asserted CC BY4.0 release-store basis documented with actual
quotes, attribution, modification notice and upstream uncertainty in
`docs/HISTORY_RETENTION.md`. No blanket ESPN rights or recurring collection grant
is inferred. Raw provider bodies/large Parquets remain excluded; the full input
record is excluded from Pages. Rights receipt payload SHA604fec4c1b2ecc884543d9a9a3d997e640e09a2d44bf9bb0bcd7c1a8098ee92f.

Final integrated software verification: **221 Python tests**, **35 frontend
tests**, synthetic demo and artifact checks passed. Local Chromium desktop1440px
and mobile390/320px checks passed, including a clearly synthetic prospective-v2
fixture, pending grades, all14categories and scoped2–6/direction NO_ACTION.
Separate verification reproduced actual source normalization and compact recovery
without model evaluation. The new manual `prospective_outcomes` path checks actual
issued-input context/final boxscore identity, strict counts/DNP/missing semantics,
original source-clock recovery and explicit corrections. Sixteen focused grading
checks pass. A later actual historical final-boxscore audit verified the parser
shape and all selected counts; the upcoming event must still supply its own
verified final observation before any prospective grade.
The real preparation grading-status command returned PENDING/NO_ISSUED_FORECASTS,
zero source requests/outcomes/grades; no future result was fabricated.

The bounded actual offer continuation made nine requests/4,782,230bytes: ESPN
1,132items with73future-update anomalies; Sleeper1,360rows/2,720side options,
2,472mapped partial options plus248unmapped quarter options. RA/PR/BLK+STL/PA
were actually observed and added as aliases. Actual generic Sleeper rules were
read, but board variant, exact complete side/period/economics remain unresolved.
Complete contracts/usable quotes/qualified tickets remain0. Authoritative pilot
receipt payload SHA269b3f74d2176ed39ce96c62c15f781711a4b98957cc67c2d7f0d1be9883d4fd.

**Independent remote retention is verified.** Input checkpoint
`a3934f5b7773999e2aa30c07c1ce85e0f5d9907f` was pushed and independently cloned.
At02:13:42.628019UTC, all19 ledger files matched exact remote bytes. A fresh
process with raw sources absent and network/model generation forbidden recovered
the exact26,645 rows/panel SHA, original source clocks, import and actual input
receipt02:10:44.260387UTC. All34 original frozen evidence/source/record hashes
matched; no old record was changed. A real early issuance CLI attempt exited2
before generation. The full independent source/test/recovery/public-state and
browser proofs are retained in
`evidence/research/2026-10-20-pregame-cycle-checkpoint.json`.

Final local artifact build a3934f5 passed all seven routes at1440/390/320px,
exact3 Upcoming reasons,45 scope×size×direction NO_ACTION cases, and unchanged
six historical bundles/84 PMFs/six grades. All9 allowed artifact files were
checked; no raw/full-history/research_inputs bytes were exported. NBA asset
151,194bytes SHA930771e60caabf40063b8bae628f31ffa3f9b54df0123d53f1e33bc212c04cbe.
A system-verified public manifest read at02:14:53UTC still served deployed main
eca2a06 and its original snapshot76da4612...; this PR is not deployed.

[PR #5](https://github.com/NickNicky19/Nicks-multisport-lab-project/pull/5) contains
the carried29253a3 deployment status and this package. Initial a3934f5 checks
passed; final exact-head checks/landing status come from the guarded watcher.
No PR #5 merge or deployment has been performed. Current branch head is
`git rev-parse HEAD`; source/retention commits are exact above. Exact package
files: `git diff --name-status eca2a0679bd99eaff77c1c0785df13840fb99762 HEAD`.
The input normalizer, coherent producer and ledger remain the5554760 code.
A later actual historical-source audit exposed and fixed the separate outcome
parser period-count path; its exact evidence/code hash and regression results
are recorded below. It does not change or rerun any frozen model result.

Commands actually run, in addition to the source/offer commands retained in the
linked evidence:

```bash
python3 -m unittest discover -s tests -v
python3 -m multisport_lab.demo
node --test --test-isolation=none web/tests/*.test.mjs
python3 -m multisport_lab.prospective persist --pack .local-data/pregame-cycle/preparation-sourcepack-v3.json
python3 -m multisport_lab.prospective issue --input-record-id dfa1c4345495eb3aa6b203f2e8309c89c112b6b78a36cd3d2c603d390776b6fc --model-commit 55547606e4fad6907f8fc06577976a83b3ed40a8
python3 -m multisport_lab.prospective_outcomes --event 401909088 --input-record-id dfa1c4345495eb3aa6b203f2e8309c89c112b6b78a36cd3d2c603d390776b6fc
python3 -m multisport_lab.publication --build-commit a3934f5b7773999e2aa30c07c1ce85e0f5d9907f --output /tmp/nml-pregame-final-artifact
node web/tests/site-smoke.mjs /tmp/nml-pregame-final-artifact
python3 web/tests/browser_smoke.py /tmp/nml-pregame-final-artifact --screenshots /tmp/nml-pregame-final-screenshots
sha256sum --check --quiet MANIFEST.sha256
git diff --check
```

A final bounded historical-source audit made one actual ESPN summary request
for event401810135, with two retrospective subjects declared beforehand. All12
identity fields,30count fields, reported minutes and28derived-category values
matched the retained panel. It exposed a missing status.period despite a verified
final status. The separate outcome parser now derives the count only from explicit
NBA format4×720seconds/300second OT and both complete matching quarter arrays,
whose sums must equal the final team scores; supplied ordinal/value conflicts
fail. No default four-period assumption or old panel rewrite. This is one historical
source-shape verification, not a whole-history exact-duration REB admission.
Authoritative append-only evidence:
`evidence/data/2026-10-20-outcome-normalizer-audit-v2.json`, payload
c253d19d8cbefb01e7e1a9a0182ef62cc419357289d6d925847a5bd1c847ed93.
Final outcome-source code SHA8d22da881bcae0e0e213e314f0181bc727edd4116361fa2b7413f01f154919bf;
221Python/35frontend checks and demo pass. No forecast generation, model evaluation,
actual future-source request, outcome/grade ledger write or financial settlement
was performed by this extra audit. Independent re-normalization and16focused
checks passed; proof is retained in
`evidence/research/2026-10-20-outcome-independent-check.json`.
The original18records and prepared input are unchanged.

Next concrete task: land/deploy this exact reviewed PR only under its own
head-specific confirmation, then perform the exact **unscheduled** manual capture
and issuance commands in `docs/PREGAME_RESEARCH_CYCLE.md` at the eligible Central
times above. The capture command recovers history from Git, not lost `/tmp`
files. Do not issue from the early preparation pack or backdate a missed window.
Later verified outcomes need a new manual grading capture; financial settlement
stays separate. PROS004 still needs paired prospective versions, deduplicated
history retention, freshness rules, remote activation freeze and a bounded export
plan beyond today's32forecast/64grade caps. Independent review corrected its
future total to474record slots/38reserved; the inactive reservation stays unchanged.
No new scoring or K0 promotion follows. The original R0 pilot, DEV002, DEV003 and
18 historical ledger bytes remain unchanged.

## Prior deployment checkpoint — 2026-10-20 01:32 UTC

**PR #4 is merged and deployed.** The user explicitly approved its exact head
`1f80112ed54a8c2eaa20024e806054739b815c98`. Fresh guarded checks confirmed that
head, CLEAN/MERGEABLE state, successful build, no pending/failed checks, no missing
required reviewers and zero unresolved review threads. The canonical helper
used policy digest
`70b3b0605cddc6f2e6abe9331942e469e32758fbc1abb1474b3af09fdda825df`,
the approved merge method and exact-head guard. No admin/bypass/force-push was
used. GitHub records the merge at **2026-10-20T01:27:21Z** as main commit
**`eca2a0679bd99eaff77c1c0785df13840fb99762`**. Its tree equals the approved head;
parents are prior main `002a6b994c862c758f1d7c8199831c75eff761af` and that head.
Local main was fast-forwarded, preserving all reviewed work.

Live site: https://nicknicky19.github.io/Nicks-multisport-lab-project/ .
[Workflow 39353520895](https://github.com/NickNicky19/Nicks-multisport-lab-project/actions/runs/39353520895)
completed successfully: build at 01:27:41Z and deploy at 01:27:57Z. The main workflow
ran the 177 Python/31 frontend checks, demo and artifact checks. System-verified
HTTPS readback returned 200 for ten resources. The served v2 manifest identifies
the exact main merge above, publication RESEARCH_ONLY, snapshot
`76da4612338f8609f9f112ee13d370acda9104be63ece873f3d897d28013649d`.
Manifest raw SHA256:
`5c1c4b2c69346516dbdc30389431993b3bc8488b899627f957e5561786d6f868`.
NBA asset 151,222 bytes, SHA256:
`0cee10c154e9f4d678a05ef758cf7e239da363e5db19fa5c51ab8b3f1f1deeeb`.
All seven static assets matched `git show eca2a06:web/<asset>` bytes.

Independent public Chromium 154 checks ran 01:29:21.763192–01:29:58.168980 UTC at
1440px desktop and 390/320px mobile. All seven routes/direct reloads, fourteen
category filters, six original historical bundles/84 PMFs and six statistical
grades passed. Performance now publicly shows the one actual R0 reconstruction
group with full eight-field model/lane identity; mixed groups remain synthetic
test cases. History uses the neutral past-event wording. Exact original
event/cutoff/issue/grade identities were retained. Upcoming correctly explains
its three missing-input/issuance reasons. SINGLE/SELECTED/ALL scopes, every 2–6-leg
size and OVER_ONLY/UNDER_ONLY/MIXED passed all 45 combinations with zero candidates,
NO_ACTION and Not issued. There were no page errors, failed HTTP responses or
requests outside the repository prefix. Browser rendering used only the
process-local configured-proxy CA SPKI pin; urllib independently verified TLS.
No persistent trust settings changed.

Separate offline verification at 01:32:36 UTC reproduced the manifest and NBA
asset exactly from main code/config/web/records at the served publication clock,
with no model generation or external requests. It checked the four guarded-helper
and three browser artifact hashes, original record bindings, and deployment to
HTTP/browser to receipt clock order. All checks passed.

All 18 original ledger files/175,190 bytes, their original clocks, the v1
publication summary and frozen R0/DEV002/DEV003 evidence are unchanged. These six
forecasts remain **historical reconstructions**, actually issued October 20, 2026
for November 24, 2025 events. Their statistical grades are separate from venue
financial settlement. Deployment performed no model evaluation, source capture,
genuine future issuance, outcome grading or ticket creation. No qualified ticket,
confirmatory skill, admission of a prospective producer or financial result is
claimed. NFL and MLB remained untouched; no new paid services, signups or keys.

Durable combined evidence:
`evidence/deployment/2026-10-20-pr4-pages.json`, payload SHA256
`0d84bfb41a10c1f67a46e8cc258ce1fdccbccd4f3e2a2d5a80067a23016c6299`.
This post-deployment documentation checkpoint is on `docs/pr4-deployment`, based
on deployed main eca2a06. It changes only HANDOFF_STATUS.md, PROJECT_CONTEXT.md,
docs/VERIFICATION.md, docs/UI_NOTES.md, MANIFEST.sha256 and that new receipt;
it is separate from the approved application merge. Resolve its exact commit
with `git log -1 --format=%H docs/pr4-deployment`. Earlier branch-only/open-PR
statements below describe the prior checkpoint and are superseded here.

Commands actually run (the receipt records HTTP/browser methods and all hashes):

```bash
PATH=/tmp/nml-pr-completion/bin:$PATH python3 /tmp/nml-pr-completion/pr_watch.py --target /workspace/Nicks-multisport-lab-project=4 --mode until-actionable --interval 15 --timeout 180 --cursor /tmp/nml-pr-completion/pr4-cursor.json --observations-file /tmp/nml-pr-completion/pr4-observations.ndjson --pretty
PATH=/tmp/nml-pr-completion/bin:$PATH python3 /tmp/nml-pr-completion/pr_land.py --repo /workspace/Nicks-multisport-lab-project --pr 4 --head 1f80112ed54a8c2eaa20024e806054739b815c98 --mode auto --method merge --pretty
PATH=/tmp/nml-pr-completion/bin:$PATH python3 /tmp/nml-pr-completion/pr_land.py --repo /workspace/Nicks-multisport-lab-project --pr 4 --head 1f80112ed54a8c2eaa20024e806054739b815c98 --mode auto --method merge --policy-digest 70b3b0605cddc6f2e6abe9331942e469e32758fbc1abb1474b3af09fdda825df --confirm --pretty
gh run view 39353520895 --repo NickNicky19/Nicks-multisport-lab-project --json status,conclusion,jobs,headSha,url,createdAt,updatedAt
PYTHONPATH=. python3 /tmp/nml-pr4-pages-audit.py
python3 /tmp/nml-public-pr4-qa.py eca2a0679bd99eaff77c1c0785df13840fb99762 > /tmp/nml-public-pr4-qa.log 2>&1
sha256sum --check MANIFEST.sha256
git diff --check
```

Next concrete task: revalidate the first as-observed event 401909088/start 19:00Z
and a permitted selected-player/history route before its as-observed 17:30Z T90.
Current status, player universe, history freshness/lineage, permission and an
admitted current-T90 producer remain unresolved. The reported-clock audit below
does not admit a forecast. Do not backdate issuance or schedule a collector.
Any further development comparison needs a separately frozen protocol; retain
tail/coverage concerns and the separate confirmatory holdout. K0 remains an
unpromoted development challenger and exact-duration REB requirements remain open.

## Prior deployment and implementation checkpoint — 2026-10-20 01:02–01:23 UTC

Deployment/status checkpoint committed/pushed as
`ff0cb00a2833bf7d3e889652157292df5a87a95d` on the separate follow-up branch.
The approved deployed main below remains unchanged.

**Follow-up application checkpoint:** committed/pushed as
**73dd8a5a15fd5ffa2e49513daa19546cdba91b13** on
`implementation/recovery-and-evidence-groups`;
[PR #4](https://github.com/NickNicky19/Nicks-multisport-lab-project/pull/4) is open.
[Workflow39352862246](https://github.com/NickNicky19/Nicks-multisport-lab-project/actions/runs/39352862246)
passed177Python/31frontend tests, demo, build/artifact checks; deploy skipped by
the non-main guard. Guarded watcher reported ready, clean/mergeable, zero
unresolved review threads, no auto-merge. Exact package files/commits:
`git diff --name-status 002a6b9 73dd8a5` and the checkpoint commits below.
No PR #4 landing/deployment is claimed; PR #3 approval applied only to its2d30
head. The public site remains main002a6b9, independently verified above/below.

Independent fresh remote checkout at73dd8a5, checked01:22:22.917014 UTC, matched
46 evidence/record/source files including all18 original records /175,190bytes
and the frozen DEV003 source fingerprints. An isolated new process recovered
the actual six-bundle/six-outcome/six-grade ledger and existing v1 summary with
raw inputs absent and model/panel generation forbidden. All original clocks and
bytes stayed intact. Proof/hashes/commands:
`evidence/research/2026-10-20-followup-remote-check.json`. This is Git retention
and recovery evidence, not another model run, deployment, future issuance,
permission or statistical qualification. A documentation-only follow-up records
this final checkpoint; final live PR head/check state is reported by the watcher.

**Completed DEV003 continuation:** new DEV003 specification was frozen at
`2026-10-20T01:09:19.742752Z`, protocol payloadSHA
`06600825f5c64f396315c29251516da72133f659efca6e3f72a7a2ab7c3322db`.
New files: `multisport_lab/development_003.py`, `tests/test_development_003.py`,
`docs/NBA_DEVELOPMENT_003.md`, `evidence/research/dev003-inventory.json`,
`evidence/research/dev003-protocol.json`. The fixed input is unchanged;12week
hashed-ID selection gives24 complete games/517 appearances, nine true n0 cases.
One K0 lagged-workload-prior challenger uses donor-specific prior T90/daily-freeze
contexts, fixed8-minute bandwidth/0.25 league floor, unchanged R0 personal
weights/5-prior mass and exact n0 fallback. All14 outcomes stay coherent.
Two games/42rows overlap exposedDEV002; no confirmation/model-selection or
promotion is authorized. Independent pre-scoring review checked exact game list,
cohort hash, all8 executed source/test hashes, equations and synthetic causal
tests. Frozen source/tests/protocol were committed and pushed before execution
as **2b58ac45c7ec29fa0cba2c41facd3862c137a961**. Exactly one authorized run
completed01:11:10.705240–01:14:56.988909 UTC:517 appearances under each of R0,
L0 and K0,24games/12weeks,508kernel cases/nine exact R0 cold-start fallbacks,
zero post-score exclusions,226.283679 wall seconds/169,436KiB peak RSS. Results:
`evidence/research/dev003-results.json`, payloadSHA
`e02454af951c9af4efb3491a23329e1d78574805e7b2f108172205ed850b3fb7`.
All14 per-category scores/intervals/zero/tail/log/workload/subgroup diagnostics
are in `docs/NBA_DEVELOPMENT_003.md` and the receipt. K0 rawCRPS was lower in13
categories; TD worsened slightly, with only two observed TDs, and TD/DD/BLK paired
intervals cross zero. All models retain infinite log losses for oneBLK/twoPRA
outcomes. K0 minute95% coverage worsened to0.938104 versus R0 0.947776 and K0
predicted mass0.964426. No confirmation, model selection, calibrated probability,
promotion, product qualification or future paper evidence follows. Independent
review reproduced3,018 aggregate/bootstrap checks from retained weekly summaries
without model reruns (largest difference2.27e-13). No executed code/test/protocol
changed after scoring began. Existing R0/DEV002 and18 ledger bytes are unchanged.

**Follow-up fixes and future-input checkpoint:** `record_reference.py` now writes
v2 only for a batch without an existing summary, copying each original record's
source/receipt/model/input/issue/grade metadata. Mixed retained/new outcome clocks
stay individual; the common clock appears only when all agree. Recovery verifies
both v1/v2 exact references, identities, grade dependencies and chronology.
Synthetic interruption before summary and partial1-old/5-new-outcome recovery
passed. Actual v1 summary and all18 original receipts remain byte-identical.
See `tests/test_record_reference.py`, `docs/REFERENCE_PUBLICATION_002.md`.
Core follow-up fixes were committed/pushed as
**d4fad699a5da11cc3e6847a55040589642cf8a35** (17files; `git show --stat d4fad69`).

Performance now groups by league, lane, exact model version/commit/code hash,
conditioning and period/OT. History includes past captured forecasts while
retaining their lane and avoiding a completion claim from start time alone.
31 frontend checks and local Chromium1440/390/320px passed, including real6/84/6
records and a clearly synthetic mixed4-record/3-group fixture. This follow-up UI
is branch-only; the public site remains the approved002a6b9 implementation.

New `nba_inputs.py` and12 focused tests implement a bounded offline readiness
contract/CLI with exact event/version/player/team/source identity, hashes, clocks,
coverage and lagged complete counts. Structural success explicitly remains
NOT_ADMITTED, with no source authenticity/permission or prospective producer
claim. No capture, forecast or source network request is made. Actual diagnostic
commands and limits are in `docs/PREGAME_INPUT_READINESS.md`; current172 Python
tests and synthetic demo passed at that checkpoint; final suite now passes177.
New evidence:
`evidence/data/2026-10-20-input-readiness.json` and the scoped clarification
`2026-10-20-input-readiness-v2.json`. The latter is authoritative: an archive
alone is not a prospective bundle; its old statistics can still be eligible for
a later future event when actual source observations precede that event's bounds.
No event-specific future-history timing audit is claimed. The readiness pilot's
20k rows/8MiB metadata cannot silently replace the complete26,645-row R0 cohort.

The retained-source discovery audit in
`evidence/data/2026-10-20-pregame-discovery.json` verified two original captures /
142,589 bytes without new HTTP. As observed October19, three games were scheduled
for October20 19:00Z,23:00Z and October21 01:30Z; exact ESPN IDs/start/team/status
were retained. No explicit roster/player boxscore or leader athlete IDs exist;
two injury IDs do not establish a pregame candidate universe. Source event-update
clocks remain unknown. Earliest **as-observed** T90 is October20 17:30Z and needs
fresh event/player/source revalidation before use; no scheduler or future issue
is enabled. Permission, complete input provenance and admitted current-T90
producer remain unresolved independently of prices.

A separate actual **event-specific history timing audit**, checked01:16:19 UTC,
now fills that earlier NOT_EVALUATED timing gap without changing either prior
diagnostic: `evidence/data/2026-10-20-future-history-timing.json`. All26,645 rows
were validated under the existing64MiB/100k importer, not truncated to the20k
readiness pilot. The reported October19 player/schedule observations precede all
three as-captured freezes/cutoffs; old event starts and reconstructed completion
bounds also pass. Status is only REPORTED_CLOCK_CONSISTENCY_PASS. Current event
status, selected-player universe, history freshness/lineage, source authenticity,
permission and current-T90 producer remain unverified; no future admission or
capture/forecast/grade was created. At audit time all three T90 windows were
still in the future. Independent metadata-only recomputation matched every
substantive report field;17 focused readiness/timing tests passed.

Additional commands actually run:

```bash
python3 -m multisport_lab.development_003 --input /tmp/nml-nba-audit/normalized.jsonl --output evidence/research/dev003-inventory.json --inventory-only
python3 -m multisport_lab.development_003 --input /tmp/nml-nba-audit/normalized.jsonl --output evidence/research/dev003-results.json --protocol evidence/research/dev003-protocol.json
python3 -m multisport_lab.nba_inputs archive-diagnostic --panel /tmp/nml-nba-audit/normalized.jsonl --source-receipts evidence/data/2026-10-19-source-receipts.json
python3 -m multisport_lab.nba_inputs history-timing --panel /tmp/nml-nba-audit/normalized.jsonl --source-receipts evidence/data/2026-10-19-source-receipts.json --discovery evidence/data/2026-10-20-pregame-discovery.json
python3 -m unittest discover -s tests -v
python3 -m multisport_lab.demo
node --test --test-isolation=none web/tests/*.test.mjs
python3 -m multisport_lab.publication --build-commit d4fad699a5da11cc3e6847a55040589642cf8a35
node web/tests/site-smoke.mjs output
python3 web/tests/browser_smoke.py output --screenshots /tmp/nml-followup-final-ui
```

Next concrete work: review/land this separate follow-up only under its own exact
head authorization; revalidate the first as-observed event401909088/start19:00Z
and permitted selected-player/history source route before17:30Z T90. That clock
is a captured schedule assumption, not a currently verified deadline. Establish
the admitted producer/full history budget/provenance first; do not backdate an
issue, treat two injury IDs as a roster, or schedule a collector. Keep future
statistical grades separate from later venue financial settlement. Research next
needs independently frozen tail/coverage and confirmation guards; favorable
development CRPS does not promote K0 or unblock the precise-duration REB design.

**PR #3 is merged and typed v2 is deployed.** The user approved only head
`2d30ae98b20918bc97ea9eda4578ef0c8d509d71`. A fresh guarded watcher confirmed
that exact head ready, clean/mergeable, build passed, no pending checks, no
missing required reviewers and zero unresolved threads. The canonical helper
used policy digest `70b3b0605cddc6f2e6abe9331942e469e32758fbc1abb1474b3af09fdda825df`,
normal merge method, no admin/bypass/force-push, and the exact-head merge watcher
observed MERGED. Actual main merge commit:
**`002a6b994c862c758f1d7c8199831c75eff761af`**, merged 2026-10-20 00:59:09 UTC.

Live site: https://nicknicky19.github.io/Nicks-multisport-lab-project/ .
[Workflow39350851916](https://github.com/NickNicky19/Nicks-multisport-lab-project/actions/runs/39350851916)
completed successfully; build/deploy passed, deployment completed00:59:52 UTC.
System-CA HTTPS returned200 for root, manifest, NBA asset and seven static assets.
The served build commit is the exact main merge above; every static asset matched
`git show 002a6b9:web/<asset>` bytes. Public snapshot:
`45f9c2d7cf10baf00ace7b399f948e91d95c0e14fc5dbf494b8191af24ce7ae5`.
Manifest raw SHA256:
`957520ca4128a3c86c0d64fdd1f50bf5a682cfdb26f37a0cd8a57c9d7b392cc6`.
NBA asset151,222 bytes, SHA256:
`e33696949bb60d07643682748701011f864930919dccde6ba270d639b4c54789`.

Independent public Chromium154 checks,01:01:39.714719–01:02:10.831386 UTC,
passed1440px desktop/390px/320px mobile, all seven routes/direct reloads,
84 PMFs across six original bundles, all14 category filters, six separate
statistical grade records and exact event/cutoff/actual-issue/grade identities.
Upcoming has no forecasts and three specific missing-input/issuance reasons.
SINGLE/SELECTED/ALL scopes, every2–6-leg size and all three directions passed
45 builder combinations, with zero admitted candidates, NO_ACTION and Not issued.
No JS errors, failedHTTP requests or URLs outside the repository prefix occurred.
Browser trust used only the process-local configured-proxy CA SPKI pin;
independent urllib used verified system HTTPS. No persistent trust/HOME changes.

All18 original ledger records and exported bundles/grades match committed main
bytes and clocks. These are six **historical reconstructions** issued October20
for November24,2025 games, with retrospective source observations and statistical
forecast grades. No genuine future forecast, actual issued/settled paper ticket,
financial settlement, qualified pick or confirmatory model quality is claimed.

Exact commands, workflow jobs, public hashes, original record clocks and browser
results: `evidence/deployment/2026-10-20-pr3-pages.json`. Deployment changed main
through the merge only; this status follow-up changes HANDOFF_STATUS.md,
PROJECT_CONTEXT.md, README.md, docs/VERIFICATION.md, MANIFEST.sha256 and the new
deployment receipt. Existing R0/DEV002/eighteen ledger receipts are unchanged.

Commands actually run:

```bash
PATH=/tmp/nml-pr-completion/bin:$PATH python3 /tmp/nml-pr-completion/pr_watch.py --target /workspace/Nicks-multisport-lab-project=3 --mode until-actionable --interval 15 --timeout 180 --cursor /tmp/nml-pr-completion/pr3-cursor.json --observations-file /tmp/nml-pr-completion/pr3-observations.ndjson --pretty
PATH=/tmp/nml-pr-completion/bin:$PATH python3 /tmp/nml-pr-completion/pr_land.py --repo /workspace/Nicks-multisport-lab-project --pr 3 --head 2d30ae98b20918bc97ea9eda4578ef0c8d509d71 --mode auto --method merge --pretty
PATH=/tmp/nml-pr-completion/bin:$PATH python3 /tmp/nml-pr-completion/pr_land.py --repo /workspace/Nicks-multisport-lab-project --pr 3 --head 2d30ae98b20918bc97ea9eda4578ef0c8d509d71 --mode auto --method merge --policy-digest 70b3b0605cddc6f2e6abe9331942e469e32758fbc1abb1474b3af09fdda825df --confirm --pretty
PATH=/tmp/nml-pr-completion/bin:$PATH python3 /tmp/nml-pr-completion/pr_watch.py --target /workspace/Nicks-multisport-lab-project=3 --await-merge 2d30ae98b20918bc97ea9eda4578ef0c8d509d71 --await-merge-mode auto --await-merge-since 2026-10-20T00:59:10.831382Z --mode until-actionable --interval 10 --timeout 180 --cursor /tmp/nml-pr-completion/pr3-cursor.json --observations-file /tmp/nml-pr-completion/pr3-observations.ndjson --pretty
git fetch origin main
git switch main
git merge --ff-only origin/main
git switch -c implementation/recovery-and-evidence-groups
```

Read-only workflow/HTTPS/browser commands and their exact programs/outputs are
retained in the deployment receipt. Main's workflow reran142Python/25frontend
tests and demo/build successfully; deployment verification did not rerun any
statistical evaluation or generate new forecasts/outcomes.

Next package is isolated on **implementation/recovery-and-evidence-groups**,
based on002a6b9. Carry both user review findings: interrupted publication summary
must preserve original outcome clocks and validate every referenced record;
Performance must separate lanes/models and History must describe past prospective
records accurately before those records are admitted. Bounded coherent NBA
development and offline pregame-input readiness work continue; no new paid
service/signup/key, source collector, NFL/MLB mutation or prospective result.

## Previous implementation checkpoint — 2026-10-20

PR #2 was reviewed and merged through the guarded workflow at authorized head
`05643e1f9f3a60c457357b301d3021f670629b70`; main advanced to
`e9bfa4ce7ec07b57dc5688bd592fd2e61d45f7ba`. New work is on
`implementation/typed-research-ledger` with one integration owner.

Implementation package committed/pushed as **900a7df5ed5270ec6e32054cfa7e6bb2bf29dec7**
(58 files; exact inventory: `git show --stat 900a7df`).
[PR #3](https://github.com/NickNicky19/Nicks-multisport-lab-project/pull/3) is open.
[GitHub build39347811263](https://github.com/NickNicky19/Nicks-multisport-lab-project/actions/runs/39347811263)
passed for that exact head; deploy was skipped by the non-main guard. Guarded
watcher reported ready, clean/mergeable, zero unresolved review threads, no
auto-merge configured. A documentation-only follow-up records this checkpoint.

**Remote durability verified:** independent fresh HTTPS checkout of this same
repository at900a7df matched all18 original record files /175,190 bytes. An
isolated fresh Python process loaded the checkout's modules, blocked reads of the
integration/raw-data directories and recovered every schema/hash/reference/grade
and original clock with a missing raw input path. No forecasts were regenerated.
Exact commands, per-file hashes and readback clocks are in
`evidence/research/2026-10-20-remote-ledger.json`; verification completed
2026-10-20 00:29:44.860776 UTC. Persisted local-receipt labels remain honest;
this separately observed remote Git checkpoint establishes retention. It is not
source authenticity, historical as-of evidence or genuine future issuance.

Current published main is **e9bfa4ce7ec07b57dc5688bd592fd2e61d45f7ba**:
[workflow39345735154](https://github.com/NickNicky19/Nicks-multisport-lab-project/actions/runs/39345735154)
build/deploy succeeded, deployment completed 2026-10-20 00:07:45 UTC. Public
root/manifest/NBA asset/app modules returned HTTP200 with verified HTTPS and
matching commit/hashes at00:23:44 UTC. See
`evidence/deployment/2026-10-20-pr2-pages.json`. This is deployed **v1**; the new
typed feature remains branch-only until its separately verified rollout.

Import findings A/B are fixed in **`cde185088f032db587e1fb10845cd84541ef0a8b`**:
`multisport_lab/nba_data.py`, `multisport_lab/offer_import.py`, their tests and
`docs/NBA_IMPORT_VALIDATION.md`, `docs/SLEEPER_IMPORT_VALIDATION.md`.
The exact reproducers failed before fixes and pass after; 101 Python tests and
synthetic demo passed. FGM must equal FG2M+FG3M whenever known, and a Sleeper
player identity requires matching explicit row/option player subject types.
Recognized teams are classified separately; missing/conflicting types diagnosed.

The retained 26,645-row panel has zero FGM component contradictions, and every
NBA subject in the prior real Sleeper sample explicitly says player. Neither
finding establishes corrupted saved evidence. Frozen R0 protocol/pilot receipt
bytes remain unchanged; no original pilot evaluation was rerun.

Typed exports, immutable issuance/outcome/grading records and frontend v2 are
implemented on this branch. Python/frontend validate the same fourteen-category
contract, period/OT, exact identities, microsecond clocks, PMFs and scores. Six
deterministically selected **historical reconstructions** were actually generated
2026-10-20 00:21:42.792328–00:21:48.758578 UTC for three 2025-11-24 games. Their
already exposed outcomes make these engineering examples, not a new holdout.
Eighteen create-only ledger receipts total 175,190 bytes. Restart/readback and
idempotent recovery preserve every original clock/hash; commit/push/fresh remote
readback is verified separately above. No actual future issuance,
paper-ticket outcome or financial settlement exists.

The static build reads saved records without running a model or fetching sources.
History has 84 marginal PMFs and six separately scored forecast records. Upcoming
explains that no admitted pregame candidate universe/observed-input producer and
genuine T90 capture exist. Current R0 explicitly rejects REAL_TIME issuance.
Active correction chains prevent superseded forecasts/outcomes/grades from being
double-counted; original receipts remain immutable and readable. The builder
retains scopes, 2–6 legs, all directions, smaller-ticket/NO_ACTION behavior.

DEV002 was frozen before one run: eight full UTC weeks, 16 fixed games /338
appearances, all 13+PA, fixed R0 versus league-only L0, shared T90/daily freeze,
reconstructed start+24h history and 2,000 paired week-bootstrap draws. Runtime
156.871699 seconds; peak RSS 96,232 KiB; no post-score exclusions/tuning. R0 CRPS
was descriptively lower in 13 categories; TD worsened (only one TD observed),
delta +0.0002771724865 with 95% week CI [0.000001325405,0.000587670881]. PR had
one zero-support log outcome in both models, so infinite aggregate log loss was
retained. These sparse selected games establish no confirmatory quality or
product qualification. The separate exact-duration REB experiment remains blocked.

OFFER-PILOT-002 used four bounded ordinary GETs, all200, 3.367 MB. The **correct
full inherited NBA `propBets` route and both declared pages** returned 1,135 ESPN
items, 48 type/name families, 12 requested families plus PA (TOV absent this
event). Provider ref verified DraftKings; prices exist but side, period/OT and
settlement meaning remain unresolved, and 138 update clocks exceeded capture.
Sleeper returned 675 NBA rows /1,350 options with matching player subject types,
nine families; absent families are snapshot-specific. Zero complete usable
quotes, qualified contracts/tickets or source-automation permission are claimed.

Exact package file inventory is `git diff --name-status cde1850 900a7df`: new typed forecast,
ledger, fixed-publication command, DEV002 modules/tests; `records/`; publication
and web validators/renderers/tests; capability/inventory and research docs; new
offer/development/publication receipts. See `docs/FORECAST_CONTRACT.md`,
`docs/DURABLE_LEDGER.md`, `docs/REFERENCE_PUBLICATION_002.md`,
`docs/NBA_DEVELOPMENT_002.md`, `docs/OFFER_PILOT_002.md` for exact contracts and
source/execution hashes. Original R0 receipt bytes remain unchanged.

Current package verification: 142 Python tests, synthetic demo, 25 frontend tests,
artifact checks and actual-history Chromium at 1440/390/320px passed. Actual
artifact was 151,222 bytes after the source-description refresh, below512 KiB.
Final committed900a7df artifact/Chromium checks passed; all seven routes/reloads,
all84 PMFs, category filtering, exact
event/cutoff/issue IDs, grades/NOT_EVALUATED, empty future and builder scopes were
checked. An independent read-only review checked actual source rows, cutoff
input hashes, model code, ledger recovery and bootstrap arithmetic without
rerunning old R0 or DEV002 forecasts. These are distinct evidence lanes.

Commands used for this package (plus the earlier required checks below):

```bash
python3 -m multisport_lab.development_002 --input /tmp/nml-nba-audit/normalized.jsonl --output evidence/research/dev002-results.json --protocol evidence/research/dev002-protocol.json
python3 -m multisport_lab.record_reference --input /tmp/nml-nba-audit/normalized.jsonl --model-commit cde185088f032db587e1fb10845cd84541ef0a8b
python3 -m unittest discover -s tests -v
python3 -m multisport_lab.demo
node --test --test-isolation=none web/tests/*.test.mjs
python3 -m multisport_lab.publication --build-commit cde185088f032db587e1fb10845cd84541ef0a8b
node web/tests/site-smoke.mjs output
python3 web/tests/browser_smoke.py output --screenshots /tmp/nicks-multisport-real-research-002
python3 -m multisport_lab.publication --build-commit 900a7df5ed5270ec6e32054cfa7e6bb2bf29dec7
python3 web/tests/browser_smoke.py output --screenshots /tmp/nml-final-typed-900a
```

The final browser command initially lacked sandbox localhost socket access;
rerunning with network-enabled execution passed. No application fix or trust
store change was required. Remote readback used `git clone --depth 1
--single-branch --branch implementation/typed-research-ledger <existing-origin>`
and the isolated verification program retained in its evidence JSON.

Remaining: publish this feature only after its PR/checks/authorized landing and
main Pages verification. Current live
site and deployment PR #2 are separate from local typed v2. Next research task is
a new frozen challenger protocol with broader/sparser-category guards and an
independently unexamined confirmation window; next future-input task is a permitted
observed pregame universe/capture producer, not relabeling an archive. Exact
provider semantics/identity/rules and ongoing permission remain admission blockers.
Ledger limits are 512 receipt files /32 MiB total /4 MiB per file, checked before
new writes and before recovery decoding. Identical retries work at capacity;
expansion needs a versioned retention decision rather than deleting originals.

Next concrete integration task: obtain the new PR's exact-head landing approval,
use the guarded helper, observe merge, then verify main build/deploy and public
typed manifest/asset hashes. PR #2 authorization was used only for PR #2. Until
then the live v1 site and locally/GitHub-tested typed v2 branch are distinct.

## Prior implementation and deployment history

- Exact repository: `NickNicky19/Nicks-multisport-lab-project`.
- Observed starting `main` / `origin/main`: `de86e92352f0fb5a76831275f6de6b256ce05434`.
- Implementation commit: **`243bc9e495f25906216f1a438cb060ec64de3f7c`**.
- Landed branch: **`implementation/nba-foundation`**.
- [PR #1](https://github.com/NickNicky19/Nicks-multisport-lab-project/pull/1) merged
  on 2026-10-19 at 23:23:30 UTC, after the user explicitly requested deployment of
  its exact head `6c6647108a7e807046aecc5ce93e28dda7b95618`.
- Deployed `main` commit: **`5d19fa344de5ceaa6e7cc550f0ac8ac832458202`**.
  Guarded helper/watchers verified ready → landing requested → merged, with a
  normal merge commit preserving history, no admin bypass or force-push.
- This deployment-record update is on `docs/pages-deployment`; it does not alter
  the deployed application or the source/model/product qualification gates.
- Earlier feature-branch CI revision: `70b74ed49c458fbcc61715df0d26a3f95c983b15`.
  Both [branch run](https://github.com/NickNicky19/Nicks-multisport-lab-project/actions/runs/39339596935)
  and [PR run](https://github.com/NickNicky19/Nicks-multisport-lab-project/actions/runs/39339634821)
  completed successfully, including checks, build and artifact upload. Deploy was
  **skipped** by the non-main guard at that earlier checkpoint. The main run and
  completed deployment are recorded in the verified Pages section below.
- Workspace originally had no project checkout. Cloned the existing remote into
  `/workspace/Nicks-multisport-lab-project`; initial tree clean, no workflows.
  Re-fetched before integration: remote main remained at the starting SHA.
- No reset, older ZIP import, replacement remote, force-push or external NFL/MLB
  writes/session contact/workflow triggers occurred. Original bootstrap
  `042bedaa73e36033eb30885af06c79bea0bd4f6b` remains ancestry/provenance only.
- One root integration owner. Bounded data, offers, baseline, frontend, paper and
  independent-review agents completed their packages; no recurring agents/jobs.

## What changed

`git show --stat 243bc9e495f25906216f1a438cb060ec64de3f7c` is the exact file list
(50 files). Main implementation groups:

- `multisport_lab/nba_data.py`, `scripts/prepare_nba_panel.py`: namespaced data,
  DNP/zero/missing distinctions, schedule joins, field audits and offline panel replay.
- `multisport_lab/baseline.py`, `research_pilot.py`: complete-line empirical R0,
  same-outcome scoring/sums/DD/TD, all 13 requested categories plus PA, timing and
  per-category development diagnostics. No independent marginal splicing.
- `multisport_lab/offer_import.py`: bounded authorized local JSON imports,
  observed Sleeper shape, exact decimal/provenance checks and explicit diagnostics.
- `multisport_lab/paper.py`: 2–6-leg manual research contracts, common clock,
  scope/direction/eligibility/horizon gates, supplied terms/joint-state arithmetic,
  six-first complete-ticket assessment with smaller sizes/NO_ACTION.
- `multisport_lab/publication.py`, `web/`, `.github/workflows/pages.yml`:
  bounded content-addressed research catalog export, responsive seven-view UI,
  shared SINGLE/SELECTED/ALL scope, artifact checks and dependent Pages workflow.
- `tests/`: concrete integrity/timing/identity/payout/coherence/export risks.
- `DATA_FEASIBILITY.md`, `docs/{DECISIONS,BASELINE_REFERENCE,OFFER_INVENTORY,
  PAPER_CONTRACT,PUBLICATION_SCHEMA,UI_NOTES}.md`, `evidence/`: decisions and
  real aggregate evidence. Configs, README, verification/source/website docs and
  checksums updated. Raw source responses are excluded from Git and site output.

## Evidence lanes and actual results

| Layer | Observed result | Limits |
| --- | --- | --- |
| Original software baseline | 28 tests passed; synthetic demo exit 0 | No statistical evidence |
| Final local software and CI | **94 Python tests**, **14 named Node tests**, demo, checksum and whitespace checks passed; branch and PR check/build jobs succeeded | Synthetic checks establish specified behavior only |
| Real statistical data | 34,883 roster rows audited; 33 invalid identities quarantined; strict schedule joins; one primary game reconciled on 300 count comparisons and 27 participation states | One ending-year archive; primary reconciliation covers one game; no verified historical feature clocks or ongoing-use rights |
| Reproducible panel | 26,645 source-stage-2 standard-team complete appearances; offline replay reproduces **14,720,351 bytes** and SHA `489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c` | DNP/unknowns not zeros; 104 rounded-zero appearances retained; source stage2 can include Cup final |
| R0 development evaluation | Frozen before scoring; 200 appearances/200 players/nine games, actual date 2025-10-28, 16 cold starts, two rounded-zero appearances; 22.776781 s / 77,204 KiB | Registered Oct28/29 had 411 candidates; 211 omitted by fixed upfront cap; no post-score exclusions. Historical appearance-conditioned development only, no holdout/promotion |
| Per-category results | All 13 + PA scored separately; PTS RPS 4.267494, REB 1.661492, DD Brier 0.070140, TD Brier 0.002640; complete table/interval/zero/log diagnostics retained | Unseen-support infinite log losses retained. DD 18 positives, TD one positive: no rare-event qualification or aggregate accuracy claim |
| Actual offers | Sleeper: 657 NBA rows / 1,314 options / nine observed families. ESPN current Draft Kings label and game/team prices observed; attempted player route 404 | Four requested families absent only in this snapshot; complete paging, period/OT/start/crosswalk/entry rules unverified. Zero complete actual contracts/quotes/qualified candidates |
| Website local | Built under repository prefix; Chromium 154 desktop/390px/320px, seven routes/direct reloads, scopes/builder, errors/hash/retention checked | Research inventory and empty collections only; no public forecasts/picks or qualified tickets |
| Future paper evidence | No issued paper ticket, completed future grade or return | Real offer capture is not a frozen model/ticket/settlement record |
| Product qualification | **Unavailable**; production/live/priced-selection gates disabled | Generic supplied terms and independence assumptions do not certify providers |
| Deployment | **Deployed and public HTTP/browser verified** at 2026-10-19 23:25:46 UTC; main build/deploy succeeded | Research inventory and empty states only; no model/product qualification follows |

Exact source routes/clocks/hash/missingness/budgets: [data report](DATA_FEASIBILITY.md)
and [offer inventory](docs/OFFER_INVENTORY.md). Full results and protocol:
[reference report](docs/BASELINE_REFERENCE.md),
[pre-scoring receipt](evidence/research/r0-protocol.json),
[aggregate pilot receipt](evidence/research/r0-pilot.json).
The run occurred on a dirty implementation tree based on the handoff SHA; the
receipt preserves exact executed source hashes, which match the committed files.
No score/evaluator code changed after results. It does not backdate issuance.
Independent review reproduced schedule joins, actual offer import counts, receipt
integrity, code hashes and all category sample counts without rerunning scores.

## Earlier Pages verification — 2026-10-19

Live research site: **[Nick’s Multisport Lab](https://nicknicky19.github.io/Nicks-multisport-lab-project/)**.
[Main workflow 39341268746](https://github.com/NickNicky19/Nicks-multisport-lab-project/actions/runs/39341268746)
succeeded in build and deploy; deployment completed 2026-10-19 23:23:58 UTC.
Root, manifest and NBA asset returned HTTP 200 using system-verified HTTPS. The
served manifest identifies main commit `5d19fa344de5ceaa6e7cc550f0ac8ac832458202`,
snapshot `ea7d3bb77ad9e112f8f0f5d5522c01d0ff3f7362869b659cd3e0a1130da84019`,
and its NBA asset hash matched. The owner’s GitHub Actions source setting resolved
the earlier integration-only setup blocker; no further Pages setting is pending.

Independent public Chromium checks passed desktop, 390px and 320px, all seven
routes/direct reloads, repository-prefix assets, shared scope, all 2–6-leg sizes
and three direction modes with honest NO_ACTION/not-issued states. Public QA used
a temporary process-only exception pinned to the configured proxy CA for browser
rendering, with independent urllib HTTPS verification. No persistent trust or
HOME change occurred. Full bounded evidence:
[evidence/deployment/2026-10-19-pages.json](evidence/deployment/2026-10-19-pages.json).
No statistical evaluation, quotes, qualification or future paper outcomes changed.

## Earlier commands actually run — 2026-10-19

From this repository root (raw-file paths are local, not durable storage):

```bash
python3 -m unittest discover -s tests -v
python3 -m multisport_lab.demo
node --test --test-isolation=none web/tests/*.test.mjs
python3 -m multisport_lab.publication --build-commit "$(git rev-parse HEAD)"
node web/tests/site-smoke.mjs output
python3 web/tests/browser_smoke.py output --screenshots /tmp/nml-final-ui
sha256sum --check MANIFEST.sha256
git diff --check
```

The exact one-time pilot invocation is retained in `r0-pilot.json` and copied in
`docs/BASELINE_REFERENCE.md`; do not re-run it to select a better result or replace
its create-only receipt. Inventory-only validates inputs without scoring. The
preparation command and exact byte-for-byte replay appear in `DATA_FEASIBILITY.md`.
Actual local offer import returned `partial: 1314 observations, 0 diagnostics`;
zero qualification. The audit used ordinary bounded public GETs with no new key,
account, paid service or access bypass. No collector/scheduler was enabled.

## Earlier next tasks — superseded by the current checkpoint above

1. **PR #1 is merged and its research site is deployed.** The deployment record
   is a documentation-only follow-up; it does not require a new application rollout.
2. **Pages setting complete:** Source is GitHub Actions, HTTPS enforced, and
   workflow plus public manifest commit/hash/routes verified. Preserve the checked
   static artifact path and main-only deployment guard for subsequent releases.
3. **Next local implementation package:** version typed event/forecast records
   for research-only static export, retaining exact identities, real issuance,
   input hashes, conditioning and independent gates. Current v1 deliberately
   rejects all nonempty observations. A browser draft is not an evidence ledger.
4. **Source/product blockers:** permitted complete full-game captures, identity
   crosswalks, paging/period/OT, actual payout/settlement/eligibility and durable
   authorized future capture retention. Reviewed source terms do not establish
   ongoing automated access; use authorized local capture import meanwhile.
5. **Scientific blockers:** REB duration/share protocol remains proposed: rounded
   minutes, incomplete precise duration coverage and unfrozen confirmation guards
   prevent B0/B1/C1 execution. R0 has finite tails, no role/pace adjustment or
   participation/cross-player model. Establish new frozen development/challenger
   and genuinely unexamined/future confirmation protocol before accuracy claims.

Keep current raw/normalized files under `/tmp` or ignored `.local-data`; they may
vanish with this environment. Public summaries and immutable hashes survive in
Git, but they are not a signed source or a durable raw-capture store. Preserve all
13-category and future-sport goals, and leave the independent NFL/MLB projects
untouched. Future outcomes must be appended when events actually occur.

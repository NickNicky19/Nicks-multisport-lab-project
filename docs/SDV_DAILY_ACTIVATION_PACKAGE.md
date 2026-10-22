# Daily-snapshot release and first-cycle decision

Status: **IMPLEMENTED CANDIDATE; NOT ACTIVATED OR DEPLOYED**. Review is PR #13:
https://github.com/NickNicky19/Nicks-multisport-lab-project/pull/13 . Its eventual
landing request must name the actual current PR head, including the handoff.
PR #10/#12 remain draft and unchanged. This main-targeted release includes their
existing inactive implementation ancestry; it requires approval of that code
integration. It does not activate those protocols or S0.

## Fixed reviewed producer and source scope

Freeze producer commit **`0c37b30060c2dffb20226bd3efbedc65a75d04e3`** for this
cycle. Do not substitute `git rev-parse HEAD` after metadata or records commits.
All 23 executed files match it; binding ID:
`002419f25184496ccead9cf92556116872550e6f29ad6edfc60cc5846a00f733`.
The main release may be a descendant only while those exact files remain identical.

The scoped basis is the publisher-labelled CC BY 4.0 public data-release store,
not direct ESPN access. See `evidence/data/2026-10-22-sdv-daily-source-review.json`:
it retains the exact original README as well as attribution/modification terms.
Only the named schedule and roster families below are in this operating approval.
No additional data-source HTTP request was made during this implementation.

| Asset | Fixed publisher route |
| --- | --- |
| Schedule release metadata | `https://api.github.com/repos/sportsdataverse/sportsdataverse-data/releases/tags/espn_nba_schedules` |
| Schedule CSV | `https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_schedules/nba_schedule_2027.csv` |
| Roster release metadata | `https://api.github.com/repos/sportsdataverse/sportsdataverse-data/releases/tags/espn_nba_rosters` |
| Roster CSV | `https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_rosters/rosters_2027.csv` |

At capture, authenticate the actual asset IDs, exact body bytes, publisher digests,
sizes and update clocks. A future file hash cannot be invented in advance. Capture
retains the exact new revision; earlier preparation files cannot be admitted as
fresh observations. Each metadata response is capped at 256 KiB; each CSV at 2 MiB.
The shared counter permits at most **six GETs**, including redirects, with no
automatic retries. Public redirect follows are limited to the GitHub release host.
Source requests have no credential header or provider key. Existing GITHUB_TOKEN
is used separately for this repository's run verification, Git, PR and Pages work.

The initial schedule/roster publisher-age ceiling is **36 hours**, including final
original readback. This is 24-hour documented cadence plus 12-hour delay tolerance,
not a scientifically established optimum. Upstream observation remains UNKNOWN.
New retrieval does not change publisher age. Missing injuries, lineups and
participation remain explicit; every distribution is conditional on appearance.

## Fixed cycle and windows

Cycle: `NBA-SDV-DAILY-001-20261023-401909094`.
Config: `config/sdv_daily_cycle_v1.json`, registered at
`2026-10-22T01:17:48.625614Z`, digest
`eab839d53f26623f1256ef09d64b617f6b6bbb96dd36a1ea65d534c3e1590f92`.
Event: Denver Nuggets at Oklahoma City Thunder, ESPN namespace `401909094`,
October 23 at 01:30 UTC. Cohort: Alex Caruso 2991350, Kenrich Williams 3133626,
DeMar DeRozan 3978, Aaron Gordon 3064290. The two-lowest-active-IDs-per-team rule
and all exact identities must still reproduce in the new files; no replacement
subject is permitted. This small operation establishes no league-wide accuracy.

| Actual phase | UTC | October 22 America/Chicago |
| --- | --- | --- |
| Manual runner start | October 22, 22:00 through strictly before 22:30 | 5:00 through strictly before 5:30 p.m. CDT |
| Retrieval / normalization / durable input and intent recovery | October 22, 23:00–October 23, 00:00 | 6:00–7:00 p.m. CDT |
| Generation / verification / persistence / required readback | October 23, 00:00–00:15 | 7:00–7:15 p.m. CDT |
| Scheduled game | October 23, 01:30 | 8:30 p.m. CDT |

Each original has at most 300 seconds from generation start through required
independent readback. Shared T90 model cutoff and daily history freeze are
unchanged. The retained panel ends at reconstructed availability
`2026-04-14T00:30:00.000000Z`; no new training data or outcomes are introduced.
This daily protocol does not satisfy the original fresh-observation T90 protocol.

The exact manual dispatch command, **only after approval and in the start window**:

```bash
gh workflow run sdv-daily.yml \
  --repo NickNicky19/Nicks-multisport-lab-project --ref main \
  -f cycle_id=NBA-SDV-DAILY-001-20261023-401909094 \
  -f producer_commit=0c37b30060c2dffb20226bd3efbedc65a75d04e3 \
  -f 'confirmation=APPROVE NBA-SDV-DAILY-001-20261023-401909094 0c37b30060c2dffb20226bd3efbedc65a75d04e3'
```

The existing authenticated CLI identifies `NickNicky19`; the trusted entrypoint
requires that owner, main, the exact workflow/run/attempt and actual GitHub API
evidence. No new secret, private-key installation, signup or paid service is
required by this public-release route. Administrative workflow-settings inventory
was unavailable (GitHub HTTP 403), not inferred from that result. The new genuine
workflow itself has not executed. GitHub-hosted CI/local transport verification is
distinct from proving a future operating run's permissions, source availability or
timing. No computer/app needs to remain running after successful hosted dispatch.

**Nothing is scheduled or armed.** This command must actually be dispatched in
the stated start window; approval of code alone does not start it. If the window
is missed, this cycle stays inactive/partial and any later proposal is versioned
separately. Do not shift OPS002, PROS004 or this cycle's clocks.

## Storage, recovery and publication actions covered by the decision

One retained worker state and one writer target
`records/sdv-daily-001-20261023-401909094` in the existing repository. The worker
pushes original inputs, authorization, durable capture-start marker, input/intent
acknowledgments, forecasts, completion/failure reports and original readback
proofs. Fresh-host recovery cannot reset a used/uncertain capture request budget;
without a complete original input it stops rather than recapturing. Existing
subjects retain their original input/producer/clocks. Only missing models may be
generated while timely; a late/missing peer remains missing. No atomic-success
claim is fabricated.

Raw licensed originals are losslessly compressed, publicly retained in Git and
excluded from Pages. The old encrypted ESPN design remains untouched. Combined
ledger capacity, including all original 19 records and worst-case corrections,
outcomes, grades and operational metadata, is 131 records / 29,433,032 bytes,
within unchanged 512-record / 33,554,432-byte limits. Probability atoms/history are
never dropped and source limits are never silently raised.

After actual eligible originals are durably recovered, the worker prepares a draft
records PR and dispatches the **existing** `pages.yml` with the actual final records
commit. That build independently fetches the fixed branch, validates original
bytes, typed relationships, owner authority, source commit and timely admission,
then imports only immutable ledger JSON. It executes no code from the records
branch. Later main builds reuse the same admitted fixed branch. This independent
publication channel does not require merging the future records PR or any offer.
The final approval must explicitly include this data import/Pages publication.

Pages success must still be checked: workflow/deployment result, public manifest,
served build/data hashes, readable Upcoming cards and mobile/desktop behavior.
A dispatch acceptance is not a verified deployment. A branch with no eligible
originals is not imported; the prior public site remains available while its
factual failure/partial report is retained in Git/PR for review. No unavailable
forecast is counted as issued.

Outcomes stay pending. When actual final evidence exists, review its specific
source/schema admission, retain originals, then append one shared verified outcome
and separate R0/K0 statistical grades. The final-CSV normalizer/grading/correction
route is exercised with synthetic data; genuine final-source collection is not
pre-admitted by this schedule/roster review. DNP is not zero; missing, postponed,
nonfinal and unresolved states remain explicit. Corrections append original-linked
revisions. No financial settlement or ticket qualification follows from this cycle.

## Evidence supplied for release review

The actual retained-source development run used producer
`86cbb6142e2ee24f3d8e5c9dc5043aca7b9f565a`: eight bundles, all 14 categories,
26,645 atoms each, 80.947 seconds / 150,512 KiB peak RSS. Its immutable records
remain under that original pin. Subsequent candidate changes are genuine-capture
restart guards and publication import fixes; focused real-transport/synthetic-wire
tests verify them without repeating the completed model calculation.

Archive commit `14d4dab3f6fc8a4125e472f8b1f7461f007a73e3` on
`diagnostics/sdv-daily-001-20261022-dev-86cbb61` independently recovered all original
inputs and outputs: 40 records / 2,295,625 bytes, eight DEVELOPMENT_ONLY/null-issue
bundles, zero genuine forecasts/outcomes/grades. Existing 19 receipts are byte
identical. This diagnostics branch is not the operating destination and cannot
enter automatic genuine publication. Actual-source private preview passed
desktop/mobile 1440/390/320, all names/categories, source ages, conditional meaning,
History routes and 2–6-leg/direction/scope NO_ACTION behavior.

To rebuild the private review preview after an environment restart, independently
fetch archive commit `14d4dab3f6fc8a4125e472f8b1f7461f007a73e3` from the existing
repository into a fresh checkout, verify that exact fetched head, then run from
the current candidate checkout:

```bash
python3 scripts/preview_sdv_daily.py \
  --records-root <fresh-archive-checkout> --output <separate-preview-directory>
node web/tests/site-smoke.mjs <separate-preview-directory>
```

The helper copies only authenticated bounded ledger entries into private staging
and uses the current trusted website. It rejects source/output aliases and never
generates a forecast, executes archived code or changes original records.

The handoff records final repository checks, exact release head and separate
independent findings. None of this software/development evidence establishes
forecast accuracy, timely future issuance, betting qualification or live deployment.

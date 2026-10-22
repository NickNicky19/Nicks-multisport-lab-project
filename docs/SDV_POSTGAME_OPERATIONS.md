# First daily cycle: final-statistics recovery

This additive release installs postgame processing for
`NBA-SDV-DAILY-001-20261023-401909094`. It does not launch the original forecast
producer. Recurring pregame issuance is **not implemented** by this coordinator.
OPS002, PROS004, S0 and the expired October 20 pilot remain inactive.

## First forecast launch remains separate

The approved first producer is `0c37b30060c2dffb20226bd3efbedc65a75d04e3`.
Its 23 execution files, cycle, four-player cohort, public Git destination and
windows are unchanged. Follow [the activation package](SDV_DAILY_ACTIVATION_PACKAGE.md).
The installed `sdv-daily.yml` is owner-manual only. No future first-cycle dispatch
is installed. Its owner-authenticated start is October 22, 2026, 22:00 through
strictly before 22:30 UTC; capture is 23:00–00:00 and issuance/readback is October
23, 00:00–00:15 UTC. Approval is not a scheduled launch. A bot must not impersonate
the owner or change that producer's guards.

## Installed hosted postgame execution

The owner-approved PR #14 head `c7862040063c4bc6088aeb8978839dff54b90eb9`
merged as `af0456d29b2922a400340c998502e963bf85d6e8` on October 22.
GitHub reports workflow **392458906** active at
`.github/workflows/nba-operations.yml`; the retained deployment checkpoint is
[evidence/deployment/2026-10-22-pr14-pages.json](../evidence/deployment/2026-10-22-pr14-pages.json).
It is the one GitHub-hosted postgame coordinator. Its cron is
**13:17 UTC daily (8:17 a.m. CDT)**. The code permits work
only October 23–30 inclusive, between 13:00 and 14:30 UTC, then expires without
source collection. GitHub scheduled delivery can be delayed or omitted; cron is
not proof of execution. No local computer or app needs to stay open. The next configured cron occurrence
is October 22 at 13:17 UTC, which the date guard treats as a no-op before the
postgame window. The first eligible occurrence is October 23 at 13:17 UTC.
After October 30 the code refuses source collection; this does not automatically
disable the GitHub cron. Neither a calculated occurrence nor active workflow
status proves that GitHub will actually deliver a run.

The main-only workflow verifies the actual GitHub run, event, actor, attempt,
checked-out source and frozen producer binding. Owner-manual catch-up is available
inside the same operating window:

```bash
gh workflow run nba-operations.yml \
  --repo NickNicky19/Nicks-multisport-lab-project --ref main \
  -f cycle_id=NBA-SDV-DAILY-001-20261023-401909094
```

This command is runnable only after installation, not authorization to bypass
the date/window checks. It does not generate forecasts. Both workflows share the
first cycle's concurrency group; a retained filesystem lock rejects a competing
local writer. Only existing GitHub access is used, with no provider credentials.

## Originals, budgets and corrections

The worker independently fetches only
`records/sdv-daily-001-20261023-401909094` into a new Git object database. Missing
or ineligible originals cause **zero sports-data requests** and an honest failure
report; no branch, player or forecast replacement is manufactured.

For eligible originals it replays already-retained complete observations before
collection. The source scope is [the final-source review](SDV_FINAL_SOURCE_REVIEW.md)
and sealed `config/sdv_final_admission_v1.json`. Each capture permits at most six
GETs including redirects, no retries: exact release metadata and advertised
schedule/player-boxscore CSVs. Metadata is capped at 256 KiB and each CSV at 2 MiB.
Only the registered GitHub release hosts/routes are admitted. Upstream observation
time remains UNKNOWN; publisher update, retrieval and grading clocks differ.

There are at most **two started captures in total**, at most one per UTC day.
A start marker is independently persisted before any source GET. A restart after
an interrupted capture does not reset its unknown request count or recapture that
day. Exhausted requests/observations do not block replay or publication recovery.
At most two complete source observations fit this version; further correction
collection requires a newly reviewed budget/version, not a silent limit increase.

Exact successful originals and admission proof are committed, pushed and recovered
before grading. Failed attempts retain admissible completed HTTP 200 bodies and
safe request clocks/hashes in Git when possible. Redirect/error originals can
contain ephemeral access material: their diagnostic workflow artifact expires
after **14 days**, and is not a durable source archive or grading admission.
Interruption before remote persistence remains a factual durability failure.

Final admission requires exact event/start/season/team identity, explicit final
status, usable selected-player evidence and count/score reconciliation. DNP is
not zero; missing, postponed and nonfinal evidence stays unresolved. Unsupported
cancelled semantics retain evidence without inventing an outcome. Source finality
is provisional: later admitted changes append linked outcomes and separate grades,
preserving original probabilities, clocks, evidence and earlier grade history.

## Publication and operational recovery

The worker flushes the actual records head and prepares a draft records PR.
PR creation and publication are independent: a PR permission failure does not
discard records or prevent the existing Pages import path from being requested.
No merge of a records PR is needed to recover the approved original records branch.

Before dispatching Pages, compare its actual public manifest/build, daily asset
hash and typed active originals/outcomes/grades with independent record recovery.
An unchanged matching site causes no deployment. Otherwise dispatch the existing
Pages workflow with the **exact current records commit**. Poll at most once per
minute for twenty minutes. An accepted dispatch is only a request. Success requires
actual served-byte agreement; write a publication acknowledgment only afterward,
so the records head cannot move before Pages imports its requested revision.
An interrupted or failed publication is retried on the next eligible run, even
with no new grades or no capture budget. Publication checks do not consume the
separate sports-data GET allowance.

Failure reports are bounded, sanitize URL queries, and retain observed state.
An idempotent repository issue provides a durable alert when existing permissions
allow it; a failed alert is reported rather than claimed successful. A missing run
or branch cannot establish why the original launch failed. Workflow reports and
emergency originals also have the explicit 14-day artifact limitation.

Pause the installed coordinator with `gh workflow disable nba-operations.yml`
if needed; preserve existing Git records and inspect the report before any manual
catch-up. Do not disable, rerun or rewrite the frozen first cycle to repair grading.

## Capacity and reporting

The combined conservative plan includes the original 19 records / 1,817,800 bytes,
60 first-cycle slots / 9,658,368 bytes, and 76 postgame slots / 19,955,712 bytes:
**155 records / 31,431,880 bytes**, below unchanged **512-record / 32-MiB** limits.
Postgame slots include partial retainer failures, two source attempts, eight run
proofs, 24 start/final/publication reports, eight outcomes, 16 grades and 12
correction links. Exact originals already embedded in a valid proof are recovered
there; a captured CSV covered by that proof is retained directly in its canonical
proof-linked record. No second raw copy is needed to recover that same original.
Unknown or unrelated originals are never discounted.

Runtime checks use actual retained bytes plus **unused** postgame role ceilings;
already-consumed slots are not reserved twice, and closed pregame slots cannot
generate new forecasts. Every source GET and retainer uses this same accounting.
Changed existing content can still reject the reserve. The separate static plan
is planning evidence, not a claim that all its records have been written. No
history or probability atom is dropped. This is a bounded first-cycle reserve,
not perpetual full-league capacity.

[Daily scorecard definitions](DAILY_PERFORMANCE.md) were registered before any
genuine daily outcome. The website groups descriptive metrics by evidence lane,
exact model revision and category, preserves zero-support failures and separates
DNP/pending. Tests and local previews are invented data, not actual grades,
accuracy qualification, ticket settlement or financial results.

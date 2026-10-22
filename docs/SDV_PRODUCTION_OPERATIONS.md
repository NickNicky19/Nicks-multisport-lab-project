# Recurring NBA daily-snapshot operation

This is the **NBA-SDV-PRODUCTION-001 implementation candidate**, extending the
existing `nba-operations.yml` coordinator. It is not an installed recurring
producer until its exact release and operating scope are approved and merged.
The protected first daily cycle retains its separate owner launch, producer,
23 files, 19 original records and dated windows. OPS002, PROS004 and S0 remain
inactive. Nothing here backfills a missed forecast or establishes accuracy.

## Source, population and clocks

Reuse the retained publisher README and the scoped reviews in
`evidence/data/2026-10-22-sdv-daily-source-review.json` and
`evidence/data/2026-10-22-sdv-final-statistical-admission-v1.json`. SportsDataverse
labels its public data-release store CC BY 4.0. Attribution, the license link,
ESPN/hoopR provenance and the Lab's modification notice accompany archived
sources and exported research. This admits the named public publisher releases;
it grants no direct ESPN access, provider-account access or betting settlement.

Only schedule, roster and player-boxscore CSV families are used. The seasonal
asset must actually exist in its original release response; its advertised
ID, URL, exact size, SHA256 and update clock must match the entire retrieved
file. No provider key, signup, login, wallet, paid service or trial is involved.
GitHub authentication is existing project access, separate from source GETs.
The old ESPN encryption/key design is unchanged and unused by this licensed
public-release archive.

The complete schedule CSV determines each **UTC game date**, rather than a
local-date scoreboard. Planning runs on the preceding UTC date at 13:00–14:00.
The first admissible game date is October 24, 2026. Every valid scheduled NBA
event and every active source-roster member of its two teams is included, sorted
deterministically. Inactive members, unscheduled events and unavailable team
rosters have explicit exclusions. The guard ceilings are 32 events per date,
64 subjects per event, and sixteen subjects per immutable runtime shard. A
ceiling violation rejects the inventory; it does not truncate it. Actual source
membership is not confirmed appearance, health, a starting role or minutes.

A daily plan freezes event versions, teams, starts, complete cohorts, exact
source originals, full-history reference, model/source binding and shard tasks
before inspecting forecasts or outcomes. Fresh shared schedule/roster capture
is T150–T90; automatic new captures stop at T105 to leave preparation margin.
Already captured original bytes may be recovered until T90, without another GET
or a replacement input. Both models reference the identical input receipt.
The input and generation intent must be independently recovered before T90.
Generation is T90–T75 and never at/after game start. Each original's generation
start through its required original readback is limited to 300 seconds.

Schedule and roster publisher age is at most **36 hours**, checked against the
exact consumed revisions throughout admission. This initial policy allows the
documented daily cadence plus twelve hours of publication delay; it is not an
estimated optimal threshold and does not satisfy the older fresh-input T90
protocol. Publisher upload, unknown upstream observation, our metadata/CSV
retrieval, normalization, generation, verification, local write, original remote
readback and proof filing remain separate clocks. Another download does not
refresh unchanged content.

## Models and qualification

R0 and K0 retain their original mathematical laws, parameters and causal rules.
Shared preparation avoids repeating unchanged historical work; equivalence
tests compare support, input hashes and every category with the original laws.
All 26,645 retained historical rows remain available, with the original
exclusions, reconstructed-availability limitation and April 14 historical-panel
cutoff disclosed. No training refresh, comparative scoring or frozen experiment
is performed by this operating package.

Every original has all thirteen requested categories plus PA, derived from its
complete coherent joint law. No probability atoms are removed. Distributions are
**conditional on appearance**. Missing injuries, lineups, upstream observations,
own-player history and workload limitations remain explicit. Forecasts, grades
and corrections never establish product qualification, ticket value or profit.
Offers, prices, EV and venue financial settlement are independent; the builder
retains its scopes, directions, 2–6 legs and NO_ACTION gates.

## Storage and admission

Future production uses its own explicit budgets. It does not consume the old
planning-only pool's remaining 25,400 bytes or raise either protected pilot's
limits. Each runtime shard still has **512 records / 32 MiB**. Its complete
reserved role allocation is **319 records / 9,609,216 encoded bytes**, including
two outcome versions, paired grades, correction links, post-action proofs and
64 bounded status records. A new production-only failure allowance reserves at
most eight unpublished files / 4 MiB; the complete maximum projection is
327 files / 13,803,520 encoded bytes, still within the unchanged 512 / 32-MiB
ledger. Actual files plus unused obligations are charged before every write.
Interrupted `.receipt-*` files remain charged, archived and recoverable as
unpublished forensic bytes; they are never counted as forecasts. At the failure
allowance boundary, new writes stop. Recovery preserves even an already-present
over-limit file; it cannot turn that state into permission for another write.

Exact source bytes are shared, losslessly chunked at 1 MiB. Content-addressed
GitHub Release objects use tags `nml-nba-records-v1-YYYYMM`. New receipt packs
contain at most 1 MiB of canonical bytes; later snapshots reuse original packs
instead of duplicating full history or forecasts. No asset is overwritten or
deleted. Monthly archive budget is **32 GiB**, lifetime budget **64 GiB**, with a
separate 100,000-object transport ceiling. These finite future-production limits
reserve every unused forecast/input/authorization/outcome/grade/correction/
status/proof role, bounded failure files, cumulative immutable full-snapshot
manifests, registry metadata and globally shared final-source captures.
The first 8-GiB draft allocation was insufficient and was replaced explicitly
before release approval; no protected pilot budget changes. A fresh shard's
conservative remaining archive liability is **71,647,232 B**, including a
128-KiB compressed ceiling for each possible new snapshot state. No-change
retries reuse the original object. Forty-five fresh shards per day across seven
days reserve 22,568,878,080 B; adding seven days' maximum shared final sources
(1,908,408,320 B), registry metadata (536,870,912 B), parallel headroom
(268,435,456 B), and 1 GiB of existing actual objects totals **26,356,334,592 B**,
below 32 GiB. This calculation establishes **byte headroom only**. The
100,000-object ceiling also reserves each unused receipt pack and snapshot,
shared source objects and metadata; it can prevent an inventory from being
admitted before its byte budget is exhausted. Server rate limits, response
sizes, action counts and actual execution windows can stop earlier too. This is
an explicit engineering envelope, not a promise of unlimited history, guaranteed
315-shard coverage, or measured hosted throughput. Actual admitted cohorts and strict recovered
capacity determine each new reservation; larger inventories reject in full
rather than truncating. Existing archived bytes are charged separately from
unused obligations. Cold workers receive the same authenticated global reserve
and a private new-write allowance; concurrent workers cannot spend a peer's
remaining liability. They stop new work before exhaustion; they are not an unlimited free
storage guarantee. Reaching a limit requires a new reviewed storage decision,
never silent growth or evidence deletion.

Runtime logical disk is capped at 2 GiB. Read-only coordinator/publication probes
materialize one independently recovered shard at a time, then remove only that
verified cache. Retained worker originals and unacknowledged partial states are
not cleaned up. Public production output is capped at 512 MiB, under the Pages
site limit, with 1-MiB date-partitioned pages and at most 1,024 pages. A browser
loads a selected date within 64 MiB. The site exposes seven UTC dates of full
records and dated archive pointers for older originals; metrics declare their
loaded date coverage. Projection failure does not erase records or stop otherwise
permitted price-independent statistical work.

Each shard has one normal-push records branch and a small `latest.json` pointer.
`records/sdv-production-index` holds a bounded small pointer to the exact
immutable registry bytes in the same archive. Routine no-change checks do not
append another full registry blob to Git. Registry originals consume the
explicit metadata/archive budget; older Git pointer commits remain independently
readable. Immutable source,
forecast, outcome, grade and correction originals remain in the archive. Fresh
Git object databases and independent archive readers verify bytes, references
and typed meaning before acknowledging recovery. There is no force push.

An original and its post-write local marker must be independently recovered
before the applicable deadline/latency limit. Proof metadata must itself be
durable before public admission; its later filing/readback is reported separately
and is not a recursive acknowledgment of itself. A late original remains
ineligible after restart. Missing proof remains unacknowledged. A timely original
whose proof filing completes later may become admissible when that proof is
actually recovered, without claiming the whole checkpoint finished on time.

## One scheduler and bounded work

The existing coordinator's proposed cron is `2,17,32,47 * * * *`. Actual GitHub
main run/event/actor/attempt/head/source bytes are authenticated. A recovered
authorization is evidence, not a fresh execution capability. A scheduled check
is not guaranteed to start on time. Every phase rechecks the actual clock; no
waiting process, second scheduler or early/late first-cycle dispatch is added.

The global lock is shared with the protected first cycle. Each worker retains
one shard and one writer. Pregame jobs precede catch-up grading so an old grading
queue cannot consume the issuance window. Matrices allow at most 128 due pregame
shards and 128 grading shards per pass; deferred grading stays explicit and
unacknowledged for the next check. At most sixteen shard jobs run together,
with at most two model workers per host.

Every capture first durably reserves six GETs, counting redirects, with **zero
HTTP retries**. Unknown interrupted requests consume their reservation. Limits
are 24 source GETs per UTC hour, 256 per UTC day, two planning attempts and two
input attempts per event. Complete inputs/cohorts cannot be rebound on retry.
Final snapshots are shared across pending events, at most twice per UTC day.
GitHub transport has its separate bounded limits; it is not a provider-request
budget. No request bypasses an access denial or automatic approval rejection.

Both laws preflight before writing a player pair. Checkpoints batch at most four
subjects/eight forecast references. Before generation, an OPEN attempt is
independently checkpointed. The original executing process can close it only
after independent recovery of its complete current footprint, including any
unpublished forensic receipt. These two status records use the existing
64-status reserve; they are not extra per-forecast records.

On interruption, recover originals first. A caught failure with a durably CLOSED
complete footprint permits missing peers to continue only while timely. A fresh
host finding an unresolved OPEN refuses generation: unseen local originals may
have existed before the previous host died. It cannot close that old attempt
using its incomplete inventory. Recover the emergency artifact's original bytes
and review the uncertain attempt; if those bytes are unavailable, retain the
partial/unrecoverable result rather than creating another original. An
unpublished receipt likewise blocks generation until addressed. A late peer is
never regenerated or erased.
Failures appear in the actual workflow, bounded retained status/report, and one
project failure issue per UTC date. They never become a fabricated atomic success.

## Outcomes, corrections and publication

Final observation uses the same licensed publisher's exact schedule and player
boxscores, separately verifying explicit final status, event/start/season/teams,
selected-player rows, DNP, count arithmetic and both teams' scoring totals.
Missing/nonfinal/postponed/cancelled/unresolved data stays pending. DNP is not
zero production. One outcome links every original peer; only eligible genuine
forecasts receive prospective statistical grades. Development grades stay in
their own lane. No financial settlement is inferred.

Automatic source captures/corrections are limited to seven days after the event
and two outcome versions. Already admitted original source evidence can finish
statistical processing after that capture window. Later changed statistics append
outcome/grade revisions and correction links; original probabilities and clocks
never change. A third conflicting observation is retained as unresolved and
excluded from current Performance pending a separate review, rather than silently
overwriting or treating the old grade as current truth.

The existing Pages workflow independently reads an exact registry commit and
immutable source/shard snapshots. A previous index commit remains readable while
new operational metadata advances the branch. Publication is asynchronous: a
dispatch is pending until a later coordinator verifies the actual public manifest,
served build, typed index, every referenced page and all hashes. Unchanged content
does not trigger another deployment. Historical six bundles/grades and the frozen
first daily publication channel remain independent.

Read-only independent recovery, after an actual records branch exists:

```bash
python3 scripts/recover_sdv_production.py \
  --branch records/sdv-prod-YYYYMMDD-EVENT-PLANSEED-s0 \
  --work-root /tmp/nml-production-independent-readback-UNIQUE
```

The placeholders must be replaced by the exact registered branch. The command
fetches JSON/objects only, never executes fetched code, requests a provider,
generates a forecast or rewrites timestamps. Its recovered local directory is a
readback copy; durable originals remain in the verified remote archive.

The isolated development diagnostic command is:

```bash
python3 scripts/diagnose_sdv_production.py \
  --work-dir /tmp/nml-production-diagnostic-UNIQUE \
  --producer-commit REVIEWED_SOURCE_SHA
```

It uses the full retained history, invented inputs, sixteen labeled diagnostic
aliases, a filesystem archive and a temporary bare Git repository. It cannot issue
genuine records or evaluate accuracy. Hosted diagnostic mode additionally requires
explicit authorization for its exact head and the diagnostic workflow input.
The one authorized execution at `2b8bcd4767fd85d19148dea5587e7da28290a988`
is consumed by run 39768069169; it is not permission to rerun a changed head.
Its archive client enforces at most **32 MiB / 64 new immutable
objects** before mutation. It makes zero sports-source requests, performs no
public publication, and includes the same OPEN/CLOSED checkpoints as operation.
Local timing is not hosted timing or genuine pregame evidence.

## Current release and remaining operating gate

PR #15 merged at `377a3e4e69749efeee912a75c51673144f9fc27f`; Pages run
39741220070 deployed successfully. Exact public proof is
`evidence/deployment/2026-10-22-pr15-pages.json`. The recurring candidate is
separate and is not installed by that release.

The first new archive upload failed with its server reason unretained/unknown.
Read-only reconciliation found no uploaded asset. Automatic approval review then
rejected another diagnostic upload before execution; no workaround was used.
An actual CLI/local mock reproduced missing Content-Length/chunked framing, and
the explicit length header is fixed. That local finding does not prove the cause
of the original server failure or establish successful GitHub recovery. See both
dated archive diagnostic receipts in `evidence/operational/`.

The subsequently approved hosted diagnostic ran on October 22 at 11:06 UTC.
It uploaded eight immutable objects (17,611 compressed bytes) and committed
pointer `edfec1ce4bc20f66a7f58f32a006c2ed92a7d39a` on
`diagnostics/sdv-production-load-20261022T110633`, then failed before generation:
the authenticated draft existed but its by-tag endpoint returned 404. The
corrected diagnostic-only lookup checks the bounded authenticated release list;
it does not change public production lookup or treat 403 as absence. Independent
GET-only recovery verified all eight objects and the three original plan/input/
local-completion records at 11:11 UTC. No forecast or genuine issuance resulted.
An additional offline reproduction found that a reader retaining an older
decoded draft-asset inventory could miss later checkpoint objects. The reader
now refreshes that inventory once on an exact-name miss from an already-cached
list. Size/hash/identity mismatches, ambiguity and 403 still fail; this is not a
write retry. Separate decoded-reader tests cover original and later objects.
This establishes partial-input archive recovery, not full hosted generation or
the 300-second original-delivery latency. The actual failed run and readback are
retained in `sdv-production-hosted-diagnostic-39768069169-20261022.json`.

Before recurring activation: finish exact-head checks/review, obtain a new
exact-head authorization for one corrected hosted development diagnostic,
verify connected generation/checkpoint timing, then obtain the exact-head release/
operating decision. Do not claim recurring readiness from local tests, a draft
release or an accepted dispatch. Completion of the overall goal still requires
public genuine forecasts, verified real final grades, a subsequent scheduled run,
tested recovery and the operating evidence described above.

Research cards now expose each unchanged model's retained reported-minutes mean
and 80% interval. These history-based estimates are conditional on appearance;
they are not confirmed playing time or current injury/lineup/blowout adjustments.
The first-cycle producer and its website channel remain unchanged. SportsLine
is not admitted for automated collection or website redistribution by this
release; its public lines and subscription terms were reviewed separately.

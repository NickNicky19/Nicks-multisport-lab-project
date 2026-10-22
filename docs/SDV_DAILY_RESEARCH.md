# SportsDataverse daily-snapshot research

Protocol `NBA-SDV-DAILY-001` is a separate operating version. It does not activate,
replace or backfill OPS002, PROS004 or the expired October 20 pilot. Its code and
first cycle require the exact-head release/operating decision in the handoff.

The implementation consumes two actual public release assets, rather than four
invented ESPN responses. `sdv_daily_inputs` binds the selected schedule/roster
rows to exact original CSV and GitHub release JSON bytes, asset IDs and hashes.
Event snapshot identity is derived from this source representation. There is no
invented provider event revision. Missing or contradictory identities, duplicate
IDs, changed teams/cohort, unscheduled status and post-start operation fail closed.

## Initial operating policy

| Requirement | Limit |
| --- | --- |
| Schedule publisher asset age at use and final original readback | 129,600 seconds (36 hours) |
| Roster publisher asset age at use and final original readback | 129,600 seconds (36 hours) |
| Actual retrieval, normalization and durable input/intent recovery | T150 through T90 |
| Actual generation, verification, persistence and required readback | T90 through T75 (900 seconds) |
| Each original: generation start through independent original readback | At most 300 seconds |

The publisher documents a daily update cadence. One daily interval plus twelve
hours of publication-delay tolerance is an explicit initial operational choice,
not a scientifically optimal freshness threshold. Downloading the same stale
content cannot refresh its publisher clock. The input records separately retain
publisher update, retrieval start/completion and normalization clocks. Upstream
observation is UNKNOWN; an upload does not date each individual fact. Forecasts
retain actual generation/verification/issue clocks, game start, horizon, the
unchanged T90 model cutoff, UTC history freeze and training-panel cutoff/version.
This route does **not** satisfy the old fresh-observation T90 protocol.

## Statistical scope

Unchanged R0 and K0 consume the same complete 26,645-row fixed history and admitted
current input. Shared source bytes, causal exclusions and reconstructed-history
limitations remain intact. One coherent joint law supplies PTS, PRA, REB, 3PM,
AST, RA, PR, TOV, TD, DD, BLK, STL, BLK+STL and PA. No probability atoms or history
rows are omitted to meet a budget. Generation preflights both models before
persisting either member of a subject pair. A failure can leave a preserved
original and missing peer; recovery does not invent atomic success or a late peer.

These distributions are **conditional on the player appearing**. Active roster
membership establishes neither participation nor health, a starting role or
minutes. Injury/lineup/confirmed-participation information remains missing. No
confidence adjustment, mathematical retuning, new comparison or qualification is
part of this delivery. A current 517-row roster audit is not league-wide forecast
coverage, and the older historical panel has not been silently refreshed.

## Source use and exact retention

The scoped publisher-release decision and recoverable original publisher README
are in `evidence/data/2026-10-22-sdv-daily-source-review.json`. SportsDataverse
labels its data-release store CC BY 4.0. We credit SportsDataverse, retain its
ESPN/hoopR provenance, link the license and identify normalization/filtering and
modeling modifications. This basis is specific to the public release route; it
does not authorize direct ESPN access or establish unrestricted upstream rights.

The existing repository holds losslessly compressed exact CSV and original
release-metadata bytes in `daily/records/research_inputs/`, alongside the existing
immutable ledger. No private encryption key is necessary for these publicly
licensed assets. The old encryption design and its separate access scope are
unchanged. Raw source bytes stay outside Pages. The parent history is referenced
once; it is not duplicated in each event pack. Combined parent/daily limits stay
512 records / 32 MiB; individual source responses stay at 2 MiB. Oversized sources
fail without truncation or a silent limit increase.

Local write, remote push, fresh-object-database original recovery, and comparison
eligibility are distinct. Completion metadata records actual completed actions.
Late/unacknowledged originals survive, but cannot become timely through restart.
Create-only identity/input/producer binding prevents a different revision or new
input from silently creating a replacement cohort. One state and one writer are
retained. Independently fetched bytes and typed relationships are verified before
acknowledgment; storage checks do not disappear under optimized Python.

## First proposed cycle

The registered config is `config/sdv_daily_cycle_v1.json`. Its fixed event is
ESPN-namespace `401909094`, Denver Nuggets at Oklahoma City Thunder, October 23,
2026 at 01:30 UTC (October 22, 8:30 p.m. CDT). The cohort is Alex Caruso 2991350,
Kenrich Williams 3133626, DeMar DeRozan 3978 and Aaron Gordon 3064290. Selection
reproduces the two lowest numeric active IDs per current event team. These are
source facts from the retained sample and must be revalidated during operation;
the old OPS002 plan is not rebound to them.

| Phase | UTC | America/Chicago (CDT) |
| --- | --- | --- |
| Earliest owner manual workflow start | October 22, 22:00 | October 22, 5:00 p.m. |
| Actual reviewed activation completed | Strictly before October 22, 22:30 | Strictly before October 22, 5:30 p.m. |
| Retrieve, normalize, retain and independently recover inputs/intent | October 22, 23:00–October 23, 00:00 | October 22, 6:00–7:00 p.m. |
| Generate, verify, persist and recover originals | October 23, 00:00–00:15 | October 22, 7:00–7:15 p.m. |

The manual-only `sdv-daily.yml` workflow uses the existing GitHub-hosted runner
and GITHUB_TOKEN, without a source API key, signup, encryption secret or scheduler.
It authenticates the actual owner/main/workflow run through GitHub, checks all
executed source bytes against the fixed reviewed producer commit and retains its
authorization before the deadline. A supplied dictionary does not authorize a
genuine producer. A same-run restart authenticates the retained original rather
than creating another activation; another run/attempt is not a replacement.

The proposed destination is
`records/sdv-daily-001-20261023-401909094`. A maximum of six source GETs includes
two release-metadata requests, two canonical CSV requests and at most two public
asset redirect follows; no retries or broader collection. GitHub authorization,
record push/readback and Pages delivery are separate repository operations.
Any missed window or changed source/cohort produces factual inactive/partial
evidence, not replacement players, relaxed freshness or backdated issuance.

## Preview, publication and later outcomes

The offline `sdv_daily_runner preview` uses retained originals, actual generation
clocks and DEVELOPMENT_ONLY records with no issue time. It never becomes genuine
prospective evidence. The manifest-6 independent daily channel preserves all six
original historical bundles and grades. Cards show names, matchup, model,
conditional participation, source ages/clocks and panel cutoff. Genuine admitted
future records belong in Upcoming; development/test records have their own panel.
Expired original forecasts belong in History without rewriting their probabilities.

The existing Pages workflow is the delivery mechanism. Licensed originals and
typed records are independently recovered before export. Code release, cycle
activation and public forecast delivery are separate actions, even when the final
owner decision explicitly covers all three. A draft records PR alone does not
publish data, and merging inactive software alone does not populate Upcoming.

No outcome is fabricated in advance. After the game, retain and review applicable
final source evidence before genuine import. The offline final-CSV normalizer
reuses the existing count validation and schedule-finality checks; replay verifies
the exact original evidence. One outcome links separate R0/K0 statistical grades.
DNP is not zero; absent/nonfinal/postponed/unresolved evidence remains explicit.
Corrections append replacements and traceable correction edges, leaving original
probabilities, timestamps and grading history intact. Genuine final-source
admission is not inferred from this schedule/roster review. Statistical scoring
has no financial-settlement or betting-contract prerequisite.

Offers, odds, EV, qualified tickets and settlements remain separate. The 2–6-leg
builder, direction choices, sport scopes and accurate NO_ACTION remain unchanged.

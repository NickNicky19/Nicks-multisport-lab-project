# PROS004 paired producer readiness

Status: implementation in progress; **INACTIVE / READINESS ONLY**. This package
prepares a draft PR. It authorizes no source capture, scheduler, genuine issuance,
activation, merge or deployment. The mathematical reservation remains unchanged in
`docs/NBA_PROSPECTIVE_004.md` and its immutable protocol receipt.
Genuine writes explicitly fail `READINESS_ONLY`, including caller-supplied
activation flags. The proposed operational wrappers are
`pros004-r0-producer-v1` and `pros004-k0-producer-v1`.

## Preservation and versions

Base main:735a464e9e8718303ef481abf711a8969de56694. Worktree:
`/workspace/nml-pros004-readiness`, branch `implementation/pros004-paired-readiness`.
Original pilot records worktree is clean at `df446eee`; PR #8 remains draft with that
head and workflow 390126745 active. No manual retrigger or native-task unpause.
PR #9 remains draft at `d680157`; DEV005/S0 is frozen and inactive. This branch does
not import S0, change its verifier or include it in prospective comparisons.

New wrappers identify their producer versions separately from R0/K0 law versions
and bind exact executed source bytes/commits. R0 keeps the same 28-day decay and
five-appearance prior; K0 keeps latest-up-to-five earlier reported-minute context,
eight-minute bandwidth, 0.25 league floor, 0.75 kernel component and exact R0 fallback.
Both use each target's T90 / daily 00 UTC freeze and each donor's own earlier context.
No retrospective execution receipt is presented as a prospective issuance.

## Shared inputs and clocks

Recover all 26,645 retained appearances / 1,231 games / 14,720,351 normalized bytes with
SHA-256 `489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c`.
Keep its source observations/update clocks, normalization version, provenance,
upstream exclusions and reconstructed start+24h availability conventions. Latest
history is April 13, 2026; no current-season freshness or verified role follows.
No 20,000-row readiness truncation is permitted.

One shared history pack is referenced by every compact event pack and both
producers. Forecasts retain every original category PMF and a complete joint-law
recipe bound to the exact full history, source versions, target and all-atom
weight hash. Independent restart replay must recover every atom and PMF exactly.
No finite subset, tail smoothing, atom omission or category splicing is admitted.

For each registered UTC date select the first event by `(start, numeric ESPN ID)`
from a complete retained daily inventory, and the two lowest numeric explicitly
active athlete IDs/team. Selection and schedule retention close at T90−10 minutes.
Proposed source freshness is 1,200 seconds at T90. Capture/import/persistence of the
one event input must finish within `[T90−20 minutes, T90−10 minutes]`. Observations, source
updates, imports and receipt clocks remain separate. This policy is chosen before
activation, not inferred from a readiness pass. Status means last observed status;
it is not a continuous-feed assertion. Missing source completeness or conflicting
versions/identities block admission rather than replacing the event/cohort.

Complete UTC inventory admission requires three adjacent ESPN local-date routes
and explicit pagination/count evidence. An invented `complete: true` flag is
insufficient. Retained ESPN responses do not prove that contract; a permitted,
verified source route or separately reviewed completeness proof is still required.

Both producers preflight before a pair. Actual generation, verification, issuance
and persistence must fit `[T90, T90+5 minutes]`, with maximum 120-second generation latency,
inputs observed/retained before T90 and event still valid/pregame. A readiness pass
alone proves no actual capture/issuance timing. Recovery pins original inputs and
producer identity even after documentation/records change HEAD. The original
forecast's probabilities and clocks survive; missing/late peers remain explicit.

## Bounded persistence

Existing ledger limits remain 512 records / 32 MiB. Complete encoded-envelope ceilings:
history 2 MiB, event 32 KiB, forecast 64 KiB, outcome 8 KiB, grade 16 KiB. Metadata has its
own measured bound. Current existing ledger is 19 records / 1,817,800 bytes; the full
baseline/pilot allowance is 32 records / 4 MiB, including 13 future pilot records.

The complete study base is 442 records (168 forecasts + 84 shared outcomes + 168 grades +
21 event packs + 1 history pack). Base 474 including existing/pilot; 21 event admission
claims and 4 study/activation/readback/evaluation metadata slots make 499. Reserve 13
correction/failure records up to 512. The conservative premetadata envelope budget
is 21,430,272 bytes (20.4375 MiB). Record slots, not just byte totals, constrain recovery
and corrections. Bounds never rise automatically; no inconvenient record is dropped.

Including metadata and all 13 reserve records at 64 KiB each, the conservative
plan is **22,487,040 bytes**, leaving 11,067,392 bytes under 32 MiB. There are no
unallocated file slots after the reserve. These are 13 record slots, not 13
corrected subjects: one paired correction may require a new outcome, two new
grades and three supersession links.

`Pros004Store` extends research-input validation in a new private ledger subclass;
the frozen ledger and its legacy validators remain unchanged. Existing generic
readers and the public exporter do not yet admit these new contracts. Actual
repository records remain unchanged. Diagnostic stores are restricted to roots
outside Git worktrees. A separately reviewed publication/readback adapter remains
an activation dependency.

Event admission claims do not claim that generation began or that a pair committed
atomically. Atomic original receipts are authoritative issuance. A single-writer
lock and complete validated recovery prevent duplicates; orphan/unacknowledged
state blocks regeneration. A post-link interruption recovers the original bytes.
Loss of local state requires independent complete remote recovery before resuming.
Remote commit/readback evidence is distinct from local persistence.
Synthetic checkpoint callbacks test stopping and recovery; they do not establish
an actual GitHub writer integration for the new record version.

## Outcomes and statistical grading

One verified subject outcome links the original R0/K0 forecasts and their separate
statistical grades. DNP is not zero. Missing, postponed, nonfinal and unresolved
states remain distinct. A partial pair's issued model can be graded without
fabricating a peer. Corrections append replacements and explicit supersession
links; they preserve original forecasts, probabilities, clocks and outcomes.
These grades are not financial settlement or qualified tickets.
The offline raw-summary normalizer binds source bytes to normalized outcome
meaning. Durable raw outcome evidence retention/retrieval remains separate from
the compact hash-bound record and must be resolved before actual operation.

No reserved comparative aggregates are computed here. Earliest registered
comparison time remains `2026-11-25T00:00:00Z` after the fixed window and resolution
period. Code/test correctness and full-history size/runtime diagnostics establish
no predictive result or future evidence. New verification rejects malformed data
with explicit exceptions under normal and optimized Python; DEV005 stays frozen.

## Activation checklist

| Requirement | Current state |
| --- | --- |
| Separate wrapper/input/store implementation | In progress |
| Unchanged R0/K0 and coherent all 13 + PA | Pending independent tests |
| Full-history retention/restart/encoded sizes | Pending bounded diagnostic |
| Full-study capacity including pilot/metadata/corrections | Defined, measurement pending |
| Timing, partial peers, duplicates, DNP and correction tests | In progress |
| Explicit integrity checks under python -O | In progress |
| Reviewed source commit and independent GitHub readback | Pending draft delivery |
| Complete permitted first UTC-date schedule and selected cutoff | **Unresolved** |
| Actual source route completeness/operation admission | **Unresolved** |
| Actual fresh event/cohort/input capture | Not performed; not authorized here |
| Source-bound remotely recovered activation evidence | Not created; not authorized here |
| Reviewed genuine activation validator and remote writer integration | **Unresolved; live guard disabled** |
| Bounded public history/publication admission for 168 forecasts / 168 grades | Separate activation dependency |
| Genuine paired issuance / outcomes / financial settlement | None |

Existing authorized retained October 20 local-date scoreboard shows an October 21 01:30 UTC
candidate. If unchanged and first, its T90 would be October 21 00:00 UTC, selection close
October 20 23:50 UTC. This is **not an established actual deadline**: adjacent route and
pagination/count coverage are absent. A complete permitted UTC October 21 inventory
with current versions is required before declaring the first selected cutoff.
The reservation alone permits a first T90 as early as October 20 22:30 UTC (17:30 CDT).
Do not assume midnight is safe, move the reservation, backfill or replace misses.

Exact implementation commits, commands, actual checks, diagnostic sizes/costs and
remaining blockers will be appended at the completed checkpoint. Next: finish the
shared contracts and verification, then commit/push and open a draft readiness PR.

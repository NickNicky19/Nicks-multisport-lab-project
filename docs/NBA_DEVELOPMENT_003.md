# NBA DEV003: one lagged-workload-prior challenger

**Status: implemented for inventory and synthetic verification; no real-data
forecasting or scoring has run.** The integration owner must freeze the exact
proposed protocol and authorize one execution before evaluation. R0, L0, DEV002
and their immutable receipts remain unchanged. This is a new exposed-development
trial, not confirmation, model selection or product qualification.

## Hypothesis and limits

R0 shrinks sparse personal history toward a league-wide workload mixture. One
untuned challenger, K0, replaces only that pooled prior with a soft neighborhood
of donors whose **earlier reported workload** resembles the target's earlier
workload. Personal R0 weights, 28-day recency and the five-appearance prior
strength stay fixed. This targets sparse-history/workload-prior mismatch.

It cannot solve true zero-history cold starts. The retained input has no
earlier-season/preseason appearances or verified upcoming role metadata; its
other retained source stages are later play-in/playoff records. A target with
no earlier available appearances receives the **exact existing R0 support**.
This is an implementation control, not an improvement claim. A lagged minute
average is not verified role, lineup, injury, pace, participation or exact game
duration. It may reflect overtime, garbage time and past injuries. The proposed
REB B0/B1/C1 share-duration experiment remains separate and blocked.

## Frozen candidate specification to approve before scoring

Input: original 26,645-row ESPN normalized panel, SHA-256
`489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c`.
Keep the existing source-stage-2, archived FINAL, standard team/opponent IDs
1–30, identified complete APPEARED cohort and all upstream exclusions. DNP and
missing fields remain separate from production zero. All reported minutes in
this panel are rounded whole minutes, including valid zero-minute reports.

Every target and every historical donor uses **its own** exact T90 cutoff.
History freezes at 00:00 UTC on that cutoff's date. Earlier event starts and
`event_start + 24 hours` reconstructed completion bounds must satisfy that
freeze. No actual future minutes, donor's own outcome, later correction clock,
same-cutoff-date result or upcoming role information enters a context. Archived
starts and availability remain reconstructed conventions, not historical as-of
proof. Actual issuance is read at execution; no historical capture is backdated.

For event/player i, context `x_i` is the arithmetic mean of reported minutes in
its latest **up to five** eligible appearances; at least one is required. Donor
context `x_j` is calculated by exactly that rule at donor j's own earlier cutoff,
not from the donor outcome's minutes or from the target's later information.
Known rounded zero is a valid context; no history is `None`, not zero.

For the target's eligible completed historical atoms j:

```text
w_j = 2 ** (-elapsed_days_from_start_j_to_target_T90 / 28)
L_j = w_j / sum_league(w)
u_j = L_j * exp(-0.5*((x_i-x_j)/8)^2)  # known donor contexts only
K_j = u_j / sum_known_donors(u)
A_j = 0.25*L_j + 0.75*K_j
P_i = sum_target_player(w)
Q_j = (1[player_j=i]*w_j + 5*A_j) / (P_i+5)
```

Missing-context donors remain in `L`; only their contribution to the kernel
component is zero. Missing target context, no known donor contexts, or numerical
zero kernel mass triggers an **exact R0-support fallback**. Nonfinite quantities
fail the run. The fixed bandwidth is eight reported minutes; the league floor
is 0.25. Neither parameter nor the five-appearance context window is tuned.

Every atom keeps its same observed minutes and FG2M, FG3M, FTM, REB, AST, TOV,
BLK and STL. All 13 requested outcomes plus PA derive inside that same atom,
including scoring, sums and five-stat DD/TD. The strictly positive league floor
retains the existing empirical support; it does not add an unseen-tail model or
repair infinite log loss. There is still no cross-player/same-game joint law.

## Identity-only development cohort

Use 12 complete UTC Monday–Sunday weeks, **2025-10-27 through 2026-01-18**.
For each eligible event, hash exactly these UTF-8 bytes with SHA-256:

```text
NBA-ALL13-JOINT-DEV-003|20261020|{week_start}|{event_id}
```

Rank events by ascending full hexadecimal digest, then event start/event ID for
ties; choose two games per week. Score their eligible appearances in chronological
event/player order. This reduces the fixed earliest-UTC-game restriction of
DEV002 without selecting on outcomes. It remains a sparse deterministic sample,
not demonstrated full-slate representation. Retain complete selected games;
exceeding 600 appearances fails before scoring instead of splitting games.

Metadata and lagged-feature inventory found **24 games and 517 appearances**:

| UTC week start | Game IDs in chronological order | Appearances |
| --- | --- | ---: |
| 2025-10-27 | 401809978, 401809508 | 42 |
| 2025-11-03 | 401810021, 401810047 | 51 |
| 2025-11-10 | 401810060, 401810069 | 40 |
| 2025-11-17 | 401810098, 401810099 | 39 |
| 2025-11-24 | 401809812, 401810156 | 43 |
| 2025-12-01 | 401810169, 401810200 | 43 |
| 2025-12-08 | 401810216, 401836746 | 41 |
| 2025-12-15 | 401836806, 401810248 | 39 |
| 2025-12-22 | 401810255, 401810272 | 46 |
| 2025-12-29 | 401810302, 401810352 | 44 |
| 2026-01-05 | 401810357, 401810375 | 45 |
| 2026-01-12 | 401810411, 401810435 | 44 |

Earlier available appearance counts are 0 for nine targets, 1–3 for 44, 4–9 for
126 and at least ten for 338. Two selected appearances have rounded zero minutes.
There are 21 lagged-workload-shift cases, defined before scoring as at least ten
earlier appearances and an absolute difference of at least eight minutes between
the means of the latest five and preceding five. That diagnostic subgroup
overlaps the history groups and is not an additive population. Across the full
input, 25,961 of 26,645 donor appearances have a known lagged context. These
counts establish feature feasibility, not model performance.

This cohort shares **two games/42 appearances with exposed DEV002**
(`401810216`, `401810255`), and no game with the original 200-row R0 pilot.
The design itself was informed by previous development results. All 517 rows
therefore remain development, including newly selected games; none is labeled
confirmation. A later chronological block cannot be called confirmatory without
an exposure declaration and separately frozen guards. Genuinely future captured
confirmation needs immutable actual pregame records and admitted capture paths.

## Evaluation and uncertainty, still unexecuted

Reference laws are unchanged R0 and L0. K0 is the only challenger and the only
new registered trial; there is no search. Primary comparisons are **per-category
paired mean discrete CRPS/RPS differences K0 minus R0**, where negative favors
K0 on this development sample. L0 is a descriptive reference anchor. Do not pool
raw scores across categories or pick a winning method after inspecting results.

Use 2,000 whole-week cluster bootstrap replicates, Python `random.Random` seed
20261020. Draw 12 registered week clusters with replacement, retain their selected
games/all appearances, and recompute summed paired differences divided by the
resampled row count. Report 95% percentile intervals with linear interpolation
at 0.025/0.975. Forecasts are not refitted inside bootstrap replicates. Twelve
clusters provide limited information, cross-week dependence remains possible,
and no multiplicity correction or confirmatory claim is defined.

Keep DD/TD Brier and unsmoothed log diagnostics, observed/predicted zeros, tails,
50/80/95% coverage alongside predicted interval masses, and reported-minute
errors. Zero-support losses stay infinite with explicit null/status/count in
strict JSON. Report the four history groups and overlapping lagged-shift group
as **counts and point diagnostics only**; no sparse-subgroup interval or
qualification claims. All 517 rows remain in the primary comparison even if a
model performs poorly. No changed population, smoothing or support repair follows
score inspection. No ticket dependence, price, payout, settlement, DNP, product
qualification or prospective paper evidence is established.

## Software and pre-scoring evidence

`multisport_lab/development_003.py` implements the new lane in a separate file,
using unchanged earlier source validation, exact R0/L0 laws and scoring helpers.
`tests/test_development_003.py` contains 12 synthetic tests for donor-specific
causality, own-outcome exclusion, earlier-feature sensitivity, arithmetic context,
rounded zero versus unknown, exact n0 fallback, empty-kernel fallback, normalized
support/floor/full joint outcomes, future-input hash invariance, exact cohort
selection, freeze integrity, cluster resampling and the complete synthetic runner.
These are software checks, not real-data evaluation.

Inventory command only:

```bash
python3 -m multisport_lab.development_003 \
  --input /tmp/nml-nba-audit/normalized.jsonl \
  --output evidence/research/dev003-inventory.json --inventory-only
```

Its create-only receipt contains a proposed protocol binding exact input/cohort,
all game IDs, feature clocks, mixture constants, model versions, budgets and
executed source/test content hashes. The integration owner adds actual
`recorded_at` and `approved_by="root_integration_owner"` to that exact payload
and writes an immutable protocol before authorizing one evaluation. Changed
code, cohort, parameters or approval invalidate the match.

Registered proposed budgets are **900 wall seconds/512 MiB peak RSS**, with a
512-MiB virtual-memory cap and inherited 64-MiB/100,000-row input bounds. Integrity,
code-change or budget failure aborts the whole run without partial publication
or automatic restart. Actual code/input hashes, issuance/execution clocks, frozen
cohort, fallback/zero/cold-start counts, weekly metrics and resource measurements
will be retained only when a run is authorized and actually occurs.

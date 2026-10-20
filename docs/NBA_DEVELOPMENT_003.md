# NBA DEV003: one lagged-workload-prior challenger

**Status: one frozen, authorized development run completed.** All 517 selected
appearances were scored under all three laws; complete results and material
limitations appear below. R0, L0, DEV002 and their immutable receipts remain
unchanged. This is exposed development, not confirmation, model selection or
product qualification.

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

## Candidate specification frozen before scoring

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

## Frozen evaluation and uncertainty

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
are retained in the authorized run's immutable result receipt.

## Observed single run, 2026-10-20

The integration owner froze [`dev003-protocol.json`](../evidence/research/dev003-protocol.json)
at **2026-10-20T01:09:19.742752Z**. Its payload SHA-256 is
`06600825f5c64f396315c29251516da72133f659efca6e3f72a7a2ab7c3322db`.
The implementation, tests, specification, inventory and frozen protocol were
committed and pushed as `2b58ac45c7ec29fa0cba2c41facd3862c137a961` **before
scoring**. Independent pre-scoring review verified cohort, clocks and content
hashes. Exactly one authorized command then created
[`dev003-results.json`](../evidence/research/dev003-results.json):

```bash
python3 -m multisport_lab.development_003 \
  --input /tmp/nml-nba-audit/normalized.jsonl \
  --output evidence/research/dev003-results.json \
  --protocol evidence/research/dev003-protocol.json
```

All three models scored **517 appearances, 24 games and all 12 weeks**, with
zero post-score exclusions. K0 used its kernel prior for 508 rows and reused
the exact R0 support for all nine true cold starts. Both rounded-zero-minute
appearances remained included. Training pools contained 899–12,802 appearances
and personal histories zero to 39. No scoring code, test, parameter or protocol
changed after execution began.

The principal cautions are **slightly higher TD Brier/CRPS under K0**, paired
intervals crossing zero for **TD, DD and BLK**, **infinite BLK/PRA log losses**,
and unresolved workload/zero/tail coverage. Those findings remain visible beside
the favorable point-score changes; they do not trigger retuning or exclusions.

| Category | R0 CRPS | L0 CRPS | K0 CRPS | K0 minus R0 | 95% week-cluster percentile interval |
| --- | ---: | ---: | ---: | ---: | --- |
| PTS | 3.474106 | 4.793755 | 3.320331 | -0.153775 | [-0.213216, -0.105163] |
| PRA | 4.709303 | 6.776717 | 4.454433 | -0.254871 | [-0.353693, -0.174784] |
| REB | 1.483866 | 1.845569 | 1.453300 | -0.030566 | [-0.045624, -0.017435] |
| 3PM | 0.641035 | 0.764988 | 0.631348 | -0.009687 | [-0.018342, -0.002718] |
| AST | 0.978332 | 1.326097 | 0.949368 | -0.028964 | [-0.043292, -0.015965] |
| RA | 2.053225 | 2.684400 | 1.979846 | -0.073379 | [-0.107934, -0.043700] |
| PR | 4.293402 | 5.934992 | 4.090327 | -0.203075 | [-0.281106, -0.140031] |
| TOV | 0.658574 | 0.778410 | 0.643164 | -0.015410 | [-0.022317, -0.009320] |
| TD | 0.003669754 | 0.003850044 | 0.003670558 | +0.000000804 | [-0.000020442, +0.000013576] |
| DD | 0.056740599 | 0.069873543 | 0.056111858 | -0.000628741 | [-0.001513496, +0.000035030] |
| BLK | 0.323670 | 0.357060 | 0.323237 | -0.000433 | [-0.001344, +0.000484] |
| STL | 0.468282 | 0.495387 | 0.463651 | -0.004631 | [-0.007516, -0.001985] |
| BLK+STL | 0.652964 | 0.701887 | 0.646441 | -0.006523 | [-0.010138, -0.003056] |
| PA, optional | 3.910215 | 5.660330 | 3.707872 | -0.202343 | [-0.280819, -0.138628] |

K0's raw mean CRPS was lower than R0's for 13 categories and higher for TD.
There is no unscaled pooled score, model selection, promotion or confirmatory
decision. These unadjusted intervals describe the registered sparse development
sample with 12 week clusters and do not establish product accuracy.

There were **39 DD events and two TD events**. Mean DD probabilities were
0.077302 for R0 and 0.075620 for K0, against observed frequency 0.075435.
Mean TD probabilities were 0.006601 and 0.006286, against observed frequency
0.003868. TD log loss was lower for K0 (0.019704 versus 0.021049), while its
Brier was slightly higher; both diagnostics remain retained. Two events cannot
establish rare-event reliability. Binary CRPS and Brier agree here.

All three models assigned zero mass to **one BLK outcome and two PRA outcomes**.
Their respective aggregate unsmoothed log losses are therefore **infinite**,
represented by null means with explicit status/count. These rows remain in all
CRPS and applicable diagnostics. The league floor preserves empirical support;
it did not fix the unsupported outcomes and does not model unseen tails.

The sparse-history point diagnostics support only a limited mechanism check:

| Earlier appearances / diagnostic group | Rows | PTS CRPS difference | REB CRPS difference | Reported-minute CRPS difference |
| --- | ---: | ---: | ---: | ---: |
| 0 | 9 | 0.000000 | 0.000000 | 0.000000 |
| 1–3 | 44 | -0.609582 | -0.137974 | -1.285643 |
| 4–9 | 126 | -0.197373 | -0.045399 | -0.454365 |
| 10+ | 338 | -0.082281 | -0.011869 | -0.155160 |
| Overlapping lagged shift | 21 | -0.175467 | -0.022649 | -0.266260 |

These are K0-minus-R0 point differences with no subgroup intervals. The role
group overlaps established-history rows. All 14 category diagnostics for every
group are in the receipt, including the TD worsening within the 4–9-history
group. Exact zero differences for nine cold starts follow by construction and
are not evidence that cold-start predictions are accurate or improved.

Reported-minute MAE was 5.614846 for K0 versus 6.255385 for R0; RMSE 7.172859
versus 7.856510 and CRPS 3.913093 versus 4.234684. Coverage remains unresolved:
K0's 95% workload interval covered **0.938104**, below mean predicted interval
mass **0.964426**, and below R0's observed coverage 0.947776. K0's intervals
were narrower (mean width 30.311412 versus 34.259188). These are rounded-minute
diagnostics, not exact-duration or participation validation.

Other cautions also remain. Observed zero TOV frequency was 0.386847 while K0
predicted 0.354970, versus R0's 0.356392. The observed fraction above K0's 95%
TOV endpoint was 0.029014 versus predicted tail mass 0.013477. For BLK the
corresponding values were 0.019342 versus 0.010732. These descriptive zero/tail
mismatches are retained without claiming a confirmed calibration failure or
allowing better mean scores to substitute for distributional qualification.

Execution ran from **2026-10-20T01:11:10.705240Z to
2026-10-20T01:14:56.988909Z**, taking **226.283679 wall seconds** and process
peak RSS **169,436 KiB**, within the fixed budgets. The receipt records actual
issuance ranges, all executed content hashes, protocol/cohort hashes and weekly
metrics for independent verification without forecasting again. No future paper
outcomes, pregame participation/role proof, calibrated prices, ticket dependence,
provider settlement or product qualification follows from this development run.

Independent read-only review verified the saved protocol, fingerprints, cohort,
clocks and negative findings, then rebuilt all 14 categories' three-model
aggregates, history-band pooled metrics and 2,000-draw cluster intervals from
retained summaries only. Its 3,018 checks agreed within floating roundoff
(maximum absolute difference 2.27e-13), including exact cold-start subgroup
equality. No forecasts were rerun. Earlier research receipts and 18 retained
reference records also matched their pre-existing committed bytes.

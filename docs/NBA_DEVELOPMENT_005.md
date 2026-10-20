# NBA DEV005: coherent count-support challenger

Status: source/protocol frozen after independent pre-scoring review; no DEV005
result generated or inspected. Exact pre-scoring commit will be recorded below.
This package stays on `research/nba-count-support-dev005`, with no merge,
deployment or live activation. R0, K0, DEV002, DEV003 and PROS004 remain frozen.
The separate October 20 scheduled operating pilot is not an input or a tuning run.

## Pre-scoring construction

One new model, `nba_joint_count_support_s0_v1` (S0), is registered under
`NBA-ALL13-JOINT-DEV-005`. Its constants are modeling assumptions chosen before
this comparison: mixture weight epsilon=0.10, negative-binomial shape r=2, and
half-count/half-appearance positive prior. There is no parameter search.

Let K0's eligible, weighted complete historical atoms have normalized weights
w_j, primitive means m_k, and effective size N=1/sum(w_j**2). Define
mu_k=(N*m_k+0.5)/(N+0.5). With probability 0.90, retain an entire K0 joint atom.
With probability 0.10, draw FG2M, FG3M, FTM, REB, AST, TOV, BLK and STL
independently from NB(r=2, mean=mu_k). Draw reported minutes from K0 in that
lane, independently of those counts. This specifies one joint probability law,
not independently repaired market marginals. The original K0 lane retains its
complete within-player dependence; the new lane assumes independent primitives.
No cross-player or ticket probability law is supplied. Unbounded support also
assigns tiny mass to unrealistic extremes; full support is not physical tail
validation.

All 13 requested categories plus PA derive from that law. PTS=2*FG2M+3*FG3M+FTM;
combinations use the same counts; DD/TD count PTS/REB/AST/STL/BLK >=10. TD<=DD.
The law is conditional on appearance; DNP and missing outcomes are not zero.
The NB lane gives every nonnegative primitive vector positive mathematical mass,
including unseen historical values, before any evaluation outcome is inspected.

The count mean is 0.9*m_k+0.1*mu_k, so it changes slightly. The NB variance is
mu_k+mu_k**2/2; marginal mixture variance also includes the between-lane mean
term. Zero probabilities and tails change as part of this complete construction.
For distinct primitives i,j, covariance is 0.9*Cov_K0(i,j) plus
0.09*(m_i-mu_i)*(m_j-mu_j). Count-minute covariance is 0.9*Cov_K0(count,minutes).
These assumptions attenuate dependence and may worsen forecasting, particularly
joint rare events. Arithmetic coherence does not validate those assumptions.

S0 preserves K0's reported-minute marginal exactly. Its diagnostics must match
within 1e-12. This experiment cannot fix K0's workload undercoverage, rounded
minute precision, role freshness or the separate blocked duration/share REB
experiment. Cold starts inherit K0's exact R0 fallback as the empirical component;
they still receive the declared NB lane, rather than a claim of exact S0/R0 equality.

## Common causal input and identity-only cohort

Recover the existing retained input
`dfa1c4345495eb3aa6b203f2e8309c89c112b6b78a36cd3d2c603d390776b6fc`
through `history_from_input_record`, `unpack_history` and `_panel_bytes`.
Lossless recovery must reproduce 26,645 rows / 1,231 games / 14,720,351 bytes,
SHA256 `489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c`.
No 20,000-row truncation or new source download is permitted. Source attribution,
raw hashes, old observation/update clocks and upstream exclusions remain those
of the retained record and `docs/HISTORY_RETENTION.md`. This recovery proves
content consistency, not original pregame availability or upstream authenticity.

Select eight consecutive UTC Monday-Sunday weeks, January 19 through March 15,
2026. In each week rank eligible games by SHA256 of the exact UTF-8 string
`NBA-ALL13-JOINT-DEV-005|20261020005|{week_start}|{event_id}`, followed by start
and event ID for ties, taking two complete games. Keep every eligible appearance
in each selected game, including genuine rounded-zero-minute appearances.
Fail before scoring if more than 500 rows; do not split games or reduce the sample.

Keep the existing stage-2, standard ESPN team/opponent 1-30, archived FINAL,
identified complete APPEARED cohort and upstream exclusions. Shared target T90
and cutoff-date 00:00 UTC freeze apply to all models. A prior row's start and
reconstructed outcome_available_at=start+24 hours must precede/satisfy that
freeze. Each donor's lagged context uses its own earlier cutoff. Refit K0 weights
and S0 means/effective size for each target from that eligible information only.
All eligible prior history is retained; later selected games may train on earlier
results only under those common availability predicates.

The archive was already inspected, normalized and used in prior development.
These weeks follow DEV003's window, but the design is informed by its results;
this is exposed chronological development, not confirmation. The fixed game
identity rule does not establish full-slate or player-population representativeness.
The operational pilot and PROS004 future reservation remain separate.

Metadata-only inventory: 350 appearances in 16 games, five cold starts,
338 targets with at least ten earlier appearances, six with 4-9 and one with
1-3. Two rounded-zero-minute appearances remain. There is no selected-game
or row overlap with the R0, DEV002 or DEV003 evaluations. Cohort identity hash:
`03d43b7c0560e9787dc5bff638d0088d2d33cdbfab719115642845805990db87`.

| UTC week | Games | Rows |
| --- | --- | ---: |
| 2026-01-19 | 401810474, 401810505 | 45 |
| 2026-01-26 | 401810539, 401810561 | 41 |
| 2026-02-02 | 401810602, 401810614 | 42 |
| 2026-02-09 | 401810626, 401810629 | 46 |
| 2026-02-16 | 401810654, 401810656 | 40 |
| 2026-02-23 | 401810703, 401810725 | 45 |
| 2026-03-02 | 401810738, 401810742 | 49 |
| 2026-03-09 | 401810813, 401810816 | 42 |

## Numerical and scoring contract

Use analytic NB probabilities and generating-function coefficient calculations,
not Monte Carlo histogram frequencies. Compute DD/TD through positive threshold
and Poisson-binomial recurrences inside the NB lane, then mix with K0. No
post-outcome probability floor, clipping, smoothing or score-based exclusion.

Prediction grids are numerical integration devices, never renormalized laws.
Declare omitted probability and first-moment bounds; bound omitted CRPS and
dependence calculations, record floating-roundoff checks separately, and fail
explicitly on a numerical budget violation. Exact observed coefficient likelihoods
must use the underlying law even when the value exceeds the prediction grid.
The frozen source/protocol supplies exact tolerances and hard numerical ceilings.

Compare unchanged R0, unchanged K0 and complete S0 on the same rows. Primary
family: 14 per-category paired mean discrete CRPS/RPS differences S0 minus K0.
Negative favors S0. S0-R0 and K0-R0 are descriptive anchors; there is no pooled
unscaled all-category score. Binary CRPS is Brier for DD/TD. Retain log losses
and unsupported counts, predicted/observed zeros, 50/80/95% intervals with actual
predicted masses and widths, and upper-95% tails. Preserve unsupported R0/K0
losses as infinite with explicit JSON statuses, never replace them with a floor.

Use 2,000 whole-week bootstrap draws, random.Random seed 20261020005. Sample
eight complete week clusters with replacement and divide resampled paired sums
by resampled row counts, without refitting. Report 95% percentile intervals and
one-sided upper bounds at 1-0.05/14 with linear interpolation. Only eight clusters
and roughly seven draws in that adjusted upper tail make these approximate
bounds fragile descriptive research evidence, not finite-sample guarantees.
Report DD/TD event counts, Brier differences and cluster uncertainty explicitly.

Dependence diagnostic: primitive variogram with power 1, scales all one and equal
1/28 weights on primitive pairs, computed from analytic expected absolute
differences under each complete law. This proper, non-strict joint diagnostic
does not uniquely identify dependence or validate cross-player probabilities.

A category can only be marked ADVANCE_FOR_FURTHER_RESEARCH if its primary
Bonferroni upper bound is strictly negative, support/numerical checks pass,
absolute zero discrepancy <=.05, absolute observed-minus-predicted interval
mass discrepancy <=.05 at every level, and upper-tail excess <=.02. DD/TD each
need >=20 positives and >=20 negatives; BLK needs >=20 nonzeros. Common workload
95% coverage must be within .03 of predicted mass and at most .01 below R0,
and S0/K0 minute diagnostics must agree within 1e-12. Failed guards and sparse
counts remain visible. No category splicing, whole-model promotion or product
qualification follows from any favorable diagnostic.

## Freeze, review and operating budget

One candidate, one registered execution, zero tuning trials. Limits: 64MiB /
100,000 input rows; 500 scored appearances; 900 wall seconds; 512MiB peak RSS;
16MiB result. Preserve failures instead of rerunning under adjusted settings.
Exact code/test hashes, selected identity manifest, input/provenance, cutoffs,
algorithm constants, numerical tolerances and budgets go into the immutable
protocol. Before scoring, independently review the integrated source and freeze,
commit/push it, then independently read back exact source and protocol from GitHub.
The integration owner records internal approval without requesting routine user
approval. A create-only attempt record prevents an accidental second execution.

Pre-scoring resource checks used invented event IDs and a fixed artificial
all-zero line, never any evaluation outcome. An initial pre-window fit plus
marginal evaluation took 5.943s including input; a later, larger 21,571-row prior
fit and synthetic diagnostic check took 6.082s / 108,684KiB. Cache profiling
measured first/same-day/new-day fits of 2.850/0.816/2.166s, peak 127,760KiB.
These timing-only checks support the unchanged 900s/512MiB budget; they establish
no forecasting result. Receipts: `dev005-input-recovery.json` and
`dev005-prescore-feasibility.json`. No parameter changed during feasibility.

This document will append the exact freeze, commands, measured costs and actual
per-category findings after that single run. Software tests, historical scores,
future issuance, statistical grading, website deployment, financial settlement
and betting qualification remain distinct evidence lanes.

The independent pre-scoring review is retained in `dev005-prescore-review.json`:
10,275 synthetic mathematical checks against independent SciPy/NumPy calculations
(maximum absolute difference2.75e-14), plus11,995 synthetic receipt replay checks
(maximum3.55e-15) and deliberate aggregate-tamper rejection. No real evaluation
outcome was scored. All12 declared source/test/verification files match inventory.
The integration owner approved the exact immutable `dev005-protocol.json` only
after that review. Before execution, GitHub readback must bind its committed SHA.

Exact one-run command after remote recovery:

```bash
python3 -m multisport_lab.development_005 \
  --input /tmp/nml-dev005/recovered.jsonl \
  --output evidence/research/dev005-result.json \
  --protocol evidence/research/dev005-protocol.json \
  --readback evidence/research/dev005-freeze-readback.json
```

The protocol-adjacent create-only `dev005-protocol-attempt.json` preserves the
single attempt even if an output filename changes. Failure is an actual result,
not permission to retune or restart. Independent score-only verification uses
`scripts/verify_dev005_result.py`; it fits or generates no new forecasts.

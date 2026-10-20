# NBA DEV005: coherent count-support challenger

Status: one frozen development comparison completed; mixed results. Source and
protocol remain unchanged. Independent verification and draft-PR delivery are
recorded below and in the handoff. No merge, deployment or activation.
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
(maximum absolute difference 2.75e-14), plus 11,995 synthetic receipt replay checks
(maximum 3.55e-15) and deliberate aggregate-tamper rejection. No real evaluation
outcome was scored. All 12 declared source/test/verification files match inventory.
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

## Actual single development comparison — October 20, 2026

Frozen implementation/protocol commit **`c2780d79bd4110582e14a75317af36fac0400bcb`** was pushed before scoring. Independent fresh GitHub readback completed at **08:56:02.243607Z**, binding all 12 source files and protocol payload SHA256 **`74c5430a8dc938c8f6e17a07e733af9aab5e17d429b754bcd5381a40d102c945`**. The create-only attempt was claimed at **08:56:20.240997Z**. Exactly one actual comparison ran from **08:56:20.246091Z to 09:05:30.638996Z**, with no code, parameter, protocol or population change.

All **350 appearances / 16 games / eight weeks** were scored under each complete law, with **zero post-score exclusions**. K0 used its kernel for 345 and exact R0 fallback for five cold starts; S0 then applied its registered mixture to every subject. Training pools contained **13,889–21,187** earlier rows and personal histories **0–66**; S0 effective sizes ranged **25.328–11,087.049**. Both rounded-zero-minute appearances remain.

Actual scoring/aggregation runtime was **550.392914 seconds**, peak RSS **232,580 KiB (227.13 MiB)**, within the frozen 900-second/512-MiB limits. Runtime starts after input/inventory preflight and includes model fits, scores and bootstraps. The result envelope is **8,427,627 bytes**, below its 16-MiB cap. Python **3.12.14 / Linux x86_64**, executable hash and actual invocation are retained.

### Per-category CRPS/RPS

Negative S0-minus-K0 differences favor S0. Intervals are descriptive whole-week percentiles; adjusted upper bounds use the registered 14-comparison allocation. No unscaled pooled category score is calculated.

| Category | R0 | K0 | S0 | S0 − K0 | 95% week interval | Adjusted upper | Interpretation |
| --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| PTS | 3.355518 | 3.293355 | 3.294962 | +0.00160648 | [-0.00601366, +0.00888203] | +0.01071683 | Worse point; inconclusive interval |
| PRA | 4.515494 | 4.394348 | 4.391242 | -0.00310527 | [-0.01257507, +0.00683525] | +0.00895831 | Lower point; inconclusive interval |
| REB | 1.321693 | 1.305738 | 1.306026 | +0.00028781 | [-0.00152498, +0.00214480] | +0.00287969 | Worse point; interval guard fails |
| 3PM | 0.610153 | 0.605967 | 0.606480 | +0.00051298 | [-0.00025226, +0.00132796] | +0.00152545 | Worse point; inconclusive interval |
| AST | 0.960380 | 0.940175 | 0.942287 | +0.00211138 | [+0.00123649, +0.00302004] | +0.00338697 | Worse; interval above zero |
| RA | 1.904602 | 1.861972 | 1.861655 | -0.00031735 | [-0.00359869, +0.00275103] | +0.00408019 | Lower point; inconclusive interval |
| PR | 4.040365 | 3.947495 | 3.946248 | -0.00124736 | [-0.00946999, +0.00631078] | +0.00843273 | Lower point; inconclusive interval |
| TOV | 0.598179 | 0.593552 | 0.593364 | -0.00018855 | [-0.00099901, +0.00060264] | +0.00082587 | Lower point; inconclusive interval |
| TD | 0.012457 | 0.012451 | 0.012507 | +0.00005553 | [-0.00010117, +0.00027277] | +0.00035796 | Worse point; only five events |
| DD | 0.039347 | 0.038949 | 0.039071 | +0.00012192 | [-0.00017363, +0.00044723] | +0.00056128 | Worse point; inconclusive interval |
| BLK | 0.272939 | 0.271944 | 0.271685 | -0.00025836 | [-0.00038412, -0.00008572] | -0.00001516 | Exploratory requirements met |
| STL | 0.465304 | 0.463293 | 0.462456 | -0.00083684 | [-0.00139971, -0.00021422] | -0.00000576 | Exploratory requirements met |
| BLK+STL | 0.608473 | 0.604770 | 0.603256 | -0.00151369 | [-0.00192560, -0.00112526] | -0.00097651 | Exploratory requirements met |
| PA | 3.797098 | 3.706881 | 3.708954 | +0.00207285 | [-0.00645860, +0.01027345] | +0.01283612 | Worse point; inconclusive interval |

S0 has seven lower and seven higher point CRPS values than K0. **AST regresses with its descriptive 95% interval entirely above zero.** Only **BLK, STL and BLK+STL** meet the predeclared exploratory requirements. This is permission to consider a later independently frozen study of the coherent model, not category splicing, a selected winning joint model, live admission or qualification. Eight clusters and the very sparse adjusted-bootstrap tail sharply limit inference.

All three models had **zero unsupported observed outcomes in every category on this sample**, and no likelihood underflow occurred. Thus the run contains no observed marginal zero-support case to demonstrate a realized gain on that failure mode. Joint-vector log likelihood was not a registered metric and was not computed; individual eight-count vectors may still be unseen in the empirical law. S0’s positive support is established by its construction and mathematical/software checks; this sample tests its broader distributional consequences. S0 log loss is lower than K0 for the 12 nonbinary categories but slightly higher for DD and TD. Finite log loss alone establishes no forecasting improvement.

### Calibration, rare events and dependence

Complete three-model zero, tail, log and 50/80/95% coverage/mass/width diagnostics are in [`dev005-category-summary.csv`](../evidence/research/dev005-category-summary.csv); full row records and uncertainty remain in [`dev005-result.json`](../evidence/research/dev005-result.json). These retain regressions and inconclusive findings, not only favorable rows.

S0 REB fails its 50% interval guard: **0.694286 observed coverage versus 0.641838 predicted mass**, a +0.052448 gap. Its 80/95% coverage is 0.911429/0.982857 versus mass 0.885267/0.978677. Its predicted zero rate is 0.109350 versus observed 0.085714. Wider or better-supported distributions do not automatically improve calibration.

**DD: 22 positives / 328 negatives.** S0 Brier/CRPS is **0.039070502**, versus K0 **0.038948577** and R0 **0.039346899**. S0-minus-K0 is +0.000121924, 95% interval [−0.000173634,+0.000447231]. Observed frequency is **0.062857**, with week interval [0.045711,0.078717]; S0 mean probability **0.070191**, K0 **0.070159**. The event-count requirement passes, but the primary bound does not.

**TD: five positives / 345 negatives.** S0 Brier/CRPS is **0.012506682**, versus K0 **0.012451150** and R0 **0.012457331**. S0-minus-K0 is +0.000055532, interval [−0.000101170,+0.000272775]. Observed frequency **0.014286** has interval [0.002976,0.026163]; S0 probability **0.004890**, K0 **0.005071**. Sparse positives fail the registered count requirement. No reliable rare-event or dependence claim follows.

Primitive power-1 variogram means: **R0 3.196112, K0 3.142433, S0 3.138114**. S0-minus-K0 is **−0.004319**, interval **[−0.012675,+0.002135]**. Its lower point does not establish improved dependence; the interval crosses zero and this diagnostic is non-strict. No cross-player or ticket law has been evaluated.

### Unchanged workload prior and numerical controls

K0 has lower point CRPS than R0 in **all 14 categories** on this new development window. Its descriptive intervals still cross zero for 3PM, BLK, STL, BLK+STL, TOV and TD. These reference-anchor comparisons are secondary and do not promote K0 or alter DEV003/PROS004. The earlier workload-prior benefit therefore has descriptive support here with category-specific uncertainty.

All **350** S0 reported-minute marginals and diagnostics equal K0 exactly. K0/S0 minute CRPS **3.868213**, MAE **5.552654**, RMSE **7.041597**, compared with R0 **4.014621 / 5.851395 / 7.358117**. K0/S0 95% observed coverage **0.968571**, predicted mass **0.964789**, width **29.171429**; R0 coverage **0.965714**, mass **0.964953**, width **32.902857**. Common workload guards pass on this sample. This unchanged-law result does not erase DEV003’s undercoverage, fix workload uncertainty or validate exact playing minutes/duration.

Largest prediction grid **1472**; largest declared CRPS omission bound **3.562e−14**; largest coefficient mass residual **2.221e−15**; largest variogram score omission bound **6.649e−17**. All are below frozen tolerances. These analytic-tail bounds and operational floating checks remain distinct from a rigorous interval-arithmetic certificate. No simulation histogram, renormalized finite tail, probability floor or clipping was used.

### Evidence, recovery and next task

[`dev005-protocol.json`](../evidence/research/dev005-protocol.json), [`dev005-freeze-readback.json`](../evidence/research/dev005-freeze-readback.json), the immutable attempt and result preserve the sole execution. Result payload SHA256 **`1c5f9882fac2b0272d3244f0bacbb11516526d75bb66e4287d1441091a3193e3`**; complete file SHA256 **`b535f38e1d5604ee4ab59dae397344b76f18fc2871f9967cb56ccf961abd3ac2`**. Do not rerun the historical one-run command above. Recover/replay retained evidence instead:

```bash
python3 scripts/verify_dev005_result.py \
  --result evidence/research/dev005-result.json \
  --protocol evidence/research/dev005-protocol.json
```

The half-count/half-exposure regularizer estimates the generator mean from weighted moments; fixed NB shape 2 is an explicit dispersion assumption, not an exact conjugate posterior fit. Full support also allocates mass to unrealistic extremes and weakens count/minute dependence. The fixed mixture remains a research candidate with mixed results. **No parameter or category has been changed after scoring.**

Next concrete research task: audit the saved row-level zero/interval and rare-event/dependence diagnostics, then specify any revised support/dependence mechanism as a new model and experiment on a separately frozen sample. Do not retune DEV005, substitute it into PROS004 or today’s operating pilot, or splice its three favorable categories into K0. No prospective issuance, new statistical ledger grade, financial settlement, qualified ticket or website deployment was created by this package.


Independent score-only verification completed **34,880 checks**, maximum numeric
difference **7.106e−15**, with no forecast generation/refitting. It confirms the
exact protocol/source hashes, all 14 categories, causal clocks, complete cohort,
three paired comparisons, bootstrap bounds, guards and minute identities.
`dev005-result-verification.json` preserves that proof. The append-only
`dev005-verification-interpretation.json` explicitly limits the no-zero-support
finding to category marginals; it preserves the original review rather than
silently changing its clock or wording. No joint-vector log score was registered.

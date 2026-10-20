# NBA complete-category chronological development comparison 002

Protocol `NBA-ALL13-JOINT-DEV-002` compares two fixed complete-line empirical
research distributions. It is a broader **development** comparison following
the exposed 200-row R0 pilot, with no untouched confirmation claim, tuning,
model selection, promotion rule, ticket qualification or prospective paper
results. The original R0 pilot, model implementation and immutable receipts
remain unchanged. The REB B0/B1/C1 experiment is separate and is not executed.

## Specification before scoring

The exact input is the original 26,645-row normalized panel with byte SHA-256
`489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c`.
The data owner independently checked the panel under the strengthened importer:
zero FGM component contradictions and no reconciliation failures were observed.
This is ESPN source-stage-2, archived FINAL, standard team/opponent IDs 1–30,
complete identified APPEARED rows. Source stage 2 is retained as a source
classification, not a claim about all competitions' rules. Existing upstream
exclusions remain recorded separately; the filtered input does not establish
complete roster, as-of publication or source permission.

Use eight complete UTC Monday–Sunday weeks from **2025-11-24 through
2026-01-18**. In each week, choose the first two eligible games ordered by
`(event_start, event_id)`, and retain every eligible appearance in those games.
This selects 16 games and 338 player-game appearances, with weekly counts
43, 46, 42, 40, 39, 44, 40 and 44. The cap is 400 appearances; exceeding it
fails before scoring rather than splitting a game or omitting outcomes.
The identity-only inventory and exact game list are included in the protocol
receipt before scoring. No future score determines inclusion.

All earlier eligible history from the source beginning 2025-10-21 is available
for expanding-window training, including earlier development weeks only when
their reconstructed outcomes meet the current cutoff. Each target uses exactly
T90, and its history freezes at **00:00 UTC on the T90 cutoff date**. Earlier
event starts and `event_start + 24 hours` reconstructed completion bounds must
both meet the existing R0 eligibility rules. Same-day results, upcoming actual
minutes, role/lineup knowledge and target outcomes never enter. The completion
bound and archived starts remain reconstructed research conventions, not proof
of historic publication or an authentic pregame schedule.

## Two fixed coherent distributions

R0 calls the existing `baseline.forecast_reference` unchanged: 28-day
half-life, five appearance equivalents of shrinkage from personal earlier
complete stat lines toward the same league pool. L0 is the **league-only**
recency-weighted empirical distribution on exactly those completed lines,
with the same 28-day half-life and no personal component. A cold-start R0 and
L0 therefore agree. This isolates personal-history shrinkage relative to an
unchanged league reference; there are no additional model families or searches.

Every atom preserves its observed minutes and FG2M/FG3M/FTM/REB/AST/TOV/BLK/STL
together. All 13 requested categories and optional PA derive inside the atom,
including scoring reconciliation, combinations and five-stat DD/TD. L0 caches
only the training-only daily league law. R0 may receive that already-validated
eligible pool rather than the whole source; its resulting weights and canonical
input hash are identical because excluded rows do not affect either quantity.
Synthetic tests check that equivalence. No marginal is independently aligned,
replaced or smoothed. Finite support, zero probabilities and infinite
unsmoothed log losses remain explicit limitations.

## Scores and week-cluster uncertainty

Report each category's mean discrete CRPS/RPS for both models and the paired
player-row mean difference **R0 minus L0**; negative favors R0 on this sample.
Do not pool raw scores across categories with different scales. Report DD/TD
Brier and unsmoothed log diagnostics, zero and tail behavior, and 50/80/95%
interval coverage alongside each interval's predicted mass. Keep minutes errors
and intervals at documented reported precision separate from count targets.
An infinite model log loss makes its aggregate log mean null with an explicit
infinite status/count, never an omitted row or a repaired probability.

Use **2,000** complete-calendar-week cluster bootstrap replicates with fixed
Python `random.Random` seed **20261020**. Each replicate draws eight registered
week clusters with replacement and retains their selected games and every
player row. Recompute the paired sum of score differences divided by the
resampled number of rows, preserving unequal week sizes. Report two-sided 95%
percentile intervals with linear interpolation at probabilities 0.025 and 0.975.
Binary CRPS equals Brier for DD/TD, so their paired Brier interval is the same.
Weekly model metrics and row counts remain in the result for inspection.

Eight clusters provide limited uncertainty information. The first two UTC games
each week form a fixed sparse sample, not a representative full-slate sample.
The bootstrap conditions on the already-issued reconstructed forecasts and does
not refit models in each replicate. Week clusters preserve within-week dependence
but do not remove possible dependence or drift between successive weeks.
The 14 per-category intervals have **no multiplicity correction**; they are
descriptive development diagnostics and cannot authorize selection or promotion.
This comparison does not validate same-game/cross-player ticket dependence,
DNP probabilities, current quotes, settlement or economic eligibility.

## Execution and evidence

`python3 -m multisport_lab.development_002 --inventory-only` produces an immutable
identity/timing inventory and exact proposed protocol without forecasting or
scoring. Evaluation additionally requires an immutable protocol receipt with
the same full specification, actual `recorded_at` clock and approval by the
integration owner. The runner rejects any changed input, cohort, window,
parameters or model list. No scoring occurs until that approval is frozen.

Inputs inherit the bounded 64-MiB/100,000-row source validation. Registered
evaluation limits are **900 wall seconds and 512 MiB**. The process also caps
virtual address space at 512 MiB. A missing cluster, integrity failure, code
change during execution or resource failure aborts the whole run with no partial
score publication. There are no post-score exclusions or automatic restarts.
Actual issuance and execution clocks, input/protocol/code hashes, weekly cohort,
pool/cold-start/rounded-zero counts and runtime are recorded. Historical results
remain `RECONSTRUCTED_RESEARCH`, conditional on eventual appearance.

## Observed registered run, 2026-10-20

The integration owner froze [`dev002-protocol.json`](../evidence/research/dev002-protocol.json)
at 2026-10-20T00:13:45.256745Z, before scoring. Its payload SHA-256 is
`23e6df68ec536e96b6ae2cbf7aaf7e43300d6bc859046a3dbeb9f341127699d4`.
The create-only [`dev002-results.json`](../evidence/research/dev002-results.json)
records the single execution and all model, week, zero, tail, interval and
reported-minute diagnostics. The original R0 evidence was not rerun or changed.

Both models scored **all 338 appearances in all 16 games across all eight
registered weeks**, with no post-score exclusions. There was one cold start.
The selected sample happened to contain no rounded-zero-minute appearances;
the source's rounded-zero appearances were retained in eligibility and training.
Pools contained 5,029–12,182 earlier appearances and personal histories zero to
38. No actual upcoming workload was supplied.

The sample has two material cautions: R0's **TD Brier/CRPS was higher** than
L0's, and **one PR outcome had zero empirical support under both models**,
making each model's aggregate PR log loss infinite. These findings are retained
alongside every category's results, without smoothing, omissions or retuning.

| Category | R0 mean CRPS | L0 mean CRPS | R0 minus L0 | 95% week-cluster percentile interval |
| --- | ---: | ---: | ---: | --- |
| PTS | 3.196459 | 4.550093 | -1.353633 | [-1.603322, -1.093998] |
| PRA | 4.223587 | 6.386946 | -2.163359 | [-2.461103, -1.866392] |
| REB | 1.325169 | 1.805928 | -0.480758 | [-0.538199, -0.426202] |
| 3PM | 0.580209 | 0.700210 | -0.120001 | [-0.147669, -0.092839] |
| AST | 0.849243 | 1.223152 | -0.373909 | [-0.423691, -0.318320] |
| RA | 1.773018 | 2.499865 | -0.726847 | [-0.794485, -0.655234] |
| PR | 3.869129 | 5.624230 | -1.755100 | [-2.024357, -1.490629] |
| TOV | 0.607264 | 0.713808 | -0.106544 | [-0.142229, -0.072279] |
| TD | 0.003236834 | 0.002959662 | +0.000277172 | [+0.000001325, +0.000587671] |
| DD | 0.064930598 | 0.076085831 | -0.011155233 | [-0.020373030, -0.002253769] |
| BLK | 0.297275 | 0.339411 | -0.042137 | [-0.053886, -0.028198] |
| STL | 0.459034 | 0.481811 | -0.022778 | [-0.040987, -0.002330] |
| BLK+STL | 0.628148 | 0.679813 | -0.051665 | [-0.083591, -0.016697] |
| PA, optional | 3.553181 | 5.338004 | -1.784823 | [-2.077539, -1.507833] |

Raw CRPS was lower for R0 in 13 of these 14 categories; TD moved in the opposite
direction. The scores have different target scales, and no pooled target score
or model-selection conclusion is defined. The intervals describe this sparse
eight-cluster development sample, with no multiplicity correction or confirmation
claim. They are not evidence that any market or ticket policy qualifies.

There were **28 DD events and one TD event**. Mean DD probabilities were
0.079087 (R0) and 0.073578 (L0), versus the sample rate 0.082840. Mean TD
probabilities were 0.006392 and 0.005621, versus the sample rate 0.002959.
The TD sample is far too small to establish rare-event reliability. Binary CRPS
equals Brier here; TD log loss favored R0 (0.016781 versus 0.021184), while its
Brier favored L0. Both diagnostics remain visible; neither is used to select a
preferred model after results.

Zero/interval/tail diagnostics also remain unresolved. For example, observed
zero TOV frequency was 0.399408 versus R0's mean predicted 0.356382; zero STL
frequency was 0.523669 versus predicted 0.482608. R0's observed fraction above
the 95% BLK interval endpoint was 0.020710 versus mean predicted tail mass
0.010003. These are descriptive mismatches, not an independently confirmed
failure threshold or a calibrated-probability claim. The full receipt retains
every category, both models, all three intervals and each predicted interval
mass so favorable score changes cannot conceal coverage or tail weaknesses.

Reported-minute mean MAE was 5.367118 for R0 versus 8.286461 for L0; RMSE was
6.621316 versus 9.932516 and CRPS 3.603833 versus 5.682066. R0's 80% interval
covered 0.890533 of outcomes against mean predicted interval mass 0.839283.
These diagnostics concern rounded reported workload; they do not establish
exact-second exposure, share calibration or the proposed REB experiment.

Execution ran from **2026-10-20T00:14:01.938278Z to
2026-10-20T00:16:38.809969Z**, taking **156.871699 wall seconds** with process
peak RSS **96,232 KiB**, within the frozen budgets. The receipt records the
exact command and source fingerprints at repository HEAD
`cde185088f032db587e1fb10845cd84541ef0a8b`; the new development runner was
uncommitted then and is identified by its executed content hash. No scoring
code changed after results were observed. There is no promotion, confirmation,
selection-policy qualification or prospective paper result from this run.

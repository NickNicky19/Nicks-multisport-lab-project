# NBA complete-line research reference R0

Implementation: [`multisport_lab/baseline.py`](../multisport_lab/baseline.py).
Protocol `NBA-ALL13-JOINT-001`, model `nba_joint_empirical_r0_v1`, feature
`nba_pregame_features_v1`, cutoff `nba_cutoff_90m_v1`, panel
`nba_chronological_panel_v1`. This is one fixed development prototype, with no
hyperparameter search or promotion decision. The integration owner records the
protocol and each evaluation cohort before examining its scores in
[`DECISIONS.md`](DECISIONS.md). This reference is distinct from B0/B1/C1 in
[`NBA_REBOUNDS_EXPERIMENT.md`](NBA_REBOUNDS_EXPERIMENT.md); it changes none of
that experiment's definitions, tuning budget or unresolved confirmation fields.

## Population, identity and timing

R0 forecasts **conditional on appearance**. `HistoricalAppearance` requires
resolved namespace/event/player/team/opponent identity, retrospective UTC event
start, reconstructed completed-outcome availability bound, reported minutes,
their precision, and all eight primitive counts. DNP is excluded by the source
adapter and remains a separate outcome; missing fields or unresolved identity
are reported coverage failures. A missing count or missing minutes is never
converted to zero. Pooling is league-wide within NBA and one resolved identifier
namespace; the default namespace is ESPN and must not be confused with NBA IDs.

The target cutoff is exactly 90 minutes before its declared event start. All
history is frozen at **00:00 UTC of the cutoff date**. A historical row enters
only if its event start is strictly before that freeze and its outcome bound is
at or before it. The target event is always excluded. This deliberately excludes
same-cutoff-date outcomes, even when a game finished before T90. Using the event
date instead would leak for a game shortly after UTC midnight whose T90 is on
the previous date. Duplicate event/player identities and conflicting starts for
one event fail validation even when those rows would otherwise be excluded.

The start and availability clocks in an archive do not establish authentic
historical availability. All generated artifacts remain
`RECONSTRUCTED_RESEARCH`. The forecast reads its issuance clock at actual
execution; it cannot accept a caller-supplied historical issuance time. It rejects
execution before T90. Reconstruction may occur after the target event, which is
explicitly not a captured pregame forecast. A genuine future captured forecast
requires its actual issuance at or after T90 and strictly before event start,
immutable capture retention, and a separate capture path; changing this reference's
lane label cannot establish those facts.

`trained_through` is the latest reconstructed outcome bound among included rows.
The canonical SHA-256 input hash includes sorted eligible rows, identity, timing,
precision and protocol versions. Excluded future/same-day rows do not affect the
hash. Hashes establish content identity, not upstream authenticity or permission.

## Fixed pooling and complete-line dependence

For each eligible appearance j, let

```text
d_j = elapsed days from historical event start to the target T90 cutoff
w_j = 2 ** (-d_j / 28)
L_j = w_j / sum_league(w)
P = sum_target_player(w)
probability_of_line_j = (1[player_j = target_player] * w_j + 5 * L_j) / (P + 5)
```

Thus the prior contributes exactly five appearance equivalents. The league pool
includes the target player's *earlier* appearances; the target event and future
outcomes never enter. A cold-start player receives only the recency-weighted
league distribution. A nonexistent pool is a feasibility failure. League weights
are computed relative to the latest eligible event for numerical stability,
which is algebraically identical after normalization. Extremely old negligible
weights can underflow at floating precision; no tail mass is invented for them.

Each atom carries the **same observed row's** minutes, FG2M, FG3M, FTM, REB, AST,
TOV, BLK and STL. The distribution is an exact weighted empirical measure; there
is no Monte Carlo seed, sample alignment or independent marginal sampling.
Observed workload and all within-row co-movement are preserved together. There
is no separate role/pace adjustment or upcoming actual minutes input. Such
features need their own verified timing and a new registered challenger.

Scoring and every combination are derived inside the atom:

```text
PTS = 2*FG2M + 3*FG3M + FTM      3PM = FG3M
PR = PTS + REB                   RA = REB + AST
PRA = PTS + REB + AST            BLK+STL = BLK + STL
PA = PTS + AST                   # optional additional category
k = number of [PTS, REB, AST, STL, BLK] values >= 10
DD = int(k >= 2)                 TD = int(k >= 3)
```

All 13 requested markets plus optional PA therefore share one coherent outcome
law. Count primitives must be nonnegative true integers. The data adapter must
also reconcile scoring, attempts and rebound components against the raw source;
the forecaster cannot establish provenance by checking supplied primitives alone.

## Minutes and finite empirical tails

Minutes are finite and nonnegative. Exact zero minutes is not an appearance.
A documented `rounded_whole_minutes` appearance may legitimately report zero,
and remains in the population. R0 does not divide by minutes. Exact seconds use
`minutes_precision="seconds"`; source adapters convert seconds into minute
units explicitly. A missing minutes value remains a coverage failure. No fixed
48-minute cap excludes overtime. When verified final duration is supplied it
must be `48 + 5*overtime_periods` and bounds played minutes with rounding
tolerance. Without duration, reported minutes cannot exceed elapsed time to the
completed-outcome bound, but that permissive check does not certify duration.

The distribution has **finite observed support** with zero probability outside
it. There is no fitted tail, smoothing, truncation of an underlying infinite law,
or claim that the empirical maximum is a physical maximum. Rare-event and tail
performance can be weak, and an unseen observed outcome has infinite unsmoothed
log loss. Do not repair that loss after inspection by changing support. DD/TD
probabilities may be exactly zero; those research probabilities are unqualified
for ticket valuation. Complete-line resampling establishes within-player
coherence but no same-game/cross-player joint law or coherent team minutes.

## Evaluation interface and limits

```python
forecast = forecast_reference(history, ForecastTarget(event_id, player_id, start))
artifact = forecast.to_record()
report = evaluate_forecast(forecast, observed_primitive_line)
```

`forecast.support` contains weighted complete lines; `forecast.marginal("PRA")`
returns the resulting count PMF. `evaluate_forecast` computes each category
individually: exact weighted discrete CRPS/RPS, mean and median, mean absolute
and squared error, unsmoothed observed-outcome log loss, zero mass, support limits,
50/80/95% central intervals, their predicted mass, observed coverage and width,
and tail diagnostics above the 95% interval endpoint. DD/TD also receive Brier
scores. The CRPS identity includes observations beyond empirical support:

```text
CRPS(F,y) = E|X-y| - 0.5*E|X-X'|
```

The implementation uses sorted weighted support rather than a finite CDF cutoff
or an O(n squared) pairwise loop. On integer counts this equals the unnormalized
RPS over the full nonnegative count CDF. When observed probability is zero the
JSON log-loss field is null with status `ZERO_SUPPORT_INFINITE_LOSS`; null does
not mean an omitted row or finite score. An aggregate log-loss report containing
such a row must report the infinite loss and its count.

Minutes have separate mean-error, weighted CRPS and interval diagnostics at the
documented reported precision. Rounded-minute diagnostics do not establish
second-level workload quality and do not admit the rebound share/duration
experiment. Optional `variogram_score` evaluates the eight primitive counts
within a player, using fixed power 1/2 and equal pair weights. It requires explicit
positive per-count scales, frozen before evaluation. It is not strictly proper
for the full joint law and does not validate ticket dependence.

The evaluator does not choose folds, holdouts, thresholds or source cohorts.
Those must be frozen separately, with eligible/common counts, omissions, cold
starts, actual input hashes, model revision and runtime. No unscaled average
across different categories is a cross-category accuracy result. A bounded
historical development smoke run is not confirmation, prospective paper evidence,
product qualification or a website deployment. Future paper outcomes can be
recorded only after the relevant events occur.

Synthetic checks in `tests/test_baseline.py` cover timing, leakage, issuance,
identity, precision, pooling, cold starts, row dependence, scoring/coherent sums,
DD/TD, exact CRPS, intervals, log-loss handling and the optional joint diagnostic.
They verify software behavior only; real-data results belong in the separately
identified development report and handoff record.

## Bounded development pilot CLI

[`research_pilot.py`](../multisport_lab/research_pilot.py) accepts the exact
`NBAPlayerGame.to_record()` JSONL schema. It validates identities, duplicate rows,
scoring/rebound reconciliation and the predeclared cohort before forecasting.
The cohort requires ESPN namespace, source `season_type="2"`, standard team and
opponent IDs 1–30, explicit FINAL status, APPEARED participation, complete
primitives/minutes and known precision. Source stage 2 is a retained source
classification, not a universal assertion about competition rules; All-Star
games in the same source stage are excluded by the explicit team inventory.

The first two observed eligible UTC event dates with at least seven earlier
observed dates supply candidates. Sort by `(event_start, event_id, player_id)`
and retain at most the first 200, including poor outcomes, cold starts and
rounded-zero-minute appearances. If the first date fills the cap, the report
explicitly records that the second registered date supplied no scored rows.
Every forecast uses the R0 daily cutoff-date freeze and the fixed reconstructed
availability convention `event_start + 24 hours`.

Inventory mode performs no forecasting or scoring:

```bash
python3 -m multisport_lab.research_pilot \
  --input /tmp/nml-nba-audit/normalized.jsonl \
  --output /tmp/r0-inventory-preflight.json \
  --protocol evidence/research/r0-protocol.json --inventory-only
```

Evaluation requires a create-only pre-scoring protocol receipt binding the
exact input byte SHA-256, row count, warmup dates, target dates, fixed parameters,
200-row cap and diagnostic definitions. The first protocol receipt freezes
2025-10-28 and 2025-10-29 after seven observed dates from 2025-10-21–27; it is
development evidence and reserves no confirmatory window. The fixed primitive
variogram uses unit scales, power 1/2 and equal 1/28 pair weights. No tuning,
evaluation-driven exclusions or source-window substitution is permitted.

```bash
python3 -m multisport_lab.research_pilot \
  --input /tmp/nml-nba-audit/normalized.jsonl \
  --output evidence/research/r0-pilot.json \
  --protocol evidence/research/r0-protocol.json \
  --target-dates 2025-10-28 2025-10-29
```

Optional repeated `--source-hash NAME=SHA256` arguments record exact upstream
asset hashes. Output is an immutable finite-JSON aggregate receipt, readable by
`multisport_lab.integrity.read_receipt`; no player rows or forecast support are
published. It records the actual execution and issuance clocks, input/protocol/
code hashes, cohort and pool counts, category-specific scores, infinite log-loss
counts, workload diagnostics, cold starts, source precision and runtime. The
CLI bounds inputs to 64 MiB/100,000 rows and one run to 200 forecasts/300 wall
seconds; a budget failure publishes no partial evaluation. An upstream-filtered
input does not imply zero upstream exclusions; those remain separately recorded
in the data feasibility report and evidence summaries.

## First frozen development run, 2026-10-19

The create-only [`r0-protocol.json`](../evidence/research/r0-protocol.json)
receipt was recorded before scoring; its payload SHA-256 is
`61f82c1d1f715166f8789fb747d646ee4500df09368d960b8b3a9a43634a70f5`.
The single resulting [`r0-pilot.json`](../evidence/research/r0-pilot.json)
receipt used exact normalized input SHA-256
`489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c`.
Inventory-only validation matched all 26,645 filtered input rows, seven warmup
dates and both registered target dates before the evaluation command executed.
The input was already filtered; its zero additional exclusions does not erase
the upstream unidentified/DNP/incomplete/nonstandard/stage exclusions recorded
in [`DATA_FEASIBILITY.md`](../DATA_FEASIBILITY.md).

The first 200 sorted rows covered **200 players in nine games on 2025-10-28**.
They included 16 cold starts and two rounded-zero-minute appearances. All 200
were scored in every category; there were no post-score exclusions. The two
registered dates contained 411 candidates; the fixed cap omitted the remaining
211 before scoring, including every 2025-10-29 candidate. No result from the
second date is claimed. Training pools contained 716–899 earlier appearances;
individual player histories contained zero to three appearances.

| Category | Mean CRPS/RPS | Zero-support log-loss rows, of 200 |
| --- | ---: | ---: |
| PTS | 4.267494 | 1 |
| PRA | 6.091462 | 2 |
| REB | 1.661492 | 2 |
| 3PM | 0.665466 | 0 |
| AST | 1.173284 | 2 |
| RA | 2.432188 | 3 |
| PR | 5.377882 | 2 |
| TOV | 0.648693 | 0 |
| TD | 0.002640 | 0 |
| DD | 0.070140 | 0 |
| BLK | 0.301181 | 0 |
| STL | 0.446996 | 0 |
| BLK+STL | 0.603752 | 0 |
| PA, optional | 4.988766 | 2 |

These scores use different target units and must not be pooled or compared as
an equal-target accuracy measure. Any nonzero zero-support count means that
category's unsmoothed aggregate log loss is **infinite**, represented by a null
mean with explicit status and count in strict JSON. Such rows remain included
in CRPS and every other applicable diagnostic.

DD Brier was 0.070140 with 18 observed DD events; mean predicted probability was
0.064184 versus the observed rate 0.09. TD Brier was 0.002640 with only **one**
observed TD event; mean predicted probability was 0.002881 versus the observed
rate 0.005. A low score on this small rare-event sample establishes no reliable
rare-event accuracy or qualification. Binary CRPS equals Brier here. Rounded
reported-minute mean MAE was 7.962050, RMSE 9.795642 and CRPS 5.281158; those are
reported-precision diagnostics, not exact workload or minutes-share validation.
The fixed within-player variogram diagnostic was 0.656847.

Actual execution ran from 2026-10-19T23:02:52.548715Z to
2026-10-19T23:03:15.325474Z: 22.776781 wall seconds, process peak RSS 77,204 KiB.
The receipt records exact commands, source asset hashes, actual forecast issuance
range, protocol hash and executed source hashes. Execution occurred on the
uncommitted implementation tree above repository HEAD
`de86e92352f0fb5a76831275f6de6b256ce05434`; its source hashes identify the actual
code rather than implying that the old HEAD already contained it. No model or
scoring code changed after examining these results.

This is one early-season, conditional-on-appearance reconstructed **development
pilot**, with dependent player rows within nine games, no comparison candidate,
no confirmatory uncertainty interval and no promotion decision. It verifies
that the coherent complete-category research path executes on the audited panel.
It establishes no calibrated probabilities, model improvement, live value,
provider eligibility, ticket dependence, future paper outcomes or deployment.

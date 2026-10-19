# NBA-REB-OPPORTUNITY-001: integrate pregame minutes uncertainty

**Status: proposed, not run.** Target and design selected October 19, 2026. No
accuracy, calibration or profitability result exists for this experiment yet.

**Full NBA scope remains all 13 requested categories:** PTS, REB, AST, PRA,
PR, RA, 3PM, BLK, STL, BLK+STL, TOV, double-doubles (DD) and triple-doubles
(TD). PA is an optional additional category in the market registry. REB is the
first isolated improvement experiment within that full scope; it does not limit
the planned NBA baseline, market-discovery or grading coverage. Each category
still needs its own validated forecast/contract/settlement path before activation.

## Research question and why this target

Does integrating uncertainty about a player's minutes improve the full-game
rebounds distribution beyond a comparable model using one estimated minutes value?

Rebounds is a bounded first NBA mechanism test: player boxscores contain the target
and played minutes, and it avoids immediately building the additional shot-value
and conversion components required to model points. This is not a claim that
rebounds is the easiest or most profitable market. Existing NBA research may supply
a baseline after its code, source timing and target semantics have been inspected.

Use full-game official individual total rebounds. Preserve the overtime policy and
stat-provider definition. The initial model is **conditional on a player appearing
in the game**. DNP probability and venue void rules are separate outputs/admission
requirements; a conditional model is not sold as a complete unconditional ticket
forecast. On an appearance, a recorded zero rebound game remains a real zero.

One primary pregame horizon: 90 minutes before scheduled tip as known at capture.
Additional horizons are collection/diagnostic opportunities, not extra simultaneous
optimization targets. Late-changing start times and postponed games need explicit
versioned event handling. Future ticket decisions use their common ticket clock,
which may differ from this per-game research horizon.

## Data that the experiment actually needs

Minimum historical research panel:

- Stable game/player/team/opponent IDs; game date, season and competition stage.
- Played minutes with explicitly parsed units; official individual rebounds;
  appearance/DNP distinction; sufficient source rows to resolve missing outcomes.
- Completed prior player games, team games and elapsed rest days, shifted so that
  no current-game or later-game outcome contributes to any feature.
- An independently recorded data/version/hash manifest and fixed population rule.
- For the registered duration/share candidate and its matched control: verified
  final period count or regulation/overtime game duration for completed prior
  games. For standard NBA games, G = 48 + 5*O minutes, where O is completed overtime
  periods. Do not infer G from the maximum player minutes or an unverified sum of
  rounded player-minute fields. Source units, recording precision and completed
  game status must be reconciled before a share M/G is accepted.

Possible later inputs include timestamped injury/availability reports, starter/role
information available before the cutoff, rebound-chance tracking, teammate minutes
availability and pace estimates. **Do not require or use those in the first controlled
comparison until their historical coverage and availability clocks are verified.**
Today's roster, final starting lineup and a retrospectively updated injury field
cannot be relabeled as historical pregame knowledge.

Public NBA player-boxscore release assets are verified to exist, and primary injury
PDF examples are accessible. Their rows, completeness and exact 90-minute archive
coverage are not yet audited. Final period-count/duration availability in the
selected row source is also unverified. See SOURCE_CAPABILITY_MATRIX.md. Release
existence admits a feasibility check; it does not establish the model is runnable
as written. If verified duration is unavailable, this C1-versus-B1 protocol is
blocked pending that specific source requirement; do not substitute an unverified
duration estimator or a different minutes model after seeing results. B0/data
feasibility, other NBA categories and unrelated platform work can continue.

For reconstructed history, use only clearly lagged inputs and call the lane
RECONSTRUCTED_RESEARCH unless actual historical input availability is independently
verified. Result corrections can serve as a documented grading target; corrected
historic feature data do not prove what the real-time pipeline would have observed.

## Population and conditioning

Pre-register a deterministic player-game candidate universe using the historical
roster source if available. If only game logs are available, the first experiment
may evaluate conditional-on-appearance player-game distributions, but must say so
and report that no roster/DNP forecasting claim follows. It must not silently use
eventual appearances to claim an operational pregame selection universe.

Use the same player-game rows for all methods. Include low-minute and zero-rebound
appearances and documented cold-start cases; do not discard them after errors are
seen. If a method cannot forecast a row, report its coverage failure and apply a
predeclared common fallback or common cohort rule. Show both total eligible and
common scored counts. A smaller, retrospectively convenient cohort cannot win by
omitting difficult cases.

For future operation, freeze the roster/candidate universe at issuance and record
appearance/nonappearance outcomes for every candidate. Participation accuracy is
evaluated separately before combining the model with void-sensitive entry payouts.

## Small comparison: three forecasts, one primary candidate

### Shared history, mean and prior definitions

Use only completed prior games available to the relevant evidence lane. For a
historical player appearance j, let S_j = M_j/G_j be that player's share of game
duration. Weights are w_j = 2^(-d_j/H), where d_j is elapsed calendar days at the
forecast cutoff and H is a shared decay half-life. The same history and weights
are used by B1 and C1. Pooling is league-wide in this first experiment; no final
season role groups, injury features or opponent adjustments are added.

Compute the league share mean s_pool from earlier eligible appearances. Set the
player share estimate to:

    s_hat_i = (3*s_pool + sum_j w_j*S_j) / (3 + sum_j w_j)

The fixed prior strength is three appearance equivalents. Because the pool mean
is strictly between zero and one, s_hat_i must also be in (0,1). A cold-start
player receives s_pool. Impossible shares or unresolved rounded-minute records
are input-validation issues, not values silently clipped to improve performance.

Fit one league overtime law using each earlier completed game once, never once
per player. Let N be the game count, N_OT the count with O>=1, and T_OT the sum of
overtime periods across those overtime games. Fix uniform Beta(1,1) pseudocounts:

    q   = (N_OT + 1) / (N + 2)
    rho = (T_OT - N_OT + 1) / (T_OT + 2)
    P(O=0) = 1-q
    P(O=k) = q*(1-rho)*rho^(k-1), k>=1
    G = 48 + 5*O
    E[G] = 48 + 5*q/(1-rho)
    m_hat_i = s_hat_i * E[G]

Using the league duration law for an appeared player and treating share and game
duration as conditionally independent are explicit first-model approximations.
They may fail for low-minute players whose appearances depend on overtime. Keep
those appearances in the evaluation and diagnose that limitation. This is an
individual marginal experiment; it does not produce coherent team minute totals
or validated same-game joint distributions.

For rebound rate lambda, let mu_pool be total rebounds divided by total played
minutes in earlier eligible training appearances. With pooled prior exposure c:

    b_pool = c
    a_pool = c*mu_pool
    a_i = a_pool + sum_j w_j*R_j
    b_i = b_pool + sum_j w_j*M_j
    lambda_i | history ~ Gamma(shape=a_i, rate=b_i)

Rate is in rebounds per minute. Treat lambda as independent of the future share
and duration given the available history. Exponential weighting is a declared
shrunk/generalized estimation choice, not an exact stationary Bayesian posterior.
The finite-data pool and prior are identical for B1/C1. No player-specific extra
dispersion, matchup multiplier or market feature is introduced.

### B0: shrunk recent-outcome distribution

Use a recency-weighted empirical rebounds distribution with the shared H selected
for B1, and a fixed five-appearance shrinkage toward a training-only geometric
count distribution f_pool. Its mean is the earlier league rebounds-per-appearance
mean mu_R_pool, so it has positive support on every nonnegative integer:

    f_pool(r) = (1/(1+mu_R_pool)) * (mu_R_pool/(1+mu_R_pool))^r
    f0(r) = [sum_j w_j*1(R_j=r) + 5*f_pool(r)] / [sum_j w_j + 5]

This baseline uses no upcoming actual minutes or prop line. The pooled tail and
shrinkage are fixed before test use; do not repair a zero-likelihood surprise by
changing smoothing after inspection. If the training pool is too small or invalid
to estimate the stated prior, report a feasibility failure rather than fabricate it.

### B1: the matched deterministic-minutes control

Use the shared m_hat_i and rate model above, replacing uncertain future minutes
with that single value:

    R | M=m_hat_i, history ~ NB(shape=a_i, success=b_i/(b_i+m_hat_i))
    mean_B1 = m_hat_i*a_i/b_i
    variance_B1 = mean_B1 + mean_B1^2/a_i

This negative binomial is the Poisson-Gamma predictive distribution. B1 already
integrates the same rate uncertainty as C1; it holds only future minutes fixed.

### C1: beta share times overtime-aware duration — the one candidate

Use exactly the same s_hat_i, overtime law and Gamma rate parameters as B1:

    S | history, appeared ~ Beta(tau*s_hat_i, tau*(1-s_hat_i))
    M = G*S, with S independent of G conditional on history
    R | M=m, history ~ NB(shape=a_i, success=b_i/(b_i+m))

Its predictive PMF is:

    f1(r) = sum_{o=0..infinity} P(O=o) * integral_{s=0..1}
              NB(r; a_i, b_i/(b_i+(48+5*o)*s))
              * Beta(s; tau*s_hat_i, tau*(1-s_hat_i)) ds

This gives positive minutes within each possible game duration and allows more
than 48 minutes when overtime occurs. It models overtime from earlier completed
games; the target game's eventual overtime is never a pregame input.

The mean is matched by construction:

    E[M]_C1 = E[G]*E[S] = E[G]*s_hat_i = m_hat_i
    E[R]_C1 = E[R]_B1 = m_hat_i*a_i/b_i
    variance_C1 - variance_B1 = a_i*(a_i+1)/b_i^2 * Var(M)

**Isolation rule:** only the integration over future minutes changes. Forecast
means, mean-based MAE and mean-based RMSE must agree between B1/C1 within declared
numerical tolerance. A difference in those quantities is a failed isolation check,
not a mean-accuracy gain. Medians, full-distribution scores, intervals and tails
can differ; label median-based MAE separately if reporting it.

Use deterministic beta quadrature and the explicit infinite overtime law; avoid
Monte Carlo noise in the primary comparison. Start with 64-point Gauss-Jacobi
quadrature and refine to 128/256 only under a frozen numerical error criterion,
not as model tuning. Retain the law/parameters in the artifact. For overtime
truncation after K, both omitted probability q*rho^K and omitted duration first
moment q*rho^K*[48+5*(K+1/(1-rho))] have closed forms. Bound and report both, and
account for the resulting score/moment error as well as the rebound-count tail.
A small overtime probability tail is not the same object as the rebound tail.
Do not silently renormalize omitted overtime probability or move it to a rebound
overflow cell. Lock the evaluator's absolute CRPS-error tolerance at 1e-6 per row;
if the numerical implementation cannot meet it, withhold that row's C1 score and
apply the registered coverage-failure rule consistently.

The beta concentration tau is the only C1-specific tuning choice. Select it from
forward predictions in development folds. There is no residual-model alternative,
no extra feature family and no discretionary support transform in this experiment.
Missed-shot opportunities, lineup competition, positioning and conversion remain
possible later mechanisms. Actual rebound chances are retrospective unless they
are forecast using information available before the decision cutoff.

## Distinguish workload from production errors

Report minutes forecast error/interval coverage separately from rebounds scores.
A useful point-error decomposition, using pregame rate r_hat and point minutes
m_hat, is the exact identity:

    R_actual - m_hat*r_hat
      = (M_actual-m_hat)*r_hat + (R_actual-M_actual*r_hat)

The first term is the realized workload contribution under that pregame rate; the
second is the production-per-minute residual. The second includes environment,
opportunity mix, rate-estimation error and outcome randomness, so calling it pure
player efficiency would overstate the diagnosis. Squared-error contributions have
a cross-term and must not be presented as additive causal percentages.

Also run an explicitly labeled RETROSPECTIVE_ACTUAL_MINUTES diagnostic that feeds
M_actual into the unchanged rate model. It asks how much error remains when minutes
are supplied after the game. It is neither a pregame model nor a deployable upper
bound on forecast skill. Do not include it among admissible candidates or ticket
probabilities, and do not tune the pregame pipeline against its outputs.

## Forecast artifacts

For each row preserve target and conditional semantics, participant/event IDs,
start time as known, cutoff, issued clock, trained-through clock, model version,
evidence lane, input hashes, predictive PMF/CDF or weighted draws, mean/median,
intervals, tail truncation accounting and any availability flag. A normalized PMF
needs explicit tail mass; do not silently drop or redistribute the extreme tail.

When captured contracts exist, derive P(R>line), P(R<line) and P(R=line) from the
same distribution. For an integer line, equality is a push only if the actual
product's rule says so. Forecasting a zero outcome and grading a void are separate
operations. Prices do not enter the first sport-only model.

## Chronological design

The exact seasons are locked only after the feasibility inventory and prior-work
exposure check. A proposed development split is training through 2022–23,
rolling validation on 2023–24, and a later consecutive test season/block. The last
block qualifies as confirmatory only if neither this project nor imported prior
work has used it to choose models. If all historical seasons have been inspected,
use historical results for development and future captured games for confirmation.

All rows from a game remain together. Train/standardize/select priors only from
earlier games. For a same-day slate, every feature must respect the individual
cutoff; a late game cannot use a same-day earlier result unless that result was
actually final and available before the declared forecast cutoff. A simpler first
protocol may freeze all historical features at the start of the game date.

Use expanding-window refits with a fixed schedule. Do not use random player-row
splits. Keep all tuning inside development folds. Save every registered trial and
its selection criterion. Deduplicate replays at the event/player/horizon/model
identity; corrected data versions are revisions, not independent new games.

## Metrics and uncertainty

**Primary:** paired mean discrete CRPS (equivalently an unnormalized RPS over the
nonnegative count CDF), with lower better:

    RPS(F,y) = sum_{k=0..infinity} [F(k) - 1(y<=k)]^2

Use the same support/tail accounting for all models and include the contribution
beyond any computational cutoff. Report the raw score difference C1-B1, relative
improvement and game/week-block uncertainty interval. Aggregated player rows within
a game are not independent samples.

Secondary: log score with declared tail policy; explicitly mean- or median-based
MAE and mean-based RMSE; 50/80/95% interval coverage and width; zero mass; randomized PIT; high-tail
and low-minute behavior; minutes MAE/CRPS/coverage; missingness and cold-start
coverage. Discrete central intervals can contain more mass than their nominal
level: record each interval's predicted mass and compare observed coverage with
that mass as well as the nominal label. Do not fail a model merely because integer
intervals cannot achieve exact 50/80/95% mass. Threshold Brier/log score and reliability plots use actual captured
lines, with absent prices/quotes reported instead of reconstructed from today's
board. Selected-row calibration is separate from population calibration.

Within the separate full-category NBA baseline, compute PR/PA/RA/PRA from the
same joint draws. Evaluate each marginal and sum, with a predeclared scale/reference
if aggregating scores across targets, and assess joint dependence with appropriate
energy/variogram-type diagnostics. Marginally good models alone do not establish
correct same-game parlay probabilities. That joint evaluation is separate from
this first REB comparison; integration of a REB challenger requires reassessing
affected joint outputs rather than replacing one marginal without validation.

## Bounded tuning budget

There are at most **nine registered development configurations** for selection:

1. Evaluate the six shared settings H in {14,28,56} calendar days and pooled rate
   exposure c in {60,180} minutes using B1's forward-validation mean CRPS. Select
   the lowest score; for an exact numerical tie prefer larger c, then larger H.
   The share-prior strength of three, B0 strength of five, league-only pooling
   and the overtime pseudocounts are fixed, not additional search dimensions.
2. Freeze the selected shared settings for B1 and C1. Evaluate only the three
   C1 concentrations tau in {5,20,80} on those same forward development folds,
   selecting by C1 CRPS and preferring larger tau for an exact numerical tie.
3. B0 uses the selected shared H without independent tuning. Refit the final
   selected methods using only admissible earlier data on the registered daily
   schedule. Deterministic numerical refinement and a default B1 output are not
   additional statistical candidates.

Use a chronological development block, with all earlier games available to each
refit; no row's own or future outcomes enter its features, pools or overtime law.
The validation data may select these nine settings but cannot serve as the final
confirmatory holdout. If imported prior work has used a proposed holdout for model
selection, choose genuinely future captured games for confirmation.

CPU-only run. Fix bootstrap seed 20261019 and use 2,000 complete-calendar-week
cluster bootstrap replicates for paired uncertainty, retaining every game's rows
and recomputing the pooled player-row mean/ratio in each replicate. The week
partition and final evaluation window must be frozen before results; do not choose
block length after inspecting significance. Effective independent information is
not the count of player rows. Record fit time, rows and memory during feasibility.

The final test is one registered C1-versus-B1 comparison with the B0 adequacy guard.
Any changed candidate after final-test inspection gets a new experiment ID and
fresh confirmatory data. No third model family is added to this experiment.

## Promotion, rejection and inconclusive decisions

Define relative CRPS improvement as:

    I = 1 - mean_CRPS_C1/mean_CRPS_B1

Positive is better. Freeze delta=0.01 (one percent) as the smallest worthwhile
point improvement for advancing this research candidate. This is an engineering
choice, not a universal statistical threshold or a probability haircut. Compute
its paired 95% week-cluster bootstrap interval [L,U], and also report the raw
C1-minus-B1 score difference. Use ratio-based interval endpoints for the practical
benefit decision instead of comparing a raw-score interval to a percentage.

Before final-test access, lock numerical calibration/coverage non-regression,
B0-adequacy and runtime tolerances in the run manifest using development evidence.
The manifest must also fix the sample/window, refit schedule, numerical evaluator,
cohort/fallback rule and prior-work exposure declaration. This document remains
**proposed, not preregistered or executed**, until those fields and the chosen
shared settings/tau are recorded and frozen. Missing fields cannot be filled after
final-test results are seen.

Apply decisions in this order:

- **Integrity/numerical failure:** invalidate affected evidence and withhold
  affected performance claims. Repairing the defect does not license post-hoc
  cohort exclusions or another unreported attempt on the same holdout.
- **Promote to the next prospective research stage:** point estimate I>=delta,
  lower interval endpoint L>0, intact common population/mean isolation, and every
  frozen calibration, coverage, B0 and runtime guard passed. This establishes
  evidence of improvement sufficient to continue research; it does not establish
  that the improvement is at least one percent. That stronger claim requires L
  itself to exceed delta.
- **Reject this candidate:** if promotion does not apply and U<delta, the interval
  rules out the required practical benefit at its stated uncertainty level.
  Supported material worsening or a demonstrated failure of a frozen performance
  guard also rejects advancement. Do not reverse this inequality: L<delta alone
  does not rule out a worthwhile gain.
- **Inconclusive:** all remaining cases, including an interval spanning useful and
  insufficient improvement, too little effective independent information, or an
  unresolved data/conditioning guard. An unavailable duration source blocks this
  specific matched experiment; it does not block unrelated platform work.

Missing current bookmaker prices does not make the distribution comparison
inconclusive; it makes value evaluation unavailable. A passed conditional-on-
appearance 90-minute experiment does not validate DNP probabilities, longer ticket
horizons, a cross-sport ranking or a six-leg policy. Those require genuine future
quote/ticket evidence and the relevant participation, product and dependence
validation.

## Which NFL findings affect this experiment

Reusable direct concerns are complete UTC clock precision; strict JSON/finite
values; exact identity; source evidence matching its normalized interpretation;
unambiguous final/DNP/zero handling; immutable forecasts; and correct probability
versus projection semantics. Selectively carried generic helpers and exact source
revisions are documented in REUSE_PROVENANCE.md.

NFL matchup multipliers, receptions half-adjustment, NFL count rounding, NFL injury
heuristics, football target mappings and inherited lean scoring are not imported
into this NBA candidate. The current NFL runtime repair, offer display, deployment,
and hosting issues are not blanket prerequisites for this independent experiment.

NBA-specific labels, minutes units, roster/participation semantics and grading must
be verified before reporting NBA scores. If a defect affects those paths, withhold
the affected performance claims until corrected. Report unaffected feasibility and
software work without rerunning the broad NFL audit.

## References

- [NBA playing rules](https://cdn.nba.com/manage/2026/01/Official-2025-26-NBA-Playing-Rules.pdf)
- [NBA statistical client](https://github.com/swar/nba_api)
- [pbpstats](https://github.com/dblackrun/pbpstats)
- [NBA player-boxscore public releases](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_nba_player_boxscores)
- [Official NBA injury report archive page](https://official.nba.com/nba-injury-report-2025-26-season/)
- [Proper scoring rules, Gneiting and Raftery 2007](https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf)

The experiment design, budget and thresholds above are proposed research choices,
not findings or performance claims made by these source authors.

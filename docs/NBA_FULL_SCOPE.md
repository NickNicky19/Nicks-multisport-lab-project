# Full NBA scope: all 13 requested categories

**Status: comprehensive development scope; no trained forecast or live-feed admission.**
The registry is [`config/nba_markets.json`](../config/nba_markets.json). Every
requested category is mandatory project scope from the start:

| Requested category | Meaning | Development group |
| --- | --- | --- |
| PTS | Points | Scoring |
| PRA | Points + rebounds + assists | Rebounds, assists, combinations |
| REB | Rebounds | Rebounds, assists, combinations |
| 3PM | Three-point field goals made | Scoring |
| AST | Assists | Rebounds, assists, combinations |
| RA | Rebounds + assists | Rebounds, assists, combinations |
| PR | Points + rebounds | Rebounds, assists, combinations |
| TOV | Turnovers | Turnovers |
| TD | Triple-double indicator | Double/triple doubles |
| DD | Double-double indicator | Double/triple doubles |
| BLK | Blocks | Defensive events |
| STL | Steals | Defensive events |
| BLK+STL | Blocks + steals | Defensive events |

PA (points + assists) is registered as an **optional additional category**. It
does not replace, reduce, or change any of the 13 requested categories. NBA TD
means triple double; league-qualified identities prevent confusion with football
touchdowns. This NBA registry makes no automatic admission claim for WNBA or any
other sport.

## One foundation covering the complete category set

The planned baseline uses one candidate universe, one causal input panel, and a
shared pregame participation/minutes/role/pace process. Every primary statistic
uses that shared exposure information. A category group must not independently
rewrite minutes forecasts, choose a different final lineup, or quietly change
the population to improve its result.

The joint sample contract includes nonnegative integer draws for:

```text
FG2M, FG3M, FTM, REB, AST, TOV, BLK, STL
```

Each draw belongs to the same player, game, forecast cutoff, model version, and
sample ID. Shared latent exposure and a stated dependence construction are part
of the forecast. Independently drawing every marginal and aligning array indexes
does not demonstrate a defensible joint distribution. A simple training-only
resampling baseline of complete historical stat lines is a useful coherent
reference; its conditioning, shrinkage, cold-start and tail treatment must be
specified before scoring. A workload-aware candidate can then improve individual
mechanisms while preserving the shared sample interface.

Scoring follows the NBA's two-point, three-point and free-throw accounting:

```text
PTS = 2 * FG2M + 3 * FG3M + FTM
3PM = FG3M
```

See [NBA Rule 5: Scoring and Timing](https://official.nba.com/rule-no-5-scoring-and-timing/).
Input adapters must distinguish total FGM from two-point FGM; where the raw fields
support it, `FG2M = FGM - FG3M`, with nonnegative-integer and scoring reconciliation
checks. Forecasting PTS and 3PM without preserving their scoring relationship is
insufficient for the complete baseline. Modeling shot attempts and conversion
separately is a candidate mechanism; no such model is claimed to exist here.

Derive combinations from each joint draw:

```text
PR = PTS + REB
RA = REB + AST
PRA = PTS + REB + AST
BLK+STL = BLK + STL
PA = PTS + AST                    # optional additional category
```

This gives consistent sums, probabilities and intervals. Adding marginal
percentiles, or training an unrelated sum model and silently replacing the joint
result, does not. Direct sum forecasts may be separately evaluated challengers;
they are not allowed to create an incoherent production sample vector.

Double/triple doubles use all five main statistics, including steals and blocks:

```text
k = count(value >= 10 for value in [PTS, REB, AST, STL, BLK])
DD = int(k >= 2)
TD = int(k >= 3)
```

These indicator definitions follow the
[NBA's explanation](https://jr.nba.com/double-double-and-triple-double/). They also
preserve `TD <= DD`; a four-category achievement satisfies both. TOV and 3PM are
not additional double-double categories. Restricting these outputs to PTS/REB/AST
would discard valid defensive-stat outcomes.

## Broad data and offer audit from the start

The collection plan covers **all requested categories**, including their
underlying box-score fields and any legitimately available offers, from project
start. It does not wait for a rebounds experiment to finish before recording the
other categories' future evidence. Actual scheduled collection remains disabled
until the relevant source and operation have passed admission.

For each source/category, record access and reuse scope, exact statistic and units,
league/event/player IDs, period/overtime semantics, line/side/variant, price type,
both-side presence, event status, full capture clock, upstream update time or
unknown, source receipt/version, parser version, and settlement mapping. Preserve
complete entry terms where the product requires them. Count missing and unmapped
contracts. A website menu or registry row is not verified source coverage.

The broad statistical panel includes minutes and participation, FG2M/FG3M/FTM,
their attempt fields where available, REB and offensive/defensive components,
AST, TOV, BLK and STL. Availability, role, lineup, teammate and tracking features
are candidate inputs only where their pregame timing and coverage are established.
One source's lack of advanced tracking must not erase categories supported by the
common basic-data baseline.

Historical final box scores supply outcomes. Their current publication does not
prove what an earlier forecast knew. No actual upcoming minutes, final starting
lineup, corrected future totals or postgame projections enter pregame features.
Actual workload belongs only in a labeled retrospective diagnostic. If the first
historical panel covers appearances alone, the initial distribution is explicitly
conditional on appearance; DNP and venue voids remain separate. Future candidate
universes must be frozen before results, not recovered from eventual appearances.

## Coordinated category agents with a shared experiment contract

All groups work within **`NBA-ALL13-JOINT-001`**, using
`nba_pregame_features_v1`, `nba_cutoff_90m_v1`, and
`nba_chronological_panel_v1`. A run records those versions, model commit, dataset
hashes, permitted feature list, time splits, player-game cohort, exposure model
version, random seed/sample specification, and tuning budget.

| Work package | Deliverable | Shared dependency |
| --- | --- | --- |
| Foundation owner | Candidate universe, data panel, minutes/role/pace baseline, sample interface | One common protocol for every category |
| Scoring agent | PTS/3PM mechanisms and component diagnostics | Foundation exposure and features |
| REB/AST/combinations agent | REB/AST mechanisms and sample-derived sums | Foundation plus scoring draws |
| TOV agent | Turnover opportunity/rate candidate | Foundation and stated dependence |
| Defensive agent | BLK/STL counts, their sum and zero/tail behavior | Foundation and shared joint interface |
| DD/TD agent | Achievement probabilities and threshold diagnostics | Joint PTS/REB/AST/STL/BLK draws |
| Independent verifier | Timing, identity, coherence, evaluation and claims review | Frozen evidence from every group |

These are bounded work packages, scheduled in batches as agent capacity permits.
One integrator owns shared interfaces and integration; category agents work in
separate files or branches. Do not start 13 unrelated architectures or separate
minutes pipelines. The verifier must independently reproduce the comparisons and
report failed or unknown checks rather than infer correctness from passing code.

The primary research cutoff is 90 minutes before scheduled tip as known at issue.
Extra capture horizons are recorded for later experiments, with their own timing
evidence. A paper ticket uses its common issuance clock across all legs; forecasts
first issued after that clock cannot be retroactively placed in the ticket.

## Evaluation, tails and category-specific admission

Use common chronological development/validation/holdout windows and frozen
eligibility rules across all groups. Register candidate counts and tuning budgets
before holdout use. Report each category's coverage and proper distribution score:
RPS for integer counts/sums; Brier score plus log-score diagnostics for DD/TD.
Joint diagnostics assess dependence beyond the correctness of arithmetic sums.
Do not average unscaled RPS values across different statistic ranges and call the
result an equally weighted accuracy result; use per-category evidence and a
predeclared scale/reference if a platform aggregate is needed.

Examine count zeros and tails, interval coverage, threshold calibration, minutes
error and workload/efficiency diagnostics. DD is not automatically a rare event
for every player. TD is a sparse-event challenge for many player/role cohorts;
estimate actual training-window frequencies and uncertainty rather than applying
one universal rarity prior. Sparse positives, selection into offered markets,
and joint threshold dependence can leave a category inconclusive even when its
mean forecast looks sensible. Do not promote a rare-event model because it
usually predicts the majority outcome. Determine event-count/precision needs
from the frozen design before reading holdout results.

Promotion is per category and contract family. Derivation proves identities; it
does not automatically validate PRA, BLK+STL, DD or TD calibration. Control the
multiple-candidate/category selection process and evaluate the eventual ticket
selection policy prospectively. An unready category stays visible as planned,
research-only, missing-data or inconclusive, as appropriate. It does not disappear
from project scope, and it does not borrow another category's validation status.

[`NBA_REBOUNDS_EXPERIMENT.md`](NBA_REBOUNDS_EXPERIMENT.md) is the first controlled
change to this full-category baseline: whether integrating minutes uncertainty
improves REB forecasts. It changes one mechanism while other baseline components
remain fixed. Its narrow comparison is not a REB-only platform, a reason to delay
the complete category audit, or a replacement for the category work packages.

The REB challenger first runs in a separate research lane. Do not splice its
independent marginal into the baseline's joint samples and assume the dependence
is preserved. Integration requires an explicit joint construction and renewed
evaluation of affected sums, DD/TD probabilities and ticket dependencies before
those outputs can inherit the change.

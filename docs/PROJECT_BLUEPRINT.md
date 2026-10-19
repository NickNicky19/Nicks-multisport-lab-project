# Project blueprint: one interface, independently tested sports models

Prepared October 19, 2026. This is an implementation specification and research
proposal, not a performance report. The starter's code capabilities are listed in
README.md; source admission evidence is in SOURCE_CAPABILITY_MATRIX.md.

## 1. Concrete decision

Use Nick's new repository `NickNicky19/Nicks-multisport-lab-project`, with one new
Codex implementation owner. Build useful work now without making the current NFL runtime
correction a prerequisite. NFL remains external. Integrate Nick's existing MLB
model later through a versioned export, rather than recreating it here.

Choose NBA for the first feasibility experiment because its public statistical
archives, minute-level opportunity variables and possession tooling offer a
credible data path. This is a sequencing judgment, not a claim that NBA is easiest
to beat. Before building, inspect any existing NBA artifact Nick provides for
causal, reusable baselines; past reported results are not automatically validated.

Initial NBA scope contains all 13 requested full-game categories: PTS, PRA, REB,
3PM, AST, RA, PR, TOV, TD, DD, BLK, STL and BLK+STL. PA is an optional natural
addition. Collect the shared base-stat history and build a coherent reference
baseline for all these outputs. The full registry and agent workstreams are in
NBA_FULL_SCOPE.md and config/nba_markets.json.

The first isolated improvement experiment is full-game NBA rebounds with minutes
uncertainty. It is a scientific comparison inside the full platform, not a permanent
one-category project. Improve scoring, assists, turnovers and defensive statistics
through related workstreams sharing minutes/role/pace and one evaluation contract.
WNBA and NHL are candidates for the next independently admitted sport. Current
data, price, settlement and maintenance evidence determines their order.

For every sport, the long-term goal is comprehensive supported-category coverage.
Inventory the full observed market universe at admission. A first target narrows
the first validation task; it does not remove other categories from the roadmap.

## 2. What a high standard means

“Astra-level” is a research and engineering quality target. It cannot be certified
by an LLM name, the number of data sources, a million simulated games, a visually
confident confidence score, or historical wins chosen after seeing the results.

The standard is: correctly timed inputs; explicit outcome definitions; strong
simple baselines; distributions over workload and production; calibration; fair
chronological evaluation; frozen future forecasts; exact economic settlement; and
honest uncertainty. A complex method must demonstrate an improvement to displace
a simpler one. A better forecast may still produce no supported value opportunity.

LLMs can research mechanisms, write/test code, inspect inconsistencies and extract
structured information with source evidence. They do not supply unexplained final
win probabilities from prose intuition. Model parameters and probabilities come
from evaluated statistical procedures. CPU-friendly models are the first route;
GPU infrastructure and paid APIs are not prerequisites.

## 3. Shared architecture

Use a modular Python project with a compact static publication interface. Avoid
microservices until measured needs justify them. A sensible flow is:

1. **Observe:** source-specific adapters preserve evidence and original IDs.
2. **Normalize:** resolve events, participants and exact contracts; reject ambiguity.
3. **Forecast:** sport-specific modules produce versioned distributions using only
   information available at their declared cutoff.
4. **Evaluate value:** compare supported probability estimates to the exact offer
   or entry terms, preserving their evidence and conditioning.
5. **Freeze paper decisions:** record the full decision universe, selected ticket,
   quotes, forecasts, terms, joint method and policy before its first event starts.
6. **Grade and publish:** apply versioned outcome and settlement rules; preserve
   corrections without rewriting original forecasts or decision records.

The shared foundation owns identifiers, provenance, clocks, source health, evidence
lanes, contract and quote records, economics interfaces, paper ledgers and website
contracts. Sport modules own participation, opportunity, outcome distributions,
stat definitions and target-specific validation. Venue modules own settlement and
entry constraints. Those are different dimensions of the same project.

One bad hockey response must not replace a valid NBA publication. Publish each
sport's bounded report independently and assemble a manifest for the common UI.

## 4. Source and contract policy

The NFL code's ESPN/DraftKings-labelled collector produces mapped NFL thresholds;
it does not establish a new sport's two-sided sportsbook prices. The Sleeper
collector stores line and side multipliers. Those multipliers do not establish
the full entry payout or a sportsbook single-bet price.

Build the same general adapter pattern per sport, preserving:

`sport, league, event_id, player_id, stat_definition, units, period, extra_time_policy,
line, side, variant, venue, product, settlement_version`.

Keep original provider event/market/selection IDs, raw labels and source evidence.
Stable event identity must distinguish doubleheaders, tournament rounds and
rescheduled events. Preserve lineup/stat-provider differences, not just player
names. Exact decimals prevent a 5.5 line changing identity through floating-point
formatting. Observation time belongs to a quote, not the underlying market identity.

Quotes add provider, observed clock, source update clock if supplied, start time as
known at capture, market status, evidence hash, parser version and price semantics.
The line and price are one observation. An older price stays attached to its older
line; a fresh unpriced line can be displayed but cannot be called currently +EV.

Public, documented fantasy APIs and undocumented app Picks endpoints have different
access evidence. A processing library's license does not automatically cover every
underlying data feed. Record the actual access and output-use route; keep offline
modeling and authorized file imports moving when live collection remains unresolved.
Do not build a bypass or remove data checks to make a board look populated.

The planned ESPN inventory must assess all requested NBA categories. Prove the adapter
path first with a retained response from any observed supported full-game category,
then add representative
fixtures and mappings for each observed family. Each check must inspect:
request/response identity, all pages, bookmaker metadata, side and price fields,
period and settlement. If both sides' actual prices cannot be verified, classify it
as thresholds only. Provider ID 100 is not assumed to mean the same thing for every
sport forever. A failed request is distinct from a valid empty market board.

## 5. Forecast and evidence semantics

Every output declares target, horizon, model/version, feature cutoff, parameter
training cutoff, source snapshot hashes and whether it conditions on participation.
Represent DNP/void, zero production and actual zero minutes distinctly.

Suggested evidence lanes:

| Lane | What it establishes |
| --- | --- |
| SYNTHETIC_TEST | Specified software behavior on invented examples only. |
| RECONSTRUCTED_RESEARCH | Historical comparison using reconstructible data; no invented first-seen clocks. |
| VERIFIED_ASOF_REPLAY | Archived inputs can be verified as available at the stated historical cutoff. |
| REAL_TIME_CAPTURED | Actual future forecast/input capture, made before the declared decision deadline. |

A hash detects changes in saved content. It does not prove upstream publication,
truth, completeness or execution at a bookmaker. Keep those claims separate.

“Model-derived,” “market-derived” and “hybrid” are probability-source labels, not
degrees of certainty. A hybrid needs its own out-of-sample evaluation. For a
two-sided no-vig market reference, match the exact contract and exclude the offered
venue. Report number of remaining independent venues, time skew and method.
Multiple feeds from the same book are not multiple independent opinions.

For integer thresholds with refund-on-push pricing, two-sided normalization yields
probabilities conditional on no push. Do not feed those directly into unconditional
win/loss/push probabilities without estimating the push mass. An independently
validated full distribution can provide that mass; line-only data cannot.

## 6. One common ticket clock

Player experiments may compare forecasts at 24 hours, 90 minutes and 15 minutes
before each event. A ticket has ONE decision clock before its earliest leg starts.
At that clock all included forecasts, quotes, reference quotes and terms must be
available. Later games consequently have longer horizons.

Do not retrospectively assemble six independently favorable 15-minute forecasts
if the first game had already started when the sixth forecast existed. The actual
ticket policy must be evaluated using the information it could have assembled at
its common decision time. Report performance by the real decision clock and horizon,
not just the day on which a report file happened to run.

A successful 90-minute forecast experiment does not automatically validate a
six-hour forecast for a later leg. Each forecast at the ticket's actual common
cutoff needs support for that horizon and conditioning before a qualified claim.

## 7. Six-leg preference and economic objective

The objective is well-supported expected return and transparent success probability
under an actual product, with six as a preferred size. “Hit six” and “maximize
expected return” are different objectives. Show both. High all-win probability can
come with a poor price, and a large payout can come with a low all-win probability.

For illustration only, if independent legs each win with probability p, the chance
all n win is p^n. These invented numbers are not forecasts:

| Legs | Each leg 55% | Each leg 60% | Each leg 65% |
| --- | ---: | ---: | ---: |
| 2 | 30.25% | 36.00% | 42.25% |
| 3 | 16.64% | 21.60% | 27.46% |
| 4 | 9.15% | 12.96% | 17.85% |
| 5 | 5.03% | 7.78% | 11.60% |
| 6 | 2.77% | 4.67% | 7.54% |

Six 60% legs have a 4.6656% all-win chance under independence. For an all-or-nothing
entry paying gross multiplier D, the no-void EV is D*p_all - 1. Break-even would
require approximately 21.43x gross in that example. This is hypothetical arithmetic,
not a current Sleeper/DraftKings product or payout. Six 70% independent legs would
still all win only about 11.76% of the time.

For a sportsbook single with win/loss probabilities and refund-on-push/void:

`EV = p_win*(decimal_odds - 1) - p_loss`.

For a full entry with joint state vector z and gross returned stake D(z):

`EV = sum_z P(z | information_at_decision)*D(z) - 1`.

This expression handles partial-win payouts, void reductions and refunds if the
actual table and joint probabilities are supplied. The starter implements this
arithmetic; it does not infer or certify provider rules.

Sleeper's current rules discuss guaranteed contest payouts and pool awards. A
bounded first analysis can model the verified guaranteed payout component and
explicitly leave pool upside unvalued. If it is a genuine guarantee for every
modeled state, this is a payout lower bound conditional on the model assumptions;
it is not a lower confidence bound for real profitability. Never silently equate
it with complete contest EV. A pooled contest requiring opponents' entries cannot
be fully valued from the selected players' marginal probabilities alone.

All ticket legs must belong to one eligible venue/product and rule variant. A
DraftKings contract and a Sleeper contract cannot be combined and called an offered
entry. Start with different players and different events for suggested tickets.
Same-game and repeated-player combinations require explicit eligibility and joint
dependence support. Different events make an independence approximation more
plausible; they do not prove it or eliminate shared parameter uncertainty.

The eventual selector should consider n in 2..6, calculate supported complete-entry
economics, enforce fixed exposure/overlap constraints, then apply the preregistered
six-preferred policy. Do not rank by raw projection-minus-line gap across stats or
sports. For pick'em entries, a leg need not have a meaningful standalone EV at all;
the entry is the economic object. No undocumented probability haircut is allowed.

## 8. Validation and ticket scorecards

Distribution accuracy, calibration and financial performance are three different
tests. Use a proper full-distribution score as the forecast experiment's primary
metric. Keep threshold calibration at actual captured lines and selected-candidate
calibration as separate diagnostics. Log-score/CRPS foundations are described by
[Gneiting and Raftery (2007)](https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf).

The whole ticket-selection policy must run prospectively on a frozen universe.
Logging only winning tickets or only the model's largest positive gaps cannot
establish future selection skill. If the engine searches many combinations, report
the search space and constrain tuning on development data. Evaluate its chosen
tickets, not the best ticket one could have assembled after results arrived.

The scorecard should show, for each 2/3/4/5/6-leg policy and venue/product: eligible
slates, candidate counts, issued tickets, NO_ACTION slates, pending/unresolved counts,
all-leg wins, leg outcomes, full/partial returns, refunds, stakes in paper units,
gross/net return, ROI and uncertainty intervals. Include drawdown and shared-leg
exposure in the portfolio report. Overlapping tickets are not independent samples.

Use chronological out-of-sample rows, paired comparisons and game/slate/week blocks
for uncertainty. Freeze sample-size/precision targets using development variability
before evaluating results. Small bins by weekday/category/over-under remain
descriptive; a new optimized policy needs a new evaluation.

## 9. Website design

Both Props and Paper Builder must support one sport, a selected group of sports,
and all supported sports. Define the selection contract in the initial NBA website
work and expose choices according to actual coverage. Keep the displayed rows and
ticket candidate universe within the selected scope. Provide
Events, Props, Value Research, Paper Builder, Performance and Source Health views.
On phone-sized screens, each card should make the player, stat/period, line/price,
forecast interval, probability source, observation age and evidence status readable.

Distinguish observed offer only, research forecast, evaluated forecast, priced paper
candidate, stale/unavailable and unresolved settlement. These are independent
dimensions, so a row may have a good forecast and no current price. Avoid a single
green badge that implies every stage is passed. Show supported capabilities, not
marketing placeholders for every named sport.

Data processing owns forecasts; the UI reads versioned output files. A website
refresh should not trigger a full historical rebuild or upstream scrape. Discovery,
forecast refresh, quote capture, outcome grading and website publication have
different workloads and only run on justified schedules.

## 10. Recovery and bounded operations

Use request budgets, bounded retries/backoff, timeouts, cached immutable inputs,
explicit schema checks and quarantine. Preserve the last successful report with its
true age. Record valid-empty, unavailable, rate-limited, malformed, unsupported and
stale states separately. Never fill missing data with invented prices or zeros.

A source rename may produce a proposed parser repair with retained fixtures and
negative tests. A change to stat meaning, player identity or settlement is a semantic
change and needs review and a new parser/rules version before activation. Automated
recovery is useful; unattended guessing about market meaning is not.

Measure the initial backfill size and bounded incremental runtime. Store large
Parquet/raw archives outside Git; publish only compact validated assets. Establish a
durable authorized observation store before relying on ephemeral cloud workers for
prospective evidence. Do not claim a hard free operating budget until actual runtime,
storage and hosting constraints have been measured on the chosen environment.

## 11. Milestones and completion evidence

| Milestone | Concrete completion evidence |
| --- | --- |
| 0: Source feasibility | Parsed row sample, primary-boxscore reconciliation, provenance, causal feature map, source access result and measured runtime. |
| 1: Full NBA baseline and improvements | Shared base-stat forecasts and coherent derived outputs; per-category scores; the first isolated REB opportunity comparison; frozen protocols and promotion/rejection/inconclusive decisions. |
| 2: Future single-contract paper research | Genuine pregame receipts, exact offers, model semantics, correct outcome/settlement grade and no backdating. |
| 3: Paper tickets | Actual entry terms, common decision clock, joint method, 2–6-leg scorecard and validated selected-policy behavior. |
| 4: Website | Consistent schema, age/status display, isolated sport publication and an actual reviewed deployment. |
| 5: Expansion | Inventory full category scope for each league; related families pass their own data, forecast, quote and settlement gates; MLB imports retain provenance. |

Milestone 0/1 should also build the website contract and a usable static interface
with honest empty/research states while live odds remain unresolved. Full website
delivery remains Milestone 4; an early research site can be published when its
own build and labeling checks pass. See WEBSITE_DELIVERY.md and the detailed
CODEX_START_HERE.txt roadmap. Milestone 1 does not require book prices to compare outcome distributions.
Price and payout gaps block value claims for affected products. Display issues do
not invalidate a correctly scoped offline forecasting experiment.

## 12. Handoff and current setup status

Nick created the canonical public repository
`NickNicky19/Nicks-multisport-lab-project`. Its initial main commit was
`c82225cf893b16de70ebbbcd476774f043360d24`, containing an initial README. This
bootstrap imports the starter contents at the repository root and tailors the
kickoff to that exact destination. Inspect the actual checkout and HANDOFF_STATUS.md
for current status; do not overwrite newer repository work with the original ZIP.

A new Codex task has not been launched by this handoff. Start a separate task in
an environment containing this repository and execute CODEX_START_HERE.txt. The
current official cloud route creates/prepares an environment, publishes it and
then starts a task. If the repository is missing from the chooser, resolve access
through the existing Codex/GitHub connection settings. A ChatGPT project folder
does not by itself create that Codex environment.

No website or deployment workflow exists in this bootstrap. The expected Pages
project prefix is `/Nicks-multisport-lab-project/`. GitHub Pages serves generated
static assets; Python data/model work runs separately before publication. The
exact setup, tests and remaining Pages setting are in WEBSITE_DELIVERY.md.

Official setup references:
- https://learn.chatgpt.com/docs/environments/cloud-environments
- https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages

Existing NFL, MLB and other NBA projects remain separate. This import does not
start their workflows, schedules or implementation sessions.

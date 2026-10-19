# Nick's Multisport Lab

**An independent, NBA-first player-prop research project with shared paper-ticket
infrastructure for 2–6 legs.** Six legs are preferred only when the complete ticket
meets the eventual evidence and economics policy. Smaller tickets and NO_ACTION
remain valid results.

Prepared October 19, 2026 for a **new repository and new Codex session**.
Canonical repository: [NickNicky19/Nicks-multisport-lab-project](https://github.com/NickNicky19/Nicks-multisport-lab-project).
Nick created this repository; this bootstrap imports the starter and its tailored
implementation roadmap. A new Codex implementation task must be started separately.

## Start the new Codex task

Open this repository in the intended Codex environment and tell it to read and
execute [`CODEX_START_HERE.txt`](CODEX_START_HERE.txt). The current repository
already contains the starter's contents at its root; an older ZIP is unnecessary.
Use [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) and
[`HANDOFF_STATUS.md`](HANDOFF_STATUS.md) for the accepted scope and actual status.

The website is explicit implementation scope. Its expected address after a
successful GitHub Pages deployment is
`https://nicknicky19.github.io/Nicks-multisport-lab-project/`.
That address is a deployment target, not a verified live site. See
[`docs/WEBSITE_DELIVERY.md`](docs/WEBSITE_DELIVERY.md) for the hosting plan and
[`docs/CHATGPT_PROJECT_SETUP.md`](docs/CHATGPT_PROJECT_SETUP.md) for session organization.

## What exists in this starter

- Offline Python primitives for exact prop-contract identities and timestamped
  quote observations, with sportsbook prices distinct from pick'em multipliers.
- Explicit win/loss/push/void single-return arithmetic; two-sided conditional
  market-reference arithmetic; an assumption-labeled independent-hit calculation;
  and a supplied joint-state/payout-table ticket calculator for 2–6 legs.
- Attributed generic timestamp, canonical-JSON and hash helpers selected from
  Nick's NFL additions, plus a small generic immutable evidence store.
- Meaningful synthetic tests for timing, identity, probability, payout and receipt
  integrity. These tests are not sports validation or evidence of profitability.
- A source capability register, first NBA experiment, staged implementation order,
  and an actionable Codex kickoff brief.
- All 13 requested NBA markets in a planned registry, with deterministic coherent
  sums and double-/triple-double indicators from one supplied basketball draw.

## What is planned, not built

No live multisport Sleeper/ESPN collector, trained NBA model, automatic ticket
selector, provider-specific settlement engine, website deployment, or wagering
integration is included. There are no current picks. The package is deliberately
the smallest useful foundation for the next implementation session.

All live quote sources remain unverified for the new project. A sport's appearance
in the capability register does not imply that its feed or model works.

## Run the offline checks

Python 3.11+; the starter uses only the standard library.

```bash
python3 -m unittest discover -s tests -v
python3 -m multisport_lab.demo
```

The demo uses fictional probabilities and payout terms. It makes no network calls.

## Read in this order

1. `CODEX_START_HERE.txt` — start the new implementation session.
2. `docs/PROJECT_BLUEPRINT.md` — architecture, ticket policy and build sequence.
3. `docs/NBA_FULL_SCOPE.md` — the complete NBA category scope and agent workstreams.
4. `docs/NBA_REBOUNDS_EXPERIMENT.md` — one bounded improvement comparison within that scope.
5. `docs/SOURCE_CAPABILITY_MATRIX.md` — current source findings and limitations.
6. `docs/REUSE_PROVENANCE.md` — exactly what was selected from NFL and why.
7. `docs/VERIFICATION.md` — checks run on this starter and remaining work.

## Initial sport decisions

| Sport | Initial role |
| --- | --- |
| NBA | Full requested 13-market scope; REB is the first controlled improvement experiment. |
| WNBA | Later independent basketball model, with shared software only. |
| NHL | Comprehensive category goal; skater shots on goal is a candidate first improvement experiment. |
| Soccer | Competition-specific historical research until current coverage passes. |
| Tennis | Separate serve/return and match-format research; data access unresolved. |
| CFB | Separate college model; public archives assessed independently of keyed APIs. |
| MLB | Import the existing model's versioned, independently evaluated outputs. |
| NFL | External, disabled here; existing project and writer stay independent. |

## What “Astra-level” means here

It is a quality target for research and engineering: causally timed inputs, strong
baselines, opportunity uncertainty, full distributions, calibrated probabilities,
correct entry economics, reproducible grading and prospective evidence. It is not
a model brand, a guaranteed hit rate, or a claim that any forecast beats a book.

Accuracy and profitable selection are separate hypotheses. A model can improve
its outcome forecasts while producing no supported positive-value tickets.

## Full NBA scope

Points; points + rebounds + assists; rebounds; three-pointers made; assists;
rebounds + assists; points + rebounds; turnovers; triple-double; double-double;
blocks; steals; blocks + steals. Points + assists is a natural optional addition.

The baseline/data plan covers all primary boxscore statistics. Combined categories
come from the same joint draws. Individual families can improve and earn admission
independently; the REB experiment does not cap the project at one category. The same
comprehensive-category goal applies when each later sport is admitted, subject to
actual data, contract and settlement coverage.

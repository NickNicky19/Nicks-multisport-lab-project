# Nick's Multisport Lab — project instructions

## Ownership and scope

Work only in `NickNicky19/Nicks-multisport-lab-project`. Use the current
`PROJECT_CONTEXT.md`, `HANDOFF_STATUS.md` and `CODEX_START_HERE.txt` for continuity.
NFL stays in `NickNicky19/nicks-expert-nfl-picks`
under its existing session. Do not contact that session, write to that repository,
or trigger its workflows. Nick's MLB project remains independently owned; import
versioned outputs later. Inspect existing NBA work before duplicating it, but do
not mutate a separate NBA repository without task-specific authorization.

One implementation owner per branch. Research and independent verification may
run in parallel in separate files. Do not create an implementation/audit scheduler
or recurring live collector as part of importing this starter.

## Product goal and limits

Develop scientifically evaluated player-outcome distributions and a paper-ticket
system for 2–6 legs. Six is a preferred ticket size when supported; never fill six
by relaxing evidence, data freshness, identity, or payout requirements. Support
OVER_ONLY, UNDER_ONLY and MIXED as separate evaluated policies. NO_ACTION is valid.

Props and Paper Builder both support one sport, a selected group of sports, or all
supported sports. Keep display and candidate selection within that scope. Actual
coverage determines the available choices, beginning with NBA.

NBA is the first sport, with ALL 13 requested markets in config/nba_markets.json:
PTS, PRA, REB, 3PM, AST, RA, PR, TOV, TD, DD, BLK, STL and BLK+STL. PA is an optional
additional derived market. Build common historical inputs and a coherent reference
baseline across base statistics, then improve related families in parallel. The
proposed REB comparison is the first controlled improvement, not a scope limit.
Use a shared minutes/role/pace layer; do not give every derived sum its own unrelated
model or allow agents to use different cutoffs and holdouts. WNBA, NHL,
soccer, tennis and CFB remain separate research/admission decisions. MLB is an
external-model import. NFL is external and disabled in this new project's initial
runtime. There is no automatic transfer of accuracy between leagues.

Use no new paid services, signups, subscriptions, trials, or API keys under this
initial scope. Use permitted public data, existing authorized access, or retained
user-provided files. An accessible URL and a library's code license do not by
themselves establish permission for scheduled extraction or data redistribution.
Keep offline methods work moving when live-price admission is unresolved.

## Evidence and scientific semantics

Every forecast declares its target, conditional/unconditional participation
semantics, cutoff, model version, input hashes, and evidence lane. Keep captured
future observations separate from reconstructed historical research. Never backdate
capture clocks or claim that a checksum proves upstream authenticity/publication.

Never use actual future minutes, final lineups, postgame projections, closing
prices or revised season totals as if available pregame. Actual workload is allowed
only in clearly retrospective diagnostics. Keep DNP distinct from zero production.

Follow `docs/NBA_REBOUNDS_EXPERIMENT.md`. Pre-register feature set, splits,
population, primary metric, tuning budget and decision rules before evaluating
the holdout. A defective grading path invalidates affected metrics only; unrelated
website or offer issues do not block a price-independent forecast experiment.

Full category coverage is the goal for every admitted sport. Enumerate the actual
offered families, retain unmapped observations, and admit data/forecasts/quotes per
category. Do not reduce a whole sport permanently to its first experiment, or call
an unsupported market accurate merely because its code is in a registry.

Use exact sport/league/event/player/stat/period/line/side/variant/venue/product/rules
identities. Line and price are a joint observation. Unknown mappings and incomplete
terms remain unknown. A pick'em side multiplier is not sportsbook decimal odds.

Ticket EV requires actual supported entry terms and a joint outcome distribution.
An independence calculation must be explicitly labeled as an assumption. Product
guarantees, contest pools, pushes, voids and entry reductions need the appropriate
settlement model; generic arithmetic is not provider certification.

## Engineering and publication

The starter is offline. Nothing in it is a trained model or validated live adapter.
Its synthetic tests demonstrate specified software behavior, not profitable picks.
Keep large historical/raw files out of Git. Establish durable capture retention and
a bounded runtime/storage budget before enabling production collection.

Reuse only the generic, attributed helpers documented in
`docs/REUSE_PROVENANCE.md`. Do not copy the inherited NFL app, forecasts or schedules
into this project by default. Preserve third-party notices and dataset terms.

Required local check after behavior changes:

```bash
python3 -m unittest discover -s tests -v
python3 -m multisport_lab.demo
```

Add tests for concrete identity, timing, probability, payout or evidence-integrity
risks. Do not create meaningless test-count targets. Report actual files changed,
commands and outcomes, and distinguish built, tested, data-verified, model-validated,
published and prospective-paper states.

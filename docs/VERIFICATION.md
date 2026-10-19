# Starter verification and delivery status

Prepared October 19, 2026. This report describes the local starter package, not a
trained forecasting system or an operating player-prop service.

## Software checks completed

From the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 -m multisport_lab.demo
```

The unit-test command completed successfully: **28 tests, all passed**.
The offline demo completed with exit code 0 and correctly marked its supplied
numbers as synthetic examples. No network calls, live quotes, actual tickets or
trained probabilities are used by either command.

| Area | Checks and observed result |
| --- | --- |
| Evidence integrity | 11 passing tests cover strict JSON, nonfinite values, timezone precision, complete-payload conflict checking, bounded reads and create-only receipt behavior. |
| Contract and quote meaning | 4 passing tests cover exact contract identity, equivalent versus genuinely different Decimal lines, clock/evidence constraints and explicit pregame freshness checks. |
| Economics | 7 passing tests cover win/loss/push/void arithmetic, coherent two-sided quote pairs, pick'em versus sportsbook price types, explicit independence, 2–6-leg supplied payout laws and repeated/opposing-market rejection. |
| Basketball derivation | 6 passing tests cover all 13 requested categories plus optional PA, same-draw sums, integer/zero/missing semantics, the scoring constraint on made threes, and correct five-stat DD/TD definitions. |
| Offline demonstration | Produces the expected +5.0% and approximately -8.33% single-return examples at fictional 55% win probability, an explicitly assumed independent-hit table, a supplied joint payout example, all requested basketball outputs, and a successful temporary evidence round trip. |

The current basketball helper consumes a supplied points/rebounds/assists/threes/
turnovers/blocks/steals draw. It checks that points cannot be below points from made
threes. The planned FG2M/FG3M/FTM forecasting interface and full scoring-component
reconciliation are documented, but are not a trained or implemented simulator.

These checks verify stated software behavior. They do not establish source
authenticity, historical input availability, source permissions, complete provider
rules, feasible bookmaker entries, a correct dependency model, forecast accuracy
or profitability. Generic supplied scenario arithmetic does not certify an
arbitrary caller's joint probability law or payout table.

## Scope and configuration verification

The JSON registries were parsed and checked for these exact mandatory codes:

```text
PTS, PRA, REB, 3PM, AST, RA, PR, TOV, TD, DD, BLK, STL, BLK+STL
```

PA is additional and optional, with `requested: false`. Codes are unique, work
groups cover them, and the capture plan includes the complete requested set.
Scoring and DD/TD definitions are recorded with primary NBA references.

All source collectors, local trained/validated-model flags and priced-selection
flags remain disabled or false. The source register distinguishes inspected
documentation/release metadata from row audits and actual operating-runner access.
Every listed sport refers to existing source IDs in the capability register.

The rebound opportunity comparison is **proposed, not run or preregistered**.
Unresolved source and protocol fields must be settled before a confirmatory test.
It is one isolated improvement inside the full NBA scope. A change to its marginal
distribution cannot silently replace a component of the planned joint model.

## Reuse and source evidence

Read-only NFL code inspection used main revision
`4d5751a130b6efc0a526f8f7539626d529cef798` and selected later generic helpers from
revision `551d605d78fd9b64d525f0748cfc3ca2c83bc2de`. Exact provenance, source
fingerprints and adaptations are in `REUSE_PROVENANCE.md`.

No current NFL writer, workflow, deployment, source collector or active session
was changed. The hosted website was not visually audited. The existing MLB model
was not imported, run or reassessed. Public statistical source metadata and
documentation were researched; no historical NBA row panel was downloaded or
trained in this session.

## Delivery and remaining implementation

The ZIP contains repository files, a source capability matrix, the complete NBA
scope, a proposed controlled experiment and `CODEX_START_HERE.txt`. It excludes
temporary caches, raw copies used during NFL review and any credentials. Its
manifest records SHA-256 hashes for the delivered project files; those hashes
verify package content only.

At original ZIP delivery, the remote repository and new Codex session had not
been created. Nick has now created
`NickNicky19/Nicks-multisport-lab-project`, replacing the earlier suggested name.
The repository bootstrap includes the starter and a tailored CODEX_START_HERE.txt,
plus project/session and website-delivery documents. The Python behavior is
unchanged by that documentation/import update. Read the current HANDOFF_STATUS.md
and actual repository revision for delivery status. No new Codex task, live model,
source collector or website deployment is created merely by importing these files.

The next concrete implementation work is source-row feasibility and exact offer
fixtures, followed by the complete NBA reference baseline, controlled category
improvements, captured future forecasts, product-specific paper settlement, ticket
selection and website publication. Their completion is not implied by this kit.

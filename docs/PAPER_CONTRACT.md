# Manual paper draft contract v1

Implemented in `multisport_lab/paper.py`. This is offline research infrastructure,
not an operational ticket selector, provider eligibility certification, settlement
adapter, prospective ledger, or qualified product. No current opportunities or
provider payouts are bundled. `tests/test_paper.py` uses fictional terms and
probabilities solely to check software behavior.

## Exact scope, identity and one clock

`ManualDraft` freezes 2–6 `QuoteObservation` objects, matching `ForecastEvidence`
references and one timezone-aware `decision_at`. The portable `to_record()` keeps
each complete contract, exact quote ID, capture/source clocks, forecast version,
input hashes, conditioning and evidence lane. `draft_id` fingerprints that complete
record; it does not prove when someone created it. Exporting the local record does
not issue a prospective paper entry.

`validate_draft()` returns `DraftValidation` with `accepted` and `reasons`;
acceptance means the supplied draft meets these internal checks. Its
`qualification` always remains `UNAVAILABLE`.

- Sport selection reuses `publication.resolve_scope`. `SINGLE` requires exactly
  one league; `SELECTED` requires a nonempty subset of actual supported leagues;
  `ALL` requires an empty explicit selection and resolves to all supported leagues.
  Initially the admitted interface scope is NBA only. Future-sport fixtures in
  tests establish set semantics, not actual future coverage. A selected group
  never expands to fill an entry. Scope names use league codes such as NBA,
  matching the export contract; the contract's sport field remains basketball.
- `OVER_ONLY` and `UNDER_ONLY` require the corresponding side on every leg.
  `MIXED` permits either side, including a ticket containing only one side. These
  are separate policy identities, not evidence of separately evaluated policies.
- Every leg has the same exact venue, product and settlement version. Repeated
  players and games are unsupported in this initial contract. Their identities
  are namespaced by sport and league so IDs from different leagues cannot collide.
  Duplicate contracts are rejected.
- Every quote must be pregame at the common decision, with capture at or before
  that decision and within the caller's explicit positive `max_quote_age`.
  Known source-update clocks must also be fresh. Unknown source-update times fail
  by default; `require_source_timestamp=False` is an explicit research policy
  recorded in the draft, not a claim that the missing clock is known.
- Exactly one forecast reference is required for each exact contract ID. Training
  and latest-input availability must precede its cutoff; cutoff precedes issuance;
  issuance is no later than the common decision. Forecast and quote start times
  must match, preserving the event version used by the ticket.
- Each forecast supplies an exact `supported_decision_horizon` and a nonempty
  `horizon_evidence_id`. The supported duration must equal event start minus the
  common decision. Support at T−90 cannot be substituted for a later leg's T−180
  decision horizon. Missing support is representable but rejects the draft.
  These metadata are evidence assertions; this module does not read an evaluation
  archive or grant horizon/conditioning/model admission from their presence.

The caller must derive `supported_sports` from actual coverage. This generic
module cannot independently certify an arbitrary caller-supplied sport registry.
Its missingness and rejection reasons remain visible rather than manufacturing a
quote, forecast, longer-horizon validation, or six-leg entry.

## Explicit entry economics

`draft_ev(draft, terms=..., joint=..., max_terms_age=...)` revalidates the draft
before calling the existing `economics.ticket_ev` kernel.

`EntryTerms` supplies the exact ordered quote IDs, venue/product/settlement version,
terms and eligibility evidence IDs, settlement rule IDs, capture/update clocks,
effective interval and complete gross-payout mapping for the states being valued.
Terms must be available and effective at the same decision and satisfy the explicit
positive terms-age limit. Unknown terms source updates follow the same recorded
policy as quotes. Terms cannot be silently reused after a line, price, capture,
leg order, or rule identity changes.

`JointOutcomes` supplies matching ordered quote IDs, the complete listed state
probabilities, probability-source label, available clock, method, evidence ID and
nonempty explicit assumptions. Its evidence must exist by the common decision.
Different players/games do not establish independence. An independence scenario
must be supplied and labeled explicitly; this function never manufactures one.
Both terms payouts and joint probabilities are copied into immutable mappings.

The existing kernel requires 2–6 legs, probability mass summing to one without
renormalization, valid win/loss/push/void states and explicit finite nonnegative
gross payouts for every listed state, even listed zero-probability states. Gross
includes returned stake. Omitted probability states are explicitly zero under
the supplied scenario. Pushes, voids, entry reductions and pool components receive
no default rules or assumed multipliers. The caller must supply the actual
applicable state/payout model before claiming complete product economics; a
partial guarantee table alone cannot establish complete contest EV.

`EntryTerms.provenance` defaults to `SCENARIO_INPUT`; `CAPTURED_TERMS` can label a
caller-supplied captured record. Both return `NOT_PROVIDER_CERTIFIED` and
`qualification=UNAVAILABLE`. These strings do not admit provider eligibility or
validate the supplied probability law. Supporting a payout scenario is different
from having verified actual current terms, calibrated participation/void outcomes,
joint forecast accuracy, or a profitable paper policy.

## Six-first policy primitive

`choose_six_first()` accepts only explicit `FullTicketAssessment` records. Each
record identifies a complete 2–6-quote ticket, a supplied boolean qualification
outcome and its assessment evidence. The helper returns the first qualifying
six-leg entry; otherwise it tries five, four, three and two in order. Caller order
breaks ties within a size. With no supplied qualifying complete ticket it returns
`None`, meaning `NO_ACTION`. It cannot fill six from a count of attractive legs.

This pure policy helper does not generate combinations, grant qualification, or
connect to current candidates. All project product qualification remains
unavailable pending independent forecast, horizon, participation, actual entry
terms, joint settlement and prospective policy evidence.

## Verification and remaining work

Run `python3 -m unittest discover -s tests -p test_paper.py -v` for the bounded
synthetic checks and the repository's full required suite/demo after integration.
Checks cover exact quote identity/order, scope containment, modes, 2–6 legs,
distinct players/games, one-clock freshness, forecast availability and exact later
leg horizons, terms/rules/joint requirements, explicit partial-state payouts,
immutable caller inputs, smaller tickets and `NO_ACTION`.

Still required: inspect actual product entry eligibility and settlement evidence;
bind normalized evidence to immutable source receipts; implement actual outcome
grading and append-only correction records; durable issuance with a real clock;
evaluated complete joint forecasts and horizon/participation support; browser draft
import/export integration; and preregistered prospective policy evaluation. Future
paper outcomes must wait for the corresponding events to occur.

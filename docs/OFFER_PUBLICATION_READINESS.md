# Offer publication remains a separate delivery path

October 23 update: the [MoviOdds private parser](MOVIODDS_NBA_PRIVATE_REVIEW.md)
now establishes 34 actual local binary DD/TD source-semantic contracts from a
free keyless API. This is a private snapshot proof, with a blocked canonical-event
start crosswalk and no public offer admission. The earlier zero-contract findings
below describe their dated ESPN/Sleeper samples; they are not a claim that all
alternative sources lack usable player contracts. Existing public admission and
ticket guards remain unchanged.

Reviewed October 20, 2026 UTC. This website display package publishes verified
names and clearer status explanations. It does not admit offers, prices, value
claims, candidates or tickets. Research forecasts do not require bookmaker prices.

## What the current public export actually permits

The public readback in `evidence/display/2026-10-20-public-site-before.json`
serves main `735a464e9e8718303ef481abf711a8969de56694`, manifest schema 2 and
NBA research schema 2: six historical forecast bundles, six statistical grades,
zero offers, zero candidates and zero tickets. Website publication was
`2026-10-20T05:59:32.398269Z`; that is not a new source capture or forecast issue.

`multisport_lab/publication.py::_validate_research_sport` rejects any nonempty
`offers`, `candidates` or `tickets`. `web/snapshot.mjs::validateSport` independently
enforces the same restriction. This display package preserves that restriction;
its new manifest/display metadata asset does not silently introduce an offer
contract. A complete future research forecast may already be published through
the existing typed research-forecast path with all three collections empty.

## Evidence and distinct admission decisions

Use the retained [OFFER-PILOT-003](OFFER_PILOT_003.md) response summaries first.
The corrected ESPN route and both declared pages were observed successfully;
side/selection identity, period/OT, market status, settlement mapping and source
clock anomalies remain unresolved. Sleeper's player types and supported labels
were checked, but event crosswalk/start, period/variant and exact product/rules
binding remain incomplete. Generic Max/Flex/pool rules do not establish the
specific captured entry's state payouts. The retained actual responses establish
zero complete actual player contracts and zero usable kernel quotes. Production
source access and redistribution admission also remain unresolved.

These are separate gates:

| Evidence | Permitted interpretation |
| --- | --- |
| Partial observation | Retain the exact known fields and missing terms for audit. Do not present it as a complete player offer. |
| Complete, independently verified and permitted offer-only contract | Exact identity, line, side, period/OT, variant, venue/product and applicable settlement meaning may be displayed, with source clocks and provenance. Price may be unavailable. |
| Usable quote | Requires an actual supported price or relevant entry economics, paired with the exact line and source evidence, plus status/freshness and identity checks. |
| Value candidate | Additionally requires an applicable forecast, supported economic calculation and the relevant evaluation/qualification gates. |
| Qualified paper ticket | Requires the whole 2–6-leg ticket to satisfy product eligibility, common decision time, actual entry payouts/settlement and explicit joint-outcome assumptions. |

The existing offline `normalized_v1` importer already permits an explicitly
complete `PropContract` with `price: null`: the contract survives, `quote` is null
and `qualified` remains false. An import status of `ok` means parsing succeeded;
it does not independently verify supplied semantics or authorize publication.
The Sleeper-shaped importer deliberately leaves unresolved rows as partial
observations. A pick'em side multiplier is never standalone sportsbook odds.

## Next concrete offer-delivery package

1. Retain and independently verify one permitted actual player contract with
   exact provider namespace IDs, event/version/start, player/team identity,
   side, line, period/OT, variant, venue/product and applicable settlement rules.
   Record actual observation, source-update (or unknown) and import clocks, raw
   hashes, semantic evidence references, and the precise access/public-display
   admission basis. Do not invent missing terms or repair anomalous clocks.
2. Introduce a separately versioned bounded offer-publication contract and update
   Python and JavaScript validation together. Keep partial observations distinct
   from admitted offer-only records. Reject identity, clock, reference and
   duplicate inconsistencies with focused negative tests.
3. Render an explicit `PRICE_UNAVAILABLE` offer-only state with `quote: null`,
   qualification unavailable and no price/EV claim or builder eligibility. A
   missing price alone must not reject an otherwise complete, permitted offer.
   Independently verify the artifact and desktop/mobile display.
4. Add usable quotes, economic candidates and ticket publication only through
   their own validated contracts and evidence gates. Preserve scope filters,
   OVER_ONLY / UNDER_ONLY / MIXED, 2–6 legs, smaller tickets and NO_ACTION;
   prefer six only when the complete ticket qualifies.

No new paid service, signup or API key is required by this design. It does not
grant ongoing source collection permission. Missing offer terms do not block
price-independent research issuance or statistical forecast grading.

## Next concrete future-forecast task

The expired October 20 operating pilot must remain its factual late guarded
abort, with zero forecasts. PROS004 remains inactive in draft PR #10. Finish its
independent timing/recovery, input/source completeness, raw retention and reviewed
activation gates before any eligible original cutoff; otherwise retain the
reservation inactive and use a separate later reservation. Only genuinely timely
captured and durably recovered research forecasts may populate Upcoming. Never
reuse early preparation inputs, backdate issuance, or require bookmaker prices
for that statistical research path.

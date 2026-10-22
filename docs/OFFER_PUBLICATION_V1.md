# Separate NBA offer-only publication readiness

This package implements a separate, bounded `nba-player-offers-v1` asset. It
does not admit any actual provider contract. Both Python and browser validators
have an empty exact public-admission registry. The legacy sport-v2 `offers`,
`candidates`, and `tickets` arrays remain empty. Research forecasts can publish
through their own typed channels while offer admission remains unresolved.

## What is implemented

`multisport_lab/offer_publication.py` and `web/offers.mjs` agree on the complete
contract, review, asset, descriptor, matching, and display semantics. A complete
offer requires namespaced canonical and provider identities; exact event version,
start and historical teams; category, source-verified statistic meaning, units,
period, overtime, line, explicit side, variant, venue/product, market status, and
settlement version. All 13 requested NBA categories plus PA remain in the asset
inventory, including categories absent from a particular capture.

Settlement meaning is explicit rather than an arbitrary version label:
`settlement_terms.status` must be `SOURCE_VERIFIED`, with bounded participation,
DNP, postponement, ties/push, official-stat-source, and stat-correction meanings.
Unknown or missing components reject the complete contract. This describes the
selection's meaning; it does not implement entry payouts or ticket settlement.

Each critical normalized field is bound to a retained source's JSON pointer,
exact original value, and reviewed normalized meaning. Required evidence roles
are contract view, event identity, player identity, provider crosswalk, and rules.
The durable store replays every pointer against exact raw bytes before admitting
an offer record and again during recovery. Observation, source-update, import,
and review clocks remain distinct. The contract observation/update clocks must
match its contract-view evidence; later identity/rules verification must complete
by import. A hash verifies consistency, not source authenticity or permission.

`PRICE_UNAVAILABLE` with `price=null`, `quote=null`, and
`qualification=UNAVAILABLE` is valid for a complete, separately admitted offer.
An observed price remains `OBSERVED_PRICE_NOT_QUALIFIED`; side multipliers retain
their pick'em type. A price requires the same source observation as its exact
line, side, and selection. There are no EV, executable-quote, payout, financial
settlement, recommendation, or ticket-eligibility claims in this channel.

An admission binds the exact offer subject and a scoped review basis. A caller
cannot self-publish by asserting a rights declaration: the admission's exact ID
must also appear in both reviewed code registries. No actual IDs are registered.
The declaration explicitly grants neither scheduled collection nor raw-body
redistribution. Synthetic fixtures require explicit test mode and never enter
the default publication path.

## Retention and restart

`OfferStore` appends generic `input_captures` metadata under the existing shared
single-writer lock and uses `CompositeEnvelopeLedger` to coexist with the
versioned research inputs. It preserves exact original bytes and clocks,
supports idempotent retry/readback, and appends correction links without replacing
originals. Raw references are exact `LedgerRef`s, with payload hashes retained in
the offer envelope. The bounded private raw-reader adapter must independently
recover source bytes and metadata; missing recovery fails closed.

Real provider bodies may not pass through the compressed-raw test helper. That
helper accepts only `SYNTHETIC_TEST` captures on `.test`/`.invalid` hosts. It rejects
actual provider URLs. The separate encrypted raw-retention candidate still needs
source/backend admission and a verified ledger-link adapter before it can serve
actual offers; no encryption or checksum establishes provider rights.

Publication recovers only offer contracts, exact required raw references, and
their correction graph, so an unrelated invalid forecast cannot suppress a valid
offer channel. Bounded inventory checks remain global; all input/correction
envelopes must be readable and checksummed to classify them safely. Offer
corruption is never skipped. No recovery generates missing forecasts or captures.

Limits remain 512 ledger/shared-metadata files and 32 MiB. Pre-write accounting
uses `operational_pilot.metadata_inventory` and includes old PROS004 completion
metadata plus all current/archived operational journals and recovery proofs.
Offer envelopes are capped at 64 KiB; individual offer bodies at 32 KiB. The
public asset is capped at 256 KiB and 32 offers/reviews. The count and byte limits
both apply; 32 maximum-size offers do not fit merely because the count allows 32.
Every offer, raw-link, correction, and backend file must be included in the
integration owner's actual operating budget before activation.

## Website and research matching

The optional manifest-v5 `offers` descriptor has a content-addressed
`nba-offers.<sha256>.json` path and `OFFER_ONLY_RESEARCH` status. Python and browser
paths verify outer bytes, nested asset/offer/admission seals, exact subject binding,
semantic contracts, full inventory, clocks, and limits. The asset collection is
`offers`; each record has top-level `league` for the existing sport scope filter.
An error in this independent channel must not admit candidates or tickets.

`renderOffers` shows a verified contract's player, direction, line, category,
venue/product, event date, period/OT, observation clocks, source IDs, raw hashes,
and settlement meanings. Historical captures are labeled as historical when the
event starts. An offer is always a recorded observation, with no claim that the
book still offers it. Missing price is explicit; the paper builder remains
`NO_ACTION` until its separate eligibility and financial-contract requirements
are met. The renderer escapes source text and reuses responsive research styles.

`match_research_forecast` / `matchResearchForecast` compare already validated
records using exact league/namespace/player/event/version/teams, start, category
units, period, OT, genuinely captured evidence, appearance conditioning, and one
explicit pregame decision time. Both the offer import and forecast issuance must
exist by that time. Price absence does not prevent this semantic research match.
The result is `MATCHED_RESEARCH_ONLY` or `UNMATCHED`, always with unavailable
qualification, `ticket_eligible=false`, and `ev=null`. It is not a pricing or
source-freshness policy for an executable quote.

## Actual bounded source diagnostic: 21 October 2026

The integration owner selected ESPN event `401909094`, Denver at Oklahoma City,
scheduled `2026-10-23T01:30:00.000000Z`, before this offer diagnostic. Two bounded
GETs used the already reviewed route structure and an actually returned provider
reference. They did not collect another scoreboard, player pool, or source sweep.

The correct inherited core route, with `propBets` casing, returned HTTP 200 at
`2026-10-21T01:39:45.791491Z`. It contained six items on one complete page: four
team-total items and two overtime items. None had an athlete reference. The
actually linked provider-100 detail returned HTTP 200 at
`2026-10-21T01:40:19.564083Z` and identified DraftKings. Neither response supplied
a player selection/detail/rules reference to follow. No side was inferred from
row order, and no price or source timing was manufactured. This establishes no
player contract in this snapshot; it does not establish permanent future absence.

The create-only derived audit receipt records exact URLs, clocks, source hashes,
byte counts, inventory, limitations, and prior retained evidence. Current raw
bodies remain temporary/private and are not put in the public ledger or Git.
Earlier pilot summaries survive, but their original `/tmp` raw directories are
missing. The surviving Sleeper import-v0.3 receipt has 2,720 partial observations,
no complete contracts, and no usable quotes; its local-research/no-public-
redistribution assertion is not a public offer admission. Generic previously
inspected rules do not bind a particular player contract's period/OT, DNP,
postponement, entry terms, or identity crosswalk.

## Verification and remaining work

Focused synthetic checks cover complete price-unavailable contracts; missing
and contradictory identities, period/OT, side, rule/DNP and clock meanings;
source-pointer replay; unchanged originals; duplicate retry; interrupted
acknowledgment/restart; correction links; independent channel recovery; shared
record/byte exhaustion including operational metadata; explicit optimized-Python
rejection; nested browser hashes; exact research matching; and safe rendering.
The nonempty Chromium fixture runs at 1440, 390, and 320 pixels, opens all source
details, and verifies no horizontal overflow or browser errors. These are
software diagnostics, not actual offer or future-forecast evidence.

```bash
python3 -m unittest discover -s tests -p test_offer_publication.py -v
python3 -O -m unittest discover -s tests -p test_offer_publication.py
node web/tests/offers.test.mjs
python3 evidence/offers/2026-10-21-offer-card-browser.py
```

The next actual-offer task is a separately permitted, bounded exact player
contract capture with explicit side, market status, period/OT, provider mapping,
and complete source-verified settlement meaning; independently recover its
private source bytes, complete the scoped publication-rights review, and pin that
exact admission in both validators. If terms remain incomplete or publication
permission is unavailable, retain the observation as partial/private and publish
no offer. Missing bookmaker terms do not block the independent future research
forecast path. No live issuance, scheduling, merge, deployment, model-law change,
comparative evaluation, financial settlement, or qualified ticket occurs here.

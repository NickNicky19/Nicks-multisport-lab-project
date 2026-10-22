# Bounded NBA player-offer parser checkpoint — October 21, 2026

**Implemented offline parsing; no complete actual player contract established.**
Collection must remain free with no provider API key, signup, account login,
subscription or trial. The parser has none of those requirements and performs
no network requests. No private encryption key is needed to inspect retained
local bytes. Operational encrypted-archive custody remains a separate dependency;
this package does not change it or install a substitute retention design.

## Actual result and evidence

This package made **zero sports-data requests**, nine official-document GETs
(including one redirect), and six read-only NFL GitHub metadata/code GETs.
No NFL checkout, collector, session, workflow or Git state was changed. Generic
HTTP/integrity lessons and exact source pins are in
[NFL_KEYLESS_REFERENCE.md](NFL_KEYLESS_REFERENCE.md). No inherited collector was
copied, and NFL access is not NBA source admission.

Two original NBA responses from the earlier OFFER-PILOT-004 remain locally
recoverable. They were re-read, not recaptured:

| Original | Actual capture completed (UTC) | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| ESPN event 401909094 `propBets`, page 1 | 2026-10-21 01:39:45.791491 | 4,167 | `dcee4d4f8fb16617f6ff46e52489165101e02fe1fc532d3a9e2886056e6ccb29` |
| Linked provider 100 lookup | 2026-10-21 01:40:19.564083 | 160 | `101448a5e2bf365ae79efff5e7355e8e1193324014386df04b66afa82e974fa2` |

The exact first URL is:

```
https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events/401909094/competitions/401909094/odds/100/propBets?lang=en&region=us&limit=64
```

Original bodies and capture sidecars are at
`/tmp/nml-offer-pilot-004/espn-401909094-propBets-page1.bin`,
`espn-401909094-propBets-page1.metadata.json`, `espn-provider-100.bin` and
`espn-provider-100.metadata.json`. These are local retained originals, **not a
verified remote archive**. The parser checks their byte counts, exact raw hashes,
capture/import ordering, source route and provider reference before inspection.
Checksums do not prove upstream authenticity or permission.

Actual parsed example: event **401909094**, source **ESPN**, returned provider
**100 / DraftKings**, market labels **Team Total Points (4 rows)** and
**Will There Be Overtime? (2 rows)**. There are **zero athlete references,
zero parsed player observations, zero complete player contracts and zero usable
quotes**. No player name, side, period, overtime policy or rules are inferred.
The provider name is supported by the separate returned lookup, not hard-coded
from ID 100. That lookup's later capture clock is retained; it is not proof of
historical point-in-time provider identity.

The machine-readable inventories are
[retained evidence](../evidence/offers/2026-10-21-keyless-retained-inventory.json)
and [source-use review](../evidence/offers/2026-10-21-keyless-source-use-review.json).
The old pilot-002/003 raw directories and local Sleeper importer report are absent.
Their summaries cannot recover individual player names, lines, prices or original
bytes, so this package does not reconstruct an offer from them.

## Category coverage

Historical columns below reproduce the **pilot-003 summary**, not a new raw replay.
ESPN counts are primary-family items with unresolved side/selection/period/rules.
Sleeper counts are recognized partial side observations reported by importer 0.3,
not complete contracts. Its 248 first-quarter options remained unmapped.

| Category | ESPN 003 historical items | Sleeper 003 historical parsed partials |
| --- | ---: | ---: |
| PTS | 26 | 316 |
| PRA | 22 | 270 |
| REB | 26 | 312 |
| 3PM | 16 | 268 |
| AST | 20 | 238 |
| RA | 20 | 260 |
| PR | 26 | 308 |
| TOV | 0 | 36 |
| TD | 4 | 0 |
| DD | 12 | 52 |
| BLK | 8 | 36 |
| STL | 10 | 116 |
| BLK+STL | 6 | 16 |
| PA | 22 | 244 |

All fourteen player categories are **UNOBSERVED_IN_SAMPLE** in recoverable ESPN
004, not permanently unsupported. The native ESPN inspector now has exact-label
handlers for fourteen categories; its player handlers have only synthetic tests.
`Total Turnovers` is an expected, synthetic-only label because it was absent in
003. Milestones and quarter variants remain explicitly unsupported by these
primary-label mappings. Sleeper's existing strict importer supports thirteen
observed aliases; no TD alias was observed or invented. The zero historical TD
count means unobserved there; its parser handler is unimplemented pending an
actual label and semantics. Neither source has an admitted complete contract.

Kalshi and Polymarket categories are **NOT_INSPECTED_SOURCE_USE_GATE**, not zero
sample counts or unsupported categories. Both document keyless public APIs;
specific extraction/software/retention restrictions remain unreconciled. Their
exact official URLs, clauses, clocks and hashes are in
[KEYLESS_SOURCE_FEASIBILITY.md](KEYLESS_SOURCE_FEASIBILITY.md). ESPN/Sleeper retain
their existing scoped source-use blockers. No conclusion covers all possible
free sources.

## Runnable local inspection

The following command already ran successfully, reporting
`0 player observations; 6 nonplayer rows; 0 diagnostics; complete_contracts=0`:

```bash
python3 -m multisport_lab.offer_feasibility \
  --raw /tmp/nml-offer-pilot-004/espn-401909094-propBets-page1.bin \
  --metadata /tmp/nml-offer-pilot-004/espn-401909094-propBets-page1.metadata.json \
  --provider-raw /tmp/nml-offer-pilot-004/espn-provider-100.bin \
  --provider-metadata /tmp/nml-offer-pilot-004/espn-provider-100.metadata.json \
  --receipt .local-data/keyless-feasibility/20261021/espn-004-replay.json
```

That create-only local diagnostic receipt already exists. Read it with
`multisport_lab.integrity.read_receipt`; a deliberate later inspection needs a
distinct output filename because its import clock changes. Re-import never
refreshes the original source-observation clock. Reports may contain individual
source facts, so they stay in ignored local storage and are not website exports.

The inspector retains supplied numeric line/price lexemes without floating-point
rounding, diagnoses contradictory threshold fields and future source-update
clocks, and never infers sides from row order. It preserves absent prices as
**PRICE_UNAVAILABLE**. Missing price alone is not a contract defect: the separate
existing normalized importer/offer-only contract supports price-free complete
contracts. This inspector deliberately emits partial observations only; its
completion requires independently verified identity and rules, not a fabricated
price. No quote, EV, ticket qualification or publication admission follows.

## Smallest next steps

1. Resolve one official public API's exact allowance for **one credentialless
   NBA player-market read and local original-response retention**, separately
   from public redistribution. The promising Gamma informational API invitation
   must be reconciled with the reviewed extraction/copying clauses. Do not
   introduce an API key, signup or broad bespoke-consent requirement where an
   applicable published allowance suffices.
2. Once that source-use gate is established, register a tiny request/byte budget,
   then inspect one actual contract and only its necessary linked player/event
   and settlement references. Verify stable player name/identity, event,
   statistic, period/OT, threshold operator, side, variant, venue/product,
   observation clocks and rule applicability. Retain exact originals. Keep
   absent prices PRICE_UNAVAILABLE and exchange YES/NO economics distinct from
   sportsbook odds.
3. Review offer-only publication separately after actual contract and retention
   admission. Continue statistical-forecast readiness independently; neither
   missing odds nor this local parser depends on operational key backup.

No new collector, scheduler, activation, genuine issuance, outcome, financial
settlement, qualified ticket, public offer, merge or deployment was performed.
PR #10/#12 remain draft; PROS004/S0 and all frozen comparisons remain unchanged.

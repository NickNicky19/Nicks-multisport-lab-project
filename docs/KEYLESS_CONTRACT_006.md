# KEYLESS-CONTRACT-006 — actual Gamma observations and private local preview

October 21, 2026. **28 player rows observed, 28 parsed, zero complete contracts.**
Local desktop/mobile preview verified; zero normalized complete offers, public
offers or ticket candidates. This advances actual-source feasibility, while the
complete-contract milestone remains unmet for the field-level reasons below.

## Source decision and bounded collection

ESPN/DraftKings and Sleeper remain preferred. Their existing reviews did not
establish an applicable allowance for the proposed automated routes. The six
nonplayer rows in ESPN004 do not establish permanent player/category absence.
This package chose **one alternative prop venue: Polymarket**, through its
documented **Gamma API**. Wikidata supplied linked canonical identity evidence,
not a second prop product.

A new, scoped decision was retained before the first data request. The official
[Discover Markets documentation](https://docs.polymarket.com/market-data/discover-markets)
explicitly invites public unauthenticated integrations and NBA/player-prop
queries. The retained terms' informational Content Features and personal
use/copy license support this bounded documented API client and private local
review. This is a scoped interpretation of published allowance, not new provider
consent or a general data license. It excludes site scraping, bulk/recurring
collection, trading, wallets, accounts and public data redistribution. US
informational access is distinguished from trading restrictions. Kalshi's
explicit software/AI-use restrictions were not treated as resolved by a keyless
technical guide. The earlier unresolved review remains unchanged; this narrower
decision is a new checkpoint.

The independent identity source's
[published licensing](https://www.wikidata.org/wiki/Wikidata:Licensing) states
that structured entity/property data is CC0. One search, one entity response and
one property-definition response disambiguated the selected basketball player
and verified the meanings of the NBA/ESPN identifier claims. No archived/current
roster affiliation was inferred. A canonical Wikidata identity is not represented
as a nonexistent Gamma player entity ID.

**Exactly 12 additional HTTP GETs: 8 data/identity, 4 documentation/schema; zero
redirects, retries or rejected attempts.** All agents shared this counter; only
the integration owner made requests. Total response bodies: **1,591,978 bytes**;
each stayed below the unchanged **2 MiB** limit. Collection occurred
11:24:44.695528–11:32:18.771983 UTC. No more source GETs are authorized by this
package's exhausted allowance. Repository administration and loopback browser
asset reads are separate from those source requests.

The actual request sequence was:

1. Documented NBA event listing, limited to five events.
2. Official sports-market-type enumeration.
3. NBA points-market listing, limited to five markets.
4. One returned market's complete response.
5. That market's returned parent-event response.
6. Official resolution documentation, linked from retained documentation.
7. Wikidata licensing.
8. Bounded canonical-name search.
9. Selected Wikidata entity.
10. Official price/order-book documentation.
11. The actual market's linked official JSON schema.
12. Two necessary Wikidata identifier-property definitions in one response.

Exact URLs, originals, counts, source clocks and hashes remain in the private
local request ledger. The public independent receipt retains structural counts,
hashes and clocks without publishing individual offers, prices or raw bodies:
[gamma-local-review-independent-20261021.json](../evidence/verification/gamma-local-review-independent-20261021.json).

## Actual evidence and normalization decision

The initial bounded event page returned futures and roster-change propositions,
not game-stat contracts. A documented market-type filter then returned actual
NBA player-stat rows. The linked event supplied **60 markets total**, including
**28 unique player-stat markets across 14 names**. The separately fetched target
market agrees with its linked event on question, threshold, condition ID,
outcomes, token array, rules, category and game start. Stable source event/market
IDs are preserved. Team IDs retain the source namespace; opaque provider IDs
are not relabeled as ESPN or NBA identifiers.

Source rules explicitly supply full-game/overtime inclusion, the YES predicate,
the complementary NO predicate, DNP treatment, postponement, cancellation and
the official NBA box-score source. Actual exchange price arrays and bare bid/ask
fields remain literal. They are not sportsbook odds, Sleeper multipliers, model
probabilities, executable quotes or compatible parlay legs. Standalone sportsbook
price status is **PRICE_UNAVAILABLE**. Missing prices alone do not prevent a
complete offer-only contract.

**The existing complete normalized offer-only path remains blocked:**

- Gamma provides no stable player entity ID. The independently verified
  canonical identity is retained separately. A source market ID, name hash or
  Wikidata ID is never substituted into `provider_player_id`.
- The reviewed evidence does not establish NBA stat-correction/regrading
  treatment for this contract. Generic oracle finality does not fill that field.
- Outcome and token arrays are retained exactly, but their correspondence is
  not asserted without a source-backed mapping. `selection_id` stays null.
- The market's literal `customLiveness` field is preserved without assuming
  units or applying the generic documentation's two-hour challenge period.
- Source context/status flags remain explicit. Their combination does not prove
  an executable, geographically eligible or currently available offer.

`normalization.receipt.json` stages the verified facts, references the existing
required settlement fields and records `BLOCKED_INCOMPLETE_CONTRACT` with
`normalized_capture: null`. No fake complete record is imported simply to render
a card. Public admission registries remain empty. A later versioned identity
crosswalk representation can preserve a verified canonical player without
inventing a native provider ID, but it cannot resolve missing settlement or
selection meaning.

## All-category inventory

| Category | Observed player rows | Parsed partial rows | This event sample |
| --- | ---: | ---: | --- |
| PTS | 10 | 10 | Observed, incomplete |
| PRA | 0 | 0 | Unobserved |
| REB | 10 | 10 | Observed, incomplete |
| 3PM | 0 | 0 | Unobserved |
| AST | 8 | 8 | Observed, incomplete |
| RA | 0 | 0 | Unobserved |
| PR | 0 | 0 | Unobserved |
| TOV | 0 | 0 | Unobserved |
| TD | 0 | 0 | Unobserved |
| DD | 0 | 0 | Unobserved |
| BLK | 0 | 0 | Unobserved |
| STL | 0 | 0 | Unobserved |
| BLK+STL | 0 | 0 | Unobserved |
| PA | 0 | 0 | Unobserved |

The global enum also lists threes, PRA and DD family names. This is not evidence
of an offered NBA contract in those families. If such a recognized row is
returned before its rules parser exists, it is counted as observed with an
unsupported-parser diagnosis. It must not disappear into an unobserved count.
Other unknown type names remain outside asserted mappings. No whole-source or
permanent category absence follows from these bounded pages or this one event.

## Local evidence, replay and preview

Original responses, capture sidecars, request ledger and scoped decision are
retained under **`.local-data/keyless-contract-006/originals/`**: 26 create-only
files, locally read back and hash-checked. Independent copying and replay matched
all twelve originals. This is **local recovery**, not a remotely verified durable
archive. The temporary capture directory `/tmp/nml-keyless-contract-006/` also
remains; it is not a durable archive either. No operational encryption key was
generated, replaced or needed by this parser. The operating retention design and
private-key recovery decision remain independent and unchanged.

Ready-to-run local commands (use a new preview directory for a new generation
clock; existing receipts/assets are create-only):

```bash
python3 -m multisport_lab.gamma_offer_review \
  --bundle .local-data/keyless-contract-006/originals \
  --preview .local-data/keyless-contract-006/preview-v3
node scripts/render_local_offer_review.mjs \
  .local-data/keyless-contract-006/preview-v3/review.json \
  .local-data/keyless-contract-006/preview-v3/standalone.html
python3 -O web/tests/local_offer_browser_smoke.py \
  .local-data/keyless-contract-006/preview-v3 \
  --evidence .local-data/keyless-contract-006/qa-v3
```

Those artifacts already exist. The HTML can be opened without scripts or a
server. It shows readable source player labels, the verified source matchup and
start, separate capture/update/review-generation clocks, literal source arrays,
PRICE_UNAVAILABLE and ordinary-language gaps. Source IDs and canonical identity
remain accessible in details. It labels all cards **partial source observations**,
shows zero complete contracts, and preserves **NO_ACTION**. It is an inspection
preview, not the deployed site or a public-admission bypass.

Chromium checks passed 1440/390/320px, both standalone and module routes,
all 28 cards, fourteen categories, source details, gaps and no horizontal
overflow. Browser requests were restricted to the ephemeral loopback server;
external requests were zero. Screenshots and browser receipt stay private under
`.local-data/keyless-contract-006/qa-v3/`. Root visually reviewed desktop and
320px screenshots. Initial harness runs needed loopback socket permission and a
case-insensitive check for CSS-transformed text; no product claim preceded the
successful verification.

## Review fixes, checks and exact next task

Independent review found and verified fixes for tiny fractional prices above 1,
observed-but-unimplemented family counting, and local output symlink confinement.
Eight Python checks pass normally and under `python -O`; eight focused frontend
checks and all 86 frontend tests pass. Final required Python/CI measurements are
recorded in the latest handoff rather than anticipated here. No frozen experiment
or full-history diagnostic was rerun.

The next bounded source investigation has two concrete targets: a documented
market/token response that explicitly binds outcome labels to selection IDs for
the selected condition, and an official NBA stat-correction/finality rule that
actually applies to that same market. The retained generic schema/documentation
did not supply them. This requires a **new request allowance**, not provider
credentials or a universal bespoke-consent requirement. If no applicable rule is
published, retain Gamma as a partial observational source for this contract;
do not weaken the complete-contract gate. Review a versioned canonical-identity
crosswalk representation separately from native provider identifiers.

Price-independent forecast preparation remains separate. The canonical identity
witness can inform a later reviewed identity adapter; it is not a timely operating
input or a genuinely issued forecast. The current genuine-input/activation gates
remain unchanged. PR #10/#12 remain draft, PROS004/S0 inactive. No scheduler,
genuine issuance, public offer, outcome, grade, qualified ticket, settlement,
merge or deployment occurred; NFL, MLB and frozen records remain untouched.

# OFFER-PILOT-002: corrected NBA route and subject-safe import

Bounded inspection: **2026-10-20 00:10:09–00:10:50 UTC**. Public evidence:
[`2026-10-20-offer-pilot-002.json`](../evidence/offers/2026-10-20-offer-pilot-002.json).
This report supersedes the earlier ESPN **route-feasibility unknown** with actual
successful route evidence. It does not erase the earlier failed requests or
establish source automation permission, executable quotes or product admission.

## Route reasoning and actual requests

The [previous audit](OFFER_INVENTORY.md) tried `propBets` casing on a core route
without `/leagues/`, and later added `/leagues/` while using lowercase `propbets`.
Neither tested the combination. The next ordinary public GET therefore retained
the existing event, competition and provider IDs and combined the proper NBA
league hierarchy with **case-sensitive `propBets`**:

```text
https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events/401909088/competitions/401909088/odds/100/propBets?lang=en&region=us&limit=1000
```

No NFL repository, session, workflow or inherited source file was accessed.
Reasoning used only the routes and generic structure already recorded here.
The bounded pilot made **four requests total**, with no signup, credential,
payment, access bypass, retries, sport sweep or recurring collection:

| Request | Result | Capture completed UTC |
| --- | --- | --- |
| Corrected NBA `propBets` route above | HTTP 200; `count: 1135`, `pageIndex: 1`, `pageSize: 1000`, `pageCount: 2`; 1,000 items | `00:10:09.838153Z` |
| `https://api.sleeper.com/lines/available` | HTTP 200; mixed-sport bare array of 1,508 rows | `00:10:10.659737Z` |
| Same NBA route plus `&page=2` | HTTP 200; consistent declared count/page count; remaining 135 items | `00:10:50.454783Z` |
| `https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/casinos/100?lang=en&region=us` | HTTP 200; provider ID `100`, name `DraftKings` | `00:10:50.814448Z` |

The provider URL came from an actual returned public provider `$ref`; HTTPS was
used. It was not assumed from a universal provider ID. Page 2 was the collection's
declared remaining page. All **1,135 returned items across both pages** were
inspected, including nonplayer, period and milestone families. Counts agree, but
the pages were captured 40.616630 seconds apart and have no atomic snapshot token.
No cross-page simultaneous market snapshot is claimed.

The requests used Python standard-library `urllib.request`, inherited proxy/TLS
verification, 20-second timeouts and an 8 MiB response cap. Four response bodies
totaled **3,367,044 bytes**. Exact URLs, real clocks, response hashes, content
types, HTTP Date, durations and field shapes are in the evidence JSON. Response
HTTP Date is not a per-offer update clock. The raw responses remain under local
`/tmp/nml-offer-pilot-002/` and are excluded from Git and the website.

## Complete requested-category inventory

These are **observed family-label item counts**, not qualified offers or matched
over/under pairs. ESPN counts below use primary total/achievement labels only;
its additional milestone and quarter rows are inventoried separately in evidence.
Sleeper counts are individual side options after subject validation.

| Category | ESPN primary label | ESPN items | Sleeper options |
| --- | --- | ---: | ---: |
| PTS | Total Points | 26 | 278 |
| PRA | Total Points, Rebounds, and Assists | 22 | 202 |
| REB | Total Rebounds | 26 | 292 |
| 3PM | Total 3-Point Field Goals | 16 | 246 |
| AST | Total Assists | 20 | 222 |
| RA | Total Assists and Rebounds | 22 | 0 |
| PR | Total Points and Rebounds | 26 | 0 |
| TOV | Not observed in this event | 0 | 6 |
| TD | To Record a Triple Double | 4 | 0 |
| DD | To Record a Double Double | 12 | 32 |
| BLK | Total Blocks | 8 | 24 |
| STL | Total Steals | 10 | 48 |
| BLK+STL | Total Steals and Blocks | 6 | 0 |
| PA (optional) | Total Points and Assists | 22 | 0 |

Sleeper's RA, PR, TD and BLK+STL remain absent **in this snapshot**. ESPN's TOV
absence applies to this one bounded event. None is a permanent source-coverage
finding. All 13 requested categories remain initial development scope; labels
observed across sources do not create a common tradable universe or validation.

## ESPN fields: prices present, contract meaning incomplete

The response contains 1,093 athlete-linked items and 42 without an athlete link,
covering 13 athlete references and one competition reference. Its 48 observed
type-ID/name pairs include team/game markets, quarter/half markets, first-basket
markets and milestones. These must not be normalized as ordinary player totals.
Type IDs here are league-qualified observations, not universal cross-sport codes.

Every item contains `odds.american`, `odds.decimal` and `odds.fraction`, with
`value` and `open` entries. The collection therefore **does contain explicit
price representations**; it is not accurately described as thresholds-only.
`current.target` and `odds.total.value` are present for 1,069 items; 66 have neither
current target nor total value. Open and current values remain separate.

A recursive field-path inspection found **no explicit side/outcome selector,
provider market/selection ID, period field, overtime policy, market-status field
or settlement-version field**. A repeated athlete/type/target group or adjacent
pair does not prove which price is over or under; no side was inferred by order.
An achievement label alone does not supply a supported yes/no-to-over/under
mapping. Generic “Total” labels do not independently verify full-game/OT rules.
The athlete and competition refs preserve provider identity but do not establish
a cross-source player/event reconciliation or current event start.

Every item has `lastUpdated` with an explicit `Z` timezone. Values range from
`2026-10-15T06:12Z` to `2026-10-20T02:52Z`. **124 page-1 items and 14 page-2 items**
have source updates later than their own actual page capture. These are timing
anomalies, not valid pre-capture availability evidence. They remain in diagnostic
counts; capture clocks are not backdated, shifted or refreshed to make them pass.

Result: **zero complete actual full-game contracts, zero kernel quotes and zero
qualified paper candidates**. This pilot inventories source structure; no ESPN
parser admission, artificial side mapping or price-independent forecast change
was added to make the raw board usable.

## Sleeper replay after identity fix

The new board contains **675 NBA player rows / 1,350 options**, with 164 subject
IDs and 14 game IDs. Both row and option subject types explicitly match `player`
throughout. The source still supplies the nine observed families from the earlier
audit. All NBA rows use `line_type: normal`. All other returned sports were
ignored in this NBA-only importer; no other sport model or repository was touched.

Parser `nba-offer-import-0.2`, documented in
[SLEEPER_IMPORT_VALIDATION.md](SLEEPER_IMPORT_VALIDATION.md), returned:

```text
status=partial, observations=1350, diagnostics=0,
nonplayer_rows_ignored=0, subject_type_invalid_rows=0,
complete_contracts=0, quotes=0, qualified=0
```

The `partial` state preserves unproved remote pagination completeness. Raw
period/OT, current event start, settlement and complete entry terms remain absent;
`normal` does not fill them. `payout_multiplier` remains a **pick'em side
multiplier**, never sportsbook decimal odds or a complete-entry payout table.
A new create-only report receipt was written to ignored
`.local-data/offers/2026-10-20-pilot-002-sleeper-import.json`. Old captures and
receipts were left unchanged. Direct parsing took approximately **0.146111 s**.
Local files are not durable remote capture storage or a prospective paper ledger.

## Permission, evidence lanes and verification

The user explicitly requested bounded read-only verification. This establishes
task authorization, not a provider grant. Prior reviewed Disney/Sleeper terms
restrict automated access/extraction; no overriding permission for scheduled
collection, data reuse or raw public redistribution was established. Sleeper's
documented fantasy API grant does not establish a Picks-route grant. Production
adapters and scheduled collection remain disabled. No new terms interpretation
or rights admission is inferred from HTTP success.

Only derived structural summaries, aggregate counts and hashes are public. They
detect saved-content changes but do not establish provider authenticity, lawful
redistribution, historical publication or executable prices. This is real offer
inspection, separate from synthetic software tests, model evaluation, future
forecast/ticket issuance, settlement, product qualification and website deployment.

Commands actually run from the repository root:

```bash
python3 /tmp/nml-offer-pilot-002/probe.py
PYTHONPATH=. python3 /tmp/nml-offer-pilot-002/summarize.py
python3 -m unittest discover -s tests -p 'test_offer_import.py' -v
python3 -m unittest discover -s tests -v
python3 -m multisport_lab.demo
git diff --check
```

The explicit page-2/provider follow-up used the same bounded `urllib.request`
recipe and its exact requests are retained in the evidence; no probe loop was
enabled. Actual checks at this integration point: **12 focused offer tests and
110 current full-suite software tests passed**, demo exit 0, whitespace check
clean. The first summary invocation without `PYTHONPATH=.` failed to import the
local package; the corrected offline command above succeeded without new requests.

Next requirement: obtain permitted semantic evidence for exact side/selection,
full-game/OT and participation/settlement rules, with consistent source clocks and
identity crosswalks. Complete Sleeper entry terms/eligibility remain separately
required. Use authorized local imports meanwhile; continue typed research export
and price-independent forecasting without claiming complete actual quotes.

# OFFER-PILOT-003: current labels and actual Sleeper rules

Bounded inspection: **October 19, 2026, 8:52:13–8:52:38 p.m. CDT**
(`2026-10-20T01:52:13.284962Z–01:52:38.092528Z`). This is separate from the
price-independent pregame forecast cycle. No ticket or quote is admitted.

Current evidence is the append-only
[v2 summary](../evidence/offers/2026-10-20-offer-pilot-003-v2.json), payload SHA256
`269b3f74d2176ed39ce96c62c15f781711a4b98957cc67c2d7f0d1be9883d4fd`.
The [first summary](../evidence/offers/2026-10-20-offer-pilot-003.json), payload
SHA256 `7778eba48fc26ec2aa2a6b198228129762ecb37230d0a41f013d8fab3e8ff345`,
is retained unchanged. Its Sleeper counts describe recognized parser 0.2 labels,
not absence of raw sum-family labels. The v2 summary references that original,
adds raw-label counts and parser 0.3 replay, and explicitly corrects an old metadata
key that named an envelope-byte checksum as a payload checksum. No source,
observation clock, prior pilot, or original receipt was overwritten.

## Actual requests and retention

Nine ordinary public GETs returned HTTP 200, totaling **4,782,230 raw bytes**.
There were no retries, source sweeps, account/sign-up/API-key requirements,
access bypasses, payments, wagers or recurring collection.

| Route | Actual result |
| --- | --- |
| Correct `/sports/basketball/leagues/nba/events/401909088/competitions/401909088/odds/100/propBets?lang=en&region=us&limit=1000` | 1,000 items; declared total 1,132 and two pages |
| Same route plus `&page=2` | Remaining 132 items; consistent total/pages |
| `https://api.sleeper.com/lines/available` | 2,066 returned mixed-sport rows; 1,360 NBA rows |
| Sleeper's previously observed DFS collection 3125886 and Contest Rules collection 3126755 | Both HTTP 200; actual article links resolved |
| Player Picks Rules article 9047931 | Current generic product, payout, participation and void rules |
| Stats Explained article 6262990 | Basketball DD/TD definitions and period-specific rules |
| NBA Injury Insurance article 9869439 | Direction-dependent injury/void treatment |
| Flex Contests article 9261402 | Max/Flex distinction and void reductions |

Exact complete URLs, request/finish clocks, HTTP Date, content types, byte counts
and raw hashes are in the evidence. Requests used standard-library `urllib`,
inherited proxy, verified TLS, 20-second timeout and an 8 MiB per-response cap.
The two ESPN pages were observed **22.412769 seconds apart**; full declared paging
is verified, simultaneous/atomic board identity is not. Sleeper's bare array does
not prove remote pagination completeness.

Raw files and local inspection scripts remain in `/tmp/nml-offer-pilot-003/`;
local parser reports are ignored under `.local-data/offers/`. Those paths are
not remote archives. Only derived counts, field shapes, semantic facts, URLs,
clocks and hashes enter Git; no individual actual prices or raw response bodies
are published to Pages.

## Complete category inventory

ESPN counts are primary observed family-label items, not paired selections.
Sleeper counts are recognized player side observations after subject validation.
All thirteen requested categories plus optional PA remain in scope. Absence
applies only to this bounded snapshot.

| Category | ESPN primary-family items | Sleeper side observations |
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
| PA (optional) | 22 | 244 |

Sleeper now actually contains `rebounds_and_assists`, `points_and_rebounds`,
`blocks_and_steals` and `points_and_assists`: **828 side options** across the four
sum families, unlike the prior pilot. Parser `nba-offer-import-0.3` adds only
these observed statistic aliases. It preserves absent period, overtime, event
start, product/entry and settlement bindings; every one remains a partial
observation with no kernel contract, quote or qualification.

Of the 2,720 actual NBA options, 2,472 now have supported category labels and 248
quarter options remain explicitly unmapped (`first_qtr_points`: 198,
`first_qtr_rebounds`: 46, `first_qtr_assists`: 4). Quarter labels are never stripped
or mapped to full-game points/rebounds/assists. Every row and option explicitly
matches player subject type; there were zero subject-type errors or other parser
diagnostics. The board has 158 player IDs, 14 game IDs and active/pre-game/normal
labels throughout; none of those labels independently proves exact period or
current event start. Source update clocks range from
`2026-10-19T22:05:02.919000Z` to `2026-10-20T01:51:04.088000Z` and precede this
capture. Actual parser 0.3 import time was `2026-10-20T01:55:52.885069Z`, distinct
from source updates and capture, with approximately 0.218 seconds parsing time.

ESPN contains 1,090 athlete-linked items, 13 athlete refs, 48 type-label families,
explicit American/decimal/fraction prices on all 1,132 items, and 1,066 current
thresholds. There is still no explicit side/selection ID, period, overtime,
settlement-version or market-status field. Adjacent/repeated rows are not mapped
to over/under by order. The retained provider 100/DraftKings identity is prior
actual evidence; this pilot did not make a new provider-identity request.
**73 source updates are later than their own page captures** (65 on page 1, 8 on page 2),
with an observed maximum `2026-10-20T04:31Z`. They remain clock anomalies and are
not repaired by shifting observations or interpreting response HTTP Date as an
offer update. No current executable-contract claim follows.

## New settlement evidence and remaining gaps

The actual [Player Picks Rules](https://support.sleeper.com/en/articles/9047931-sleeper-player-picks-rules)
describes peer-to-peer daily fantasy, VS Score, pool placement and a guaranteed
contest payout. The higher of applicable pool/guaranteed payouts applies;
they do not stack. Pool types have different sizes/economics. The required number
correct and Max/Flex choice are displayed before submission. A side multiplier
from the board is consequently **not standalone sportsbook odds or a complete
entry payout table**.

The generic article describes 2–8 players, multiple teams and no duplicate player.
This project's builder remains 2–6 legs with its existing directions/scopes and
six-first rule only when the whole ticket qualifies. Generic basketball DNP is
0:00 minutes; pushes are void; voids reduce 3+ pick entries, cancel 2-pick entries,
and cancel entries reduced to one team. Overtime counts in the generic product;
postponed/canceled/abandoned basketball games are void. Corrections within 30 minutes
of game end trigger regrading; later corrections do not. These facts do not
establish applicability to a captured row whose period/product is unverified.

[Stats Explained](https://support.sleeper.com/en/articles/6262990-sleeper-player-picks-stats-explained)
confirms DD/TD thresholds in PTS/REB/AST/STL/BLK and separately explains that
quarter markets exclude overtime, while second-half markets include it. This
prevents using the generic overtime rule to fill every missing period field.
[NBA Injury Insurance](https://support.sleeper.com/en/articles/9869439-nba-injury-insurance)
distinguishes eligible MORE and LESS picks after first-half removal/no second-half
return, and describes exceptions and adjusted payouts. It does not by itself
resolve all equality/variant cases or implement financial settlement.
[Flex rules](https://support.sleeper.com/en/articles/9261402-sleeper-player-picks-flex-contests)
require at least three picks, describe payouts with misses and a minimum 1.25x
Flex multiplier, and convert a void-reduced two-pick entry to Max. The actual
applicable state payout table is still unavailable.

**Result: zero complete actual contracts, zero kernel quotes, zero qualified
candidates or tickets.** Remaining gates include exact event/player crosswalk,
current event start, period/variant and rules binding, Max/Flex/pool identity,
actual complete entry economics/eligibility, and supported settlement mapping.
No payout is invented; no independence or same-game joint assumption is admitted.

Prior reviewed source restrictions remain unresolved: bounded user authorization
is not a provider grant for scheduled automation or raw public redistribution.
Production adapters remain disabled. These gaps do not block price-independent
research issuance or later statistical forecast grading.

## Verification and next step

Commands actually run:

```bash
python3 /tmp/nml-offer-pilot-003/probe.py
PYTHONPATH=/tmp/nml-offer-pilot-003 python3 - # inline explicit page2/article follow-up using capture()
PYTHONPATH=. python3 /tmp/nml-offer-pilot-003/summarize.py
PYTHONPATH=. python3 /tmp/nml-offer-pilot-003/expand_summary.py
python3 -m unittest discover -s tests -p test_offer_import.py -v
git diff --check
```

All 9 raw hashes/lengths, declared ESPN page counts and both create-only evidence
receipts were read back and verified. **13 focused software tests passed** after
the alias change. The new regression verifies sum labels, retained pick'em price
kind, unknown period/product/settlement, absence of contract/quote/qualification,
and unmapped quarter markets. Full-suite/demo checks belong to the integration
checkpoint; this report does not claim their result in advance.

Next: obtain an authorized exact entry/variant example with the matched provider
event/player identity, explicit period, displayed Max/Flex/pool economics, complete
state payouts and actual applicable rules. Continue offline imports and
price-independent research; all unsupported quote/ticket claims remain unavailable.

# NBA offer inventory and local capture import

Updated **2026-10-20 UTC**. The latest bounded source inspection was
**2026-10-20 00:10:09–00:10:50 UTC**; see [OFFER-PILOT-002](OFFER_PILOT_002.md)
and its [structural evidence](../evidence/offers/2026-10-20-offer-pilot-002.json).
These are real-source feasibility findings, not live-feed admission, product
qualification, model evaluation, wagering or future paper settlement.

## Current checkpoint

The corrected case-sensitive ESPN NBA route combines `/sports/basketball/leagues/nba/`
with `/odds/100/propBets`. It returned **HTTP 200 and 1,135 items across both declared
pages**, with the returned provider reference confirming `100 / DraftKings`.
The prior 404 was a path/casing failure, not evidence of absent player markets.
The current collection includes explicit American, decimal and fractional price
fields; it must not be described as thresholds-only. Side/selection identity,
full-game/OT, current status and settlement meaning remain incomplete, and
**138 source update timestamps are later than their own page captures**.
No side is inferred by item order and no capture clock is shifted to make a row pass.

Current observed family counts follow. ESPN counts are primary total/achievement
labels, excluding its separately retained milestone/quarter labels. Sleeper counts
are individual side options. Neither column counts complete tradable contracts.

| Category | ESPN primary-family items | Sleeper options |
| --- | ---: | ---: |
| PTS | 26 | 278 |
| PRA | 22 | 202 |
| REB | 26 | 292 |
| 3PM | 16 | 246 |
| AST | 20 | 222 |
| RA | 22 | 0 |
| PR | 26 | 0 |
| TOV | 0 | 6 |
| TD | 4 | 0 |
| DD | 12 | 32 |
| BLK | 8 | 24 |
| STL | 10 | 48 |
| BLK+STL | 6 | 0 |
| PA (optional) | 22 | 0 |

ESPN has 12 requested families plus PA in this one event; TOV was not observed.
Sleeper has 675 NBA rows / 1,350 options in nine families; RA, PR, TD, BLK+STL
and optional PA were not observed. These are bounded snapshot findings, not
permanent coverage exclusions. All 13 requested categories remain in scope.

ESPN's declared paging was fully inspected, but the two pages are not an atomic
snapshot. Sleeper's bare-array remote paging remains unknown. Both sources still
establish **zero complete full-game contracts, zero kernel quotes and zero
qualified candidates**. Production adapters remain disabled: reviewed restrictive
terms do not establish ongoing automation or raw-public-redistribution permission.
Sleeper multipliers remain pick'em multipliers, not sportsbook odds or entry terms.

The [subject-type validation fix](SLEEPER_IMPORT_VALIDATION.md) requires matching
player types before assigning player identities, explicitly counts ignored team
rows and diagnoses missing/conflicting types. The new actual capture has matching
player types throughout; it produced zero subject-type errors and remains partial
because remote paging is unproved. Full contract semantics remain missing.

## Historical first audit: 2026-10-19

The first inspection ran **2026-10-19 22:53–22:55 UTC**. Its observations below
remain recorded as observed; they do not replace the newer successful route evidence.

The public retained evidence is
[`evidence/offers/2026-10-19-offer-audit.json`](../evidence/offers/2026-10-19-offer-audit.json):
request URLs, actual clocks, HTTP states, byte sizes/hashes, structural keys and
aggregate counts. It excludes raw responses and individual real offer rows/prices.
Raw inspection files remain local in `/tmp/nml-offer-audit/`; a normalized local
receipt is in ignored `.local-data/offers/2026-10-19-sleeper-import-receipt.json`.
Those local paths are neither public archives nor durable remote retention.

## First-audit responses (historical)

| Route | Actual result | Consequence |
| --- | --- | --- |
| `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20261020` | HTTP 200; 3 events; response provider ID `100`, name `Draft Kings` | This observed NBA provider label is verified. It is not assumed universal across sports or future responses. |
| `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401909088` | HTTP 200; `pickcenter` includes the same provider and game/team American prices; `odds` is empty | Game/team prices do not establish player-prop prices. No player category is verified from this response. |
| `https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events/401909088/competitions/401909088/odds/100/propbets?limit=1000` | HTTP 404; JSON error; 52 bytes | Candidate route error, not a valid empty board. Requested NBA player offers, thresholds, both-side prices, periods and settlement remain UNKNOWN. |
| `https://api.sleeper.com/lines/available` | HTTP 200; JSON array of 1,916 rows, 3,266,652 bytes, 0.511 s | 657 NBA rows; 1,314 options; 157 provider subject IDs and 14 provider game IDs. All returned NBA rows inspected. |
| `https://api.sleeper.com/lines/available?sport=nba` | HTTP 200; mixed-sport JSON array of 1,953 rows | The query does not establish NBA filtering. Counts differ between real capture times; no stale response is substituted. |
| `https://api.sleeper.com/picks/available` | HTTP 200 HTML marketing page | Not a JSON board; parser failure, not empty success. |
| `https://api.sleeper.com/schedule/nba/2026/regular` and `/2025/regular` | HTTP 200 empty JSON arrays | Those candidate schedule routes did not establish start-time reconciliation. Do not infer no scheduled NBA games. |
| `https://api.sleeper.com/players/nba` | HTTP 200; 2,146 player objects keyed by provider ID | A provider identity lookup exists. League/official crosswalks, current team accuracy and offer-event reconciliation were not independently verified. |

Earlier exploratory ESPN core requests omitted `/leagues/` and also returned 404.
They are retained as wrong-route attempts in the evidence; they cannot establish
missing source coverage. A single ordinary corrected-path request was made under
the user's explicit bounded audit instruction. No authentication, bypass, paid
access or new account was used. No collector was enabled. The later separately
bounded pilot above corrected both path structure and casing together.

Sleeper's response is a bare array, without count/page/next-page metadata. All
returned rows were processed, but **upstream pagination completeness is UNKNOWN**.
The importer records `pagination.complete: false` and reports `partial`; it cannot
claim a comprehensive remote board solely from a successful HTTP response.

## First-capture inventory (historical)

Counts are NBA board rows and individual side options from the first Sleeper
capture. They are not independent forecasts, paper decisions or eligible tickets.
Each of the 657 rows has two options, one over and one under, at its captured line.

| Category | Observed Sleeper label | Rows | Side options | ESPN player evidence |
| --- | --- | ---: | ---: | --- |
| PTS | `points` | 125 | 250 | UNKNOWN |
| PRA | `pts_reb_ast` | 95 | 190 | UNKNOWN |
| REB | `rebounds` | 146 | 292 | UNKNOWN |
| 3PM | `threes_made` | 118 | 236 | UNKNOWN |
| AST | `assists` | 110 | 220 | UNKNOWN |
| RA | Not observed | 0 | 0 | UNKNOWN |
| PR | Not observed | 0 | 0 | UNKNOWN |
| TOV | `turnovers` | 4 | 8 | UNKNOWN |
| TD | Not observed | 0 | 0 | UNKNOWN |
| DD | `double_double` | 17 | 34 | UNKNOWN |
| BLK | `blocks` | 9 | 18 | UNKNOWN |
| STL | `steals` | 33 | 66 | UNKNOWN |
| BLK+STL | Not observed | 0 | 0 | UNKNOWN |

Optional PA was not observed. Unobserved categories remain initial development
scope; a snapshot's zero count does not prove permanent source absence. The parser
maps only actually observed labels. Future labels remain unmapped diagnostics.

For that first actual NBA subset:

- Every row has `sport: nba`, `subject_type: player`, `outcome_type: over_under`,
  `line_type: normal`, `season: 2026`, `season_type: regular`, `game_status: pre_game`
  and `status: active`. This provider's season label has not been reconciled to
  ESPN's ending-year `2027` convention.
- Event, subject, market and option IDs are retained in their provider namespaces.
  There are no duplicate option `line_id` values, or repeated
  `(game_id, subject_id, market_type)` board keys in this capture.
- All 1,314 options have `outcome_value` and explicit `payout_multiplier` fields.
  The latter are **pick'em side multipliers, never sportsbook decimal odds**.
  No complete entry payout, contest identity, pool payout or void-reduction table
  is present. No single-leg EV or complete-entry EV is available.
- The board has `updated_at` integers interpreted as Unix milliseconds, ranging
  from `2026-10-19T15:16:01.258000Z` to `2026-10-19T22:53:10.134000Z`.
  Capture completed at `2026-10-19T22:53:27.139910Z`. The source field's update
  semantics beyond its name are unverified; HTTP Date is not a per-offer update.
- Explicit period, overtime policy, event start, settlement rule version,
  participation/DNP rules and complete entry terms are absent. Option metadata
  is empty. “Normal” is retained as a variant label; it does not prove full game.
  Thus **zero complete full-game kernel contracts, zero kernel quote records,
  zero qualified candidates** were established. Unknowns are not filled from
  a generic NBA model or another venue's rules.

The requested first verified full-game source example and provider rules fixture
remain blocked by missing semantics/access permission. The actual observed-shape
parser is implemented now, with explicit unknown fields. Synthetic software
fixtures exercise its mechanics without publicly redistributing source responses;
they are not source evidence or full-game fixtures.

## Rights and rules findings

The audit retrieved these public documents, with exact response hashes retained:

- [Sleeper API documentation](https://docs.sleeper.com/) describes a free,
  noncommercial, read-only API for users' leagues, drafts and rosters. It does not
  document this Picks line route or establish permission for its automation.
- [Sleeper terms](https://sleeper.com/terms) include restrictions on crawling,
  scraping and automated access/query/extraction without written consent, and
  restrictions on third-party data access. No such written grant was established.
- [Disney terms](https://disneytermsofuse.com/english/) restrict automated
  access/monitoring/copying/extraction, including data mining and datasets/AI uses.
  No provider grant overriding the relevant restriction was established.
- Candidate Sleeper support URLs returned 404, and `/picks/rules` returned the
  generic marketing page. The support home linked a current DFS Picks collection
  and the terms linked a contest-rules collection, but current exact NBA entry
  terms were not captured or verified. A rules link is not a settled payout model.

**PASS:** bounded runtime access, observed Sleeper labels/IDs/line-multiplier
structure, and now the corrected ESPN NBA player route, explicit price fields and
both declared pages. **Historical request FAIL:** the earlier ESPN path/casing
attempts and attempted rule URLs did not supply the required evidence.
**UNKNOWN:** permitted ongoing Picks or ESPN automation, raw redistribution,
Sleeper remote paging, cross-page atomicity, exact sides/full-game/OT and settlement
identity, actual ticket eligibility and complete payout economics. ESPN also has
the source-clock anomalies reported above.
Both live adapters remain disabled. Accessible URLs and the user's one-time audit
request are not presented as provider permission for scheduled extraction or
publication. No raw public redistribution was added.

## Authorized local JSON import

`multisport_lab.offer_import` is an offline import path, not a source collector.
It accepts a user-supplied or otherwise authorized capture only with an explicit
local-research authorization statement. The statement and clocks remain caller
assertions; the import does not independently certify them. Public redistribution
must be false in this initial importer. Store inputs/receipts outside the website
artifact and ordinary Git history.

The envelope has these fields:

```json
{
  "schema_version": "nba-offer-capture-v1",
  "source": "sleeper",
  "source_url": "file:authorized-capture.json",
  "observed_at": "2026-10-19T22:53:27.139910Z",
  "evidence_lane": "REAL_TIME_CAPTURED",
  "http_status": 200,
  "content_type": "application/json",
  "format": "sleeper_lines_v1",
  "authorization": {
    "scope": "local_research",
    "public_redistribution": false,
    "basis": "State the actual authorization; an accessible URL is insufficient"
  },
  "pagination": {"complete": false, "pages_observed": 1},
  "data": []
}
```

The empty `data` above illustrates the envelope only; it is not a captured board.
Use actual observed clocks and source responses. Never relabel historical imports
as real-time evidence. `sleeper_lines_v1` accepts the inspected array shape and
keeps unknown semantics unknown. `normalized_v1` accepts rows with a complete
`PropContract` object, exact decimal-string line/price, explicit provider IDs,
semantic evidence reference, event start, status and nullable source update.
See the fictional constructors in `tests/test_offer_import.py` for the exact row
shape. A missing normalized price preserves a line-only contract with no quote.
An importer-created quote is a software record, never product qualification.

```bash
python3 -m multisport_lab.offer_import .local-data/authorized-capture.json .local-data/offer-report.json
python3 -m unittest discover -s tests -p 'test_offer_import.py' -v
```

The CLI uses strict bounded JSON loading (8 MiB), a 10,000-row limit and create-only
checksummed receipts. It records a new actual import time independently of capture.
An existing different receipt is not overwritten. Hashes fingerprint canonical
decoded JSON and do not prove upstream authenticity, original publication,
permitted reuse or executable prices. HTTP error, blocked access, malformed
response, incomplete board, valid empty board and unmapped labels remain distinct.
Row/option identity mismatches, duplicated provider selections, source-update
clocks later than capture, mismatched units and nonfinite values fail closed.

## First-audit commands and measured results (historical)

The bounded probes used Python standard-library `urllib.request`, inherited proxy
and TLS verification, 18–20 second per-request timeouts, and at most three workers.
The evidence JSON records every attempted URL, request start/end, status and hash;
no hidden collectors or recurring jobs were created. These commands made no
new network calls:

```bash
python3 -m unittest discover -s tests -p 'test_offer_import.py' -v
python3 -m multisport_lab.offer_import /tmp/nml-offer-audit/sleeper_authorized_capture.json /tmp/nml-offer-audit/cli-import-receipt.json
```

Actual result: **8 synthetic software tests passed**. Actual local capture import:
`partial: 1314 observations, 0 diagnostics; receipt_created=True; qualified=False`.
Initial direct parsing plus receipt write took 0.355 s; the receipt was 1,423,710
bytes. These timings describe this bounded run, not an approved production budget.

Next concrete requirement: obtain a permitted local full-game example with exact
period/OT, event/player crosswalk, current rules/product and complete entry terms;
then test the corresponding semantic mapping and settlement. ESPN route access is
now verified; exact side/selection mapping, consistent source clocks and permitted
ongoing use remain unresolved. See the current pilot report for commands, counts
and the separate synthetic software checks.
Continue price-independent forecasting and honest research website work now.

# Private NBA player-line observations

This package adds a separately versioned local view of actual parsed player
thresholds. A line observation can retain an exact source player ID, statistic,
threshold and side while event, period, overtime or settlement fields remain
unknown. It is not a complete betting contract, quote, qualified selection or
financial settlement. Missing prices do not suppress an observation.

Use the existing offline `offer_import` output. Preserve every original receipt
byte and its capture/import clocks. Derive the full 13-category plus PA inventory
from all observations, including PA omitted from the old report's coverage map.
Quarter and unknown labels remain unmapped. A bounded display window is explicit;
it never changes the retained input or claims complete league/source coverage.

Historical derived receipts do not reconstruct missing HTTP bytes. Their decoded
JSON hash must never be labeled a raw-response hash. Verified labels require a
namespaced crosswalk; native Sleeper IDs must not be treated as ESPN IDs.

The October 23 owner instruction authorizes finishing player-line work and asserts
that collection is legal. For this continuation, the integration owner interprets
it as authority for at most **one ordinary read-only GET** of the previously
inspected public `https://api.sleeper.com/lines/available` route for private
inspection. The request has **zero redirects/retries**, the existing **8-MiB**
import response ceiling, a **30-second** timeout, and no credentials, login,
signup, wallet or access-control workaround. A denied or oversized response stops
the attempt; incomplete bytes cannot become parsed source evidence.

That owner assertion is recorded as an assertion, not as independently verified
provider permission. Earlier source reviews remain unchanged. This continuation
does not admit recurring collection or public redistribution, reopen the parked
Polymarket investigation, enable a live adapter, issue forecasts, or authorize a
merge/deployment. All source/provider facts must be reported from actual results.

## Actual result, October 23

The single GET completed at **11:12:31.699799 UTC**, HTTP 200 JSON,
**7,008,196 original bytes**. SHA-256:
`3cc836b9efac5a5e7eb7b9ba098a837f9094d685cabd9a8fc46142b1069aa8aa`.
There were no redirects, retries, credentials or further sports-source requests.
The saved body has 4,015 rows across sports. The existing strict importer accepts
**1,272 NBA player rows / 2,544 side observations**, with zero diagnostics and
188 unmapped quarter side observations. These are source observations, not
forecasts, full betting contracts or an assertion of complete remote coverage.

| Category | Parsed side observations |
| --- | ---: |
| PTS | 346 |
| PRA | 256 |
| REB | 320 |
| 3PM | 278 |
| AST | 230 |
| RA | 230 |
| PR | 316 |
| TOV | 0 |
| TD | 0 |
| DD | 56 |
| BLK | 30 |
| STL | 48 |
| BLK+STL | 6 |
| PA | 240 |

TOV and TD are unobserved in this bounded parsed sample; neither is declared
permanently unsupported. Quarter lines remain explicitly unmapped. The native
player/event/selection IDs, thresholds, sides, variant, literal source team label,
source-declared status and update clocks survive replay. Supplied pick'em side
multipliers remain literal economics; standalone prices are `PRICE_UNAVAILABLE`.

The body does not establish player names, a canonical event crosswalk, scheduled
start, period, overtime treatment or applicable settlement rules. The previously
observed player lookup's original body is no longer available in this workspace;
the six published ESPN name mappings cannot identify native Sleeper IDs. No name,
event, minutes, injury status or full-game interpretation is guessed. A verified
name/event crosswalk and period/OT evidence are the concrete next matching inputs;
financial product rules remain a separate ticket dependency.

## Run and recover without any HTTP requests

From the repository root, replay the already retained body:

```bash
python3 -m multisport_lab.player_line_review \
  --body .local-data/sleeper-lines-20261023/board.body \
  --metadata .local-data/sleeper-lines-20261023/board.metadata.json \
  --output .local-data/sleeper-lines-20261023/review
node scripts/render_local_offer_review.mjs \
  .local-data/sleeper-lines-20261023/review/review.json \
  .local-data/sleeper-lines-20261023/review/player-lines-preview.html
python3 -O -m multisport_lab.player_line_review \
  --verify .local-data/sleeper-lines-20261023/review
```

The input, normalized report and sealed view are retained with create-only writes.
The first intent binds exact source/metadata hashes, window and import/review
clocks. A retry uses that same binding and rejects replacement bytes or a changed
window. Read-only recovery replays original bytes and cross-checks normalized
facts, all observations, receipts and view. All 2,544 accepted observations are
validated, including those outside the 32-card display window. No source file is
truncated. Use a new output directory with explicit `--offset` and `--limit`
to inspect another window; the full-input counts remain unchanged.

An old derived receipt can instead be supplied with `--receipt`. It retains its
original observation/import clocks and is labeled `DERIVED_RECEIPT_ONLY`; it
cannot reconstruct absent HTTP bytes or establish original decimal precision.

The local package ceiling is 512 files / 32 MiB, including receipt/intent metadata;
the raw body/import ceiling remains 8 MiB. NBA options are bounded at 20,000 before
import, with at most 64 per source row; the view is at most 32 cards / 256 KiB.
These local-review bounds do not alter any production or protected pilot budget.

Actual current package: **7 files / 9,971,504 bytes**, including a **57,225-byte**
HTML preview. Original response bytes and metadata exist under ignored
`.local-data/sleeper-lines-20261023/`; they have independent local replay, not
verified durable remote archival. No source rows or original bodies are committed
or included in public site data. Desktop 1440 and mobile 390/320 Chromium checks
verified all 14 inventory rows, explicit gaps, exact threshold/IDs, missing prices,
source provenance and no horizontal overflow or external requests.

## October 23 follow-up: verified names and scoped period rules

A separate bounded follow-up used **six GETs**, with zero redirects/retries and
one shared integration-owner counter. Agents made no source requests. The new
inspection reused the original board; it did not fetch another board or prices.
Exact response bytes, metadata and pre-request claims remain in ignored
`.local-data/nba-live-lines-20261023/`. These originals have local recovery only.
The six requests were the official API documentation, documented NBA player
catalogue, Player Picks Rules, Stats Explained, the retained NBA schedule route,
and General Terms of Use. Response ceilings stayed at 8 MiB for provider JSON,
2 MiB for documentation and 32 MiB for the inspection package.

The documented `https://api.sleeper.app/v1/players/nba` response contains 2,176
objects: 2,146 player entries and 30 explicitly recognized team entries. It
resolves **all 173 native player IDs** in the board. Catalogue key, `player_id`,
sport, first/last/full name are cross-checked; team entries cannot supply player
identities. All source board/catalogue team literals agree in this sample. That
agreement does not independently verify a game or a player's game participation.
No ESPN player ID is supplied for these 173 catalogue entries.

Name lookup was observed at **12:11:50.061540 UTC**, later than the original
**11:12:31.699799 UTC** board. Enrichment retains both clocks. It does not refresh
the line, change an original forecast, or become a historical model input.

Official Player Picks Rules state that overtime counts toward statistics and
that corrections within 30 minutes of game end trigger regrading, while later
corrections do not affect contest results. Official Stats Explained gives the
specific first-quarter/end-of-quarter and quarter-overtime-exclusion rules.
The **94 explicit `first_qtr_points` rows / 188 selections** can therefore carry
Q1 / `OT_EXCLUDED` display metadata. They remain outside this full-game forecast
matcher. Every NBA row, including those Q1 rows, has `line_type=normal`; that
field demonstrably cannot mean full game. Unprefixed markets retain unknown
period/overtime bindings until a native contract or applicable official UI label
establishes them. Generic overtime rules alone do not fill this gap.

The exact retained schedule route `/schedule/nba/2026/regular` returned `[]`.
The board contains **12 opaque native game IDs**, each with two source-declared
team labels, but no verified scheduled starts or canonical event links. These
are a raw team-label inventory, not admitted matchup mappings. Empty output from
this one route does not prove permanent game/source absence. Neither a native
ID's encoded creation time, a recent-performance date nor the nearest game
between two teams may substitute for event evidence.

The API documentation expressly allows noncommercial read-only API use and
own-server caching of the player-ID map, at most once per day. This is a
published allowance for that documented operation. General Terms 11.1/11.3
restrict automated extraction and distinguish provider approval from user
authorization. No retained allowance covers recurring undocumented Picks board
collection or public derived Picks offers. The catalogue allowance does not
grant that separate scope. No further Picks data requests were made after this
restriction was revalidated; the remaining request ceiling was not spent.

The new sealed companion `nba-private-player-line-enrichment-v1` binds the exact
original review/board and retained catalogue/rules bytes. It never rewrites the
v1 review. Its selected cards show verified names, native IDs, later name-lookup
clocks, raw team labels and verified Q1 rules or an explicit unknown-period
fallback. Missing event/start, product-variant and complete-contract fields
remain explicit. Recovery independently replays all retained originals with
explicit integrity exceptions, including under optimized Python.

```bash
python3 -m multisport_lab.player_line_enrichment \
  --base .local-data/sleeper-lines-20261023/review \
  --output .local-data/sleeper-lines-20261023/enrichment \
  --catalogue-body .local-data/nba-live-lines-20261023/02-sleeper-players.body \
  --catalogue-metadata .local-data/nba-live-lines-20261023/02-sleeper-players.metadata.json \
  --picks-rules-body .local-data/nba-live-lines-20261023/03-sleeper-picks-rules.body \
  --picks-rules-metadata .local-data/nba-live-lines-20261023/03-sleeper-picks-rules.metadata.json \
  --stats-rules-body .local-data/nba-live-lines-20261023/04-sleeper-stats-rules.body \
  --stats-rules-metadata .local-data/nba-live-lines-20261023/04-sleeper-stats-rules.metadata.json
python3 -O -m multisport_lab.player_line_enrichment \
  --base .local-data/sleeper-lines-20261023/review \
  --verify .local-data/sleeper-lines-20261023/enrichment
node scripts/render_local_offer_review.mjs \
  .local-data/sleeper-lines-20261023/review/review.json \
  .local-data/sleeper-lines-20261023/enriched-preview.html \
  --enrichment .local-data/sleeper-lines-20261023/enrichment/enrichment.json
```

The existing complete-offer matcher now also accepts original admitted
daily-snapshot and recurring R0/K0 publication graphs. Both Python and browser
paths require their strict typed validators and hashes, exact input/event/player/
team/period/overtime identities, genuine modes, and required remote completion.
The matcher keeps their original evidence lanes and rejects decisions predating
local persistence, independent recovery or publication. Development previews,
late/unacknowledged originals and Q1/full-game mismatches cannot match. The Props
renderer uses the same microsecond decision clock and preserves valid independent
channels if another channel's matching proof fails. No price is required.
This software path does not grant public source admission or make the incomplete
actual board observations into contracts. Synthetic graph tests are explicitly
separate from actual-source verification.

This package installs no collector or public offer route. Existing licensed
SportsDataverse forecast delivery stays independent; absent player lines or odds
do not block its authorized statistical forecast path. The paper builder remains
`NO_ACTION` until its own eligibility is established.

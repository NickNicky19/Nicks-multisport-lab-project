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

This package installs no collector or public offer route. Existing licensed
SportsDataverse forecast delivery stays independent; absent player lines or odds
do not block its authorized statistical forecast path. The paper builder remains
`NO_ACTION` until its own eligibility is established.

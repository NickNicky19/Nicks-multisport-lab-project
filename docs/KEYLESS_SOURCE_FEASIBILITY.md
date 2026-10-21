# Keyless NBA player-offer source feasibility

Documentation checkpoint: **October 21, 2026**, repository head
`74a7914ab7499cfb6963e326bf9c3c4543a0c8c0`.

This additional-source review established **two documented credentialless public
market APIs**, but admitted **no new provider-data request or complete NBA player
contract**. Source-use scope for this parser-and-retained-evidence task remains
unresolved or restrictive in the documents reviewed. This is a bounded finding,
not a claim that every possible free/keyless source is unavailable.

The user constraint is explicit: collection must need no provider API key,
signup, account login, subscription or trial. The proposed private raw-evidence
decryption key is separate. Its backup decision did not block this review or the
independent retained-source parser work.

## Existing ESPN and Sleeper review remains separate

Reuse [OPS002_SOURCE_USE_REVIEW.md](OPS002_SOURCE_USE_REVIEW.md) and the retained
[actual-source receipt](../evidence/offers/2026-10-21-offer-source-followup-v1.json).
Disney's reviewed terms restrict automated extraction; Sleeper's documented free,
tokenless fantasy API allowance has not been established for the undocumented
Picks `/lines/available` feed. No new ESPN or Sleeper data request was made here.

The surviving ESPN October 21 snapshot has six team/overtime rows, no athlete
references and no complete player contract. Its returned provider reference
explicitly identifies DraftKings; that attribution belongs to that response.
Earlier player-family evidence, actual prices and unresolved contract semantics
remain as recorded. Missing original Sleeper bodies are not recreated from their
surviving summaries. Empty or partial snapshots do not establish permanent source
absence. Offline replay/parser work can proceed on retained actual bytes while
preserving the original access/admission limitation.

## Additional candidate 1: Kalshi

The official [Quick Start: Market Data](https://docs.kalshi.com/getting_started/quick_start_market_data)
says “Kalshi provides several public endpoints that don’t require API keys” and
“No authentication headers are required for the endpoints in this guide. You can
start making requests immediately!” It supplies production API examples and
explicitly suggests building market-monitoring tools and analysis dashboards.
This is evidence of documented keyless API access, not an inferred permission
from an HTTP 200.

The Kalshi site's linked [Data Terms of Use](https://kalshi-public-docs.s3.amazonaws.com/kalshi-data-terms-of-service.pdf)
create a specific unresolved conflict for this task. Section I excludes software
development and providing archived/cached datasets to others from noncommercial
use absent prior written consent. Section II restricts collecting, copying,
electronic extraction and AI-assisted uses. It says use of Kalshi Data “in any
manner for any machine learning and/or artificial intelligence,” including coding
or development, is expressly prohibited. These are data-use terms; a client SDK's
code license would not remove them.

The data terms frame their scope around website Kalshi Data; the quick start
expressly invites public API reads. This review does not resolve every possible
API/website scope question. It stopped before any data GET because the reviewed
material does not establish the proposed software/parser inspection and original
response retention allowance. No NBA player market, category coverage, exact
identity or contract rules were inspected. Kalshi binary event contracts would be
a separate venue/product, not sportsbook odds or a pick'em multiplier.

Smallest next step: identify an applicable published API-specific allowance or
exception that covers this exact one-off parser inspection and retained evidence.
Do not substitute a new signup, provider key or generic scraper license.

## Additional candidate 2: Polymarket

Official [Discover Markets documentation](https://docs.polymarket.com/market-data/discover-markets)
says “Find the events and markets your integration needs” and “This data is
public and does not require authentication.” It documents NBA tag `745` as an
example and says companion sports events may cover player props, with a
`-player-props` suffix. These are documentation examples, not an observed NBA
contract, verified player identity or category-support claim.

The [official terms page](https://polymarket.com/tos) embeds
[the original terms document](https://docs.google.com/document/d/1N4aYlRcqaWCeKMID7vUSWJ1UPMvw_v6SP4cOFN8ZxR4/preview),
marked **effective August 11, 2026**. Its public preview body was recovered without
login. The text distinguishes informational Content Features from trading and
Technology Features. Restricted-jurisdiction users may use Content Features;
US trading restrictions are not treated here as a universal ban on informational
reads. Official [Geographic Restrictions documentation](https://docs.polymarket.com/api-reference/geoblock)
likewise describes order-placement restrictions. No order, wallet, account,
geoblock probe or circumvention was attempted.

However, “Your Responsibilities & Prohibited Conduct” restricts data-mining,
robot/crawler or similar extraction tools to scrape/remove data, and manual
monitoring/copying without prior consent. Terms also separately restrict Capital
Market Clients and market data distributors from API/raw/derived data access
without written agreement. “Ownership & License” grants a limited personal
license subject to those terms; open-source software licenses are separate.

The explicit public API invitation is promising. Its applicability to this
single software/parser proof with retained originals has not been reconciled
against the extraction/copying and distributor restrictions. No data GET was
made, so no actual NBA player-contract semantics, prices or coverage are claimed.
This is the international Polymarket / Adventure One QSS, Inc. service, not
Polymarket US or a sportsbook product.

Smallest next step: resolve the documented Gamma informational API allowance for
one bounded read and local evidence retention under the applicable US
informational-use terms. Review any public derived-fact display separately.
No trading access or provider credential is proposed.

## Request and evidence boundary

The machine-readable [request ledger and findings](../evidence/offers/2026-10-21-keyless-source-use-review.json)
retain exact URLs, start/completion clocks, statuses, byte counts, SHA-256 hashes,
redirects and local original-document locations. Eight requested documentation
URLs plus one HTTP redirect produced **nine documentation HTTP GETs**; the
incorrect Kalshi `/api-agreement` URL returned 404 and supplied the official Data
Terms link. **Provider-data GETs: zero.** The Polymarket terms text was decoded
locally from the already-received public Google Docs preview model; that local
read required no further network request or private document access.

Automatic approval review rejected a proposed pair of Manifold documentation
GETs on the stated ground that they would exceed the authorized 12-GET bound.
Neither request executed; no retry or alternate transport followed. The retained
task-specific ledger contains nine actual GETs. No third-source conclusion is
made. A further review would first need the bounded-request authorization resolved.

Original document bodies and request receipts currently live under
`/tmp/nml-keyless-source-basis-20261021/`. Their exact hashes are recorded, but
remote durable recovery has not been verified. They are documentation-review
originals, not an admitted or durably recovered raw player-offer contract.

## Full category scope and next work

PTS, PRA, REB, 3PM, AST, RA, PR, TOV, TD, DD, BLK, STL, BLK+STL and optional PA all
remain in scope. For **both additional sources every category is
`NOT_INSPECTED_SOURCE_USE_GATE`**, with observed count unknown and parsed count
zero. That is distinct from “unobserved in a bounded data sample” and from
“unsupported.” No live NBA data sample was requested from either source.

Continue the separate offline native-source parser against retained ESPN
originals. Preserve observed prices exactly; absent prices remain
`PRICE_UNAVAILABLE`. Complete identity, event, period/overtime, side/line,
variant, product and settlement meaning are still required for an offer-only
contract. Price-independent statistical forecasts remain independent of all
bookmaker availability. No new admission, collection, scheduler, forecast,
publication, activation, merge or deployment follows from this review.

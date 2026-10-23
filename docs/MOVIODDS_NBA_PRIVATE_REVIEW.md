# Free NBA source result and private parser

October 23, 2026 UTC. This is an actual-source result and an offline private
review implementation. It is not a scheduled collector, a currently live board,
a public offer admission, a forecast, or an executable quote.

## Established source and scope

[MoviOdds](https://moviodds.com/) is an independent publisher that explicitly
identifies its feed as bet365 data. Its [API reference](https://moviodds.com/doc)
invites free keyless REST reads and instructs clients to keep their own copied
matches, names and prices. Its [sports reference](https://moviodds.com/docs/sports/)
includes basketball and player props. This is an applicable published invitation
for the bounded private read/cache/replay performed here, not an inference from
an HTTP 200, another scraper's license, or blanket upstream authorization.
No provider key, account, signup, payment, wallet or trading operation was used.
The separately keyed Bet Builder pricing POST was not called.

This package uses exact original catalog/snapshot responses and the official
[bet365 basketball rules](https://help.bet365.com/s/en/sportsrules/basketball).
It does not identify bet365 as DraftKings or Sleeper. It does not establish
account/jurisdiction eligibility, a permanent availability guarantee, permission
to mirror the raw board publicly, or a public display admission. The absence of
a key requirement does not make every endpoint or redistribution use equivalent.

## Actual bounded result

The complete individual-game snapshot contains **2,097 selections**:

- **1,229 full-game player selections**, all parsed as source observations and
  matched uniquely by exact name, season and event-team affiliation to the
  retained SportsDataverse roster (**19 distinct player labels**, not 1,229
  different players). No native permanent player IDs were supplied
  or invented.
- **34 complete local binary contracts:** 28 DD and six TD selections. An
  explicitly offered Yes/No achievement does not require inventing a source
  numerical threshold or comparing a numeric ladder label to an assumed line.
- **1,195 numeric player selections remain incomplete.** The response supplies
  a number but does not establish its exact comparison operator. The adapter
  preserves that literal selection and its price without assuming `>=`, `>`,
  over/under, a push rule for that number, or an alternative-line equivalence.
- Six game selections (spread, total and winner), 175 first-quarter player
  selections, and 687 other selections are accounted for separately. None is
  silently counted as a complete full-game player contract.

| Category | Observed / parsed full-game selections | Complete local contracts |
| --- | ---: | ---: |
| PTS | 114 | 0 |
| PRA | 135 | 0 |
| REB | 96 | 0 |
| 3PM | 122 | 0 |
| AST | 67 | 0 |
| RA | 149 | 0 |
| PR | 129 | 0 |
| TOV | 0 | 0 |
| TD | 6 | 6 |
| DD | 28 | 28 |
| BLK | 68 | 0 |
| STL | 91 | 0 |
| BLK+STL | 111 | 0 |
| PA | 113 | 0 |

TOV is **unobserved in this sample**, not proven permanently unavailable. Its
native group mapping is not yet implemented. Other numeric families have reviewed
group/name extraction, but lack reviewed comparison semantics. DD/TD has the
reviewed binary achievement meaning. One game cannot establish league-wide
coverage or feed reliability.

The provider's scheduled start differs from the retained canonical schedule
candidate by **600 seconds**. Both originals and both literal times remain
visible. Provider-native event identity is established; forecast matching to
the canonical candidate is explicitly blocked. No presumed tip-off offset,
current roster assumption or fuzzy join clears that discrepancy.

## Clocks, meanings and recovery

The price snapshot was observed at **20:00:14.986063 UTC**. Its complete original
is 543,939 bytes, SHA256
`32d073114b74f8d3bc743a4f783cddccbbc393cee9073a16d0e47fd3cad3ab9b`.
Complete event metadata was observed at **20:01:21.535885 UTC**; official rules
at **20:01:31.153166 UTC**. Completing interpretation using those later originals
does not backdate completion to the quote observation. Actual normalization and
latest-knowledge clocks are retained separately. Nothing is prospective issuance.

Official rules establish the ordinary full-game DD/TD definitions, overtime,
dressed/court-time participation, game-date/interruption/replay requirements,
push treatment and competition-statistics correction meaning. Later amendments
do not change that venue settlement. Statistical forecast grading remains a
separate process; this module performs no financial settlement. Region and
account eligibility are not supplied by this feed. Special quarter, first-basket
or promotional rules are not substituted for ordinary full-game DD/TD rules.

The new `bet365-static-rules-text-v1` extractor reuses the existing strict static
HTML extractor and handles only self-closing drawing leaves inside excluded SVG.
The old `html-static-text-v1` behavior is unchanged. Rules are replayed from the
original HTML with explicit derived-text hashes and UTF-8 quotation spans.

Price-change, market-confirmation, publisher-response, retrieval and
normalization clocks remain distinct, including original nine-digit fractional
source clocks. Comparisons use exact nanoseconds. A recent fixture clock cannot
rescue a stale exact market. A stale/suspended or post-start selection cannot
become a complete pregame observation. Prices remain literal, selection-linked
source decimal prices with qualification unavailable; there is no EV conversion.
An absent decimal price remains `PRICE_UNAVAILABLE` without making an otherwise
complete Boolean offer incomplete. A supplied fractional string is preserved and
is not silently converted to fill a missing decimal field.

The original first prototype is retained at
`.local-data/moviodds-review-20261023/`. The corrected review is separately stored
at **`.local-data/moviodds-review-20261023-v2/`**, including seven bodies, seven
original metadata inventories, a create-only intent and the normalized review.
Its later normalization clock is genuine. The original bodies and metadata are
identical across these directories. The corrected review eliminates an integral
float serialization mismatch; the prototype is not rewritten or relabeled.

Recovery checks complete raw hashes, actual redirect chronology, semantic replay,
original normalization time, identities and original intent. A retry cannot
rebind inputs or select another fixture. The old SportsDataverse source clocks
and actual 302/200 inventory are reused; no synthetic ESPN responses or new source
captures are substituted. This is an **independently replayed local copy**;
durable remote archival of these new private originals has **not** been verified.
An upstream URL or a digest is not a recoverable archive.

Limits remain 2 MiB per admitted original, 256 KiB per review, eight explicitly
selected display rows, and 512 files / 32 MiB per private package. The shared
ledger's separate 512-record / 32-MiB limits are unchanged and no new ledger
records are written. The full basketball board exceeded its 8-MiB collection
ceiling and is retained as an incomplete failed discovery response. It was never
imported or truncated into a valid board; the complete per-fixture route fit.

## Runnable offline path

The current package can be recovered without any provider or encryption key:

```bash
python3 -O -m multisport_lab.moviodds_offer \
  --verify .local-data/moviodds-review-20261023-v2

node scripts/render_local_offer_review.mjs \
  .local-data/moviodds-review-20261023-v2/review.json \
  .local-data/moviodds-review-20261023-v2/private-preview-final.html
```

The renderer independently invokes optimized-Python original-byte recovery
before producing static HTML. It does not execute source scripts, load external
resources or grant public admission. The fixture under `tests/fixtures` is
explicitly fictional and synthetic; it is not a copy of actual individual offer
facts. Identity attribution remains SportsDataverse/hoopR, ESPN-derived, CC BY4.0,
with an explicit normalization/modification notice. Roster membership is not
confirmed participation or a minutes estimate.

## Request accounting and next delivery work

The sole direct-request writer made **26 GET attempts: 15 documentation and 11
data-route requests**, zero retries or redirects. The initial root-owned budget
of 24 was explicitly extended by two named requests before execution to finish
the selected fixture's complete identity and official rules. Other agents made
zero direct GETs and no provider contacts. Documentation/search tools are counted
separately; their underlying service-managed HTTP count is unknown. No automatic
approval rejection occurred in this investigation.

Other bounded candidates produced specific results: PropEdge returned an empty
NBA edges result and no usable selected-player stats; NuroPicks returned no NBA
rows in the requested date sample; the permitted FOX NBA RSS sample contained no
complete game-player prop; Flash supplied five actual partial NBA rows through a
free sample while its full production feed requires paid/keyed access; the linked
Azuro documentation route returned 503. None proves universal source absence.
No new Sleeper, ESPN, Covers or Polymarket data request was made.

Next: resolve the exact provider/canonical start mapping and document numeric
selection operators before matching these families to forecasts. A separate
public-derived-display admission and permitted durable private-original archive
must precede website offer delivery. This adapter can already recover and display
the verified binary source contracts privately; it does not need a provider key.
Price-independent research forecasting continues under its own existing source,
timing, retention and publication gates. Nothing here changes R0/K0, frozen
experiments, original records, protected pilots, PROS004/S0, NFL/MLB, schedules,
public publication or the 2–6-leg/direction/scope/NO_ACTION policy.

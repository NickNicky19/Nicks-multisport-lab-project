# Local semantic offer v2

`nba-local-semantic-offer-v2` is a new, isolated **LOCAL_REVIEW_ONLY** contract.
It neither changes `nba-player-offer-v1` nor admits an offer to the website,
paper builder, executable quotes or public publication. The product is explicitly
Polymarket binary event contracts. It is not DraftKings, Sleeper or a compatible
parlay-leg representation. All thirteen requested NBA categories plus PA remain
in `category_inventory`; the current source predicate adapter handles PTS/REB/AST
and rejects other source families rather than fabricating their meanings.

## Identity and completion

The player has a source label, an independently evidenced Wikidata canonical
identity, and a separately nullable native provider ID. The declared selection
is `(market_id, outcome_label)` with `kind: MARKET_OUTCOME_LABEL`; its condition ID
links optional CLOB evidence. A native token ID is separately nullable. Neither
native ID, assigned price nor execution eligibility is a universal requirement
for an otherwise complete **price-free semantic** contract.

Required gaps are computed from missing canonical identity, player team/opponent,
event version, period/overtime and the six required settlement meanings. A source
matchup does not assign the player to a team. An affiliation witness must identify
the same canonical player and event. An observed event snapshot version is
explicitly `OBSERVED_SNAPSHOT_SHA256`, derived from canonical decoded JSON of the
entire retained event object. It is not an upstream event revision. The original
provider version literal has a separate field. If that recipe or affiliation
has not been reviewed, retain null and its gap.

`semantic_status` is `INCOMPLETE` or `COMPLETE_LOCAL` as computed from those gaps.
`completed_at` is null for an incomplete contract and equals the actual
`normalized_at` for a complete local review. These are not forecast issuance
clocks. Toggling flags cannot clear a missing requirement. `public_admission` and
`ticket_eligibility` remain false and `qualification` remains `UNAVAILABLE` in
both states. Source restriction/readiness flags are independently retained and
do not define semantic completeness or prove trading availability.

This version always keeps `price.status: PRICE_UNAVAILABLE` and `price.value:
null`. Literal outcome price arrays and bid/ask strings remain under
`unassigned_source_economics`, with `PRICE_TO_SELECTION_UNVERIFIED` separately
from semantic gaps. A later verified token pair does not, by itself, establish
the alignment of an earlier price array. This version cannot assign such a price.

## Original evidence and clocks

Every original evidence entry declares its exact URL, raw SHA256/count,
request/observation clocks, content type and nullable source update time.
`contract_observed_at` equals the primary market original's observation clock.
`knowledge_observed_at` is the latest included observation. `normalized_at` must
follow all included evidence and cannot be in the future. Linking later CLOB or
rules evidence therefore never backdates completion or replaces the original
market observation.

Every populated semantic fact or literal economic/status value has one explicit
binding: `{field, evidence_id, pointer, transform}`. `pointer` is a strict JSON
pointer. Each field has an exact reviewed source-role/pointer/transform tuple;
matching aliases, unrelated same-host routes and direct-value bypasses are not
accepted. For example, Gamma event identity uses its top-level `/id`, not an
`alias_id`; category uses `/sportsMarketType`, not an unrelated string equal to
the normalized category. Bounded transforms support exact values/quotes, UTC conversion,
source-question parsing, Gamma team identities, canonical identity, explicit
same-player/event affiliation, observed snapshot hashing, and labeled CLOB
tokens. CLOB token replay checks the exact condition path, response condition,
query-free route, binary outcome pair and any supplied game start. If an original
event provides `markets`, the selected contract must appear exactly once and its
identity, question, category, line, start, description, outcomes and token fields
must agree with the primary original. It never infers token mapping
from Gamma array position. Decimal lexemes can be retained before binary-float
conversion. Unknown liveness units and unspecified correction meanings stay
unknown; generic oracle finality cannot fill the correction field.

Actual settlement bindings in this deliberately narrow Gamma-v2 adapter must be
verbatim quotations from the primary market's `/description`. The fictional
fixture additionally supports structured `/settlement/<field>` values only in
the `SYNTHETIC` lane. An unrelated generic NBA or oracle document cannot become
applicable settlement evidence merely because it contains matching words. A
future linked-rule adapter requires an explicit applicability review and version
extension. The conservative whole-word correction/regrading language guard
rejects text such as “the correct generic oracle proposal”; passing that lexical
guard is **not** proof of venue-policy applicability. Numerical wire values and
identifiers use ASCII digits consistently in Python and the frontend. This
bounded English-language policy guard also uses explicit ASCII case/whitespace
rules, preventing Python-only Unicode matches from disagreeing with the browser.

`validate_semantic_offer` checks types, field sets, bounded size, seal, identities,
clocks, binding coverage and computed completeness. `replay_semantic_offer` also
requires the original bytes, checks every raw hash/count and replays every
binding. This verifies local integrity and declared relationships. It does not
establish upstream authenticity, provider permission, real capture chronology
or the semantic applicability of an incorrectly reviewed quotation. Actual
correction/regrading meaning still requires source review for this exact product
and market; a keyword alone is never that evidence. Local recovery is explicitly
not a verified durable remote archive.

Limits remain **32 contracts / 256 KiB** for a review batch, **256 KiB** for one
contract, at most sixteen original references and **2 MiB per original**. There
is no HTTP client, key/account requirement, collector, scheduler, issuance,
trading, grading or financial settlement in this module.

## Offline integration and fictional fixture

`tests/fixtures/semantic_offer_v2.json` contains `{contract, originals}`. Every
subject, event, affiliation and correction rule in it is fictional and marked
`SYNTHETIC`. Its complete price-free case demonstrates software behavior only.
Do not reuse its affiliation, snapshot or correction policy for actual data.

An actual adapter constructs the same shape from retained Gamma market/event,
canonical identity and any later documented CLOB/rules originals, preserving
each individual clock and source literal. Set unresolved actual affiliation,
event version or correction meaning to null and omit its verified binding.
Call `seal_semantic_offer`, then `validate_semantic_offer` and
`replay_semantic_offer` with an `evidence_id -> original bytes` map. Retain the
replay receipt and source decision separately. Do not put actual originals or
individual source offer facts into the public fixture or Git history.

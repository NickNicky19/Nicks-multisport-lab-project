# Sleeper NBA game, period and public-feed documentation

Inspected October 23, 2026. This is a documentary checkpoint for the existing
private player-line review, not admission of a live or public Picks feed.

| Requirement | Official document and actual finding |
| --- | --- |
| Player names and native IDs | [API documentation, Players](https://docs.sleeper.com/#players) documents the player catalogue and own-server ID-map caching, at most once daily. The retained catalogue already resolves all 173 board player IDs; it supplies no ESPN IDs for them. |
| NBA game IDs, matchup, scheduled start | The retained API reference documents fantasy-league matchups, not a lookup for the real NBA `game_id` values in the Picks board. No official mapping route was established in this inspection. The earlier exact schedule request returned `[]`; it does not prove permanent absence. |
| In-game target | [In-Game Contests](https://support.sleeper.com/en/articles/6998002-sleeper-player-picks-in-game-contests) expressly grades in-game selections on the entire game's statistics, including play before entry. This establishes that product's target, not a native pregame field mapping. |
| Quarter / second-half overtime | The same article excludes overtime from quarter markets and includes it in second-half markets. [Stats Explained](https://support.sleeper.com/en/articles/6262990-sleeper-player-picks-stats-explained) also supports the already verified explicit Q1 labels. |
| Unprefixed pregame rows | Neither document binds `line_type=normal` or every unprefixed wager label to a full-game target. All retained Q1 rows also have `line_type=normal`. Those fields remain unresolved for pregame full-game contracts. |
| Participation and corrections | [Player Picks Rules](https://support.sleeper.com/en/articles/9047931-sleeper-player-picks-rules) supplies the retained pregame DNP and correction rules. The newer in-game article's no-automatic-DNP treatment is expressly for in-game selections; it must not replace pregame rules. |
| Free documented API access | [API introduction](https://docs.sleeper.com/#introduction) permits noncommercial read-only use without an API token. Its stated resources are fantasy leagues, drafts and rosters, with the documented player lookup. It separately permits attributed embedding of its trending list. |
| Recurring Picks access and public derived thresholds | No applicable allowance for undocumented Picks-board collection and public derived offer display was established. [General Terms](https://support.sleeper.com/en/articles/5486620-general-terms-of-use), sections 11.1/11.3, must be considered alongside any narrower API approval. The fantasy/trending allowance cannot simply be expanded to Picks. |

An applicable published allowance can satisfy its stated scope; bespoke written
consent is not universally required. No claim is made that a permission or NBA
mapping document cannot exist. Its applicability has not been established here.

## What was actually retrieved

Three controlled documentation GETs, zero redirects/retries, no Picks-board or
other sports-data capture. Each body was bounded at 2 MiB; the unchanged local
package limit is 32 MiB. Agents made no provider requests. Three successful web
discovery calls used nine queries; the browsing service's underlying HTTP count
is unknown and is not included in the three controlled GETs. One malformed tool
invocation returned no source content and was not a provider denial.

| URL / document | Result | Observation UTC | Original bytes |
| --- | --- | --- | ---: |
| [Legacy rules link](https://support.sleeper.com/en/articles/5556096-over-under-rules), linked by the retained Stats Explained article | 404 | 17:47:12.334102 | 65,914 |
| [In-Game Contests](https://support.sleeper.com/en/articles/6998002-sleeper-player-picks-in-game-contests) | 200 | 17:47:37.975310 | 84,581 |
| [Contest Rules directory](https://support.sleeper.com/en/collections/3126755-contest-rules) | 200; 27 listed articles | 17:48:34.228020 | 109,292 |

Original bodies, request claims, receipts and discovery results are retained under
ignored `.local-data/nba-feed-document-review-20261023/`. SHA-256 values and exact
receipt references are in
`evidence/offers/2026-10-23-sleeper-feed-document-review.json`. These originals have
verified local readback, **not verified durable remote archival**. The later rule
capture does not refresh the board's original 11:12:31.699799 UTC observation.
No full copyrighted article or private board body is added to public output.

## Exact next source action

The retained official API page identifies **api@sleeper.app** in its encoded
email link. Picks Rules separately gives **support@sleeper.app**. The prepared
[request](SLEEPER_NBA_FEED_REQUEST.txt) asks the API team to identify published
documentation or confirm a narrow, free, credentialless scope and the missing
NBA game/period schema. It is a draft; **no email or support message was sent**.

The request distinguishes private original-response caching from attributed
public derived display and from raw redistribution. It asks for no payment,
provider key, login or signup. The offline parser still needs only retained
source bytes and metadata, independently of operational encryption-key custody.

Until the missing source evidence is supplied, keep verified names and explicit
Q1 semantics in the private review. Keep unverified games, pregame periods and
public admission unresolved. More board pulls or prices cannot answer these
documentary questions. All 13 categories plus PA remain in scope; price-independent
statistical forecasting remains a separate admitted path.

# KEYLESS-CONTRACT-007 — exact-condition CLOB linkage and semantic offer v2

October 21, 2026. **One retained NBA player contract enriched and normalized as
an incomplete local semantic record; zero complete contracts.** A verified
canonical identity and declared market/outcome selection no longer require an
invented native player ID. The exact CLOB witness supplies native YES/NO token
associations. Price-to-selection correspondence, player affiliation, event
version and the applicable NBA correction rule remain unresolved as described
below. No public offer, qualified ticket or genuine forecast is created.

## Four-request result and scope

Nick authorized at most four additional read-only source/documentation GETs,
including redirects and retries, for the same retained condition. One integration
owner was the sole HTTP requester; all agents used zero source requests. The
create-only private supplement references the earlier request ledger's exact
SHA256 and never rewrites that ledger or its original observation clocks.

| Request | Official route | Status | Body bytes | Observed UTC |
| --- | --- | ---: | ---: | --- |
| 1 | Documentation: Get CLOB market info | 200 | 578,287 | 12:36:02.581777 |
| 2 | Help Center root | 302 | 0 | 12:36:38.940819 |
| 3 | The returned Help Center `/en/` location | 200 | 72,511 | 12:36:50.030627 |
| 4 | Production `GET /clob-markets/{condition_id}`, exact retained condition | 200 | 476 | 12:39:13.542467 |

**4/4 requests, 651,274 bytes, one separately counted redirect response and its
manual follow, zero retries or automatic-approval rejections.** Automatic
redirects were disabled. Every response stayed below the unchanged 2 MiB limit.
No source request followed budget exhaustion. GitHub repository administration
and local artifact verification are separate from source collection.

The first document independently establishes the production base
`https://clob.polymarket.com`, exact path, `security: []`, credentialless GET
examples, and the `t[].t` token ID / `t[].o` outcome-label meanings. The separately
retained CLOB scope decision precedes the data request. Its basis combines this
operation with the previously retained official Market Data Overview's explicit
application workflow for reading outcome/order-book data and the retained
personal informational-use/copy terms. It does not automatically inherit a Gamma
allowance, treat HTTP 200 as permission, or infer a trading right from a public
read. This is a narrow documented-API interpretation for one personal/local
informational inspection, original retention and private review. No account,
wallet, key, signup, paid service, recurring/bulk collector, order, trade or public
offer/raw redistribution is admitted. Source-use declarations and checksums do
not themselves grant permission or attest upstream authenticity.

The CLOB body explicitly agrees with the retained Gamma condition, start and
token set. Its labeled token objects establish the selected native token without
assuming array order. Its rewards/fee/trading-parameter fields are not resolution
rules. Its literal version is not an event revision. Gamma's earlier price arrays
remain unassigned: a later token association does not by itself establish their
price-to-selection correspondence at the earlier observation time.

## Settlement question and concrete recommendation

The retained market describes the player-stat threshold, full game including
overtime, DNP, postponement/cancellation and official NBA statistical source. It
does not state what happens if the NBA later corrects its statistics. The Help
Center root redirected to its English landing page, which exposed category
links rather than an applicable NBA player-contract correction article. The
exact CLOB endpoint supplies order-book parameters and outcome identities,
without a correction/regrading policy.

Thus this package did **not** establish any of these as an applicable rule:
accept corrections until a particular clock, ignore later corrections, regrade
after resolution, or never regrade. Generic NBA statistics documentation and
generic oracle challenge/finality language cannot fill the field. The retained
`customLiveness` literal is not assigned units or substituted for a postgame
correction deadline. No claim is made that every venue policy or clarification
is absent; no onchain clarification was inspected.

**Recommendation: keep this Gamma/CLOB observation partial. The currently
retained routes cannot satisfy the complete-contract requirement. Do not spend
more requests on additional events or prices to solve this settlement gap.**
The specific next documentary lead returned by the Help Center is
`https://help.polymarket.com/en/collections/17859586-markets`. A later bounded
review must locate an explicit correction/regrading statement and establish its
applicability to this international Polymarket/A1 NBA player-stat contract;
Polymarket US, another sport or a generic oracle rule is insufficient. If no such
applicable evidence can be established, this source remains observational for
this requirement. ESPN/DraftKings and Sleeper remain the preferred separate
products. No further request is authorized by this exhausted allowance.

## Versioned, price-free representation

The new isolated wire contract is **`nba-local-semantic-offer-v2`**, documented in
[OFFER_SEMANTIC_V2.md](OFFER_SEMANTIC_V2.md). Existing offer-v1, local-review-v1,
public validators/admission registries and original records remain unchanged.
The v2 Python and frontend validators/renderers are implemented together.

It supports a verified external canonical player crosswalk with
`native_provider_id: null` and an explicitly declared
`(market_id, outcome_label)` selection. A native token is optional for semantic
completeness; the current actual token is populated only from the later exact
CLOB witness. Native identity absence, unavailable prices, source restriction
flags and execution eligibility are not universal semantic-completeness gates.
No exchange YES/NO contract becomes a DraftKings/Sleeper selection or compatible
parlay leg.

The selected actual record has these computed **required semantic gaps**:

- `PLAYER_TEAM` and `PLAYER_OPPONENT`: source event teams identify the matchup,
  without establishing the player's affiliation for that game.
- `EVENT_VERSION`: the retained source version literal is preserved separately
  and is not promoted to a verified event snapshot/revision.
- `SETTLEMENT_STAT_CORRECTIONS`: applicable correction/regrading meaning remains
  unspecified.

`PRICE_TO_SELECTION_UNVERIFIED` remains in a separate price-binding inventory,
with `PRICE_UNAVAILABLE` and no assigned value. Exact source price arrays/bid/ask
are preserved separately. No odds, probability, value or EV is derived. Semantic
status is `INCOMPLETE`, `completed_at` is null, and public admission, execution
and ticket eligibility remain false. A complete price-free example with null
native IDs exists **only as a clearly labeled synthetic software fixture**.

The primary contract clock remains **11:26:31.749940 UTC**. Latest linked knowledge
is **12:39:13.542467 UTC**. The first local v2 normalization was actually recorded
at **12:50:08.291254 UTC** and is retained unchanged through retries. Later replay
verification does not relabel any of those clocks or imply prior completeness.
The unmodified actual record replays eight original references and 31 field
bindings. Validation improvements made during draft review are separately
verified against that retained record; it is not a genuinely issued forecast.

The original bounded inventory remains **28 player-stat rows / 14 source name
labels, 28 partial parses, zero complete contracts**: PTS10/REB10/AST8, with the
other eleven categories unobserved in that event. The new preview selects one
of those contracts. All thirteen requested categories plus PA remain in the
inventory; the single-card table does not claim every category was observed.

## Original retention, replay and private preview

Actual facts, individual source IDs, prices and response bodies stay ignored
and private. Locations:

- Original package: `.local-data/keyless-contract-006/originals/` unchanged.
- Supplement: `.local-data/keyless-contract-007/originals/`, ten create-only files
  comprising four bodies, four sidecars, the shared ledger and CLOB scope decision.
- Previously retained source-use witnesses copied without new requests:
  `.local-data/keyless-contract-007/source-use/`.
- New record/HTML: `.local-data/keyless-contract-007/preview-v2/`.
- Browser evidence: `.local-data/keyless-contract-007/qa-v3/`.

These prove **local retention/readback**, not verified durable remote archival.
The private encryption-key design and backup decision are separate, unchanged,
and not required by the offline parser. Public Git contains code, fictional
fixtures and sanitized counts/hashes, without actual individual offers or raw
bodies. Independent GitHub recovery of code/evidence is distinct from recovery
of the private raw originals.

```bash
python3 -m multisport_lab.gamma_semantic_review \
  --prior-bundle .local-data/keyless-contract-006/originals \
  --supplement .local-data/keyless-contract-007/originals \
  --output .local-data/keyless-contract-007/preview-v2
node scripts/render_semantic_offer_review.mjs \
  .local-data/keyless-contract-007/preview-v2/contract.json \
  .local-data/keyless-contract-007/preview-v2/standalone.html
python3 -O web/tests/semantic-offer-browser.py \
  .local-data/keyless-contract-007/preview-v2/standalone.html \
  .local-data/keyless-contract-007/qa-v3
```

The first two outputs already exist. The writer independently replays an existing
receipt on retry, preserves original normalized content/clocks, and can finish
an interrupted local write. The HTML is create-only/idempotent. Browser QA needs
a **new** ignored output directory on another run.

The private card shows the readable player/matchup/date, composite selection,
canonical identity, native token, separate clocks, known settlement terms and
four explicit semantic gaps. Price and execution reviews are separate, the full
category scope is visible, and Paper Builder remains **NO_ACTION**.

Managed Chromium rejected direct `file://` navigation with
`net::ERR_BLOCKED_BY_ADMINISTRATOR`. That attempt stopped without changing policy.
Rendering the already-authorized local HTML bytes through `page.set_content`
passed 1440/390/320px with details expanded, no overflow/errors and zero HTTP
requests. The receipt explicitly records `PROVIDED_LOCAL_HTML_BYTES` and
`file_url_navigation_verified: false`. This verifies rendering, not the blocked
file route. No automatic approval rejection occurred and no rejected source
action was retried through another transport.

## Review and operating boundaries

Independent review found generic replay alias/source-role and event-membership
gaps, a misleading correction-keyword guard and a Python/JS Unicode-digit
validation mismatch. The connected actual adapter used fixed roles and retained
an incomplete result. New v2 verification is tightened with explicit integrity
exceptions under optimized Python and focused negative regressions before the
required integrated checks. Actual results and final source pins are recorded in
the latest handoff and review receipts; no result is anticipated here.

There is no model evaluation, genuine forecast, prospective outcome/grade,
qualified ticket, financial settlement, activation, scheduler, public offer,
merge or deployment. PR #10/#12 stay draft, PROS004/S0 inactive. Price-independent
forecast preparation remains separate under its existing genuine-input and
activation safeguards. No missing offer or price is added as a forecast gate.
All original records, frozen research, builder scopes/directions/2–6-leg behavior,
NFL and MLB remain unchanged.

# PROS004 public research contract v1 — inactive readiness

This is implementation readiness. It does not activate the reservation, authorize
collection, admit issuance, evaluate the reserved comparison, or publish a site.
The repository currently retains no genuine PROS004 original forecasts or grades.
The historical six R0 bundles/grades use their unchanged existing public contract.

## Versioned assets and completeness

The static builder now emits manifest schema 3. Existing manifest 1/2 readers
remain supported. Schema 3 adds `pros004` (a content-addressed index descriptor,
or null on a first failed collection) and `pros004_error`. A failed new collection
retains previously verified assets and their original generation clock, or names
the error; it cannot manufacture a successful empty research collection.

`nba-pros004-public-index-v1` declares its full forecast/grade totals, all 13
requested categories plus PA, exclusions, future availability reasons, and every
content-addressed page. Index activation is **INACTIVE**, qualification
**UNAVAILABLE**, financial settlement **NOT_EVALUATED**, and comparative aggregate
evaluation **NOT_RUN**, with the registered November 25 evaluation gate retained.
There is no comparative score, mean, best model, or model-selection output.

Pages use `nba-pros004-public-page-v1`. Four complete records per page support
168 originals and 168 active grades across at most 84 pages. A page is at most
512 KiB; the complete collection is at most 24 MiB. A forecast projection is at
most 96 KiB, a grade projection 24 KiB, including their retained source bodies.
Those row ceilings reserve 19.6875 MiB for all 336 records before bounded index
and page metadata. The assembler and independent browser loader check all page
counts, hashes, byte lengths, identities and total limits. Neither truncates
records or probability atoms to fit. These public limits do not increase the
private ledger's unchanged 512-record / 32-MiB limits.

## Original bytes, admission, grades and corrections

Forecast and grade projections retain their source `LedgerRef`, evidence lane,
original ID, and `record_json`: the exact canonical original unsigned JSON body,
with `record_encoding = CANONICAL_ORIGINAL_BODY_WITHOUT_ID`. The original ID is
the SHA-256 of those exact UTF-8 bytes. This preserves Python numeric lexemes such
as `10.0`, which a browser number roundtrip would otherwise change to `10`.
The browser verifies that string's bytes before parsing and rejects duplicate
JSON keys. Outer projection hashes separately bind original bytes and metadata.
This is forecast/grade content; it does not export the history panel or raw feeds.

All original category PMFs, minutes PMF, joint replay recipe, original identities,
producer/source versions, generation/verification/issue clocks and exact shared
input references remain intact. Python and JavaScript validators enforce the
frozen R0/K0 identities, complete source-binding inventory, coherent category
summaries, T90/window/latency bounds, and separate completion clocks.

Operational producer 3 uses source binding 3 with the same 19-file source
inventory as binding 2. The original forecast body and public projection schema
remain unchanged. The source forecast receipt references the versioned event
claim retaining its original input-finalization proof. Strict source-store
recovery checks that proof before public assembly; the browser retains its exact
source references and admission explanation without exporting raw inputs.
Producer/binding 1 (13 files) and producer/binding 2 (19 files) remain readable as
original evidence. Operational and binding version numbers must agree exactly;
compatibility does not admit legacy evidence under the new completion policy.

`admission` separately reports retained-original status, actual local completion,
independent remote completion, eligibility and reasons. A missing or late proof
cannot be inferred from pre-write `received_at`. The inactive collection rejects
`eligible_for_comparison = true`, including when its supplied clocks would be
timely. Timing proof alone does not establish reviewed activation.

The public collection retains unadmitted originals with their explanations;
it does not silently erase a single issued peer. History names a missing peer,
preserves source clocks and original probabilities, and never generates a
replacement. Upcoming remains empty with specific source-inventory, activation
and completion reasons. Passing an event start does not establish an outcome.

Only active statistical grade revisions enter public grade pages. The index
counts superseded grades, and source-ledger references identify originals; the
append-only source ledger retains correction links and previous receipts.
Original forecasts are never rewritten. DNP, missing, postponed, nonfinal and
unresolved grade states stay separate from scored outcomes. Individual category
and minute scores are checked against their matching original PMFs; paired
active grades must share the same outcome identity for their event/player.
These are statistical grades, not financial settlement or qualified tickets.

## Interface and verification

Props and Performance render this collection separately from legacy historical
research and legacy aggregate diagnostics. R0/K0 and REAL_TIME_CAPTURED identities
are explicit. No PROS004 record enters the paper candidate universe. Existing
one/selected/all-sport scope, 2–6 legs, OVER_ONLY/UNDER_ONLY/MIXED and NO_ACTION
semantics remain unchanged.

Synthetic fixtures stay under `tests/` or `web/tests/` and never enter build assets
or the repository ledger. Checks include full 168+168 paging/readback, invalid
checksums and valid-checksum semantic errors, missing pages/peers, late or absent
completion proof, invalid minutes, duplicate JSON keys and inactive eligibility.
A Python-produced current source binding and original `LedgerRef` pass through
the actual JavaScript snapshot loader, including a complete scored grade.

```bash
python -m unittest discover -s tests -p test_pros004_publication.py -v
node web/tests/pros004.test.mjs
python -O web/tests/pros004_browser_smoke.py
```

The last command requires existing Playwright/Chromium and permission to bind
loopback. It uses temporary invented assets, tests desktop 1440/mobile 390 views,
all categories/PA, model and missing-admission labels, sport scope and the builder.
It supplies no operational issuance, real-data verification or deployment evidence.

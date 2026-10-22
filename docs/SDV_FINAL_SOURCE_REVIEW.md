# NBA final-source metadata inspection

## Initial scope, before the metadata request

This package admits **one bounded inspection of SportsDataverse release
metadata**. It does not yet admit a player-boxscore download, a final outcome,
genuine grading or a recurring collector. No new HTTP request has occurred.

The create-only review is
[`2026-10-22-sdv-final-source-metadata-scope.json`](../evidence/data/2026-10-22-sdv-final-source-metadata-scope.json).
Its publisher evidence is the exact README retained on October 21 at
23:09:03.630520 UTC: 292,938 bytes, SHA256
`ab5be8c4c7a303883f6e8eea134b7737ff06eab884b8b6303e18d618ca4d9df9`.
The receipt records the original witness location and exact numbered excerpts.

The README identifies the repository as the SportsDataverse **data-release
store**, displays its CC BY 4.0 label and explicitly lists
`espn_nba_player_boxscores`. This is a publisher data-release basis, with ESPN
and hoopR provenance preserved. It is neither a software-license inference nor
authorization for direct ESPN collection. Retention and attributed review of
the exact public release metadata are within this limited scope.

The next eligible request, after integration-owner review, is:

```text
GET https://api.github.com/repos/sportsdataverse/sportsdataverse-data/releases/tags/espn_nba_player_boxscores
```

The shared allowance is **one GET total**, at most **256 KiB**, with **no
redirects or retries** and no credentials. Retain its exact body when within
the limit and its actual request/completion clocks even if unsuitable. An
oversized response is a factual failure; limited diagnostic bytes must not be
labeled its complete original. Stop on failure or oversize.
An HTTP 200 cannot establish final-player coverage, field semantics or finality.

The retained README lists player boxscores through season **2026**, even though
schedule and roster releases reach 2027. The metadata inspection must establish
whether an actual 2027 asset exists, its advertised exact name/format/size,
asset identity, hash and update time. Do not request a guessed filename or infer
permanent absence if the release has not yet advanced.

After inspection, select only an actually advertised bounded asset and register
its schema and finality criteria before collection. Existing offline
`nba_data.normalize_sdv_row` and `with_sdv_schedule` can retain exact identities,
explicit FINAL status, DNP and count checks. The current daily outcome CSV
normalizer is development-only; a genuine final-source admission remains a
separate implementation step. Missing rows stay missing. Later corrections
append original evidence, revised outcomes and statistical grades while
preserving original forecasts and prior grading history.

The broader owner goal permits preparing a recurring permitted forecast/grading
path. Actual source-family verification, bounded operating rules and durable
retention still precede operation. This receipt creates no scheduler, changes
no first-cycle producer file and activates no collection.

## October 22, 2026 — one metadata response retained

The one authorized credentialless GET completed at **02:51:46.408272 UTC**
(started 02:51:45.763476 UTC): HTTP **200**, **174,922 bytes**, **0.646378
seconds**. Redirects and retries were disabled. The complete original metadata,
safe response headers, actual clocks and seasonal inventory are retained in
[`2026-10-22-sdv-final-source-release-inspection-v1.json`](../evidence/data/2026-10-22-sdv-final-source-release-inspection-v1.json).
Raw-body SHA256 is
`d1de79ac784cc5f0247b3578828bd467992b204ab549bd49b0105ba73e993d11`.
An independent local decompression/reparse reproduced its bytes/hash and every
retained inventory entry. Remote durable recovery remains a later checkpoint.

The actual release now advertises 102 seasonal assets covering 1994–2027 in
CSV, Parquet and RDS formats. The retained README's through-season label lagged
this release inventory. Actual advertised 2027 assets are:

| Name | GitHub asset ID | Bytes | Publisher updated (UTC) | Advertised SHA256 |
| --- | --- | --- | --- | --- |
| `player_box_2027.csv` | 662283964 | 43,806 | 2026-10-21 11:30:15 | `697c67283cac7d1af7b0f7a579aa0f60dd3fd76520a9940526d93c4ea7df4029` |
| `player_box_2027.parquet` | 662284035 | 27,731 | 2026-10-21 11:30:16 | `768b3cc20e38d4b134a1395938f1123b8b8635adf12c28d51c6fbb6b2f09580a` |
| `player_box_2027.rds` | 662283872 | 5,829 | 2026-10-21 11:30:13 | `7ae8577f2445a736669b900126a9276f559e3f88a8066c7fe64e72c10a15e1a3` |

**Request count: 1/1 metadata GET; zero asset GETs, player rows or outcomes.**
These advertised hashes and formats have not yet been checked against downloaded
asset bytes. They establish neither finality nor complete target-player coverage.
No further request remains within this inspection allowance.

The smallest useful next step is a separately bounded inspection of the actual
advertised 43,806-byte CSV, retaining its original bytes and checking the existing
offline normalizer's required columns, event/player identities, DNP encoding,
count arithmetic and source update limitations. Later genuine grading also needs
an independently retained final schedule observation and explicit completeness
criteria. Missing/nonfinal data remains pending; no outcome is inferred from
this metadata or publisher upload time.

## October 22, 2026 — bounded actual CSV and retained-schedule audit

A separate reviewed scope admitted the actual advertised CSV only:
[`2026-10-22-sdv-final-source-csv-inspection-scope-v1.json`](../evidence/data/2026-10-22-sdv-final-source-csv-inspection-scope-v1.json).
Its canonical GET returned 302; one explicitly validated public GitHub release
asset redirect returned 200 at **02:56:18.797775 UTC**. There were **two asset
GETs, no retries**, consuming the package total of **3/3 requests** including
the earlier metadata GET. No further request remains in this package.

The exact body is **43,806 bytes**, SHA256
`697c67283cac7d1af7b0f7a579aa0f60dd3fd76520a9940526d93c4ea7df4029`,
matching the advertised asset. Exact original bodies, safe headers and later
actual request/completion clocks are retained in
[`2026-10-22-sdv-final-source-csv-capture-v1.json`](../evidence/data/2026-10-22-sdv-final-source-csv-capture-v1.json).
Transient signed redirect query values were not retained. Local decompression,
hash verification and CSV replay succeeded; durable remote recovery still needs
the integration checkpoint.

The offline audit retained all **57 fields and 84 rows**. Existing source
normalization accepted all 84 rows: **68 APPEARED, 16 explicit DNP**. It found
no duplicate event/player key, missing required field, count-identity failure,
normalization rejection or retained-schedule join rejection. DNP remains distinct
from zero production. Decimal source minutes retain the existing
`rounded_whole_minutes` precision; no exact duration was inferred.

Only the already-retained October 21 schedule original was read for finality and
score comparisons; **zero new schedule requests** occurred. All three observed
events have matching event/start/season/team identities and explicit retained
`STATUS_FINAL`, `post`, completed status. Summed player points and source team
scores match all six retained final team scores:

| Event | Archived matchup and score | Source rows |
| --- | --- | --- |
| `401909088` | Boston 113 at Detroit 121 | 28 |
| `401909089` | Philadelphia 106 at New York 100 | 28 |
| `401909090` | Oklahoma City 116 at San Antonio 104 | 28 |

The create-only row/field/clock audit is
[`2026-10-22-sdv-final-source-csv-audit-v1.json`](../evidence/data/2026-10-22-sdv-final-source-csv-audit-v1.json).
Its complete ordered field list is the contract input for a later wrapper.
These are two retained observations from the same publisher lineage, not
independent upstream verification. A matching point sum does not establish every
non-scoring count or a complete participant roster.

The first daily-cycle event **`401909094` has zero rows in this earlier file**
and remains pending. No genuine outcome, grade, forecast, financial settlement or
qualification was created. The inspection does not refresh the publisher's
October 21 update clock or automatically admit recurring/genuine grading.

The next implementation step is a separately versioned genuine final-source
wrapper using these verified CSV fields and exact retained schedule evidence.
It must require exact original forecast identities, explicit final status and
complete required selected-player counts; preserve DNP/missing/nonfinal states;
recover grades by original forecast/outcome identity before writing; and append
correction evidence and revisions without replacing original records. The first
cycle's protected producer files and dated windows remain unchanged.

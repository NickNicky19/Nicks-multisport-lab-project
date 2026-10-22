# NBA final-source metadata inspection

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

# Historical input retention: publisher evidence and bounded decision

Checked October 20, 2026, 02:06 UTC. This is a bounded source-document review,
not a new historical dataset download or a blanket assertion of upstream rights.
Exact response hashes, observation clocks, excerpts and the integration decision
are retained in `evidence/data/2026-10-20-history-retention-rights.json`.

## Evidence actually retrieved

Four verified-HTTPS GETs inspected the public SportsDataverse data-release
repository root, its README and LICENSE, and the NBA producer README. All four
returned 200, totaling 319,908 response-body bytes. No account, key, paid service,
dataset refresh or scheduled extraction was used. Original response bodies remain
in `/tmp/nml-history-rights/`; the compact evidence record retains their hashes
and the relevant exact excerpts. These observation clocks do not become source
publication/update clocks.

The release-store [README](https://github.com/sportsdataverse/sportsdataverse-data/blob/main/README.md)
has this literal badge/link at lines 10–11:

```text
[![License: CC
BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-blue.svg?style=flat-square)](https://creativecommons.org/licenses/by/4.0/)
```

Its immediately following text describes the repository as the **release store**
whose package loaders read data from its GitHub releases. The same README's
NBA (ESPN) section identifies `hoopR-nba-data`, sourced from `hoopR-nba-raw`, and
lists the `espn_nba_player_boxscores` and `espn_nba_schedules` releases used here.
The [producer README](https://github.com/sportsdataverse/hoopR-nba-data/blob/main/README.md)
independently shows that ESPN processing pipeline feeding those release names.
This is direct **publisher-asserted CC BY 4.0 labeling of the data release
store**, beyond the previously inspected software licenses or public URL access.
The audit did not fetch or independently interpret the linked license deed.

The actual root [LICENSE](https://github.com/sportsdataverse/sportsdataverse-data/blob/main/LICENSE)
says `MIT License`, copyright 2023 SportsDataverse, and scopes its permission to
`this software and associated documentation files (the "Software")`. That text
is not converted into an upstream ESPN data grant. The README data-store label
and the software-license wording are recorded separately. The four retrieved
responses contain no explicit representation establishing that every upstream
ESPN right is licensed to this project; that scope remains unverified.

README body SHA-256:
`ab5be8c4c7a303883f6e8eea134b7737ff06eab884b8b6303e18d618ca4d9df9`.
Its Git blob SHA-1 `8b27188f09849c5d048b0c57b09487e39484bbdf` matches the
independently retrieved repository-root listing. LICENSE body SHA-256:
`9c3898cce6957255c63911737a6441daf7ed70c445381b8a7f32b75a28123ea6`;
its blob likewise matches the listing. Full URLs/hashes for all four responses
are in the evidence record. A content hash binds received bytes; it does not
authenticate the original provider or establish data freshness.

## Concrete integration decision

The integration owner accepts the publisher's observed CC BY 4.0 data-store
assertion, together with the user's explicit durable-input research request,
as the recorded basis for retaining **one bounded compact derived normalized
model-input record** for this pilot, with attribution, the license URL, source
references and a modification notice. This is a scoped operating decision; it
does not claim blanket ESPN clearance or infer permission from small file size.

**Lossless compaction still discloses the full normalized player statistics in
this PUBLIC GitHub repository.** It is not merely a hash, aggregate or harmless
metadata record. The retained input must be identified accurately as a full
normalized-history representation, within the explicit file/byte budget.
Original raw Parquet/JSON source bodies remain excluded from Git. The complete
normalized input record is also excluded from GitHub Pages assets: the website
receives typed forecasts, compact grades and appropriate provenance only.

The retained history remains the full 26,645-row cohort with original normalized
SHA-256 `489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c`.
No 20,000-row truncation is permitted. Lossless encoding, raw-source normalization
bindings and independent restart/readback must be verified separately; this
rights review neither creates that input record nor proves its data lineage.

Required attribution accompanies the retained input and its documentation:

> Historical player and schedule data: SportsDataverse, processed by the
> hoopR ESPN NBA pipeline (`hoopR-nba-data` / `hoopR-nba-raw`), ending-year
> season 2026. The `sportsdataverse-data` release-store README labels its
> releases CC BY 4.0: https://creativecommons.org/licenses/by/4.0/ . Original
> release URLs, raw hashes and observation clocks are retained in this project.
> Changes: schedule/player joining, explicit complete-appearance and standard-team
> cohort filtering, field/identity normalization, and lossless compact encoding
> for model-input recovery. This does not assert ESPN endorsement or blanket
> clearance of all upstream rights.

Retain actual transformation versions/hashes and upstream exclusions beside this
notice. Keep original observation, known source update, normalization/import and
issuance clocks distinct. Neither public access nor this bounded retention
decision admits unrestricted bulk redistribution, new source coverage, recurring
extraction or an automated collector. Any broader operation needs its own actual
source-operation and retention assessment under the existing project constraints.
No additional service, signup, key or wagering account is introduced here.

## Prospective comparison retention and publication dependency

The immutable `prospective004-protocol.json` remains an **inactive reservation**;
its original bytes are not amended by this follow-up. Besides its paired-producer
and deduplicated shared-history requirements, the full 21-date comparison would
produce up to 168 forecasts and 168 grades. The current typed public snapshot
accepts at most **32 forecasts and 64 grades** (`publication.py`). Activation
therefore also requires a versioned bounded publication/history plan: for example,
validated pagination or an explicitly declared export subset with complete
durable ledger recovery. Silent truncation or dropping inconvenient grades is
not an admissible fix. The single operational pilot, six old plus four new
forecasts when genuinely issued, fits today's public cap. No public-schema or
ledger-limit increase is made by this document or the rights evidence.

Independent integration review also corrected the reservation's pilot record
allowance: preparation input + fresh input + four forecasts + four later outcomes
+ four later grades is **14**, rather than six. The complete planned ceiling is
442 comparison records +18 original records +14 pilot records =**474**, leaving
**38** of512 slots for corrections/failures. This correction does not alter the
immutable inactive reservation. Activation must measure actual bytes against the
unchanged32MiB cap and preserve the full pilot/outcome history.

# NBA statistical data feasibility

Observed **2026-10-19 22:53–23:01 UTC**, from this repository's managed runtime.
Implementation started on `implementation/nba-foundation` at
`de86e92352f0fb5a76831275f6de6b256ce05434`; the integration checkpoint/commit is
recorded in [HANDOFF_STATUS.md](HANDOFF_STATUS.md). This report covers bounded
source verification and normalization. It contains no model-performance,
prospective-paper, product-qualification or website-deployment claim.

The actual offer inventory is separate: [docs/OFFER_INVENTORY.md](docs/OFFER_INVENTORY.md).
Source admission remains per operation/category. Successful public reads do not
establish permission for scheduled extraction or public redistribution.

## Findings

| Check | Result | Actual evidence and limit |
| --- | --- | --- |
| SportsDataverse public, no-key file route | PASS | 2026 player Parquet downloaded, 606,444 bytes; its SHA-256 matches GitHub's advertised digest. One ending-year season only. |
| `nba_api` documented NBA Stats route | UNKNOWN | The exact documented `boxscoretraditionalv3` request timed out after 18 seconds. The package was not installed or certified; no retry/bypass was attempted. |
| NBA CDN live boxscore route | FAIL for this request | HTTP 403 for game `0022500001`; no bypass attempted. This does not establish every NBA source is inaccessible. |
| Primary NBA public game page / gamebook | PASS for one game | Both returned HTTP 200. Embedded player boxscore, final period and official PDF were inspected for HOU–OKC, 2025-10-21. |
| `pbpstats` public game-stat route | PASS for one game | HTTP 200, 178,327 bytes / 4.959 seconds; complete-player counts reconciled to primary. Package installation, full season and DNP population remain unverified. |
| All primitive count fields | PASS in identified rows | 28,779 identified appearances have every required count. No scoring/rebound identity or made/attempt failure. |
| Complete player identity | FAIL for 33 raw rows | Missing athlete ID/name; quarantined, never assigned guessed IDs. All 33 belong to source team Chicago. |
| Complete appearance minutes | FAIL for 24 identified appearances | Minutes null despite count fields and `did_not_play=false`. Preserved as missing; no zero fill. |
| Precise played minutes | FAIL for the release | All numeric values are whole minutes. Primary sample proves rounding can turn a six-second appearance into zero. |
| Final status / period evidence | PASS with limitations | Separate 525,802-byte schedule asset has 1,326 explicit final and four postponed games. Strict event/team/season/time joins cover every identified player row. Reset final clocks prevent duration admission on affected games. |
| Broad primary reconciliation / complete season coverage | UNKNOWN | One game, including two overtimes, reconciled. The whole schedule is not independently reconciled to primary NBA results. |
| Corrections / historical revision sequence | UNKNOWN | Current asset hash/update retained; original/revised row histories are not supplied by this audit. |
| Historical pregame availability | UNKNOWN | Final boxscores and archive updates do not prove information existed at T−90. No pregame roster/DNP/role claim. |
| Intended recurring extraction / raw redistribution rights | UNKNOWN | Public direct downloads need no signup/key; code licenses do not settle upstream rights. Production adapters and raw publication stay disabled. |

## Actual retained sample and field audit

SportsDataverse's `player_box_2026.parquet` represents the **2025–26 ending-year
season**, dates 2025-10-21 through 2026-06-13. Its producer describes ESPN NBA API
lineage; the inspected creation script reads per-game `nba/json/final/{id}.json`.
The release is a current reconstructed archive, not an immutable pregame ledger.

The complete bounded file contains **34,883 rows / 57 columns / 1,326 events**.
Raw flags identify 28,801 appearances and 6,082 DNP rows. Removing 33 invalid-ID
rows from normalization leaves **34,850 identified rows**, **591 players**,
28,779 appearances and 6,071 DNP rows. There are zero duplicate namespaced
event/player keys. Distinct source-team count is 33, explained below; a null
athlete ID is never counted as another player.

The required fields checked are participation, minutes, PTS, FGM/FGA,
FG3M/FG3A, FTM/FTA, OREB/DREB/REB, AST, TOV, BLK and STL. FG2M is derived as
`FGM−FG3M`, checked nonnegative. All 28,779 identified appearances satisfy
`PTS=2*FG2M+3*FG3M+FTM`, `REB=OREB+DREB` and made ≤ attempted. All count
primitives are present. There are 24 missing-minute appearances and **104
rounded-zero-minute appearances**, which remain appearances. Recorded zero
production is retained: 3,322 zero-point and 3,329 zero-rebound appearances,
for example. Per-field missing/zero counts are in the retained summary.

SDV DNP rows have null minutes/counts. NBA's primary page instead carries zero
placeholders on blank-minute rows with explicit DNP/DND comments. The primary
adapter changes those placeholders to null outcomes only after checking the
explicit comment and absence of positive production. Missing participation stays
UNKNOWN. Final-game `starter`, `active`, `reason` and current roster fields are
not admitted pregame features; the inspected release even carries
`reason="COACH'S DECISION"` on actual appearances.

IDs are preserved as **ESPN** or **NBA** namespaces. ESPN event `401809243` and
NBA event `0022500001` are not interchangeable. Matching names were manually
checked one-to-one for this bounded reconciliation, along with team, matchup,
date, tip and final scores. This is not a general player identity resolver.

## Independent primary reconciliation

The real 2025-10-21 HOU–OKC sample has **27 roster rows: 20 appeared, seven DNP**.
SDV agrees with the official NBA boxscore on all **300 count comparisons** (15
fields × 20 appearances), all participation states and the 125–124 final score.
Every reported whole-minute value is within 0.5 minutes of the primary clock.
Chris Youngblood's six-second appearance demonstrates why a rounded zero is
not DNP. The official PDF independently lists the player rows and six periods.

`pbpstats` supplies 20 player appearances plus separate team entries. Its count
objects are sparse. For this audit only, absent count keys were hypothesized
zero and individually checked against primary: **300/300 comparisons agree**.
That is not a blanket zero-fill rule for other pbpstats responses. Its player
minutes differ by one second on nine rows. DNP roster coverage is absent from
this game-stat response, so it does not establish participation prediction.

The NBA page declares `Final/OT2`, period six; primary scores by period confirm
**58 playing minutes**. The page's `duration=3:16` and PDF's `Game Duration:3:15`
are elapsed wall-clock measurements, not playing duration. Neither is a valid
denominator for player share.

## Schedule join, competition scope and duration limits

The separate `nba_schedule_2026.parquet` contains **1,330 unique events**: 1,326
`STATUS_FINAL`, `completed=true`, `state=post`; four postponed with
`completed=false`. Every player-asset event is in the final schedule set; no final
schedule event lacks player rows. Joining 34,850 identified rows by exact ESPN
event, team pair, season/stage and archived event timestamp produces zero conflicts.
These are current archive statuses, not original completion-publication clocks.

The release also contains **four All-Star mini-games**, team IDs `111386`,
`132374`, `132375`, labeled `season_type=2` with one regulation period.
`season_type=2` alone is therefore insufficient to select standard NBA games.
The reviewed standard-team inventory in this ending-year asset is ESPN IDs
1–30. There are 1,231 stage-2 standard-team events, not an asserted 1,230-game
regular-season cohort; the stage can include the NBA Cup final. Source stage
codes 3 and 5 are preserved rather than silently merged into stage 2.

Schedule clocks are zero on 484 events, 720 seconds on 808, and 300 seconds on
38. Many explicit final records evidently retain/reset a full-period clock.
The adapter retains their explicit archived FINAL status but withholds playing
duration when that clock conflicts. For standard teams, four-regulation-period
format, integral final period ≥4 and zero final clock, it derives
`48+5*(period−4)`. **12,639 roster rows** have duration admitted under these
checks. The six-period primary sample corroborates this derivation for one game.

The proposed duration/share REB comparison remains blocked for a complete
eligible panel: rounded/missing minutes and conflicting clocks need an explicit
precision/coverage resolution before any share-model evaluation. The empirical
whole-line reference baseline can continue with reported-minute precision and
an explicitly declared common cohort. No unverified duration is substituted.

## Pregame metadata and evidence clocks

The official historical injury PDF
`Injury-Report_2026-04-12_01_00PM.pdf` returned HTTP 200, 103,444 bytes, and its
text contains `Injury Report:04/12/26 01:00 PM`, game times, player status and
reasons. The HTTP Last-Modified is 2026-04-12 17:00:06 GMT. One report's existence
does not establish full-season or T−90 archive coverage. The old-season archive
page now contains current October 2026 links, further reason not to treat today's
page as a frozen historical roster. No injury/role feature is enabled.

Receipts preserve actual UTC request clocks, response hashes, URLs and HTTP
metadata. Player asset `updated_at=2026-09-09T05:17:36Z`; schedule asset
`updated_at=2026-09-09T05:18:08Z`. These are archive revision times, not original
feature-publication times. A checksum establishes retained-content consistency;
it does not prove upstream authenticity, permission or historical availability.
All historical use stays **RECONSTRUCTED_RESEARCH**.

## Measured budget and repeatable commands

The file read used temporary **PyArrow 23.0.1**, installed only under
`/tmp/nml-nba-audit/deps`; the application and normalizers retain standard-library
runtime dependencies. Measurements from one process: 0.327 seconds Parquet
read; 1.638 seconds conversion to Python; 0.607 seconds normalization; 0.342
seconds audit. Arrow decoded size was 23,209,406 bytes and process peak RSS
285,324 KiB. Player and schedule downloads took 0.756 and 0.680 seconds.
NBA Stats' failed request consumed its 18-second timeout; request times vary.

The bounded exploratory budget is **one season per process**, ≤40,000 player
rows, ≤2 MiB per binary asset, 20-second request timeout, at most two concurrent
future manual requests, no automatic retries, ≤60 seconds CPU and ≤512 MiB
RSS / temporary storage. Stop and record a budget/schema failure on exceedance.
This run's `/tmp` workspace, including a 149 MiB optional dependency and three
normalized copies, occupied about 203 MiB. This is a measured local bound, not a
guaranteed free production budget. No backfill, scheduler or recurring collector
is enabled. Durable permitted retention remains required before future capture.

Actual commands included:

```bash
python3 -m pip install --disable-pip-version-check --target /tmp/nml-nba-audit/deps pyarrow==23.0.1
python3 -m unittest discover -s tests -p test_nba_data.py -v
python3 -m multisport_lab.nba_data --format nba-html --input /tmp/nml-nba-audit/nba_game_page.html --season-ending-year 2026 --season-type 2
python3 -m unittest discover -s tests -v
python3 -m multisport_lab.demo
pdftotext -layout /tmp/nml-nba-audit/nba_gamebook.pdf /tmp/nml-nba-audit/nba_gamebook.txt
pdftotext -layout /tmp/nml-nba-audit/nba_historical_injury.pdf /tmp/nml-nba-audit/nba_historical_injury.txt
```

Public downloads used Python `urllib.request.urlopen` with TLS verification,
the inherited proxy, explicit 15–20 second timeouts and bounded reads. Exact
requested URLs and success/failure clocks are retained in the source receipts.
Audit calls used `pyarrow.parquet.read_table(...).to_pylist()`,
`normalize_sdv_rows(...,max_rows=40000)`, `with_sdv_schedule(...)`, and
`audit_rows(...)`. The normalizer's offline JSON/HTML CLI requires no network.

The focused parser suite passed **11 tests**. A concurrent integration snapshot
also passed **84 tests** and the synthetic demo. The integration owner reruns
and records the final suite count; these are software checks, not model evidence.

## Reproduce the local panel offline

The bounded preparation CLI uses the optional local PyArrow installation, makes
no network requests, and performs no forecast evaluation. The exact replay run was:

```bash
PYTHONPATH=/tmp/nml-nba-audit/deps python3 scripts/prepare_nba_panel.py --players /tmp/nml-nba-audit/sdv_player_box_2026.parquet --schedule /tmp/nml-nba-audit/sdv_schedule_2026.parquet --output /tmp/nml-nba-audit/reproduced_normalized.jsonl > /tmp/nml-nba-audit/reproduced_preparation_summary.json
python3 -m unittest discover -s tests -p test_prepare_nba_panel.py -v
```

The replay produced **14,720,351 bytes**, byte-identical to the original frozen
pilot input, SHA-256
`489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c`.
The original input was never overwritten or substituted. Re-running requires a
new output filename: publication is atomic and create-only. Output is restricted
to `/tmp` or this repository's ignored `.local-data`, with `web`, `output` and
`evidence` paths explicitly rejected, including symlink aliases. Compressed
inputs must be regular files of at most 2 MiB and 40,000 rows; declared/actual
decoded Arrow storage is additionally bounded at 128 MiB per asset.

Exclusive upstream exclusions total **8,238 rows**: 33 normalization rejections,
zero schedule join rejections, 73 exhibition-team rows, 2,589 outside-stage-2
rows, 5,530 DNP rows and 13 otherwise-eligible rows missing minutes/primitives.
This accounts for every source row: 26,645 retained plus 8,238 excluded equals
34,883. The order of exclusion predicates is recorded in the report; the
whole-file missing-minute count remains 24 because other stages are counted
before missingness in this cohort. Five preparation integrity tests passed
without installing PyArrow as an application/test dependency.

The retained [preparation summary](evidence/data/2026-10-19-panel_preparation_summary.json)
records both input asset hashes, counts, exclusions, output bytes and hash.

## Retention and next task

Git retains only derived audit summaries/receipts:

- [Source receipts](evidence/data/2026-10-19-source-receipts.json): URLs, actual clocks, entity hashes and failures.
- [Player audit](evidence/data/2026-10-19-sdv_audit_summary.json): counts, missingness, identities and runtime.
- [Schedule join](evidence/data/2026-10-19-sdv_schedule_join_summary.json): status, clock and competition diagnostics.
- [Primary reconciliation](evidence/data/2026-10-19-primary_reconciliation_summary.json): comparison results and source IDs, no raw boxscore copy.
- [Primary audit](evidence/data/2026-10-19-nba_primary_audit_summary.json): normalized one-game field checks.

Raw assets, HTML, PDFs and normalized rows remain outside Git under `/tmp`.
Their continued presence is not durable retention. No raw source files belong in
the Pages artifact while redistribution scope is unresolved.

For root-owned development only, `/tmp/nml-nba-audit/normalized.jsonl` has
26,645 identified complete appearances in 1,231 stage-2 standard-team final
events; it excludes missing identities/minutes, DNP and exhibition teams under
an explicit pre-evaluation preparation rule. Its SHA-256 is
`489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c`.
The full identified roster join remains separately available as
`normalized_sdv_2026_with_schedule.jsonl`; source rejections are retained locally.

The integration owner subsequently froze the exact cohort, chronological
development dates, availability reconstruction and reference settings before the
one development run; its separate record is `docs/BASELINE_REFERENCE.md` and
`evidence/research/`. The source worker performed no evaluation. Next local work
is typed research export and durable permitted capture design; this audit alone
does not admit a future operational source or prospective claim.
Confirmatory evaluation, participation modeling, complete precision/duration
resolution, future issuance/settlement evidence and source-operation permission
remain separate unresolved tasks.

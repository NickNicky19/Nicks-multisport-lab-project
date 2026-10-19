# Source capability matrix

Checked: **2026-10-19 21:14 UTC**. This is a source assessment for a new, separate multisport research project. It is not an assertion that a collector, model, current quote feed or profitable selection policy is operating.

Implementation follow-up: actual runtime row/route checks now supplement the
original assessment below in [`DATA_FEASIBILITY.md`](../DATA_FEASIBILITY.md) and
[`OFFER_INVENTORY.md`](OFFER_INVENTORY.md). These reports retain source clocks,
hashes, sample counts and failures. NBA statistical row evidence does not admit
production operation, historical as-of availability, source rights or settlement;
offer inventory does not establish a complete full-game priced contract. The
dated original observations below remain provenance, not the current handoff.

The NBA project scope is **all 13 requested categories**: points (PTS), rebounds (REB), assists (AST), points + rebounds + assists (PRA), points + rebounds (PR), rebounds + assists (RA), three-pointers made (3PM), blocked shots (BLK), steals (STL), blocks + steals (BLK+STL), turnovers (TOV), double-doubles (DD) and triple-doubles (TD). Points + assists (PA) is optional additional coverage in the market registry.

The first isolated improvement experiment is **NBA full-game rebounds (REB)**. This bounds one scientific comparison; it does **not** limit the planned NBA baseline, market-discovery or grading coverage. Inclusion in full scope does not establish that a source/forecast/settlement path is already working. The experiment protocol is maintained separately.

## Status and scope

| Sport | Planning status | Initial scope |
|---|---|---|
| NBA | research-planned-pending-row-audit | All 13 requested categories planned; REB is the first isolated improvement experiment |
| WNBA | queued | Separate basketball validation after an admission decision |
| NHL | queued | Possible skater shots-on-goal pilot; order relative to WNBA remains conditional |
| Soccer | research-only | One competition and exact statistic at a time |
| Tennis | research-only | Establish a maintained source before an operational pilot |
| CFB | research-only | Separate college-football evidence; no NFL model transfer |
| MLB | external-model-import | Import versioned outputs from Nick's existing model after contract validation |
| NFL | external-disabled | Remains with the existing NFL repository and owner/session |

**Every current multisport player-prop and two-sided-price feed remains unverified and disabled in this scaffold. All local forecasting models are untrained and unvalidated.** The existing MLB/NFL models were not reassessed here; their external performance and production status are not implied by the local flags.

## Sources and what has actually been checked

| Sport | Primary sources | Supported research use | Limits and remaining checks |
|---|---|---|---|
| NBA | [nba_api](https://github.com/swar/nba_api), [pbpstats](https://github.com/dblackrun/pbpstats), [hoopR](https://github.com/sportsdataverse/hoopR), [public player boxscores](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_nba_player_boxscores) | Historical game outcomes/minutes; lagged role and rate features; possession and lineup reconstruction. pbpstats documents NBA/WNBA support and some event-order repairs. | Documentation and release metadata checked; actual rows and intended-runner access not audited. Package software licenses do not themselves grant all upstream data rights. No current odds service established. |
| WNBA | [wehoop](https://github.com/sportsdataverse/wehoop), [player boxscores](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_wnba_player_boxscores), [WNBA Stats producer](https://github.com/sportsdataverse/wehoop-wnba-stats-data) | Player/game stats, play-by-play, shots, possessions and lineups. | Public current-season asset metadata verified; row completeness, pregame availability and operational collection still require checks. Reuse basketball infrastructure while independently training and evaluating WNBA. |
| NHL | [MoneyPuck download page](https://moneypuck.com/data.htm), [fastRhockey](https://github.com/sportsdataverse/fastRhockey) | Game-level skater/goalie/line data and historical shot events. | MoneyPuck explicitly allows noncommercial use with credit and asks approval before scraping data outside its download page. Its shot archive includes saved shots, misses and goals, and excludes blocked shots. Downloaded rows, future availability/lineup clocks and settlement definitions are not yet audited. |
| Soccer | [StatsBomb Open Data](https://github.com/hudl/open-data), [competitions file](https://github.com/hudl/open-data/blob/master/data/competitions.json), [kloppy](https://github.com/PySport/kloppy), [socceraction](https://github.com/ML-KULeuven/socceraction) | Selected competition-season events/lineups; format conversion and methods research. | Selected historical coverage does not provide all current leagues or props. kloppy and socceraction are software, not access entitlements to all supported vendors. StatsBomb requests attribution/logo when publishing derived research; inspect its included license before the intended publication. |
| Tennis | [Match Charting Project](https://github.com/JeffSackmann/tennis_MatchChartingProject), [Tennis Abstract](https://www.tennisabstract.com/) | Selected user-charted point/shot-level historical research. | [tennis_atp](https://github.com/JeffSackmann/tennis_atp) and [tennis_wta](https://github.com/JeffSackmann/tennis_wta) returned 404 through both web retrieval and GitHub connector GET. Do not treat them as working current feeds. Match Charting documents CC BY-NC-SA 4.0, attribution and noncommercial limits; it is not a comprehensive upcoming-match feed. |
| CFB | [cfbfastR](https://github.com/sportsdataverse/cfbfastR), [CFBD getting started](https://api.collegefootballdata.com/getting-started), [CFBD coverage](https://api.collegefootballdata.com/data-availability), [CFBD terms](https://collegefootballdata.com/terms) | Public-release loaders are candidates for historical play/player research. CFBD is a separate API route. | CFBD requires a key and therefore does not satisfy strict no-new-signup by default. Its terms allow model training and derived predictions but restrict raw bulk redistribution. Data family/era matters: enriched passing/rushing begins in 2025; older play-by-play is not equivalent coverage. |
| MLB | Existing Nick MLB project, [pybaseball](https://github.com/jldbc/pybaseball), [Savant CSV documentation](https://baseballsavant.mlb.com/csv-docs) | Import separately evaluated distributions; pitch/plate-appearance data can inform opportunity and efficiency research. | No new MLB model is authorized by this source file. Preserve external model/cutoff/evidence identifiers. Version measurement definitions: Savant documents a 2026 pitch-location geometry change relative to prior years. |

The [SportsDataverse status page](https://www.sportsdataverse.org/status) helps locate producers and refresh metadata. A successful workflow or newly written file is not a row-quality audit or proof of historical pregame availability.

## Concrete NBA/WNBA asset evidence

GitHub connector GETs to the following release metadata endpoints succeeded:

- [NBA release metadata](https://api.github.com/repos/sportsdataverse/sportsdataverse-data/releases/tags/espn_nba_player_boxscores)
- [WNBA release metadata](https://api.github.com/repos/sportsdataverse/sportsdataverse-data/releases/tags/espn_wnba_player_boxscores)

| Asset | Size | Asset updated_at (UTC) | SHA-256 from GitHub |
|---|---:|---|---|
| [NBA player_box_2026.parquet](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_player_boxscores/player_box_2026.parquet) | 606,444 bytes | 2026-09-09T05:17:36Z | 29a29dc9efd055a93e069a0382ac830d98a13274bee655beba69d95cff099713 |
| [WNBA player_box_2026.parquet](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_wnba_player_boxscores/player_box_2026.parquet) | 155,809 bytes | 2026-10-18T10:52:28Z | 7a8e4d3fce9a78ebfe2771bb1cc8bed665a6bb47b5c4472c804fb53b910a81a6 |

These release descriptions explicitly document direct files with no authentication or API key. Their separate data.sportsdataverse.org API requires a bearer token.

NBA season 2026 means the **2025–26 ending year**; WNBA season 2026 means its **2026 calendar year**. The listed NBA asset is historical, not evidence that 2026–27 results already exist.

Only metadata was inspected. Binary rows have not been downloaded, reconciled, graded or tested through the intended execution environment. Direct shell network reads were blocked in the assessment environment; connector/web reads succeeded. That local environment restriction is not evidence that a source is generally unavailable.

## Historical archive versus information available before a forecast

Preserve event time, source publication time when supplied, observation time, source revision/hash, feature cutoff and model version separately.

- [NBA's official 2025–26 injury-report page](https://official.nba.com/nba-injury-report-2025-26-season/) describes scheduled reporting and continual updates. An actual [2026-04-12 13:00 report PDF](https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-04-12_01_00PM.pdf) was retrieved and contains report clocks, game times and player statuses. This proves a timestamped historical example exists, not full archive coverage at every forecasting horizon.
- The inspected StatsBomb competitions JSON contained 80 competition-season entries. Older competitions have newer update clocks: for example, Champions League 2018/19 has a May 2026 match_updated value. That field cannot establish exactly what was available before a 2019 match. Dataset update time and season label answer different questions.
- CFBD's coverage page explicitly says historical data may be corrected after publication. Derived ratings and enriched features also have different era/version boundaries.
- Recompute rolling features from prior completed games; a present-day season aggregate can contain future games relative to a historical target. Preserve corrections for outcome grading without rewriting frozen forecasts.
- Actual minutes, ice time, plate appearances and eventual lineups belong to outcomes or explicitly retrospective diagnostics unless their pregame availability is proved. They must not be silently used as pregame workload inputs.

## Hugging Face: optional historical mirror

[Vladislav/nba_dataset](https://huggingface.co/datasets/Vladislav/nba_dataset) is a plausible historical mirror to inspect. Its card describes NBA/WNBA event data sourced from league APIs and pbpstats and labels its packaging Apache-2.0. It has not been admitted as a production source.

A mirror must pass source-lineage, underlying-rights, coverage, duplicate-event, row-quality and version checks. Its dataset-card license is not an independent grant from every upstream provider. Large event-row counts are not counts of independent player games, and overlapping provider representations must be reconciled. No Hugging Face model or dataset was found here that establishes a ready, accurate or profitable multisport forecasting system.

## Next source acceptance evidence

The duration/share model in NBA-REB-OPPORTUNITY-001 additionally needs verified final period count or game duration for completed prior games. This field was not verified in the inspected player-boxscore asset metadata. Its absence blocks that specific matched experiment; it does not make a duration feed a universal prerequisite for the other 12 categories or shared platform work.

Before an adapter is enabled, produce a small retained sample and report:

1. Exact public access route, permitted use, request budget and intended-runner success.
2. Event/player identity reconciliation, schema, null/duplicate counts and boxscore agreement.
3. Target definition and zero/DNP/missing distinctions; period/overtime coverage.
4. Versioned input snapshots and the historical/prospective evidence lane.
5. Current quote/settlement evidence if a priced paper claim is requested; a statistical forecast can remain a clearly labelled research forecast without odds.

Missing source evidence disables the affected adapter or claim. It does not make unrelated sports or offline experiments universal prerequisites.


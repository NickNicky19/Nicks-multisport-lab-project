# Manual selected-player outcome capture and statistical grading

`multisport_lab.prospective_outcomes` prepares the post-event half of the bounded
pregame research cycle. It does **not** issue a forecast, place or settle a ticket,
request an outcome before event start, create a scheduler, or turn an offline
readiness result into prospective evidence.

At this implementation checkpoint, all outcome examples are synthetic fixtures.
There have been **zero actual future-outcome requests, appended prospective
outcomes or prospective grades**. Actual postgame ESPN shape and outcome accuracy
must be checked when the chosen event has occurred. The historical ledger and
R0/DEV002/DEV003 receipts remain unchanged.

## Exact event, player and source path

The CLI requires the actual `research_inputs` record ID used by issued R1
forecasts and an exact ESPN NBA event ID. It recovers that input package from the
ledger, validates its original version, and selects only active
`REAL_TIME_CAPTURED` / `nba_joint_empirical_pregame_r1_v1` forecasts bound to that
same input record. Historical records and forecasts from a different capture
are excluded. A partially issued cohort is not silently called complete.

Before event start, or without an issued forecast, the command reports `PENDING`
and makes zero HTTP requests. It never accepts an observation-time, grading-time,
caller-clock, outcome-value or final-status override. After start it makes one
bounded standard-library GET, without retries, to the already inspected route:

```text
https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=<exact-event-id>
```

The response must be successful JSON within an **8 MiB** cap and a **20-second**
timeout, plus an actual **30-second** elapsed/clock latency limit. A socket
timeout alone does not establish that bound. Raw paths must resolve under `/tmp`
or this repository's `.local-data`; public/Git paths and symlinked path components
are rejected before requesting or writing source data. Raw bytes are saved
create-only by SHA256 under ignored local storage,
with a separate capture receipt containing actual retrieval-start/observed clocks,
URL, HTTP metadata, hash and byte length. Source update time remains explicitly
unknown; HTTP Date/Last-Modified are retained separately and are not promoted to
a per-event publication clock. The normalizer owns a separate actual import clock.
A checksum binds saved content but does not prove source authenticity or rights.

## Versioned normalization

`espn-nba-selected-outcomes-v1` cross-checks header/competition ID, start, season,
home/away teams and player membership against the original pregame identity.
The pregame event-version digest includes its scheduled state and is retained as
such. A final observation receives its own outcome-version digest; it is not
required to equal a digest of the earlier scheduled state. A changed start or
team identity fails closed rather than being silently treated as the issued event.

An event only qualifies as final with explicit `STATUS_FINAL`, `state=post`,
`completed=true`, an integer final period count of at least four, and consistent
team period scores when present. Other statuses remain pending, including
postponed/suspended/in-progress states. No incomplete event becomes an all-zero
outcome.

The full-game player-statistics group must contain unique explicit labels:
`MIN`, `FG`, `3PT`, `FT`, `OREB`, `DREB`, `REB`, `AST`, `TO`, `STL`, `BLK`, `PTS`.
Values are joined by those labels rather than a fixed column position. Made and
attempted fields use explicit `made-attempted` text. Scoring, field-goal,
rebound and attempt identities are audited before any append. `FG2M` derives as
`FGM-FG3M`; contradictory counts are rejected. All thirteen categories plus PA
then derive from that same primitive line in the existing ledger grader.

Whole-minute source text retains `rounded_whole_minutes`; `MM:SS` retains seconds.
No exact playing duration is invented. Overtime is included through the completed
full-game boxscore and explicit final period count. Named quarter/half/period
statistics are rejected. An unrecognized or incomplete shape remains blocked
until the actual source mapping can be reviewed; synthetic fixtures do not
establish a verified live adapter.

An appearance needs an explicit `didNotPlay=false` and a complete valid line.
An explicit `didNotPlay=true` becomes DNP with null statistics, provided supplied
placeholders do not contradict that flag. A missing selected athlete, unknown
participation flag, or absent player boxscore stays pending. Missing does not mean
DNP, and DNP does not mean a zero-stat appearance. Some verified selected subjects
may be graded while other declared subjects remain explicitly pending.

## Immutable records, retries and corrections

The operating path uses the existing `Ledger.record_outcome()` and
`Ledger.grade_forecast()` APIs. Statistical outcomes and grades persist in
`records/outcomes/` and `records/grades/`; old forecasts, probabilities, issue clocks
and original records are never replaced. The existing ledger's bounded storage,
reference validation, correction graph and recovery checks apply.

A later capture with the same statistical status and primitive outcomes reuses
the original outcome and grade records, even when unrelated response bytes or the
new capture clock changed. Its source report explicitly distinguishes the fresh
capture metadata from each retained outcome's **original** source clock/hash and
each grade's original grading clock. It does not relabel an old outcome as newly
observed. Selected normalized rows retain minutes, attempts and rebound fields;
a change to a nongrading field does not create an artificial extra score.

Changed statistical outcomes require both `--correct-outcomes` and a nonempty
`--correction-reason`. The new outcome, new statistical grade, outcome-correction
link and grade-correction link are appended separately; originals remain intact.
No silent revision, replacement timestamp or obsolete-grade double counting is
allowed. An interrupted replacement before its correction link can recover under
the explicit correction request. A retry after correction/regrading preserves
existing records and clocks. Ambiguous concurrent revisions fail for manual review.

A create-only compact source/grading report is saved in `evidence/data/` after
successful processing. `verify_report()` reads referenced records and cross-checks
exact event, selected statistical values, forecast/outcome dependencies, original
source clocks/hashes and original grade clocks/status. In particular, recovery
containing both retained and newly written outcomes preserves their individual
source clocks. A common fresh-capture clock is never substituted for them.
A fresh `Ledger` instance independently reads that saved report and its records.

These writes initially remain `LOCAL_RECEIPT_ONLY_REQUIRES_COMMIT_PUSH_READBACK`.
The integration owner must commit/push the actual derived receipts and independently
recover their exact remote bytes before claiming durable remote retention. Raw
provider responses remain outside Git/Pages unless separate rights establish
otherwise. This package does not claim that a temporary raw file is a durable
remote capture archive.

## Command after actual issuance and event start

Use the exact input record ID returned by the successful R1 issuance, not an early
preparation record or a fabricated ID:

```bash
python3 -m multisport_lab.prospective_outcomes --event 401909088 --input-record-id "$NML_ISSUED_INPUT_ID"
```

`NML_ISSUED_INPUT_ID` denotes the real saved issuance reference and must be set
from that record when it exists. This is a future operating recipe, not evidence
that the current pregame cycle has already issued or completed. The command is
safe to check while pending: it makes no source request before start or when no
forecast exists. It does not guarantee that a game will be final at its start.
Run another manual check only when an actual completed result is expected; no
recurring job is created.

For a genuinely verified changed outcome, repeat with:

```bash
python3 -m multisport_lab.prospective_outcomes --event 401909088 --input-record-id "$NML_ISSUED_INPUT_ID" --correct-outcomes --correction-reason "Describe the actual verified source correction"
```

The reason shown is explanatory text, not a verified correction or permission to
invent one. Pending events remain pending. Rebuild/publish only after the real
receipt commit and normal review workflow; browser refresh never captures or grades.

## Evidence boundaries and verification

A statistical grade measures the saved forecast distribution against the verified
player outcome. DNP remains `DNP_NOT_SCORED`; an appearance receives all fourteen
CRPS/log-loss scores and DD/TD Brier scores, including explicit zero-support loss.
This does not apply Sleeper injury insurance, sportsbook voids, entry reductions,
payouts or financial settlement. Those venue/product rules are a separate contract.
Every report retains `financial_settlement=NOT_EVALUATED` and
`qualification=UNAVAILABLE`. No product, accuracy or betting qualification follows.

Actual focused command:

```bash
python3 -m unittest discover -s tests -p test_prospective_outcomes.py -v
```

The synthetic tests cover label reordering, overtime period count, explicit
DNP/missing/unknown participation, identity/start/team/season/version conflicts,
contradictory scoring/rebounds, incomplete/period-specific data, duplicate JSON
keys, capture/import/source clocks, mocked bounded HTTP retention, raw-path and
symlink restrictions, actual capture latency, no premature
requests, exact input/lane filtering, restart/readback, retained/new source-clock
recovery, explicit corrections, interrupted correction recovery, immutable bytes
and separate financial status. No actual source outcome or model result is
created by those tests. Full-suite/demo and integration checks are reported by
the integration owner separately.

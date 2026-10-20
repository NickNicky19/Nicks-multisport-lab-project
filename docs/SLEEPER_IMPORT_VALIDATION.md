# Sleeper subject identity validation

Finding B was reproduced before editing on `main` at
`5d19fa344de5ceaa6e7cc550f0ac8ac832458202`. The integration branch was then created
from merged `main` at `e9bfa4ce7ec07b57dc5688bd592fd2e61d45f7ba`.

## Reproduced defect

The prior Sleeper parser checked sport, event, subject ID, statistic and variant
agreement but omitted `subject_type`. Four synthetic inputs each returned status
`ok`, two `sleeper:nba:player:fictional-subject` IDs and zero diagnostics:

1. The row and both options explicitly declared `subject_type: team`.
2. The row omitted its subject type while options declared `player`.
3. The row declared `player` while options omitted their subject types.
4. The row declared `player` while options declared `team`.

The existing fictional `sleeper()` test helper also omitted `subject_type`; its
passing tests therefore failed to detect this identity risk. This was a software
import validation defect, not evidence of a corrupted real capture. The retained
2026-10-19 sample independently contains `player` on all **657 NBA rows and all
1,314 options**, with no row/option type conflicts.

The pre-change reproduction used `runpy.run_path('tests/test_offer_import.py')`
to obtain the fictional constructors, applied each mutation above, then called
`import_capture(..., imported_at=IMPORTED)`. No source or network call was involved.

## Implemented behavior

Parser `nba-offer-import-0.2` validates the row's subject type and **every option's
matching subject type before constructing any player identity**. A conflict in a
later option rejects the entire row, including earlier options.

| Input | Report behavior |
| --- | --- |
| Row and all options explicitly `player` | Continue the existing identity, line/multiplier and clock checks; emit incomplete player observations only when those checks succeed. |
| Row and all options explicitly `team` | Recognized nonplayer row; increment `nonplayer_rows_ignored` and append an `ignored_rows` entry with row index, subject type, reason and hash. No player fields, observations, contracts or quotes are created. |
| Missing row subject type | Increment `subject_type_invalid_rows`; retain `missing_row_subject_type` diagnostic and row hash. |
| Missing option subject type | Increment `subject_type_invalid_rows`; retain `missing_option_subject_type`, option index and row hash. |
| Row/option subject types conflict | Increment `subject_type_invalid_rows`; retain `row_option_subject_type_mismatch`, option index and row hash. |
| Unrecognized row type | Increment `subject_type_invalid_rows`; retain `unrecognized_row_subject_type` diagnostic. It is not silently ignored as a known team. |

The counts are **rows**, not options. They remain separate from
`other_sport_rows_ignored`, category option coverage and ordinary parsing errors.
An otherwise valid complete board containing team rows only has no NBA player
observations (`empty`), with its ignored-team count and reason retained explicitly.
A missing/conflicting type is a parsing failure, not valid empty success. A board
with valid player observations and a type error is `partial`. Declared incomplete
pagination remains `partial` even without row errors.

This change does not fill period, overtime, event start, crosswalk or settlement
unknowns. Actual Sleeper-shaped rows still create no complete kernel contract or
quote. Side multipliers remain pick'em multipliers. Neither normalized records
nor parser success establishes product or forecast qualification.

## Verification

```bash
python3 -m unittest discover -s tests -p 'test_offer_import.py' -v
git diff --check
```

Actual focused result: **12 synthetic software tests passed** (eight existing,
four added). The new tests cover matching team rows/options, both conflict
directions including a conflict in a later option, missing row/option and unknown
types, and a mixed board with separately counted valid players, ignored teams and
type failures. The player fixture now explicitly declares its subject type.

A separate offline replay used the retained local
`/tmp/nml-offer-audit/sleeper_authorized_capture.json` and the new parser, with a
new actual import clock. Observed result:

```text
status=partial, observations=1314, nonplayer_rows_ignored=0,
subject_type_invalid_rows=0, diagnostics=0, contracts=0, quotes=0
```

That replay confirms compatibility with this previously captured real sample; it
does not establish current coverage, complete paging, ongoing source permission,
a prospective paper record, forecast performance or provider rules. The old
capture clock and old create-only receipt were not overwritten. The next bounded
source inspection is reported separately in `docs/OFFER_PILOT_002.md`.

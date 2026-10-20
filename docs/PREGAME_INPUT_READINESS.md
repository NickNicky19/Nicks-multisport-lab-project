# Offline NBA pregame-input readiness

`multisport_lab/nba_inputs.py` checks a locally supplied, price-independent input
snapshot. It makes no network requests, writes no ledger capture, generates no
forecast and admits no real-time producer. The current R0 issuer continues to
reject `REAL_TIME_CAPTURED`; this module does not change the forecast, publication
or ledger schemas.

Its most favorable status is **STRUCTURAL_CHECKS_PASSED_NOT_ADMITTED**. Every
report retains `future_issuance_admitted=false`, `qualification=UNAVAILABLE`, and
explicit unverified source-clock authenticity, permission and normalization
lineage. A plausible supplied capture clock or access assertion cannot prove
that a file existed before the cutoff or that its extraction was permitted.

## Minimal local snapshot contract

The strict `nba-input-readiness-v1` envelope has these exact top-level fields:

| Field | Meaning |
| --- | --- |
| `snapshot_id`, `producer_version` | Canonical decoded-JSON body SHA-256 and explicit preparation version. The snapshot ID excludes only itself. |
| `input_kind` | `SYNTHETIC_FIXTURE`, `RETAINED_ARCHIVE` or `SUPPLIED_PREGAME_ASSERTION`; never a real-time admission label. |
| `conditioning` | `CONDITIONAL_ON_APPEARANCE`; no participation probability is supplied. |
| `event` | Explicit ESPN NBA event ID/version/start, two standard team IDs, `PRE_GAME` status and source reference. |
| `cutoff_at`, `history_freeze` | Exact T90 cutoff and 00:00 UTC of the cutoff date, matching the shared history convention. |
| `coverage` | `DECLARED_SELECTED_PLAYERS`, exact requested IDs, `complete_declared_selection=true`, `full_roster_claim=false`, `participation_model_claim=false`. |
| `candidates` | Player, team, opponent, matching event ID/version/start and source reference for every selected player. |
| `sources` | Unique source IDs, original URL/local provenance, explicit source version, raw SHA-256, supplied observed clock, upstream update clock or null, and structured access-basis assertion. |
| `history` | Bounded prior `NBAPlayerGame.to_record()` appearances, each bound to a source reference. |

Clock fields in the snapshot use six-digit microsecond UTC `Z` timestamps.
The CLI owns a separate actual `imported_at`; it has no backdating flag.
Source observations remain supplied assertions and are never changed to equal
import time or historical event time.

`event` fields are `id_namespace`, `league`, `event_id`, `event_version`,
`event_starts_at`, `home_team_id`, `away_team_id`, `status`, `source_ref`.
Each candidate has `player_id`, `team_id`, `opponent_id`, `event_id`,
`event_version`, `event_starts_at`, `source_ref`. Coverage also contains the
`requested_player_ids` list. Each source has `source_id`, `source_url`,
`source_version`, `raw_sha256`, `observed_at`, `source_updated_at`, `access_basis`.
An access assertion has `kind` (`USER_PROVIDED_FILE`, `AUTHORIZED_LOCAL_FILE` or
`SYNTHETIC_TEST_FILE`), `operation=LOCAL_RESEARCH_IMPORT` and a nonempty
`reference`. Synthetic source files require the synthetic input kind. Public URL
access alone is not a supported permission assertion. None grants automation or
redistribution rights. History items have `source_ref` and `row` only.

Selected-player coverage deliberately differs from a complete roster. A supplied
selection can be structurally complete without containing every roster player.
Eventual appearance lists, final starting lineups and postgame roster fields are
not admitted as pregame coverage. This validator cannot independently authenticate
the declared selection; provenance and source-operation review remain open.

## Checks and bounds

The validator rejects unknown schemas/keys, checksum conflicts, duplicate sources,
players or history identities, mismatched candidate event/version/start or teams,
unknown source references and foreign namespaces. It compares every supplied
source file's actual hash to its declared raw hash. That binds bytes, not parser
meaning or source authenticity.

The event must still be upcoming at actual local import. Schedule and candidate
source observations must be at or before T90 and no later than actual import;
known source updates cannot exceed observation. Prior history observations must
follow their event start and be at or before the midnight history freeze. Target,
same-freeze-date and future events cannot enter history. Duplicate revisions are
not automatically selected or combined. Final appearance, minutes/precision and
all count fields are required; the common validator/audit checks field-goal,
scoring, rebound and made/attempt identities. Missing counts are not zeros.

Budgets are **8 MiB metadata, 20,000 prior rows, 1,000 selected candidates,
1,000 source references and 64 MiB aggregate local source bytes**. Files must be
regular files, with symlink inputs rejected. There are no paid dependencies,
accounts, keys, collectors, schedules or retry loops.

These are bounded readiness-pilot limits, not a universal ceiling on valid NBA
history. In particular, the 20,000-row / 8 MiB contract does not provide complete
coverage of the existing 26,645-row R0 panel. A future producer must declare and
version its actual history cohort and resource budget; this diagnostic does not
authorize silently truncating an otherwise required history to make it pass.

Run against an authorized supplied file, mapping every declared source exactly:

```bash
python3 -m multisport_lab.nba_inputs check .local-data/inputs/snapshot.json --source schedule=.local-data/inputs/schedule.json --source history=.local-data/inputs/history.json
```

This is an interface example, not evidence that those files or a permitted
pregame source currently exist. Reports go to stdout and do not create ledger
records. Malformed CLI input exits with an error; a structural `BLOCKED` report
is printed and `check` exits with status one. A zero exit from structural checks
still means **NOT_ADMITTED**. The separate archive diagnostic reports its future
blockers without treating a completed diagnostic as a failed command.

## Actual retained-archive diagnostic

The actual command run without any source request was:

```bash
python3 -m multisport_lab.nba_inputs archive-diagnostic --panel /tmp/nml-nba-audit/normalized.jsonl --source-receipts evidence/data/2026-10-19-source-receipts.json
python3 -m unittest discover -s tests -p test_nba_inputs.py -v
```

The initial [diagnostic](../evidence/data/2026-10-20-input-readiness.json), produced
at **2026-10-20T01:05:50.879136Z**, is preserved unchanged. A scoped v2
[diagnostic](../evidence/data/2026-10-20-input-readiness-v2.json) clarifies its
meaning without changing the input or claiming a new capture. The retained
panel's whole-file hash is still
`489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c`,
14,720,351 bytes / 26,645 lines. Detailed missing-field inspection is explicitly
limited to its **first 20,000 rows**, not presented as a new full-panel audit.
That prefix has zero per-row observed clocks, source-version bindings, event
versions or pregame candidate-universe evidence. The complete file also exceeds
this new snapshot's prior-row bound.

Retained receipts say the actual player/schedule archive fetches occurred
2026-10-19 at 22:53:58.496791 UTC and 22:58:04.960091 UTC, later than the inspected
historical event cutoffs. Their asset update clocks remain separate
`source_updated_at` fields. No explicit producer `source_version` exists in those
receipts, so the diagnostic preserves it as null; asset IDs and hashes remain
available without promoting an update time to a version or as-of clock.

The v2 status is **ARCHIVE_ALONE_NOT_ADMITTED_AS_PROSPECTIVE_BUNDLE**: this archive
alone does not supply the pregame universe, event/version/capture references or
an admitted future producer. Its past statistics are **not inherently invalid
future-forecast inputs**. For a later event, their actual October 19 observation
clocks may precede that event's freeze/cutoff. That eligibility needs a separately
bound event-specific timing and history-coverage audit; this diagnostic records
`future_event_history_timing_audit.status=NOT_EVALUATED`, with no chosen future
event or cutoff, rather than asserting a blanket future-history timing failure.

The known fetches after **historical** cutoffs prevent using these receipts as
proof of availability before those historical games. That limitation does not
prohibit using the same retained past outcomes for a later event. The diagnostic
remains `RECONSTRUCTED_RESEARCH`; future issuance and producer admission are
separate. Earlier independent whole-panel inventory found all
26,645 appearance rows (1,231 events) historical; that separate result does not expand
this diagnostic's 20,000-row inspection claim.

No old receipt, historical input, forecast, protocol, score, publication asset or
model admission was changed. The next resolvable requirement is an independently
reviewed permitted event/player/history producer with retained source evidence
available at the declared cutoff. Actual future issuance and its horizon and
participation evaluation are subsequent distinct requirements.

The separate retained-source [pregame discovery audit](../evidence/data/2026-10-20-pregame-discovery.json)
contains three future events as actually observed October 19. The earliest
observed start was October 20 at 19:00 UTC, with T90 at 17:30 UTC. Those older
observations require fresh event/player/source revalidation before the relevant
decision window; the discovery record does not establish their current status or
a complete selected-player universe. No scheduler or future issuance is enabled.

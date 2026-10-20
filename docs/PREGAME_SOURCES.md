# Selected-player prospective input source pack

`multisport_lab/pregame_sources.py` implements `nba-pregame-sourcepack-v1`, a
separate versioned normalizer for the bounded manual research operation requested
in this session. It does not make the older `nba_inputs` structural diagnostic a
prospective issuer. It does not authorize a recurring collector, assert upstream
authenticity or grant raw redistribution rights.

The current pack binds the two existing ESPN event routes (scoreboard and summary)
to the same explicit NBA event ID, competition ID, league, season, status, valid
start and home/away teams. Normalized event identity/start/status fields determine
the SHA256 event version. Team roster responses must match the event's teams and
season. Selected athletes need numeric ESPN IDs, names and an explicit roster
`status.type=active`; a contradictory supplied athlete team or `active=false`
fails. Roster status is not verified participation, starting status or workload.

The rule was declared before forecasts or target outcomes were examined: the two
lowest numeric active athlete IDs on each event team. The initial declaration
also requested an `active=true` field, which the actual roster response omits.
A separate amendment accepted the explicit status field before selection or
scoring. The fixed cohort is now:

| ESPN player | Source label | Team | Opponent |
| --- | --- | --- | --- |
| 2596112 | Javonte Green | 8 (Detroit) | 2 (Boston) |
| 2990962 | Taurean Prince | 8 (Detroit) | 2 (Boston) |
| 3195 | Mike Conley | 2 (Boston) | 8 (Detroit) |
| 4251 | Paul George | 2 (Boston) | 8 (Detroit) |

Four additional bounded ESPN core athlete-profile reads cross-checked all four
IDs, names, active statuses and exact 2027 season team references. Both routes
are ESPN observations, not independent upstream providers. Future refreshes must
retain the same selected IDs/labels/team assignments and active status, or block;
they cannot silently select replacement athletes based on model output or outcome.
Complete coverage means all four selected players, not an all-league roster.

The event was revalidated as `401909088`, scheduled/pre and noncompleted, Detroit
home versus Boston away, on **October 20, 2026 at 2:00 PM CDT (19:00 UTC)**. This
is the source-reported current event, including potentially surprising roster
assignments; it is not corrected using familiarity with past seasons. Exact
captures and source update uncertainties are recorded in
`evidence/data/2026-10-20-pregame-cycle-verification.json`.

## Clocks, bytes and operating limits

Primary source observations completed October 19 at 8:51:42.675230–8:51:55.889290 PM
CDT (October 20, 01:51 UTC). Every response's actual request start, response
completion/observation, raw-body byte count and SHA256 are retained separately.
HTTP Date is not an event update. Per-event/player update clocks remain null;
the roster's response `timestamp` is retained in a separate field with unverified
upstream semantics. The source pack's actual `imported_at` comes from normalization,
and never replaces either source clock. No clock argument permits backdating.

The source operation is four manual HTTP requests, at most 30 seconds and 2 MiB
per response, with no retry loop or schedule. Initial source inspection and the
four secondary identity checks total eight actual requests. Raw bodies are saved
create-only under ignored `.local-data` (or `/tmp`); they are not Pages assets.
Compact derived inputs and source evidence can be persisted separately through
the repository ledger. A hash binds bytes, not source authenticity or permission.

History uses the complete frozen 26,645-appearance / 1,231-event panel. The
versioned path re-reads the original 606,444-byte player and 525,802-byte schedule
Parquets, checks their original receipts, applies the existing preparation rules,
and reproduces all **14,720,351 original normalized bytes**, SHA256
`489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c`.
No 20,000-row truncation occurs. The new operational limit is the existing full
panel importer's **64 MiB / 100,000 rows**, independent of the old readiness pilot.
Optional PyArrow is used only by explicit offline rebuilding of retained Parquets.

Lossless event/player dictionaries and array columns retain every normalized
NBA count, identity, minute value/precision, status and final-period value in
**1,636,253 canonical JSON bytes**. Reconstruction produces the exact original
ordered normalized JSONL bytes; a changed field, count arithmetic, source binding,
source clock or dictionary identity fails. A source pack fits the existing 4 MiB
per-ledger-record limit. Recovery needs no source network request or model run.
Original upstream exclusions remain recorded. The latest retained event starts
April 13, 2026; there are no 2026–27 appearances or current-role/minutes claims.
Historical completion bounds remain reconstructed even when old source captures
precede the new future event's daily history freeze.

## Manual refresh and readback

The normalizer API is `normalize_event`, `normalize_roster`, `freeze_selection`,
`verify_selection`, `rebuild_history`, `make_pack`, `validate_pack`, `load_pack`,
`history_from_input_record`, `binding_view`, `sourcepack_digest` and
`unpack_history`. The small binding view
exposes current event/candidates, selection and pack hashes, actual current source
clock range, history source observation clock, history count/latest event and import
clock without conflating old history observations and current event captures.

For this fixed event, capture observations must complete **October 20 between
12:20 and 12:30 PM CDT (17:20–17:30 UTC)**. The separate prospective producer
allows issuance only **12:30–12:35 PM CDT (17:30–17:35 UTC)**, with its documented
generation budget. Initial preparation was far earlier and is not timely capture
or genuine issuance. The refresh command is explicit and unscheduled:

After committing/pushing the preparation input record, use its exact
`research_inputs` record ID from the handoff. This route independently reads the
bounded original receipt and complete `LedgerRef`, validates it through
`Ledger.read`, and recovers all 26,645 normalized rows plus their original
source/observation/update metadata. It needs no retained `/tmp` files, PyArrow,
Parquets or old raw responses. Recovery performs no HTTP or model operation;
only the subsequent four explicit event/roster requests are fresh captures.
The record ID is an original ledger identity, not a source-pack content hash:

```bash
python3 -m multisport_lab.pregame_sources capture \
  --event 401909088 --date 20261020 \
  --selection evidence/data/2026-10-20-pregame-cycle-cohort.json \
  --history-input-record-id RESEARCH_INPUT_RECORD_ID_FROM_HANDOFF \
  --raw-directory .local-data/pregame-cycle/t90 \
  --output .local-data/pregame-cycle/t90-sourcepack.json
```

Alternatively, explicitly rebuilding from the original retained source assets
uses all four raw-history arguments together:

```bash
PYTHONPATH=/tmp/nml-nba-audit/deps:. python3 -m multisport_lab.pregame_sources capture \
  --event 401909088 --date 20261020 \
  --selection evidence/data/2026-10-20-pregame-cycle-cohort.json \
  --history-panel /tmp/nml-nba-audit/normalized.jsonl \
  --players /tmp/nml-nba-audit/sdv_player_box_2026.parquet \
  --schedule /tmp/nml-nba-audit/sdv_schedule_2026.parquet \
  --source-receipts evidence/data/2026-10-19-source-receipts.json \
  --raw-directory .local-data/pregame-cycle/t90 \
  --output .local-data/pregame-cycle/t90-sourcepack.json
python3 -m multisport_lab.pregame_sources check .local-data/pregame-cycle/t90-sourcepack.json
python3 -m unittest discover -s tests -p test_pregame_sources.py -v
```

The two history routes are mutually exclusive. Missing, corrupt, symlinked,
wrong-kind or mismatched ledger evidence fails before source capture. The capture
command recovers or rebuilds/validates history before the bounded source reads.
Allow enough time for reads to finish by the cutoff. `check` reads the original
pack and recovers its full history; it never refreshes timestamps or establishes
that an issuance window was met. The separate prospective command rejects stale,
late, early, revised-event or changed-selection inputs. Until genuine issuance
and verified outcomes occur, there is no new forecast score, ticket settlement,
qualified probability or betting recommendation.

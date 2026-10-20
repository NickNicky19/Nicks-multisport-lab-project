# Bounded pregame research cycle R1

This is a separately versioned operating path, not a change to frozen R0,
DEV002 or DEV003. `nba_joint_empirical_pregame_r1_v1` uses the unchanged R0
complete-line empirical formula with current, observed event/player inputs.
Every player has all 13 requested categories plus PA, conditional on appearance.
Finite support, stale history, no participation model and no cross-player joint
law remain explicit. Qualification is unavailable. Prices and venue contracts
are not prerequisites for statistical forecasts or statistical grading.

The fixed pilot is ESPN NBA event401909088, observed as Detroit8 versus Boston2,
starting2026-10-20T19:00:00Z. Its normalized event version is
`10579839a07f7b146eb82e9f9cd905bdc6d68198f396ff5fd0670a16410466b7`.
The deterministic cohort is two lowest numeric ESPN IDs whose current roster
status.type is active on each team. The source schema lacks a separate active
boolean; that documented pre-forecast amendment does not imply participation.
Selected IDs: Detroit2596112 Javonte Green and2990962 Taurean Prince;
Boston3195 Mike Conley and4251 Paul George. All four were cross-checked against
actual secondary ESPN athlete profiles. Source facts are retained observations,
not signatures or independent certification of upstream truth.

The cohort receipt is `evidence/data/2026-10-20-pregame-cycle-cohort.json`.
Selection SHA256:
`8dd4a0c284e97abd92ccb2e9094e4eb50994ab7bad6ae18a50d0d27aeb4db17a`.
The issuer pins both selection and normalized event version. A transfer,
inactive/missing selected player, changed name, changed event teams/start/status
or changed event version blocks this cycle. There is no silent reselection or
rescheduling. A substantive new cycle requires a versioned policy decision.

## Actual clocks and operating window

The event and both current team rosters are freshly read through four bounded
manual ESPN requests. Each request must finish within30 seconds. Observation is
the actual response-completion clock; upstream source update remains null when
unknown. A root response timestamp is retained separately with unknown meaning,
not relabeled as an upstream update. HTTP headers do not prove source freshness.
Source versions/hashes, normalization import and actual generation remain distinct.

The target cutoff is T90; history freezes at00:00 UTC of that cutoff date.
Event/player observations and normalization import must finish in
`[cutoff-10 minutes, cutoff]`; the input ledger receipt must also exist by cutoff.
Generation starts at or after cutoff, completes within120 seconds, and its actual
completion is issued_at. Verification and original forecast receipt must finish
by cutoff+5 minutes. CLI code has no backdating/time-override argument. All clocks
use microsecond UTC. Passing the old offline readiness validator admits nothing.

For the current observed schedule, capture is **October20 12:20–12:30p.m.
America/Chicago** (17:20–17:30UTC), followed by issuance **12:30–12:35p.m.**
(17:30–17:35UTC). Do not wait or schedule collection in this session. Earlier
preparation observations cannot be relabeled as captures from that window.
Revalidate the event at capture; a conflict blocks issuance under the fixed policy.

## History and retention budget

Use the entire existing26,645-row/1,231-game retained normalized panel, SHA256
`489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c`.
The versioned source normalizer rebuilds it from the actual original player and
schedule Parquets and requires exact14,720,351-byte equality. It preserves every
primitive count, identity, minutes/precision and final-period field. A lossless
1,636,253-byte dictionary/array representation retains all normalized model inputs
within the existing4MiB record and32MiB/512-record ledger budget. The20,000-row
readiness pilot is neither reused as a limit nor silently substituted.

The source Parquets and raw current ESPN responses remain outside Git/Pages.
One explicitly bounded compact derived research-input record is retained in Git;
it discloses all normalized historical statistics in the public repository and
is not included in Pages assets. The publisher's observed CC BY 4.0 release-store
label, exact scope/remaining uncertainty, source attribution and modification
notice are recorded in [HISTORY_RETENTION.md](HISTORY_RETENTION.md). This is a
bounded retention decision, not blanket upstream ESPN clearance.
Original source URLs/hash/observation/
update/version references remain bound to it. This storage choice satisfies
original-input restart recovery without creating a bulk source collector or
claiming a raw-source redistribution grant. No general source rights or scheduled
extraction permission is established. The user's authorized bounded research
operation does not authorize broader reuse or recurring collection.

Historical event starts and completion bounds remain reconstructed. Their archive
observations were actually retained October19 before this future event's freeze;
those actual observations, rather than a backfilled historical capture, permit
use for this later event. Latest history starts April13,2026; no2026–27 completed
appearances or current role/minute/injury features are supplied. Long staleness is
a material forecast limitation, not silently filled using future information.

## Manual commands and recovery

Run from this repository with the existing optional PyArrow directory for the
source normalization command. The commands make no paid-service/API-key request.
Use a new create-only output filename for every capture attempt.

During the capture window:

```bash
PYTHONPATH=/tmp/nml-nba-audit/deps python3 -m multisport_lab.pregame_sources capture \
  --event 401909088 --date 20261020 \
  --selection evidence/data/2026-10-20-pregame-cycle-cohort.json \
  --history-panel /tmp/nml-nba-audit/normalized.jsonl \
  --players /tmp/nml-nba-audit/sdv_player_box_2026.parquet \
  --schedule /tmp/nml-nba-audit/sdv_schedule_2026.parquet \
  --source-receipts evidence/data/2026-10-19-source-receipts.json \
  --raw-directory .local-data/pregame-cycle/t90 \
  --output .local-data/pregame-cycle/t90-sourcepack.json
python3 -m multisport_lab.prospective persist --pack .local-data/pregame-cycle/t90-sourcepack.json
```

The persist command returns the exact research_inputs record ID. At or after
T90, still within the five-minute issuance window:

```bash
python3 -m multisport_lab.prospective issue \
  --input-record-id <ID returned by persist> --model-commit "$(git rev-parse HEAD)"
```

The full model commit must contain the exact executed producer, normalizer,
ledger, probability/count/integrity dependencies and historical-panel preparation
source. Uncommitted/different model code fails. The operating wrapper does not
claim that the R0 model itself is newly trained, calibrated or promoted.

Records are create-only and idempotent. After interruption, already issued cohort
subjects recover unchanged; only missing subjects may generate while still timely.
A partial cohort is never reported complete. Readback after the event recovers
original inputs/probabilities/clocks without rerunning the model or needing the
large source Parquets. Direct generic append cannot create a new prospective
forecast from a self-supplied attestation. The consistency attestation is not a
cryptographic signature or upstream authenticity proof.

Local writes still require commit/push and independent remote byte/readback
verification. Commit the exact new records, normally push, and complete the
existing PR workflow; publication consumes retained records and performs no live
capture/model rebuild. Use the independently reviewed, committed producer for
actual issuance. Publishing a changed main site follows the existing per-PR
exact-head landing authorization; an open PR is not a deployed site. If timely
capture or issuance fails, report no issuance and do not backdate it.

The website distinguishes future captured records from historical reconstruction,
shows explicit generation/capture/history dates, and keeps missing grades pending.
Passing the event-start clock moves a captured record to History without implying
completion. Performance groups by lane and exact model. Verified outcomes and
statistical grades are appended later through the separate manual grading path;
financial settlement and qualified tickets remain unavailable.

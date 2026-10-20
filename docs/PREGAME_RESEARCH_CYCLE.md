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
ESPN requests. Each request must finish within30 seconds. Observation is
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
(17:30–17:35UTC). The later explicit user authorization permits ONE unattended
October 20 pilot; see [the one-shot operating plan](SCHEDULED_PILOT.md). This
exception does not authorize a recurring collector or another cycle. Earlier
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

## Frozen producer and cycle metadata

The reviewed producer for this cycle is **exactly**
`58530309cf384425e15f02fd9fa980899a4dc0bc`. Never derive `--model-commit` from
HEAD. Committing input/forecast records, a handoff or a publication artifact can
move HEAD without changing the executed model. All retries and readback retain
this producer SHA and the **same fresh input record ID**.

The create-only plan is
`evidence/cycles/2026-10-20-nba-401909088-plan.json` (payload SHA256
`22ae8db607374486ebee6eb569d236a3d27aedc8535c3085a6b6858226921908`).
It freezes the producer, its nine checked source hashes, event/version, selected
IDs/selection hash, capture/issuance bounds, history-only preparation reference
and all 19 original record hashes. Its actual preparation clock does not claim
capture or issuance. A later create-only binding at
`evidence/cycles/nba-20261020-401909088-t90-r1-binding.json` retains the exact plan
hash, producer SHA, complete fresh input LedgerRef and actual binding clock.
No fresh input binding exists yet. The plan is metadata, not a forecast.

`multisport_lab.manual_cycle` is a bounded operating guard outside the reviewed
producer's `MODEL_FILES`; the producer and ledger bytes remain unchanged. It
verifies those executed bytes against the pinned Git commit and plan. Before
calling the reviewed `issue_cohort`, it checks all original forecasts for this
cycle, across model revisions and input IDs. A different model/input, duplicate
original or changed subject blocks recovery instead of creating another original
cohort. The direct reviewed `prospective issue` command alone does not have this
cross-model guard: **use the guarded command below for this cycle**. Direct API
hardening remains a separately versioned follow-up with the changed-model
regression case; it must not silently change this reviewed producer's identity.

## Local preflight — safe outside the execution window

Run from this repository; keep newer legitimate work. These commands perform no
source capture, model issuance, outcome capture or grading:

```bash
cd /workspace/Nicks-multisport-lab-project
git status --short --branch
python3 -m multisport_lab.manual_cycle preflight \
  --plan evidence/cycles/2026-10-20-nba-401909088-plan.json
python3 -m multisport_lab.manual_cycle recover \
  --plan evidence/cycles/2026-10-20-nba-401909088-plan.json
```

A shallow checkout must first fetch the two exact provenance objects; this is
GitHub repository history, not a provider capture or a branch reset:

```bash
git fetch --no-tags --depth=1 origin \
  58530309cf384425e15f02fd9fa980899a4dc0bc \
  c19bcd67d4fefe7f818fed569c683db9cc5ab9fc
```

The existing Actions workflow performs the same bounded fetch before testing.

Preflight validates the retained full-history record and all original receipts;
its phase is diagnostic, never timely-capture admission. `recover` only reads
records, reports original issue/receipt clocks, selected/missing subjects and
partial/complete state. It can be run after the window or event without generating
anything. Check the actual local UTC clock before any operating command. The
one-shot GitHub Actions worker is the sole live writer when armed or claimed.
Do not run the manual capture/issue commands in parallel. Manual takeover requires
cancelling/disarming the workflow, confirming no queued/in-progress worker and
recovering the same remote branch, input and originals first. A disabled workflow
can still have its original job running; do not infer an idle writer from that
flag alone. After a scheduled claim/intent, standalone `manual_cycle recover`
is diagnostic only and cannot clear ambiguous intents. Any live continuation must
use the intent-aware scheduled runner under its original claim; do not invoke the
standalone manual issue command to fill a subject whose original may have been
lost. Ambiguous capture/generation remains blocked. Read-only recovery remains
allowed. The worker's short phase waits
are limited to this explicitly authorized run; no general collector is installed.

## Capture and input persistence — October 20, 12:20–12:30 p.m. CDT

The early preparation ID
`dfa1c4345495eb3aa6b203f2e8309c89c112b6b78a36cd3d2c603d390776b6fc`
is used **only** by `--history-input-record-id`. It recovers all 26,645 original
normalized rows with their original clocks, without `/tmp` Parquets or PyArrow.
It must never be supplied as the issuance input ID. Capture makes four actual
current event/roster requests and revalidates the exact selected event/version,
teams, player IDs/labels and active statuses. Changed source facts block this
cycle; do not alter the plan, swap players or silently change the event.

During the capture window only, in a shell that stops on an error:

```bash
set -eu
python3 -m multisport_lab.manual_cycle preflight \
  --plan evidence/cycles/2026-10-20-nba-401909088-plan.json --require-capture-window
test ! -e .local-data/pregame-cycle/t90-sourcepack.json
test ! -L .local-data/pregame-cycle/t90-sourcepack.json
test ! -e .local-data/pregame-cycle/t90-persist-report.json
test ! -L .local-data/pregame-cycle/t90-persist-report.json
set -C
python3 -m multisport_lab.pregame_sources capture \
  --event 401909088 --date 20261020 \
  --selection evidence/data/2026-10-20-pregame-cycle-cohort.json \
  --history-input-record-id dfa1c4345495eb3aa6b203f2e8309c89c112b6b78a36cd3d2c603d390776b6fc \
  --raw-directory .local-data/pregame-cycle/t90 \
  --output .local-data/pregame-cycle/t90-sourcepack.json
python3 -m multisport_lab.prospective persist \
  --pack .local-data/pregame-cycle/t90-sourcepack.json \
  > .local-data/pregame-cycle/t90-persist-report.json
NML_FRESH_INPUT_ID="$(python3 -c 'import json; print(json.load(open(".local-data/pregame-cycle/t90-persist-report.json"))["input_reference"]["record_id"])')"
python3 -m multisport_lab.manual_cycle bind \
  --plan evidence/cycles/2026-10-20-nba-401909088-plan.json \
  --input-record-id "$NML_FRESH_INPUT_ID"
```

All response observations, normalization, actual ledger persistence and binding
must finish by **17:30 UTC**. Allow time for four at-most-30-second source reads,
normalization and persistence; starting a request before cutoff is insufficient.
The output prechecks and shell noclobber prevent accidental overwriting/redundant
requests on a copied capture block. If persistence finished but stdout was lost,
recover its ID without another request or append, then bind it while still timely:

```bash
set -eu
NML_FRESH_INPUT_ID="$(python3 - <<'PY_ID'
from multisport_lab.integrity import digest, read_receipt
from multisport_lab.ledger import Ledger, LedgerRef
from multisport_lab.pregame_sources import load_pack
pack = load_pack('.local-data/pregame-cycle/t90-sourcepack.json')
record_id = digest({'kind': 'research_inputs', 'logical_id': 'research-inputs:'+digest(pack)})
store = Ledger()
payload = read_receipt(store._path('research_inputs', record_id), max_bytes=4*1024*1024)
ref = LedgerRef('research_inputs', record_id, digest(payload))
assert store.read(ref)['data']['source_pack'] == pack
print(record_id)
PY_ID
)"
python3 -m multisport_lab.manual_cycle bind \
  --plan evidence/cycles/2026-10-20-nba-401909088-plan.json \
  --input-record-id "$NML_FRESH_INPUT_ID"
```

The report file and shell variable are conveniences: the original input receipt
and create-only cycle binding are the authoritative records and must be committed
and pushed. A retry reads the existing binding and input; it does not recapture.

If capture was interrupted before any binding, inspect the actual partial state.
A further explicit capture attempt may use a new create-only raw/output path only
while capture is still timely, before any subject was issued. Keep failed evidence
and actual failure clocks. Once bound, do not replace the fresh input. If the
capture/persistence window is missed, report failure; do not issue from the early
pack or shift/backdate a clock. `persist` alone can store an early research pack;
only successful guard validation/binding admits that pack for this cycle.

## Issuance and interrupted recovery — 12:30–12:35 p.m. CDT

In any restarted shell, recover the same fresh ID from the create-only binding:

```bash
set -eu
NML_FRESH_INPUT_ID="$(python3 -c 'from multisport_lab.integrity import read_receipt; print(read_receipt("evidence/cycles/nba-20261020-401909088-t90-r1-binding.json")["input_reference"]["record_id"])')"
python3 -m multisport_lab.manual_cycle issue \
  --plan evidence/cycles/2026-10-20-nba-401909088-plan.json \
  --input-record-id "$NML_FRESH_INPUT_ID" \
  --model-commit 58530309cf384425e15f02fd9fa980899a4dc0bc
python3 -m multisport_lab.manual_cycle recover \
  --plan evidence/cycles/2026-10-20-nba-401909088-plan.json
```

Use one operator process at a time; do not run capture/issuance or retries in
parallel. Run issuance only at/after **17:30 UTC**. Generation must complete within
120 seconds per subject; verification and original forecast persistence must
finish by **17:35 UTC**. The guard passes the fixed SHA to the unchanged reviewed
producer, which enforces actual clocks. The four selected subjects each retain
all 13 categories plus PA from coherent shared stat outcomes.

On failure or interruption, run `recover` even if the issuance shell stopped.
It must report the actual partial count/missing IDs. Repeat the same guarded
`issue` command with the original SHA/input only while timely. Already-issued
subjects recover byte-for-byte; only missing subjects may generate. If all are
already present, a late retry may read them; if any remain missing after the
window, preserve and publish the partial state without generating replacements.
Never use a later HEAD as a new model identity to "recover" the same cycle.

## Commit, push and independent remote recovery

Use one ordinary records branch derived from the preparation branch. Do not reset
newer work. Even a partial/failure checkpoint should retain its actual new input,
binding and any originals. Inspect/stage exact new receipt paths; never stage raw
responses, `.local-data`, all of `evidence/`, or unrelated changes indiscriminately.
Refresh the manifest using only its tracked existing entries and the selected
new tracked evidence/record paths. Run the repository's software checks and
artifact smoke check before publication; none of them performs actual capture.

For a successful or accurately partial issuance checkpoint:

```bash
set -eu
# First creation only; on retry retain/switch to the existing branch.
git switch -c records/nba-20261020-401909088-t90
# First update HANDOFF_STATUS.md with actual clocks/counts/partial state.
git status --short
python3 - <<'PY_STAGE'
import subprocess
from pathlib import Path
from multisport_lab.manual_cycle import recover
report = recover()
assert report['input_reference'] is not None, 'No bound input: document the failure manually'
paths = [f"records/research_inputs/{report['input_reference']['record_id']}.json",
         'evidence/cycles/nba-20261020-401909088-t90-r1-binding.json', 'HANDOFF_STATUS.md']
paths += [f"records/forecasts/{item['reference']['record_id']}.json"
          for item in report['forecast_records'].values()]
assert all(Path(name).is_file() for name in paths)
print('Stage only these inspected paths:', *paths, sep='\n')
subprocess.run(['git', 'add', '--', *paths], check=True)
PY_STAGE
python3 - <<'PY_MANIFEST'
import hashlib, subprocess
from pathlib import Path
names = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
paths = sorted(name for name in names if name and name != 'MANIFEST.sha256')
Path('MANIFEST.sha256').write_text(''.join(
    hashlib.sha256(Path(name).read_bytes()).hexdigest()+'  '+name+'\n' for name in paths))
PY_MANIFEST
sha256sum --check --quiet MANIFEST.sha256
git add -- MANIFEST.sha256
git diff --cached --stat
git diff --cached --check
git commit -m 'Record actual manual NBA pregame pilot state'
NML_RECORD_BRANCH="$(git branch --show-current)"
NML_RECORD_COMMIT="$(git rev-parse HEAD)"
printf 'Records checkpoint: %s\n' "$NML_RECORD_COMMIT"
git push -u origin "$NML_RECORD_BRANCH"
```

If that records branch already exists, retain it and skip branch creation; do not
replace or reset it. Retain the printed full `NML_RECORD_COMMIT` for this checkpoint
if the shell restarts; do not silently replace it with a later HEAD.

That commit is a **records revision**, not a replacement producer revision.
Retries still use the pinned `58530309...` and binding's exact input ID.
Independently fetch the same remote project into a fresh readback directory:

```bash
set -eu
NML_RECOVERY_DIR="$(mktemp -d /tmp/nml-pregame-readback.XXXXXX)"
git clone --single-branch --branch "$NML_RECORD_BRANCH" \
  https://github.com/NickNicky19/Nicks-multisport-lab-project.git "$NML_RECOVERY_DIR"
test "$(git -C "$NML_RECOVERY_DIR" rev-parse HEAD)" = "$NML_RECORD_COMMIT"
(cd "$NML_RECOVERY_DIR" && \
  python3 -m multisport_lab.manual_cycle recover \
    --plan evidence/cycles/2026-10-20-nba-401909088-plan.json)
python3 - "$NML_RECORD_COMMIT" "$NML_RECOVERY_DIR" <<'PY_REMOTE'
import hashlib, subprocess, sys
from pathlib import Path
commit, remote = sys.argv[1], Path(sys.argv[2])
for directory in ('records', 'evidence/cycles'):
    names = subprocess.check_output(
        ['git', 'ls-tree', '-r', '--name-only', commit, '--', directory], text=True).splitlines()
    paths = sorted(name for name in names if name.endswith('.json'))
    recovered = sorted(str(p.relative_to(remote)) for p in (remote/directory).glob('**/*.json'))
    assert paths == recovered, 'Remote checkpoint inventory differs'
    for name in paths:
        expected = subprocess.check_output(['git', 'show', f'{commit}:{name}'])
        assert expected == (remote/name).read_bytes(), name
        print(hashlib.sha256(expected).hexdigest(), name)
print('Exact committed remote record/metadata bytes recovered; no generation performed.')
PY_REMOTE
```

If the remote advanced, investigate and preserve that revision; do not reset it.
Record the actual remote revision, original forecast/input refs/clocks, byte
comparisons and readback time in the handoff/evidence and push that documentation
normally. Readback is a fresh process with no source requests, forecasts or
probability regeneration. Local/browser/temp files alone do not establish remote
durability; a normal push plus independent remote receipt validation is required.

## Publication — separate from issuance

After the records commit and independent recovery:

```bash
set -eu
python3 -m unittest discover -s tests -v
python3 -m multisport_lab.demo
node --test --test-isolation=none web/tests/*.test.mjs
python3 -m multisport_lab.publication --build-commit "$(git rev-parse HEAD)"
node web/tests/site-smoke.mjs output
gh pr create --repo NickNicky19/Nicks-multisport-lab-project --base main \
  --head "$(git branch --show-current)" \
  --title 'Publish actual manual NBA pregame pilot records' \
  --body-file .local-data/pregame-cycle/publication-pr.md
```

Write that PR body first with the actual count, partial/failure state, exact
record/producer revisions, clocks, coverage, recovery results and pending grades.
The export's build SHA identifies the published repository snapshot; unlike
`--model-commit`, it legitimately follows the new records/publication revision.
Do not replace the original forecast's model SHA with the export/build SHA.

Complete the existing guarded PR checks/review/exact-head landing workflow.
Explicit per-PR approval is required to merge/deploy a new publication PR; past
PR #5 approval does not cover it. Main's existing workflow builds validated static
records and deploys; a branch build or open PR does not deploy. Verify the actual
main merge/workflow, public manifest build SHA, asset hashes and desktop/mobile
Upcoming/History/Performance. After start, History does not itself mean a completed
or graded result. A site refresh never scrapes sources or rebuilds a model.

## Later verified outcomes and statistical grading

Keep all actual prospective forecasts pending until verified final evidence
exists. After the event has actually started and a completed result is expected,
recover the original binding/records and explicitly run:

```bash
set -eu
NML_FRESH_INPUT_ID="$(python3 -c 'from multisport_lab.integrity import read_receipt; print(read_receipt("evidence/cycles/nba-20261020-401909088-t90-r1-binding.json")["input_reference"]["record_id"])')"
python3 -m multisport_lab.manual_cycle recover \
  --plan evidence/cycles/2026-10-20-nba-401909088-plan.json
python3 -m multisport_lab.prospective_outcomes \
  --event 401909088 --input-record-id "$NML_FRESH_INPUT_ID" \
  --raw-directory .local-data/pregame-cycle/outcomes
```

This makes one actual bounded source request when eligible, retains its actual
capture clock/hash, validates final identity/teams/start/period/stat arithmetic,
and appends separate outcomes/statistical grades only for verified selected rows.
Nonfinal, missing or unclear participation stays pending; do not force an
UNRESOLVED record or assign a zero line. Explicit source DNP becomes
`DNP_NOT_SCORED` with no category scores. A verified appearance scores all 14
original category PMFs; finite-support failures remain `ZERO_SUPPORT` rather
than silently smoothing. `UNRESOLVED` ledger semantics do not authorize inventing
an observation when the source is ambiguous.

An actually verified changed final line requires an explicit reason:

```bash
set -eu
python3 -m multisport_lab.manual_cycle recover \
  --plan evidence/cycles/2026-10-20-nba-401909088-plan.json
python3 -m multisport_lab.prospective_outcomes \
  --event 401909088 --input-record-id "$NML_FRESH_INPUT_ID" \
  --raw-directory .local-data/pregame-cycle/outcome-corrections \
  --correct-outcomes --correction-reason 'REPLACE WITH THE ACTUAL VERIFIED CORRECTION'
```

Never run that placeholder as a claimed correction. Unchanged source outcomes
recover original clocks and receipts; changed verified outcomes/grades append
traceable correction links while preserving originals. Recover, commit/push,
independently read back and publish grades through the same separate workflow.
Statistical grades are not venue financial settlement. K0, prior experiments,
PROS004 activation, qualified tickets and predictive qualification remain outside
this operating pilot. Qualification stays unavailable.

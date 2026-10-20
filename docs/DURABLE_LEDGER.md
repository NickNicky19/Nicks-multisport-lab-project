# Repository research ledger

`multisport_lab/ledger.py` stores small immutable JSON receipts in this repository:

- `records/forecasts/`: typed price-independent NBA forecasts and producer checks.
- `records/outcomes/`: compact normalized outcomes, source hash and actual source
  observation clock; raw provider responses stay outside public assets.
- `records/grades/`: per-category forecast scores and exact forecast/outcome refs.
- `records/corrections/`: explicit supersedes/replacement links and reasons.
- `records/input_captures/`: actual local capture-clock metadata groundwork for a
  later independently admitted future-input producer.

No account, key, paid service, browser storage, scheduler or database is required.
The default `Ledger()` root is this package's repository. Tests explicitly use
temporary directories; those tests establish software behavior only.

The initial milestone budget is **512 receipt files and 32 MiB total**, across all
five kinds, with a **4 MiB maximum per file**. Counts and exact envelope bytes are
checked before a new append. Identical retries preserve the original bytes and
continue to work when the budget is exactly full. Recovery inventories file sizes
and counts before parsing any receipt and fails closed if the store is over budget.
Unpublished `.receipt-*` files left by an interrupted process consume the budget
but never become evidence records. Nothing is deleted or overwritten to make room.
Operate with the documented single integration writer; this is not a distributed
storage quota. Expanding the budget or introducing retention requires a recorded,
versioned decision that preserves the immutable evidence and its references.

## Local receipts and remote durability are separate

Every file uses the existing `integrity.write_receipt` create-only envelope and
canonical decoded-JSON SHA-256. A `LedgerRef` includes kind, deterministic record ID
and complete payload hash. Logical IDs determine filenames; retries read the
original payload and preserve its original `received_at`, forecast issuance,
source observation and grading clocks. Changed data, references or original clocks
under the same logical ID fail. Corrupt files are never repaired by overwriting.

`received_at` comes from the actual local clock on initial creation. It is not a
caller-supplied historical timestamp. Forecast `issued_at` remains the generator's
actual clock. Source `observed_at` remains the supplied retained source receipt's
actual capture clock; historical event dates never substitute for that clock.
Clocks retain six microsecond digits in UTC.

The persisted status is deliberately `LOCAL_RECEIPT_ONLY`. Local creation and a
checksum do not establish upstream authenticity, historical feature availability,
permission, independent issuance, or remote retention. A completed durability
checkpoint additionally requires the integration owner to commit the exact receipt
files, push the commit, and independently read those exact remote bytes/hashes.
Report that observed commit and readback evidence separately; the library does
not claim that a local write has already completed them.

## Issue and recover reconstructed forecasts

The current production API is:

```python
store = Ledger(repository_root)
forecast_ref = store.issue_forecast(bundle, reference=actual_joint_forecast)
payload = store.read(forecast_ref)
recovered_index = Ledger(repository_root).scan()
```

The bundle follows `forecast_contract.py`'s `nba-research-forecast-v1` schema.
Issuance requires the actual coherent `JointForecast` producer object.
`verify_reference()` checks the joint-support digest, every marginal PMF and the
producer's metadata against that object before persistence. The saved producer
attestation binds the complete forecast ID/hash, joint and input hashes, code and
model versions, category hash and actual verification clock. Readback/reindexing
checks those bindings again without publishing or storing the large support rows.
An identical retry re-verifies its producer and retains the original attestation.

Current R0 issuance supports `RECONSTRUCTED_RESEARCH` only. Its historical records
are issued now, after their historical events; they are never pregame paper picks.
They remain conditional on appearance, finite empirical distributions with no
smoothing or unseen tail mass. Producer matching is an internal consistency check,
not statistical validation or proof of source authenticity.

`record_input_capture(metadata)` owns its actual local `observed_at` clock and
preserves source version, source-evidence hash, input hash, access-basis assertion,
and exact event/player identity. It does not fetch data, establish permission, or
turn archived inputs into observed pregame inputs. `REAL_TIME_CAPTURED` issuance
is explicitly rejected for the current R0 producer even if capture metadata exist.
A future producer requires an independently admitted input-capture route, matching
input receipts available at its cutoff, a fresh actual generator clock before the
event, and horizon/participation evaluation. No genuine future capture or result is
created merely to demonstrate this API.

`scan()` reconstructs its index from all bounded receipt files, validating schemas,
hashes, reference existence, referenced payload hashes, receipt chronology and
correction graphs. No process-memory index is authoritative. `iter_forecasts()`
and `iter_grades()` expose all retained typed versions for history inspection.
Publication uses `iter_active_forecasts()` and `iter_active_grades()`: superseded
records stay on disk but are omitted from the current view. Grades whose forecast
or outcome has been superseded are also omitted, even if their own grade has no
correction link. They become current only after an explicit replacement grade is
appended against the current evidence. This prevents double-counting revisions or
presenting a score against an obsolete source outcome as current.

## Record outcomes and grade forecasts

```python
outcome_ref = store.record_outcome(
    validated_nba_player_game,
    source_evidence_sha256=retained_source_hash,
    source_observed_at=actual_source_capture_time,
)
grade_ref = store.grade_forecast(forecast_ref, outcome_ref)
```

Outcomes require an explicit ESPN NBA identity matching the forecast. Other source
namespaces need an independently verified crosswalk first. The source observation
cannot be in the future; final/DNP observations cannot precede the event. A final
appearance needs a complete nonnegative primitive line with `FGM=FG2M+FG3M` and
`PTS=2*FG2M+3*FG3M+FTM`; row-level scoring, rebound and attempt reconciliation is
checked before persistence. All fourteen category outcomes, including optional PA,
derive from that same line. DD/TD use PTS/REB/AST/BLK/STL and preserve TD≤DD.

Explicit final DNP records have no statistical values. Nonfinal, unknown or
incomplete outcomes remain unresolved. Neither becomes a zero-stat appearance.
Compact outcome records retain exact identity, period/overtime semantics, source
hash, original source clock and outcome status; they do not reproduce a raw feed.

Grading checks exact namespace/event/player/start/team/opponent identity and
category units, then applies each weighted marginal PMF to the observed category.
It computes finite-support discrete CRPS/RPS without dropping an observed outcome
outside the support. DD and TD also receive binary Brier scores. Count categories
have no invented threshold Brier score. Log loss is a decimal string when finite;
zero support remains explicit as `log_loss=null`, `log_loss_status=ZERO_SUPPORT`.
No category is dropped because its error or tail is inconvenient.

`nba-forecast-grade-v1` contains `SCORED` with all fourteen category scores,
`DNP_NOT_SCORED`, or `UNRESOLVED`; the latter two have empty category arrays.
Grade IDs fingerprint the complete body, including actual initial grading time.
`validate_grade(body, forecast=None, outcome=None)` checks the typed wire record;
with a forecast it independently recomputes every score from the supplied observed
values and PMFs (absolute tolerance `1e-9`, matching browser validation). Adding
the outcome body also proves that the supplied observed values and status match
the exact retained outcome and its source clock. Full ledger recovery always
checks both evidence bodies and reproduces the producer's canonical grade.

Forecast grading is separate from venue settlement. The public grade's
`financial_settlement` is `NOT_EVALUATED`; the internal grade record explicitly
says `UNSETTLED_FINANCIAL_NOT_IMPLEMENTED`. No profit, payout, void reduction or
paper-ticket settlement follows from a statistical score.

## Corrections preserve originals

Persist a corrected outcome/forecast/grade as a new immutable record, then call
`store.correct(original_ref, replacement_ref, reason="...")`. Both records must
have the same subject identity and evidence kind. A correction receipt stores
the original as `supersedes` and references the exact replacement hash.

Original bytes, issuance clocks and grades remain intact. Branching replacements,
cycles, subject changes, missing references and altered hashes fail. Validation
occurs before creating a new correction file, including when the generic append
API is used. `latest(original_ref)` follows the checked correction chain; callers
can still read every original record. A corrected outcome requires a separately
appended new grade and an explicit grade correction link; original results are
never silently recomputed in place.

Manual paper draft records must remain labeled research drafts with their exact
`ManualDraft.to_record()` and supplied terms/joint evidence. There is no actual
ticket issuance or financial grading API in this milestone, and no fake actual
ticket is persisted. Venue terms, selection admission, durable pregame issuance
and genuine future event outcomes remain separate requirements.

## Verification

Run `python3 -m unittest discover -s tests -p test_ledger.py -v` and the repository's
required full suite/demo. Synthetic checks cover retry/restart clocks, corruption,
references, immutable originals, direct-append correction graph rejection before
write, producer attestation, exact grading identities/units, RPS and DD/TD Brier,
zero support, DNP/unresolved distinctions and explicit rejection of unsupported
real-time producer claims. These checks do not establish remote durability,
independently evaluated predictive performance or any future paper result.

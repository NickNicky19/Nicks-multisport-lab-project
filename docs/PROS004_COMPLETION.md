# PROS004 completion and recovery policy v3

This implementation remains inactive. R0/K0 mathematical laws, the original
reservation, frozen experiments and October 20 pilot code/records are unchanged.
The prospective wrappers are `pros004-r0-producer-v3` and
`pros004-k0-producer-v3`, bound to the same 19 dependencies. Legacy v1/v2 records
remain readable with their original identities and policies;
missing completion proof cannot be inferred from their pre-write receipt clock.

## Distinct operations and clocks

`received_at` in the frozen ledger is sampled before writing. The new store
observes local completion only after the original receipt write/fsync and exact
readback finish. Generation completion and model verification keep their own
clocks. One append-only completion journal preserves post-operation observations.
An interrupted write/acknowledgment preserves its original bytes, fails admission
and never authorizes regeneration of that original.

The required remote checkpoint commits/pushes the exact original and current
journal prefix, then fetches into an independent Git object database, validates
all snapshot bytes/references/typed meanings and reads the exact original back.
The acknowledgment binds repository, branch, commit, snapshot digest, original
raw-byte hash and actual readback completion. The store cross-checks that digest
against its pre-operation snapshot and rejects local mutation during the call.

For event inputs, both local and remote completion must finish by T90−10 minutes.
For each forecast, generation through required original remote completion must
fit 120 seconds and the full registered `[T90,T90+300 seconds]` window. Late and
unacknowledged originals remain retained and explicitly unadmitted after restart.
A new pre-write clock, later receipt or later unrelated record cannot repair them.

The remote acknowledgment is journaled after its call completes. A final,
nonrecursive prefix checkpoint publishes that last original acknowledgment too.
It preserves every original acknowledgment/time, creates no new issuance or
recursive journal acknowledgment, and independently reads the complete prefix.
Input proof publication must finish by selection close; cohort proof publication
must finish by T90+300. The 120-second limit continues to apply to each original's
own generation-through-original-acknowledgment, rather than being renewed by
later evidence publication. A late final publication is explicitly
`LATE_METADATA_PUBLICATION`, including on retries, and cannot produce a successful
cycle-completion report.

Before generating a missing peer, the paired path requires the original typed
input-finalization receipt. It verifies the exact event, acknowledgment clocks,
original journal prefix and reconstructed snapshot. A missing, unrelated,
tampered, late or ambiguous report cannot be replaced by a boolean readiness flag.
Complete original forecasts remain readable without recreating this phase.
The v3 event-admission claim embeds that original report inside its existing
8-KiB envelope. It is written, remotely acknowledged and independently published
before selection closes. Generation recovers this claim and its original proof
without a temporary file or a new generation-phase claim. An optional supplied
report must match the retained one exactly. Legacy claim-v1 records remain
evidence and cannot satisfy this new admission policy. This changes producer
identity and completion policy, not either mathematical law. Genuine activation
and operational destination admission remain disabled.
The paired primitive requires the original claim acknowledgment; it does not
claim that the acknowledgment journal has itself been published. The complete
operating driver and report separately require timely final claim-prefix
publication and fresh remote recovery. A local-only restart cannot establish
that final publication, and remote recovery without the acknowledgment blocks
generation. Bypassing the complete driver cannot establish a completed cycle. Genuine
operating-entrypoint admission must require independently recovered original
admission-finalization evidence, or a separately reviewed equivalent; claim
`timing_complete` alone must not stand in for full phase-publication success.
That operating admission remains an activation dependency behind the hard guard.

`timing_complete` describes an original's local/remote completion evidence.
`metadata_publication_status=NOT_ESTABLISHED_BY_LOCAL_JOURNAL` prevents local
restart from claiming the final journal prefix reached GitHub. A separately
verified final-prefix readback establishes that operation. Comparison eligibility
is a third dimension and remains false while activation is disabled. Diagnostic
records always have zero eligible/issued models even when all eight originals and
their timely synthetic operation evidence were recovered.

## Retention allocation

The unchanged limits are 512 records and 33,554,432 bytes. One shared journal uses
one previously reserved metadata slot: at most 1,024 canonical hash-chained lines,
2,048 bytes including LF per line, and 2,097,152 bytes total. Original prefixes
are immutable. Torn/unrecognized state is retained and rejected without truncation.
There are no extra per-forecast ledger records.

The 499 planned files include 442 comparison records, 32 baseline/pilot slots,
21 event-admission claims, one study manifest, one journal, one combined inactive
activation/review/readback package and one eventual evaluation artifact. Thirteen
correction/failure slots bring the maximum to 512. The proposal has a 5-KiB body
ceiling, combined review package 7 KiB, each inside its 8-KiB envelope allowance.
Its earlier independently recovered proposal must not consume another ledger
slot: operational packaging/admission remains a review dependency.

The full conservative encoded budget is **24,576,000 bytes**, leaving 8,978,432
bytes. All original history/event/forecast/outcome/grade ceilings remain unchanged.
No atom or original receipt is removed to satisfy capacity. Private raw provider
bodies are a separate bounded archive, never silently added to public Git/Pages.

## Typed recovery and inactive operating preparation

The standalone checker first independently verifies exact bytes, hashes,
references, correction graphs, clocks, frozen source pins and capacity. A second
read-only pass reuses the strict typed store validators for every supported
history/event/date/admission/failure/forecast/outcome/grade contract and individual
grade arithmetic. This pass neither generates forecasts nor computes a comparative
aggregate. Snapshots v2 retain exact journal bytes; old v1 snapshots retain their
original bytes and cannot manufacture completion proof.

Activation proposal/review validation is read-only, binds the original first UTC
study date and exact event/source versions, and requires actual gate evidence.
Caller flags and synthetic successes cannot enable genuine writes. The remote
adapter enables only the isolated explicitly diagnostic branch; an operational
writer destination and activation artifact admission still require review.

Raw retention provides immutable content-addressed bytes, capture clocks,
correction links, exact outcome/hash/source-clock cross-checks and a private
transport/readback contract. No actual private primary backend is admitted.
Reviewed indefinite retention, source permission, independent private readback,
raw-to-normalized outcome verification and genuine grading integration remain
activation dependencies. A local archive, synthetic transport, hash link or
public Git object does not establish those facts.

Public manifest v3 adds a separately bounded PROS004 index and pages while reading
legacy v1/v2 assets. Full original probabilities and clocks remain unchanged.
Retained/unadmitted records, individual statistical grades and evidence/model
identities remain distinct. No reserved comparative means, winners or aggregate
study result are published before the registered evaluation gate. Empty inactive
views and the paper builder preserve NBA scope, all 13 categories plus PA, 2–6
legs, directions and NO_ACTION. This package does not deploy that interface.

## Bounded validation reuse after the failed v2 timing diagnostic

### One-operation local proof after the failed v3 timing diagnostic

Source commit `5a1b16edf84e0d765e20accc242f00597d0c749c` removes only the
duplicate pure semantic replay after one local checkpoint callback. Before the
callback, complete strict snapshot verification creates a private single-use
proof bound to the resolved root/directory identities, schema, limits, exact
source hashes and complete canonical manifest. Callers cannot supply a manifest
to construct it; returned JSON trees are isolated copies. Any attempted use,
including a failed one, consumes it.

After the callback, a fresh pass still decodes every receipt, verifies canonical
payload and raw-byte hashes, exact inventory/references/chronology, correction
graph, current clocks, bounded completion journal and final on-disk seals. The
raw bytes and journal must be identical to the prior fully typed snapshot.
Changed source, root, inventory, receipt, journal or clocks reject the proof.
Only the previously checked typed meaning of those exact bytes is reused.
There is no cached durability, timing, eligibility or acknowledgment result,
and every independent remote fetch still receives full strict typed validation.
Actual operation completion is sampled after this fresh pass; the same selection,
120-second and five-minute deadlines apply, including after restart.

The proof adds no retained record or journal line and changes no envelope cap or
ledger allocation. New normal/optimized regressions cover checksum-consistent
semantic mutation, parent/claim changes, inventory/journal replacement, root
replacement, single-use interruption and an actual post-proof completion at
126 seconds that must remain unadmitted after restart. Its independent review
receipt is `evidence/verification/pros004-callback-proof-review-v4.json`.
Any timing benefit requires the new separately retained advancing-clock v4
diagnostic; the earlier failed v2/v3 measurements remain immutable.

### Earlier bounded reuse

The failed c188 full-history receipt is immutable. The next implementation reduces
repeated JSON work, preserving source bytes, clock gates, models and every typed
semantic check. A ledger-instance cache holds only successful legacy source-pack
payload identities, at most 512; every read still checks fresh receipt bytes,
checksum, references and the current clock. Compact PROS004 inputs bypass it.

Within each independent verification invocation, a private bounded index reuses
already decoded/hashed originals and their canonical finite-JSON bytes. Every
reference checks the original payload hash; strict generic validators run once
for each read original and all normal typed store/grade/correction validators
still run. Every supported PROS004 type receives strict semantic validation;
legacy input semantics are validated for referenced parents. Unrelated legacy
receipts retain the independent byte/hash/envelope/reference/clock/correction
checks, as in the previous typed recovery scope.
Fresh JSON decoding gives each caller isolated mutable containers. Initial/final
payload/encoded seals and final on-disk raw hashes, sizes, inventory and journal
checks reject mutation during verification. No cache crosses invocations or
independent source roots; every fresh remote fetch receives a full typed pass.
At most 512 entries / 32 MiB of canonical index bytes are retained in memory.
This optimization establishes no latency result until the separately versioned
fixed-source timing diagnostic completes.

The v3 diagnostic additionally recovers the embedded original input admission
from independently fetched state before generating missing peers. No extra
ledger record is allocated: the 21 existing event-claim slots retain the proof.
The focused synthetic fixture measured 5,675 bytes against the unchanged
8,192-byte claim ceiling; the full-history measurement is reported separately.

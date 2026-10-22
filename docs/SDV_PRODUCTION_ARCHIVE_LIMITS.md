# Production archive bounds

This describes the new, inactive `NBA-SDV-PRODUCTION-001` implementation. It does
not change the first-cycle producer, its ledger limits, or any historical record.
GitHub upload and hosted recovery are **not verified**: the retained first upload
failed, and automatic approval review rejected the additional hosted upload.

## Immutable storage and remaining obligations

Original source files are chunked into exact 1-MiB raw pieces. Ledger receipts
are grouped in immutable packs whose canonical decoded JSON is at most 1 MiB.
Each checkpoint preserves existing pack references and only packs new files.
Admitted receipts and unpublished `.receipt-*` forensic files are retained
separately. Forensic files never become forecasts or grades through recovery.

Every complete transport snapshot has a hard **128-KiB compressed ceiling** and
a 1-MiB decoded ceiling, enforced before publishing the snapshot. A larger
snapshot fails closed; previously uploaded originals remain evidence.

The future manifest reserve must fund every remaining distinct ledger state,
not just the final snapshot. The intended writer maintains one monotone pointer
chain. A changed valid state adds at least one immutable admitted or forensic
file; an unchanged state is content-addressed and idempotent. Thus the remaining
state count is bounded by the remaining typed role slots, remaining permitted
forensic file slots, and one potentially unarchived current state. Multiplying
that count by 131,072 gives the full-snapshot wire reserve. Remaining receipt
packs and forensic bytes are additional obligations. The strict store capacity
and `archive_liability` calculation implement the current complete arithmetic.
Already stored release-asset bytes are charged separately once.

Both backends support a per-run `write_budget_bytes` cap and a monotonically
increasing `new_bytes_reserved` counter. An existing exact object costs zero new
bytes. A new object's exact compressed bytes are reserved before a file write or
any GitHub POST. An ambiguous write keeps its reserve. The coordinator must
allocate the parallel writers' caps from its sealed shared remaining budget;
resetting a process does not authorize another allocation.

The same rules apply independently to object counts: `reserved_objects` funds
remaining shared obligations under the unchanged 100,000-object global ceiling;
`write_budget_objects` limits a writer's allocation, and `new_objects_reserved`
charges only new immutable objects. Exact duplicate puts and ordinary reads
remain available when either reserve is exhausted. Both byte and object guards
must pass before a mutation. Any shard-count arithmetic based on byte headroom
alone (including a 315-shard estimate) is **not an object-capacity guarantee**;
the object quota or API/runtime limits can stop coverage earlier.

## GitHub API inventory cost

The backend uses at most 100 asset metadata rows per inventory page, at most
1,000 pages per release, and at most twelve 100-release inventory pages. The
global archive object ceiling is 100,000. These are hard failure bounds, **not a
verified throughput guarantee**.

For `A` assets in an uncached release, a complete asset inventory needs
`floor(A / 100) + 1` requests, including the final short or empty page. Inventories
are cached within a writer. Across a fresh writer's archive inventory, the
release-list pages and uncached asset pages add together. Each new object then
needs its upload and exact readback. Public immutable reads use the canonical
own-repository asset URL with at most one allowlisted asset redirect and avoid
enumerating all monthly assets on every read. Draft diagnostic reads use the
authenticated official API.

Every individual API response is bounded at 16 MiB. GitHub release JSON includes
asset metadata, so a response-size failure can occur before the object-count
ceiling. Each writer or independent reader stops before action 1,001; the count
includes observed API calls and public asset HTTP requests. This guard can stop
an inventory before 100,000 objects because lookup, inventory, upload and readback
all consume actions. CLI-internal redirects remain explicitly uninstrumented.

The client guard does not establish the GitHub credential's server rate limit,
nor a shared quota for parallel workers. Actual server authorization, rate
headroom, and hosted timing remain unverified. A rate/size/action/operation-budget
failure retains the actual partial state and blocks further admission; it does
not relax gates, replace originals, or establish a successful forecast cycle.

## Clocks and recovery

The remote writer independently fetches the exact pointer commit into a fresh
Git object database without alternates, then reconstructs exact source bytes
and typed ledger contents from a separate archive reader. It records the actual
original-recovery clock separately from the later proof-metadata recovery clock.
Timely original recovery does not claim that the whole operation or later proof
retention was timely. Public admission requires recovery of the proof metadata.

Relevant retained diagnostics are
`evidence/operational/sdv-production-archive-diagnostic-20261022.json` and
`evidence/operational/sdv-production-local-upload-framing-20261022.json`.
The local framing test demonstrates a client fix, not a successful GitHub upload.


## Temporary emergency artifacts

The production prepare, issue and grading jobs upload emergency artifacts only
when their job fails, or when prepare records an actual bounded phase failure
while allowing other due work to continue. They expire after one day and include only the factual
execution report, complete bounded capture originals, and shard ledger receipt
originals (including hidden `.receipt-*` forensic files). Git repositories,
archive copies, independent-readback caches and unrelated work-root files are
excluded. The finish job retains only its failure report. The development-only
diagnostic retains its report and diagnostic ledger originals for one day.

These artifacts are temporary recovery aids, not durable archives or prospective
issuance evidence. Successful immutable archive retention and independent
readback remain required for admission; a failed archive/checkpoint cannot be
made eligible by an artifact upload. Losing an unacknowledged emergency copy
must remain an actual partial or unrecoverable result. The protected first-cycle
postgame job's existing fourteen-day emergency-artifact scope is unchanged.

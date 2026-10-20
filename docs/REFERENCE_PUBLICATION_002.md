# Six historical publication examples

Recorded before these per-player exports/grades are generated, October 20, 2026.
This is an engineering publication sample, not a new accuracy evaluation. The
archive, outcomes and development windows have already been exposed by R0 and
DEV002. Do not interpret these six grades as held-out or prospective evidence.

Use the existing normalized panel SHA-256
`489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c`.
Use `read_normalized_panel`'s unchanged eligibility predicates. Sort eligible
games starting on/after 2025-11-24 00:00 UTC by `(event_start,event_id)`; take the
first three games and the first two player IDs in lexicographic order per game.
Export all fourteen categories for every selected player, without inspecting
errors to select examples. No model changes, tuning, exclusions or aggregate
accuracy claim are authorized by this publication exercise.

Generate the existing coherent R0 reference once per target. Its actual generator
clock is `issued_at`; historical event, T90 cutoff and reconstructed archive
availability clocks retain their distinct meaning. Identity/team membership is
retrospective. The compact outcomes are read now from the retained archive and
record this actual local read time, not an invented original provider capture.
The source hash identifies retained bytes; it does not prove upstream authenticity
or past availability. No raw empirical support rows enter the public export.

Save original forecasts, compact outcomes and separate forecast grades as
create-only ledger receipts. Re-running the publication command recovers existing
records and their clocks without regenerating them. After commit/push, verify
all record bytes and recovery in a fresh remote checkout. That establishes Git
retention, not genuine future issuance, ticket settlement or source permission.
No actual paper tickets, future outcomes or financial results are created here.

Command: `python3 -m multisport_lab.record_reference --input
/tmp/nml-nba-audit/normalized.jsonl --model-commit <full-current-commit>`.
The summary receipt at `evidence/research/reference-publication-002.json` records
the actual selected identities, issue clocks and immutable ledger references.

## Interrupted batches and versioned summary recovery

The existing `reference-publication-002-v1` receipt remains unchanged. Recovery
accepts that schema only when its single `source_observed_at` exactly matches the
actual source observation clock in every referenced outcome. It checks the
receipt's model/source identity, issue clocks, reference kinds and exact grade
dependencies against the retained ledger records. A contradictory v1 receipt
fails; recovery never rewrites its clock or silently upgrades its version.

New batches with no existing summary write `reference-publication-002-v2`.
Each example records its original namespace/event/player/start, period/overtime
and conditioning, model version/commit/code hash, per-target input and joint
hashes, cutoff/training clocks, generator issuance, source observation, outcome
receipt, grade and grade-receipt clocks, source evidence hash and exact ledger
references. These values come from the referenced records. A resumed batch does
not substitute its new execution time for an older retained outcome's clock.

The current compact outcome schema does not contain an upstream source version.
The v2 example therefore preserves `source_version: null` and records the actual
`outcome_schema_version`; the normalized schema version is not presented as an
upstream publication version. `common_source_observed_at` is optional and may
appear only when every example has the same actual source observation clock.
Mixed retained/new outcomes retain their individual clocks and omit that field.

An interrupted historical engineering batch can legitimately read a missing
outcome after a retained forecast's issue time. Recovery requires source
observation at or before its outcome receipt, grade time after both forecast and
outcome receipts, and summary time after all referenced evidence. It does not
claim that the retrospective outcome was known at forecast issuance. Forecasts
remain `RECONSTRUCTED_RESEARCH`; genuine future issuance remains zero.

Recovery needs no normalized panel or model rerun. It validates the six unique
example identities, three distinct games with two players each, ordering, date
boundary, declared selection rule, clocks, metadata and exact forecast/outcome
references used by each grade. Without the frozen panel it cannot independently
prove that those games were the first three eligible games or that a normalized
file hash produced each per-target feature hash. It validates the fixed declared
panel inventory and the saved target-input hashes without equating those two
different hashes or upgrading them to upstream authenticity/availability proof.
Stored model metadata is compared with the referenced bodies, not today's
working-tree code or branch head. The summary is a historical record even after
later corrections; current publication uses the ledger's active-record views.

Before creating a batch, the bounded second read used for outcome normalization
must still match the frozen normalized-panel SHA-256. A file changed after the
initial panel audit fails before any new exemplar is generated or recorded.
Summary reads/writes are bounded at 128 KiB and remain create-only. No existing
forecast, outcome, grade or v1 summary is overwritten to finish an interrupted
batch.

`tests/test_record_reference.py` uses temporary synthetic stores to check failure
before summary creation, recovery of unchanged original clocks/bytes, partial
batches with mixed old/new outcome clocks, exact-reference/metadata rejection,
v1 compatibility and second-read input integrity. These are software checks, not
new model evaluations, actual source captures, financial results or prospective
paper evidence.

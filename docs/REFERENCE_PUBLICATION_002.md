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

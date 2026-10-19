# Reuse provenance

This starter reuses small generic integrity ideas and helpers from additions
authored in Nick's NFL repository. It does not run that project's engine,
collector, writer gate, scheduling, historical grader or website.

## Exact reviewed source

The read-only review pinned the open Phase 2 PR source to
[`551d605d78fd9b64d525f0748cfc3ca2c83bc2de`](https://github.com/NickNicky19/nicks-expert-nfl-picks/tree/551d605d78fd9b64d525f0748cfc3ca2c83bc2de).
The default `main` branch was separately inspected at
[`4d5751a130b6efc0a526f8f7539626d529cef798`](https://github.com/NickNicky19/nicks-expert-nfl-picks/tree/4d5751a130b6efc0a526f8f7539626d529cef798),
with `config/release-mode.json` still set to `phase1`. The PR is a code reference;
this review did not merge, deploy, contact an existing Codex session or write to
the NFL repository.

The GitHub commit response identified the following files as newly **added**,
with author, committer and resolved GitHub author account `NickNicky19`:

| Reviewed file | Introducing commit | Role in this starter |
| --- | --- | --- |
| [tools/reliability.py](https://github.com/NickNicky19/nicks-expert-nfl-picks/blob/551d605d78fd9b64d525f0748cfc3ca2c83bc2de/tools/reliability.py) | [c5fd39cb2277b1b46c224fc2552b314377694bb2](https://github.com/NickNicky19/nicks-expert-nfl-picks/commit/c5fd39cb2277b1b46c224fc2552b314377694bb2) | Source for generic integrity exception, UTC timestamps, canonical JSON, hashing and duplicate-key rejection. |
| [tools/evidence.py](https://github.com/NickNicky19/nicks-expert-nfl-picks/blob/551d605d78fd9b64d525f0748cfc3ca2c83bc2de/tools/evidence.py) | [2e6a83e68304419efd3a21465daabf0b5ef4d1ae](https://github.com/NickNicky19/nicks-expert-nfl-picks/commit/2e6a83e68304419efd3a21465daabf0b5ef4d1ae) | Design reference for checksummed, create-only evidence. Its NFL season/week wrapper is not included. |
| [tools/source_evidence.py](https://github.com/NickNicky19/nicks-expert-nfl-picks/blob/551d605d78fd9b64d525f0748cfc3ca2c83bc2de/tools/source_evidence.py) | [b4a159bdc5f9a1bad98c1f33fc7aa21b792da8b3](https://github.com/NickNicky19/nicks-expert-nfl-picks/commit/b4a159bdc5f9a1bad98c1f33fc7aa21b792da8b3) | Design reference for distinguishing a decoded provider-response fingerprint from normalized data and raw HTTP bytes. Its ESPN/NFL URL and request rules are not included. |

The later reliability change
[`2061f812bdba7f6736c5885f83b94282446b225f`](https://github.com/NickNicky19/nicks-expert-nfl-picks/commit/2061f812bdba7f6736c5885f83b94282446b225f)
preserved microsecond collection timestamps. The new generic `stamp` helper
retains that precision rather than truncating to whole seconds.

For reproducibility, the reviewed source files had these byte fingerprints:

| Source file | Git blob SHA | SHA-256 of file bytes |
| --- | --- | --- |
| `tools/reliability.py` | `5a91fb5d2ad8bd7d209df4e03e42b9bfcee8ceb9` | `1fd09f98011611181ac2bfab9d3be97fb8425ca4e0cfc29b02f2f561647b6ee8` |
| `tools/evidence.py` | `de434ee4b232f000fd161216f67fae995ee7e5c1` | `dd1de007e40439f2a8f01fa5034372434d5ec79e50e658dd81b14c74485c1ba9` |
| `tools/source_evidence.py` | `014f701f02fdac7f0724be48b011a82640d96ed8` | `ddb970319ccc12492ade6d9ffd35c465a3ab54579608e8acae5418fce3a11354` |

## Deliberate adaptations

`multisport_lab/integrity.py` contains a new small provider-independent receipt
store. The functions `utc`, `stamp`, `digest` and `_pairs` retain the generic
behavior of the pinned reliability helpers. `canonical` and `load_json` are
hardened to reject non-string object keys, silent tuple conversion, non-finite
numbers including overflowing JSON exponents, oversized inputs and receipt-file
symlinks. Those are implementation choices for this starter, not claims that the
NFL source already enforced all of them.

The new `write_receipt` does **not** copy the old `immutable_write` retry
comparison. The old baseline path ignored selected metadata fields in its
conflict comparison. Here, every field in the complete canonical payload must
match, including rows, clocks and code/source metadata. A conflicting or corrupt
receipt is rejected and left unchanged. Atomic create-only publication uses a
temporary file, file flush and exclusive same-directory link creation; the
destination is never replaced. This is local filesystem behavior, not a claim
of remote archival, a signed source or independent publication.

Receipts use bounded plain JSON. Their declared format is
`sha256-canonical-decoded-json-v1`; they are not fingerprints of raw HTTP wire
bytes. A correct checksum alone does not prove the data was available before
an event, that the provider is authentic, that a quote was executable, or that
collection/public redistribution is permitted. Those claims need separate
source records and policies.

The new tests exercise malformed JSON, numeric overflow, timestamp precision,
full-payload conflicts, corruption, byte limits, symlinks and failed atomic
publication. All examples are synthetic software checks, with no sports
performance implications.

## What was intentionally left in the NFL project

The repository is a fork of Joshua Moy's project. Neither inspected repository
metadata nor the reviewed source trees established a general license for the
inherited app/model code. This starter therefore contains no inherited
`output/app.js`, stylesheet, NFL projection engine, player database, historical
results or source collector. The user authorized reuse of useful components;
this narrow set is attributed to Nick's later additions. Commit attribution is
provenance evidence and is not a claim of a blanket third-party license grant.

The existing `pull/books.py` is a useful parser reference, but it remains
NFL-specific and records ESPN prop targets without both player-prop prices.
Its Sleeper multipliers do not establish complete ticket economics. Future
sport adapters require their own permitted source route, exact event/contract
identities, observed fixtures and tests before activation. The new integrity
module makes none of those sports or pricing capabilities available by itself.

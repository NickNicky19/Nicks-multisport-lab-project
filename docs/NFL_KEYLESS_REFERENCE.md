# Read-only NFL collection reference — 2026-10-21

This is a code reference for the NBA source-feasibility task, not proof that any
NBA data route is permitted, complete or reliable. No sports-provider request
was made. Provider API keys, login, signup and subscriptions are not parser
prerequisites.

The existing NFL repository was inspected through six read-only GitHub API GETs:
three metadata/tree requests and three immutable source-blob requests. Its
default branch was `main`, observed at
`57c84dea3e7211356e04e201e11cd7090e14adaa`. The recursive tree contained 504 entries
and was not truncated. No active NFL checkout or session was accessed, no NFL
code was executed, and no NFL Git state or workflow was changed.

The complete request clocks, response hashes, exact source-file hashes and
readback-verified receipt are in
[`evidence/verification/nfl-readonly-keyless-reference-20261021.json`](../evidence/verification/nfl-readonly-keyless-reference-20261021.json).
The response hashes describe GitHub CLI output, rather than HTTP wire bytes.
Decoded source contents were additionally checked against their Git blob IDs.

| Reviewed source | Git blob | SHA-256 of source bytes |
| --- | --- | --- |
| `pull/sources.py` | `99b9029acf9a046a590589f001d99b242cc5576f` | `36555cdbc55d73ba632d5adae1130288f4f532073857c642ac3ebc7e626b0061` |
| `pull/books.py` | `406c24755aa9823311c01e3116662845854cf393` | `0b89744960136a4f2e594b61e6df754d357706d8c66a8ae359d8eb02bbfa53f8` |
| `tools/reliability.py` | `a035a4393934ff429588fe89fef24f8c995f72fe` | `cac8e91d80225f99f03d82bb48bacb287bf4b41f9b3d94a13c9b7571930acc38` |

The repository is a fork of `joshuam0y/joshua-moy-expert-nfl-picks`; GitHub's
license metadata was null. No blanket inherited-code license was established.
No inherited collector was copied. Existing
[`REUSE_PROVENANCE.md`](REUSE_PROVENANCE.md) separately attributes Nick's generic
reliability additions and NML's prior hardened adaptation.

## Patterns and limits

- The NFL HTTP helper centralizes a session, an identifying User-Agent,
  `raise_for_status`, a 30-second timeout per attempt and three attempts. The
  inspected code contains no provider credentials. A new admitted NBA capture
  still needs explicit total request, byte, redirect and pagination bounds.
- The ESPN code follows an event/competition/provider hierarchy using
  `propBets`, extracts athlete IDs from references and maps exact market names.
  NBA routes, market semantics and attribution must be verified separately.
  A hard-coded provider number or NFL docstring does not establish DraftKings
  attribution for an NBA response.
- The NFL ESPN return value retains open/current thresholds but omits enough
  contract and observation detail that it cannot be reused as a complete NBA
  offer. `limit=1000` is not a pagination-completeness check. A current target
  does not establish when it was observed or that it was an actual closing line.
- Sleeper's first-option filter and later side aggregation are too weak for the
  NBA contract. Validate the row and every option's subject type, player, sport,
  event, line, period, variant and side before assigning identity. Preserve
  missing/conflicting fields. Pick'em multipliers are not sportsbook odds.
- Stable identity should be league, namespace and source ID. The NFL fallback
  of normalized name and team can collapse ambiguous names, and dictionaries
  can overwrite variants. An old game's identity must not be inferred from a
  player's current roster.
- Provider exceptions converted to empty lists hide the distinction between
  no observed markets and failed collection. NBA diagnostics must retain that
  distinction, plus incomplete pages and unsupported contract semantics.
- Nick's generic integrity helper provides explicit exceptions, timezone-aware
  clocks, canonical finite JSON, duplicate-key rejection, source pins and
  create-only receipts. NML already hardens these ideas. Preserve every field
  when comparing retries; do not adopt the older helper's metadata exclusions.

## Next source task

Use retained NBA evidence and the existing source-use review first. Before a
new bounded provider request, establish the scoped collection/retention basis.
Then verify one actual NBA player contract against recoverable original bytes,
including exact player/event, category, side, threshold, period, overtime,
variant, venue/product, clocks and settlement meaning. Retain actual prices or
`PRICE_UNAVAILABLE`. Missing prices can coexist with a valid offer-only record;
missing contract terms remain unresolved. This code review establishes none of
those real-data requirements and authorizes no collector or publication.

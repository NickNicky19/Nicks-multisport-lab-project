# OPS002 delivery and activation preparation

Status: **REVIEWABLE SOFTWARE / NOT ACTIVATED**, October 21, 2026.

This document specifies the next operating package. It does not install a source
admission, a key, a scheduler or an activation. PR #12 remains draft and unapproved
for landing. The separate approval of website PR #11 does not change that state.
The latest handoff identifies the exact implementation commit and check results.

## Fixed operation and evidence lanes

| Item | Exact proposal or retained evidence |
| --- | --- |
| Protocol | `NBA-PAIRED-OPS-002`; one named game, descriptive operation rather than a new accuracy comparison |
| Plan | `evidence/operational/ops002-plan.json`; plan ID `41b219cb141824131166b0b50a5f08d5942a56bf63c8670a2143b2cad8a57410` |
| Event | ESPN `401909094`, Denver at Oklahoma City; retained start `2026-10-23T01:30:00Z` |
| Cohort | The unchanged plan's four source-selected IDs: `2991350`, `3133626`, `3978`, `3064290`; labels/team assignment remain preparation facts until genuine source verification |
| Statistical scope | Unchanged R0 and K0 laws, four subjects each, all 13 requested categories plus PA; no new model qualification |
| Historical input | Exact retained 26,645-row panel, SHA256 `489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c`; earlier availability/role limitations remain |
| Previously measured producer | `06dbb492dda5d0043ec7a3a6c97ce9c46201edc8`, synthetic run `39536525048`, eight originals, final proof T90+289.817868s |
| New delivery producer | The subsequent source commit identified in the handoff, with `execution_binding()` covering the added modules. It is an unapproved candidate; the previous timing result does not measure these new components. |
| Proposed destination | `NickNicky19/Nicks-multisport-lab-project`, branch `records/nba-paired-ops-002-20261022`, `encrypted-raw/` plus the bounded ledger and completion metadata |
| Publication | Independently admitted forecast and offer-only channels; an absent price or offer is not a statistical-forecast requirement |

The destination above is a proposal, not a created records branch. Ciphertext
would be in a **public GitHub repository**. Plaintext and the private key remain
outside Git, Pages, logs and artifacts. Encrypted retention still needs a
source-use basis for its actual location and duration.

The four proposed source URLs, their exact date/season qualifiers and the scoped
terms review are in [OPS002_SOURCE_USE_REVIEW.md](OPS002_SOURCE_USE_REVIEW.md).
Its result is **NO_OPERATIONAL_ADMISSION**. This checkpoint makes no provider-data
request and does not reinterpret a successful HTTP response as permission.

## Unchanged windows

| Requirement | UTC | America/Chicago (CDT) |
| --- | --- | --- |
| Reviewed activation fully recovered | Strictly before October 22, 23:40 | Strictly before October 22, 6:40 p.m. |
| Fresh capture, persistence and recovery | October 22, 23:40–23:50 | October 22, 6:40–6:50 p.m. |
| Generation and all required final recovery | October 23, 00:00–00:05 | October 22, 7:00–7:05 p.m. |
| Retained game start | October 23, 01:30 | October 22, 8:30 p.m. |

Each original retains its 120-second limit. The complete generation phase retains
its 300-second limit. The old synthetic run's 10.182132-second margin is not a
guarantee for source collection, encryption, actual secret recovery or the new
delivery path. If the requirements cannot be met before the fixed deadline, this
reservation stays inactive. Any later event requires its own reviewed version;
do not shift clocks or relabel preparation data.

## Implemented source and delivery connections

`operational_source_links.EncryptedSourceLinks` authenticates each retained
original response through `EncryptedRawArchive`, compares its exact metadata,
and writes an immutable small ledger link. Four links bind one event input:
dated scoreboard, event summary and both season-qualified team rosters.
`recover_binding()` repeats the actual normalization and cohort selection from
those exact bytes; it rejects changed event, player, mode, URL, clock, hash or
byte count. The reviewed route inventory is stored with the binding. It is not
inferred from a bare endpoint or a UTC calendar date.

The same adapter's `offer_reader()` returns recovered original bytes and source
clocks to `OfferStore`. It does not turn a source link into a publication
admission. The forecast channel does not need an offer record to recover.

`operational_delivery.verify_delivery()` inventories ledger and encrypted archive,
authenticates all manifest-referenced captures, verifies each source link and
event binding, then runs existing typed ledger recovery. A retained event without
its exact source binding is incomplete. A partial archive can remain partial;
recovery does not manufacture a missing input or forecast.

`PreparedOperatingWriter` connects those checks to the existing preserved-prefix,
ordinary Git push and fresh-object-database recovery implementation. Its genuine
constructor calls the unchanged hard-closed activation guard before transport.
Only a fixed diagnostic branch on a temporary local bare Git repository can be
exercised in this checkpoint. The local fixture cannot write GitHub, a records
branch or main. This is real encryption and local Git software verification with
invented bytes, **not an authenticated GitHub-hosted operating run**.

All cipher objects proposed for transport, including orphans, must satisfy the
existing CMS envelope/suite checks. An orphan is preserved and counted without
being promoted to a capture. Invalid bytes remain local and stop delivery. An
archive-only checkpoint also participates in immutable-prefix preservation.

The read-only CLI prints source identity and the proposed destination:

```bash
python3 -m multisport_lab.operational_delivery \
  --source-root . \
  --producer-commit <exact-implementation-source-commit> \
  --records-branch records/nba-paired-ops-002-20261022
```

Exit **2** means preparation remains inactive. Omitting `--producer-commit`
produces an explicitly `LOCAL_UNREVIEWED` file inventory. Neither form captures,
issues, installs an activation or schedules a worker. The expanded execution
binding is separate from the frozen original producer bindings; old evidence is
not rewritten under new code.

## Admission references and authority

`operational_admission.resolve_activation_candidate()` resolves the existing
five activation references and the raw backend's three references against actual
bounded retained receipts. A hash-keyed review inventory specifies each receipt's
path, semantic role, schema, exact context bindings and reviewed expectations.
It checks original payload hashes, producer/file identities, plan, destination,
certificate and secret name where applicable, and reads the graph back again.

The review inventory is not an authority. Resolution cannot create a provider
grant, user approval, genuine timing result or installed key. Successful output
is `REVIEWABLE_CANDIDATE / NOT_ACTIVATED`; all authority, rights, hosted execution,
key-installation and timeliness flags remain false. There is no installed
operational inventory or activation in this checkpoint.

The old hosted receipt retains its `SOFTWARE_DIAGNOSTIC_NON_ISSUANCE` identity and
original source/file map. Resolving it does not make it an execution of the newly
connected delivery code. No additional full-history hosted measurement was run.
Any proposed future measurement must identify the remaining concrete risk (for
example actual encrypted-source, secret and remote delivery overhead), pin its
exact source, scope one bounded run and preserve the old result. Repeating the
completed synthetic experiment is not an automatic next step.

## Concrete key custody and recovery arrangement

The prepared arrangement uses the existing GitHub repository and Actions, without
a new service, signup or provider API key. **It is not installed yet.**

1. The owner identifies an existing private durable backup with a tested retrieval
   method. Recommended: an already-used password manager that supports secure
   file storage, or an existing encrypted offline backup. A runner directory or
   repository secret alone does not establish owner recovery of the original key.
2. After source retention is admitted, generate one RSA key of at least 3072 bits
   outside every checkout, with owner-only file permissions. Generate the matching
   public certificate. Record only the certificate SHA256 and a public-key
   fingerprint in reviewed evidence; never print or commit private key bytes.
3. Retain the original private key in the chosen private backup and independently
   retrieve it. Verify the restored key matches the reviewed public certificate
   and decrypts a non-provider synthetic canary. Record actual check times and
   public fingerprints, not the backup contents or secret location credentials.
4. In the existing authenticated owner environment, install that same key into the
   repository Actions secret `NML_OP002_RAW_PRIVATE_KEY` using stdin. Do not put it
   in a command argument, workflow file, artifact, chat or shell tracing output.
   There is no key rotation or silent replacement within the frozen cycle.
5. A separately reviewed trusted hosted path writes the secret to an owner-only
   file outside the checkout, checks the certificate/key pairing, authenticates a
   retained encrypted canary, and removes the temporary file on every exit. Fork
   pull requests and ordinary CI receive no decryption secret.
6. Recover the resulting permitted encrypted checkpoint into an independent fresh
   Git object database, decrypt with the restored original key and retain factual
   fingerprints, source/host identity, operation clocks and success/failure. A
   ciphertext hash or successful local fixture is insufficient.

The unresolved owner input is the **existing private durable backup and recovery
method**. The source review, actual key installation and hosted readback must
also be completed. This document does not assert those have happened.

## Exact capacity proposal

Capacity v4 reserves **124 ledger/metadata files, 4,848,840 bytes** against the
unchanged 512-file/33,554,432-byte limits. It adds four event-source links and one
event binding, an explicit 32-KiB reference inventory and sufficient small
registration/activation/execution receipts. The old v3 receipt remains unchanged.

The separate raw allocation reserves four pregame captures plus up to eight offer
captures: a subtotal of **25,559,040 bytes**. One later final-summary capture and
up to eight correction captures bring the complete-cycle reserve to **44,728,320
bytes / 21 captures** at the existing 2-MiB source, 16-KiB CMS-overhead and 16-KiB
metadata ceilings. This remains within 64 MiB and 128 capture/cipher-object caps.
Outcome envelopes already contain their raw references and metadata; no additional
standalone ledger link is assumed for those final/correction captures.

This is a capacity proposal, not 21 admitted sources or performed GETs. Postgame
source operation and outcome recovery need their own actual evidence; the
pregame summary cannot serve as final results. Retries and orphan objects also
consume actual space. Every later reservation recalculates the remaining capacity
without increasing a cap.

## Separate first-offer package

The typed offer-only channel remains usable independently when its own admission
requirements are met. It permits `PRICE_UNAVAILABLE`; that does not create a
quote, EV estimate or eligible ticket. Actual offer publication remains **zero**.

The new `source_evidence` adapter lets RULES evidence use exact HTML or plain-text
source bytes. It pins media type, extraction version, extracted-text hash/length
and exact UTF-8 byte spans for reviewed quotations. Backend recovery checks the
original bytes and quotes; the browser checks the published descriptor and
normalized meaning. No rule meaning is guessed from a familiar label.

The HTML extractor is deliberately conservative, does not run CSS/JavaScript and
rejects unsupported markup. Tests use invented source bodies. No real rules page
has been captured, replayed or admitted through it in this checkpoint.

Before the first actual offer can publish, retain one permitted complete NBA
player contract, verify its exact player/event/line/side/period/product and
applicable OT, DNP/participation, postponement, tie/push and correction rules,
authenticate the originals through the admitted retention route, and review its
public derived-fact admission. The current registry stays empty. A missing offer
does not block an otherwise admitted forecast cycle.

## What still prevents genuine operation

- A source-use basis covering the exact proposed fresh collection, encrypted
  retention and necessary public facts has not been established.
- No original operational key, owner backup, Actions secret or authenticated
  hosted recovery has been installed or demonstrated.
- The new delivery modules have local fixture evidence only. A genuine entrypoint
  connecting reviewed authority to the actual hosted capture/writer remains
  disabled and unverified; the old synthetic timing does not cover it.
- Exact-head landing and activation of PR #12 are not approved. PROS004 remains
  inactive, and no scheduler has been armed.

Separately, offer publication remains blocked by the absence of a complete actual
permitted player contract and its publication admission. This does not block an
otherwise admitted statistical forecast cycle.

Preserve the six historical bundles/grades, all 19 original ledger records, all
frozen experiments, NBA category scope and builder behavior. NFL, MLB and the
expired pilot remain separate and untouched.

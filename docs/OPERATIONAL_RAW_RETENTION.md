# OP002 candidate encrypted raw retention

Status: **IMPLEMENTED FOR REVIEW / UNADMITTED**. No operational key/certificate,
GitHub secret, actual source capture, remote raw archive, scheduler, or genuine
issuance was created by this work. Test keys/certificates were ephemeral. The
existing PROS004 archive, protocol and limits are
unchanged. This is a candidate for the separately versioned
`NBA-PAIRED-OPS-002` operating pilot, subject to its reviewed activation gates.

`multisport_lab/operational_raw.py` encrypts already supplied bytes. It makes no
HTTP request and has no GitHub credential. Proposed durability uses ciphertext
on this repository's single records branch, a reviewed public recipient
certificate, and a separately held RSA private key in the existing repository's
Actions secret `NML_OP002_RAW_PRIVATE_KEY`. This is an encryption key, not a new
API key or external service. **That secret is not installed or verified.**

This design needs review before use. Encrypted source copies may still be
subject to source retention terms. Encryption establishes neither collection
permission, redistribution permission, source authenticity, nor pregame
availability. An HTTP200, source hash, or typed admission dictionary establishes
none of those facts. Provider raw plaintext must not enter Git or Pages.

## Contract and recovery API

```python
archive = EncryptedRawArchive(
    encrypted_archive_root, reviewed_public_certificate,
    private_key=private_key_outside_git, admission=reviewed_admission_or_none,
)
reference = archive.retain(
    supplied_raw_bytes, mode="READINESS_DIAGNOSTIC", event_id=event_id,
    source_url=exact_url, request_started_at=actual_request_start,
    observed_at=actual_response_completion,
    source_updated_at=source_update_if_explicit_else_none,
)
metadata, original_raw_bytes = archive.read(reference)
original_references = archive.recover()
```

`inspect(reference)` checks ciphertext, metadata, algorithms and hashes without
the private key. It explicitly does **not** prove authenticated recovery.
`read`/`recover` require the key and authenticate/decrypt before returning bytes.
The key must be an owner-only regular file outside every Git worktree. No key
contents, decrypt stdout, or OpenSSL stderr enter exception messages.

The format uses OpenSSL CMS AuthEnvelopedData, AES-256-GCM, RSA-OAEP with SHA256
and MGF1SHA256, and RSA of at least 3072 bits. Readback inspects the actual CMS
algorithm identifiers, rejecting CBC, alternate OAEP digests and multiple
recipients even if metadata checksums match. The recipient certificate's exact
bytes are pinned and rechecked around operations. An earlier runtime used
OpenSSL 3.5.7; the October 21 connected-component checks also pass with system
OpenSSL 3.0.13. The actual hosted runtime must support and pass this exact CMS
suite; the earlier version string is not itself a required minimum or a proof.

The capture identity commits to pilot, evidence lane, event, source URL,
request/observation/source-update clocks, exact plaintext hash/length,
certificate, admission reference, and correction relationship. Ciphertext is
separately content addressed. Repeating the same capture returns its original
receipt and randomized ciphertext, preserving the first import/encryption and
blob-persistence clocks. It never refreshes an old capture's freshness.
Corrections append a new capture referencing the original, with an explicit
reason and consistent event/source/lane. Original bytes and references remain.

The metadata distinguishes request start, response observation, upstream update
(possibly unknown), import, encryption completion, cipher-blob fsync/readback,
and manifest preparation. **Manifest preparation is not manifest persistence
completion.** After `retain` returns, the guarded caller must sample actual
completion, then checkpoint the entire encrypted archive plus input references,
independently fetch into a fresh Git object database, authenticate every required
raw object, and sample remote recovery completion. None of these clocks or
timeliness/admission conclusions is inferred from metadata written beforehand.

## Source links, bounds and interruption

Archive files are only `ciphertext/<sha256>.cms` and
`captures/<capture-id>.json`. Unexpected files, symlinks and output/Git-internals
roots reject; a public artifact must never recursively copy the archive.
Raw bytes pass through process pipes/memory, not plaintext temporary files.
The eventual runner holds the private key outside the checkout and removes its
ephemeral file after use. No key rotation or replacement is permitted silently
within the frozen cycle.

The original 512-record/32-MiB ledger cap remains separate and unchanged. The
archive adds **no** ledger records itself. Each source needed by an offer or
input may need one small `input_captures` link containing the encrypted raw
reference; these links must be included in the integration capacity plan.
The new `operational_source_links.EncryptedSourceLinks` implements this link and
its authenticated offer reader, exposing `source_observed_at` as `observed_at`
while preserving original clocks. Four event links and a separate event binding
also replay exact event/roster normalization. Local fixture verification does
not establish an actual provider capture or admitted operating backend.

The unchanged bounded raw allowance is enforced over **ciphertext plus receipt
envelopes**, including orphan ciphertext: at most128captures/128cipher objects,
64MiB total, and8MiB per encoded encrypted object. A manifest is at most16KiB;
CMS overhead is at most16KiB. A2MiB source therefore reserves at most2,129,920B
including maximum metadata. Eight such source captures reserve17,039,360B
(16.25MiB); this earlier example remains factual. The connected capacity-v4
proposal reserves four pregame captures plus up to eight offer captures:
25,559,040B. Adding one final summary and eight correction captures gives
44,728,320B for the complete cycle, still within64MiB. None of these counts is
an admitted source inventory. Exact source use, actual partial objects and
remaining budget still need operating review.

Writes use create-only hard links, fsync and readback. A crash before manifest
publication can leave an orphan encrypted object, which remains counted and
preserved. Recovery reports only referenced complete captures, never promotes
an orphan or creates a missing capture. An identical retry may create a second
ciphertext while recovering the interrupted original; both count toward limits.
Unknown temporary files fail closed for manual diagnosis. The caller must keep
one writer and retain partial results rather than deleting them to gain space.

## Required admission before actual use

`REAL_TIME_CAPTURED` fails `RAW_BACKEND_UNADMITTED` with no admission. A typed
admission must pin this repository, its `records/nba-paired-ops-002...` branch,
recipient certificate, exact reviewed source commit, review receipt, source
permission receipt, actual hosted private-key readback receipt, secret name and
indefinite reviewed retention. The outer guarded entrypoint must independently
resolve and verify those references against approved activation; the archive
validator checks meaning/shape only and cannot confer authority.

Remaining prerequisites:

- Review whether encrypted retention in this existing public repository is
  acceptable under the actual source terms and this pilot's protocol.
- Approve/pin the complete backend, certificate, source and host-writer package.
- Generate the private key outside Git and install it through stdin into the
  existing Actions secret without displaying it; commit only the certificate.
- Execute the exact trusted hosted path, independently fetch its encrypted
  checkpoint, decrypt using the retained secret, and retain the factual timing
  and key/ciphertext fingerprint receipt. Fork PRs receive no decryption secret.
- Verify loss/restart access, ongoing primary retention and recovery of the
  original key. Losing or replacing the key invalidates raw recovery; an
  artifact or local temporary key alone is insufficient.
- Count all source links, ciphertext, partial objects, metadata and corrections
  in the exact cycle budget before activation.

There is no actual admission or hosted secret-readback evidence yet. The
existing Actions account alone does not prove these prerequisites.

## Observed synthetic checks

On October 21, 2026, local normal and optimized Python tests exercise authenticated
exact readback, retained retry clocks, a fresh clone with a new Git object
database, wrong keys, changed cipher/tag, checksum-consistent wrong plaintext
identity, CBC/OAEP mismatch, future source clocks, corrections, unadmitted real
capture, capacity, interrupted manifest publication, symlinks/plaintext and key
placement/permissions. They use generated ephemeral synthetic keys and no
provider request, GitHub write or model evaluation.

```bash
python3 -m unittest discover -s tests -p 'test_operational_raw.py' -v
python3 -O -m unittest discover -s tests -p 'test_operational_raw.py' -v
```

An additional non-issuance local size probe used random synthetic bytes and an
ephemeral RSA3072 certificate:56raw bytes became678cipher bytes plus1174receipt
bytes;2,097,152raw bytes became2,097,783cipher bytes plus1183receipt bytes.
Local encryption, persistence and authenticated readback measured0.025023s and
0.670358s respectively. The later request-start field adds metadata bytes; these
earlier measurements remain factual and are not rewritten. They are not hosted
transport latency, source verification or production activation evidence.

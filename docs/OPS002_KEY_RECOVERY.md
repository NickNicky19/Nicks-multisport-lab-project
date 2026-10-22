# OPS002 local key recovery preparation

This is an offline, read-only check for a future, separately admitted operating
key. No operating key, backup, Actions secret or hosted recovery has been created
by this implementation. PR #12 remains draft and genuine operation stays closed.

The owner-only decision is which **existing private durable backup and retrieval
method** will retain the original key. An already-used secure-file password
manager is recommended; an existing encrypted offline backup is also suitable.
Never paste a private key in chat. A runner file or repository secret alone does
not demonstrate owner recovery. Selecting a backup does not admit provider data,
approve public ciphertext retention or activate the pilot.

After the source/backend and key-custody arrangement is separately admitted, the
original RSA key must remain outside every checkout, owner-only, and unchanged
within the cycle. Restore that same original from the chosen backup to a distinct
owner-only file outside Git. A hard link or another reference to the original
file is not a restored copy. The helper cannot independently attest where a file
came from: the actual backup retrieval and its clocks still need factual evidence.

`multisport_lab.operational_key_recovery` verifies the original and restored
private keys against the public certificate and the exact registered public
canary. It pins no-follow file descriptors, checks permissions/placement and
rejects changes or replacement during verification. It requires exactly one
public PEM certificate, refusing bundles that contain an appended private key.
Its decoded PEM bytes must equal the complete parsed X509 DER certificate;
additional material hidden inside the same base64 envelope also rejects.
Both keys must match the certificate's public SPKI and authenticate/decrypt the
canary through the existing AES256-GCM/RSA-OAEP-SHA256/MGF1-SHA256 CMS suite.

The following are preparation commands, **not performed operating setup**. All
`NML_...` values are caller-supplied file paths; no command contains key bytes.
Keep original/restored private-key paths and reports outside checkouts and public
artifacts. The canary text is a fixed public constant, not provider content.

```bash
(
  set -o pipefail -o noclobber
  python3 -c 'import sys; from multisport_lab.operational_key_recovery import CANARY; sys.stdout.buffer.write(CANARY)' |
    openssl cms -encrypt -binary -aes-256-gcm -outform DER \
      -recip "$NML_RECIPIENT_CERTIFICATE" \
      -keyopt rsa_padding_mode:oaep -keyopt rsa_oaep_md:sha256 \
      -keyopt rsa_mgf1_md:sha256 > "$NML_PUBLIC_CANARY"
)

(
  set -o noclobber
  python3 -m multisport_lab.operational_key_recovery \
    --certificate "$NML_RECIPIENT_CERTIFICATE" \
    --original-key "$NML_ORIGINAL_PRIVATE_KEY" \
    --restored-key "$NML_RESTORED_PRIVATE_KEY" \
    --canary "$NML_PUBLIC_CANARY" \
    --backup-method EXISTING_SECURE_FILE_MANAGER \
    > "$NML_LOCAL_KEY_RECOVERY_REPORT"
)
```

For the other existing arrangement, use
`--backup-method EXISTING_ENCRYPTED_OFFLINE_BACKUP`. This field is a declaration,
not proof of backup origin. These Bash subshells use `noclobber` so existing
canary/report paths reject rather than overwrite; OpenSSL writes through the
create-only stdout redirection, not its own overwritable `-out` option. Retain
the exact first result and use a distinct path for a later check. A failed command
may leave an empty or partial new file: retain that actual failure for diagnosis
rather than silently replacing it.

Exit 0 means `VERIFIED_LOCAL_CANARY_ONLY`; exit 2 rejects invalid files or failed
cryptographic recovery. The report includes actual verification clocks, the
verifier's stable local source-file SHA256, exact certificate and public-SPKI
fingerprints, canary hashes and explicit false flags
for durable-backup origin, hosted-secret recovery, source admission and genuine
operation. It contains neither key bytes nor private file paths. This helper
performs no network request, secret installation, key generation, source capture,
forecast issuance or scheduler mutation.

The later trusted hosted secret path still needs separate review and actual
execution. Install the same original through stdin into the existing Actions
secret, recover/decrypt an independently fetched canary with that exact key and
retain the actual host/destination/clocks. Ordinary CI and fork PRs must receive
no decryption secret. Local fixture success does not establish hosted runtime
compatibility or timing of the newly connected operating path.

The verifier fingerprint is labeled `LOCAL_FILE_BYTES_ONLY`, with no reviewed
commit assigned by the helper. Review must independently match those exact bytes
to the intended committed helper source; a local fingerprint is not code approval
or execution attestation. It does not change the frozen operating producer's
binding or timing result.

Focused checks use only ephemeral synthetic keys and local files:

```bash
python3 -m unittest discover -s tests -p 'test_operational_key_recovery.py' -v
python3 -O -m unittest discover -s tests -p 'test_operational_key_recovery.py' -v
```

No actual durable backup or owner retrieval is claimed by those tests. The
registered event/cohort, deadlines, original producer measurements and all frozen
research remain unchanged.

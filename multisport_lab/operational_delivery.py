"""Prepared encrypted input/record delivery, with genuine execution disabled.

The local integration fixture uses actual encryption and Git transport to a
temporary bare repository. It cannot use GitHub, install keys, issue forecasts,
or turn a source review into permission. The production constructor calls the
unchanged activation guard before any transport or source-store mutation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from functools import partial
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from . import operational_pilot as op
from . import operational_remote as remote
from . import operational_raw as raw
from .integrity import IntegrityError, digest, read_receipt, stamp
from .ledger import LedgerRef
from .operational_source_links import EncryptedSourceLinks
from . import pros004_remote as transport

ARCHIVE_DIRECTORY = "encrypted-raw"
DELIVERY_SCHEMA = "nba-op002-encrypted-delivery-snapshot-v1"
LOCAL_BRANCH = "diagnostics/ops002-encrypted-local-fixture"
EXECUTION_FILES = tuple(sorted(set(op.SOURCE_FILES) | {
    "multisport_lab/operational_delivery.py",
    "multisport_lab/operational_source_links.py",
    "multisport_lab/operational_admission.py",
    "multisport_lab/source_evidence.py",
}))


def destination_plan(branch):
    """An exact destination proposal, never an authorization or new branch."""
    op.require(type(branch) is str and re.fullmatch(
        r"records/nba-paired-ops-002(?:-[a-z0-9-]{1,64})?", branch) is not None,
        "delivery needs one isolated OP002 records destination")
    return {"repository": op.REPOSITORY, "remote_url": transport.REMOTE_URL,
            "records_branch": branch, "archive_directory": ARCHIVE_DIRECTORY,
            "ciphertext_visibility": "PUBLIC_GIT_REPOSITORY",
            "plaintext_and_private_key": "OUTSIDE_PUBLICATION",
            "activation": "INACTIVE", "scheduler_installed": False}


def execution_binding(root, commit=None):
    """Pin all added delivery dependencies without rewriting old producer pins.

With no commit this is an explicitly unreviewed local inventory. An exact Git
commit is independently read for every dependency before VERIFIED_COMMIT is
reported; this remains software identity, not activation or source admission.
"""
    root = transport._safe_root(root)
    files = {}
    if commit is not None:
        op.sha(commit, 40)
    for name in EXECUTION_FILES:
        path = transport._safe_root(root / name)
        op.require(path.is_file(), "delivery dependency is missing: " + name)
        content = path.read_bytes()
        files[name] = hashlib.sha256(content).hexdigest()
        if commit is not None:
            result = subprocess.run(["git", "-C", str(root), "show", commit + ":" + name],
                                    capture_output=True, check=False, timeout=10)
            op.require(result.returncode == 0 and result.stdout == content,
                       "delivery dependency differs from exact commit: " + name)
    op.require(all(files[name] == value for name, value in (
        ("multisport_lab/baseline.py", op.LAW_SHA256["R0"]),
        ("multisport_lab/development_003.py", op.LAW_SHA256["K0"]))),
        "delivery changed a frozen model law")
    return op.seal({"schema_version": "nba-op002-delivery-source-binding-v1",
                    "protocol_id": op.PROTOCOL_ID, "commit": commit, "files": files,
                    "verification": "VERIFIED_COMMIT" if commit else "LOCAL_UNREVIEWED",
                    "activation": "INACTIVE"}, "binding_id")


def _archive(root, certificate, private_key, admission):
    return raw.EncryptedRawArchive(transport._safe_root(root) / ARCHIVE_DIRECTORY,
                                   certificate, private_key=private_key, admission=admission)


def delivery_snapshot(root, certificate, *, private_key=None, admission=None):
    """Inventory ledger and ciphertext under their separate unchanged budgets.

This hash-only function is deliberately not an authenticated recovery proof.
Unreferenced ciphertext is preserved and counted; it is not admitted as a
capture or silently deleted to make the snapshot fit.
"""
    root = transport._safe_root(root)
    ledger_snapshot = op.snapshot_manifest(root)
    archive = _archive(root, certificate, private_key, admission)
    inventory = archive.inventory()
    entries = []
    for folder in ("captures", "ciphertext"):
        for path in sorted((archive.root / folder).glob("*")):
            content = path.read_bytes()
            checksum = hashlib.sha256(content).hexdigest()
            if folder == "ciphertext":
                op.require(path.stem == checksum, "ciphertext filename differs from original bytes")
                # An orphan still occupies the unchanged archive budget, but
                # arbitrary plaintext renamed to <hash>.cms must never be
                # transported. This proves envelope format, not source meaning
                # or a complete capture; referenced objects are decrypted below.
                raw._inspect_cipher(content)
            else:
                # Archive recovery derives a reference from the manifest body.
                # Bind that body to this actual filename as well, so a copied
                # manifest cannot appear as another independently recovered
                # capture merely by choosing a different valid-looking name.
                body = read_receipt(path, max_bytes=raw.MAX_METADATA_BYTES)
                op.require(type(body) is dict and body.get("capture_id") == path.stem,
                           "capture manifest filename differs from its original identity")
            entries.append({"path": path.relative_to(root).as_posix(), "bytes": len(content),
                            "raw_sha256": checksum})
    op.require(sum(item["bytes"] for item in entries) == inventory["encoded_bytes"],
               "archive changed while inventorying delivery")
    files = sorted(ledger_snapshot["files"] + entries, key=lambda item: item["path"])
    return op.seal({"schema_version": DELIVERY_SCHEMA, "protocol_id": op.PROTOCOL_ID,
                    "files": files, "file_count": len(files),
                    "total_bytes": sum(item["bytes"] for item in files),
                    "ledger_snapshot_id": ledger_snapshot["snapshot_id"],
                    "ledger_file_count": ledger_snapshot["file_count"],
                    "ledger_encoded_bytes": ledger_snapshot["total_bytes"],
                    "archive_file_count": len(entries),
                    "archive_encoded_bytes": inventory["encoded_bytes"]}, "snapshot_id")


def verify_delivery(root, certificate, private_key, *, admission=None, plan=None,
                    diagnostic=False, replay=False):
    """Authenticate every referenced source and replay each event/source link.

Every event retained in this OP002 snapshot must have its exact four-source
binding. Offer evidence and event evidence remain independent. A partial archive
without a retained event can be preserved without claiming input admission.
"""
    op.require(type(diagnostic) is bool, "delivery diagnostic policy must be explicit")
    root = transport._safe_root(root)
    before = delivery_snapshot(root, certificate, private_key=private_key, admission=admission)
    archive = _archive(root, certificate, private_key, admission)
    capture_refs = archive.recover()
    allowed_modes = {"SYNTHETIC_DIAGNOSTIC", "READINESS_DIAGNOSTIC"} if diagnostic else {"REAL_TIME_CAPTURED"}
    for reference in capture_refs:
        metadata = archive.inspect(reference)
        op.require(metadata["mode"] in allowed_modes,
                   "delivery archive evidence lane differs from its execution policy")
        if plan is not None:
            op.validate_plan(plan)
            op.require(metadata["event_id"] == plan["event"]["event_id"],
                       "delivery archive contains another event")
    links = EncryptedSourceLinks(root, archive)
    index = links.ledger.scan()
    event_refs, bound_events, source_refs = {}, {}, []
    for kind, values in index.items():
        for payload in values.values():
            data = payload["data"]
            reference = LedgerRef(kind, payload["record_id"], digest(payload))
            if "encrypted_source_link" in data:
                recovered = links.read(reference)
                op.require(recovered["body"]["mode"] in allowed_modes,
                           "source link evidence lane differs from delivery policy")
                source_refs.append(reference)
            if "event_source_links" in data:
                recovered = links.recover_binding(reference)
                event_ref = recovered["event_ref"]
                op.require(event_ref not in bound_events, "duplicate binding for a retained event")
                bound_events[event_ref] = recovered
            body = data.get("operational")
            if type(body) is dict:
                op.require(body.get("mode") in allowed_modes,
                           "operational evidence lane differs from delivery policy")
                if body.get("schema_version") == op._schema("event"):
                    event_refs[reference] = body
                    if plan is not None:
                        op.require(body["plan"] == plan, "delivery retained another event/cohort plan")
    op.require(set(event_refs) == set(bound_events),
               "retained event lacks its exact authenticated four-source binding")
    modes = {links.read(ref)["body"]["mode"] for ref in source_refs}
    op.require(len(modes) <= 1, "mixed source evidence lanes cannot share an offer reader")
    mode = next(iter(modes), "SYNTHETIC_DIAGNOSTIC" if diagnostic else "REAL_TIME_CAPTURED")
    verified = op.verify_store(root, replay=replay, allow_synthetic_foreign=diagnostic,
                               raw_reader=partial(links.offer_reader, mode=mode))
    after = delivery_snapshot(root, certificate, private_key=private_key, admission=admission)
    op.require(before == after, "delivery bytes changed during authenticated recovery")
    return {"status": "VERIFIED_RETAINED_BYTES_NOT_ACTIVATED", "snapshot": after,
            "authenticated_captures": len(capture_refs), "source_links": len(source_refs),
            "bound_event_inputs": len(bound_events), "typed_records": verified,
            "genuine_execution_enabled": False, "qualification": "UNAVAILABLE"}


class PreparedOperatingWriter(remote.OperatingDiagnosticWriter):
    """Prepared encrypted transport; only isolated local fixtures are runnable.

Production construction requires the unchanged activation guard. The local
fixture switch accepts only a temporary bare Git repository and its fixed
diagnostic branch; it cannot direct a synthetic run to GitHub or records/*.
    """
    _commit_message = "Retain OP002 encrypted source and record checkpoint"

    def __init__(self, source_root, writer_root, *, base_commit, certificate,
                 private_key, branch, plan=None, admission=None, activation=None,
                 producer_binding=None, local_fixture=False, remote_url=transport.REMOTE_URL,
                 command_seconds=60):
        op.require(type(local_fixture) is bool, "local fixture policy must be boolean")
        if local_fixture:
            op.require(branch == LOCAL_BRANCH, "local fixture needs its isolated diagnostic branch")
            candidate = transport._safe_root(remote_url)
            op.require(candidate.is_dir() and candidate.is_relative_to(Path(tempfile.gettempdir())),
                       "local fixture needs an existing temporary bare repository")
            check = subprocess.run(["git", "-C", str(candidate), "rev-parse", "--is-bare-repository"],
                                   capture_output=True, text=True, check=False, timeout=10)
            op.require(check.returncode == 0 and check.stdout.strip() == "true",
                       "local fixture destination is not a bare repository")
            remote_url = str(candidate)
        else:
            destination_plan(branch)
            op.require(remote_url == transport.REMOTE_URL, "genuine destination changed repository")
            op.require_activation(activation, plan, producer_binding)
        self.source_root, self.root = transport._safe_root(source_root), transport._safe_root(writer_root)
        self.base_commit = transport._sha(base_commit, "base commit", 40)
        self.branch, self.remote_url = branch, str(remote_url)
        self._fixture_remote = self.remote_url if local_fixture else None
        self._local_remote = local_fixture
        self.diagnostic, self.plan, self.admission = local_fixture, plan, admission
        self.certificate, self.private_key = Path(certificate), Path(private_key)
        op.require(type(command_seconds) is int and 1 <= command_seconds <= 60,
                   "invalid delivery Git operation budget")
        self.command_seconds, self._deadline, self._head = command_seconds, None, None
        self.operations = []
        op.require(not self.root.is_relative_to(self.source_root)
                   and not self.source_root.is_relative_to(self.root),
                   "delivery writer and retained source need separate roots")
        archive = _archive(self.source_root, self.certificate, self.private_key, admission)
        self.certificate_sha256 = archive.certificate_sha256
        op.require(not self.private_key.absolute().is_relative_to(self.source_root)
                   and not self.private_key.absolute().is_relative_to(self.root),
                   "private key must be outside both delivery roots")

    def _fixture_guard(self):
        if self._fixture_remote is None:
            op.require_activation()
        op.require(self._local_remote is True and self.diagnostic is True
                   and self.branch == LOCAL_BRANCH and self.remote_url == self._fixture_remote,
                   "local fixture destination or branch changed after construction")
        candidate = transport._safe_root(self.remote_url)
        op.require(candidate.is_dir() and candidate.is_relative_to(Path(tempfile.gettempdir())),
                   "local fixture no longer has its temporary bare destination")

    @staticmethod
    def _local_git_args(*args):
        # Every fixture transport stays local even in a caller environment with
        # URL rewrites or explicit network-protocol defaults. URL checks below
        # independently reject a different local destination as well.
        return ["git", "-c", "protocol.allow=never", "-c", "protocol.file.allow=always",
                "-c", "protocol.http.allow=never", "-c", "protocol.https.allow=never",
                "-c", "protocol.ssh.allow=never", "-c", "protocol.git.allow=never",
                "-c", "protocol.ext.allow=never", *args]

    def _fixture_origin(self, root):
        for flags in (("--all",), ("--push", "--all")):
            result = self._command(self._local_git_args("remote", "get-url", *flags, "origin"), cwd=root)
            op.require(result.stdout.splitlines() == [self._fixture_remote],
                       "local fixture fetch/push origin differs from the exact temporary destination")

    def _git(self, *args, cwd=None, check=True):
        self._fixture_guard()
        root = transport._safe_root(cwd or self.root)
        if args and args[0] in {"fetch", "push", "ls-remote", "clone", "pull"}:
            self._fixture_origin(root)
        return self._command(self._local_git_args(*args), cwd=root, check=check)

    def prepare(self):
        # Validate before the inherited method creates even a local checkout.
        self._fixture_guard()
        probe = self._command(self._local_git_args("rev-parse", "--is-bare-repository"),
                              cwd=self._fixture_remote)
        op.require(probe.stdout.strip() == "true", "local fixture destination is no longer bare")
        result = super().prepare()
        self._fixture_origin(self.root)
        return result

    def _preserve(self, manifest):
        # A first partial delivery can contain only encrypted sources. Preserve
        # it just as strictly as a checkpoint that already contains records.
        if not ((self.root / "records").exists() or (self.root / ARCHIVE_DIRECTORY).exists()):
            return
        previous = self._verified(self.root)
        current = {entry["path"]: entry for entry in manifest["files"]}
        for entry in previous["files"]:
            relative = entry["path"]
            op.require(relative in current, "delivery source is missing a retained remote original")
            old = (self.root / relative).read_bytes()
            if relative == op.JOURNAL:
                op.require((self.source_root / relative).read_bytes().startswith(old),
                           "delivery completion journal cannot replace its original prefix")
            elif relative == op.PROOF and old != (self.source_root / relative).read_bytes():
                archived = Path(op.PROOF).with_name("remote-recovery." + hashlib.sha256(old).hexdigest() + ".json").as_posix()
                op.require(archived in current and (self.source_root / archived).read_bytes() == old,
                           "delivery must retain its original recovery proof revision")
            else:
                op.require(entry == current[relative], "delivery cannot replace a retained encrypted or ledger original")

    def _snapshot(self, root):
        op.require(hashlib.sha256(self.certificate.read_bytes()).hexdigest() == self.certificate_sha256,
                   "delivery certificate changed after construction")
        return delivery_snapshot(root, self.certificate, private_key=self.private_key,
                                 admission=self.admission)

    def _verified(self, root):
        self._snapshot(root)
        return verify_delivery(root, self.certificate, self.private_key,
                               admission=self.admission, plan=self.plan,
                               diagnostic=self.diagnostic, replay=False)["snapshot"]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only OP002 delivery package; no activation or source I/O")
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--producer-commit")
    parser.add_argument("--records-branch", required=True)
    args = parser.parse_args(argv)
    report = {"schema_version": "nba-op002-delivery-preparation-v1",
              "observed_at": stamp(datetime.now(timezone.utc)),
              "destination": destination_plan(args.records_branch),
              "execution_binding": execution_binding(args.source_root, args.producer_commit),
              "status": "BLOCKED_NOT_ACTIVATED", "genuine_issuance_created": 0,
              "provider_requests": 0, "scheduler_installed": False}
    print(json.dumps(report, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

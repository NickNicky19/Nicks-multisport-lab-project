"""Read-only reference resolution for a reviewable, never activated OPS002 proposal.

The review inventory maps canonical payload hashes to exact retained receipt
paths, semantic kinds, schemas, context-field JSON pointers and explicit semantic
expectations. It is an input to review, not a signature or source-rights grant.
No successful result enables ``operational_pilot.require_activation``.

All hashes here are decoded canonical payload SHA256 values (``integrity.digest``),
not receipt-file, Git-object or original HTTP-body hashes. Existing descriptive
receipt filenames are allowed; the hash-keyed inventory supplies the address.
"""
from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path, PurePosixPath
import stat

from . import operational_pilot as pilot
from . import operational_raw as raw
from .integrity import (HASH_FORMAT, RECEIPT_SCHEMA, IntegrityError, _decode,
                        canonical, digest)

MAX_INVENTORY_ENTRIES = 8
MAX_INVENTORY_BYTES = 32 * 1024
MAX_ASSERTIONS = 12
RESULT_SCHEMA = "nba-operational002-resolved-candidate-v1"

ACTIVATION_ROLES = {
    "approval_evidence_sha256": "ACTIVATION_APPROVAL",
    "source_admission_sha256": "SOURCE_OPERATION_ADMISSION",
    "retention_admission_sha256": "RAW_RETENTION_ADMISSION",
    "hosted_diagnostic_sha256": "HOSTED_DIAGNOSTIC",
    "remote_recovery_sha256": "INDEPENDENT_REMOTE_RECOVERY",
}
RAW_ROLES = {
    "review_evidence_sha256": "RAW_BACKEND_REVIEW",
    "source_permission_sha256": "SOURCE_PERMISSION",
    "host_readback_sha256": "HOSTED_RAW_RECOVERY",
}
_RAW_CONTEXT = {"repository", "records_branch", "reviewed_commit",
                "recipient_certificate_sha256", "private_key_secret"}
_PLAN_CONTEXT = _RAW_CONTEXT | {"protocol_id", "plan_id", "producer_binding_id"}
_REQUIRED_BINDINGS = {
    "ACTIVATION_APPROVAL": _PLAN_CONTEXT,
    "SOURCE_OPERATION_ADMISSION": _PLAN_CONTEXT,
    "RAW_RETENTION_ADMISSION": set(),  # Exact existing validator and direct fields below.
    "HOSTED_DIAGNOSTIC": {"protocol_id", "reviewed_commit", "producer_files"},
    "INDEPENDENT_REMOTE_RECOVERY": _PLAN_CONTEXT,
    "RAW_BACKEND_REVIEW": _RAW_CONTEXT,
    "SOURCE_PERMISSION": _RAW_CONTEXT,
    "HOSTED_RAW_RECOVERY": _RAW_CONTEXT,
}
_CEILINGS = {kind: 16 * 1024 for kind in _REQUIRED_BINDINGS}
_CEILINGS.update(HOSTED_DIAGNOSTIC=1024 * 1024,
                 INDEPENDENT_REMOTE_RECOVERY=64 * 1024)


def _require(condition, message):
    if not condition:
        raise IntegrityError("OPS002 reference review: " + message)


def _pointer(value, pointer):
    _require(type(pointer) is str and 0 < len(pointer) <= 512 and pointer.startswith("/"),
             "a bounded explicit JSON pointer is required")
    for token in pointer[1:].split("/"):
        # Reject malformed escapes instead of treating them as alternate spellings.
        i = 0
        while i < len(token):
            if token[i] == "~":
                _require(i + 1 < len(token) and token[i + 1] in "01", "invalid pointer escape")
                i += 1
            i += 1
        token = token.replace("~1", "/").replace("~0", "~")
        if type(value) is dict:
            _require(token in value, "referenced field is missing")
            value = value[token]
        elif type(value) is list:
            _require(token.isascii() and token.isdigit() and str(int(token)) == token,
                     "invalid array pointer")
            index = int(token)
            _require(index < len(value), "array pointer is outside the receipt")
            value = value[index]
        else:
            raise IntegrityError("OPS002 reference review: pointer crosses a scalar")
    return value


def _same(actual, expected):
    # Python equality otherwise admits True == 1 and False == 0.
    return canonical(actual) == canonical(expected)


def _directory_flags():
    _require(hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"),
             "this platform lacks required no-follow directory descriptors")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _open_root(root):
    """Open every absolute component without following a symlink; caller closes."""
    flags = _directory_flags()
    directory = os.open("/", flags)
    try:
        for part in root.parts[1:]:
            child = os.open(part, flags, dir_fd=directory)
            os.close(directory)
            directory = child
        result, directory = directory, None
        return result
    finally:
        if directory is not None:
            os.close(directory)


def _regular_root(root):
    directory = None
    try:
        root = Path(root).absolute()
        _require(root.anchor == "/" and "\x00" not in str(root) and len(str(root)) <= 4096
                 and ".." not in root.parts, "invalid canonical receipt root")
        directory = _open_root(root)
        identity = os.fstat(directory)
        return root, (identity.st_dev, identity.st_ino)
    except (OSError, ValueError, TypeError) as error:
        if isinstance(error, IntegrityError):
            raise
        raise IntegrityError("OPS002 reference review: receipt root is missing, not a directory, or contains a symlink") from error
    finally:
        if directory is not None:
            os.close(directory)


class _Resolver:
    def __init__(self, root, inventory, context):
        self.root, self.root_identity = _regular_root(root)
        _require(type(inventory) is dict and 0 < len(inventory) <= MAX_INVENTORY_ENTRIES,
                 "invalid or excessive evidence inventory")
        _require(len(canonical(inventory)) <= MAX_INVENTORY_BYTES, "evidence inventory exceeds its byte limit")
        self.inventory = deepcopy(inventory)
        self.context = deepcopy(context)
        self.resolved = {}
        paths = set()
        for payload_sha, item in self.inventory.items():
            pilot.sha(payload_sha)
            _require(type(item) is dict and set(item) ==
                     {"path", "kind", "schema_version", "bindings", "assertions"},
                     "invalid inventory entry")
            kind = item["kind"]
            _require(type(kind) is str and kind in _REQUIRED_BINDINGS, "unknown evidence kind")
            path = item["path"]
            _require(type(path) is str and 0 < len(path) <= 512 and "\\" not in path and "\x00" not in path,
                     "invalid receipt path")
            parsed = PurePosixPath(path)
            _require(not parsed.is_absolute() and path == "/".join(parsed.parts)
                     and all(part not in {".", "..", ".git"} for part in parsed.parts)
                     and path.endswith(".json"), "receipt path must stay under its inventory root")
            _require(path not in paths, "different inventory entries reuse one receipt path")
            paths.add(path)
            _require(type(item["schema_version"]) is str and 0 < len(item["schema_version"]) <= 160,
                     "expected evidence schema is missing")
            bindings = item["bindings"]
            _require(type(bindings) is dict and set(bindings) == _REQUIRED_BINDINGS[kind],
                     "required evidence context bindings differ")
            for pointer in bindings.values():
                _require(type(pointer) is str and pointer.startswith("/"), "invalid context binding pointer")
            assertions = item["assertions"]
            _require(type(assertions) is dict and len(assertions) <= MAX_ASSERTIONS,
                     "invalid semantic expectations")
            if kind != "RAW_RETENTION_ADMISSION":
                _require(bool(assertions), "explicit semantic expectations are required")
            for pointer in assertions:
                _require(type(pointer) is str and pointer.startswith("/"), "invalid semantic expectation pointer")
            if kind == "RAW_RETENTION_ADMISSION":
                _require(item["schema_version"] == raw.ADMISSION_SCHEMA,
                         "retention reference has the wrong schema")
            if kind == "HOSTED_DIAGNOSTIC":
                # A complete synthetic timing receipt remains synthetic evidence.
                _require(item["schema_version"] == "nba-op002-hosted-operating-diagnostic-v2"
                         and assertions.get("/mode") == "SOFTWARE_DIAGNOSTIC_NON_ISSUANCE"
                         and assertions.get("/status") == "PASS_FULL_COHORT_OPERATIONAL_DIAGNOSTIC",
                         "hosted diagnostic must retain its explicit synthetic meaning")

    def _read_bound_receipt(self, relative, *, max_bytes):
        """Read bounded bytes below the pinned root using only no-follow opens.

        A renamed parent cannot redirect an already opened directory descriptor.
        Reopening the root also requires its original device/inode identity.
        NONBLOCK prevents a concurrent FIFO replacement from hanging before the
        final descriptor's regular-file check. Nothing is read before that check.
        """
        directory = descriptor = None
        try:
            directory = _open_root(self.root)
            root_stat = os.fstat(directory)
            _require((root_stat.st_dev, root_stat.st_ino) == self.root_identity,
                     "original receipt root was replaced")
            parts = PurePosixPath(relative).parts
            for part in parts[:-1]:
                child = os.open(part, _directory_flags(), dir_fd=directory)
                os.close(directory)
                directory = child
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
            descriptor = os.open(parts[-1], flags, dir_fd=directory)
            before = os.fstat(descriptor)
            _require(stat.S_ISREG(before.st_mode), "referenced receipt is missing or not regular")
            _require(before.st_size <= max_bytes, "receipt exceeds its byte limit")
            chunks, total = [], 0
            while total <= max_bytes:
                chunk = os.read(descriptor, min(65536, max_bytes + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            _require(total <= max_bytes, "receipt exceeds its byte limit")
            after = os.fstat(descriptor)
            stable = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            _require(stable(before) == stable(after) and total == after.st_size,
                     "receipt changed while its bytes were read")
            encoded = b"".join(chunks)
        except (OSError, ValueError) as error:
            if isinstance(error, IntegrityError):
                raise
            raise IntegrityError("OPS002 reference review: referenced receipt is missing or not regular, "
                                 "contains a symlink, or could not be read") from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if directory is not None:
                os.close(directory)
        try:
            envelope = _decode(encoded)
            _require(type(envelope) is dict and set(envelope) ==
                     {"schema_version", "hash_format", "payload_sha256", "payload"}
                     and envelope["schema_version"] == RECEIPT_SCHEMA
                     and envelope["hash_format"] == HASH_FORMAT,
                     "unsupported receipt envelope or hash format")
            _require(envelope["payload_sha256"] == digest(envelope["payload"]),
                     "receipt payload checksum mismatch")
        except RecursionError as error:
            raise IntegrityError("OPS002 reference review: receipt nesting is unsupported") from error
        return envelope["payload"]

    def resolve(self, payload_sha, kind):
        _require(payload_sha in self.inventory, "referenced receipt is absent from the reviewed inventory")
        item = self.inventory[payload_sha]
        _require(item["kind"] == kind, "reference resolves to the wrong semantic kind")
        body = self._read_bound_receipt(item["path"], max_bytes=_CEILINGS[kind])
        _require(digest(body) == payload_sha, "referenced payload hash differs from retained bytes")
        _require(type(body) is dict and body.get("schema_version") == item["schema_version"],
                 "retained evidence schema differs")
        for key, pointer in item["bindings"].items():
            _require(key in self.context and _same(_pointer(body, pointer), self.context[key]),
                     "retained evidence contradicts the exact " + key)
        for pointer, expected in item["assertions"].items():
            _require(_same(_pointer(body, pointer), expected), "retained evidence contradicts its semantic expectation")
        self.resolved[payload_sha] = {"path": item["path"], "kind": kind,
                                     "schema_version": item["schema_version"]}
        if kind == "HOSTED_DIAGNOSTIC":
            self.resolved[payload_sha]["evidence_lane"] = body["mode"]
        return body

    def stable_readback(self):
        for payload_sha, item in self.resolved.items():
            # Recheck path and exact payload after resolving the complete graph.
            self.resolve(payload_sha, item["kind"])


def _context(producer_commit, records_branch, certificate_sha256):
    pilot.sha(producer_commit, 40)
    pilot.sha(certificate_sha256)
    return {"repository": pilot.REPOSITORY, "records_branch": records_branch,
            "reviewed_commit": producer_commit, "recipient_certificate_sha256": certificate_sha256,
            "private_key_secret": "NML_OP002_RAW_PRIVATE_KEY"}


def _raw(admission, resolver):
    raw.validate_admission(admission, certificate_sha256=resolver.context["recipient_certificate_sha256"])
    _require(admission["repository"] == resolver.context["repository"]
             and admission["records_branch"] == resolver.context["records_branch"]
             and admission["reviewed_source_commit"] == resolver.context["reviewed_commit"],
             "raw admission changes the exact producer or destination")
    for field, kind in RAW_ROLES.items():
        resolver.resolve(admission[field], kind)


def _result(resolver, *, admission, activation=None):
    resolver.stable_readback()
    return {"schema_version": RESULT_SCHEMA, "status": "REVIEWABLE_CANDIDATE",
            "activation": "NOT_ACTIVATED", "authorized": False,
            "source_rights_verified": False, "genuine_host_path_verified": False,
            "executed_source_verified": False, "reference_timeliness_verified": False,
            "private_key_installed_or_recovered": False,
            "inventory_sha256": digest(resolver.inventory),
            "context": dict(resolver.context), "raw_admission_sha256": digest(admission),
            "activation_candidate_sha256": digest(activation) if activation is not None else None,
            "resolved_receipts": dict(resolver.resolved),
            "meaning": "Verified retained payload integrity and declared review-inventory bindings only; "
                       "inventory provenance, approval authority, source rights, executed bytes, evidence timeliness "
                       "and actual hosted/key operation "
                       "remain separate. Synthetic timing evidence stays synthetic. Genuine writes remain disabled."}


def resolve_raw_admission(admission, *, receipt_root, inventory, producer_commit,
                          records_branch, certificate_sha256):
    """Resolve the three existing backend references; perform no decrypt or write."""
    resolver = _Resolver(receipt_root, inventory, _context(producer_commit, records_branch, certificate_sha256))
    _raw(admission, resolver)
    return _result(resolver, admission=admission)


def resolve_activation_candidate(activation, plan, binding, *, receipt_root, inventory,
                                 records_branch, certificate_sha256):
    """Resolve five activation and three backend references without granting admission.

    ``bindings`` in each reviewed inventory entry maps the required context names
    in ``_REQUIRED_BINDINGS`` to JSON pointers in its retained receipt. ``assertions``
    pins the reviewer's explicit semantic expectations. Neither declares who may
    approve the operation; all successful results remain NOT_ACTIVATED.
    """
    pilot.validate_plan(plan)
    pilot.validate_source_binding(binding, check_current=False)
    pilot.validate_activation_candidate(activation, plan, binding)
    context = {**_context(binding["commit"], records_branch, certificate_sha256),
               "protocol_id": pilot.PROTOCOL_ID, "plan_id": plan["plan_id"],
               "producer_binding_id": binding["binding_id"], "producer_files": binding["files"]}
    resolver = _Resolver(receipt_root, inventory, context)
    bodies = {kind: resolver.resolve(activation[field], kind)
              for field, kind in ACTIVATION_ROLES.items()}
    admission = bodies["RAW_RETENTION_ADMISSION"]
    _raw(admission, resolver)
    return _result(resolver, admission=admission, activation=activation)

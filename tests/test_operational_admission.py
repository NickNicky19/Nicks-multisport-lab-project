"""Small fictional receipt graphs; no source capture, model run or activation."""
from copy import deepcopy
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from multisport_lab import operational_admission as admission
from multisport_lab import operational_pilot as pilot
from multisport_lab import operational_raw as raw
from multisport_lab.integrity import (HASH_FORMAT, RECEIPT_SCHEMA, IntegrityError,
                                     canonical, digest, read_receipt, write_receipt)

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "records/nba-paired-ops-002-fixture"
CERTIFICATE = "a" * 64


def reseal(body, field):
    body.pop(field, None)
    return pilot.seal(body, field)


class Fixture:
    """All approval/source/key claims below are explicitly fictional test inputs."""
    def __init__(self, root, binding=None):
        self.root = root
        self.plan = read_receipt(ROOT / "evidence/operational/ops002-plan.json")
        if binding is None:
            self.binding = pilot.make_source_binding(diagnostic=True, root=ROOT)
            self.binding.update(commit="1" * 40, verification="VERIFIED_COMMIT")
            self.binding = reseal(self.binding, "binding_id")
        else:
            self.binding = deepcopy(binding)
        self.context = {"repository": pilot.REPOSITORY, "records_branch": BRANCH,
                        "reviewed_commit": self.binding["commit"],
                        "recipient_certificate_sha256": CERTIFICATE,
                        "private_key_secret": "NML_OP002_RAW_PRIVATE_KEY",
                        "protocol_id": pilot.PROTOCOL_ID, "plan_id": self.plan["plan_id"],
                        "producer_binding_id": self.binding["binding_id"],
                        "producer_files": self.binding["files"]}
        self.inventory = {}
        self.hashes = {}
        self.bodies = {}
        for kind in admission.RAW_ROLES.values():
            self.put(kind, self.proof(kind))
        self.raw = {"schema_version": raw.ADMISSION_SCHEMA, "pilot_id": raw.PILOT_ID,
                    "repository": pilot.REPOSITORY, "records_branch": BRANCH,
                    "private_key_secret": "NML_OP002_RAW_PRIVATE_KEY",
                    "recipient_certificate_sha256": CERTIFICATE,
                    "reviewed_source_commit": self.binding["commit"],
                    **{field: self.hashes[kind] for field, kind in admission.RAW_ROLES.items()},
                    "privacy": "ENCRYPTED_WITH_SEPARATE_PRIVATE_KEY",
                    "retention_through": "INDEFINITE_REVIEWED",
                    "state": "REVIEWED_EXACT_SOURCE_AND_BACKEND"}
        self.put("RAW_RETENTION_ADMISSION", self.raw)
        for kind in admission.ACTIVATION_ROLES.values():
            if kind != "RAW_RETENTION_ADMISSION":
                self.put(kind, self.proof(kind))
        self.activation = pilot.seal({
            "schema_version": pilot._schema("activation"), "protocol_id": pilot.PROTOCOL_ID,
            "plan_id": self.plan["plan_id"], "producer_binding_id": self.binding["binding_id"],
            "reviewed_commit": self.binding["commit"], "reviewed_at": "2026-10-21T04:00:00.000000Z",
            "status": "REVIEWED_READY",
            **{field: self.hashes[kind] for field, kind in admission.ACTIVATION_ROLES.items()},
        }, "activation_id")

    def proof(self, kind):
        body = {"schema_version": "fictional-op002-" + kind.lower() + "-v1",
                "evidence_lane": "SYNTHETIC_TEST", "subject": deepcopy(self.context),
                "decision": {"matches_reviewed_expectation": True}}
        if kind == "HOSTED_DIAGNOSTIC":
            body.update(schema_version="nba-op002-hosted-operating-diagnostic-v2",
                        mode="SOFTWARE_DIAGNOSTIC_NON_ISSUANCE",
                        status="PASS_FULL_COHORT_OPERATIONAL_DIAGNOSTIC")
        return body

    def put(self, kind, body, *, item=None):
        value = digest(body)
        relative = "receipts/" + value + ".json"
        write_receipt(self.root / relative, body)
        if item is None:
            item = {"path": relative, "kind": kind, "schema_version": body["schema_version"],
                    "bindings": {key: "/subject/" + key for key in admission._REQUIRED_BINDINGS[kind]},
                    "assertions": {} if kind == "RAW_RETENTION_ADMISSION" else
                                  {"/decision/matches_reviewed_expectation": True}}
            if kind == "HOSTED_DIAGNOSTIC":
                item["assertions"].update({"/mode": "SOFTWARE_DIAGNOSTIC_NON_ISSUANCE",
                                           "/status": "PASS_FULL_COHORT_OPERATIONAL_DIAGNOSTIC"})
        else:
            item = {**deepcopy(item), "path": relative}
        old = self.hashes.get(kind)
        if old is not None:
            del self.inventory[old]
        self.inventory[value] = item
        self.hashes[kind] = value
        self.bodies[kind] = deepcopy(body)
        return value

    def replace(self, kind, body, *, item=None):
        old_item = deepcopy(item or self.inventory[self.hashes[kind]])
        self.put(kind, body, item=old_item)
        for field, role in admission.RAW_ROLES.items():
            if role == kind:
                self.raw[field] = self.hashes[kind]
                self.put("RAW_RETENTION_ADMISSION", self.raw)
        for field, role in admission.ACTIVATION_ROLES.items():
            self.activation[field] = self.hashes[role]
        self.activation = reseal(self.activation, "activation_id")

    def run(self, **kwargs):
        options = {"receipt_root": self.root, "inventory": self.inventory,
                   "records_branch": BRANCH, "certificate_sha256": CERTIFICATE, **kwargs}
        return admission.resolve_activation_candidate(self.activation, self.plan, self.binding, **options)


class OperationalAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = Fixture(self.root)

    def test_complete_graph_is_read_only_and_never_activates_or_generates(self):
        f = self.fixture
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with mock.patch.object(pilot, "require_activation", side_effect=AssertionError("unexpected activation")), \
             mock.patch.object(pilot, "_fit_laws", side_effect=AssertionError("unexpected model execution")), \
             mock.patch("subprocess.run", side_effect=AssertionError("unexpected external command")):
            result = f.run()
        after = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(result["status"], "REVIEWABLE_CANDIDATE")
        self.assertEqual(result["activation"], "NOT_ACTIVATED")
        for flag in ("authorized", "source_rights_verified", "genuine_host_path_verified",
                     "executed_source_verified", "reference_timeliness_verified",
                     "private_key_installed_or_recovered"):
            self.assertIs(result[flag], False)
        self.assertEqual(len(result["resolved_receipts"]), 8)
        self.assertEqual(result["raw_admission_sha256"], digest(f.raw))
        with self.assertRaisesRegex(IntegrityError, "NO_REVIEWED_ACTIVATION_INSTALLED"):
            pilot.require_activation(f.activation, f.plan, f.binding)

    def test_raw_admission_resolves_only_its_three_existing_references(self):
        f = self.fixture
        result = admission.resolve_raw_admission(f.raw, receipt_root=self.root,
            inventory=f.inventory, producer_commit=f.binding["commit"],
            records_branch=BRANCH, certificate_sha256=CERTIFICATE)
        self.assertEqual(len(result["resolved_receipts"]), 3)
        self.assertIsNone(result["activation_candidate_sha256"])
        self.assertEqual(result["activation"], "NOT_ACTIVATED")

    def test_missing_inventory_reference_rejects(self):
        del self.fixture.inventory[self.fixture.hashes["SOURCE_PERMISSION"]]
        with self.assertRaisesRegex(IntegrityError, "absent from the reviewed inventory"):
            self.fixture.run()

    def test_missing_file_rejects(self):
        f = self.fixture
        (self.root / f.inventory[f.hashes["HOSTED_RAW_RECOVERY"]]["path"]).unlink()
        with self.assertRaisesRegex(IntegrityError, "missing or not regular"):
            f.run()

    def test_wrong_semantic_kind_rejects_even_with_valid_bytes(self):
        f = self.fixture
        f.inventory[f.hashes["SOURCE_PERMISSION"]]["kind"] = "RAW_BACKEND_REVIEW"
        with self.assertRaisesRegex(IntegrityError, "wrong semantic kind"):
            f.run()

    def test_schema_contradiction_rejects_after_valid_rehash(self):
        f = self.fixture
        body = deepcopy(f.bodies["SOURCE_PERMISSION"])
        body["schema_version"] = "fictional-unrelated-report-v1"
        f.replace("SOURCE_PERMISSION", body)
        with self.assertRaisesRegex(IntegrityError, "schema differs"):
            f.run()

    def test_context_contradictions_reject_after_valid_rehash(self):
        for field, wrong in (("repository", "another/repository"), ("records_branch", "main"),
                             ("reviewed_commit", "2" * 40), ("recipient_certificate_sha256", "b" * 64),
                             ("private_key_secret", "SOME_OTHER_SECRET"),
                             ("plan_id", "c" * 64), ("producer_binding_id", "d" * 64)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                f = Fixture(Path(directory))
                body = deepcopy(f.bodies["ACTIVATION_APPROVAL"])
                body["subject"][field] = wrong
                f.replace("ACTIVATION_APPROVAL", body)
                with self.assertRaisesRegex(IntegrityError, "contradicts the exact " + field):
                    f.run()

    def test_semantic_contradiction_and_boolean_coercion_reject(self):
        for wrong in (False, 1):
            with self.subTest(wrong=wrong), tempfile.TemporaryDirectory() as directory:
                f = Fixture(Path(directory))
                body = deepcopy(f.bodies["SOURCE_PERMISSION"])
                body["decision"]["matches_reviewed_expectation"] = wrong
                f.replace("SOURCE_PERMISSION", body)
                with self.assertRaisesRegex(IntegrityError, "semantic expectation"):
                    f.run()

    def test_wrong_supplied_destination_certificate_or_producer_rejects(self):
        f = self.fixture
        for options in ({"records_branch": BRANCH + "-wrong"}, {"certificate_sha256": "f" * 64}):
            with self.subTest(options=options), self.assertRaises(IntegrityError):
                f.run(**options)
        with self.assertRaisesRegex(IntegrityError, "exact producer or destination"):
            admission.resolve_raw_admission(f.raw, receipt_root=self.root, inventory=f.inventory,
                producer_commit="e" * 40, records_branch=BRANCH, certificate_sha256=CERTIFICATE)

    def test_wrong_plan_and_unverified_binding_reject(self):
        f = self.fixture
        plan = deepcopy(f.plan)
        plan["registered_at"] = "2026-10-21T00:00:00.000000Z"
        f.plan = reseal(plan, "plan_id")
        with self.assertRaisesRegex(IntegrityError, "exact reviewed source/plan"):
            f.run()
        f.plan = self.fixture.plan = read_receipt(ROOT / "evidence/operational/ops002-plan.json")
        f.binding["commit"] = None
        f.binding["verification"] = "LOCAL_DIAGNOSTIC_SOURCE"
        f.binding = reseal(f.binding, "binding_id")
        with self.assertRaisesRegex(IntegrityError, "exact reviewed source/plan"):
            f.run()

    def test_file_corruption_and_wrong_payload_hash_reject(self):
        f = self.fixture
        path = self.root / f.inventory[f.hashes["SOURCE_PERMISSION"]]["path"]
        original = path.read_bytes()
        envelope = {"schema_version": RECEIPT_SCHEMA, "hash_format": HASH_FORMAT,
                    "payload_sha256": "0" * 64, "payload": f.bodies["SOURCE_PERMISSION"]}
        path.write_bytes(canonical(envelope))
        with self.assertRaisesRegex(IntegrityError, "checksum mismatch"):
            f.run()
        body = deepcopy(f.bodies["SOURCE_PERMISSION"])
        body["extra"] = "checksum-consistent replacement"
        envelope.update(payload=body, payload_sha256=digest(body))
        path.write_bytes(canonical(envelope))
        with self.assertRaisesRegex(IntegrityError, "payload hash differs"):
            f.run()
        path.write_bytes(original)

    def test_paths_must_stay_beneath_root_without_symlinks(self):
        f = self.fixture
        item = f.inventory[f.hashes["SOURCE_PERMISSION"]]
        original = item["path"]
        for path in ("../outside.json", "/tmp/outside.json", "./receipts/x.json",
                     "receipts//x.json", ".git/config.json", "receipts\\x.json", "receipts/\x00.json"):
            with self.subTest(path=path):
                item["path"] = path
                with self.assertRaises(IntegrityError):
                    f.run()
        item["path"] = original
        (self.root / "alias").symlink_to(self.root / "receipts", target_is_directory=True)
        item["path"] = "alias/" + Path(original).name
        with self.assertRaisesRegex(IntegrityError, "symlink"):
            f.run()
        item["path"] = original
        alias = self.root / "leaf.json"
        alias.symlink_to(self.root / original)
        item["path"] = "leaf.json"
        with self.assertRaisesRegex(IntegrityError, "symlink"):
            f.run()

    def test_root_replacement_and_invalid_root_fail_with_typed_errors(self):
        candidate = self.root / "candidate"
        candidate.mkdir()
        f = Fixture(candidate)
        resolver = admission._Resolver(candidate, f.inventory, f.context)
        old = self.root / "original-candidate"
        candidate.rename(old)
        shutil.copytree(old, candidate)
        with self.assertRaisesRegex(IntegrityError, "original receipt root was replaced"):
            resolver.resolve(f.hashes["SOURCE_PERMISSION"], "SOURCE_PERMISSION")
        with self.assertRaises(IntegrityError):
            self.fixture.run(receipt_root=str(self.root) + "\x00")

    def test_leaf_symlink_swap_at_open_cannot_read_outside_root(self):
        f = self.fixture
        item = f.inventory[f.hashes["SOURCE_PERMISSION"]]
        path = self.root / item["path"]
        with tempfile.TemporaryDirectory() as outside_directory:
            outside = Path(outside_directory) / "outside.json"
            outside.write_bytes(path.read_bytes())
            real_open = admission.os.open
            swapped = False

            def swap_leaf(name, flags, *args, **kwargs):
                nonlocal swapped
                if name == path.name and kwargs.get("dir_fd") is not None and not swapped:
                    swapped = True
                    path.unlink()
                    path.symlink_to(outside)
                return real_open(name, flags, *args, **kwargs)

            with mock.patch.object(admission.os, "open", side_effect=swap_leaf), \
                 self.assertRaisesRegex(IntegrityError, "symlink"):
                f.run()
            self.assertTrue(swapped)

    def test_parent_symlink_swap_at_open_cannot_redirect_traversal(self):
        f = self.fixture
        parent = self.root / "receipts"
        with tempfile.TemporaryDirectory() as outside_directory:
            outside = Path(outside_directory) / "receipts"
            shutil.copytree(parent, outside)
            real_open = admission.os.open
            swapped = False

            def swap_parent(name, flags, *args, **kwargs):
                nonlocal swapped
                if name == "receipts" and kwargs.get("dir_fd") is not None and not swapped:
                    swapped = True
                    parent.rename(self.root / "held-receipts")
                    parent.symlink_to(outside, target_is_directory=True)
                return real_open(name, flags, *args, **kwargs)

            with mock.patch.object(admission.os, "open", side_effect=swap_parent), \
                 self.assertRaisesRegex(IntegrityError, "symlink"):
                f.run()
            self.assertTrue(swapped)

    def test_disappearance_and_fifo_replacement_during_open_fail_without_blocking(self):
        for replacement in ("missing", "fifo"):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as directory:
                f = Fixture(Path(directory))
                path = f.root / f.inventory[f.hashes["SOURCE_PERMISSION"]]["path"]
                real_open = admission.os.open
                swapped = False

                def replace_leaf(name, flags, *args, **kwargs):
                    nonlocal swapped
                    if name == path.name and kwargs.get("dir_fd") is not None and not swapped:
                        swapped = True
                        path.unlink()
                        if replacement == "fifo":
                            os.mkfifo(path)
                    return real_open(name, flags, *args, **kwargs)

                with mock.patch.object(admission.os, "open", side_effect=replace_leaf), \
                     self.assertRaisesRegex(IntegrityError, "missing or not regular"):
                    f.run()
                self.assertTrue(swapped)

    def test_duplicate_path_missing_binding_and_unknown_inventory_fields_reject(self):
        f = self.fixture
        saved = deepcopy(f.inventory)
        source = f.inventory[f.hashes["SOURCE_PERMISSION"]]
        source["path"] = f.inventory[f.hashes["RAW_BACKEND_REVIEW"]]["path"]
        with self.assertRaisesRegex(IntegrityError, "reuse one receipt path"):
            f.run()
        f.inventory = deepcopy(saved)
        del f.inventory[f.hashes["SOURCE_PERMISSION"]]["bindings"]["records_branch"]
        with self.assertRaisesRegex(IntegrityError, "context bindings differ"):
            f.run()
        f.inventory = deepcopy(saved)
        f.inventory[f.hashes["SOURCE_PERMISSION"]]["self_authorized"] = True
        with self.assertRaisesRegex(IntegrityError, "invalid inventory entry"):
            f.run()

    def test_missing_and_malformed_pointer_reject(self):
        f = self.fixture
        item = f.inventory[f.hashes["SOURCE_PERMISSION"]]
        for pointer in ("/missing", "/subject/~2bad", "/subject/reviewed_commit/extra"):
            with self.subTest(pointer=pointer):
                item["bindings"]["repository"] = pointer
                with self.assertRaises(IntegrityError):
                    f.run()

    def test_bounded_receipt_and_inventory_reject_oversize(self):
        f = self.fixture
        body = deepcopy(f.bodies["SOURCE_PERMISSION"])
        body["oversize"] = "x" * (16 * 1024)
        f.replace("SOURCE_PERMISSION", body)
        with self.assertRaisesRegex(IntegrityError, "byte limit"):
            f.run()
        f.inventory[f.hashes["SOURCE_PERMISSION"]]["assertions"]["/oversize"] = "x" * (32 * 1024)
        with self.assertRaisesRegex(IntegrityError, "inventory exceeds"):
            f.run()

    def test_change_after_first_read_is_detected_by_final_readback(self):
        f = self.fixture
        path = self.root / f.inventory[f.hashes["ACTIVATION_APPROVAL"]]["path"]
        real_read = admission._Resolver._read_bound_receipt
        changed = False

        def change_after_read(resolver, relative, **kwargs):
            nonlocal changed
            result = real_read(resolver, relative, **kwargs)
            if resolver.root / relative == path and not changed:
                changed = True
                replacement = {**result, "unexpected_revision": True}
                envelope = {"schema_version": RECEIPT_SCHEMA, "hash_format": HASH_FORMAT,
                            "payload_sha256": digest(replacement), "payload": replacement}
                path.write_bytes(canonical(envelope))
            return result

        with mock.patch.object(admission._Resolver, "_read_bound_receipt", change_after_read), \
             self.assertRaisesRegex(IntegrityError, "payload hash differs"):
            f.run()

    def test_synthetic_host_evidence_cannot_be_relabelled_genuine(self):
        f = self.fixture
        body = deepcopy(f.bodies["HOSTED_DIAGNOSTIC"])
        body["mode"] = "REAL_TIME_CAPTURED"
        item = deepcopy(f.inventory[f.hashes["HOSTED_DIAGNOSTIC"]])
        item["assertions"]["/mode"] = "REAL_TIME_CAPTURED"
        f.replace("HOSTED_DIAGNOSTIC", body, item=item)
        with self.assertRaisesRegex(IntegrityError, "explicit synthetic meaning"):
            f.run()

    def test_retained_real_host_diagnostic_stays_synthetic_in_candidate_result(self):
        # Read existing evidence only. This executes no diagnostic or model.
        report = read_receipt(ROOT / "evidence/operational/hosted-diagnostic-39536525048.json")
        # Its original diagnostic binding remains unchanged. The test's candidate
        # uses a separately shaped commit binding with exactly the same file map.
        binding = deepcopy(report["producer_binding"])
        binding.update(commit=report["source_commit"], verification="VERIFIED_COMMIT")
        binding = reseal(binding, "binding_id")
        with tempfile.TemporaryDirectory() as directory:
            f = Fixture(Path(directory), binding=binding)
            item = {"path": "unused.json", "kind": "HOSTED_DIAGNOSTIC",
                    "schema_version": report["schema_version"],
                    "bindings": {"protocol_id": "/producer_binding/protocol_id",
                                 "reviewed_commit": "/source_commit",
                                 "producer_files": "/producer_binding/files"},
                    "assertions": {"/mode": "SOFTWARE_DIAGNOSTIC_NON_ISSUANCE",
                                   "/status": "PASS_FULL_COHORT_OPERATIONAL_DIAGNOSTIC"}}
            f.replace("HOSTED_DIAGNOSTIC", report, item=item)
            result = f.run()
            self.assertIn(digest(report), result["resolved_receipts"])
            self.assertEqual(result["resolved_receipts"][digest(report)]["evidence_lane"],
                             "SOFTWARE_DIAGNOSTIC_NON_ISSUANCE")
            self.assertIs(result["genuine_host_path_verified"], False)
            self.assertIs(result["authorized"], False)
            self.assertEqual(result["activation"], "NOT_ACTIVATED")


if __name__ == "__main__":
    unittest.main()

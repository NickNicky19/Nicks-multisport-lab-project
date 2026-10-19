"""Synthetic integrity checks: these are not sports performance observations."""
import copy
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab.integrity import (
    HASH_FORMAT, IntegrityError, canonical, digest, load_json, read_receipt,
    stamp, utc, write_receipt,
)


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "receipt.json"

    def test_duplicate_json_keys_are_rejected_at_any_depth(self):
        for raw in ('{"x":1,"x":2}', '{"outer":{"x":1,"x":2}}'):
            with self.subTest(raw=raw):
                self.path.write_text(raw, encoding="utf-8")
                with self.assertRaises(IntegrityError):
                    load_json(self.path)

    def test_nonfinite_json_including_overflowing_exponents_is_rejected(self):
        for number in ("NaN", "Infinity", "-Infinity", "1e999"):
            with self.subTest(number=number):
                self.path.write_text('{"x":' + number + '}', encoding="utf-8")
                with self.assertRaises(IntegrityError):
                    load_json(self.path)
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaises(IntegrityError):
                canonical({"x": [value]})

    def test_canonical_json_does_not_silently_convert_key_or_value_types(self):
        with self.assertRaises(IntegrityError):
            canonical({1: "number-key", "1": "string-key"})
        with self.assertRaises(IntegrityError):
            canonical({"tuple": (1, 2)})
        self.assertEqual(digest({"b": 2, "a": 1}), digest({"a": 1, "b": 2}))
        self.assertNotEqual(digest({"x": 1}), digest({"x": True}))

    def test_timezone_required_and_microseconds_preserved(self):
        with self.assertRaises(IntegrityError):
            utc(datetime(2026, 1, 1))
        with self.assertRaises(IntegrityError):
            utc("2026-01-01T00:00:00.123456")
        local = datetime(2026, 1, 1, 12, 0, 0, 123456,
                         tzinfo=timezone(timedelta(hours=-6)))
        self.assertEqual(stamp(local), "2026-01-01T18:00:00.123456Z")
        self.assertEqual(utc(stamp(local)), local)

    def test_create_then_identical_retry_preserves_existing_bytes(self):
        payload = {"fixture_only": True, "rows": [{"x": 1}],
                   "captured_at": "2026-01-01T18:00:00.123456Z"}
        self.assertTrue(write_receipt(self.path, payload))
        before = self.path.read_bytes()
        self.assertFalse(write_receipt(self.path, copy.deepcopy(payload)))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(read_receipt(self.path), payload)
        envelope = json.loads(before)
        self.assertEqual(envelope["hash_format"], HASH_FORMAT)
        self.assertNotIn("prospective", envelope)

    def test_every_payload_field_participates_in_conflict_detection(self):
        payload = {"rows": [{"value": 1}], "captured_at": "first", "code_commit": "first"}
        write_receipt(self.path, payload)
        before = self.path.read_bytes()
        changes = ({"rows": [{"value": 2}]}, {"captured_at": "later"},
                   {"code_commit": "other"}, {"rows": [{"value": True}]})
        for change in changes:
            with self.subTest(change=change):
                with self.assertRaises(IntegrityError):
                    write_receipt(self.path, payload | change)
                self.assertEqual(self.path.read_bytes(), before)

    def test_mutated_payload_hash_mismatch_is_not_repaired_by_retry(self):
        payload = {"rows": [{"value": 1}]}
        write_receipt(self.path, payload)
        envelope = json.loads(self.path.read_bytes())
        envelope["payload"]["rows"][0]["value"] = 2
        self.path.write_bytes(canonical(envelope))
        corrupted = self.path.read_bytes()
        with self.assertRaises(IntegrityError):
            read_receipt(self.path)
        with self.assertRaises(IntegrityError):
            write_receipt(self.path, payload)
        self.assertEqual(self.path.read_bytes(), corrupted)

    def test_unsupported_wire_hash_label_and_extra_labels_are_rejected(self):
        write_receipt(self.path, {"fixture_only": True})
        envelope = json.loads(self.path.read_bytes())
        for change in ({"hash_format": "sha256-raw-http-bytes"}, {"prospective": True}):
            self.path.write_bytes(canonical(envelope | change))
            with self.assertRaises(IntegrityError):
                read_receipt(self.path)

    def test_byte_limits_apply_before_create_and_while_reading(self):
        with self.assertRaises(IntegrityError):
            write_receipt(self.path, {"long": "x" * 200}, max_bytes=100)
        self.assertFalse(self.path.exists())
        self.path.write_text(" " * 101, encoding="utf-8")
        with self.assertRaises(IntegrityError):
            load_json(self.path, max_bytes=100)
        for limit in (0, -1, True):
            with self.assertRaises(IntegrityError):
                write_receipt(self.path, {}, max_bytes=limit)

    def test_symlink_is_not_accepted_as_a_receipt(self):
        original = self.path.with_name("original.json")
        write_receipt(original, {"fixture_only": True})
        self.path.symlink_to(original)
        with self.assertRaises(IntegrityError):
            read_receipt(self.path)
        with self.assertRaises(IntegrityError):
            write_receipt(self.path, {"fixture_only": True})

    def test_failed_atomic_publication_leaves_no_partial_receipt(self):
        with patch("multisport_lab.integrity.os.link", side_effect=PermissionError("fixture failure")):
            with self.assertRaises(PermissionError):
                write_receipt(self.path, {"fixture_only": True})
        self.assertFalse(self.path.exists())
        self.assertEqual(list(self.path.parent.glob(".receipt-*")), [])


if __name__ == "__main__":
    unittest.main()

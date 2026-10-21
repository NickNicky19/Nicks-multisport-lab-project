"""Actual shared-capacity and frozen-source guards, without provider/model calls."""
from pathlib import Path
import unittest
from unittest.mock import patch

from multisport_lab.integrity import IntegrityError
from multisport_lab import operational_preflight as preflight


class PreparationGuards(unittest.TestCase):
    def test_one_event_plus_one_offer_counts_all_allocations(self):
        base = {"maximum_records": 98, "maximum_bytes": 4000000}
        with patch.object(preflight.pilot, "capacity_report", return_value=base):
            result = preflight.combined_capacity("unused")
        self.assertEqual(result["maximum_files"], 117)
        self.assertEqual(result["maximum_encoded_bytes"], 5425408)
        self.assertEqual(result["hosted_report_encoded_ceiling"], 1048576)
        self.assertEqual(result["reserved_independent_audit_files"], 2)
        self.assertEqual(result["independent_audit_encoded_ceiling"], 65536)
        self.assertEqual(result["raw_archive_eight_capture_reserve_bytes"], 17039360)
        self.assertFalse(result["raw_plaintext_publication"])

    def test_offer_metadata_can_exhaust_record_budget(self):
        with patch.object(preflight.pilot, "capacity_report", return_value={"maximum_records": 496, "maximum_bytes": 4000000}):
            with self.assertRaisesRegex(IntegrityError, "allocation exceeds"):
                preflight.combined_capacity("unused")

    def test_independent_audits_use_two_real_file_slots_at_the_boundary(self):
        with patch.object(preflight.pilot, "capacity_report", return_value={"maximum_records": 493, "maximum_bytes": 4000000}):
            self.assertEqual(preflight.combined_capacity("unused")["maximum_files"], 512)
        with patch.object(preflight.pilot, "capacity_report", return_value={"maximum_records": 494, "maximum_bytes": 4000000}):
            with self.assertRaisesRegex(IntegrityError, "allocation exceeds"):
                preflight.combined_capacity("unused")

    def test_offer_metadata_can_exhaust_byte_budget(self):
        with patch.object(preflight.pilot, "capacity_report", return_value={"maximum_records": 98, "maximum_bytes": 33400000}):
            with self.assertRaisesRegex(IntegrityError, "allocation exceeds"):
                preflight.combined_capacity("unused")

    def test_reviewed_original_pilot_bytes_still_exact(self):
        root = Path(__file__).resolve().parents[1]
        result = preflight.check_frozen_producer(root)
        self.assertEqual(len(result), 9)
        self.assertEqual(set(result), set(preflight.FROZEN_FILES))


if __name__ == "__main__":
    unittest.main()

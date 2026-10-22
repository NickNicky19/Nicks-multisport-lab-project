"""Tiny transport-fixture checks; no full-load measurement in the test suite."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from multisport_lab import pros004_load_diagnostic as load
from multisport_lab.integrity import IntegrityError, read_receipt


class Pros004LoadDiagnosticTests(unittest.TestCase):
    def test_small_explicit_generic_transport_roundtrip_is_not_typed_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);output=root/'measurement.json'
            result=load.run_diagnostic(output,work_root=root/'work',small_test=True,
                records=4,encoded_bytes=16*1024)
            self.assertEqual(result,read_receipt(output))
            self.assertEqual(result['load']['records'],4)
            self.assertEqual(result['load']['encoded_ledger_bytes'],16*1024)
            self.assertEqual(result['load']['typed_pros004_records'],0)
            self.assertEqual(result['measurement'],'SMALL_SYNTHETIC_TEST')
            self.assertEqual(set(result['source_sha256']),
                set(load.PRODUCER_SOURCE_FILES)|{'multisport_lab/pros004_load_diagnostic.py'})
            self.assertFalse(result['claims']['typed_full_study_execution_timing'])
            self.assertFalse(result['claims']['primary_remote_durability'])
            self.assertFalse(result['claims']['comparative_evaluation'])
            self.assertEqual(result['claims']['genuine_issuance'],0)
            self.assertTrue(result['transport']['independent_fetch_and_full_byte_readback'])
            self.assertTrue((root/'work/bare.git').is_dir())
            with self.assertRaisesRegex(IntegrityError,'output must be new'):
                load.run_diagnostic(output,small_test=True,records=4,encoded_bytes=16*1024)

    def test_dimensions_cannot_silently_shrink_or_raise_limits(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for records,size,small in ((4,16384,False),(513,16384,True),(499,33554433,True),
                                       (4,1,True),(True,16384,True)):
                with self.subTest(records=records,size=size,small=small),self.assertRaises(IntegrityError):
                    load.build_transport_store(root/'source',records=records,encoded_bytes=size,small_test=small)

    def test_optimized_python_keeps_exact_load_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            result=subprocess.run([sys.executable,'-O','-c',
                'from multisport_lab.pros004_load_diagnostic import build_transport_store; '
                'build_transport_store('+repr(str(Path(folder)/'source'))+', records=4, encoded_bytes=16384)'],
                cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('cannot silently change',result.stderr)
            self.assertNotIn('AssertionError',result.stderr)


if __name__=='__main__':
    unittest.main()

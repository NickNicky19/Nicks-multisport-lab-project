"""Diagnostic orchestration safeguards; no full-law execution or source access."""
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from multisport_lab import pros004_inputs as inputs
from multisport_lab import pros004_readiness as readiness
from multisport_lab.integrity import IntegrityError
from multisport_lab.ledger import Ledger, LedgerRef


class Pros004ReadinessDriverTests(unittest.TestCase):
    def test_invented_source_pack_is_explicit_diagnostic_and_restores_actual_clock(self):
        actual_clock = inputs._now
        body = readiness.synthetic_event_pack(LedgerRef('research_inputs','a'*64,'b'*64),['10','20','30','40'])
        self.assertEqual(body['mode'],'SYNTHETIC_DIAGNOSTIC')
        self.assertEqual(body['event']['event_id'],'999000004')
        self.assertEqual(len(body['candidates']),4)
        self.assertTrue(all(p['player_label'].startswith('DIAGNOSTIC subject ') for p in body['candidates']))
        self.assertEqual(body['imported_at'],'2026-10-21T22:45:00.000000Z')
        self.assertIs(inputs._now,actual_clock)
        self.assertLess(abs((inputs._now()-datetime.now(timezone.utc)).total_seconds()),10)

    def test_diagnostic_never_reuses_nonempty_state_or_writes_in_git_worktree(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'retained.txt').write_text('preserve')
            with self.assertRaisesRegex(IntegrityError,'new nonexistent'):
                readiness._new_store_root(root)
            self.assertEqual((root/'retained.txt').read_text(),'preserve')
        with self.assertRaisesRegex(IntegrityError,'new nonexistent'):
            readiness._new_store_root(Path(__file__).resolve().parents[1])

    def test_baseline_copy_preserves_existing_receipt_bytes_and_detects_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=root/'source'
            original=Ledger(source).append('input_captures','synthetic-existing-baseline',
                {'label':'Existing independent evidence; preserve original bytes'})
            (source/'records'/'README.md').write_text('Ledger documentation; not an evidence receipt')
            inventory=readiness._existing_inventory(source)
            destination=readiness._new_store_root(root/'copy')
            copied=readiness._copy_baseline(source,destination,inventory,root/'snapshot')
            self.assertEqual(copied['original_records'],1)
            self.assertTrue(copied['all_original_bytes_preserved'])
            self.assertEqual(Ledger(source).read(original),Ledger(destination.root).read(original))
            path=destination.ledger._path(original.kind,original.record_id)
            original_bytes=path.read_bytes()
            self.assertEqual(original_bytes,Ledger(source)._path(original.kind,original.record_id).read_bytes())
            path.write_bytes(original_bytes+b' ')
            with self.assertRaisesRegex(IntegrityError,'original baseline receipt changed'):
                readiness._verify_baseline_files(destination.root,inventory)

    def test_malformed_or_nonfixed_diagnostic_cohort_fails_explicitly(self):
        ref=LedgerRef('research_inputs','a'*64,'b'*64)
        for ids in (['10','20','30'],['10','20','30','30'],['20','10','30','40'],['x','20','30','40'],[10,'20','30','40']):
            with self.assertRaisesRegex(IntegrityError,'four unique sorted numeric'):
                readiness.synthetic_event_pack(ref,ids)


if __name__ == '__main__':
    unittest.main()

"""Diagnostic orchestration safeguards; no full-law execution or source access."""
from contextlib import ExitStack
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import pros004_inputs as inputs
from multisport_lab import pros004_readiness as readiness
from multisport_lab import pregame_sources
from multisport_lab.integrity import IntegrityError
from multisport_lab.ledger import Ledger, LedgerRef
from test_pregame_sources import tiny_history, provenance


class Pros004ReadinessDriverTests(unittest.TestCase):
    def test_advancing_clock_preserves_actual_delayed_completion_and_restores_modules(self):
        elapsed=[100.0]
        clock=readiness.AdvancingDiagnosticClock(readiness.GENERATION_CLOCK,monotonic=lambda:elapsed[0])
        original=inputs._now
        with readiness._advancing_clock(clock):
            self.assertEqual(inputs._now(),readiness.GENERATION_CLOCK)
            elapsed[0]+=121
            self.assertEqual(inputs._now(),readiness.GENERATION_CLOCK+timedelta(seconds=121))
            elapsed[0]-=122
            with self.assertRaisesRegex(IntegrityError,'moved backwards'):
                inputs._now()
        self.assertIs(inputs._now,original)

    def test_restart_comparison_ignores_only_observation_and_transport_metadata(self):
        original={'retained_models':2,'recovered_at':'first','final_checkpoint':{'clock':'first'}}
        recovered={'retained_models':2,'recovered_at':'later'}
        self.assertEqual(readiness._recovery_content(original),readiness._recovery_content(recovered))
        recovered['retained_models']=1
        self.assertNotEqual(readiness._recovery_content(original),readiness._recovery_content(recovered))

    def test_late_event_proof_publication_retains_input_and_never_starts_generation(self):
        baseline_forecasts=readiness._existing_inventory(Path(__file__).resolve().parents[1])['records_by_kind']['forecasts']
        base=tiny_history()[0]
        rows=[replace(base,event_id=str(1000+i),player_id=str(10*(i+1))) for i in range(4)]
        raw=pregame_sources._panel_bytes(rows);source=provenance(rows)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root=Path(folder)
            for name,value in [('PANEL_ROWS',4),('PANEL_BYTES',len(raw)),
                    ('PANEL_SHA256',hashlib.sha256(raw).hexdigest())]:
                stack.enter_context(patch.object(inputs,name,value))
            stack.enter_context(patch.object(inputs,'_original_provenance',return_value=source))
            # Invented history is imported in this test's fixed input phase;
            # actual-day import would be future-dated inside that simulation.
            stack.enter_context(patch.object(inputs,'_now',return_value=readiness.INPUT_CLOCK))
            stack.enter_context(patch.object(pregame_sources,'history_from_input_record',
                return_value=(pregame_sources.compact_history(rows),source)))
            stack.enter_context(patch.object(readiness.records.Pros004Store,'finalize_checkpoint',
                return_value={'timely':False,'metadata_publication_status':'LATE_METADATA_PUBLICATION'}))
            generation=stack.enter_context(patch.object(readiness.producer,'generate_forecast',
                side_effect=AssertionError('late input proof must not permit generation')))
            with self.assertRaisesRegex(IntegrityError,'missed selection close'):
                readiness.run_diagnostic(output=root/'report.json',store_root=root/'retained')
            generation.assert_not_called()
            self.assertTrue(list((root/'retained/records/research_inputs').glob('*.json')))
            self.assertEqual(len(list((root/'retained/records/forecasts').glob('*.json'))),baseline_forecasts)
            self.assertFalse((root/'report.json').exists())

    def test_tiny_joint_driver_uses_actual_git_push_fetch_and_completion_journal(self):
        # Four invented retained rows exercise orchestration and original-byte
        # recovery; this is not the full-history resource diagnostic.
        base=tiny_history()[0]
        rows=[replace(base,event_id=str(1000+i),player_id=str(10*(i+1))) for i in range(4)]
        raw=pregame_sources._panel_bytes(rows);source=provenance(rows)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root=Path(folder)
            for name,value in [('PANEL_ROWS',4),('PANEL_BYTES',len(raw)),
                    ('PANEL_SHA256',hashlib.sha256(raw).hexdigest())]:
                stack.enter_context(patch.object(inputs,name,value))
            stack.enter_context(patch.object(inputs,'_original_provenance',return_value=source))
            stack.enter_context(patch.object(inputs,'_now',return_value=readiness.INPUT_CLOCK))
            stack.enter_context(patch.object(pregame_sources,'history_from_input_record',
                return_value=(pregame_sources.compact_history(rows),source)))
            report=readiness.run_diagnostic(output=root/'report.json',store_root=root/'retained')
            self.assertEqual(report['schema_version'],'nba-pros004-readiness-report-v3')
            self.assertEqual(report['diagnostic_status'],'PASS')
            self.assertEqual(report['history']['rows'],4)
            self.assertEqual(report['recovery']['retained_models'],8)
            self.assertEqual(report['recovery']['timing_complete_models'],8)
            self.assertEqual(report['recovery']['eligible_models'],0)
            self.assertTrue(report['recovery']['remote_recovery'])
            self.assertTrue(report['recovery']['input_admission_recovered'])
            self.assertFalse(report['recovery']['github_recovery'])
            self.assertEqual(report['recovery']['transport']['transport'],'ISOLATED_LOCAL_BARE_GIT')
            self.assertGreater(len(report['performance']['git_checkpoint_actual_seconds']),8)
            self.assertTrue(report['recovery']['final_checkpoint']['timely'])
            self.assertTrue(report['event_input']['final_checkpoint']['timely'])
            self.assertEqual(report['event_input']['final_checkpoint']['references'],
                [report['event_input']['event_ref']])
            self.assertTrue(report['event_input']['admission_final_checkpoint']['timely'])
            self.assertLessEqual(report['event_input']['admission_encoded_envelope_bytes'],8192)
            self.assertEqual(report['maximum_study_timing']['status'],'NOT_MEASURED_AT_MAXIMUM_LEDGER_LOAD')
            self.assertEqual(report['evidence']['genuine_issuance'],0)
            self.assertGreater(report['performance']['cohort_generate_verify_persist_actual_seconds'],0)
            self.assertTrue((root/'retained/evidence/pros004/completion-journal.jsonl').is_file())

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

"""Invented sources, bounded synthetic timing and isolated local Git only."""
from dataclasses import replace
from datetime import timedelta
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import operating_diagnostic as diagnostic,operational_pilot as op,pregame_sources as source
from multisport_lab.integrity import IntegrityError,digest,read_receipt
from multisport_lab.ledger import Ledger
from test_pregame_sources import pack_fixture,tiny_history,provenance,NOW as OLD_NOW
from test_pros004_remote import RemoteFixture


class OperatingDiagnosticTests(unittest.TestCase):
    def test_final_retention_deadline_total_cpu_memory_and_missing_peer_fail_closed(self):
        evidence={'retained_originals':8,'eligible_originals':8}
        kwargs=dict(restart=evidence,exact_remote=True,cohort_seconds=295,total_seconds=900,peak_rss_kib=512*1024)
        self.assertEqual(diagnostic.completion_failures(**kwargs),[])
        for key,value in (('cohort_seconds',295.000001),('total_seconds',900.000001),
                          ('peak_rss_kib',512*1024+1),('exact_remote',False),
                          ('restart',{'retained_originals':8,'eligible_originals':7})):
            with self.subTest(key=key):
                self.assertTrue(diagnostic.completion_failures(**{**kwargs,key:value}))

    def test_explicit_authorization_and_pin_are_checked_before_creating_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for kwargs in ({},{'authorize_diagnostic_push':True}):
                with self.assertRaises(IntegrityError):
                    diagnostic.run_diagnostic(output=root/'report.json',store_root=root/'store',writer_root=root/'writer',**kwargs)
                self.assertFalse((root/'store').exists())

    def test_cli_partial_returns_failure_and_retains_existing_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'receipt.json'
            from multisport_lab.integrity import write_receipt
            report={'status':'PARTIAL_OR_FAILED_DIAGNOSTIC','genuine_issuance':0}
            write_receipt(path,report);original=path.read_bytes()
            args=['diagnostic','--output',str(path),'--store-root',str(root/'store'),
                '--writer-root',str(root/'writer'),'--producer-commit','a'*40,'--authorize-diagnostic-push']
            with patch.object(sys,'argv',args),patch.object(diagnostic,'run_diagnostic',return_value=report):
                with self.assertRaises(SystemExit) as failure:diagnostic.main()
            self.assertEqual(failure.exception.code,2)
            self.assertEqual(path.read_bytes(),original)

    def test_cli_unreadable_partial_writes_factual_unadmitted_error_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);store=root/'store';store.mkdir();(store/'interrupted').write_bytes(b'actual partial bytes')
            path=root/'report.json'
            args=['diagnostic','--output',str(path),'--store-root',str(store),'--writer-root',str(root/'writer'),
                '--producer-commit','a'*40,'--authorize-diagnostic-push']
            with patch.object(sys,'argv',args),patch.object(diagnostic,'run_diagnostic',side_effect=IntegrityError('invalid source pin')):
                with self.assertRaises(SystemExit):diagnostic.main()
            report=read_receipt(path)
            self.assertFalse(report['recovery_admitted']);self.assertEqual(report['genuine_issuance'],0)
            self.assertEqual(report['unverified_retained_files'][0]['raw_sha256'],hashlib.sha256(b'actual partial bytes').hexdigest())

    def test_full_toy_driver_uses_real_git_and_new_operating_path_without_sources_or_scores(self):
        f=RemoteFixture(self)
        seed=f.root/'tiny-baseline';seed.mkdir()
        base=tiny_history()[0]
        rows=[replace(base,event_id=str(1000+i),player_id=str(10*(i+1)),
            event_start=base.event_start+timedelta(days=i)) for i in range(4)]
        p=provenance(rows);panel=source._panel_bytes(rows)
        with patch.object(source,'_now',return_value=OLD_NOW):pack=pack_fixture()
        pack['history']=source.compact_history(rows);pack['history_provenance']=p
        pack['sourcepack_id']=digest({k:v for k,v in pack.items() if k!='sourcepack_id'})
        original_copy=diagnostic._copy_baseline;original_check=diagnostic._baseline_unchanged;original_git=diagnostic._git
        code=Path(diagnostic.__file__).resolve().parents[1]
        with patch.object(source,'PANEL_SHA',p['normalized_panel_sha256']):
            ref=Ledger(seed).append('research_inputs','research-inputs:'+digest(pack),{'source_pack':pack})
            with (patch.object(op,'PANEL_ROWS',len(rows)),patch.object(op,'PANEL_BYTES',len(panel)),
                  patch.object(op,'PANEL_SHA256',hashlib.sha256(panel).hexdigest()),
                  patch.object(op,'ORIGINAL_HISTORY_ID',ref.record_id),
                  patch.object(diagnostic,'_copy_baseline',side_effect=lambda _,target:original_copy(seed,target)),
                  patch.object(diagnostic,'_baseline_unchanged',side_effect=lambda root,expected:original_check(seed if root==code else root,expected)),
                  patch.object(diagnostic,'_git',side_effect=lambda args,root:f.base if args==['rev-parse','HEAD'] and root==code else original_git(args,root))):
                report=diagnostic.run_diagnostic(output=f.root/'report.json',store_root=f.root/'full-toy-store',
                    writer_root=f.root/'full-toy-writer',authorize_diagnostic_push=True,local_test_remote=f.remote)
        self.assertEqual(report['status'],'PASS_FULL_COHORT_OPERATIONAL_DIAGNOSTIC',str(report['failure']))
        self.assertEqual(report['history']['rows'],4)  # Explicit small software fixture, never real full-history evidence.
        self.assertEqual(report['independent_restart']['retained_originals'],8)
        self.assertEqual(report['independent_restart']['eligible_originals'],8)
        self.assertTrue(report['exact_remote_snapshot'])
        self.assertEqual(report['evidence']['live_source_captures'],0)
        self.assertEqual(report['evidence']['statistical_grades'],0)
        self.assertEqual(report['evidence']['genuine_issuance'],0)
        self.assertFalse(report['evidence']['activation'])
        self.assertEqual(len(report['performance']['paired_generation_and_verification']),4)
        batches=[item for item in report['transport']['operations'] if 'references' in item]
        self.assertEqual(len(batches),4)
        self.assertTrue(all(len(item['references']) == 2 for item in batches))
        self.assertEqual(len(report['transport']['operations']),11)
        self.assertFalse(report['transport']['atomic_pair_issuance'])


if __name__=='__main__':unittest.main()

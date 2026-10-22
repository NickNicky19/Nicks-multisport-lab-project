"""Synthetic append-only operation observations; never prospective issuance."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import pros004_completion as journal
from multisport_lab.integrity import IntegrityError, canonical, digest, stamp
from multisport_lab.ledger import LedgerRef

NOW=datetime(2026,10,21,12,tzinfo=timezone.utc)
REF=LedgerRef('forecasts','1'*64,'2'*64)
RAW='3'*64


def ack(reference=REF, *, completed=NOW):
    return {'schema_version':journal.ACK_SCHEMA,'reference':reference.to_record(),
        'remote_repository':journal.REPOSITORY,'remote_branch':'records/SYNTHETIC_ONLY',
        'remote_commit':'4'*40,'snapshot_sha256':'5'*64,
        'readback_raw_sha256':RAW,'remote_completed_at':stamp(completed)}


def append(root,reference=REF,**kwargs):
    values={'mode':'SYNTHETIC_DIAGNOSTIC','raw_sha256':RAW,
        'completed_at':NOW,'recorded_at':NOW}
    values.update(kwargs)
    return journal.append_completion(root,reference,**values)


class Pros004CompletionTests(unittest.TestCase):
    def test_exact_restart_chain_and_idempotent_original_clocks(self):
        with tempfile.TemporaryDirectory() as root:
            original=append(root)
            path=journal.journal_path(root);raw=path.read_bytes()
            # A retry reads the original observation rather than renewing it.
            self.assertEqual(append(root,completed_at=NOW+timedelta(seconds=10),
                recorded_at=NOW+timedelta(seconds=10)),original)
            self.assertEqual(path.read_bytes(),raw)
            remote=append(root,started_at=NOW,acknowledgment=ack())
            self.assertEqual(remote['previous_sha256'],original['entry_sha256'])
            self.assertEqual(journal.load_journal(root),[original,remote])
            inventory=journal.journal_inventory(root)
            self.assertEqual(inventory['entries'],2)
            self.assertEqual(inventory['files'],1)
            self.assertEqual(inventory['raw_sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
            with self.assertRaisesRegex(IntegrityError,'changed the original'):
                append(root,raw_sha256='6'*64)

    def test_torn_prefix_and_valid_hash_invalid_clock_are_never_repaired(self):
        with tempfile.TemporaryDirectory() as root:
            body=append(root);path=journal.journal_path(root)
            original=path.read_bytes();path.write_bytes(original[:-1])
            with self.assertRaisesRegex(IntegrityError,'interrupted'):
                journal.load_journal(root)
            with self.assertRaisesRegex(IntegrityError,'interrupted'):
                append(root)
            self.assertEqual(path.read_bytes(),original[:-1])
            changed=deepcopy(body);changed['recorded_at']=stamp(NOW-timedelta(seconds=1))
            changed['entry_sha256']=digest({k:v for k,v in changed.items() if k!='entry_sha256'})
            path.write_bytes(canonical(changed)+b'\n')
            with self.assertRaisesRegex(IntegrityError,'clocks'):
                journal.load_journal(root)

    def test_remote_identity_and_actual_operation_bounds_are_strict(self):
        for field,value in [('readback_raw_sha256','6'*64),('remote_repository','other/repository'),
                            ('remote_commit','short'),('remote_branch','x'*161),
                            ('remote_completed_at',stamp(NOW+timedelta(microseconds=1)))]:
            with self.subTest(field=field):
                changed=ack();changed[field]=value
                with self.assertRaises(IntegrityError):
                    journal.validate_acknowledgment(changed,REF,started_at=stamp(NOW),
                        completed_at=stamp(NOW),raw_sha256=RAW)
        with self.assertRaisesRegex(IntegrityError,'structured independent'):
            journal.validate_acknowledgment(True,REF,started_at=stamp(NOW),completed_at=stamp(NOW),raw_sha256=RAW)

    def test_entry_count_and_encoded_line_limits_fail_without_replacing_prefix(self):
        with tempfile.TemporaryDirectory() as root:
            append(root);path=journal.journal_path(root);original=path.read_bytes()
            other=LedgerRef('forecasts','7'*64,'8'*64)
            with patch.object(journal,'MAX_JOURNAL_ENTRIES',1):
                with self.assertRaisesRegex(IntegrityError,'entry budget'):
                    append(root,other)
            self.assertEqual(path.read_bytes(),original)
            with patch.object(journal,'MAX_ENTRY_BYTES',len(original)):
                # The local prefix still fits; the remote line is larger.
                with self.assertRaisesRegex(IntegrityError,'encoded line size'):
                    append(root,started_at=NOW,acknowledgment=ack())
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(journal.MAX_JOURNAL_BYTES,journal.MAX_JOURNAL_ENTRIES*journal.MAX_ENTRY_BYTES)

    def test_optimized_python_rejects_checksum_consistent_invalid_completion(self):
        with tempfile.TemporaryDirectory() as root:
            entry=append(root);entry['completed_at']=stamp(NOW+timedelta(seconds=1))
            entry['entry_sha256']=digest({k:v for k,v in entry.items() if k!='entry_sha256'})
            journal.journal_path(root).write_bytes(canonical(entry)+b'\n')
            code=("from multisport_lab.pros004_completion import load_journal; "
                  "from multisport_lab.integrity import IntegrityError; "
                  "import sys\ntry: load_journal(sys.argv[1])\n"
                  "except IntegrityError: print('REJECTED'); sys.exit(0)\n"
                  "raise RuntimeError('optimized verification admitted an invalid completion')")
            result=subprocess.run([sys.executable,'-O','-c',code,root],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.strip(),'REJECTED')


if __name__=='__main__':unittest.main()

"""Conservative generic-ledger transport load; never a PROS004 study execution.

The default is 499 explicitly synthetic generic receipts totaling 24 MiB. This
exceeds the 24,576,000-byte full-plan allowance while retaining the unchanged
512-record/32-MiB ledger caps. High-entropy padding avoids an all-zero compression
shortcut. These records are not forecasts, outcomes, grades or a replacement for
the full-history typed producer measurement. No source client, GitHub remote,
clock harness, model generator, scoring or activation path is called.

The actual Git checkpoint path pushes to a temporary local bare repository and
fetches into an independent object store before acknowledging exact bytes. A
retained work root permits examination after the diagnostic; temporary defaults
make no claim of ongoing primary durability or hosted-network performance.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import resource
import subprocess
import tempfile
import time

from .integrity import IntegrityError, canonical, digest, stamp, write_receipt
from .ledger import LedgerRef, MAX_LEDGER_BYTES, MAX_LEDGER_RECORDS
from .pros004_producer import SOURCE_FILES as PRODUCER_SOURCE_FILES
from .pros004_remote import GitCheckpointWriter, DIAGNOSTIC_BRANCH
from .pros004_snapshot import _new_root, snapshot_manifest

SCHEMA = 'nba-pros004-generic-transport-load-v1'
MODE = 'SYNTHETIC_GENERIC_TRANSPORT_LOAD_ONLY'
PLANNED_RECORDS = 499
TARGET_LEDGER_BYTES = 24*1024*1024
FULL_PLAN_BYTES = 24576000
SOURCE_FILES = tuple(dict.fromkeys((*PRODUCER_SOURCE_FILES,
    'multisport_lab/pros004_load_diagnostic.py')))


def _require(condition, message):
    if not condition:
        raise IntegrityError(message)


def _now():
    return datetime.now(timezone.utc)


def _sources():
    root=Path(__file__).resolve().parents[1]
    return {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def _command(args, *, cwd=None):
    result=subprocess.run(args,cwd=cwd,capture_output=True,text=True,check=False,timeout=60)
    _require(result.returncode==0,'local synthetic Git command failed: '+args[0])
    return result.stdout.strip()


def _payload(index, clock, padding=''):
    logical='SYNTHETIC_GENERIC_TRANSPORT_LOAD_ONLY:'+str(index)
    return {'schema_version':'multisport-research-ledger-v1','kind':'input_captures',
        'record_id':digest({'kind':'input_captures','logical_id':logical}),
        'logical_id':logical,'received_at':clock,
        'data':{'diagnostic_lane':MODE,'sample_index':index,
            'not_a_forecast_outcome_or_grade':True,'padding':padding},
        'references':[],'supersedes':None,'persistence_status':'LOCAL_RECEIPT_ONLY'}


def _encoded_size(payload):
    return len(canonical({'schema_version':'decoded-json-receipt-v1',
        'hash_format':'sha256-canonical-decoded-json-v1','payload_sha256':digest(payload),'payload':payload}))


def build_transport_store(root, *, records=PLANNED_RECORDS, encoded_bytes=TARGET_LEDGER_BYTES,
                          small_test=False):
    """Create fresh generic bytes; this is not typed-study persistence timing."""
    _require(type(small_test) is bool,'test diagnostic flag must be explicit')
    _require(type(records) is int and 1<=records<=MAX_LEDGER_RECORDS and
             type(encoded_bytes) is int and 0<encoded_bytes<=MAX_LEDGER_BYTES,
             'generic transport dimensions exceed unchanged ledger limits')
    _require(small_test or (records==PLANNED_RECORDS and encoded_bytes==TARGET_LEDGER_BYTES),
             'full transport diagnostic cannot silently change its registered load')
    _require(small_test or encoded_bytes>=FULL_PLAN_BYTES,
             'generic transport load understates the complete byte allowance')
    root=_new_root(root)
    folder=root/'records/input_captures';folder.mkdir(parents=True)
    clock=stamp(_now());references=[]
    base,remainder=divmod(encoded_bytes,records)
    for index in range(records):
        target=base+int(index<remainder)
        value=_payload(index,clock)
        padding_bytes=target-_encoded_size(value)
        _require(0<=padding_bytes and target<=64*1024,
                 'generic transport envelope is too small or exceeds its 64-KiB diagnostic ceiling')
        raw=hashlib.shake_256(('PROS004/SYNTHETIC-TRANSPORT/'+str(index)).encode()).digest(padding_bytes)
        padding=base64.b64encode(raw).decode('ascii')[:padding_bytes]
        value=_payload(index,clock,padding)
        _require(_encoded_size(value)==target,'generic transport encoded-size arithmetic differs')
        write_receipt(folder/(value['record_id']+'.json'),value,max_bytes=64*1024)
        references.append(LedgerRef(value['kind'],value['record_id'],digest(value)))
    manifest=snapshot_manifest(root)
    _require(manifest['record_count']==records and manifest['encoded_bytes']==encoded_bytes,
             'generic load did not retain its exact record/byte dimensions')
    _require(manifest['completion_journal_count']==0,
             'generic load cannot invent typed completion or admission evidence')
    return references,manifest


def run_diagnostic(output, *, work_root=None, small_test=False, records=PLANNED_RECORDS,
                   encoded_bytes=TARGET_LEDGER_BYTES):
    """Measure an isolated actual local-Git checkpoint and retain a factual receipt."""
    output=Path(output).absolute()
    _require(not output.exists(),'retain previous load measurements; output must be new')
    sources=_sources();began=_now();started=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='nml-pros004-generic-load-') as temporary:
        location=Path(work_root).absolute() if work_root is not None else Path(temporary)/'work'
        _require(location.is_relative_to(Path(tempfile.gettempdir()).resolve()),
                 'local diagnostic bare remote must remain under the temporary directory')
        location=_new_root(location)
        build_started=time.perf_counter()
        references,manifest=build_transport_store(location/'source',records=records,
            encoded_bytes=encoded_bytes,small_test=small_test)
        build_seconds=time.perf_counter()-build_started
        bare=location/'bare.git';seed=location/'seed'
        _command(['git','init','--bare','--quiet',str(bare)])
        _command(['git','init','--quiet',str(seed)])
        _command(['git','config','user.name','Synthetic PROS004 transport diagnostic'],cwd=seed)
        _command(['git','config','user.email','synthetic-load@example.invalid'],cwd=seed)
        _command(['git','commit','--quiet','--allow-empty','-m','Synthetic transport baseline only'],cwd=seed)
        base_commit=_command(['git','rev-parse','HEAD'],cwd=seed)
        _command(['git','remote','add','origin',str(bare)],cwd=seed)
        _command(['git','push','--quiet','origin','HEAD:refs/heads/main'],cwd=seed)
        writer=GitCheckpointWriter(location/'source',location/'writer',base_commit=base_commit,
            branch=DIAGNOSTIC_BRANCH,remote_url=bare,diagnostic=True,allow_local_test_remote=True)
        prepare_started=time.perf_counter();writer.prepare()
        prepare_seconds=time.perf_counter()-prepare_started
        checkpoint_started=time.perf_counter()
        acknowledgment=writer.checkpoint(references[-1])
        checkpoint_seconds=time.perf_counter()-checkpoint_started
        _require(acknowledgment['snapshot_sha256']==digest(manifest),
                 'generic load checkpoint did not acknowledge its exact manifest')
        _require(_sources()==sources,'generic load source bytes changed during the diagnostic')
        report={'schema_version':SCHEMA,'mode':MODE,
            'measurement':'SMALL_SYNTHETIC_TEST' if small_test else 'CONSERVATIVE_499_RECEIPT_24_MIB_TRANSPORT',
            'actual_started_at':stamp(began),'actual_completed_at':stamp(_now()),
            'source_sha256':sources,'status':'PASS_LOCAL_BARE_GIT_INDEPENDENT_READBACK',
            'load':{'records':manifest['record_count'],'encoded_ledger_bytes':manifest['encoded_bytes'],
                'full_plan_ceiling_bytes':FULL_PLAN_BYTES,'global_record_limit':MAX_LEDGER_RECORDS,
                'global_byte_limit':MAX_LEDGER_BYTES,'all_receipts_explicit_generic_synthetic':True,
                'padding':'deterministic high-entropy base64; not repeated zero bytes',
                'typed_pros004_records':0,'full_fixed_history_included':False,
                'comparison_probabilities_generated':0,'source_observations':0},
            'transport':{'backend':'ISOLATED_LOCAL_BARE_GIT_NOT_GITHUB','branch':DIAGNOSTIC_BRANCH,
                'base_commit':base_commit,'remote_commit':acknowledgment['remote_commit'],
                'manifest_id':manifest['manifest_id'],'acknowledgment':acknowledgment,
                'independent_fetch_and_full_byte_readback':True,
                'work_root':str(location),'retained_after_command':work_root is not None},
            'performance':{'fixture_build_and_full_generic_validation_seconds':build_seconds,
                'writer_prepare_seconds':prepare_seconds,
                'actual_checkpoint_push_fresh_fetch_readback_seconds':checkpoint_seconds,
                'total_actual_elapsed_seconds':time.perf_counter()-started,
                'peak_process_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},
            'claims':{'pros004_activation':False,'typed_full_study_execution_timing':False,
                'hosted_network_latency_or_availability':False,'genuine_issuance':0,
                'statistical_grades':0,'comparative_evaluation':False,'qualification':'UNAVAILABLE',
                'primary_remote_durability':False}}
        write_receipt(output,report,max_bytes=128*1024)
        return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--work-root',type=Path,help='New /tmp root retained for independent examination')
    args=parser.parse_args()
    report=run_diagnostic(args.output,work_root=args.work_root)
    print(report['status']+' '+str(report['load']['records'])+' records '+
          str(report['load']['encoded_ledger_bytes'])+' bytes '+
          format(report['performance']['actual_checkpoint_push_fresh_fetch_readback_seconds'],'.3f')+' checkpoint seconds')


if __name__=='__main__':
    main()

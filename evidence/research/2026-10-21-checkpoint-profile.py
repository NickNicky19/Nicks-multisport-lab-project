"""Read-only source profiling and isolated local Git checkpoint; no model calls."""
from pathlib import Path
import cProfile
from collections import defaultdict
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib, io, json, pstats, shutil, subprocess, sys, tempfile, time
from unittest.mock import patch

CODE=Path('/workspace/nml-one-event-pilot')
sys.path.insert(0,str(CODE))
from multisport_lab import pros004_snapshot as snap, pros004_remote as remote
from multisport_lab import pros004_inputs as inputs, pros004_producer as producer
from multisport_lab import integrity
from multisport_lab.ledger import LedgerRef
import scripts.verify_pros004_readiness as verify

ORIGINAL=Path('/tmp/nml-pros004-diagnostic-5a1b16edf84e')
OUT=Path('/tmp/nml-operating-checkpoint-profile-20261021')
if OUT.exists():raise RuntimeError('Preserve prior measurement')
OUT.mkdir()
def now():return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')
def inventory(root):
 paths=sorted(root.glob('records/*/*.json'))
 journal=root/'evidence/pros004/completion-journal.jsonl'
 if journal.exists():paths.append(journal)
 return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
original=inventory(ORIGINAL)
source=OUT/'source';shutil.copytree(ORIGINAL,source)
code_paths=producer.SOURCE_FILES+('multisport_lab/pros004_readiness.py',)
code_before={p:hashlib.sha256((CODE/p).read_bytes()).hexdigest() for p in code_paths}
rows=[]
def measure(label,fn):
 start=now();wall=time.perf_counter();cpu=time.process_time()
 try:
  value=fn();error=None
 except Exception as exc:
  value=None;error={'type':type(exc).__name__,'message':str(exc)}
 result={'label':label,'actual_started_at':start,'actual_completed_at':now(),
  'wall_seconds':time.perf_counter()-wall,'process_cpu_seconds':time.process_time()-cpu,'error':error}
 rows.append(result);print(json.dumps(result),flush=True)
 if error:raise RuntimeError('Profile phase failed: '+label)
 return value
def git(*args):
 result=subprocess.run(['git',*map(str,args)],capture_output=True,text=True,timeout=60)
 if result.returncode:raise RuntimeError('Isolated Git preparation failed: '+result.stderr[:200])
 return result.stdout.strip()

manifest=measure('cold_full_strict_snapshot',lambda:snap.snapshot_manifest(source))
reference_entry=next(e for e in manifest['entries'] if e['entry_type']=='LEDGER_RECEIPT' and '/forecasts/' in e['path'])
reference=LedgerRef('forecasts',Path(reference_entry['path']).stem,reference_entry['payload_sha256'])
bare=OUT/'remote.git';git('init','--quiet','--bare',bare)
base=git('-C',CODE,'rev-parse','HEAD')
git('-C',CODE,'push','--quiet',bare,'HEAD:refs/heads/source-base')
writer=remote.GitCheckpointWriter(source,OUT/'writer',base_commit=base,
    remote_url=str(bare),allow_local_test_remote=True)
measure('writer_prepare',writer.prepare)
measure('warm_initial_checkpoint',lambda:writer.checkpoint(reference))

events=[]
def timed(owner,name,label=None):
 original=getattr(owner,name)
 def wrapper(*args,**kwargs):
  start=time.perf_counter();cpu=time.process_time();error=None
  try:return original(*args,**kwargs)
  except BaseException as exc:error=type(exc).__name__;raise
  finally:
   events.append({'label':label or name,'wall_seconds':time.perf_counter()-start,
       'process_cpu_seconds':time.process_time()-cpu,'error':error,
       'root':str(args[0])[:180] if args and isinstance(args[0],(str,Path)) else None})
 return patch.object(owner,name,wrapper)
with ExitStack() as stack:
 for owner,name,label in ((snap,'snapshot_manifest','full_strict_snapshot'),
     (snap,'export_snapshot','verified_export_including_three_snapshots'),
     (verify,'_strict_semantics','typed_semantic_pass'),
     (inputs,'validate_history','full_history_validation'),
     (inputs,'_original_provenance','frozen_history_provenance_read'),
     (verify,'canonical','independent_canonical_json'),
     (integrity,'canonical','core_canonical_json')):
  stack.enter_context(timed(owner,name,label))
 original_command=writer._command
 def command(*args,**kwargs):
  started=time.perf_counter()
  try:return original_command(*args,**kwargs)
  finally:events.append({'label':'git_command','command':args[0][:4],
       'wall_seconds':time.perf_counter()-started})
 stack.enter_context(patch.object(writer,'_command',command))
 ack=measure('idempotent_full_store_checkpoint_instrumented',lambda:writer.checkpoint(reference))

profile=cProfile.Profile()
start=now();wall=time.perf_counter();profile.enable()
profiled_manifest=snap.snapshot_manifest(source)
profile.disable()
profile_wall=time.perf_counter()-wall
profile.dump_stats(str(OUT/'strict-snapshot.cprofile'))
text=io.StringIO();pstats.Stats(profile,stream=text).strip_dirs().sort_stats('cumulative').print_stats(45)
(OUT/'strict-snapshot-profile.txt').write_text(text.getvalue())
summary=defaultdict(lambda:{'calls':0,'cumulative_wall_seconds':0.0,'cumulative_process_cpu_seconds':0.0})
for event in events:
 v=summary[event['label']];v['calls']+=1;v['cumulative_wall_seconds']+=event['wall_seconds'];v['cumulative_process_cpu_seconds']+=event.get('process_cpu_seconds',0)
if manifest!=profiled_manifest or original!=inventory(ORIGINAL) or original!=inventory(source):raise RuntimeError('Profiling changed original bytes')
if code_before!={p:hashlib.sha256((CODE/p).read_bytes()).hexdigest() for p in code_paths}:raise RuntimeError('Source changed during profile')
report={'schema_version':'nba-operating-checkpoint-profile-v1','status':'PASS_READONLY_NON_ISSUANCE_PROFILE',
 'source_commit':base,'source_sha256':code_before,'retained_original_store':str(ORIGINAL),
 'original_record_count':manifest['record_count'],'original_encoded_bytes':manifest['encoded_bytes'],
 'original_and_copied_bytes_unchanged':True,'manifest_id':manifest['manifest_id'],
 'actual_completed_at':now(),'measurements':rows,'instrumentation_summary':dict(summary),'events':events,
 'strict_profile':{'actual_started_at':start,'actual_wall_seconds':profile_wall,
  'is_operational_timing_evidence':False,'reason':'cProfile overhead; read-only strict verification, no issuance',
  'text':text.getvalue()},'checkpoint_acknowledgment':ack,
 'limitations':['One30-file retained full-history diagnostic state, not maximum study ledger or host timing.',
  'No source capture, model generation, scoring, genuine issuance, activation, GitHub write or scheduler.'],
 'evidence':{'model_generation_calls':0,'source_requests':0,'real_outcomes':0,'statistical_grades':0,
  'genuine_issuance':0,'activation':False,'deployment':False}}
(OUT/'profile.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({'report':str(OUT/'profile.json'),'sha256':hashlib.sha256((OUT/'profile.json').read_bytes()).hexdigest(),
 'summary':dict(summary),'cprofile_wall_seconds':profile_wall}),flush=True)

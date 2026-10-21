"""Non-issuance checkpoint timing; existing retained input bytes, no model/source calls."""
from pathlib import Path
from datetime import datetime,timezone
from contextlib import ExitStack
from unittest.mock import patch
from collections import defaultdict
import hashlib,json,shutil,subprocess,sys,time
CODE=Path('/workspace/nml-one-event-pilot');sys.path.insert(0,str(CODE))
from multisport_lab import pros004_snapshot as snap,pros004_remote as remote,pros004_producer as producer
from multisport_lab.ledger import LedgerRef
ORIGINAL=Path('/tmp/nml-pros004-diagnostic-5a1b16edf84e')
OUT=Path('/tmp/nml-operating-checkpoint-after-20261021')
if OUT.exists():raise RuntimeError('Preserve prior checkpoint measurement')
OUT.mkdir()
def inventory(root):
 paths=sorted(root.glob('records/*/*.json'));journal=root/'evidence/pros004/completion-journal.jsonl'
 if journal.exists():paths.append(journal)
 return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
def utcnow():return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')
def git(*args):
 r=subprocess.run(['git',*map(str,args)],capture_output=True,text=True,timeout=60)
 if r.returncode:raise RuntimeError('Isolated Git failed '+r.stderr[:100])
 return r.stdout.strip()
source=OUT/'source';original=inventory(ORIGINAL);shutil.copytree(ORIGINAL,source)
code_paths=producer.SOURCE_FILES+('multisport_lab/pros004_readiness.py',)
code_before={p:hashlib.sha256((CODE/p).read_bytes()).hexdigest() for p in code_paths}
manifest=snap.snapshot_manifest(source)
entry=next(e for e in manifest['entries'] if e['entry_type']=='LEDGER_RECEIPT' and '/forecasts/' in e['path'])
ref=LedgerRef('forecasts',Path(entry['path']).stem,entry['payload_sha256'])
bare=OUT/'remote.git';git('init','--bare','--quiet',bare)
base=git('-C',CODE,'rev-parse','HEAD');git('-C',CODE,'push','--quiet',bare,'HEAD:refs/heads/source-base')
writer=remote.GitCheckpointWriter(source,OUT/'writer',base_commit=base,remote_url=str(bare),allow_local_test_remote=True);writer.prepare()
rows=[];events=[]
def measure(label):
 started=utcnow();wall=time.perf_counter();cpu=time.process_time();ack=writer.checkpoint(ref)
 row={'label':label,'actual_started_at':started,'actual_completed_at':utcnow(),
 'wall_seconds':time.perf_counter()-wall,'process_cpu_seconds':time.process_time()-cpu}
 rows.append(row);print(json.dumps(row),flush=True);return ack
def timed(name):
 original=getattr(snap,name)
 def wrapped(*a,**kw):
  wall=time.perf_counter();cpu=time.process_time()
  try:return original(*a,**kw)
  finally:events.append({'label':name,'root':str(a[0]),'wall_seconds':time.perf_counter()-wall,'process_cpu_seconds':time.process_time()-cpu})
 return patch.object(snap,name,wrapped)
measure('initial_full_checkpoint')
with ExitStack() as stack:
 for name in ('snapshot_manifest','_fresh_identical_snapshot'):stack.enter_context(timed(name))
 ack=measure('idempotent_checkpoint_with_phase_timing')
if original!=inventory(ORIGINAL) or original!=inventory(source):raise RuntimeError('Original bytes changed')
if code_before!={p:hashlib.sha256((CODE/p).read_bytes()).hexdigest() for p in code_paths}:raise RuntimeError('Source changed during timing')
report={'schema_version':'nba-exact-checkpoint-transport-profile-v1','status':'PASS_READONLY_NON_ISSUANCE_PROFILE',
 'source_commit':base,'source_sha256':code_before,'original_record_count':manifest['record_count'],
 'original_encoded_bytes':manifest['encoded_bytes'],'manifest_id':manifest['manifest_id'],
 'actual_completed_at':utcnow(),'measurements':rows,'events':events,'checkpoint_acknowledgment':ack,
 'retained_original_and_copied_bytes_unchanged':True,
 'evidence':{'model_calls':0,'source_requests':0,'genuine_issuance':0,'activation':False},
 'limitations':['One retained diagnostic state and isolated local bare Git; no host or full-cycle timing.','Simulated PROS004 clocks remain diagnostic and establish no timely genuine issuance.']}
(OUT/'profile.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({'report':str(OUT/'profile.json'),'sha256':hashlib.sha256((OUT/'profile.json').read_bytes()).hexdigest(),'events':events}),flush=True)

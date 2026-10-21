"""One diagnostic OP002 Git writer, full typed fresh independent readback.

Only the explicitly isolated diagnostic branch is enabled. This adapter contains
no source client, activation, scheduler or model generation. A missing or late
acknowledgment never changes originals or supplies a successful completion.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import time

from . import operational_pilot as op
from . import pros004_remote as git_transport
from .integrity import IntegrityError, digest, read_receipt, stamp
from .ledger import LedgerRef

DIAGNOSTIC_BRANCH = "diagnostics/ops002-paired-batch-20261021"


def _actual_now():
    return datetime.now(timezone.utc)


class OperatingDiagnosticWriter(git_transport.GitCheckpointWriter):
    """Separate diagnostic guard; the PROS004 writer's guard is unchanged.

    Git locking, normal push/restart and command deadlines reuse the existing
    transport. Every operation starts with full OP002 typed source verification
    and ends with a fresh object database/fetch and full typed verification.
    Only exact identical local bytes reuse the source's checked meanings.
    """
    def __init__(self,source_root,writer_root,*,base_commit,branch=DIAGNOSTIC_BRANCH,
                 remote_url=git_transport.REMOTE_URL,diagnostic=True,
                 allow_local_test_remote=False,command_seconds=60):
        op.require(diagnostic is True,"OP002 genuine remote writes remain INACTIVE")
        op.require(branch == DIAGNOSTIC_BRANCH,"only the named one-off OP002 diagnostic branch is enabled")
        self.source_root=git_transport._safe_root(source_root)
        self.root=git_transport._safe_root(writer_root)
        self.base_commit=git_transport._sha(base_commit,"base commit",40)
        self.branch,self.remote_url=branch,str(remote_url)
        op.require(type(command_seconds) is int and 1 <= command_seconds <= 60,"invalid diagnostic Git operation budget")
        self.command_seconds=command_seconds;self._deadline=None;self._head=None
        self._local_remote=allow_local_test_remote is True;self.operations=[]
        if self._local_remote:
            candidate=git_transport._safe_root(self.remote_url)
            op.require(candidate.is_dir() and candidate.is_relative_to(Path(tempfile.gettempdir())),
                       "test remote must be an isolated existing temporary bare repository")
            result=subprocess.run(["git","-C",str(candidate),"rev-parse","--is-bare-repository"],
                capture_output=True,text=True,check=False,timeout=command_seconds)
            op.require(result.returncode == 0 and result.stdout.strip() == "true","test remote is not bare")
        else:
            op.require(self.remote_url in (git_transport.REMOTE_URL,git_transport.REMOTE_URL[:-4],
                "git@github.com:"+op.REPOSITORY+".git"),"not the existing authorized repository")
        op.require(not self.root.is_relative_to(self.source_root) and not self.source_root.is_relative_to(self.root),
                   "diagnostic writer and retained source must be separate roots")

    @staticmethod
    def _context(root):
        root=git_transport._safe_root(root)
        op.require(root.is_dir(),"diagnostic root is unavailable")
        return [(str(path),path.stat().st_dev,path.stat().st_ino)
                for path in (root,root/'records') if path.exists()]

    @staticmethod
    def _verified(root):
        verified=op.verify_store(root,replay=False)
        op.require(verified['genuine_issued'] == 0,"diagnostic writer cannot publish genuine issuance")
        for entry in verified['snapshot']['files']:
            if not entry['path'].startswith('records/'):continue
            payload=read_receipt(Path(root)/entry['path'],max_bytes=4*1024*1024)
            body=payload['data'].get('operational')
            if body is None:continue
            op.require(body['mode'] in {'READINESS_DIAGNOSTIC','SYNTHETIC_DIAGNOSTIC'} and
                body['schema_version'] not in {op._schema('outcome'),op._schema('grade')},
                "diagnostic transport cannot publish live records/outcomes/grades")
        op.require(op.snapshot_manifest(root) == verified['snapshot'],
                   "diagnostic record bytes changed after full typed validation")
        return verified['snapshot']

    def _preserve(self,manifest):
        if not (self.root/'records').exists():return
        previous=self._verified(self.root)
        current={item['path']:item for item in manifest['files']}
        for entry in previous['files']:
            relative=entry['path']
            op.require(relative in current,"diagnostic source is missing a retained remote original")
            old=(self.root/relative).read_bytes()
            if relative == op.JOURNAL:
                op.require((self.source_root/relative).read_bytes().startswith(old),
                           "diagnostic completion journal cannot truncate or replace its original prefix")
            elif relative == op.PROOF and old != (self.source_root/relative).read_bytes():
                archived=Path(op.PROOF).with_name('remote-recovery.'+hashlib.sha256(old).hexdigest()+'.json').as_posix()
                op.require(archived in current and (self.source_root/archived).read_bytes() == old,
                           "original recovery proof must be retained in its exact revision archive")
            else:
                op.require(entry == current[relative],"diagnostic checkpoint cannot replace an original")

    def _fresh_readback(self,commit,manifest,reference):
        with tempfile.TemporaryDirectory(prefix='nml-op002-independent-') as directory:
            root=Path(directory)/'readback';root.mkdir()
            self._git('init','--quiet',cwd=root)
            self._git('remote','add','origin',self.remote_url,cwd=root)
            self._git('fetch','--no-tags','--depth=1','origin','refs/heads/'+self.branch,cwd=root)
            op.require(self._git('rev-parse','FETCH_HEAD',cwd=root).stdout.strip() == commit,
                       "independent OP002 readback recovered another commit")
            self._git('checkout','--quiet','--detach','FETCH_HEAD',cwd=root)
            op.require(self._verified(root) == manifest,"independent OP002 typed snapshot changed")
            references=reference if type(reference) is tuple else (reference,) if reference is not None else ()
            expected={entry['path']:entry for entry in manifest['files']};raw_hashes=[]
            for original in references:
                relative='records/'+original.kind+'/'+original.record_id+'.json';path=root/relative
                op.require(digest(read_receipt(path,max_bytes=4*1024*1024)) == original.payload_sha256,
                           "independent OP002 reference payload changed")
                raw_sha=hashlib.sha256(path.read_bytes()).hexdigest()
                op.require(relative in expected and raw_sha == expected[relative]['raw_sha256'],
                           "independent OP002 original bytes changed after typed verification")
                raw_hashes.append(raw_sha)
            op.require(self._remote_head() == commit,"remote advanced during independent OP002 recovery")
            return tuple(raw_hashes) if type(reference) is tuple else raw_hashes[0] if raw_hashes else None

    def _retain(self,reference=None,required_prefix=None,*,references=None):
        op.require(self._head is not None,"prepare one retained diagnostic writer before checkpoint")
        is_batch=references is not None
        originals=references if is_batch else (reference,) if reference is not None else ()
        actual_started=_actual_now();wall=time.perf_counter();cpu=time.process_time()
        self._deadline=time.monotonic()+self.command_seconds
        operation={'actual_started_at':stamp(actual_started),'reference':reference.to_record() if reference else None}
        if is_batch:operation['references']=[original.to_record() for original in originals]
        try:
            with self._writer_lock():
                op.require(not self._git('status','--porcelain').stdout.strip(),"retain interrupted dirty writer; do not replace it")
                local=self._git('rev-parse','HEAD').stdout.strip()
                op.require(local == self._head,"retained OP002 writer changed")
                remote=self._remote_head()
                if remote is not None and remote != local:
                    self._git('fetch','--no-tags','origin','refs/heads/'+self.branch)
                    op.require(self._git('merge-base','--is-ancestor',remote,local,check=False).returncode == 0,
                               "another writer advanced OP002 remote state")
                context=self._context(self.source_root);manifest=self._verified(self.source_root)
                op.require(self._context(self.source_root) == context,"source directory changed during OP002 verification")
                journal=self.source_root/op.JOURNAL
                prefix=hashlib.sha256(journal.read_bytes() if journal.exists() else b'').hexdigest()
                op.require(required_prefix is None or required_prefix == prefix,"final journal prefix differs from actual source")
                bodies=[]
                for original in originals:
                    source=self.source_root/'records'/original.kind/(original.record_id+'.json')
                    payload=read_receipt(source,max_bytes=4*1024*1024)
                    op.require(digest(payload) == original.payload_sha256,
                               "OP002 checkpoint reference changed")
                    if is_batch:
                        body=payload['data'].get('operational')
                        op.require(type(body) is dict and body.get('schema_version') == op._schema('forecast'),
                                   "paired checkpoint requires original OP002 forecasts")
                        bodies.append(body)
                if is_batch:
                    identity=('plan_id','event_id','event_version','event_starts_at','player_id','team_id','opponent_id',
                              'event_ref','history_ref','producer_binding','mode')
                    op.require(all(all(body[key] == bodies[0][key] for key in identity) for body in bodies),
                               "paired checkpoint cannot combine different subjects, events or exact inputs/producers")
                    models=[body['model_key'] for body in bodies]
                    op.require(len(set(models)) == len(models) and set(models) <= {'R0','K0'},
                               "paired checkpoint requires distinct unchanged R0/K0 originals")
                self._preserve(manifest)
                for entry in manifest['files']:
                    source=self.source_root/entry['path'];target=git_transport._safe_root(self.root/entry['path'])
                    raw=source.read_bytes()
                    op.require(len(raw) == entry['bytes'] and hashlib.sha256(raw).hexdigest() == entry['raw_sha256'],
                               "OP002 source bytes changed during copy")
                    target.parent.mkdir(parents=True,exist_ok=True)
                    if target.exists() and target.read_bytes() == raw:continue
                    with target.open('wb') as handle:
                        op.require(handle.write(raw) == len(raw),"incomplete OP002 original copy")
                        handle.flush();os.fsync(handle.fileno())
                    descriptor=os.open(target.parent,os.O_RDONLY)
                    try:os.fsync(descriptor)
                    finally:os.close(descriptor)
                op.require(op.snapshot_manifest(self.root) == manifest and
                    op.snapshot_manifest(self.source_root) == manifest and self._context(self.source_root) == context,
                    "OP002 exact source/copy inventory changed")
                self._git('add','--',*[entry['path'] for entry in manifest['files']])
                if self._git('diff','--cached','--quiet',check=False).returncode:
                    self._git('-c',"user.name=Nick's Multisport Lab",'-c','user.email=research@users.noreply.github.com',
                              'commit','--quiet','-m','Retain non-issuance OP002 timing diagnostic')
                commit=git_transport._sha(self._git('rev-parse','HEAD').stdout.strip(),'checkpoint commit',40)
                self._head=commit
                self._git('push','origin','HEAD:refs/heads/'+self.branch)
                raw_sha=self._fresh_readback(commit,manifest,originals if is_batch else reference)
                op.require(time.monotonic() <= self._deadline,"OP002 remote recovery exceeded its actual operation budget")
                completed=stamp(op._now())  # Explicit diagnostic clock only.
                common={'remote_repository':op.REPOSITORY,'remote_branch':self.branch,'remote_commit':commit,
                        'snapshot_sha256':digest(manifest)}
                if is_batch:
                    op.require(type(raw_sha) is tuple and len(raw_sha) == len(originals),
                               "independent paired readback did not verify every original")
                    result=tuple({**common,'schema_version':op._schema('remote-checkpoint'),
                        'reference':original.to_record(),'readback_raw_sha256':raw,
                        'journal_prefix_sha256':prefix,'remote_completed_at':completed}
                        for original,raw in zip(originals,raw_sha))
                elif reference is not None:
                    result=dict(common)
                    result.update(schema_version=op._schema('remote-checkpoint'),reference=reference.to_record(),
                        readback_raw_sha256=raw_sha,journal_prefix_sha256=prefix,remote_completed_at=completed)
                else:
                    result=dict(common)
                    result.update(schema_version=op._schema('remote-recovery'),protocol_id=op.PROTOCOL_ID,
                        journal_sha256=prefix,independent_recovery_completed_at=completed)
                operation.update(status='PASS_FULL_TYPED_FRESH_FETCH',remote_commit=commit,
                    snapshot_sha256=digest(manifest),file_count=manifest['file_count'],encoded_bytes=manifest['total_bytes'])
                return result
        except BaseException as exc:
            operation.update(status='UNACKNOWLEDGED_RETAINED_STATE',error_type=type(exc).__name__,error=str(exc)[:2048])
            raise
        finally:
            self._deadline=None
            operation.update(actual_completed_at=stamp(_actual_now()),wall_seconds=time.perf_counter()-wall,
                             process_cpu_seconds=time.process_time()-cpu)
            self.operations.append(operation)

    def checkpoint(self,reference):
        op.require(isinstance(reference,LedgerRef),"OP002 checkpoint requires original LedgerRef")
        return self._retain(reference=reference)

    def checkpoint_many(self,references):
        """One strict transfer for one/two existing same-subject originals.

        All independently fetched original hashes and identities are checked
        before returning the separate acknowledgments. This does not make the
        caller's subsequent per-original witness writes atomic or timely.
        """
        op.require(type(references) is tuple and 1 <= len(references) <= 2 and
            all(isinstance(ref,LedgerRef) and ref.kind == 'forecasts' for ref in references) and
            len(set(references)) == len(references),"paired checkpoint requires one or two unique forecast references")
        return self._retain(references=references)

    def final_checkpoint(self,prefix):
        op.sha(prefix)
        return self._retain(required_prefix=prefix)

    __call__=checkpoint

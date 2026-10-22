"""Bounded external raw-outcome retention, inactive for actual publication.

Raw provider bodies never enter the public repository or Pages. This archive
accepts supplied bytes only and preserves their separate source/import clocks.
A transport checkpoint requires independently read-back bytes and an explicit
reviewed private-retention plan. No such actual backend is admitted by this
readiness package: actual external publication fails closed. Synthetic transport
tests establish contract behavior, never source permission or primary durability.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time

from .integrity import IntegrityError, canonical, digest, read_receipt, stamp, utc, write_receipt

SCHEMA = "nba-pros004-raw-capture-v1"
REF_SCHEMA = "nba-pros004-raw-reference-v1"
MAX_OBJECT_BYTES = 8*1024*1024
MAX_ARCHIVE_BYTES = 64*1024*1024
MAX_CAPTURES = 128
MAX_METADATA_BYTES = 16*1024
MAX_TRANSPORT_SECONDS = 60
MODES = {"SYNTHETIC_DIAGNOSTIC", "READINESS_DIAGNOSTIC", "REAL_TIME_CAPTURED"}


class RawEvidenceError(IntegrityError):
    pass


def _require(condition, message):
    if not condition:
        raise RawEvidenceError(message)


def _now():
    return datetime.now(timezone.utc)


def _hash(value, name):
    _require(type(value) is str and re.fullmatch('[a-f0-9]{64}',value) is not None,
             'invalid '+name)
    return value


def _clock(value, name):
    _require(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z',value) is not None,
             name+' requires precise original UTC clock')
    try:
        return utc(value)
    except ValueError as error:
        raise RawEvidenceError(name+' is not a valid UTC clock') from error


def _safe_root(value):
    root=Path(value).absolute()
    for part in (root,*root.parents):
        _require(not part.is_symlink(),'raw archive paths cannot traverse symlinks')
    probe=root
    while not probe.exists():probe=probe.parent
    result=subprocess.run(['git','-C',str(probe),'rev-parse','--show-toplevel'],
                          capture_output=True,text=True,check=False,timeout=10)
    _require(result.returncode!=0,'raw source bodies must stay outside every Git worktree and public artifact')
    return root


def validate_private_retention_plan(plan):
    """Validate reviewed candidate metadata; does not enable actual publication."""
    fields={'schema_version','backend_id','privacy','durability','reviewed_evidence_sha256',
            'permitted_raw_retention','retention_through'}
    _require(type(plan) is dict and set(plan)==fields and plan['schema_version']=='nba-pros004-private-raw-plan-v1',
             'invalid private raw-retention plan')
    _require(type(plan['backend_id']) is str and 0<len(plan['backend_id'])<=160,
             'raw backend identity is required')
    _require(plan['privacy']=='PRIVATE_VERIFIED' and plan['durability']=='PRIMARY_DURABLE' and
             plan['permitted_raw_retention'] is True,'private permission/durability admission is unresolved')
    _hash(plan['reviewed_evidence_sha256'],'reviewed raw-retention evidence')
    _require(plan['retention_through']=='INDEFINITE_REVIEWED',
             'private primary evidence requires reviewed indefinite retention; evaluation-start expiry is insufficient')
    return plan


def _reference(body):
    return {'schema_version':REF_SCHEMA,'capture_id':body['capture_id'],
            'payload_sha256':digest(body),'raw_sha256':body['raw_sha256'],'raw_bytes':body['raw_bytes']}


class RawEvidenceArchive:
    """Create-only content-addressed bytes with immutable capture receipts."""
    def __init__(self,root):
        self.root=_safe_root(root)

    def _inventory(self):
        _safe_root(self.root)
        count=total=0
        for folder in ('blobs','captures'):
            directory=self.root/folder
            if not directory.exists():continue
            _require(not directory.is_symlink() and directory.is_dir(),'raw archive directory is unsafe')
            for path in directory.iterdir():
                _require(stat.S_ISREG(path.lstat().st_mode),'raw archive objects must be regular files')
                _require(re.fullmatch('[a-f0-9]{64}'+(r'\.bin' if folder=='blobs' else r'\.json'),path.name) is not None,
                         'interrupted or unrecognized raw archive object; retain for recovery')
                size=path.stat().st_size
                _require(size<=(MAX_OBJECT_BYTES if folder=='blobs' else MAX_METADATA_BYTES),'raw archive object exceeds its bound')
                total+=size
                if folder=='captures':count+=1
        _require(count<=MAX_CAPTURES and total<=MAX_ARCHIVE_BYTES,'raw archive exceeds bounded capture/byte capacity')
        return count,total

    def _blob(self,sha):
        return self.root/'blobs'/(_hash(sha,'raw hash')+'.bin')

    def _capture(self,capture_id):
        return self.root/'captures'/(_hash(capture_id,'capture identity')+'.json')

    def _validate(self,body):
        fields={'schema_version','mode','event_id','source_url','source_observed_at','source_updated_at',
                'imported_at','raw_persistence_completed_at','raw_sha256','raw_bytes','supersedes',
                'correction_reason','capture_id'}
        _require(type(body) is dict and set(body)==fields and body['schema_version']==SCHEMA,
                 'invalid raw capture contract')
        _require(type(body['mode']) is str and body['mode'] in MODES and type(body['event_id']) is str and len(body['event_id'])<=20 and
                 re.fullmatch('[1-9][0-9]*',body['event_id']) is not None,'raw event/evidence lane is invalid')
        source='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event='+body['event_id']
        synthetic='synthetic://pros004/outcome/'+body['event_id']
        _require(body['source_url']==source or body['mode']!='REAL_TIME_CAPTURED' and body['source_url']==synthetic,
                 'raw archive requires exact outcome-source identity')
        observed=_clock(body['source_observed_at'],'source observation')
        imported=_clock(body['imported_at'],'raw import')
        completed=_clock(body['raw_persistence_completed_at'],'raw persistence completion')
        _require(observed<=imported<=completed<=_now(),'raw source/import/completion clocks conflict')
        if body['source_updated_at'] is not None:
            _require(_clock(body['source_updated_at'],'source update')<=observed,'source update follows actual observation')
        _hash(body['raw_sha256'],'raw hash')
        _require(type(body['raw_bytes']) is int and 0<body['raw_bytes']<=MAX_OBJECT_BYTES,'invalid raw byte budget')
        if body['supersedes'] is None:
            _require(body['correction_reason'] is None,'raw correction reason requires an original capture')
        else:
            _require(type(body['correction_reason']) is str and 0<len(body['correction_reason'].strip())<=2048,
                     'raw correction needs a bounded factual reason')
            original,_=self.read(body['supersedes'])
            _require(original['event_id']==body['event_id'] and original['mode']==body['mode'] and
                     _clock(original['source_observed_at'],'original observation')<=observed,
                     'raw correction changes event/evidence lane or precedes its original')
        identity={k:body[k] for k in fields-{'capture_id','imported_at','raw_persistence_completed_at'}}
        _require(body['capture_id']==digest(identity),'raw capture identity changed')
        return body

    def read(self,reference):
        self._inventory()
        _require(type(reference) is dict and set(reference)=={'schema_version','capture_id','payload_sha256','raw_sha256','raw_bytes'}
                 and reference['schema_version']==REF_SCHEMA,'invalid raw evidence reference')
        for key in ('capture_id','payload_sha256','raw_sha256'):
            _hash(reference[key],key)
        _require(type(reference['raw_bytes']) is int and 0<reference['raw_bytes']<=MAX_OBJECT_BYTES,
                 'raw evidence reference needs an actual byte count')
        body=read_receipt(self._capture(reference['capture_id']),max_bytes=MAX_METADATA_BYTES)
        _require(digest(body)==reference['payload_sha256'],'raw capture receipt hash changed')
        self._validate(body)
        _require(_reference(body)==reference,'raw byte identity differs from its capture reference')
        path=self._blob(body['raw_sha256'])
        _require(path.is_file() and not path.is_symlink() and path.stat().st_size==body['raw_bytes'],
                 'retained raw bytes missing or changed size')
        raw=path.read_bytes()
        _require(hashlib.sha256(raw).hexdigest()==body['raw_sha256'],'retained raw byte hash changed')
        return body,raw

    def retain(self,raw,*,mode,event_id,source_url,observed_at,source_updated_at=None,
               supersedes=None,correction_reason=None):
        """Retain already supplied bytes; never make a provider request."""
        _require(type(raw) is bytes and 0<len(raw)<=MAX_OBJECT_BYTES,'raw outcome bytes exceed the source bound')
        count,total=self._inventory()
        imported=_now();sha=hashlib.sha256(raw).hexdigest()
        identity={'schema_version':SCHEMA,'mode':mode,'event_id':event_id,'source_url':source_url,
                  'source_observed_at':stamp(utc(observed_at)),
                  'source_updated_at':stamp(utc(source_updated_at)) if source_updated_at is not None else None,
                  'raw_sha256':sha,'raw_bytes':len(raw),'supersedes':supersedes,'correction_reason':correction_reason}
        capture_id=digest(identity);capture_path=self._capture(capture_id)
        if capture_path.exists():
            original=read_receipt(capture_path,max_bytes=MAX_METADATA_BYTES)
            reference=_reference(original);self.read(reference)
            _require({k:original[k] for k in identity}==identity,'raw retry conflicts with an original capture')
            return reference
        # Validate meaning before writing any bytes. The final completion is
        # observed after immutable data flush/readback, never inferred pre-write.
        proposed={**identity,'imported_at':stamp(imported),'raw_persistence_completed_at':stamp(imported),
                  'capture_id':capture_id}
        self._validate(proposed)
        _require(count+1<=MAX_CAPTURES and total+len(raw)+MAX_METADATA_BYTES<=MAX_ARCHIVE_BYTES,
                 'new raw capture would exceed bounded archive capacity')
        path=self._blob(sha);path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():
            fd,temporary=tempfile.mkstemp(prefix='.raw-',dir=path.parent)
            try:
                with os.fdopen(fd,'wb') as handle:
                    handle.write(raw);handle.flush();os.fsync(handle.fileno())
                os.link(temporary,path)
            finally:
                # A linked original remains immutable. An interrupted process
                # may leave a .raw-* file; future inventory refuses it.
                if Path(temporary).exists():Path(temporary).unlink()
            descriptor=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(descriptor)
            finally:os.close(descriptor)
        _require(path.read_bytes()==raw,'raw content-addressed original has conflicting bytes')
        completed=_now()
        body={**proposed,'raw_persistence_completed_at':stamp(completed)}
        self._validate(body)
        write_receipt(capture_path,body,max_bytes=MAX_METADATA_BYTES)
        reference=_reference(body);self.read(reference)
        return reference

    def recover(self):
        """Recover exact originals without changing clocks or fetching a source."""
        self._inventory();result=[]
        for path in sorted((self.root/'captures').glob('*.json')):
            body=read_receipt(path,max_bytes=MAX_METADATA_BYTES)
            reference=_reference(body);self.read(reference);result.append(reference)
        return result

    def verify_outcome_reference(self, outcome, reference):
        """Cross-check an outcome against exact retained raw capture evidence.

        This establishes byte/identity/clock linkage, not upstream authenticity,
        successful statistical normalization or admitted private durability.
        Real operation still requires that independently reviewed integration.
        """
        from .pros004_records import validate_outcome_body
        validate_outcome_body(outcome)
        body, _ = self.read(reference)
        _require(all(outcome[left] == body[right] for left, right in (
            ('event_id', 'event_id'), ('mode', 'mode'),
            ('source_raw_sha256', 'raw_sha256'),
            ('source_observed_at', 'source_observed_at'),
            ('source_updated_at', 'source_updated_at'))),
            'outcome/raw capture identity, bytes or original source clocks conflict')
        _require(_clock(outcome['normalized_at'], 'outcome normalization') >=
                 _clock(body['source_observed_at'], 'source observation'),
                 'outcome normalization precedes retained capture')
        return {'schema_version': 'nba-pros004-outcome-raw-link-v1',
                'outcome_id': outcome['outcome_id'], 'reference': reference,
                'exact_byte_identity_and_source_clocks_verified': True,
                'statistical_normalization_independently_verified': False,
                'actual_raw_primary_durability_established': False,
                'activation': False}

    def checkpoint_private(self,reference,transport,*,plan):
        """Exercise a private-backend contract only for explicit synthetic bytes.

        ``transport.put`` and ``transport.readback`` must be separate operations.
        Their implementation and reviewed privacy/permission evidence are external
        dependencies. A local mirror or public artifact does not prove primary
        private durability, and caller flags cannot activate actual publication.
        """
        validate_private_retention_plan(plan)
        body,raw=self.read(reference)
        _require(body['mode']!='REAL_TIME_CAPTURED','INACTIVE: actual raw publication has no admitted private backend')
        started=_now();monotonic=time.monotonic()
        metadata=transport.describe()
        _require(type(metadata) is dict and metadata.get('backend_id')==plan['backend_id'] and metadata.get('visibility')=='PRIVATE',
                 'raw backend is not the reviewed private destination')
        locator=transport.put(reference,raw)
        _require(type(locator) is str and 0<len(locator)<=2048 and
                 '?' not in locator and '@' not in locator,
                 'raw transport must return a bounded non-secret object locator')
        observed=transport.readback(locator)
        _require(type(observed) is bytes and observed==raw,'independent raw readback differs from original bytes')
        completed=_now()
        _require(time.monotonic()-monotonic<=MAX_TRANSPORT_SECONDS and completed>=started,
                 'raw transport/readback exceeded its actual operation budget')
        return {'schema_version':'nba-pros004-raw-readback-v1','reference':reference,
                'backend_id':plan['backend_id'],'locator':locator,'raw_sha256':hashlib.sha256(observed).hexdigest(),
                'started_at':stamp(started),'completed_at':stamp(completed),
                'evidence_lane':'SYNTHETIC_TRANSPORT_DIAGNOSTIC','activation':False,
                'actual_raw_primary_durability_established':False,
                'source_permission_established':False}

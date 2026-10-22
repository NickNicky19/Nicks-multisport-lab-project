#!/usr/bin/env python3
"""Read-only independent Git/archive recovery; never captures or issues."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from multisport_lab.integrity import _bounded_bytes,_decode,canonical,stamp
from multisport_lab import sdv_production_common as common
from multisport_lab.sdv_production_archive import GitHubReleaseArchive,recover_snapshot
from multisport_lab.sdv_production_remote import validate_pointer


def recover(branch,work_root,*,archive=None,remote_url=common.REMOTE_URL,allow_local_test_remote=False):
    common.require(type(branch) is str and re.fullmatch(r"records/sdv-prod-[0-9]{8}-[1-9][0-9]*-[a-f0-9]{12}-s[0-3]",branch),
        "Recovery requires one exact production records branch")
    work=Path(work_root).absolute()
    common.require(not any(p.is_symlink() for p in (work,*work.parents)) and not work.exists(),"Independent readback needs a new non-symlink directory")
    common.require(not work.is_relative_to(ROOT) and not ROOT.is_relative_to(work),"Recovery must not write inside the source repository or its parents")
    common.require(remote_url == common.REMOTE_URL or allow_local_test_remote and Path(remote_url).absolute().is_relative_to(Path('/tmp')),
        "Recovery remote differs from this repository")
    checkout=work/'git';checkout.mkdir(parents=True)
    def git(*args):
        result=subprocess.run(['git',*args],cwd=checkout,capture_output=True,timeout=60,check=False)
        common.require(result.returncode == 0,'Read-only recovery Git command failed: '+args[0]);return result.stdout
    git('init','--quiet');git('remote','add','origin',str(remote_url))
    lines=git('ls-remote','--heads','origin','refs/heads/'+branch).decode().strip().splitlines()
    common.require(len(lines) == 1,'Exact production records branch is absent or ambiguous')
    expected=lines[0].split();common.require(len(expected) == 2 and expected[1] == 'refs/heads/'+branch,'Recovery branch identity differs')
    git('fetch','--no-tags','--depth=1','origin','refs/heads/'+branch)
    commit=git('rev-parse','FETCH_HEAD').decode().strip()
    common.require(commit == expected[0],'Records branch changed during independent readback; retry read-only')
    git('checkout','--quiet','--detach','FETCH_HEAD')
    common.require(not (checkout/'.git/objects/info/alternates').exists(),'Independent recovery has alternate Git objects')
    pointer=validate_pointer(_decode(_bounded_bytes(checkout/'latest.json',1024*1024)),branch=branch)
    reader=archive or GitHubReleaseArchive()
    store=recover_snapshot(pointer['snapshot_ref'],reader,work/'state',source_root=ROOT)
    recovered=store.recover();snapshot=store.snapshot_manifest()
    common.require(snapshot['snapshot_id'] == pointer['snapshot_id'],'Recovered originals differ from the Git pointer')
    report={'schema_version':'nba-sdv-production-independent-recovery-v1','protocol_id':common.PROTOCOL_ID,
        'branch':branch,'commit':commit,'snapshot_ref':pointer['snapshot_ref'],'snapshot_id':snapshot['snapshot_id'],
        'recovered_at':stamp(common.now()),'genuine_issued':recovered['genuine_issued'],
        'counts':{key:len(recovered[key]) for key in ('forecasts','outcomes','grades')},
        'admissions':recovered['admissions'],'read_only':True,'source_http_requests':0,'generated_forecasts':0}
    (work/'recovery-report.json').write_bytes(canonical(report)+b'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--branch',required=True);parser.add_argument('--work-root',required=True)
    args=parser.parse_args();print(canonical(recover(args.branch,args.work_root)).decode())


if __name__ == '__main__':main()

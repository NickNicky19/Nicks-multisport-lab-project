"""Build an isolated local preview from recovered DEV originals; never generate.

Fetch the documented diagnostics branch separately, then pass that checkout as
--records-root. Current trusted website code renders the unchanged archived data.
No remote code is executed and no source/provider requests are performed.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from multisport_lab.integrity import IntegrityError
from multisport_lab.publication import build_site
from multisport_lab.sdv_daily_remote import snapshot_manifest
from multisport_lab.sdv_daily_store import DailyStore


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    records=args.records_root.absolute();output=args.output.absolute()
    if any(path.is_symlink() for path in (output,*output.parents)):
        raise IntegrityError("Preview output cannot traverse a symlink")
    output=output.resolve()
    if (output == ROOT or ROOT.is_relative_to(output) or output == records
            or output.is_relative_to(records) or records.is_relative_to(output)):
        raise IntegrityError("Preview artifact and recovered originals must be separate")
    if output.is_relative_to(ROOT) and not any(output.is_relative_to(ROOT/name) for name in ("output",".local-data")):
        raise IntegrityError("Preview cannot replace tracked project directories")
    before=snapshot_manifest(records);recovery=DailyStore(records).recover()
    if not recovery["forecasts"] or any(body["mode"] != "DEVELOPMENT_ONLY" for _,body in recovery["forecasts"]):
        raise IntegrityError("This preview command requires explicitly development-only originals")
    commit=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="nml-sdv-preview-build-") as folder:
        staged=Path(folder)
        for name in ("web","config","evidence"):
            shutil.copytree(ROOT/name,staged/name)
        for name in ("records","daily/records"):
            shutil.copytree(records/name,staged/name)
        manifest=build_site(staged,output,build_commit=commit,now=datetime.now(timezone.utc))
        if manifest["daily_research_error"] is not None:raise IntegrityError("Daily preview export failed")
    if snapshot_manifest(records) != before:raise IntegrityError("Recovered original records changed during preview")
    print(f"Built {len(recovery['forecasts'])} DEVELOPMENT_ONLY bundles at {output}; zero genuine issuance or deployment")


if __name__ == "__main__":main()

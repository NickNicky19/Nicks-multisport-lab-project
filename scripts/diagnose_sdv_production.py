#!/usr/bin/env python3
"""One purposeful DEV-only full-history shard/checkpoint diagnostic.

No sports HTTP, genuine activation, public export or accuracy evaluation exists
here. A hosted run needs an explicit diagnostic archive flag and uses this
repository's draft-only diagnostic release/branch. Local defaults use a
temporary bare Git remote and filesystem archive. Never truncate fixed history.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import timedelta
import hashlib
import io
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from multisport_lab.integrity import IntegrityError, canonical, stamp, utc
from multisport_lab import sdv_production_common as common
from multisport_lab import sdv_production_inputs as inputs
from multisport_lab import sdv_production_forecasts as forecasts
from multisport_lab.sdv_production_archive import FileArchive, GitHubReleaseArchive
from multisport_lab.sdv_production_remote import ProductionGitCheckpointWriter
from multisport_lab.sdv_production_store import ProductionStore

PURPOSE="full-26645-history-16-player-original-checkpoint-latency"
EVENT_ID="999999999"
PLAYER_COUNT=16


def _csv(rows):
    out=io.StringIO(newline="");writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return out.getvalue().encode()


def synthetic_assets(history,*,at):
    """Invented schedule/roster; retained IDs are diagnostic aliases, not facts."""
    at=utc(at);start=at+timedelta(days=3);season=start.year+int(start.month >= 7)
    counts=Counter(row.player_id for row in history)
    pids=sorted(counts,key=lambda pid:(-counts[pid],int(pid)))[:PLAYER_COUNT]
    common.require(len(pids) == PLAYER_COUNT,"Diagnostic needs sixteen distinct retained player-ID aliases; no padded or repeated subjects")
    event={"id":EVENT_ID,"game_id":EVENT_ID,"uid":"s:40~l:46~e:"+EVENT_ID+"~c:"+EVENT_ID,"season":str(season),"season_type":"2",
        "date":stamp(start),"start_date":stamp(start),"game_date_time":stamp(start),"home_id":"25","away_id":"7",
        "home_display_name":"SYNTHETIC DIAGNOSTIC HOME","away_display_name":"SYNTHETIC DIAGNOSTIC AWAY",
        "status_type_name":"STATUS_SCHEDULED","status_type_state":"pre","status_type_completed":"false","time_valid":"true"}
    roster=[{"season":str(season),"athlete_id":pid,"uid":"s:40~l:46~a:"+pid,"team_id":"25" if index < 8 else "7",
        "team_display_name":event["home_display_name"] if index < 8 else event["away_display_name"],
        "display_name":"SYNTHETIC diagnostic alias "+str(index+1),"status_type":"active","status_name":"Active","status_id":"1"}
        for index,pid in enumerate(pids)]
    result={}
    for role,raw,tag,name in (("schedule",_csv([event]),"espn_nba_schedules","nba_schedule_"+str(season)+".csv"),
            ("roster",_csv(roster),"espn_nba_rosters","rosters_"+str(season)+".csv")):
        route="https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"+tag+"/"+name
        original=canonical({"nml_synthetic_diagnostic":True,"description":"INVENTED METADATA: not captured publisher evidence",
            "tag_name":tag,"assets":[{"id":1 if role == "schedule" else 2,"name":name,"size":len(raw),
                "browser_download_url":route,"digest":"sha256:"+hashlib.sha256(raw).hexdigest(),"updated_at":stamp(at-timedelta(minutes=10))}]})
        meta=inputs.source_metadata(raw,original,{"role":role,"release_tag":tag,"asset_name":name,"asset_url":route},
            retrieval_started_at=at-timedelta(seconds=1),retrieved_at=at,
            metadata_retrieval_started_at=at-timedelta(seconds=3),metadata_retrieved_at=at-timedelta(seconds=2))
        result[role]=(raw,meta,original)
    return result,start


def _git(*args,cwd=None):
    result=subprocess.run(["git",*args],cwd=cwd,capture_output=True,text=True,check=False,timeout=60)
    common.require(result.returncode == 0,"Local diagnostic Git setup failed: "+args[0])
    return result.stdout.strip()


def local_remote(root):
    """Small throwaway base avoids copying or altering any project Git refs."""
    root=Path(root);bare=root/"bare.git";seed=root/"seed";seed.mkdir(parents=True)
    _git("init","--quiet","--bare",str(bare));_git("init","--quiet",cwd=seed)
    (seed/"README.txt").write_text("SYNTHETIC diagnostic remote; no public research.\n",encoding="utf-8")
    _git("add","README.txt",cwd=seed)
    _git("-c","user.name=NML diagnostic","-c","user.email=diagnostic@users.noreply.github.com","commit","--quiet","-m","Synthetic diagnostic base",cwd=seed)
    commit=_git("rev-parse","HEAD",cwd=seed);_git("push",str(bare),"HEAD:refs/heads/main",cwd=seed)
    return str(bare),commit


def run_diagnostic(work_dir,*,model_commit=None,hosted=False,authorize_diagnostic_archive=False):
    """Exercise the complete original-to-independent-restart path exactly once."""
    common.require(type(hosted) is bool and type(authorize_diagnostic_archive) is bool,"Invalid diagnostic flags")
    common.require(not hosted or authorize_diagnostic_archive,"Hosted diagnostic archive writes require explicit authorization")
    common.require(hosted or not authorize_diagnostic_archive,"Diagnostic archive flag is only meaningful with --hosted")
    if hosted:
        common.require(os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_REPOSITORY") == common.REPOSITORY,
            "Hosted diagnostic must run in this repository's actual Actions environment")
        common.sha(model_commit,40)
    work=Path(work_dir).absolute()
    common.require(not work.is_relative_to(ROOT) and not ROOT.is_relative_to(work),"Diagnostic state must be isolated from repository/history")
    work.mkdir(parents=True,exist_ok=True)
    common.require(not any(work.iterdir()),"Use one new empty retained diagnostic work directory")
    overall=time.monotonic();started=stamp(common.now());stages={}
    timer=time.monotonic();history_ref,history,provenance=forecasts.retained_history(ROOT)
    common.require(len(history) == common.HISTORY_ROWS,"Diagnostic refuses a truncated historical panel")
    stages["fixed_history_authentication_seconds"]=time.monotonic()-timer
    timer=time.monotonic();binding=forecasts.make_source_binding(model_commit,root=ROOT)
    assets,start=synthetic_assets(history,at=common.now())
    raw_s,meta_s,original_s=assets["schedule"];raw_r,meta_r,original_r=assets["roster"]
    originals={"schedule":original_s,"roster":original_r}
    plan=inputs.make_plan(raw_s,raw_r,meta_s,meta_r,source_originals=originals,game_date=start.date().isoformat(),producer_binding=binding,mode="DEVELOPMENT_ONLY")
    input_body=inputs.make_input(plan,EVENT_ID,raw_s,raw_r,meta_s,meta_r,source_originals=originals,mode="DEVELOPMENT_ONLY")
    common.require(len(input_body["candidates"]) == PLAYER_COUNT and len(input_body["shards"]) == 1,"Diagnostic must use the full sixteen-player shard")
    stages["synthetic_input_and_binding_seconds"]=time.monotonic()-timer
    token=common.now().strftime("%Y%m%dT%H%M%S");tag="diagnostics-nml-nba-production-load-"+token.lower()
    branch="diagnostics/sdv-production-load-"+token
    archive=GitHubReleaseArchive(allow_diagnostics=True) if hosted else FileArchive(work/"archive",allow_diagnostics=True)
    timer=time.monotonic();source_refs=tuple(archive.retain_source(*assets[role],tag=tag) for role in ("schedule","roster"))
    stages["raw_source_archive_and_recovery_seconds"]=time.monotonic()-timer
    store=ProductionStore(work/"state",source_root=ROOT,source_resolver=archive.recover_source,
        snapshot_resolver=lambda ref:archive.get_json(ref)["ledger_snapshot"],allow_diagnostics=True)
    plan_ref=store.append_body(plan,archive_refs=source_refs)
    input_ref=store.append_body(input_body,references=(plan_ref,),archive_refs=source_refs)
    if hosted:remote_url=common.REMOTE_URL;base_commit=_git("rev-parse","HEAD",cwd=ROOT)
    else:remote_url,base_commit=local_remote(work/"git")
    writer=ProductionGitCheckpointWriter(ROOT,work/"writer",base_commit=base_commit,branch=branch,archive=archive,tag=tag,
        remote_url=remote_url,allow_local_test_remote=not hosted,allow_diagnostics=True,command_seconds=60)
    timer=time.monotonic();writer.prepare();stages["writer_setup_seconds"]=time.monotonic()-timer
    checkpoints=[]
    def checkpoint(refs):
        before=stamp(common.now());tick=time.monotonic();proof=writer.checkpoint(store,refs)
        checkpoints.append({"started_at":before,"completed_at":stamp(common.now()),"seconds":time.monotonic()-tick,
            "target_record_ids":[ref.record_id for ref in refs],"proof":proof})
        return proof
    checkpoint((input_ref,))
    forecasts.prepare_intent(store,input_ref,binding,input_body["shards"][0],plan_ref=plan_ref,checkpoint=checkpoint,mode="DEVELOPMENT_ONLY")
    timer=time.monotonic();forecasts.issue_shard(store,input_ref,binding,input_body["shards"][0],plan_ref=plan_ref,checkpoint=checkpoint,mode="DEVELOPMENT_ONLY")
    stages["complete_shard_generation_persistence_checkpoint_seconds"]=time.monotonic()-timer
    pairs=[(ref,body) for ref,body in store.records() if body["schema_version"] == common.FORECAST_SCHEMA]
    common.require(len(pairs) == 2*PLAYER_COUNT and all(body["mode"] == "DEVELOPMENT_ONLY" and body["issued_at"] is None for _,body in pairs),"Diagnostic produced an incomplete or genuine record")
    timer=time.monotonic()
    restarted=ProductionStore(work/"restart",source_root=ROOT,source_resolver=archive.fresh_reader().recover_source,
        snapshot_resolver=lambda ref:archive.fresh_reader().get_json(ref)["ledger_snapshot"],allow_diagnostics=True)
    second=ProductionGitCheckpointWriter(ROOT,work/"restart-writer",base_commit=base_commit,branch=branch,archive=archive.fresh_reader(),tag=tag,
        remote_url=remote_url,allow_local_test_remote=not hosted,allow_diagnostics=True,command_seconds=60)
    second.prepare();second.restore(restarted)
    common.require(store.snapshot_manifest() == restarted.snapshot_manifest(),"Independent restart differs from original retained bytes")
    stages["separate_restart_readback_seconds"]=time.monotonic()-timer
    completion={record_id:entry["proof"]["original_recovery"]["remote_recovered_at"] for entry in checkpoints for record_id in entry["target_record_ids"]}
    timing={"generation_seconds":[],"verification_seconds":[],"verification_to_local_persistence_seconds":[],"local_to_original_readback_seconds":[],"generation_to_original_readback_seconds":[]}
    for ref,body in pairs:
        start_clock=common.clock(body["generation_started_at"]);generated=common.clock(body["generation_completed_at"]);verified=common.clock(body["verified_at"])
        local=common.clock(store.local_completion(ref)["local_completed_at"]);recovered=common.clock(completion[ref.record_id])
        for key,value in (("generation_seconds",generated-start_clock),("verification_seconds",verified-generated),
                ("verification_to_local_persistence_seconds",local-verified),("local_to_original_readback_seconds",recovered-local),
                ("generation_to_original_readback_seconds",recovered-start_clock)):
            timing[key].append(value.total_seconds())
    maxima={key:max(values) for key,values in timing.items()};capacity=store.capacity()
    envelopes=[(Path(store.root)/"records/forecasts"/(ref.record_id+".json")).stat().st_size for ref,_ in pairs]
    report={"schema_version":"nba-sdv-production-load-diagnostic-v1","purpose":PURPOSE,"evidence_lane":"DEVELOPMENT_ONLY",
        "synthetic_source_metadata":True,"sports_data_requests":0,"genuine_forecasts":0,"published_offers":0,"public_publication":False,
        "prospective_outcomes":0,"prospective_grades":0,"qualified_tickets":0,"financial_settlements":0,
        "started_at":started,"completed_at":stamp(common.now()),"total_seconds":time.monotonic()-overall,"stages":stages,
        "source_binding":binding,"fixed_history_ref":history_ref.to_record(),"fixed_history_rows":len(history),
        "fixed_history_panel_sha256":common.HISTORY_SHA256,"players":PLAYER_COUNT,"models":["R0","K0"],"forecast_records":len(pairs),
        "all14_categories":all(len(body["categories"]) == 14 for _,body in pairs),"maximum_encoded_forecast_envelope_bytes":max(envelopes),
        "maximum_actual_stage_seconds":maxima,"within_300_second_original_latency":maxima["generation_to_original_readback_seconds"] <= 300,
        "within_900_second_generation_window_duration":stages["complete_shard_generation_persistence_checkpoint_seconds"] <= 900,
        "actual_T90_issuance_tested":False,"capacity":capacity,"independent_restart_verified":True,"hosted":hosted,
        "archive_tag":tag,"records_branch":branch,"retained_work_dir":str(work),"checkpoints":checkpoints,
        "outcome_fixture_note":"No future result was manufactured. APPEARED/DNP/correction semantics have separate invented-source unit tests; this diagnostic measures original delivery only.",
        "limitations":["No model accuracy or comparative aggregate evaluated.","Synthetic future schedule/roster with retained IDs used only as aliases.",
            "Development timing does not establish future input availability or prospective eligibility.","Local filesystem/bare Git recovery is not hosted durability." if not hosted else "Diagnostic draft archive and branch are excluded from public forecasts."]}
    (work/"report.json").write_bytes(canonical(report)+b"\n")
    return report


def parser():
    result=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    result.add_argument("--work-dir",required=True);result.add_argument("--producer-commit","--model-commit",dest="model_commit")
    result.add_argument("--hosted",action="store_true");result.add_argument("--authorize-diagnostic-archive",action="store_true")
    return result


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        result=run_diagnostic(args.work_dir,model_commit=args.model_commit,hosted=args.hosted,authorize_diagnostic_archive=args.authorize_diagnostic_archive)
    except (IntegrityError,OSError) as exc:
        print("Diagnostic failed; retained originals are not prospective issuance: "+str(exc),file=sys.stderr);return 1
    print(json.dumps({key:result[key] for key in ("purpose","forecast_records","maximum_encoded_forecast_envelope_bytes",
        "maximum_actual_stage_seconds","capacity","independent_restart_verified","genuine_forecasts","retained_work_dir")},indent=2))
    return 0


if __name__ == "__main__":raise SystemExit(main())

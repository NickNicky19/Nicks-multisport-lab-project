"""Explicitly synthetic source packs. Never saved as actual evidence."""
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from unittest.mock import patch
from multisport_lab.integrity import canonical, digest, stamp, load_json, utc
from multisport_lab.nba_data import NBAPlayerGame
from multisport_lab.pregame_sources import (compact_history, freeze_selection, make_pack, _panel_bytes)

CUTOFF = datetime(2026, 10, 20, 17, 30, tzinfo=timezone.utc)
CAPTURE = CUTOFF - timedelta(minutes=5)
ISSUE = CUTOFF + timedelta(seconds=30)


def synthetic_pack():
    event = {"id_namespace":"espn", "league":"NBA", "event_id":"999999999",
        "event_starts_at":stamp(CUTOFF+timedelta(minutes=90)), "home_team_id":"1", "away_team_id":"2",
        "status":"PRE_GAME", "season_ending_year":2027, "season_type":"2"}
    event["event_version"]=digest(event)
    rosters = {team:[{"player_id":str(int(team)*10+i),"team_id":team,"player_label":f"Synthetic {team}-{i}"} for i in range(2)] for team in ("1","2")}
    with patch("multisport_lab.pregame_sources._now", return_value=CAPTURE-timedelta(seconds=1)):
        selection=freeze_selection(event,rosters)
    rows=[]
    for i in range(2):
        rows.append(NBAPlayerGame(id_namespace="espn",event_id=str(100+i),player_id=str(10+i),team_id="1",opponent_id="2",
            season_ending_year=2026,season_type="2",event_start=datetime(2026,4,1+i,19,tzinfo=timezone.utc),
            participation="APPEARED",minutes=20.,minutes_precision="rounded_whole_minutes",points=12+i*2,
            fgm=4+i,fga=8+i,fg2m=2+i,fg3m=2,fg3a=4,ftm=2,fta=2,oreb=1,dreb=2,rebounds=3,
            assists=4,turnovers=1,blocks=0,steals=1,final_status="FINAL"))
    history=compact_history(rows); panel=_panel_bytes(rows)
    base="https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
    sources=[]
    for key,path in [("scoreboard","scoreboard?dates=20261020"),("summary","summary?event=999999999"),("roster-1","teams/1/roster"),("roster-2","teams/2/roster")]:
        sources.append({"source_id":key,"source_url":base+"/"+path,"request_started_at":stamp(CAPTURE),
            "observed_at":stamp(CAPTURE+timedelta(seconds=1)),"response_completed_at":stamp(CAPTURE+timedelta(seconds=1)),
            "source_updated_at":None,"source_response_generated_at":None,"raw_sha256":"a"*64,"raw_bytes":100,
            "http_status":200,"http_date":None,"etag":None,"last_modified":None})
    receipt_path=Path(__file__).resolve().parents[1]/"evidence/data/2026-10-19-source-receipts.json"
    originals={row["key"]:row for row in load_json(receipt_path)["receipts"]}
    prior=[]
    for key in ["sdv_player_box_2026","sdv_schedule_2026"]:
        r=originals[key]
        prior.append({"source_id":key,"source_url":r["url"],"raw_sha256":r["sha256"],
            "raw_bytes":r["bytes"],"observed_at":stamp(utc(r["observed_at"])),
            "source_updated_at":stamp(utc(r["source_updated_at"])),"source_version":"github-asset:"+str(r["github_asset_id"])})
    provenance={"normalized_panel_sha256":hashlib.sha256(panel).hexdigest(),"normalized_panel_bytes":len(panel),
        "normalized_panel_rows":len(rows),"normalization_version":"nba-panel-preparation-v1","source_receipts":prior,
        "upstream_exclusions":load_json(Path(__file__).resolve().parents[1]/"evidence/data/2026-10-19-panel_preparation_summary.json")["upstream_exclusions"],
        "availability_semantics":"observed archive before future freeze; original historical completion bounds remain reconstructed",
        "source_receipts_sha256":hashlib.sha256(receipt_path.read_bytes()).hexdigest(),"cohort":"all retained complete APPEARED FINAL source-stage2 standard-team rows; no truncation",
        "current_season_history_claim":False,"history_freshness":"latest event 2026-04-13; no 2026-27 appearances",
        "normalizer_source_sha256":"d"*64}
    with patch("multisport_lab.pregame_sources._now", return_value=CAPTURE+timedelta(seconds=2)), patch("multisport_lab.pregame_sources.PANEL_SHA", provenance["normalized_panel_sha256"]):
        return make_pack(event,rosters,sources,selection,history,provenance)

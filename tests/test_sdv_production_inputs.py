"""Bounded invented native production source/input contracts, never collection."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
import unittest
from unittest.mock import patch

from multisport_lab import sdv_production_inputs as source
from multisport_lab import sdv_production_common as common
from multisport_lab.integrity import IntegrityError, canonical, stamp, utc
from test_sdv_daily_inputs import fixtures, csv_bytes


def synthetic_binding():
    return common.seal({"schema_version":source.BINDING_SCHEMA,"commit":"1"*40,"files":{
        "multisport_lab/baseline.py":common.LAW_SHA256["R0"],"multisport_lab/development_003.py":common.LAW_SHA256["K0"]},
        "law_sha256":deepcopy(common.LAW_SHA256)},"binding_id")


class ProductionInputTests(unittest.TestCase):
    def setUp(self):
        self.now=utc("2026-10-23T13:17:00.000000Z")
        clock=patch.object(common,"now",side_effect=lambda:self.now);clock.start();self.addCleanup(clock.stop)
        _,_,schedule,roster,_=fixtures(); self.schedule=[];self.roster=[]
        # Three events and 40 active subjects each: explicitly beyond both old
        # caps, while retaining each source's complete all-active team cohort.
        for index in range(3):
            row=deepcopy(schedule[0]);eid=str(900+index);starts=stamp(utc("2026-10-24T00:00:00.000000Z")+timedelta(hours=index))
            row.update(id=eid,game_id=eid,uid="s:40~l:46~e:"+eid+"~c:"+eid,date=starts,start_date=starts,game_date_time=starts,
                home_id=str(100+index*2),away_id=str(101+index*2),home_display_name="Synthetic Home "+str(index),away_display_name="Synthetic Away "+str(index))
            self.schedule.append(row)
            for home in (True,False):
                for player_index in range(20):
                    player=deepcopy(roster[0]);pid=str(1000+index*100+int(not home)*20+player_index)
                    player.update(athlete_id=pid,uid="s:40~l:46~a:"+pid,team_id=row["home_id"] if home else row["away_id"],
                        team_display_name=row["home_display_name"] if home else row["away_display_name"],display_name="Synthetic Player "+pid)
                    self.roster.append(player)
        self.binding=synthetic_binding()

    def assets(self,*,age=timedelta(hours=12),metadata_clocks=True):
        raws=[csv_bytes(self.schedule),csv_bytes(self.roster)]; metas=[];originals={}
        for index,(role,raw) in enumerate(zip(("schedule","roster"),raws)):
            tag="espn_nba_schedules" if role == "schedule" else "espn_nba_rosters"
            name="nba_schedule_2027.csv" if role == "schedule" else "rosters_2027.csv"
            url="https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"+tag+"/"+name
            original=canonical({"tag_name":tag,"assets":[{"id":123+index,"name":name,"size":len(raw),"browser_download_url":url,
                "digest":"sha256:"+hashlib.sha256(raw).hexdigest(),"updated_at":stamp(self.now-age)}]})
            metadata=source.source_metadata(raw,original,{"role":role,"release_tag":tag,"asset_name":name,"asset_url":url},
                retrieval_started_at=stamp(self.now-timedelta(minutes=2)),retrieved_at=stamp(self.now-timedelta(minutes=1)),
                metadata_retrieval_started_at=stamp(self.now-timedelta(minutes=4)) if metadata_clocks else None,
                metadata_retrieved_at=stamp(self.now-timedelta(minutes=3)) if metadata_clocks else None)
            metas.append(metadata);originals[role]=original
        return *raws,*metas,originals

    def build(self,assets=None,*,mode="DEVELOPMENT_ONLY",at=None):
        assets=assets or self.assets()
        return source.make_plan(*assets[:4],source_originals=assets[4],game_date="2026-10-24",producer_binding=self.binding,mode=mode,at=at)

    def fresh(self,plan,assets=None,*,mode=None,at=None):
        assets=assets or self.assets()
        return source.make_input(plan,"900",*assets[:4],source_originals=assets[4],mode=mode or plan["mode"],at=at)

    def test_all_events_all_active_players_and_exact_shards_are_native_production_records(self):
        assets=self.assets();plan=self.build(assets)
        self.assertEqual(len(plan["events"]),3)
        self.assertEqual([len(event["candidates"]) for event in plan["events"]],[40,40,40])
        self.assertEqual([len(shard) for shard in plan["events"][0]["shards"]],[16,16,8])
        self.assertEqual(plan["protocol_id"],"NBA-SDV-PRODUCTION-001")
        self.assertNotIn("source_interpretation",plan["events"][0])
        self.assertTrue(all(source["upstream_observed_at"] is None for source in plan["sources"]))
        self.assertIn("CONFIRMED_PARTICIPATION",plan["missing_information"])
        self.assertEqual(plan["policy"]["participation"],"CONDITIONAL_ON_APPEARANCE")
        self.assertIs(source.verify_plan_sources(plan,*assets[:4],source_originals=assets[4]),plan)

    def test_uncommitted_binding_is_development_only(self):
        self.binding=common.seal({key:value for key,value in self.binding.items() if key != "binding_id"}|{"commit":None},"binding_id")
        self.assertIsNone(self.build()["producer_binding"]["commit"])
        with self.assertRaisesRegex(IntegrityError,"frozen producer commit"):self.build(mode="PROSPECTIVE_RESEARCH")

    def test_boxscore_uses_its_real_source_family_and_exact_release_original(self):
        raw=b"game_id,points\n900,12\n";role="boxscore";tag="espn_nba_player_boxscores";name="player_box_2027.csv"
        route={"role":role,"release_tag":tag,"asset_name":name,"asset_url":"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"+tag+"/"+name}
        original=canonical({"tag_name":tag,"assets":[{"id":999,"name":name,"size":len(raw),"browser_download_url":route["asset_url"],
            "digest":"sha256:"+hashlib.sha256(raw).hexdigest(),"updated_at":stamp(self.now-timedelta(hours=48))}]})
        metadata=source.source_metadata(raw,original,route,retrieval_started_at=stamp(self.now-timedelta(minutes=2)),retrieved_at=stamp(self.now-timedelta(minutes=1)),
            metadata_retrieval_started_at=stamp(self.now-timedelta(minutes=4)),metadata_retrieved_at=stamp(self.now-timedelta(minutes=3)))
        # Metadata authentication does not admit finality, nor inherit the
        # pregame publisher-age gate for verified older final evidence.
        self.assertIs(source.validate_source(raw,metadata,original,role,2027),metadata)
        with self.assertRaisesRegex(IntegrityError,"season conflicts"):source.validate_source(raw,metadata,original,role,2030)
        with self.assertRaises(IntegrityError):source.validate_source(raw,metadata,b"{}",role,2027)

    def test_source_order_does_not_change_complete_event_player_order(self):
        self.schedule.reverse();self.roster.reverse();plan=self.build()
        self.assertEqual([event["event"]["event_id"] for event in plan["events"]],["900","901","902"])
        self.assertEqual([player["player_id"] for player in plan["events"][0]["candidates"]],[str(number) for number in range(1000,1040)])

    def test_inactive_players_and_unscheduled_events_have_explicit_exclusions(self):
        self.roster[0].update(status_type="inactive",status_name="Inactive",status_id="2")
        self.schedule[1].update(status_type_name="STATUS_POSTPONED")
        plan=self.build();self.assertEqual(len(plan["events"]),2)
        self.assertEqual(len(plan["events"][0]["candidates"]),39)
        self.assertTrue(any(row.get("player_id") == "1000" and row["reason"] == "SOURCE_ROSTER_NOT_ACTIVE" for row in plan["exclusions"]))
        self.assertEqual(plan["inventory"][1]["exclusion_reasons"],["NOT_SCHEDULED"])

    def test_empty_game_date_still_authenticates_full_table_year(self):
        for row in self.schedule:
            for key in ("date","start_date","game_date_time"):row[key]=row[key].replace("2026-10-24","2026-10-25")
        plan=self.build();self.assertEqual(plan["events"],[]);self.assertEqual(plan["outside_game_date_rows"],3)
        assets=list(self.assets())
        for index,role in enumerate(("schedule","roster")):
            metadata=deepcopy(assets[index+2]);metadata["asset_name"]=metadata["asset_name"].replace("2027","2030");metadata["asset_url"]=metadata["asset_url"].replace("2027","2030")
            original=json.loads(assets[4][role]);original["assets"][0].update(name=metadata["asset_name"],browser_download_url=metadata["asset_url"])
            raw=canonical(original);assets[4][role]=raw
            assets[index+2]=source.source_metadata(assets[index],raw,metadata,retrieval_started_at=metadata["retrieval_started_at"],retrieved_at=metadata["retrieved_at"],
                metadata_retrieval_started_at=metadata["metadata_retrieval_started_at"],metadata_retrieved_at=metadata["metadata_retrieved_at"])
        with self.assertRaisesRegex(IntegrityError,"asset year"):self.build(assets)

    def test_stale_future_and_missing_clock_contracts_reject(self):
        self.assertEqual(len(self.build(self.assets(age=timedelta(hours=36)))["events"]),3)
        with self.assertRaisesRegex(IntegrityError,"stale"):self.build(self.assets(age=timedelta(hours=36,microseconds=1)))
        for field,value in (("retrieved_at",stamp(self.now+timedelta(seconds=1))),("publisher_updated_at",None)):
            assets=list(self.assets());assets[2][field]=value
            with self.subTest(field=field),self.assertRaises(IntegrityError):self.build(assets)
        assets=self.assets(metadata_clocks=False)
        self.assertIn("PUBLISHER_METADATA_OBSERVATION_CLOCK",self.build(assets)["missing_information"])
        with self.assertRaisesRegex(IntegrityError,"metadata needs actual capture"):self.build(assets,mode="PROSPECTIVE_RESEARCH")

    def test_missing_duplicate_conflicting_identities_reject_without_partial_coverage(self):
        original_s,original_r=deepcopy(self.schedule),deepcopy(self.roster)
        for mutate in (lambda:self.schedule.append(deepcopy(self.schedule[0])),lambda:self.roster.append(deepcopy(self.roster[0])),
                lambda:self.schedule[0].update(game_date_time=""),lambda:self.roster[0].update(uid="s:40~l:46~a:999"),
                lambda:self.schedule[0].update(start_date="2026-10-24T00:01:00.000000Z")):
            self.schedule,self.roster=deepcopy(original_s),deepcopy(original_r);mutate()
            with self.subTest(mutate=mutate),self.assertRaises(IntegrityError):self.build()

    def test_complete_cohort_and_event_ceiling_fail_without_truncation(self):
        original_roster=deepcopy(self.roster)
        first=[row for row in self.roster if row["team_id"] == "100"][0]
        for index in range(25):
            row=deepcopy(first);pid=str(9000+index);row.update(athlete_id=pid,uid="s:40~l:46~a:"+pid);self.roster.append(row)
        with self.assertRaisesRegex(IntegrityError,"no player truncation"):self.build()
        self.roster=original_roster
        # Additional events sharing teams are a valid source inventory; the
        # declared safety ceiling must refuse the complete date, not select 32.
        for index in range(30):
            row=deepcopy(self.schedule[0]);eid=str(10000+index);row.update(id=eid,game_id=eid,uid="s:40~l:46~e:"+eid+"~c:"+eid);self.schedule.append(row)
        with self.assertRaisesRegex(IntegrityError,"no event truncation"):self.build()

    def test_genuine_plan_and_input_use_actual_completion_and_refuse_supplied_clocks(self):
        with self.assertRaisesRegex(IntegrityError,"supplied clock"):self.build(mode="PROSPECTIVE_RESEARCH",at=self.now)
        plan=self.build(mode="PROSPECTIVE_RESEARCH")
        self.now=common.clock(plan["events"][0]["cutoff_at"])-timedelta(minutes=20)
        with self.assertRaisesRegex(IntegrityError,"supplied clock"):self.fresh(plan,mode="PROSPECTIVE_RESEARCH",at=self.now)
        assets=self.assets();body=self.fresh(plan,assets)
        self.assertEqual(body["mode"],"PROSPECTIVE_RESEARCH")
        self.assertEqual(body["producer_binding"],plan["producer_binding"])
        self.assertIs(source.verify_input_sources(body,*assets[:4],source_originals=assets[4],plan=plan),body)
        self.now=common.clock(plan["events"][0]["cutoff_at"])
        checked=source.freshness(body,at=self.now,require_retrieval_window=True)
        self.assertEqual(checked["forecast_horizon_seconds"],5400)
        self.now+=timedelta(days=1)
        self.assertIs(source.verify_input_sources(body,*assets[:4],source_originals=assets[4],plan=plan),body)

    def test_preparation_or_changed_event_cohort_cannot_become_fresh_input(self):
        preparation=self.assets();plan=self.build(preparation,mode="PROSPECTIVE_RESEARCH")
        self.now=common.clock(plan["events"][0]["cutoff_at"])-timedelta(minutes=20)
        with self.assertRaisesRegex(IntegrityError,"pre-cutoff"):self.fresh(plan,preparation)
        self.roster[0].update(status_type="inactive",status_name="Inactive",status_id="2")
        with self.assertRaisesRegex(IntegrityError,"version/cohort"):self.fresh(plan)
        self.roster[0].update(status_type="active",status_name="Active",status_id="1")
        for key in ("date","start_date","game_date_time"):self.schedule[0][key]="2026-10-24T00:01:00.000000Z"
        with self.assertRaisesRegex(IntegrityError,"version/cohort"):self.fresh(plan)

    def test_late_source_validation_completion_refuses_original_record(self):
        original=source._tables
        def delayed(*args):
            result=original(*args);self.now+=timedelta(seconds=2);return result
        self.now=utc("2026-10-23T13:59:59.000000Z")
        with patch.object(source,"_tables",side_effect=delayed),self.assertRaisesRegex(IntegrityError,"window"):
            self.build(mode="PROSPECTIVE_RESEARCH")
        self.now=utc("2026-10-23T13:17:00.000000Z");plan=self.build(mode="PROSPECTIVE_RESEARCH")
        self.now=common.clock(plan["events"][0]["cutoff_at"])-timedelta(seconds=1)
        with patch.object(source,"_tables",side_effect=delayed),self.assertRaisesRegex(IntegrityError,"pre-cutoff"):
            self.fresh(plan)

    def test_live_valid_delayed_completion_is_retained_and_replayed(self):
        original=source._tables;begun=self.now
        def delayed(*args):
            result=original(*args);self.now+=timedelta(seconds=2);return result
        assets=self.assets()
        with patch.object(source,"_tables",side_effect=delayed):plan=self.build(assets,mode="PROSPECTIVE_RESEARCH")
        self.assertEqual(plan["planning_started_at"],stamp(begun));self.assertEqual(plan["planned_at"],stamp(begun+timedelta(seconds=2)))
        self.assertIs(source.verify_plan_sources(plan,*assets[:4],source_originals=assets[4]),plan)
        self.now=common.clock(plan["events"][0]["cutoff_at"])-timedelta(minutes=20);begun=self.now;assets=self.assets()
        with patch.object(source,"_tables",side_effect=delayed):body=self.fresh(plan,assets)
        self.assertEqual(body["normalization_started_at"],stamp(begun));self.assertEqual(body["normalized_at"],stamp(begun+timedelta(seconds=2)))
        self.assertIs(source.verify_input_sources(body,*assets[:4],source_originals=assets[4],plan=plan),body)

    def test_checksum_consistent_missing_event_or_player_fails_independent_byte_replay(self):
        assets=self.assets();plan=self.build(assets)
        changed=deepcopy(plan);changed["events"].pop();changed["inventory"].pop();changed["source_schedule_rows"]-=1
        changed["plan_seed"]=source._seed(changed["game_date"],changed["sources"],changed["producer_binding"],changed["events"])
        for row in changed["events"]:row["cycle_id"]=common.cycle_id(changed["game_date"],row["event"]["event_id"],changed["plan_seed"])
        changed=common.seal({key:value for key,value in changed.items() if key != "plan_id"},"plan_id")
        with self.assertRaisesRegex(IntegrityError,"source replay"):source.verify_plan_sources(changed,*assets[:4],source_originals=assets[4])
        self.now=common.clock(plan["events"][0]["cutoff_at"])-timedelta(minutes=20);assets=self.assets();body=self.fresh(plan,assets)
        body["candidates"].pop();size=body["policy"]["players_per_shard"];ids=[row["player_id"] for row in body["candidates"]]
        body["shards"]=[ids[index:index+size] for index in range(0,len(ids),size)]
        body=common.seal({key:value for key,value in body.items() if key != "input_id"},"input_id")
        with self.assertRaisesRegex(IntegrityError,"semantics differ"):source.verify_input_sources(body,*assets[:4],source_originals=assets[4])


if __name__ == "__main__":unittest.main()

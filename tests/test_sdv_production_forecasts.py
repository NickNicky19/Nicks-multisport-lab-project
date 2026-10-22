"""Invented production control/CSV examples; no collected data or model study."""
from contextlib import ExitStack, nullcontext
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace, ModuleType
import sys
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import sdv_production_forecasts as production
from multisport_lab import sdv_production_common as common
from multisport_lab import sdv_production_inputs as inputs
from multisport_lab import baseline
from multisport_lab.baseline import HistoricalAppearance, PrimitiveLine, WeightedOutcome, JointForecast, ForecastTarget
from multisport_lab.integrity import IntegrityError, canonical, digest, stamp, utc
from multisport_lab.ledger import LedgerRef


START=utc("2030-01-02T03:00:00.000000Z")
ISSUE=START-timedelta(minutes=89)
TRAINED=utc("2025-01-02T00:00:00.000000Z")


def csv_bytes(rows,fields=None):
    out=io.StringIO(newline="");writer=csv.DictWriter(out,fieldnames=fields or list(rows[0]));writer.writeheader();writer.writerows(rows)
    return out.getvalue().encode()


def binding():
    files={name:"f"*64 for name in production.SOURCE_FILES}
    files["multisport_lab/baseline.py"]=common.LAW_SHA256["R0"]
    files["multisport_lab/development_003.py"]=common.LAW_SHA256["K0"]
    return common.seal({"schema_version":production.BINDING_SCHEMA,"commit":"a"*40,"files":files,"law_sha256":dict(common.LAW_SHA256)},"binding_id")


class MemoryStore:
    """Only a producer restart-control double, not a durable-storage claim."""
    source_root=Path("/synthetic-unread-path")
    def __init__(self):self.bodies={};self.interrupt=None;self.acknowledged={};self.checkpoints=[]
    def lock(self):return nullcontext()
    def append_body(self,body,*,references=(),archive_refs=(),logical_id=None):
        if self.interrupt is not None and body.get("model_key") == self.interrupt:raise InterruptedError("Synthetic peer write interruption")
        kind=common.KINDS[body["schema_version"]]
        ref=LedgerRef(kind,digest({"logical":logical_id or digest(body),"kind":kind}),digest(body))
        self.bodies.setdefault(ref,deepcopy(body));return ref
    def read_body(self,ref):return deepcopy(self.bodies[ref])
    def records(self):return [(ref,deepcopy(body)) for ref,body in self.bodies.items()]
    def admission(self,ref):return {"eligible":True,"remote_recovered_at":self.acknowledged.get(ref)}
    def checkpoint(self,refs):
        self.checkpoints.append(tuple(refs))
        for ref in refs:self.acknowledged.setdefault(ref,stamp(production._now()))
    def _verified_forecast_write(self,body,references):return nullcontext()
    def recover(self):return {"forecasts":[(ref,body) for ref,body in self.records() if body["schema_version"] == production.FORECAST_SCHEMA]}


class ProductionFixture(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close);self.actual=ISSUE
        self.stack.enter_context(patch.object(production,"_now",side_effect=lambda:self.actual))
        self.stack.enter_context(patch.object(common,"now",side_effect=lambda:self.actual))
        self.binding=binding();self.input_ref=LedgerRef("input_captures","c"*64,"d"*64)
        self.history_ref=LedgerRef("research_inputs",common.HISTORY_ID,"e"*64)
        self.history=[SimpleNamespace(outcome_available_at=TRAINED)]*common.HISTORY_ROWS
        self.input={"schema_version":common.INPUT_SCHEMA,"protocol_id":common.PROTOCOL_ID,"plan_id":"1"*64,"cycle_id":"synthetic-production-cycle",
            "mode":"DEVELOPMENT_ONLY","producer_binding":self.binding,"input_id":"2"*64,"normalized_at":stamp(START-timedelta(minutes=100)),
            "event":{"event_id":"900","event_snapshot_id":"3"*64,"event_starts_at":stamp(START),"home_team_id":"25","away_team_id":"7",
                "home_team_name":"Synthetic Home","away_team_name":"Synthetic Away","season_ending_year":2030,"season_type":"2"},
            "candidates":[{"player_id":"1","player_label":"Invented Player","team_id":"25","opponent_id":"7"}],"shards":[["1"]]}
        self.input_api=SimpleNamespace(validate_input=lambda body:body,freshness=lambda *args,**kwargs:{},validate_source=inputs.validate_source)
        self.stack.enter_context(patch.object(production,"_inputs",return_value=self.input_api))
        original=production.validate_binding
        self.stack.enter_context(patch.object(production,"validate_binding",side_effect=lambda body,**kwargs:original(body,current=False)))
        self.stack.enter_context(patch.object(production,"_fit_laws",side_effect=self.laws))
        self.stack.enter_context(patch.object(production,"_development_laws",side_effect=self.laws))

    def laws(self,history,target):
        lines=[PrimitiveLine(20,4,2,1,10,10,2,0,0),PrimitiveLine(30,5,1,2,10,4,1,0,1),PrimitiveLine(12,1,0,0,2,1,0,1,2)]
        return {key:JointForecast(target,target.cutoff,TRAINED,"d"*64,tuple(WeightedOutcome("synthetic-"+str(i),target.player_id,line,w)
            for i,(line,w) in enumerate(zip(lines,weights))),3,3) for key,weights in (("R0",(.25,.25,.5)),("K0",(.2,.3,.5)))}

    def pair(self,mode="DEVELOPMENT_ONLY"):
        self.input["mode"]=mode
        return production.generate_pair(self.input,self.input_ref,self.binding,self.history_ref,self.history,player_id="1",mode=mode)

    def source(self,raw,role):
        tag="espn_nba_schedules" if role == "schedule" else "espn_nba_player_boxscores"
        name="nba_schedule_2030.csv" if role == "schedule" else "player_box_2030.csv"
        source={"role":role,"release_tag":tag,"asset_name":name,"asset_url":"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"+tag+"/"+name}
        meta_raw=canonical({"tag_name":tag,"assets":[{"id":1 if role == "schedule" else 2,"name":name,"size":len(raw),
            "browser_download_url":source["asset_url"],"digest":"sha256:"+hashlib.sha256(raw).hexdigest(),"updated_at":stamp(self.actual-timedelta(minutes=10))}]})
        meta=inputs.source_metadata(raw,meta_raw,source,retrieval_started_at=self.actual-timedelta(seconds=1),retrieved_at=self.actual,
            metadata_retrieval_started_at=self.actual-timedelta(seconds=3),metadata_retrieved_at=self.actual-timedelta(seconds=2))
        ref={"tag":"diagnostics-nml-nba-synthetic","name":"object-"+hashlib.sha256(raw).hexdigest()+".z","sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)}
        return ref,(raw,meta,meta_raw)

    def final_rows(self):
        event={"game_id":"900","home_id":"25","away_id":"7","season":"2030","season_type":"2","game_date_time":stamp(START),
            "status_type_completed":"true","status_type_name":"STATUS_FINAL","status_type_state":"post","home_score":"12","away_score":"12"}
        common_row={"game_id":"900","season":"2030","season_type":"2","game_date_time":stamp(START),"did_not_play":"false","minutes":"20",
            "points":"12","field_goals_made":"4","field_goals_attempted":"10","three_point_field_goals_made":"2","three_point_field_goals_attempted":"5",
            "free_throws_made":"2","free_throws_attempted":"2","rebounds":"4","offensive_rebounds":"1","defensive_rebounds":"3","assists":"3","turnovers":"1","blocks":"0","steals":"1",
            "team_score":"12","opponent_team_score":"12"}
        return event,[{**common_row,"athlete_id":"1","team_id":"25","opponent_team_id":"7"},{**common_row,"athlete_id":"2","team_id":"7","opponent_team_id":"25"}]

    def normalize(self,forecast,event,rows,*,previous=None):
        schedule_ref,schedule=self.source(csv_bytes([event]),"schedule")
        boxscore_ref,boxscore=self.source(csv_bytes(rows,fields=list(self.final_rows()[1][0])),"boxscore")
        sources={digest(schedule_ref):schedule,digest(boxscore_ref):boxscore}
        archive=SimpleNamespace(recover_source=lambda ref:sources[digest(ref)])
        body=production.normalize_outcome(forecast,self.input,archive=archive,schedule_ref=schedule_ref,boxscore_ref=boxscore_ref,previous=previous)
        return body,(schedule,boxscore)


class ProductionForecastTests(ProductionFixture):
    def test_source_binding_pins_frozen_and_new_executable_bytes_independently_of_head(self):
        # A tiny synthetic tree plus the two actual unchanged mathematical files;
        # mocked git supplies exact retained bytes, never a real reviewed commit.
        original=production.make_source_binding
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);project=Path(production.__file__).resolve().parents[1]
            for name in production.SOURCE_FILES:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes((project/name).read_bytes() if name in {"multisport_lab/baseline.py","multisport_lab/development_003.py"} else b"synthetic executable bytes\n")
            def git_show(args,**kwargs):return SimpleNamespace(returncode=0,stdout=(root/args[2].split(":",1)[1]).read_bytes())
            with patch.object(production.subprocess,"run",side_effect=git_show):
                pinned=original("a"*40,root=root)
                self.assertEqual(set(pinned["files"]),set(production.SOURCE_FILES));self.assertEqual(pinned["commit"],"a"*40)
                # The test does not consult git HEAD. Its frozen commit is passed
                # unchanged even after separate documentation could be added.
                self.assertEqual(original("a"*40,root=root),pinned)
                (root/"multisport_lab/sdv_production_forecasts.py").write_bytes(b"changed source\n")
                self.assertNotEqual(original("a"*40,root=root),pinned)
            with patch.object(production.subprocess,"run",return_value=SimpleNamespace(returncode=0,stdout=b"wrong source")):
                with self.assertRaisesRegex(IntegrityError,"differs from frozen commit"):original("a"*40,root=root)

    def test_both_complete_joint_models_preserve_all14_categories_and_conditioning(self):
        pair=self.pair();self.assertEqual([body["model_key"] for body in pair],["R0","K0"])
        for body in pair:
            self.assertEqual(set(row["code"] for row in body["categories"]),set(baseline.MARKETS));self.assertIsNone(body["issued_at"])
            self.assertEqual(body["conditioning"],"CONDITIONAL_ON_APPEARANCE");self.assertEqual(body["joint_recipe"]["omitted_atoms"],0)
            production.validate_forecast(body,self.input)
        genuine=self.pair("PROSPECTIVE_RESEARCH")
        self.assertTrue(all(body["issued_at"] == stamp(self.actual) for body in genuine))
        self.assertTrue(all(body["evidence_lane"] == production.EVIDENCE_LANE for body in genuine))

    def test_real_clock_window_mode_identity_and_complete_history_gates(self):
        with self.assertRaisesRegex(IntegrityError,"mode/input"):production.generate_pair(self.input,self.input_ref,self.binding,self.history_ref,self.history,player_id="1",mode="PROSPECTIVE_RESEARCH")
        self.input["mode"]="PROSPECTIVE_RESEARCH";self.actual=START-timedelta(minutes=74)
        with self.assertRaisesRegex(IntegrityError,"T90..T75"):self.pair("PROSPECTIVE_RESEARCH")
        self.actual=ISSUE
        with self.assertRaisesRegex(IntegrityError,"26,645"):production.generate_pair(self.input,self.input_ref,self.binding,self.history_ref,self.history[:-1],player_id="1",mode="PROSPECTIVE_RESEARCH")
        with self.assertRaisesRegex(IntegrityError,"outside selected"):production.generate_pair(self.input,self.input_ref,self.binding,self.history_ref,self.history,player_id="999",mode="PROSPECTIVE_RESEARCH")

    def test_actual_slow_generation_fails_before_either_original_is_returned(self):
        original=self.laws
        def slow(*args):
            result=original(*args);self.actual+=timedelta(seconds=301);return result
        with patch.object(production,"_fit_laws",side_effect=slow):
            with self.assertRaisesRegex(IntegrityError,"exceeds latency"):self.pair("PROSPECTIVE_RESEARCH")

    def test_typed_forecast_and_grade_reject_rehashed_invalid_mean_identity_and_scores(self):
        original=self.pair()[0]
        for change in ("mean","time","model","history"):
            body=deepcopy(original)
            if change == "mean":body["categories"][0]["mean"]="999"
            if change == "time":body["verified_at"]=stamp(self.actual+timedelta(seconds=1))
            if change == "model":body["producer_version"]="other-law"
            if change == "history":body["history_rows"]-=1
            body=common.seal({k:v for k,v in body.items() if k != "forecast_id"},"forecast_id")
            with self.assertRaises(IntegrityError):production.validate_body(body,self.input)

    def test_interrupted_peer_recovery_keeps_original_and_late_retry_cannot_fill_missing(self):
        self.input["mode"]="PROSPECTIVE_RESEARCH";store=MemoryStore();store.bodies[self.input_ref]=deepcopy(self.input)
        plan_ref=LedgerRef("input_captures","4"*64,"5"*64);store.bodies[plan_ref]={"schema_version":common.PLAN_SCHEMA,"plan_id":self.input["plan_id"]}
        auth_ref=LedgerRef("input_captures","6"*64,"7"*64);store.bodies[auth_ref]={"schema_version":common.AUTH_SCHEMA}
        runner=ModuleType("multisport_lab.sdv_production_runner");runner.require_execution_context=lambda *args,**kwargs:None
        prepared=SimpleNamespace(started_at=self.actual,for_target=lambda target:self.laws(self.history,target))
        with patch.dict(sys.modules,{runner.__name__:runner}),patch.object(production,"retained_history",return_value=(self.history_ref,self.history,{})),patch.object(production,"PreparedLaws",return_value=prepared):
            with self.assertRaisesRegex(IntegrityError,"original intent recovered"):production.issue_shard(store,self.input_ref,self.binding,["1"],plan_ref=plan_ref,authorization_ref=auth_ref,checkpoint=lambda refs:None)
            self.actual=START-timedelta(minutes=100)
            production.prepare_intent(store,self.input_ref,self.binding,["1"],plan_ref=plan_ref,authorization_ref=auth_ref,checkpoint=store.checkpoint)
            self.actual=ISSUE
            store.interrupt="K0"
            with self.assertRaises(InterruptedError):production.issue_shard(store,self.input_ref,self.binding,["1"],plan_ref=plan_ref,authorization_ref=auth_ref,checkpoint=store.checkpoint)
            original=next(body for _,body in store.records() if body["schema_version"] == production.FORECAST_SCHEMA)
            store.interrupt=None;self.actual=START-timedelta(minutes=74)
            with self.assertRaises(IntegrityError):production.issue_shard(store,self.input_ref,self.binding,["1"],plan_ref=plan_ref,authorization_ref=auth_ref,checkpoint=store.checkpoint)
            self.assertEqual(len(store.recover()["forecasts"]),1);self.assertEqual(store.recover()["forecasts"][0][1],original)
            self.actual=ISSUE
            recovered=production.issue_shard(store,self.input_ref,self.binding,["1"],plan_ref=plan_ref,authorization_ref=auth_ref,checkpoint=store.checkpoint)
            self.assertEqual(len(recovered["forecasts"]),2);self.assertIn(original,[body for _,body in recovered["forecasts"]])
            self.assertEqual(len(production.issue_shard(store,self.input_ref,self.binding,["1"],plan_ref=plan_ref,authorization_ref=auth_ref,checkpoint=store.checkpoint)["forecasts"]),2)

    def test_four_subject_batches_and_restart_acknowledge_originals_before_new_generation(self):
        store=MemoryStore();ids=[str(i) for i in range(1,10)]
        self.input["candidates"]=[{**self.input["candidates"][0],"player_id":pid,"player_label":"Invented "+pid} for pid in ids]
        self.input["shards"]=[ids];store.bodies[self.input_ref]=deepcopy(self.input)
        plan_ref=LedgerRef("input_captures","4"*64,"5"*64);store.bodies[plan_ref]={"schema_version":common.PLAN_SCHEMA,"plan_id":self.input["plan_id"]}
        prepared=SimpleNamespace(started_at=self.actual,for_target=lambda target:self.laws(self.history,target))
        with patch.object(production,"retained_history",return_value=(self.history_ref,self.history,{})),patch.object(production,"PreparedLaws",return_value=prepared):
            result=production.issue_shard(store,self.input_ref,self.binding,ids,plan_ref=plan_ref,checkpoint=store.checkpoint)
            self.assertEqual(len(result["forecasts"]),18);self.assertEqual([len(refs) for refs in store.checkpoints],[8,8,2])
            original_ref,original=result["forecasts"][0];original_bytes=canonical(original)
            del store.acknowledged[original_ref];store.checkpoints=[]
            with patch.object(production,"generate_pair",side_effect=AssertionError("Existing originals must not regenerate")):
                production.issue_shard(store,self.input_ref,self.binding,ids,plan_ref=plan_ref,checkpoint=store.checkpoint)
            self.assertEqual(store.checkpoints,[(original_ref,)]);self.assertEqual(canonical(store.read_body(original_ref)),original_bytes)

    def test_failed_partial_write_attempts_target_checkpoint_and_preserves_original_error(self):
        store=MemoryStore();store.bodies[self.input_ref]=deepcopy(self.input);store.interrupt="K0"
        plan_ref=LedgerRef("input_captures","4"*64,"5"*64);store.bodies[plan_ref]={"schema_version":common.PLAN_SCHEMA,"plan_id":self.input["plan_id"]}
        pending=[]
        def unavailable(refs):pending.extend(refs);raise IntegrityError("Synthetic remote unavailable")
        prepared=SimpleNamespace(started_at=self.actual,for_target=lambda target:self.laws(self.history,target))
        with patch.object(production,"retained_history",return_value=(self.history_ref,self.history,{})),patch.object(production,"PreparedLaws",return_value=prepared):
            with self.assertRaisesRegex(InterruptedError,"peer write interruption"):
                production.issue_shard(store,self.input_ref,self.binding,["1"],plan_ref=plan_ref,checkpoint=unavailable)
        self.assertEqual(len(pending),1);self.assertEqual(store.read_body(pending[0])["model_key"],"R0")
        original_bytes=canonical(store.read_body(pending[0]));store.interrupt=None;actions=[];generate=production.generate_pair
        def capture(refs):actions.append("checkpoint");return store.checkpoint(refs)
        def missing(*args,**kwargs):actions.append("generate missing peer");return generate(*args,**kwargs)
        with patch.object(production,"retained_history",return_value=(self.history_ref,self.history,{})),patch.object(production,"PreparedLaws",return_value=prepared),patch.object(production,"generate_pair",side_effect=missing):
            production.issue_shard(store,self.input_ref,self.binding,["1"],plan_ref=plan_ref,checkpoint=capture)
        self.assertEqual(actions,["checkpoint","generate missing peer","checkpoint"])
        self.assertEqual(canonical(store.read_body(pending[0])),original_bytes)

    def test_prepared_shared_laws_match_unchanged_fit_exactly_for_multiple_players(self):
        rows=[HistoricalAppearance(str(100+i),str(1+i%2),"25","7",TRAINED-timedelta(days=10-i),TRAINED-timedelta(days=9-i),20+i,
            2+i,1,2,3+i,4,1,0,1) for i in range(4)]
        target=ForecastTarget("900","1",START)
        with patch.object(baseline,"_now",return_value=self.actual):
            prepared=production.PreparedLaws(rows,target,mode="PROSPECTIVE_RESEARCH")
            for pid in ("1","2","999"):
                target=ForecastTarget("900",pid,START)
                from multisport_lab.pros004_producer import _fit_laws
                expected=_fit_laws(rows,target);actual=prepared.for_target(target)
                for key in ("R0","K0"):
                    self.assertEqual(actual[key].input_sha256,expected[key].input_sha256)
                    self.assertEqual(actual[key].support,expected[key].support)
                    self.assertEqual(production._categories(actual[key]),production._categories(expected[key]))


class ProductionOutcomeTests(ProductionFixture):
    def setUp(self):
        super().setUp();self.forecast=self.pair()[0];self.actual=START+timedelta(hours=4)

    def test_exact_archived_sources_replay_complete_outcome_and_statistical_grade(self):
        event,rows=self.final_rows();outcome,(schedule,box)=self.normalize(self.forecast,event,rows)
        self.assertEqual(outcome["primitives"]["FG2M"],2);self.assertEqual(outcome["status"],"APPEARED");self.assertEqual(len(outcome["categories"]),14)
        production.verify_outcome_sources(outcome,*[schedule[0],box[0],schedule[1],box[1]],source_originals={"schedule":schedule[2],"boxscore":box[2]},forecasts=(self.forecast,),input_body=self.input)
        grade=production.make_grade(self.forecast,outcome);production.validate_grade(grade,self.forecast,outcome)
        self.assertEqual(grade["status"],"SCORED");self.assertEqual(grade["financial_settlement"],"NOT_EVALUATED")
        forged=deepcopy(grade);forged["categories"][0]["crps"]="999";forged=common.seal({k:v for k,v in forged.items() if k != "grade_id"},"grade_id")
        with self.assertRaisesRegex(IntegrityError,"differs from original"):production.validate_grade(forged,self.forecast,outcome)
        forged=deepcopy(outcome);forged["primitives"]["REB"]+=1
        from multisport_lab.ledger import _outcome_categories
        forged["categories"]=_outcome_categories(forged["primitives"])
        forged=common.seal({k:v for k,v in forged.items() if k != "outcome_id"},"outcome_id")
        with self.assertRaisesRegex(IntegrityError,"archived source bytes"):
            production.verify_outcome_sources(forged,schedule[0],box[0],schedule[1],box[1],source_originals={"schedule":schedule[2],"boxscore":box[2]},forecasts=(self.forecast,),input_body=self.input)
        with self.assertRaisesRegex(IntegrityError,"hash/size"):
            production.verify_outcome_sources(outcome,schedule[0]+b" ",box[0],schedule[1],box[1],source_originals={"schedule":schedule[2],"boxscore":box[2]},forecasts=(self.forecast,),input_body=self.input)

    def test_retained_day_six_sources_can_be_corrected_on_day_eight_but_late_capture_cannot(self):
        event,rows=self.final_rows();original,_=self.normalize(self.forecast,event,rows)
        rows[0]["rebounds"]="5";rows[0]["defensive_rebounds"]="4"
        self.actual=START+timedelta(days=6)
        schedule_ref,schedule=self.source(csv_bytes([event]),"schedule")
        boxscore_ref,boxscore=self.source(csv_bytes(rows),"boxscore")
        retained={digest(schedule_ref):schedule,digest(boxscore_ref):boxscore}
        archive=SimpleNamespace(recover_source=lambda ref:retained[digest(ref)])
        self.actual=START+timedelta(days=8)
        replacement=production.normalize_outcome(self.forecast,self.input,archive=archive,schedule_ref=schedule_ref,
            boxscore_ref=boxscore_ref,previous=original)
        self.assertEqual(replacement["source_observed_at"],stamp(START+timedelta(days=6)))
        self.assertEqual(replacement["normalized_at"],stamp(self.actual));self.assertEqual(replacement["correction_revision"],2)
        production.verify_outcome_sources(replacement,schedule[0],boxscore[0],schedule[1],boxscore[1],
            source_originals={"schedule":schedule[2],"boxscore":boxscore[2]},forecasts=(self.forecast,),input_body=self.input)
        # Each role's exact retained raw retrieval must meet the deadline. A
        # timely schedule cannot lend its clock to a newly captured boxscore.
        for late_role in ("schedule","boxscore"):
            ref,source=self.source(csv_bytes([event]) if late_role == "schedule" else csv_bytes(rows),late_role)
            sources={digest(schedule_ref):schedule,digest(boxscore_ref):boxscore,digest(ref):source}
            changed=SimpleNamespace(recover_source=lambda value:sources[digest(value)])
            with self.subTest(role=late_role),self.assertRaisesRegex(IntegrityError,"retrieval exceeded its capture window"):
                production.normalize_outcome(self.forecast,self.input,archive=changed,schedule_ref=ref if late_role == "schedule" else schedule_ref,
                    boxscore_ref=ref if late_role == "boxscore" else boxscore_ref,previous=original)

    def test_dnp_missing_nonfinal_postponed_and_cancelled_remain_unscored(self):
        event,rows=self.final_rows()
        for state,expected in (("STATUS_IN_PROGRESS","NONFINAL"),("STATUS_POSTPONED","POSTPONED"),("STATUS_CANCELLED","CANCELLED")):
            changed={**event,"status_type_completed":"false","status_type_name":state,"status_type_state":"in"}
            body,_=self.normalize(self.forecast,changed,rows);self.assertEqual(body["status"],expected);self.assertIsNone(body["primitives"])
            self.assertEqual(production.make_grade(self.forecast,body)["categories"],[])
        body,_=self.normalize(self.forecast,event,[]);self.assertEqual(body["status"],"MISSING")
        rows[0]["did_not_play"]="true";rows[0]["minutes"]="";event["home_score"]="0"
        for row in rows:
            row["team_score"]="0" if row["team_id"] == "25" else "12";row["opponent_team_score"]="12" if row["team_id"] == "25" else "0"
        for key in production.SDV_FIELDS.values():rows[0][key]="0"
        body,_=self.normalize(self.forecast,event,rows);self.assertEqual(body["status"],"DNP");self.assertIsNone(body["minutes"])
        self.assertEqual(production.make_grade(self.forecast,body)["status"],"DNP_NOT_SCORED")

    def test_final_identity_count_and_original_byte_contradictions_reject(self):
        for mutation in ("team","start","season","duplicate","score","fg2","dnp"):
            event,rows=self.final_rows()
            if mutation == "team":event["away_id"]="9"
            if mutation == "start":event["game_date_time"]=stamp(START+timedelta(minutes=1))
            if mutation == "season":event["season_type"]="3"
            if mutation == "duplicate":rows.append(deepcopy(rows[0]))
            if mutation == "score":rows[0]["points"]="13"
            if mutation == "fg2":rows[0]["FG2M"]="3"
            if mutation == "dnp":rows[0]["did_not_play"]="true"
            with self.subTest(mutation=mutation),self.assertRaises((IntegrityError,ValueError)):self.normalize(self.forecast,event,rows)

    def test_two_version_corrections_append_traceable_originals_and_cannot_retune_forecasts(self):
        event,rows=self.final_rows();original,_=self.normalize(self.forecast,event,rows);original_bytes=canonical(original)
        grade=production.make_grade(self.forecast,original);self.actual+=timedelta(seconds=1)
        rows[0]["rebounds"]="5";rows[0]["defensive_rebounds"]="4"
        replacement,_=self.normalize(self.forecast,event,rows,previous=original)
        self.assertEqual(replacement["previous_outcome_id"],original["outcome_id"]);self.assertEqual(replacement["correction_revision"],2)
        corrected=production.make_grade(self.forecast,replacement,previous=grade);production.validate_grade(corrected,self.forecast,replacement,previous=grade)
        self.assertEqual(corrected["previous_grade_id"],grade["grade_id"]);self.assertEqual(canonical(original),original_bytes)
        with self.assertRaisesRegex(IntegrityError,"two versions"):self.normalize(self.forecast,event,rows,previous=replacement)
        changed=deepcopy(replacement);changed["player_id"]="9";changed=common.seal({k:v for k,v in changed.items() if k != "outcome_id"},"outcome_id")
        with self.assertRaisesRegex(IntegrityError,"subject/chain"):production.validate_outcome(changed,previous=original)


if __name__ == "__main__":unittest.main()

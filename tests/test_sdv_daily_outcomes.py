"""Synthetic final CSV replay only; no source collection or model evaluation."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab.integrity import IntegrityError, load_json, stamp
from multisport_lab import sdv_daily_outcomes as outcomes
from multisport_lab import sdv_daily_producer as producer
from multisport_lab import sdv_daily_store as storage
from test_sdv_daily_inputs import csv_bytes


class DailyOutcomesTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,24,tzinfo=timezone.utc)
        for module in (outcomes,producer,storage):
            p=patch.object(module,"_now",return_value=self.now);p.start();self.addCleanup(p.stop)
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=storage.DailyStore(self.folder.name)
        fixture=load_json(Path(__file__).parent/"fixtures/sdv-daily-synthetic.json")
        self.forecast=fixture["forecasts"][0]["body"]
        self.event={"game_id":self.forecast["event_id"],"home_id":"25","away_id":"7","season":"2027","season_type":"2",
            "game_date_time":self.forecast["event_starts_at"],"status_type_completed":"true","status_type_name":"STATUS_FINAL","status_type_state":"post"}
        self.row={"game_id":self.forecast["event_id"],"athlete_id":self.forecast["player_id"],"team_id":self.forecast["team_id"],"opponent_team_id":self.forecast["opponent_id"],
            "season":"2027","season_type":"2","game_date_time":self.forecast["event_starts_at"],"did_not_play":"false","minutes":"20.0",
            "points":"12","field_goals_made":"4","field_goals_attempted":"10","three_point_field_goals_made":"2","three_point_field_goals_attempted":"5",
            "free_throws_made":"2","free_throws_attempted":"2","rebounds":"4","offensive_rebounds":"1","defensive_rebounds":"3","assists":"3","turnovers":"1","blocks":"0","steals":"1"}

    def retain(self,rows,kind):
        return self.store.retain_outcome_evidence(csv_bytes(rows),{"source_kind":kind,"source_url":"https://example.test/synthetic.csv",
            "source_observed_at":stamp(self.now),"retrieval_started_at":stamp(self.now),"retrieved_at":stamp(self.now),"content_type":"text/csv","source_use_basis":"Synthetic test only; no actual source admission"})

    def normalize(self):
        event=self.retain([self.event],"SportsDataverse NBA schedule CSV")
        box=self.retain([self.row],"SportsDataverse NBA player boxscore CSV")
        return outcomes.normalize_outcome(self.store,self.forecast,schedule_ref=event,boxscore_ref=box)

    def test_exact_final_primitives_replay_and_statistical_grade(self):
        ref,body=self.normalize()
        self.assertEqual(body["status"],"APPEARED");self.assertEqual(body["primitives"]["FG2M"],2)
        self.assertEqual(len(body["categories"]),14)
        self.assertEqual(outcomes.verify_outcome_sources(self.store,body),body)
        self.assertEqual(self.store.ledger.read(ref)["data"]["daily"],body)
        grade=producer.make_grade(self.forecast,body,graded_at=stamp(self.now))
        self.assertEqual(grade["status"],"SCORED");self.assertEqual(grade["financial_settlement"],"NOT_EVALUATED")
        changed=deepcopy(body);changed["primitives"]["REB"]+=1
        from multisport_lab.ledger import _outcome_categories
        changed["categories"]=_outcome_categories(changed["primitives"])
        changed=producer.seal({k:v for k,v in changed.items() if k != "outcome_id"},"outcome_id")
        with self.assertRaisesRegex(IntegrityError,"original source bytes"):outcomes.verify_outcome_sources(self.store,changed)

    def test_explicit_dnp_is_not_zero_and_absence_stays_missing(self):
        self.row["did_not_play"]="true";self.row["minutes"]=""
        for key in list(self.row):
            if key in {"points",*outcomes.SDV_FIELDS.values()}:self.row[key]=""
        _,body=self.normalize()
        self.assertEqual(body["status"],"DNP");self.assertIsNone(body["primitives"])
        self.assertEqual(producer.make_grade(self.forecast,body,graded_at=stamp(self.now))["status"],"DNP_NOT_SCORED")
        self.row["athlete_id"]="999"
        _,missing=self.normalize();self.assertEqual(missing["status"],"MISSING")

    def test_nonfinal_and_changed_event_are_not_final_results(self):
        self.event.update(status_type_completed="false",status_type_name="STATUS_IN_PROGRESS",status_type_state="in")
        _,body=self.normalize();self.assertEqual(body["status"],"NONFINAL");self.assertEqual(body["categories"],[])
        self.event["away_id"]="9"
        with self.assertRaisesRegex(IntegrityError,"identity/version"):self.normalize()

    def test_correction_appends_new_evidence_and_preserves_original(self):
        first,body=self.normalize()
        original=self.store.ledger._path(first.kind,first.record_id).read_bytes()
        self.row.update(points="13",free_throws_made="3",free_throws_attempted="3")
        replacement,corrected=self.normalize()
        link=self.store.ledger.correct(first,replacement,reason="Synthetic final-stat correction")
        self.assertNotEqual(body["outcome_id"],corrected["outcome_id"])
        self.assertEqual(self.store.ledger._path(first.kind,first.record_id).read_bytes(),original)
        self.assertEqual(self.store.corrections()[0]["reference"],link.to_record())
        self.assertEqual(len([b for _,b in self.store.records() if b["schema_version"]==producer.OUTCOME_SCHEMA]),2)


if __name__ == "__main__":unittest.main()

"""Synthetic input assertions only; no real pregame capture or admission."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab.integrity import IntegrityError, digest
from multisport_lab.nba_data import NBAPlayerGame
from multisport_lab.nba_inputs import assess_snapshot, diagnose_archive, audit_future_history_timing

NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)


def snapshot(raw_hash):
    row = NBAPlayerGame(id_namespace="espn", event_id="past", player_id="p", team_id="1", opponent_id="2",
        season_ending_year=2026, season_type="2", event_start="2026-10-18T15:00:00Z",
        participation="APPEARED", minutes=20., minutes_precision="rounded_whole_minutes",
        points=12, fgm=4, fga=8, fg2m=2, fg3m=2, fg3a=4, ftm=2, fta=2,
        oreb=1, dreb=2, rebounds=3, assists=4, turnovers=1, blocks=0, steals=1,
        final_status="FINAL").to_record()
    def source(key, clock):
        return {"source_id": key, "source_url": "file:synthetic-only.json", "source_version": "synthetic-v1",
            "raw_sha256": raw_hash, "observed_at": clock, "source_updated_at": None,
            "access_basis": {"kind": "SYNTHETIC_TEST_FILE", "operation": "LOCAL_RESEARCH_IMPORT", "reference": "fictional fixture only"}}
    return {"schema_version": "nba-input-readiness-v1", "snapshot_id": "0"*64,
        "input_kind": "SYNTHETIC_FIXTURE", "producer_version": "synthetic-v1", "conditioning": "CONDITIONAL_ON_APPEARANCE",
        "event": {"id_namespace": "espn", "league": "NBA", "event_id": "future", "event_version": "v1",
            "event_starts_at": "2026-10-20T15:00:00.000000Z", "home_team_id": "1", "away_team_id": "2", "status": "PRE_GAME", "source_ref": "schedule"},
        "cutoff_at": "2026-10-20T13:30:00.000000Z", "history_freeze": "2026-10-20T00:00:00.000000Z",
        "coverage": {"basis": "DECLARED_SELECTED_PLAYERS", "requested_player_ids": ["p"], "complete_declared_selection": True,
                     "full_roster_claim": False, "participation_model_claim": False},
        "candidates": [{"player_id": "p", "team_id": "1", "opponent_id": "2", "event_id": "future", "event_version": "v1",
                        "event_starts_at": "2026-10-20T15:00:00.000000Z", "source_ref": "schedule"}],
        "sources": [source("schedule", "2026-10-20T11:30:00.000000Z"), source("history", "2026-10-19T20:00:00.000000Z")],
        "history": [{"source_ref": "history", "row": row}]}


class NBAInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nba-input-test-")
        self.file = Path(self.temp.name)/"synthetic.json"
        self.file.write_bytes(b'{"synthetic":true}')
        self.body = snapshot(hashlib.sha256(self.file.read_bytes()).hexdigest())
        self.paths = {"schedule": self.file, "history": self.file}

    def tearDown(self):
        self.temp.cleanup()

    def assess(self, body=None, paths=None, now=NOW):
        body = deepcopy(body or self.body)
        body["snapshot_id"] = digest({k:v for k,v in body.items() if k != "snapshot_id"})
        with patch("multisport_lab.nba_inputs._now", return_value=now):
            return assess_snapshot(body, self.paths if paths is None else paths)

    def blocked(self, body, code):
        report = self.assess(body)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["structural_blockers"][0]["code"], code)
        self.assertFalse(report["future_issuance_admitted"])
        return report

    def test_complete_assertions_pass_structure_and_never_admit_real_time(self):
        report = self.assess()
        self.assertEqual(report["status"], "STRUCTURAL_CHECKS_PASSED_NOT_ADMITTED")
        self.assertEqual(report["imported_at"], "2026-10-20T12:00:00.000000Z")
        self.assertEqual(report["inventory"]["selected_candidate_count"], 1)
        self.assertEqual(report["inventory"]["input_kind"], "SYNTHETIC_FIXTURE")
        self.assertFalse(report["future_issuance_admitted"])
        self.assertFalse(report["source_permission_verified"])
        self.assertFalse(report["source_clock_authenticity_verified"])
        self.assertEqual(report["qualification"], "UNAVAILABLE")

    def test_duplicate_players_sources_and_history_fail(self):
        for field, code in [("candidates", "DUPLICATE_CANDIDATE"), ("sources", "DUPLICATE_SOURCE"), ("history", "DUPLICATE_HISTORY")]:
            body = deepcopy(self.body)
            body[field].append(deepcopy(body[field][0]))
            with self.subTest(field=field): self.blocked(body, code)

    def test_exact_event_version_start_namespace_and_team_required(self):
        for field, value, code in [("event_id", "other", "CANDIDATE_EVENT_IDENTITY"), ("event_version", "v2", "CANDIDATE_EVENT_IDENTITY"),
                                    ("event_starts_at", "2026-10-20T15:01:00.000000Z", "CANDIDATE_EVENT_IDENTITY"),
                                    ("opponent_id", "3", "CANDIDATE_TEAM_IDENTITY")]:
            body=deepcopy(self.body);body["candidates"][0][field]=value
            with self.subTest(field=field):self.blocked(body, code)
        body=deepcopy(self.body);body["event"]["id_namespace"]="nba"
        self.blocked(body,"EVENT_IDENTITY")

    def test_cutoff_future_and_late_source_clocks_fail(self):
        body=deepcopy(self.body);body["cutoff_at"]="2026-10-20T13:31:00.000000Z"
        self.blocked(body,"CUTOFF")
        body=deepcopy(self.body);body["sources"][0]["observed_at"]="2026-10-20T12:00:00.000001Z"
        self.blocked(body,"FUTURE_SOURCE_CLOCK")
        body=deepcopy(self.body);body["sources"][0]["source_updated_at"]="2026-10-20T11:31:00.000000Z"
        self.blocked(body,"SOURCE_UPDATE_CLOCK")
        body=deepcopy(self.body);body["sources"][1]["observed_at"]="2026-10-20T01:00:00.000000Z"
        self.blocked(body,"HISTORY_AFTER_FREEZE")
        body=deepcopy(self.body);body["sources"][0]["observed_at"]="2026-10-20T14:00:00.000000Z"
        report=self.assess(body,now=datetime(2026,10,20,14,30,tzinfo=timezone.utc))
        self.assertEqual(report["structural_blockers"][0]["code"],"INPUT_AFTER_CUTOFF")

    def test_target_and_same_freeze_date_history_fail_without_reconstruction(self):
        for field,value in [("event_id","future"),("event_start","2026-10-20T00:00:00Z")]:
            body=deepcopy(self.body);body["history"][0]["row"][field]=value
            with self.subTest(field=field):self.blocked(body,"TARGET_OR_FUTURE_HISTORY")

    def test_incomplete_and_contradictory_history_counts_fail(self):
        body=deepcopy(self.body);body["history"][0]["row"]["fgm"]=None
        self.blocked(body,"INCOMPLETE_HISTORY")
        body=deepcopy(self.body);body["history"][0]["row"]["fgm"]=5
        report=self.blocked(body,"INVALID_INPUT")
        self.assertIn("FGM = FG2M + FG3M",report["structural_blockers"][0]["detail"])

    def test_local_source_hash_missing_file_and_permission_claims_fail(self):
        body=deepcopy(self.body);body["sources"][0]["raw_sha256"]="a"*64
        self.blocked(body,"SOURCE_HASH")
        self.assertEqual(self.assess(paths={})["structural_blockers"][0]["code"],"SOURCE_FILE_MISSING")
        body=deepcopy(self.body);body["sources"][0]["access_basis"]["kind"]="PUBLIC_URL_SO_AUTOMATION_ALLOWED"
        self.blocked(body,"ACCESS_BASIS")

    def test_selected_coverage_cannot_be_final_appearance_universe_or_all_roster(self):
        for field,value in [("basis","EVENTUAL_APPEARANCES"),("requested_player_ids",["p","missing"]),
                            ("full_roster_claim",True),("participation_model_claim",True)]:
            body=deepcopy(self.body);body["coverage"][field]=value
            with self.subTest(field=field):self.blocked(body,"UNIVERSE_COVERAGE")

    def test_stale_event_and_false_real_time_kind_never_pass(self):
        report=self.assess(now=datetime(2026,10,20,15,tzinfo=timezone.utc))
        self.assertEqual(report["structural_blockers"][0]["code"],"EVENT_ALREADY_STARTED")
        body=deepcopy(self.body);body["input_kind"]="REAL_TIME_CAPTURED"
        self.blocked(body,"UNSUPPORTED_INPUT_KIND")
        body=deepcopy(self.body);body["input_kind"]="SUPPLIED_PREGAME_ASSERTION"
        self.blocked(body,"SYNTHETIC_SOURCE_MISMATCH")

    def test_row_candidate_metadata_and_aggregate_source_budgets(self):
        for budget, value, code in [("MAX_HISTORY_ROWS", 0, "HISTORY_BUDGET"),
                ("MAX_CANDIDATES", 0, "CANDIDATE_BUDGET"),
                ("MAX_METADATA_BYTES", 1, "METADATA_BUDGET"),
                ("MAX_SOURCE_BYTES", len(self.file.read_bytes()), "SOURCE_BUDGET")]:
            with self.subTest(budget=budget), patch("multisport_lab.nba_inputs."+budget, value):
                self.blocked(self.body, code)

    def test_source_symlink_is_not_accepted_as_local_evidence(self):
        alias=Path(self.temp.name)/"alias.json";alias.symlink_to(self.file)
        report=self.assess(paths={"schedule":alias,"history":self.file})
        self.assertEqual(report["structural_blockers"][0]["code"],"INVALID_SOURCE_FILE")

    def test_archive_diagnostic_limits_prefix_and_does_not_relabel_update_clock(self):
        panel=Path(self.temp.name)/"archive.jsonl"
        row=self.body["history"][0]["row"]
        panel.write_text(json.dumps(row)+"\n"+json.dumps(row)+"\n")
        receipts=Path(self.temp.name)/"receipts.json"
        receipts.write_text(json.dumps({"receipts":[{"key":"sdv_player_box_2026",
            "observed_at":"2026-10-20T11:00:00Z", "source_updated_at":"2026-10-19T10:00:00Z", "sha256":"a"*64}]}))
        with patch("multisport_lab.nba_inputs.MAX_HISTORY_ROWS",1):
            report=diagnose_archive(panel,receipts)
        self.assertEqual(report["total_file_rows"],2)
        self.assertEqual(report["inspected_prefix_rows"],1)
        self.assertIsNone(report["archive_observations"][0]["source_version"])
        self.assertEqual(report["archive_observations"][0]["source_updated_at"],"2026-10-19T10:00:00Z")
        self.assertFalse(report["future_issuance_admitted"])
        self.assertEqual(report["status"],"ARCHIVE_ALONE_NOT_ADMITTED_AS_PROSPECTIVE_BUNDLE")
        self.assertEqual(report["future_event_history_timing_audit"]["status"],"NOT_EVALUATED")
        self.assertIsNone(report["future_event_history_timing_audit"]["event_id"])
        self.assertTrue(report["future_event_history_timing_audit"]["past_statistics_not_inherently_disqualified"])
        self.assertEqual(report["historical_asof_limitations"]["sources_fetched_after_inspected_historical_event_cutoffs"],
                         ["sdv_player_box_2026"])
        self.assertTrue(report["pilot_budget_scope"]["whole_file_exceeds_prior_row_limit"])


class FutureHistoryTimingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="nba-history-timing-")
        self.root=Path(self.temp.name)
        self.panel=self.root/"panel.jsonl";self.receipts=self.root/"receipts.json";self.discovery=self.root/"discovery.json"
        base=snapshot("a"*64)["history"][0]["row"]
        rows=[]
        for day in range(1,10):
            row=deepcopy(base);row["event_id"]=f"past{day}";row["event_start"]=f"2026-10-{day:02}T15:00:00+00:00"
            rows.append(row)
        self.panel.write_text("".join(json.dumps(row)+"\n" for row in rows))
        self.panel_sha=hashlib.sha256(self.panel.read_bytes()).hexdigest()
        self.sources={"receipts":[{"key":key,"status":200,"sha256":"b"*64,
            "observed_at":"2026-10-19T22:00:00Z","source_updated_at":"2026-10-19T21:00:00Z"}
            for key in ("sdv_player_box_2026","sdv_schedule_2026")]}
        self.events={"schema_version":"nba-pregame-discovery-audit-v1","event_count":1,
            "sources":[{"source_id":"espn_scoreboard","raw_file_sha256":"c"*64,
                "original_observed_at":"2026-10-19T23:00:00.000000Z","source_updated_at":None}],
            "event_metadata_as_captured":[{"provider":"ESPN","league":"NBA","provider_event_id":"future",
                "provider_competition_id":"future","event_and_competition_start_agree":True,
                "team_competitor_id_agreement":True,"time_valid_flag":True,
                "provider_home_team_id":"1","provider_away_team_id":"2",
                "status_name_as_captured":"STATUS_SCHEDULED","status_state_as_captured":"pre","completed_as_captured":False,
                "scheduled_start_as_captured":"2026-10-21T01:30:00.000000Z",
                "original_observed_at":"2026-10-19T23:00:00.000000Z",
                "derived_t90_for_recorded_start":"2026-10-21T00:00:00.000000Z"}]}

    def tearDown(self):self.temp.cleanup()

    def audit(self,now=NOW):
        self.receipts.write_text(json.dumps(self.sources));self.discovery.write_text(json.dumps(self.events))
        with patch("multisport_lab.nba_inputs._now",return_value=now), \
                patch("multisport_lab.baseline.forecast_reference",side_effect=AssertionError("no forecast allowed")), \
                patch("multisport_lab.research_pilot.forecast_reference",side_effect=AssertionError("no forecast allowed")):
            return audit_future_history_timing(self.panel,self.receipts,self.discovery,expected_panel_sha256=self.panel_sha)

    def test_prior_stats_can_pass_later_event_timing_without_future_admission(self):
        report=self.audit();event=report["events"][0]
        self.assertEqual(report["status"],"REPORTED_CLOCK_CONSISTENCY_PASS")
        self.assertEqual(event["daily_history_freeze"],"2026-10-21T00:00:00.000000Z")
        self.assertEqual(event["prior_row_start_and_reconstructed_completion_eligible_count"],9)
        self.assertEqual(event["window_state_at_audit"],"T90_NOT_YET_REACHED_AT_AUDIT")
        self.assertFalse(report["future_issuance_admitted"])
        self.assertFalse(report["normalization_lineage_verified"])
        self.assertFalse(report["current_event_status_verified"])

    def test_late_stat_observation_fails_only_reported_timing_component(self):
        self.sources["receipts"][0]["observed_at"]="2026-10-21T00:00:00.000001Z"
        report=self.audit(now=datetime(2026,10,21,0,10,tzinfo=timezone.utc));event=report["events"][0]
        self.assertEqual(report["status"],"REPORTED_CLOCK_CONSISTENCY_FAIL")
        self.assertEqual(event["prior_row_start_and_reconstructed_completion_eligible_count"],9)
        self.assertEqual(event["reported_batch_source_clock_compatible_prior_rows"],0)

    def test_event_clock_and_history_source_clock_are_separate_checks(self):
        late="2026-10-21T00:01:00.000000Z"
        self.events["sources"][0]["original_observed_at"]=late
        self.events["event_metadata_as_captured"][0]["original_observed_at"]=late
        report=self.audit(now=datetime(2026,10,21,0,10,tzinfo=timezone.utc));event=report["events"][0]
        self.assertEqual(event["old_stat_source_clock_consistency"],"PASS")
        self.assertEqual(event["event_metadata_reported_clock_checks"]["reported_clock_consistency"],"FAIL")
        self.assertEqual(event["reported_batch_source_clock_compatible_prior_rows"],9)

    def test_panel_change_duplicate_event_or_conflicting_event_clock_rejected(self):
        self.panel.write_text(self.panel.read_text()+"\n")
        with self.assertRaisesRegex(IntegrityError,"exact expected full normalized panel"):self.audit()
        self.panel.write_text(self.panel.read_text()[:-1])
        self.events["event_metadata_as_captured"].append(deepcopy(self.events["event_metadata_as_captured"][0]));self.events["event_count"]=2
        with self.assertRaisesRegex(IntegrityError,"duplicate as-observed event"):self.audit()
        self.events["event_metadata_as_captured"].pop();self.events["event_count"]=1
        self.events["event_metadata_as_captured"][0]["derived_t90_for_recorded_start"]="2026-10-21T00:00:01.000000Z"
        with self.assertRaisesRegex(IntegrityError,"event observation/T90"):self.audit()

    def test_audit_after_as_captured_start_never_calls_event_current(self):
        report=self.audit(now=datetime(2026,10,21,2,tzinfo=timezone.utc))
        self.assertEqual(report["events"][0]["window_state_at_audit"],"AS_CAPTURED_START_ALREADY_REACHED_AT_AUDIT")
        self.assertFalse(report["current_event_status_verified"])


if __name__ == "__main__":
    unittest.main()

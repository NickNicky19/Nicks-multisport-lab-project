from copy import deepcopy
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import unittest
from unittest.mock import patch

from multisport_lab.integrity import IntegrityError, digest, stamp
from multisport_lab import sdv_daily_inputs as daily


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def fixtures():
    start = datetime(2027, 1, 2, 1, 30, tzinfo=timezone.utc)
    normalized = start - timedelta(minutes=100)
    event = {"id": "900", "game_id": "900", "uid": "s:40~l:46~e:900~c:900",
             "season": "2027", "season_type": "2", "date": stamp(start),
             "start_date": stamp(start), "game_date_time": start.isoformat(),
             "home_id": "25", "home_display_name": "Synthetic Home",
             "away_id": "7", "away_display_name": "Synthetic Away",
             "status_type_name": "STATUS_SCHEDULED", "status_type_state": "pre",
             "status_type_completed": "false", "time_valid": "true"}
    roster = [{"season": "2027", "athlete_id": str(pid), "uid": "s:40~l:46~a:" + str(pid),
               "team_id": team, "team_display_name": name, "display_name": "Synthetic " + str(pid),
               "status_type": "active", "status_name": "Active", "status_id": "1"}
              for pid, team, name in [(1, "25", "Synthetic Home"), (2, "25", "Synthetic Home"),
                                      (3, "7", "Synthetic Away"), (4, "7", "Synthetic Away")]]
    expected = [{"player_id": row["athlete_id"], "player_label": row["display_name"],
                 "team_id": row["team_id"], "opponent_id": "7" if row["team_id"] == "25" else "25"}
                for row in roster]
    return start, normalized, [event], roster, expected


def metadata(raw, role, normalized):
    tag = "espn_nba_schedules" if role == "schedule" else "espn_nba_rosters"
    name = "nba_schedule_2027.csv" if role == "schedule" else "rosters_2027.csv"
    return {"role": role, "publisher": "SportsDataverse", "release_tag": tag,
            "asset_name": name, "asset_url": "https://github.com/sportsdataverse/"
             "sportsdataverse-data/releases/download/" + tag + "/" + name,
            "asset_id": 123 if role == "schedule" else 124, "asset_bytes": len(raw),
            "asset_sha256": hashlib.sha256(raw).hexdigest(),
            "publisher_updated_at": stamp(normalized - timedelta(hours=12)),
            "upstream_observed_at": None, "upstream_observation_status": "UNKNOWN",
            "retrieval_started_at": stamp(normalized - timedelta(minutes=2)),
            "retrieved_at": stamp(normalized - timedelta(minutes=1)),
            "metadata_sha256": hashlib.sha256(b"synthetic metadata").hexdigest(),
            "metadata_bytes": len(b"synthetic metadata")}


class DailyInputTests(unittest.TestCase):
    def setUp(self):
        self.start, self.normalized, self.schedule, self.roster, self.expected = fixtures()
        self.clock = patch.object(daily, "_now", return_value=self.normalized)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def build(self, *, schedule=None, roster=None, expected=None, source_mutator=None,
              mode="DEVELOPMENT_ONLY", normalized_at=True):
        s = csv_bytes(self.schedule if schedule is None else schedule)
        r = csv_bytes(self.roster if roster is None else roster)
        sm, rm = metadata(s, "schedule", self.normalized), metadata(r, "roster", self.normalized)
        if source_mutator:
            source_mutator(sm, rm)
        return daily.normalize_inputs(s, r, sm, rm, event_id="900",
            expected_candidates=self.expected if expected is None else expected,
            mode=mode, normalized_at=self.normalized if normalized_at else None)

    def test_two_actual_csv_contracts_keep_separate_clocks_and_unknown_information(self):
        body = self.build()
        self.assertEqual(body["schema_version"], daily.INPUT_SCHEMA)
        self.assertEqual(body["candidates"], self.expected)
        self.assertIsNone(body["event"]["provider_event_revision"])
        self.assertIn("UPSTREAM_OBSERVATION_CLOCK", body["missing_information"])
        self.assertIn("CONFIRMED_PARTICIPATION", body["missing_information"])
        self.assertEqual(body["policy"]["participation"], "CONDITIONAL_ON_APPEARANCE")
        self.assertEqual(body["input_id"], digest({k: v for k, v in body.items() if k != "input_id"}))
        status = daily.freshness(body, at=self.start - timedelta(minutes=90), require_retrieval_window=True)
        self.assertEqual(status["forecast_horizon_seconds"], 5400)
        self.assertIsNone(status["sources"]["schedule"]["upstream_age_seconds"])

    def test_fixed_policy_cannot_be_relaxed_and_resealed(self):
        policy = daily.make_policy()
        for field, value in [("schedule_max_age_seconds", 129601),
                             ("retrieval_lookback_seconds", True),
                             ("rationale", "Make this sample pass")]:
            candidate = deepcopy(policy)
            candidate[field] = value
            candidate["policy_id"] = digest({k: v for k, v in candidate.items() if k != "policy_id"})
            with self.subTest(field=field), self.assertRaises(IntegrityError):
                daily.validate_policy(candidate)

    def test_prospective_source_replay_is_read_only_and_requires_original_semantics(self):
        body = self.build(mode="PROSPECTIVE_RESEARCH", normalized_at=False)
        original = deepcopy(body)
        s, r = csv_bytes(self.schedule), csv_bytes(self.roster)
        sm, rm = metadata(s, "schedule", self.normalized), metadata(r, "roster", self.normalized)
        self.assertIs(daily.verify_input_sources(body, s, r, sm, rm), body)
        self.assertEqual(body, original)
        changed = deepcopy(body)
        changed["event"]["home_team_name"] = "Invented historical label"
        changed["event"]["event_snapshot_id"] = digest({k: v for k, v in changed["event"].items()
                                                       if k != "event_snapshot_id"})
        changed["input_id"] = digest({k: v for k, v in changed.items() if k != "input_id"})
        with self.assertRaisesRegex(IntegrityError, "semantics differ"):
            daily.verify_input_sources(changed, s, r, sm, rm)

    def test_retrieval_cannot_refresh_stale_publisher_content(self):
        def stale(sm, rm):
            sm["publisher_updated_at"] = stamp(self.normalized - timedelta(hours=36, seconds=1))
        with self.assertRaisesRegex(IntegrityError, "publisher asset is stale"):
            self.build(source_mutator=stale)

    def test_missing_future_and_conflicting_source_clocks_reject(self):
        cases = [lambda sm, rm: sm.pop("publisher_updated_at"),
                 lambda sm, rm: sm.update(publisher_updated_at=stamp(self.normalized + timedelta(seconds=1))),
                 lambda sm, rm: rm.update(retrieved_at=stamp(self.normalized + timedelta(seconds=1))),
                 lambda sm, rm: rm.update(upstream_observed_at=stamp(self.normalized)),
                 lambda sm, rm: rm.update(upstream_observation_status="SUPPLIED")]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(IntegrityError):
                self.build(source_mutator=case)

    def test_asset_role_exact_public_route_hash_size_and_season_are_bound(self):
        cases = [lambda sm, rm: sm.update(asset_url=sm["asset_url"] + "?another=1"),
                 lambda sm, rm: sm.update(asset_sha256="0" * 64),
                 lambda sm, rm: rm.update(asset_bytes=rm["asset_bytes"] + 1),
                 lambda sm, rm: rm.update(asset_id=True),
                 lambda sm, rm: rm.update(role="schedule"),
                 lambda sm, rm: sm.update(metadata_bytes=2 * 1024 * 1024 + 1),
                 lambda sm, rm: rm.update(asset_name="rosters_2026.csv")]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(IntegrityError):
                self.build(source_mutator=case)

    def test_duplicate_missing_and_conflicting_schedule_identities_reject(self):
        cases = [self.schedule * 2]
        for field, value in [("id", "901"), ("uid", "s:40~l:46~e:901~c:901"),
                             ("home_id", "7"), ("season", "2026"),
                             ("status_type_completed", "true"), ("time_valid", "false"),
                             ("date", stamp(self.start + timedelta(minutes=1)))]:
            rows = deepcopy(self.schedule)
            rows[0][field] = value
            cases.append(rows)
        for case in cases:
            with self.subTest(case=case), self.assertRaises(IntegrityError):
                self.build(schedule=case)

    def test_duplicate_conflicting_or_ineligible_player_rows_reject(self):
        cases = [self.roster + [self.roster[0]], self.roster[:3]]
        for field, value in [("season", "2026"), ("uid", "s:40~l:46~a:999"),
                             ("team_id", "7"), ("team_display_name", "Wrong team"),
                             ("display_name", "Different player"),
                             ("status_type", "inactive"), ("status_name", "Inactive"),
                             ("athlete_id", "１")]:
            rows = deepcopy(self.roster)
            rows[0][field] = value
            cases.append(rows)
        for case in cases:
            with self.subTest(case=case), self.assertRaises(IntegrityError):
                self.build(roster=case)

    def test_current_active_selection_rule_cannot_silently_replace_fixed_cohort(self):
        extra = deepcopy(self.roster[0])
        extra.update(athlete_id="5", uid="s:40~l:46~a:5", display_name="Synthetic 5")
        changed = deepcopy(self.expected)
        changed[1].update(player_id="5", player_label="Synthetic 5")
        with self.assertRaisesRegex(IntegrityError, "cohort changed"):
            self.build(roster=self.roster + [extra], expected=changed)

    def test_missing_csv_headers_and_oversized_bytes_do_not_get_truncated(self):
        s, r = csv_bytes(self.schedule), csv_bytes(self.roster)
        sm, rm = metadata(s, "schedule", self.normalized), metadata(r, "roster", self.normalized)
        with self.assertRaises(IntegrityError):
            daily.normalize_inputs(b"id\n900\n", r, sm, rm, event_id="900",
                expected_candidates=self.expected, normalized_at=self.normalized)
        with self.assertRaises(IntegrityError):
            daily.normalize_inputs(b"x" * (2 * 1024 * 1024 + 1), r, sm, rm,
                event_id="900", expected_candidates=self.expected, normalized_at=self.normalized)

    def test_retained_input_does_not_expire_during_structural_recovery(self):
        body = self.build()
        with patch.object(daily, "_now", return_value=self.start + timedelta(days=2)):
            self.assertEqual(daily.validate_input(body), body)
        with self.assertRaises(IntegrityError):
            daily.freshness(body, at=self.start + timedelta(seconds=1))

    def test_issuance_window_freshness_and_post_start_are_distinct(self):
        body = self.build()
        cutoff = self.start - timedelta(minutes=90)
        daily.freshness(body, at=cutoff + timedelta(seconds=900), require_retrieval_window=True)
        for actual in [cutoff - timedelta(seconds=1), cutoff + timedelta(seconds=901), self.start]:
            with self.subTest(at=actual), self.assertRaises(IntegrityError):
                daily.freshness(body, at=actual, require_retrieval_window=True)
        old = deepcopy(body)
        old["sources"][0]["retrieval_started_at"] = stamp(cutoff - timedelta(seconds=3601))
        old["input_id"] = digest({k: v for k, v in old.items() if k != "input_id"})
        with self.assertRaisesRegex(IntegrityError, "retrieval missed"):
            daily.freshness(old, at=cutoff, require_retrieval_window=True)

    def test_prospective_normalization_uses_actual_completion_not_supplied_time(self):
        with self.assertRaisesRegex(IntegrityError, "supplied completion clock"):
            self.build(mode="PROSPECTIVE_RESEARCH")
        body = self.build(mode="PROSPECTIVE_RESEARCH", normalized_at=False)
        self.assertEqual(body["normalized_at"], stamp(self.normalized))
        self.assertEqual(body["mode"], "PROSPECTIVE_RESEARCH")

    def test_checksum_consistent_invented_provider_revision_and_hidden_gaps_reject(self):
        body = self.build()
        revision = deepcopy(body)
        revision["event"]["provider_event_revision"] = "old-espn-version"
        revision["event"]["event_snapshot_id"] = digest({k: v for k, v in revision["event"].items() if k != "event_snapshot_id"})
        hidden = deepcopy(body)
        hidden["missing_information"].remove("CONFIRMED_PARTICIPATION")
        for changed in [revision, hidden]:
            changed["input_id"] = digest({k: v for k, v in changed.items() if k != "input_id"})
            with self.assertRaises(IntegrityError):
                daily.validate_input(changed)


if __name__ == "__main__":
    unittest.main()

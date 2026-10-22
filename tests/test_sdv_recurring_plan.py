"""Invented planning/revalidation fixtures, never a collector or issued forecast."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
import unittest
from unittest.mock import patch

from multisport_lab import sdv_recurring_plan as plan
from multisport_lab.integrity import IntegrityError, canonical, stamp, utc
from test_sdv_daily_inputs import fixtures, csv_bytes


class RecurringPlanTests(unittest.TestCase):
    def setUp(self):
        self.now = utc("2026-10-22T10:00:00.000000Z")
        for module in (plan, plan.inputs):
            clock = patch.object(module, "_now", side_effect=lambda: self.now)
            clock.start(); self.addCleanup(clock.stop)
        self.reservation = plan.make_reservation()
        self.now = utc("2026-10-23T13:17:00.000000Z")
        _, _, schedule, roster, _ = fixtures()
        self.schedule = []
        self.roster = []
        for index, starts in enumerate(("2026-10-24T00:00:00.000000Z", "2026-10-24T01:00:00.000000Z", "2026-10-24T02:00:00.000000Z")):
            event = deepcopy(schedule[0]); eid = str(900 + index)
            event.update(id=eid, game_id=eid, uid="s:40~l:46~e:" + eid + "~c:" + eid,
                date=starts, start_date=starts, game_date_time=starts,
                home_id=str(25 + index * 2), away_id=str(7 + index * 2),
                home_display_name="Synthetic Home " + str(index), away_display_name="Synthetic Away " + str(index))
            self.schedule.append(event)
            for source in roster:
                player = deepcopy(source); pid = str(int(source["athlete_id"]) + index * 10)
                home = source["team_id"] == "25"
                player.update(athlete_id=pid, uid="s:40~l:46~a:" + pid,
                    team_id=event["home_id"] if home else event["away_id"],
                    team_display_name=event["home_display_name"] if home else event["away_display_name"],
                    display_name="Synthetic Player " + pid)
                self.roster.append(player)

    def assets(self, *, publisher_age=timedelta(hours=12)):
        raws = [csv_bytes(self.schedule), csv_bytes(self.roster)]
        metadata, originals = [], {}
        for role, raw in zip(("schedule", "roster"), raws):
            tag = "espn_nba_schedules" if role == "schedule" else "espn_nba_rosters"
            name = "nba_schedule_2027.csv" if role == "schedule" else "rosters_2027.csv"
            url = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/" + tag + "/" + name
            original = canonical({"tag_name": tag, "assets": [{"id": 123 if role == "schedule" else 124,
                "name": name, "size": len(raw), "browser_download_url": url,
                "digest": "sha256:" + hashlib.sha256(raw).hexdigest(), "updated_at": stamp(self.now - publisher_age)}]})
            source = {"role": role, "publisher": "SportsDataverse", "release_tag": tag, "asset_name": name, "asset_url": url}
            metadata.append(plan.source_metadata(raw, original, source,
                retrieval_started_at=stamp(self.now - timedelta(minutes=2)), retrieved_at=stamp(self.now - timedelta(minutes=1))))
            originals[role] = original
        return *raws, *metadata, originals

    def build(self, assets=None):
        sr, rr, sm, rm, originals = assets or self.assets()
        return plan.plan_day(sr, rr, sm, rm, source_originals=originals, reservation=self.reservation, game_date="2026-10-24")

    def fresh(self, body, assets=None, event_id="900"):
        sr, rr, sm, rm, originals = assets or self.assets()
        return plan.revalidate_event(body, event_id, sr, rr, sm, rm, source_originals=originals)

    def test_fixed_seven_days_first_two_events_and_eight_subjects_have_no_issuance_authority(self):
        assets = self.assets(); body = self.build(assets)
        self.assertEqual(self.reservation["game_dates"], ["2026-10-%02d" % day for day in range(24, 31)])
        self.assertEqual([event["event"]["event_id"] for event in body["selected_events"]], ["900", "901"])
        self.assertEqual(body["subject_count"], 8); self.assertEqual(body["unique_player_count"], 8)
        self.assertEqual(len(body["inventory"]), 3)
        self.assertEqual(body["inventory"][2]["exclusion_reasons"], ["DAILY_EVENT_LIMIT"])
        self.assertEqual(body["issuance_authority"], "NONE_PLANNING_ONLY")
        for event in body["selected_events"]:
            self.assertEqual(event["source_interpretation"]["mode"], "DEVELOPMENT_ONLY")
            self.assertEqual(event["source_interpretation"]["policy"]["participation"], "CONDITIONAL_ON_APPEARANCE")
            self.assertIn("UPSTREAM_OBSERVATION_CLOCK", event["source_interpretation"]["missing_information"])
            self.assertIn("CONFIRMED_PARTICIPATION", event["source_interpretation"]["missing_information"])
            self.assertEqual(event["cutoff_at"], stamp(utc(event["event"]["event_starts_at"]) - timedelta(minutes=90)))
        self.assertIs(plan.verify_plan_sources(body, *assets[:4], source_originals=assets[4]), body)

    def test_source_order_cannot_change_chronological_selection(self):
        self.schedule.reverse(); self.roster.reverse()
        body = self.build()
        self.assertEqual([event["event"]["event_id"] for event in body["selected_events"]], ["900", "901"])
        self.assertEqual([p["player_id"] for p in body["selected_events"][0]["candidates"]], ["1", "2", "3", "4"])

    def test_inventory_keeps_excluded_events_and_selects_consecutive_eligible_ones(self):
        self.schedule[0].update(status_type_name="STATUS_POSTPONED")
        body = self.build()
        self.assertEqual(body["inventory"][0]["exclusion_reasons"], ["NOT_SCHEDULED"])
        self.assertEqual([event["event"]["event_id"] for event in body["selected_events"]], ["901", "902"])
        changed = deepcopy(body); changed["inventory"][0]["eligibility"] = "ELIGIBLE"
        changed = plan._seal({k: v for k, v in changed.items() if k != "plan_id"}, "plan_id")
        with self.assertRaises(IntegrityError): plan.validate_plan(changed)

    def test_empty_game_date_is_explicit_and_does_not_invent_events(self):
        for row in self.schedule:
            for key in ("date", "start_date", "game_date_time"): row[key] = row[key].replace("2026-10-24", "2026-10-25")
        body = self.build()
        self.assertEqual(body["status"], "NO_ELIGIBLE_EVENTS")
        self.assertEqual(body["inventory"], []); self.assertEqual(body["selected_events"], [])
        self.assertEqual(body["outside_game_date_rows"], 3)

    def test_zero_selected_events_still_bind_publisher_asset_year_to_csv_season(self):
        for empty_date in (True, False):
            if empty_date:
                for row in self.schedule:
                    for field in ("date", "start_date", "game_date_time"):
                        row[field] = row[field].replace("2026-10-24", "2026-10-25")
            else:
                for row in self.schedule:
                    for field in ("date", "start_date", "game_date_time"):
                        row[field] = row[field].replace("2026-10-25", "2026-10-24")
                    row["status_type_name"] = "STATUS_POSTPONED"
            assets = list(self.assets())
            # The bytes, hashes and exact original publisher JSON agree with
            # each other. Only the advertised file year contradicts CSV season.
            for index, role in enumerate(("schedule", "roster")):
                metadata = deepcopy(assets[index + 2])
                metadata["asset_name"] = metadata["asset_name"].replace("2027", "2030")
                metadata["asset_url"] = metadata["asset_url"].replace("2027", "2030")
                original = json.loads(assets[4][role])
                original["assets"][0].update(name=metadata["asset_name"], browser_download_url=metadata["asset_url"])
                raw_original = canonical(original)
                assets[4][role] = raw_original
                assets[index + 2] = plan.source_metadata(assets[index], raw_original, metadata,
                    retrieval_started_at=metadata["retrieval_started_at"], retrieved_at=metadata["retrieved_at"])
            with self.subTest(empty_date=empty_date), self.assertRaisesRegex(IntegrityError, "asset year.*CSV table season"):
                self.build(assets)

    def test_missing_cohort_is_recorded_without_substituting_inactive_player(self):
        self.roster[0].update(status_type="inactive", status_name="Inactive", status_id="2")
        body = self.build()
        self.assertIn("INSUFFICIENT_ACTIVE_COHORT", body["inventory"][0]["exclusion_reasons"])
        self.assertEqual([event["event"]["event_id"] for event in body["selected_events"]], ["901", "902"])

    def test_planning_is_refused_early_late_or_outside_reservation(self):
        for instant in ("2026-10-23T13:16:59.999999Z", "2026-10-23T13:47:00.000001Z"):
            self.now = utc(instant)
            with self.subTest(instant=instant), self.assertRaisesRegex(IntegrityError, "window"): self.build()
        self.now = utc("2026-10-23T13:17:00.000000Z")
        raw = self.assets()
        with self.assertRaisesRegex(IntegrityError, "seven-day"):
            plan.plan_day(*raw[:4], source_originals=raw[4], reservation=self.reservation, game_date="2026-10-31")

    def test_stale_missing_future_clocks_and_changed_originals_reject(self):
        original = self.assets()
        changes = [lambda sm: sm.pop("publisher_updated_at"),
            lambda sm: sm.update(publisher_updated_at=stamp(self.now - timedelta(hours=36, seconds=1))),
            lambda sm: sm.update(retrieved_at=stamp(self.now + timedelta(seconds=1))),
            lambda sm: sm.update(metadata_sha256="0" * 64)]
        for change in changes:
            assets = deepcopy(original); change(assets[2])
            with self.subTest(change=change), self.assertRaises(IntegrityError): self.build(assets)
        assets = deepcopy(original); assets[4]["schedule"] = b"{}"
        with self.assertRaises(IntegrityError): self.build(assets)

    def test_authenticated_publisher_age_has_an_exact_36_hour_limit(self):
        self.assertEqual(self.build(self.assets(publisher_age=timedelta(hours=36)))["status"], "PLANNED")
        with self.assertRaisesRegex(IntegrityError, "stale"):
            self.build(self.assets(publisher_age=timedelta(hours=36, microseconds=1)))

    def test_replay_rejects_checksum_consistent_truncated_inventory(self):
        assets = self.assets(); body = self.build(assets)
        body["inventory"].pop(); body["source_schedule_rows"] -= 1
        body = plan._seal({k: v for k, v in body.items() if k != "plan_id"}, "plan_id")
        # Structural counts cannot authenticate a claimed complete inventory.
        # Replay must recover it from all original bytes, including capped events.
        with self.assertRaisesRegex(IntegrityError, "source replay"):
            plan.verify_plan_sources(body, *assets[:4], source_originals=assets[4])

    def test_duplicates_missing_event_fields_and_conflicting_start_are_rejected(self):
        original_schedule = deepcopy(self.schedule); original_roster = deepcopy(self.roster)
        for mutate in (lambda: self.schedule.append(deepcopy(self.schedule[0])),
                lambda: self.roster.append(deepcopy(self.roster[0])),
                lambda: self.schedule[0].update(game_date_time=""),
                lambda: self.schedule[0].update(start_date="2026-10-24T00:01:00.000000Z"),
                lambda: self.roster[0].update(uid="s:40~l:46~a:999")):
            self.schedule = deepcopy(original_schedule); self.roster = deepcopy(original_roster); mutate()
            with self.subTest(mutate=mutate), self.assertRaises(IntegrityError): self.build()

    def test_revalidation_binds_fresh_inputs_separately_and_recovers_original_clocks(self):
        body = self.build(); original = deepcopy(body)
        self.now = utc(body["selected_events"][0]["cutoff_at"]) - timedelta(minutes=20)
        assets = self.assets(); fresh = self.fresh(body, assets)
        self.assertEqual(body, original)
        self.assertEqual(fresh["protocol_id"], "NBA-SDV-DAILY-002")
        self.assertEqual(fresh["status"], "FRESH_INPUT_CANDIDATE_NOT_ISSUED")
        self.assertNotEqual(fresh["source_interpretation"]["input_id"], body["selected_events"][0]["source_interpretation"]["input_id"])
        self.assertIs(plan.verify_event_input_sources(fresh, body, *assets[:4], source_originals=assets[4]), fresh)
        self.now += timedelta(days=1)
        self.assertIs(plan.verify_event_input_sources(fresh, body, *assets[:4], source_originals=assets[4]), fresh)

    def test_preparation_inputs_late_revalidation_and_replacement_events_reject(self):
        assets = self.assets(); body = self.build(assets)
        self.now = utc(body["selected_events"][0]["cutoff_at"]) - timedelta(minutes=20)
        with self.assertRaisesRegex(IntegrityError, "Preparation"): self.fresh(body, assets)
        with self.assertRaisesRegex(IntegrityError, "no replacements"): self.fresh(body, event_id="902")
        for late in (utc(body["selected_events"][0]["cutoff_at"]) + timedelta(microseconds=1),
                     utc(body["selected_events"][0]["event"]["event_starts_at"])):
            self.now = late
            with self.subTest(late=late), self.assertRaisesRegex(IntegrityError, "retrieval window"): self.fresh(body)

    def test_changed_event_version_or_cohort_rejects_without_replacement(self):
        body = self.build(); self.now = utc(body["selected_events"][0]["cutoff_at"]) - timedelta(minutes=20)
        for key in ("date", "start_date", "game_date_time"): self.schedule[0][key] = "2026-10-24T00:01:00.000000Z"
        with self.assertRaisesRegex(IntegrityError, "identity/version changed"): self.fresh(body)
        for key in ("date", "start_date", "game_date_time"): self.schedule[0][key] = "2026-10-24T00:00:00.000000Z"
        self.roster[0].update(status_type="inactive", status_name="Inactive", status_id="2")
        with self.assertRaises(IntegrityError): self.fresh(body)

    def test_planning_rejects_source_or_normalizer_completion_after_window_close(self):
        closes = plan.planning_window("2026-10-24")[1]
        for component in ("source", "normalizer"):
            self.now = closes - timedelta(seconds=1)
            assets = self.assets()
            target = plan if component == "source" else plan.inputs
            name = "_sources" if component == "source" else "normalize_inputs"
            original = getattr(target, name)
            def delayed(*args, **kwargs):
                result = original(*args, **kwargs)
                self.now += timedelta(seconds=2)
                return result
            with self.subTest(component=component), patch.object(target, name, side_effect=delayed), \
                    self.assertRaisesRegex(IntegrityError, "completion missed"):
                self.build(assets)

    def test_fresh_input_rejects_source_or_normalizer_completion_after_t90(self):
        body = self.build(); cutoff = utc(body["selected_events"][0]["cutoff_at"])
        for component in ("source", "normalizer"):
            self.now = cutoff - timedelta(seconds=1)
            assets = self.assets()
            target = plan if component == "source" else plan.inputs
            name = "_sources" if component == "source" else "normalize_inputs"
            original = getattr(target, name)
            def delayed(*args, **kwargs):
                result = original(*args, **kwargs)
                self.now += timedelta(seconds=2)
                return result
            with self.subTest(component=component), patch.object(target, name, side_effect=delayed), \
                    self.assertRaisesRegex(IntegrityError, "completion missed"):
                self.fresh(body, assets)

    def test_live_completion_clocks_follow_validation_and_readonly_replay_keeps_them(self):
        started = self.now; assets = self.assets(); original = plan.inputs.normalize_inputs
        def delayed(*args, **kwargs):
            result = original(*args, **kwargs)
            self.now += timedelta(seconds=2)
            return result
        with patch.object(plan.inputs, "normalize_inputs", side_effect=delayed):
            body = self.build(assets)
        self.assertEqual(body["planning_started_at"], stamp(started))
        self.assertEqual(body["planned_at"], stamp(started + timedelta(seconds=4)))
        self.assertEqual(body["sources"], [assets[2], assets[3]])
        for event in body["selected_events"]:
            self.assertEqual(event["source_interpretation"]["normalized_at"], body["planned_at"])
        self.assertIs(plan.verify_plan_sources(body, *assets[:4], source_originals=assets[4]), body)
        self.now = utc(body["selected_events"][0]["cutoff_at"]) - timedelta(minutes=20)
        fresh_assets = self.assets(); started = self.now
        with patch.object(plan.inputs, "normalize_inputs", side_effect=delayed):
            fresh = self.fresh(body, fresh_assets)
        self.assertEqual(fresh["validation_started_at"], stamp(started))
        self.assertEqual(fresh["validated_at"], stamp(started + timedelta(seconds=2)))
        self.assertEqual(fresh["source_interpretation"]["normalized_at"], fresh["validated_at"])
        self.assertEqual(fresh["source_interpretation"]["sources"], [fresh_assets[2], fresh_assets[3]])
        self.now += timedelta(days=1)
        self.assertIs(plan.verify_plan_sources(body, *assets[:4], source_originals=assets[4]), body)
        self.assertIs(plan.verify_event_input_sources(fresh, body, *fresh_assets[:4], source_originals=fresh_assets[4]), fresh)

    def test_fixed_reservation_cannot_shift_or_be_registered_after_planning(self):
        changed = deepcopy(self.reservation); changed["max_events_per_day"] = 3
        changed = plan._seal({k: v for k, v in changed.items() if k != "reservation_id"}, "reservation_id")
        with self.assertRaises(IntegrityError): plan.validate_reservation(changed)
        with self.assertRaises(IntegrityError): plan.make_reservation(first_game_date="2026-10-25")
        self.now = utc("2026-10-23T13:17:00.000000Z")
        with self.assertRaises(IntegrityError): plan.make_reservation()


if __name__ == "__main__":
    unittest.main()

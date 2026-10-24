"""Invented held-worker clocks with real local archives and bare-Git recovery.

No HTTP, hosted authorization, real-history fit, activation or genuine issuance.
The existing coordinator fixture retains exact fictional source originals while
its mathematical laws are explicit, small test doubles.
"""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from multisport_lab import sdv_production_common as common
from multisport_lab import sdv_production_coordinator as engine
from multisport_lab import sdv_production_runner as runner
from multisport_lab.integrity import IntegrityError, stamp, utc
import test_sdv_production_coordinator as native_fixture


class HeldProductionTests(unittest.TestCase):
    def setUp(self):
        self.native = native_fixture.ProductionCoordinatorTests(
            "test_complete_native_local_phases_recover_exact_forecasts_and_separate_grades")
        self.addCleanup(self.native.doCleanups)
        self.native.setUp()
        self.fixture = self.native.fixture
        self.policy = common.make_policy("v2")
        self.start = utc("2026-10-25T00:00:00.000000Z")
        self.cutoff = self.start - timedelta(minutes=90)
        for row in self.fixture.schedule:
            for field in ("date", "start_date", "game_date_time"):
                row[field] = stamp(self.start)
        self.native.case.start = self.start
        self.native.case.cutoff = self.cutoff
        self.fixture.now = self.start - timedelta(hours=6)
        self.elapsed = 0.0
        self.sleeps = []
        self.current = self.coordinator()
        self.native.current = self.current

    def coordinator(self, registry=None):
        self.native.count += 1
        current = engine.Coordinator(
            deepcopy(registry) if registry is not None else runner.empty_registry(),
            self.native.writer, self.native.archive, None,
            self.native.folder / ("held-worker-" + str(self.native.count)),
            mode="DEVELOPMENT_ONLY", source_root=self.native.case.source,
            binding=self.fixture.binding, collector=self.native.collect,
            remote_factory=self.native.remote_factory, policy=self.policy)
        current._pack = self.native.recover_pack
        return current

    def sleep(self, seconds):
        self.assertGreater(seconds, 0)
        self.assertLessEqual(seconds, 30)
        self.sleeps.append(seconds)
        self.elapsed += seconds
        self.fixture.now += timedelta(seconds=seconds)

    def monotonic(self):
        return self.elapsed

    def planned_holds(self):
        from multisport_lab import sdv_production_held as held
        tasks = self.current.prepare_tasks()
        self.assertEqual(tasks, [])
        self.assertEqual(len(self.current.registry["days"]), 1)
        self.assertEqual(self.current.registry["days"][0]["game_date"], "2026-10-25")
        self.assertEqual(len(self.native.calls), 1)
        descriptors, exclusions = held.prepare_holds(self.current, tasks)
        self.assertEqual(exclusions, [])
        self.assertEqual(len(descriptors), 1)
        return descriptors[0]

    def test_hold_rejects_resealed_cohort_and_producer_changes(self):
        from multisport_lab import sdv_production_held as held
        descriptor = self.planned_holds()
        body = self.native.archive.get_json(descriptor["task_ref"])
        plan = self.native.archive.get_json(body["plan_ref"])
        self.assertIs(held.validate_hold(body, plan), body)
        for field, value in (("player_ids", ["1000"]),
                             ("producer_binding_id", "f" * 64),
                             ("cohort_sha256", "f" * 64)):
            with self.subTest(field=field):
                forged = common.seal({key: deepcopy(item) for key, item in body.items()
                                      if key != "hold_id"} | {field: value}, "hold_id")
                with self.assertRaises(IntegrityError):
                    held.validate_hold(forged, plan)

    def test_resealed_shard_outside_original_plan_rejects_as_integrity_error(self):
        from multisport_lab import sdv_production_held as held
        descriptor = self.planned_holds()
        body = self.native.archive.get_json(descriptor["task_ref"])
        plan = self.native.archive.get_json(body["plan_ref"])
        forged = common.seal({key: deepcopy(item) for key, item in body.items()
                              if key != "hold_id"} | {
            "shard_index": 1, "branch": common.shard_branch(body["cycle_id"], 1)}, "hold_id")
        with self.assertRaises(IntegrityError):
            held.validate_hold(forged, plan)

    def test_held_inventory_recovery_reuses_original_without_rebinding(self):
        from multisport_lab import sdv_production_held as held
        original = self.planned_holds()
        retained = deepcopy(self.current.registry)
        self.fixture.now += timedelta(minutes=10)
        cold = self.coordinator(retained)
        descriptors, exclusions = held.prepare_holds(cold, [])
        self.assertEqual(exclusions, [])
        self.assertEqual(descriptors, [original])
        self.assertEqual(len(cold.registry["days"][0]["held_tasks"]), 1)
        self.assertEqual(len(self.native.calls), 1)

    def test_waiting_worker_recovers_exact_input_prepares_and_issues_both_laws(self):
        from multisport_lab import sdv_production_held as held
        descriptor = self.planned_holds()
        capturer = self.current
        worker = self.coordinator(capturer.registry)
        captured = False
        reads = []
        history_after_capture = []

        def sleep(seconds):
            nonlocal captured
            self.sleep(seconds)
            if not captured and self.fixture.now >= self.start - timedelta(minutes=140):
                self.native.current = capturer
                capturer._new_inputs()
                captured = True
                history_after_capture.append(len(self.native.writer.history))

        def read_registry():
            reads.append(self.fixture.now)
            self.assertGreaterEqual(self.fixture.now, self.start - timedelta(minutes=135))
            return deepcopy(capturer.registry)

        with patch.object(worker, "collector", side_effect=AssertionError("worker captured a source")):
            report = held.run_worker(worker, descriptor, read_registry=read_registry,
                                     sleep=sleep, monotonic=self.monotonic)
        self.assertEqual(report["status"], "ISSUED_PENDING_OUTCOMES", report)
        self.assertEqual([row["status"] for row in report["phases"]],
                         ["PREPARED", "ISSUED_PENDING_OUTCOMES"])
        self.assertEqual(len(reads), 1)
        self.assertEqual(len(self.native.calls), 2)
        self.assertEqual(len(self.native.writer.history), history_after_capture[0])
        task = engine.validate_task(self.native.archive.get_json(report["task_ref"]))
        recovered = worker._store(task)[0].recover()
        self.assertEqual(len(recovered["forecasts"]), 4)
        self.assertEqual({body["model_key"] for _, body in recovered["forecasts"]}, {"R0", "K0"})
        self.assertTrue(all(len(body["categories"]) == 14 for _, body in recovered["forecasts"]))
        self.assertTrue(all(body["issued_at"] is None for _, body in recovered["forecasts"]))
        self.assertEqual(recovered["genuine_issued"], 0)
        self.assertEqual(recovered["outcomes"], [])
        self.assertEqual(recovered["grades"], [])

    def test_missing_input_stops_at_t90_without_worker_capture_or_generation(self):
        from multisport_lab import sdv_production_held as held
        descriptor = self.planned_holds()
        worker = self.coordinator(self.current.registry)
        reads = []

        def read_registry():
            reads.append(self.fixture.now)
            return None

        with patch.object(worker, "work", side_effect=AssertionError("missing input generated work")):
            with self.assertRaisesRegex(IntegrityError, "before T90"):
                held.run_worker(worker, descriptor, read_registry=read_registry,
                                sleep=self.sleep, monotonic=self.monotonic)
        self.assertLessEqual(len(reads), self.policy["held_registry_maximum_probes"])
        self.assertLessEqual(self.fixture.now, self.cutoff)
        self.assertEqual(len(self.native.calls), 1)

    def test_forward_clock_jump_after_input_recovery_cannot_issue_late(self):
        from multisport_lab import sdv_production_held as held
        descriptor = self.planned_holds()
        self.fixture.now = self.start - timedelta(minutes=140)
        self.current._new_inputs()
        worker = self.coordinator(self.current.registry)
        original_work = worker.work
        actions = []

        def work(actual):
            actions.append(actual["action"])
            return original_work(actual)

        def jump(seconds):
            self.sleep(seconds)
            self.fixture.now = self.start - timedelta(minutes=74)

        with patch.object(worker, "work", side_effect=work):
            with self.assertRaisesRegex(IntegrityError, "runtime expired"):
                held.run_worker(worker, descriptor, read_registry=lambda: None,
                                sleep=jump, monotonic=self.monotonic)
        self.assertEqual(actions, ["PREPARE"])
        self.assertEqual(len(self.native.calls), 2)

    def test_backwards_actual_clock_cannot_continue_waiting(self):
        from multisport_lab import sdv_production_held as held
        descriptor = self.planned_holds()

        def backwards(seconds):
            self.sleeps.append(seconds)
            self.elapsed += seconds
            self.fixture.now -= timedelta(seconds=1)

        with patch.object(self.current, "work", side_effect=AssertionError("clock reversal generated work")):
            with self.assertRaisesRegex(IntegrityError, "backwards"):
                held.run_worker(self.current, descriptor, read_registry=lambda: None,
                                sleep=backwards, monotonic=self.monotonic)

    def test_monotonic_hold_ceiling_stops_without_resetting_actual_windows(self):
        from multisport_lab import sdv_production_held as held
        descriptor = self.planned_holds()

        def expensive_sleep(seconds):
            self.sleep(seconds)
            self.elapsed = self.policy["held_runtime_maximum_seconds"] + 1

        with self.assertRaisesRegex(IntegrityError, "runtime expired"):
            held.run_worker(self.current, descriptor, read_registry=lambda: None,
                            sleep=expensive_sleep, monotonic=self.monotonic)
        self.assertLess(self.fixture.now, self.start - timedelta(minutes=150))
        self.assertEqual(len(self.native.calls), 1)

    def test_registry_reader_unchanged_heads_never_repeat_full_archive_recovery(self):
        from multisport_lab import sdv_production_held as held
        descriptor = self.planned_holds()
        recovered = deepcopy(self.current.registry)
        root = self.native.folder / "held-registry-reader"
        root.mkdir()
        reader = held.RegistryReader(self.native.case.source, root, self.native.archive, self.policy)
        head = "f" * 40
        response = SimpleNamespace(stdout=(head + "\trefs/heads/" + runner.INDEX_BRANCH + "\n").encode())

        def prepare(instance, *, commit):
            self.assertEqual(commit, head)
            instance.root.mkdir()
            return deepcopy(recovered)

        with patch.object(runner, "_git", return_value=response), \
                patch.object(runner.RegistryWriter, "prepare", autospec=True, side_effect=prepare) as full:
            self.assertEqual(reader(), recovered)
            for _ in range(self.policy["held_registry_maximum_probes"] - 1):
                self.assertIsNone(reader())
            self.assertEqual(full.call_count, 1)
            with self.assertRaisesRegex(IntegrityError, "head-probe budget"):
                reader()
        self.assertEqual(reader.probes, 96)
        self.assertEqual(reader.readbacks, 1)
        self.assertFalse((root / "1").exists())

    def test_registry_reader_changing_heads_stop_before_seventeenth_readback(self):
        from multisport_lab import sdv_production_held as held
        self.planned_holds()
        recovered = deepcopy(self.current.registry)
        root = self.native.folder / "changing-registry-reader"
        root.mkdir()
        reader = held.RegistryReader(self.native.case.source, root, self.native.archive, self.policy)
        count = 0

        def probe(*args, **kwargs):
            nonlocal count
            count += 1
            return SimpleNamespace(stdout=(format(count, "040x") + "\trefs/heads/" + runner.INDEX_BRANCH + "\n").encode())

        def prepare(instance, *, commit):
            instance.root.mkdir()
            return deepcopy(recovered)

        with patch.object(runner, "_git", side_effect=probe), \
                patch.object(runner.RegistryWriter, "prepare", autospec=True, side_effect=prepare) as full:
            for _ in range(self.policy["held_registry_maximum_readbacks"]):
                self.assertEqual(reader(), recovered)
            with self.assertRaisesRegex(IntegrityError, "full-readback budget"):
                reader()
            self.assertEqual(full.call_count, 16)
        self.assertEqual(reader.readbacks, 16)

    def test_sole_capturer_uses_one_shared_input_without_repeated_source_attempts(self):
        from multisport_lab import sdv_production_held as held
        descriptor = self.planned_holds()
        publication = []
        with patch.object(self.current, "refresh", return_value=[]) as refresh, \
                patch.object(self.current, "_new_inputs", wraps=self.current._new_inputs) as inputs:
            report = held.run_capturer(
                self.current, [descriptor], sleep=self.sleep, monotonic=self.monotonic,
                publish=lambda coordinator: publication.append(self.fixture.now))
        self.assertEqual(report["status"], "HELD_CAPTURE_COMPLETE", report)
        self.assertEqual(report["source_cycles_attempted"], [descriptor["cycle_id"]])
        self.assertEqual(inputs.call_count, 1)
        self.assertEqual(len(self.native.calls), 2)
        self.assertLessEqual(refresh.call_count, self.policy["held_capture_maximum_refreshes"])
        self.assertLessEqual(len(publication), self.policy["held_publication_maximum_checks"])
        shard = self.current.registry["days"][0]["shards"][0]
        self.assertIsNotNone(shard["input_task_ref"])
        self.assertIsNone(shard["issued_input_task_ref"])
        self.assertLessEqual(self.elapsed, self.policy["held_runtime_maximum_seconds"])

    def test_capturer_source_failure_stays_partial_without_clock_tick_retries(self):
        from multisport_lab import sdv_production_held as held
        descriptor = self.planned_holds()
        with patch.object(self.current, "refresh", return_value=[]), \
                patch.object(self.current, "_new_inputs", side_effect=IntegrityError("synthetic source unavailable")) as inputs:
            report = held.run_capturer(self.current, [descriptor], sleep=self.sleep,
                                       monotonic=self.monotonic, publish=lambda coordinator: None)
        self.assertEqual(report["status"], "PARTIAL_OR_FAILED", report)
        self.assertEqual(inputs.call_count, 1)
        self.assertEqual(len(self.native.calls), 1)
        self.assertIn("synthetic source unavailable", report["phase_errors"][0]["error"])

    def test_expired_capturer_does_not_claim_completed_capture(self):
        from multisport_lab import sdv_production_held as held
        descriptor = self.planned_holds()
        self.fixture.now = self.start - timedelta(minutes=74)
        with patch.object(self.current, "_new_inputs", side_effect=AssertionError("late replacement capture")):
            with self.assertRaises(IntegrityError):
                held.run_capturer(self.current, [descriptor], sleep=self.sleep,
                                   monotonic=self.monotonic, publish=lambda coordinator: None)
        self.assertEqual(len(self.native.calls), 1)

    def test_capturer_that_starts_after_t105_keeps_missed_input_explicit(self):
        from multisport_lab import sdv_production_held as held
        descriptor = self.planned_holds()
        self.fixture.now = self.start - timedelta(minutes=100)
        with patch.object(self.current, "_new_inputs", side_effect=AssertionError("late replacement capture")), \
                patch.object(self.current, "refresh", return_value=[]):
            report = held.run_capturer(self.current, [descriptor], sleep=self.sleep,
                                       monotonic=self.monotonic, publish=lambda coordinator: None)
        self.assertEqual(report["status"], "PARTIAL_OR_FAILED", report)
        self.assertEqual(report["missing_input_cycles"], [descriptor["cycle_id"]])
        self.assertEqual(report["source_cycles_attempted"], [])
        self.assertEqual(self.sleeps, [])
        self.assertEqual(len(self.native.calls), 1)
        self.assertIsNone(self.current.registry["days"][0]["shards"][0]["input_task_ref"])

    def test_held_slot_limit_excludes_whole_event_without_truncating_its_cohort(self):
        from multisport_lab import sdv_production_held as held
        event_template = deepcopy(self.fixture.schedule[0])
        home_template, away_template = (deepcopy(row) for row in self.fixture.roster)
        self.fixture.schedule = []
        self.fixture.roster = []
        for index in range(6):
            event = deepcopy(event_template)
            event_id = str(900 + index)
            start = stamp(self.start + timedelta(minutes=index))
            event.update(id=event_id, game_id=event_id,
                         uid="s:40~l:46~e:" + event_id + "~c:" + event_id,
                         date=start, start_date=start, game_date_time=start,
                         home_id=str(100 + 2 * index), away_id=str(101 + 2 * index),
                         home_display_name="Synthetic Home " + str(index),
                         away_display_name="Synthetic Away " + str(index))
            self.fixture.schedule.append(event)
            for away, template in ((False, home_template), (True, away_template)):
                for player_index in range(20):
                    player = deepcopy(template)
                    player_id = str(1000 + index * 100 + int(away) * 20 + player_index)
                    player.update(athlete_id=player_id, uid="s:40~l:46~a:" + player_id,
                                  team_id=event["away_id"] if away else event["home_id"],
                                  team_display_name=event["away_display_name"] if away else event["home_display_name"],
                                  display_name="Synthetic Player " + player_id)
                    self.fixture.roster.append(player)
        self.assertEqual(self.current.prepare_tasks(), [])
        descriptors, exclusions = held.prepare_holds(self.current, [])
        self.assertEqual(len(descriptors), 15)
        self.assertEqual(len(exclusions), 1)
        self.assertEqual(exclusions[0]["event_id"], "905")
        self.assertEqual(exclusions[0]["reason"], "COMPLETE_EVENT_HELD_CAPACITY_UNAVAILABLE")
        plan = self.native.archive.get_json(self.current.registry["days"][0]["plan_ref"])
        self.assertEqual([len(event["candidates"]) for event in plan["events"]], [40] * 6)
        self.assertEqual(len(self.current.registry["days"][0]["shards"]), 18)
        self.assertEqual({row["cycle_id"] for row in descriptors},
                         {event["cycle_id"] for event in plan["events"][:5]})

    def bound_task(self):
        self.planned_holds()
        self.fixture.now = self.start - timedelta(minutes=140)
        self.current._new_inputs()
        row = self.current.registry["days"][0]["shards"][0]
        return {"action": "PREPARE", "task_ref": row["input_task_ref"],
                "final_source_pack_ref": None, "branch": row["branch"],
                "cycle_id": row["cycle_id"], "shard_index": row["shard_index"]}

    def test_failed_readback_result_keeps_capture_running_and_reports_partial(self):
        from multisport_lab import sdv_production_held as held
        descriptor = self.planned_holds()
        with patch.object(self.current, "refresh", return_value=[{"status": "RECOVERY_FAILED"}]):
            report = held.run_capturer(self.current, [descriptor], sleep=self.sleep,
                                       monotonic=self.monotonic, publish=lambda coordinator: None)
        self.assertEqual(report["status"], "PARTIAL_OR_FAILED", report)
        self.assertTrue(any(row["phase"] == "REFRESH" for row in report["phase_errors"]))
        self.assertEqual(len(self.native.calls), 2)
        self.assertIsNotNone(self.current.registry["days"][0]["shards"][0]["input_task_ref"])

    def test_publication_failure_does_not_abort_timely_shared_capture(self):
        from multisport_lab import sdv_production_held as held
        descriptor = self.planned_holds()

        def publish(coordinator):
            raise IntegrityError("synthetic public readback unavailable")

        with patch.object(self.current, "refresh", return_value=[]):
            report = held.run_capturer(self.current, [descriptor], sleep=self.sleep,
                                       monotonic=self.monotonic, publish=publish)
        self.assertEqual(report["status"], "PARTIAL_OR_FAILED", report)
        self.assertTrue(any(row["phase"] == "PUBLICATION" for row in report["phase_errors"]))
        self.assertEqual(len(self.native.calls), 2)
        self.assertIsNotNone(self.current.registry["days"][0]["shards"][0]["input_task_ref"])
        self.assertLessEqual(report["publication_checks"], self.policy["held_publication_maximum_checks"])

    def test_retained_exact_input_recovery_stops_at_sixteen_without_new_source(self):
        from multisport_lab import sdv_production_held as held
        descriptor = self.planned_holds()
        self.fixture.now = self.start - timedelta(minutes=140)
        day = self.current.registry["days"][0]
        plan = self.native.archive.get_json(day["plan_ref"])
        event = plan["events"][0]
        original, _ = self.current._capture(
            "INPUT", [event["cycle_id"]], season=2027,
            opens=common.clock(event["capture_opens_at"]), closes=common.clock(event["cutoff_at"]))
        self.fixture.now = self.start - timedelta(minutes=100)
        with patch.object(self.current, "refresh", return_value=[]), \
                patch.object(self.current, "_new_inputs", side_effect=IntegrityError("synthetic interrupted binding")) as recovery:
            report = held.run_capturer(self.current, [descriptor], sleep=self.sleep,
                                       monotonic=self.monotonic, publish=lambda coordinator: None)
        self.assertEqual(report["status"], "PARTIAL_OR_FAILED", report)
        self.assertEqual(report["input_recovery_attempts"], 16)
        self.assertEqual(recovery.call_count, 16)
        self.assertEqual(report["source_cycles_attempted"], [])
        self.assertEqual(len(self.native.calls), 2)
        self.assertEqual(self.current.registry["attempts"][-1]["source_pack_ref"], original)
        self.assertIsNone(day["shards"][0]["input_task_ref"])

    def test_v2_final_capture_does_not_fetch_for_prepared_only_subjects(self):
        self.bound_task()
        self.fixture.now = self.start + timedelta(hours=4)
        count = len(self.native.calls)
        self.current._final_sources()
        self.assertEqual(len(self.native.calls), count)
        self.assertIsNone(self.current.registry["days"][0]["shards"][0]["final_source_pack_ref"])

    def test_v2_final_age_spacing_cap_and_current_grading_binding(self):
        task = self.bound_task()
        self.assertEqual(self.current.work(task)["status"], "PREPARED")
        self.fixture.now = self.cutoff + timedelta(seconds=1)
        issue = deepcopy(task)
        issue["action"] = "ISSUE"
        self.assertEqual(self.current.work(issue)["status"], "ISSUED_PENDING_OUTCOMES")
        self.current.refresh()
        baseline = len(self.native.calls)
        self.fixture.now = self.start + timedelta(hours=4) - timedelta(microseconds=1)
        self.current._final_sources()
        self.assertEqual(len(self.native.calls), baseline)
        self.fixture.now = self.start + timedelta(hours=4)
        self.current._final_sources()
        self.assertEqual(len(self.native.calls), baseline + 1)
        old_matrix = self.current.grading_tasks()
        self.assertEqual(len(old_matrix), 1)
        old_reference = old_matrix[0]["final_source_pack_ref"]
        self.fixture.now = self.start + timedelta(hours=14) - timedelta(microseconds=1)
        self.current._final_sources()
        self.assertEqual(len(self.native.calls), baseline + 1)
        self.fixture.now = self.start + timedelta(hours=14)
        self.current._final_sources()
        self.assertEqual(len(self.native.calls), baseline + 2)
        counter = len(self.native.calls)
        with patch.object(self.current, "_new_plan", side_effect=AssertionError("grading planned a source")), \
                patch.object(self.current, "_new_inputs", side_effect=AssertionError("grading captured an input")), \
                patch.object(self.current, "_final_sources", side_effect=AssertionError("grading captured a final")):
            current_matrix = self.current.grading_tasks()
        self.assertEqual(len(self.native.calls), counter)
        self.assertNotEqual(current_matrix[0]["final_source_pack_ref"], old_reference)
        self.assertEqual(current_matrix[0]["final_source_pack_ref"],
                         self.current.registry["days"][0]["shards"][0]["final_source_pack_ref"])
        with self.assertRaisesRegex(IntegrityError, "final source changed"):
            self.current.work(old_matrix[0])
        self.fixture.now = self.start + timedelta(days=1) - timedelta(microseconds=1)
        self.current._final_sources()
        self.assertEqual(len(self.native.calls), baseline + 2)
        self.assertEqual(sum(row["phase"] == "FINAL" for row in self.current.registry["attempts"]), 2)

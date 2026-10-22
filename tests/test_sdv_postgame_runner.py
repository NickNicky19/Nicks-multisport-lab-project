"""Synthetic coordinator controls only: no source, dispatch, issue or live Git."""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from multisport_lab import sdv_postgame_runner as post
from multisport_lab.integrity import IntegrityError, canonical, stamp
from multisport_lab.ledger import LedgerRef

NOW = datetime(2026, 10, 23, 13, 17, tzinfo=timezone.utc)
REF = LedgerRef("forecasts", "a" * 64, "b" * 64)
AUTH = LedgerRef("research_inputs", "c" * 64, "d" * 64)


class MemoryStore:
    def __init__(self, root):
        self.project_root = root
        self.rows = []
    def records(self):
        return list(self.rows)
    def corrections(self):
        return []
    def capacity(self, **kwargs):
        return {"existing_records": 19, "existing_bytes": 1024 * 1024,
            "maximum_records": 512, "maximum_bytes": 32 * 1024 * 1024}
    def append_body(self, kind, body, **kwargs):
        ref = LedgerRef(kind, str(len(self.rows) + 1).zfill(64), "f" * 64)
        self.rows.append((ref, body))
        return ref


class PostgameTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(post, "_now", return_value=NOW))
        self.stack.enter_context(patch.object(post, "current_main_head", return_value="1" * 40))

    def test_fixed_window_and_expiration_cannot_make_pregame_forecasts(self):
        for time, expected in [("2026-10-22T13:17:00Z", "BEFORE_POSTGAME_WINDOW"),
                ("2026-10-23T12:59:59Z", "OUTSIDE_DAILY_POSTGAME_WINDOW"),
                ("2026-10-23T14:30:00Z", "OPEN"),
                ("2026-10-23T14:30:00.000001Z", "OUTSIDE_DAILY_POSTGAME_WINDOW"),
                ("2026-10-31T13:17:00Z", "POSTGAME_RESERVATION_EXPIRED")]:
            with self.subTest(time=time):
                self.assertEqual(post.operating_window(time), expected)
        with patch.object(post, "_now", return_value=NOW - timedelta(days=1)), \
                patch.object(post, "authorize_current_run") as authorize, \
                patch.object(post, "failure_alert") as alert:
            report = post.run(work_root=self.root / "before")
            self.assertEqual(report["recurring_pregame_issuance"], "NOT_IMPLEMENTED")
            self.assertEqual(report["source_requests"], 0)
            authorize.assert_not_called(); alert.assert_not_called()

    def test_single_retained_writer_lock_rejects_competitor(self):
        with post.retained_lock(self.root / "lock"):
            with self.assertRaisesRegex(IntegrityError, "writer is active"):
                with post.retained_lock(self.root / "lock"):
                    self.fail("Competing writer entered")

    def test_unauthorized_runtime_never_reaches_api(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(post.cycles, "_fetch_run_metadata") as get:
            with self.assertRaises(IntegrityError):
                post.authorize_current_run()
            get.assert_not_called()

    def test_hosted_schedule_uses_actual_bot_identity_and_manual_dispatch_cannot(self):
        head = "1" * 40
        event_path = self.root / "event.json"
        event_path.write_bytes(canonical({"repository": {"full_name": post.cycles.REPOSITORY},
            "schedule": post.CRON}))
        env = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": post.cycles.REPOSITORY,
            "GITHUB_REF": "refs/heads/main", "GITHUB_WORKFLOW_REF": post.cycles.REPOSITORY + "/"
                + post.WORKFLOW + "@refs/heads/main", "GITHUB_EVENT_NAME": "schedule",
            "GITHUB_ACTOR": "github-actions[bot]", "GITHUB_TRIGGERING_ACTOR": "github-actions[bot]",
            "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_EVENT_PATH": str(event_path),
            "GITHUB_SHA": head, "GH_TOKEN": "SYNTHETIC-NONSECRET"}
        run = {"id": 123, "run_attempt": 1, "event": "schedule", "path": post.WORKFLOW,
            "head_branch": "main", "head_sha": head, "status": "in_progress", "conclusion": None,
            "repository": {"full_name": post.cycles.REPOSITORY}, "actor": {"login": "github-actions[bot]"},
            "triggering_actor": {"login": "github-actions[bot]"}, "run_started_at": stamp(NOW)}
        def committed(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, (post.ROOT / args[2].split(":", 1)[1]).read_bytes(), b"")
        with patch.dict(os.environ, env, clear=True), \
                patch.object(post.cycles, "_fetch_run_metadata", return_value=canonical(run)) as get, \
                patch.object(post, "_git", return_value=subprocess.CompletedProcess([], 0, head, "")), \
                patch.object(post.producer, "make_source_binding", return_value={"binding_id": "a" * 64}), \
                patch.object(post.subprocess, "run", side_effect=committed):
            proof = post.authorize_current_run()
            self.assertEqual(proof["actor"], "github-actions[bot]")
            self.assertEqual(proof["event"], "schedule")
            get.assert_called_once_with(123, "SYNTHETIC-NONSECRET")
            get.reset_mock()
            with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_dispatch"}), self.assertRaises(IntegrityError):
                post.authorize_current_run()
            get.assert_not_called()

    def test_missing_branch_alerts_truthfully_without_source_or_branch_creation(self):
        with patch.object(post, "authorize_current_run", return_value={"verified_at": stamp(NOW)}) as auth, \
                patch.object(post, "fetch_existing_branch", return_value=None), \
                patch.object(post, "failure_alert", return_value={"status": "CREATED"}) as alert, \
                patch.object(post, "DailyGitCheckpointWriter") as writer, \
                patch.object(post.prior, "BoundedCapture") as capture:
            report = post.run(work_root=self.root / "missing")
            self.assertEqual(report["status"], "NO_ELIGIBLE_ORIGINALS")
            self.assertEqual(report["source_requests"], 0)
            self.assertIn("cannot be established", report["error"])
            auth.assert_called_once(); alert.assert_called_once()
            writer.assert_not_called(); capture.assert_not_called()

    def test_combined_reserve_counts_partial_raw_and_rejects_before_capture(self):
        store = MemoryStore(self.root)
        report = post.capacity_preflight(store)
        self.assertTrue(report["fits"])
        self.assertLessEqual(report["existing_bytes"] + report["reserved_bytes"], 32 * 1024 * 1024)
        store.capacity = lambda **kwargs: {"existing_records": 500, "existing_bytes": 20 * 1024 * 1024,
            "maximum_records": 512, "maximum_bytes": 32 * 1024 * 1024}
        with self.assertRaisesRegex(IntegrityError, "Combined"):
            post.capacity_preflight(store)

    def prepare_controller(self):
        store = MemoryStore(self.root / "state")
        originals = [(REF, {"forecast_id": "e" * 64, "input_ref": AUTH.to_record()})]
        self.stack.enter_context(patch.object(post, "authorize_current_run", return_value={"verified_at": stamp(NOW), "head_sha": "1" * 40}))
        self.stack.enter_context(patch.object(post, "fetch_existing_branch", return_value={"commit": "1" * 40}))
        self.stack.enter_context(patch.object(post.prior, "copy_records"))
        self.stack.enter_context(patch.object(post, "DailyStore", return_value=store))
        self.stack.enter_context(patch.object(post, "_eligible", return_value=originals))
        self.stack.enter_context(patch.object(post, "_authority_record", return_value=AUTH))
        self.stack.enter_context(patch.object(post, "_retained_sources", return_value=[]))
        self.stack.enter_context(patch.object(post.grading, "validate_stored_admissions"))
        self.stack.enter_context(patch.object(post.grading, "load_config", return_value={}))
        self.stack.enter_context(patch.object(post.prior, "_records_pr", return_value="https://github.com/example/pr"))
        self.stack.enter_context(patch.object(post, "failure_alert", return_value={"status": "EXISTING_OPEN_ALERT"}))
        self.publisher = self.stack.enter_context(patch.object(post, "reconcile_publication",
            return_value={"status": "PUBLICATION_REQUESTED_UNVERIFIED"}))
        writer = Mock(); writer.prepare.return_value = {}; writer.flush.return_value = {"commit": "2" * 40}
        self.stack.enter_context(patch.object(post, "DailyGitCheckpointWriter", return_value=writer))
        return store, writer

    def test_durable_marker_precedes_get_and_same_day_retry_does_not_recapture(self):
        store, writer = self.prepare_controller()
        capture = Mock(requests=[], root=self.root / "raw")
        factory = self.stack.enter_context(patch.object(post.prior, "BoundedCapture", return_value=capture))
        def interrupted(*args, **kwargs):
            self.assertEqual(store.rows[0][1]["status"], "POSTGAME_CAPTURE_STARTED")
            writer.flush.assert_called_once()
            raise IntegrityError("Synthetic interrupted source retrieval")
        collector = self.stack.enter_context(patch.object(post, "collect_final", side_effect=interrupted))
        report = post.run(work_root=self.root / "work")
        self.assertEqual(report["status"], "PARTIAL_OR_FAILED_POSTGAME")
        self.assertIn("final_checkpoint", report)
        collector.reset_mock(); factory.reset_mock()
        again = post.run(work_root=self.root / "work")
        self.assertEqual(again["status"], "INTERRUPTED_CAPTURE_NO_RECAPTURE")
        collector.assert_not_called(); factory.assert_not_called()
        self.assertEqual(len(store.rows), 2)

    def test_two_started_attempts_block_a_third_get(self):
        store, _ = self.prepare_controller()
        for day in ("2026-10-23", "2026-10-24"):
            store.rows.append((AUTH, {"schema_version": post.prior.OPERATION_SCHEMA,
                "phase": post.PHASE + day, "status": "POSTGAME_CAPTURE_STARTED",
                "recorded_at": day + "T13:17:00.000000Z"}))
        with patch.object(post, "_now", return_value=NOW + timedelta(days=2)), \
                patch.object(post.prior, "BoundedCapture") as capture:
            report = post.run(work_root=self.root / "bounded")
        self.assertEqual(report["status"], "POSTGAME_OBSERVATION_BUDGET_EXHAUSTED")
        capture.assert_not_called()

    def test_success_adds_statistical_records_and_requests_existing_publication_only_once(self):
        store, writer = self.prepare_controller()
        capture = Mock(requests=[], root=self.root / "raw")
        captured = {"schedule": (b"CSV", b"JSON", {}), "boxscore": (b"CSV", b"JSON", {})}
        grade_ref = LedgerRef("grades", "7" * 64, "8" * 64)
        def grade(*args):
            store.rows.append((grade_ref, {"schema_version": post.producer.GRADE_SCHEMA}))
            return {"outcomes": [], "grades": [grade_ref], "corrections": [], "pending": []}
        with patch.object(post.prior, "BoundedCapture", return_value=capture), \
                patch.object(post, "collect_final", return_value=captured), \
                patch.object(post.grading, "retain_source_with_proof", return_value=(AUTH, AUTH)), \
                patch.object(post.grading, "normalize_and_grade", side_effect=grade), \
                patch.object(post.prior, "_publish_records", return_value={"status": "DISPATCH_REQUEST_ACCEPTED_NOT_DEPLOYMENT_VERIFIED"}) as publish:
            self.publisher.side_effect = lambda store, commit, head: {"status": "PUBLICATION_REQUESTED_UNVERIFIED",
                "request": post.prior._publish_records(commit)}
            report = post.run(work_root=self.root / "success")
            self.assertEqual(report["status"], "STATISTICAL_GRADING_RETAINED")
            self.assertEqual(report["statistical_grades"], 1)
            self.assertEqual(report["publication"]["status"], "PUBLICATION_REQUESTED_UNVERIFIED")
            self.assertEqual(report["publication"]["request"]["status"], "DISPATCH_REQUEST_ACCEPTED_NOT_DEPLOYMENT_VERIFIED")
            publish.assert_called_once_with("2" * 40)

    def test_pr_failure_and_exhausted_source_budget_still_publish_recovered_statistics(self):
        store, writer = self.prepare_controller()
        for day in ("2026-10-23", "2026-10-24"):
            store.rows.append((AUTH, {"schema_version": post.prior.OPERATION_SCHEMA,
                "phase": post.PHASE + day, "status": "POSTGAME_CAPTURE_STARTED",
                "recorded_at": day + "T13:17:00.000000Z"}))
        with patch.object(post, "_now", return_value=NOW + timedelta(days=2)), \
                patch.object(post.prior, "BoundedCapture") as capture, \
                patch.object(post.prior, "_records_pr", side_effect=IntegrityError("Synthetic PR HTTP 403")):
            report = post.run(work_root=self.root / "publish-catchup")
        self.assertIn("403", report["records_pr_error"])
        self.publisher.assert_called_once_with(store, "2" * 40, "1" * 40)
        capture.assert_not_called()

    def test_failed_or_interrupted_publication_retries_without_new_statistical_records(self):
        with patch.object(post, "verify_publication", return_value={"status": "PUBLICATION_UNVERIFIED"}) as verify, \
                patch.object(post.prior, "_publish_records", side_effect=IntegrityError("Synthetic dispatch failure")) as dispatch:
            with self.assertRaises(IntegrityError):
                post.reconcile_publication(Mock(), "2" * 40, "1" * 40)
            dispatch.assert_called_once()
        with patch.object(post, "verify_publication", side_effect=[{"status": "PUBLICATION_UNVERIFIED"},
                {"status": "PUBLICATION_VERIFIED", "verified_at": stamp(NOW)}]), \
                patch.object(post.prior, "_publish_records", return_value={"status": "ACCEPTED_ONLY"}) as dispatch, \
                patch.object(post.time, "sleep") as sleep:
            report = post.reconcile_publication(Mock(), "2" * 40, "1" * 40)
            self.assertEqual(report["status"], "PUBLICATION_VERIFIED")
            dispatch.assert_called_once_with("2" * 40); sleep.assert_called_once_with(60)

    def test_public_readback_prevents_unchanged_redeployment_and_limits_failed_polling(self):
        with patch.object(post, "verify_publication", return_value={"status": "PUBLICATION_VERIFIED"}), \
                patch.object(post.prior, "_publish_records") as dispatch:
            self.assertEqual(post.reconcile_publication(Mock(), "2" * 40, "1" * 40)["status"], "PUBLICATION_VERIFIED")
            dispatch.assert_not_called()
        with patch.object(post, "verify_publication", return_value={"status": "PUBLICATION_UNVERIFIED"}), \
                patch.object(post.prior, "_publish_records", return_value={"status": "ACCEPTED_ONLY"}), \
                patch.object(post.time, "sleep") as sleep:
            report = post.reconcile_publication(Mock(), "2" * 40, "1" * 40)
            self.assertEqual(report["status"], "PUBLICATION_REQUESTED_UNVERIFIED")
            self.assertEqual(sleep.call_count, 20)

    def test_advanced_main_does_not_dispatch_a_known_mismatched_build(self):
        with patch.object(post, "verify_publication", return_value={"status": "PUBLICATION_UNVERIFIED"}), \
                patch.object(post, "current_main_head", return_value="9" * 40), \
                patch.object(post.prior, "_publish_records") as dispatch:
            with self.assertRaisesRegex(IntegrityError, "Main advanced"):
                post.reconcile_publication(Mock(), "2" * 40, "1" * 40)
            dispatch.assert_not_called()

    def public_fixture(self):
        from multisport_lab import publication
        import hashlib
        asset = post.public.make_asset(self.root / "empty", now=NOW)
        raw = canonical(asset); sha = hashlib.sha256(raw).hexdigest()
        manifest = {"schema_version": 6, "build_commit": "1" * 40, "published_at": stamp(NOW),
            "publication_status": "RESEARCH_ONLY", "supported_sports": ["NBA"], "errors": {},
            "sports": [{"league": "NBA", "path": "nba." + "2" * 64 + ".json", "sha256": "2" * 64,
                "generated_at": stamp(NOW), "status": "RESEARCH_ONLY", "retained": False, "error": None}]}
        for channel in publication._channel_names(6):
            manifest[channel] = None; manifest[channel + "_error"] = None
        manifest["daily_research"] = {"path": "sdv-daily." + sha + ".json", "sha256": sha,
            "generated_at": stamp(NOW), "status": "DAILY_SNAPSHOT_RESEARCH", "retained": False, "error": None}
        manifest["snapshot_id"] = post.digest(manifest)
        return manifest, asset

    def test_actual_typed_publication_validation_checks_hashes_meaning_build_and_ids(self):
        manifest, asset = self.public_fixture()
        with patch.object(post, "_public_get", side_effect=[canonical(manifest), canonical(asset)]) as get:
            result = post.verify_publication(MemoryStore(self.root), "1" * 40)
            self.assertEqual(result["status"], "PUBLICATION_VERIFIED")
            self.assertEqual(get.call_count, 2)
        with patch.object(post, "_public_get", return_value=canonical(manifest)):
            self.assertEqual(post.verify_publication(MemoryStore(self.root), "9" * 40)["status"], "PUBLICATION_UNVERIFIED")
        with patch.object(post, "_public_get", side_effect=[canonical(manifest), canonical(asset)]), \
                patch.object(post, "_expected_public", return_value={"forecasts": {"missing": {}}, "outcomes": {}, "grades": {}}):
            self.assertEqual(post.verify_publication(MemoryStore(self.root), "1" * 40)["status"], "PUBLICATION_UNVERIFIED")
        import hashlib
        asset["financial_settlement"] = "SETTLED"
        asset["asset_id"] = post.digest({k: v for k, v in asset.items() if k != "asset_id"})
        sha = hashlib.sha256(canonical(asset)).hexdigest()
        manifest["daily_research"].update(sha256=sha, path="sdv-daily." + sha + ".json")
        manifest["snapshot_id"] = post.digest({k: v for k, v in manifest.items() if k != "snapshot_id"})
        with patch.object(post, "_public_get", side_effect=[canonical(manifest), canonical(asset)]):
            self.assertEqual(post.verify_publication(MemoryStore(self.root), "1" * 40)["status"], "PUBLICATION_UNVERIFIED")

    def test_bounded_collector_retains_distinct_metadata_and_final_asset_clocks(self):
        config = json.loads((post.ROOT / post.grading.DEFAULT_CONFIG_PATH).read_bytes())
        counter = [0]
        def get(url, *, limit, label, **kwargs):
            counter[0] += 1
            start = NOW + timedelta(seconds=counter[0])
            return label.encode(), {"status": 200, "retrieval_started_at": stamp(start),
                "retrieved_at": stamp(start + timedelta(milliseconds=1))}, None
        capture = Mock(); capture.get.side_effect = get
        before = Mock()
        result = post.collect_final(capture, config, preflight=before)
        self.assertEqual(capture.get.call_count, 4)
        self.assertEqual(before.call_count, 4)
        self.assertEqual(set(result), {"schedule", "boxscore"})
        self.assertLess(result["schedule"][2]["metadata_retrieved_at"],
            result["schedule"][2]["asset_retrieval_started_at"])

    def test_partial_archive_excludes_redirect_html_and_preserves_exact_200_bytes(self):
        directory = self.root / "originals"; directory.mkdir()
        raw = b"exact admitted metadata bytes"
        (directory / "request-01.body").write_bytes(raw)
        (directory / "request-02.body").write_bytes(b"https://signed.example/?private=temporary")
        import hashlib
        request = {"request_number": 1, "status": 200, "response_limit_bytes": 262144,
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "route": "https://api.github.com/repos/sportsdataverse/releases",
            "retrieved_at": stamp(NOW), "retrieval_started_at": stamp(NOW)}
        store = Mock(); store.retain_outcome_evidence.return_value = AUTH
        store.records.return_value = []
        store.ledger = Mock(spec=[])
        post._preserve_partial(store, directory, [request, {"request_number": 2, "status": 302}], AUTH)
        self.assertEqual(store.retain_outcome_evidence.call_args.args[0], raw)
        store.retain_outcome_evidence.assert_called_once()

    def test_static_full_plan_and_runtime_remaining_slots_are_distinct(self):
        store = MemoryStore(self.root)
        initial = post.capacity_preflight(store)
        self.assertEqual(initial["reserved_records"], 76)
        self.assertEqual(initial["reserved_bytes"], 19955712)
        self.assertEqual(initial["static_full_planned_capacity"]["total_records"], 155)
        self.assertEqual(initial["static_full_planned_capacity"]["total_reserved_bytes"], 31431880)
        # Unknown existing bytes are never reclaimed. A closed attempt's full
        # source reserve is not incorrectly reserved a second time.
        store.rows = [(AUTH, {"schema_version": post.prior.OPERATION_SCHEMA,
            "phase": "POSTGAME_2026-10-23", "status": status})
            for status in ("POSTGAME_CAPTURE_STARTED", "PARTIAL_OR_FAILED_POSTGAME")]
        store.capacity = lambda **kwargs: {"existing_records": 100, "existing_bytes": 20 * 1024 * 1024,
            "maximum_records": 512, "maximum_bytes": 32 * 1024 * 1024}
        remaining = post.capacity_preflight(store)
        self.assertTrue(remaining["fits"])
        self.assertEqual(remaining["future_capture_attempts"], 1)
        self.assertEqual(remaining["reserved_records"], 70)
        self.assertEqual(remaining["reserved_bytes"], initial["reserved_bytes"] - 7864320 - 16384)
        store.capacity = lambda **kwargs: {"existing_records": 100, "existing_bytes": 24 * 1024 * 1024,
            "maximum_records": 512, "maximum_bytes": 32 * 1024 * 1024}
        with self.assertRaisesRegex(IntegrityError, "Combined"):
            post.capacity_preflight(store)

    def grading_fixture(self):
        from test_sdv_daily_grading import GenuineGradingReadinessTests
        fixture = GenuineGradingReadinessTests("runTest")
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        return fixture

    def write_capture_bodies(self, fixture):
        triples, requests = fixture.last_capture
        bodies = (triples[0][1], triples[0][0], triples[1][1], triples[1][0])
        root = self.root / "interrupted-originals"; root.mkdir()
        for row, raw in zip(requests, bodies):
            (root / ("request-%02d.body" % row["request_number"])).write_bytes(raw)
        return root, requests

    def test_partial_proof_recovery_retains_exact_canonical_csv_without_duplicates(self):
        fixture = self.grading_fixture(); original_append = fixture.store.append_body
        def interrupt(kind, body, **kwargs):
            ref = original_append(kind, body, **kwargs)
            if body.get("metadata", {}).get("source_kind") == "SportsDataverse NBA schedule CSV":
                raise InterruptedError("Synthetic stop after durable schedule CSV")
            return ref
        with patch.object(fixture.store, "append_body", side_effect=interrupt), self.assertRaises(InterruptedError):
            fixture.capture()
        proof_ref, proof = post._retained_sources(fixture.store)[0]
        original_proof = fixture.store.path(proof_ref).read_bytes()
        root, requests = self.write_capture_bodies(fixture)
        post._preserve_partial(fixture.store, root, requests, AUTH)
        evidence = [(ref, body) for ref, body in fixture.store.records()
            if body["schema_version"] == post.OUTCOME_EVIDENCE_SCHEMA]
        self.assertEqual(len(evidence), 3)  # one proof plus the two original CSVs
        self.assertNotIn(post.PARTIAL_KIND, [body["metadata"]["source_kind"] for _, body in evidence])
        self.assertEqual(fixture.store.path(proof_ref).read_bytes(), original_proof)
        sr, br = post.recover_source_refs(fixture.store, proof_ref, proof)
        result = post.grading.normalize_and_grade(fixture.store, fixture.refs, sr, br)
        self.assertEqual(len(result["grades"]), 2)
        before = {path: path.read_bytes() for path in fixture.store.project_root.rglob("*.json")}
        post._preserve_partial(fixture.store, root, requests, AUTH)
        self.assertEqual(before, {path: path.read_bytes() for path in fixture.store.project_root.rglob("*.json")})

    def test_incomplete_proof_stays_partial_and_can_recover_from_legacy_exact_original(self):
        fixture = self.grading_fixture(); fixture.store.interrupt_after = "research_inputs"
        with self.assertRaises(InterruptedError):
            fixture.capture()
        proof_ref, proof = post._retained_sources(fixture.store)[0]
        with self.assertRaises(post.IncompleteRetainedObservation):
            post.recover_source_refs(fixture.store, proof_ref, proof)
        # Legacy generic partial originals remain untouched and count as actual
        # additional footprint; recovery adds only the missing canonical links.
        triples, requests = fixture.last_capture
        for role, triple in zip(("schedule", "boxscore"), triples):
            row = next(row for row in requests if row["label"] == role + "_asset")
            body = post.grading._retained_body(triple[0], post.grading._meta(post.PARTIAL_KIND,
                row["route"], row["retrieved_at"], "Synthetic legacy exact original",
                started=row["retrieval_started_at"]))
            fixture.store.append_body("research_inputs", body)
        retained = {path: path.read_bytes() for path in fixture.store.project_root.rglob("*.json")}
        sr, br = post.recover_source_refs(fixture.store, proof_ref, proof)
        self.assertTrue(all(path.read_bytes() == raw for path, raw in retained.items()))
        self.assertEqual(len(post.grading.normalize_and_grade(fixture.store, fixture.refs, sr, br)["grades"]), 2)

    def test_pending_retained_event_does_not_block_second_capture_or_reset_two_attempt_bound(self):
        fixture = self.grading_fixture()
        complete_rows = fixture.rows
        fixture.rows = []
        fixture.capture()  # Complete original source bytes, not final player evidence.
        preserved = {path: path.read_bytes() for path in fixture.store.project_root.rglob("*.json")}
        first_day = fixture.now.date().isoformat()
        fixture.now += timedelta(days=1)
        fixture.now = fixture.now.replace(hour=13, minute=17)
        fixture.rows = complete_rows
        # Prepare exactly one later synthetic observation without retaining it;
        # the real controller/retainer below must consume this allowed attempt.
        with patch.object(post.grading, "retain_source_with_proof", return_value=(AUTH, AUTH)):
            fixture.capture()
        triples, requests = fixture.last_capture
        captured = {"schedule": triples[0], "boxscore": triples[1]}
        originals = [(ref, fixture.store.read(ref)["data"]["daily"]) for ref in fixture.refs]
        writer = Mock(); writer.prepare.return_value = {}; writer.flush.return_value = {"commit": "2" * 40}
        capture = Mock(requests=requests, root=self.root / "mock-source-originals")
        with ExitStack() as stack:
            stack.enter_context(patch.object(post, "_now", side_effect=lambda: fixture.now))
            stack.enter_context(patch.object(post, "authorize_current_run",
                side_effect=lambda: {"verified_at": stamp(fixture.now), "head_sha": "1" * 40}))
            stack.enter_context(patch.object(post, "fetch_existing_branch", return_value={"commit": "1" * 40}))
            stack.enter_context(patch.object(post.prior, "copy_records"))
            stack.enter_context(patch.object(post, "DailyStore", return_value=fixture.store))
            stack.enter_context(patch.object(post, "_eligible", return_value=originals))
            stack.enter_context(patch.object(post, "_authority_record", return_value=AUTH))
            stack.enter_context(patch.object(post, "DailyGitCheckpointWriter", return_value=writer))
            stack.enter_context(patch.object(post.prior, "_records_pr", return_value="SYNTHETIC_PR"))
            stack.enter_context(patch.object(post, "reconcile_publication",
                return_value={"status": "PUBLICATION_REQUESTED_UNVERIFIED"}))
            stack.enter_context(patch.object(post, "failure_alert", return_value={"status": "SYNTHETIC_NO_EXTERNAL_WRITE"}))
            factory = stack.enter_context(patch.object(post.prior, "BoundedCapture", return_value=capture))
            collector = stack.enter_context(patch.object(post, "collect_final", return_value=captured))
            result = post.run(work_root=self.root / "second-observation")
            self.assertEqual(result["status"], "STATISTICAL_GRADING_RETAINED")
            self.assertEqual(result["statistical_grades"], 2)
            self.assertEqual(result["outcome_records"], 1)
            factory.assert_called_once(); collector.assert_called_once()
            self.assertEqual(len(post._retained_sources(fixture.store)), 2)
            self.assertTrue(all(path.read_bytes() == raw for path, raw in preserved.items()))
            self.assertEqual(post._retained_sources(fixture.store)[0][1]["created_at"][:10], first_day)
            # A third UTC day can replay/grade already retained evidence, but
            # cannot create another capture or treat the pending first one as free.
            fixture.now += timedelta(days=1)
            factory.reset_mock(); collector.reset_mock()
            again = post.run(work_root=self.root / "second-observation")
            self.assertEqual(again["status"], "POSTGAME_OBSERVATION_BUDGET_EXHAUSTED")
            factory.assert_not_called(); collector.assert_not_called()
            self.assertEqual(len(post._retained_sources(fixture.store)), 2)
            self.assertTrue(all(path.read_bytes() == raw for path, raw in preserved.items()))

    def test_same_day_incomplete_proof_is_not_reported_as_completed(self):
        store, _ = self.prepare_controller()
        store.rows.append((AUTH, {"schema_version": post.prior.OPERATION_SCHEMA,
            "phase": post.PHASE + "2026-10-23", "status": "POSTGAME_CAPTURE_STARTED",
            "recorded_at": stamp(NOW)}))
        proof = {"proof_id": "1" * 64, "created_at": stamp(NOW)}
        with patch.object(post, "_retained_sources", return_value=[(AUTH, proof)]), \
                patch.object(post, "recover_source_refs", side_effect=post.IncompleteRetainedObservation("Missing exact original CSV")), \
                patch.object(post.prior, "BoundedCapture") as capture:
            report = post.run(work_root=self.root / "incomplete-today")
        self.assertEqual(report["status"], "INTERRUPTED_CAPTURE_NO_RECAPTURE")
        self.assertEqual(len(report["incomplete_observations"]), 1)
        capture.assert_not_called()

    def test_failure_alert_is_idempotent_and_403_is_reported_separately(self):
        report = {"status": "NO_ELIGIBLE_ORIGINALS", "recorded_at": stamp(NOW), "source_requests": 0}
        title = "NBA research operational failure [" + post.cycles.CYCLE_ID + "]"
        result = subprocess.CompletedProcess([], 0, json.dumps([{"title": title, "url": "https://github.com/issue/1"}]), "")
        with patch.object(post.subprocess, "run", return_value=result) as command:
            alert = post.failure_alert(report)
            self.assertEqual(alert["status"], "EXISTING_OPEN_ALERT")
            command.assert_called_once()
        with patch.object(post, "failure_alert", side_effect=IntegrityError("GitHub HTTP 403")):
            finished = post._finish(report, self.root / "report.json", alert=True)
        self.assertEqual(finished["failure_alert"]["status"], "UNAVAILABLE")
        self.assertIn("403", finished["failure_alert"]["reason"])


if __name__ == "__main__":
    unittest.main()

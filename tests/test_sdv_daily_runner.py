from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from multisport_lab import sdv_daily_runner as runner
from multisport_lab.integrity import IntegrityError, canonical, digest, stamp
from multisport_lab.ledger import LedgerRef


class Response:
    def __init__(self, raw=b"data", status=200, headers=None):
        self.raw, self.code, self.headers = raw, status, headers or {}

    def read(self, limit):
        return self.raw[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class DailyRunnerTests(unittest.TestCase):
    def test_copy_preserves_existing_parent_and_daily_originals_and_rejects_conflict(self):
        with tempfile.TemporaryDirectory() as folder:
            source, destination = Path(folder) / "source", Path(folder) / "destination"
            for prefix in ("records", "daily/records"):
                path = source / prefix / "research_inputs/one.json"
                path.parent.mkdir(parents=True)
                path.write_bytes(b'{"original":true}\n')
            runner.copy_records(source, destination)
            runner.copy_records(source, destination)
            self.assertEqual((destination / "daily/records/research_inputs/one.json").read_bytes(),
                             b'{"original":true}\n')
            (source / "records/research_inputs/one.json").write_bytes(b"changed")
            with self.assertRaisesRegex(IntegrityError, "replace original"):
                runner.copy_records(source, destination)

    def test_publisher_metadata_binds_actual_asset_bytes_and_does_not_invent_upstream_clock(self):
        source = runner.cycles.SOURCE_ASSETS[0]
        now = datetime.now(timezone.utc) - timedelta(minutes=5)
        raw = b"synthetic original CSV"
        asset = {"id": 100, "name": source["asset_name"], "size": len(raw),
            "digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "browser_download_url": source["asset_url"], "updated_at": stamp(now - timedelta(hours=1))}
        metadata_raw = canonical({"tag_name": source["release_tag"], "assets": [asset]})
        body = runner.source_metadata(raw, metadata_raw, source,
            retrieval_started_at=now, retrieved_at=now + timedelta(seconds=1))
        self.assertEqual(body["upstream_observation_status"], "UNKNOWN")
        self.assertIsNone(body["upstream_observed_at"])
        self.assertEqual(body["metadata_sha256"], hashlib.sha256(metadata_raw).hexdigest())
        with self.assertRaisesRegex(IntegrityError, "publisher release bytes"):
            runner.source_metadata(raw + b"changed", metadata_raw, source,
                retrieval_started_at=now, retrieved_at=now + timedelta(seconds=1))

    def test_capture_counts_every_attempt_and_never_publishes_signed_redirect_queries(self):
        with tempfile.TemporaryDirectory() as folder:
            capture = runner.BoundedCapture(folder)
            capture.opener = MagicMock()
            capture.opener.open.return_value = Response()
            url = "https://release-assets.githubusercontent.com/github-production-release-asset/a?sig=PRIVATE"
            for _ in range(6):
                capture.get(url, limit=20, label="synthetic_redirect", redirect=True)
            with self.assertRaisesRegex(IntegrityError, "budget exhausted"):
                capture.get(url, limit=20, label="seventh", redirect=True)
            self.assertEqual(capture.opener.open.call_count, 6)
            retained = (Path(folder) / "requests.json").read_text()
            self.assertNotIn("PRIVATE", retained)
            self.assertNotIn("?sig", retained)
            self.assertEqual(len(json.loads(retained)), 6)
            with self.assertRaisesRegex(IntegrityError, "recovered"):
                runner.BoundedCapture(folder)

    def test_oversized_response_retains_observed_status_without_pretending_complete_original(self):
        with tempfile.TemporaryDirectory() as folder:
            capture = runner.BoundedCapture(folder)
            capture.opener = MagicMock()
            capture.opener.open.return_value = Response(b"x" * 12)
            with self.assertRaisesRegex(IntegrityError, "no truncation"):
                capture.get("https://api.github.com/example", limit=10, label="oversized")
            row = json.loads((Path(folder) / "requests.json").read_text())[0]
            self.assertEqual(row["status"], 200)
            self.assertEqual(row["bytes_read"], 11)
            self.assertTrue(row["response_exceeded_limit"])
            self.assertNotIn("sha256", row)
            self.assertFalse((Path(folder) / "request-01.body").exists())

    def test_capture_rejects_nonadmitted_redirect_without_spending_request(self):
        with tempfile.TemporaryDirectory() as folder:
            capture = runner.BoundedCapture(folder)
            with self.assertRaisesRegex(IntegrityError, "outside the admitted route"):
                capture.get("https://unrelated.example/data", limit=10, label="bad", redirect=True)
            self.assertEqual(capture.requests, [])

    def test_complete_first_asset_is_persisted_before_second_source_failure(self):
        source = runner.cycles.SOURCE_ASSETS[0]
        now = datetime.now(timezone.utc) - timedelta(minutes=5)
        raw = b"synthetic first CSV"
        metadata = canonical({"tag_name": source["release_tag"], "assets": [{"id": 100,
            "name": source["asset_name"], "size": len(raw),
            "digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "browser_download_url": source["asset_url"], "updated_at": stamp(now - timedelta(hours=1))}]})
        receipt = {"status": 200, "retrieval_started_at": stamp(now), "retrieved_at": stamp(now)}
        with tempfile.TemporaryDirectory() as folder:
            capture = runner.BoundedCapture(folder)
            callback = MagicMock()
            with patch.object(capture, "get", side_effect=[(metadata, receipt, None),
                    (raw, receipt, None), IntegrityError("second source failed")]):
                with self.assertRaisesRegex(IntegrityError, "second source failed"):
                    capture.collect({"source_assets": runner.cycles.SOURCE_ASSETS}, on_asset=callback)
            callback.assert_called_once()
            self.assertEqual(callback.call_args.args[0], raw)
            self.assertEqual(callback.call_args.args[2], metadata)

    def test_recovered_original_intent_requires_all_timely_acknowledgments(self):
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
        ref = LedgerRef("input_captures", "a" * 64, "b" * 64)
        rows = [(None, {"schema_version": "nba-sdv-daily-completion-v1", "stage": stage,
            "reference": ref.to_record(), "completed_at": stamp(cutoff - timedelta(seconds=3 - number)),
            "remote_commit": "c" * 40 if number else None})
            for number, stage in enumerate(("LOCAL_PERSISTENCE", "REMOTE_CHECKPOINT", "FINAL_RECOVERY"))]
        store = MagicMock()
        store.records.return_value = rows
        # Recovery occurs later; original timely clocks remain authoritative.
        self.assertTrue(runner._intent_ready(store, ref, cutoff=stamp(cutoff)))
        store.records.return_value = rows[:2]
        self.assertFalse(runner._intent_ready(store, ref, cutoff=stamp(cutoff)))
        store.records.return_value = rows
        rows[-1][1]["completed_at"] = stamp(cutoff + timedelta(seconds=1))
        with self.assertRaisesRegex(IntegrityError, "missed durable pre-cutoff"):
            runner._intent_ready(store, ref, cutoff=stamp(cutoff))

    def test_wait_checks_actual_deadline_and_uses_at_most_thirty_second_sleeps(self):
        start = datetime(2026, 10, 22, 23, tzinfo=timezone.utc)
        with patch.object(runner, "_now", side_effect=[start, start + timedelta(seconds=31),
                start + timedelta(seconds=61)]), patch.object(runner.time, "sleep") as sleep:
            runner.wait_until(start + timedelta(seconds=60), deadline=start + timedelta(seconds=100))
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [30, 29])
        with patch.object(runner, "_now", return_value=start + timedelta(seconds=101)):
            with self.assertRaisesRegex(IntegrityError, "deadline was missed"):
                runner.wait_until(start, deadline=start + timedelta(seconds=100))

    def test_recover_is_strictly_read_only_and_does_not_generate(self):
        report = {"records": [], "forecasts": [], "inputs": [], "genuine_issued": 0, "admissions": {}}
        with patch.object(runner, "DailyStore") as store, \
                patch.object(runner.producer, "issue_cycle") as issue, \
                patch.object(runner, "BoundedCapture") as capture:
            store.return_value.recover.return_value = report
            result = runner.recover("/tmp/synthetic-retained-store")
        issue.assert_not_called()
        capture.assert_not_called()
        self.assertEqual(result["status"], "READ_ONLY_RECOVERY")
        self.assertEqual(result["genuine_issued"], 0)

    def test_unapproved_run_fails_before_source_or_remote_writer_and_retains_factual_report(self):
        report = {"records": [], "forecasts": [], "inputs": [], "genuine_issued": 0, "admissions": {}}
        cycle = {"cycle_id": "synthetic-cycle", "records_branch": "records/sdv-daily-synthetic"}
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(runner.cycles, "load_cycle", return_value=cycle), \
                    patch.object(runner.producer, "make_source_binding", return_value={}), \
                    patch.object(runner, "copy_records"), patch.object(runner, "DailyStore") as store, \
                    patch.dict(runner.os.environ, {}, clear=True), \
                    patch.object(runner, "BoundedCapture") as capture, \
                    patch("multisport_lab.sdv_daily_remote.DailyGitCheckpointWriter") as writer:
                store.return_value.records.return_value = []
                store.return_value.recover.return_value = report
                with self.assertRaisesRegex(IntegrityError, "see retained execution-report"):
                    runner.run(work_root=folder, producer_commit="a" * 40,
                               records_branch=cycle["records_branch"])
                capture.assert_not_called()
                writer.assert_not_called()
                factual = json.loads((Path(folder) / "execution-report.json").read_text())
                self.assertEqual(factual["status"], "FAILED_OR_PARTIAL")
                self.assertEqual(factual["source_requests"], 0)
                self.assertEqual(factual["genuine_issued"], 0)
                self.assertIn("exact owner manual main workflow", factual["error"])

    def test_failed_authenticated_authority_after_readonly_recovery_never_pushes(self):
        report = {"records": [], "forecasts": [], "inputs": [], "genuine_issued": 0, "admissions": {}}
        cycle = {"cycle_id": "synthetic-cycle", "records_branch": "records/sdv-daily-synthetic"}
        env = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": runner.cycles.REPOSITORY,
            "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_ACTOR": runner.cycles.OWNER,
            "GITHUB_REF": "refs/heads/main", "GITHUB_WORKFLOW_REF": runner.cycles.REPOSITORY
            + "/" + runner.cycles.WORKFLOW_PATH + "@refs/heads/main"}
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(runner.cycles, "load_cycle", return_value=cycle), \
                    patch.object(runner.producer, "make_source_binding", return_value={}), \
                    patch.object(runner.cycles, "authorize_owner_dispatch", side_effect=IntegrityError("actual API rejects authority")), \
                    patch.object(runner, "copy_records"), patch.object(runner, "DailyStore") as store, \
                    patch.dict(runner.os.environ, env, clear=True), \
                    patch.object(runner, "BoundedCapture") as capture, patch.object(runner, "_records_pr") as pr, \
                    patch("multisport_lab.sdv_daily_remote.DailyGitCheckpointWriter") as writer:
                store.return_value.records.return_value = []
                store.return_value.recover.return_value = report
                writer.return_value._head = "a" * 40
                writer.return_value.prepare.return_value = {"local_head": "a" * 40}
                with self.assertRaises(IntegrityError):
                    runner.run(work_root=folder, producer_commit="a" * 40,
                               records_branch=cycle["records_branch"])
                writer.return_value.prepare.assert_called_once()
                writer.return_value.flush.assert_not_called()
                writer.return_value.checkpoint.assert_not_called()
                capture.assert_not_called()
                pr.assert_not_called()

    def test_operating_report_rejects_resealed_impossible_counts_clocks_and_private_urls(self):
        now = datetime.now(timezone.utc) - timedelta(minutes=1)
        row = {"request_number": 1, "label": "schedule_publisher_metadata",
            "route": runner.cycles.SOURCE_ASSETS[0]["metadata_url"],
            "retrieval_started_at": stamp(now), "response_limit_bytes": runner.MAX_METADATA_BYTES,
            "automatic_redirects": False, "automatic_retries": 0, "status": "UNOBSERVED",
            "failed_at": stamp(now + timedelta(seconds=1))}
        body = {"schema_version": runner.OPERATION_SCHEMA, "protocol_id": runner.inputs.PROTOCOL_ID,
            "cycle_id": runner.cycles.CYCLE_ID, "mode": "PROSPECTIVE_RESEARCH", "phase": "CAPTURE",
            "status": "FAILED_OR_PARTIAL", "recorded_at": stamp(now + timedelta(seconds=2)),
            "source_requests": [row], "input_ref": None, "forecast_ids": [], "genuine_issued": 0,
            "error": "Synthetic failure"}
        body["operation_id"] = digest(body)
        runner.validate_operation(body)
        from copy import deepcopy
        for mutate in (lambda b: b.update(genuine_issued=1),
                lambda b: b["source_requests"][0].update(route="https://github.com/a?sig=SECRET"),
                lambda b: b["source_requests"][0].update(failed_at=stamp(now + timedelta(seconds=3))),
                lambda b: b["source_requests"][0].update(sha256="a" * 64)):
            bad = deepcopy(body)
            mutate(bad)
            bad["operation_id"] = digest({key: value for key, value in bad.items() if key != "operation_id"})
            with self.assertRaises(IntegrityError):
                runner.validate_operation(bad)

    def test_publication_dispatch_uses_existing_workflow_and_exact_records_commit_only(self):
        result = MagicMock(returncode=0)
        with patch.object(runner.subprocess, "run", return_value=result) as command:
            receipt = runner._publish_records("a" * 40)
        self.assertEqual(command.call_args.args[0], ["gh", "workflow", "run", "pages.yml", "--repo",
            runner.cycles.REPOSITORY, "--ref", "main", "-f", "daily_records_commit=" + "a" * 40])
        self.assertEqual(receipt["status"], "DISPATCH_REQUEST_ACCEPTED_NOT_DEPLOYMENT_VERIFIED")
        with self.assertRaises(IntegrityError):
            runner._publish_records("main")


if __name__ == "__main__":
    unittest.main()

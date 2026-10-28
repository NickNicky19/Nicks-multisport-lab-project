"""Invented publication/recovery contracts; no collection or model fitting."""
from copy import deepcopy
from datetime import timedelta
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import sdv_production_common as common
from multisport_lab import sdv_production_forecasts as forecasts
from multisport_lab import sdv_production_publication as public
from multisport_lab.integrity import IntegrityError, canonical, digest, load_json, stamp, utc
from multisport_lab.ledger import LedgerRef
import test_sdv_production_inputs as input_fixtures

ROOT = Path(__file__).resolve().parents[1]


def synthetic_ref(kind, seed):
    return LedgerRef(kind, digest({"invented_record": seed}), digest({"invented_payload": seed}))


def synthetic_publication(*, at=None, policy=None, game_date="2026-10-24"):
    """Actual source normalizer plus static invented PMFs, never law fitting."""
    source = input_fixtures.ProductionInputTests()
    try:
        source.setUp()
        if at is not None:
            source.now = utc(at)
        if game_date != "2026-10-24":
            for event in source.schedule:
                for field in ("date", "start_date", "game_date_time"):
                    event[field] = event[field].replace("2026-10-24", game_date)
        source.binding = common.seal({"schema_version": forecasts.BINDING_SCHEMA, "commit": None,
            "files": {name: common.LAW_SHA256["R0"] if name == "multisport_lab/baseline.py"
                      else common.LAW_SHA256["K0"] if name == "multisport_lab/development_003.py"
                      else digest({"synthetic_source_name": name}) for name in forecasts.SOURCE_FILES},
            "law_sha256": deepcopy(common.LAW_SHA256)}, "binding_id")
        assets = source.assets()
        from multisport_lab import sdv_production_inputs
        plan = sdv_production_inputs.make_plan(*assets[:4], source_originals=assets[4],
            game_date=game_date, producer_binding=source.binding, policy=policy)
        input_body = source.fresh(plan)
        template = load_json(ROOT / "tests/fixtures/sdv-daily-synthetic.json")["forecasts"][0]["body"]
        plan_ref, input_ref = synthetic_ref("input_captures", "production plan"), synthetic_ref("input_captures", "production input")
        rows = [public.project_original(plan_ref, plan), public.project_original(input_ref, input_body)]
        candidate, event = input_body["candidates"][0], input_body["event"]
        cutoff = common.clock(event["event_starts_at"]) - timedelta(minutes=90)
        for model in ("R0", "K0"):
            body = deepcopy(template)
            body.update(schema_version=common.FORECAST_SCHEMA, protocol_id=common.PROTOCOL_ID,
                plan_id=plan["plan_id"], cycle_id=input_body["cycle_id"], model_key=model,
                model_version=common.MODEL_VERSIONS[model], producer_version=forecasts.PRODUCERS[model],
                producer_binding=deepcopy(source.binding), input_ref=input_ref.to_record(), input_id=input_body["input_id"],
                event_snapshot_id=event["event_snapshot_id"], event_id=event["event_id"], event_starts_at=event["event_starts_at"],
                **candidate, matchup=event["away_team_name"]+" @ "+event["home_team_name"], cutoff_at=stamp(cutoff),
                history_freeze=stamp(cutoff.replace(hour=0,minute=0,second=0,microsecond=0)),
                generation_started_at=stamp(source.now), generation_completed_at=stamp(source.now),
                verified_at=stamp(source.now), issued_at=None, mode="DEVELOPMENT_ONLY", evidence_lane="DEVELOPMENT_ONLY")
            body["joint_recipe"]["algorithm"] = common.MODEL_VERSIONS[model]
            body = common.seal({k: v for k, v in body.items() if k != "forecast_id"}, "forecast_id")
            forecasts.validate_forecast(body, input_body)
            admission = {"eligible": False, "local_completed_at": None, "remote_recovered_at": None,
                         "reasons": ["DEVELOPMENT_ONLY_NOT_PROSPECTIVE"], "archive_ref": None}
            rows.append(public.project_original(synthetic_ref("forecasts", "production "+model), body, admission))
        return source.now, rows
    finally:
        source.doCleanups()


class ProductionPublicationTests(unittest.TestCase):
    def setUp(self):
        self.now, self.records = synthetic_publication()
        timer = patch.object(common, "now", return_value=self.now)
        timer.start(); self.addCleanup(timer.stop)

    def emit(self, *, records=None):
        return public.make_publication(self.records if records is None else records,
                                       now=self.now, allow_development=True)

    def test_development_originals_never_enter_default_public_export(self):
        original = deepcopy(self.records)
        with self.assertRaisesRegex(IntegrityError, "Development records"):
            public.make_publication(self.records, now=self.now)
        index, pages = self.emit()
        self.assertEqual(index["counts"]["development_forecasts"], 2)
        self.assertEqual(index["counts"]["genuine_forecasts"], 0)
        self.assertEqual(index["counts"]["pending_grades"], 0)
        self.assertEqual(self.records, original)
        self.assertEqual({len(public.original_record(row)["categories"]) for row in self.records
                          if public.original_record(row)["schema_version"] == common.FORECAST_SCHEMA}, {14})

    def test_catalog_recovery_uses_a_new_bounded_reader_for_every_shard(self):
        from multisport_lab import sdv_production_archive as archive_module
        from multisport_lab import sdv_production_runner as runner
        readers, observations = [], []
        class Reader:
            def __init__(self): self.requests = 0
            def request_metrics(self): return {"public_http_requests": self.requests, "gh_api_actions": 0}
        class Archive:
            def fresh_reader(self):
                reader = Reader(); readers.append(reader); return reader
        class Store:
            def __init__(store):
                store.rows = [(LedgerRef.from_record(row["reference"]), public.original_record(row))
                              for row in self.records]
            def recover(store):
                return {"records": store.rows, "admissions": {
                    LedgerRef.from_record(row["reference"]).record_id: row["admission"]
                    for row in self.records}}
        def recover(ref, reader, destination, **kwargs):
            reader.requests += 1
            if reader.requests > 1:
                raise IntegrityError("Invented per-reader action guard exhausted")
            return Store()
        registry = runner.empty_registry(self.now)
        shards = [{"snapshot_ref": {"bytes": 10, "name": "object-"+seed*64+".z",
                    "sha256": seed*64, "tag": "nml-nba-records-v1-202610"},
                   "branch": "invented-read-scope-"+seed} for seed in ("a", "b", "c")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/"production").mkdir()
            (root/public.STATE_PATH).write_bytes(canonical({
                "schema_version": "nba-sdv-production-prepared-publication-v1",
                "registry": registry, "shards": shards, "archived_days": []}))
            with patch.object(public, "_state_parts", return_value=(shards, [])), \
                 patch.object(archive_module, "recover_snapshot", side_effect=recover):
                descriptor = public.emit_publication(root/"site/data", root, now=self.now,
                    allow_development=True, archive=Archive(), recovery_observer=observations.append)
            verified = public.read_publication(root/"site/data", descriptor,
                                               now=self.now, allow_development=True)
            original = (root/"site/data"/descriptor["path"]).read_bytes()
            failures = []
            def over_budget(ref, reader, destination, **kwargs):
                store = recover(ref, reader, destination, **kwargs)
                if ref == shards[1]["snapshot_ref"]:
                    reader.requests += 1
                    raise IntegrityError("Invented per-reader action guard exhausted")
                return store
            with patch.object(public, "_state_parts", return_value=(shards, [])), \
                 patch.object(archive_module, "recover_snapshot", side_effect=over_budget):
                with self.assertRaisesRegex(IntegrityError, "per-reader action guard"):
                    public.emit_publication(root/"site/data", root, now=self.now,
                        allow_development=True, archive=Archive(), recovery_observer=failures.append)
            self.assertEqual((root/"site/data"/descriptor["path"]).read_bytes(), original)
        self.assertEqual(len(readers), 5)
        self.assertEqual([reader.requests for reader in readers], [1, 1, 1, 1, 2])
        self.assertEqual([row["branch"] for row in observations], [row["branch"] for row in shards])
        self.assertEqual(sum(row["transport"]["public_http_requests"] for row in observations), 3)
        self.assertEqual(sum(row["transport"]["public_http_requests"] for row in failures), 3)
        self.assertEqual(verified["index"]["counts"]["development_forecasts"], 2)
        self.assertEqual(verified["index"]["counts"]["genuine_forecasts"], 0)

    def test_complete_page_bytes_hash_readback_and_explicit_preview_gate(self):
        index, pages = self.emit()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = canonical(index); sha = hashlib.sha256(raw).hexdigest()
            descriptor = {"path": "sdv-production."+sha+".json", "sha256": sha,
                          "generated_at": index["generated_at"], "status": public.STATUS, "retained": False, "error": None}
            (root/descriptor["path"]).write_bytes(raw)
            for ref, page in zip(index["pages"], pages):
                (root/ref["path"]).write_bytes(canonical(page))
            with self.assertRaisesRegex(IntegrityError, "Development records"):
                public.read_publication(root, descriptor, now=self.now)
            recovered = public.read_publication(root, descriptor, now=self.now, allow_development=True)
            self.assertEqual(recovered["records"], [row for page in pages for row in page["records"]])
            (root/index["pages"][0]["path"]).write_bytes(canonical(pages[0])+b" ")
            with self.assertRaisesRegex(IntegrityError, "hash/bytes"):
                public.read_publication(root, descriptor, now=self.now, allow_development=True)

    def test_conflicting_duplicate_admission_and_original_reference_reject(self):
        rows = deepcopy(self.records)
        duplicate = deepcopy(rows[-1])
        duplicate["reference"] = synthetic_ref("forecasts", "conflicting receipt").to_record()
        duplicate["admission"]["reasons"] = ["OTHER_FAILURE"]
        with self.assertRaisesRegex(IntegrityError, "duplicate public original/admission"):
            self.emit(records=[*rows, duplicate])
        body = public.original_record(rows[-1]); body["input_ref"] = synthetic_ref("input_captures", "wrong input").to_record()
        body = common.seal({k: v for k, v in body.items() if k != "forecast_id"}, "forecast_id")
        rows[-1] = public.project_original(synthetic_ref("forecasts", "wrong reference"), body, rows[-1]["admission"])
        with self.assertRaisesRegex(IntegrityError, "exact original input reference"):
            self.emit(records=rows)

    def test_ordinary_operating_status_never_claims_an_actual_scheduled_run(self):
        from multisport_lab import sdv_production_runner as runner
        from multisport_lab.sdv_production_archive import FileArchive
        index, _ = self.emit()
        self.assertEqual(index["operations"]["last_run_status"], "NOT_STARTED")
        self.assertIsNone(index["operations"]["last_run_at"])
        self.assertEqual(index["operations"]["next_check_basis"], "CONFIGURED_CRON_NOT_GUARANTEED")
        self.assertGreater(common.clock(index["operations"]["next_configured_check_at"]), self.now)
        self.assertEqual(public._next_check("2026-10-23T13:17:00.000000Z"),
                         "2026-10-23T13:32:00.000000Z")
        self.assertLess(common.clock(public._next_check("2026-10-23T13:17:00.000000Z")),
                        common.clock(index["policy"]["enabled_after"]))
        registry = {"registry_id": "a"*64, "updated_at": stamp(self.now), "status": "PARTIAL",
                    "last_run": {"run_id": 777, "observed_at": stamp(self.now), "status": "PARTIAL",
                                 "details": {"reason": "INCOMPLETE_OR_UNOBSERVED_WINDOW",
                                             "missing_preparations": 1, "partial_issuances": 2}}}
        retained = deepcopy(registry)
        operations = public.make_operations(registry, self.records, now=self.now)
        self.assertIn("window passed without a complete admitted cycle", operations["reason"])
        self.assertIn("missed forecasts are not backfilled", operations["reason"])
        self.assertEqual(operations["last_run_id"], 777)
        self.assertEqual(registry, retained)
        # Consume the actual current registry constructor and strict validator;
        # adding sealed internal capacity metadata must not alter the public
        # operations contract or require a source/network call.
        empty = runner.empty_registry(self.now)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = {"schema_version": "nba-sdv-production-prepared-publication-v1",
                     "registry": empty, "shards": [], "archived_days": []}
            (root/"production").mkdir()
            (root/public.STATE_PATH).write_bytes(canonical(state))
            descriptor = public.emit_publication(root/"site/data", root, now=self.now,
                                                 archive=FileArchive(root/"archive"))
            recovered = public.read_publication(root/"site/data", descriptor, now=self.now)
            self.assertEqual(recovered["index"]["operations"]["registry_id"], empty["registry_id"])
            self.assertEqual(recovered["index"]["counts"]["forecasts"], 0)
        bad = deepcopy(index); bad["operations"]["last_run_at"] = stamp(self.now+timedelta(seconds=1))
        bad = common.seal({k: v for k, v in bad.items() if k != "index_id"}, "index_id")
        with self.assertRaisesRegex(IntegrityError, "operating clock"):
            public.validate_index(bad, now=self.now)

    def test_checksum_consistent_outcome_with_wrong_subject_is_rejected(self):
        forecast = public.original_record(self.records[-1])
        body = {"schema_version": common.OUTCOME_SCHEMA, "protocol_id": common.PROTOCOL_ID,
                **{key: forecast[key] for key in forecasts.SUBJECT_FIELDS},
                "event_starts_at": forecast["event_starts_at"], "season_ending_year": 2027, "season_type": "2",
                "status": "UNRESOLVED", "source_archive_refs": [
                    {"tag": "diagnostics-nml-nba-test", "name": "object-"+seed*64+".z", "sha256": seed*64, "bytes": 10}
                    for seed in ("a", "b")], "source_observed_at": stamp(self.now), "normalized_at": stamp(self.now),
                "normalizer_version": forecasts.NORMALIZER_VERSION, "primitives": None, "minutes": None,
                "minutes_precision": None, "categories": [], "correction_revision": 1, "previous_outcome_id": None}
        body["player_id"] = "999999"
        body = common.seal(body, "outcome_id")
        with self.assertRaisesRegex(IntegrityError, "exact original subject"):
            self.emit(records=[*self.records, public.project_original(synthetic_ref("outcomes", "wrong subject"), body)])

    def test_delivery_identity_tracks_real_failures_and_windows_without_clock_only_redeploys(self):
        from multisport_lab import sdv_production_runner as runner
        original = runner.empty_registry(self.now)
        base = deepcopy(original)
        base["last_run"] = {"run_id": 777, "run_attempt": 1, "observed_at": stamp(self.now),
                            "status": "CATALOG_RECOVERED", "details": {"shards": 0}}
        before = public.publication_content_identity(base)
        tick = deepcopy(base)
        tick["updated_at"] = stamp(self.now+timedelta(seconds=1))
        tick["last_run"].update(run_id=778, run_attempt=2, observed_at=tick["updated_at"])
        self.assertEqual(public.publication_content_identity(tick), before)
        def attempt(at, state, source_ref=None):
            row = {"phase": "INPUT", "scope": ["invented-event"], "started_at": stamp(at),
                   "reserved_gets": 6, "used_gets": 4 if state == "CAPTURED" else None,
                   "status": state, "source_pack_ref": source_ref}
            row["attempt_id"] = digest({key: row[key] for key in ("phase", "scope", "started_at")})
            return row
        failed = deepcopy(base)
        failed["attempts"] = [attempt(self.now-timedelta(seconds=3), "FAILED")]
        failure = public.publication_content_identity(failed)
        self.assertTrue(failure["has_operational_failure"])
        self.assertNotEqual(failure["content_id"], before["content_id"])
        self.assertIn("source capture for pregame inputs failed", public.make_operations(failed, [], now=self.now)["reason"])
        novel = deepcopy(failed)
        novel["attempts"].append(attempt(self.now-timedelta(seconds=2), "FAILED"))
        self.assertNotEqual(public.publication_content_identity(novel)["content_id"], failure["content_id"])
        retry = deepcopy(novel)
        retry["attempts"].append(attempt(self.now-timedelta(seconds=1), "RESERVED"))
        self.assertEqual(public.publication_content_identity(retry), public.publication_content_identity(novel))
        recovered = deepcopy(retry)
        reference = {"tag": "nml-nba-records-v1-202610", "name": "object-"+"b"*64+".z", "sha256": "b"*64, "bytes": 20}
        recovered["attempts"][-1].update(status="CAPTURED", used_gets=4, source_pack_ref=reference)
        successful = public.publication_content_identity(recovered)
        self.assertFalse(successful["has_operational_failure"])
        self.assertNotEqual(successful["content_id"], failure["content_id"])
        missed = deepcopy(recovered)
        missed["last_run"]["details"] = {"reason": "INCOMPLETE_OR_UNOBSERVED_WINDOW",
                                         "missed_planning_dates": 1, "affected_game_dates": ["2026-10-24"]}
        self.assertTrue(public.publication_content_identity(missed)["has_operational_failure"])
        self.assertNotEqual(public.publication_content_identity(missed)["content_id"], successful["content_id"])
        hosted = deepcopy(base)
        hosted["last_run"]["details"] = {"failures": [{"name": "Shard preparation", "conclusion": "failure", "run_id": 777}]}
        self.assertTrue(public.publication_content_identity(hosted)["has_operational_failure"])
        self.assertIn("hosted preparation", public.make_operations(hosted, [], now=self.now)["reason"])
        observed = deepcopy(hosted)
        observed["last_run"]["details"]["failures"][0]["run_id"] = 999
        self.assertEqual(public.publication_content_identity(hosted), public.publication_content_identity(observed))
        self.assertEqual(original, runner.empty_registry(self.now))

    def test_pages_pack_complete_originals_and_reject_total_budget_exhaustion(self):
        biggest = max(len(canonical(row)) for row in self.records)
        with patch.object(public, "MAX_ASSET_BYTES", biggest+512):
            index, pages = self.emit()
            self.assertGreater(len(pages), 1)
            self.assertEqual(sum(len(page["records"]) for page in pages), len(self.records))
        with patch.object(public, "MAX_TOTAL_BYTES", 1):
            with self.assertRaisesRegex(IntegrityError, "projection exceeds"):
                self.emit()

    def test_issuance_attempt_originals_are_typed_linked_and_never_forecast_counts(self):
        from multisport_lab import sdv_production_runner as runner
        normalized = next(public.original_record(row) for row in self.records
                          if public.original_record(row)["schema_version"] == common.INPUT_SCHEMA)
        baseline = deepcopy(self.records)
        opened_at, closed_at, later = (self.now+timedelta(seconds=value) for value in (1, 2, 4))
        details = {"task_id": digest({"invented_guard_task": 0}), "shard_index": 0,
                   "player_ids": normalized["shards"][0], "error": None,
                   "final_source_pack_ref": None, "processing_complete": False}
        attempt = {"attempt_number": 1, "run_attempt": 1, "opened_at": stamp(opened_at), "open_status_id": None,
                   "footprint_snapshot_ref": None, "footprint_snapshot_id": None, "footprint_recovered_at": None}
        def identity(item, detail):
            return digest({key: detail[key] for key in ("task_id", "shard_index", "player_ids")} |
                          {"run_id": 0, **{key: item[key] for key in ("run_attempt", "opened_at", "attempt_number")}})
        attempt["attempt_id"] = identity(attempt, details)
        details["issuance_attempt"] = attempt
        opened = common.seal({"schema_version": common.STATUS_SCHEMA, "protocol_id": common.PROTOCOL_ID,
            "plan_id": normalized["plan_id"], "cycle_id": normalized["cycle_id"], "phase": "ISSUE",
            "status": runner.ISSUE_OPEN, "details": details, "observed_at": stamp(opened_at), "run_id": 0}, "status_id")
        closed = deepcopy(opened); closed.pop("status_id")
        closed.update(status=runner.ISSUE_CLOSED, observed_at=stamp(closed_at))
        reference = {"tag": "nml-nba-records-v1-202610", "name": "object-"+"b"*64+".z", "sha256": "b"*64, "bytes": 20}
        closed["details"]["issuance_attempt"].update(open_status_id=opened["status_id"],
            footprint_snapshot_ref=reference, footprint_snapshot_id="c"*64, footprint_recovered_at=stamp(closed_at))
        closed = common.seal(closed, "status_id")
        def row(body):
            return public.project_original(synthetic_ref("input_captures", body["status_id"]), body)
        def emit(guards):
            return public.make_publication([*self.records, *(row(body) for body in guards)], now=later,
                                           allow_development=True)
        with patch.object(common, "now", return_value=later):
            for guards in ([opened], [opened, closed]):
                index, _ = emit(guards)
                self.assertEqual(index["counts"]["forecasts"], 2)
                self.assertEqual(index["counts"]["genuine_forecasts"], 0)
            for change in ("missing_open", "foreign_open", "late_footprint", "foreign_cohort", "attempt_hash", "duplicate_close"):
                invalid = deepcopy(closed); invalid.pop("status_id")
                if change == "foreign_open": invalid["details"]["issuance_attempt"]["open_status_id"] = "a"*64
                elif change == "late_footprint": invalid["details"]["issuance_attempt"]["footprint_recovered_at"] = stamp(later)
                elif change == "foreign_cohort":
                    invalid["details"]["player_ids"] = ["999999"]
                    invalid["details"]["issuance_attempt"]["attempt_id"] = identity(invalid["details"]["issuance_attempt"], invalid["details"])
                elif change == "attempt_hash": invalid["details"]["issuance_attempt"]["attempt_id"] = "a"*64
                elif change == "duplicate_close": invalid["observed_at"] = stamp(closed_at+timedelta(seconds=1))
                invalid = common.seal(invalid, "status_id")
                guards = [invalid] if change == "missing_open" else [opened, invalid]
                if change == "duplicate_close": guards.append(closed)
                with self.assertRaises(IntegrityError, msg=change): emit(guards)
        self.assertEqual(self.records, baseline)

    def test_authentication_event_string_is_shared_without_losing_original_bytes(self):
        from multisport_lab import sdv_production_runner as runner
        binding = public.original_record(self.records[-1])["producer_binding"]
        event = {"repository": {"full_name": common.REPOSITORY}, "schedule": common.CRON}
        run = {"id": 777, "run_attempt": 1, "event": "schedule", "head_sha": "a"*40,
               "head_branch": "main", "path": common.WORKFLOW, "status": "in_progress", "conclusion": None,
               "repository": {"full_name": common.REPOSITORY}, "actor": {"login": common.OWNER},
               "triggering_actor": {"login": common.OWNER},
               "run_started_at": stamp(self.now-timedelta(seconds=1))}
        auth = common.seal({"schema_version": common.AUTH_SCHEMA, "protocol_id": common.PROTOCOL_ID,
            "repository": common.REPOSITORY, "workflow_path": common.WORKFLOW, "event": "schedule", "actor": common.OWNER,
            "run_id": 777, "run_attempt": 1, "head_sha": "a"*40, "run_started_at": run["run_started_at"],
            "verified_at": stamp(self.now), "event_original": runner._encoded(canonical(event)),
            "run_original": runner._encoded(canonical(run)), "executed_files": binding["files"]}, "authorization_id")
        row = public.project_original(synthetic_ref("input_captures", "invented authority"), auth)
        original = row["record_json"]
        index, pages = self.emit(records=[*self.records, row])
        self.assertEqual(index["dates"][0]["game_date"], "2026-10-24")
        self.assertTrue(all(page["game_date"] == "2026-10-24" for page in pages))
        self.assertIn(original, [item["record_json"] for page in pages for item in page["records"]])
        self.assertEqual(index["counts"]["genuine_forecasts"], 0)

    def test_completed_later_correction_gap_survives_a_newer_failed_run(self):
        forecast = public.original_record(self.records[-1])
        normalized = next(public.original_record(row) for row in self.records
                          if public.original_record(row)["schema_version"] == common.INPUT_SCHEMA)
        def status(at, *, completed, flagged, shard_index=0):
            body = common.seal({"schema_version": common.STATUS_SCHEMA, "protocol_id": common.PROTOCOL_ID,
                "plan_id": forecast["plan_id"], "cycle_id": forecast["cycle_id"], "phase": "GRADE",
                "status": "STATISTICAL_GRADING_RETAINED" if completed else "FAILED_OR_PARTIAL",
                "details": {"task_id": digest({"invented_task": shard_index}), "shard_index": shard_index,
                    "player_ids": normalized["shards"][shard_index],
                    "processing_complete": completed, "grading": {"outcomes": 1, "grades": 2,
                    "pending": [], "correction_quota_exhausted": [forecast["player_id"]] if flagged else [],
                    "unscored_originals": [], "unscored_reason": "ORIGINAL_NOT_TIMELY_ADMITTED"}},
                "observed_at": stamp(at), "run_id": 777}, "status_id")
            return public.project_original(synthetic_ref("input_captures", body["status_id"]), body)
        old = status(self.now, completed=True, flagged=True)
        index, _ = self.emit(records=[*self.records, old])
        self.assertEqual(index["counts"]["genuine_forecasts"], 0)
        self.assertEqual(index["counts"]["active_grades"], 0)
        failed = status(self.now+timedelta(seconds=1), completed=False, flagged=False)
        rows = [*self.records, old, failed]
        self.assertEqual(set(public.unresolved_grading(rows).values()), {"UNRESOLVED_LATER_CORRECTION"})
        self.assertEqual(len(public.unresolved_grading(rows)), 2)
        other_shard = status(self.now+timedelta(seconds=1), completed=True, flagged=False, shard_index=1)
        self.assertEqual(public.unresolved_grading([*rows, other_shard]), public.unresolved_grading(rows))
        pending = public.original_record(old)
        pending["details"]["grading"].update(pending=[forecast["player_id"]], correction_quota_exhausted=[])
        pending = common.seal({key: value for key, value in pending.items() if key != "status_id"}, "status_id")
        pending_row = public.project_original(synthetic_ref("input_captures", "pending shard zero"), pending)
        self.assertEqual(set(public.unresolved_grading([*self.records, pending_row, other_shard]).values()),
                         {"PENDING_FINAL_EVIDENCE"})
        confirmed = status(self.now+timedelta(seconds=2), completed=True, flagged=False)
        self.assertEqual(public.unresolved_grading([*rows, confirmed]), {})
        invalid = public.original_record(old)
        invalid["details"]["grading"]["unscored_originals"] = [forecast["player_id"]+":UNKNOWN"]
        invalid = common.seal({key: value for key, value in invalid.items() if key != "status_id"}, "status_id")
        invalid_row = public.project_original(synthetic_ref("input_captures", "invalid unscored model"), invalid)
        with self.assertRaisesRegex(IntegrityError, "unscored original"):
            self.emit(records=[*self.records, invalid_row])
        for change in ("foreign_player", "foreign_task", "foreign_cycle", "foreign_shard"):
            body = public.original_record(old)
            if change == "foreign_player": body["details"]["player_ids"] = ["999999"]
            elif change == "foreign_task": body["details"]["task_id"] = "not-an-original-task"
            elif change == "foreign_cycle": body["cycle_id"] = "prod-20990101-999-aaaaaaaaaaaa"
            else: body["details"]["shard_index"] = 3
            body = common.seal({key: value for key, value in body.items() if key != "status_id"}, "status_id")
            with self.assertRaises(IntegrityError, msg=change):
                self.emit(records=[*self.records, public.project_original(
                    synthetic_ref("input_captures", change), body)])


if __name__ == "__main__":
    unittest.main()

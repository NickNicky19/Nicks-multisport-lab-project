"""Full typed publication replay with explicit synthetic prospective wire data.

No producer is activated or fitted. Invented clocks, CSVs, probabilities and
dispatch evidence live only in a temporary local bare Git repository. The real
parent receipts/source bytes are copied read-only to test the publication trust
boundary; these fixture records must never be pushed to GitHub or called genuine
operating evidence. Clocks and the explicitly synthetic producer/material trust
fixture are patched; source semantics, ledger validation and Git recovery run.
"""
from contextlib import ExitStack
from copy import deepcopy
from datetime import timedelta
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from multisport_lab import ledger, sdv_daily_cycle as cycles
from multisport_lab import sdv_daily_inputs as inputs
from multisport_lab import sdv_daily_producer as producer
from multisport_lab import sdv_daily_publication as publication
from multisport_lab import sdv_daily_remote as remote
from multisport_lab import sdv_daily_store as storage
from multisport_lab import sdv_daily_grading as grading
from multisport_lab import sdv_daily_outcomes as outcomes
from multisport_lab import sdv_daily_runner as runner
from multisport_lab import publication as site_publication
from multisport_lab.integrity import IntegrityError, canonical, digest, load_json, read_receipt, stamp, utc
from multisport_lab.ledger import LedgerRef
from test_sdv_daily_cycle import proof
from test_sdv_daily_inputs import csv_bytes, fixtures, metadata


ROOT = Path(__file__).resolve().parents[1]
NORMALIZED = utc("2026-10-22T23:30:00.000000Z")
ISSUED = utc("2026-10-23T00:00:10.000000Z")


class DailyFullTypedImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nml-typed-synthetic-only-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.state, self.root = self.folder / "state", self.folder / "release"
        self.state.mkdir(); self.root.mkdir()
        self.now = NORMALIZED
        stack = ExitStack(); self.addCleanup(stack.close)
        for module in (cycles, inputs, producer, storage, ledger, remote, grading, outcomes, runner):
            stack.enter_context(patch.object(module, "_now", side_effect=lambda: self.now))
        current_binding = producer.make_source_binding()
        self.cycle = cycles.load_cycle()
        self.branch = self.cycle["records_branch"]
        for destination in (self.state, self.root):
            shutil.copytree(ROOT / "records", destination / "records")
        # CI checks out a depth-one synthetic merge. Bare-cloning that checkout
        # would also create a shallow server: an ordinary fetch can return zero
        # while rejecting its shallow root and leaving FETCH_HEAD empty. Seed a
        # complete, one-commit SOFTWARE FIXTURE instead. Its source bytes and all
        # original receipts (including records/README.md) remain exact copies.
        # This synthetic commit is not an approved operating producer revision.
        seed = self.folder / "synthetic-source"
        seed.mkdir()
        shutil.copytree(ROOT / "records", seed / "records")
        for filename in producer.SOURCE_FILES:
            raw = (ROOT / filename).read_bytes()
            for destination in (self.root, seed):
                target = destination / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
        self.git("init", "--quiet", cwd=seed)
        self.git("add", "--all", cwd=seed)
        self.git("-c", "user.name=Synthetic Typed Import Test",
            "-c", "user.email=software-fixture@example.invalid", "commit", "--quiet",
            "-m", "Complete synthetic source fixture with exact current bytes", cwd=seed)
        self.source_commit = self.git("rev-parse", "HEAD", cwd=seed).stdout.strip()
        self.binding = producer.make_source_binding(self.source_commit, root=seed)
        self.assertEqual(self.binding["files"], current_binding["files"])
        self.assertEqual(self.git("rev-parse", "--is-shallow-repository", cwd=seed).stdout.strip(), "false")
        self.originals = self.inventory(self.root / "records")
        self.remote = self.folder / "local-only.git"
        # --no-hardlinks supplies an independent object database, without HTTP.
        self.git("clone", "--bare", "--no-hardlinks", "--quiet", str(seed), str(self.remote), cwd=self.folder)
        self.store = storage.DailyStore(self.state)
        self.writer = remote.DailyGitCheckpointWriter(self.state, self.folder / "writer",
            base_commit=self.source_commit, branch=self.branch, remote_url=str(self.remote),
            allow_local_test_remote=True)
        self.writer.prepare()
        self.input_ref, self.input = self.make_input()
        self.store.record_completion(self.input_ref, started_at=self.now)
        self.writer.checkpoint(self.input_ref)
        self.auth = proof(self.cycle, self.binding)  # Invented software proof, never live authority.
        self.store.append_body("input_captures", self.cycle)
        self.auth_ref = self.store.append_body("input_captures", self.auth)
        payload = read_receipt(self.state / "records/research_inputs" / (producer.HISTORY_ID + ".json"))
        history_ref = LedgerRef("research_inputs", producer.HISTORY_ID, digest(payload))
        self.intent = producer.seal({"schema_version": producer.INTENT_SCHEMA,
            "protocol_id": inputs.PROTOCOL_ID, "cycle_id": self.cycle["cycle_id"],
            "mode": "PROSPECTIVE_RESEARCH", "input_ref": self.input_ref.to_record(),
            "input_id": self.input["input_id"], "producer_binding_id": self.binding["binding_id"],
            "history_ref": history_ref.to_record(), "created_at": "2026-10-22T23:30:00.000000Z"}, "intent_id")
        cycle_ref = self.store.append_body("input_captures", self.cycle)
        self.intent_ref = self.store.append_body("input_captures", self.intent,
            references=(self.input_ref, cycle_ref, self.auth_ref))
        self.store.record_completion(self.intent_ref, started_at=self.now)
        self.writer.checkpoint(self.intent_ref)
        self.now = ISSUED
        fixture = load_json(ROOT / "tests/fixtures/sdv-daily-synthetic.json")
        self.forecast_refs = []
        for entry in fixture["forecasts"][:2]:
            body = deepcopy(entry["body"])
            body.update(mode="PROSPECTIVE_RESEARCH", evidence_lane="DAILY_SNAPSHOT_PROSPECTIVE",
                producer_binding=self.binding, history_ref=history_ref.to_record(),
                input_ref=self.input_ref.to_record(), input_id=self.input["input_id"],
                event_snapshot_id=self.input["event"]["event_snapshot_id"],
                matchup=self.input["event"]["away_team_name"] + " @ " + self.input["event"]["home_team_name"],
                generation_started_at="2026-10-23T00:00:01.000000Z",
                generation_completed_at="2026-10-23T00:00:02.000000Z",
                verified_at="2026-10-23T00:00:03.000000Z", issued_at="2026-10-23T00:00:03.000000Z")
            body = producer.seal({key: value for key, value in body.items() if key != "forecast_id"}, "forecast_id")
            references = (self.input_ref, self.intent_ref)
            # Explicit fixture insertion, not the authenticated issuance entrypoint.
            with self.store._verified_forecast_write(body, references):
                ref = self.store.append_body("forecasts", body, references=references)
            self.store.record_completion(ref, started_at=utc(body["generation_started_at"]))
            self.forecast_refs.append(ref)
        result = self.writer.checkpoint(tuple(self.forecast_refs))
        self.head = result["commit"]

    @staticmethod
    def inventory(root):
        return {path.relative_to(root): path.read_bytes() for path in root.rglob("*.json")}

    @staticmethod
    def git(*args, cwd):
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
            text=True, timeout=60)

    def make_input(self):
        _, _, schedules, _, _ = fixtures()
        row = schedules[0]
        event = self.cycle["event"]
        row.update(id=event["event_id"], game_id=event["event_id"],
            uid="s:40~l:46~e:" + event["event_id"] + "~c:" + event["event_id"],
            date=event["event_starts_at"], start_date=event["event_starts_at"],
            game_date_time=event["event_starts_at"])
        rosters = [{"season": "2027", "athlete_id": candidate["player_id"],
            "uid": "s:40~l:46~a:" + candidate["player_id"], "team_id": candidate["team_id"],
            "team_display_name": "Synthetic Home" if candidate["team_id"] == "25" else "Synthetic Away",
            "display_name": candidate["player_label"], "status_type": "active", "status_name": "Active",
            "status_id": "1"} for candidate in self.cycle["candidates"]]
        retained = []
        for role, raw in (("schedule", csv_bytes(schedules)), ("roster", csv_bytes(rosters))):
            meta = metadata(raw, role, NORMALIZED)
            original = canonical({"tag_name": meta["release_tag"], "assets": [{
                "id": meta["asset_id"], "name": meta["asset_name"], "size": len(raw),
                "browser_download_url": meta["asset_url"], "digest": "sha256:" + meta["asset_sha256"],
                "updated_at": meta["publisher_updated_at"]}]})
            meta.update(metadata_sha256=hashlib.sha256(original).hexdigest(), metadata_bytes=len(original))
            retained.append((raw, meta, original))
        body = inputs.normalize_inputs(retained[0][0], retained[1][0], retained[0][1], retained[1][1],
            event_id=event["event_id"], expected_candidates=self.cycle["candidates"], mode="PROSPECTIVE_RESEARCH")
        refs = [self.store.retain_asset(*source) for source in retained]
        return self.store.persist_input(body, refs), body

    def test_real_typed_validator_and_independent_local_import_accept_synthetic_partial_pair(self):
        self.assertEqual(self.store.recover()["genuine_issued"], 2)  # Fixture clocks only.
        # The exact-code rejection and positive recovery share one bounded fixture;
        # this avoids constructing/checkpointing the same synthetic cohort twice.
        target = self.root / "multisport_lab/sdv_daily_inputs.py"
        source = target.read_bytes()
        target.write_bytes(source + b"\n# synthetic different release\n")
        with patch.object(publication, "REMOTE_URL", str(self.remote)), self.assertRaisesRegex(IntegrityError, "Current release differs"):
            publication.prepare_published_records(self.root, self.head, now=self.now)
        self.assertFalse((self.root / "daily/records").exists())
        self.assertEqual(self.inventory(self.root / "records"), self.originals)
        target.write_bytes(source)
        with patch.object(publication, "REMOTE_URL", str(self.remote)):
            result = publication.prepare_published_records(self.root, self.head, now=self.now)
        self.assertEqual(result["status"], "IMPORTED")
        self.assertEqual(result["eligible_forecasts"], 2)
        asset = publication.make_asset(self.root, now=self.now)
        self.assertEqual(asset["status"], "PARTIAL")
        self.assertEqual(asset["counts"]["genuine_forecasts"], 2)
        self.assertEqual(asset["counts"]["pending_grades"], 2)
        self.assertEqual({len(row["body"]["categories"]) for row in asset["forecasts"]}, {14})
        self.assertEqual(self.inventory(self.root / "records"), self.originals)
        self.assertEqual(self.inventory(self.root / "daily/records"), self.inventory(self.state / "daily/records"))

        # Continue this same pair/history fixture through the actual final-source
        # path. All CSV rows, publisher JSON, requests and clocks below are
        # INVENTED SOFTWARE INPUTS, never real player results or source captures.
        # The one trusted-material boundary is explicit because this complete
        # synthetic producer commit is deliberately not the approved live SHA.
        config = deepcopy(load_json(ROOT / grading.DEFAULT_CONFIG_PATH))
        review = deepcopy(load_json(ROOT / config["source_review_receipt_path"]))
        review["payload"]["software_fixture_only"] = (
            "Invented CSV/request evidence for typed grading and Git recovery; "
            "not provider observation, operating approval or real forecast results.")
        review["payload_sha256"] = digest(review["payload"])
        review_raw = canonical(review)
        config.update(supported_producer_commit=self.source_commit,
            source_review_receipt_sha256=hashlib.sha256(review_raw).hexdigest(),
            source_review_payload_sha256=review["payload_sha256"])
        config["attribution"].append("SOFTWARE FIXTURE ONLY: all final rows and source requests are invented.")
        config = grading.sealed({key: value for key, value in config.items() if key != "config_id"}, "config_id")
        config_raw = canonical(config)

        def synthetic_trusted_materials(commit=None):
            self.assertIn(commit, (None, self.source_commit))
            grading.validate_config(config)
            grading._review(review_raw, config)
            return deepcopy(config), config_raw, review_raw, self.source_commit

        original_forecasts = {ref: (self.state / "daily/records/forecasts" / (ref.record_id + ".json")).read_bytes()
                              for ref in self.forecast_refs}
        originals = [self.store.ledger.read(ref)["data"]["daily"] for ref in self.forecast_refs]
        self.assertEqual(len({row["player_id"] for row in originals}), 1)
        self.assertEqual({row["model_key"] for row in originals}, {"R0", "K0"})
        forecast = originals[0]
        self.now = utc("2026-10-24T12:00:00.000000Z")
        event = {key: "" for key in config["roles"]["schedule"]["required_headers"]}
        event.update(game_id=forecast["event_id"], home_id="25", away_id="7", season="2027", season_type="2",
            game_date_time=forecast["event_starts_at"], status_type_completed="true", status_type_name="STATUS_FINAL",
            status_type_state="post", home_score="12", away_score="11")

        def final_line(player_id, team_id, opponent_id):
            points = 12 if team_id == "25" else 11
            line = {key: "" for key in config["roles"]["boxscore"]["required_headers"]}
            line.update(game_id=forecast["event_id"], athlete_id=player_id, team_id=team_id,
                opponent_team_id=opponent_id, season="2027", season_type="2", game_date="2026-10-23",
                game_date_time=forecast["event_starts_at"], athlete_display_name=(forecast["player_label"]
                    if player_id == forecast["player_id"] else "Synthetic opposing player"),
                did_not_play="false", active="true", starter="false", ejected="false", minutes="20.0",
                field_goals_made="4", field_goals_attempted="10", three_point_field_goals_made="2",
                three_point_field_goals_attempted="5", free_throws_made=str(points - 10),
                free_throws_attempted=str(points - 10), points=str(points), offensive_rebounds="1",
                defensive_rebounds="3", rebounds="4", assists="3", steals="1", blocks="0", turnovers="1",
                fouls="0", plus_minus="1" if team_id == "25" else "-1",
                home_away="home" if team_id == "25" else "away", team_winner="true" if team_id == "25" else "false",
                team_score=str(points), opponent_team_score="11" if team_id == "25" else "12")
            return line

        lines = [final_line(forecast["player_id"], forecast["team_id"], forecast["opponent_id"]),
                 final_line("9000001", forecast["opponent_id"], forecast["team_id"])]
        self.assertEqual(len(lines[0]), 57)
        captures, requests = [], []
        for index, (role, rows) in enumerate((("schedule", [event]), ("boxscore", lines))):
            rule = config["roles"][role]
            raw = csv_bytes(rows)
            publisher_raw = canonical({"tag_name": rule["release_tag"], "assets": [{"id": 90001 + index,
                "name": rule["asset_name"], "size": len(raw), "browser_download_url": rule["asset_url"],
                "digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "updated_at": "2026-10-23T04:00:00.000000Z"}]})
            start = self.now - timedelta(seconds=8 - 4 * index)
            clocks = {key: stamp(start + timedelta(seconds=offset)) for offset, key in enumerate((
                "metadata_retrieval_started_at", "metadata_retrieved_at", "asset_retrieval_started_at", "asset_retrieved_at"))}
            captures.append((raw, publisher_raw, clocks))
            for label, url, body, first, last, limit in (
                    (role + "_metadata", rule["metadata_url"], publisher_raw, start, start + timedelta(seconds=1), config["max_metadata_bytes"]),
                    (role + "_asset", rule["asset_url"], raw, start + timedelta(seconds=2), start + timedelta(seconds=3), rule["max_asset_bytes"])):
                requests.append({"request_number": len(requests) + 1, "label": label, "route": url,
                    "retrieval_started_at": stamp(first), "response_limit_bytes": limit,
                    "automatic_redirects": False, "automatic_retries": 0, "status": 200,
                    "retrieved_at": stamp(last), "response_read_completed_at": stamp(last),
                    "bytes": len(body), "bytes_read": len(body), "response_exceeded_limit": False,
                    "sha256": hashlib.sha256(body).hexdigest()})
        self.assertEqual(len(requests), 4)  # Only invented rows; no HTTP client is invoked.
        timings = {}
        with patch.object(grading, "FIRST_PRODUCER", self.source_commit), \
                patch.object(grading, "_trusted_materials", side_effect=synthetic_trusted_materials):
            started = time.perf_counter()
            source_refs = grading.retain_source_with_proof(self.store, self.forecast_refs,
                schedule=captures[0], boxscore=captures[1], requests=requests)
            timings["retain_source_seconds"] = time.perf_counter() - started
            started = time.perf_counter()
            graded = grading.normalize_and_grade(self.store, self.forecast_refs, *source_refs)
            timings["normalize_and_grade_seconds"] = time.perf_counter() - started
            self.assertEqual(len(graded["outcomes"]), 1)
            self.assertEqual(len(graded["grades"]), 2)
            self.assertEqual(graded["pending"], [])
            self.assertEqual(graded["corrections"], [])
            for ref in self.forecast_refs:
                self.assertEqual((self.state / "daily/records/forecasts" / (ref.record_id + ".json")).read_bytes(), original_forecasts[ref])

            # The real writer persists all proof/CSV/outcome/grade originals and
            # independently fetches them. No semantic validator/store is mocked.
            started = time.perf_counter()
            try:
                flushed = self.writer.flush()
            finally:
                timings["grading_flush_seconds"] = time.perf_counter() - started
                print("SYNTHETIC grading integration timings (no source/model execution):", timings, flush=True)
            self.assertLessEqual(timings["grading_flush_seconds"], remote.MAX_COMMAND_SECONDS)
            started = time.perf_counter()
            with patch.object(publication, "REMOTE_URL", str(self.remote)):
                imported = publication.prepare_published_records(self.root, flushed["commit"], now=self.now)
            timings["fresh_publication_import_seconds"] = time.perf_counter() - started
            self.assertEqual(imported["eligible_forecasts"], 2)
            recovered = storage.DailyStore(self.root)
            admissions = grading.validate_stored_admissions(recovered)
            self.assertEqual((admissions["genuine_outcomes"], admissions["genuine_grades"]), (1, 2))

            # Exercise the actual independently admitted publication branch,
            # alongside the unchanged historical sport collection. Other optional
            # source channels may remain unavailable in this compact test root.
            shutil.copytree(ROOT / "web", self.root / "web")
            for filename in ("config/capabilities.json", "config/nba_markets.json"):
                target = self.root / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / filename).read_bytes())
            started = time.perf_counter()
            manifest = site_publication.build_site(self.root, self.folder / "graded-public-preview",
                build_commit=self.source_commit, now=self.now)
            timings["graded_publication_build_seconds"] = time.perf_counter() - started
            self.assertIsNone(manifest["daily_research_error"])
            self.assertIsNotNone(manifest["daily_research"])
            public = load_json(self.folder / "graded-public-preview/data" / manifest["daily_research"]["path"])
            publication.validate_asset(public, now=self.now)
            self.assertEqual(len(public["outcomes"]), 1)
            self.assertEqual(len(public["grades"]), 2)
            self.assertEqual(public["counts"]["pending_grades"], 0)
            self.assertEqual({row["body"]["status"] for row in public["grades"]}, {"SCORED"})
            self.assertEqual({len(row["body"]["categories"]) for row in public["grades"]}, {14})
            self.assertEqual({row["body"]["outcome_id"] for row in public["grades"]},
                             {public["outcomes"][0]["body"]["outcome_id"]})
            self.assertEqual({row["body"]["forecast_id"] for row in public["grades"]},
                             {body["forecast_id"] for body in originals})
            historical = load_json(self.folder / "graded-public-preview/data" / manifest["sports"][0]["path"])
            self.assertEqual((len(historical["forecasts"]), len(historical["performance"])), (6, 6))
            self.assertEqual(self.inventory(self.root / "records"), self.originals)

            # Restart with an independent store, then retry the SAME retained
            # capture at a later test clock. No new issuance, outcome, proof,
            # grade timestamp or receipt may be minted by successful recovery.
            before_retry = self.inventory(self.root / "daily/records")
            self.now += timedelta(seconds=30)
            restarted = storage.DailyStore(self.root)
            same_sources = grading.retain_source_with_proof(restarted, self.forecast_refs,
                schedule=captures[0], boxscore=captures[1], requests=requests)
            repeated = grading.normalize_and_grade(restarted, self.forecast_refs, *same_sources)
            self.assertEqual(same_sources, source_refs)
            self.assertEqual(repeated["outcomes"], graded["outcomes"])
            self.assertEqual(repeated["grades"], graded["grades"])
            self.assertEqual(self.inventory(self.root / "daily/records"), before_retry)
            self.assertEqual(self.inventory(self.root / "records"), self.originals)
            for ref in self.forecast_refs:
                self.assertEqual((self.root / "daily/records/forecasts" / (ref.record_id + ".json")).read_bytes(), original_forecasts[ref])
            print("SYNTHETIC complete grading/recovery/publication timings:", timings, flush=True)

if __name__ == "__main__":
    unittest.main()

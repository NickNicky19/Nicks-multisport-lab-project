"""Full typed publication replay with explicit synthetic prospective wire data.

No producer is activated or fitted. Invented clocks, CSVs, probabilities and
dispatch evidence live only in a temporary local bare Git repository. The real
parent receipts/source bytes are copied read-only to test the publication trust
boundary; these fixture records must never be pushed to GitHub or called genuine
operating evidence. Only private clock boundaries are patched.
"""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import ledger, sdv_daily_cycle as cycles
from multisport_lab import sdv_daily_inputs as inputs
from multisport_lab import sdv_daily_producer as producer
from multisport_lab import sdv_daily_publication as publication
from multisport_lab import sdv_daily_remote as remote
from multisport_lab import sdv_daily_store as storage
from multisport_lab.integrity import IntegrityError, canonical, digest, load_json, read_receipt, utc
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
        for module in (cycles, inputs, producer, storage, ledger, remote):
            stack.enter_context(patch.object(module, "_now", side_effect=lambda: self.now))
        self.source_commit = self.git("rev-parse", "HEAD", cwd=ROOT).stdout.strip()
        self.binding = producer.make_source_binding(self.source_commit)
        self.cycle = cycles.load_cycle()
        self.branch = self.cycle["records_branch"]
        for destination in (self.state, self.root):
            shutil.copytree(ROOT / "records", destination / "records")
        for filename in producer.SOURCE_FILES:
            target = self.root / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / filename).read_bytes())
        self.originals = self.inventory(self.root / "records")
        self.remote = self.folder / "local-only.git"
        # --no-hardlinks supplies an independent object database, without HTTP.
        self.git("clone", "--bare", "--no-hardlinks", "--quiet", str(ROOT), str(self.remote), cwd=self.folder)
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

if __name__ == "__main__":
    unittest.main()

"""Invented Pages archives; no provider requests, issuance or remote writes."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import restore_pages_artifact as restore
from multisport_lab import publication
from multisport_lab import sdv_production_common as common
from multisport_lab import sdv_production_forecasts as forecasts
from multisport_lab import sdv_production_publication as production
from multisport_lab.integrity import IntegrityError, canonical, digest, stamp
import test_sdv_production_store as store_fixtures

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "b"*40


def packed_files(files, *, extra=None):
    tar_body = io.BytesIO()
    with tarfile.open(fileobj=tar_body, mode="w") as archive:
        for name, raw in files.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(raw)
            archive.addfile(entry, io.BytesIO(raw))
        if extra is not None:
            archive.addfile(extra)
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("artifact.tar", tar_body.getvalue())
    return zipped.getvalue()


class FakeArtifacts:
    def __init__(self, candidates, *, now):
        self.candidates, self.now, self.downloaded = candidates, now, []

    def runs(self):
        return [{"id": number, "head_branch": "main", "path": restore.WORKFLOW,
                 "head_sha": COMMIT, "event": "workflow_dispatch", "status": "completed",
                 "conclusion": "success", "repository": {"full_name": restore.REPOSITORY},
                 "head_repository": {"full_name": restore.REPOSITORY},
                 "created_at": stamp(self.now-timedelta(minutes=number)),
                 "updated_at": stamp(self.now-timedelta(seconds=number))}
                for number, _ in self.candidates]

    def artifacts(self, run_id):
        packed = dict(self.candidates)[run_id]
        return [{"id": run_id+100, "name": "github-pages", "expired": False,
                 "size_in_bytes": len(packed), "digest": "sha256:"+hashlib.sha256(packed).hexdigest(),
                 "workflow_run": {"id": run_id, "head_sha": COMMIT}}]

    def download(self, artifact_id, target, maximum):
        packed = dict(self.candidates)[artifact_id-100]
        if len(packed) > maximum:
            raise IntegrityError("Invented download exceeds bound")
        self.downloaded.append(artifact_id)
        target.write_bytes(packed)
        return len(packed)


class RestorePagesArtifactTests(unittest.TestCase):
    def setUp(self):
        fixture = store_fixtures.ProductionStoreTests(
            "test_independent_archive_restart_keeps_exact_originals_and_all14_categories")
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        references, bodies = fixture.persisted_pair()
        fixture.fixture.now = fixture.start+timedelta(hours=4)
        outcome_ref, outcome = fixture.append_outcome(references)
        for reference, body in zip(references, bodies):
            fixture.store.append_body(forecasts.make_grade(body, outcome), references=(reference, outcome_ref))
        recovered = fixture.store.recover()
        rows = [production.project_original(ref, body,
            recovered["admissions"][ref.record_id] if body["schema_version"] == common.FORECAST_SCHEMA else None)
            for ref, body in recovered["records"] if body["schema_version"] in production.PUBLIC_SCHEMAS]
        self.generated = fixture.fixture.now
        self.now = self.generated+timedelta(hours=1)
        index, pages = production.make_publication(rows, now=self.generated)
        self.index = index
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            sport = publication.empty_nba(ROOT, now=self.generated)
            manifest = publication.publish(data, {"NBA": sport}, build_commit=COMMIT, now=self.generated)
            manifest["schema_version"] = 7
            for channel in publication.AUXILIARY_CHANNELS:
                manifest[channel] = None
                manifest[channel+"_error"] = "Explicitly absent from invented archive fixture."
            raw = canonical(index); sha = hashlib.sha256(raw).hexdigest()
            manifest["production_research"] = {"path": "sdv-production."+sha+".json", "sha256": sha,
                "generated_at": index["generated_at"], "status": production.STATUS, "retained": False, "error": None}
            manifest["production_research_error"] = None
            manifest["snapshot_id"] = digest({key: value for key, value in manifest.items() if key != "snapshot_id"})
            self.files = {"data/"+path.name: path.read_bytes() for path in data.iterdir() if path.name != "manifest.json"}
            self.files["data/manifest.json"] = canonical(manifest)
            self.files["data/"+manifest["production_research"]["path"]] = raw
            for ref, page in zip(index["pages"], pages):
                self.files["data/"+ref["path"]] = canonical(page)
        self.manifest = manifest

    def archived(self, files=None):
        return packed_files(self.files if files is None else files)

    def restore_to(self, folder, candidates):
        reader = FakeArtifacts(candidates, now=self.now)
        output = Path(folder)/"output"
        report = restore.restore(output, now=self.now, reader=reader)
        return output, report, reader

    def test_fresh_host_skips_null_latest_and_existing_builder_retains_exact_originals(self):
        null_files = deepcopy(self.files); manifest = deepcopy(self.manifest)
        manifest["production_research"] = None
        manifest["production_research_error"] = "Invented failed archive readback."
        manifest["snapshot_id"] = digest({key: value for key, value in manifest.items() if key != "snapshot_id"})
        null_files["data/manifest.json"] = canonical(manifest)
        with tempfile.TemporaryDirectory() as folder:
            output, report, reader = self.restore_to(folder, [(2, self.archived()), (1, self.archived(null_files))])
            self.assertEqual(report["status"], "RESTORED_VERIFIED_PRIOR_PRODUCTION")
            self.assertEqual(report["counts"]["genuine_forecasts"], 2)
            self.assertEqual(report["counts"]["outcomes"], 1)
            self.assertEqual(report["counts"]["grades"], 2)
            self.assertEqual(reader.downloaded, [101, 102])
            self.assertEqual((output/"data/manifest.json").read_bytes(), self.files["data/manifest.json"])
            original = self.manifest["production_research"]
            with patch.object(production, "emit_publication", side_effect=IntegrityError("Invented archive failure")):
                built = publication.build_site(ROOT, output, build_commit="c"*40, now=self.now)
            self.assertTrue(built["production_research"]["retained"])
            self.assertIsNotNone(built["production_research_error"])
            self.assertEqual(built["production_research"]["generated_at"], original["generated_at"])
            self.assertEqual(built["published_at"], stamp(self.now))
            for name in [original["path"], *(ref["path"] for ref in self.index["pages"])]:
                self.assertEqual((output/"data"/name).read_bytes(), self.files["data/"+name])

    def test_hash_corrupt_and_checksum_consistent_semantically_invalid_candidates_reject(self):
        for semantic in (False, True):
            with self.subTest(semantic=semantic), tempfile.TemporaryDirectory() as folder:
                bad = deepcopy(self.files)
                if semantic:
                    index = deepcopy(self.index); index["qualification"] = "QUALIFIED"
                    index["index_id"] = digest({key: value for key, value in index.items() if key != "index_id"})
                    raw = canonical(index); sha = hashlib.sha256(raw).hexdigest()
                    manifest = deepcopy(self.manifest)
                    manifest["production_research"].update(path="sdv-production."+sha+".json", sha256=sha)
                    manifest["snapshot_id"] = digest({key: value for key, value in manifest.items() if key != "snapshot_id"})
                    bad["data/manifest.json"] = canonical(manifest)
                    bad["data/sdv-production."+sha+".json"] = raw
                else:
                    bad["data/"+self.index["pages"][0]["path"]] += b" "
                output, report, reader = self.restore_to(folder, [(1, self.archived(bad)), (2, self.archived())])
                self.assertEqual(report["source_run_id"], 2)
                self.assertEqual(len(report["rejected"]), 1)
                self.assertTrue((output/"data/manifest.json").is_file())

    def test_missing_prepared_registry_cannot_replace_retained_forecasts_with_empty_success(self):
        with tempfile.TemporaryDirectory() as folder:
            output, _, _ = self.restore_to(folder, [(1, self.archived())])
            project = Path(folder)/"project"; project.mkdir()
            for name in ("config", "web"):
                shutil.copytree(ROOT/name, project/name)
            self.assertFalse((project/production.STATE_PATH).exists())
            built = publication.build_site(project, output, build_commit="c"*40, now=self.now)
            self.assertTrue(built["production_research"]["retained"])
            self.assertIsNotNone(built["production_research_error"])
            descriptor = self.manifest["production_research"]
            self.assertEqual(built["production_research"]["generated_at"], descriptor["generated_at"])
            self.assertEqual(production.read_publication(output/"data", built["production_research"],
                                                       now=self.now)["index"]["counts"], self.index["counts"])

    def test_traversal_links_duplicates_and_unknown_archive_paths_are_never_extracted(self):
        fixtures = []
        for name in ("../escape.json", "/absolute.json", "data/../../escape.json", "unknown/private.txt"):
            fixtures.append(packed_files({**self.files, name: b"{}"}))
        linked = tarfile.TarInfo("data/link.json"); linked.type = tarfile.SYMTYPE; linked.linkname = "../outside"
        fixtures.append(packed_files(self.files, extra=linked))
        duplicate = tarfile.TarInfo("data/manifest.json"); duplicate.size = 0
        fixtures.append(packed_files(self.files, extra=duplicate))
        for packed in fixtures:
            with self.subTest(sha=hashlib.sha256(packed).hexdigest()), tempfile.TemporaryDirectory() as folder:
                output, report, _ = self.restore_to(folder, [(1, packed)])
                self.assertEqual(report["status"], "NO_VALID_PRIOR_PAGES_ARTIFACT")
                self.assertFalse(output.exists())
                self.assertFalse((Path(folder)/"escape.json").exists())

    def test_oversized_data_and_expired_artifact_reject_without_installing_partial_output(self):
        bad = {**self.files, "data/oversized.json": b" "*(restore.MAX_FILE_BYTES+1)}
        with tempfile.TemporaryDirectory() as folder:
            output, report, _ = self.restore_to(folder, [(1, self.archived(bad))])
            self.assertEqual(report["status"], "NO_VALID_PRIOR_PAGES_ARTIFACT")
            self.assertFalse(output.exists())
        reader = FakeArtifacts([(1, self.archived())], now=self.now)
        original = reader.artifacts
        reader.artifacts = lambda run_id: [{**original(run_id)[0], "expired": True}]
        with tempfile.TemporaryDirectory() as folder:
            report = restore.restore(Path(folder)/"output", now=self.now, reader=reader)
            self.assertEqual(report["status"], "NO_VALID_PRIOR_PAGES_ARTIFACT")
            self.assertEqual(reader.downloaded, [])
        reader.artifacts = lambda run_id: [{**original(run_id)[0], "size_in_bytes": restore.MAX_ARCHIVE_BYTES+1}]
        with tempfile.TemporaryDirectory() as folder:
            report = restore.restore(Path(folder)/"output", now=self.now, reader=reader)
            self.assertEqual(report["status"], "NO_VALID_PRIOR_PAGES_ARTIFACT")
            self.assertEqual(reader.downloaded, [])

    def test_untrusted_run_and_existing_work_are_not_overwritten(self):
        reader = FakeArtifacts([(1, self.archived())], now=self.now)
        rows = reader.runs(); rows[0]["repository"]["full_name"] = "someone/else"
        reader.runs = lambda: rows
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/"output"
            report = restore.restore(output, now=self.now, reader=reader)
            self.assertEqual(report["status"], "NO_VALID_PRIOR_PAGES_ARTIFACT")
            self.assertEqual(reader.downloaded, [])
            output.mkdir(); sentinel = output/"existing"; sentinel.write_bytes(b"retained work")
            report = restore.restore(output, now=self.now, reader=reader)
            self.assertEqual(report["status"], "EXISTING_OUTPUT_PRESERVED")
            self.assertEqual(sentinel.read_bytes(), b"retained work")

    def test_candidate_budget_stops_without_scanning_unbounded_history(self):
        files = deepcopy(self.files); manifest = deepcopy(self.manifest)
        manifest["production_research"] = None
        manifest["production_research_error"] = "Explicitly unavailable in invented candidate."
        manifest["snapshot_id"] = digest({key: value for key, value in manifest.items() if key != "snapshot_id"})
        files["data/manifest.json"] = canonical(manifest)
        with tempfile.TemporaryDirectory() as folder:
            _, report, reader = self.restore_to(folder,
                [(number, self.archived(files)) for number in range(1, restore.MAX_CANDIDATES+2)])
            self.assertEqual(report["status"], "NO_VALID_PRIOR_PAGES_ARTIFACT")
            self.assertEqual(len(reader.downloaded), restore.MAX_CANDIDATES)
            self.assertEqual(report["examined"], restore.MAX_CANDIDATES)

    def test_main_only_workflow_restores_before_build_with_read_only_permissions(self):
        text = (ROOT/".github/workflows/pages.yml").read_text()
        self.assertLess(text.index("python3 scripts/restore_pages_artifact.py --output output"),
                        text.index("python3 -m multisport_lab.publication --build-commit"))
        self.assertIn("      contents: read\n      actions: read", text)
        step = text.split("- name: Restore strictly verified prior production data", 1)[1].split("- name:", 1)[0]
        self.assertIn("github.ref == 'refs/heads/main' && github.event_name != 'pull_request'", step)


if __name__ == "__main__":
    unittest.main()

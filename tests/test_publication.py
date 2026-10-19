from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest

from multisport_lab.integrity import IntegrityError, canonical
from multisport_lab.publication import build_site, empty_nba, publish, read_manifest, resolve_scope, validate_sport

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 19, 23, tzinfo=timezone.utc)
COMMIT = "a" * 40


class PublicationTests(unittest.TestCase):
    def test_single_selected_all_never_expand_unsupported_scope(self):
        supported = ["NBA", "WNBA"]  # synthetic future coverage, not admitted sports
        self.assertEqual(resolve_scope("SINGLE", ["NBA"], supported), {"NBA"})
        self.assertEqual(resolve_scope("SELECTED", ["WNBA"], supported), {"WNBA"})
        self.assertEqual(resolve_scope("ALL", [], supported), {"NBA", "WNBA"})
        for mode, selection in [("SELECTED", []), ("ALL", ["NBA"]), ("SINGLE", supported), ("SINGLE", ["NFL"])]:
            with self.assertRaises(ValueError):
                resolve_scope(mode, selection, supported)

    def test_research_schema_rejects_claims_missing_categories_or_rows(self):
        snapshot = empty_nba(ROOT, now=NOW)
        validate_sport(snapshot, league="NBA", now=NOW)
        for field, value in [("candidates", [{"qualified": True}]), ("offers", [{}]),
                             ("status", "QUALIFIED"), ("schema_version", True),
                             ("generated_at", "2026-10-20T00:00:00Z")]:
            bad = deepcopy(snapshot)
            bad[field] = value
            with self.assertRaises((ValueError, IntegrityError)):
                validate_sport(bad, league="NBA", now=NOW)
        bad = deepcopy(snapshot)
        bad["markets"] = [m for m in bad["markets"] if m["code"] != "TD"]
        with self.assertRaises(IntegrityError):
            validate_sport(bad, league="NBA", now=NOW)

    def test_failed_sport_preserves_old_bytes_and_time_other_sport_publishes(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            nba = empty_nba(ROOT, now=NOW)
            initial = publish(data, {"NBA": nba}, build_commit=COMMIT, now=NOW)
            old = initial["sports"][0]
            before = (data / old["path"]).read_bytes()
            # WNBA is fictional test coverage only, with no markets or observations.
            wnba = deepcopy(nba)
            wnba.update(league="WNBA", markets=[], generated_at="2026-10-19T23:01:00Z")
            later = NOW + timedelta(minutes=1)
            manifest = publish(data, {"NBA": ValueError("private upstream body"), "WNBA": wnba},
                               build_commit="b"*40, now=later)
            saved = next(x for x in manifest["sports"] if x["league"] == "NBA")
            self.assertTrue(saved["retained"])
            self.assertEqual(saved["generated_at"], old["generated_at"])
            self.assertEqual((data / old["path"]).read_bytes(), before)
            self.assertNotIn("private", canonical(manifest).decode())
            self.assertEqual(read_manifest(data, now=later), manifest)

    def test_corruption_and_failed_first_update_do_not_publish_success(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            with self.assertRaises(IntegrityError):
                publish(data, {"NBA": ValueError("failed")}, build_commit=COMMIT, now=NOW)
            self.assertFalse((data / "manifest.json").exists())
            manifest = publish(data, {"NBA": empty_nba(ROOT, now=NOW)}, build_commit=COMMIT, now=NOW)
            asset = data / manifest["sports"][0]["path"]
            raw = asset.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest["sports"][0]["sha256"])
            asset.write_bytes(raw.replace(b"UNVALIDATED", b"QUALIFIED!!"))
            with self.assertRaises(IntegrityError):
                read_manifest(data, now=NOW)

    def test_build_excludes_stale_private_files_and_keeps_modules(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            (root / "web").mkdir()
            (root / "web/index.html").write_text("<title>Research</title>")
            (root / "web/app.mjs").write_text("export const research = true;")
            (root / "config").mkdir()
            for name in ("nba_markets.json", "capabilities.json"):
                (root / "config" / name).write_bytes((ROOT / "config" / name).read_bytes())
            output = root / "output"
            output.mkdir()
            (output / "private-raw.json").write_text('{"must_not_publish":true}')
            build_site(root, output, build_commit=COMMIT, now=NOW)
            self.assertFalse((output / "private-raw.json").exists())
            self.assertTrue((output / "app.mjs").is_file())
            self.assertTrue((output / "index.html").is_file())
            read_manifest(output / "data", now=NOW)


if __name__ == "__main__":
    unittest.main()

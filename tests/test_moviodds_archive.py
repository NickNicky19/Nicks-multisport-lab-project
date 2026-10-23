"""Offline fictional archive/recovery tests; never provider or GitHub requests."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab.integrity import IntegrityError, canonical, digest
from multisport_lab import moviodds_archive as archive
from multisport_lab import sdv_production_archive as transport
from multisport_lab.native_offer import build_native_offer
from test_moviodds_offer import FIXTURE, NOW, fictional_assets, fictional_review

ROOT = Path(__file__).resolve().parents[1]


class FakeHosted(archive.GuardedGitHubReleaseArchive):
    """Existing authenticated transport interface, all I/O in a fictional disk."""
    def __init__(self, files, state):
        super().__init__(allow_diagnostics=True)
        self.files, self.state = files, state

    def _json(self, route, **kwargs):
        self.state["queries"] += 1
        return deepcopy(self.state["release"])

    def _listed_diagnostic_release(self, tag):
        self.state["queries"] += 1
        return deepcopy(self.state["release"])

    def _release(self, tag, *, create=False):
        if create and self.state["release"] is None:
            self.state["release"] = {"id": 9001, "tag_name": tag, "draft": True}
        return deepcopy(self.state["release"])

    def put(self, raw, tag):
        self.state["puts"] += 1
        return self.files.put(raw, tag)

    def get(self, ref, max_raw_bytes):
        self.state["gets"] += 1
        return self.files.get(ref, max_raw_bytes)

    def fresh_reader(self):
        return FakeHosted(self.files.fresh_reader(), self.state)


class MoviOddsArchiveTests(unittest.TestCase):
    def setUp(self):
        private = ROOT / ".local-data"
        private.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="fictional-moviodds-archive-", dir=private)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.package = self.base / "originals"
        self.package.mkdir()
        self.assets = fictional_assets()
        self.review = fictional_review()
        files = {k + suffix: asset[field] for k, asset in self.assets.items()
                 for suffix, field in [(".body", "raw"), (".metadata.json", "metadata_raw")]}
        intent = {"fixture": FIXTURE, "normalized_at": NOW,
            "originals": {k: {field: hashlib.sha256(raw).hexdigest() for field, raw in asset.items()}
                          for k, asset in self.assets.items()}}
        files.update({"review-intent.json": canonical(intent), "review.json": canonical(self.review)})
        for name, raw in files.items():
            (self.package / name).write_bytes(raw)
        self.files = files
        self.backend = transport.FileArchive(self.base / "objects", allow_diagnostics=True)
        self.client = archive.PrivateMoviOddsArchive(self.backend, allow_synthetic=True)

    def stored(self):
        return self.client.archive(self.package, now=NOW)["reference"]

    def test_archive_cold_recovery_byte_clocks_and_no_preview(self):
        (self.package / "private-preview.html").write_bytes(b"not original: never upload")
        result = self.client.archive(self.package, now=NOW)
        self.assertFalse(result["durable_remote_archive_verified"])
        self.assertEqual(result["files"], 16)
        self.assertEqual(result["originals_replayed"], 7)
        self.assertEqual(result["budget"]["unique_objects"], 17)
        destination = self.base / "recovered"
        recovery = self.client.fresh_reader().recover(result["reference"], destination, now=NOW)
        self.assertEqual(recovery["review_id"], self.review["review_id"])
        self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, self.files)
        self.assertEqual(json.loads((destination / "review.json").read_bytes())["normalized_at"], NOW)
        self.assertFalse(recovery["public_admission"])
        self.assertEqual(recovery["source_provider_requests"], 0)

    def test_archive_idempotent_and_compact_bridge_replays_all_originals(self):
        first = self.stored()
        count, size = self.backend.new_objects_reserved, self.backend.new_bytes_reserved
        self.assertEqual(self.stored(), first)
        self.assertEqual((self.backend.new_objects_reserved, self.backend.new_bytes_reserved), (count, size))
        compact = {k: first[k] for k in ("manifest_ref", "manifest_id")}
        found = archive.load_recovered_assets(compact, archive=self.backend, now=NOW, allow_synthetic=True)
        self.assertEqual(found["assets"], self.assets)
        self.assertEqual(found["review"], self.review)
        self.assertEqual(found["reference"], first)
        self.assertEqual(archive.validate_manifest(found["manifest"]), found["manifest"])

    def test_wrong_source_original_intent_or_synthetic_lane_reject_before_writes(self):
        for filename in ["snapshot.body", "review-intent.json", "review.json"]:
            with self.subTest(filename=filename):
                original = (self.package / filename).read_bytes()
                (self.package / filename).write_bytes(b"{}")
                with self.assertRaises(IntegrityError):
                    self.client.archive(self.package, now=NOW)
                (self.package / filename).write_bytes(original)
        with self.assertRaises(IntegrityError):
            archive.PrivateMoviOddsArchive(self.backend).archive(self.package, now=NOW)
        self.assertEqual(self.backend.inventory(), [])

    def test_typed_manifest_rejects_resealed_meaning_clocks_and_namespace(self):
        reference = self.stored()
        body = self.backend.get_json(reference["manifest_ref"], max_raw_bytes=archive.MAX_MANIFEST_BYTES)
        cases = [("source_namespace", "sdv"), ("source_schema", "nba-forecast-v1"),
                 ("tag", "nml-nba-20261023"), ("source_observed_at", "2026-10-23T13:00:00Z"),
                 ("evidence_lane", "PROSPECTIVE"), ("adapter_source_sha256", "0" * 64),
                 ("file_count", True), ("public_admission", True)]
        for key, value in cases:
            candidate = deepcopy(body); candidate[key] = value
            candidate["manifest_id"] = digest({k: v for k, v in candidate.items() if k != "manifest_id"})
            with self.subTest(key=key), self.assertRaises(IntegrityError):
                archive.validate_manifest(candidate)
        candidate = deepcopy(body); candidate["files"]["private-key.pem"] = candidate["files"].pop("api.body")
        candidate["manifest_id"] = digest({k: v for k, v in candidate.items() if k != "manifest_id"})
        with self.assertRaises(IntegrityError):
            archive.validate_manifest(candidate)

    def test_foreign_or_compact_wrong_manifest_reference_rejected(self):
        reference = self.stored()
        for candidate in [dict(reference, review_id="0" * 64),
                {"manifest_ref": reference["manifest_ref"], "manifest_id": "0" * 64}]:
            with self.assertRaises(IntegrityError):
                self.client.load_recovered_assets(candidate, now=NOW)
        foreign = deepcopy(reference); foreign["manifest_ref"]["tag"] = "diagnostics-nml-nba-unrelated"
        with self.assertRaises(IntegrityError):
            self.client.load_recovered_assets(foreign, now=NOW)

    def test_interrupted_upload_retries_exact_objects_and_clocks(self):
        put = self.backend.put
        calls = 0
        def interrupted(raw, tag):
            nonlocal calls
            calls += 1
            result = put(raw, tag)
            if calls == 5:
                raise IntegrityError("Fictional interruption after durable write")
            return result
        with patch.object(self.backend, "put", side_effect=interrupted):
            with self.assertRaises(IntegrityError):
                self.client.archive(self.package, now=NOW)
        self.assertEqual(len(self.backend.inventory()), 5)
        reference = self.stored()
        self.assertEqual(len(self.backend.inventory()), 17)
        self.assertEqual(self.client.fresh_reader().load_recovered_assets(reference, now=NOW)["review"], self.review)

    def test_partial_local_recovery_restart_is_create_only(self):
        reference = self.stored()
        from multisport_lab import player_line_review
        create = player_line_review._create
        calls = 0
        def interrupted(*args, **kwargs):
            nonlocal calls
            calls += 1
            result = create(*args, **kwargs)
            if calls == 4:
                raise IntegrityError("Fictional interrupted copy")
            return result
        destination = self.base / "partial"
        with patch.object(player_line_review, "_create", side_effect=interrupted):
            with self.assertRaises(IntegrityError):
                self.client.recover(reference, destination, now=NOW)
        self.assertEqual(len(list(destination.iterdir())), 4)
        self.client.fresh_reader().recover(reference, destination, now=NOW)
        self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, self.files)
        first = destination / archive.FILENAMES[0]
        first.write_bytes(b"conflict")
        with self.assertRaises(IntegrityError):
            self.client.recover(reference, destination, now=NOW)
        self.assertEqual(first.read_bytes(), b"conflict")

    def test_unrelated_entries_symlink_or_outside_private_destination_rejected(self):
        reference = self.stored()
        destination = self.base / "protected"; destination.mkdir()
        (destination / "private-key.pem").write_bytes(b"fictional")
        with self.assertRaises(IntegrityError):
            self.client.recover(reference, destination, now=NOW)
        link = self.base / "link"; link.symlink_to(self.package, target_is_directory=True)
        with self.assertRaises(IntegrityError):
            self.client.archive(link, now=NOW)
        with self.assertRaises(IntegrityError):
            self.client.recover(reference, Path("/tmp/not-admitted-private-offer-directory"), now=NOW)

    def test_missing_or_corrupt_remote_original_rejected(self):
        reference = self.stored()
        body = self.backend.get_json(reference["manifest_ref"], max_raw_bytes=archive.MAX_MANIFEST_BYTES)
        ref = body["files"]["snapshot.body"]["archive_ref"]
        path = self.backend.root / ref["tag"] / ref["name"]
        packed = path.read_bytes(); path.unlink()
        with self.assertRaises(IntegrityError):
            self.client.fresh_reader().load_recovered_assets(reference, now=NOW)
        path.write_bytes(packed[:-1] + b"x")
        with self.assertRaises(IntegrityError):
            self.client.fresh_reader().load_recovered_assets(reference, now=NOW)

    def test_budgets_checked_before_mutation_and_not_silently_raised(self):
        with patch.object(archive, "MAX_NEW_OBJECTS", 16):
            with self.assertRaises(IntegrityError):
                self.client.archive(self.package, now=NOW)
        with patch.object(archive, "MAX_NEW_WIRE_BYTES", 128):
            with self.assertRaises(IntegrityError):
                self.client.archive(self.package, now=NOW)
        self.assertEqual(self.backend.inventory(), [])
        for key, value in [("write_budget_bytes", 8 * 1024 * 1024 + 1),
                ("write_budget_objects", 33), ("write_budget_objects", True)]:
            backend = transport.FileArchive(self.base / (key + str(value)), allow_diagnostics=True,
                                           **{key: value})
            with self.assertRaises(IntegrityError):
                archive.PrivateMoviOddsArchive(backend)

    def test_hosted_fresh_draft_before_every_access_and_no_warm_cache_admission(self):
        state = {"release": None, "queries": 0, "puts": 0, "gets": 0}
        backend = FakeHosted(self.backend, state)
        client = archive.PrivateMoviOddsArchive(backend, allow_synthetic=True)
        result = client.archive(self.package, now=NOW)
        self.assertTrue(result["durable_remote_archive_verified"])  # fictional hosted interface only
        before = state["queries"]
        client.load_recovered_assets(result["reference"], now=NOW)
        self.assertGreaterEqual(state["queries"] - before, 18)
        backend._release_cache[archive.TAG] = {"id": 9001, "tag_name": archive.TAG, "draft": True}
        state["release"]["draft"] = False
        gets, puts = state["gets"], state["puts"]
        with self.assertRaises(IntegrityError):
            client.load_recovered_assets(result["reference"], now=NOW)
        with self.assertRaises(IntegrityError):
            client._put(b"no published write")
        self.assertEqual((state["gets"], state["puts"]), (gets, puts))

    def test_native_offer_durable_original_normalization_and_cold_replay(self):
        reference = self.stored()
        offer = build_native_offer(self.review, 0, now="2026-10-23T12:02:00Z")
        result = self.client.archive_native_offer(reference, offer, now="2026-10-23T12:03:00Z")
        recovered = self.client.fresh_reader().recover_native_offer(result["reference"], now="2026-10-23T12:04:00Z")
        self.assertEqual(recovered["offer"], offer)
        self.assertEqual(recovered["assets"], self.assets)
        self.assertEqual(recovered["native_descriptor"]["offer_normalized_at"], offer["normalized_at"])
        self.assertFalse(result["durable_remote_archive_verified"])
        self.assertEqual(result["budget"]["unique_objects"], 19)
        count = len(self.backend.inventory())
        retry = self.client.archive_native_offer(reference, offer, now="2026-10-23T12:05:00Z")
        self.assertEqual(retry["reference"], result["reference"])
        self.assertEqual(len(self.backend.inventory()), count)

    def test_native_descriptor_resealed_clock_identity_and_source_conflicts_rejected(self):
        source = self.stored(); offer = build_native_offer(self.review, 0, now=NOW)
        reference = self.client.archive_native_offer(source, offer, now=NOW)["reference"]
        descriptor = self.backend.get_json(reference["descriptor_ref"], max_raw_bytes=archive.MAX_MANIFEST_BYTES)
        for key, value in [("offer_normalized_at", "2026-10-23T11:00:00Z"),
                ("offer_sha256", "0" * 64), ("native_adapter_source_sha256", "0" * 64),
                ("public_admission", True)]:
            candidate = deepcopy(descriptor); candidate[key] = value
            badref = {"descriptor_ref": self.backend.put_json(candidate, tag=archive.TAG), "offer_id": offer["offer_id"]}
            with self.subTest(key=key), self.assertRaises(IntegrityError):
                self.client.recover_native_offer(badref, now=NOW)

    def test_real_transport_publication_during_inventory_blocks_actual_post(self):
        state = {"draft": True, "uploads": 0, "asset_queries": 0}
        backend = archive.GuardedGitHubReleaseArchive(allow_diagnostics=True)
        client = archive.PrivateMoviOddsArchive(backend)
        def command(args, **kwargs):
            endpoint = args[2]
            release = {"id": 9001, "tag_name": archive.TAG, "draft": state["draft"]}
            if endpoint.endswith("/tags/" + archive.TAG):
                body = release
            elif "/assets?per_page=" in endpoint:
                state["asset_queries"] += 1
                state["draft"] = False  # changes after the initial outer check
                body = []
            elif "/releases?per_page=" in endpoint:
                body = [release]
            elif endpoint.startswith("https://uploads."):
                state["uploads"] += 1
                body = {}
            else:
                self.fail("Unexpected fictional transport route: " + endpoint)
            return SimpleNamespace(returncode=0, stdout=canonical(body), stderr=b"")
        with patch.object(transport.subprocess, "run", side_effect=command):
            with self.assertRaises(IntegrityError):
                client._put(b"private fictional original")
        self.assertGreater(state["asset_queries"], 0)
        self.assertEqual(state["uploads"], 0)

    def test_unguarded_hosted_backend_and_namespace_budget_bypass_rejected(self):
        with self.assertRaises(IntegrityError):
            archive.PrivateMoviOddsArchive(transport.GitHubReleaseArchive(allow_diagnostics=True))
        for i in range(archive.MAX_NEW_OBJECTS):
            self.backend.put(("fictional prior object " + str(i)).encode(), tag=archive.TAG)
        with self.assertRaises(IntegrityError):
            self.client.fresh_reader()._put(b"one more object after reset client")

    def test_interrupted_native_body_retry_reuses_original_normalization(self):
        source = self.stored(); offer = build_native_offer(self.review, 0, now=NOW)
        put = self.backend.put; calls = 0
        def interrupted(raw, tag):
            nonlocal calls
            calls += 1
            result = put(raw, tag)
            if calls == 1:
                raise IntegrityError("Fictional native body saved before acknowledgment")
            return result
        with patch.object(self.backend, "put", side_effect=interrupted):
            with self.assertRaises(IntegrityError):
                self.client.archive_native_offer(source, offer, now=NOW)
        self.assertEqual(len(self.backend.inventory()), 18)
        saved = self.client.archive_native_offer(source, offer, now="2026-10-23T12:03:00Z")
        recovered = self.client.fresh_reader().recover_native_offer(saved["reference"], now="2026-10-23T12:04:00Z")
        self.assertEqual(recovered["offer"], offer)
        self.assertEqual(len(self.backend.inventory()), 19)


if __name__ == "__main__":
    unittest.main()

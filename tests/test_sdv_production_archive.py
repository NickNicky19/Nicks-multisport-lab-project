from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zlib

from multisport_lab.integrity import IntegrityError, canonical
from multisport_lab import sdv_production_archive as archive
from multisport_lab import sdv_production_store as production

TAG = "nml-nba-records-v1-202610"
DIAGNOSTIC = "diagnostics-nml-nba-archive-test"


def snapshot_fixture(entries):
    counts={key:0 for key in production.SLOTS}
    counts[archive.common.STATUS_SCHEMA]=len(entries)
    total=sum(row["bytes"] for row in entries)
    return archive.common.seal({"schema_version":production.SNAPSHOT_SCHEMA,
        "protocol_id":archive.common.PROTOCOL_ID,"entries":entries,"unpublished_entries":[],
        "records":len(entries),"bytes":total,
        "capacity":production._capacity_summary(len(entries),total,counts)},"snapshot_id")


class MemoryGitHub(archive.GitHubReleaseArchive):
    """Official-API-shaped offline fake; never a hosted/archive result."""
    def __init__(self):
        super().__init__(allow_diagnostics=True)
        self.calls, self.releases, self.assets, self.raw = [], {}, {}, {}

    def _gh(self, args, *, input_bytes=None, maximum=archive.MAX_WIRE, missing=False, reconcile=False):
        self.calls.append(args)
        endpoint = args[0]
        method = args[args.index("--method") + 1] if "--method" in args else "GET"
        if "/releases/tags/" in endpoint:
            value = self.releases.get(endpoint.rsplit("/", 1)[1])
            return canonical(value) if value else None
        if method == "POST" and endpoint.endswith("/releases"):
            value = json.loads(input_bytes)
            value["id"] = len(self.releases) + 1
            self.releases[value["tag_name"]] = value
            self.assets[value["id"]] = []
            return canonical(value)
        if method == "POST" and endpoint.startswith("https://uploads.github.com/"):
            rid = int(endpoint.split("/releases/", 1)[1].split("/", 1)[0])
            name = endpoint.split("?name=", 1)[1]
            value = {"id": len(self.raw) + 100, "name": name, "size": len(input_bytes)}
            self.assets[rid].append(value)
            self.raw[value["id"]] = input_bytes
            return canonical(value)
        if "/releases/assets/" in endpoint:
            return self.raw[int(endpoint.rsplit("/", 1)[1])]
        if "/assets?" in endpoint:
            rid = int(endpoint.split("/releases/", 1)[1].split("/", 1)[0])
            return canonical(self.assets[rid])
        if "/releases?" in endpoint:
            return canonical(list(self.releases.values()))
        raise RuntimeError("Unexpected offline fake endpoint")


class DraftTagMissingGitHub(MemoryGitHub):
    """Model the observed draft-by-tag 404 with an authenticated inventory."""
    def __init__(self):
        super().__init__()
        self.unacknowledged_create = False

    def _gh(self, args, *, input_bytes=None, maximum=archive.MAX_WIRE, missing=False, reconcile=False):
        if "/releases/tags/" in args[0]:
            self.calls.append(args)
            return None
        result = super()._gh(args, input_bytes=input_bytes, maximum=maximum,
                             missing=missing, reconcile=reconcile)
        if self.unacknowledged_create and args[0].endswith("/releases") and "POST" in args:
            return None
        return result

    def fresh_reader(self):
        reader = DraftTagMissingGitHub()
        reader.releases, reader.assets, reader.raw = self.releases, self.assets, self.raw
        return reader


class ProductionArchiveTests(unittest.TestCase):
    def test_file_archive_restart_idempotence_and_exact_wire_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            first = archive.FileArchive(folder)
            raw = b"original probability and input bytes\x00" * 100
            ref = first.put(raw, TAG)
            second = archive.FileArchive(folder)
            self.assertEqual(second.get(ref, len(raw)), raw)
            self.assertEqual(second.put(raw, TAG), ref)
            self.assertEqual(len(second.inventory()), 1)
            packed = (Path(folder) / TAG / ref["name"]).read_bytes()
            self.assertEqual(ref["sha256"], hashlib.sha256(packed).hexdigest())
            self.assertEqual(ref["bytes"], len(packed))

    def test_changed_truncated_or_oversized_objects_never_recover(self):
        with tempfile.TemporaryDirectory() as folder:
            client = archive.FileArchive(folder)
            ref = client.put(b"a" * 100, TAG)
            with self.assertRaises(IntegrityError):
                client.get(ref, 99)
            path = Path(folder) / TAG / ref["name"]
            path.write_bytes(path.read_bytes()[:-1])
            with self.assertRaisesRegex(IntegrityError, "wire bytes/hash differ"):
                client.get(ref, 100)
            packed = zlib.compress(b"a") + zlib.compress(b"hidden")
            fake = {"tag": TAG, "name": "object-" + hashlib.sha256(packed).hexdigest() + ".z",
                    "sha256": hashlib.sha256(packed).hexdigest(), "bytes": len(packed)}
            (Path(folder) / TAG / fake["name"]).write_bytes(packed)
            with self.assertRaisesRegex(IntegrityError, "trailing members"):
                client.get(fake, 100)

    def test_chunked_source_originals_recover_without_history_duplication(self):
        with tempfile.TemporaryDirectory() as folder:
            client = archive.FileArchive(folder)
            raw = b"x" * (archive.CHUNK + 19)
            metadata_raw = b'{"actual":"publisher release metadata"}'
            metadata = {"asset_bytes": len(raw), "asset_sha256": hashlib.sha256(raw).hexdigest(),
                "metadata_bytes": len(metadata_raw), "metadata_sha256": hashlib.sha256(metadata_raw).hexdigest(),
                "role": "schedule", "upstream_observed_at": None}
            ref = client.retain_source(raw, metadata, metadata_raw, tag=TAG)
            rebuilt = archive.FileArchive(folder).recover_source(ref)
            self.assertEqual(rebuilt, (raw, metadata, metadata_raw))
            manifest = client.get_json(ref)
            self.assertEqual([x["raw_bytes"] for x in manifest["asset_chunks"]], [archive.CHUNK, 19])
            self.assertEqual(client.retain_source(raw, metadata, metadata_raw, tag=TAG), ref)
            self.assertEqual(len(client.inventory()), 4)

    def test_source_manifest_cannot_reorder_or_omit_validly_hashed_chunks(self):
        with tempfile.TemporaryDirectory() as folder:
            client = archive.FileArchive(folder)
            raw, meta = b"a" * (archive.CHUNK + 1), b"{}"
            metadata = {"asset_bytes": len(raw), "asset_sha256": hashlib.sha256(raw).hexdigest(),
                "metadata_bytes": 2, "metadata_sha256": hashlib.sha256(meta).hexdigest()}
            ref = client.retain_source(raw, metadata, meta, tag=TAG)
            body = client.get_json(ref)
            body["asset_chunks"].reverse()
            body = archive.common.seal({k: v for k, v in body.items() if k != "source_manifest_id"}, "source_manifest_id")
            bad = client.put_json(body, tag=TAG)
            with self.assertRaisesRegex(IntegrityError, "order/length"):
                client.recover_source(bad)

    def test_quota_reserves_outstanding_grade_bytes_and_no_object_is_deleted(self):
        with tempfile.TemporaryDirectory() as folder:
            client = archive.FileArchive(folder, reserved_bytes=archive.common.make_policy()["archive_month_bytes"])
            with self.assertRaisesRegex(IntegrityError, "reserved grading budget"):
                client.put(b"new", TAG)
            self.assertEqual(client.inventory(), [])
            client.reserved_bytes = 0
            ref = client.put(b"original", TAG)
            client.reserved_bytes = archive.common.make_policy()["archive_total_bytes"]
            self.assertEqual(client.put(b"original", TAG), ref)
            self.assertFalse(client.quota(TAG)["fits"])
            self.assertEqual(client.get(ref, 8), b"original")

    def test_diagnostics_require_explicit_scope_and_remain_draft_in_official_api(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(IntegrityError):
                archive.FileArchive(folder).put(b"synthetic", DIAGNOSTIC)
        client = MemoryGitHub()
        ref = client.put(b"synthetic", DIAGNOSTIC)
        self.assertTrue(client.releases[DIAGNOSTIC]["draft"])
        self.assertEqual(client.get(ref, 9), b"synthetic")
        self.assertEqual(client.put(b"synthetic", DIAGNOSTIC), ref)
        writes = [args for args in client.calls if "POST" in args]
        self.assertEqual(len(writes), 2)  # One create and one upload, no replacement.
        self.assertFalse(any("DELETE" in args or "PATCH" in args for args in client.calls))

    def test_forbidden_api_is_not_treated_as_missing_and_never_creates_release(self):
        result = subprocess.CompletedProcess([], 1, b"", b"gh: Forbidden (HTTP 403)")
        client = archive.GitHubReleaseArchive()
        with patch.object(archive.subprocess, "run", return_value=result) as command:
            with self.assertRaisesRegex(IntegrityError, "do not change transports"):
                client.put(b"no mutation", TAG)
        command.assert_called_once()

    def test_cold_reader_recovers_existing_draft_omitted_by_tag_without_new_writes(self):
        first = DraftTagMissingGitHub()
        original = b"immutable original draft bytes"
        ref = first.put(original, DIAGNOSTIC)
        cold = first.fresh_reader()
        cold.write_budget_bytes, cold.write_budget_objects = 0, 0
        self.assertEqual(cold.get(ref, len(original)), original)
        self.assertEqual(cold.put(original, DIAGNOSTIC), ref)
        self.assertEqual(cold.new_bytes_reserved, 0)
        self.assertEqual(cold.new_objects_reserved, 0)
        self.assertTrue(any("/releases?" in args[0] for args in cold.calls))
        self.assertFalse(any("POST" in args for args in cold.calls))
        self.assertEqual(len(first.releases), 1)
        self.assertEqual(len(first.assets[1]), 1)

    def test_existing_draft_reader_refreshes_decoded_inventory_for_later_original(self):
        writer = DraftTagMissingGitHub()
        first = writer.put(b"first original", DIAGNOSTIC)
        reader = writer.fresh_reader()
        reader.write_budget_bytes, reader.write_budget_objects = 0, 0
        self.assertEqual(reader.get(first, 64), b"first original")
        rid = writer.releases[DIAGNOSTIC]["id"]
        self.assertIsNot(reader._asset_cache[rid], writer.assets[rid])
        self.assertEqual(len(reader._asset_cache[rid]), 1)
        second = writer.put(b"second later original", DIAGNOSTIC)
        self.assertEqual(len(reader._asset_cache[rid]), 1)
        before = len([args for args in reader.calls if "/assets?" in args[0]])
        self.assertEqual(reader.get(second, 64), b"second later original")
        self.assertEqual(len([args for args in reader.calls if "/assets?" in args[0]]), before + 1)
        self.assertEqual(reader.get(first, 64), b"first original")
        self.assertEqual(reader.put(b"second later original", DIAGNOSTIC), second)
        self.assertEqual(reader.new_bytes_reserved, 0)
        self.assertEqual(reader.new_objects_reserved, 0)
        self.assertFalse(any("POST" in args for args in reader.calls))

    def test_missing_draft_object_refreshes_cached_inventory_only_once(self):
        writer = DraftTagMissingGitHub()
        first = writer.put(b"first original", DIAGNOSTIC)
        missing = archive._wire(b"never uploaded", DIAGNOSTIC, True)[1]
        reader = writer.fresh_reader()
        self.assertEqual(reader.get(first, 64), b"first original")
        before = len([args for args in reader.calls if "/assets?" in args[0]])
        with self.assertRaisesRegex(IntegrityError, "object identity/size differs"):
            reader.get(missing, 64)
        self.assertEqual(len([args for args in reader.calls if "/assets?" in args[0]]), before + 1)
        self.assertFalse(any("POST" in args for args in reader.calls))
        cold = writer.fresh_reader()
        with self.assertRaisesRegex(IntegrityError, "object identity/size differs"):
            cold.get(missing, 64)
        self.assertEqual(len([args for args in cold.calls if "/assets?" in args[0]]), 1)

    def test_existing_draft_identity_size_and_hash_failures_never_refresh_inventory(self):
        for failure in ("size", "hash", "ambiguous"):
            with self.subTest(failure=failure):
                writer = DraftTagMissingGitHub()
                ref = writer.put(b"immutable original", DIAGNOSTIC)
                reader = writer.fresh_reader()
                rid = writer.releases[DIAGNOSTIC]["id"]
                reader._asset_cache[rid] = json.loads(canonical(writer.assets[rid]))
                item = reader._asset_cache[rid][0]
                if failure == "size":
                    item["size"] += 1
                elif failure == "hash":
                    original = writer.raw[item["id"]]
                    writer.raw[item["id"]] = bytes([original[0] ^ 1]) + original[1:]
                else:
                    reader._asset_cache[rid].append(dict(item))
                with self.assertRaises(IntegrityError):
                    reader.get(ref, 64)
                self.assertFalse(any("/assets?" in args[0] or "POST" in args for args in reader.calls))

    def test_forbidden_draft_inventory_refresh_is_fatal_without_another_attempt(self):
        writer = DraftTagMissingGitHub()
        first = writer.put(b"first original", DIAGNOSTIC)
        reader = writer.fresh_reader()
        self.assertEqual(reader.get(first, 64), b"first original")
        second = writer.put(b"second later original", DIAGNOSTIC)
        with patch.object(reader, "_json", side_effect=archive.ArchiveHTTPError(403, "Forbidden")) as request:
            with self.assertRaises(archive.ArchiveHTTPError) as caught:
                reader.get(second, 64)
        self.assertEqual(caught.exception.http_status, 403)
        request.assert_called_once()
        self.assertIn("/assets?", request.call_args.args[0])
        self.assertFalse(any("POST" in args for args in reader.calls))

    def test_unacknowledged_draft_creation_reconciles_once_without_second_post(self):
        client = DraftTagMissingGitHub()
        client.unacknowledged_create = True
        ref = client.put(b"original survives interrupted create acknowledgment", DIAGNOSTIC)
        self.assertEqual(client.fresh_reader().get(ref, 100),
                         b"original survives interrupted create acknowledgment")
        creates = [args for args in client.calls if args[0].endswith("/releases") and "POST" in args]
        self.assertEqual(len(creates), 1)
        self.assertEqual(len(client.releases), 1)

    def test_draft_inventory_rejects_invalid_matching_identities_before_creation(self):
        variants = [
            [{"tag_name": DIAGNOSTIC, "id": 1, "draft": False}],
            [{"tag_name": DIAGNOSTIC, "id": True, "draft": True}],
            [{"tag_name": DIAGNOSTIC, "id": 0, "draft": True}],
            [{"tag_name": DIAGNOSTIC, "draft": True}],
            [{"tag_name": None, "id": 1, "draft": True}],
            ["not a release"],
            [{"tag_name": DIAGNOSTIC, "id": 1, "draft": True},
             {"tag_name": DIAGNOSTIC, "id": 2, "draft": True}],
        ]
        for releases in variants:
            with self.subTest(releases=releases):
                client = DraftTagMissingGitHub()
                def response(endpoint, **kwargs):
                    self.assertNotEqual(kwargs.get("method"), "POST")
                    return None if "/releases/tags/" in endpoint else releases
                with patch.object(client, "_json", side_effect=response):
                    with self.assertRaises(IntegrityError):
                        client._release(DIAGNOSTIC, create=True)

    def test_draft_inventory_scans_complete_pages_before_accepting_unique_match(self):
        client = DraftTagMissingGitHub()
        first = [{"tag_name": "unrelated-" + str(i), "id": i + 1, "draft": False}
                 for i in range(99)] + [{"tag_name": DIAGNOSTIC, "id": 100, "draft": True}]
        duplicate = [{"tag_name": DIAGNOSTIC, "id": 101, "draft": True}]
        def response(endpoint, **kwargs):
            self.assertNotEqual(kwargs.get("method"), "POST")
            if "/releases/tags/" in endpoint:
                return None
            return first if endpoint.endswith("page=1") else duplicate
        with patch.object(client, "_json", side_effect=response):
            with self.assertRaisesRegex(IntegrityError, "Ambiguous diagnostic draft"):
                client._release(DIAGNOSTIC, create=True)

    def test_incomplete_draft_inventory_rejects_before_release_creation(self):
        client = DraftTagMissingGitHub()
        full = [{"tag_name": "unrelated-" + str(i), "id": i + 1, "draft": False}
                for i in range(100)]
        def response(endpoint, **kwargs):
            self.assertNotEqual(kwargs.get("method"), "POST")
            return None if "/releases/tags/" in endpoint else full
        with patch.object(client, "_json", side_effect=response) as request:
            with self.assertRaisesRegex(IntegrityError, "draft release inventory exceeds bounded pagination"):
                client._release(DIAGNOSTIC, create=True)
        self.assertEqual(request.call_count, 13)  # One tag lookup, twelve bounded list pages.

    def test_forbidden_draft_lookup_never_falls_back_to_inventory_or_creates(self):
        result = subprocess.CompletedProcess([], 1, b"", b"gh: Forbidden (HTTP 403)")
        client = archive.GitHubReleaseArchive(allow_diagnostics=True)
        with patch.object(archive.subprocess, "run", return_value=result) as command:
            with self.assertRaises(archive.ArchiveHTTPError):
                client._release(DIAGNOSTIC, create=True)
        command.assert_called_once()

    def test_published_production_lookup_does_not_inherit_diagnostic_fallback(self):
        client = MemoryGitHub()
        self.assertIsNone(client._release(TAG))
        self.assertEqual(len(client.calls), 1)
        self.assertIn("/releases/tags/", client.calls[0][0])

    def test_binary_stdin_upload_declares_exact_wire_content_length(self):
        client=MemoryGitHub(); raw=b"invented release upload payload"*100
        ref=client.put(raw,DIAGNOSTIC)
        upload=next(args for args in client.calls if args[0].startswith("https://uploads.github.com/"))
        self.assertIn("Content-Length: "+str(ref["bytes"]),upload)
        self.assertIn("Content-Type: application/zlib",upload)
        self.assertEqual(client.get(ref,len(raw)),raw)

    def test_file_write_budget_charges_only_new_wire_bytes_before_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            raw=b"new immutable original"; size=len(zlib.compress(raw,9))
            client=archive.FileArchive(folder,write_budget_bytes=size)
            ref=client.put(raw,TAG)
            self.assertEqual(client.new_bytes_reserved,size)
            self.assertEqual(client.put(raw,TAG),ref)
            self.assertEqual(client.new_bytes_reserved,size)
            with self.assertRaisesRegex(IntegrityError,"write budget exhausted before mutation"):
                client.put(b"different immutable original",TAG)
            self.assertEqual(len(client.inventory()),1)

    def test_github_write_budget_rejects_before_upload_and_duplicate_costs_zero(self):
        empty=MemoryGitHub();empty.write_budget_bytes=0
        with self.assertRaisesRegex(IntegrityError,"write budget exhausted before mutation"):
            empty.put(b"nevercreatearelease",DIAGNOSTIC)
        self.assertFalse(any("POST" in args for args in empty.calls))
        client=MemoryGitHub();raw=b"new immutable original";size=len(zlib.compress(raw,9))
        client.write_budget_bytes=size
        ref=client.put(raw,DIAGNOSTIC)
        self.assertEqual(client.put(raw,DIAGNOSTIC),ref)
        before=len([row for row in client.calls if row[0].startswith("https://uploads.github.com/")])
        with self.assertRaisesRegex(IntegrityError,"write budget exhausted before mutation"):
            client.put(b"different immutable original",DIAGNOSTIC)
        after=len([row for row in client.calls if row[0].startswith("https://uploads.github.com/")])
        self.assertEqual(before,after)
        self.assertEqual(client.new_bytes_reserved,size)

    def test_full_snapshot_encoded_ceiling_blocks_publication_before_snapshot_write(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);state=root/"state";client=archive.FileArchive(root/"archive")
            path="records/input_captures/"+"a"*64+".json"
            target=state/path;target.parent.mkdir(parents=True);target.write_bytes(b'{"invented":true}')
            entries=[{"path":path,"bytes":target.stat().st_size,"sha256":hashlib.sha256(target.read_bytes()).hexdigest()}]
            store=type("SyntheticStore",(),{"root":state,"snapshot_manifest":lambda _:snapshot_fixture(entries)})()
            original=client.put_json;schemas=[]
            def observe(body,**kwargs):schemas.append(body["schema_version"]);return original(body,**kwargs)
            with patch.object(archive,"SNAPSHOT_MAX_WIRE",1),patch.object(client,"put_json",side_effect=observe):
                with self.assertRaisesRegex(IntegrityError,"reserved 128-KiB"):
                    archive.archive_snapshot(store,client,tag=TAG)
            self.assertEqual(schemas,[archive.PACK_SCHEMA])

    def test_api_guard_stops_before_transport_without_counting_a_phantom_request(self):
        client=archive.GitHubReleaseArchive();client._gh_actions=999;client._public_requests=1
        with patch.object(archive.subprocess,"run") as command:
            with self.assertRaisesRegex(IntegrityError,"action guard exhausted"):
                client._gh(["repos/this/request/must/not/run"])
        command.assert_not_called()
        self.assertEqual(client.request_metrics()["gh_api_actions"],999)

    def test_cold_file_object_reserve_and_run_budget_keep_original_readable(self):
        with tempfile.TemporaryDirectory() as folder:
            first=archive.FileArchive(folder,write_budget_objects=1)
            ref=first.put(b"retained original",TAG)
            self.assertEqual(first.new_objects_reserved,1)
            with self.assertRaisesRegex(IntegrityError,"object budget exhausted"):
                first.put(b"different original",TAG)
            self.assertEqual(first.new_objects_reserved,1)
            cold=archive.FileArchive(folder,reserved_objects=100000,write_budget_objects=0)
            self.assertFalse(cold.quota(TAG)["fits"])
            self.assertEqual(cold.get(ref,17),b"retained original")
            self.assertEqual(cold.put(b"retained original",TAG),ref)
            self.assertEqual(cold.new_objects_reserved,0)
            with self.assertRaisesRegex(IntegrityError,"quota/reserved grading"):
                cold.put(b"another original",TAG)
            self.assertEqual(len(cold.inventory()),1)

    def test_cold_mock_github_object_reserve_stops_post_not_exact_read_or_retry(self):
        first=MemoryGitHub();first.write_budget_objects=1
        ref=first.put(b"retained original",DIAGNOSTIC)
        with self.assertRaisesRegex(IntegrityError,"object budget exhausted"):
            first.put(b"different original",DIAGNOSTIC)
        self.assertEqual(first.new_objects_reserved,1)
        cold=MemoryGitHub();cold.releases=first.releases;cold.assets=first.assets;cold.raw=first.raw
        cold.reserved_objects=100000;cold.write_budget_objects=0
        self.assertFalse(cold.quota(DIAGNOSTIC)["fits"])
        self.assertEqual(cold.get(ref,17),b"retained original")
        self.assertEqual(cold.put(b"retained original",DIAGNOSTIC),ref)
        self.assertEqual(cold.new_objects_reserved,0)
        with self.assertRaisesRegex(IntegrityError,"quota/reserved grading"):
            cold.put(b"another original",DIAGNOSTIC)
        self.assertFalse(any("POST" in args for args in cold.calls))

    def test_failed_api_exposes_only_bounded_sanitized_standard_message(self):
        raw = canonical({"message": "Forbidden token=secret https://signed.invalid/?sig=private ghp_secret"})
        result = subprocess.CompletedProcess([], 1, raw, b"gh: Forbidden (HTTP 403) arbitrary secret stderr")
        with patch.object(archive.subprocess, "run", return_value=result):
            with self.assertRaises(archive.ArchiveHTTPError) as caught:
                archive.GitHubReleaseArchive()._json("repos/example")
        self.assertEqual(caught.exception.http_status, 403)
        self.assertNotIn("secret", str(caught.exception))
        self.assertNotIn("signed.invalid", str(caught.exception))
        self.assertNotIn("stderr", str(caught.exception))
        self.assertIn("[REDACTED]", str(caught.exception))

    def test_new_receipts_share_one_pack_and_old_pack_is_reused(self):
        class Store:
            def __init__(self, root): self.root = root
            def snapshot_manifest(self):
                entries = [{"path": str(p.relative_to(self.root)), "bytes": p.stat().st_size,
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                    for p in sorted((self.root / "records").rglob("*.json"))]
                return snapshot_fixture(entries)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); store=Store(root / "state"); client=archive.FileArchive(root / "archive")
            directory=store.root / "records/input_captures"; directory.mkdir(parents=True)
            for letter in "ab": (directory / (letter*64+".json")).write_bytes(canonical({"invented":letter}))
            first=archive.archive_snapshot(store,client,tag=TAG)
            manifest=client.get_json(first)
            self.assertEqual(manifest["objects"][0]["archive_ref"],manifest["objects"][1]["archive_ref"])
            self.assertEqual([x["index"] for x in manifest["objects"]],[0,1])
            (directory / ("c"*64+".json")).write_bytes(canonical({"invented":"c"}))
            second=archive.archive_snapshot(store,client,tag=TAG,previous=first)
            self.assertEqual(client.get_json(second)["objects"][:2],manifest["objects"])
            self.assertEqual(len(client.inventory()),4) # Two immutable packs, two snapshots.

    def test_snapshot_cannot_drop_original_and_failure_preserves_uploaded_receipts(self):
        class Store:
            def __init__(self, root):
                self.root = root
            def snapshot_manifest(self):
                path = "records/input_captures/" + "a" * 64 + ".json"
                raw = (self.root / path).read_bytes()
                return snapshot_fixture([{"path":path,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "state/records/input_captures" / ("a" * 64 + ".json")
            target.parent.mkdir(parents=True)
            target.write_bytes(b'{"synthetic":"receipt"}')
            client = archive.FileArchive(root / "archive")
            store = Store(root / "state")
            first = archive.archive_snapshot(store, client, tag=TAG)
            self.assertEqual(archive.archive_snapshot(store, client, tag=TAG, previous=first), first)
            target.write_bytes(b'{"replaced":"original"}')
            with self.assertRaisesRegex(IntegrityError, "erase or replace"):
                archive.archive_snapshot(store, client, tag=TAG, previous=first)
            self.assertEqual(len(client.inventory()), 2)


if __name__ == "__main__":
    unittest.main()

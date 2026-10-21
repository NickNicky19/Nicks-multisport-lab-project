"""Synthetic bytes and ephemeral keys only; no provider requests or issuance."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import operational_pilot as op
from multisport_lab import operational_raw as raw
from multisport_lab.integrity import IntegrityError, digest
from multisport_lab.operational_source_links import EncryptedSourceLinks, canonical_source_inventory, _source_route
from test_operational_pilot import OperationalFixture
from test_pros004_inputs import NOW


class OperationalSourceLinksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("openssl") is None:
            raise unittest.SkipTest("OpenSSL CMS is required")
        cls.key_directory = tempfile.TemporaryDirectory(prefix="nml-source-link-keys-")
        directory = Path(cls.key_directory.name)
        cls.key, cls.cert = directory / "private.pem", directory / "recipient.pem"
        cls.wrong_key = directory / "wrong.pem"
        for key, cert in ((cls.key, cls.cert), (cls.wrong_key, directory / "wrong-recipient.pem")):
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:3072", "-sha256",
                            "-days", "1", "-nodes", "-keyout", str(key), "-out", str(cert),
                            "-subj", "/CN=OP002 synthetic source-link test"],
                           capture_output=True, check=True, timeout=30)
            key.chmod(0o600)

    @classmethod
    def tearDownClass(cls):
        cls.key_directory.cleanup()

    def setUp(self):
        # The existing fixture replaces the full history with three invented
        # rows. It does not generate forecasts or execute a timing diagnostic.
        self.fixture = OperationalFixture(self, acknowledge_event=False)
        self.fixture.at(NOW)
        self.raw_clock = patch.object(raw, "_now", side_effect=lambda: self.fixture.clock.return_value)
        self.raw_clock.start()
        self.addCleanup(self.raw_clock.stop)
        self.archive = raw.EncryptedRawArchive(self.fixture.root / "encrypted", self.cert, private_key=self.key)
        self.links = EncryptedSourceLinks(self.fixture.root, self.archive, diagnostic=True)

    def retained(self, observation=None, *, event_id=None, mode="SYNTHETIC_DIAGNOSTIC"):
        observation = deepcopy(observation or self.fixture.observations[0])
        source = observation["metadata"]
        ref = self.archive.retain(observation["raw"], mode=mode,
            event_id=event_id or self.fixture.plan["event"]["event_id"],
            source_url=source["source_url"], request_started_at=source["request_started_at"],
            observed_at=source["observed_at"], source_updated_at=source["source_updated_at"])
        return ref, source

    def all_links(self, observations=None):
        return tuple(self.links.link(*self.retained(item)) for item in (observations or self.fixture.observations))

    def forged_link(self, body):
        body = op.seal({key: value for key, value in body.items() if key != "link_id"}, "link_id")
        return self.links.ledger.append("input_captures", "op002-source-link:" + body["link_id"],
            {"identity": self.links._identity(body), "encrypted_source_link": body})

    def test_four_authenticated_inputs_bind_and_recover_in_independent_copy(self):
        refs = self.all_links()
        expected = sorted(self.fixture.observations, key=lambda item: item["source_id"])
        self.assertEqual(self.links.observations(self.fixture.plan, refs, mode="SYNTHETIC_DIAGNOSTIC"), expected)
        binding = self.links.bind_event(self.fixture.event_ref, refs)
        original = {str(p.relative_to(self.fixture.root)): p.read_bytes()
                    for p in self.fixture.root.rglob("*") if p.is_file() and ".local-data" not in p.parts}
        with tempfile.TemporaryDirectory(prefix="nml-source-link-readback-") as temporary:
            fetched = Path(temporary) / "independent"
            shutil.copytree(self.fixture.root, fetched)
            archive = raw.EncryptedRawArchive(fetched / "encrypted", self.cert, private_key=self.key)
            recovered = EncryptedSourceLinks(fetched, archive).recover_binding(binding)
            self.assertEqual(recovered["event"], self.fixture.event)
            self.assertEqual(recovered["event_ref"], self.fixture.event_ref)
            self.assertEqual(recovered["observations"], expected)
            self.assertEqual(original, {str(p.relative_to(fetched)): p.read_bytes()
                for p in fetched.rglob("*") if p.is_file() and ".local-data" not in p.parts})
        self.assertEqual(original, {str(p.relative_to(self.fixture.root)): p.read_bytes()
            for p in self.fixture.root.rglob("*") if p.is_file() and ".local-data" not in p.parts})

    def test_identical_retry_retains_original_link_and_binding_clocks(self):
        refs = self.all_links()
        binding = self.links.bind_event(self.fixture.event_ref, refs)
        originals = {ref: self.links.ledger._path(ref.kind, ref.record_id).read_bytes() for ref in (*refs, binding)}
        self.fixture.at(NOW + timedelta(seconds=2))
        self.assertEqual(self.all_links(), refs)
        self.assertEqual(self.links.bind_event(self.fixture.event_ref, reversed(refs)), binding)
        self.assertEqual(originals, {ref: self.links.ledger._path(ref.kind, ref.record_id).read_bytes()
                                     for ref in (*refs, binding)})

    def test_missing_wrong_key_or_changed_ciphertext_cannot_recover_source(self):
        raw_ref, metadata = self.retained()
        reference = self.links.link(raw_ref, metadata)
        wrong_archive = raw.EncryptedRawArchive(self.archive.root, self.cert, private_key=self.wrong_key)
        with self.assertRaises(IntegrityError):
            EncryptedSourceLinks(self.fixture.root, wrong_archive).read(reference)
        path = self.archive._cipher(raw_ref["cipher_sha256"])
        original = path.read_bytes()
        path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        with self.assertRaises(IntegrityError):
            self.links.read(reference)
        path.unlink()
        with self.assertRaises(IntegrityError):
            self.links.read(reference)

    def test_resealed_link_cannot_change_archived_clocks_hash_url_event_or_mode(self):
        reference = self.links.link(*self.retained())
        original = self.links.read(reference)["body"]
        for field, value in (("source_url", "https://site.api.espn.com/another-route"),
                             ("request_started_at", original["source"]["observed_at"]),
                             ("raw_sha256", "a" * 64)):
            with self.subTest(field=field):
                forged = deepcopy(original)
                forged["source"][field] = value
                with self.assertRaises(IntegrityError):
                    self.links.read(self.forged_link(forged))
        for field, value in (("event_id", "999001"), ("mode", "READINESS_DIAGNOSTIC")):
            with self.subTest(field=field):
                forged = deepcopy(original)
                forged[field] = value
                with self.assertRaisesRegex(IntegrityError, "archived event or evidence mode"):
                    self.links.read(self.forged_link(forged))

    def test_missing_duplicate_or_wrong_lane_inputs_reject(self):
        refs = self.all_links()
        for changed in (refs[:3], (*refs[:3], refs[0])):
            with self.assertRaisesRegex(IntegrityError, "four distinct"):
                self.links.observations(self.fixture.plan, changed, mode="SYNTHETIC_DIAGNOSTIC")
        with self.assertRaisesRegex(IntegrityError, "evidence mode"):
            self.links.observations(self.fixture.plan, refs, mode="READINESS_DIAGNOSTIC")
        duplicate_source = deepcopy(self.fixture.observations[-1])
        duplicate_source["metadata"]["source_id"] = self.fixture.observations[0]["source_id"]
        duplicate = self.links.link(*self.retained(duplicate_source))
        with self.assertRaisesRegex(IntegrityError, "duplicate or foreign"):
            self.links.observations(self.fixture.plan, (*refs[:3], duplicate), mode="SYNTHETIC_DIAGNOSTIC")

    def test_wrong_summary_route_or_archived_event_rejects_even_with_matching_bytes(self):
        observations = deepcopy(self.fixture.observations)
        summary = next(item for item in observations if item["source_id"] == "summary")
        summary["metadata"]["source_url"] = summary["metadata"]["source_url"].replace("401900001", "999001")
        with self.assertRaisesRegex(IntegrityError, "source route"):
            self.links.observations(self.fixture.plan, self.all_links(observations), mode="SYNTHETIC_DIAGNOSTIC")
        refs = self.all_links()
        foreign = self.links.link(*self.retained(event_id="999001"))
        with self.assertRaisesRegex(IntegrityError, "planned event"):
            self.links.observations(self.fixture.plan, (foreign, *refs[1:]), mode="SYNTHETIC_DIAGNOSTIC")

    def test_explicit_season_and_bounded_calendar_routes_replay_actual_intended_formats(self):
        inventory = canonical_source_inventory(self.fixture.plan, scoreboard_date="20261021")
        self.assertTrue(inventory["scoreboard"].endswith("?dates=20261021&limit=1000"))
        self.assertTrue(inventory["roster-8"].endswith("/teams/8/roster?season=2027"))
        observations = deepcopy(self.fixture.observations)
        for item in observations:
            item["metadata"]["source_url"] = inventory[item["source_id"]]
        refs = self.all_links(observations)
        self.assertEqual(self.links.observations(self.fixture.plan, refs, mode="SYNTHETIC_DIAGNOSTIC",
            expected_routes=inventory), sorted(observations, key=lambda item: item["source_id"]))
        event = op.make_event_body(self.fixture.plan, self.fixture.history_ref, observations, mode="SYNTHETIC_DIAGNOSTIC")
        self.links.verify_event(event, refs, expected_routes=inventory)
        wrong_day = canonical_source_inventory(self.fixture.plan, scoreboard_date="20261022")
        with self.assertRaisesRegex(IntegrityError, "reviewed exact source inventory"):
            self.links.observations(self.fixture.plan, refs, mode="SYNTHETIC_DIAGNOSTIC", expected_routes=wrong_day)

    def test_routes_reject_wrong_season_repeated_foreign_empty_and_fragment_queries(self):
        inventory = canonical_source_inventory(self.fixture.plan, scoreboard_date="20261021")
        for name, url in inventory.items():
            _source_route(self.fixture.plan, name, url, mode="REAL_TIME_CAPTURED")
        invalid = [("roster-8", inventory["roster-8"].replace("2027", "2026")),
                   ("roster-8", inventory["roster-8"].split("?")[0]),
                   ("roster-8", inventory["roster-8"] + "&season=2027"),
                   ("summary", inventory["summary"] + "&event=401900001"),
                   ("summary", inventory["summary"] + "#ignored"),
                   ("scoreboard", inventory["scoreboard"] + "&dates=20261021"),
                   ("scoreboard", inventory["scoreboard"].replace("limit=1000", "limit=")),
                   ("scoreboard", inventory["scoreboard"] + "&groups=all"),
                   ("scoreboard", inventory["scoreboard"].replace("20261021", "20260230"))]
        for name, url in invalid:
            with self.subTest(url=url), self.assertRaises(IntegrityError):
                _source_route(self.fixture.plan, name, url, mode="REAL_TIME_CAPTURED")
        with self.assertRaisesRegex(IntegrityError, "reviewed exact source inventory"):
            self.links.observations(self.fixture.plan, self.all_links(), mode="REAL_TIME_CAPTURED")

    def test_recovered_player_cohort_and_event_metadata_are_replayed(self):
        refs = self.all_links()
        plan = deepcopy(self.fixture.plan)
        plan["candidates"][0]["player_label"] = "Wrong supplied label"
        plan = op.seal({key: value for key, value in plan.items() if key != "plan_id"}, "plan_id")
        with self.assertRaisesRegex(IntegrityError, "player cohort"):
            self.links.observations(plan, refs, mode="SYNTHETIC_DIAGNOSTIC")
        event = deepcopy(self.fixture.event)
        event["sources"][0]["etag"] = "different-retained-header"
        event = op.seal({key: value for key, value in event.items() if key != "event_input_id"}, "event_input_id")
        with self.assertRaisesRegex(IntegrityError, "original event inputs"):
            self.links.verify_event(event, refs)

    def test_resealed_event_binding_cannot_swap_source_reference_labels(self):
        binding = self.links.bind_event(self.fixture.event_ref, self.all_links())
        body = deepcopy(self.links.ledger.read(binding)["data"]["event_source_links"])
        names = sorted(body["source_refs"])
        body["source_refs"][names[0]], body["source_refs"][names[1]] = body["source_refs"][names[1]], body["source_refs"][names[0]]
        body = op.seal({key: value for key, value in body.items() if key != "binding_id"}, "binding_id")
        from multisport_lab.ledger import LedgerRef
        refs = (self.fixture.event_ref, *(LedgerRef.from_record(body["source_refs"][name]) for name in names))
        forged = self.links.ledger.append("input_captures", "op002-event-source-links:" + body["binding_id"],
                                         {"event_source_links": body}, references=refs)
        with self.assertRaisesRegex(IntegrityError, "source names"):
            self.links.recover_binding(forged)

    def test_offer_reader_preserves_original_metadata_and_requires_explicit_lane(self):
        raw_ref, metadata = self.retained()
        reference = self.links.link(raw_ref, metadata)
        with self.assertRaisesRegex(IntegrityError, "different evidence mode"):
            self.links.offer_reader(reference)
        recovered = self.links.offer_reader(reference, mode="SYNTHETIC_DIAGNOSTIC")
        archive_metadata, original = self.archive.read(raw_ref)
        self.assertEqual(recovered["raw"], original)
        self.assertEqual(recovered["metadata"], {**metadata, "imported_at": archive_metadata["imported_at"]})

    def test_both_existing_writer_locks_prevent_concurrent_link_creation(self):
        args = self.retained()
        before = self.links.ledger._inventory()[1:]
        for store, message in ((self.links.store, "another OP002 writer"), (self.links.peer, "another PROS004 writer")):
            with self.subTest(writer=message), store.single_writer(), self.assertRaisesRegex(IntegrityError, message):
                self.links.link(*args)
        self.assertEqual(before, self.links.ledger._inventory()[1:])

    def test_links_count_shared_metadata_in_capacity_before_writing(self):
        args = self.retained()
        count = self.links.ledger._inventory()[1]
        metadata_count = op.metadata_inventory(self.fixture.root)["file_count"]
        self.assertGreater(metadata_count, 0)
        with patch.object(op, "MAX_LEDGER_RECORDS", count + metadata_count):
            with self.assertRaisesRegex(IntegrityError, "shared ledger limits"):
                self.links.link(*args)
        self.assertEqual(count, self.links.ledger._inventory()[1])
        size = self.links.ledger._inventory()[2] + op.metadata_inventory(self.fixture.root)["total_bytes"]
        with patch.object(op, "MAX_LEDGER_BYTES", size):
            with self.assertRaisesRegex(IntegrityError, "shared ledger limits"):
                self.links.link(*args)
        self.assertEqual(count, self.links.ledger._inventory()[1])

    def test_default_store_rejects_diagnostic_write_and_genuine_guard_stays_closed(self):
        args = self.retained()
        with self.assertRaisesRegex(IntegrityError, "isolated diagnostic"):
            EncryptedSourceLinks(self.fixture.root, self.archive).link(*args)
        body, original = self.archive.read(args[0])
        # An injected claim of a genuine archive cannot authorize a new link.
        with patch.object(self.archive, "read", return_value=({**body, "mode": "REAL_TIME_CAPTURED"}, original)):
            with self.assertRaisesRegex(IntegrityError, "NO_REVIEWED_ACTIVATION_INSTALLED"):
                self.links.link(*args)


if __name__ == "__main__":
    unittest.main()

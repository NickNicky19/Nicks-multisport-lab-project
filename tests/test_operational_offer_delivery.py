"""Invented HTML/JSON offer bridge with ephemeral encryption; no model or HTTP."""
from datetime import datetime
from functools import partial
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import offer_publication as offers
from multisport_lab import operational_delivery as delivery
from multisport_lab import operational_pilot as op
from multisport_lab import operational_publication as publication
from multisport_lab import operational_raw as raw
from multisport_lab.integrity import IntegrityError, canonical, stamp
from multisport_lab.operational_source_links import EncryptedSourceLinks
from test_offer_publication import finish, text_rules_fixture
from test_operational_pilot import OperationalFixture
from test_pros004_inputs import NOW


class OperationalOfferDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("openssl") is None:
            raise unittest.SkipTest("OpenSSL CMS is required")
        cls.keys = tempfile.TemporaryDirectory(prefix="nml-offer-bridge-keys-")
        folder = Path(cls.keys.name)
        cls.key, cls.cert = folder / "private.pem", folder / "recipient.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:3072", "-sha256",
                        "-days", "1", "-nodes", "-keyout", str(cls.key), "-out", str(cls.cert),
                        "-subj", "/CN=OP002 synthetic HTML offer integration"],
                       capture_output=True, check=True, timeout=30)
        cls.key.chmod(0o600)

    @classmethod
    def tearDownClass(cls):
        cls.keys.cleanup()

    def test_encrypted_json_and_html_offer_recovery_remains_separate_from_forecasts(self):
        self.enterContext(patch.object(op, "generate_forecast",
                                       side_effect=AssertionError("no forecast generation in this test")))
        fixture = OperationalFixture(self, acknowledge_event=False)
        fixture.at(NOW)
        self.enterContext(patch.object(raw, "_now", return_value=NOW))
        offer_clock = self.enterContext(patch.object(offers, "datetime", wraps=datetime))
        offer_clock.now.return_value = NOW
        archive = raw.EncryptedRawArchive(fixture.root / delivery.ARCHIVE_DIRECTORY,
                                          self.cert, private_key=self.key)
        links = EncryptedSourceLinks(fixture.root, archive, diagnostic=True)

        def retain(original, source):
            reference = archive.retain(original, mode="SYNTHETIC_DIAGNOSTIC",
                event_id=fixture.plan["event"]["event_id"], source_url=source["source_url"],
                request_started_at=source["request_started_at"], observed_at=source["observed_at"],
                source_updated_at=source["source_updated_at"])
            return reference, links.link(reference, source)

        # The existing fixture supplies three invented historical rows and four
        # invented event inputs. Their recovery needs neither an offer nor odds.
        event_refs = [retain(item["raw"], item["metadata"])[1] for item in fixture.observations]
        event_binding = links.bind_event(fixture.event_ref, event_refs)
        before_event = links.recover_binding(event_binding)
        before_forecasts = publication.make_asset(fixture.root, now=NOW)
        reader = partial(links.offer_reader, mode="SYNTHETIC_DIAGNOSTIC")
        store = offers.OfferStore(fixture.root, allow_synthetic=True, raw_reader=reader)
        self.assertEqual(store.active(), [])

        offer, admission, _, retained_rules = text_rules_fixture(media_type="text/html")
        offer.update({name: fixture.plan["event"][name]
                      for name in ("event_id", "event_version", "event_starts_at")})
        offer.update(fixture.plan["candidates"][0])
        clock_source = fixture.observations[0]["metadata"]
        offer.update(observed_at=clock_source["observed_at"], imported_at=stamp(NOW))
        admission["reviewed_at"] = stamp(NOW)
        original_json = canonical({"fields": {name: offers._target(offer, name)
                                                for name in offers.BOUND_FIELDS}})
        originals = {"contract": original_json, "rules": retained_rules["raw"]}
        captures, references, metadata = {}, {}, {}
        for name, original in originals.items():
            # These are invented, unrequested routes on an allowed archive host.
            source = {**clock_source, "source_id": "synthetic-offer-" + name,
                "source_url": "https://site.api.espn.com/synthetic-op002-offer/" + name,
                "raw_sha256": hashlib.sha256(original).hexdigest(), "raw_bytes": len(original)}
            captures[name], references[name] = retain(original, source)
            metadata[name] = source
        for evidence in offer["source_evidence"]:
            name = "rules" if evidence["kind"] == "RULES" else "contract"
            evidence.update({key: metadata[name][key] for key in
                ("source_url", "raw_sha256", "raw_bytes", "request_started_at", "observed_at", "source_updated_at")})
            evidence["raw_record_id"] = references[name].record_id
            if name == "contract":
                for field, binding in evidence["bindings"].items():
                    binding.update(source_value=offers._target(offer, field), meaning=offers._target(offer, field))
        offer, admission = finish(offer, admission)
        reference = store.persist(offer, admission, raw_references=tuple(references.values()))
        original_record = store.ledger._path(reference.kind, reference.record_id).read_bytes()
        snapshot = delivery.delivery_snapshot(fixture.root, self.cert)
        self.assertEqual(store.active()[0][1]["offer"], offer)
        self.assertEqual(offer["evidence_lane"], "SYNTHETIC_TEST")
        self.assertEqual(offer["price_status"], "PRICE_UNAVAILABLE")
        self.assertIsNone(offer["price"])
        self.assertIsNone(offer["quote"])
        self.assertEqual(offer["qualification"], "UNAVAILABLE")

        # Independent copied-root readback uses the actual CMS decryptor and
        # source-link reader for both JSON identity/contract and HTML RULES.
        # This is local recovery evidence, not a host or GitHub delivery claim.
        with tempfile.TemporaryDirectory(prefix="nml-offer-bridge-readback-") as temporary:
            fetched = Path(temporary) / "fetched"
            shutil.copytree(fixture.root, fetched)
            recovered_archive = raw.EncryptedRawArchive(fetched / delivery.ARCHIVE_DIRECTORY,
                                                         self.cert, private_key=self.key)
            recovered_links = EncryptedSourceLinks(fetched, recovered_archive)
            recovered_reader = partial(recovered_links.offer_reader, mode="SYNTHETIC_DIAGNOSTIC")
            recovered_store = offers.OfferStore(fetched, allow_synthetic=True, raw_reader=recovered_reader)
            self.assertEqual(recovered_store.active()[0][1]["offer"], offer)
            self.assertEqual(recovered_store.ledger._path(reference.kind, reference.record_id).read_bytes(),
                             original_record)
            for name, source_ref in references.items():
                recovered = recovered_reader(source_ref)
                self.assertEqual(recovered["raw"], originals[name])
                self.assertEqual(recovered["metadata"], {**metadata[name], "imported_at": stamp(NOW)})
            verified = delivery.verify_delivery(fetched, self.cert, self.key,
                                                 plan=fixture.plan, diagnostic=True)
            self.assertEqual(verified["authenticated_captures"], 6)
            self.assertEqual(verified["source_links"], 6)
            self.assertEqual(verified["bound_event_inputs"], 1)
            self.assertFalse(verified["genuine_execution_enabled"])
            self.assertEqual(verified["typed_records"]["genuine_issued"], 0)
            self.assertEqual(verified["snapshot"], snapshot)

        # Broken/missing encrypted evidence rejects the offer. The independently
        # bound statistical inputs and forecast-only export still recover with
        # their original result; no offer/price prerequisite is introduced.
        for name, capture in captures.items():
            path = archive._cipher(capture["cipher_sha256"])
            original_cipher = path.read_bytes()
            for damage in ("tampered", "missing"):
                with self.subTest(source=name, damage=damage):
                    try:
                        if damage == "tampered":
                            path.write_bytes(original_cipher[:-1] + bytes([original_cipher[-1] ^ 1]))
                        else:
                            path.unlink()
                        with self.assertRaises(IntegrityError):
                            store.active()
                        self.assertEqual(links.recover_binding(event_binding), before_event)
                        self.assertEqual(publication.make_asset(fixture.root, now=NOW), before_forecasts)
                    finally:
                        path.write_bytes(original_cipher)
        self.assertEqual(store.persist(offer, admission, raw_references=tuple(references.values())), reference)
        self.assertEqual(store.ledger._path(reference.kind, reference.record_id).read_bytes(), original_record)
        self.assertEqual(delivery.delivery_snapshot(fixture.root, self.cert), snapshot)
        index = store.ledger.scan()
        self.assertTrue(all(not index[kind] for kind in ("forecasts", "outcomes", "grades")))


if __name__ == "__main__":
    unittest.main()

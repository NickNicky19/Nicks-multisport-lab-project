"""Synthetic exact-route retained-byte joins and interrupted local recovery."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab.gamma_semantic_review import build_contract, persist_review
from multisport_lab.integrity import IntegrityError, canonical, read_receipt, write_receipt
from test_gamma_offer_review import write_bundle

NOW = datetime(2026, 10, 21, 14, tzinfo=timezone.utc)
CONDITION = "0x" + "ab" * 32


def bundles(root):
    prior, new = root / "prior", root / "supplement"
    prior.mkdir(); new.mkdir()
    def change(data):
        for market in (data["gamma-edwards-market"], data["gamma-game-event"]["markets"][0]):
            market["conditionId"] = CONDITION
        data["gamma-game-event"]["version"] = "fictional-source-v1"
    write_bundle(prior, change)
    ledger = json.loads((prior / "requests.json").read_bytes())
    for entry in ledger["requests"]:
        entry["content_type"] = "application/json"
        (prior / (entry["label"] + ".metadata.json")).write_bytes(canonical(entry))
    (prior / "requests.json").write_bytes(canonical(ledger))
    specs = (
        ("clob-market-info-doc", "https://docs.polymarket.com/api-reference/markets/get-clob-market-info", 200, b"Fictional official documentation.", "text/html"),
        ("polymarket-help-root", "https://help.polymarket.com", 302, b"", "text/html"),
        ("polymarket-help-en", "https://help.polymarket.com/en/", 200, b"Fictional help index.", "text/html"),
        ("clob-selected-market", "https://clob.polymarket.com/clob-markets/" + CONDITION, 200,
         canonical({"c": CONDITION, "gst": "2026-10-21T23:30:00Z",
                    "t": [{"o": "No", "t": "22222"}, {"o": "Yes", "t": "11111"}]}), "application/json"),
    )
    entries = []
    for ordinal, (label, url, status, raw, mime) in enumerate(specs, 1):
        entry = {"ordinal": ordinal, "label": label, "url": url, "final_url": url,
            "content_type": mime, "http_status": status, "raw_bytes": len(raw),
            "raw_sha256": hashlib.sha256(raw).hexdigest(), "complete_body": True,
            "request_started_at": f"2026-10-21T12:00:0{ordinal}.000000Z",
            "observed_at": f"2026-10-21T12:00:0{ordinal}.000001Z",
            "automatic_redirects": False, "retries": 0}
        if ordinal == 2:
            entry["location"] = "https://help.polymarket.com/en/"
        (new / (label + ".body")).write_bytes(raw)
        (new / (label + ".metadata.json")).write_bytes(canonical(entry))
        entries.append(entry)
    supplement = {"limit": 4, "max_response_bytes": 2097152,
        "parent_request_ledger_sha256": hashlib.sha256((prior / "requests.json").read_bytes()).hexdigest(),
        "requests": entries}
    (new / "requests.json").write_bytes(canonical(supplement))
    (new / "clob-source-decision.json").write_bytes(canonical({
        "decision": "ALLOW_EXACT_PUBLIC_CREDENTIALLESS_INFORMATIONAL_GET",
        "exact_url": specs[-1][1], "recorded_at": "2026-10-21T12:00:03.500000Z",
        "public_redistribution_admitted": False}))
    return prior, new


def reseal_original(directory, label, change):
    path = directory / (label + ".body")
    value = json.loads(path.read_bytes()); change(value)
    raw = canonical(value); path.write_bytes(raw)
    ledger = json.loads((directory / "requests.json").read_bytes())
    entry = next(x for x in ledger["requests"] if x["label"] == label)
    entry.update(raw_bytes=len(raw), raw_sha256=hashlib.sha256(raw).hexdigest())
    (directory / (label + ".metadata.json")).write_bytes(canonical(entry))
    (directory / "requests.json").write_bytes(canonical(ledger))


class GammaSemanticReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.prior, self.new = bundles(self.root)

    def build(self, now=NOW):
        return build_contract(self.prior, self.new, now=now, evidence_lane="SYNTHETIC")

    def test_new_mapping_is_later_enrichment_not_completion_or_old_price_assignment(self):
        c, replay = self.build()
        self.assertEqual(c["player"]["canonical_identity"]["id"], "Q123456")
        self.assertIsNone(c["player"]["native_provider_id"])
        self.assertEqual(c["selection"]["native_token_id"], "11111")
        self.assertEqual(c["selection"]["outcome_label"], "Yes")
        self.assertEqual(c["price"], {"status": "PRICE_UNAVAILABLE", "value": None})
        self.assertEqual(c["unassigned_source_economics"]["outcome_prices"][0], "0.6100000000000000001")
        self.assertEqual(c["required_gaps"], ["PLAYER_TEAM", "PLAYER_OPPONENT", "EVENT_VERSION", "SETTLEMENT_STAT_CORRECTIONS"])
        self.assertEqual(c["contract_observed_at"], "2026-10-21T11:00:00.000001Z")
        self.assertEqual(c["knowledge_observed_at"], "2026-10-21T12:00:04.000001Z")
        self.assertEqual(c["semantic_status"], "INCOMPLETE")
        self.assertIsNone(c["completed_at"])
        self.assertEqual(replay["originals_verified"], 8)

    def test_checksum_consistent_wrong_condition_start_and_conflicting_token_set_are_rejected(self):
        for change in (lambda x: x.update(c="0x" + "cd" * 32),
                       lambda x: x.update(gst="2026-10-22T23:30:00Z"),
                       lambda x: x["t"][0].update(t="33333"),
                       lambda x: x["t"][0].update(o="Yes")):
            with self.subTest(change=change):
                old = {p.name:p.read_bytes() for p in self.new.iterdir()}
                reseal_original(self.new, "clob-selected-market", change)
                with self.assertRaises(IntegrityError): self.build()
                for name, raw in old.items(): (self.new / name).write_bytes(raw)

    def test_missing_scope_precedence_and_changed_parent_binding_are_not_waived(self):
        decision = self.new / "clob-source-decision.json"
        original = decision.read_bytes()
        for change in (lambda d:d.update(recorded_at="2026-10-21T12:00:05.000000Z"),
                       lambda d:d.update(exact_url="https://clob.polymarket.com/other"),
                       lambda d:d.update(public_redistribution_admitted=True)):
            d=json.loads(original);change(d);decision.write_bytes(canonical(d))
            with self.assertRaises(IntegrityError): self.build()
        decision.write_bytes(original)
        p=self.prior / "requests.json";p.write_bytes(p.read_bytes()+b" ")
        with self.assertRaises(IntegrityError): self.build()

    def test_counter_redirect_and_late_knowledge_cannot_be_rewritten(self):
        p=self.new / "requests.json"; original=p.read_bytes()
        for change in (lambda d:d.update(limit=5), lambda d:d["requests"].pop(),
                       lambda d:d["requests"][1].update(location="https://example.invalid/")):
            d=json.loads(original);change(d);p.write_bytes(canonical(d))
            # Sidecar mismatch also invalidates the claimed ledger change.
            with self.assertRaises(IntegrityError): self.build()
        p.write_bytes(original)
        with self.assertRaises(IntegrityError):
            self.build(now=datetime(2026,10,21,11,59,tzinfo=timezone.utc))

    def test_interrupted_write_recovers_same_content_and_clocks_then_is_idempotent(self):
        destination=self.root / ".local-data/review"
        def interrupt(path, value):
            if path.name=="replay.receipt.json": raise RuntimeError("Synthetic interruption after original receipt")
            return write_receipt(path,value)
        with patch("multisport_lab.gamma_semantic_review.write_receipt", side_effect=interrupt):
            with self.assertRaises(RuntimeError):
                persist_review(self.prior,self.new,destination,now=NOW,source_root=self.root,evidence_lane="SYNTHETIC")
        original=(destination / "contract.receipt.json").read_bytes()
        first=read_receipt(destination / "contract.receipt.json")
        recovered=persist_review(self.prior,self.new,destination,now=NOW+timedelta(hours=1),source_root=self.root,evidence_lane="SYNTHETIC")
        self.assertTrue(recovered["recovered_existing"])
        self.assertEqual((destination / "contract.receipt.json").read_bytes(),original)
        self.assertEqual(recovered["normalized_at"],first["normalized_at"])
        self.assertEqual(recovered["contract_id"],first["contract_id"])
        again=persist_review(self.prior,self.new,destination,now=NOW+timedelta(hours=2),source_root=self.root,evidence_lane="SYNTHETIC")
        self.assertEqual(again,recovered)
        (destination / "contract.json").write_text("changed")
        with self.assertRaises(IntegrityError):
            persist_review(self.prior,self.new,destination,now=NOW+timedelta(hours=3),source_root=self.root,evidence_lane="SYNTHETIC")

    def test_output_confinement_refuses_public_paths_and_symlinked_local_parent(self):
        with self.assertRaises(IntegrityError):
            persist_review(self.prior,self.new,self.root / "public",now=NOW,source_root=self.root,evidence_lane="SYNTHETIC")
        target=self.root / "outside";target.mkdir()
        (self.root / ".local-data").symlink_to(target,target_is_directory=True)
        with self.assertRaises(IntegrityError):
            persist_review(self.prior,self.new,self.root / ".local-data/review",now=NOW,source_root=self.root,evidence_lane="SYNTHETIC")
        self.assertEqual(list(target.iterdir()),[])


if __name__ == "__main__":
    unittest.main()

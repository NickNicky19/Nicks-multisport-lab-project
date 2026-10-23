"""Invented catalogue/rule fixtures exercise offline private source replay only."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab import player_line_enrichment as enrichment
from multisport_lab import player_line_review as base
from multisport_lab.integrity import IntegrityError, canonical, digest, stamp
from test_player_line_review import OBSERVED, original, source_row

CAPTURED = OBSERVED+timedelta(minutes=3)
NOW = OBSERVED+timedelta(minutes=4)


class PlayerLineEnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.inputs = self.root/"inputs"; self.inputs.mkdir()
        self.base = self.root/".local-data"/"base"; self.destination = self.root/".local-data"/"enrichment"

    @staticmethod
    def player(identity="1001", **overrides):
        return {"player_id": identity, "sport": "nba", "position": "SF", "first_name": "Test", "last_name": "Player",
                "full_name": "Test Player", "team": "Fictional Team", **overrides}

    def write_asset(self, key, raw, observed=CAPTURED):
        body = self.inputs/(key+".body"); meta = self.inputs/(key+".metadata.json")
        body.write_bytes(raw)
        metadata = {"url": enrichment.SOURCES[key], "final_url": enrichment.SOURCES[key], "http_status": 200,
                    "content_type": "application/json" if key == "catalogue" else "text/html", "complete_body": True,
                    "request_started_at": stamp(observed-timedelta(seconds=1)), "observed_at": stamp(observed),
                    "raw_sha256": hashlib.sha256(raw).hexdigest(), "raw_bytes": len(raw)}
        meta.write_bytes(canonical(metadata)); return body, meta

    def setup_sources(self, *, rows=None, catalogue=None, limit=32):
        raw, meta = original(rows)
        source = self.inputs/"board.body"; metadata = self.inputs/"board.metadata.json"
        source.write_bytes(raw); metadata.write_bytes(meta)
        base.build_preview(destination=self.base, source_root=self.root, now=OBSERVED+timedelta(minutes=2),
                           body=source, metadata=metadata, limit=limit)
        assets = {"catalogue": self.write_asset("catalogue", canonical(catalogue if catalogue is not None else {"1001": self.player()}))}
        for key in ("picks_rules", "stats_rules"):
            text = " ".join(v for k,v in enrichment.WITNESSES.values() if k == key)
            text = text.replace("Quarter Markets:", "<strong>Quarter Markets</strong>:")
            assets[key] = self.write_asset(key, ("<html><body>"+text+"</body></html>").encode())
        return assets

    def build(self, **options):
        assets = self.setup_sources(**options)
        result = enrichment.build_enrichment(base_directory=self.base, destination=self.destination,
                                            source_root=self.root, assets=assets, now=NOW)
        body = json.loads((self.destination/"enrichment.json").read_bytes())
        return result, body, assets

    def inventory(self, directory):
        return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir()}

    def test_names_later_clocks_unknown_event_and_immutable_originals(self):
        assets = self.setup_sources(); before = self.inventory(self.base)
        result = enrichment.build_enrichment(base_directory=self.base, destination=self.destination,
                                            source_root=self.root, assets=assets, now=NOW)
        body = json.loads((self.destination/"enrichment.json").read_bytes()); row = body["observations"][0]
        self.assertEqual(row["player_label"], "Test Player")
        self.assertEqual((row["league"], row["namespace"], row["provider_player_id"]), ("NBA", "sleeper", "1001"))
        self.assertEqual(row["period"], "UNKNOWN"); self.assertEqual(row["overtime"], "UNKNOWN")
        self.assertIsNone(row["event_label"]); self.assertIsNone(row["event_starts_at"])
        self.assertFalse(row["ticket_eligible"]); self.assertIn("native_event_mapping", row["missing_fields"])
        self.assertEqual(body["base"]["observed_at"], stamp(OBSERVED))
        self.assertEqual(body["sources"]["catalogue"]["observed_at"], stamp(CAPTURED))
        self.assertEqual(body["sources"]["catalogue"]["upstream_observed_at"], None)
        self.assertEqual(self.inventory(self.base), before)
        self.assertEqual(result["recovery"], "LOCAL_ORIGINAL_SOURCE_REPLAY_VERIFIED")
        self.assertFalse(result["durable_remote_archive_verified"])
        self.assertLess(result["combined_package_bytes"], base.MAX_PACKAGE_BYTES)

    def test_explicit_q1_excludes_overtime_normal_is_not_full_game(self):
        _, body, _ = self.build(rows=[source_row("first_qtr_points"), source_row("points")])
        self.assertEqual([r["period"] for r in body["observations"]], ["Q1", "Q1", "UNKNOWN", "UNKNOWN"])
        self.assertEqual(body["observations"][0]["period_evidence"], ["q1", "quarter_overtime"])
        self.assertEqual(body["counts"]["q1_side_observations"], 2)
        self.assertEqual(body["observations"][0]["overtime"], "OT_EXCLUDED")
        self.assertIn("complete_settlement_contract", body["observations"][0]["missing_fields"])

    def test_full_source_name_counts_survive_a_small_display_window(self):
        rows = [source_row(player=str(1001+i)) for i in range(3)]
        catalogue = {"1001": self.player(), "1002": self.player("1002")}
        _, body, _ = self.build(rows=rows, catalogue=catalogue, limit=2)
        self.assertEqual(body["counts"]["source_player_ids"], 3)
        self.assertEqual(body["counts"]["name_resolved_player_ids"], 2)
        self.assertEqual(body["counts"]["name_unresolved_player_ids"], 1)
        self.assertEqual(body["counts"]["displayed_observations"], 2)

    def test_catalogue_identity_sport_and_name_conflicts_reject(self):
        mutations = [{"player_id": "9999"}, {"sport": "nfl"}, {"full_name": "Other Person"},
                     {"first_name": ""}, {"full_name": None}]
        for change in mutations:
            with self.subTest(change=change), self.assertRaises(IntegrityError):
                enrichment.catalogue_players(canonical({"1001": self.player(**change)}))
        with self.assertRaises(IntegrityError):
            enrichment.catalogue_players(b'{"1001":{},"1001":{}}')

    def test_unknown_ids_and_explicit_team_subjects_are_not_named_as_players(self):
        catalogue = {"BOS": {"player_id": "BOS", "sport": "nba", "position": "DEF", "team": "BOS"}}
        _, body, _ = self.build(catalogue=catalogue)
        self.assertEqual(body["counts"]["catalogue_team_entries"], 1)
        self.assertEqual(body["counts"]["name_unresolved_player_ids"], 1)
        self.assertEqual(body["observations"][0]["name_status"], "UNVERIFIED_NOT_IN_CATALOGUE")
        self.assertIsNone(body["observations"][0]["player_label"])

    def test_current_team_conflict_and_native_event_inventory_stay_unverified(self):
        rows = [source_row(player=str(1001+i)) for i in range(3)]
        for i,row in enumerate(rows):
            for option in row["options"]: option["subject_team"] = "Team "+str(i)
        _, body, _ = self.build(rows=rows)
        self.assertEqual(body["observations"][0]["team_status"], "CONFLICT_UNVERIFIED")
        self.assertEqual(body["observations"][0]["board_team"], "Team 0")
        self.assertEqual(body["event_team_inventory"], [{"provider_event_id": "9001", "source_team_labels": ["Team 0", "Team 1", "Team 2"], "status": "CONFLICT_UNVERIFIED"}])

    def test_missing_future_and_backdated_source_clocks_fail(self):
        assets = self.setup_sources(); review = json.loads((self.base/"review.json").read_bytes())
        loaded = {k: (p[0].read_bytes(), p[1].read_bytes()) for k,p in assets.items()}
        with self.assertRaises(IntegrityError):
            enrichment.make_enrichment(review, (self.base/"source.body").read_bytes(), loaded,
                                       generated_at=OBSERVED+timedelta(minutes=2), now=NOW)
        for field,value in (("observed_at", stamp(NOW+timedelta(seconds=1))), ("request_started_at", None)):
            bad = deepcopy(loaded); meta = json.loads(bad["catalogue"][1]); meta[field] = value
            bad["catalogue"] = (bad["catalogue"][0], canonical(meta))
            with self.subTest(field=field), self.assertRaises(IntegrityError):
                enrichment.make_enrichment(review, (self.base/"source.body").read_bytes(), bad, generated_at=NOW, now=NOW)

    def test_interrupted_creation_retry_keeps_original_enrichment_clock(self):
        assets = self.setup_sources(); real = base._create
        def interrupted(directory, name, raw, *, maximum):
            if name == "catalogue.body": raise OSError("simulated interruption")
            return real(directory, name, raw, maximum=maximum)
        with patch.object(base, "_create", side_effect=interrupted), self.assertRaises(OSError):
            enrichment.build_enrichment(base_directory=self.base, destination=self.destination,
                                        source_root=self.root, assets=assets, now=NOW)
        original_companion = (self.destination/"enrichment.json").read_bytes()
        result = enrichment.build_enrichment(base_directory=self.base, destination=self.destination,
                                            source_root=self.root, assets=assets, now=NOW+timedelta(days=1))
        self.assertEqual((self.destination/"enrichment.json").read_bytes(), original_companion)
        self.assertEqual(result["source_http_requests"], 0)

    def test_resealed_name_and_source_tampering_fail_independent_replay(self):
        _, body, _ = self.build()
        body["observations"][0]["player_label"] = "Invented Name"
        body["enrichment_id"] = digest({k:v for k,v in body.items() if k != "enrichment_id"})
        (self.destination/"enrichment.json").write_bytes(canonical(body))
        with self.assertRaises(IntegrityError): enrichment.verify_package(self.destination, base_directory=self.base, now=NOW)

    def test_resealed_invalid_catalogue_team_is_rejected_by_standalone_validation(self):
        _, body, _ = self.build(); review = json.loads((self.base/"review.json").read_bytes())
        body["observations"][0]["catalogue_team"] = 7
        body["observations"][0]["team_status"] = "CONFLICT_UNVERIFIED"
        body["observations"][0]["missing_fields"].append("team_conflict")
        body["enrichment_id"] = digest({k:v for k,v in body.items() if k != "enrichment_id"})
        with self.assertRaises(IntegrityError): enrichment.validate_enrichment(body, review, now=NOW)

    def test_missing_original_hash_change_rule_change_and_budget_reject(self):
        _, _, _ = self.build()
        catalogue = self.destination/"catalogue.body"; original_bytes = catalogue.read_bytes()
        catalogue.write_bytes(original_bytes+b" ")
        with self.assertRaises(IntegrityError): enrichment.verify_package(self.destination, base_directory=self.base, now=NOW)
        catalogue.unlink()
        with self.assertRaises(IntegrityError): enrichment.verify_package(self.destination, base_directory=self.base, now=NOW)
        catalogue.write_bytes(original_bytes)
        with patch.object(base, "MAX_PACKAGE_BYTES", 1), self.assertRaises(IntegrityError):
            enrichment.verify_package(self.destination, base_directory=self.base, now=NOW)

    def test_optimized_python_rejects_a_checksum_consistent_invalid_event(self):
        _, body, _ = self.build()
        body["observations"][0]["event_label"] = "Invented verified matchup"
        body["enrichment_id"] = digest({k:v for k,v in body.items() if k != "enrichment_id"})
        (self.destination/"enrichment.json").write_bytes(canonical(body))
        result = subprocess.run([sys.executable, "-O", "-m", "multisport_lab.player_line_enrichment", "--base", str(self.base),
                                 "--verify", str(self.destination)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0); self.assertIn("IntegrityError", result.stderr)

    def test_overlapping_destination_cannot_add_even_a_directory_to_original_package(self):
        assets = self.setup_sources(); before = self.inventory(self.base)
        with self.assertRaises(IntegrityError):
            enrichment.build_enrichment(base_directory=self.base, destination=self.base/"nested",
                                        source_root=self.root, assets=assets, now=NOW)
        self.assertEqual(self.inventory(self.base), before)


if __name__ == "__main__": unittest.main()

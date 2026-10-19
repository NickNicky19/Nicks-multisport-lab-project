"""Offline preparation integrity checks, with no PyArrow dependency or network."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.prepare_nba_panel import (MAX_ASSET_BYTES, prepare_panel, read_parquet,
                                      validate_output_path, write_create_only)
from multisport_lab.nba_data import normalize_sdv_row


def player():
    return {"game_id": 11, "athlete_id": 22, "team_id": 1, "opponent_team_id": 2,
        "season": 2026, "season_type": 2, "game_date_time": "2025-10-21T23:30:00Z",
        "did_not_play": False, "minutes": 0., "points": 0, "field_goals_made": 0,
        "field_goals_attempted": 0, "three_point_field_goals_made": 0,
        "three_point_field_goals_attempted": 0, "free_throws_made": 0,
        "free_throws_attempted": 0, "offensive_rebounds": 0, "defensive_rebounds": 0,
        "rebounds": 0, "assists": 0, "turnovers": 0, "blocks": 0, "steals": 0}


def schedule():
    return {"game_id": 11, "home_id": 1, "away_id": 2, "season": 2026,
        "season_type": 2, "game_date_time": "2025-10-21T23:30:00Z",
        "status_type_completed": True, "status_type_state": "post",
        "status_type_name": "STATUS_FINAL", "format_regulation_periods": 4.,
        "status_period": 4., "status_clock": 720.}


class PreparePanelTests(unittest.TestCase):
    def test_all_upstream_rejections_accounted_and_rounded_zero_retained(self):
        valid = player()
        missing_id = {**valid, "athlete_id": None}
        missing_minutes = {**valid, "athlete_id": 23, "minutes": None}
        unknown_participation = {**valid, "athlete_id": 24, "did_not_play": None}
        rows, report = prepare_panel([valid, missing_id, missing_minutes, unknown_participation], [schedule()])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].minutes, 0)
        self.assertEqual(rows[0].final_status, "FINAL")
        self.assertIsNone(rows[0].game_duration_minutes)
        rejected = report["upstream_exclusions"]
        self.assertEqual(rejected["normalization_rejected"], 1)
        self.assertEqual(rejected["cohort_exclusion_counts"], {
            "incomplete_primitive_or_minutes": 1, "unknown_participation": 1})
        self.assertEqual(rejected["total_excluded_rows"], 3)

    def test_duplicate_sources_fail_and_schedule_conflicts_are_reported(self):
        with self.assertRaises(ValueError):
            prepare_panel([player(), player()], [schedule()])
        with self.assertRaises(ValueError):
            prepare_panel([player()], [schedule(), schedule()])
        rows, report = prepare_panel([player()], [{**schedule(), "home_id": 3}])
        self.assertEqual(rows, [])
        self.assertEqual(report["upstream_exclusions"]["schedule_join_rejected"], 1)

    def test_create_only_exact_bytes_and_existing_file_unchanged(self):
        row = normalize_sdv_row(player())
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "panel.jsonl"
            expected = (json.dumps(row.to_record(), allow_nan=False) + "\n").encode()
            report = write_create_only(target, [row])
            self.assertEqual(target.read_bytes(), expected)
            self.assertEqual(report["sha256"], hashlib.sha256(expected).hexdigest())
            with self.assertRaises(ValueError):
                write_create_only(target, [])
            self.assertEqual(target.read_bytes(), expected)
            self.assertEqual(list(Path(folder).glob(".nba-panel-*")), [])

    def test_publication_paths_and_symlink_destinations_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            for name in ["web", "output", "evidence"]:
                (base / name).mkdir()
                with self.subTest(name=name), self.assertRaises(ValueError):
                    validate_output_path(base / name / "raw.jsonl")
            (base / "alias").symlink_to(base / "web", target_is_directory=True)
            with self.assertRaises(ValueError):
                validate_output_path(base / "alias" / "raw.jsonl")

    def test_oversize_and_symlink_inputs_fail_before_optional_import(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "source.parquet"
            with target.open("wb") as handle:
                handle.truncate(MAX_ASSET_BYTES + 1)
            with self.assertRaises(ValueError):
                read_parquet(target)
            alias = Path(folder) / "alias.parquet"
            alias.symlink_to(target)
            with self.assertRaises(ValueError):
                read_parquet(alias)


if __name__ == "__main__":
    unittest.main()

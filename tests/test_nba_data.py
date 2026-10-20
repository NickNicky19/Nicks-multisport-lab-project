"""Synthetic parser and data-integrity checks; no performance evidence."""
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from multisport_lab.nba_data import (
    COUNT_FIELDS, audit_rows, extract_nba_game, normalize_nba_game,
    normalize_sdv_row, normalize_sdv_rows, parse_minutes, with_sdv_schedule,
)


def raw_row():
    return {
        "game_id": 11, "athlete_id": 22, "team_id": 1, "opponent_team_id": 2,
        "season": 2026, "season_type": 2, "game_date_time": "2025-10-21T20:00:00-04:00",
        "did_not_play": False, "minutes": 20.0, "points": 12,
        "field_goals_made": 4, "field_goals_attempted": 8,
        "three_point_field_goals_made": 2, "three_point_field_goals_attempted": 4,
        "free_throws_made": 2, "free_throws_attempted": 2,
        "offensive_rebounds": 1, "defensive_rebounds": 2, "rebounds": 3,
        "assists": 4, "turnovers": 1, "blocks": 0, "steals": 1,
    }


def official_game():
    stats = {
        "minutes": "20:06", "points": 12, "fieldGoalsMade": 4, "fieldGoalsAttempted": 8,
        "threePointersMade": 2, "threePointersAttempted": 4,
        "freeThrowsMade": 2, "freeThrowsAttempted": 2,
        "reboundsOffensive": 1, "reboundsDefensive": 2, "reboundsTotal": 3,
        "assists": 4, "turnovers": 1, "blocks": 0, "steals": 1,
    }
    return {
        "gameId": "0022500001", "gameStatus": 3, "period": 6,
        "gameTimeUTC": "2025-10-21T23:30:00Z",
        "homeTeam": {"teamId": 10, "periods": [{"period": p} for p in range(1, 7)],
                     "players": [{"personId": 20, "comment": "", "statistics": stats}]},
        "awayTeam": {"teamId": 11, "periods": [{"period": p} for p in range(1, 7)], "players": []},
    }


class NBADataTests(unittest.TestCase):
    def test_declared_minutes_units(self):
        self.assertEqual(parse_minutes(36.5, encoding="decimal_minutes"), 36.5)
        self.assertEqual(parse_minutes("36:30", encoding="clock"), 36.5)
        self.assertEqual(parse_minutes("PT00M06.00S", encoding="clock"), .1)
        self.assertIsNone(parse_minutes("", encoding="clock"))
        for value, encoding in [(True, "decimal_minutes"), (float("nan"), "decimal_minutes"),
                                ("36:60", "clock"), ("36.30", "clock"), (-1, "decimal_minutes")]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_minutes(value, encoding=encoding)

    def test_source_ids_timezone_scoring_and_missing_duration(self):
        row = normalize_sdv_row(raw_row())
        self.assertEqual(row.identity, ("espn", "11", "22"))
        self.assertEqual(row.fg2m, 2)
        self.assertEqual(row.event_start, datetime(2025, 10, 22, tzinfo=timezone.utc))
        self.assertEqual(row.final_status, "UNKNOWN")
        self.assertIsNone(row.game_duration_minutes)
        self.assertFalse(audit_rows([row])["claims"]["historical_asof_verified"])

    def test_supplied_field_goals_must_equal_two_and_three_point_makes(self):
        row = normalize_sdv_row(raw_row())
        with self.assertRaisesRegex(ValueError, "FGM = FG2M \\+ FG3M"):
            replace(row, fgm=5)
        # Incomplete counts stay missing; validation must not invent a value.
        incomplete = replace(row, fg2m=None)
        self.assertIsNone(incomplete.fg2m)
        report = audit_rows([incomplete])
        self.assertEqual(report["appearance_missing_fields"]["fg2m"], 1)
        self.assertEqual(report["identity_failures"], {})

    def test_audit_independently_flags_legacy_field_goal_contradictions(self):
        for participation in ("APPEARED", "UNKNOWN"):
            row = replace(normalize_sdv_row(raw_row()), participation=participation)
            # Simulate an unchecked/legacy in-memory row so this exercises the
            # audit independently of the current constructor's rejection.
            object.__setattr__(row, "fgm", 5)
            with self.subTest(participation=participation):
                self.assertEqual(audit_rows([row])["identity_failures"], {"fgm_component_identity": 1})

    def test_normalized_panel_import_rejects_contradictory_supplied_fgm(self):
        from multisport_lab.research_pilot import read_normalized_panel

        record = normalize_sdv_row(raw_row()).to_record()
        record["fgm"] = 5
        # Points still equal 2*FG2M + 3*FG3M + FTM and FGM <= FGA. This
        # specifically reaches the formerly missing component identity.
        with tempfile.TemporaryDirectory(prefix="nba-import-validation-") as folder:
            path = Path(folder) / "contradictory.jsonl"
            path.write_text(json.dumps(record) + "\n")
            with self.assertRaisesRegex(ValueError, "FGM = FG2M \\+ FG3M"):
                read_normalized_panel(path)

    def test_dnp_is_not_zero_and_unknown_is_preserved(self):
        raw = raw_row()
        raw["did_not_play"] = True
        with self.assertRaises(ValueError):
            normalize_sdv_row(raw)
        for key in list(raw):
            if key not in {"game_id", "athlete_id", "team_id", "opponent_team_id", "season",
                           "season_type", "game_date_time", "did_not_play"}:
                raw[key] = None
        row = normalize_sdv_row(raw)
        self.assertEqual(row.participation, "DNP")
        self.assertTrue(all(getattr(row, field) is None for field in COUNT_FIELDS))
        raw["did_not_play"] = None
        self.assertEqual(normalize_sdv_row(raw).participation, "UNKNOWN")
        raw["did_not_play"] = "false"
        with self.assertRaises(ValueError):
            normalize_sdv_row(raw)

    def test_zero_and_missing_minutes_appearances_not_discarded(self):
        raw = raw_row()
        raw["minutes"] = 0.0
        zero = normalize_sdv_row(raw)
        raw["minutes"] = None
        missing = normalize_sdv_row(raw)
        report = audit_rows([zero, missing])
        self.assertEqual(report["participation"], {"APPEARED": 2})
        self.assertEqual(report["appearance_zero_fields"]["minutes"], 1)
        self.assertEqual(report["appearance_missing_fields"]["minutes"], 1)
        with self.assertRaises(ValueError):
            replace(zero, minutes_precision="seconds")

    def test_duplicate_revision_and_incoherent_fields_are_flagged(self):
        row = normalize_sdv_row(raw_row())
        revised = replace(row, points=13, rebounds=4, fga=1)
        report = audit_rows([row, revised])
        self.assertEqual(report["row_count"], 2)
        self.assertEqual(report["duplicate_event_player_rows"], 1)
        self.assertEqual(report["identity_failures"], {
            "scoring_identity": 1, "rebound_identity": 1, "fgm_exceeds_attempts": 1})
        self.assertEqual(audit_rows([row, replace(row, id_namespace="nba")])["duplicate_event_player_rows"], 0)
        with self.assertRaises(ValueError):
            audit_rows([row, row], max_rows=1)

    def test_invalid_counts_ids_and_clock_rejected(self):
        for field, value in [("field_goals_made", True), ("points", 12.0), ("team_id", 2),
                             ("three_point_field_goals_made", 5), ("game_id", None),
                             ("game_date_time", "2025-10-22T00:00:00")]:
            raw = raw_row()
            raw[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                normalize_sdv_row(raw)

    def test_batch_quarantines_missing_ids_without_guessing(self):
        anonymous = raw_row()
        anonymous["athlete_id"] = None
        rows, rejected = normalize_sdv_rows([raw_row(), anonymous])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rejected, [{"source_row_index": 1, "event_id": "11",
                                    "reason": "athlete_id needs a nonempty source ID"}])
        with self.assertRaises(ValueError):
            normalize_sdv_rows([raw_row(), anonymous], max_rows=1)

    def test_primary_final_periods_and_precise_minutes(self):
        game = official_game()
        row = normalize_nba_game(game, season_ending_year=2026, season_type="Regular Season")[0]
        self.assertEqual(row.id_namespace, "nba")
        self.assertEqual(row.final_periods, 6)
        self.assertEqual(row.game_duration_minutes, 58)
        self.assertAlmostEqual(row.minutes, 20.1)
        game["period"] = 5
        with self.assertRaises(ValueError):
            normalize_nba_game(game, season_ending_year=2026, season_type="Regular Season")

    def test_final_schedule_join_and_exhibition_duration_guard(self):
        row = normalize_sdv_row(raw_row())
        schedule = {"game_id": 11, "home_id": 1, "away_id": 2, "season": 2026,
                    "season_type": 2, "game_date_time": row.event_start,
                    "status_type_completed": True, "status_type_state": "post",
                    "status_type_name": "STATUS_FINAL", "format_regulation_periods": 4.,
                    "status_period": 6., "status_clock": 0.}
        joined = with_sdv_schedule(row, schedule, standard_team_ids=frozenset({"1", "2"}))
        self.assertEqual(joined.game_duration_minutes, 58)
        exhibition = with_sdv_schedule(row, schedule, standard_team_ids=frozenset())
        self.assertEqual(exhibition.final_status, "FINAL")
        self.assertIsNone(exhibition.game_duration_minutes)
        for key, value in [("game_id", 12), ("home_id", 3), ("season", 2025),
                           ("game_date_time", "2025-10-23T00:00:00Z"), ("status_period", 4.5)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                with_sdv_schedule(row, {**schedule, key: value}, standard_team_ids=frozenset({"1", "2"}))
        reset_clock = with_sdv_schedule(row, {**schedule, "status_clock": 720.},
                                        standard_team_ids=frozenset({"1", "2"}))
        self.assertEqual(reset_clock.final_status, "FINAL")
        self.assertIsNone(reset_clock.game_duration_minutes)
        pending = with_sdv_schedule(row, {**schedule, "status_type_completed": False},
                                    standard_team_ids=frozenset({"1", "2"}))
        self.assertEqual(pending.final_status, "NOT_FINAL")

    def test_primary_dnp_placeholders_and_unknown_blank_minutes(self):
        game = official_game()
        player = game["homeTeam"]["players"][0]
        player["comment"] = "DND - Injury/Illness"
        player["statistics"] = {field: 0 for field in player["statistics"]}
        player["statistics"]["minutes"] = ""
        dnp = normalize_nba_game(game, season_ending_year=2026, season_type="2")[0]
        self.assertEqual(dnp.participation, "DNP")
        self.assertIsNone(dnp.points)
        player["comment"] = ""
        self.assertEqual(normalize_nba_game(game, season_ending_year=2026, season_type="2")[0].participation, "UNKNOWN")
        player["comment"] = "DNP - Coach's Decision"
        player["statistics"]["points"] = 1
        with self.assertRaises(ValueError):
            normalize_nba_game(game, season_ending_year=2026, season_type="2")

    def test_embedded_primary_game_parse_and_fail_closed(self):
        game = official_game()
        html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps({"props": {"pageProps": {"game": game}}}) + '</script>'
        self.assertEqual(extract_nba_game(html)["gameId"], "0022500001")
        with self.assertRaises(ValueError):
            extract_nba_game("upstream error page")
        for payload in ['{"props":{},"props":{}}', '{"props":1e999}', '{"props":NaN}']:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                extract_nba_game('<script id="__NEXT_DATA__">' + payload + '</script>')


if __name__ == "__main__":
    unittest.main()

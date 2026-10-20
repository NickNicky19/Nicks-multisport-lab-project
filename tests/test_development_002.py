"""Synthetic DEV002 timing, cohort and cluster-integrity checks, not NBA scores."""
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from multisport_lab.baseline import ForecastTarget, HistoricalAppearance, MARKETS, forecast_reference
from multisport_lab.development_002 import (INPUT_SHA256, WINDOW_START, DailyPool,
    inventory_panel, paired_week_bootstrap, protocol_specification, validate_protocol)


def row(event, player, start, team="1", **changes):
    values = dict(event_id=event, player_id=player, team_id=team,
        opponent_id="2" if team == "1" else "1", event_start=start,
        outcome_available_at=start+timedelta(hours=24), minutes=20,
        minutes_precision="rounded_whole_minutes", fg2m=4, fg3m=1, ftm=2,
        rebounds=5, assists=3, turnovers=2, blocks=1, steals=1)
    return HistoricalAppearance(**(values | changes))


def panel():
    rows = []
    for week in range(8):
        for game in range(3):
            start = datetime.combine(WINDOW_START+timedelta(weeks=week),
                datetime.min.time(), tzinfo=timezone.utc)+timedelta(hours=18+game)
            for team in ("1", "2"):
                rows.append(row(f"w{week}g{game}", f"player{team}", start, team))
    source = dict(input_file_sha256=INPUT_SHA256, input_bytes=1, input_rows=len(rows),
        eligible_panel_rows=len(rows), input_excluded_rows=0, input_exclusions={},
        upstream_exclusions={"status": "EXTERNAL_TO_NORMALIZED_INPUT"},
        minutes_precision_counts={"rounded_whole_minutes": len(rows)},
        rounded_zero_minute_appearances=0, season_types={"2": len(rows)})
    return rows, source


class Development002Tests(unittest.TestCase):
    def test_calendar_week_sampling_retains_all_appearances_of_first_two_games(self):
        rows, source = panel()
        selected, inventory = inventory_panel(rows, source)
        self.assertEqual(len(selected), 32)
        self.assertEqual(inventory["selected_games"], 16)
        self.assertEqual(inventory["window_start"], "2025-11-24")
        self.assertEqual(inventory["window_end"], "2026-01-18")
        self.assertTrue(all("g2" not in observed.event_id for _, observed in selected))
        self.assertTrue(all(week["selected_appearances"] == 4 for week in inventory["weekly_inventory"]))
        self.assertEqual({observed.team_id for _, observed in selected}, {"1", "2"})

    def test_missing_week_or_split_game_cap_or_wrong_hash_fails_before_scoring(self):
        rows, source = panel()
        with self.assertRaisesRegex(ValueError, "each registered"):
            inventory_panel([r for r in rows if not r.event_id.startswith("w7")], source)
        with self.assertRaisesRegex(ValueError, "SHA256"):
            inventory_panel(rows, source | {"input_file_sha256": "0"*64})
        with patch("multisport_lab.development_002.MAX_ROWS", 31):
            with self.assertRaisesRegex(ValueError, "no game is split"):
                inventory_panel(rows, source)

    def test_frozen_protocol_binds_complete_cohort_and_exact_two_models(self):
        _, inventory = inventory_panel(*panel())
        frozen = protocol_specification(inventory) | {
            "recorded_at": "2026-01-01T00:00:00Z", "approved_by": "root_integration_owner"}
        validate_protocol(frozen, inventory)
        self.assertEqual(set(frozen["models"]), {"R0", "L0"})
        with self.assertRaisesRegex(ValueError, "cohort_identity_sha256"):
            validate_protocol(frozen | {"cohort_identity_sha256": "0"*64}, inventory)
        with self.assertRaisesRegex(ValueError, "approval"):
            validate_protocol(frozen | {"approved_by": "automatic"}, inventory)

    def test_league_only_is_cold_start_r0_and_preserves_same_full_lines(self):
        start = datetime(2025, 10, 21, 20, tzinfo=timezone.utc)
        rows = [row("a", "old1", start, fg2m=0, fg3m=0, ftm=0, rebounds=0),
                row("b", "old2", start+timedelta(days=28), fg2m=10, fg3m=0, ftm=0, rebounds=20)]
        target = ForecastTarget("future", "cold", datetime(2025, 12, 1, 20, tzinfo=timezone.utc))
        league = DailyPool(rows).forecast(target)
        reference = forecast_reference(rows, target)
        for market in MARKETS:
            self.assertEqual(set(league.marginal(market)), set(reference.marginal(market)))
            for outcome, probability in league.marginal(market).items():
                self.assertAlmostEqual(probability, reference.marginal(market)[outcome], places=12)
        self.assertNotIn(20, league.marginal("PR"))
        self.assertAlmostEqual(league.marginal("PTS")[0], 1/3)
        self.assertTrue(all(item.line.market_values()["TD"] <= item.line.market_values()["DD"]
                            for item in league.support))

    def test_cached_training_pool_excludes_future_and_matches_unchanged_r0_hash(self):
        target = ForecastTarget("new", "p1", datetime(2025, 12, 1, 0, 30, tzinfo=timezone.utc))
        start = datetime(2025, 11, 26, 20, tzinfo=timezone.utc)
        before = row("before", "p1", start)
        unavailable = row("unavailable", "p1", target.history_freeze-timedelta(hours=1))
        after = row("after", "p1", target.event_start+timedelta(days=1))
        rows = [before, unavailable, after]
        pool = DailyPool(rows)
        eligible, support, bound, _ = pool.get(target)
        self.assertEqual(eligible, (before,))
        self.assertEqual(len(support), 1)
        self.assertLessEqual(bound, target.history_freeze)
        from_all = forecast_reference(rows, target)
        from_cached = forecast_reference(eligible, target)
        self.assertEqual(from_all.input_sha256, from_cached.input_sha256)
        self.assertEqual(from_all.support, from_cached.support)

    def test_cluster_bootstrap_recomputes_row_weighted_mean_and_is_reproducible(self):
        counts = list(range(1, 9))
        sums = [{market: index*count for market in MARKETS} for index, count in enumerate(counts)]
        result = paired_week_bootstrap(sums, counts)
        expected = sum(index*count for index, count in enumerate(counts))/sum(counts)
        self.assertAlmostEqual(result["PTS"]["mean_difference_R0_minus_L0"], expected)
        self.assertEqual(result, paired_week_bootstrap(sums, counts))
        self.assertLessEqual(result["PTS"]["cluster_percentile95_lower"], expected)
        self.assertGreaterEqual(result["PTS"]["cluster_percentile95_upper"], expected)
        constant = [{market: -2*count for market in MARKETS} for count in counts]
        interval = paired_week_bootstrap(constant, counts)["PTS"]
        self.assertEqual(interval["cluster_percentile95_lower"], -2)
        self.assertEqual(interval["cluster_percentile95_upper"], -2)


if __name__ == "__main__":
    unittest.main()

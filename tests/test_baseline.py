"""Synthetic reference-integrity tests; these do not measure forecast accuracy."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import math
import unittest
from unittest.mock import patch

from multisport_lab.baseline import (
    BaselineError, COUNT_FIELDS, ForecastTarget, HistoricalAppearance, MARKETS,
    discrete_crps, evaluate_forecast, forecast_reference, variogram_score,
)
from multisport_lab.integrity import canonical


UTC = timezone.utc
NOW = datetime(2026, 10, 19, 12, tzinfo=UTC)


def appearance(event="g1", player="p1", **changes):
    values = dict(event_id=event, player_id=player, team_id="t1", opponent_id="t2",
        event_start=datetime(2024, 1, 1, 20, tzinfo=UTC),
        outcome_available_at=datetime(2024, 1, 2, 0, tzinfo=UTC),
        minutes=30, fg2m=3, fg3m=2, ftm=2, rebounds=6, assists=4,
        turnovers=2, blocks=1, steals=1)
    return HistoricalAppearance(**(values | changes))


def target(**changes):
    values = dict(event_id="new", player_id="p1",
                  event_start=datetime(2024, 2, 1, 20, tzinfo=UTC))
    return ForecastTarget(**(values | changes))


class ReferenceTests(unittest.TestCase):
    def forecast(self, history, selected=None):
        with patch("multisport_lab.baseline._now", return_value=NOW):
            return forecast_reference(history, selected or target())

    def test_all_category_values_come_from_the_same_scoring_primitives(self):
        observed = appearance(fg2m=4, fg3m=4, ftm=8, rebounds=10, assists=11)
        forecast = self.forecast([observed])
        values = forecast.support[0].line.market_values()
        self.assertEqual(set(values), set(MARKETS))
        self.assertEqual(values["PTS"], 28)
        self.assertEqual(values["PRA"], values["PR"]+values["AST"])
        self.assertEqual(values["PRA"], values["RA"]+values["PTS"])
        self.assertEqual(values["PA"], values["PTS"]+values["AST"])
        self.assertEqual(values["BLK+STL"], values["BLK"]+values["STL"])
        self.assertEqual((values["DD"], values["TD"]), (1, 1))

    def test_shared_whole_rows_preserve_dependence_instead_of_realigning_marginals(self):
        low = appearance("a", fg2m=0, fg3m=0, ftm=0, rebounds=0)
        high = appearance("b", fg2m=10, fg3m=0, ftm=0, rebounds=20)
        forecast = self.forecast([high, low])
        self.assertEqual(forecast.marginal("PR"), {0: 0.5, 40: 0.5})
        self.assertNotIn(20, forecast.marginal("PR"))
        self.assertTrue(all(item.line.market_values()["TD"] <=
                            item.line.market_values()["DD"] for item in forecast.support))

    def test_fixed_five_appearance_pool_and_28_day_calendar_decay(self):
        own = appearance("a", "p1", fg2m=0, fg3m=0, ftm=0)
        other = appearance("b", "p2", fg2m=10, fg3m=0, ftm=0)
        selected = target(event_start=own.event_start+timedelta(days=28, minutes=90))
        forecast = self.forecast([own, other], selected)
        # Each pool row receives 2.5 prior equivalents; own recency weight is0.5.
        self.assertAlmostEqual(forecast.marginal("PTS")[0], 3/5.5)
        self.assertAlmostEqual(forecast.marginal("PTS")[20], 2.5/5.5)

    def test_cold_start_is_recency_weighted_league_pool(self):
        old = appearance("a", "p2", fg2m=0, fg3m=0, ftm=0)
        new = appearance("b", "p3", event_start=old.event_start+timedelta(days=28),
                         outcome_available_at=old.outcome_available_at+timedelta(days=28),
                         fg2m=10, fg3m=0, ftm=0)
        forecast = self.forecast([old, new])
        self.assertTrue(forecast.cold_start)
        self.assertAlmostEqual(forecast.marginal("PTS")[0], 1/3)
        self.assertAlmostEqual(forecast.marginal("PTS")[20], 2/3)

    def test_future_same_day_unavailable_and_target_event_rows_do_not_enter(self):
        earlier = appearance()
        selected = target()
        later = appearance("future", event_start=selected.event_start+timedelta(days=1),
                           outcome_available_at=selected.event_start+timedelta(days=2))
        same_day = appearance("same", event_start=selected.history_freeze+timedelta(hours=1),
                             outcome_available_at=selected.history_freeze+timedelta(hours=3))
        late_available = appearance("late", outcome_available_at=selected.history_freeze+
                                    timedelta(microseconds=1))
        own_target = appearance(selected.event_id)
        actual = self.forecast([earlier, later, same_day, late_available, own_target], selected)
        expected = self.forecast([earlier], selected)
        self.assertEqual(actual.input_sha256, expected.input_sha256)
        self.assertEqual(actual.support, expected.support)
        self.assertEqual(actual.trained_through, earlier.outcome_available_at)

    def test_utc_midnight_freeze_is_based_on_cutoff_date(self):
        selected = target(event_start=datetime(2024, 2, 1, 0, 30, tzinfo=UTC))
        self.assertEqual(selected.cutoff, datetime(2024, 1, 31, 23, tzinfo=UTC))
        self.assertEqual(selected.history_freeze, datetime(2024, 1, 31, tzinfo=UTC))
        self.assertEqual(selected.cutoff-selected.history_freeze, timedelta(hours=23))
        before = appearance("before", event_start=selected.history_freeze-timedelta(hours=3),
                            outcome_available_at=selected.history_freeze)
        at_freeze = appearance("at", event_start=selected.history_freeze,
                              outcome_available_at=selected.history_freeze+timedelta(hours=3))
        self.assertEqual(self.forecast([before, at_freeze], selected).pool_history_count, 1)

    def test_missing_training_support_does_not_fabricate_zero(self):
        with self.assertRaisesRegex(BaselineError, "no eligible"):
            self.forecast([])

    def test_duplicates_including_excluded_rows_and_conflicting_event_clocks_fail(self):
        row = appearance()
        with self.assertRaisesRegex(BaselineError, "duplicate"):
            self.forecast([row, row])
        with self.assertRaisesRegex(BaselineError, "conflicting"):
            self.forecast([row, replace(row, player_id="another",
                event_start=row.event_start+timedelta(minutes=1))])
        with self.assertRaisesRegex(BaselineError, "namespaces"):
            self.forecast([replace(row, id_namespace="nba")])

    def test_real_issuance_is_not_backdated_to_historical_cutoff(self):
        forecast = self.forecast([appearance()])
        self.assertEqual(forecast.issued_at, NOW)
        self.assertGreater(forecast.issued_at, forecast.target.event_start)
        record = forecast.to_record()
        self.assertEqual(record["evidence_lane"], "RECONSTRUCTED_RESEARCH")
        self.assertFalse(record["product_qualified"])
        self.assertFalse(record["same_game_joint_model"])
        self.assertEqual(record["participation_semantics"], "CONDITIONAL_ON_APPEARANCE")
        upcoming = target(event_start=NOW+timedelta(hours=2))
        with self.assertRaisesRegex(BaselineError, "cutoff has not occurred"):
            self.forecast([appearance()], upcoming)
        at_cutoff = target(event_start=NOW+timedelta(minutes=90))
        self.assertEqual(self.forecast([appearance()], at_cutoff).issued_at, NOW)

    def test_invalid_counts_minutes_clocks_and_identities_fail(self):
        row = appearance()
        for name in ("fg2m", "fg3m", "ftm", "rebounds", "assists", "turnovers", "blocks", "steals"):
            for value in (True, 1.0, -1, None):
                with self.subTest(name=name, value=value), self.assertRaises(BaselineError):
                    replace(row, **{name: value})
        for value in (True, -1, float("nan"), float("inf"), 1000):
            with self.subTest(minutes=value), self.assertRaises(BaselineError):
                replace(row, minutes=value)
        with self.assertRaises(BaselineError):
            replace(row, outcome_available_at=row.event_start)
        with self.assertRaises(ValueError):
            replace(row, event_start=datetime(2024, 1, 1))
        with self.assertRaises(BaselineError):
            replace(row, player_id=" p1")
        with self.assertRaises(BaselineError):
            replace(row, opponent_id=row.team_id)

    def test_rounded_zero_appearance_is_retained_and_overtime_has_no_48_minute_cap(self):
        row = appearance()
        with self.assertRaises(BaselineError):
            replace(row, minutes=0)
        rounded_zero = replace(row, minutes=0, minutes_precision="rounded_whole_minutes")
        forecast = self.forecast([rounded_zero])
        self.assertEqual(forecast.support[0].line.minutes, 0)
        self.assertEqual(forecast.support[0].line.minutes_precision, "rounded_whole_minutes")
        self.assertEqual(replace(row, minutes=52, game_duration_minutes=53).minutes, 52)
        with self.assertRaises(BaselineError):
            replace(row, minutes=52, game_duration_minutes=48)
        with self.assertRaises(BaselineError):
            replace(row, game_duration_minutes=50)
        with self.assertRaises(BaselineError):
            replace(row, minutes=0.1, minutes_precision="rounded_whole_minutes")

    def test_order_independent_hash_and_exact_weights_are_normalized(self):
        rows = [appearance("b", "p2"), appearance("a", "p1")]
        first = self.forecast(rows)
        second = self.forecast(reversed(rows))
        self.assertEqual(first.to_record(), second.to_record())
        self.assertAlmostEqual(math.fsum(item.weight for item in first.support), 1)
        canonical(first.to_record())

    def test_crps_matches_direct_rps_including_out_of_support_tail(self):
        pmf = {0: 0.2, 2: 0.3, 6: 0.5}
        for observed in (0, 1, 2, 6, 10):
            expected = math.fsum((math.fsum(p for x, p in pmf.items() if x <= k)
                                 - int(observed <= k))**2 for k in range(11))
            self.assertAlmostEqual(discrete_crps(pmf, observed), expected)
        for invalid in ({}, {0: float("nan")}, {0: 0.5}, {True: 1}, {-1: 1}):
            with self.subTest(pmf=invalid), self.assertRaises(BaselineError):
                discrete_crps(invalid, 1)

    def test_category_evaluation_binary_scores_intervals_and_zero_support_log(self):
        low = appearance("a", fg2m=0, fg3m=0, ftm=0, rebounds=0, assists=0,
                         blocks=0, steals=0)
        high = appearance("b", fg2m=10, fg3m=0, ftm=0, rebounds=10, assists=10)
        forecast = self.forecast([low, high])
        result = evaluate_forecast(forecast, low.primitive_line())
        self.assertEqual(set(result["categories"]), set(MARKETS))
        for binary in ("DD", "TD"):
            scores = result["categories"][binary]
            self.assertEqual(scores["probability"], 0.5)
            self.assertEqual(scores["brier"], 0.25)
            self.assertEqual(scores["crps"], scores["brier"])
        pts = result["categories"]["PTS"]
        self.assertEqual(pts["zero_probability"], 0.5)
        self.assertEqual(pts["intervals"]["0.8"]["predicted_mass"], 1)
        self.assertTrue(pts["intervals"]["0.8"]["covered"])
        self.assertEqual(result["minutes_mean"], 30)
        self.assertEqual(result["minutes_diagnostics"]["crps"], 0)
        unseen = replace(low.primitive_line(), ftm=1)
        scores = evaluate_forecast(forecast, unseen)["categories"]["PTS"]
        self.assertIsNone(scores["log_loss"])
        self.assertEqual(scores["log_loss_status"], "ZERO_SUPPORT_INFINITE_LOSS")
        canonical(evaluate_forecast(forecast, unseen))

    def test_variogram_diagnostic_requires_explicit_scales_and_exact_row_scores_zero(self):
        row = appearance()
        forecast = self.forecast([row])
        scales = {name: 1 for name in COUNT_FIELDS}
        self.assertEqual(variogram_score(forecast, row.primitive_line(), scales=scales), 0)
        different = replace(row.primitive_line(), rebounds=20)
        self.assertGreater(variogram_score(forecast, different, scales=scales), 0)
        for invalid in ({}, scales | {"rebounds": 0}, scales | {"assists": True}):
            with self.subTest(scales=invalid), self.assertRaises(BaselineError):
                variogram_score(forecast, different, scales=invalid)


if __name__ == "__main__":
    unittest.main()

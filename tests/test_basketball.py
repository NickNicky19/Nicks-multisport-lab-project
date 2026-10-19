"""Synthetic stat-contract checks, not NBA observations or forecast evaluation."""
from dataclasses import replace
from decimal import Decimal
import unittest

from multisport_lab.basketball import BasketballDraw


def draw(**changes):
    values = dict(points=0, rebounds=0, assists=0, threes_made=0,
                  turnovers=0, blocks=0, steals=0)
    return BasketballDraw(**(values | changes))


class BasketballTests(unittest.TestCase):
    def test_all_markets_are_derived_coherently_from_one_draw(self):
        sample = draw(points=28, rebounds=10, assists=12, threes_made=4,
                      turnovers=3, blocks=1, steals=2)
        values = sample.market_values()
        self.assertEqual(values, {"PTS": 28, "PRA": 50, "REB": 10, "3PM": 4,
            "AST": 12, "RA": 22, "PR": 38, "PA": 40, "TOV": 3,
            "TD": 1, "DD": 1, "BLK": 1, "STL": 2, "BLK+STL": 3})
        self.assertEqual(values["PRA"], values["PR"] + values["AST"])
        self.assertEqual(values["PRA"], values["RA"] + values["PTS"])
        self.assertEqual(values["PRA"], values["PA"] + values["REB"])
        values["PTS"] = 999
        self.assertEqual(sample.market_values()["PTS"], 28)

    def test_zero_draw_is_valid_but_missing_count_is_not_zero(self):
        self.assertTrue(all(value == 0 for value in draw().market_values().values()))
        with self.assertRaises(TypeError):
            BasketballDraw(points=0, rebounds=0, assists=0, threes_made=0,
                           turnovers=0, blocks=0)  # Missing steals is unknown.

    def test_all_base_counts_require_nonnegative_true_integers(self):
        for name in ("points", "rebounds", "assists", "threes_made",
                     "turnovers", "blocks", "steals"):
            for value in (-1, True, False, 1.0, Decimal(1), "1", None, float("nan")):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    replace(draw(), **{name: value})

    def test_points_cannot_be_less_than_points_from_made_threes(self):
        with self.assertRaises(ValueError):
            draw(points=8, threes_made=3)
        self.assertEqual(draw(points=9, threes_made=3).market_values()["3PM"], 3)

    def test_steals_and_blocks_can_qualify_double_and_triple_doubles(self):
        for sample, expected in (
            (draw(points=10, steals=10), (1, 0)),
            (draw(blocks=10, steals=10), (1, 0)),
            (draw(points=10, rebounds=10, steals=10), (1, 1)),
            (draw(points=10, assists=10, blocks=10), (1, 1)),
            (draw(points=10, rebounds=10, assists=10, blocks=10, steals=10), (1, 1)),
        ):
            values = sample.market_values()
            self.assertEqual((values["DD"], values["TD"]), expected)
            self.assertGreaterEqual(values["DD"], values["TD"])

    def test_threes_and_turnovers_do_not_count_as_double_double_categories(self):
        values = draw(points=30, threes_made=10, turnovers=10).market_values()
        self.assertEqual((values["DD"], values["TD"]), (0, 0))
        boundary = draw(points=10, rebounds=9, assists=9, steals=9, blocks=9).market_values()
        self.assertEqual((boundary["DD"], boundary["TD"]), (0, 0))


if __name__ == "__main__":
    unittest.main()

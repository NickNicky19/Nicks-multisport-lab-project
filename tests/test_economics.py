from dataclasses import replace
from decimal import Decimal
import unittest

from multisport_lab.contracts import PriceKind
from multisport_lab.economics import single_ev, conditional_two_sided_no_vig, independent_all_hit, ticket_ev
from test_contracts import contract, quote


class EconomicsTests(unittest.TestCase):
    def test_known_price_reversal_and_returned_stakes(self):
        self.assertAlmostEqual(single_ev(quote(), p_win=.55, p_loss=.45), .05)
        expensive = quote(price=Decimal(5) / Decimal(3))  # American -150
        self.assertAlmostEqual(single_ev(expensive, p_win=.55, p_loss=.45), -1 / 12)
        self.assertAlmostEqual(single_ev(quote(price=2), p_win=.4, p_loss=.3,
                                        p_push=.2, p_void=.1), .1)
        self.assertEqual(single_ev(quote(), p_win=0, p_loss=0, p_void=1), 0)
        for values in (dict(p_win=.6, p_loss=.6), dict(p_win=float("nan"), p_loss=.4),
                       dict(p_win=-.1, p_loss=1.1), dict(p_win=.5, p_loss=.4)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                single_ev(quote(), **values)

    def test_pickem_multiplier_never_becomes_single_odds(self):
        pickem = quote(price_kind=PriceKind.PICKEM_MULTIPLIER, price=1.9)
        with self.assertRaises(ValueError):
            single_ev(pickem, p_win=.55, p_loss=.45)
        with self.assertRaises(ValueError):
            conditional_two_sided_no_vig(pickem, replace(pickem, contract=contract(side="under")))

    def test_no_vig_is_conditional_and_requires_identical_priced_contract(self):
        over = quote(contract=contract(line=22), price=1.8)
        under = quote(contract=contract(line=22, side="under"), price=2.2)
        estimate = conditional_two_sided_no_vig(over, under)
        self.assertAlmostEqual(estimate.p_over_given_nonpush, .55)
        self.assertAlmostEqual(estimate.p_under_given_nonpush, .45)
        # With externally supplied .10 push mass, unconditional over is .495, not .55.
        self.assertAlmostEqual(.9 * estimate.p_over_given_nonpush, .495)
        for changed in (replace(under, contract=contract(line=23, side="under")),
                        replace(under, contract=contract(line=22, side="under", period="first_quarter")),
                        replace(under, line_evidence_id="other", price_evidence_id="other")):
            with self.assertRaises(ValueError):
                conditional_two_sided_no_vig(over, changed)

    def test_independence_is_explicit_and_six_leg_probability_is_not_leg_probability(self):
        self.assertAlmostEqual(independent_all_hit([.6] * 6, assume_independent=True), .046656)
        with self.assertRaises(ValueError):
            independent_all_hit([.6] * 6, assume_independent=False)
        with self.assertRaises(ValueError):
            independent_all_hit([.6, float("inf")], assume_independent=True)

    def test_explicit_joint_law_can_change_ev_at_identical_marginals(self):
        legs = [contract(), contract(player_id="synthetic-player-2")]
        payouts = {("win", "win"): 3, ("win", "loss"): 0,
                   ("loss", "win"): 0, ("loss", "loss"): 0}
        independent = dict(zip(payouts, [.36, .24, .24, .16]))
        dependent = dict(zip(payouts, [.5, .1, .1, .3]))
        first = ticket_ev(legs, state_probabilities=independent, gross_payouts=payouts)
        second = ticket_ev(legs, state_probabilities=dependent, gross_payouts=payouts)
        self.assertAlmostEqual(first.net_return, .08)
        self.assertAlmostEqual(second.net_return, .5)
        self.assertEqual(second.all_win_probability, .5)
        returned = ticket_ev(legs, state_probabilities={("push", "void"): 1},
                             gross_payouts={("push", "void"): 1})
        self.assertEqual(returned.net_return, 0)

    def test_ticket_incomplete_economics_and_mixed_venues_are_rejected(self):
        legs = [contract(), contract(player_id="p2")]
        good = {("win", "win"): 1}
        cases = [({}, {}), (good, {}), (good, {("win", "win"): None}),
                 (good, {("win", "win"): float("inf")}),
                 ({("win", "win"): .9}, {("win", "win"): 3}),
                 ({("unknown", "win"): 1}, {("unknown", "win"): 3})]
        for probabilities, payouts in cases:
            with self.subTest(probabilities=probabilities, payouts=payouts), self.assertRaises(ValueError):
                ticket_ev(legs, state_probabilities=probabilities, gross_payouts=payouts)
        for bad_legs in ([legs[0]], [legs[0], legs[0]],
                         [legs[0], replace(legs[1], venue="other")],
                         [legs[0], replace(legs[1], product="other")]):
            with self.assertRaises(ValueError):
                ticket_ev(bad_legs, state_probabilities=good, gross_payouts={("win", "win"): 3})

    def test_opposite_sides_of_same_market_reject_impossible_all_win_law(self):
        over = contract()
        under = replace(over, side="under")
        self.assertNotEqual(over.contract_id, under.contract_id)
        self.assertEqual(over.market_id, under.market_id)
        with self.assertRaisesRegex(ValueError, "same market"):
            ticket_ev([over, under], state_probabilities={("win", "win"): 1},
                      gross_payouts={("win", "win"): 3})


if __name__ == "__main__":
    unittest.main()

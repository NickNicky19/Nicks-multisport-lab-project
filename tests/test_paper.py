"""Synthetic contract checks only; no provider terms or evaluated probabilities."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import unittest

from multisport_lab.contracts import PriceKind, PropContract, QuoteObservation
from multisport_lab.paper import (EntryTerms, ForecastEvidence, FullTicketAssessment,
                                  JointOutcomes, ManualDraft, PaperMode,
                                  choose_six_first, draft_ev, validate_draft)


DECISION = datetime(2026, 10, 19, 18, 0, tzinfo=timezone.utc)
MINUTE = timedelta(minutes=1)


def quote(index, *, league="NBA", side="over", **contract_changes):
    values = dict(sport="basketball", league=league, event_id=f"synthetic-game-{index}",
                  player_id=f"synthetic-player-{index}", stat="REB", units="rebounds",
                  period="full_game", extra_time_policy="includes_overtime", line=Decimal("6.5"),
                  side=side, variant="standard", venue="fictional-venue", product="fictional-product",
                  settlement_version="fictional-rules-v1")
    values.update(contract_changes)
    return QuoteObservation(PropContract(**values), Decimal("1.91"), PriceKind.SPORTSBOOK_DECIMAL,
                            "synthetic-source", DECISION - MINUTE, DECISION + index * 90 * MINUTE,
                            f"fixture-{index}", f"fixture-{index}", DECISION - MINUTE)


def forecast(offer, **changes):
    result = ForecastEvidence("synthetic-forecast-" + offer.contract.player_id,
                              offer.contract.contract_id, "synthetic-model", "SYNTHETIC_TEST",
                              "conditional_on_appearance", ("synthetic-input-hash",),
                              DECISION - 2 * MINUTE, DECISION - 3 * MINUTE,
                              DECISION - timedelta(days=1), DECISION - 4 * MINUTE,
                              offer.event_starts_at, offer.event_starts_at - DECISION,
                              "synthetic-exact-horizon-evidence")
    return replace(result, **changes)


def draft(offers=None, **changes):
    offers = tuple(offers) if offers is not None else (quote(1), quote(2))
    result = ManualDraft(offers, tuple(forecast(q) for q in offers), DECISION,
                         "SINGLE", ("NBA",), ("NBA",), PaperMode.MIXED, 5 * MINUTE)
    return replace(result, **changes)


def terms_for(ticket, **changes):
    count = len(ticket.quotes)
    result = EntryTerms("synthetic-terms", "fictional-venue", "fictional-product", "fictional-rules-v1",
                        tuple(q.quote_id for q in ticket.quotes), "synthetic-terms-evidence",
                        "synthetic-eligibility-evidence", ("fictional-rules-v1",),
                        {("win",) * count: 3.0, ("loss",) * count: 0.0},
                        DECISION - MINUTE, DECISION - timedelta(days=1), DECISION + timedelta(days=1),
                        DECISION - MINUTE)
    return replace(result, **changes)


def joint_for(ticket, **changes):
    count = len(ticket.quotes)
    result = JointOutcomes(tuple(q.quote_id for q in ticket.quotes),
                           {("win",) * count: 0.4, ("loss",) * count: 0.6},
                           "SUPPLIED_DEPENDENT_SCENARIO", ("Invented complete joint law for software test.",),
                           "synthetic-joint-evidence", "SYNTHETIC_TEST", DECISION - MINUTE)
    return replace(result, **changes)


class ManualDraftTests(unittest.TestCase):
    def test_valid_draft_preserves_exact_quotes_and_stays_unqualified(self):
        ticket = draft()
        result = validate_draft(ticket)
        self.assertTrue(result.accepted, result.reasons)
        self.assertEqual(result.qualification, "UNAVAILABLE")
        record = json.loads(json.dumps(ticket.to_record()))
        self.assertEqual(record["legs"][0]["quote_id"], ticket.quotes[0].quote_id)
        self.assertEqual(record["legs"][0]["contract"], ticket.quotes[0].contract.to_record())
        changed = draft((replace(quote(1), price=Decimal("1.92")), quote(2)))
        self.assertNotEqual(ticket.draft_id, changed.draft_id)

    def test_two_through_six_legs_and_six_is_not_required(self):
        for count in range(2, 7):
            self.assertTrue(validate_draft(draft(quote(i) for i in range(1, count + 1))).accepted)
        for count in (0, 1, 7):
            self.assertIn("LEG_COUNT_OUTSIDE_2_TO_6",
                          validate_draft(draft(quote(i) for i in range(1, count + 1))).reasons)

    def test_all_scope_means_supported_only_and_selected_does_not_expand(self):
        nba_wnba = (quote(1), quote(2, league="WNBA"))
        for mode, selected in (("SELECTED", ("NBA", "WNBA")), ("ALL", ())):
            ticket = draft(nba_wnba, scope_mode=mode, selected_sports=selected,
                           supported_sports=("NBA", "WNBA"))
            self.assertTrue(validate_draft(ticket).accepted)
        ticket = draft(nba_wnba, scope_mode="SELECTED", selected_sports=("NBA",),
                       supported_sports=("NBA", "WNBA"))
        self.assertIn("LEG_OUTSIDE_SELECTED_SCOPE", validate_draft(ticket).reasons)
        self.assertIn("INVALID_SPORT_SCOPE", validate_draft(draft(selected_sports=("WNBA",))).reasons)
        self.assertIn("INVALID_SPORT_SCOPE", validate_draft(draft(scope_mode="ALL")).reasons)

    def test_side_modes(self):
        mixed = (quote(1, side="over"), quote(2, side="under"))
        self.assertTrue(validate_draft(draft(mixed)).accepted)
        for mode in (PaperMode.OVER_ONLY, PaperMode.UNDER_ONLY):
            self.assertIn("SIDE_OUTSIDE_POLICY", validate_draft(draft(mixed, mode=mode)).reasons)
        self.assertTrue(validate_draft(draft(mode=PaperMode.OVER_ONLY)).accepted)
        self.assertTrue(validate_draft(draft((quote(1, side="under"), quote(2, side="under")),
                                                   mode=PaperMode.UNDER_ONLY)).accepted)

    def test_one_venue_product_and_settlement_version(self):
        for name in ("venue", "product", "settlement_version"):
            result = validate_draft(draft((quote(1), quote(2, **{name: "different"}))))
            self.assertIn("VENUE_PRODUCT_OR_RULES_MISMATCH", result.reasons)

    def test_initial_policy_requires_distinct_players_and_games(self):
        same_player = draft((quote(1), quote(2, player_id=quote(1).contract.player_id)))
        self.assertIn("REPEATED_PLAYER_UNSUPPORTED", validate_draft(same_player).reasons)
        same_game = draft((quote(1), quote(2, event_id=quote(1).contract.event_id)))
        self.assertIn("SAME_GAME_UNSUPPORTED", validate_draft(same_game).reasons)
        duplicate = draft((quote(1), quote(1)))
        self.assertIn("DUPLICATE_CONTRACT", validate_draft(duplicate).reasons)

    def test_one_clock_rejects_future_stale_started_and_unknown_source_quotes(self):
        changes = (
            {"observed_at": DECISION + MINUTE},
            {"observed_at": DECISION - 6 * MINUTE, "source_updated_at": DECISION - 6 * MINUTE},
            {"event_starts_at": DECISION},
            {"source_updated_at": None},
            {"status": "suspended"},
        )
        for change in changes:
            ticket = replace(draft(), quotes=(replace(quote(1), **change), quote(2)))
            self.assertTrue(any("LEG_1_QUOTE:" in reason for reason in validate_draft(ticket).reasons))
        unknown = draft((replace(quote(1), source_updated_at=None), quote(2)), require_source_timestamp=False)
        self.assertTrue(validate_draft(unknown).accepted)
        self.assertFalse(validate_draft(draft((replace(quote(1), source_updated_at=DECISION - 6 * MINUTE),
                                                       quote(2)))).accepted)
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            draft(decision_at=DECISION.replace(tzinfo=None))

    def test_forecasts_must_match_exact_contracts(self):
        ticket = draft()
        for forecasts in ((), (ticket.forecasts[0], ticket.forecasts[0]),
                          (forecast(quote(1, stat="AST")), ticket.forecasts[1])):
            self.assertFalse(validate_draft(replace(ticket, forecasts=forecasts)).accepted)

    def test_forecast_clocks_prevent_future_training_inputs_and_issuance(self):
        ticket = draft()
        for field, value in (("issued_at", DECISION + MINUTE),
                             ("cutoff_at", DECISION),
                             ("trained_through", DECISION),
                             ("input_available_at", DECISION)):
            future = replace(ticket.forecasts[0], **{field: value})
            result = validate_draft(replace(ticket, forecasts=(future, ticket.forecasts[1])))
            self.assertIn("LEG_1_FORECAST_NOT_AVAILABLE_ASOF_DECISION", result.reasons)

    def test_exact_later_leg_horizon_is_not_inferred_from_t90(self):
        ticket = draft()
        self.assertEqual(ticket.forecasts[1].supported_decision_horizon, 180 * MINUTE)
        for changes in ({"supported_decision_horizon": 90 * MINUTE},
                        {"supported_decision_horizon": None}, {"horizon_evidence_id": None}):
            wrong = replace(ticket.forecasts[1], **changes)
            result = validate_draft(replace(ticket, forecasts=(ticket.forecasts[0], wrong)))
            self.assertIn("LEG_2_DECISION_HORIZON_UNSUPPORTED", result.reasons)
        wrong_start = replace(ticket.forecasts[0], event_starts_at=DECISION + 91 * MINUTE)
        self.assertIn("LEG_1_FORECAST_EVENT_START_MISMATCH",
                      validate_draft(replace(ticket, forecasts=(wrong_start, ticket.forecasts[1]))).reasons)


class PaperEconomicsTests(unittest.TestCase):
    def calculate(self, ticket=None, *, terms=None, joint=None):
        ticket = ticket or draft()
        return draft_ev(ticket, terms=terms or terms_for(ticket), joint=joint or joint_for(ticket),
                        max_terms_age=5 * MINUTE)

    def test_explicit_dependent_scenario_stays_uncertified(self):
        result = self.calculate()
        self.assertAlmostEqual(result.expectation.net_return, 0.2)
        self.assertAlmostEqual(result.expectation.all_win_probability, 0.4)
        self.assertEqual(result.provider_certification, "NOT_PROVIDER_CERTIFIED")
        self.assertEqual(result.qualification, "UNAVAILABLE")
        self.assertEqual(result.terms_provenance, "SCENARIO_INPUT")

    def test_all_listed_push_void_and_reduction_states_need_actual_supplied_payouts(self):
        ticket = draft()
        joint = joint_for(ticket, state_probabilities={
            ("win", "win"): 0.2, ("loss", "win"): 0.4,
            ("push", "win"): 0.1, ("void", "win"): 0.3})
        terms = terms_for(ticket, gross_payouts={
            ("win", "win"): 3.0, ("loss", "win"): 0.0,
            ("push", "win"): 1.4, ("void", "win"): 1.0})
        self.assertAlmostEqual(self.calculate(ticket, terms=terms, joint=joint).expectation.net_return, 0.04)
        with self.assertRaisesRegex(ValueError, "explicit gross payout"):
            self.calculate(ticket, joint=joint)
        for bad in ({("win", "win"): 0.8}, {("win", "win"): float("nan")}):
            with self.assertRaises(ValueError):
                self.calculate(ticket, joint=joint_for(ticket, state_probabilities=bad))

    def test_exact_terms_and_joint_quote_order_cannot_change(self):
        ticket = draft()
        reversed_ids = tuple(q.quote_id for q in reversed(ticket.quotes))
        with self.assertRaisesRegex(ValueError, "exact draft quote IDs"):
            self.calculate(ticket, terms=terms_for(ticket, quote_ids=reversed_ids))
        with self.assertRaisesRegex(ValueError, "exact draft quote IDs"):
            self.calculate(ticket, joint=joint_for(ticket, quote_ids=reversed_ids))
        for field in ("venue", "product", "settlement_version"):
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                self.calculate(ticket, terms=terms_for(ticket, **{field: "different"}))

    def test_terms_joint_and_rules_must_exist_at_the_common_decision(self):
        ticket = draft()
        for changes in ({"captured_at": DECISION + MINUTE},
                        {"captured_at": DECISION - 6 * MINUTE, "source_updated_at": DECISION - 6 * MINUTE},
                        {"effective_from": DECISION + MINUTE}, {"effective_until": DECISION},
                        {"source_updated_at": None}, {"source_updated_at": DECISION - 6 * MINUTE}):
            with self.assertRaises(ValueError):
                self.calculate(ticket, terms=terms_for(ticket, **changes))
        with self.assertRaisesRegex(ValueError, "after the common decision"):
            self.calculate(ticket, joint=joint_for(ticket, available_at=DECISION + MINUTE))
        with self.assertRaisesRegex(ValueError, "rule IDs"):
            terms_for(ticket, rule_ids=())
        with self.assertRaisesRegex(ValueError, "joint-outcome assumptions"):
            joint_for(ticket, assumptions=())
        with self.assertRaisesRegex(ValueError, "eligibility_evidence_id"):
            terms_for(ticket, eligibility_evidence_id="")

    def test_state_and_payout_inputs_are_frozen_and_never_create_independence(self):
        ticket = draft()
        probabilities = {("win", "win"): 0.4, ("loss", "loss"): 0.6}
        payouts = {("win", "win"): 3.0, ("loss", "loss"): 0.0}
        joint = joint_for(ticket, state_probabilities=probabilities)
        terms = terms_for(ticket, gross_payouts=payouts)
        probabilities[("win", "win")] = 0
        payouts[("win", "win")] = 100
        self.assertAlmostEqual(self.calculate(ticket, terms=terms, joint=joint).expectation.net_return, 0.2)
        with self.assertRaises(TypeError):
            terms.gross_payouts[("win", "win")] = 100
        with self.assertRaisesRegex(ValueError, "draft rejected"):
            self.calculate(draft(mode=PaperMode.UNDER_ONLY))


class SixFirstPolicyTests(unittest.TestCase):
    def assessment(self, count, qualifies, label="a"):
        return FullTicketAssessment(f"fictional-ticket-{count}-{label}",
                                    tuple(f"synthetic-quote-{i}" for i in range(count)),
                                    qualifies, "synthetic-full-ticket-assessment", () if qualifies else ("FAILED",))

    def test_six_preference_requires_full_ticket_qualification(self):
        five = self.assessment(5, True)
        six = self.assessment(6, False)
        self.assertIs(choose_six_first((six, five, self.assessment(2, True))), five)
        qualified_six = replace(six, qualifies=True, reasons=())
        self.assertIs(choose_six_first((five, qualified_six)), qualified_six)

    def test_fewer_legs_and_no_action_never_fill_from_candidates(self):
        two = self.assessment(2, True)
        self.assertIs(choose_six_first((self.assessment(6, False), two)), two)
        self.assertIsNone(choose_six_first((self.assessment(6, False),)))
        self.assertIsNone(choose_six_first(()))
        with self.assertRaisesRegex(ValueError, "full-ticket assessments"):
            choose_six_first((6, 5))
        with self.assertRaisesRegex(ValueError, "2–6"):
            self.assessment(1, True)


if __name__ == "__main__":
    unittest.main()

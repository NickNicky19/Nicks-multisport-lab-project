"""Synthetic probability/coherence/numerical tests; no development-row scoring."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import math
from itertools import product
import unittest

from multisport_lab.baseline import (COUNT_FIELDS, MARKETS, ForecastTarget, JointForecast,
    PrimitiveLine, WeightedOutcome, evaluate_forecast)
from multisport_lab.count_support import (CountSupportForecast, CountDistribution,
    MIXTURE_SHARE, NegativeBinomial2, NumericalLawError, TERMS, _coefficients,
    _double_triple_probabilities, _log_coefficient, _threshold_probability,
    empirical_variogram_score, evaluate_count_support)


def primitive(**changes):
    values = dict(minutes=20, fg2m=4, fg3m=1, ftm=2, rebounds=5, assists=3,
                  turnovers=2, blocks=1, steals=1)
    return PrimitiveLine(**(values | changes))


def empirical(lines=None):
    lines = lines or [(primitive(), 0.75), (primitive(minutes=30, fg2m=8,
        fg3m=3, rebounds=11, assists=10, blocks=0), 0.25)]
    target = ForecastTarget("target", "player", datetime(2025, 12, 15, 20, tzinfo=timezone.utc))
    return JointForecast(target, datetime(2026, 10, 20, tzinfo=timezone.utc),
        target.history_freeze, "1"*64,
        tuple(WeightedOutcome(f"source{index}", "player", line, weight)
              for index, (line, weight) in enumerate(lines)), 2, len(lines))


class CountSupportTests(unittest.TestCase):
    def test_nb_closed_form_mean_variance_and_positive_full_support(self):
        for mean in (0.01, 0.3, 2, 13):
            nb = NegativeBinomial2(mean)
            upper = nb.cutoff()
            masses = [nb.pmf(n) for n in range(upper+1)]
            self.assertAlmostEqual(math.fsum(masses)+nb.sf(upper), 1, places=12)
            self.assertAlmostEqual(math.fsum(n*p for n, p in enumerate(masses)), mean, places=9)
            self.assertAlmostEqual(math.fsum((n-mean)**2*p for n, p in enumerate(masses)),
                                   mean+mean*mean/2, places=8)
            for n in (0, 1, 7, 100):
                self.assertTrue(math.isfinite(nb.logpmf(n)))
            self.assertLess(nb.sf(upper), 1e-15)
        with self.assertRaises(ValueError):
            NegativeBinomial2(0)

    def test_positive_recurrence_equals_independent_direct_convolution_and_sum_nb(self):
        primitives = {name: NegativeBinomial2(2) for name in COUNT_FIELDS}
        coefficients = _coefficients(TERMS["BLK+STL"], primitives, 120)
        for n in range(40):
            direct = math.fsum(primitives["blocks"].pmf(k)*primitives["steals"].pmf(n-k)
                               for k in range(n+1))
            # Sum of two shape-2 NB with common p has shape 4.
            closed = math.comb(n+3, 3)*0.5**(n+4)
            self.assertAlmostEqual(coefficients[n], direct, places=14)
            self.assertAlmostEqual(coefficients[n], closed, places=14)
        self.assertAlmostEqual(math.fsum(coefficients), 1, places=13)

    def test_weighted_point_coefficient_enumerates_every_nonnegative_contribution(self):
        primitives = {name: NegativeBinomial2(1) for name in COUNT_FIELDS}
        calculated = _coefficients(TERMS["PTS"], primitives, 40)
        for points in range(20):
            direct = math.fsum(primitives["fg2m"].pmf(twos)*primitives["fg3m"].pmf(threes)
                *primitives["ftm"].pmf(points-2*twos-3*threes)
                for twos in range(points//2+1) for threes in range((points-2*twos)//3+1))
            self.assertAlmostEqual(calculated[points], direct, places=14)

    def test_threshold_and_dd_td_are_actual_positive_probabilities(self):
        primitives = {name: NegativeBinomial2(0.02) for name in COUNT_FIELDS}
        # A rare event remains strictly positive, rather than 1-rounded_CDF.
        rare = _threshold_probability(TERMS["PTS"], primitives)
        self.assertGreater(rare, 0)
        low = _coefficients(TERMS["PTS"], primitives, 200)
        self.assertAlmostEqual(rare, math.fsum(low[10:]), places=16)
        binary = _double_triple_probabilities(primitives)
        self.assertGreater(binary["TD"][1], 0)
        self.assertLess(binary["TD"][1], binary["DD"][1])
        for pair in binary.values():
            self.assertAlmostEqual(math.fsum(pair), 1, places=14)
        # Independent enumeration checks both the threshold mapping and DP.
        probabilities = [rare]+[primitives[name].sf(9) for name in ("rebounds", "assists", "steals", "blocks")]
        for category, threshold in (("DD", 2), ("TD", 3)):
            direct = math.fsum(math.prod(probability if bit else 1-probability
                for bit, probability in zip(bits, probabilities))
                for bits in product((0, 1), repeat=5) if sum(bits) >= threshold)
            self.assertAlmostEqual(binary[category][1], direct, delta=1e-30)
        candidate = CountSupportForecast(empirical())
        self.assertLessEqual(candidate.distribution("TD").mean, candidate.distribution("DD").mean)

    def test_fitting_effective_exposure_is_prior_only_and_cold_zero_is_not_zero_support(self):
        zero = primitive(**{name: 0 for name in COUNT_FIELDS}, minutes=0,
                         minutes_precision="rounded_whole_minutes")
        reference = empirical([(zero, 1.0)])
        reference = replace(reference, player_history_count=0)
        candidate = CountSupportForecast(reference)
        self.assertEqual(candidate.effective_sample_size, 1)
        self.assertTrue(candidate.fitting_metadata()["cold_start"])
        for name in COUNT_FIELDS:
            self.assertEqual(candidate.generator_means[name], 1/3)
        for market in MARKETS:
            self.assertGreater(candidate.distribution(market).pmf(1), 0)
        report = evaluate_count_support(candidate, primitive(fg2m=9))
        for category in report["categories"].values():
            self.assertEqual(category["log_loss_status"], "FINITE")

    def test_joint_derived_means_and_reported_minutes_are_exact_k0(self):
        reference = empirical()
        candidate = CountSupportForecast(reference)
        means = {name: (1-MIXTURE_SHARE)*candidate.empirical_means[name]
                 +MIXTURE_SHARE*candidate.generator_means[name] for name in COUNT_FIELDS}
        distribution = candidate.distribution
        self.assertAlmostEqual(distribution("PTS").mean, 2*means["fg2m"]+3*means["fg3m"]+means["ftm"])
        self.assertAlmostEqual(distribution("PRA").mean, distribution("PTS").mean+means["rebounds"]+means["assists"])
        self.assertAlmostEqual(distribution("PA").mean, distribution("PTS").mean+means["assists"])
        self.assertAlmostEqual(distribution("BLK+STL").mean, means["blocks"]+means["steals"])
        self.assertEqual(candidate.reported_minutes_marginal(), {20: .75, 30: .25})
        observed = primitive(fg2m=15, blocks=9)
        original = evaluate_forecast(reference, observed)
        report = evaluate_count_support(candidate, observed, original)
        self.assertIs(report["minutes_diagnostics"], original["minutes_diagnostics"])
        self.assertEqual(report["minutes_mean"], original["minutes_mean"])
        self.assertEqual(report["observed_minutes"], original["observed_minutes"])
        self.assertEqual(set(report["categories"]), set(MARKETS))
        for market in MARKETS:
            self.assertTrue(math.isfinite(report["categories"][market]["log_loss"]))
            self.assertEqual(report["categories"][market]["support_max"], 1 if market in ("DD", "TD") else None)

    def test_source_cutoff_and_training_bound_are_required(self):
        reference = empirical()
        # JointForecast validates its own clocks, so use the same simple offline
        # wrapper shape as WorkloadForecast to exercise S0's independent gate.
        from types import SimpleNamespace
        forged = SimpleNamespace(**{field: getattr(reference, field) for field in (
            "support", "target", "issued_at", "trained_through", "player_history_count", "pool_history_count", "input_sha256")})
        forged.issued_at = reference.target.cutoff-timedelta(seconds=1)
        with self.assertRaisesRegex(ValueError, "before its target cutoff"):
            CountSupportForecast(forged)
        forged.issued_at = reference.issued_at
        forged.trained_through = reference.target.history_freeze+timedelta(seconds=1)
        with self.assertRaisesRegex(ValueError, "training exceeds"):
            CountSupportForecast(forged)

    def test_actual_joint_law_assigns_unseen_tuple_mass_and_records_own_generation_clock(self):
        reference = empirical()
        candidate = CountSupportForecast(reference)
        counts = {name: 17 for name in COUNT_FIELDS}
        expected = math.log(MIXTURE_SHARE)+math.fsum(candidate.primitives[name].logpmf(17)
                                                    for name in COUNT_FIELDS)
        self.assertAlmostEqual(candidate.primitive_joint_logpmf(counts), expected)
        self.assertGreater(candidate.issued_at, reference.issued_at)
        self.assertEqual(candidate.fitting_metadata()["k0_generation_clock"], reference.issued_at.isoformat())
        with self.assertRaises(ValueError):
            candidate.primitive_joint_logpmf({name: True for name in COUNT_FIELDS})

    def test_grid_is_not_renormalized_and_intervals_use_complete_coefficients(self):
        candidate = CountSupportForecast(empirical())
        for market in MARKETS:
            distribution = candidate.distribution(market)
            self.assertFalse(distribution.diagnostics()["renormalized"])
            self.assertLessEqual(distribution.crps_omission_bound, 1e-9)
            self.assertAlmostEqual(math.fsum(distribution.values), 1, places=10)
            median = distribution.quantile(0.5)
            self.assertGreaterEqual(distribution.cdf(median), 0.5)
            self.assertLess(distribution.cdf(median-1), 0.5)
            if market not in ("TD", "DD"):
                self.assertEqual(distribution.diagnostics()["support"], "all_nonnegative_integers")
                self.assertGreater(distribution.pmf(max(candidate.empirical[market])+1), 0)
        with self.assertRaises(ValueError):
            candidate.distribution("PTS").quantile(1)

    def test_crps_matches_independently_larger_grid_and_binary_brier(self):
        candidate = CountSupportForecast(empirical())
        for market in MARKETS:
            distribution = candidate.distribution(market)
            observed = 1 if market in ("DD", "TD") else 27
            if market in ("DD", "TD"):
                self.assertAlmostEqual(distribution.crps(observed), (distribution.pmf(1)-observed)**2)
                continue
            upper = min(4096, distribution.upper*2)
            larger = _coefficients(TERMS[market], candidate.primitives, upper)
            values = [(1-MIXTURE_SHARE)*candidate.empirical[market].get(n, 0)
                      +MIXTURE_SHARE*larger[n] for n in range(upper+1)]
            cumulative = 0.0
            score = 0.0
            for n, probability in enumerate(values):
                cumulative = math.fsum((cumulative, probability))
                score += (cumulative-(1 if n >= observed else 0))**2
            self.assertAlmostEqual(distribution.crps(observed), score, delta=1e-9)

    def test_log_underflow_and_numeric_budget_never_become_unsupported_model_claim(self):
        primitives = {name: NegativeBinomial2(0.001) for name in COUNT_FIELDS}
        distribution = CountDistribution({0: 1.0}, primitives, terms=TERMS["BLK"])
        self.assertEqual(distribution.pmf(1000), 0)
        self.assertTrue(math.isfinite(distribution.logpmf(1000)))
        self.assertAlmostEqual(distribution.logpmf(1000), math.log(MIXTURE_SHARE)+primitives["blocks"].logpmf(1000), places=8)
        self.assertAlmostEqual(_log_coefficient(TERMS["BLK"], primitives, 1000), primitives["blocks"].logpmf(1000), places=8)
        with self.assertRaises(NumericalLawError):
            distribution.pmf(4097)

    def test_outcome_beyond_prediction_grid_only_extends_numerical_score_not_forecast(self):
        primitives = {name: NegativeBinomial2(0.001) for name in COUNT_FIELDS}
        distribution = CountDistribution({0: 1.0}, primitives, terms=TERMS["BLK"])
        original_grid = distribution.upper
        outcome = original_grid+20
        # Alternative expectation identity using analytic mean and a large grid.
        coefficients = _coefficients(TERMS["BLK"], primitives, outcome+100)
        values = [(1-MIXTURE_SHARE)*(n == 0)+MIXTURE_SHARE*p for n, p in enumerate(coefficients)]
        absolute = math.fsum(abs(n-outcome)*p for n, p in enumerate(values))
        pair_half = math.fsum(p*q*(j-i) for i, p in enumerate(values)
            for j, q in enumerate(values) if j > i)
        self.assertAlmostEqual(distribution.crps(outcome), absolute-pair_half, delta=1e-9)
        self.assertEqual(distribution.upper, original_grid)
        candidate = CountSupportForecast(empirical())
        wrong = evaluate_forecast(empirical(), primitive())
        wrong["target"] = dict(wrong["target"], player_id="other")
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            evaluate_count_support(candidate, primitive(), wrong)

    def test_variogram_power_one_matches_direct_empirical_and_nb_expectation(self):
        reference = empirical()
        observed = primitive()
        expected = math.fsum((abs(getattr(observed, first)-getattr(observed, second))
            -math.fsum(item.weight*abs(getattr(item.line, first)-getattr(item.line, second))
                       for item in reference.support))**2
            for index, first in enumerate(COUNT_FIELDS) for second in COUNT_FIELDS[index+1:])/28
        self.assertAlmostEqual(empirical_variogram_score(reference, observed), expected, places=13)
        candidate = CountSupportForecast(reference)
        self.assertTrue(math.isfinite(candidate.variogram_score(observed)))
        self.assertGreaterEqual(candidate.variogram_score(observed), 0)
        self.assertLessEqual(candidate.dependence_diagnostics["score_omission_upper_bound"], 1e-9)


if __name__ == "__main__":
    unittest.main()

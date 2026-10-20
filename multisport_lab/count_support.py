"""S0: an offline, conditional-on-appearance joint count-support challenger.

The frozen K0 empirical joint law is retained with probability 0.90. With
probability 0.10, eight independent negative-binomial (shape 2) counts are
produced from earlier K0-weighted moments. This is an ex-ante generative
mixture, never an outcome-triggered probability floor. Both lanes draw reported
minutes from the exact K0 marginal; the new count lane assumes count/minute
independence. This does not fix workload coverage or model participation.

Finite numerical grids below are coefficient calculations for an infinite law,
NOT normalized finite-PMF exports. They are deliberately incompatible with the
frozen producer's finite-support interface. No simulation is used.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math

from .baseline import COUNT_FIELDS, MARKETS, evaluate_forecast
from .integrity import digest

MODEL_VERSION = "nba_joint_count_support_s0_v1"
MIXTURE_SHARE = 0.10
NB_SHAPE = 2
PRIOR_COUNT = 0.5
PRIOR_EXPOSURE = 0.5
MAX_GRID = 4096
PRIMITIVE_TAIL_MASS = 1e-16
FIRST_TAIL_MOMENT = 1e-10
MAX_CRPS_OMISSION = 1e-9
MASS_ROUNDOFF_TOLERANCE = 1e-10
DEPENDENCE_OMISSION_TOLERANCE = 1e-9

# Each category is a deterministic function of the SAME eight primitive counts.
TERMS = {
    "PTS": (("fg2m", 2), ("fg3m", 3), ("ftm", 1)),
    "PRA": (("fg2m", 2), ("fg3m", 3), ("ftm", 1), ("rebounds", 1), ("assists", 1)),
    "REB": (("rebounds", 1),), "3PM": (("fg3m", 1),),
    "AST": (("assists", 1),), "RA": (("rebounds", 1), ("assists", 1)),
    "PR": (("fg2m", 2), ("fg3m", 3), ("ftm", 1), ("rebounds", 1)),
    "TOV": (("turnovers", 1),), "BLK": (("blocks", 1),),
    "STL": (("steals", 1),), "BLK+STL": (("blocks", 1), ("steals", 1)),
    "PA": (("fg2m", 2), ("fg3m", 3), ("ftm", 1), ("assists", 1)),
}


class NumericalLawError(ValueError):
    """An explicit numerical/budget failure, never a fabricated zero likelihood."""


class NegativeBinomial2:
    """Number of failures before two successes, mean mu, full nonnegative support."""
    def __init__(self, mean):
        if not isinstance(mean, (int, float)) or not math.isfinite(mean) or mean <= 0:
            raise ValueError("NB mean must be finite and strictly positive")
        self.mean = float(mean)
        self.p = 2.0/(2.0+self.mean)
        self.q = self.mean/(2.0+self.mean)
        self.logp = math.log(self.p)
        self.logq = math.log(self.q)

    def logpmf(self, n):
        if type(n) is not int:
            raise ValueError("count must be an integer")
        return -math.inf if n < 0 else math.log(n+1)+2*self.logp+n*self.logq

    def pmf(self, n):
        return math.exp(self.logpmf(n)) if n >= 0 else 0.0

    def sf(self, n):
        if n < 0:
            return 1.0
        return self.q**(n+1)*(1+(n+1)*self.p)

    def first_tail_moment(self, n):
        """E[X 1(X>n)] = mu P(NB(3,p)>n-1), evaluated positively."""
        if n < 0:
            return self.mean
        return self.mean*self.q**n*(1+n*self.p+n*(n+1)*self.p*self.p/2)

    def cutoff(self):
        n = 16
        while self.sf(n) > PRIMITIVE_TAIL_MASS or self.first_tail_moment(n) > FIRST_TAIL_MOMENT:
            n *= 2
            if n > MAX_GRID:
                raise NumericalLawError("primitive tail budget exceeds maximum numerical grid")
        return n


def _coefficients(terms, primitives, upper):
    """Exact PGF coefficients through upper (apart from floating roundoff).

    A shape-2 NB is the sum of two geometric counts. Multiplying by each
    geometric PGF uses positive new[n]=p*old[n]+q*new[n-a]. Unlike truncating
    each primitive at its tail cutoff, this includes EVERY configuration that
    can contribute to a coefficient <=upper. No cancellation/renormalization.
    """
    if upper > MAX_GRID:
        raise NumericalLawError("requested coefficient exceeds maximum numerical grid")
    result = [1.0]+[0.0]*upper
    for name, coefficient in terms:
        nb = primitives[name]
        for _ in range(NB_SHAPE):
            updated = [0.0]*(upper+1)
            for n in range(upper+1):
                updated[n] = nb.p*result[n]+(nb.q*updated[n-coefficient] if n >= coefficient else 0.0)
            result = updated
    return result


def _logadd(a, b):
    if a == -math.inf:
        return b
    if b == -math.inf:
        return a
    higher, lower = (a, b) if a >= b else (b, a)
    return higher+math.log1p(math.exp(lower-higher))


def _log_coefficient(terms, primitives, n):
    if n > MAX_GRID:
        raise NumericalLawError("observed likelihood calculation exceeds maximum numerical grid")
    result = [0.0]+[-math.inf]*n
    for name, coefficient in terms:
        nb = primitives[name]
        for _ in range(NB_SHAPE):
            updated = [-math.inf]*(n+1)
            for k in range(n+1):
                updated[k] = _logadd(nb.logp+result[k],
                    nb.logq+updated[k-coefficient] if k >= coefficient else -math.inf)
            result = updated
    return result[n]


def _threshold_probability(terms, primitives, threshold=10):
    """P(sum a_i X_i >=threshold), using a positive absorbing-overflow DP."""
    masses = [1.0]+[0.0]*threshold
    for name, coefficient in terms:
        nb = primitives[name]
        updated = [0.0]*(threshold+1)
        updated[threshold] = masses[threshold]
        for state in range(threshold):
            maximum = (threshold-1-state)//coefficient
            for n in range(maximum+1):
                updated[state+coefficient*n] += masses[state]*nb.pmf(n)
            updated[threshold] += masses[state]*nb.sf(maximum)
        masses = updated
    if abs(math.fsum(masses)-1) > MASS_ROUNDOFF_TOLERANCE:
        raise NumericalLawError("threshold DP mass residual exceeds roundoff tolerance")
    return masses[-1]


def _double_triple_probabilities(primitives):
    probabilities = [_threshold_probability(TERMS["PTS"], primitives)]
    probabilities += [primitives[name].sf(9) for name in ("rebounds", "assists", "steals", "blocks")]
    counts = [1.0]+[0.0]*5
    for probability in probabilities:
        updated = [0.0]*6
        for count, mass in enumerate(counts):
            updated[count] += mass*(1-probability)
            if count < 5:
                updated[count+1] += mass*probability
        counts = updated
    return {"DD": (math.fsum(counts[:2]), math.fsum(counts[2:])),
            "TD": (math.fsum(counts[:3]), math.fsum(counts[3:]))}


class CountDistribution:
    """A marginal of S0's infinite joint law, with explicit numerical bounds."""
    def __init__(self, empirical, primitives, terms=None, binary=None):
        self.empirical = empirical
        self.primitives = primitives
        self.terms = terms
        self.binary = binary
        self.empirical_mean = math.fsum(n*p for n, p in empirical.items())
        self.tail_mass_bound = self.first_tail_moment_bound = self.crps_omission_bound = 0.0
        if binary is not None:
            self.upper = 1
            self.generator = list(binary)
            self.generator_mean = binary[1]
        else:
            cutoffs = {name: primitives[name].cutoff() for name, _ in terms}
            self.upper = max(max(empirical), sum(coefficient*cutoffs[name] for name, coefficient in terms))
            if self.upper > MAX_GRID:
                raise NumericalLawError("category prediction grid exceeds maximum numerical grid")
            self.generator = _coefficients(terms, primitives, self.upper)
            self.generator_mean = math.fsum(coefficient*primitives[name].mean for name, coefficient in terms)
            self.tail_mass_bound = math.fsum(primitives[name].sf(cutoffs[name]) for name, _ in terms)
            self.first_tail_moment_bound = math.fsum(
                coefficient*primitives[name].first_tail_moment(cutoffs[name]) for name, coefficient in terms)
            # Finite suffix omits <=epsilon*delta at each term; beyond upper,
            # SF_S0^2 <=epsilon^2 SF_generator and the excess first moment bound.
            self.crps_omission_bound = (2*(self.upper+1)*MIXTURE_SHARE*self.tail_mass_bound
                +MIXTURE_SHARE**2*self.first_tail_moment_bound)
            if self.crps_omission_bound > MAX_CRPS_OMISSION:
                raise NumericalLawError("CRPS omitted-tail bound exceeds registered tolerance")
        self.generator_mass_residual = 1-math.fsum(self.generator)
        if abs(self.generator_mass_residual) > self.tail_mass_bound+MASS_ROUNDOFF_TOLERANCE:
            raise NumericalLawError("coefficient mass residual exceeds numerical tolerance")
        self.values = [(1-MIXTURE_SHARE)*empirical.get(n, 0)+MIXTURE_SHARE*self.generator[n]
                       for n in range(self.upper+1)]
        self.mean = (1-MIXTURE_SHARE)*self.empirical_mean+MIXTURE_SHARE*self.generator_mean
        self._cdf = []
        # fsum avoids a long cumulative-addition drift; these arrays are small.
        # A compensated prefix recurrence has O(U) cost with comparable accuracy.
        total = correction = 0.0
        for value in self.values:
            adjusted = value-correction
            updated = total+adjusted
            correction = (updated-total)-adjusted
            total = updated
            self._cdf.append(total)
        self._sf = [0.0]*(self.upper+1)
        total = correction = 0.0
        for n in range(self.upper, -1, -1):
            self._sf[n] = total
            adjusted = self.values[n]-correction
            updated = total+adjusted
            correction = (updated-total)-adjusted
            total = updated

    def pmf(self, n):
        if type(n) is not int:
            raise ValueError("count must be an integer")
        if n < 0 or (self.binary is not None and n > 1):
            return 0.0
        if n <= self.upper:
            return self.values[n]
        generator = _coefficients(self.terms, self.primitives, n)[n]
        return (1-MIXTURE_SHARE)*self.empirical.get(n, 0)+MIXTURE_SHARE*generator

    def logpmf(self, n):
        if type(n) is not int or n < 0:
            raise ValueError("observed count must be a nonnegative integer")
        mass = self.pmf(n)
        if mass > 0:
            return math.log(mass)
        if self.binary is not None:
            raise NumericalLawError("binary outcome lies outside declared support")
        # Underflow is a numerical representation issue, not zero model support.
        return _logadd(math.log((1-MIXTURE_SHARE)*self.empirical[n]) if self.empirical.get(n, 0) else -math.inf,
                       math.log(MIXTURE_SHARE)+_log_coefficient(self.terms, self.primitives, n))

    def cdf(self, n):
        if n < 0:
            return 0.0
        if n > self.upper:
            raise NumericalLawError("CDF query exceeds outcome-independent prediction grid")
        return self._cdf[n]

    def sf(self, n):
        """Positive finite-suffix approximation; omitted mass <=epsilon*bound."""
        if n < 0:
            return 1.0
        if n > self.upper:
            raise NumericalLawError("survival query exceeds prediction grid")
        return self._sf[n]

    def quantile(self, probability):
        if not 0 < probability < 1:
            raise ValueError("quantile requires 0<p<1 for unbounded count support")
        for n, mass in enumerate(self._cdf):
            if mass >= probability:
                return n
        raise NumericalLawError("prediction grid cannot resolve requested quantile")

    def crps(self, observed):
        if type(observed) is not int or observed < 0:
            raise ValueError("CRPS observation must be a nonnegative integer")
        if observed > self.upper:
            # Purely numerical extension of the SAME law. The forecast grid,
            # interval definitions and parameters are not changed by the outcome.
            if observed > MAX_GRID:
                raise NumericalLawError("observed CRPS extension exceeds numerical budget")
            generator = _coefficients(self.terms, self.primitives, observed)
            total = 0.0
            prefix = []
            for n, probability in enumerate(generator):
                total = math.fsum((total, (1-MIXTURE_SHARE)*self.empirical.get(n, 0)+MIXTURE_SHARE*probability))
                prefix.append(total)
            return math.fsum(value*value for value in prefix[:observed])
        return math.fsum(self._cdf[n]**2 for n in range(observed))+math.fsum(
            self._sf[n]**2 for n in range(observed, self.upper+1))

    def diagnostics(self):
        return {"support": "{0,1}" if self.binary is not None else "all_nonnegative_integers",
                "prediction_grid_max": self.upper, "renormalized": False,
                "generator_omitted_mass_upper_bound": self.tail_mass_bound,
                "mixture_sf_omission_upper_bound": MIXTURE_SHARE*self.tail_mass_bound,
                "generator_first_tail_moment_upper_bound": self.first_tail_moment_bound,
                "crps_omission_upper_bound": self.crps_omission_bound,
                "generator_mass_residual": self.generator_mass_residual,
                "mass_roundoff_tolerance": MASS_ROUNDOFF_TOLERANCE,
                "floating_point": "positive_recurrences_compensated_sums_not_interval_arithmetic_certificate"}


class CountSupportForecast:
    """S0 fit from a causally admitted unchanged K0 forecast, no target outcomes."""
    def __init__(self, k0):
        if not k0.support or abs(math.fsum(item.weight for item in k0.support)-1) > 1e-12:
            raise ValueError("S0 requires an admitted normalized K0 support")
        if k0.issued_at < k0.target.cutoff or datetime.now(timezone.utc) < k0.target.cutoff:
            raise ValueError("S0 cannot be generated before its target cutoff")
        if k0.trained_through > k0.target.history_freeze:
            raise ValueError("S0 training exceeds target daily freeze")
        self.k0 = k0
        self.target = k0.target
        self.trained_through = k0.trained_through
        self.player_history_count = k0.player_history_count
        self.pool_history_count = k0.pool_history_count
        self.effective_sample_size = 1/math.fsum(item.weight**2 for item in k0.support)
        empirical = {market: {} for market in MARKETS}
        weighted_counts = {name: [] for name in COUNT_FIELDS}
        for item in k0.support:
            for name in COUNT_FIELDS:
                weighted_counts[name].append(item.weight*getattr(item.line, name))
            for market, value in item.line.market_values().items():
                empirical[market].setdefault(value, []).append(item.weight)
        self.empirical = {market: {n: math.fsum(weights) for n, weights in grouped.items()}
                          for market, grouped in empirical.items()}
        self.empirical_means = {name: math.fsum(values) for name, values in weighted_counts.items()}
        self.generator_means = {name: (self.effective_sample_size*mean+PRIOR_COUNT)
            /(self.effective_sample_size+PRIOR_EXPOSURE) for name, mean in self.empirical_means.items()}
        self.primitives = {name: NegativeBinomial2(mean) for name, mean in self.generator_means.items()}
        binary = _double_triple_probabilities(self.primitives)
        self.dependence_diagnostics = None
        self._distributions = {market: CountDistribution(self.empirical[market], self.primitives,
                terms=TERMS.get(market), binary=binary.get(market)) for market in MARKETS}
        if self._distributions["TD"].mean > self._distributions["DD"].mean+1e-14:
            raise NumericalLawError("joint-law TD probability exceeds DD")
        self.input_sha256 = digest({"model_version": MODEL_VERSION, "k0_input_sha256": k0.input_sha256,
            "mixture_share": MIXTURE_SHARE, "shape": NB_SHAPE,
            "prior_count": PRIOR_COUNT, "prior_exposure": PRIOR_EXPOSURE,
            "effective_sample_size": self.effective_sample_size, "generator_means": self.generator_means})
        self.issued_at = datetime.now(timezone.utc)

    def distribution(self, market):
        try:
            return self._distributions[market]
        except KeyError as exc:
            raise ValueError(f"unsupported market: {market}") from exc

    def reported_minutes_marginal(self):
        """Both generative lanes have this EXACT unchanged K0 minutes law."""
        grouped = {}
        for item in self.k0.support:
            grouped.setdefault(item.line.minutes, []).append(item.weight)
        return {minutes: math.fsum(weights) for minutes, weights in sorted(grouped.items())}

    def primitive_joint_logpmf(self, counts):
        """The actual eight-count joint likelihood (no cross-player semantics)."""
        if set(counts) != set(COUNT_FIELDS) or any(type(value) is not int or value < 0
                                                for value in counts.values()):
            raise ValueError("one nonnegative integer is required for every primitive count")
        empirical_mass = math.fsum(item.weight for item in self.k0.support
            if all(getattr(item.line, name) == counts[name] for name in COUNT_FIELDS))
        generator_log = math.fsum(self.primitives[name].logpmf(counts[name]) for name in COUNT_FIELDS)
        return _logadd(math.log((1-MIXTURE_SHARE)*empirical_mass) if empirical_mass else -math.inf,
                       math.log(MIXTURE_SHARE)+generator_log)

    def fitting_metadata(self):
        return {"model_version": MODEL_VERSION, "k0_input_sha256": self.k0.input_sha256,
            "input_sha256": self.input_sha256, "mixture_share": MIXTURE_SHARE,
            "k0_generation_clock": self.k0.issued_at.isoformat(),
            "s0_generation_clock": self.issued_at.isoformat(),
            "negative_binomial_shape": NB_SHAPE, "prior_count": PRIOR_COUNT,
            "prior_exposure": PRIOR_EXPOSURE, "effective_sample_size": self.effective_sample_size,
            "empirical_primitive_means": self.empirical_means, "generator_primitive_means": self.generator_means,
            "cold_start": self.player_history_count == 0, "inherited_k0_fallback": getattr(self.k0, "fallback", None),
            "reported_minutes": "exact_K0_marginal_in_both_lanes",
            "dependence": "0.90_K0_joint_plus0.10_independent_counts_independent_K0_minutes",
            "participation_semantics": "CONDITIONAL_ON_APPEARANCE", "product_qualification": "UNAVAILABLE"}

    def variogram_score(self, observed):
        expectations = empirical_pair_expectations(self.k0)
        scores, bounds, score_bounds = [], [], []
        for index, first in enumerate(COUNT_FIELDS):
            for second in COUNT_FIELDS[index+1:]:
                one, two = self.primitives[first], self.primitives[second]
                upper = max(one.cutoff(), two.cutoff())
                expected_min = math.fsum(one.sf(k-1)*two.sf(k-1) for k in range(1, upper+1))
                bound = 2*min(one.first_tail_moment(upper), two.first_tail_moment(upper))
                expected_abs = one.mean+two.mean-2*expected_min
                expectation = (1-MIXTURE_SHARE)*expectations[(first, second)]+MIXTURE_SHARE*expected_abs
                actual = abs(getattr(observed, first)-getattr(observed, second))
                scores.append((actual-expectation)**2)
                delta = MIXTURE_SHARE*bound
                bounds.append(delta)
                score_bounds.append(2*abs(actual-expectation)*delta+delta*delta)
        if max(bounds) > DEPENDENCE_OMISSION_TOLERANCE:
            raise NumericalLawError("dependence expectation omitted-tail bound exceeded")
        score_bound = math.fsum(score_bounds)/len(score_bounds)
        if score_bound > DEPENDENCE_OMISSION_TOLERANCE:
            raise NumericalLawError("dependence score omitted-tail bound exceeded")
        self.dependence_diagnostics = {"method": "primitive_variogram_power1_all_scales1_equal_pair_weights1/28",
            "maximum_pair_expected_abs_omission_upper_bound": max(bounds),
            "score_omission_upper_bound": score_bound,
            "floating_point": "operational_mass_checks_not_certified_interval_arithmetic"}
        return math.fsum(scores)/len(scores)


def empirical_pair_expectations(forecast):
    results = {}
    for index, first in enumerate(COUNT_FIELDS):
        for second in COUNT_FIELDS[index+1:]:
            results[(first, second)] = math.fsum(item.weight*abs(
                getattr(item.line, first)-getattr(item.line, second)) for item in forecast.support)
    return results


def empirical_variogram_score(forecast, observed):
    expectations = empirical_pair_expectations(forecast)
    return math.fsum((abs(getattr(observed, first)-getattr(observed, second))-expected)**2
        for (first, second), expected in expectations.items())/28


def evaluate_count_support(forecast, observed, k0_report=None):
    """Underlying-law category diagnostics; reported-minute report reused exactly."""
    original = k0_report if k0_report is not None else evaluate_forecast(forecast.k0, observed)
    actual = observed.market_values()
    if (original.get("target") != forecast.target.to_record()
            or original.get("observed_minutes") != observed.minutes
            or original.get("observed_minutes_precision") != observed.minutes_precision
            or any(original["categories"][market]["observed"] != actual[market] for market in MARKETS)):
        raise ValueError("reused K0 evaluation target/observed identity mismatch")
    categories = {}
    for market in MARKETS:
        distribution = forecast.distribution(market)
        outcome = actual[market]
        intervals = {}
        for level in (0.5, 0.8, 0.95):
            lower = distribution.quantile((1-level)/2)
            upper = distribution.quantile(1-(1-level)/2)
            intervals[str(level)] = {"lower": lower, "upper": upper,
                "predicted_mass": math.fsum(distribution.values[lower:upper+1]),
                "covered": lower <= outcome <= upper, "width": upper-lower}
        upper95 = intervals["0.95"]["upper"]
        probability = distribution.pmf(outcome)
        score = {"observed": outcome, "mean": distribution.mean,
            "median": distribution.quantile(0.5), "crps": distribution.crps(outcome),
            "mean_absolute_error": abs(distribution.mean-outcome),
            "mean_squared_error": (distribution.mean-outcome)**2,
            "log_loss": -distribution.logpmf(outcome),
            "log_loss_status": "FINITE" if probability > 0 else "FINITE_WITH_PROBABILITY_UNDERFLOW",
            "observed_probability": probability if probability > 0 else None,
            "probability_underflow": probability == 0,
            "zero_probability": distribution.pmf(0), "support_min": 0,
            "support_max": 1 if market in ("DD", "TD") else None,
            "probability_above_upper95": distribution.sf(upper95),
            "observed_above_upper95": outcome > upper95, "intervals": intervals}
        if market in ("DD", "TD"):
            event_probability = distribution.pmf(1)
            score.update(probability=event_probability, brier=(event_probability-outcome)**2)
        categories[market] = score
    return {**{key: value for key, value in original.items() if key != "categories"},
        "model_version": MODEL_VERSION, "categories": categories,
        "fitting_metadata": forecast.fitting_metadata(),
        "numerical_diagnostics": {market: forecast.distribution(market).diagnostics() for market in MARKETS}}

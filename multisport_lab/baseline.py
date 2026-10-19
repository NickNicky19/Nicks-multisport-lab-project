"""Coherent, conditional-on-appearance NBA empirical research reference.

R0 is a finite weighted distribution of COMPLETE earlier observed stat lines.
It is not a participation model, a same-game joint law, a qualified product
probability source, or the separate B0/B1/C1 rebound experiment. Historical
availability bounds are reconstructed; issuance is read from the actual clock.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Iterable

from .basketball import BasketballDraw
from .integrity import digest, stamp, utc


PROTOCOL_ID = "NBA-ALL13-JOINT-001"
MODEL_VERSION = "nba_joint_empirical_r0_v1"
FEATURE_VERSION = "nba_pregame_features_v1"
CUTOFF_VERSION = "nba_cutoff_90m_v1"
PANEL_VERSION = "nba_chronological_panel_v1"
EVIDENCE_LANE = "RECONSTRUCTED_RESEARCH"
HALF_LIFE_DAYS = 28.0
PRIOR_APPEARANCES = 5.0
MARKETS = ("PTS", "PRA", "REB", "3PM", "AST", "RA", "PR", "TOV",
           "TD", "DD", "BLK", "STL", "BLK+STL", "PA")
COUNT_FIELDS = ("fg2m", "fg3m", "ftm", "rebounds", "assists", "turnovers",
                "blocks", "steals")


class BaselineError(ValueError):
    """Invalid input or unavailable training support; never a zero forecast."""


def _identity(value: str, field: str) -> None:
    if type(value) is not str or not value or value.strip() != value:
        raise BaselineError(f"{field} must be a nonempty, trimmed identifier")


def _now() -> datetime:
    """A patch point for synthetic clock tests, not a caller-supplied clock."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class PrimitiveLine:
    minutes: float
    fg2m: int
    fg3m: int
    ftm: int
    rebounds: int
    assists: int
    turnovers: int
    blocks: int
    steals: int
    minutes_precision: str = "seconds"

    def __post_init__(self):
        if self.minutes_precision not in ("seconds", "rounded_whole_minutes"):
            raise BaselineError("minutes precision must be documented")
        if (type(self.minutes) not in (int, float)
                or not math.isfinite(self.minutes) or self.minutes < 0):
            raise BaselineError("minutes must be finite and nonnegative")
        if self.minutes == 0 and self.minutes_precision != "rounded_whole_minutes":
            raise BaselineError("an exact-zero-minute record is not an appearance")
        if (self.minutes_precision == "rounded_whole_minutes"
                and not float(self.minutes).is_integer()):
            raise BaselineError("rounded whole minutes require integer values")
        for name in COUNT_FIELDS:
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise BaselineError(f"{name} must be a nonnegative true integer")

    def market_values(self) -> dict[str, int]:
        return BasketballDraw(
            points=2*self.fg2m + 3*self.fg3m + self.ftm,
            rebounds=self.rebounds, assists=self.assists,
            threes_made=self.fg3m, turnovers=self.turnovers,
            blocks=self.blocks, steals=self.steals,
        ).market_values()

    def to_record(self) -> dict:
        return {"minutes": self.minutes, "minutes_precision": self.minutes_precision,
                **{name: getattr(self, name) for name in COUNT_FIELDS}}


@dataclass(frozen=True, slots=True)
class HistoricalAppearance:
    """One completed appearance, with an explicitly reconstructed availability bound.

    Source adapters own DNP versus appearance resolution. A reported rounded zero
    is retained. Missing minutes is a coverage failure, never a fabricated zero.
    Event starts are retrospective archive timestamps, not as-known schedule proof.
    """
    event_id: str
    player_id: str
    team_id: str
    opponent_id: str
    event_start: datetime
    outcome_available_at: datetime
    minutes: float
    fg2m: int
    fg3m: int
    ftm: int
    rebounds: int
    assists: int
    turnovers: int
    blocks: int
    steals: int
    id_namespace: str = "espn"
    minutes_precision: str = "seconds"
    game_duration_minutes: float | None = None

    def __post_init__(self):
        for name in ("event_id", "player_id", "team_id", "opponent_id", "id_namespace"):
            _identity(getattr(self, name), name)
        if self.team_id == self.opponent_id:
            raise BaselineError("team and opponent identities must differ")
        object.__setattr__(self, "event_start", utc(self.event_start))
        object.__setattr__(self, "outcome_available_at", utc(self.outcome_available_at))
        if self.outcome_available_at <= self.event_start:
            raise BaselineError("completed outcome cannot be available before event start")
        self.primitive_line()
        # A permissive reconstructed completion bound still cannot precede the
        # elapsed playing time. No arbitrary 48-minute cap excludes overtime.
        tolerance = 0.5 if self.minutes_precision == "rounded_whole_minutes" else 0.0
        elapsed = (self.outcome_available_at-self.event_start).total_seconds()/60
        if self.minutes-tolerance > elapsed:
            raise BaselineError("played minutes exceed elapsed completion bound")
        if self.game_duration_minutes is not None:
            duration = self.game_duration_minutes
            if (type(duration) not in (int, float) or not math.isfinite(duration)
                    or duration < 48 or (duration-48) % 5 != 0):
                raise BaselineError("NBA final duration must be 48 + 5*overtime periods")
            if self.minutes-tolerance > duration:
                raise BaselineError("played minutes exceed verified game duration")

    def primitive_line(self) -> PrimitiveLine:
        return PrimitiveLine(
            minutes=self.minutes, minutes_precision=self.minutes_precision,
            **{name: getattr(self, name) for name in COUNT_FIELDS})

    def to_record(self) -> dict:
        return {"sport": "basketball", "league": "NBA", "id_namespace": self.id_namespace,
                "event_id": self.event_id, "player_id": self.player_id,
                "team_id": self.team_id, "opponent_id": self.opponent_id,
                "event_start": stamp(self.event_start),
                "outcome_available_at": stamp(self.outcome_available_at),
                "availability_semantics": "reconstructed_completed_outcome_bound",
                "game_duration_minutes": self.game_duration_minutes,
                **self.primitive_line().to_record()}


@dataclass(frozen=True, slots=True)
class ForecastTarget:
    event_id: str
    player_id: str
    event_start: datetime
    id_namespace: str = "espn"

    def __post_init__(self):
        for name in ("event_id", "player_id", "id_namespace"):
            _identity(getattr(self, name), name)
        object.__setattr__(self, "event_start", utc(self.event_start))

    @property
    def cutoff(self) -> datetime:
        return self.event_start-timedelta(minutes=90)

    @property
    def history_freeze(self) -> datetime:
        # The cutoff date matters for games starting just after UTC midnight.
        return self.cutoff.replace(hour=0, minute=0, second=0, microsecond=0)

    def to_record(self) -> dict:
        return {"sport": "basketball", "league": "NBA", "id_namespace": self.id_namespace,
                "event_id": self.event_id, "player_id": self.player_id,
                "event_start": stamp(self.event_start), "cutoff": stamp(self.cutoff)}


@dataclass(frozen=True, slots=True)
class WeightedOutcome:
    source_event_id: str
    source_player_id: str
    line: PrimitiveLine
    weight: float

    def __post_init__(self):
        _identity(self.source_event_id, "source_event_id")
        _identity(self.source_player_id, "source_player_id")
        if (type(self.weight) not in (int, float)
                or not math.isfinite(self.weight) or not 0 < self.weight <= 1):
            raise BaselineError("support weights must be finite positive probabilities")
        if not isinstance(self.line, PrimitiveLine):
            raise BaselineError("support requires a complete primitive line")

    def to_record(self) -> dict:
        return {"source_event_id": self.source_event_id,
                "source_player_id": self.source_player_id,
                "weight": self.weight, "line": self.line.to_record(),
                "markets": self.line.market_values()}


@dataclass(frozen=True, slots=True)
class JointForecast:
    target: ForecastTarget
    issued_at: datetime
    trained_through: datetime
    input_sha256: str
    support: tuple[WeightedOutcome, ...]
    player_history_count: int
    pool_history_count: int

    def __post_init__(self):
        object.__setattr__(self, "issued_at", utc(self.issued_at))
        object.__setattr__(self, "trained_through", utc(self.trained_through))
        if self.issued_at < self.target.cutoff:
            raise BaselineError("a T90 forecast cannot be issued before its cutoff")
        if self.trained_through > self.target.history_freeze:
            raise BaselineError("training outcomes exceed the daily freeze")
        if (not self.support or not math.isclose(
                math.fsum(item.weight for item in self.support), 1.0, abs_tol=1e-12,
                rel_tol=0.0)):
            raise BaselineError("weighted empirical support must sum to one")

    @property
    def cold_start(self) -> bool:
        return self.player_history_count == 0

    def marginal(self, market: str) -> dict[int, float]:
        if market not in MARKETS:
            raise BaselineError(f"unsupported market: {market}")
        grouped: dict[int, list[float]] = {}
        for item in self.support:
            grouped.setdefault(item.line.market_values()[market], []).append(item.weight)
        return {value: math.fsum(weights) for value, weights in sorted(grouped.items())}

    def to_record(self) -> dict:
        record = {
            "protocol_id": PROTOCOL_ID, "model_version": MODEL_VERSION,
            "feature_version": FEATURE_VERSION, "cutoff_version": CUTOFF_VERSION,
            "panel_version": PANEL_VERSION, "evidence_lane": EVIDENCE_LANE,
            "target": self.target.to_record(),
            "participation_semantics": "CONDITIONAL_ON_APPEARANCE",
            "issued_at": stamp(self.issued_at),
            "history_freeze": stamp(self.target.history_freeze),
            "trained_through": stamp(self.trained_through),
            "input_sha256": self.input_sha256,
            "sampling": "exact_weighted_empirical_support_no_monte_carlo",
            "half_life_days": HALF_LIFE_DAYS, "prior_appearances": PRIOR_APPEARANCES,
            "player_history_count": self.player_history_count,
            "pool_history_count": self.pool_history_count, "cold_start": self.cold_start,
            "tail_policy": "finite_observed_support_no_smoothing_or_unseen_tail_mass",
            "same_game_joint_model": False, "product_qualified": False,
            "support": [item.to_record() for item in self.support],
        }
        return {"forecast_id": digest(record), **record}


def forecast_reference(history: Iterable[HistoricalAppearance],
                       target: ForecastTarget) -> JointForecast:
    """Fit the frozen R0 empirical measure using only earlier eligible outcomes.

    Actual execution time is the issuance clock; callers cannot backdate it.
    Historical targets are allowed only in the reconstructed research lane.
    Upcoming targets require execution on or after T90. A captured future lane
    needs a separate authenticated capture path and is not a caller toggle here.
    """
    issued_at = _now()
    if issued_at < target.cutoff:
        raise BaselineError("the T90 cutoff has not occurred")
    eligible = []
    identities = set()
    event_starts = {}
    for row in history:
        if not isinstance(row, HistoricalAppearance):
            raise BaselineError("history must contain resolved HistoricalAppearance rows")
        identity = (row.id_namespace, row.event_id, row.player_id)
        if identity in identities:
            raise BaselineError("duplicate historical event/player identity")
        identities.add(identity)
        if row.id_namespace != target.id_namespace:
            raise BaselineError("identity namespaces must match; crosswalk first")
        if row.event_id in event_starts and event_starts[row.event_id] != row.event_start:
            raise BaselineError("one event has conflicting start timestamps")
        event_starts[row.event_id] = row.event_start
        if (row.event_id != target.event_id
                and row.event_start < target.history_freeze
                and row.outcome_available_at <= target.history_freeze):
            eligible.append(row)
    eligible.sort(key=lambda row: (row.event_start, row.event_id, row.player_id))
    if not eligible:
        raise BaselineError("no eligible earlier completed appearances for league prior")
    # Relative recency is numerically stable even when every row is very old.
    latest = max(row.event_start for row in eligible)
    pool_weights = [2**(-(latest-row.event_start).total_seconds()/86400/HALF_LIFE_DAYS)
                    for row in eligible]
    pool_total = math.fsum(pool_weights)
    own_weights = [2**(-(target.cutoff-row.event_start).total_seconds()/86400/HALF_LIFE_DAYS)
                   if row.player_id == target.player_id else 0.0 for row in eligible]
    denominator = PRIOR_APPEARANCES + math.fsum(own_weights)
    support = tuple(WeightedOutcome(
        source_event_id=row.event_id, source_player_id=row.player_id,
        line=row.primitive_line(),
        weight=(own+PRIOR_APPEARANCES*pool/pool_total)/denominator,
    ) for row, own, pool in zip(eligible, own_weights, pool_weights)
        if own+pool > 0)
    return JointForecast(
        target=target, issued_at=issued_at,
        trained_through=max(row.outcome_available_at for row in eligible),
        input_sha256=digest({"protocol_id": PROTOCOL_ID, "model_version": MODEL_VERSION,
            "target": target.to_record(), "history_freeze": stamp(target.history_freeze),
            "rows": [row.to_record() for row in eligible]}),
        support=support,
        player_history_count=sum(row.player_id == target.player_id for row in eligible),
        pool_history_count=len(eligible),
    )


def _quantile(pmf: dict, probability: float):
    cumulative = 0.0
    for value, weight in pmf.items():
        cumulative += weight
        if cumulative >= probability:
            return value
    return max(pmf)  # Rounding tolerance at probability=1.


def discrete_crps(pmf: dict[int, float], observed: int) -> float:
    """Exact discrete CRPS/RPS for a finite nonnegative-count distribution.

    E|X-y| - E|X-X'|/2 avoids truncating the CDF before an out-of-support outcome.
    Runtime is O(n log n), not quadratic in the number of historical appearances.
    """
    if type(observed) is not int or observed < 0:
        raise BaselineError("observed count must be a nonnegative true integer")
    if not pmf or any(type(x) is not int or x < 0 for x in pmf):
        raise BaselineError("support values must be nonnegative true integers")
    if (any(type(p) not in (int, float) or not math.isfinite(p) or p < 0
            for p in pmf.values())
            or not math.isclose(math.fsum(pmf.values()), 1, rel_tol=0, abs_tol=1e-12)):
        raise BaselineError("PMF must contain finite nonnegative mass summing to one")
    return _weighted_crps(pmf, observed)


def _weighted_crps(pmf: dict, observed: float) -> float:
    absolute_error = math.fsum(p*abs(x-observed) for x, p in pmf.items())
    previous_mass = previous_moment = pair_half = 0.0
    for x, p in sorted(pmf.items()):
        pair_half += p*(x*previous_mass-previous_moment)
        previous_mass += p
        previous_moment += p*x
    return max(0.0, absolute_error-pair_half)  # Only guards floating roundoff.


def evaluate_forecast(forecast: JointForecast, observed: PrimitiveLine) -> dict:
    """Per-category diagnostics on one explicit appearance; no pooled accuracy label.

    Zero-support log loss is mathematically infinite. JSON uses null plus an
    explicit ZERO_SUPPORT status so finite JSON never converts infinity to a number.
    This is an evaluator, not a registered development/confirmation cohort runner.
    """
    actual = observed.market_values()
    grouped: dict[str, dict[int, list[float]]] = {market: {} for market in MARKETS}
    for item in forecast.support:
        for market, value in item.line.market_values().items():
            grouped[market].setdefault(value, []).append(item.weight)
    categories = {}
    for market in MARKETS:
        pmf = {value: math.fsum(weights) for value, weights in sorted(grouped[market].items())}
        outcome = actual[market]
        mean = math.fsum(value*p for value, p in pmf.items())
        mass = pmf.get(outcome, 0.0)
        intervals = {}
        for level in (0.5, 0.8, 0.95):
            lower = _quantile(pmf, (1-level)/2)
            upper = _quantile(pmf, 1-(1-level)/2)
            intervals[str(level)] = {"lower": lower, "upper": upper,
                "predicted_mass": math.fsum(p for x, p in pmf.items() if lower <= x <= upper),
                "covered": lower <= outcome <= upper, "width": upper-lower}
        upper95 = intervals["0.95"]["upper"]
        scores = {"observed": outcome, "mean": mean, "median": _quantile(pmf, 0.5),
            "crps": discrete_crps(pmf, outcome),
            "mean_absolute_error": abs(mean-outcome),
            "mean_squared_error": (mean-outcome)**2,
            "log_loss": -math.log(mass) if mass else None,
            "log_loss_status": "FINITE" if mass else "ZERO_SUPPORT_INFINITE_LOSS",
            "observed_probability": mass, "zero_probability": pmf.get(0, 0.0),
            "support_min": min(pmf), "support_max": max(pmf),
            "probability_above_upper95": math.fsum(p for x, p in pmf.items() if x > upper95),
            "observed_above_upper95": outcome > upper95, "intervals": intervals}
        if market in ("DD", "TD"):
            probability = pmf.get(1, 0.0)
            scores.update(probability=probability, brier=(probability-outcome)**2)
        categories[market] = scores
    minutes_grouped: dict[float, list[float]] = {}
    for item in forecast.support:
        minutes_grouped.setdefault(item.line.minutes, []).append(item.weight)
    minutes_pmf = {value: math.fsum(weights) for value, weights in sorted(minutes_grouped.items())}
    minutes_mean = math.fsum(value*p for value, p in minutes_pmf.items())
    minutes_intervals = {}
    for level in (0.5, 0.8, 0.95):
        lower = _quantile(minutes_pmf, (1-level)/2)
        upper = _quantile(minutes_pmf, 1-(1-level)/2)
        minutes_intervals[str(level)] = {"lower": lower, "upper": upper,
            "predicted_mass": math.fsum(p for x, p in minutes_pmf.items() if lower <= x <= upper),
            "covered": lower <= observed.minutes <= upper, "width": upper-lower}
    return {"protocol_id": PROTOCOL_ID, "model_version": MODEL_VERSION,
            "evidence_lane": EVIDENCE_LANE,
            "participation_semantics": "CONDITIONAL_ON_APPEARANCE",
            "target": forecast.target.to_record(), "categories": categories,
            "observed_minutes": observed.minutes,
            "observed_minutes_precision": observed.minutes_precision,
            "minutes_mean": minutes_mean,
            "minutes_diagnostics": {"crps": _weighted_crps(minutes_pmf, observed.minutes),
                "mean_absolute_error": abs(minutes_mean-observed.minutes),
                "mean_squared_error": (minutes_mean-observed.minutes)**2,
                "intervals": minutes_intervals,
                "support_precisions": sorted({item.line.minutes_precision for item in forecast.support}),
                "interpretation": "reported_workload_at_documented_source_precision"},
            "product_qualification": "UNAVAILABLE"}


def variogram_score(forecast: JointForecast, observed: PrimitiveLine, *,
                    scales: dict[str, float]) -> float:
    """Eight-count within-player variogram diagnostic, fixed power 1/2.

    Every pair has weight 1/28. Scales MUST be explicitly supplied and frozen
    before evaluation; they are not learned from the target. This diagnostic is
    not strictly proper for the complete law and does not validate same-game or
    cross-player ticket dependence. Minutes/participation need separate evidence.
    """
    if set(scales) != set(COUNT_FIELDS) or any(
            type(value) not in (int, float) or not math.isfinite(value) or value <= 0
            for value in scales.values()):
        raise BaselineError("one finite positive predeclared scale is required per primitive count")
    pair_scores = []
    for index, first in enumerate(COUNT_FIELDS):
        for second in COUNT_FIELDS[index+1:]:
            actual_difference = abs(getattr(observed, first)/scales[first]
                                    - getattr(observed, second)/scales[second])**0.5
            expected_difference = math.fsum(item.weight*abs(
                getattr(item.line, first)/scales[first]
                - getattr(item.line, second)/scales[second])**0.5 for item in forecast.support)
            pair_scores.append((actual_difference-expected_difference)**2)
    return math.fsum(pair_scores)/len(pair_scores)

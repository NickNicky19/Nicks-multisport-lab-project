"""Explicit offline arithmetic. No forecasts, qualification, or venue payout rules."""

from dataclasses import dataclass
from math import fsum, isclose, isfinite, prod
from typing import Mapping, Sequence

from .contracts import PriceKind, PropContract, QuoteObservation


def _number(value, name: str, *, minimum=0.0, maximum=None) -> float:
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{name} must be finite") from None
    if isinstance(value, bool) or not isfinite(number):
        raise ValueError(f"{name} must be finite")
    if number < minimum or (maximum is not None and number > maximum):
        raise ValueError(f"{name} is out of range")
    return number


def _probabilities(values) -> tuple[float, ...]:
    result = tuple(_number(value, "probability", maximum=1.0) for value in values)
    if not result or not isclose(fsum(result), 1.0, rel_tol=0, abs_tol=1e-12):
        raise ValueError("probability mass must sum to 1; it is never renormalized")
    return result


def _decimal_odds(quote: QuoteObservation) -> float:
    if not isinstance(quote, QuoteObservation) or quote.price_kind != PriceKind.SPORTSBOOK_DECIMAL:
        raise ValueError("sportsbook decimal odds are required; a pickem multiplier is not odds")
    value = _number(quote.price, "decimal odds", minimum=1.0)
    if value <= 1.0:
        raise ValueError("decimal odds must exceed 1")
    return value


def single_ev(quote: QuoteObservation, *, p_win, p_loss, p_push=0.0, p_void=0.0) -> float:
    """Net return per unit: pushes and voids return the full stake (zero net)."""
    odds = _decimal_odds(quote)
    win, loss, _, _ = _probabilities((p_win, p_loss, p_push, p_void))
    return win * (odds - 1.0) - loss


@dataclass(frozen=True, slots=True)
class ConditionalNoVig:
    """Proportional estimates conditional on a win/loss settlement, excluding void/push."""
    p_over_given_nonpush: float
    p_under_given_nonpush: float
    overround: float


def conditional_two_sided_no_vig(over: QuoteObservation, under: QuoteObservation) -> ConditionalNoVig:
    """Never supplies push mass or unconditional probabilities at integer lines."""
    over_odds, under_odds = _decimal_odds(over), _decimal_odds(under)
    if over.contract.side != "over" or under.contract.side != "under":
        raise ValueError("supply over and under quotes in that order")
    if over.contract.market_id != under.contract.market_id:
        raise ValueError("both sides must have the identical contract except side")
    if (over.source, over.observed_at, over.line_evidence_id, over.event_starts_at,
        over.source_updated_at, over.status) != (
        under.source, under.observed_at, under.line_evidence_id, under.event_starts_at,
        under.source_updated_at, under.status):
        raise ValueError("both sides must be from the same evidence and capture clocks")
    over_raw, under_raw = 1.0 / over_odds, 1.0 / under_odds
    total = over_raw + under_raw
    return ConditionalNoVig(over_raw / total, under_raw / total, total - 1.0)


def independent_all_hit(probabilities: Sequence[float], *, assume_independent: bool) -> float:
    """Illustration under a declared assumption, not an inferred joint forecast."""
    if assume_independent is not True:
        raise ValueError("independence must be explicitly assumed")
    if not 2 <= len(probabilities) <= 6:
        raise ValueError("provide 2 to 6 leg probabilities")
    return prod(_number(value, "leg probability", maximum=1.0) for value in probabilities)


@dataclass(frozen=True, slots=True)
class TicketExpectation:
    gross_return: float
    net_return: float
    all_win_probability: float


def ticket_ev(legs: Sequence[PropContract], *,
              state_probabilities: Mapping[tuple[str, ...], float],
              gross_payouts: Mapping[tuple[str, ...], float]) -> TicketExpectation:
    """Expected gross/net return for an explicitly supplied complete joint law.

    Omitted states are declared to have probability zero. Every listed probability
    state, including a listed zero, needs an explicit gross payout. Gross includes
    returned stake. Push/void effects are supplied, never guessed. Venue/product
    consistency is checked. Repeated exact markets, including opposite sides,
    are unsupported. These checks do NOT establish an offered/legal ticket.
    """
    if not 2 <= len(legs) <= 6 or any(not isinstance(leg, PropContract) for leg in legs):
        raise ValueError("a ticket needs 2 to 6 PropContract legs")
    if len({(leg.venue, leg.product) for leg in legs}) != 1:
        raise ValueError("all legs must use the same venue and product")
    if len({leg.contract_id for leg in legs}) != len(legs):
        raise ValueError("duplicate contract legs")
    if len({leg.market_id for leg in legs}) != len(legs):
        raise ValueError("multiple legs from the same market are unsupported")
    if not isinstance(state_probabilities, Mapping) or not isinstance(gross_payouts, Mapping):
        raise ValueError("state probabilities and payouts must be mappings")
    for state in (*state_probabilities, *gross_payouts):
        if (not isinstance(state, tuple) or len(state) != len(legs)
                or any(outcome not in {"win", "loss", "push", "void"} for outcome in state)):
            raise ValueError("unknown or incorrectly sized settlement state")
    probabilities = _probabilities(state_probabilities.values())
    if not set(state_probabilities).issubset(gross_payouts):
        raise ValueError("every listed state needs an explicit gross payout")
    payouts = {state: _number(payout, "gross payout") for state, payout in gross_payouts.items()}
    gross = fsum(prob * payouts[state] for state, prob in zip(state_probabilities, probabilities))
    if not isfinite(gross):
        raise ValueError("expected gross payout must be finite")
    all_win = float(state_probabilities.get(("win",) * len(legs), 0.0))
    return TicketExpectation(gross, gross - 1.0, all_win)

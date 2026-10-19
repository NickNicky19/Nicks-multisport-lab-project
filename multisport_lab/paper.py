"""Manual, research-only paper drafts; no provider certification or live selector.

Every clock, eligibility assertion, joint law and payout is caller-supplied evidence.
Validation checks their internal consistency, not upstream truth or model skill.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Sequence

from .contracts import QuoteObservation, _fingerprint, _text, _utc, utc_timestamp, validate_pregame
from .economics import TicketExpectation, ticket_ev
from .publication import resolve_scope


class PaperMode(str, Enum):
    OVER_ONLY = "OVER_ONLY"
    UNDER_ONLY = "UNDER_ONLY"
    MIXED = "MIXED"


def _strings(values, name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be a sequence of strings")
    result = tuple(values)
    for value in result:
        _text(value, name)
    if len(set(result)) != len(result):
        raise ValueError(f"duplicate {name}")
    return result


def _positive_duration(value, name: str) -> timedelta:
    if not isinstance(value, timedelta) or value <= timedelta(0):
        raise ValueError(f"{name} must be a positive timedelta")
    return value


@dataclass(frozen=True, slots=True)
class ForecastEvidence:
    """An immutable reference, with support for this exact decision horizon.

    Horizon evidence is a supplied assertion, not an admission granted here.
    A missing supported horizon can be represented and fails draft validation.
    """
    forecast_id: str
    contract_id: str
    model_version: str
    evidence_lane: str
    conditioning: str
    input_hashes: tuple[str, ...]
    issued_at: datetime
    cutoff_at: datetime
    trained_through: datetime
    input_available_at: datetime
    event_starts_at: datetime
    supported_decision_horizon: timedelta | None = None
    horizon_evidence_id: str | None = None

    def __post_init__(self):
        for name in ("forecast_id", "contract_id", "model_version", "conditioning"):
            _text(getattr(self, name), name)
        if self.evidence_lane not in {"SYNTHETIC_TEST", "RECONSTRUCTED_RESEARCH",
                                      "VERIFIED_ASOF_REPLAY", "REAL_TIME_CAPTURED"}:
            raise ValueError("unknown forecast evidence lane")
        hashes = _strings(self.input_hashes, "input_hashes")
        if not hashes:
            raise ValueError("input hashes are required")
        object.__setattr__(self, "input_hashes", hashes)
        for name in ("issued_at", "cutoff_at", "trained_through", "input_available_at", "event_starts_at"):
            object.__setattr__(self, name, _utc(getattr(self, name), name))
        if self.supported_decision_horizon is not None:
            _positive_duration(self.supported_decision_horizon, "supported_decision_horizon")
        if self.horizon_evidence_id is not None:
            _text(self.horizon_evidence_id, "horizon_evidence_id")

    def to_record(self) -> dict:
        return {"forecast_id": self.forecast_id, "contract_id": self.contract_id,
                "model_version": self.model_version, "evidence_lane": self.evidence_lane,
                "conditioning": self.conditioning, "input_hashes": list(self.input_hashes),
                **{name: utc_timestamp(getattr(self, name)) for name in (
                    "issued_at", "cutoff_at", "trained_through", "input_available_at", "event_starts_at")},
                "supported_decision_horizon_us": (
                    self.supported_decision_horizon // timedelta(microseconds=1)
                    if self.supported_decision_horizon is not None else None),
                "horizon_evidence_id": self.horizon_evidence_id}


@dataclass(frozen=True, slots=True)
class ManualDraft:
    quotes: tuple[QuoteObservation, ...]
    forecasts: tuple[ForecastEvidence, ...]
    decision_at: datetime
    scope_mode: str
    selected_sports: tuple[str, ...]
    supported_sports: tuple[str, ...]
    mode: PaperMode
    max_quote_age: timedelta
    require_source_timestamp: bool = True

    def __post_init__(self):
        for name, kind in (("quotes", QuoteObservation), ("forecasts", ForecastEvidence)):
            values = tuple(getattr(self, name))
            if any(not isinstance(value, kind) for value in values):
                raise ValueError(f"invalid {name}")
            object.__setattr__(self, name, values)
        for name in ("selected_sports", "supported_sports"):
            object.__setattr__(self, name, _strings(getattr(self, name), name))
        object.__setattr__(self, "decision_at", _utc(self.decision_at, "decision_at"))
        object.__setattr__(self, "mode", PaperMode(self.mode))
        _positive_duration(self.max_quote_age, "max_quote_age")
        if type(self.require_source_timestamp) is not bool:
            raise ValueError("require_source_timestamp must be boolean")

    def to_record(self) -> dict:
        """Portable local draft, not a prospective timestamp receipt or qualification."""
        return {"schema_version": 1, "status": "LOCAL_RESEARCH_DRAFT",
                "qualification": "UNAVAILABLE", "decision_at": utc_timestamp(self.decision_at),
                "scope_mode": self.scope_mode, "selected_sports": list(self.selected_sports),
                "supported_sports": list(self.supported_sports), "mode": self.mode.value,
                "max_quote_age_us": self.max_quote_age // timedelta(microseconds=1),
                "require_source_timestamp": self.require_source_timestamp,
                "legs": [{"contract": quote.contract.to_record(), "quote": quote.to_record(),
                          "quote_id": quote.quote_id} for quote in self.quotes],
                "forecasts": [forecast.to_record() for forecast in self.forecasts]}

    @property
    def draft_id(self) -> str:
        return _fingerprint(self.to_record())


@dataclass(frozen=True, slots=True)
class DraftValidation:
    reasons: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return not self.reasons

    @property
    def qualification(self) -> str:
        return "UNAVAILABLE"


def validate_draft(draft: ManualDraft) -> DraftValidation:
    """Check one frozen clock, exact scope and conservative initial eligibility.

    MIXED permits either side; it does not require both. Sport scope names follow
    publication leagues (initially NBA), not the broader sport string basketball.
    Different players AND different events are required in this initial contract.
    """
    if not isinstance(draft, ManualDraft):
        raise ValueError("a ManualDraft is required")
    reasons = []
    if not 2 <= len(draft.quotes) <= 6:
        reasons.append("LEG_COUNT_OUTSIDE_2_TO_6")
    try:
        scope = resolve_scope(draft.scope_mode, list(draft.selected_sports), list(draft.supported_sports))
    except ValueError:
        reasons.append("INVALID_SPORT_SCOPE")
        scope = frozenset()
    contracts = [quote.contract for quote in draft.quotes]
    if any(contract.league not in scope for contract in contracts):
        reasons.append("LEG_OUTSIDE_SELECTED_SCOPE")
    if len({(c.venue, c.product, c.settlement_version) for c in contracts}) != 1:
        reasons.append("VENUE_PRODUCT_OR_RULES_MISMATCH")
    if len({c.contract_id for c in contracts}) != len(contracts):
        reasons.append("DUPLICATE_CONTRACT")
    if len({(c.sport, c.league, c.player_id) for c in contracts}) != len(contracts):
        reasons.append("REPEATED_PLAYER_UNSUPPORTED")
    if len({(c.sport, c.league, c.event_id) for c in contracts}) != len(contracts):
        reasons.append("SAME_GAME_UNSUPPORTED")
    required_side = {PaperMode.OVER_ONLY: "over", PaperMode.UNDER_ONLY: "under"}.get(draft.mode)
    if required_side and any(c.side != required_side for c in contracts):
        reasons.append("SIDE_OUTSIDE_POLICY")
    forecasts = {forecast.contract_id: forecast for forecast in draft.forecasts}
    if len(forecasts) != len(draft.forecasts):
        reasons.append("DUPLICATE_FORECAST_CONTRACT")
    if set(forecasts) != {c.contract_id for c in contracts}:
        reasons.append("FORECAST_CONTRACT_SET_MISMATCH")
    for index, quote in enumerate(draft.quotes):
        try:
            validate_pregame(quote, now=draft.decision_at, max_age=draft.max_quote_age,
                             require_source_timestamp=draft.require_source_timestamp)
        except ValueError as error:
            reasons.append(f"LEG_{index + 1}_QUOTE: {error}")
        forecast = forecasts.get(quote.contract.contract_id)
        if forecast is None:
            continue
        if not (forecast.trained_through <= forecast.cutoff_at <= forecast.issued_at <= draft.decision_at
                and forecast.input_available_at <= forecast.cutoff_at):
            reasons.append(f"LEG_{index + 1}_FORECAST_NOT_AVAILABLE_ASOF_DECISION")
        if forecast.event_starts_at != quote.event_starts_at:
            reasons.append(f"LEG_{index + 1}_FORECAST_EVENT_START_MISMATCH")
        if (not forecast.horizon_evidence_id or forecast.supported_decision_horizon is None
                or forecast.supported_decision_horizon != quote.event_starts_at - draft.decision_at):
            reasons.append(f"LEG_{index + 1}_DECISION_HORIZON_UNSUPPORTED")
    return DraftValidation(tuple(reasons))


@dataclass(frozen=True, slots=True)
class EntryTerms:
    """Supplied exact-entry terms evidence; never certified by this generic module."""
    terms_id: str
    venue: str
    product: str
    settlement_version: str
    quote_ids: tuple[str, ...]
    evidence_id: str
    eligibility_evidence_id: str
    rule_ids: tuple[str, ...]
    gross_payouts: Mapping[tuple[str, ...], float]
    captured_at: datetime
    effective_from: datetime
    effective_until: datetime
    source_updated_at: datetime | None = None
    provenance: str = "SCENARIO_INPUT"

    def __post_init__(self):
        for name in ("terms_id", "venue", "product", "settlement_version", "evidence_id", "eligibility_evidence_id"):
            _text(getattr(self, name), name)
        for name in ("quote_ids", "rule_ids"):
            object.__setattr__(self, name, _strings(getattr(self, name), name))
        if not self.rule_ids:
            raise ValueError("actual supplied settlement rule IDs are required")
        for name in ("captured_at", "effective_from", "effective_until"):
            object.__setattr__(self, name, _utc(getattr(self, name), name))
        if self.effective_from >= self.effective_until:
            raise ValueError("invalid terms effective interval")
        if self.source_updated_at is not None:
            updated = _utc(self.source_updated_at, "source_updated_at")
            if updated > self.captured_at:
                raise ValueError("terms source update cannot be later than capture")
            object.__setattr__(self, "source_updated_at", updated)
        if not isinstance(self.gross_payouts, Mapping):
            raise ValueError("gross_payouts must be a mapping")
        object.__setattr__(self, "gross_payouts", MappingProxyType(dict(self.gross_payouts)))
        if self.provenance not in {"SCENARIO_INPUT", "CAPTURED_TERMS"}:
            raise ValueError("unknown terms provenance")


@dataclass(frozen=True, slots=True)
class JointOutcomes:
    quote_ids: tuple[str, ...]
    state_probabilities: Mapping[tuple[str, ...], float]
    method: str
    assumptions: tuple[str, ...]
    evidence_id: str
    probability_source: str
    available_at: datetime

    def __post_init__(self):
        for name in ("method", "evidence_id", "probability_source"):
            _text(getattr(self, name), name)
        for name in ("quote_ids", "assumptions"):
            object.__setattr__(self, name, _strings(getattr(self, name), name))
        if not self.assumptions:
            raise ValueError("explicit joint-outcome assumptions are required")
        object.__setattr__(self, "available_at", _utc(self.available_at, "available_at"))
        if not isinstance(self.state_probabilities, Mapping):
            raise ValueError("state_probabilities must be a mapping")
        object.__setattr__(self, "state_probabilities", MappingProxyType(dict(self.state_probabilities)))


@dataclass(frozen=True, slots=True)
class PaperExpectation:
    expectation: TicketExpectation
    draft_id: str
    terms_id: str
    joint_evidence_id: str
    terms_provenance: str

    @property
    def provider_certification(self) -> str:
        return "NOT_PROVIDER_CERTIFIED"

    @property
    def qualification(self) -> str:
        return "UNAVAILABLE"


def draft_ev(draft: ManualDraft, *, terms: EntryTerms, joint: JointOutcomes,
             max_terms_age: timedelta) -> PaperExpectation:
    """Evaluate supplied states/payouts only after complete draft evidence checks.

    Payouts include returned stake and must explicitly cover every listed state,
    including pushes, voids and entry reductions. No provider defaults are used.
    A pool component absent from supplied terms is not valued by this function.
    """
    result = validate_draft(draft)
    if not result.accepted:
        raise ValueError("draft rejected: " + "; ".join(result.reasons))
    if not isinstance(terms, EntryTerms) or not isinstance(joint, JointOutcomes):
        raise ValueError("exact entry terms and joint outcomes are required")
    _positive_duration(max_terms_age, "max_terms_age")
    quote_ids = tuple(quote.quote_id for quote in draft.quotes)
    identity = {(q.contract.venue, q.contract.product, q.contract.settlement_version) for q in draft.quotes}
    if identity != {(terms.venue, terms.product, terms.settlement_version)}:
        raise ValueError("terms venue/product/settlement identity mismatch")
    if terms.quote_ids != quote_ids or joint.quote_ids != quote_ids:
        raise ValueError("terms and joint state order must match exact draft quote IDs")
    if not (terms.captured_at <= draft.decision_at
            and draft.decision_at - terms.captured_at <= max_terms_age
            and terms.effective_from <= draft.decision_at < terms.effective_until):
        raise ValueError("terms unavailable, stale or ineffective at the common decision")
    if terms.source_updated_at is None:
        if draft.require_source_timestamp:
            raise ValueError("terms source update time is unknown")
    elif draft.decision_at - terms.source_updated_at > max_terms_age:
        raise ValueError("terms source update is stale")
    if joint.available_at > draft.decision_at:
        raise ValueError("joint outcome evidence is after the common decision")
    expectation = ticket_ev([q.contract for q in draft.quotes],
                            state_probabilities=joint.state_probabilities,
                            gross_payouts=terms.gross_payouts)
    return PaperExpectation(expectation, draft.draft_id, terms.terms_id, joint.evidence_id, terms.provenance)


@dataclass(frozen=True, slots=True)
class FullTicketAssessment:
    """Externally supplied complete-ticket outcome, not a marginal-leg count."""
    ticket_id: str
    quote_ids: tuple[str, ...]
    qualifies: bool
    assessment_evidence_id: str
    reasons: tuple[str, ...] = ()

    def __post_init__(self):
        _text(self.ticket_id, "ticket_id")
        _text(self.assessment_evidence_id, "assessment_evidence_id")
        object.__setattr__(self, "quote_ids", _strings(self.quote_ids, "quote_ids"))
        object.__setattr__(self, "reasons", _strings(self.reasons, "reasons"))
        if not 2 <= len(self.quote_ids) <= 6 or type(self.qualifies) is not bool:
            raise ValueError("an assessment needs 2–6 distinct quotes and an explicit boolean result")


def choose_six_first(assessments: Sequence[FullTicketAssessment]) -> FullTicketAssessment | None:
    """Pure policy: six, then five through two, else None (NO_ACTION).

    Within a size, caller order breaks ties. This helper neither generates tickets
    nor grants qualification; actual project qualification remains unavailable.
    """
    values = tuple(assessments)
    if any(not isinstance(value, FullTicketAssessment) for value in values):
        raise ValueError("explicit full-ticket assessments are required")
    if len({value.ticket_id for value in values}) != len(values):
        raise ValueError("duplicate ticket assessment")
    for size in range(6, 1, -1):
        for value in values:
            if len(value.quote_ids) == size and value.qualifies:
                return value
    return None

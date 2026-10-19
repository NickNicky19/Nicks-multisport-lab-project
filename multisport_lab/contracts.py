"""Original, offline contract/observation records; no source or venue is certified."""

from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be a nonempty, trimmed string")
    return value


def _decimal(value, name: str) -> Decimal:
    try:
        result = Decimal(str(value)) if not isinstance(value, bool) else Decimal("NaN")
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{name} must be a finite number") from None
    if not result.is_finite():
        raise ValueError(f"{name} must be a finite number")
    return result


def _decimal_text(value: Decimal) -> str:
    # Exact canonicalization without Decimal.normalize() context rounding.
    if value.is_zero():
        return "0"
    digits = list(value.as_tuple().digits)
    exponent = value.as_tuple().exponent
    while digits[-1] == 0:
        digits.pop()
        exponent += 1
    sign = "-" if value.is_signed() else ""
    return f"{sign}{''.join(map(str, digits))}e{exponent}"


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def utc_timestamp(value: datetime) -> str:
    """An unambiguous UTC timestamp, including all six microsecond digits."""
    return _utc(value, "timestamp").isoformat(timespec="microseconds").replace("+00:00", "Z")


def _fingerprint(record: dict) -> str:
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PropContract:
    sport: str
    league: str
    event_id: str
    player_id: str
    stat: str
    units: str
    period: str
    extra_time_policy: str
    line: Decimal
    side: str
    variant: str
    venue: str
    product: str
    settlement_version: str

    def __post_init__(self):
        for field in fields(self):
            if field.name != "line":
                _text(getattr(self, field.name), field.name)
        object.__setattr__(self, "line", _decimal(self.line, "line"))
        if self.side not in {"over", "under"}:
            raise ValueError("side must be over or under; equality is a separate push state")

    def to_record(self) -> dict:
        record = {field.name: getattr(self, field.name) for field in fields(self)}
        record["line"] = _decimal_text(self.line)
        return record

    @property
    def contract_id(self) -> str:
        return _fingerprint(self.to_record())

    @property
    def market_id(self) -> str:
        """Exact offered market, including venue/rules, excluding only the side."""
        record = self.to_record()
        del record["side"]
        return _fingerprint(record)


class PriceKind(str, Enum):
    SPORTSBOOK_DECIMAL = "sportsbook_decimal"
    PICKEM_MULTIPLIER = "pickem_multiplier"


@dataclass(frozen=True, slots=True)
class QuoteObservation:
    contract: PropContract
    price: Decimal
    price_kind: PriceKind
    source: str
    observed_at: datetime
    event_starts_at: datetime
    line_evidence_id: str
    price_evidence_id: str
    source_updated_at: datetime | None = None
    status: str = "pre_game"

    def __post_init__(self):
        if not isinstance(self.contract, PropContract):
            raise ValueError("contract must be a PropContract")
        for name in ("source", "line_evidence_id", "price_evidence_id"):
            _text(getattr(self, name), name)
        if self.line_evidence_id != self.price_evidence_id:
            raise ValueError("line and price must come from the same captured evidence")
        try:
            object.__setattr__(self, "price_kind", PriceKind(self.price_kind))
        except (ValueError, TypeError):
            raise ValueError("unknown price kind") from None
        object.__setattr__(self, "price", _decimal(self.price, "price"))
        minimum = 1 if self.price_kind == PriceKind.SPORTSBOOK_DECIMAL else 0
        if self.price <= minimum:
            raise ValueError(f"{self.price_kind.value} price must exceed {minimum}")
        for name in ("observed_at", "event_starts_at", "source_updated_at"):
            value = getattr(self, name)
            if value is not None or name != "source_updated_at":
                object.__setattr__(self, name, _utc(value, name))
        if self.source_updated_at is not None and self.source_updated_at > self.observed_at:
            raise ValueError("source update cannot be later than observation")
        if self.status not in {"pre_game", "live", "closed", "suspended"}:
            raise ValueError("unknown market status")

    def to_record(self) -> dict:
        return {
            "contract_id": self.contract.contract_id,
            "price": _decimal_text(self.price), "price_kind": self.price_kind.value,
            "source": self.source, "observed_at": utc_timestamp(self.observed_at),
            "event_starts_at": utc_timestamp(self.event_starts_at),
            "source_updated_at": (utc_timestamp(self.source_updated_at)
                                  if self.source_updated_at is not None else None),
            "line_evidence_id": self.line_evidence_id,
            "price_evidence_id": self.price_evidence_id, "status": self.status,
        }

    @property
    def quote_id(self) -> str:
        return _fingerprint(self.to_record())


def validate_pregame(quote: QuoteObservation, *, now: datetime, max_age: timedelta,
                     require_source_timestamp: bool = False) -> None:
    """Check supplied clocks/status only; this does not assert current availability."""
    now = _utc(now, "now")
    if not isinstance(max_age, timedelta) or max_age <= timedelta(0):
        raise ValueError("max_age must be a positive timedelta")
    if quote.status != "pre_game" or now >= quote.event_starts_at:
        raise ValueError("quote is not eligible for a pregame check")
    if quote.observed_at > now:
        raise ValueError("observation is in the future")
    if now - quote.observed_at > max_age:
        raise ValueError("stale observation")
    if quote.source_updated_at is None:
        if require_source_timestamp:
            raise ValueError("source update time is unknown")
    elif now - quote.source_updated_at > max_age:
        raise ValueError("stale source update")

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest

from multisport_lab.contracts import PropContract, PriceKind, QuoteObservation, utc_timestamp, validate_pregame


CAPTURE = datetime(2026, 10, 19, 20, 0, 0, 123456, tzinfo=timezone.utc)


def contract(**changes):
    values = dict(sport="basketball", league="nba", event_id="synthetic-event-1",
                  player_id="synthetic-player-1", stat="points", units="points",
                  period="full_game", extra_time_policy="includes_overtime",
                  line=Decimal("22.5"), side="over", variant="standard", venue="synthetic-book",
                  product="sportsbook", settlement_version="synthetic-v1")
    return PropContract(**(values | changes))


def quote(**changes):
    values = dict(contract=contract(), price=Decimal(21) / Decimal(11),
                  price_kind=PriceKind.SPORTSBOOK_DECIMAL, source="synthetic-fixture",
                  observed_at=CAPTURE, event_starts_at=CAPTURE + timedelta(hours=2),
                  line_evidence_id="synthetic-evidence-1", price_evidence_id="synthetic-evidence-1")
    return QuoteObservation(**(values | changes))


class ContractTests(unittest.TestCase):
    def test_identity_retains_contract_meaning_and_exact_decimals(self):
        base = contract()
        for change in (dict(event_id="doubleheader-2"), dict(period="first_quarter"),
                       dict(line="23.5"), dict(venue="another-book"), dict(product="pickem"),
                       dict(side="under"), dict(settlement_version="v2"),
                       dict(extra_time_policy="regulation_only"), dict(variant="alternate")):
            with self.subTest(change=change):
                self.assertNotEqual(base.contract_id, replace(base, **change).contract_id)
        self.assertEqual(base.contract_id, replace(base, line=Decimal("22.5000")).contract_id)
        self.assertEqual(base.market_id, replace(base, side="under").market_id)
        self.assertNotEqual(contract(line="0.12345678901234567890123456781").contract_id,
                            contract(line="0.12345678901234567890123456782").contract_id)

    def test_timestamps_are_full_utc_and_observation_ids_preserve_microseconds(self):
        self.assertEqual(utc_timestamp(CAPTURE), "2026-10-19T20:00:00.123456Z")
        local = CAPTURE.astimezone(timezone(timedelta(hours=-5)))
        self.assertEqual(quote(observed_at=local).quote_id, quote().quote_id)
        self.assertNotEqual(quote().quote_id,
                            quote(observed_at=CAPTURE + timedelta(microseconds=1)).quote_id)

    def test_same_evidence_nonfinite_and_unknown_price_are_rejected(self):
        bad = [dict(price_evidence_id="different-capture"), dict(price="NaN"),
               dict(price="Infinity"), dict(price=True), dict(price_kind="implied_probability"),
               dict(observed_at=CAPTURE.replace(tzinfo=None)),
               dict(source_updated_at=CAPTURE + timedelta(seconds=1))]
        for changes in bad:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                quote(**changes)
        for value in ("NaN", "Infinity", float("nan"), True):
            with self.subTest(line=value), self.assertRaises(ValueError):
                contract(line=value)

    def test_pregame_clocks_and_source_freshness_fail_closed(self):
        q = quote()
        validate_pregame(q, now=CAPTURE + timedelta(minutes=1), max_age=timedelta(minutes=5))
        for now in (CAPTURE - timedelta(microseconds=1), CAPTURE + timedelta(minutes=6),
                    q.event_starts_at):
            with self.subTest(now=now), self.assertRaises(ValueError):
                validate_pregame(q, now=now, max_age=timedelta(minutes=5))
        for bad in (replace(q, status="suspended"),
                    replace(q, source_updated_at=CAPTURE - timedelta(hours=1))):
            with self.assertRaises(ValueError):
                validate_pregame(bad, now=CAPTURE, max_age=timedelta(minutes=5))
        with self.assertRaises(ValueError):
            validate_pregame(q, now=CAPTURE, max_age=timedelta(minutes=5), require_source_timestamp=True)


if __name__ == "__main__":
    unittest.main()

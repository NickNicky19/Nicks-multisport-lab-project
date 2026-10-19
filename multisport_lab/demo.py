"""Run fictional offline examples: python3 -m multisport_lab.demo.

No live odds, trained forecast, issued paper ticket or provider-certified terms.
"""

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .basketball import BasketballDraw
from .contracts import PriceKind, PropContract, QuoteObservation, validate_pregame
from .economics import conditional_two_sided_no_vig, independent_all_hit, single_ev, ticket_ev
from .integrity import read_receipt, write_receipt


def build_demo() -> dict:
    clock = datetime(2026, 1, 1, 18, 0, 0, 123456, tzinfo=timezone.utc)
    leg = PropContract(
        sport="basketball", league="nba", event_id="fictional-event-1",
        player_id="fictional-player-1", stat="rebounds", units="count",
        period="full_game", extra_time_policy="includes_overtime",
        line=Decimal("7.5"), side="over", variant="standard",
        venue="fictional-book", product="sportsbook",
        settlement_version="fictional-full-refund-push-void-v1",
    )
    quote = QuoteObservation(
        contract=leg, price=Decimal(21) / Decimal(11),
        price_kind=PriceKind.SPORTSBOOK_DECIMAL, source="synthetic-fixture",
        observed_at=clock, event_starts_at=clock + timedelta(hours=2),
        line_evidence_id="synthetic-receipt-1", price_evidence_id="synthetic-receipt-1",
    )
    # An explicit historical fixture clock, never a claim of live availability.
    validate_pregame(quote, now=clock + timedelta(minutes=1), max_age=timedelta(minutes=5))
    opposite = replace(quote, contract=replace(leg, side="under"))
    second = replace(leg, event_id="fictional-event-2", player_id="fictional-player-2")
    supplied_law = {
        ("win", "win"): 0.4, ("win", "loss"): 0.2,
        ("loss", "win"): 0.2, ("loss", "loss"): 0.2,
    }
    invented_payouts = {state: 4.0 if state == ("win", "win") else 0.0
                       for state in supplied_law}
    basketball = BasketballDraw(points=28, rebounds=10, assists=12,
                                threes_made=4, turnovers=3, blocks=1, steals=2)
    result = {
        "evidence_lane": "SYNTHETIC_TEST",
        "status": "OFFLINE_EXAMPLES_ONLY",
        "forecast_model_trained": False,
        "live_quote_or_venue_terms_verified": False,
        "supplied_joint_law_is_not_a_forecast": True,
        "supplied_basketball_draw": basketball.market_values(),
        "nba_scope": "All 13 requested categories plus optional PA; deterministic derivation only",
        "fictional_single_net_ev_at_p55": {
            "minus_110": single_ev(quote, p_win=0.55, p_loss=0.45),
            "minus_150": single_ev(replace(quote, price=Decimal(5) / Decimal(3)),
                                  p_win=0.55, p_loss=0.45),
        },
        "fictional_same_quote_pair_no_vig": asdict(conditional_two_sided_no_vig(quote, opposite)),
        "all_legs_win_under_explicit_independence": [
            {"legs": n, "p55": independent_all_hit([0.55] * n, assume_independent=True),
             "p60": independent_all_hit([0.60] * n, assume_independent=True),
             "p65": independent_all_hit([0.65] * n, assume_independent=True)}
            for n in range(2, 7)
        ],
        "fictional_two_leg_supplied_scenario": asdict(ticket_ev(
            [leg, second], state_probabilities=supplied_law, gross_payouts=invented_payouts)),
        "no_current_picks": True,
    }
    with TemporaryDirectory(prefix="multisport-offline-demo-") as temporary:
        path = Path(temporary) / "synthetic_receipt.json"
        created = write_receipt(path, result)
        repeated = write_receipt(path, result)
        recovered = read_receipt(path)
        if not created or repeated or recovered != result:
            raise RuntimeError("Offline evidence round-trip failed")
    return result


def main() -> None:
    print(json.dumps(build_demo(), indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()

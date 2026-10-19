# Offline kernel API

The original standard-library modules `multisport_lab/contracts.py` and
`multisport_lab/economics.py` record contract meaning and evaluate explicitly
supplied scenarios. They do not fetch offers, forecast results, certify venue
rules, or qualify selections.

## Contract and observation records

`PropContract` is an immutable dataclass with these required fields:

```python
PropContract(
    sport, league, event_id, player_id, stat, units,
    period, extra_time_policy, line, side, variant,
    venue, product, settlement_version,
)
```

All text fields must be nonempty and trimmed. `line` becomes a finite `Decimal`.
`side` is `"over"` or `"under"`; equality is a separate settlement outcome.
Stat and rule strings are explicit caller-supplied definitions, not an admitted
market registry. Milestone or other comparison operators are not implemented.

| Member | Meaning |
| --- | --- |
| `contract_id` | SHA-256 identity containing every contract field. |
| `market_id` | The same identity excluding only side; venue and rules still participate. |
| `to_record()` | JSON-safe canonical record; Decimal values are exact numeric strings such as `"225e-1"`. |

Equivalent Decimal scales have the same identity; distinct precise values remain
distinct. Identity equality checks the supplied values. It does not prove athlete
resolution, semantic equivalence, source authenticity, or observation timing.

```python
QuoteObservation(
    contract, price, price_kind, source, observed_at, event_starts_at,
    line_evidence_id, price_evidence_id,
    source_updated_at=None, status="pre_game",
)
```

`price_kind` is `PriceKind.SPORTSBOOK_DECIMAL` or
`PriceKind.PICKEM_MULTIPLIER`. Sportsbook decimal odds must exceed one; a pick'em
multiplier must exceed zero. Both require finite values. The two evidence IDs
must match. This is a provenance assertion; the constructor does not read a source
receipt to prove that the line and price occur together.

Timezone-aware datetimes normalize to UTC. `utc_timestamp(value)` and observation
serialization retain all six microsecond digits. Naive timestamps and source
updates later than capture are rejected. `quote_id` includes contract identity,
price kind/value, evidence, clocks, source, and status.

**A line-only offer has no `QuoteObservation`.** Preserve its `PropContract` and
source receipt separately until matching price evidence is available. Do not fill
an absent price with default odds or a placeholder multiplier.

## Explicit freshness validation

```python
validate_pregame(quote, *, now, max_age, require_source_timestamp=False)
```

Supply a timezone-aware `now` and a positive `timedelta` for `max_age`. The check
rejects non-pregame status, an event at or beyond its supplied start time, future
captures, stale captures, and known stale source updates. Unknown source update
times are rejected when `require_source_timestamp=True`.

This validates supplied metadata only. It cannot detect an external suspension,
price change, or rescheduling absent updated inputs. **Pure economics functions
do not invoke pregame or freshness validation implicitly**; this also permits
their use in clearly labeled historical/offline research.

## Economics functions

`single_ev(quote, *, p_win, p_loss, p_push=0.0, p_void=0.0)` returns expected net
units: `p_win * (decimal_odds - 1) - p_loss`. It assumes pushes and voids return
the entire stake. It requires sportsbook odds; a pick'em multiplier is rejected.
All four masses must be finite, within zero and one, and sum to one within an
absolute floating-point tolerance of `1e-12`. No renormalization is performed.

`conditional_two_sided_no_vig(over_quote, under_quote)` requires sportsbook odds
for the same exact market and matching source/evidence/capture clocks. It returns
`ConditionalNoVig(p_over_given_nonpush, p_under_given_nonpush, overround)` using
proportional removal of margin. The probabilities are conditional on a win/loss
settlement, excluding pushes and voids. The function does not estimate those
excluded masses or create unconditional probabilities at integer lines.

`independent_all_hit(probabilities, *, assume_independent)` multiplies two to six
finite probabilities. `assume_independent` must explicitly be `True`. The result
is an assumption-based illustration; the function does not infer independence.

```python
ticket_ev(legs, *, state_probabilities, gross_payouts)
```

The ticket function requires two to six `PropContract` legs with the same venue
and product. Duplicate contracts and multiple legs sharing the same `market_id`,
including opposite sides, are unsupported in this initial scope.

Both mappings use tuples in leg order, for example `("win", "void")`. Recognized
outcomes are `"win"`, `"loss"`, `"push"`, and `"void"`. The supplied joint law
must sum to one; omitted states are a declaration of zero probability. Every
listed probability state, including listed zero-mass states, needs an explicit,
finite, nonnegative gross payout. Gross payouts include returned stake. No
push/void reduction, Max/Flex payout, or pool reward is inferred.

The result is `TicketExpectation(gross_return, net_return, all_win_probability)`;
`net_return = gross_return - 1`. An explicit state/payout table is scenario input,
not certification that a venue offers that ticket or payout. Beyond the narrow
same-market rejection, the kernel does not verify that arbitrary joint laws are
physically realizable, consistent with a forecast model, or calibrated. Different
thresholds, combined statistics, same-player legs, and other dependencies still
require separate modeling and validation before real paper-selection claims.

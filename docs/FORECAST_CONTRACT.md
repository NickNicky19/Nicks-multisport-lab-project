# Typed NBA research forecasts v1/v2

`forecast_contract.py` and `web/research.mjs` validate
`nba-research-forecast-v1` together. Every bundle has all thirteen requested
categories plus PA, with explicit ESPN NBA event/player/team/opponent identities,
retrospective player label, full-game period including overtime, event start,
model version/full commit/code hash, eligible-input hash and training bound.
It declares T90 cutoff, midnight cutoff-date history freeze, actual issue clock,
conditional-on-appearance meaning, evidence lane and availability basis.

Every category carries units, sorted finite integer-support PMF, mean and central
80% interval from that same PMF. Probability and real score/mean fields use
nonnegative fixed-point decimal **strings**, without exponent notation, to keep
decoded-JSON checksums stable across Python and JavaScript. Clocks use six-digit
microsecond UTC `Z` timestamps; the browser checks their exact ordering without
discarding submillisecond precision. A degenerate one-atom producer PMF is written
as probability `"1"` when floating summation is within 1e-12; supplied arbitrary
PMFs are rejected rather than silently normalized.

Validation checks complete category support, units, mass, means, quantiles,
combination mean identities, scoring bounds, TD≤DD and necessary DD/TD threshold
bounds from primitive tails. These marginal checks cannot prove a full joint law.
`Ledger.issue_forecast(..., reference=actual_joint_forecast)` therefore compares
every marginal and joint/input digest to the actual coherent complete-line R0
producer before saving a binding attestation. All sums and DD/TD come from that
one player-stat law. Raw source/support rows remain out of the public asset.
The attestation is an internal consistency receipt, not a signature, source
authenticity certificate, same-game dependence model or predictive qualification.

Current R0 records are `RECONSTRUCTED_RESEARCH` with `RECONSTRUCTED_BOUND` and no
observed input-capture IDs. Their actual issuance occurs after historical games;
event/player membership is retrospective. Archived start+24h availability is a
research convention, not observed historical publication. The producer explicitly
rejects relabeling these as `REAL_TIME_CAPTURED`. That future lane requires a
separately admitted captured-input producer and a genuine current-clock issue
between cutoff and event. Upcoming stays empty with specific reasons meanwhile.

R0 is conditional on appearance, with finite empirical support and no tail
smoothing, participation model, role/pace adjustment or cross-player joint law.
`qualification=UNAVAILABLE` is independent of implemented category support.
`nba-research-event-v1` ties the bundles to explicit event version/start/team
sets and retrospective/observed schedule meaning. Model provenance, checksum and
passing software checks establish neither calibration nor real-time availability.

`nba-forecast-grade-v1` records exact forecast/outcome IDs, actual grading time,
evidence lane and all-category discrete CRPS, log loss and DD/TD Brier scores.
Zero support keeps `log_loss=null` and `ZERO_SUPPORT`; DNP/unresolved have no
statistical scores. Python and browser recompute scores against the PMFs;
ledger recovery additionally checks the referenced compact source outcome.
`financial_settlement=NOT_EVALUATED` keeps these grades separate from venue rules,
payouts, profits and paper-ticket settlement. See [ledger](DURABLE_LEDGER.md).

## Separately versioned pregame producer contract

`nba-research-forecast-v2` preserves the v1 identity, conditioning, all fourteen
category PMFs, coherence, finite-support and qualification checks and adds one
strict `prospective` object. V2 admits only `REAL_TIME_CAPTURED`,
`OBSERVED_INPUT_CAPTURE`, model `nba_joint_empirical_pregame_r1_v1` and producer
`nba-pregame-r1-v1`. Historical R0 export and producer attestation remain v1 and
reconstructed-only; changing a lane or passing an offline validator does not
admit prospective issuance.

The added object contains exactly: producer version; event version; selection
SHA-256; source-pack SHA-256 and immutable record ID; actual generation start and
completion; minimum/maximum current-source observation clocks; actual normalized
import clock; base R0 version/code SHA-256; complete history row count; and latest
historical event clock. The input-capture ID list must contain exactly the stated
source-pack record ID. All identity hashes use lowercase SHA-256 and all clocks
retain six UTC microsecond digits. The base model remains
`nba_joint_empirical_r0_v1`; generation under a new version does not promote R0
or K0's predictive quality.

With cutoff fixed at event start minus ninety minutes, the strict public timing
contract is:

- Current event/player source observations lie between T90 minus ten minutes and
  T90; their observation range precedes or equals the actual import clock.
- Import finishes by T90. Generation starts at or after T90, completes within
  120 seconds of its start, and completes no later than T90 plus five minutes.
- Generation completion equals actual issuance. The forecast remains before the
  event. A late capture/import/generation cannot be repaired by supplied clocks.
- The complete declared history count is 1–100,000 and the latest historical
  event precedes the daily freeze. The retained 26,645-row cohort is not reduced
  to the separate readiness pilot's 20,000-row cap.

Python and JavaScript enforce these same wire rules. Ledger recovery separately
binds original source records, identities, source-pack hashes and producer
attestation; a well-formed JSON object alone does not establish actual timely
capture, permission, remote durability or genuine issuance. Raw source bytes and
complete support stay outside the public asset. Cards expose the compact capture,
import, generation and source-reference metadata under provenance.

An ungraded forecast is pending whether its event is future or past. It receives
no outcome value or statistical score until a matching verified outcome and grade
are appended. An event start moves a captured record to History but proves no
completion. Statistical grades retain the original lane/model and remain separate
from financial settlement, qualified tickets and confirmatory model evaluation.

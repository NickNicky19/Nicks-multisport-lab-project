# Bounded recurring daily-source planning

This component is planning and exact-input retention, not an operating producer.
`NBA-SDV-DAILY-002` is a separate, inactive proposal. Its records declare
`issuance_authority=NONE_PLANNING_ONLY`; no scheduler, collection, forecast,
statistical grade or public publication is created by this component. The
approved first `NBA-SDV-DAILY-001` cycle and its 23 execution files are unchanged.

## Frozen planning rule

`config/sdv_recurring_reservation_v1.json` records its actual registration clock.
The seven UTC game dates are October 24–30, 2026. Each date's planning window is
the previous UTC day, 13:17–13:47 inclusive. Missing the window does not roll the
reservation forward. This is operational selection, not a new model comparison.

The full retained season schedule is inspected for the requested **UTC game
date**, with all in-date event identities and explicit exclusions retained.
Outside-date rows are counted and bound by exact full-source replay. Select the
first two chronological eligible events, breaking ties by numeric event ID;
keep later eligible games visible as excluded by the daily event limit. Each
selected event uses the existing two-lowest-numeric-active-IDs-per-team rule:
four subjects per event, up to eight player-event subjects across two events.
That is a selection ceiling, not a claim that capacity or forecasts exist.
No player is substituted after planning.

Active roster status means roster membership. It does not establish health,
starting status, participation or minutes. Model identities remain unchanged R0
and K0; all 13 requested categories plus PA remain in scope, conditional on
appearance. The complete fixed 26,645-row reconstructed-history panel and its
cutoff/version remain unchanged. This component never fits either model.

## Source and timing meaning

The existing daily-source normalizer is reused only as a source-interpretation
codec. Its nested `DEVELOPMENT_ONLY` body cannot authorize a v1 forecast. The new
wrapper binds the separate protocol, plan and event identity. Exact CSV and
publisher-release JSON bytes are required. Hashes, asset IDs/names, season,
event/player/team identity, complete inventory, metadata and clocks are replayed;
even an empty/excluded date must match the release asset's actual season.

Existing limits remain: 2-MiB CSV, 256-KiB release JSON, 5,000 source rows and
36-hour publisher age. Complete oversized inputs fail; nothing is truncated.
Publisher update, unknown upstream observation, retrieval, planning start and
planning completion have different fields. Downloading unchanged content does
not refresh its publisher clock. These are initial daily-source operating limits,
not proven scientific freshness thresholds or the original fresh-observation
T90 protocol.

Before a future producer can use an event, a **separate fresh capture** must
revalidate exactly the frozen event and cohort. Retrieval and complete input
validation must finish in T150–T90. The proposed generation/readback window is
T90–T75 with the existing 300-second original latency bound. New code checks the
actual clock after source/semantic validation and rejects completion overruns;
read-only replay uses original clocks and creates no new capture. The component
does not establish local or remote persistence completion, producer authority or
forecast eligibility merely by passing those input checks.

## Retention and recovery

`sdv_recurring_store.py` uses the existing create-only `Ledger` public APIs and a
strict planning schema registry in `recurring/records`. The generic ledger's
`research_inputs` namespace is reserved for its historical-package contract;
these new source observations/plans therefore use typed `input_captures` bodies.
Every recovery validates their meaning and references, not only checksums.
Forecast/outcome/grade bodies are rejected by this planning store.

The exact parent history receipt is authenticated through its original
`LedgerRef`. Sources are losslessly retained with their original release JSON.
Plans reference the two ordered source packs and replay the original source
interpretation. A changed source clock cannot overwrite an original observation;
the later operating path needs a separate observation linked to shared bytes.
Originals interrupted after atomic publication are recovered rather than replaced.

The fixed planning pool is **64 records / 2,097,152 encoded bytes**, shared by
reservation, source packs and plans. It is charged once alongside the greater of
actual original/daily usage and the protected first-cycle reservation of
**155 records / 31,431,880 bytes**. Thus the conservative combined projection is
**219 records / 33,529,032 bytes**, leaving **25,400 bytes** under the unchanged
512-record / 33,554,432-byte limits. Consumption is credited against that pool;
unknown/interrupted files remain charged. Another folder never resets the limit.
This protects the first cycle; it is **not a reserve for expanded forecasts** or
a promise that all seven days' sources will fit. Exhaustion fails closed.

`Ledger.received_at` is a pre-write receipt clock. Recovery explicitly returns
`local_persistence_completion=NOT_ESTABLISHED_BY_RECEIPT_CLOCK`,
`prospective_admission=False` and `genuine_forecasts=0`, including delayed writes.
A local bare-Git round trip verifies independent byte/typed recovery only; it is
not proof of authenticated remote archival or genuine prospective operation.

## Remaining operating work

The fixed v1 cycle, owner-only authorization, eight-forecast export and current
producer-source equality checks cannot admit arbitrary recurring cycles.
The next integration needs strict v2 producer/intent/completion contracts, trusted
scheduled-run authority, fresh-input remote acknowledgments, a new thin typed Git
checkpoint adapter, and bounded per-cycle publication pages with v1 delegation.
The existing `nba-operations.yml` must remain the single coordinator; no second
scheduler should be installed. Status-only failures need authenticated publication
without weakening forecast admission. Cross-cycle outcomes and Performance joins
must include protocol/cycle identity and use each original input's own policy.

Expanded issuance also needs a reviewed actual-plus-unused-role capacity policy;
the planning pool cannot pay for it. Existing first-cycle records and future
outcome/correction obligations stay charged. Keep exact probability atoms and
history; reject an entire unsupported cycle instead of dropping data or silently
raising limits. The retained schedule is already near its 2-MiB raw ceiling, so
season-long operation needs explicit size monitoring and a separate reviewed
source representation if that ceiling is exceeded.

No first-cycle dispatch or new operating activation is installed here. The
already-approved first manual launch and its original clocks remain governed by
`SDV_DAILY_ACTIVATION_PACKAGE.md`. OPS002, PROS004, S0, DEV005 and the expired
October 20 pilot remain unchanged. Offers/odds and ticket qualification remain
independent of price-independent research forecasting.

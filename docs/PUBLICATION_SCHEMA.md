# Static publication contracts

## Joint manifest v5, prepared for review

The combined implementation preserves exact legacy manifest 1/2/3/4 readers and
sport 1/2 contracts. Manifest 5 retains the bounded core fields below and adds four
independent descriptor/error pairs:

| Channel | Fields | Complete asset ceiling |
| --- | --- | --- |
| Reserved PROS004 | `pros004`, `pros004_error` | Existing paged contract, 24 MiB total |
| Source-backed labels/status | `display`, `display_error` | 128 KiB |
| Admitted offer-only facts | `offers`, `offers_error` | 256 KiB, at most 32 contracts |
| Separate one-game paired research | `paired_research`, `paired_research_error` | 1 MiB |

Each descriptor binds a relative content-addressed filename, raw-byte SHA256,
original generation clock and retention/error state. Both producers and browser
readers validate exact fields, paths, sizes, source identities and nested content
seals. Unsafe or invalid descriptors are rejected before fetching. One auxiliary
channel's fetch/meaning/hash error does not erase valid peer channels. A retained
previous valid asset keeps its original generation/source clocks. Rejected or
unreferenced intermediate assets are pruned before the artifact swap.

Research sport 2 still rejects nonempty `offers`, `candidates` and `tickets`.
Actual offers have their own strict `nba-player-offers-v1` asset and reviewed
source/admission registry. Complete verified offer facts may carry
`PRICE_UNAVAILABLE`; no quote, EV or ticket eligibility follows. Incomplete
identity, period/OT, statistical or settlement meaning cannot be filled with
assumptions. The actual admission registry is empty in this readiness revision.
See `OFFER_PUBLICATION_V1.md` and the source-specific audit receipts.

The new paired channel has its own `NBA-PAIRED-OPS-002` identities and typed
originals, completion admission, outcome/grade/correction links. It never relabels
PROS004 or retrospective results. Original canonical contents and hashes remain
available; active corrections drive individual status. Diagnostics and unadmitted
claims cannot become genuine Upcoming forecasts. No reserved comparative study
aggregate is exported. Genuine activation remains hard disabled.

The display channel maps `(league, ID namespace, player ID)` to independently
verified source names and uses retained event teams/start for historical matchup
labels. Source IDs remain accessible and missing metadata uses an explicit ID
fallback. Enrichment does not change forecast/outcome/grade bytes or model inputs.
Publication, source capture, import and issuance clocks are distinct. Empty
Upcoming, zero admitted offers and NO_ACTION are independent states.

An independent valid offer channel can survive a research export failure. The
builder first retains a valid earlier research asset; if none exists it emits a
valid empty NBA category catalog with an explicit research error. The UI reports
research unavailable rather than presenting that fallback as successful empty
issuance. Offer failure likewise cannot suppress valid future research forecasts.
No publication creates a new ledger record, source observation or forecast.

## Retained sport v2 and legacy core contract

Build: `python3 -m multisport_lab.publication --build-commit "$(git rev-parse HEAD)"`.
Source `web/` → artifact `output/`, with `index.html` at artifact root.
The browser reads `./data/manifest.json`, then relative content-addressed assets.
No collection, rebuild or credential is triggered by visiting or refreshing.

Manifest fields: `schema_version` (2), `snapshot_id` (canonical JSON SHA-256 of
the other fields), full `build_commit`, actual `published_at`,
`publication_status` (`RESEARCH_ONLY`), `supported_sports`, `sports`, and `errors`.
Each sport entry has `league`, `path`, raw-byte `sha256`, `generated_at`, `status`,
`retained` and nullable `error`. Asset paths are `<league>.<sha256>.json` under
`data/`. No raw upstream data is copied. Both schema and asset size are bounded.

Sport v2 retains version, league, generated clock, research evidence/status,
coverage, complete catalog and sources. Typed `events`, `forecasts` and
`performance` now follow [FORECAST_CONTRACT.md](FORECAST_CONTRACT.md). The build
recovers checksummed records from `records/`, validates exact references and
grades, then exports compact PMFs and forecast scores. It never runs a forecaster
or fetches sources. Originals and corrections remain in Git; only active
correction-chain forecasts/grades publish, and grades referring to superseded
outcomes or forecasts stay hidden until separately regraded. Offers, candidates
and tickets remain empty and fail closed if populated. V1 manifests/assets remain
readable for rollback/failed-update retention; v1 still rejects populated arrays.

`future_availability` has `status` AVAILABLE/UNAVAILABLE and explicit `reasons`.
AVAILABLE requires an actual pregame captured forecast for an upcoming event.
Retrospective distributions are shown under History, with historical event and
actual current issue dates. All categories retain separate unvalidated forecast,
unverified quote/settlement and NO_ACTION paper gates. Counts of displayed grades
are record counts, not independent accuracy estimates. The current six examples
are an engineering sample of already exposed historical data, not a new holdout.
Bounds: 32 events/forecasts, 64 grades and 512 KiB per sport; no raw feed/support
rows, ticket financial results or executable betting contract are exported.

`supported_sports` means selectable **research coverage**, initially NBA. It does
not enable quotes, evaluated forecasts or product qualification. SINGLE accepts
exactly one supported sport; SELECTED a nonempty explicit supported subset; ALL
accepts no explicit list and resolves to supported coverage. Both Props and
Paper Builder use this set without expansion. Future multi-sport test fixtures
do not admit a real second sport. The UI can show future coverage separately.

Each sport is validated independently before writing content-addressed assets;
the manifest is replaced atomically last. If an update fails, retain the previous
validated sport bytes and its original generation time, flag `retained` and the
failure. Other sports can publish. An initial failure without a prior asset stays
unavailable; no valid assets means no manifest publication. An old asset's age is
never refreshed to the build clock. Corrupt previous assets fail closed.

No retention schedule or automated source job is enabled. Small issuance/outcome/
grade receipts are retained in this repository through commit/push/fresh remote
readback; original clocks remain intact on restart. Raw bulk archives are excluded.
Rebuilding a catalog updates its generation clock only: it does not claim new
source capture or fresh forecast issuance. Actual future capture and issuance remain separate operating evidence; preparation
and a successful build do not create either.

## Prospective records and pending grades

Sport and manifest versions remain 2. The exporter and browser accept forecast
wire versions v1 and v2, with v2's strict separately versioned pregame contract
in [FORECAST_CONTRACT.md](FORECAST_CONTRACT.md). Loader checksum verification uses
the forecast ID for both versions. An unknown version or modified inner payload
fails even when the outer asset was rehashed.

A sport envelope containing any captured record is labeled `RESEARCH_COLLECTION`;
individual forecast and grade lanes remain authoritative. Reconstruction-only
assets keep `RECONSTRUCTED_RESEARCH`, and retained v1/v2 assets stay readable.
Python and JavaScript reject an envelope label that contradicts its records.
`SCHEDULED`/`OBSERVED_CAPTURE` events describe the schedule snapshot bound at
issuance, not a fresh assertion that an elapsed event is still pending or final.
The interface uses the event clock only to select Upcoming versus History.

AVAILABLE still requires an actual upcoming captured forecast. An elapsed captured
record remains immutable in History; the next publication reports no remaining
upcoming record. Between builds, the visitor's current clock also prevents an
elapsed event appearing Upcoming. Empty states distinguish absence of issuance,
current filters excluding available research, and a captured event whose start
has passed. No unsupported qualification is needed to inspect research.

Missing grades are not synthesized as unresolved, zero, loss or win records.
Forecast cards show pending statistical grading until exact matching grade records
exist, and Performance reports the number still pending separately from DNP and
unresolved grades. No automatic source fetch, model rerun or outcome generation
occurs during export or browser display. Scope, all fourteen categories and the
2–6-leg direction/NO_ACTION contract remain unchanged.

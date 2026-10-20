# Static publication v2

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
source capture or fresh forecast issuance. New observed future inputs and an
admitted real-time producer remain separate work.

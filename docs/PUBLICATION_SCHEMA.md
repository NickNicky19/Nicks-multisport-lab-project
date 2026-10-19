# Static publication v1

Build: `python3 -m multisport_lab.publication --build-commit "$(git rev-parse HEAD)"`.
Source `web/` → artifact `output/`, with `index.html` at artifact root.
The browser reads `./data/manifest.json`, then relative content-addressed assets.
No collection, rebuild or credential is triggered by visiting or refreshing.

Manifest fields: `schema_version` (1), `snapshot_id` (canonical JSON SHA-256 of
the other fields), full `build_commit`, actual `published_at`,
`publication_status` (`RESEARCH_ONLY`), `supported_sports`, `sports`, and `errors`.
Each sport entry has `league`, `path`, raw-byte `sha256`, `generated_at`, `status`,
`retained` and nullable `error`. Asset paths are `<league>.<sha256>.json` under
`data/`. No raw upstream data is copied. Both schema and asset size are bounded.

Sport fields: version, league, generated clock, evidence lane, research status,
coverage, complete market catalog and sources; events, offers, forecasts,
candidates, tickets and performance are empty arrays in this first schema.
The exporter rejects nonempty arrays until typed identity/time/probability/rules
validation is implemented in a new contract. A nonempty internal model file is
never implicitly eligible for publication. The NBA catalog contains all thirteen
requested markets and optional PA, with separate unvalidated/unverified gates.

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

No retention schedule or automated source job is enabled. Old content-addressed
files remain locally available; a production durable capture store and bounded
archive cleanup policy remain separate work. Rebuilding the empty catalog updates
its generation clock only: it does not claim new source capture.

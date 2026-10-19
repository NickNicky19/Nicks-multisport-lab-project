# Early research interface

Implemented 2026-10-19 in `web/`; the integration owner records the exact commit
in HANDOFF_STATUS.md. Plain HTML, CSS and browser ES modules require no frontend
dependency installation or build framework. The Python publication command copies
only approved top-level frontend files to `output/` and creates `output/data/`.
The artifact has `index.html` at its root. No raw source data or test files are
frontend assets.

The seven hash routes are `#/overview`, `#/props`, `#/value`, `#/builder`,
`#/performance`, `#/sources` and `#/specials`. Assets and JSON use relative URLs
and were tested beneath `/Nicks-multisport-lab-project/`. A browser refresh reads
published files; it never requests an upstream source or runs a model.

All thirteen required NBA categories remain visible in the published inventory;
PA is marked optional. Forecast, quote and settlement gates are separate. No
players, event rows, offers, prices, forecast scores, settled outcomes or qualified
paper entries are invented. The browser rejects nonempty observation collections
under the initial research-only v1 schema; admitting real rows requires an explicit
typed export and display implementation. The current Paper Builder configures a
request and reports `NO_ACTION`; it does not issue a ticket or establish a ledger.

Props and Paper Builder share one sport selection state and the pure set functions
in `web/scope.mjs`. `SINGLE` requires exactly one published sport, `SELECTED` a
nonempty explicit supported subset, and `ALL` an empty explicit list resolving to
all supported coverage. Invalid, duplicate and unsupported selections fail closed.
An empty group remains empty; the builder cannot widen it. Initially NBA is the
only selectable research coverage. Synthetic WNBA test rows do not admit WNBA.
Direction policies filter the selected candidate universe; they never create or
qualify a candidate. Integral requested ticket sizes are 2 through 6. Six remains
a preference subject to full-ticket qualification, with smaller tickets or
`NO_ACTION` permitted. No browser-local draft storage is used.

The client checks the manifest schema and canonical checksum, repository-relative
content-addressed paths, generation/publication/source clocks, each sport's raw
SHA-256, complete categories, source IDs and independent research-only gates.
Incompatible, corrupt, oversized and failed assets are unavailable, not a successful
empty board. Valid sports remain usable if another fails. A retained snapshot keeps
its original generation clock and error; a first failed sport without an older
snapshot is shown as unavailable and excluded from choices. Source update time
stays unknown where not established. Publication time is explicitly not quote age.
Public hashes establish content consistency, not upstream authenticity or permission.

Verified commands:

```bash
node --test web/tests/*.test.mjs
node --test --test-isolation=none web/tests/*.test.mjs
python3 -m multisport_lab.publication --build-commit "$(git rev-parse HEAD)"
node web/tests/site-smoke.mjs output
python3 web/tests/browser_smoke.py output --screenshots /tmp/nicks-multisport-ui
```

The explicit nonisolated Node run passed **14 individual software tests**; the
default isolated runner reported **2 passed file harnesses** in this runtime.
Artifact smoke passed four relative entry assets, both validated JSON files,
all-thirteen inventory and research-only `NO_ACTION`. Chromium 154 with the
already-installed Python Playwright passed desktop 1440px and mobile 390px/320px:
all seven routes and direct reloads, no page-level horizontal overflow, scoped
inventory, shared scope changes, 2/4/6-leg direction changes, explicit `NO_ACTION`,
unknown routes, incompatible schemas, corrupt sport hashes, retained clocks and
first-failure visibility. The HTTP server is local and needs local networking
permission in the managed execution sandbox. Neither Playwright nor Chromium is
an application dependency or required for the standard GitHub check workflow.

Local screenshots were retained outside Git at
`/tmp/nicks-multisport-ui/overview-desktop.png` and
`/tmp/nicks-multisport-ui/{overview,props,builder}-mobile.png`. Desktop overview and
mobile builder received visual inspection. These are local build/browser checks;
they do not establish deployed Pages availability, real data verification, model
evaluation, future paper evidence or product qualification. A live Pages job and
public HTTP/browser readback remain separate delivery evidence.

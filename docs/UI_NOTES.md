# Research interface

## Evidence groups and History correction, 2026-10-20

Performance now summarizes grades separately by league, evidence lane, model
version, full model commit, model code SHA-256, conditioning, period and overtime
policy. The full identity is visible beside each category table. Different input
hashes and player/event IDs remain observations within the same model cohort;
they do not erase the lane/model boundary. DNP and unresolved records retain
their counts without entering score means. A zero-support log-loss row makes
only its own group's category loss infinite. Counts remain grade records, not
independent trials, and no cross-category accuracy score or product qualification
is introduced. Missing or mismatched forecast references fail closed.

History now means past-event forecasts and reconstructed research. One shared
classifier drives its rows and shortcut count, including `REAL_TIME_CAPTURED`
records whose event start has passed. Passing that clock does not establish game
completion. The selector, empty states and banner preserve this distinction;
captured records retain their original lane and pregame issue time rather than
being described as backfilled. Current retained records remain reconstructed-only;
all mixed-lane examples are explicitly synthetic software/browser fixtures. This
change creates no input receipt, real-time producer, forecast or outcome and admits
no new evidence lane to the ledger.

Verification commands on the branch based on
`002a6b994c862c758f1d7c8199831c75eff761af`:

```bash
node --test --test-isolation=none web/tests/*.test.mjs
python3 -m multisport_lab.publication --build-commit "$(git rev-parse HEAD)" \
  --output /tmp/nml-recovery-groups-ui
node web/tests/site-smoke.mjs /tmp/nml-recovery-groups-ui
python3 web/tests/browser_smoke.py /tmp/nml-recovery-groups-ui \
  --screenshots /tmp/nml-recovery-groups-ui-screenshots
```

All **31 Node checks** passed. Local Chromium checked the unchanged six real
research bundles/84 PMFs/six grades and all seven routes at 1440px, 390px and
320px, plus synthetic mixed-lane/model cohorts: four forecast records in History,
three separate summary groups, isolated means and zero-support loss, exact lane
labels and an empty selected scope hiding both forecasts and grade groups. The
first 320px run exposed overflow from an unbroken lane heading; the heading now
uses a readable label with the full lane code in metadata, and the repeated
browser check passed. The synthetic 390px group screenshot received visual
inspection. Offer, candidate and ticket arrays remain empty; all existing sport
scope, direction and 2–6-leg semantics retain `NO_ACTION`. These are local checks
of the correction, not deployment evidence for the new branch.

Before these changes, the approved PR 3 deployment was independently checked at
public build `002a6b994c862c758f1d7c8199831c75eff761af`, snapshot
`45f9c2d7cf10baf00ace7b399f948e91d95c0e14fc5dbf494b8191af24ce7ae5`, from
2026-10-20T01:01:39.714719Z to 2026-10-20T01:02:10.831386Z. System-verified HTTPS
and Chromium public readback passed all seven routes/reloads at 1440px, 390px and
320px, all 84 PMFs and fourteen category filters, six grade receipts and all
45 sport-scope × 2–6-size × direction readiness combinations. There were no page
errors or failed HTTP responses; nine requested assets stayed inside the Pages
repository prefix. The 151,222-byte NBA asset and manifest/forecast/grade hashes
matched. The browser used only a process-local SPKI trust pin for the configured
environment proxy CA; urllib independently used normal verified TLS. No persistent
trust store, repository or existing receipt changed during that public check.
The aggregate and screenshots are `/tmp/nml-public-typed-qa/`; the integration
owner's deployment receipt retains the durable evidence. That deployment readback
establishes website delivery for the approved commit, not model accuracy, genuine
prospective outcomes or product qualification.

## Typed research update, 2026-10-20

The client now accepts publication manifests v1/v2 and retained sport snapshots
v1/v2. Research v2 adds bounded typed NBA events, coherent forecast bundles and
forecast grades; quote, candidate and ticket collections remain unadmitted.
`web/research.mjs` mirrors `multisport_lab/forecast_contract.py` and the public
grade contract in `multisport_lab/ledger.py`. Validation checks exact fields,
namespaced event/player/team identities, all 13 requested categories plus optional
PA, units, positive normalized PMFs, finite observed support, PMF means/intervals,
scoring/sum constraints, necessary DD/TD threshold bounds, microsecond clock
ordering and qualification `UNAVAILABLE`. Fixed-point decimal strings preserve
cross-language record hashes. Manifest, asset, forecast and grade checksums are
independently verified. The browser cannot attest to unpublished raw joint support
or source input receipts; ledger verification owns that evidence.

Props separates price-independent research distributions from offers. Upcoming
research excludes every historical reconstruction and every started event. When
future capture is unavailable it displays the exported concrete reasons and links
to available History. History cards expose player/event IDs or source labels,
actual UTC dates, model revision, training/history/input cutoffs, actual issue
time, conditioning, evidence lane, a PMF chart and exact PMF table, mean, central
80% interval, zero probability, finite support and probability above the central
95% interval endpoint. The finite empirical maximum is explicitly not a physical
maximum. A reconstructed cutoff never becomes a backdated pregame issue receipt.
The shared one/selected/all scope filters forecast bundles as well as the builder
candidate universe. Side and venue filters apply to offers rather than suppressing
a price-independent research distribution. Category/evidence filters apply
to research; charts do not infer a missing line or price. Large filtered lists
state the shown/total count and offer the next 28 category distributions.

Performance renders each category's typed forecast diagnostics separately from
financial settlement. It exposes grade/forecast/outcome receipt IDs, actual grade
clocks and per-category observations, CRPS/RPS and log-loss states. Any zero-support
row keeps the category's mean log loss infinite. DD/TD have separately identified
Brier scores; unscaled category scores are not pooled. DNP and unresolved records
have no statistical scores, and all financial statuses remain `NOT_EVALUATED`.
No descriptive sample establishes model validation, prospective paper skill or
product qualification. Builder remains a 2–6-leg direction/sport request ending
in `NO_ACTION`, without admitted terms or a qualified ticket universe.

Verification at this frontend checkpoint:

```bash
node --test --test-isolation=none web/tests/*.test.mjs
python3 -m multisport_lab.publication --build-commit "$(git rev-parse HEAD)" \
  --output /tmp/nicks-multisport-typed-ui
node web/tests/site-smoke.mjs /tmp/nicks-multisport-typed-ui
python3 web/tests/browser_smoke.py /tmp/nicks-multisport-typed-ui \
  --screenshots /tmp/nicks-multisport-typed-screenshots
```

The Node run passed **25 individual software checks**. Artifact smoke and local
Chromium checks passed desktop 1440px and mobile 390px/320px across all seven routes,
reloads, relative repository-prefix assets, shared scopes, 2/4/6-leg directions,
`NO_ACTION`, failed/incompatible/corrupt/retained snapshots and first-failure
visibility. Clearly synthetic v2 fixtures, intercepted only inside the browser
test, exercised all fourteen History categories, category filtering, provenance,
future exclusion and separate typed grades while offers stayed empty. They are
not published assets, real data verification or model evaluation. Screenshots
under `/tmp/nicks-multisport-typed-screenshots/` are local test artifacts; the
`synthetic-` filenames expressly identify fixture screenshots. Actual retained
record readback, repository checks and live deployment are separate integration
checkpoints owned by the root implementation owner.

Actual retained-data browser readback then passed against the root-built `output/`
artifact, without regenerating any record:

```bash
node web/tests/site-smoke.mjs output
python3 web/tests/browser_smoke.py output \
  --screenshots /tmp/nicks-multisport-real-research-002
```

That checked manifest/sport v2 snapshot
`8c40f9a541d4262c04efba9d3ec4a5339d59dd3b05438bc4480bd6f5221072cd`, built with
commit metadata `cde185088f032db587e1fb10845cd84541ef0a8b`. The NBA asset was
150,915 bytes against the 524,288-byte budget. It contained three historical
events on 2025-11-24, six player forecast bundles, 84 category PMFs and six typed
forecast grades. Actual issue clocks were
2026-10-20T00:21:42.792328Z–2026-10-20T00:21:48.758578Z, explicitly later than the
historical events. The browser checked event/cutoff/issue/forecast-ID readback,
all fourteen categories and all 84 loaded distributions, REB filtering to six
cards, fourteen category-grade summary rows and six grade receipts. Upcoming
coverage remained `UNAVAILABLE`; offers, candidates and tickets stayed empty,
financial settlement stayed `NOT_EVALUATED`, and the builder stayed `NO_ACTION`.
All seven routes, reloads and scope/builder controls passed at desktop 1440px
and mobile 390px/320px. Real-data screenshots
`real-reb-history-desktop.png`, `real-reb-history-mobile.png` and
`real-reb-card-mobile.png` are under the command's `/tmp` destination; the
desktop history and mobile card received visual inspection. This verifies the
retained examples' public UI/contract readback, not source authenticity, calibrated
forecast quality, prospective skill, financial results or deployment. Final
publication metadata will change when the integration owner commits and rebuilds;
the immutable forecast issue clocks must not change.

## Original empty-state checkpoint, 2026-10-19

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

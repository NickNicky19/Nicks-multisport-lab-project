# Website delivery plan

## Destination and current status

The canonical repository is
[NickNicky19/Nicks-multisport-lab-project](https://github.com/NickNicky19/Nicks-multisport-lab-project).
The expected GitHub Pages address, after configuration and a successful deployment,
is `https://nicknicky19.github.io/Nicks-multisport-lab-project/`.

**This document is a delivery specification. The starter contains no implemented
dashboard, Pages workflow or verified live deployment.** Importing the starter
does not publish a website. The public URL must remain described as expected until
a deployment and HTTP/browser readback establish it.

Implementation update, 2026-10-19: `web/` now provides the initial research
interface; `multisport_lab.publication` assembles validated catalogs into `output/`.
`.github/workflows/pages.yml` checks/builds on the implementation branch and PRs;
its dependent Pages job runs only from `main`, never unreviewed PR code. Action
major tags were resolved to full upstream SHAs and their action metadata inspected
on this date (checkout/setup-python/setup-node v7, configure-pages v6,
upload-pages-artifact/deploy-pages v5). No source polling or scheduled jobs are
enabled. See `PUBLICATION_SCHEMA.md` and the current handoff for actual check,
configuration and deployment results; this specification alone proves none.

Deployment update, 2026-10-19: PR #1 is merged and the research site is **deployed**
at https://nicknicky19.github.io/Nicks-multisport-lab-project/ . The main build/deploy
run 39341268746 succeeded for `5d19fa344de5ceaa6e7cc550f0ac8ac832458202`;
public HTTP/hash/manifest and desktop/mobile browser checks passed. Source is
GitHub Actions. Exact evidence and remaining model/source/product limits are in
`HANDOFF_STATUS.md` and `evidence/deployment/2026-10-19-pages.json`. The starter
status above is historical; no model or ticket qualification is implied.

## Hosting architecture

Use the same basic hosting pattern as Nick's NFL project: Python produces validated
data assets; a build assembles HTML, CSS, JavaScript and JSON; GitHub Actions uploads
the selected site artifact; GitHub Pages serves it. Pages is static hosting. Python
forecasting, source collection and outcome grading execute separately from browser
page loads. Filters, charts and ticket drafting can run in the browser.

Keep the front end modest: plain modules or a small Vite application are acceptable.
Choose after inspecting available project code, without importing the NFL app's
fantasy integrations or changing that repository. Keep historical training archives,
raw response archives, credentials, tokens, private user data and internal working
files outside the public site artifact. Publish only material approved for public
redistribution. Static client code cannot hide a credential.

## Deliver an honest interface early

Build a responsive, phone-friendly research interface alongside data and model work.
Useful initial screens can show the category inventory, source coverage, research
status and documented empty states before forecasts qualify. Synthetic fixtures
belong in explicitly labeled demonstrations and must never appear as current picks.

Provide these views:

| View | Required behavior |
|---|---|
| Props | One sport, selected multiple sports or all supported sports; league, event window, category, period, side, venue and evidence filters; distributions and probabilities when supported; explicit age and missingness. |
| Compare / Value Research | Compare exact matching contracts; show supported prices, reference method and economic calculation when eligible. |
| Paper Builder | Use one sport, selected multiple sports or all supported sports; request 2–6 legs, prefer six when the complete ticket qualifies, support OVER_ONLY / UNDER_ONLY / MIXED, and allow fewer legs or NO_ACTION. |
| Performance | Separate forecast accuracy, selected-leg outcomes and complete ticket settlement; retain methodology, horizon, model version and sample counts. |
| Source Health | Show source/category coverage, freshness, failures, unmapped observations and concrete reasons capabilities are unavailable. |

NBA is first, with all 13 requested categories: **PTS, PRA, REB, 3PM, AST, RA, PR,
TOV, TD, DD, BLK, STL and BLK+STL**. PA is an optional addition. The initial rebounds
experiment does not reduce this interface or research scope. WNBA, NHL, soccer,
tennis and CFB enter independently; MLB later imports versioned external outputs;
NFL remains external and disabled initially. "All sports" includes admitted data
only. Registry membership never implies model validation.

Define these three sport-selection scopes in the early export/UI contract. Apply
the chosen scope to both displayed opportunities and the builder's candidate
universe; a selected group must not expand silently to fill a ticket. Available
choices follow actual coverage, beginning with NBA. Unsupported sports retain
their true availability status as later integrations are developed.

## Export and display contract

Define a versioned publication schema before coupling the dashboard to model files.
Each bounded snapshot needs a manifest identifying schema version, build commit,
publication time, source/model versions, actual capture/input cutoffs, evidence
lane, per-sport status and content hashes. A build time cannot substitute for an
older quote's observation time. Retain exact contract identity and settlement
semantics from the Python records.

The exporter validates types, identities, finite probabilities, required fields and
referential consistency. The client rejects incompatible schemas and displays
partial coverage honestly. Keep offer-only, research forecast, evaluated forecast,
priced paper candidate and stale/unavailable states distinguishable. Do not infer
qualification from a nonempty number or replace unknown prices with assumed odds.
Hide started/completed events from the actionable pregame view while preserving
their immutable records for grading and history.

Publish a complete validated artifact with per-sport snapshots. A failing new
observation must not overwrite the last valid asset with misleading empty success.
Any retained prior snapshot keeps its real age and applicable stale restrictions.

## Paths, routes and publication checks

The production base path is **`/Nicks-multisport-lab-project/`**, including the
repository's capitalization and trailing slash. If Vite is used, configure its
`base` accordingly and use that base for fetched data. Plain HTML/JS should use
consistent relative URLs. Root-relative `/data/...` would point outside the project.

Hash navigation such as `#/props` and `#/performance` fits Pages without server
route rewrites. If another router is chosen, test direct navigation and reloads
explicitly. Test the production build beneath the repository prefix, not only a
development server at `/`. Check assets, JSON loads, filters, navigation, mobile
layout, empty/partial/stale states and an incompatible schema response.

Upload only the chosen website directory, such as `output/` or `web/dist/`.
**The deployment artifact must contain `index.html` at its root.** A successful
workflow must be followed by checking the published page and its manifest against
the intended commit/snapshot. Report a blocked or failed deployment accurately.

## Setup, refresh and ownership

Configure the new repository's Settings → Pages → Build and deployment → Source
as **GitHub Actions**. If the available connection cannot change this setting,
report that exact user action after completing the reviewable implementation.
Use a successful build/check job before deployment, the `github-pages` environment,
and the required Pages/OIDC permissions. Do not deploy unreviewed pull-request code.

Use one publisher and bounded jobs. Begin with intentional builds/publication;
add justified schedules after source access, runtime, storage and freshness are
measured. Separate discovery, forecasts, quotes and grading responsibilities.
Do not copy self-restarting ticker loops. Scheduled execution may be delayed:
record actual capture times. A website refresh retrieves the newest published
assets; it does not trigger model retraining or upstream requests.

Browser storage can preserve a local draft, but it is not the durable prospective
ledger. Design explicit export/import or an authorized ingestion route for frozen
tickets, decision times and later settlement. A ticket must preserve one common
decision time, its exact legs, supported joint assumptions and actual product terms.

## Verified references

Reviewed 2026-10-19; these are hosting references, not proof of a new deployment:

- [GitHub Pages architecture and project URLs](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages).
- [Publishing-source configuration](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).
- [Custom workflows and deployment requirements](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
- [Entry-file and artifact requirements](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site).
- [Vite project-base configuration](https://vite.dev/guide/static-deploy).
- [GitHub scheduled-event limitations](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
- [NFL hosting reference, pinned read-only](https://github.com/NickNicky19/nicks-expert-nfl-picks/blob/5889447a457597d0383d8cd59cbd9afb07fadfb2/.github/workflows/hourly.yml): builds Python outputs and uploads `output/` to Pages. Its schedules, writers and engine are outside this project's implementation scope.

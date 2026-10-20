# Implementation decisions

## 2026-10-19 — ownership, evidence and publication

Observed clean remote `main` at `de86e92352f0fb5a76831275f6de6b256ce05434`.
There was no checkout, workflow or concurrent writer in this workspace. Cloned
the existing repository and created `implementation/nba-foundation`; no reset,
ZIP import, external repository writes or workflow triggers occurred. Root is
integration owner; bounded agents own data, offers, baseline and frontend files.

Choose standard-library Python and buildless ES modules. Publish only `output/`,
built from `web/` and validated, content-addressed JSON. NBA is selectable as
**research coverage**; this does not enable production forecasting, quotes or
selection in `config/capabilities.json`. Other sports remain unavailable choices.
Both screens share SINGLE / SELECTED / ALL set semantics. SELECTED requires a
nonempty explicit subset; ALL resolves only actual supported research coverage.
Unsupported selections fail; the builder never expands scope to fill tickets.

Initial export v1 accepts empty observations and a typed coverage catalog only.
Reject nonempty event/offer/forecast/candidate/ticket/performance collections
until their typed export/admission contract is implemented. This narrower
first schema prevents accidental publication of unreviewed source payloads or
unsupported qualification claims. It is not the final forecasting API.

## 2026-10-19 — reference protocol before development scoring

Register one untuned reference prototype, `NBA-ALL13-JOINT-001/R0`, with common
`nba_pregame_features_v1`, `nba_cutoff_90m_v1` and
`nba_chronological_panel_v1` versions. This is separate from the proposed REB
B0/B1/C1 comparison; no change to that protocol or candidate promotion occurs.

Population: completed historical appearances, including low-minute and zero-stat
appearances, conditional on appearing. Missing/DNP records are excluded with
counts and reasons, never relabeled zero. Historical selection from eventual
appearances cannot establish an operational pregame roster universe.

Reference distribution: recency-weighted complete observed stat lines, with a
28-calendar-day half-life and five appearance equivalents of shrinkage toward
the same training-only league pool. Cold starts use the pool. Every outcome keeps
minutes and eight primitive counts together; scoring, sums and five-stat DD/TD
come from that same outcome. This captures empirical exposure/production
dependence. It has finite observed support, cannot extrapolate unseen tails and
does not model cross-player/game joint outcomes or certify ticket probabilities.
No unverified role, pace, injury, final-lineup or future-minute feature is added.
Those remain explicit limitations of this reference, not invented inputs.

Historical features freeze at 00:00 UTC on the T-90 cutoff date, earlier than
the T-90 cutoff. Include only prior-date completed rows whose declared outcome
availability bound is no later than that freeze. Any reconstructed availability
bound is a conservative research convention, not proof of historical publication.
Save actual run issuance time; never backdate a historical forecast capture.

Budget: one fixed configuration, no tuning, no confirmatory window. A first pilot
may score at most 200 appearances from the first two eligible dates after at
least seven earlier observed calendar dates in the bounded audited source.
It is development and feasibility evidence only; no held-out season is claimed.
Do not inspect another period to choose a favorable report. Report each category
separately: proper weighted empirical RPS; Brier and unsmoothed log diagnostics
for DD/TD; observed/predicted zeros, interval coverage and minutes errors.
Zero-support log loss stays infinite/unavailable, never silently smoothed.
No unscaled aggregate score or product accuracy claim. The later confirmatory
protocol needs source admission, exposure history, windows, uncertainty/precision
and performance guards frozen independently.

Pre-scoring data refinement: SportsDataverse minutes are rounded whole minutes;
a genuine six-second appearance is recorded as zero minutes. Preserve that row
with its precision label. Do not infer nonappearance from rounded zero or use
those values as exact exposure shares. Freezing on the cutoff date also handles
events near UTC midnight without admitting information after T-90.

Pre-scoring cohort refinement: require a successful exact event/teams schedule
join and explicit FINAL status. Include only standard NBA clubs (ESPN team and
opponent integer IDs 1–30); source season-type labels alone include short-format
All-Star events and cannot establish normal NBA rules. Exclude unidentified
players, DNP/unknown participation and incomplete primitive/minute rows, reporting
all exclusions before scoring. Missing identities are quarantined, never guessed.
Do not repair scoring/rebound inconsistencies by replacing values.

For this development pilot only, set a completed historical row's reconstructed
availability bound to its archived event start +24 hours. This conservative
calendar convention is not independently verified as-of evidence, even when the
archive now marks that game final. It cannot admit a captured-future claim.
The primitive variogram diagnostic uses fixed unit scales and power 1/2 across
eight counts; it is descriptive, not an equally scaled multi-target accuracy
metric or a validation of cross-player ticket dependence.


## 2026-10-20 — typed research and durable record package

User requested current PR #2 reconciliation and the next implementation package.
PR #2 head05643e1 was verified ready and merged; main e9bfa4c retained all prior
history. Validation findings A/B reproduced and fixed before this package, with
no contradictions in the frozen panel and no changed old protocol/pilot receipts.

Publish compact all-14-category marginal PMFs from the same complete-line R0
measure. Keep the joint construction and input/support hashes without publishing
raw historical support/player rows. Typed real-valued numbers use fixed-point
strings for stable cross-language hashes. Identity, event version/start, actual
issue, cutoff, reconstructed availability and conditional appearance are explicit.
A record issued now for an old event stays historical reconstruction. Public
future view remains empty until an admitted event/player universe, observed input
captures and actual pregame issuance exist. Model qualification remains unavailable.

Use create-only checksummed records under this existing Git repository, with
append-only references/corrections. A local write alone is pending durability;
commit/push and independent fresh remote read establish retained content. Record
actual receipt clock separately from original issuance. Browser storage and /tmp
are never the sole issuance ledger. Forecast outcome scoring is independent from
venue contract grading and financial settlement. No synthetic ticket is entered
as an actual issued ticket.

Broader development protocol NBA-ALL13-JOINT-DEV-002: fixed R0 versus league-only
L0, original unchanged panel, useful prior history from Oct21 onward, window
Nov24 2025–Jan18 2026, first two games in each of eight full UTC weeks and all
appearances (338 total /16games), shared T90/midnight daily freeze and reconstructed
start+24h completion bound. 2,000 paired whole-week bootstrap draws, fixed seed
20261020; per-category scores/uncertainty, sparse-event/tail limits and no
multiplicity-adjusted promotion or confirmatory claim. No tuning. Full exact
pre-scoring inventory and protocol receipts bind the fixed game list and hashes.
The old R0 pilot and separate proposed REB B0/B1/C1 protocol are unchanged.

## 2026-10-20 — post-deployment clocks, evidence groups and DEV003

PR #3's exact approved2d30ae9 head merged as002a6b9 and its typed site passed
main workflow/public HTTP/hash/desktop/mobile verification. Follow-up work starts
from that main on implementation/recovery-and-evidence-groups; no approved-head
rewrite, forced push, external NFL/MLB write or inherited scheduler.

An interrupted historical publication may retain outcomes whose original source
clock predates the resumed batch's local read. New v2 summaries copy each
referenced record's actual metadata/clocks and supply a common source clock only
when all outcomes agree. Existing v1/eighteen original receipts remain unchanged.
Recovery validates exact references, identities, source/model/clock metadata and
grade dependencies. Source observations after a retained historical forecast's
issue time remain valid for reconstructed grading; they never imply pregame
availability. Publication and source receipt clocks retain separate meanings.

Performance summaries partition by sport, evidence lane, model version/full
commit/code hash, conditioning and period/overtime. History retains past captured
forecasts without calling them reconstructions or assuming a game is complete
solely because its start clock has passed. Record counts are not independent
trials. No new prospective producer or product qualification is admitted.

The offline readiness pilot binds exact event/version/player/team/source hashes,
supplied source clocks, coverage and lagged complete inputs, while explicitly
refusing authenticity/permission/real-time admission claims. A retained archive
alone lacks a prospective bundle, but old statistics observed before a later
future cutoff are not inherently invalid features. Historical late-fetch clocks
block historical as-of claims; future-event-specific timing must be assessed
separately. The20k/8MiB pilot limits do not silently truncate full R0 history.

DEV003 is one untuned coherent K0 workload-prior challenger versus unchanged R0
and L0. Its donor contexts use the donor's own lagged cutoff history, never its
outcome minutes. Fix latest≤5 arithmetic reported-minute mean,8-minute kernel,
0.25 league floor, unchanged R0 personal28day weights/5-prior strength, exact n0
fallback. All14 outputs retain complete stat-line atoms. Hashed identity-only
selection across12 full UTC weeks gives24 games/517 rows; source/cohort/code
fingerprints, one-trial/no-search budgets900sec/512MiB and paired week-bootstrap
metrics are frozen in dev003-protocol.json before scoring. This exposed
development is neither the blocked precise-duration REB experiment nor later
confirmation/promotion/model selection. No post-score parameter/cohort changes.

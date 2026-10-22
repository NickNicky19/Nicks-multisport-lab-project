# OPS002 source-use review

Reviewed **October 21, 2026** against the repository checkpoint
`fe09956ac5708d3e2df65ebb6c833a3fbafdd73d` and the official documents linked below.

**Result: `NO_OPERATIONAL_ADMISSION`.** This bounded documentation review has not
established a source-use basis for the proposed fresh ESPN operation or a complete
actual player-offer publication. It creates no permission receipt, admitted source
ID, activation, scheduler, data capture or forecast. It does not decide that every
possible public-data route is unavailable or make a general legal determination.

The review used retained repository evidence and rendered official documentation.
It did not collect player or offer data, contact a provider, obtain a grant, or
retain original provider-document entity bodies. The links and document sections
below are review references, not claimed raw-byte recovery receipts.

## Separate the operations

| Intended operation | Exact scope | Current review result |
| --- | --- | --- |
| Fresh pregame inputs | Four ESPN responses: one dated scoreboard, one event summary and the two fixed teams' rosters, followed by normalization for the fixed four-player cohort | No applicable allowance for this automated operation established in the reviewed evidence |
| Later outcome inputs | A separately observed final response from the exact event-summary route, with separately retained corrections if needed | Not captured or admitted; pregame summary bytes cannot establish final outcomes |
| Source-byte retention | Encrypt original supplied responses and retain ciphertext and metadata on this repository's public records branch; keep the private key separately | Source retention basis and installed, recoverable operational key/backend remain unresolved |
| Research publication | Typed forecasts and the necessary verified event/player facts, with actual observation and issuance clocks | Must be reviewed for the admitted source/use; bookmaker prices are not a prerequisite |
| Offer-only publication | One complete player contract and its exact identities, side/line, period/OT and applicable rules | No actual contract or public admission; price may be unavailable once other requirements are satisfied |
| Existing historical input | Frozen 26,645-row derived normalized SportsDataverse panel | Preserve its existing bounded acceptance and attribution; it does not authorize fresh direct ESPN extraction |
| PR #11 historical display | Previously reviewed names, archived matchups/dates and status explanations | Independent of this new-operation review; this document does not reopen or block its approved release |

### Proposed fresh input request inventory

The fixed plan is `NBA-PAIRED-OPS-002`, event `401909094`, Denver at Oklahoma City,
with the cohort and event version in
[`ops002-plan.json`](../evidence/operational/ops002-plan.json). The intended source
routes are:

1. `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20261022&limit=1000`
2. `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401909094`
3. `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/25/roster?season=2027`
4. `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/7/roster?season=2027`

This is a proposed operating inventory, not four requests made by this review.
The preparation receipts document prior responses and their actual clocks. They
are not fresh inputs for the October 22 capture window. Any additional source,
redirect, request, retry or changed destination must be covered by the reviewed
operating package rather than inferred from this list.

The separate offer observations used these routes:

- ESPN core NBA `events/401909094/competitions/401909094/odds/100/propBets`, with
  `lang=en&region=us&limit=64`, and its returned provider-100 reference.
- Earlier Sleeper `https://api.sleeper.com/lines/available`, plus the separately
  recorded identity and official product-rules observations.

The latest retained ESPN offer response had six team/overtime items and no
complete player contract. Earlier Sleeper observations remain partial; their
surviving summaries do not recreate missing original response bytes. See
[`2026-10-21-offer-source-followup-v1.json`](../evidence/offers/2026-10-21-offer-source-followup-v1.json).

## Official documentation reviewed

### ESPN / Disney

[Disney Terms of Use, United States](https://disneytermsofuse.com/english/), marked
**Last Updated: May 24, 2024**, explicitly includes ESPN in its product scope.
Section **2.B.x** restricts automated access, copying and extraction, including
scripts and data compilation. Sections **1.C** and **2.A** distinguish specific
terms and the limited consumer license. No reviewed exception or applicable
supplemental permission establishes this pilot's proposed direct collection and
retention arrangement. A public endpoint, successful response or owner task
authorization does not supply that missing basis.

### Sleeper

[Sleeper General Terms of Use](https://support.sleeper.com/en/articles/5486620-general-terms-of-use),
reached from `https://sleeper.com/terms`, was marked **Last Updated: October 6,
2026**. Sections **11.1** and **11.3** address automated extraction and third-party
access, with provider authorization distinct from a user's authorization.

[Sleeper API documentation](https://docs.sleeper.com/), **Introduction**, describes
a free, tokenless, noncommercial API for its documented fantasy league, draft and
roster resources. This review found no corresponding documentation there for the
Picks `/lines/available` route. The documented fantasy allowance is therefore not
treated as a blanket Picks-feed grant.

These findings are scoped to the documents and operation reviewed. An applicable
documented public-source allowance can establish a basis when it actually covers
the selected use; this review imposes no universal requirement to obtain a bespoke
provider agreement for every source.

## Preserve the existing historical allowance

[`2026-10-20-history-retention-rights.json`](../evidence/data/2026-10-20-history-retention-rights.json)
records the integration owner's acceptance of one bounded compact derived
normalized input, using the publisher-asserted CC BY 4.0 label on the
SportsDataverse release store. Preserve its exact rows, attribution, modification
notice and scope. That decision did not establish blanket upstream clearance,
recurring direct ESPN extraction, or raw-provider redistribution.

This review neither revokes that bounded historical acceptance nor expands it to
fresh event, roster or offer collection. Existing six-bundle historical display
evidence and PR #11's release remain separate.

## The actual retention design and owner decision

The candidate in [`OPERATIONAL_RAW_RETENTION.md`](OPERATIONAL_RAW_RETENTION.md)
places **ciphertext in this public repository**. It is not a private GitHub
repository. Confidentiality of plaintext is distinct from the source's permitted
retention or redistribution scope. Source review must address the actual
ciphertext location, duration and derived public facts.

The proposed Actions secret `NML_OP002_RAW_PRIVATE_KEY` holds a **decryption key**,
not a new provider API key or paid-service credential. The current checkpoint has
no installed operational key/certificate, verified hosted key recovery or admitted
backend. Synthetic encryption and fresh-clone tests do not establish those facts.

Before installation, prepare the exact custody, installation, fingerprint,
authenticated hosted-readback and recovery procedure. The specific owner input
needed is an **existing owner-controlled durable backup location and recovery
method for the original private key**. An ephemeral runner file, temporary test
key or ciphertext checksum is not a backup. Keep key material outside Git and
public output; test the intended recovery without exposing its contents. Do not
silently replace the original key during a frozen cycle.

This configuration decision is separate from source admission. Another blanket
owner approval cannot establish rights belonging to a provider.

## Practical closure routes and work that can continue

An operating admission must identify the exact source, access method, retained
copies, duration, intended derived publication and supporting evidence. It may
come from an applicable documented allowance, existing provider authorization, or
a separately reviewed permitted source/import route. If a different route changes
the plan or identity contract, prepare that change under a new reviewed version
before activation. No such route is admitted by this document.

Continue the encrypted-source-to-ledger adapter, authenticated raw reader, exact
admission-reference resolver, genuine entrypoint/destination preparation and
offline source-format verification. Genuine operation remains disabled until the
actual requirements and separate activation approval are satisfied. A supplied
admission dictionary must resolve to reviewed evidence; it cannot admit itself.

For an actual offer, separately verify its complete contract and applicable rules,
recover the original evidence through an admitted backend, and review the exact
derived-fact publication. A missing price may remain explicit. Missing contract
semantics, source evidence or source-use basis remain blockers to that offer only.
Statistical forecast delivery remains independent of bookmaker prices.

No new service, signup, provider API key, collection schedule or provider contact
is introduced. A later activation deadline cannot be met by relabeling early
preparation captures, filling missing rights with an assertion or changing a
frozen clock. Preserve the actual inactive/partial state if the named plan's
requirements are not satisfied in time.

This documentation review changes no model, category inventory, forecast,
outcome, grade, ticket, frozen receipt, historical record, NFL/MLB project or
activation state. It is not a runtime or hosted-timing test.

## October 21 integration-owner follow-up

The e5eb1a2 / 714630dd review and forward software fixes do not supply the missing
source-use allowance. Reused official-document findings above remain scoped to
the four exact proposed input routes, public-repository ciphertext retention,
necessary research facts and a separate first-offer contract. No new provider GET
was performed by this follow-up. An independent offline replay of the surviving
ESPN originals matched their retained hashes: six team/overtime items and no
complete player contract. Earlier partial Sleeper summaries do not recover their
missing originals or contract rules. No permanent source-absence conclusion.

The smallest source task remains an applicable existing documented allowance or
authorization for this exact import/access, retention and derived publication,
then original-byte recovery through the admitted backend. Another blanket owner
approval, HTTP200, synthetic offer or encryption test cannot fill that gap. Price
may remain unavailable for an otherwise complete admitted offer. Forecast delivery
requires its own valid statistical inputs, not an offer or sportsbook price.

# Native Boolean NBA offers and private recovery

October 23, 2026 UTC. Draft implementation in PR #20. No source collector,
public admission, new forecast, merge, deployment or scheduler is enabled here.

## What works

`nba-native-player-offer-v2` represents an actual source-native player contract
without inventing a permanent provider player ID or converting a Yes/No
achievement into an offered `0.5` line. It preserves the external ESPN player
crosswalk, native event/version, exact group/market/selection, literal prices,
full-game/overtime meaning, eleven settlement witnesses and seven original
source identities. Missing decimal prices remain `PRICE_UNAVAILABLE`.

The actual prepared record is **9,450 encoded bytes**, derived from the retained
Myles Turner DD Yes observation, with normalization actually at
**21:14:32.682251 UTC**. Its original board observation remains
**20:00:14.986063 UTC**, supporting evidence **20:01:31.153166 UTC** and original
review normalization **20:13:01.190345 UTC**. Nothing is backdated or issued.
The private preview verifies the create-only package intent and independently
replays all seven originals under `python -O` before rendering.

The existing offer channel now has explicit `nba-player-offers-v2` dispatch;
v1 validation and records remain unchanged. The existing OfferStore can retain
one bounded private-archive pointer and its derived native contract in the shared
ledger, then replay the complete source graph on restart. The actual Pages
`make_asset` entrypoint has a native-only authenticated default reader after the
admission gate. Actual-source records require strict remote source-graph recovery;
synthetic local readers cannot establish that status. Legacy reader behavior is
unchanged. A synthetic recovery
exercise verifies idempotency, byte preservation and refusal of a changed source
reference. The shared 512-record/32-MiB limits are unchanged. A native Yes/No
filter does not alter OVER_ONLY/UNDER_ONLY/MIXED ticket policies.

Both Python and JavaScript require an **internal reviewed exact-record registry**
before actual public export. That registry is empty. Caller flags, a valid hash,
a local preview or a passing test cannot grant admission. Native event identity
does not establish a canonical forecast join; current matching returns UNMATCHED,
EV null, qualification unavailable and ticket eligibility false.

## Source meaning and scope

The retained [MoviOdds API documentation](https://moviodds.com/doc) explicitly
invites saving copied matches, names and prices. This is a published basis for
bounded private retention and independent replay; another bespoke-consent step
is not automatically necessary for that scope. The newly retained
[NBA documentation](https://moviodds.com/bet365-nba-odds-api/) confirms free,
credentialless informational access and the independent bet365 attribution.
It does not supply the missing NBA numeric comparison operator.

Narrow attributed informational display and unrestricted raw-feed redistribution
are different scopes. No public raw mirror or recurring MoviOdds collector has
been admitted. Any actual offer-publication registry entry still needs its exact
source/contract/archive review and authorized release. Preferred DraftKings/
Sleeper work and price-independent SportsDataverse forecasts remain separate.

The native record can describe the complete source DD/TD contract despite a
conflicting canonical start. It preserves both starts and does not manufacture
an event crosswalk. Of the retained sample's 1,229 player observations, 34 binary
contracts are complete locally; 1,195 numeric selections lack an established
operator. TOV was unobserved, not proven absent. All 13 categories plus PA remain
inventoried. No new prices, events, full-history diagnostics or model comparisons
were requested by this package.

## Private archive implementation and actual blocked attempt

`multisport_lab.moviodds_archive` reuses this repository's existing content-addressed
GitHub Release object transport, with a new source-specific manifest. It never
labels these bytes as SDV production records. Its fixed destination is the draft
`diagnostics-nml-nba-moviodds-20261023`; **do not publish that draft**.
[GitHub documents](https://docs.github.com/en/rest/releases/releases) that draft
listings require push access. Fresh draft checks occur at every read/write,
including immediately before actual raw upload/download and cache readback.
Application writes are create-only; GitHub administrators can still mutate a
draft, so this is not a claim of platform-enforced immutable storage.

Sixteen exact original files total **3,208,947 bytes**. Deduplication projects
**16 source/manifest objects, 243,579 wire bytes**. The native record and its
descriptor add at most two objects. The complete namespace is bounded at
**32 objects / 8 MiB**, each original body at 2 MiB, metadata at 256 KiB and the
private package at 512 files / 32 MiB. Previews are excluded. Interrupted retries
reuse original bytes and normalization clocks; a fresh reader must recover every
original and validate meaning before acknowledging durability.

The actual attempt made **21 archiver GitHub API actions**. It created draft
release **422318512**, but its **first raw asset upload returned HTTP 401,
`Bad credentials`**. A later read-only inventory found **zero assets**. Normal
GitHub metadata authentication still worked. The exact upload failure's cause is
unestablished; no alternate transport, public raw fallback, automatic upload retry
or false recovery acknowledgment was used. This was a GitHub HTTP failure,
**not an automatic approval-review rejection**. Original bytes, intent and the
request inventory remain in ignored local storage. **Durable remote raw recovery
has not been established.**

Two later read-only GET diagnostics using the installed and newer CLI versions
both sent an authorization header and received HTTP 400 at the upload URL. They
performed no upload, did not establish POST capability and did not explain the
first 401. No credential values or raw debug headers were retained.

The existing Pages token's actual private-draft read access also remains
unverified. Synthetic default-reader tests exercise the connected entrypoint;
they cannot establish that hosted capability. Public registries remain empty
until the exact original archive, canonical record and source/display review
meet their own admission requirements.

No new sports-provider key or encryption-key arrangement is required by this
private draft design. Its remaining infrastructure dependency is a working
existing GitHub authorization context for **release-asset uploads to
`uploads.github.com`**, followed by actual independent recovery. Do not ask the
owner to put private key/token material in chat.

Private handover is prepared at
`.local-data/moviodds-private-originals-20261023.zip`: **17 files / 249,419 bytes**,
SHA256 `67d13f6da7985c4b9022f98bd1c269b8dc104277892fe173add494a7df3fc2d2`.
It contains only the sixteen exact originals/intent/review and the unchanged
native record. All extracted bytes were compared against the source package.
It remains a local private handover, not a public artifact or durable remote
archive. If this environment's upload access cannot be restored, the smallest
owner-controlled alternative is the same prepared archive command in an existing
authenticated GitHub CLI environment with that private package. No provider
account/key or new service is needed.

The existing CLI, once that upload access works, preserves the same originals:

```bash
python3 -O -m multisport_lab.moviodds_archive \
  --archive .local-data/moviodds-review-20261023-v2

# Retain the exact successful reference JSON, then recover with a cold process:
python3 -O -m multisport_lab.moviodds_archive \
  --recover .local-data/SUCCESSFUL_ARCHIVE_REFERENCE.json \
  --output .local-data/moviodds-independent-recovery

node scripts/render_local_offer_review.mjs \
  .local-data/moviodds-review-20261023-v2/native-offer.json \
  .local-data/moviodds-review-20261023-v2/private-native-offer.html
```

The native archive method additionally retains `native-offer.json` and its exact
original normalization through `archive_native_offer` / `recover_native_offer`.
Use the same existing record on retry; rebuilding it would change its identity.
Preserve the first failed attempt's source pins and intent. A later continuation
must record its actual reviewed implementation and later operation clock instead
of rewriting that failed receipt. Source 7915972 completes the default Pages
reader; the first attempted uploader predates that follow-up.

## Bounded event-discrepancy follow-up

One new document GET and two licensed schedule-identity GETs (including the one
redirect) consumed **three of four registered requests**, zero retries. The new
complete NBA document is 14,423 bytes. The same-game schedule download exceeded
its declared **2-MiB identity-reader ceiling** at 21:23:17.393242 UTC. Its retained
2,097,153-byte prefix is explicitly incomplete, never imported and never assigned
a full-file hash. No limit was raised and the old review was not rebound.

The ten-minute disagreement therefore remains unresolved. Reuse a complete new
schedule original from the **already separately admitted 64-MiB SDV production
capture path** when an actual timely plan obtains it; a versioned crosswalk
companion can then retain the later observation and both original starts. Do not
retroactively claim that this later resolution was available at the old capture.
For numeric selections, the exact remaining source question is whether NBA
group `181446`, `side: "5"` means at least five, over five, or another predicate.
A matched published native label/schema clarification can answer that question;
more unrelated events or prices cannot.

See `evidence/offers/2026-10-23-moviodds-completion.json` and the latest handoff
for actual verification and the independent automatic-delivery diagnosis.

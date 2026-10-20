# PROS004 current schedule evidence — October 20, 2026

**Result: SOURCE_COMPLETENESS_BLOCKED; PROS004 remains INACTIVE.**
The user's bounded current metadata inspection is separate from the expired
October 20 operating pilot. No pilot operation, player selection, forecast,
statistical outcome or scheduler action occurred.

Actual requests ran **2026-10-20T19:32:07.895099Z–2026-10-20T19:32:08.968371Z**.
Exactly three verified-HTTPS GETs used the existing ESPN NBA scoreboard route,
with adjacent `dates=20261020`, `20261021`, `20261022` and `limit=1000`.
Each request had a 30-second / 2-MiB limit; redirects and retries were disabled.
All completed HTTP 200. Total retained raw body size was
**204,880 bytes**. Raw bodies remain only
under `/tmp/nml-pros004-current-schedule-20261020-1933/`, outside Git and Pages.

| Local date route | HTTP | Source event count | Body bytes | Raw SHA-256 |
| --- | ---: | ---: | ---: | --- |
| 20261020 | 200 | 3 | 41,560 | `681eba776a330eece32bd78714cad5ab961b8de810d7ebef294d0bbc083b93db` |
| 20261021 | 200 | 11 | 134,614 | `c70e7149cc1fe821105ecf7e5c8736dda1cc8a774d397f2db4bfedeb521b4b3f` |
| 20261022 | 200 | 2 | 28,706 | `f0133a0accd5025148bc1e845ad82693f3d874113bbe70b9d3c74510d0b10b3e` |

The safe metadata/hash receipt is
`evidence/data/2026-10-20-pros004-current-schedule.json`. It retains exact URLs,
actual request/response-completion clocks, normalization-import clocks, HTTP
Date/ETag/Last-Modified when supplied, source update `null` when unknown, and
normalized event identities/start/teams/status. HTTP Date is not treated as the
upstream event-update time. No actual historical availability is inferred.

## What this evidence establishes

The three routes yielded these six distinct observed event identities whose
starts fall on UTC October 21:

| ESPN event | Observed UTC start | Home / away team IDs | Observed source status |
| --- | --- | --- | --- |
| `401909090` | 2026-10-21T01:30:00.000000Z | 24 / 25 | STATUS_SCHEDULED |
| `401909834` | 2026-10-21T23:00:00.000000Z | 19 / 1 | STATUS_SCHEDULED |
| `401909835` | 2026-10-21T23:00:00.000000Z | 27 / 15 | STATUS_SCHEDULED |
| `401909091` | 2026-10-21T23:30:00.000000Z | 14 / 16 | STATUS_SCHEDULED |
| `401909836` | 2026-10-21T23:30:00.000000Z | 17 / 30 | STATUS_SCHEDULED |
| `401909837` | 2026-10-21T23:30:00.000000Z | 28 / 4 | STATUS_SCHEDULED |

No cross-route version conflict or normalization rejection was observed. This
is metadata observed now, with no assertion that provider status is continuously
monitored or that source operations are admitted for a 21-day recurring study.
The current user authorization covers this bounded inspection; accessibility or
HTTP 200 alone is not expanded into a broader source permission claim.

## Completeness and activation deadline

All three actual decoded response bodies lack `pagination` and any other
root pagination/count/page/total/limit metadata. They contain fewer events than
the requested `limit=1000`, which is **not** a completeness certificate.
Calling the registered `make_schedule('2026-10-21', observations,
mode='READINESS_DIAGNOSTIC')` against the exact bytes rejected them with:

```text
UNKNOWN_SCHEDULE_COMPLETENESS: source pagination/count metadata is absent
```

Therefore the complete UTC-date inventory, and hence the actual first selected
T90, remain **UNKNOWN** under the registered source contract. This does not prove
that the provider omitted games or permanently lacks a usable route. It identifies
the missing source-completeness evidence required for admission.

The earliest **observed candidate** is `401909090`, home team 24 / away team 25,
starting October 21 01:30 UTC, still labeled `STATUS_SCHEDULED` in these bytes.
**If** it is the first event in a complete inventory and its version stays
unchanged, its T90 would be **October 21 00:00 UTC** and selection close **October
20 23:50 UTC**. Neither time is declared the actual deadline by this audit.

The reservation's theoretical earliest T90 remains **October 20 22:30 UTC /
17:30 CDT**, from the earliest possible UTC October 21 start. That theoretical
boundary is distinct from the observed conditional candidate and from a verified
actual cutoff. October 21 midnight is not an automatic safe implementation
freeze deadline.

The next source task is a separately reviewed, permitted completeness proof or
source route that satisfies the frozen contract, without inventing page metadata
or weakening the registered window. Keep the original reservation inactive if
timely reviewed activation cannot be established; no backfill or replacement
subjects are admitted by this metadata audit.

## Exact verification

Executed audit command:

```bash
PYTHONPATH=/workspace/nml-pros004-readiness python3 /tmp/nml-pros004-current-schedule-audit.py
```

The receipt binds the executed script SHA-256 and the unchanged input-normalizer
source SHA-256. An independent local check re-read all three raw bodies, reproduced
their sizes and hashes, checked route uniqueness and request/observation/import
ordering, and confirmed zero player selections, forecasts, outcomes and pilot
operations. No model was fitted or evaluated. All original records and earlier
source receipts remain unchanged.

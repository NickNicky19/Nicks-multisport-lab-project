# October 20 expired pilot: read-only operational diagnosis

Latest dated observation: a late scheduled run is now visible and its guarded
abort is independently recovered. See the final section. Earlier findings below
remain observations at their stated times, not claims about later remote state.

Observation interval: October 20, 2026, **19:30–19:35 UTC**, after the original
17:20–17:30 capture and 17:30–17:35 issuance windows. This is a new checkpoint;
earlier preparation, activation and source observations remain unchanged.

**Classification: MISSED_OR_UNOBSERVED_EXECUTION. Cause: NOT_ESTABLISHED.**
The available GitHub run inventories and independently recovered records contain
no actual scheduled pilot execution or timely issuance. An absent run is not
proof of a particular scheduler, permission, source or application failure. No
scheduled execution log exists in the observed inventory from which to establish
such a cause.

The create-only evidence receipt is
`evidence/cycles/2026-10-20-pilot-operational-recovery.json`. It retains exact
query arguments, observation clocks, response hashes, complete available run/job
metadata, archive/file log hashes, the original record inventory and read-only
recovery output. Raw API responses and job-log archives remain under
`/tmp/nml-pilot-recovery-20261020/`; signed download credentials and raw provider
bodies are excluded from public evidence.

## Current findings

| Read-only check | Actual observation |
| --- | --- |
| Workflow 390126745 | `active`, path `.github/workflows/nba-20261020-pilot.yml` |
| Available workflow timestamps | created `2026-10-20T04:12:56.000Z`; updated `2026-10-20T05:59:11.000Z` |
| Actual default branch | `main`, `735a464e9e8718303ef481abf711a8969de56694` |
| Default-branch workflow bytes | 3,413 bytes; SHA-256 `900783602710fd82761c071a143ad7e9c7d5d491461ca4c8d650427638583dab`; cron `15 17 20 10 *` |
| Repository-wide available runs | 72; all returned in one page, below the requested page size of 100 |
| Repository schedule-filtered runs | `total_count: 0`; repeated final read also zero |
| Pilot workflow available runs | 18; all returned in one page |
| Pilot workflow schedule-filtered runs | `total_count: 0`; repeated final read also zero |
| Actual pilot-workflow events | All 18 are `pull_request`, with attempt 1; all are setup-era runs |
| Latest pilot-workflow run | `39370196314`, created/started `04:33:21Z`, updated `04:36:05Z`, successful PR setup |
| Available actual job/log evidence | Six runs have jobs; all six run-log ZIP archives were retrieved and inspected as setup activity |
| Repository runs created at/after 16:00 UTC | None in the fully returned initial repository inventory |
| PR #8 | Open draft, head `df446eee302fd6662ef82184e2c733f5d6e2d2dd`, updated `06:07:36Z` |
| Independently cloned records branch | Same exact `df446eee302fd6662ef82184e2c733f5d6e2d2dd`; clean working tree |
| Retained ledger | Original 19 receipts / 1,817,800 encoded bytes, every raw hash equal to the frozen plan |
| Execution claim / capture intent / fresh binding | Absent at the frozen outer runner's exact paths |
| Generation intents / execution reports / capture-attempt metadata | No matching files retained |
| Read-only `manual_cycle recover` | `ISSUANCE_WINDOW_CLOSED`, `NOT_READY`, null fresh input, zero selected forecasts, all four subjects missing |
| Native automation | Private read-only lookup at 19:34:17–19:34:18 UTC confirms `is_enabled: false`, null next run; no state mutation |

The native task's null run history is not proof that it never ran. Its current
disabled state was observed without changing it. The GitHub workflow's active
flag proves configuration state only; it proves neither a dispatch nor a worker.
Earlier successful PR setup runs and source probes do not become a scheduled
pilot execution or timely inputs.

The six `gh run view --log` commands returned successful but empty output; those
attempts are recorded as unavailable log contents. The supported REST run-log
archive route then returned actual archives for all six runs with jobs. A direct
job-log redirect request returned HTTP 403; the signed redirect query is omitted.
There is still no actual scheduled run/log for the expired operating window.

## Exact safe recovery path used

```bash
git clone --single-branch --branch records/nba-20261020-401909088-t90 \
  https://github.com/NickNicky19/Nicks-multisport-lab-project.git \
  /tmp/nml-pilot-recovery-20261020/records-readback
cd /tmp/nml-pilot-recovery-20261020/records-readback
git rev-parse HEAD
git status --short --branch
python3 -m multisport_lab.manual_cycle recover \
  --plan evidence/cycles/2026-10-20-nba-401909088-plan.json
```

`recover` performed zero provider requests and generated zero forecasts. Original
records, reviewed producer `58530309cf384425e15f02fd9fa980899a4dc0bc`, the plan,
event, cohort, windows, PR #8 and the records branch were not changed. No
`pilot_github preflight`, dispatch, rerun, workflow enable/disable, capture, bind,
issue, grading, native-task mutation, merge or deployment was invoked.

## Next action and limits

Retain this original cycle as expired/missed-or-unobserved. No observed genuine
forecast exists to grade; the original six historical grades remain unchanged.
Do not recreate the missed cycle, use the early preparation input as fresh data,
replace subjects or backdate records. This diagnosis establishes no forecasting
quality, financial settlement or qualified ticket.

If an actual later run or previously unavailable checkpoint becomes visible,
append a new dated observation of its real state and clocks. Do not rewrite this
observation or treat a late invocation as timely issuance. Any later operating
cycle requires a separate versioned reservation and authorization. PROS004's
separate inactive implementation work does not revive this expired pilot.

## Read-only follow-up, October 20 20:30 UTC

A separate checkpoint at 20:30:40.993165–20:30:46.121326 UTC retained the
same classification. Repository-wide and workflow-specific schedule filters
still returned zero runs; workflow390126745 remains active at the unchanged
path/timestamps. Its inventory remains18 earlier PR setup runs. The repository
now has76 runs because PR10 review builds continued; this is unrelated to pilot
execution. Main remains735a464e9e8718303ef481abf711a8969de56694 and draft
PR8/records branch remain df446eee302fd6662ef82184e2c733f5d6e2d2dd. No
execution log was found from which to establish a cause. Ten read-only GitHub
queries, their exact clocks and response hashes are retained in
`evidence/cycles/2026-10-20-pilot-operational-followup-2030.json` (raw SHA256
`4e971b62c6da3eec814a7b87e7072beee30bcdf899164ca511c4ea45fefcba37`).
The earlier full inventory, six log archives, independent records clone and
read-only manual recovery remain preserved; no pilot mutation occurred.

## Later actual execution, observed20:55–20:59 UTC

**ACTUAL_PARTIAL_EXECUTION / LATE_GUARDED_ABORT.** Scheduled run39493005199,
attempt1, main735a464, was created/started20:33:35 and failed20:36:37 UTC.
Actual executor logs match the retained report20:34:24.536822–20:34:33.119840:
EXPIRED_INCOMPLETE/exit1, issuance window expired, zero provider requests,
zero forecasts, null input and all four subjects missing. Why the scheduler
created the run late is not established; source/access failure is not inferred.

Independent fresh records recovery atdec5cc9fa397332244985bea8815bd9a89ea264e
retains the claim and factual abort/publication metadata, while all19 original
ledger records/1,817,800 bytes still match the plan. No binding, capture/generation
intent or new forecast exists. Read-only manual recovery returns closed/NOT_READY,
null input, zero selected records and zero pending grades. Clone stays clean.

Workflow390126745 is now observed disabled_manually (updated20:33:43 UTC).
No state mutation or retry was performed by this implementation session.
PUBLICATION_VERIFIED denotes the factual draft-PR8 checkpoint, not completed
issuance or site publication. New source/forecast/grade/settlement counts remain0.
The older observations and original cycle identity/deadlines remain unchanged.

Exact evidence: `evidence/cycles/2026-10-20-pilot-late-observation.json`, raw
SHA256 `be524327d6b0abd649239291e642e7e0bbfa06e5353834d2d1239d04367d6203`.

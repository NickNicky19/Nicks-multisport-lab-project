# October 20 expired pilot: read-only operational diagnosis

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

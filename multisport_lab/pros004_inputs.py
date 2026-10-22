"""Offline PROS004 source-byte contracts and deduplicated fixed history.

No HTTP or scheduler is installed. A caller must supply actual response bytes
and capture receipts; checksums bind retained content, not source authenticity.
Unknown daily-route pagination/completeness is rejected rather than upgraded by
an operator's boolean assertion. Diagnostic inputs are never issuance evidence.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .baseline import COUNT_FIELDS, HistoricalAppearance
from .integrity import IntegrityError, canonical, digest, load_json, read_receipt, stamp, utc
from .ledger import LedgerRef
from . import pregame_sources as old

STUDY_ID = "NBA-ALL13-JOINT-PROS-004"
HISTORY_SCHEMA = "nba-pros004-history-v1"
SCHEDULE_SCHEMA = "nba-pros004-utc-schedule-v1"
SELECTION_SCHEMA = "nba-pros004-selection-v1"
EVENT_SCHEMA = "nba-pros004-event-v1"
NORMALIZER_VERSION = "nba-pros004-source-inputs-v1"
INPUT_RECORD_ID = "dfa1c4345495eb3aa6b203f2e8309c89c112b6b78a36cd3d2c603d390776b6fc"
PANEL_SHA256 = old.PANEL_SHA
PANEL_ROWS = 26_645
PANEL_BYTES = 14_720_351
MAX_SOURCE_BYTES = 2*1024*1024
MAX_ROUTE_EVENTS = 1000
MAX_EVENT_BODY_BYTES = 31*1024  # complete ledger envelope receives the 32KiB ceiling
MAX_HISTORY_BODY_BYTES = 2*1024*1024-2048
SOURCE_MAX_AGE_SECONDS = 1200  # chosen before activation; complete input persisted by T90-10m
MAX_CAPTURE_SECONDS = 30
BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
MODES = frozenset(("SYNTHETIC_DIAGNOSTIC", "READINESS_DIAGNOSTIC", "REAL_TIME_CAPTURED"))
WINDOW_FIRST = date(2026, 10, 21)
WINDOW_LAST = date(2026, 11, 10)
STANDARD_TEAMS = frozenset(str(t) for t in range(1,31))


def _now():
    return datetime.now(timezone.utc)


def _exact(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        raise IntegrityError(f"invalid {label} fields")
    return value


def _clock(value, label):
    try:
        parsed = utc(value)
    except (ValueError, TypeError) as error:
        raise IntegrityError(f"invalid {label} clock") from error
    if type(value) is not str or stamp(parsed) != value:
        raise IntegrityError(f"{label} requires canonical microsecond UTC clock")
    return parsed


def _sha(value, label):
    if type(value) is not str or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise IntegrityError(f"invalid {label} SHA256")
    return value


def _id(value, label):
    if type(value) is not str or not re.fullmatch(r"[1-9][0-9]*", value):
        raise IntegrityError(f"invalid {label} numeric identity")
    return value


def _check_digest(body, key):
    if body.get(key) != digest({k:v for k,v in body.items() if k != key}):
        raise IntegrityError(f"{key} checksum conflicts")


def _seal(body, key):
    return {**body, key:digest(body)}


def _mode(mode):
    if mode not in MODES:
        raise IntegrityError("unsupported input evidence mode")
    return mode


def _source_check(source, *, raw=None, imported_at=None):
    keys = {"source_id","source_url","request_started_at","observed_at","response_completed_at",
            "source_updated_at","source_response_generated_at","raw_sha256","raw_bytes","http_status",
            "http_date","etag","last_modified"}
    _exact(source, keys, "capture receipt")
    if type(source['source_id']) is not str or not source['source_id']:
        raise IntegrityError("capture needs an explicit source identity")
    started = _clock(source['request_started_at'],'request start')
    observed = _clock(source['observed_at'],'observation')
    completed = _clock(source['response_completed_at'],'response completion')
    if not started <= observed == completed or (completed-started).total_seconds() > MAX_CAPTURE_SECONDS:
        raise IntegrityError("capture chronology or latency conflicts")
    if imported_at is not None and completed > imported_at:
        raise IntegrityError("capture occurs after normalization/import")
    for key in ('source_updated_at','source_response_generated_at'):
        if source[key] is not None and _clock(source[key], key) > observed:
            raise IntegrityError("source update/generation clock follows observation")
    _sha(source['raw_sha256'],'source body')
    if type(source['raw_bytes']) is not int or not 0 < source['raw_bytes'] <= MAX_SOURCE_BYTES or type(source['http_status']) is not int or source['http_status'] != 200:
        raise IntegrityError("capture status/byte bound conflicts")
    for key in ('http_date','etag','last_modified'):
        if source[key] is not None and type(source[key]) is not str:
            raise IntegrityError('source HTTP metadata must be text or unknown')
    if type(source['source_url']) is not str:
        raise IntegrityError('source URL must be explicit text')
    if raw is not None:
        if type(raw) is not bytes or len(raw) != source['raw_bytes'] or hashlib.sha256(raw).hexdigest() != source['raw_sha256']:
            raise IntegrityError("capture receipt does not bind supplied response bytes")
    return source


def _observations(observations, expected, imported_at):
    if type(observations) is not dict or set(observations) != set(expected):
        raise IntegrityError("all exact event/roster source observations are required")
    proofs, raw = {}, {}
    for name, value in observations.items():
        _exact(value, {'raw','source'}, 'source observation')
        source = _source_check(value['source'], raw=value['raw'], imported_at=imported_at)
        if source['source_id'] != name:
            raise IntegrityError("source observation identity conflicts")
        wanted = (f"{BASE}/summary?event={expected[name]}" if name == 'summary'
                  else f"{BASE}/teams/{expected[name]}/roster" if name.startswith('roster-') else None)
        if wanted is not None and source['source_url'] != wanted:
            raise IntegrityError("source route does not identify normalized event/team")
        if name == 'scoreboard':
            route_date(source['source_url'])
        proofs[name] = deepcopy(source)
        raw[name] = value['raw']
    return proofs, raw


def _original_provenance():
    path = Path(__file__).resolve().parents[1]/'records/research_inputs'/f'{INPUT_RECORD_ID}.json'
    original = read_receipt(path,max_bytes=4*1024*1024)
    if original.get('record_id') != INPUT_RECORD_ID or original.get('kind') != 'research_inputs':
        raise IntegrityError('original retained history record identity conflicts')
    return original['data']['source_pack']['history_provenance']


@lru_cache(maxsize=1)
def _fixed_history_rows(encoded_history, panel_sha256, panel_bytes, panel_rows):
    """Memoize only exact-content, target-neutral immutable historical rows.

    The complete canonical compact bytes and fixed expected panel identity form
    the cache key. Clocks, evidence lanes, mutable bodies and on-disk provenance
    are deliberately outside this bounded cache and are rechecked by callers.
    """
    rows = tuple(old.unpack_history(json.loads(encoded_history)))
    if any(r.participation != 'APPEARED' or r.final_status != 'FINAL' or r.season_type != '2'
           or r.minutes is None or any(getattr(r,k) is None for k in COUNT_FIELDS)
           or r.team_id not in STANDARD_TEAMS or r.opponent_id not in STANDARD_TEAMS for r in rows):
        raise IntegrityError('history must keep complete standard-team appearances, with DNP/missing distinct')
    raw = old._panel_bytes(rows)
    if (hashlib.sha256(raw).hexdigest(), len(raw), len(rows)) != (panel_sha256, panel_bytes, panel_rows):
        raise IntegrityError("PROS004 requires the complete fixed history without truncation")
    return rows


def _history_provenance(provenance, imported):
    _exact(provenance, old._HISTORY_PROVENANCE_KEYS, 'history provenance')
    if provenance != _original_provenance():
        raise IntegrityError('history provenance and reconstructed-availability limitations must remain unchanged')
    if (provenance['normalized_panel_sha256'],provenance['normalized_panel_bytes'],provenance['normalized_panel_rows']) != (PANEL_SHA256,PANEL_BYTES,PANEL_ROWS):
        raise IntegrityError("history provenance accounting conflicts with recovered bytes")
    if provenance['normalization_version'] != 'nba-panel-preparation-v1' or provenance['current_season_history_claim'] is not False:
        raise IntegrityError("history version/current-season meaning conflicts")
    path = Path(__file__).resolve().parents[1]/'evidence/data/2026-10-19-source-receipts.json'
    if provenance['source_receipts_sha256'] != hashlib.sha256(path.read_bytes()).hexdigest():
        raise IntegrityError("history source receipt file binding conflicts")
    originals = {r['key']:r for r in load_json(path)['receipts']}
    expected = []
    for key in ('sdv_player_box_2026','sdv_schedule_2026'):
        r = originals[key]
        expected.append({'source_id':key,'source_url':r['url'],'raw_sha256':r['sha256'],
                         'raw_bytes':r['bytes'],'observed_at':stamp(utc(r['observed_at'])),
                         'source_updated_at':stamp(utc(r['source_updated_at'])) if r['source_updated_at'] else None,
                         'source_version':'github-asset:'+str(r['github_asset_id'])})
    if provenance['source_receipts'] != expected:
        raise IntegrityError("historical source/version/update/observation binding conflicts")
    for source in expected:
        if _clock(source['observed_at'],'historical observation') > imported:
            raise IntegrityError("history import precedes retained source observation")
    original_exclusions = load_json(path.parent/'2026-10-19-panel_preparation_summary.json')['upstream_exclusions']
    if provenance['upstream_exclusions'] != original_exclusions:
        raise IntegrityError("original upstream history exclusions changed")
    _sha(provenance['normalizer_source_sha256'],'history normalizer')
    return provenance


def make_history_body(history, provenance, *, mode='READINESS_DIAGNOSTIC', retained_input_record_id=INPUT_RECORD_ID):
    body = _seal({'schema_version':HISTORY_SCHEMA,'study_id':STUDY_ID,'mode':_mode(mode),
                  'retained_input_record_id':retained_input_record_id,'imported_at':stamp(_now()),
                  'history':deepcopy(history),'history_provenance':deepcopy(provenance)},'history_id')
    return validate_history(body)


def validate_history(body, *, now=None):
    _exact(body, {'schema_version','study_id','mode','retained_input_record_id','imported_at','history','history_provenance','history_id'}, 'shared history')
    if body['schema_version'] != HISTORY_SCHEMA or body['study_id'] != STUDY_ID:
        raise IntegrityError("unsupported shared history contract")
    _mode(body['mode']); _check_digest(body,'history_id')
    if body['retained_input_record_id'] != INPUT_RECORD_ID:
        raise IntegrityError("history must preserve exact original retained input reference")
    imported = _clock(body['imported_at'],'history import')
    if imported > utc(now if now is not None else _now()):
        raise IntegrityError("history import is in the future")
    if len(canonical(body)) > MAX_HISTORY_BODY_BYTES:
        raise IntegrityError("shared history exceeds complete-envelope reserved budget")
    try:
        _fixed_history_rows(canonical(body['history']),PANEL_SHA256,PANEL_BYTES,PANEL_ROWS)
        _history_provenance(body['history_provenance'],imported)
    except (ValueError, KeyError, TypeError) as error:
        if isinstance(error,IntegrityError):
            raise
        raise IntegrityError(f"invalid fixed history: {error}") from error
    return body


@lru_cache(maxsize=1)
def _historical_appearances(encoded_history, panel_sha256, panel_bytes, panel_rows):
    rows = _fixed_history_rows(encoded_history,panel_sha256,panel_bytes,panel_rows)
    converted = [HistoricalAppearance(event_id=r.event_id,player_id=r.player_id,
        team_id=r.team_id,opponent_id=r.opponent_id,event_start=r.event_start,
        outcome_available_at=r.event_start+timedelta(hours=24),minutes=r.minutes,
        minutes_precision=r.minutes_precision,id_namespace=r.id_namespace,
        game_duration_minutes=r.game_duration_minutes,**{key:getattr(r,key) for key in COUNT_FIELDS}) for r in rows]
    return tuple(sorted(converted,key=lambda r:(r.event_start,r.event_id,r.player_id)))


def history_rows(body):
    validate_history(body)
    # A new list prevents callers from mutating the retained cache container;
    # every HistoricalAppearance itself is a frozen immutable data object.
    return list(_historical_appearances(canonical(body['history']),PANEL_SHA256,PANEL_BYTES,PANEL_ROWS))


def validate_input_lanes(event_body, history_body):
    """A prospective event cannot relabel diagnostic retained history as live."""
    if type(event_body) is not dict or type(history_body) is not dict:
        raise IntegrityError('event and shared history must be typed input objects')
    event_mode,history_mode = _mode(event_body.get('mode')),_mode(history_body.get('mode'))
    if event_mode != history_mode:
        raise IntegrityError('event and shared history evidence lanes differ')
    return event_mode


def route_date(url):
    parsed = urlparse(url)
    if f'{parsed.scheme}://{parsed.netloc}{parsed.path}' != f'{BASE}/scoreboard':
        raise IntegrityError("unsupported NBA schedule route")
    query = parse_qs(parsed.query,keep_blank_values=True)
    if set(query) not in ({'dates'},{'dates','limit'}) or len(query['dates']) != 1:
        raise IntegrityError("schedule route requires exactly one calendar date")
    if 'limit' in query and query['limit'] != [str(MAX_ROUTE_EVENTS)]:
        raise IntegrityError("unsupported schedule route result bound")
    value = query['dates'][0]
    if not re.fullmatch(r'\d{8}',value):
        raise IntegrityError("schedule route date is malformed")
    try:
        return datetime.strptime(value,'%Y%m%d').date()
    except ValueError as error:
        raise IntegrityError("schedule route date is invalid") from error


def _schedule_fact(event):
    # Scheduled status is retained even for a first event that later became
    # postponed/final; selection must fail rather than replace that event.
    if type(event) is not dict or len(event.get('competitions',[])) != 1:
        raise IntegrityError("schedule event requires one explicit competition")
    competition = event['competitions'][0]
    status = competition.get('status',event.get('status',{})).get('type',{})
    if type(status.get('name')) is not str or type(status.get('state')) is not str or type(status.get('completed')) is not bool:
        raise IntegrityError("schedule event requires explicit status")
    as_scheduled = deepcopy(event)
    as_scheduled['status'] = {'type':{'name':'STATUS_SCHEDULED','state':'pre','completed':False}}
    as_scheduled['competitions'][0]['status'] = deepcopy(as_scheduled['status'])
    try:
        facts = old._event_facts(as_scheduled,as_scheduled['competitions'][0],season=as_scheduled.get('season',{}))
    except (ValueError,KeyError,TypeError,AttributeError) as error:
        raise IntegrityError(f"invalid schedule event facts: {error}") from error
    if facts['season_ending_year'] != 2027:
        raise IntegrityError('PROS004 October2026 events require ending-year2027 season')
    return {'event_id':facts['event_id'],'event_starts_at':facts['event_starts_at'],
            'home_team_id':facts['home_team_id'],'away_team_id':facts['away_team_id'],
            'season_ending_year':facts['season_ending_year'],'season_type':facts['season_type'],
            'source_status':deepcopy(status),'scheduled_event_version':facts['event_version']}


def make_schedule(utc_date, observations, *, mode='READINESS_DIAGNOSTIC'):
    try:
        day = date.fromisoformat(utc_date)
    except (ValueError,TypeError) as error:
        raise IntegrityError("UTC study date must be ISO calendar date") from error
    if not WINDOW_FIRST <= day <= WINDOW_LAST:
        raise IntegrityError("date is outside the unchanged PROS004 reservation")
    imported = _now()
    if type(observations) is not list or len(observations) != 3:
        raise IntegrityError("UTC schedule requires three adjacent calendar-date response bodies")
    routes, proofs, all_events = set(), [], {}
    for observation in observations:
        _exact(observation,{'raw','source'},'schedule observation')
        source = _source_check(observation['source'],raw=observation['raw'],imported_at=imported)
        route = route_date(source['source_url'])
        if route in routes:
            raise IntegrityError("duplicate schedule date route")
        routes.add(route)
        try:
            raw = old._decode(observation['raw'])
        except (ValueError,TypeError) as error:
            raise IntegrityError(f"invalid schedule source bytes: {error}") from error
        if type(raw.get('leagues')) is not list or len(raw['leagues']) != 1 or type(raw['leagues'][0]) is not dict or raw['leagues'][0].get('id') != '46' or raw['leagues'][0].get('abbreviation') != 'NBA':
            raise IntegrityError("schedule source does not identify NBA league")
        events = raw.get('events')
        if type(events) is not list or len(events) > MAX_ROUTE_EVENTS:
            raise IntegrityError("schedule event count exceeds bounded source route")
        pagination = raw.get('pagination')
        required = {'page','pageCount','totalCount','pageSize'}
        if type(pagination) is not dict or set(pagination) != required:
            raise IntegrityError("UNKNOWN_SCHEDULE_COMPLETENESS: source pagination/count metadata is absent")
        if any(type(pagination[k]) is not int for k in required) or pagination != {'page':1,'pageCount':1,'totalCount':len(events),'pageSize':MAX_ROUTE_EVENTS}:
            raise IntegrityError("schedule pagination or exact source event count conflicts")
        if parse_qs(urlparse(source['source_url']).query).get('limit') != [str(MAX_ROUTE_EVENTS)]:
            raise IntegrityError("complete schedule route requires its explicit admitted limit")
        route_events = []
        for event in events:
            facts = _schedule_fact(event)
            previous = all_events.get(facts['event_id'])
            if previous is not None and previous != facts:
                raise IntegrityError("adjacent schedule routes disagree on event/version")
            all_events[facts['event_id']] = facts
            route_events.append(facts)
        proofs.append({'source':deepcopy(source),'route_date':route.isoformat(),
                       'pagination':deepcopy(pagination),'normalized_events_sha256':digest(route_events),
                       'normalized_events':route_events})
    if routes != {day-timedelta(days=1),day,day+timedelta(days=1)}:
        raise IntegrityError("UTC schedule date routes do not cover both adjacent dates")
    selected = sorted((v for v in all_events.values() if utc(v['event_starts_at']).date() == day),
                      key=lambda v:(utc(v['event_starts_at']),int(v['event_id'])))
    return validate_schedule(_seal({'schema_version':SCHEDULE_SCHEMA,'study_id':STUDY_ID,
        'mode':_mode(mode),'study_date':day.isoformat(),'imported_at':stamp(imported),
        'route_contract':'EXPLICIT_SOURCE_SINGLE_PAGE_TOTAL_COUNT_V1',
        'source_proofs':sorted(proofs,key=lambda p:p['route_date']),'events':selected},'schedule_id'))


def validate_schedule(body, *, now=None):
    _exact(body,{'schema_version','study_id','mode','study_date','imported_at','route_contract','source_proofs','events','schedule_id'},'UTC daily schedule')
    if body['schema_version'] != SCHEDULE_SCHEMA or body['study_id'] != STUDY_ID or body['route_contract'] != 'EXPLICIT_SOURCE_SINGLE_PAGE_TOTAL_COUNT_V1':
        raise IntegrityError("unsupported complete daily schedule contract")
    _mode(body['mode']);_check_digest(body,'schedule_id')
    imported = _clock(body['imported_at'],'schedule import')
    if imported > utc(now if now is not None else _now()):
        raise IntegrityError("schedule import occurs in the future")
    try:
        day = date.fromisoformat(body['study_date'])
    except (ValueError,TypeError) as error:
        raise IntegrityError("invalid study date") from error
    if not WINDOW_FIRST <= day <= WINDOW_LAST:
        raise IntegrityError("schedule date is outside the unchanged PROS004 window")
    if type(body['source_proofs']) is not list or len(body['source_proofs']) != 3:
        raise IntegrityError("schedule needs exact three route source proofs")
    routes, all_events = set(), {}
    for proof in body['source_proofs']:
        _exact(proof,{'source','route_date','pagination','normalized_events_sha256','normalized_events'},'schedule source proof')
        _source_check(proof['source'],imported_at=imported)
        route = route_date(proof['source']['source_url'])
        if route.isoformat() != proof['route_date'] or route in routes:
            raise IntegrityError("schedule route/date identity conflict")
        routes.add(route)
        events = proof['normalized_events']
        if type(events) is not list or len(events) > MAX_ROUTE_EVENTS or proof['normalized_events_sha256'] != digest(events):
            raise IntegrityError("schedule normalized facts or source count conflicts")
        if (type(proof['pagination']) is not dict or any(type(proof['pagination'].get(k)) is not int for k in ('page','pageCount','totalCount','pageSize'))
                or proof['pagination'] != {'page':1,'pageCount':1,'totalCount':len(events),'pageSize':MAX_ROUTE_EVENTS}):
            raise IntegrityError("schedule completeness source metadata conflicts")
        for event in events:
            _validate_schedule_fact(event)
            prior = all_events.get(event['event_id'])
            if prior is not None and prior != event:
                raise IntegrityError("schedule source proofs conflict on event/version")
            all_events[event['event_id']] = event
    if routes != {day-timedelta(days=1),day,day+timedelta(days=1)}:
        raise IntegrityError("schedule source proofs omit adjacent calendar routes")
    expected = sorted((v for v in all_events.values() if utc(v['event_starts_at']).date() == day),key=lambda v:(utc(v['event_starts_at']),int(v['event_id'])))
    if body['events'] != expected:
        raise IntegrityError("UTC schedule inventory omits/reorders admitted source events")
    return body


def _validate_schedule_fact(event):
    _exact(event,{'event_id','event_starts_at','home_team_id','away_team_id','season_ending_year','season_type','source_status','scheduled_event_version'},'normalized scheduled event')
    for key in ('event_id','home_team_id','away_team_id'):
        _id(event[key],key)
    if event['home_team_id'] == event['away_team_id'] or any(not 1<=int(event[k])<=30 for k in ('home_team_id','away_team_id')):
        raise IntegrityError("nonstandard/conflicting schedule teams")
    _clock(event['event_starts_at'],'scheduled start')
    if type(event['season_ending_year']) is not int or event['season_ending_year'] != 2027 or event['season_type'] != '2':
        raise IntegrityError("unsupported NBA schedule season")
    status = event['source_status']
    if type(status) is not dict or type(status.get('name')) is not str or type(status.get('state')) is not str or type(status.get('completed')) is not bool:
        raise IntegrityError("schedule status missing")
    expected = {k:v for k,v in event.items() if k not in {'source_status','scheduled_event_version'}}
    expected.update(id_namespace='espn',league='NBA',status='PRE_GAME')
    if event['scheduled_event_version'] != digest(expected):
        raise IntegrityError("schedule event version does not bind normalized identity/start/teams")


def first_event(schedule, *, now=None):
    validate_schedule(schedule,now=now)
    if not schedule['events']:
        return None
    first = schedule['events'][0]
    if first['source_status'] != {'name':'STATUS_SCHEDULED','state':'pre','completed':False}:
        raise IntegrityError("earliest frozen event is not pregame; never replace it")
    return first


def _event_observations(schedule, observations, imported):
    first = first_event(schedule,now=imported)
    if first is None:
        raise IntegrityError("VALID_EMPTY_UTC_DATE: no subject may replace an empty day")
    expected = {'scoreboard':None,'summary':first['event_id'],
                f"roster-{first['home_team_id']}":first['home_team_id'],
                f"roster-{first['away_team_id']}":first['away_team_id']}
    proofs, raw = _observations(observations,expected,imported)
    if route_date(proofs['scoreboard']['source_url']) not in {date.fromisoformat(p['route_date']) for p in schedule['source_proofs']}:
        raise IntegrityError('selected event scoreboard route is outside the admitted date inventory')
    try:
        event = old.normalize_event(raw['scoreboard'],raw['summary'],first['event_id'])
        rosters = {team:old.normalize_roster(raw[f'roster-{team}'],team,season_ending_year=event['season_ending_year']) for team in (event['home_team_id'],event['away_team_id'])}
    except (ValueError,KeyError,TypeError,AttributeError) as error:
        raise IntegrityError(f"current source normalization failed: {error}") from error
    if event['event_version'] != first['scheduled_event_version']:
        raise IntegrityError("current event version changed from frozen complete schedule")
    return event,rosters,proofs


def make_selection(schedule, observations):
    imported = _now()
    event,rosters,proofs = _event_observations(schedule,observations,imported)
    first = utc(event['event_starts_at'])-timedelta(minutes=100)
    if imported > first:
        raise IntegrityError("selection closes ten minutes before T90; no late cohort")
    if imported < first-timedelta(minutes=10):
        raise IntegrityError('complete input capture opens twenty minutes before T90')
    players = []
    for team,opponent in ((event['home_team_id'],event['away_team_id']),(event['away_team_id'],event['home_team_id'])):
        players.extend({**p,'opponent_id':opponent} for p in rosters[team][:2])
    if len(players) != 4 or len({p['player_id'] for p in players}) != 4:
        raise IntegrityError("both teams require two distinct supported active players")
    return _seal({'schema_version':SELECTION_SCHEMA,'event_id':event['event_id'],
        'event_version':event['event_version'],'schedule_id':schedule['schedule_id'],
        'declared_at':stamp(imported),'rule':old.RULE,'players':players,
        'rosters':rosters,'sources':proofs},'selection_id')


def _validate_selection(selection,event,schedule,current_rosters):
    _exact(selection,{'schema_version','event_id','event_version','schedule_id','declared_at','rule','players','rosters','sources','selection_id'},'frozen selection')
    _check_digest(selection,'selection_id')
    if selection['schema_version'] != SELECTION_SCHEMA or selection['rule'] != old.RULE or selection['event_id'] != event['event_id'] or selection['event_version'] != event['event_version'] or selection['schedule_id'] != schedule['schedule_id']:
        raise IntegrityError("frozen event/selection version conflicts")
    declared = _clock(selection['declared_at'],'selection declaration')
    cutoff = utc(event['event_starts_at'])-timedelta(minutes=90)
    if declared > cutoff-timedelta(minutes=10) or _clock(schedule['imported_at'],'schedule import') > declared:
        raise IntegrityError("complete schedule and selection were not frozen before selection closes")
    if type(selection['rosters']) is not dict:
        raise IntegrityError('selection roster proofs must be a keyed object')
    expected_players = []
    for team,opponent in ((event['home_team_id'],event['away_team_id']),(event['away_team_id'],event['home_team_id'])):
        roster = selection['rosters'].get(team)
        _validate_roster_facts(roster,team)
        expected_players.extend({**p,'opponent_id':opponent} for p in roster[:2])
    if selection['players'] != expected_players:
        raise IntegrityError("selected cohort does not follow frozen lowest-numeric-ID rule")
    legacy = {'schema_version':'nba-pregame-selected-cohort-v1',**{k:selection[k] for k in ('declared_at','event_id','rule','players')}}
    try:
        old.verify_selection(event,current_rosters,legacy)
    except ValueError as error:
        raise IntegrityError(f"current selected-player identity changed: {error}") from error
    expected_sources = {'scoreboard','summary',*(f'roster-{t}' for t in (event['home_team_id'],event['away_team_id']))}
    if type(selection['sources']) is not dict or set(selection['sources']) != expected_sources:
        raise IntegrityError('selection lacks exact initial source bindings')
    if type(selection['rosters']) is not dict or set(selection['rosters']) != {event['home_team_id'],event['away_team_id']}:
        raise IntegrityError('selection contains unrelated roster identities')
    for name,source in selection['sources'].items():
        _source_check(source,imported_at=declared)
        if source['source_id'] != name:
            raise IntegrityError('selection source identity conflicts')
        wanted = f"{BASE}/summary?event={event['event_id']}" if name=='summary' else f"{BASE}/teams/{name[7:]}/roster" if name.startswith('roster-') else None
        if wanted is not None and source['source_url'] != wanted:
            raise IntegrityError('selection source route conflicts with exact event/team')
        if name=='scoreboard' and route_date(source['source_url']) not in {date.fromisoformat(p['route_date']) for p in schedule['source_proofs']}:
            raise IntegrityError('selection scoreboard date is outside admitted inventory')
    return selection


def _validate_roster_facts(roster,team):
    if type(roster) is not list or not 2 <= len(roster) <= 100:
        raise IntegrityError("two bounded explicitly active roster players required")
    ids = []
    for player in roster:
        _exact(player,{'player_id','team_id','player_label'},'active roster player')
        _id(player['player_id'],'active player');ids.append(player['player_id'])
        if player['team_id'] != team or type(player['player_label']) is not str or not player['player_label'] or player['player_label'] != player['player_label'].strip():
            raise IntegrityError("roster player name/team conflicts")
    if ids != sorted(set(ids),key=int):
        raise IntegrityError("active roster facts must be unique sorted numeric identities")


def make_event_body(history_ref,schedule,selection,observations,*,mode='READINESS_DIAGNOSTIC'):
    imported = _now()
    event,rosters,proofs = _event_observations(schedule,observations,imported)
    _validate_selection(selection,event,schedule,rosters)
    ref = history_ref.to_record() if isinstance(history_ref,LedgerRef) else history_ref
    body = _seal({'schema_version':EVENT_SCHEMA,'study_id':STUDY_ID,'mode':_mode(mode),
        'study_date':schedule['study_date'],'event':event,'history_ref':deepcopy(ref),
        'schedule':deepcopy(schedule),'selection':deepcopy(selection),'candidates':deepcopy(selection['players']),
        'rosters':rosters,'sources':proofs,'imported_at':stamp(imported),
        'normalizer':{'version':NORMALIZER_VERSION,'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}},'sourcepack_id')
    return validate_event(body)


def validate_event(body, *, now=None):
    _exact(body,{'schema_version','study_id','mode','study_date','event','history_ref','schedule','selection','candidates','rosters','sources','imported_at','normalizer','sourcepack_id'},'event input')
    if body['schema_version'] != EVENT_SCHEMA or body['study_id'] != STUDY_ID:
        raise IntegrityError("unsupported PROS004 event input contract")
    _mode(body['mode']);_check_digest(body,'sourcepack_id')
    imported = _clock(body['imported_at'],'event import')
    if imported > utc(now if now is not None else _now()):
        raise IntegrityError("event normalization/import clock is in the future")
    ref = LedgerRef.from_record(body['history_ref'])
    if ref.kind != 'research_inputs':
        raise IntegrityError("event input must reference shared research history")
    validate_schedule(body['schedule'],now=now)
    if body['mode'] != body['schedule']['mode']:
        raise IntegrityError("schedule/event diagnostic evidence lanes differ")
    event = body['event']
    if type(event) is not dict:
        raise IntegrityError('event normalized facts must be an object')
    first = first_event(body['schedule'],now=now)
    if first is None or event.get('event_id') != first['event_id'] or event.get('event_version') != first['scheduled_event_version']:
        raise IntegrityError("event input is not the frozen first daily event")
    expected_event = {'id_namespace':'espn','league':'NBA','event_id':first['event_id'],
        'event_starts_at':first['event_starts_at'],'home_team_id':first['home_team_id'],
        'away_team_id':first['away_team_id'],'status':'PRE_GAME',
        'season_ending_year':first['season_ending_year'],'season_type':first['season_type'],
        'event_version':first['scheduled_event_version']}
    if event != expected_event or body['study_date'] != body['schedule']['study_date']:
        raise IntegrityError("event normalized identity/start/version/status conflicts")
    teams = (event['home_team_id'],event['away_team_id'])
    if type(body['rosters']) is not dict or set(body['rosters']) != set(teams):
        raise IntegrityError("current event needs exactly both roster proofs")
    for team in teams:_validate_roster_facts(body['rosters'][team],team)
    _validate_selection(body['selection'],event,body['schedule'],body['rosters'])
    if body['candidates'] != body['selection']['players']:
        raise IntegrityError("current cohort cannot be replaced or reordered")
    expected_sources = {'scoreboard','summary',*(f'roster-{t}' for t in teams)}
    if type(body['sources']) is not dict or set(body['sources']) != expected_sources:
        raise IntegrityError("current event inputs need all four source receipts")
    cutoff = utc(event['event_starts_at'])-timedelta(minutes=90)
    earliest = cutoff-timedelta(seconds=SOURCE_MAX_AGE_SECONDS)
    close = cutoff-timedelta(minutes=10)
    if imported > close or imported < earliest or imported < _clock(body['selection']['declared_at'],'selection declaration'):
        raise IntegrityError("event inputs must be imported after selection and by T90-minus10-minute selection close")
    for proof in body['schedule']['source_proofs']:
        if not earliest <= _clock(proof['source']['request_started_at'],'schedule request start') <= _clock(proof['source']['observed_at'],'schedule observation') <= close:
            raise IntegrityError('schedule observation is stale or follows selection close')
    for source in body['selection']['sources'].values():
        if not earliest <= _clock(source['request_started_at'],'selection request start') <= _clock(source['observed_at'],'selection source observation') <= close:
            raise IntegrityError('selection source observation is stale or follows selection close')
    for name,source in body['sources'].items():
        _source_check(source,imported_at=imported)
        if source['source_id'] != name:
            raise IntegrityError("current source identity conflicts")
        if not earliest <= _clock(source['request_started_at'],'current request start') <= _clock(source['observed_at'],'current source observation') <= close:
            raise IntegrityError("stale/future current event or roster observation")
        wanted = f"{BASE}/summary?event={event['event_id']}" if name=='summary' else f"{BASE}/teams/{name[7:]}/roster" if name.startswith('roster-') else None
        if wanted is not None and source['source_url'] != wanted:
            raise IntegrityError("current source route does not bind event/team")
        if name=='scoreboard' and route_date(source['source_url']) not in {date.fromisoformat(p['route_date']) for p in body['schedule']['source_proofs']}:
            raise IntegrityError('current scoreboard date is outside admitted inventory')
    _exact(body['normalizer'],{'version','code_sha256'},'event normalizer')
    if body['normalizer']['version'] != NORMALIZER_VERSION:
        raise IntegrityError("event normalizer version changed")
    _sha(body['normalizer']['code_sha256'],'event normalizer')
    if body['normalizer']['code_sha256'] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise IntegrityError('event normalizer source bytes differ from declared version')
    if len(canonical(body)) > MAX_EVENT_BODY_BYTES:
        raise IntegrityError("event pack exceeds complete-envelope reserved32KiB budget")
    return body


validate_history_body = validate_history
validate_event_body = validate_event

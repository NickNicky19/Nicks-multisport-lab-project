"""Bounded manual ESPN NBA inputs and lossless retained-history normalization.

The source pack binds derived research inputs to actual retained response bytes.
It does not grant source rights, automate collection, model participation, or
establish a timely forecast. The separate prospective producer owns admission.
"""
from __future__ import annotations

import argparse
from dataclasses import fields
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import stat
import urllib.request
from typing import Any, Mapping

from .integrity import canonical, digest, load_json, read_receipt, stamp, utc, write_receipt
from .nba_data import COUNT_FIELDS, NBAPlayerGame, audit_rows


SCHEMA = "nba-pregame-sourcepack-v1"
VERSION = "espn_nba_selected_inputs_v1"
HISTORY_SCHEMA = "nba-history-compact-v1"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_PACK_BYTES = 4 * 1024 * 1024
MAX_PANEL_BYTES = 64 * 1024 * 1024
MAX_HISTORY_ROWS = 100_000
MAX_HTTP_SECONDS = 30
RULE = "two_lowest_numeric_active_ids_per_current_event_team_v1"
PANEL_SHA = "489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c"
_ROW_FIELDS = {f.name for f in fields(NBAPlayerGame)}
_HISTORY_COLUMNS = ["event_index", "player_index", "team_id", "opponent_id", "minutes",
                    *COUNT_FIELDS, "final_periods"]
_HISTORY_CONSTANTS = {"id_namespace": "espn", "season_ending_year": 2026,
                      "season_type": "2", "participation": "APPEARED",
                      "minutes_precision": "rounded_whole_minutes", "final_status": "FINAL"}
_HISTORY_PROVENANCE_KEYS = {'normalized_panel_sha256','normalized_panel_bytes','normalized_panel_rows',
    'normalization_version','source_receipts','upstream_exclusions','availability_semantics',
    'source_receipts_sha256','cohort','current_season_history_claim','history_freshness','normalizer_source_sha256'}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _exact(value: Any, keys: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"{label} has unexpected or missing fields")
    return value


def _id(value: Any, label: str) -> str:
    if type(value) is not str or not re.fullmatch(r"[1-9][0-9]*", value):
        raise ValueError(f"{label} must be a positive numeric ESPN identifier")
    return value


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{label} must be a SHA256")
    return value


def _time(value: Any, label: str) -> datetime:
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", value):
        raise ValueError(f"{label} requires six-digit UTC microseconds")
    return utc(value)


def _decode(raw: bytes) -> dict:
    if type(raw) is not bytes or len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("source bytes exceed the declared source budget")
    def pairs(values):
        out = {}
        for key, value in values:
            if key in out:
                raise ValueError("duplicate source JSON key")
            out[key] = value
        return out
    body = json.loads(raw, object_pairs_hook=pairs)
    canonical(body)
    if type(body) is not dict:
        raise ValueError("source response must be an object")
    return body


def _event_facts(event: Mapping[str, Any], competition: Mapping[str, Any], *, season: dict) -> dict:
    event_id = _id(event.get("id"), "event ID")
    if _id(competition.get("id"), "competition ID") != event_id:
        raise ValueError("event and competition IDs conflict")
    start = stamp(utc(competition["date"]))
    if event.get("date") is not None and stamp(utc(event["date"])) != start:
        raise ValueError("event and competition start conflict")
    if event.get("timeValid") is not True and competition.get("timeValid") is not True:
        raise ValueError("event time is not explicitly valid")
    status = competition.get("status", event.get("status", {})).get("type", {})
    if (status.get("name"), status.get("state"), status.get("completed")) != ("STATUS_SCHEDULED", "pre", False):
        raise ValueError("event is not explicitly scheduled, pregame and incomplete")
    teams = {}
    competitors = competition.get("competitors")
    if type(competitors) is not list or len(competitors) != 2:
        raise ValueError("event requires exactly two competitors")
    for side in competitors:
        tid = _id(side.get("id"), "competitor ID")
        if tid != _id(side.get("team", {}).get("id"), "team ID") or not 1 <= int(tid) <= 30:
            raise ValueError("competitor/team identity conflict or nonstandard NBA team")
        if side.get("homeAway") not in {"home", "away"} or side["homeAway"] in teams:
            raise ValueError("event home/away identity conflict")
        teams[side["homeAway"]] = tid
    if teams["home"] == teams["away"]:
        raise ValueError("event teams must differ")
    year, kind = season.get("year"), season.get("type")
    if type(year) is not int or type(kind) is not int or year < 2026 or kind != 2:
        raise ValueError("selected pilot requires an explicit current regular-season NBA event")
    body = {"id_namespace": "espn", "league": "NBA", "event_id": event_id,
            "event_starts_at": start, "home_team_id": teams["home"], "away_team_id": teams["away"],
            "status": "PRE_GAME", "season_ending_year": year, "season_type": str(kind)}
    return {**body, "event_version": digest(body)}


def normalize_event(scoreboard_bytes: bytes, summary_bytes: bytes, event_id: str) -> dict:
    """Cross-check the complete selected event identity in two actual responses."""
    _id(event_id, "requested event ID")
    board, summary = _decode(scoreboard_bytes), _decode(summary_bytes)
    leagues=board.get('leagues')
    if type(leagues) is not list or len(leagues)!=1 or leagues[0].get('id')!='46' or leagues[0].get('abbreviation')!='NBA':
        raise ValueError("scoreboard does not explicitly identify the NBA league")
    matching = [event for event in board.get("events", []) if event.get("id") == event_id]
    if len(matching) != 1:
        raise ValueError("scoreboard must contain exactly one selected event")
    event = matching[0]
    if len(event.get("competitions", [])) != 1:
        raise ValueError("selected event must contain exactly one competition")
    first = _event_facts(event, event["competitions"][0], season=event.get("season", {}))
    header = summary.get("header", {})
    if header.get('uid')!=f's:40~l:46~e:{event_id}':
        raise ValueError("summary UID does not identify the exact ESPN NBA event")
    if len(header.get("competitions", [])) != 1:
        raise ValueError("summary must contain exactly one competition")
    second = _event_facts(header, header["competitions"][0], season=header.get("season", {}))
    if first != second:
        raise ValueError("scoreboard and summary event/version/start/teams/status conflict")
    return first


def normalize_roster(raw: bytes, team_id: str, *, season_ending_year: int) -> list[dict]:
    """Explicit source status means roster-active, never verified appearance."""
    _id(team_id, "requested team ID")
    body = _decode(raw)
    if body.get("team", {}).get("id") != team_id:
        raise ValueError("roster team does not match requested event team")
    if body.get("season", {}).get("year") != season_ending_year or body.get("season", {}).get("type") != 2:
        raise ValueError("roster season does not match current selected event")
    athletes = body.get("athletes")
    if type(athletes) is not list or not 2 <= len(athletes) <= 100:
        raise ValueError("roster has no bounded athlete list")
    seen, active = set(), []
    for athlete in athletes:
        pid = _id(athlete.get("id"), "athlete ID")
        if pid in seen:
            raise ValueError("duplicate roster athlete identity")
        seen.add(pid)
        supplied_team = athlete.get("team")
        if supplied_team is not None and supplied_team.get("id") != team_id:
            raise ValueError("athlete-level team conflicts with roster team")
        status = athlete.get("status")
        if type(status) is not dict or type(status.get("type")) is not str:
            raise ValueError("roster athlete status is missing")
        if athlete.get("active") is False and status["type"] == "active":
            raise ValueError("roster active flag conflicts with status type")
        if status["type"] != "active":
            continue
        label = athlete.get("displayName")
        if type(label) is not str or not label or label != label.strip():
            raise ValueError("active roster athlete needs an explicit display name")
        active.append({"player_id": pid, "team_id": team_id, "player_label": label})
    return sorted(active, key=lambda value: int(value["player_id"]))


def freeze_selection(event: dict, rosters: Mapping[str, list[dict]]) -> dict:
    """Freeze two lowest active IDs/team before any forecast or outcome inspection."""
    selected = []
    for team, opponent in [(event["home_team_id"], event["away_team_id"]),
                           (event["away_team_id"], event["home_team_id"])]:
        roster = sorted(rosters.get(team, []), key=lambda value:int(_id(value.get('player_id'),'roster player ID')))
        if len(roster) < 2:
            raise ValueError("selected team lacks two explicitly active named athlete IDs")
        selected.extend({**player, "opponent_id": opponent} for player in roster[:2])
    if len({p["player_id"] for p in selected}) != 4:
        raise ValueError("same player occurs on both event teams")
    return {"schema_version": "nba-pregame-selected-cohort-v1", "declared_at": stamp(_now()),
            "event_id": event["event_id"], "rule": RULE, "players": selected}


def verify_selection(event: dict, rosters: Mapping[str, list[dict]], selection: dict) -> list[dict]:
    _exact(selection, {"schema_version", "declared_at", "event_id", "rule", "players"}, "selection")
    if selection["schema_version"] != "nba-pregame-selected-cohort-v1" or selection["rule"] != RULE:
        raise ValueError("unknown frozen player selection")
    if selection["event_id"] != event["event_id"] or type(selection["players"]) is not list or len(selection["players"]) != 4:
        raise ValueError("selection event or cohort size conflicts")
    _time(selection["declared_at"], "selection declaration")
    seen, per_team, result = set(), {}, []
    for frozen in selection["players"]:
        _exact(frozen, {"player_id", "team_id", "opponent_id", "player_label"}, "selected player")
        _id(frozen["player_id"], "selected player ID")
        if type(frozen['player_label']) is not str or not frozen['player_label'] or frozen['player_label']!=frozen['player_label'].strip():
            raise ValueError("selected player requires a nonempty explicit source label")
        if frozen["player_id"] in seen:
            raise ValueError("duplicate selected player ID")
        seen.add(frozen["player_id"])
        team, opponent = frozen["team_id"], frozen["opponent_id"]
        if {team, opponent} != {event["home_team_id"], event["away_team_id"]}:
            raise ValueError("selected player teams conflict with current event")
        current = [p for p in rosters.get(team, []) if p["player_id"] == frozen["player_id"]]
        if len(current) != 1 or current[0]["player_label"] != frozen["player_label"]:
            raise ValueError("frozen selected player is missing, inactive, renamed or transferred; never reselect")
        per_team[team] = per_team.get(team, 0) + 1
        result.append(dict(frozen))
    if sorted(per_team.values()) != [2, 2]:
        raise ValueError("selection requires two players per current event team")
    return result


def compact_history(rows: list[NBAPlayerGame]) -> dict:
    if not rows or len(rows) > MAX_HISTORY_ROWS:
        raise ValueError("history cohort is empty or exceeds 100,000 rows")
    records = [row.to_record() for row in rows]
    for record in records:
        if any(record[key] != value for key, value in _HISTORY_CONSTANTS.items()):
            raise ValueError("history falls outside the explicitly retained 2026 cohort")
    events = sorted({(row.event_id, row.event_start.isoformat()) for row in rows})
    players = sorted({row.player_id for row in rows}, key=int)
    event_index, player_index = {item: i for i, item in enumerate(events)}, {item: i for i, item in enumerate(players)}
    return {"schema_version": HISTORY_SCHEMA, "columns": _HISTORY_COLUMNS,
            "events": [list(item) for item in events], "players": players,
            "constants": _HISTORY_CONSTANTS,
            "rows": [[event_index[(row.event_id, row.event_start.isoformat())], player_index[row.player_id],
                      *[record[column] for column in _HISTORY_COLUMNS[2:]]]
                     for row, record in zip(rows, records, strict=True)]}


def unpack_history(pack: dict) -> list[NBAPlayerGame]:
    """Losslessly recover every normalized row without source/network/model work."""
    history = pack.get("history", pack)
    _exact(history, {"schema_version", "columns", "events", "players", "constants", "rows"}, "compact history")
    if history["schema_version"] != HISTORY_SCHEMA or history["columns"] != _HISTORY_COLUMNS or history["constants"] != _HISTORY_CONSTANTS:
        raise ValueError("unknown compact history layout or cohort")
    events, players, values = history["events"], history["players"], history["rows"]
    if (type(events) is not list or type(players) is not list or type(values) is not list
            or not 1 <= len(values) <= MAX_HISTORY_ROWS or not 1 <= len(events) <= MAX_HISTORY_ROWS
            or not 1 <= len(players) <= MAX_HISTORY_ROWS):
        raise ValueError("compact history dictionaries or row count exceed budget")
    for player in players:
        _id(player, "historical player ID")
    for event in events:
        if type(event) is not list or len(event) != 2:
            raise ValueError("historical event dictionary row is malformed")
        _id(event[0], "historical event ID")
        utc(event[1])
    if len(set(players)) != len(players) or len({tuple(x) for x in events}) != len(events) or len({x[0] for x in events}) != len(events):
        raise ValueError("compact history dictionaries repeat identities")
    rows = []
    for value in values:
        if type(value) is not list or len(value) != len(_HISTORY_COLUMNS):
            raise ValueError("compact history row width conflicts")
        ei, pi = value[:2]
        if type(ei) is not int or type(pi) is not int or not 0 <= ei < len(events) or not 0 <= pi < len(players):
            raise ValueError("compact history dictionary index is invalid")
        body = {**_HISTORY_CONSTANTS, "event_id": events[ei][0], "event_start": events[ei][1],
                "player_id": players[pi], **dict(zip(_HISTORY_COLUMNS[2:], value[2:], strict=True))}
        rows.append(NBAPlayerGame(**body))
    audit = audit_rows(rows, max_rows=MAX_HISTORY_ROWS)
    if audit["duplicate_event_player_rows"] or audit["identity_failures"]:
        raise ValueError("compact history has duplicate identities or count contradictions")
    return rows


def _panel_bytes(rows: list[NBAPlayerGame]) -> bytes:
    raw = b"".join((json.dumps(row.to_record(), allow_nan=False) + "\n").encode() for row in rows)
    if len(raw) > MAX_PANEL_BYTES:
        raise ValueError("history exceeds 64 MiB normalized-byte budget")
    return raw


def rebuild_history(player_path: Path, schedule_path: Path, panel_path: Path, source_receipts_path: Path) -> tuple[dict, dict]:
    """Rebuild all retained appearances from their original two Parquet assets."""
    from scripts.prepare_nba_panel import prepare_panel, read_parquet
    receipt_body = load_json(source_receipts_path)
    sources = {r["key"]: r for r in receipt_body["receipts"]}
    player_rows, player_asset = read_parquet(player_path)
    schedule_rows, schedule_asset = read_parquet(schedule_path)
    bindings = []
    for key, asset in [("sdv_player_box_2026", player_asset), ("sdv_schedule_2026", schedule_asset)]:
        original = sources[key]
        if asset["sha256"] != original["sha256"] or asset["bytes"] != original["bytes"]:
            raise ValueError("original source asset bytes conflict with retained receipt")
        bindings.append({"source_id": key, "source_url": original["url"], "raw_sha256": original["sha256"],
                         "raw_bytes": original["bytes"], "observed_at": stamp(utc(original["observed_at"])),
                         "source_updated_at": stamp(utc(original["source_updated_at"])) if original["source_updated_at"] else None,
                         "source_version": "github-asset:" + str(original["github_asset_id"])})
    rows, report = prepare_panel(player_rows, schedule_rows)
    raw = _panel_bytes(rows)
    if not stat.S_ISREG(panel_path.lstat().st_mode) or panel_path.stat().st_size > MAX_PANEL_BYTES:
        raise ValueError("retained normalized panel is not a bounded regular file")
    original_panel = panel_path.read_bytes()
    if raw != original_panel or hashlib.sha256(raw).hexdigest() != PANEL_SHA:
        raise ValueError("source-normalized history does not reproduce the exact frozen full panel")
    compact = compact_history(rows)
    if _panel_bytes(unpack_history(compact)) != raw:
        raise ValueError("compact history roundtrip changed original normalized input")
    return compact, {"normalized_panel_sha256": hashlib.sha256(raw).hexdigest(),
                     "normalized_panel_bytes": len(raw), "normalized_panel_rows": len(rows),
                     "normalization_version": "nba-panel-preparation-v1", "source_receipts": bindings,
                     "upstream_exclusions": report["upstream_exclusions"],
                     "availability_semantics": "observed archive before future freeze; original historical completion bounds remain reconstructed",
                     "source_receipts_sha256": hashlib.sha256(source_receipts_path.read_bytes()).hexdigest(),
                     "cohort": "all retained complete APPEARED FINAL source-stage2 standard-team rows; no truncation",
                     "current_season_history_claim": False, "history_freshness": "latest event 2026-04-13; no 2026-27 appearances",
                     "normalizer_source_sha256": hashlib.sha256(Path(__file__).resolve().parents[1].joinpath('scripts/prepare_nba_panel.py').read_bytes()).hexdigest()}


def capture_espn(event_id: str, date: str, raw_directory: Path) -> tuple[dict, dict[str, list[dict]], list[dict]]:
    """Four bounded manual HTTP reads; no scheduling, retries or forecast call."""
    _id(event_id, "event ID")
    if not re.fullmatch(r"\d{8}", date):
        raise ValueError("scoreboard date requires YYYYMMDD")
    raw_directory.mkdir(parents=True, exist_ok=True)
    raw_directory = raw_directory.resolve()
    root = Path(__file__).resolve().parents[1]
    if not raw_directory.is_relative_to(root / ".local-data") and not raw_directory.is_relative_to(Path('/tmp')):
        raise ValueError("raw sources must remain under ignored .local-data or /tmp")
    captured = []
    bodies = {}
    def fetch(key, url):
        started = _now()
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "NicksMultisportLab/manual-research"}), timeout=MAX_HTTP_SECONDS) as response:
            raw = response.read(MAX_SOURCE_BYTES + 1)
            status, headers = response.status, dict(response.headers)
        completed = _now()
        if (completed - started).total_seconds() > MAX_HTTP_SECONDS:
            raise ValueError("source read exceeded the 30-second operation budget")
        body = _decode(raw)
        if status != 200:
            raise ValueError("source returned non-200 status")
        checksum = hashlib.sha256(raw).hexdigest()
        path = raw_directory / f"{key}-{checksum}.raw"
        if path.exists():
            if path.read_bytes() != raw:
                raise ValueError("existing raw capture conflicts")
        else:
            with path.open('xb') as handle:
                handle.write(raw)
        generated = body.get("timestamp") if key.startswith("roster-") else None
        if generated is not None:
            try:
                generated = stamp(utc(generated))
            except (TypeError, ValueError):
                raise ValueError("source response timestamp is malformed")
        metadata = {"source_id": key, "source_url": url, "request_started_at": stamp(started),
                    "observed_at": stamp(completed), "response_completed_at": stamp(completed),
                    "source_updated_at": None, "source_response_generated_at": generated,
                    "raw_sha256": checksum, "raw_bytes": len(raw), "http_status": status,
                    "http_date": headers.get('Date'), "etag": headers.get('ETag'), "last_modified": headers.get('Last-Modified')}
        write_receipt(raw_directory / f"{key}-{stamp(completed).replace(':','')}-{checksum}.capture.json", metadata)
        captured.append(metadata)
        bodies[key] = raw
        return raw
    base = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
    scoreboard = fetch('scoreboard', f'{base}/scoreboard?dates={date}')
    summary = fetch('summary', f'{base}/summary?event={event_id}')
    event = normalize_event(scoreboard, summary, event_id)
    rosters = {}
    for team in [event['home_team_id'], event['away_team_id']]:
        rosters[team] = normalize_roster(fetch(f'roster-{team}', f'{base}/teams/{team}/roster'), team,
                                       season_ending_year=event['season_ending_year'])
    return event, rosters, captured


def make_pack(event: dict, rosters: Mapping[str, list[dict]], captures: list[dict], selection: dict,
              history: dict, history_provenance: dict) -> dict:
    candidates = verify_selection(event, rosters, selection)
    body = {"schema_version": SCHEMA, "normalizer": {"version": VERSION,
            "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            "imported_at": stamp(_now()), "event": event, "selection": selection,
            "candidates": candidates, "sources": captures, "history": history,
            "history_provenance": history_provenance}
    pack = {**body, "sourcepack_id": digest(body)}
    return validate_pack(pack)


def sourcepack_digest(pack: dict) -> str:
    return digest({key: value for key, value in pack.items() if key != 'sourcepack_id'})


def validate_pack(pack: dict) -> dict:
    _exact(pack, {'schema_version', 'sourcepack_id', 'normalizer', 'imported_at', 'event',
                  'selection', 'candidates', 'sources', 'history', 'history_provenance'}, 'source pack')
    if pack['schema_version'] != SCHEMA or pack['sourcepack_id'] != sourcepack_digest(pack):
        raise ValueError("source pack schema or checksum conflict")
    if len(canonical(pack)) > MAX_PACK_BYTES - 1024:
        raise ValueError("source pack exceeds 4 MiB durable-record budget")
    normalizer = _exact(pack['normalizer'], {'version', 'code_sha256'}, 'normalizer')
    if normalizer['version'] != VERSION:
        raise ValueError("unsupported normalizer version")
    _sha(normalizer['code_sha256'], 'normalizer code hash')
    imported = _time(pack['imported_at'], 'import clock')
    if imported > _now():
        raise ValueError("import clock is in the future")
    event = _exact(pack['event'], {'id_namespace','league','event_id','event_version','event_starts_at',
                                 'home_team_id','away_team_id','status','season_ending_year','season_type'}, 'event')
    if (event['id_namespace'],event['league'],event['status'],event['season_type']) != ('espn','NBA','PRE_GAME','2'):
        raise ValueError("source pack requires a standard explicitly pregame ESPN NBA event")
    _id(event['event_id'],'event ID')
    for side in ['home_team_id','away_team_id']:
        if not 1 <= int(_id(event[side],side)) <= 30:
            raise ValueError("nonstandard NBA event team")
    if event['home_team_id']==event['away_team_id']:
        raise ValueError("event teams must differ")
    _time(event['event_starts_at'],'event start')
    if event['event_version'] != digest({k:v for k,v in event.items() if k!='event_version'}):
        raise ValueError("normalized event version conflict")
    if type(event['season_ending_year']) is not int or event['season_ending_year'] < 2026:
        raise ValueError("event season missing")
    # Recovered packs retain original facts even after event start. Actual current
    # event freshness and issuance window are enforced only by the live issuer.
    expected_ids={'scoreboard','summary',f"roster-{event['home_team_id']}",f"roster-{event['away_team_id']}"}
    if type(pack['sources']) is not list or len(pack['sources']) != 4 or {s.get('source_id') for s in pack['sources']} != expected_ids:
        raise ValueError("source pack requires scoreboard, summary and both current event team rosters")
    for source in pack['sources']:
        _exact(source,{'source_id','source_url','request_started_at','observed_at','response_completed_at',
                       'source_updated_at','source_response_generated_at','raw_sha256','raw_bytes','http_status',
                       'http_date','etag','last_modified'},'source reference')
        started,observed,completed=[_time(source[k],k) for k in ['request_started_at','observed_at','response_completed_at']]
        if not started <= observed == completed <= imported or (completed-started).total_seconds()>MAX_HTTP_SECONDS:
            raise ValueError("source observation/response/import chronology or operation latency conflicts")
        if source['source_updated_at'] is not None:
            if _time(source['source_updated_at'],'source update')>observed:
                raise ValueError("source update occurs after source observation")
        if source['source_response_generated_at'] is not None:
            if _time(source['source_response_generated_at'],'response generation')>observed:
                raise ValueError("source response timestamp occurs after its observation")
        _sha(source['raw_sha256'],'raw source hash')
        if type(source['http_status']) is not int or source['http_status'] != 200 or type(source['raw_bytes']) is not int or not 0<source['raw_bytes']<=MAX_SOURCE_BYTES:
            raise ValueError("invalid source status or byte budget")
        base='https://site.api.espn.com/apis/site/v2/sports/basketball/nba'
        key=source['source_id']
        if key=='summary': expected=f"{base}/summary?event={event['event_id']}"
        elif key.startswith('roster-'):expected=f"{base}/teams/{key[7:]}/roster"
        else:
            expected=source['source_url']
            if not re.fullmatch(re.escape(base)+r'/scoreboard\?dates=\d{8}',expected):
                raise ValueError("unexpected scoreboard source route")
        if source['source_url']!=expected:
            raise ValueError("source URL conflicts with exact normalized identity")
    selected=pack['selection']
    # The durable candidate facts equal the frozen cohort; no silent reselection.
    if type(pack['candidates']) is not list or len(pack['candidates'])!=4:
        raise ValueError("selected candidate coverage requires exactly four players")
    for candidate in pack['candidates']:
        _exact(candidate,{'player_id','team_id','opponent_id','player_label'},'candidate')
    fake_rosters={team:[{k:v for k,v in p.items() if k!='opponent_id'} for p in pack['candidates'] if p['team_id']==team]
                  for team in [event['home_team_id'],event['away_team_id']]}
    if verify_selection(event,fake_rosters,selected)!=pack['candidates']:
        raise ValueError("candidate identities conflict with fixed selection")
    if _time(selected['declared_at'],'selection declaration')>imported:
        raise ValueError("selection declaration follows pack import")
    rows=unpack_history(pack)
    raw=_panel_bytes(rows)
    provenance=_exact(pack['history_provenance'],_HISTORY_PROVENANCE_KEYS,'history provenance')
    for name in ['normalized_panel_bytes','normalized_panel_rows']:
        if type(provenance[name]) is not int or provenance[name]<=0:
            raise ValueError("history panel accounting needs positive true integers")
    if (provenance.get('normalized_panel_sha256')!=hashlib.sha256(raw).hexdigest()
            or provenance.get('normalized_panel_sha256')!=PANEL_SHA
            or provenance.get('normalized_panel_bytes')!=len(raw)
            or provenance.get('normalized_panel_rows')!=len(rows)):
        raise ValueError("lossless normalized history does not match exact panel reference")
    if provenance['normalization_version']!='nba-panel-preparation-v1' or provenance['current_season_history_claim'] is not False:
        raise ValueError("history normalization or current-season claim conflicts")
    original_receipts=Path(__file__).resolve().parents[1]/'evidence/data/2026-10-19-source-receipts.json'
    if provenance['source_receipts_sha256']!=hashlib.sha256(original_receipts.read_bytes()).hexdigest():
        raise ValueError("history original receipt reference conflicts")
    originals={item['key']:item for item in load_json(original_receipts)['receipts']}
    if type(provenance['source_receipts']) is not list or len(provenance['source_receipts'])!=2:
        raise ValueError("history requires both original player and schedule source bindings")
    expected=[]
    for key in ['sdv_player_box_2026','sdv_schedule_2026']:
        source=originals[key]
        expected.append({'source_id':key,'source_url':source['url'],'raw_sha256':source['sha256'],
                         'raw_bytes':source['bytes'],'observed_at':stamp(utc(source['observed_at'])),
                         'source_updated_at':stamp(utc(source['source_updated_at'])) if source['source_updated_at'] else None,
                         'source_version':'github-asset:'+str(source['github_asset_id'])})
    if provenance['source_receipts']!=expected:
        raise ValueError("history source hash/version/observation/update binding conflicts")
    for source in provenance['source_receipts']:
        observed=_time(source['observed_at'],'historical observation')
        updated=_time(source['source_updated_at'],'historical source update') if source['source_updated_at'] else None
        if observed>imported or (updated is not None and updated>observed):
            raise ValueError("historical source update/observation/import chronology conflicts")
    exclusions=_exact(provenance['upstream_exclusions'],{'normalization_rejected','normalization_rejection_reasons',
        'schedule_join_rejected','schedule_join_rejection_reasons','cohort_exclusion_precedence',
        'cohort_exclusion_counts','total_excluded_rows'},'upstream history exclusions')
    for key in ['normalization_rejected','schedule_join_rejected','total_excluded_rows']:
        if type(exclusions[key]) is not int or exclusions[key]<0:
            raise ValueError("history exclusions need nonnegative true integer counts")
    for key in ['normalization_rejection_reasons','schedule_join_rejection_reasons','cohort_exclusion_counts']:
        if type(exclusions[key]) is not dict or any(type(k) is not str or not k or type(v) is not int or v<0 for k,v in exclusions[key].items()):
            raise ValueError("history exclusion reasons need explicit nonnegative counts")
    if (sum(exclusions['normalization_rejection_reasons'].values())!=exclusions['normalization_rejected']
            or sum(exclusions['schedule_join_rejection_reasons'].values())!=exclusions['schedule_join_rejected']
            or exclusions['total_excluded_rows']!=exclusions['normalization_rejected']+exclusions['schedule_join_rejected']+sum(exclusions['cohort_exclusion_counts'].values())):
        raise ValueError("upstream history exclusion accounting conflicts")
    if type(exclusions['cohort_exclusion_precedence']) is not list or not exclusions['cohort_exclusion_precedence'] or any(type(x) is not str or not x for x in exclusions['cohort_exclusion_precedence']):
        raise ValueError("history exclusion precedence must be explicit")
    _sha(provenance['normalizer_source_sha256'],'panel normalizer source hash')
    return pack


def load_pack(path: Path | str) -> dict:
    return validate_pack(read_receipt(path,max_bytes=MAX_PACK_BYTES))


def history_from_input_record(record_id: str, *, repository_root: Path | str | None = None) -> tuple[dict, dict]:
    """Recover the original full input cohort from a checked durable ledger ref.

    This performs no HTTP, Parquet import, capture, normalization-clock rewrite or
    model generation. An explicit record ID identifies exactly one original pack.
    """
    from .ledger import Ledger, LedgerRef, MAX_RECORD_BYTES
    _sha(record_id, 'history research input record ID')
    store=Ledger(repository_root)
    path=store._path('research_inputs',record_id)
    payload=read_receipt(path,max_bytes=MAX_RECORD_BYTES)
    reference=LedgerRef('research_inputs',record_id,digest(payload))
    saved=store.read(reference)
    pack=validate_pack(saved['data']['source_pack'])
    # Lossless validation above compares all rows to the pinned full-panel hash;
    # original history observations/updates and exclusions remain unchanged.
    return pack['history'],pack['history_provenance']


def binding_view(pack: dict) -> dict:
    """Small shared producer/ledger view; retains independent source clocks."""
    validate_pack(pack)
    event=pack['event']
    observations=[s['observed_at'] for s in pack['sources']]
    history_observations=[s['observed_at'] for s in pack['history_provenance']['source_receipts']]
    return {'event':{key:event[key] for key in ['event_id','event_version','event_starts_at','home_team_id','away_team_id']},
            'candidates':pack['candidates'],'selection_sha256':digest(pack['selection']),
            'source_observed_min_at':min(observations),'source_observed_max_at':max(observations),
            'imported_at':pack['imported_at'],'history_rows':len(pack['history']['rows']),
            'history_latest_event_at':stamp(max(utc(e[1]) for e in pack['history']['events'])),
            'history_source_observed_max_at':max(history_observations),'pack_sha256':sourcepack_digest(pack)}


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    capture=sub.add_parser('capture',help='bounded manual source reads; no prospective forecast issuance')
    capture.add_argument('--event',required=True)
    capture.add_argument('--date',required=True)
    capture.add_argument('--selection',type=Path,required=True)
    history_choice=capture.add_mutually_exclusive_group(required=True)
    history_choice.add_argument('--history-input-record-id',help='exact committed research_inputs ledger record; no Parquet dependency')
    history_choice.add_argument('--history-panel',type=Path)
    capture.add_argument('--players',type=Path)
    capture.add_argument('--schedule',type=Path)
    capture.add_argument('--source-receipts',type=Path)
    capture.add_argument('--raw-directory',type=Path,required=True)
    capture.add_argument('--output',type=Path,required=True)
    check=sub.add_parser('check',help='offline readback/normalization; no capture or issuance')
    check.add_argument('pack',type=Path)
    args=parser.parse_args()
    try:
        if args.command=='check':pack=load_pack(args.pack)
        else:
            selection=read_receipt(args.selection)
            raw_inputs=[args.players,args.schedule,args.source_receipts]
            if args.history_input_record_id is not None:
                if any(value is not None for value in raw_inputs):
                    raise ValueError('history input record cannot be combined with raw history arguments')
                history,provenance=history_from_input_record(args.history_input_record_id)
            else:
                if not all(value is not None for value in raw_inputs):
                    raise ValueError('raw history route requires --history-panel, --players, --schedule and --source-receipts')
                history,provenance=rebuild_history(args.players,args.schedule,args.history_panel,args.source_receipts)
            event,rosters,sources=capture_espn(args.event,args.date,args.raw_directory)
            pack=make_pack(event,rosters,sources,selection,history,provenance)
            write_receipt(args.output,pack,max_bytes=MAX_PACK_BYTES)
        print(json.dumps({'sourcepack_id':pack['sourcepack_id'],'event':pack['event'],
                          'candidates':pack['candidates'],'sources':pack['sources'],
                          'history_rows':len(pack['history']['rows']),'compact_history_bytes':len(canonical(pack['history'])),
                          'imported_at':pack['imported_at'],'future_issuance':False,
                          'qualification':'UNAVAILABLE'},indent=2))
    except (OSError,ValueError,TypeError,KeyError) as error:
        parser.error(str(error))


if __name__=='__main__':main()

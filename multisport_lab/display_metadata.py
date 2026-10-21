"""Source-backed display facts, separate from immutable research records.

No model, capture, issue, price or settlement operation exists in this module.
Names and historical matchups are checked against bounded archived boxscore
excerpts; source observations are display verification, never pregame inputs.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from .integrity import IntegrityError, canonical, digest, load_json, stamp, utc

CATALOG_SCHEMA = 'nba-display-catalog-v1'
ASSET_SCHEMA = 'multisport-display-metadata-v1'
STATUS_SCHEMA = 'multisport-display-status-v1'
MAX_BYTES = 128 * 1024
SHA = re.compile(r'[a-f0-9]{64}')
CATALOG_PATH = 'config/display_metadata_nba_v1.json'


def require(ok, message):
    if not ok:
        raise IntegrityError(message)


def exact(value, fields, label):
    require(type(value) is dict and set(value) == set(fields), 'Invalid display '+label)


def text(value):
    return type(value) is str and 0 < len(value) <= 200 and value.strip() == value


def clock(value):
    require(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z', value), 'Display clocks require microsecond UTC')
    return utc(value)


def identity(row, key):
    require(row.get('league') == 'NBA' and row.get('id_namespace') == 'espn' and text(row.get(key)), 'Unsupported display identity/namespace')
    return (row['league'], row['id_namespace'], row[key])


def seal(row, key):
    require(type(row.get(key)) is str and SHA.fullmatch(row[key]) and row[key] == digest({k:v for k,v in row.items() if k != key}), 'Display content checksum mismatch')


def validate_catalog(catalog, *, now):
    exact(catalog, {'schema_version','verified_at','sources','players','events','appearances','catalog_id'}, 'catalog')
    seal(catalog,'catalog_id')
    require(catalog['schema_version'] == CATALOG_SCHEMA and clock(catalog['verified_at']) <= utc(now), 'Unsupported/future display catalog')
    require(all(type(catalog[k]) is list and len(catalog[k]) <= limit for k,limit in [('sources',64),('players',128),('events',64),('appearances',256)]), 'Display catalog exceeds collection bounds')
    sources={}
    for source in catalog['sources']:
        exact(source, {'source_id','league','id_namespace','event_id','source_url','kind','request_started_at','observed_at','source_updated_at','http_status','raw_sha256','raw_bytes','facts'}, 'source')
        key=identity(source,'event_id')
        require(text(source['source_id']) and source['source_id'] not in sources and source['kind'] == 'ARCHIVED_EVENT_BOXSCORE'
            and source['source_url'] == 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event='+source['event_id']
            and type(source['http_status']) is int and source['http_status']==200 and type(source['raw_bytes']) is int and 0<source['raw_bytes']<=3*1024*1024
            and type(source['raw_sha256']) is str and SHA.fullmatch(source['raw_sha256']), 'Invalid display source evidence')
        require(clock(source['request_started_at']) <= clock(source['observed_at']) <= clock(catalog['verified_at'])
            and (source['source_updated_at'] is None or clock(source['source_updated_at']) <= clock(source['observed_at'])), 'Display source clocks conflict')
        facts=source['facts'];exact(facts, {'event_id','event_starts_at','status','teams','players'}, 'source facts')
        require(facts['event_id']==source['event_id'] and facts['status']=='FINAL' and clock(facts['event_starts_at']) < clock(source['observed_at']), 'Display source is not the archived event')
        require(type(facts['teams']) is list and len(facts['teams'])==2 and type(facts['players']) is list and 0<len(facts['players'])<=128, 'Invalid display source fact coverage')
        teams={};players={}
        for team in facts['teams']:
            exact(team, {'team_id','display_name','abbreviation','home_away'}, 'source team')
            require(all(text(team[k]) for k in ('team_id','display_name','abbreviation')) and team['home_away'] in {'home','away'} and team['team_id'] not in teams, 'Invalid source team identity')
            teams[team['team_id']]=team
        require({t['home_away'] for t in teams.values()}=={'home','away'}, 'Historical home/away roles conflict')
        for player in facts['players']:
            exact(player, {'player_id','display_name','team_id'}, 'source player')
            require(text(player['player_id']) and text(player['display_name']) and player['team_id'] in teams and player['player_id'] not in players, 'Invalid source player membership')
            players[player['player_id']]=player
        sources[source['source_id']]={'source':source,'key':key,'teams':teams,'players':players}
    def evidence(row):
        ids=row['source_ids']
        require(type(ids) is list and 0<len(ids)<=8 and all(type(i) is str and i in sources for i in ids) and len(set(ids))==len(ids), 'Missing/duplicate display source reference')
        return [sources[i] for i in ids]
    players={};events={};appearances=set()
    for row in catalog['players']:
        exact(row, {'league','id_namespace','player_id','display_name','source_ids'}, 'player')
        key=identity(row,'player_id');require(key not in players and text(row['display_name']), 'Duplicate/invalid display player')
        require(all(s['key'][:2]==key[:2] and s['players'].get(row['player_id'],{}).get('display_name')==row['display_name'] for s in evidence(row)), 'Display player name lacks matching source identity')
        players[key]=row
    for row in catalog['events']:
        exact(row, {'league','id_namespace','event_id','event_starts_at','teams','source_ids'}, 'event')
        key=identity(row,'event_id');require(key not in events, 'Duplicate display event')
        require(all(s['key']==key and s['source']['facts']['event_starts_at']==row['event_starts_at'] and s['source']['facts']['teams']==row['teams'] for s in evidence(row)), 'Display event/date/matchup conflicts with source')
        events[key]=row
    for row in catalog['appearances']:
        exact(row, {'league','id_namespace','event_id','player_id','team_id','opponent_id','source_ids'}, 'appearance')
        require(text(row['player_id']), 'Invalid historical player identity')
        key=identity(row,'event_id')+(row['player_id'],)
        require(key not in appearances and key[:3] in events and key[:2]+(row['player_id'],) in players, 'Duplicate/unknown historical appearance')
        require(all(s['key']==key[:3] and s['players'].get(row['player_id'],{}).get('team_id')==row['team_id']
            and row['opponent_id'] in s['teams'] and row['team_id']!=row['opponent_id'] for s in evidence(row)), 'Historical player/team/opponent conflicts with archived boxscore')
        appearances.add(key)
    require(len(canonical(catalog))<=MAX_BYTES, 'Display catalog exceeds byte budget')
    return catalog


def validate_targets(catalog, sports):
    """Missing metadata permits an explicit ID fallback; conflicting facts reject."""
    events={(r['league'],r['id_namespace'],r['event_id']):r for r in catalog['events']}
    appearances={(r['league'],r['id_namespace'],r['event_id'],r['player_id']):r for r in catalog['appearances']}
    for sport in sports:
        for row in sport['forecasts']:
            key=(row['league'],row['id_namespace'],row['event_id'])
            event=events.get(key);appearance=appearances.get(key+(row['player_id'],))
            if event is not None:
                require(event['event_starts_at']==row['event_starts_at'] and {t['team_id'] for t in event['teams']}=={row['team_id'],row['opponent_id']}, 'Display metadata conflicts with immutable forecast event')
            if appearance is not None:
                require(all(appearance[k]==row[k] for k in ('team_id','opponent_id')), 'Display metadata changes immutable historical membership')


def verify_archived_source(raw, source):
    """Independently compare each safe display fact with its exact response bytes."""
    import json
    require(type(raw) is bytes and len(raw)==source['raw_bytes'] and hashlib.sha256(raw).hexdigest()==source['raw_sha256'], 'Archived display source bytes changed')
    try:
        def unambiguous(pairs):
            value={}
            for key,item in pairs:
                require(key not in value, 'Ambiguous archived display source key')
                value[key]=item
            return value
        def nonfinite(_value):
            raise IntegrityError('Nonfinite archived display source')
        body=json.loads(raw,object_pairs_hook=unambiguous,parse_constant=nonfinite)
        header=body['header'];competitions=header['competitions']
        require(header['id']==source['event_id'] and header['uid']=='s:40~l:46~e:'+source['event_id']
            and type(competitions) is list and len(competitions)==1, 'Archived display event/league is inconsistent')
        event=competitions[0]
        require(event['id']==source['event_id'] and event['status']['type']['completed'] is True
            and event['status']['type']['state']=='post', 'Archived display event is not verified final')
        teams=[{'team_id':r['team']['id'],'display_name':r['team']['displayName'],
                'abbreviation':r['team']['abbreviation'],'home_away':r['homeAway']} for r in event['competitors']]
        selected={r['player_id'] for r in source['facts']['players']}
        players=[]
        for team in body['boxscore']['players']:
            for group in team['statistics']:
                for entry in group['athletes']:
                    player=entry['athlete']
                    if player['id'] in selected:
                        players.append({'player_id':player['id'],'display_name':player['displayName'],'team_id':team['team']['id']})
        facts={'event_id':event['id'],'event_starts_at':stamp(utc(event['date'])),'status':'FINAL','teams':teams,'players':players}
        require(facts==source['facts'], 'Display fact excerpt differs from exact archived response')
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, IntegrityError):raise
        raise IntegrityError('Malformed archived display source') from error
    return {'event_id':source['event_id'],'verified_players':len(players),'verified_teams':len(teams),'raw_sha256':source['raw_sha256']}


def status_for(root, sports, *, now):
    from .ledger import LedgerRef
    from .publication_ledger import CompositeEnvelopeLedger
    ledger=CompositeEnvelopeLedger(root);index=ledger.scan();latest=None
    for record_id,payload in index['research_inputs'].items():
        pack=payload['data'].get('source_pack')
        if pack is None:continue
        successful=[s for s in pack['sources'] if s['http_status']==200]
        if not successful:continue
        observed=max(s['observed_at'] for s in successful)
        candidate={'observed_at':observed,'imported_at':pack['imported_at'],
            'record_ref':LedgerRef('research_inputs',record_id,digest(payload)).to_record(),
            'meaning':'RETAINED_INPUT_PREPARATION_TIMELINESS_NOT_ESTABLISHED'}
        if latest is None or clock(observed)>clock(latest['observed_at']):latest=candidate
    forecasts=[r for s in sports for r in s['forecasts']]
    captured=[r for r in forecasts if r['evidence_lane']=='REAL_TIME_CAPTURED']
    return {'schema_version':STATUS_SCHEMA,'generated_at':stamp(utc(now)),
        'counts':{'forecasts':len(forecasts),'reconstructed_forecasts':sum(r['evidence_lane']=='RECONSTRUCTED_RESEARCH' for r in forecasts),
            'captured_forecasts':len(captured),'upcoming_forecasts':sum(utc(r['event_starts_at'])>utc(now) for r in captured),
            'forecast_grades':sum(len(s['performance']) for s in sports),'offers':sum(len(s['offers']) for s in sports),
            'qualified_tickets':sum(len(s['tickets']) for s in sports)},
        'latest_retained_input_capture':latest,'last_genuine_issued_at':max((r['issued_at'] for r in captured),default=None)}


def validate_status(status, sports, *, generated_at):
    from .ledger import LedgerRef
    exact(status, {'schema_version','generated_at','counts','latest_retained_input_capture','last_genuine_issued_at'}, 'status')
    require(status['schema_version']==STATUS_SCHEMA and status['generated_at']==generated_at, 'Display status generation differs')
    counts=status['counts'];exact(counts, {'forecasts','reconstructed_forecasts','captured_forecasts','upcoming_forecasts','forecast_grades','offers','qualified_tickets'}, 'status counts')
    require(all(type(n) is int and 0<=n<=512 for n in counts.values()), 'Invalid display counts')
    forecasts=[r for s in sports for r in s['forecasts']];captured=[r for r in forecasts if r['evidence_lane']=='REAL_TIME_CAPTURED']
    expected={'forecasts':len(forecasts),'reconstructed_forecasts':sum(r['evidence_lane']=='RECONSTRUCTED_RESEARCH' for r in forecasts),'captured_forecasts':len(captured),
        'upcoming_forecasts':sum(utc(r['event_starts_at'])>clock(generated_at) for r in captured),'forecast_grades':sum(len(s['performance']) for s in sports),
        'offers':sum(len(s['offers']) for s in sports),'qualified_tickets':sum(len(s['tickets']) for s in sports)}
    require(counts==expected and status['last_genuine_issued_at']==max((r['issued_at'] for r in captured),default=None), 'Display counts/genuine issuance disagree with retained forecasts')
    if status['last_genuine_issued_at'] is not None:require(clock(status['last_genuine_issued_at'])<=clock(generated_at), 'Future genuine issuance clock')
    capture=status['latest_retained_input_capture']
    if capture is not None:
        exact(capture, {'observed_at','imported_at','record_ref','meaning'}, 'retained capture')
        require(LedgerRef.from_record(capture['record_ref']).kind=='research_inputs' and capture['meaning']=='RETAINED_INPUT_PREPARATION_TIMELINESS_NOT_ESTABLISHED'
            and clock(capture['observed_at'])<=clock(capture['imported_at'])<=clock(generated_at), 'Retained capture clocks/meaning conflict')
    return status


def make_asset(root, sports, *, now):
    catalog=validate_catalog(load_json(Path(root)/CATALOG_PATH,max_bytes=MAX_BYTES),now=now)
    validate_targets(catalog,sports)
    asset={'schema_version':ASSET_SCHEMA,'generated_at':stamp(utc(now)),'catalog':catalog,'status':status_for(root,sports,now=now)}
    asset['metadata_id']=digest(asset)
    validate_asset(asset,sports,now=now)
    return asset


def validate_asset(asset, sports, *, now):
    exact(asset, {'schema_version','generated_at','catalog','status','metadata_id'}, 'asset');seal(asset,'metadata_id')
    require(asset['schema_version']==ASSET_SCHEMA and clock(asset['generated_at'])<=utc(now), 'Unsupported/future display asset')
    validate_catalog(asset['catalog'],now=clock(asset['generated_at']));validate_targets(asset['catalog'],sports)
    validate_status(asset['status'],sports,generated_at=asset['generated_at'])
    require(len(canonical(asset))<=MAX_BYTES, 'Display asset exceeds byte budget')
    return asset


def read_asset(data_dir, descriptor, sports, *, now):
    exact(descriptor, {'path','sha256','generated_at','status','retained','error'}, 'descriptor')
    require(type(descriptor['sha256']) is str and SHA.fullmatch(descriptor['sha256']) and descriptor['path']==f"display.{descriptor['sha256']}.json"
        and descriptor['status']=='DISPLAY_METADATA_ONLY' and type(descriptor['retained']) is bool and (descriptor['error'] is None or text(descriptor['error'])), 'Invalid display descriptor/path')
    path=Path(data_dir)/descriptor['path'];require(not path.is_symlink(), 'Display asset cannot be a symlink')
    raw=path.read_bytes();require(hashlib.sha256(raw).hexdigest()==descriptor['sha256'], 'Display asset byte checksum mismatch')
    asset=validate_asset(load_json(path,max_bytes=MAX_BYTES),sports,now=now)
    require(asset['generated_at']==descriptor['generated_at'], 'Display generation clock mismatch')
    return asset

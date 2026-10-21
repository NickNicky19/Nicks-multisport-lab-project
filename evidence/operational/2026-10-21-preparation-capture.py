"""Create-only bounded preparation evidence; never issuance or source admission.

Executed once in this checkpoint. Raw entity bodies remain outside Git. This
script deliberately has no retry, schedule, forecast, outcome or activation path.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

from multisport_lab.integrity import digest, read_receipt, stamp, write_receipt

ROOT = Path('/tmp/nml-ops002-preparation')
MAX_BYTES = 2 * 1024 * 1024


def now():
    return stamp(datetime.now(timezone.utc))


def capture(pair):
    label, url = pair
    target = ROOT / (label + '.bin')
    if target.exists() or target.with_suffix('.capture.json').exists():
        raise RuntimeError('existing capture must be recovered, never overwritten')
    metadata = {'label': label, 'url': url, 'request_started_at': now(),
                'source_updated_at': None, 'source_updated_at_semantics': 'NOT_SUPPLIED'}
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'Nicks-Multisport-Lab-bounded-research/1.0'})
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(MAX_BYTES + 1)
            metadata.update(status=response.status, content_type=response.headers.get('Content-Type'),
                            http_date=response.headers.get('Date'), etag=response.headers.get('ETag'),
                            last_modified=response.headers.get('Last-Modified'))
        metadata['source_observed_at'] = now()
        if len(raw) > MAX_BYTES:
            raise RuntimeError('response exceeds declared source bound')
        with target.open('xb') as handle:
            handle.write(raw)
        metadata.update(raw_sha256=hashlib.sha256(raw).hexdigest(), raw_bytes=len(raw),
                        raw_local_path=str(target), state='RETAINED_PREPARATION_ONLY')
    except Exception as error:
        metadata.update(source_observed_at=now(), state='FAILED',
                        error_type=type(error).__name__, error=str(error)[:600])
    write_receipt(target.with_suffix('.capture.json'), metadata, max_bytes=16384)
    return metadata


if __name__ == '__main__':
    policy = read_receipt('evidence/operational/ops002-preparation-policy.json')
    calls = [(f'scoreboard-{date}', 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=' + date + '&limit=1000')
             for date in policy['candidate_pool']['route_dates']]
    with ThreadPoolExecutor(max_workers=2) as executor:
        records = list(executor.map(capture, calls))
    candidates = []
    for record in records:
        if record['state'] != 'RETAINED_PREPARATION_ONLY':
            continue
        body = json.loads(Path(record['raw_local_path']).read_bytes())
        for event in body.get('events', []):
            competitors = event.get('competitions', [{}])[0].get('competitors', [])
            candidates.append({'event_id': event.get('id'), 'date': event.get('date'),
                               'label': event.get('name'), 'status': event.get('status', {}).get('type'),
                               'season': event.get('season'), 'teams': [item.get('id') for item in competitors],
                               'source_label': record['label']})
    write_receipt('evidence/operational/ops002-preparation-scoreboards.json',
                  {'schema_version': 'nba-ops002-scoreboard-inspection-v1', 'completed_at': now(),
                   'status': 'PREPARATION_NOT_ACTIVATION', 'responses': records, 'returned_events': candidates,
                   'complete_UTC_inventory_claim': False, 'policy_payload_sha256': digest(policy)},
                  max_bytes=65536)
    print(json.dumps({'responses': records, 'events': candidates}, indent=2))

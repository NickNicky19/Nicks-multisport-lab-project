"""GitHub runner boundary for one NBA pilot; no tokens or provider bodies saved.

Only this fixed repository/workflow/records branch is supported. Preflight proves
runner capabilities; execute expires its own workflow before touching pilot data.
All actual generation remains in the separately pinned, reviewed producer.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

from . import manual_cycle as guard
from .integrity import IntegrityError, digest, read_receipt, stamp, utc, write_receipt
from .ledger import Ledger, LedgerRef
from .pregame_sources import binding_view, history_from_input_record, validate_pack

REPOSITORY = 'NickNicky19/Nicks-multisport-lab-project'
BRANCH = 'records/nba-20261020-401909088-t90'
WORKFLOW = '.github/workflows/nba-20261020-pilot.yml'
PLAN = 'evidence/cycles/2026-10-20-nba-401909088-plan.json'
PLAN_SHA = '22ae8db607374486ebee6eb569d236a3d27aedc8535c3085a6b6858226921908'
PROBE_URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20261020'
PROBE_URLS = (PROBE_URL,
    'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401909088',
    'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/8/roster',
    'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/2/roster')
MAX_PROBE_BYTES = 2 * 1024 * 1024
PREFIX = 'evidence/cycles/github-pilot-'


def _now():
    return datetime.now(timezone.utc)


class PilotError(IntegrityError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise PilotError('capability probe redirects are not admitted')


def _source_probe_one(url):
    """One fixed route, never a timely input or normalized pack."""
    started, monotonic = _now(), time.monotonic()
    result = {'url': url, 'request_started_at': stamp(started), 'status': 'FAILED',
              'http_status': None, 'raw_sha256': None, 'bytes': 0, 'source_updated_at': None}
    try:
        opener = urllib.request.build_opener(NoRedirect())
        request = urllib.request.Request(url, headers={'User-Agent': 'Nicks-Multisport-Lab-capability-probe/1'})
        with opener.open(request, timeout=30) as response:
            result['http_status'] = response.status
            body = bytearray()
            while len(body) <= MAX_PROBE_BYTES:
                remaining = 30 - (time.monotonic() - monotonic)
                if remaining <= 0:
                    raise PilotError('capability probe exceeded 30 seconds')
                # urllib's socket timeout otherwise restarts for each read.
                sock = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
                if sock is not None:
                    sock.settimeout(remaining)
                chunk = response.read(min(65536, MAX_PROBE_BYTES + 1 - len(body)))
                if not chunk:
                    break
                body.extend(chunk)
            if len(body) > MAX_PROBE_BYTES or time.monotonic() - monotonic > 30:
                raise PilotError('capability probe exceeded its bytes/time budget')
            result.update(bytes=len(body), raw_sha256=hashlib.sha256(body).hexdigest())
            if response.status != 200:
                raise PilotError(f'capability probe returned HTTP {response.status}')
            result['status'] = 'PASS'
    except (OSError, ValueError) as error:
        if isinstance(error, urllib.error.HTTPError):
            result['http_status'] = error.code
        result['error'] = type(error).__name__ + ': ' + str(error)
    result['response_completed_at'] = stamp(_now())
    return result


def source_probe():
    results = [_source_probe_one(url) for url in PROBE_URLS]
    return {'schema_version': 'nba-pilot-source-capability-v1', 'results': results,
            'status': 'PASS' if all(item['status'] == 'PASS' for item in results) else 'FAILED'}


def valid_probe(probe):
    if probe.get('schema_version') != 'nba-pilot-source-capability-v1' or probe.get('status') != 'PASS':
        return False
    results = probe.get('results', [])
    if len(results) != 4 or [item.get('url') for item in results] != list(PROBE_URLS):
        return False
    try:
        return all(item.get('status') == 'PASS' and item.get('http_status') == 200
            and type(item.get('bytes')) is int and 0 <= item['bytes'] <= MAX_PROBE_BYTES
            and re.fullmatch(r'[a-f0-9]{64}', item.get('raw_sha256', ''))
            and 0 <= (utc(item['response_completed_at']) - utc(item['request_started_at'])).total_seconds() <= 30
            and utc(item['response_completed_at']) <= _now() for item in results)
    except (KeyError, TypeError, ValueError):
        return False


class GitHubPilot:
    def __init__(self, root, environ=None):
        self.root = Path(root).resolve()
        self.env = dict(os.environ if environ is None else environ)
        self.run_id = self.env.get('GITHUB_RUN_ID', '')
        self.attempt = self.env.get('GITHUB_RUN_ATTEMPT', '1')
        self.workflow_id = None
        self._derived_pending = False

    def redact(self, value):
        for name in ('GITHUB_TOKEN', 'GH_TOKEN'):
            token = self.env.get(name)
            if token:
                value = value.replace(token, '[redacted]')
        return value

    def command(self, args, *, cwd=None, input=None, check=True):
        process = subprocess.run(args, cwd=cwd or self.root, input=input,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env=self.env, text=True)
        if check and process.returncode:
            raise PilotError(self.redact(f'{args[0]} failed ({process.returncode}): {process.stderr[:600]}'))
        return process

    def git(self, *args, check=True):
        return self.command(['git', *args], check=check)

    def api(self, path, method='GET', body=None):
        endpoint = f'repos/{REPOSITORY}' + ('/' + path if path else '')
        args = ['gh', 'api', endpoint, '--method', method]
        if body is not None:
            args += ['--input', '-']
        raw = self.command(args, input=json.dumps(body) if body is not None else None).stdout
        return json.loads(raw) if raw.strip() else {}

    def execution_clock(self):
        actual = _now()
        if actual.date().isoformat() != '2026-10-20' or actual.hour * 60 + actual.minute < 17 * 60 + 15:
            raise PilotError('execute requires the single 2026-10-20 run at/after 17:15 UTC')

    def context(self, *, execute=False, check_clock=True):
        if self.env.get('GITHUB_REPOSITORY') != REPOSITORY:
            raise PilotError('runner repository is not the authorized repository')
        if not re.fullmatch(r'[1-9][0-9]{0,19}', self.run_id) or not re.fullmatch(r'[1-9][0-9]{0,3}', self.attempt):
            raise PilotError('actual GitHub run ID/attempt required')
        if execute:
            if (self.env.get('GITHUB_EVENT_NAME') != 'schedule'
                    or self.env.get('GITHUB_REF') != 'refs/heads/main'
                    or self.env.get('NML_PILOT_CRON') != '15 17 20 10 *'):
                raise PilotError('execute requires the exact one-shot cron on scheduled main')
            if check_clock:
                self.execution_clock()
        origin = self.git('remote', 'get-url', 'origin').stdout.strip()
        if origin not in (f'https://github.com/{REPOSITORY}', f'https://github.com/{REPOSITORY}.git',
                          f'git@github.com:{REPOSITORY}.git'):
            raise PilotError('origin does not identify the authorized repository')

    def read_workflow(self):
        run = self.api(f'actions/runs/{self.run_id}')
        self.workflow_id = run.get('workflow_id')
        if type(self.workflow_id) is not int or self.workflow_id <= 0:
            raise PilotError('own run did not identify a workflow')
        path = f'actions/workflows/{self.workflow_id}'
        own = self.api(path)
        if own.get('path') != WORKFLOW:
            raise PilotError('workflow identity is not the admitted pilot workflow')
        return path, own

    def workflow(self, *, probe=False):
        path, own = self.read_workflow()
        if probe and own.get('state') != 'active':
            raise PilotError('preflight requires its own active pilot workflow')
        disabled = False
        try:
            self.api(path + '/disable', 'PUT')
            disabled = True
            if self.api(path).get('state') != 'disabled_manually':
                raise PilotError('own workflow disable was not independently observed')
        finally:
            if probe and disabled:
                self.api(path + '/enable', 'PUT')
                if self.api(path).get('state') != 'active':
                    raise PilotError('preflight could not restore its own workflow to active')

    def pins(self):
        plan = guard.load_plan(self.root / PLAN)
        if digest(plan) != PLAN_SHA:
            raise PilotError('the original manual plan changed')
        guard.preflight(self.root / PLAN, repository_root=self.root)
        _, provenance = history_from_input_record(plan['history_input_record_id'], repository_root=self.root)
        if provenance['normalized_panel_rows'] != 26645 or provenance['normalized_panel_sha256'] != guard.producer.PILOT_PANEL_SHA256:
            raise PilotError('full original history did not recover')
        return plan

    def branch(self):
        if self.git('status', '--porcelain').stdout.strip():
            raise PilotError('runner checkout must be clean before branch recovery')
        source = self.git('rev-parse', 'HEAD').stdout.strip()
        expected = self.env.get('NML_EXPECTED_CHECKOUT_SHA', self.env.get('GITHUB_SHA', ''))
        if not re.fullmatch(r'[a-f0-9]{40}', expected) or source != expected:
            raise PilotError('checkout does not match the actual workflow source SHA')
        remote = self.git('ls-remote', '--heads', 'origin', f'refs/heads/{BRANCH}').stdout.strip()
        if remote:
            self.git('fetch', '--no-tags', 'origin', f'refs/heads/{BRANCH}')
            if self.git('show-ref', '--verify', '--quiet', f'refs/heads/{BRANCH}', check=False).returncode == 0:
                self.git('checkout', BRANCH)
                self.git('merge', '--ff-only', 'FETCH_HEAD')
            else:
                self.git('checkout', '-b', BRANCH, 'FETCH_HEAD')
            self.claim(existing_only=True)
            self.git('-c', 'user.name=github-actions[bot]', '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                     'merge', '--no-edit', source)
        else:
            self.git('checkout', '-b', BRANCH, source)
        self.pins()

    def receipt(self, name, payload):
        path = PREFIX + name + '.json'
        write_receipt(self.root / path, payload)
        return path

    def claim(self, *, existing_only=False):
        path = self.root / (PREFIX + guard.CYCLE_ID + '-claim.json')
        if path.exists():
            saved = read_receipt(path)
            if (saved.get('run_id') != self.run_id or saved.get('plan_sha256') != PLAN_SHA
                    or saved.get('cycle_id') != guard.CYCLE_ID or saved.get('producer_commit') != guard.PRODUCER_COMMIT
                    or saved.get('workflow_id') != self.workflow_id):
                raise PilotError('another GitHub run already owns this one-shot cycle')
            return str(path.relative_to(self.root))
        if existing_only:
            return None
        return self.receipt(guard.CYCLE_ID + '-claim', {'schema_version': 'nba-github-pilot-claim-v1',
                            'cycle_id': guard.CYCLE_ID, 'run_id': self.run_id, 'workflow_id': self.workflow_id,
                            'plan_sha256': PLAN_SHA, 'producer_commit': guard.PRODUCER_COMMIT,
                            'claimed_at': stamp(_now())})

    def cycle_paths(self):
        plan = self.pins()
        snapshot = Ledger(self.root).scan()
        paths = []
        for kind in ('research_inputs', 'forecasts'):
            for record_id, payload in snapshot[kind].items():
                path = f'records/{kind}/{record_id}.json'
                data = payload['data'].get('source_pack' if kind == 'research_inputs' else 'bundle', {})
                event = data.get('event', data).get('event_id')
                if path not in plan['original_records_sha256'] and event == plan['event_id']:
                    if kind == 'research_inputs':
                        pack = validate_pack(data)
                        view = binding_view(pack)
                        if (view['event']['event_version'] != plan['event_version'] or view['selection_sha256'] != plan['selection_sha256']
                                or [item['player_id'] for item in view['candidates']] != plan['selected_player_ids']):
                            raise PilotError('new input changes the frozen event/cohort')
                        guard.producer._check_pilot_history(pack, view)
                    paths.append(path)
        binding = f'evidence/cycles/{guard.CYCLE_ID}-binding.json'
        if (self.root / binding).exists():
            paths.append(binding)
        return paths + self.source_metadata_paths()

    def source_metadata_paths(self):
        raw = self.root / '.local-data/pregame-cycle' / guard.CYCLE_ID / 'raw'
        paths = sorted(raw.glob('*.capture.json'))
        if len(paths) > 4:
            raise PilotError('more than one four-request pilot capture is present')
        expected = {'source_id','source_url','request_started_at','observed_at','response_completed_at',
                    'source_updated_at','source_response_generated_at','raw_sha256','raw_bytes',
                    'http_status','http_date','etag','last_modified'}
        allowed = dict(zip(('scoreboard','summary','roster-8','roster-2'), PROBE_URLS))
        result = []
        for path in paths:
            metadata = read_receipt(path, max_bytes=64 * 1024)
            if (set(metadata) != expected or metadata.get('source_url') != allowed.get(metadata.get('source_id'))
                    or not re.fullmatch(r'[a-f0-9]{64}', metadata.get('raw_sha256', ''))):
                raise PilotError('capture metadata includes unadmitted fields/source identity')
            target = f'evidence/cycles/source-attempts/{guard.CYCLE_ID}-{metadata["source_id"]}-{digest(metadata)}.json'
            write_receipt(self.root / target, metadata)
            result.append(target)
        return result

    def remote_verify(self, names):
        expected = self.git('rev-parse', 'HEAD').stdout.strip()
        with tempfile.TemporaryDirectory(prefix='nml-pilot-readback-') as directory:
            self.command(['git', 'init', '--bare', directory])
            self.command(['git', '-C', directory, 'fetch', '--depth=1', '--no-tags',
                          f'https://github.com/{REPOSITORY}.git', f'refs/heads/{BRANCH}'])
            actual = self.command(['git', '-C', directory, 'rev-parse', 'FETCH_HEAD']).stdout.strip()
            if actual != expected:
                raise PilotError('fresh remote branch does not equal the pushed checkpoint')
            for name in sorted(set(names) | set(self.pins()['original_records_sha256'])):
                process = subprocess.run(['git', '-C', directory, 'show', f'FETCH_HEAD:{name}'], stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, env=self.env, check=False)
                if process.returncode or process.stdout != (self.root / name).read_bytes():
                    raise PilotError(f'fresh remote bytes differ: {name}')
                if name.endswith('.json'):
                    envelope = json.loads(process.stdout)
                    if envelope.get('payload_sha256') != digest(envelope.get('payload')):
                        raise PilotError(f'remote receipt checksum differs: {name}')
        return expected

    def persist(self, paths, phase):
        self.pins()
        allowed = set(paths)
        for name in allowed:
            if not (re.fullmatch(r'records/(research_inputs|forecasts)/[a-f0-9]{64}\.json', name)
                    or name == f'evidence/cycles/{guard.CYCLE_ID}-binding.json'
                    or re.fullmatch(r'evidence/cycles/source-attempts/[A-Za-z0-9_-]+\.json', name)
                    or re.fullmatch(r'evidence/cycles/github-pilot-[A-Za-z0-9_.-]+\.(json|md)', name)):
                raise PilotError('checkpoint contains a path outside its precise allowlist')
        staged = set(self.git('diff', '--cached', '--name-only').stdout.splitlines())
        derived = {'HANDOFF_STATUS.md', 'MANIFEST.sha256'} if self._derived_pending else set()
        if not staged <= allowed | derived:
            raise PilotError('unrelated files were already staged')
        self.git('add', '--', *sorted(allowed))
        changed = self.git('diff', '--cached', '--quiet', check=False).returncode
        if changed not in (0, 1):
            raise PilotError('could not determine staged checkpoint state')
        if changed:
            self._derived_pending = True
            if not phase.startswith('PREFLIGHT_'):
                handoff = self.root / 'HANDOFF_STATUS.md'
                with handoff.open('a') as handle:
                    handle.write(f'\nGitHub pilot checkpoint {stamp(_now())}: run {self.run_id}, {phase}. '
                                 'Research only; financial settlement and product qualification unavailable.\n')
                allowed.add('HANDOFF_STATUS.md')
                self.git('add', '--', 'HANDOFF_STATUS.md')
            tracked = self.git('ls-files', '-z').stdout.split('\0')
            names = sorted(name for name in tracked if name and name != 'MANIFEST.sha256')
            (self.root / 'MANIFEST.sha256').write_text(''.join(hashlib.sha256((self.root / name).read_bytes()).hexdigest() + '  ' + name + '\n' for name in names))
            self.git('add', '--', 'MANIFEST.sha256')
            allowed.add('MANIFEST.sha256')
            self.git('diff', '--cached', '--check')
            self.git('-c', 'user.name=github-actions[bot]', '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                     'commit', '-m', f'Record NBA pilot {phase}')
            self._derived_pending = False
        self.git('push', 'origin', f'HEAD:refs/heads/{BRANCH}')
        return self.remote_verify(allowed)

    def preflight(self):
        self.context()
        self.pins()
        metadata = self.api('')
        if metadata.get('full_name') != REPOSITORY:
            raise PilotError('GitHub metadata identity differs')
        self.workflow(probe=True)
        self.branch()
        previous = sorted((self.root / 'evidence/cycles').glob('github-pilot-probe-result-*.json'))
        probe = next((value for path in previous if valid_probe(value := read_receipt(path))), None)
        if probe is None:
            slot = next((i for i in range(1, 4) if not (self.root / f'{PREFIX}probe-intent-{i}.json').exists()), None)
            if slot is None:
                raise PilotError('three setup source-probe attempts exhausted; no valid retained probe')
            intent = self.receipt(f'probe-intent-{slot}', {'run_id': self.run_id, 'urls': list(PROBE_URLS), 'reserved_at': stamp(_now())})
            self.persist([intent], 'PREFLIGHT_PROBE_RESERVED')
            probe = source_probe()
            result = self.receipt(f'probe-result-{slot}', probe)
            self.persist([result], 'PREFLIGHT_PROBE_RESULT')
        capability = f'{PREFIX}capability-{self.run_id}.json'
        if not (self.root / capability).exists():
            self.receipt(f'capability-{self.run_id}', {'schema_version': 'nba-github-pilot-capability-v1',
            'run_id': self.run_id, 'repository': REPOSITORY, 'workflow_id': self.workflow_id,
            'checked_at': stamp(_now()), 'source_probe': probe, 'plan_sha256': PLAN_SHA,
            'producer_commit': guard.PRODUCER_COMMIT, 'workflow_disable_reenable': 'VERIFIED',
            'contents_push_and_fresh_readback': 'VERIFIED', 'pull_request_creation': 'UNTESTED'})
        self.persist([capability], 'PREFLIGHT_CAPABILITY')
        if not valid_probe(probe):
            raise PilotError('actual runner source probe failed; activation is not ready')
        return {'status': 'PREFLIGHT_PASS', 'capability': capability, 'genuine_issuance': 0}

    def reject_ambiguous_intents(self):
        recovered = guard.recover(self.root / PLAN, repository_root=self.root)
        subjects = recovered['forecast_records']
        capture = self.root / f'{PREFIX}capture-intent-{guard.CYCLE_ID}.json'
        if capture.exists():
            intent = read_receipt(capture)
            expected = {'run_id': self.run_id, 'cycle_id': guard.CYCLE_ID, 'producer_commit': guard.PRODUCER_COMMIT,
                        'event_id': '401909088', 'history_input_record_id': guard.HISTORY_RECORD_ID, 'input_reference': None}
            if any(intent.get(key) != value for key, value in expected.items()):
                raise PilotError('original capture intent identity changed')
            if (intent.get('schema_version') != 'nba-scheduled-cycle-checkpoint-v1' or intent.get('phase') != 'CAPTURE_STARTED'
                    or stamp(utc(intent['checked_at'])) != intent['checked_at'] or utc(intent['checked_at']) > _now()):
                raise PilotError('original capture intent schema/clock changed')
        for path in (self.root / 'evidence/cycles').glob(f'github-pilot-intent-{guard.CYCLE_ID}-*.json'):
            intent = read_receipt(path)
            player = intent.get('player_id')
            subject = subjects.get(player)
            if (intent.get('run_id') != self.run_id or not subject
                    or intent.get('cycle_id') != guard.CYCLE_ID or intent.get('producer_commit') != guard.PRODUCER_COMMIT
                    or intent.get('input_reference') != recovered['input_reference']
                    or intent.get('model_version') != guard.producer.MODEL_VERSION):
                raise PilotError('AMBIGUOUS_GENERATION: durable intent has no validated original; do not regenerate')
            saved = Ledger(self.root).read(LedgerRef.from_record(subject['reference']))['data']['bundle']
            if (path.name != f'github-pilot-intent-{guard.CYCLE_ID}-{player}.json'
                    or intent.get('schema_version') != 'nba-scheduled-cycle-checkpoint-v1' or intent.get('phase') != 'GENERATION_STARTED'
                    or stamp(utc(intent['checked_at'])) != intent['checked_at']
                    or utc(intent['checked_at']) > utc(saved['prospective']['generation_started_at'])
                    or utc(intent['checked_at']) > utc(saved['issued_at'])):
                raise PilotError('original generation intent filename/schema/order changed')
        for player in subjects:
            if not (self.root / f'{PREFIX}intent-{guard.CYCLE_ID}-{player}.json').exists():
                raise PilotError('EXTERNAL_OR_UNRESERVED_ORIGINAL: retained subject has no original durable intent')

    def checkpoint(self, info):
        if (info.get('schema_version') != 'nba-scheduled-cycle-checkpoint-v1'
                or info.get('cycle_id') != guard.CYCLE_ID or info.get('producer_commit') != guard.PRODUCER_COMMIT):
            raise PilotError('phase identity differs from the pinned cycle')
        phase = info.get('phase')
        if phase != 'CAPTURE_STARTED':
            reference = LedgerRef.from_record(info.get('input_reference'))
            if reference.kind != 'research_inputs':
                raise PilotError('phase requires the actual frozen research input reference')
        if phase == 'CAPTURE_STARTED':
            if (info.get('input_reference') is not None or info.get('event_id') != '401909088'
                    or info.get('history_input_record_id') != guard.HISTORY_RECORD_ID):
                raise PilotError('capture intent identity differs from the frozen preparation')
            name = f'capture-intent-{guard.CYCLE_ID}'
        elif phase == 'GENERATION_STARTED':
            player = info.get('player_id')
            if player not in guard.PLAYERS or info.get('model_version') != guard.producer.MODEL_VERSION:
                raise PilotError('generation intent is outside the selected cohort')
            name = f'intent-{guard.CYCLE_ID}-{player}'
        elif phase in ('INPUT_BOUND', 'FORECAST_RETAINED'):
            if phase == 'INPUT_BOUND':
                current = guard.recover(self.root / PLAN, repository_root=self.root)
                reported = info.get('retained_forecast_references', [])
                references = {LedgerRef.from_record(item) for item in reported}
                originals = {LedgerRef.from_record(item['reference']) for item in current['forecast_records'].values()}
                if (info.get('binding_path') != f'evidence/cycles/{guard.CYCLE_ID}-binding.json'
                        or current['input_reference'] != info['input_reference']
                        or current['clocks']['bound_at'] != info.get('bound_at')
                        or len(references) != len(reported) or references != originals):
                    raise PilotError('input checkpoint differs from the immutable binding or recovered originals')
            if phase == 'FORECAST_RETAINED' and (info.get('player_id') not in guard.PLAYERS
                    or LedgerRef.from_record(info.get('forecast_reference')).kind != 'forecasts'):
                raise PilotError('retained forecast does not identify a selected original')
            name = f'checkpoint-{self.run_id}-{phase}-{info.get("player_id", "input")}'
        else:
            raise PilotError('unknown phase checkpoint')
        path = PREFIX + name + '.json'
        if not (self.root / path).exists():
            self.receipt(name, {**info, 'run_id': self.run_id})
        elif phase in ('GENERATION_STARTED', 'CAPTURE_STARTED'):
            raise PilotError('AMBIGUOUS_OPERATION: original capture/generation intent already exists')
        elif any(read_receipt(self.root / path).get(key) != value for key, value in {**info, 'run_id': self.run_id}.items()
                 if key != 'checked_at' and not (phase == 'INPUT_BOUND' and key == 'retained_forecast_references')):
            raise PilotError('retained phase receipt changed its original identity or clocks')
        self.persist([path, *self.cycle_paths()], phase)

    def execute(self):
        self.context(execute=True, check_clock=False)
        self.workflow()  # Permanently expire before any pilot data or branch write.
        self.pins()  # Invalid pins cannot prevent expiry or permit any pilot work.
        self.execution_clock()  # Even a missed year expires before refusing data.
        self.branch()
        claim = self.claim()
        self.persist([claim], 'CLAIMED')
        started = stamp(_now())
        try:
            self.reject_ambiguous_intents()
            from .scheduled_cycle import run_cycle
            report = run_cycle(root=self.root, checkpoint=self.checkpoint)
        except Exception as error:
            report = {'status': 'FAILED_OR_PARTIAL', 'exit_code': 1, 'errors': [self.redact(str(error))]}
        report.update(run_id=self.run_id, attempt=self.attempt, started_at=report.get('started_at', started),
                      completed_at=stamp(_now()), workflow_disabled=True)
        path = self.receipt(f'report-{self.run_id}-{self.attempt}', report)
        # A failed commit can leave a prior intent staged. Preserve that exact
        # owned metadata along with originals before trying the final push.
        owned = [str(p.relative_to(self.root)) for p in (self.root / 'evidence/cycles').glob('github-pilot-*.json')
                 if read_receipt(p).get('run_id') == self.run_id]
        self.persist([path, *owned, *self.cycle_paths()], 'FINAL_' + report['status'])
        return report

    def publication_pr(self, *, draft=False):
        self.context(execute=not draft)
        self.read_workflow()  # Separate CLI process must recover its own numeric ID.
        if not draft and self.claim(existing_only=True) is None:
            raise PilotError('publication requires the original execution claim')
        if self.git('branch', '--show-current').stdout.strip() != BRANCH:
            raise PilotError('publication must use the retained records branch')
        reports = sorted((self.root / 'evidence/cycles').glob(f'github-pilot-report-{self.run_id}-*.json'))
        if not reports and not draft:
            raise PilotError('no actual pilot execution report exists')
        if draft:
            read_receipt(self.root / f'{PREFIX}capability-{self.run_id}.json')
            if reports:
                raise PilotError('actual execution exists; do not replace it with readiness-only wording')
        report = read_receipt(max(reports, key=lambda p: int(p.stem.rsplit('-', 1)[1]))) if reports else {'status': 'READINESS_ONLY_NOT_EXECUTED'}
        keep_draft = draft or report.get('exit_code', 1) != 0
        compare = f'https://github.com/{REPOSITORY}/compare/main...{BRANCH}?expand=1'
        body = (('Readiness only: zero new forecasts; pilot execution has not occurred.\n\n' if draft else 'Actual one-shot NBA paper-research checkpoint.\n\n') +
                f'GitHub run: {self.run_id}\n\nStatus: {report["status"]}\n\n'
                'Original clocks and partial results are retained. No financial settlement, '
                'product qualification or confirmatory accuracy claim.\n\n' + compare + '\n')
        body_path = f'{PREFIX}publication-{self.run_id}.md'
        (self.root / body_path).write_text(body)
        self.persist([body_path], 'PREFLIGHT_PUBLICATION_BODY' if draft else 'PUBLICATION_BODY')
        try:
            existing = self.api(f'pulls?state=open&head=NickNicky19:{BRANCH}&base=main')
            title = 'NBA pilot readiness / pending execution' if draft else 'Retain actual NBA one-shot research pilot'
            if existing:
                pr = existing[0]
                if pr['head']['ref'] != BRANCH or pr['base']['ref'] != 'main' or pr['head']['repo']['full_name'] != REPOSITORY:
                    raise PilotError('existing publication PR identity differs')
                pr = self.api(f'pulls/{pr["number"]}', 'PATCH', {'title': title, 'body': body})
                operation = 'UPDATED_EXISTING'
            else:
                pr = self.api('pulls', 'POST', {'title': title, 'head': BRANCH, 'base': 'main', 'body': body, 'draft': keep_draft})
                operation = 'CREATED'
            if not keep_draft and pr.get('draft'):
                self.command(['gh', 'pr', 'ready', pr['html_url']])
            result = {'status': 'DRAFT_PR_OPEN' if keep_draft else 'PR_OPEN', 'url': pr['html_url']}
        except PilotError as error:
            detail = self.redact(str(error))
            blocked = self.receipt(f'publication-blocked-{self.run_id}-{self.attempt}', {
                'status': 'PR_CREATION_BLOCKED', 'checked_at': stamp(_now()), 'error': self.redact(str(error)),
                'body_path': body_path, 'compare_url': compare,
                'owner_prerequisite': 'Settings → Actions → General → Allow GitHub Actions to create and approve pull requests.' if '403' in detail else None})
            self.persist([blocked], 'PREFLIGHT_PR_CREATION_BLOCKED' if draft else 'PR_CREATION_BLOCKED')
            result = {'status': 'PR_CREATION_BLOCKED', 'exit_code': 1,
                      'compare_url': compare, 'error': self.redact(str(error))}
        if result['status'] != 'PR_CREATION_BLOCKED':
            proof = self.receipt(f'publication-result-{self.run_id}-{self.attempt}', {
                'run_id': self.run_id, 'checked_at': stamp(_now()), 'status': result['status'],
                'pull_request_write': 'VERIFIED', 'operation': operation, 'url': result['url'], 'plan_sha256': PLAN_SHA})
            self.persist([proof], 'PREFLIGHT_PUBLICATION_VERIFIED' if draft else 'PUBLICATION_VERIFIED')
        try:
            result['validation'] = self.dispatch_validation()
            if result['validation'].get('conclusion') != 'success':
                result['exit_code'] = 1
        except PilotError as error:
            result.update(exit_code=1, validation={'status': 'DISPATCH_BLOCKED', 'error': self.redact(str(error))})
        return result

    def dispatch_validation(self):
        """Token-created PRs do not trigger CI; explicit dispatch does. Never merge."""
        commit = self.git('rev-parse', 'HEAD').stdout.strip()
        endpoint = 'actions/workflows/pages.yml/runs?event=workflow_dispatch&per_page=20'
        previous = {run['id'] for run in self.api(endpoint)['workflow_runs']}
        started = _now()
        self.api('actions/workflows/pages.yml/dispatches', 'POST', {'ref': BRANCH})
        deadline = time.monotonic() + 180
        last = {}
        while time.monotonic() < deadline:
            runs = self.api(endpoint)['workflow_runs']
            for run in runs:
                if (run['id'] not in previous and run['head_branch'] == BRANCH and run['head_sha'] == commit
                        and utc(run['created_at']) >= started.replace(microsecond=0)):
                    last = {'url': run['html_url'], 'status': run['status']}
                    if run['status'] == 'completed':
                        return {'head_sha': commit, 'url': run['html_url'], 'status': run['status'], 'conclusion': run['conclusion']}
            time.sleep(5)
        return {**last, 'head_sha': commit, 'status': 'PENDING_OR_UNOBSERVED', 'wait_budget_seconds': 180}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['preflight', 'execute', 'publication-pr'])
    parser.add_argument('--draft', action='store_true')
    args = parser.parse_args()
    try:
        pilot = GitHubPilot(Path(__file__).resolve().parents[1])
        result = pilot.publication_pr(draft=args.draft) if args.command == 'publication-pr' else getattr(pilot, args.command)()
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, indent=2))
    if result.get('exit_code', 0) or result.get('status') == 'PR_CREATION_BLOCKED':
        raise SystemExit(1)


if __name__ == '__main__':
    main()

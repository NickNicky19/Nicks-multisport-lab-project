"""Mocked runner/API/source tests; no actual Git, HTTP, capture or forecasts."""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from multisport_lab import pilot_github as gh
from multisport_lab.integrity import read_receipt, write_receipt

NOW = datetime(2026, 10, 20, 17, 21, tzinfo=timezone.utc)
INPUT = {'kind': 'research_inputs', 'record_id': 'b' * 64, 'payload_sha256': 'c' * 64}


def process(stdout='', returncode=0):
    return SimpleNamespace(stdout=stdout, stderr='', returncode=returncode)


def phase(name, **extra):
    return {'schema_version': 'nba-scheduled-cycle-checkpoint-v1', 'phase': name, 'cycle_id': gh.guard.CYCLE_ID, 'producer_commit': gh.guard.PRODUCER_COMMIT,
            'input_reference': INPUT, 'checked_at': gh.stamp(NOW), **extra}


class GitHubPilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'evidence/cycles').mkdir(parents=True)
        (self.root / 'HANDOFF_STATUS.md').write_text('Original handoff\n')
        self.env = {'GITHUB_REPOSITORY': gh.REPOSITORY, 'GITHUB_RUN_ID': '123',
                    'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_EVENT_NAME': 'schedule',
                    'NML_PILOT_CRON': '15 17 20 10 *',
                    'GITHUB_REF': 'refs/heads/main', 'GITHUB_SHA': 'a' * 40, 'GH_TOKEN': 'never-print-this'}
        self.pilot = gh.GitHubPilot(self.root, self.env); self.pilot.workflow_id = 99
        self.clock = patch.object(gh, '_now', return_value=NOW); self.clock.start(); self.addCleanup(self.clock.stop)

    def test_execution_identity_and_actual_clock_gates_before_any_git_or_api(self):
        self.pilot.git = Mock(); self.pilot.api = Mock()
        for field, value in [('GITHUB_REPOSITORY', 'NickNicky19/other'), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
                             ('GITHUB_REF', 'refs/heads/records'), ('GITHUB_RUN_ID', '../123')]:
            with self.subTest(field=field):
                self.pilot.env = {**self.env, field: value}; self.pilot.run_id = self.pilot.env['GITHUB_RUN_ID']
                with self.assertRaises(gh.PilotError): self.pilot.context(execute=True)
        self.pilot.env = self.env; self.pilot.run_id = '123'
        for clock in [NOW.replace(year=2027), NOW.replace(hour=17, minute=14)]:
            with patch.object(gh, '_now', return_value=clock), self.assertRaises(gh.PilotError):
                self.pilot.context(execute=True)
        self.pilot.git.assert_not_called(); self.pilot.api.assert_not_called()

    def test_wrong_origin_is_rejected_and_token_is_redacted(self):
        self.pilot.git = Mock(return_value=process('https://github.com/NickNicky19/other.git'))
        with self.assertRaises(gh.PilotError): self.pilot.context()
        self.assertEqual(self.pilot.redact('failure never-print-this'), 'failure [redacted]')

    def test_preflight_disable_failure_observation_still_restores_own_workflow(self):
        self.pilot.api = Mock(side_effect=[{'workflow_id': 99}, {'path': gh.WORKFLOW, 'state': 'active'},
                                           {}, {'state': 'active'}, {}, {'state': 'active'}])
        with self.assertRaisesRegex(gh.PilotError, 'disable was not'): self.pilot.workflow(probe=True)
        calls = self.pilot.api.call_args_list
        self.assertEqual(calls[4].args, ('actions/workflows/99/enable', 'PUT'))
        self.assertTrue(all('99' in call.args[0] or '/123' in call.args[0] for call in calls))

    def test_execute_self_disable_failure_never_reaches_branch_or_data(self):
        self.pilot.context = Mock(); self.pilot.workflow = Mock(side_effect=gh.PilotError('HTTP 403'))
        self.pilot.pins = Mock()
        self.pilot.branch = Mock(); self.pilot.claim = Mock()
        with self.assertRaisesRegex(gh.PilotError, '403'): self.pilot.execute()
        self.pilot.branch.assert_not_called(); self.pilot.claim.assert_not_called()

    def test_missed_year_expires_trusted_workflow_before_refusing_claim_or_data(self):
        self.pilot.git = Mock(return_value=process(f'https://github.com/{gh.REPOSITORY}.git'))
        self.pilot.pins = Mock(); self.pilot.workflow = Mock(); self.pilot.branch = Mock(); self.pilot.claim = Mock()
        with patch.object(gh, '_now', return_value=NOW.replace(year=2027)), self.assertRaises(gh.PilotError):
            self.pilot.execute()
        self.pilot.workflow.assert_called_once_with()
        self.pilot.branch.assert_not_called(); self.pilot.claim.assert_not_called()

    def test_workflow_identity_prevents_touching_another_workflow(self):
        self.pilot.api = Mock(side_effect=[{'workflow_id': 99}, {'path': '.github/workflows/pages.yml', 'state': 'active'}])
        with self.assertRaises(gh.PilotError): self.pilot.workflow(probe=True)
        self.assertEqual(self.pilot.api.call_count, 2)

    def test_claim_same_run_recovers_original_clock_different_run_refuses(self):
        path = self.pilot.claim(); before = (self.root / path).read_bytes()
        self.assertEqual(self.pilot.claim(), path)
        self.assertEqual((self.root / path).read_bytes(), before)
        self.pilot.run_id = '456'
        with self.assertRaisesRegex(gh.PilotError, 'another GitHub run'): self.pilot.claim()
        self.assertEqual((self.root / path).read_bytes(), before)

    def test_branch_recovery_uses_normal_merge_without_reset_or_force(self):
        self.pilot.pins = Mock(); self.pilot.claim = Mock()
        def git(*args, **_kwargs):
            if args[:2] == ('status', '--porcelain'): return process()
            if args[:2] == ('rev-parse', 'HEAD'): return process('a' * 40)
            if args[0] == 'ls-remote': return process('b' * 40 + '\trefs/heads/' + gh.BRANCH)
            if args[0] == 'show-ref': return process(returncode=1)
            return process()
        self.pilot.git = Mock(side_effect=git); self.pilot.branch()
        commands = [call.args for call in self.pilot.git.call_args_list]
        self.assertIn(('checkout', '-b', gh.BRANCH, 'FETCH_HEAD'), commands)
        self.assertTrue(any('merge' in command and '--no-edit' in command for command in commands))
        self.assertFalse(any('reset' in command or '--force' in command or '-B' in command for command in commands))

    def test_pull_request_head_checkout_is_distinct_from_synthetic_github_sha(self):
        self.pilot.env['NML_EXPECTED_CHECKOUT_SHA'] = 'b' * 40
        self.pilot.pins = Mock(); self.pilot.claim = Mock()
        self.pilot.git = Mock(side_effect=lambda *args, **kwargs:
            process('b' * 40) if args[:2] == ('rev-parse', 'HEAD') else process())
        self.pilot.branch()
        self.assertIn(('checkout', '-b', gh.BRANCH, 'b' * 40), [call.args for call in self.pilot.git.call_args_list])

    def test_git_noop_does_not_commit_or_rewrite_handoff(self):
        self.pilot.pins = Mock(); self.pilot.remote_verify = Mock(return_value='a' * 40)
        self.pilot.git = Mock(return_value=process())
        path = self.pilot.receipt('noop', {'actual': True})
        before = (self.root / 'HANDOFF_STATUS.md').read_bytes()
        self.pilot.persist([path], 'RECOVERED')
        self.assertEqual((self.root / 'HANDOFF_STATUS.md').read_bytes(), before)
        self.assertFalse(any('commit' in call.args for call in self.pilot.git.call_args_list))
        self.pilot.remote_verify.assert_called_once()

    def test_staging_rejects_raw_sources_and_unrelated_existing_stage(self):
        self.pilot.pins = Mock(); self.pilot.git = Mock(return_value=process('other.py\n'))
        with self.assertRaisesRegex(gh.PilotError, 'allowlist'): self.pilot.persist(['.local-data/raw.json'], 'FAIL')
        with self.assertRaisesRegex(gh.PilotError, 'already staged'):
            self.pilot.persist([self.pilot.receipt('stage', {})], 'FAIL')

    def test_remote_changed_bytes_fail_independent_readback(self):
        path = self.pilot.receipt('remote', {'original': True})
        self.pilot.git = Mock(return_value=process('a' * 40))
        self.pilot.pins = Mock(return_value={'original_records_sha256': {}})
        self.pilot.command = Mock(side_effect=[process(), process(), process('a' * 40)])
        with patch.object(gh.subprocess, 'run', return_value=process(b'changed')), self.assertRaisesRegex(gh.PilotError, 'remote bytes differ'):
            self.pilot.remote_verify([path])

    def test_probe_four_fixed_routes_no_response_bodies_retained(self):
        result = {'status': 'PASS'}
        with patch.object(gh, '_source_probe_one', return_value=result) as probe:
            batch = gh.source_probe()
        self.assertEqual([call.args[0] for call in probe.call_args_list], list(gh.PROBE_URLS))
        self.assertEqual(len(batch['results']), 4)
        self.assertNotIn('raw', batch)

    def test_source_probe_byte_budget_stops_without_normalization(self):
        response = Mock(); response.status = 200
        response.read.side_effect = [b'x' * 65536] * 32 + [b'x']
        response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
        with patch.object(gh.urllib.request, 'build_opener') as opener, patch.object(gh.time, 'monotonic', return_value=0):
            opener.return_value.open.return_value = response
            result = gh._source_probe_one(gh.PROBE_URL)
        self.assertEqual(result['status'], 'FAILED')
        self.assertIsNone(result['raw_sha256'])

    def test_three_reserved_probe_batches_exhaust_budget_without_source_call(self):
        for i in range(1, 4): self.pilot.receipt(f'probe-intent-{i}', {'reserved': True})
        self.pilot.context = Mock(); self.pilot.pins = Mock(); self.pilot.workflow = Mock(); self.pilot.branch = Mock()
        self.pilot.api = Mock(return_value={'full_name': gh.REPOSITORY})
        with patch.object(gh, 'source_probe') as probe, self.assertRaisesRegex(gh.PilotError, 'exhausted'):
            self.pilot.preflight()
        probe.assert_not_called()

    def test_successful_four_route_probe_is_reused_after_budget_spent(self):
        for i in range(1, 4): self.pilot.receipt(f'probe-intent-{i}', {'reserved': True})
        saved = {'schema_version': 'nba-pilot-source-capability-v1', 'status': 'PASS', 'results': [
            {'url': url, 'status': 'PASS', 'http_status': 200, 'bytes': 10, 'raw_sha256': 'a' * 64,
             'request_started_at': gh.stamp(NOW), 'response_completed_at': gh.stamp(NOW)} for url in gh.PROBE_URLS]}
        self.pilot.receipt('probe-result-1', saved)
        self.pilot.context = Mock(); self.pilot.pins = Mock(); self.pilot.workflow = Mock(); self.pilot.branch = Mock()
        self.pilot.persist = Mock(); self.pilot.api = Mock(return_value={'full_name': gh.REPOSITORY})
        with patch.object(gh, 'source_probe') as probe: result = self.pilot.preflight()
        probe.assert_not_called(); self.assertEqual(result['status'], 'PREFLIGHT_PASS')

    def test_generation_intent_without_retained_original_never_regenerates(self):
        info = phase('GENERATION_STARTED', player_id=gh.guard.PLAYERS[0], model_version=gh.guard.producer.MODEL_VERSION)
        self.pilot.persist = Mock(); self.pilot.cycle_paths = Mock(return_value=[])
        self.pilot.checkpoint(info)
        with patch.object(gh.guard, 'recover', return_value={'forecast_records': {}, 'input_reference': INPUT}), self.assertRaisesRegex(gh.PilotError, 'AMBIGUOUS_GENERATION'):
            self.pilot.reject_ambiguous_intents()
        with self.assertRaisesRegex(gh.PilotError, 'AMBIGUOUS_OPERATION'): self.pilot.checkpoint(info)

    def test_retained_original_requires_same_run_input_player_and_model(self):
        info = phase('GENERATION_STARTED', player_id=gh.guard.PLAYERS[0], model_version=gh.guard.producer.MODEL_VERSION)
        self.pilot.persist = Mock(); self.pilot.cycle_paths = Mock(return_value=[]); self.pilot.checkpoint(info)
        reference = {'kind': 'forecasts', 'record_id': 'd' * 64, 'payload_sha256': 'e' * 64}
        saved = {'forecast_records': {gh.guard.PLAYERS[0]: {'reference': reference}}, 'input_reference': INPUT}
        with patch.object(gh.guard, 'recover', return_value=saved), patch.object(gh, 'Ledger') as ledger:
            ledger.return_value.read.return_value = {'data': {'bundle': {'prospective': {'generation_started_at': gh.stamp(NOW)}, 'issued_at': gh.stamp(NOW)}}}
            self.pilot.reject_ambiguous_intents()
        with patch.object(gh.guard, 'recover', return_value={**saved, 'input_reference': {**INPUT, 'record_id': 'd' * 64}}), self.assertRaises(gh.PilotError):
            self.pilot.reject_ambiguous_intents()

    def test_unreserved_original_or_later_contradictory_intent_blocks_automatic_recovery(self):
        player = gh.guard.PLAYERS[0]
        reference = {'kind': 'forecasts', 'record_id': 'd' * 64, 'payload_sha256': 'e' * 64}
        saved = {'forecast_records': {player: {'reference': reference}}, 'input_reference': INPUT}
        with patch.object(gh.guard, 'recover', return_value=saved), self.assertRaisesRegex(gh.PilotError, 'UNRESERVED'):
            self.pilot.reject_ambiguous_intents()
        self.pilot.receipt(f'intent-{gh.guard.CYCLE_ID}-{player}', {
            **phase('GENERATION_STARTED', player_id=player, model_version=gh.guard.producer.MODEL_VERSION), 'run_id': self.pilot.run_id})
        earlier = NOW.replace(minute=20)
        with patch.object(gh.guard, 'recover', return_value=saved), patch.object(gh, 'Ledger') as ledger:
            ledger.return_value.read.return_value = {'data': {'bundle': {'prospective': {'generation_started_at': gh.stamp(earlier)}, 'issued_at': gh.stamp(NOW)}}}
            with self.assertRaisesRegex(gh.PilotError, 'order changed'): self.pilot.reject_ambiguous_intents()

    def test_capture_intent_is_create_only_and_never_authorizes_second_capture(self):
        info = phase('CAPTURE_STARTED', input_reference=None, event_id='401909088', history_input_record_id=gh.guard.HISTORY_RECORD_ID)
        self.pilot.persist = Mock(); self.pilot.cycle_paths = Mock(return_value=[])
        self.pilot.checkpoint(info)
        with self.assertRaisesRegex(gh.PilotError, 'AMBIGUOUS_OPERATION'): self.pilot.checkpoint(info)

    def test_partial_input_recovery_preserves_first_checkpoint_and_accepts_retained_originals(self):
        info = phase('INPUT_BOUND', binding_path=f'evidence/cycles/{gh.guard.CYCLE_ID}-binding.json',
                     bound_at=gh.stamp(NOW), retained_forecast_references=[])
        recovered = {'input_reference': INPUT, 'clocks': {'bound_at': gh.stamp(NOW)}, 'forecast_records': {}}
        self.pilot.persist = Mock(); self.pilot.cycle_paths = Mock(return_value=[])
        with patch.object(gh.guard, 'recover', return_value=recovered): self.pilot.checkpoint(info)
        path = self.root / f'{gh.PREFIX}checkpoint-123-INPUT_BOUND-input.json'
        original = path.read_bytes()
        reference = {'kind': 'forecasts', 'record_id': 'd' * 64, 'payload_sha256': 'e' * 64}
        partial = {**recovered, 'forecast_records': {gh.guard.PLAYERS[0]: {'reference': reference}}}
        retry = {**info, 'retained_forecast_references': [reference]}
        with patch.object(gh.guard, 'recover', return_value=partial): self.pilot.checkpoint(retry)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.pilot.persist.call_count, 2)
        self.pilot.checkpoint(phase('GENERATION_STARTED', player_id=gh.guard.PLAYERS[1], model_version=gh.guard.producer.MODEL_VERSION))
        self.assertEqual(self.pilot.persist.call_count, 3)
        with patch.object(gh.guard, 'recover', return_value=partial), self.assertRaisesRegex(gh.PilotError, 'immutable binding'):
            self.pilot.checkpoint({**retry, 'bound_at': '2026-10-20T17:22:00.000000Z'})
        self.assertEqual(path.read_bytes(), original)

    def test_per_subject_push_failure_stops_next_generation_and_finalizes_partial(self):
        self.pilot.context = Mock(); self.pilot.workflow = Mock(); self.pilot.branch = Mock()
        self.pilot.pins = Mock()
        self.pilot.reject_ambiguous_intents = Mock(); self.pilot.cycle_paths = Mock(return_value=[])
        events = []
        def persist(_paths, name):
            events.append('PUSH_' + name)
            if name == 'FORECAST_RETAINED': raise gh.PilotError('push failed')
        self.pilot.persist = Mock(side_effect=persist)
        def run_cycle(*, root, checkpoint):
            for player in gh.guard.PLAYERS:
                checkpoint(phase('GENERATION_STARTED', player_id=player, model_version=gh.guard.producer.MODEL_VERSION))
                events.append('MATH_' + player)
                checkpoint(phase('FORECAST_RETAINED', player_id=player,
                                 forecast_reference={'kind': 'forecasts', 'record_id': 'd' * 64, 'payload_sha256': 'e' * 64}))
        with patch('multisport_lab.scheduled_cycle.run_cycle', side_effect=run_cycle): result = self.pilot.execute()
        self.assertEqual(result['status'], 'FAILED_OR_PARTIAL')
        self.assertEqual([event for event in events if event.startswith('MATH_')], ['MATH_' + gh.guard.PLAYERS[0]])
        self.assertLess(events.index('PUSH_GENERATION_STARTED'), events.index('MATH_' + gh.guard.PLAYERS[0]))
        self.assertIn('PUSH_FINAL_FAILED_OR_PARTIAL', events)

    def test_failed_intent_commit_retains_owned_derived_stage_and_finalizes(self):
        self.pilot.context = Mock(); self.pilot.workflow = Mock(); self.pilot.branch = Mock(); self.pilot.pins = Mock()
        self.pilot.reject_ambiguous_intents = Mock(); self.pilot.cycle_paths = Mock(return_value=[])
        self.pilot.remote_verify = Mock(return_value='a' * 40)
        staged, commits, math = set(), [], []
        def git(*args, **kwargs):
            if args == ('diff', '--cached', '--name-only'): return process('\n'.join(staged))
            if args[:2] == ('add', '--'): staged.update(args[2:]); return process()
            if args == ('diff', '--cached', '--quiet'): return process(returncode=int(bool(staged)))
            if args == ('ls-files', '-z'):
                return process('\0'.join(str(path.relative_to(self.root)) for path in self.root.rglob('*') if path.is_file()))
            if 'commit' in args:
                commits.append(args[-1])
                if len(commits) == 2: raise gh.PilotError('synthetic intent commit failure')
                staged.clear()
            return process()
        self.pilot.git = Mock(side_effect=git)
        def run_cycle(*, root, checkpoint):
            checkpoint(phase('GENERATION_STARTED', player_id=gh.guard.PLAYERS[0], model_version=gh.guard.producer.MODEL_VERSION))
            math.append('must never reach generation')
        with patch('multisport_lab.scheduled_cycle.run_cycle', side_effect=run_cycle): result = self.pilot.execute()
        self.assertEqual(result['status'], 'FAILED_OR_PARTIAL'); self.assertEqual(math, [])
        self.assertEqual(len(commits), 3); self.assertIn('FINAL_FAILED_OR_PARTIAL', commits[-1])
        self.assertFalse(staged); self.assertFalse(self.pilot._derived_pending)

    def test_safe_capture_metadata_only_raw_body_excluded(self):
        raw = self.root / '.local-data/pregame-cycle' / gh.guard.CYCLE_ID / 'raw'; raw.mkdir(parents=True)
        metadata = dict.fromkeys(['source_updated_at','source_response_generated_at','http_date','etag','last_modified'])
        metadata.update(source_id='summary', source_url=gh.PROBE_URLS[1], request_started_at=gh.stamp(NOW), observed_at=gh.stamp(NOW),
                        response_completed_at=gh.stamp(NOW), raw_sha256='a' * 64, raw_bytes=10, http_status=200)
        write_receipt(raw / 'summary.capture.json', metadata); (raw / 'summary.raw').write_bytes(b'private body')
        paths = self.pilot.source_metadata_paths()
        self.assertEqual(len(paths), 1); self.assertEqual(read_receipt(self.root / paths[0]), metadata)
        self.assertNotIn(b'private body', (self.root / paths[0]).read_bytes())

    def test_valid_late_unbound_input_is_retained_without_window_admission(self):
        plan = {'original_records_sha256': {}, 'event_id': '401909088', 'event_version': 'version',
                'selection_sha256': 'selection', 'selected_player_ids': gh.guard.PLAYERS}
        pack = {'event': {'event_id': '401909088'}, 'imported_at': '2026-10-20T17:31:00.000000Z'}
        view = {'event': {'event_version': 'version'}, 'selection_sha256': 'selection',
                'candidates': [{'player_id': player} for player in gh.guard.PLAYERS]}
        self.pilot.pins = Mock(return_value=plan); self.pilot.source_metadata_paths = Mock(return_value=[])
        with patch.object(gh, 'Ledger') as ledger, patch.object(gh, 'validate_pack', return_value=pack), \
             patch.object(gh, 'binding_view', return_value=view), patch.object(gh.guard.producer, '_check_pilot_history'), \
             patch.object(gh.guard, '_validate_input') as admit:
            ledger.return_value.scan.return_value = {'research_inputs': {'b' * 64: {'data': {'source_pack': pack}}}, 'forecasts': {}}
            paths = self.pilot.cycle_paths()
        self.assertEqual(paths, ['records/research_inputs/' + 'b' * 64 + '.json'])
        admit.assert_not_called()

    def test_draft_pr_403_retains_body_compare_url_and_actual_owner_prerequisite(self):
        self.pilot.context = Mock(); self.pilot.persist = Mock(); self.pilot.git = Mock(return_value=process(gh.BRANCH))
        self.pilot.read_workflow = Mock()
        self.pilot.receipt('capability-123', {'status': 'PASS'})
        self.pilot.api = Mock(side_effect=[[], gh.PilotError('HTTP 403: GitHub Actions cannot create PRs')])
        self.pilot.dispatch_validation = Mock(return_value={'status': 'completed', 'conclusion': 'success'})
        result = self.pilot.publication_pr(draft=True)
        self.assertEqual(result['status'], 'PR_CREATION_BLOCKED')
        self.assertEqual(result['exit_code'], 1)
        self.assertEqual(result['validation']['conclusion'], 'success')
        self.pilot.dispatch_validation.assert_called_once_with()
        self.assertFalse((self.root / f'{gh.PREFIX}publication-result-123-1.json').exists())
        body = (self.root / f'{gh.PREFIX}publication-123.md').read_text()
        self.assertIn('zero new forecasts', body)
        blocked = read_receipt(self.root / f'{gh.PREFIX}publication-blocked-123-1.json')
        self.assertIn('Allow GitHub Actions', blocked['owner_prerequisite'])

    def test_pr_403_stays_distinct_when_shared_validation_also_fails(self):
        self.pilot.context = Mock(); self.pilot.persist = Mock(); self.pilot.read_workflow = Mock()
        self.pilot.git = Mock(return_value=process(gh.BRANCH))
        self.pilot.receipt('capability-123', {'status': 'PASS'})
        self.pilot.api = Mock(side_effect=[[], gh.PilotError('HTTP 403: GitHub Actions cannot create PRs')])
        self.pilot.dispatch_validation = Mock(side_effect=gh.PilotError('HTTP 403: workflow dispatch denied'))
        result = self.pilot.publication_pr(draft=True)
        self.assertEqual(result['status'], 'PR_CREATION_BLOCKED')
        self.assertEqual(result['exit_code'], 1)
        self.assertIn('cannot create PRs', result['error'])
        self.assertEqual(result['validation']['status'], 'DISPATCH_BLOCKED')

    def test_new_publication_process_recovers_workflow_id_and_keeps_partial_draft(self):
        self.pilot.claim(); self.pilot.workflow_id = None
        self.pilot.receipt('report-123-1', {'status': 'PARTIAL', 'exit_code': 1})
        self.pilot.context = Mock(); self.pilot.persist = Mock(); self.pilot.git = Mock(return_value=process(gh.BRANCH))
        self.pilot.dispatch_validation = Mock(return_value={'status': 'completed', 'conclusion': 'success'})
        self.pilot.api = Mock(side_effect=[{'workflow_id': 99}, {'path': gh.WORKFLOW, 'state': 'disabled_manually'}, [],
            {'html_url': 'https://github.com/pull/1', 'draft': True}])
        result = self.pilot.publication_pr()
        self.assertEqual(self.pilot.workflow_id, 99)
        self.assertEqual(result['status'], 'DRAFT_PR_OPEN')
        self.assertTrue(self.pilot.api.call_args_list[3].args[2]['draft'])
        proof = read_receipt(self.root / f'{gh.PREFIX}publication-result-123-1.json')
        self.assertEqual(proof['operation'], 'CREATED')
        self.assertEqual(proof['pull_request_write'], 'VERIFIED')

    def test_existing_root_created_draft_proves_runner_update_only(self):
        self.pilot.context = Mock(); self.pilot.persist = Mock(); self.pilot.read_workflow = Mock()
        self.pilot.git = Mock(return_value=process(gh.BRANCH))
        self.pilot.dispatch_validation = Mock(return_value={'status': 'completed', 'conclusion': 'success'})
        self.pilot.receipt('capability-123', {'status': 'PASS'})
        existing = {'number': 8, 'head': {'ref': gh.BRANCH, 'repo': {'full_name': gh.REPOSITORY}}, 'base': {'ref': 'main'}}
        self.pilot.api = Mock(side_effect=[[existing], {'html_url': 'https://github.com/pull/8', 'draft': True}])
        result = self.pilot.publication_pr(draft=True)
        self.assertEqual(result['status'], 'DRAFT_PR_OPEN')
        self.assertEqual(self.pilot.api.call_args_list[1].args[:2], ('pulls/8', 'PATCH'))
        proof = read_receipt(self.root / f'{gh.PREFIX}publication-result-123-1.json')
        self.assertEqual(proof['operation'], 'UPDATED_EXISTING')
        self.assertEqual(proof['pull_request_write'], 'VERIFIED')
        self.assertNotIn('pull_request_creation', proof)

    def test_explicit_validation_dispatch_matches_actual_records_sha_and_never_merges(self):
        self.pilot.git = Mock(return_value=process('a' * 40))
        run = {'id': 987, 'head_branch': gh.BRANCH, 'head_sha': 'a' * 40, 'created_at': gh.stamp(NOW), 'status': 'completed',
               'conclusion': 'success', 'html_url': 'https://github.com/run/1'}
        self.pilot.api = Mock(side_effect=[{'workflow_runs': []}, {}, {'workflow_runs': [run]}])
        with patch.object(gh.time, 'monotonic', side_effect=[0, 1]): result = self.pilot.dispatch_validation()
        self.assertEqual(result['conclusion'], 'success')
        self.assertEqual(self.pilot.api.call_args_list[1].args, ('actions/workflows/pages.yml/dispatches', 'POST', {'ref': gh.BRANCH}))


if __name__ == '__main__': unittest.main()

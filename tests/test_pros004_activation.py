"""Inactive review-proposal regressions; no actual activation evidence."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import unittest
from unittest.mock import patch

from multisport_lab import pros004_activation as activation
from multisport_lab import pros004_inputs as inputs
from multisport_lab import pros004_producer as producer
from multisport_lab.integrity import IntegrityError, canonical, digest, stamp
from multisport_lab.ledger import LedgerRef
from test_pros004_inputs import event_fixture, board, observation, event_observations

CAPTURE = datetime(2026, 10, 20, 23, 45, tzinfo=timezone.utc)
REVIEW = CAPTURE + timedelta(minutes=1)
START = datetime(2026, 10, 21, 1, 30, tzinfo=timezone.utc)


def fixture():
    event = event_fixture(start=START)
    observations = [observation('schedule-'+day, f'{inputs.BASE}/scoreboard?dates={day}&limit=1000',
                    board([event] if day == '20261020' else []), observed=CAPTURE-timedelta(minutes=1))
                    for day in ('20261020', '20261021', '20261022')]
    current = event_observations(event)
    for name, item in current.items():
        src = item['source']
        for key in ('observed_at', 'response_completed_at'):
            src[key] = stamp(CAPTURE-timedelta(minutes=1))
        src['request_started_at'] = stamp(CAPTURE-timedelta(minutes=1, seconds=1))
        if name == 'scoreboard':
            src['source_url'] = f'{inputs.BASE}/scoreboard?dates=20261020'
    with patch.object(inputs, '_now', return_value=CAPTURE):
        schedule = inputs.make_schedule('2026-10-21', observations, mode='SYNTHETIC_DIAGNOSTIC')
        selection = inputs.make_selection(schedule, current)
        event_body = inputs.make_event_body(LedgerRef('research_inputs','c'*64,'d'*64),
            schedule, selection, current, mode='SYNTHETIC_DIAGNOSTIC')
    ref = LedgerRef('research_inputs','a'*64,'b'*64)
    binding = producer.make_source_binding(diagnostic=True)
    gates = {name:{'status':'PASS','evidence_lane':'SYNTHETIC_DIAGNOSTIC',
        'source_commit':binding['model_commit'],'evidence_sha256':digest(name),
        'observed_at':stamp(CAPTURE),'details':{}} for name in activation.GATES}
    gates['source_permission']['details'] = {'prospective_operations_authorized':True,
        'source_reviewed':True,'review_reference':'Synthetic policy fixture, no actual permission claim'}
    gates['raw_retention']['details'] = {'private_backend_verified':True,'independent_readback':True,
                                        'outcome_linkage_verified':True}
    gates['end_to_end_timing']['details'] = {'cohort_seconds':1,'max_generation_through_ack_seconds':1,
        'all_required_acknowledgments_included':True,'realistic_ledger_verified':True}
    proposal = activation.proposal_template(source_binding=binding,event_ref=ref,
        gate_evidence=gates,recorded_at=stamp(CAPTURE))
    review = {'source_commit':binding['model_commit'],'proposal_id':proposal['proposal_id'],
        'reviewed_at':stamp(REVIEW),'independent_review':True,'review_reference':'Synthetic independent reviewer'}
    remote = {'repository':'NickNicky19/Nicks-multisport-lab-project',
        'source_commit':binding['model_commit'],'records_commit':'e'*40,
        'proposal_id':proposal['proposal_id'],'proposal_payload_sha256':digest(proposal),
        'readback_completed_at':stamp(REVIEW),'independent_fetch':True}
    return proposal, dict(store=SimpleNamespace(body=lambda _:event_body),source_binding=binding,
                          review=review,remote_readback=remote,diagnostic=True)


def reseal(proposal, context):
    proposal['proposal_id'] = digest({k:v for k,v in proposal.items() if k != 'proposal_id'})
    context['review']['proposal_id'] = proposal['proposal_id']
    context['remote_readback']['proposal_id'] = proposal['proposal_id']
    context['remote_readback']['proposal_payload_sha256'] = digest(proposal)


class Pros004ActivationTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack(); self.addCleanup(stack.close)
        stack.enter_context(patch.object(inputs,'_now',return_value=REVIEW))
        self.clock = stack.enter_context(patch.object(activation,'_now',return_value=REVIEW))

    def test_full_synthetic_proposal_validates_without_any_activation_effect(self):
        proposal, context = fixture()
        result = activation.validate_review_candidate(proposal,**context)
        self.assertEqual(result['status'],'VALIDATED_NOT_ACTIVE')
        self.assertEqual(result['activation'],'INACTIVE')
        self.assertFalse(result['genuine_issuance_authorized'])
        self.assertLess(len(canonical(proposal)),7*1024)
        for flag in (None,True,proposal):
            with self.assertRaisesRegex(IntegrityError,'READINESS_ONLY'):
                activation.require_operating_activation(flag)

    def test_caller_active_flag_and_unknown_fields_cannot_activate(self):
        for key,value in (('status','ACTIVE'),('approved',True)):
            proposal, context = fixture(); proposal[key] = value; reseal(proposal,context)
            with self.assertRaises(IntegrityError):
                activation.validate_review_candidate(proposal,**context)

    def test_review_and_readback_share_one_bounded_metadata_slot(self):
        proposal, context = fixture()
        package = activation.review_package(proposal, **context)
        self.assertEqual(package['status'], 'VALIDATED_NOT_ACTIVE')
        self.assertLessEqual(len(canonical(package)), activation.MAX_PACKAGE_BYTES)
        self.assertFalse(package['validation']['genuine_issuance_authorized'])
        context['review']['review_reference'] = 'x' * 513
        with self.assertRaises(IntegrityError):
            activation.review_package(proposal, **context)

    def test_missing_permission_raw_backend_or_ack_timing_is_not_readiness(self):
        for name,key in (('source_permission','prospective_operations_authorized'),
                         ('raw_retention','private_backend_verified'),
                         ('end_to_end_timing','all_required_acknowledgments_included')):
            proposal,context=fixture();proposal['gates'][name]['details'][key]=False;reseal(proposal,context)
            with self.assertRaises(IntegrityError):
                activation.validate_review_candidate(proposal,**context)
        proposal,context=fixture();proposal['gates'].pop('history_lineage');reseal(proposal,context)
        with self.assertRaisesRegex(IntegrityError,'evidence gates'):
            activation.validate_review_candidate(proposal,**context)

    def test_wrong_review_source_or_remote_payload_or_independence_fails(self):
        for target,key,value in (('review','source_commit','f'*40),
                                ('remote_readback','proposal_payload_sha256','f'*64),
                                ('remote_readback','independent_fetch',False)):
            proposal,context=fixture();context[target][key]=value
            with self.assertRaises(IntegrityError):
                activation.validate_review_candidate(proposal,**context)

    def test_late_or_future_remote_review_clocks_reject_original_window(self):
        proposal,context=fixture()
        context['remote_readback']['readback_completed_at']=stamp(START)
        with self.assertRaisesRegex(IntegrityError,'before first actual T90'):
            activation.validate_review_candidate(proposal,**context)
        self.clock.return_value=START
        with self.assertRaisesRegex(IntegrityError,'cutoff passed'):
            activation.validate_review_candidate(proposal,**context)

    def test_complete_inventory_and_exact_clock_policy_cannot_be_bypassed(self):
        proposal,context=fixture()
        proposal['clock_policy']['remote_readback_required']=1;reseal(proposal,context)
        with self.assertRaisesRegex(IntegrityError,'clock policy'):
            activation.validate_review_candidate(proposal,**context)
        proposal,context=fixture();context['store'].body(None)['schedule']['source_proofs'][0]['pagination']=None
        with self.assertRaises(IntegrityError):
            activation.validate_review_candidate(proposal,**context)

    def test_diagnostic_evidence_cannot_validate_as_operational(self):
        proposal,context=fixture();context['diagnostic']=False
        with self.assertRaises(IntegrityError):
            activation.validate_review_candidate(proposal,**context)

    def test_optimized_python_preserves_operational_guard(self):
        result = subprocess.run([sys.executable,'-O','-c',
            'from multisport_lab.pros004_activation import require_operating_activation; require_operating_activation(True)'],
            capture_output=True,text=True,cwd=Path(__file__).resolve().parents[1])
        self.assertNotEqual(result.returncode,0);self.assertIn('READINESS_ONLY',result.stderr)


if __name__ == '__main__':
    unittest.main()

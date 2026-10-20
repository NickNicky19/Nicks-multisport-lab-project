"""Synthetic independent verification risks; no source capture or model scoring."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1]/'scripts/verify_pros004_readiness.py'
spec = importlib.util.spec_from_file_location('verify_pros004_readiness',SCRIPT)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def receipt(path,payload):
    envelope={'schema_version':'decoded-json-receipt-v1',
        'hash_format':'sha256-canonical-decoded-json-v1',
        'payload_sha256':verifier.fingerprint(payload),'payload':payload}
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(verifier.canonical(envelope))


def report(root):
    sources={}
    for name in verifier.NEW_PRODUCER_FILES:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('synthetic source\n')
        sources[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    return {'schema_version':verifier.SCHEMA,'mode':'READINESS_DIAGNOSTIC_NON_ISSUANCE',
        'evidence':{'live_source_captures':0,'genuine_issuance':0,'statistical_grades':0,
            'aggregate_comparison_executions':0,'activation':False},'source_sha256':sources,
        'history':{'rows':26645,'events':1231,'normalized_bytes':14720351,
            'sha256':verifier.HISTORY_SHA256,'encoded_envelope_bytes':1800000},
        'retention':{'max_records':512,'max_bytes':33554432,'comparison_records':442,
            'baseline_and_pilot_records':32,'metadata_records':38,'projected_records':512,
            'projected_bytes':22487040},
        'diagnostics':{model:{'forecast_envelope_bytes':40000,'support_count':26645,
            'restored_support_count':26645,'category_count':14,
            'joint_sha256':'a'*64,'restored_joint_sha256':'a'*64} for model in ('R0','K0')}}


def payload(kind,logical,data,refs=(),clock='2026-10-20T00:00:00.000000Z'):
    identity=verifier.fingerprint({'kind':kind,'logical_id':logical})
    return {'schema_version':'multisport-research-ledger-v1','kind':kind,'record_id':identity,
        'logical_id':logical,'received_at':clock,'data':data,'references':list(refs),
        'supersedes':None,'persistence_status':'LOCAL_RECEIPT_ONLY'}


def save(root,value):
    receipt(root/'records'/value['kind']/(value['record_id']+'.json'),value)


def complete_forecast_store(root):
    """Independent invented envelopes, without calling a producer or scoring."""
    def reference(value):
        return {'kind':value['kind'],'record_id':value['record_id'],
                'payload_sha256':verifier.fingerprint(value)}
    mode='SYNTHETIC_TEST'
    history=payload('research_inputs','history',{'identity':{},'pros004':{
        'schema_version':'nba-pros004-history-v1','mode':mode,'history':{}}})
    save(root,history);history_ref=reference(history)
    facts={'event_id':'700','event_version':'e'*64,'event_starts_at':'2026-10-21T02:00:00.000000Z'}
    candidate={'player_id':'10','team_id':'1','opponent_id':'2','player_label':'Synthetic athlete'}
    event=payload('research_inputs','event',{'identity':{},'pros004':{
        'schema_version':'nba-pros004-event-v1','mode':mode,'event':facts,'history_ref':history_ref,
        'candidates':[candidate]}},[history_ref])
    save(root,event);event_ref=reference(event)
    binding={'source':'invented unchanged source reference'}
    claim=payload('input_captures','claim',{'identity':{},'pros004':{
        'schema_version':'nba-pros004-event-claim-v1','mode':mode,'event_ref':event_ref,
        'history_ref':history_ref,'producer_identity':binding}},[event_ref])
    save(root,claim);claim_ref=reference(claim)
    pmf=[{'value':0,'probability':'1'}]
    body={'schema_version':'nba-pros004-forecast-v1','mode':mode,'model_key':'R0',
        'model_version':verifier.MODEL_VERSIONS['R0'],'producer_version':'pros004-r0-producer-v1',
        'conditioning':'CONDITIONAL_ON_APPEARANCE','qualification':'UNAVAILABLE',
        'event_ref':event_ref,'history_ref':history_ref,'producer_binding':binding,
        **facts,**candidate,'cutoff_at':'2026-10-21T00:30:00.000000Z',
        'history_freeze':'2026-10-21T00:00:00.000000Z','trained_through':'2026-04-13T00:00:00.000000Z',
        'generation_started_at':'2026-10-21T00:30:01.000000Z',
        'generation_completed_at':'2026-10-21T00:30:02.000000Z',
        'verified_at':'2026-10-21T00:30:03.000000Z','issued_at':'2026-10-21T00:30:03.000000Z',
        'categories':[{'code':code,'pmf':deepcopy(pmf),'mean':'0'} for code in sorted(verifier.MARKETS)],
        'reported_minutes':{'pmf':[{'value':20,'probability':'1'}]},
        'joint_recipe':{'history_ref':history_ref,'event_ref':event_ref,'omitted_atoms':0,
            'support_atom_count':1,'pool_history_count':1,'joint_sha256':'a'*64,'input_sha256':'b'*64}}
    body['forecast_id']=verifier.fingerprint(body)
    forecast=payload('forecasts','original',{'identity':{},'pros004':body},[event_ref,history_ref,claim_ref],
        clock='2026-10-21T00:30:04.000000Z')
    save(root,forecast)
    return forecast


class Pros004VerifierTests(unittest.TestCase):
    def test_report_detects_changed_input_atoms_source_and_capacity(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=report(root)
            with patch.object(verifier,'PINNED_SOURCE_HASHES',{}):
                self.assertEqual(verifier.verify_readiness(base,root)['status'],'PASS_INDEPENDENT_READINESS_CHECK')
                for change in ('history','atoms','joint','categories','records','bytes','understated_bytes','activation'):
                    bad=deepcopy(base)
                    if change=='history':bad['history']['rows']=20000
                    if change=='atoms':bad['diagnostics']['K0']['restored_support_count']=26644
                    if change=='joint':bad['diagnostics']['R0']['restored_joint_sha256']='b'*64
                    if change=='categories':bad['diagnostics']['K0']['category_count']=13
                    if change=='records':bad['retention']['projected_records']=513
                    if change=='bytes':bad['retention']['projected_bytes']=33554433
                    if change=='understated_bytes':bad['retention']['projected_bytes']=1
                    if change=='activation':bad['evidence']['activation']=True
                    with self.subTest(change=change),self.assertRaises(verifier.VerificationError):
                        verifier.verify_readiness(bad,root)
                (root/verifier.NEW_PRODUCER_FILES[0]).write_text('changed source\n')
                with self.assertRaisesRegex(verifier.VerificationError,'fingerprint changed'):
                    verifier.verify_readiness(base,root)

    def test_frozen_pin_change_is_not_masked_by_matching_mutable_report_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=report(root);fixed=root/'fixed.py';fixed.write_bytes(b'original')
            expected=hashlib.sha256(fixed.read_bytes()).hexdigest()
            with patch.object(verifier,'PINNED_SOURCE_HASHES',{'fixed.py':expected}):
                verifier.verify_readiness(base,root)
                fixed.write_bytes(b'changed')
                with self.assertRaisesRegex(verifier.VerificationError,'frozen source changed'):
                    verifier.verify_readiness(base,root)

    def test_receipt_hash_duplicate_keys_and_nonfinite_json_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'receipt.json';receipt(path,{'value':1})
            self.assertEqual(verifier.load_receipt(path)[0],{'value':1})
            content=json.loads(path.read_text());content['payload']['value']=2;path.write_text(json.dumps(content))
            with self.assertRaisesRegex(verifier.VerificationError,'content hash'):
                verifier.load_receipt(path)
            for raw in ('{"a":1,"a":2}','{"value":NaN}','{"value":1e999}'):
                path.write_text(raw)
                with self.assertRaises(verifier.VerificationError):verifier.load_receipt(path)

    def test_store_references_and_encoded_forecast_ceiling_are_independent(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=payload('research_inputs','history',{'identity':{},'pros004':{
                'schema_version':'nba-pros004-history-v1','mode':'SYNTHETIC_TEST','history':{}}})
            save(root,source)
            ref={'kind':'research_inputs','record_id':source['record_id'],
                 'payload_sha256':verifier.fingerprint(source)}
            forecast=payload('input_captures','original',{'identity':{},'pros004':{
                'schema_version':'nba-pros004-failure-v1','mode':'SYNTHETIC_TEST'}},[ref])
            save(root,forecast)
            checked=verifier.verify_store(root);self.assertEqual(checked['records'],2)
            bad=deepcopy(forecast);bad['references'][0]['payload_sha256']='f'*64;save(root,bad)
            with self.assertRaisesRegex(verifier.VerificationError,'referenced content'):
                verifier.verify_store(root)
            bad=deepcopy(forecast);bad['data']['pros004']['padding']='x'*(8*1024);save(root,bad)
            with self.assertRaisesRegex(verifier.VerificationError,'envelope ceiling'):
                verifier.verify_store(root)

    def test_unpublished_receipt_and_global_capacity_and_live_lane_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            item=payload('forecasts','original',{'identity':{},'pros004':{
                'schema_version':'nba-pros004-forecast-v1','mode':'SYNTHETIC_TEST'}})
            save(root,item)
            with patch.object(verifier,'MAX_RECORDS',0),self.assertRaisesRegex(verifier.VerificationError,'capacity'):
                verifier.verify_store(root)
            item['data']['pros004']['mode']='REAL_TIME_CAPTURED';save(root,item)
            with self.assertRaisesRegex(verifier.VerificationError,'unmarked/live'):
                verifier.verify_store(root)
            item['data']['pros004']['mode']='SYNTHETIC_TEST';save(root,item)
            (root/'records'/'forecasts'/'.receipt-interrupted').write_bytes(b'partial')
            with self.assertRaisesRegex(verifier.VerificationError,'interrupted'):
                verifier.verify_store(root)

    def test_optimized_python_cannot_disable_activation_or_integrity_guards(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);value=report(root);value['evidence']['activation']=True
            path=root/'not-activation.json';receipt(path,value)
            run=subprocess.run([sys.executable,'-O',str(SCRIPT),'--report',str(path),'--root',str(root)],
                capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0)
            self.assertIn('activation is not authorized',run.stderr)
            self.assertNotIn('AssertionError',run.stderr)

    def test_independent_forecast_clocks_identity_coherence_and_complete_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=complete_forecast_store(root)
            self.assertEqual(verifier.verify_store(root)['independently_checked_forecast_contracts'],1)
            for change in ('late','latency','identity','cutoff','categories','mean','atoms','binding'):
                bad=deepcopy(base);body=bad['data']['pros004']
                if change=='late':bad['received_at']='2026-10-21T00:35:00.000001Z'
                if change=='latency':bad['received_at']='2026-10-21T00:32:02.000000Z'
                if change=='identity':body['team_id']='3'
                if change=='cutoff':body['cutoff_at']='2026-10-21T00:31:00.000000Z'
                if change=='categories':body['categories'].pop()
                if change=='mean':body['categories'][0]['mean']='1'
                if change=='atoms':body['joint_recipe']['omitted_atoms']=1
                if change=='binding':body['producer_binding']={'different':'revision'}
                body['forecast_id']=verifier.fingerprint({k:v for k,v in body.items() if k!='forecast_id'})
                save(root,bad)
                with self.subTest(change=change),self.assertRaises(verifier.VerificationError):
                    verifier.verify_store(root)
            save(root,base)
            bad=deepcopy(base);bad['received_at']='2026-10-21T00:35:00.000001Z';save(root,bad)
            run=subprocess.run([sys.executable,'-O',str(SCRIPT),'--store-root',str(root)],capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0)
            self.assertIn('clocks violate T90 window',run.stderr)
            self.assertNotIn('AssertionError',run.stderr)


if __name__=='__main__':
    unittest.main()

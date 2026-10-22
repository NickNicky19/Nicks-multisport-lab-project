"""Synthetic independent verification risks; no source capture or model scoring."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
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
    from multisport_lab.pros004_producer import make_source_binding
    sources={}
    for name in verifier.NEW_PRODUCER_FILES:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes((SCRIPT.parents[1]/name).read_bytes())
        sources[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    return {'schema_version':verifier.SCHEMA,'mode':'READINESS_DIAGNOSTIC_NON_ISSUANCE',
        'evidence':{'live_source_captures':0,'genuine_issuance':0,'statistical_grades':0,
            'aggregate_comparison_executions':0,'activation':False},'source_sha256':sources,
        'producer_binding':make_source_binding(diagnostic=True),
        'history':{'rows':26645,'events':1231,'normalized_bytes':14720351,
            'sha256':verifier.HISTORY_SHA256,'encoded_envelope_bytes':1800000},
        'retention':{'max_records':512,'max_bytes':33554432,'comparison_records':442,
            'baseline_and_pilot_records':32,'metadata_records':38,'projected_records':512,
            'projected_bytes':24576000,'metadata_encoded_ceiling_bytes':3145728},
        'diagnostic_status':'PASS','operation_failure':None,
        'event_input':{'final_checkpoint':{'timely':True},
            'admission_ref':{'kind':'input_captures','record_id':'a'*64,'payload_sha256':'b'*64},
            'admission_encoded_envelope_bytes':6500,
            'admission_final_checkpoint':{'timely':True,'references':[
                {'kind':'input_captures','record_id':'a'*64,'payload_sha256':'b'*64}]}},
        'recovery':{'retained_models':8,'timing_complete_models':8,'eligible_models':0,
            'remote_recovery':True,'github_recovery':False,'transport':'ISOLATED_LOCAL_BARE_GIT',
            'original_probabilities_and_clocks_preserved':True,'final_checkpoint':{'timely':True},
            'input_admission_recovered':True},
        'diagnostics':{model:{'forecast_envelope_bytes':40000,'support_count':26645,
            'restored_support_count':26645,'category_count':14,
            'model_version':verifier.MODEL_VERSIONS[model],
            'producer_version':'pros004-'+model.lower()+'-producer-v3',
            'joint_sha256':'a'*64,'restored_joint_sha256':'a'*64} for model in ('R0','K0')}}


def payload(kind,logical,data,refs=(),clock='2026-10-20T00:00:00.000000Z'):
    identity=verifier.fingerprint({'kind':kind,'logical_id':logical})
    return {'schema_version':'multisport-research-ledger-v1','kind':kind,'record_id':identity,
        'logical_id':logical,'received_at':clock,'data':data,'references':list(refs),
        'supersedes':None,'persistence_status':'LOCAL_RECEIPT_ONLY'}


def save(root,value):
    receipt(root/'records'/value['kind']/(value['record_id']+'.json'),value)


def complete_forecast_store(root, case):
    """Valid synthetic typed records; successful recovery never uses a fake schema."""
    from test_pros004_producer import ProducerFixture
    from multisport_lab import pros004_producer as producer
    from multisport_lab.integrity import read_receipt
    f=ProducerFixture(case)
    claim,_=f.store.claim_event(f.event_ref,f.binding)
    refs=[]
    for model in ('R0','K0'):
        body,_=f.generate(model)
        refs.append(f.store.persist_forecast(body,f.event_ref,f.history_ref,claim))
    shutil.copytree(Path(f.tmp)/'records',root/'records',dirs_exist_ok=True)
    # A journal is retained when the revised store supplies it. Missing legacy
    # proof is valid evidence recovery, never timely issuance admission.
    journal=Path(f.tmp)/'evidence/pros004/completion-journal.jsonl'
    if journal.exists():
        target=root/'evidence/pros004/completion-journal.jsonl'
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(journal,target)
    return read_receipt(f.store.ledger._path(refs[0].kind,refs[0].record_id))


def typed_fixture(case):
    from test_pros004_producer import ProducerFixture
    f=ProducerFixture(case)
    claim,_=f.store.claim_event(f.event_ref,f.binding)
    refs=[]
    for model in ('R0','K0'):
        body,_=f.generate(model)
        refs.append(f.store.persist_forecast(body,f.event_ref,f.history_ref,claim))
    return f,refs


def copy_for_semantic_mutation(source,root):
    """Keep the immutable input proof, without unrelated later completion seals.

    Deliberate test mutations must exercise typed meanings rather than simply
    breaking a later receipt's raw-byte seal. Missing later ACK evidence never
    grants timing admission.
    """
    from multisport_lab.integrity import read_receipt
    source=Path(source);root=Path(root)
    shutil.copytree(source/'records',root/'records')
    target_hash=None
    for path in (source/'records/input_captures').glob('*.json'):
        body=read_receipt(path)['data'].get('pros004',{})
        if body.get('schema_version')=='nba-pros004-event-claim-v2':
            target_hash=body['input_final_checkpoint']['journal_raw_sha256'];break
    if target_hash is not None:
        prefix=bytearray()
        for line in (source/'evidence/pros004/completion-journal.jsonl').read_bytes().splitlines(keepends=True):
            prefix.extend(line)
            if hashlib.sha256(prefix).hexdigest()==target_hash:
                target=root/'evidence/pros004/completion-journal.jsonl'
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(prefix)
                break
        else:raise RuntimeError('Synthetic fixture lost its original input proof')


def replace_typed_receipt(root,original,body,refs=None):
    """Re-seal all relevant identities, so meaning—not a broken checksum—fails."""
    from multisport_lab import pros004_records as rec
    root=Path(root);value=deepcopy(original)
    id_key={'nba-pros004-outcome-v1':'outcome_id','nba-pros004-grade-v1':'grade_id',
            'nba-pros004-event-v1':'sourcepack_id','nba-pros004-history-v1':'history_id'}.get(body['schema_version'])
    if id_key:body[id_key]=verifier.fingerprint({k:v for k,v in body.items() if k!=id_key})
    value['data']={'identity':rec._identity(body),'pros004':body}
    value['logical_id']=rec._logical(body)
    value['record_id']=verifier.fingerprint({'kind':value['kind'],'logical_id':value['logical_id']})
    if refs is not None:value['references']=refs
    oldpath=root/'records'/original['kind']/(original['record_id']+'.json')
    oldpath.unlink();save(root,value)
    return value


class Pros004VerifierTests(unittest.TestCase):
    def test_verified_index_is_private_reference_bound_and_returns_isolated_copies(self):
        from multisport_lab.pros004_records import _Pros004Ledger
        from multisport_lab.ledger import LedgerRef
        with tempfile.TemporaryDirectory() as folder:
            original=payload('input_captures','index-isolation',{'note':'Original immutable evidence',
                'nested':[{'values':[None,True,False,2**100,0.0,-0.0,0.1,'NBA é\n']} ]})
            key=(original['kind'],original['record_id']);sha=verifier.fingerprint(original)
            ledger=_Pros004Ledger(folder)
            index=verifier._VerifiedRecordIndex({key:original},{key:sha},ledger)
            reference=LedgerRef(*key,sha)
            with patch.object(ledger,'read',side_effect=index.read),patch.object(ledger,'_validate_payload',wraps=ledger._validate_payload) as generic:
                returned=index.read(reference);returned['data']['note']='Caller mutation'
                returned['data']['nested'][0]['values'].append('Nested caller mutation')
                self.assertEqual(index.read(reference),original)
                self.assertEqual(verifier.canonical(index.read(reference)),verifier.canonical(original))
                self.assertEqual(generic.call_count,1)
                with self.assertRaisesRegex(verifier.VerificationError,'identity/hash'):
                    index.read(LedgerRef(*key,'f'*64))
            # Mutating the caller's source map cannot contaminate the private
            # snapshot; a private-cache mutation itself must fail its final seal.
            original['data']['note']='Changed outer index'
            self.assertEqual(index.read(reference)['data']['note'],'Original immutable evidence')
            index.verify_unchanged()
            index._VerifiedRecordIndex__payloads[key]['data']['note']='Invalid private mutation'
            with self.assertRaisesRegex(verifier.VerificationError,'index changed'):
                index.verify_unchanged()
            with self.assertRaisesRegex(verifier.VerificationError,'index changed'):
                verifier._VerifiedRecordIndex({key:original},{key:sha},ledger)

    def test_verified_index_rejects_replaced_encoded_bytes_and_encoded_budget(self):
        from multisport_lab.pros004_records import _Pros004Ledger
        from multisport_lab.ledger import LedgerRef
        with tempfile.TemporaryDirectory() as folder:
            item=payload('input_captures','encoded-index',{'note':'Strict original bytes'})
            key=(item['kind'],item['record_id']);sha=verifier.fingerprint(item)
            index=verifier._VerifiedRecordIndex({key:item},{key:sha},_Pros004Ledger(folder))
            changed=deepcopy(item);changed['data']['note']='Checksum-consistent different meaning'
            index._VerifiedRecordIndex__encoded[key]=verifier.canonical(changed)
            with self.assertRaisesRegex(verifier.VerificationError,'canonical bytes changed'):
                index.read(LedgerRef(*key,sha))
            with self.assertRaisesRegex(verifier.VerificationError,'index changed'):
                index.verify_unchanged()
            with patch.object(verifier,'MAX_BYTES',1):
                with self.assertRaisesRegex(verifier.VerificationError,'index changed'):
                    verifier._VerifiedRecordIndex({key:item},{key:sha},_Pros004Ledger(folder))

    def test_semantic_scope_keeps_all_pros004_and_referenced_parents_without_legacy_reexecution(self):
        from multisport_lab import pros004_records as records
        from multisport_lab import pregame_sources
        from test_pros004_producer import ProducerFixture,ISSUE
        from test_pregame_sources import pack_fixture,tiny_history,NOW as LEGACY_CLOCK
        f=ProducerFixture(self,prepare_admission=False)
        # This checksum-consistent stand-in is deliberately unreferenced and
        # subject only to the original independent generic checks. It is not
        # presented as a semantically validated historical input package.
        f.stack.enter_context(patch.object(pregame_sources,'PANEL_SHA',
            hashlib.sha256(pregame_sources._panel_bytes(tiny_history())).hexdigest()))
        with patch.object(pregame_sources,'_now',return_value=LEGACY_CLOCK):
            legacy_pack=pack_fixture()
        legacy=payload('research_inputs','research-inputs:'+verifier.fingerprint(legacy_pack),
            {'source_pack':legacy_pack},clock=legacy_pack['imported_at'])
        save(Path(f.tmp),legacy)
        # Establish the input proof after this baseline already exists. Adding
        # a backdated original after the proof would correctly change its hash.
        capture_clock=verifier._time(f.event['imported_at'])+timedelta(microseconds=2)
        f.record_clock.return_value=capture_clock;f.ledger_clock.return_value=capture_clock
        phase=f.store.finalize_checkpoint((f.event_ref,),f.ack)
        f.record_clock.return_value=capture_clock+timedelta(microseconds=1)
        f.ledger_clock.return_value=f.record_clock.return_value
        claim,_=f.store.claim_event(f.event_ref,f.binding,input_final_checkpoint=phase)
        f.store.complete_checkpoint(claim,f.ack)
        f.store.finalize_checkpoint((claim,),f.ack)
        f.record_clock.return_value=ISSUE;f.ledger_clock.return_value=ISSUE
        for model in ('R0','K0'):
            body,_=f.generate(model)
            f.store.persist_forecast(body,f.event_ref,f.history_ref,claim)
        actual=records._Pros004Ledger._validate_payload;calls=[]
        def generic(ledger,body,*,kind,record_id):
            calls.append((kind,record_id))
            return actual(ledger,body,kind=kind,record_id=record_id)
        with patch.object(records._Pros004Ledger,'_validate_payload',generic),patch(
                'multisport_lab.pregame_sources.validate_pack',side_effect=RuntimeError('Unrelated legacy reexecution')):
            result=verifier.verify_store(f.tmp)
        semantics=result['strict_typed_semantics']
        self.assertEqual(semantics['legacy_semantic_scope'],'REFERENCED_PARENTS_ONLY')
        self.assertEqual(semantics['generic_records_read'],len(set(calls)))
        self.assertNotIn(('research_inputs',legacy['record_id']),calls)
        self.assertEqual(calls.count((f.history_ref.kind,f.history_ref.record_id)),1)
        self.assertEqual(calls.count((f.event_ref.kind,f.event_ref.record_id)),1)
        self.assertEqual(result['independently_checked_forecast_contracts'],2)
        # Scoping out unrelated legacy semantics cannot exempt a newly marked
        # PROS004 outcome, including one with internally consistent checksums.
        malformed=payload('outcomes','new-invalid-pros004-scope',{'identity':{},'pros004':{
            'schema_version':'nba-pros004-outcome-v1','mode':'SYNTHETIC_DIAGNOSTIC','status':'ALIEN'}})
        save(Path(f.tmp),malformed)
        with self.assertRaisesRegex(verifier.VerificationError,'strict typed'):
            verifier.verify_store(f.tmp)

    def test_standalone_store_rejects_source_mutation_after_indexed_semantics(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);item=payload('input_captures','concurrent-source',{'note':'Preserve original'})
            save(root,item);path=root/'records'/item['kind']/(item['record_id']+'.json')
            actual=verifier._strict_semantics
            def mutate_after_semantics(*args):
                result=actual(*args)
                envelope=json.loads(path.read_bytes())
                path.write_bytes(json.dumps(dict(reversed(list(envelope.items()))),
                    separators=(',',':'),ensure_ascii=False,allow_nan=False).encode())
                return result
            with patch.object(verifier,'_strict_semantics',side_effect=mutate_after_semantics):
                with self.assertRaisesRegex(verifier.VerificationError,'source raw bytes changed'):
                    verifier.verify_store(root)

    def test_optimized_standalone_verifier_rejects_source_mutation_after_semantics(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);item=payload('input_captures','optimized-concurrent-source',{'note':'Preserve original'})
            save(root,item)
            source="""import json
from pathlib import Path
from unittest.mock import patch
from scripts import verify_pros004_readiness as v
root=Path(%r)
original=v._strict_semantics
def mutate(*args):
    result=original(*args)
    path=next(root.glob('records/*/*.json'))
    value=json.loads(path.read_bytes())
    path.write_bytes(json.dumps(dict(reversed(list(value.items()))),separators=(',',':')).encode())
    return result
with patch.object(v,'_strict_semantics',side_effect=mutate):
    v.verify_store(root)
""" % str(root)
            run=subprocess.run([sys.executable,'-O','-c',source],cwd=SCRIPT.parents[1],capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0)
            self.assertIn('source raw bytes changed',run.stderr)
            self.assertNotIn('AssertionError',run.stderr)

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

    def test_completion_aware_report_requires_execution_recovery_pins_and_legacy_stays_readable(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=report(root)
            with patch.object(verifier,'PINNED_SOURCE_HASHES',{}):
                for source in ('multisport_lab/pros004_completion.py','multisport_lab/pros004_activation.py',
                        'multisport_lab/pros004_remote.py','multisport_lab/pros004_raw.py',
                        'multisport_lab/pros004_readiness.py','multisport_lab/pros004_snapshot.py',
                        'scripts/verify_pros004_readiness.py'):
                    bad=deepcopy(base);del bad['source_sha256'][source]
                    with self.subTest(source=source),self.assertRaisesRegex(verifier.VerificationError,'source references missing'):
                        verifier.verify_readiness(bad,root)
                bad=deepcopy(base);bad['retention']['projected_bytes']=22487040
                bad['retention']['metadata_encoded_ceiling_bytes']=1056768
                with self.assertRaisesRegex(verifier.VerificationError,'completion-aware capacity'):
                    verifier.verify_readiness(bad,root)
                legacy=deepcopy(bad);legacy['schema_version']=verifier.LEGACY_SCHEMA
                legacy['source_sha256']={name:legacy['source_sha256'][name] for name in verifier.LEGACY_PRODUCER_FILES}
                self.assertEqual(verifier.verify_readiness(legacy,root)['planned_bytes'],22487040)

    def test_v2_read_policy_does_not_gain_v3_durable_input_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);legacy=report(root)
            legacy['schema_version']=verifier.PREVIOUS_SCHEMA
            legacy['producer_binding']['schema_version']='nba-pros004-source-binding-v2'
            for model in ('R0','K0'):
                legacy['diagnostics'][model]['producer_version']='pros004-'+model.lower()+'-producer-v2'
            for key in ('admission_ref','admission_encoded_envelope_bytes','admission_final_checkpoint'):
                del legacy['event_input'][key]
            del legacy['recovery']['input_admission_recovered']
            with patch.object(verifier,'PINNED_SOURCE_HASHES',{}):
                self.assertEqual(verifier.verify_readiness(legacy,root)['status'],'PASS_INDEPENDENT_READINESS_CHECK')
                legacy['schema_version']=verifier.SCHEMA
                legacy['producer_binding']['schema_version']='nba-pros004-source-binding-v3'
                for model in ('R0','K0'):
                    legacy['diagnostics'][model]['producer_version']='pros004-'+model.lower()+'-producer-v3'
                with self.assertRaisesRegex(verifier.VerificationError,'durable input admission'):
                    verifier.verify_readiness(legacy,root)

    def test_v3_requires_durable_original_input_admission_and_unchanged_ceiling(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=report(root)
            with patch.object(verifier,'PINNED_SOURCE_HASHES',{}):
                for change in ('missing','identity','bytes','late','wrong-reference','not-recovered'):
                    bad=deepcopy(base)
                    if change=='missing':del bad['event_input']['admission_ref']
                    if change=='identity':bad['event_input']['admission_ref']['payload_sha256']='invalid'
                    if change=='bytes':bad['event_input']['admission_encoded_envelope_bytes']=8193
                    if change=='late':bad['event_input']['admission_final_checkpoint']['timely']=False
                    if change=='wrong-reference':bad['event_input']['admission_final_checkpoint']['references']=[]
                    if change=='not-recovered':bad['recovery']['input_admission_recovered']=False
                    with self.subTest(change=change),self.assertRaises(verifier.VerificationError):
                        verifier.verify_readiness(bad,root)

    def test_v2_producer_binding_cannot_disagree_with_executed_source_map(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=report(root)
            with patch.object(verifier,'PINNED_SOURCE_HASHES',{}):
                for change in ('missing','legacy','different-map','wrong-law','false-revision'):
                    bad=deepcopy(base)
                    if change=='missing':del bad['producer_binding']
                    if change=='legacy':bad['producer_binding']['schema_version']='nba-pros004-source-binding-v1'
                    if change=='different-map':bad['producer_binding']['source_sha256']['multisport_lab/pros004_completion.py']='f'*64
                    if change=='wrong-law':bad['producer_binding']['law_sha256']['R0']='f'*64
                    if change=='false-revision':bad['producer_binding']['model_commit']='a'*40
                    with self.subTest(change=change),self.assertRaisesRegex(verifier.VerificationError,'producer binding'):
                        verifier.verify_readiness(bad,root)

    def test_v2_requires_complete_timely_recovery_without_prospective_eligibility(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=report(root)
            with patch.object(verifier,'PINNED_SOURCE_HASHES',{}):
                for change in ('partial','retained','timing','eligible','no-remote','github-claim',
                        'forecast-finalization','input-finalization','producer-version'):
                    bad=deepcopy(base)
                    if change=='partial':bad['diagnostic_status']='PARTIAL_OR_FAILED_TIMING'
                    if change=='retained':bad['recovery']['retained_models']=7
                    if change=='timing':bad['recovery']['timing_complete_models']=7
                    if change=='eligible':bad['recovery']['eligible_models']=8
                    if change=='no-remote':bad['recovery']['remote_recovery']=False
                    if change=='github-claim':bad['recovery']['github_recovery']=True
                    if change=='forecast-finalization':bad['recovery']['final_checkpoint']['timely']=False
                    if change=='input-finalization':bad['event_input']['final_checkpoint']['timely']=False
                    if change=='producer-version':bad['diagnostics']['K0']['producer_version']='pros004-k0-producer-v1'
                    with self.subTest(change=change),self.assertRaises(verifier.VerificationError):
                        verifier.verify_readiness(bad,root)

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
            source=payload('input_captures','source',{'note':'explicit synthetic generic receipt'})
            save(root,source)
            ref={'kind':'input_captures','record_id':source['record_id'],
                 'payload_sha256':verifier.fingerprint(source)}
            marker={'schema_version':'nba-pros004-failure-v1','study_id':'NBA-ALL13-JOINT-PROS-004',
                'mode':'SYNTHETIC_DIAGNOSTIC','status':'SOURCE_FAILURE',
                'reason':'Explicit synthetic diagnostic fixture','recorded_at':'2026-10-20T00:00:00.000000Z'}
            item=payload('input_captures','source-failure',{'identity':{},'pros004':marker},[ref])
            # A checksum-consistent, incomplete typed body now fails semantics.
            save(root,item)
            with self.assertRaisesRegex(verifier.VerificationError,'strict typed'):
                verifier.verify_store(root)
            bad=deepcopy(item);bad['references'][0]['payload_sha256']='f'*64;save(root,bad)
            with self.assertRaisesRegex(verifier.VerificationError,'referenced content'):
                verifier.verify_store(root)
            bad=deepcopy(item);bad['data']['pros004']['padding']='x'*(8*1024);save(root,bad)
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
            root=Path(folder);base=complete_forecast_store(root,self)
            self.assertEqual(verifier.verify_store(root)['independently_checked_forecast_contracts'],2)
            for change in ('late','latency','identity','cutoff','categories','mean','atoms','binding'):
                bad=deepcopy(base);body=bad['data']['pros004']
                if change=='late':bad['received_at']='2026-10-21T23:05:00.000001Z'
                if change=='latency':bad['received_at']='2026-10-21T23:02:06.000000Z'
                if change=='identity':body['team_id']='3'
                if change=='cutoff':body['cutoff_at']='2026-10-21T23:01:00.000000Z'
                if change=='categories':body['categories'].pop()
                if change=='mean':body['categories'][0]['mean']='1'
                if change=='atoms':body['joint_recipe']['omitted_atoms']=1
                if change=='binding':body['producer_binding']={'different':'revision'}
                body['forecast_id']=verifier.fingerprint({k:v for k,v in body.items() if k!='forecast_id'})
                save(root,bad)
                with self.subTest(change=change),self.assertRaises(verifier.VerificationError):
                    verifier.verify_store(root)
            save(root,base)
            bad=deepcopy(base);bad['received_at']='2026-10-21T23:05:00.000001Z';save(root,bad)
            run=subprocess.run([sys.executable,'-O',str(SCRIPT),'--store-root',str(root)],capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0)
            self.assertIn('clocks violate T90 window',run.stderr)
            self.assertNotIn('AssertionError',run.stderr)


    def test_checksum_consistent_outcomes_fail_invalid_meaning_and_preserve_bytes(self):
        from test_pros004_records import at_outcomes,synthetic_outcome
        from multisport_lab.integrity import read_receipt
        f,refs=typed_fixture(self);at_outcomes(f)
        out=f.store.append_outcome(synthetic_outcome(f),refs)
        original=read_receipt(f.store.ledger._path(out.kind,out.record_id))
        self.assertGreater(verifier.verify_store(f.tmp)['strict_typed_semantics']['typed_records'],0)
        for change in ('status','identity','arithmetic','observation_clock','normalization_clock','mode'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);copy_for_semantic_mutation(f.tmp,root)
                body=deepcopy(original['data']['pros004'])
                if change=='status':body['status']='IMPOSSIBLE_STATUS'
                if change=='identity':body['player_id']='999'
                if change=='arithmetic':body['primitives']['PTS']+=1
                if change=='observation_clock':body['source_observed_at']='2026-10-23T00:00:00.000000Z'
                if change=='normalization_clock':body['normalized_at']='2026-10-23T00:00:00.000000Z'
                if change=='mode':body['mode']='READINESS_DIAGNOSTIC'
                replace_typed_receipt(root,original,body)
                before={p:p.read_bytes() for p in root.glob('records/*/*.json')}
                with self.assertRaisesRegex(verifier.VerificationError,'strict typed'):
                    verifier.verify_store(root)
                self.assertTrue(all(p.read_bytes()==raw for p,raw in before.items()))

    def test_checksum_consistent_grades_validate_original_distribution_outcome_and_clocks(self):
        from test_pros004_records import at_outcomes,synthetic_outcome
        from multisport_lab.integrity import read_receipt
        f,refs=typed_fixture(self);at_outcomes(f)
        out=f.store.append_outcome(synthetic_outcome(f),refs)
        grade=f.store.grade_forecast(refs[0],out)
        original=read_receipt(f.store.ledger._path(grade.kind,grade.record_id))
        verifier.verify_store(f.tmp)
        for change in ('status','score','forecast_id','grade_clock','reference'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);copy_for_semantic_mutation(f.tmp,root)
                body=deepcopy(original['data']['pros004']);changed_refs=deepcopy(original['references'])
                if change=='status':body['status']='DNP_NOT_SCORED'
                if change=='score':body['categories'][0]['crps']='999'
                if change=='forecast_id':body['forecast_id']='f'*64
                if change=='grade_clock':body['graded_at']='2026-10-21T23:00:06.000000Z'
                if change=='reference':changed_refs[0]=refs[1].to_record()
                replace_typed_receipt(root,original,body,changed_refs)
                with self.assertRaisesRegex(verifier.VerificationError,'strict typed'):
                    verifier.verify_store(root)

    def test_grade_cannot_borrow_outcome_not_linked_to_original_forecast(self):
        from test_pros004_records import at_outcomes,synthetic_outcome
        from multisport_lab.integrity import read_receipt,stamp
        f,refs=typed_fixture(self);at_outcomes(f)
        # A partial peer remains valid evidence, but does not confer an outcome
        # link on a different original merely because event/player IDs match.
        peer_path=f.store.ledger._path(refs[1].kind,refs[1].record_id)
        peer_raw=peer_path.read_bytes();peer_path.unlink()
        out=f.store.append_outcome(synthetic_outcome(f),[refs[0]])
        grade=f.store.grade_forecast(refs[0],out)
        peer_path.write_bytes(peer_raw)
        original=read_receipt(f.store.ledger._path(grade.kind,grade.record_id))
        body=f.store._grade(f.store.body(refs[1]),f.store.body(out),stamp(f.record_clock.return_value))
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);copy_for_semantic_mutation(f.tmp,root)
            replace_typed_receipt(root,original,body,[refs[1].to_record(),out.to_record()])
            with self.assertRaisesRegex(verifier.VerificationError,'not linked by its shared outcome'):
                verifier.verify_store(root)

    def test_checksum_consistent_event_and_admission_meaning_is_validated(self):
        from multisport_lab.integrity import read_receipt
        from multisport_lab import pros004_records as rec
        f,_=typed_fixture(self)
        claim_path=next((Path(f.tmp)/'records/input_captures').glob('*.json'))
        claim=read_receipt(claim_path)
        self.assertEqual(claim['data']['pros004']['schema_version'],'nba-pros004-event-claim-v2')
        for change in ('cohort','event','clock','identity'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);copy_for_semantic_mutation(f.tmp,root)
                # Remove dependents so a broken content reference cannot mask a
                # checksum-consistent admission-body semantic failure.
                shutil.rmtree(root/'records/forecasts')
                original=deepcopy(claim);body=original['data']['pros004']
                if change=='cohort':body['players'][0]['player_id']='999'
                if change=='event':body['event_id']='401999999'
                if change=='clock':body['claimed_at']='2099-01-01T00:00:00.000000Z'
                if change=='identity':original['data']['identity']['event_id']='401999999'
                if change!='identity':original['data']['identity']=rec._identity(body)
                save(root,original)
                with self.assertRaisesRegex(verifier.VerificationError,'strict typed'):
                    verifier.verify_store(root)

    def test_checksum_consistent_claim_v2_cannot_change_original_input_phase_proof(self):
        from multisport_lab.integrity import read_receipt
        f,_=typed_fixture(self)
        original=read_receipt(f.store.ledger._path(f.claim_ref.kind,f.claim_ref.record_id))
        self.assertEqual(original['data']['pros004']['schema_version'],'nba-pros004-event-claim-v2')
        for change in ('snapshot','journal','references','late','acknowledgment','missing-proof'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);copy_for_semantic_mutation(f.tmp,root)
                shutil.rmtree(root/'records/forecasts')
                body=deepcopy(original['data']['pros004']);proof=body['input_final_checkpoint']
                if change=='snapshot':proof['snapshot_sha256']='f'*64;proof['acknowledgment']['snapshot_sha256']='f'*64
                if change=='journal':proof['journal_raw_sha256']='f'*64
                if change=='references':proof['references']=[]
                if change=='late':proof['completed_at']='2026-10-21T22:50:00.000001Z'
                if change=='acknowledgment':proof['acknowledgment']['reference']=f.history_ref.to_record()
                if change=='missing-proof':del body['input_final_checkpoint']
                replace_typed_receipt(root,original,body)
                with self.assertRaisesRegex(verifier.VerificationError,'strict typed'):
                    verifier.verify_store(root)

    def test_checksum_consistent_shared_history_cannot_change_retained_limitations(self):
        from test_pros004_producer import ProducerFixture
        from multisport_lab.integrity import read_receipt
        f=ProducerFixture(self)
        original=read_receipt(f.store.ledger._path(f.history_ref.kind,f.history_ref.record_id))
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);save(root,original)
            body=deepcopy(original['data']['pros004'])
            body['history_provenance']['availability_semantics']='Proved original upstream availability'
            replace_typed_receipt(root,original,body)
            with self.assertRaisesRegex(verifier.VerificationError,'limitations must remain unchanged'):
                verifier.verify_store(root)

    def test_typed_body_clock_cannot_borrow_a_later_diagnostic_receipt_clock(self):
        from test_pros004_producer import ProducerFixture
        from multisport_lab import pros004_records as rec
        from multisport_lab.integrity import read_receipt,stamp
        f=ProducerFixture(self)
        claim,_=f.store.claim_event(f.event_ref,f.binding)
        date=f.store.store_date_status('2026-10-23',status='SOURCE_FAILURE',
            reason='Explicit synthetic unavailable date',mode='SYNTHETIC_DIAGNOSTIC')
        manifest=f.store.store_manifest()
        latest_clock=f.record_clock.return_value+timedelta(seconds=50)
        latest_body={'schema_version':'nba-pros004-date-status-v1','study_id':rec.STUDY_ID,
            'mode':'SYNTHETIC_DIAGNOSTIC','event_date':'2026-11-10','status':'SOURCE_FAILURE',
            'reason':'Explicit later synthetic metadata, never admission','recorded_at':stamp(latest_clock),
            'schedule':None}
        latest=payload('research_inputs',rec._logical(latest_body),
            {'identity':rec._identity(latest_body),'pros004':latest_body},clock=stamp(latest_clock))
        for target,key,ancestors in ((f.history_ref,'imported_at',()),
                (claim,'claimed_at',(f.history_ref,f.event_ref)),
                (date,'recorded_at',()),(manifest,'recorded_at',())):
            with self.subTest(schema=f.store.body(target)['schema_version']),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);original=read_receipt(f.store.ledger._path(target.kind,target.record_id))
                save(root,original);save(root,latest)
                for ancestor in ancestors:
                    save(root,read_receipt(f.store.ledger._path(ancestor.kind,ancestor.record_id)))
                body=deepcopy(original['data']['pros004'])
                body[key]=stamp(verifier._time(original['received_at'])+timedelta(seconds=1))
                replace_typed_receipt(root,original,body)
                with self.assertRaisesRegex(verifier.VerificationError,'after its receipt'):
                    verifier.verify_store(root)

    def test_checksum_consistent_date_state_contract_is_validated(self):
        from multisport_lab.integrity import read_receipt
        f,_=typed_fixture(self)
        date_ref=f.store.store_date_status('2026-10-23',status='SOURCE_FAILURE',
            reason='Explicit synthetic source-completeness failure')
        original=read_receipt(f.store.ledger._path(date_ref.kind,date_ref.record_id))
        for change in ('status','outside-reservation','clock','false-completeness'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);copy_for_semantic_mutation(f.tmp,root)
                body=deepcopy(original['data']['pros004'])
                if change=='status':body['status']='COMPLETE'
                if change=='outside-reservation':body['event_date']='2026-11-11'
                if change=='clock':body['recorded_at']='2099-01-01T00:00:00.000000Z'
                if change=='false-completeness':body['schedule']={}
                replace_typed_receipt(root,original,body)
                with self.assertRaisesRegex(verifier.VerificationError,'strict typed'):
                    verifier.verify_store(root)

    def test_checksum_consistent_failure_contract_and_subject_links_are_validated(self):
        from multisport_lab.integrity import read_receipt
        f,refs=typed_fixture(self)
        failure=f.store.store_failure(f.event_ref,status='UNACKNOWLEDGED',reason='Explicit synthetic failure',
            operation='REMOTE_CHECKPOINT',subject_id='10',original_reference=refs[0])
        original=read_receipt(f.store.ledger._path(failure.kind,failure.record_id))
        verifier.verify_store(f.tmp)
        for change in ('status','operation','subject','original','clock'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);copy_for_semantic_mutation(f.tmp,root)
                body=deepcopy(original['data']['pros004'])
                if change=='status':body['status']='SUCCESS'
                if change=='operation':body['operation']='BET_PLACEMENT'
                if change=='subject':body['subject_id']='999'
                if change=='original':body['original_reference']=f.history_ref.to_record()
                if change=='clock':body['recorded_at']='2099-01-01T00:00:00.000000Z'
                replace_typed_receipt(root,original,body)
                with self.assertRaisesRegex(verifier.VerificationError,'strict typed'):
                    verifier.verify_store(root)

    def test_correction_graph_requires_same_subject_and_traceable_outcome_regrade(self):
        from test_pros004_records import at_outcomes,synthetic_outcome
        from multisport_lab.integrity import read_receipt,digest
        f,refs=typed_fixture(self);at_outcomes(f)
        first=f.store.append_outcome(synthetic_outcome(f),refs)
        second=f.store.append_outcome(synthetic_outcome(f,extra_points=1),refs,correction_reason='Synthetic correction')
        verifier.verify_store(f.tmp)
        correction=next((Path(f.tmp)/'records/corrections').glob('*.json'))
        original=read_receipt(correction)
        # A reverse link uses valid target hashes and equal clocks, but creates
        # a cycle; correct checksums cannot turn it into valid correction history.
        reverse=payload('corrections','supersedes:outcomes:'+second.record_id,
            {'reason':'Synthetic invalid reverse link','replacement':first.to_record()},
            [second.to_record(),first.to_record()],clock=original['received_at'])
        reverse['supersedes']=second.to_record();save(Path(f.tmp),reverse)
        with self.assertRaisesRegex(verifier.VerificationError,'correction cycle'):
            verifier.verify_store(f.tmp)

    def test_correction_cannot_link_two_valid_different_player_outcomes(self):
        from test_pros004_records import at_outcomes,synthetic_outcome
        f,refs=typed_fixture(self)
        claim,_=f.store.claim_event(f.event_ref,f.binding)
        peer_body,_=f.generate('R0','20')
        other=f.store.persist_forecast(peer_body,f.event_ref,f.history_ref,claim)
        at_outcomes(f)
        first=f.store.append_outcome(synthetic_outcome(f),refs)
        body=synthetic_outcome(f);body['player_id']='20'
        body['outcome_id']=verifier.fingerprint({k:v for k,v in body.items() if k!='outcome_id'})
        second=f.store.append_outcome(body,[other])
        verifier.verify_store(f.tmp)
        bad=payload('corrections','supersedes:outcomes:'+first.record_id,
            {'reason':'Invalid cross-player correction','replacement':second.to_record()},
            [first.to_record(),second.to_record()],clock=f.store.read(first)['received_at'])
        bad['supersedes']=first.to_record();save(Path(f.tmp),bad)
        with self.assertRaisesRegex(verifier.VerificationError,'changes original subject identity'):
            verifier.verify_store(f.tmp)

    def test_unrelated_future_receipts_cannot_borrow_diagnostic_clock_context(self):
        f,_=typed_fixture(self)
        future=payload('input_captures','unrelated-future',{'note':'This is not diagnostic PROS004'},
            clock='2099-01-01T00:00:00.000000Z')
        save(Path(f.tmp),future)
        with self.assertRaisesRegex(verifier.VerificationError,'unrelated original receipt clock'):
            verifier.verify_store(f.tmp)

    def test_optimized_python_rejects_checksum_consistent_invalid_outcome_status(self):
        # A self-contained malformed typed outcome has no missing hash/reference;
        # it is semantically invalid even before its relation to a forecast.
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            body={'schema_version':'nba-pros004-outcome-v1','mode':'SYNTHETIC_DIAGNOSTIC','status':'ALIEN'}
            item=payload('outcomes','invalid-outcome',{'identity':{},'pros004':body})
            save(root,item)
            run=subprocess.run([sys.executable,'-O',str(SCRIPT),'--store-root',str(root)],capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0)
            self.assertIn('strict typed',run.stderr)
            self.assertNotIn('AssertionError',run.stderr)


if __name__=='__main__':
    unittest.main()

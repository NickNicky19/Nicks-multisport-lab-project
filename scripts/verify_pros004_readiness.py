#!/usr/bin/env python3
"""Independent PROS004 readiness verification; no capture, issuance or scoring.

This checker imports no producer or records implementation. Integrity failures
raise explicit exceptions under ordinary and optimized Python alike. It verifies
retained receipts, source pins, capacity arithmetic and diagnostic round trips;
it does not authorize activation or prove historical/source authenticity.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import stat

SCHEMA = 'nba-pros004-readiness-report-v1'
HISTORY_SHA256 = '489b7148db26cc68e3096cacc1c6960d2b7652d0a82755c215efbd6a96876c8c'
HISTORY_ROWS, HISTORY_EVENTS, HISTORY_BYTES = 26645, 1231, 14720351
MAX_RECORDS, MAX_BYTES = 512, 32*1024*1024
KINDS = ('forecasts', 'outcomes', 'grades', 'corrections', 'input_captures', 'research_inputs')
RECORD_CAPS = {'forecasts':64*1024, 'outcomes':8*1024, 'grades':16*1024,
               'input_captures':8*1024, 'corrections':8*1024}
PINNED_SOURCE_HASHES = {
    'multisport_lab/baseline.py':'2a217b021ae25041920d14db6fbb1a14197ef4593b2b59965bbdef6f01304689',
    'multisport_lab/basketball.py':'5dd01add55b37fc610fbf40a20750a6f35e89498f3b059eafa90e35d54f3ea75',
    'multisport_lab/forecast_contract.py':'bb1f3c31379cd3d68ae4015e8e2a8538f7d8d3e35baecbf0c1fd67d35bc51fdd',
    'multisport_lab/integrity.py':'10f9ee4f7fde032e08f4798638aa6abb95c31944ef0809dffd257b5be2e213b2',
    'multisport_lab/ledger.py':'d463690ba20c5481ba45f4fb5f7da8196d0abd917dfc55d49f8d2ea4d5b4975e',
    'multisport_lab/nba_data.py':'6fed983653f7a93f6427fa27b9ea0dbb574c595d2a35aa0b2040473d664b692b',
    'multisport_lab/pregame_sources.py':'d285c0f43d8bd6c7562d97102181a0299566650b74dd82ca49f352749c60b485',
    'multisport_lab/prospective.py':'d7094982dd1c186b2fe17b5e2992ed97a730e4ef369581679fa43fe1649bc1b5',
    'scripts/prepare_nba_panel.py':'d0864c3d399768624e25b3c278d0a3238653d422ed2a87c3c25fcea2dad2038e',
    'multisport_lab/development_003.py':'282bb23a570bc6aaa217ab7f65ba223613c805801d8c479bc51aef0291b72be7',
    'evidence/research/prospective004-protocol.json':'8302bf5455d48c9c0f6ccd40296b971955822ee09edaa9d9af94ad205d06e752',
    '.github/workflows/nba-20261020-pilot.yml':'900783602710fd82761c071a143ad7e9c7d5d491461ca4c8d650427638583dab',
}
NEW_PRODUCER_FILES = ('multisport_lab/pros004_inputs.py', 'multisport_lab/pros004_producer.py',
                      'multisport_lab/pros004_records.py')
DIAGNOSTIC_MODES = {'SYNTHETIC_TEST','READINESS_DIAGNOSTIC','READINESS_DIAGNOSTIC_NON_ISSUANCE',
                    'SYNTHETIC_NON_ISSUANCE','SYNTHETIC_DIAGNOSTIC'}
MARKETS = {'PTS','PRA','REB','3PM','AST','RA','PR','TOV','TD','DD','BLK','STL','BLK+STL','PA'}
MODEL_VERSIONS = {'R0':'nba_joint_empirical_r0_v1','K0':'nba_joint_lagged_workload_prior_k0_v1'}


class VerificationError(ValueError):
    """A failed explicit integrity check, never an assertion-only guard."""


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def _pairs(values):
    result = {}
    for key,value in values:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def _json_value(value):
    if value is None or type(value) in (str,bool,int):
        return
    if type(value) is float:
        require(math.isfinite(value), 'non-finite JSON number')
        return
    if type(value) is list:
        for item in value:
            _json_value(item)
        return
    if type(value) is dict:
        for key,item in value.items():
            require(type(key) is str, 'JSON keys must be strings')
            _json_value(item)
        return
    raise VerificationError('unsupported JSON value')


def canonical(value):
    _json_value(value)
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def fingerprint(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _invalid_number(value):
    raise VerificationError('non-finite JSON constant: '+value)


def load_receipt(path, *, maximum=16*1024*1024):
    path = Path(path)
    require(not path.is_symlink() and path.is_file(), 'receipt must be a regular file')
    require(path.stat().st_size <= maximum, 'receipt exceeds its byte budget')
    raw = path.read_bytes()
    try:
        envelope = json.loads(raw,object_pairs_hook=_pairs,parse_constant=_invalid_number)
    except (UnicodeDecodeError,json.JSONDecodeError) as error:
        raise VerificationError('invalid receipt JSON') from error
    _json_value(envelope)
    require(type(envelope) is dict and set(envelope)=={'schema_version','hash_format','payload_sha256','payload'},
            'invalid receipt envelope')
    require(envelope['schema_version']=='decoded-json-receipt-v1' and
            envelope['hash_format']=='sha256-canonical-decoded-json-v1', 'unknown receipt format')
    require(envelope['payload_sha256']==fingerprint(envelope['payload']), 'receipt content hash mismatch')
    return envelope['payload'],hashlib.sha256(raw).hexdigest(),len(raw)


def _sha(value, label):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None, 'invalid '+label)
    return value


def _time(value):
    require(type(value) is str, 'clock must be a string')
    try:
        clock = datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as error:
        raise VerificationError('invalid clock') from error
    require(clock.tzinfo is not None and clock.utcoffset() is not None, 'clock requires timezone')
    return clock.astimezone(timezone.utc)


def source_pins(root):
    root = Path(root).resolve()
    result = {}
    for name,expected in PINNED_SOURCE_HASHES.items():
        path = root/name
        require(path.is_file() and not path.is_symlink(), 'missing pinned source: '+name)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        require(actual==expected, 'frozen source changed: '+name)
        result[name] = actual
    return result


def _probability(value):
    require(type(value) is str and re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?',value) is not None,
            'probability/mean must be a finite nonnegative decimal string')
    result=float(value)
    require(math.isfinite(result),'probability/mean is not finite')
    return result


def _pmf_mean(pmf, *, count=True):
    require(type(pmf) is list and 0<len(pmf)<=1025,'invalid complete PMF')
    previous=-1
    probabilities=[]
    products=[]
    for atom in pmf:
        require(type(atom) is dict and set(atom)=={'value','probability'},'invalid probability atom')
        value=atom['value']
        require(type(value) in ((int,) if count else (int,float)) and math.isfinite(value)
                and previous<value and value>=0,'PMF values must be unique sorted nonnegative counts')
        probability=_probability(atom['probability'])
        require(0<probability<=1,'retained probabilities must be positive')
        previous=value;probabilities.append(probability);products.append(value*probability)
    require(math.isclose(math.fsum(probabilities),1,rel_tol=0,abs_tol=1e-12),'complete PMF mass must equal one')
    return math.fsum(products)


def _reference_target(reference,records):
    require(type(reference) is dict and set(reference)=={'kind','record_id','payload_sha256'},
            'invalid typed input reference')
    key=(reference['kind'],reference['record_id'])
    require(key in records and fingerprint(records[key])==reference['payload_sha256'],
            'typed input reference content is unavailable or changed')
    return records[key]


def _verify_forecast(body,payload,records):
    """Independent original clocks, common inputs and marginal arithmetic checks.

    Full-law reconstruction is a separate source-bound diagnostic. These checks
    do not substitute marginal arithmetic for verification of every joint atom.
    """
    model=body.get('model_key')
    require(model in MODEL_VERSIONS and body.get('model_version')==MODEL_VERSIONS[model],
            'forecast model law/version is not unchanged R0/K0')
    require(body.get('producer_version')=='pros004-'+model.lower()+'-producer-v1',
            'forecast prospective wrapper identity changed')
    require(body.get('conditioning')=='CONDITIONAL_ON_APPEARANCE' and body.get('qualification')=='UNAVAILABLE',
            'research conditioning/qualification changed')
    require(body.get('forecast_id')==fingerprint({k:v for k,v in body.items() if k!='forecast_id'}),
            'original forecast content hash changed')
    event_record=_reference_target(body.get('event_ref'),records)
    history_record=_reference_target(body.get('history_ref'),records)
    event=event_record['data'].get('pros004',{})
    history=history_record['data'].get('pros004',{})
    require(event.get('schema_version')=='nba-pros004-event-v1' and
            history.get('schema_version')=='nba-pros004-history-v1','forecast input contract kinds conflict')
    require(event.get('history_ref')==body['history_ref'],'models do not share the exact admitted history')
    require(len(payload['references'])==3 and payload['references'][:2]==[body['event_ref'],body['history_ref']],
            'forecast references must retain exact event/history/admission order')
    claim=_reference_target(payload['references'][2],records)['data'].get('pros004',{})
    require(claim.get('schema_version')=='nba-pros004-event-claim-v1' and
            claim.get('event_ref')==body['event_ref'] and claim.get('history_ref')==body['history_ref'] and
            claim.get('producer_identity')==body.get('producer_binding'),
            'forecast changed the original admitted input/producer')
    facts=event.get('event')
    require(type(facts) is dict,'forecast event facts are missing')
    for key in ('event_id','event_version','event_starts_at'):
        require(body.get(key)==facts.get(key),'forecast event identity/version changed: '+key)
    candidates=[p for p in event.get('candidates',[]) if p.get('player_id')==body.get('player_id')]
    require(len(candidates)==1,'forecast subject is outside the frozen cohort')
    for key in ('team_id','opponent_id','player_label'):
        require(body.get(key)==candidates[0].get(key),'forecast player/team identity changed: '+key)
    start=_time(body['event_starts_at']);cutoff=start-timedelta(minutes=90)
    require(_time(body['cutoff_at'])==cutoff,'forecast common T90 cutoff changed')
    freeze=cutoff.replace(hour=0,minute=0,second=0,microsecond=0)
    require(_time(body['history_freeze'])==freeze and _time(body['trained_through'])<=freeze,
            'forecast causal midnight history freeze changed')
    clocks=[_time(body[k]) for k in ('generation_started_at','generation_completed_at','verified_at','issued_at')]
    received=_time(payload['received_at'])
    require(cutoff<=clocks[0]<=clocks[1]<=clocks[2]==clocks[3]<=received<=cutoff+timedelta(minutes=5),
            'forecast actual generation/receipt clocks violate T90 window')
    require((received-clocks[0]).total_seconds()<=120,'forecast generation-to-receipt latency exceeded')
    categories=body.get('categories')
    require(type(categories) is list and len(categories)==14 and
            {c.get('code') for c in categories if type(c) is dict}==MARKETS,'all 13 categories plus PA required')
    means={}
    for category in categories:
        mean=_pmf_mean(category.get('pmf'))
        require(math.isclose(_probability(category.get('mean')),mean,rel_tol=0,abs_tol=1e-10),
                'original category mean differs from probabilities')
        if category['code'] in {'DD','TD'}:
            require(all(a['value'] in (0,1) for a in category['pmf']),'DD/TD probabilities must be binary')
        means[category['code']]=mean
    for target,pieces in {'PRA':('PTS','REB','AST'),'PR':('PTS','REB'),'RA':('REB','AST'),
                          'PA':('PTS','AST'),'BLK+STL':('BLK','STL')}.items():
        require(math.isclose(means[target],math.fsum(means[p] for p in pieces),rel_tol=0,abs_tol=1e-10),
                'derived category means violate the shared joint arithmetic')
    require(means['TD']<=means['DD']+1e-12 and means['PTS']+1e-10>=3*means['3PM'],
            'scoring or TD/DD coherence failed')
    recipe=body.get('joint_recipe')
    require(type(recipe) is dict and recipe.get('event_ref')==body['event_ref'] and
            recipe.get('history_ref')==body['history_ref'] and recipe.get('omitted_atoms')==0 and
            type(recipe.get('support_atom_count')) is int and recipe['support_atom_count']>0 and
            recipe['support_atom_count']==recipe.get('pool_history_count'),
            'full joint replay recipe loses atoms or changes inputs')
    _sha(recipe.get('joint_sha256'),'full joint hash')
    _sha(recipe.get('input_sha256'),'full input hash')
    _pmf_mean(body.get('reported_minutes',{}).get('pmf'),count=False)


def verify_store(root):
    """Independent generic-envelope/references/budget check of a retained store.

    New PROS004 records in readiness diagnostics must carry an explicit diagnostic
    mode. Original unrelated ledger records are counted and hashed, not relabeled.
    """
    root = Path(root)
    require(not root.is_symlink() and not (root/'records').is_symlink(), 'symlinked ledger root')
    records,encoded = {},{}
    count = total = unpublished = 0
    maxima = {kind:0 for kind in KINDS}
    for kind in KINDS:
        folder = root/'records'/kind
        require(not folder.is_symlink(), 'symlinked ledger directory')
        if not folder.exists():
            continue
        for path in folder.iterdir():
            require(stat.S_ISREG(path.lstat().st_mode), 'ledger entry must be regular')
            count += 1
            total += path.stat().st_size
            require(count<=MAX_RECORDS and total<=MAX_BYTES, 'ledger global capacity exceeded')
            if path.name.startswith('.receipt-'):
                unpublished += 1
                continue
            require(re.fullmatch('[0-9a-f]{64}\\.json',path.name) is not None, 'invalid ledger filename')
            payload,raw_sha,size = load_receipt(path,maximum=4*1024*1024)
            require(type(payload) is dict, 'ledger payload must be an object')
            required={'schema_version','kind','record_id','logical_id','received_at','data','references',
                      'supersedes','persistence_status'}
            require(set(payload)==required, 'invalid ledger payload fields')
            require(payload['schema_version']=='multisport-research-ledger-v1' and payload['kind']==kind and
                    payload['record_id']==path.stem and payload['persistence_status']=='LOCAL_RECEIPT_ONLY',
                    'ledger identity/status mismatch')
            require(payload['record_id']==fingerprint({'kind':kind,'logical_id':payload['logical_id']}),
                    'logical record checksum mismatch')
            require(type(payload['data']) is dict and type(payload['references']) is list,
                    'invalid ledger data/references')
            _time(payload['received_at'])
            marker = payload['data'].get('pros004')
            if marker is not None:
                require(type(marker) is dict, 'PROS004 body must be an object')
                inactive_manifest=(marker.get('schema_version')=='nba-pros004-study-manifest-v1' and
                                   marker.get('status')=='INACTIVE_READINESS_ONLY')
                require(inactive_manifest or marker.get('mode') in DIAGNOSTIC_MODES,
                        'readiness store contains unmarked/live PROS004 record')
                require(marker.get('evidence_lane')!='REAL_TIME_CAPTURED', 'readiness store contains genuine issuance')
                if kind=='research_inputs':
                    history = 'history' in marker or 'history' in str(marker.get('schema_version','')).lower()
                    ceiling = 2*1024*1024 if history else 32*1024
                else:
                    ceiling = RECORD_CAPS[kind]
                require(size<=ceiling, 'PROS004 encoded envelope ceiling exceeded: '+kind)
                maxima[kind] = max(maxima[kind],size)
            key=(kind,path.stem)
            require(key not in records,'duplicate ledger record')
            records[key]=payload
            encoded[key]=raw_sha
    require(unpublished==0, 'unresolved interrupted receipt file requires recovery')
    for key,payload in records.items():
        refs=[]
        for ref in payload['references']:
            require(type(ref) is dict and set(ref)=={'kind','record_id','payload_sha256'}, 'invalid ledger reference')
            target=(ref['kind'],ref['record_id'])
            require(target in records,'missing referenced record')
            require(ref['payload_sha256']==fingerprint(records[target]), 'referenced content hash mismatch')
            require(_time(records[target]['received_at'])<=_time(payload['received_at']), 'reference clock follows record')
            refs.append(target)
        require(len(refs)==len(set(refs)),'duplicate references')
    forecast_count=0
    for payload in records.values():
        body=payload['data'].get('pros004',{})
        if body.get('schema_version')=='nba-pros004-forecast-v1':
            _verify_forecast(body,payload,records)
            forecast_count+=1
    return {'status':'PASS_INDEPENDENT_STORE_CHECK','records':count,'encoded_bytes':total,
            'global_record_limit':MAX_RECORDS,'global_byte_limit':MAX_BYTES,
            'new_record_maxima':maxima,'record_file_sha256':{kind+':'+record:sha for (kind,record),sha in encoded.items()},
            'independently_checked_forecast_contracts':forecast_count,
            'new_captures_or_forecasts_generated':False}


def verify_readiness(report, root):
    require(type(report) is dict and report.get('schema_version')==SCHEMA, 'invalid readiness report schema')
    require(report.get('mode')=='READINESS_DIAGNOSTIC_NON_ISSUANCE','report is not a non-issuance diagnostic')
    evidence=report.get('evidence')
    require(type(evidence) is dict,'missing evidence lane declarations')
    for name in ('live_source_captures','genuine_issuance','statistical_grades','aggregate_comparison_executions'):
        require(type(evidence.get(name)) is int and evidence[name]==0,'readiness evidence must remain zero: '+name)
    require(evidence.get('activation') is False,'PROS004 activation is not authorized by readiness')
    pins=source_pins(root)
    sources=report.get('source_sha256')
    require(type(sources) is dict and all(name in sources for name in NEW_PRODUCER_FILES),'new producer source references missing')
    base=Path(root).resolve()
    for name,expected in sources.items():
        _sha(expected,'source hash')
        path=(base/name).resolve()
        require(path.is_relative_to(base) and path.is_file() and not (base/name).is_symlink(),'invalid source reference path')
        require(hashlib.sha256(path.read_bytes()).hexdigest()==expected,'executed source fingerprint changed: '+name)
    history=report.get('history')
    require(type(history) is dict,'missing complete-history measurement')
    for key,value in {'rows':HISTORY_ROWS,'events':HISTORY_EVENTS,'normalized_bytes':HISTORY_BYTES,'sha256':HISTORY_SHA256}.items():
        require(type(history.get(key)) is type(value) and history.get(key)==value,'fixed complete history mismatch: '+key)
    require(type(history.get('encoded_envelope_bytes')) is int and 0<history['encoded_envelope_bytes']<=2*1024*1024,
            'history envelope ceiling exceeded')
    retention=report.get('retention')
    require(type(retention) is dict,'missing capacity measurement')
    for key,value in {'max_records':MAX_RECORDS,'max_bytes':MAX_BYTES,'comparison_records':442,'baseline_and_pilot_records':32}.items():
        require(type(retention.get(key)) is type(value) and retention.get(key)==value,'capacity definition changed: '+key)
    metadata=retention.get('metadata_records')
    require(type(metadata) is int and metadata==38,'required metadata/correction reserve changed')
    require(retention.get('projected_records')==474+metadata and retention['projected_records']==MAX_RECORDS,
            'full planned record capacity exceeded or miscounted')
    base_bytes=(168*64*1024+84*8*1024+168*16*1024+21*32*1024+2*1024*1024+4*1024*1024)
    require(type(retention.get('projected_bytes')) is int and base_bytes<=retention['projected_bytes']<=MAX_BYTES,
            'full planned byte capacity exceeded or understated')
    if 'metadata_encoded_ceiling_bytes' in retention:
        require(type(retention['metadata_encoded_ceiling_bytes']) is int and retention['metadata_encoded_ceiling_bytes']>=0,
                'invalid metadata byte allowance')
        require(retention['projected_bytes']==base_bytes+retention['metadata_encoded_ceiling_bytes'],
                'full planned byte arithmetic is inconsistent')
    diagnostics=report.get('diagnostics')
    require(type(diagnostics) is dict and set(diagnostics)=={'R0','K0'},'comparison requires exactly R0 and K0')
    for model,value in diagnostics.items():
        require(type(value) is dict,'invalid producer diagnostic')
        require(type(value.get('forecast_envelope_bytes')) is int and 0<value['forecast_envelope_bytes']<=64*1024,
                'forecast envelope ceiling exceeded: '+model)
        require(value.get('support_count')==HISTORY_ROWS and value.get('restored_support_count')==HISTORY_ROWS,
                'joint support atoms were dropped: '+model)
        require(value.get('category_count')==14,'all 13 categories plus PA required: '+model)
        require(_sha(value.get('joint_sha256'),'joint hash')==_sha(value.get('restored_joint_sha256'),'restored joint hash'),
                'recovered joint law changed: '+model)
    return {'status':'PASS_INDEPENDENT_READINESS_CHECK','frozen_source_files':len(pins),
            'executed_source_files':len(sources),'full_history_rows':HISTORY_ROWS,'categories_per_model':14,
            'planned_records':retention['projected_records'],'planned_bytes':retention['projected_bytes'],
            'activation':False,'new_captures_or_forecasts_generated':False,
            'statistical_comparison_or_qualification':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--store-root',type=Path)
    args=parser.parse_args()
    require(args.report is not None or args.store_root is not None,'provide a report or diagnostic store')
    result={}
    if args.report is not None:
        report,sha,_=load_receipt(args.report)
        result['report']=verify_readiness(report,args.root)
        result['report_file_sha256']=sha
    if args.store_root is not None:
        result['store']=verify_store(args.store_root)
    result['verified_at']=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    print(json.dumps(result,sort_keys=True,allow_nan=False))


if __name__=='__main__':
    try:
        main()
    except (VerificationError,OSError,KeyError,TypeError) as error:
        raise SystemExit('PROS004 VERIFICATION FAILED: '+str(error))

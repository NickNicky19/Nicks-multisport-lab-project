import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
import {productionPolicy, validateProductionCollection, verifyProductionHashes, renderProductionResearch, productionViewCounts} from '../production.mjs';

const fixture=JSON.parse(readFileSync(new URL('../../tests/fixtures/sdv-production-v2-synthetic.json',import.meta.url),'utf8'));

test('new operating policy and producer pins independently recover without promoting development records',async()=>{
  const before=JSON.stringify(fixture),collection=validateProductionCollection(fixture.index,fixture.pages);
  await verifyProductionHashes(fixture.index,fixture.pages,webcrypto);
  assert.deepEqual(collection.plans[0].policy,productionPolicy('v2'));
  assert.equal(collection.forecasts.every(f=>f.body.producer_binding.schema_version==='nba-sdv-production-producer-binding-v2'&&f.body.categories.length===14&&f.body.issued_at===null),true);
  assert.deepEqual(productionViewCounts(collection),{upcoming:0,history:0,development:2,genuine:0,eligible:0});
  const html=renderProductionResearch(collection,{now:Date.parse(fixture.index.generated_at)});
  assert.match(html,/Development preview · not issued/);
  assert.match(html,/Conditional on the player appearing/);
  assert.equal(JSON.stringify(fixture),before);
});

test('mixed-generation publisher index cannot substitute its policy for an original',()=>{
  const changed=structuredClone(fixture);
  const row=changed.pages.flatMap(p=>p.records).find(r=>JSON.parse(r.record_json).schema_version==='nba-sdv-production-input-v1');
  const body=JSON.parse(row.record_json);
  body.policy=productionPolicy('v1');
  row.record_json=JSON.stringify(body);
  assert.throws(()=>validateProductionCollection(changed.index,changed.pages),/plan|policy|source|identity/i);
});

test('source bindings require every registered operating file and reject unregistered versions',()=>{
  for(const mutate of [b=>delete b.files['multisport_lab/sdv_production_held.py'],b=>b.schema_version='nba-sdv-production-producer-binding-v3']){
    const changed=structuredClone(fixture),row=changed.pages.flatMap(p=>p.records).find(r=>JSON.parse(r.record_json).schema_version==='nba-sdv-production-plan-v1'),body=JSON.parse(row.record_json);
    mutate(body.producer_binding);row.record_json=JSON.stringify(body);
    assert.throws(()=>validateProductionCollection(changed.index,changed.pages),/binding|inventory/i);
  }
});

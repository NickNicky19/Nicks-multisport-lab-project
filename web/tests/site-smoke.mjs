// Built-artifact checks only. Browser rendering and live deployment are separate evidence.
import {readFile, readdir} from 'node:fs/promises';
import {resolve, join} from 'node:path';
import {webcrypto} from 'node:crypto';
import assert from 'node:assert/strict';
import {loadSnapshot} from '../snapshot.mjs';

const root = resolve(process.argv[2] || 'output');
const html = await readFile(join(root, 'index.html'), 'utf8');
assert.match(html, /<html lang="en">/);
const assets = [...html.matchAll(/(?:src|href)="(\.\/[^"]+)"/g)].map(match => match[1]);
for (const asset of assets) await readFile(join(root, asset));
assert.ok(!/(?:src|href)="\/(?!\/)/.test(html), 'Assets must retain the Pages repository prefix');
const files = await readdir(root);
assert.ok(!files.includes('tests') && !files.includes('.git') && !files.includes('raw'), 'Artifact must exclude tests, repository and raw archives');
const requests = [];
const snapshot = await loadSnapshot(async path => {assert.ok(path.startsWith('./data/')); requests.push(path); return new Response(await readFile(join(root, path)));}, webcrypto);
assert.equal(snapshot.errors.length, 0);
assert.equal(snapshot.sports.length, snapshot.manifest.supported_sports.length);
assert.equal(snapshot.sports[0].coverage.paper, 'NO_ACTION');
for (const file of ['app.mjs', 'scope.mjs', 'snapshot.mjs', 'research.mjs']) await readFile(join(root, file));
console.log(`PASS: artifact root, ${assets.length} relative assets, ${requests.length} validated data files, all-13 NBA inventory and research-only NO_ACTION. Browser/deployment not established by this smoke check.`);

import test from 'node:test';
import assert from 'node:assert/strict';
import {resolveSportScope, filterRowsByScope, filterCandidateUniverse, validRequestedLegCount} from '../scope.mjs';

const supported = ['NBA', 'WNBA']; // Synthetic second-sport coverage tests; no real WNBA admission.
const rows = [{league: 'NBA', side: 'OVER'}, {league: 'WNBA', side: 'UNDER'}, {league: 'NFL', side: 'OVER'}, {league: 'NBA', side: 'UNKNOWN'}];

test('single, selected and all use actual supported research coverage', () => {
  assert.deepEqual(resolveSportScope({mode: 'SINGLE', sports: ['NBA']}, supported), ['NBA']);
  assert.deepEqual(resolveSportScope({mode: 'SELECTED', sports: ['WNBA', 'NBA']}, supported), ['WNBA', 'NBA']);
  assert.deepEqual(resolveSportScope({mode: 'ALL', sports: []}, supported), supported);
  assert.deepEqual(resolveSportScope({mode: 'ALL', sports: []}, ['NBA']), ['NBA']);
});

test('invalid, duplicate, empty selected and unsupported scopes fail closed', () => {
  for (const scope of [{mode: 'SINGLE', sports: []}, {mode: 'SINGLE', sports: ['NBA', 'WNBA']}, {mode: 'SELECTED', sports: []}, {mode: 'SELECTED', sports: ['NBA', 'NBA']}, {mode: 'SELECTED', sports: ['NBA', 'NFL']}, {mode: 'ALL', sports: ['NFL']}, {mode: 'ALL', sports: ['NBA']}, {mode: 'ALL'}, {mode: 'UNRECOGNIZED', sports: []}, null]) assert.deepEqual(resolveSportScope(scope, supported), []);
  assert.deepEqual(resolveSportScope({mode: 'ALL', sports: []}, ['NBA', 'NBA']), []);
  assert.deepEqual(resolveSportScope({mode: 'ALL', sports: []}, ['NBA', 3]), []);
});

test('display rows and builder candidate universe cannot escape selected group', () => {
  const scope = {mode: 'SELECTED', sports: ['WNBA']};
  assert.deepEqual(filterRowsByScope(rows, scope, supported), [rows[1]]);
  assert.deepEqual(filterCandidateUniverse(rows, scope, supported, 'MIXED'), [rows[1]]);
  assert.deepEqual(filterCandidateUniverse(rows, scope, supported, 'OVER_ONLY'), []);
  assert.deepEqual(filterCandidateUniverse(rows, {mode: 'ALL', sports: []}, supported, 'MIXED'), [rows[0], rows[1]]);
});

test('directions filter exactly and never manufacture or qualify candidates', () => {
  const scope = {mode: 'SINGLE', sports: ['NBA']};
  assert.deepEqual(filterCandidateUniverse(rows, scope, supported, 'OVER_ONLY'), [rows[0]]);
  assert.deepEqual(filterCandidateUniverse(rows, scope, supported, 'UNDER_ONLY'), []);
  assert.deepEqual(filterCandidateUniverse(rows, scope, supported, 'MIXED'), [rows[0]]);
  assert.deepEqual(filterCandidateUniverse(rows, scope, supported, 'INVALID'), []);
  assert.deepEqual(filterCandidateUniverse([], scope, supported, 'MIXED'), []);
});

test('only integral requests from two to six legs are supported', () => {
  for (const count of [2, 3, 4, 5, 6]) assert.equal(validRequestedLegCount(count), true);
  for (const count of [0, 1, 7, 2.5, '6', null, NaN, Infinity]) assert.equal(validRequestedLegCount(count), false);
});

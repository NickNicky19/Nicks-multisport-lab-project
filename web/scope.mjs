/** A scope is closed: invalid, empty or unsupported selections resolve to no sports.
 * supportedSports denotes actual published research coverage, not admission.
 */
export function resolveSportScope(scope, supportedSports) {
  if (!scope || !Array.isArray(supportedSports) || !Array.isArray(scope.sports)) return [];
  if (!supportedSports.length || new Set(supportedSports).size !== supportedSports.length || supportedSports.some(value => typeof value !== 'string' || !/^[A-Z]+$/.test(value))) return [];
  const supported = supportedSports;
  if (new Set(scope.sports).size !== scope.sports.length || scope.sports.some(value => !supported.includes(value))) return [];
  if (scope.mode === 'ALL') return scope.sports.length === 0 ? [...supported] : [];
  if (!['SINGLE', 'SELECTED'].includes(scope.mode) || !Array.isArray(scope.sports)) return [];
  const selected = scope.sports;
  if (!selected.length || (scope.mode === 'SINGLE' && selected.length !== 1)) return [];
  if (selected.some(value => !supported.includes(value))) return [];
  return selected;
}

export function filterRowsByScope(rows, scope, supportedSports) {
  const selected = new Set(resolveSportScope(scope, supportedSports));
  return rows.filter(row => row && selected.has(row.league));
}

/** Mode filtering never manufactures a candidate or expands the sport scope. */
export function filterCandidateUniverse(rows, scope, supportedSports, mode) {
  if (!['OVER_ONLY', 'UNDER_ONLY', 'MIXED'].includes(mode)) return [];
  return filterRowsByScope(rows, scope, supportedSports).filter(row =>
    ['OVER', 'UNDER'].includes(row.side) && (mode === 'MIXED' || row.side === mode.replace('_ONLY', ''))
  );
}

export function validRequestedLegCount(value) {
  return Number.isInteger(value) && value >= 2 && value <= 6;
}

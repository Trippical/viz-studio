// Spec 12.3, Vega-Lite: null loader, actions off, canvas renderer, interpreter
// instead of eval, and reject url / values / href / image marks / usermeta /
// datasets at any depth. Finding A5 adds: data only at the top level, and no
// sequence / graticule / sphere generators (they make rows out of nothing and
// can freeze the tab). Pure: no DOM, no vega import.
import { SanitizeError, assertPlain, deepClone, isPlainObject, walk } from './common';

export const RULES: readonly string[] = [
  'spec must be a plain JSON object',
  'top-level data must be exactly {"name": "data"}',
  'key "data" rejected below the top level',
  'key "url" rejected at any depth',
  'key "values" rejected at any depth',
  'key "href" rejected at any depth',
  'key "usermeta" rejected at any depth',
  'key "datasets" rejected at any depth',
  'data generators "sequence", "graticule", "sphere" rejected at any depth',
  'image marks rejected',
  'loader refuses load, sanitize, http and file',
  'actions menu off, canvas renderer, ast interpreter (no eval)',
];

// Keep this declaration in this exact form: tests/test_forbidden_keys.py parses it
// and requires schemas/chart.schema.json to forbid the same keys.
const FORBIDDEN_KEYS = new Set(['url', 'values', 'href', 'usermeta', 'datasets']);

// Finding A5. Mirrored in viz/schemas.py::_check_vegalite, not in the schema enum.
const DATA_GENERATORS = new Set(['sequence', 'graticule', 'sphere']);

const TOP_LEVEL_DATA_PATH = 'spec/data';

export function sanitize(spec: unknown): Record<string, unknown> {
  assertPlain(spec);
  if (!isPlainObject(spec)) throw new SanitizeError('vega-lite spec must be an object');
  const clean = deepClone(spec);
  const data = clean.data;
  if (!isPlainObject(data) || Object.keys(data).length !== 1 || data.name !== 'data') {
    throw new SanitizeError('vega-lite data must be exactly {"name": "data"}');
  }
  walk(clean, (_obj, key, value, path) => {
    if (key === 'data' && path !== TOP_LEVEL_DATA_PATH) throw new SanitizeError(`${path}: data is only allowed at the top level`);
    if (DATA_GENERATORS.has(key)) throw new SanitizeError(`${path}: data generator "${key}" is not allowed`);
    if (FORBIDDEN_KEYS.has(key)) throw new SanitizeError(`${path}: key "${key}" is not allowed`);
    if (key === 'mark' && (value === 'image' || (isPlainObject(value) && value.type === 'image'))) {
      throw new SanitizeError(`${path}: image marks are not allowed`);
    }
  });
  return clean;
}

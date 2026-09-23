// Spec 12.3, Vega-Lite: null loader, actions off, canvas renderer, interpreter
// instead of eval, and reject url / values / href / image marks / usermeta at
// any depth. Pure: no DOM, no vega import.
import { SanitizeError, assertPlain, deepClone, isPlainObject, walk } from './common';

export const RULES: readonly string[] = [
  'spec must be a plain JSON object',
  'top-level data must be exactly {"name": "data"}',
  'key "url" rejected at any depth',
  'key "values" rejected at any depth',
  'key "href" rejected at any depth',
  'key "usermeta" rejected at any depth',
  'image marks rejected',
  'loader refuses load, sanitize, http and file',
  'actions menu off, canvas renderer, ast interpreter (no eval)',
];

const FORBIDDEN_KEYS = new Set(['url', 'values', 'href', 'usermeta']);

export function sanitize(spec: unknown): Record<string, unknown> {
  assertPlain(spec);
  if (!isPlainObject(spec)) throw new SanitizeError('vega-lite spec must be an object');
  const clean = deepClone(spec);
  const data = clean.data;
  if (!isPlainObject(data) || Object.keys(data).length !== 1 || data.name !== 'data') {
    throw new SanitizeError('vega-lite data must be exactly {"name": "data"}');
  }
  walk(clean, (_obj, key, value, path) => {
    if (FORBIDDEN_KEYS.has(key)) throw new SanitizeError(`${path}: key "${key}" is not allowed`);
    if (key === 'mark' && (value === 'image' || (isPlainObject(value) && value.type === 'image'))) {
      throw new SanitizeError(`${path}: image marks are not allowed`);
    }
  });
  return clean;
}

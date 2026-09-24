// Spec 12.3, ECharts: richText tooltips everywhere, DOM-reaching keys removed,
// formatters must be HTML-free strings (never functions), no inline data,
// dataset injected by the adapter, canvas renderer. Pure.
import { SanitizeError, assertPlain, deepClone, isPlainObject, walk } from './common';

export const RULES: readonly string[] = [
  'spec must be a plain JSON object',
  'key "dataset" rejected at any depth (the adapter injects it)',
  'key "data" rejected at any depth (no inline data)',
  'key "image" rejected at any depth (no pattern-fill images)',
  'string values starting with "image://" are rejected at any depth (no image:// symbols)',
  'keys link, sublink, graphic, extraCssText, appendTo, className deleted at any depth',
  'formatter must be a string (never a function)',
  'formatter must not contain "<"',
  'tooltip true or an object is forced to renderMode richText; tooltip false stays false; any other tooltip value is rejected',
  'any other renderMode is overwritten to richText',
  'series must be an object or an array of objects',
  'canvas renderer',
];

const DELETE_KEYS = new Set(['link', 'sublink', 'graphic', 'extraCssText', 'appendTo', 'className']);
const REJECT_KEYS = new Set(['dataset', 'data', 'image']);

export function sanitize(spec: unknown): Record<string, unknown> {
  assertPlain(spec);
  if (!isPlainObject(spec)) throw new SanitizeError('echarts spec must be an object');
  const clean = deepClone(spec);
  walk(clean, (obj, key, value, path) => {
    if (REJECT_KEYS.has(key)) throw new SanitizeError(`${path}: key "${key}" is not allowed`);
    if (DELETE_KEYS.has(key)) {
      delete obj[key];
      return;
    }
    if (typeof value === 'string' && value.startsWith('image://')) {
      throw new SanitizeError(`${path}: image URLs are not allowed`);
    }
    if (key === 'formatter') {
      if (typeof value !== 'string') throw new SanitizeError(`${path}: formatter must be a string`);
      if (value.includes('<')) throw new SanitizeError(`${path}: formatter must not contain HTML`);
    }
    if (key === 'tooltip') {
      if (value === false) {
        // an author-disabled tooltip stays disabled
      } else if (value === true) {
        obj[key] = { renderMode: 'richText' };
      } else if (isPlainObject(value)) {
        value.renderMode = 'richText';
      } else {
        throw new SanitizeError(`${path}: tooltip must be true, false, or an object`);
      }
    }
    if (key === 'renderMode' && value !== 'richText') obj[key] = 'richText';
  });
  const series = clean.series;
  if (series !== undefined) {
    const list = Array.isArray(series) ? series : [series];
    list.forEach((s, i) => {
      if (!isPlainObject(s)) throw new SanitizeError(`spec/series/${i}: series must be an object`);
    });
    clean.series = list;
  }
  return clean;
}

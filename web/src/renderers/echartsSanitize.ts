// Spec 12.3, ECharts: richText tooltips everywhere, DOM-reaching keys removed,
// formatters must be HTML-free strings (never functions), no inline data,
// dataset injected by the adapter, canvas renderer. Pure.
import { SanitizeError, assertPlain, deepClone, isPlainObject, walk } from './common';

export const RULES: readonly string[] = [
  'spec must be a plain JSON object',
  'key "dataset" rejected at any depth (the adapter injects it)',
  'key "data" rejected at any depth (no inline data)',
  'keys link, sublink, graphic, extraCssText, appendTo, className deleted at any depth',
  'formatter must be a string (never a function)',
  'formatter must not contain "<"',
  'every tooltip gets renderMode richText; any other renderMode is overwritten',
  'series must be an object or an array of objects',
  'canvas renderer',
];

const DELETE_KEYS = new Set(['link', 'sublink', 'graphic', 'extraCssText', 'appendTo', 'className']);
const REJECT_KEYS = new Set(['dataset', 'data']);

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
    if (key === 'formatter') {
      if (typeof value !== 'string') throw new SanitizeError(`${path}: formatter must be a string`);
      if (value.includes('<')) throw new SanitizeError(`${path}: formatter must not contain HTML`);
    }
    if (key === 'tooltip') {
      if (isPlainObject(value)) value.renderMode = 'richText';
      else obj[key] = { renderMode: 'richText' };
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

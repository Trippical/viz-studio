// Spec 12.3, Plotly: cloud/editor off (adapter config), geo and map traces
// rejected, layout.images and map layouts deleted, "<" escaped in bound text,
// column binding as a strict walk. Mirrors _check_plotly in viz/schemas.py.
import { SanitizeError, assertPlain, deepClone, isPlainObject, walk } from './common';

export const RULES: readonly string[] = [
  'spec must be a plain object with only "traces" and "layout"',
  'traces must be a non-empty array of plain objects',
  'trace types scattergeo, choropleth, scattermapbox, choroplethmapbox, densitymapbox, scattermap, choroplethmap, densitymap rejected',
  'x, y, z, text, hovertext, labels, values, customdata must be {"column": name} bindings',
  'split, when present, must be a string',
  'layout keys images, mapbox, map, geo deleted at any depth',
  'keys __proto__, constructor, prototype dropped',
  '"<" escaped in every string bound to text or hovertext',
  'cloud export, chart studio and the Plotly logo disabled in config',
];

export const BOUND_KEYS = ['x', 'y', 'z', 'text', 'hovertext', 'labels', 'values', 'customdata'] as const;

export const FORBIDDEN_TRACE_TYPES = new Set([
  'scattergeo',
  'choropleth',
  'scattermapbox',
  'choroplethmapbox',
  'densitymapbox',
  'scattermap',
  'choroplethmap',
  'densitymap',
]);

const LAYOUT_DELETE_KEYS = new Set(['images', 'mapbox', 'map', 'geo']);

export interface PlotlySpec {
  traces: Record<string, unknown>[];
  layout: Record<string, unknown>;
}

export function sanitize(spec: unknown): PlotlySpec {
  assertPlain(spec);
  if (!isPlainObject(spec)) throw new SanitizeError('plotly spec must be an object');
  for (const key of Object.keys(spec)) {
    if (key !== 'traces' && key !== 'layout') throw new SanitizeError(`spec/${key}: plotly spec allows only traces and layout`);
  }
  const clean = deepClone(spec);
  const traces = clean.traces;
  if (!Array.isArray(traces) || traces.length === 0) throw new SanitizeError('spec/traces: must be a non-empty array');
  traces.forEach((trace, i) => {
    if (!isPlainObject(trace)) throw new SanitizeError(`spec/traces/${i}: must be an object`);
    if (typeof trace.type === 'string' && FORBIDDEN_TRACE_TYPES.has(trace.type)) {
      throw new SanitizeError(`spec/traces/${i}/type: geo and map traces are not allowed`);
    }
    for (const key of BOUND_KEYS) {
      if (!(key in trace)) continue;
      const binding = trace[key];
      if (!isPlainObject(binding) || Object.keys(binding).length !== 1 || typeof binding.column !== 'string') {
        throw new SanitizeError(`spec/traces/${i}/${key}: must be a column binding {"column": name}`);
      }
    }
    if ('split' in trace && typeof trace.split !== 'string') throw new SanitizeError(`spec/traces/${i}/split: must be a column name`);
  });
  let layout: Record<string, unknown> = {};
  if (clean.layout !== undefined) {
    if (!isPlainObject(clean.layout)) throw new SanitizeError('spec/layout: must be an object');
    layout = clean.layout;
    walk(layout, (obj, key) => {
      if (LAYOUT_DELETE_KEYS.has(key)) delete obj[key];
    }, 'spec/layout');
  }
  return { traces: traces as Record<string, unknown>[], layout };
}

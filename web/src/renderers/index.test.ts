import { describe, expect, it } from 'vitest';
import { SanitizeError } from './common';
import { RULE_COUNTS, getAdapter, sanitizeSpec } from './index';

describe('registry', () => {
  it('returns a fresh adapter per call for vega-lite', () => {
    const a = getAdapter('vega-lite');
    expect(typeof a.mount).toBe('function');
    expect(getAdapter('vega-lite')).not.toBe(a);
  });
  it('rejects unknown renderers and stat', () => {
    expect(() => getAdapter('stat')).toThrow(SanitizeError);
    expect(() => getAdapter('d3')).toThrow(SanitizeError);
    expect(() => getAdapter('__proto__')).toThrow(SanitizeError);
    expect(() => sanitizeSpec('toString', {})).toThrow(SanitizeError);
  });
  it('rejects the renderers retired after the bake-off', () => {
    for (const r of ['plotly', 'echarts']) {
      expect(() => getAdapter(r)).toThrow(SanitizeError);
      expect(() => sanitizeSpec(r, {})).toThrow(SanitizeError);
    }
    expect(Object.keys(RULE_COUNTS)).toEqual(['vega-lite']);
  });
  it('sanitizes vega-lite and counts its rules', () => {
    expect(sanitizeSpec('vega-lite', { data: { name: 'data' }, mark: 'bar' })).toEqual({ data: { name: 'data' }, mark: 'bar' });
    expect(RULE_COUNTS['vega-lite']).toBeGreaterThan(0);
  });
});

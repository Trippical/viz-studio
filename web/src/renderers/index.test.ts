import { describe, expect, it } from 'vitest';
import { SanitizeError } from './common';
import { RULE_COUNTS, getAdapter, sanitizeSpec } from './index';

describe('registry', () => {
  it('returns a fresh adapter per call for each renderer', () => {
    for (const r of ['vega-lite', 'plotly', 'echarts']) {
      const a = getAdapter(r);
      expect(typeof a.mount).toBe('function');
      expect(getAdapter(r)).not.toBe(a);
    }
  });
  it('rejects unknown renderers and stat', () => {
    expect(() => getAdapter('stat')).toThrow(SanitizeError);
    expect(() => getAdapter('d3')).toThrow(SanitizeError);
    expect(() => getAdapter('__proto__')).toThrow(SanitizeError);
    expect(() => sanitizeSpec('toString', {})).toThrow(SanitizeError);
  });
  it('sanitizes per renderer and counts rules', () => {
    expect(sanitizeSpec('vega-lite', { data: { name: 'data' }, mark: 'bar' })).toEqual({ data: { name: 'data' }, mark: 'bar' });
    expect(RULE_COUNTS['vega-lite']).toBeGreaterThan(0);
    expect(RULE_COUNTS.plotly).toBeGreaterThan(0);
    expect(RULE_COUNTS.echarts).toBeGreaterThan(0);
  });
});

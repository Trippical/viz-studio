import { describe, expect, it } from 'vitest';
import { SanitizeError } from './common';
import { RULES, sanitize } from './vegaLiteSanitize';

const base = {
  data: { name: 'data' },
  mark: 'line',
  encoding: { x: { field: 'month', type: 'temporal' }, y: { field: 'revenue', type: 'quantitative' } },
};

describe('vega-lite sanitize', () => {
  it('returns a deep copy of a clean spec', () => {
    const out = sanitize(base);
    expect(out).toEqual(base);
    expect(out).not.toBe(base);
    expect(out.encoding).not.toBe(base.encoding);
  });

  it('requires data to be exactly the named dataset', () => {
    expect(() => sanitize({ ...base, data: { name: 'data', url: 'x' } })).toThrow(SanitizeError);
    expect(() => sanitize({ ...base, data: { name: 'other' } })).toThrow(SanitizeError);
    expect(() => sanitize({ ...base, data: undefined })).toThrow(SanitizeError);
    expect(() => sanitize({ mark: 'line' })).toThrow(SanitizeError);
  });

  it('rejects url, values, href and usermeta at any depth', () => {
    expect(() => sanitize({ ...base, layer: [{ data: { url: 'https://x' }, mark: 'point' }] })).toThrow(/url/);
    expect(() => sanitize({ ...base, encoding: { ...base.encoding, href: { field: 'link' } } })).toThrow(/href/);
    expect(() => sanitize({ ...base, transform: [{ lookup: 'a', from: { data: { values: [1] }, key: 'a' } }] })).toThrow(/values/);
    expect(() => sanitize({ ...base, usermeta: { x: 1 } })).toThrow(/usermeta/);
  });

  it('rejects inline datasets at any depth', () => {
    expect(() =>
      sanitize({
        ...base,
        mark: 'bar',
        datasets: { mal: [{ x: 1 }] },
        layer: [{ data: { name: 'mal' }, mark: 'point' }],
      }),
    ).toThrow(SanitizeError);
    expect(() =>
      sanitize({
        ...base,
        layer: [{ data: { name: 'data' }, mark: 'point', datasets: { mal: [{ x: 1 }] } }],
      }),
    ).toThrow(/datasets/);
  });

  it('rejects image marks in both forms', () => {
    expect(() => sanitize({ ...base, mark: 'image' })).toThrow(/image/);
    expect(() => sanitize({ ...base, layer: [{ mark: { type: 'image' } }] })).toThrow(/image/);
  });

  it('rejects non-plain values', () => {
    expect(() => sanitize({ ...base, encoding: { x: { field: 'a', scale: { domain: new Date() } } } })).toThrow(SanitizeError);
    expect(() => sanitize('line')).toThrow(SanitizeError);
  });

  it('publishes its rule list', () => {
    expect(RULES.length).toBeGreaterThanOrEqual(6);
  });
});

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
    expect(() => sanitize({ ...base, layer: [{ mark: 'point', encoding: { x: { field: 'a', url: 'https://x' } } }] })).toThrow(/url/);
    expect(() => sanitize({ ...base, encoding: { ...base.encoding, href: { field: 'link' } } })).toThrow(/href/);
    expect(() => sanitize({ ...base, transform: [{ calculate: '1', as: 'x', values: [1] }] })).toThrow(/values/);
    expect(() => sanitize({ ...base, usermeta: { x: 1 } })).toThrow(/usermeta/);
  });

  it('rejects inline datasets at any depth', () => {
    expect(() =>
      sanitize({
        ...base,
        mark: 'bar',
        datasets: { mal: [{ x: 1 }] },
        layer: [{ mark: 'point' }],
      }),
    ).toThrow(SanitizeError);
    expect(() =>
      sanitize({
        ...base,
        layer: [{ mark: 'point', datasets: { mal: [{ x: 1 }] } }],
      }),
    ).toThrow(/datasets/);
  });

  it('rejects data below the top level, even the named dataset (A5)', () => {
    expect(() => sanitize({ ...base, layer: [{ data: { name: 'data' }, mark: 'point' }] })).toThrow(
      'spec/layer/0/data: data is only allowed at the top level',
    );
    expect(() => sanitize({ ...base, layer: [{ data: { sequence: { start: 0, stop: 1e9 } }, mark: 'point' }] })).toThrow(SanitizeError);
    expect(() => sanitize({ ...base, hconcat: [{ data: { name: 'data' }, mark: 'bar' }] })).toThrow(/top level/);
    expect(() => sanitize({ ...base, transform: [{ lookup: 'a', from: { data: { name: 'data' }, key: 'a' } }] })).toThrow(/top level/);
  });

  it('rejects the sequence, graticule and sphere generators anywhere (A5)', () => {
    for (const key of ['sequence', 'graticule', 'sphere']) {
      expect(() => sanitize({ ...base, transform: [{ [key]: true }] }), key).toThrow(`data generator "${key}" is not allowed`);
    }
    expect(() => sanitize({ ...base, data: { name: 'data', sequence: { start: 0, stop: 10 } } })).toThrow(SanitizeError);
  });

  it('keeps accepting a layered chart that inherits the top-level data', () => {
    const layered = { data: { name: 'data' }, layer: [{ mark: 'line', encoding: base.encoding }, { mark: 'rule', encoding: { y: { datum: 1 } } }] };
    expect(sanitize(layered)).toEqual(layered);
  });

  it('rejects params[].bind.element at any depth (A6)', () => {
    expect(() =>
      sanitize({ ...base, params: [{ name: 'p', value: 1, bind: { input: 'range', min: 0, max: 10, element: '#elsewhere' } }] }),
    ).toThrow('spec/params/0/bind: bind.element is not allowed');
    expect(() => sanitize({ ...base, layer: [{ mark: 'point', params: [{ name: 'q', bind: { input: 'checkbox', element: 'body' } }] }] })).toThrow(
      /bind\.element/,
    );
    expect(() => sanitize({ ...base, params: [{ name: 'p', value: 1, bind: { input: 'range', min: 0, max: 10 } }] })).not.toThrow();
    expect(() => sanitize({ ...base, params: [{ name: 'sel', select: 'point', bind: 'legend' }] })).not.toThrow();
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
    expect(RULES).toContain('key "data" rejected below the top level');
    expect(RULES).toContain('data generators "sequence", "graticule", "sphere" rejected at any depth');
  });
});

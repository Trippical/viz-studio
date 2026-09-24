import { describe, expect, it } from 'vitest';
import { SanitizeError } from './common';
import { RULES, sanitize } from './plotlySanitize';

const base = {
  traces: [{ type: 'bar', x: { column: 'region' }, y: { column: 'orders' }, name: 'Orders' }],
  layout: { title: { text: 'Orders' }, barmode: 'group' },
};

describe('plotly sanitize', () => {
  it('accepts the binding shape and copies it', () => {
    const out = sanitize(base);
    expect(out).toEqual(base);
    expect(out.traces).not.toBe(base.traces);
    expect(sanitize({ traces: base.traces }).layout).toEqual({});
  });

  it('allows only traces and layout at the top level', () => {
    expect(() => sanitize({ ...base, frames: [] })).toThrow(/frames/);
    expect(() => sanitize({ layout: {} })).toThrow(/traces/);
    expect(() => sanitize({ traces: [] })).toThrow(/traces/);
    expect(() => sanitize({ traces: ['bar'] })).toThrow(/traces\/0/);
  });

  it('rejects geo and map trace types', () => {
    for (const type of ['scattergeo', 'choropleth', 'scattermapbox', 'choroplethmapbox', 'densitymapbox', 'scattermap', 'choroplethmap', 'densitymap']) {
      expect(() => sanitize({ traces: [{ type }] })).toThrow(/geo|map/);
    }
  });

  it('requires bound keys to be column bindings', () => {
    expect(() => sanitize({ traces: [{ type: 'bar', x: [1, 2] }] })).toThrow(/x/);
    expect(() => sanitize({ traces: [{ type: 'bar', x: { column: 'a', extra: 1 } }] })).toThrow(/x/);
    expect(() => sanitize({ traces: [{ type: 'bar', text: { column: 5 } }] })).toThrow(/text/);
    expect(() => sanitize({ traces: [{ type: 'bar', split: 3 }] })).toThrow(/split/);
  });

  it('strips images, mapbox, map and geo from the layout at any depth', () => {
    const out = sanitize({
      traces: base.traces,
      layout: { images: [{ source: 'https://x' }], mapbox: {}, map: {}, geo: {}, xaxis: { images: [] }, title: { text: 'ok' } },
    });
    expect(out.layout).toEqual({ xaxis: {}, title: { text: 'ok' } });
  });

  it('rejects non-plain values and prototype keys', () => {
    expect(() => sanitize({ traces: [{ type: 'bar', marker: { color: () => 1 } }] })).toThrow(SanitizeError);
    expect(sanitize(JSON.parse('{"traces":[{"type":"bar","__proto__":{"x":1}}]}')).traces[0]).toEqual({ type: 'bar' });
  });

  it('rejects anchor tags anywhere in the spec but allows other tags', () => {
    expect(() =>
      sanitize({ traces: base.traces, layout: { title: { text: 'x <a href="javascript:alert(1)">y</a>' } } }),
    ).toThrow(/anchor/);
    expect(() => sanitize({ traces: base.traces, layout: { title: { text: 'line<br>two' } } })).not.toThrow();
    expect(() =>
      sanitize({ traces: [{ type: 'bar', hovertemplate: '%{y}<extra></extra>' }] }),
    ).not.toThrow();
    expect(() => sanitize({ traces: [{ type: 'bar', name: '<A HREF=x>' }] })).toThrow(/anchor/);
  });

  it('publishes its rule list', () => {
    expect(RULES.length).toBeGreaterThanOrEqual(6);
  });
});

import { describe, expect, it } from 'vitest';
import { SanitizeError } from './common';
import { RULES, sanitize } from './echartsSanitize';

const base = {
  xAxis: { type: 'category' },
  yAxis: { type: 'value' },
  tooltip: { trigger: 'axis' },
  series: [{ type: 'bar', encode: { x: 'region', y: 'orders' } }],
};

describe('echarts sanitize', () => {
  it('forces richText tooltips everywhere', () => {
    const out = sanitize({ ...base, series: [{ ...base.series[0], tooltip: { formatter: '{b}' } }] });
    expect((out.tooltip as Record<string, unknown>).renderMode).toBe('richText');
    const series = out.series as Record<string, unknown>[];
    expect((series[0].tooltip as Record<string, unknown>).renderMode).toBe('richText');
    expect(sanitize({ ...base, tooltip: true }).tooltip).toEqual({ renderMode: 'richText' });
    expect(sanitize({ ...base, tooltip: { renderMode: 'html' } }).tooltip).toEqual({ renderMode: 'richText' });
  });

  it('keeps tooltip false as false and rejects other tooltip types', () => {
    expect(sanitize({ ...base, tooltip: false }).tooltip).toBe(false);
    expect(() => sanitize({ ...base, tooltip: 'x' })).toThrow(SanitizeError);
    expect(() => sanitize({ ...base, tooltip: 3 })).toThrow(SanitizeError);
    expect(() => sanitize({ ...base, tooltip: [] })).toThrow(SanitizeError);
  });

  it('rejects image fills and image:// symbols', () => {
    expect(() =>
      sanitize({ ...base, series: [{ type: 'bar', itemStyle: { color: { image: 'http://evil/x.png' } } }] }),
    ).toThrow(SanitizeError);
    expect(() =>
      sanitize({ ...base, series: [{ type: 'bar', label: { rich: { a: { backgroundColor: { image: 'x' } } } } }] }),
    ).toThrow(SanitizeError);
    expect(() => sanitize({ ...base, series: [{ type: 'scatter', symbol: 'image://http://evil/x.png' }] })).toThrow(
      SanitizeError,
    );
    expect(() => sanitize({ ...base, series: [{ type: 'scatter', symbol: 'circle' }] })).not.toThrow();
  });

  it('deletes the DOM-reaching keys at any depth', () => {
    const out = sanitize({
      ...base,
      graphic: [{ type: 'text' }],
      title: { text: 't', link: 'https://x', sublink: 'https://y' },
      tooltip: { extraCssText: 'x', appendTo: 'body', className: 'c' },
    });
    expect(out.graphic).toBeUndefined();
    expect(out.title).toEqual({ text: 't' });
    expect(out.tooltip).toEqual({ renderMode: 'richText' });
  });

  it('rejects HTML and non-string formatters', () => {
    expect(() => sanitize({ ...base, tooltip: { formatter: '<b>{b}</b>' } })).toThrow(SanitizeError);
    expect(() => sanitize({ ...base, xAxis: { axisLabel: { formatter: '<img>' } } })).toThrow(/formatter/);
    expect(() => sanitize({ ...base, tooltip: { formatter: ['{a}'] } })).toThrow(/formatter/);
    expect(sanitize({ ...base, tooltip: { formatter: '{b}: {c}' } })).toBeTruthy();
  });

  it('rejects dataset and inline data', () => {
    expect(() => sanitize({ ...base, dataset: { source: [] } })).toThrow(/dataset/);
    expect(() => sanitize({ ...base, series: [{ type: 'bar', data: [1, 2] }] })).toThrow(/data/);
  });

  it('requires series to be objects and the spec to be plain', () => {
    expect(() => sanitize({ ...base, series: ['bar'] })).toThrow(SanitizeError);
    expect(() => sanitize({ ...base, series: { type: 'bar' } })).not.toThrow();
    expect(() => sanitize({ ...base, series: [{ type: 'bar', itemStyle: { color: () => 'red' } }] })).toThrow(SanitizeError);
    expect(() => sanitize([])).toThrow(SanitizeError);
  });

  it('publishes its rule list', () => {
    expect(RULES.length).toBeGreaterThanOrEqual(6);
  });
});

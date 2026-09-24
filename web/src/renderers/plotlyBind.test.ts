import { describe, expect, it } from 'vitest';
import { SanitizeError } from './common';
import { bindTraces, escapeLt } from './plotlyBind';

const rows = [
  { region: 'EMEA', orders: 1, label: '<b>x</b>', note: '<b>x</b>' },
  { region: 'NA', orders: 2, label: 'y', note: 'y' },
  { region: 'EMEA', orders: 3, label: 'z', note: 'z' },
];
const columns = [
  { name: 'region', type: 'string' as const },
  { name: 'orders', type: 'integer' as const },
  { name: 'label', type: 'string' as const },
  { name: 'note', type: 'string' as const },
];

describe('bindTraces', () => {
  it('replaces bindings with column arrays and escapes text', () => {
    const out = bindTraces([{ type: 'bar', x: { column: 'region' }, y: { column: 'orders' }, text: { column: 'label' } }], rows, columns);
    expect(out).toEqual([{ type: 'bar', x: ['EMEA', 'NA', 'EMEA'], y: [1, 2, 3], text: ['&lt;b>x&lt;/b>', 'y', 'z'] }]);
  });

  it('escapes customdata the same as text', () => {
    const out = bindTraces([{ type: 'scatter', customdata: { column: 'note' } }], rows, columns);
    expect(out).toEqual([{ type: 'scatter', customdata: ['&lt;b>x&lt;/b>', 'y', 'z'] }]);
  });

  it('escapes every bound value, including labels and category axes like x/y', () => {
    const withMarkup = [{ region: '<a href="x">Q3</a>', orders: 5 }];
    const out = bindTraces([{ type: 'bar', x: { column: 'region' }, y: { column: 'orders' } }], withMarkup, columns);
    expect(out).toEqual([{ type: 'bar', x: ['&lt;a href="x">Q3&lt;/a>'], y: [5] }]);
  });

  it('expands split into one trace per value', () => {
    const out = bindTraces([{ type: 'scatter', split: 'region', x: { column: 'orders' }, y: { column: 'orders' } }], rows, columns);
    expect(out).toEqual([
      { type: 'scatter', name: 'EMEA', x: [1, 3], y: [1, 3] },
      { type: 'scatter', name: 'NA', x: [2], y: [2] },
    ]);
  });

  it('rejects undeclared columns for bindings and split', () => {
    expect(() => bindTraces([{ type: 'bar', x: { column: 'nope' } }], rows, columns)).toThrow(SanitizeError);
    expect(() => bindTraces([{ type: 'bar', split: 'nope' }], rows, columns)).toThrow(SanitizeError);
  });

  it('escapeLt only touches strings', () => {
    expect(escapeLt('<a>')).toBe('&lt;a>');
    expect(escapeLt(5)).toBe(5);
    expect(escapeLt(null)).toBeNull();
  });
});

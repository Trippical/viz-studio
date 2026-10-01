import { describe, expect, it } from 'vitest';
import type { Control } from '../api/types';
import type { Filter } from '../data/filters';
import { CLEARED, decodeFilters, encodeFilters } from './urlState';

const controls: Control[] = [
  { id: 'period', type: 'date-range', label: 'Period', column: 'month', default: { last: '1y' } },
  { id: 'region', type: 'select', label: 'Region', column: 'region', multi: true, default: null },
  { id: 'minrev', type: 'number-range', label: 'Revenue', column: 'revenue', default: null },
];
const today = new Date(2026, 8, 22);
const options = { region: { options: ['APAC', 'EMEA', 'NA'], tooMany: false } };

describe('encodeFilters', () => {
  it('writes one parameter per control and marks inactive values', () => {
    const filters: Filter[] = [
      { controlId: 'period', column: 'month', value: { type: 'date-range', from: '2026-01-01', to: null } },
      { controlId: 'region', column: 'region', value: { type: 'select', values: ['EMEA', 'N,A'] } },
      { controlId: 'minrev', column: 'revenue', value: { type: 'number-range', min: null, max: null } },
    ];
    const params = encodeFilters(filters);
    expect(params.get('period')).toBe('2026-01-01..');
    expect(params.get('region')).toBe('EMEA,N%2CA');
    expect(params.get('minrev')).toBe(':none');
  });
});

describe('decodeFilters', () => {
  it('uses defaults when a parameter is absent', () => {
    const out = decodeFilters(new URLSearchParams(''), controls, options, today);
    expect(out).toEqual([
      { controlId: 'period', column: 'month', value: { type: 'date-range', from: '2025-09-22', to: '2026-09-22' } },
      { controlId: 'region', column: 'region', value: { type: 'select', values: [] } },
      { controlId: 'minrev', column: 'revenue', value: { type: 'number-range', min: null, max: null } },
    ]);
  });

  it('round-trips values and honours the cleared marker', () => {
    const params = new URLSearchParams('period=-&region=EMEA,N%2CA,NA&minrev=10..20.5&junk=1');
    const out = decodeFilters(params, controls, options, today);
    expect(out[0].value).toEqual({ type: 'date-range', from: null, to: null });
    expect(out[1].value).toEqual({ type: 'select', values: ['EMEA', 'NA'] }); // "N,A" is not an option
    expect(out[2].value).toEqual({ type: 'number-range', min: 10, max: 20.5 });
  });

  it('rejects malformed dates and numbers by falling back to the default', () => {
    const params = new URLSearchParams('period=2026-13-45..x&minrev=abc..1e999');
    const out = decodeFilters(params, controls, options, today);
    expect(out[0].value).toEqual({ type: 'date-range', from: '2025-09-22', to: '2026-09-22' });
    expect(out[2].value).toEqual({ type: 'number-range', min: null, max: null });
  });

  it('passes select values through while options are unknown', () => {
    const out = decodeFilters(new URLSearchParams('region=ZZ'), controls, {}, today);
    expect(out[1].value).toEqual({ type: 'select', values: ['ZZ'] });
  });

  it('decodes a text filter when the option set is too large', () => {
    const tooMany = { region: { options: [], tooMany: true } };
    expect(decodeFilters(new URLSearchParams('region=~em'), controls, tooMany, today)[1].value).toEqual({ type: 'text', text: 'em' });
    expect(decodeFilters(new URLSearchParams(''), controls, tooMany, today)[1].value).toEqual({ type: 'text', text: '' });
  });
});

describe('the cleared marker (A12)', () => {
  it('cannot collide with a select value, even "-"', () => {
    const withDash = { region: { options: ['-', 'EMEA'], tooMany: false } };
    const filters: Filter[] = [{ controlId: 'region', column: 'region', value: { type: 'select', values: ['-'] } }];
    const params = encodeFilters(filters);
    expect(params.get('region')).toBe('-');
    expect(decodeFilters(params, controls, withDash, today)[1].value).toEqual({ type: 'select', values: ['-'] });
  });

  it('writes and reads the new marker for every control type', () => {
    const cleared: Filter[] = [
      { controlId: 'period', column: 'month', value: { type: 'date-range', from: null, to: null } },
      { controlId: 'region', column: 'region', value: { type: 'select', values: [] } },
      { controlId: 'minrev', column: 'revenue', value: { type: 'number-range', min: null, max: null } },
    ];
    const params = encodeFilters(cleared);
    for (const id of ['period', 'region', 'minrev']) expect(params.get(id)).toBe(CLEARED);
    expect(CLEARED).toBe(':none');
    const out = decodeFilters(new URLSearchParams(params.toString()), controls, options, today);
    expect(out[0].value).toEqual({ type: 'date-range', from: null, to: null });
    expect(out[1].value).toEqual({ type: 'select', values: [] });
    expect(out[2].value).toEqual({ type: 'number-range', min: null, max: null });
  });

  it('still reads the old "-" marker on range controls', () => {
    const out = decodeFilters(new URLSearchParams('period=-&minrev=-'), controls, options, today);
    expect(out[0].value).toEqual({ type: 'date-range', from: null, to: null });
    expect(out[2].value).toEqual({ type: 'number-range', min: null, max: null });
  });
});

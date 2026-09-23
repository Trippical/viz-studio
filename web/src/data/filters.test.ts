import { describe, expect, it } from 'vitest';
import type { Column, Control, Row } from '../api/types';
import {
  MAX_SELECT_OPTIONS,
  applyFilters,
  defaultFilterValue,
  filterKey,
  isActive,
  resolveLast,
  selectOptions,
  type Filter,
} from './filters';

const columns: Column[] = [
  { name: 'month', type: 'date' },
  { name: 'region', type: 'string' },
  { name: 'revenue', type: 'number' },
];

const rows: Row[] = [
  { month: '2026-01-01', region: 'EMEA', revenue: 10 },
  { month: '2026-02-01', region: 'NA', revenue: 20 },
  { month: '2026-03-01', region: 'APAC', revenue: 30 },
  { month: '2026-03-01T12:00:00Z', region: 'EMEA', revenue: 40 },
];

describe('applyFilters', () => {
  it('filters dates by ISO prefix, inclusive', () => {
    const out = applyFilters(rows, columns, [
      { controlId: 'p', column: 'month', value: { type: 'date-range', from: '2026-02-01', to: '2026-03-01' } },
    ]);
    expect(out.map((r) => r.revenue)).toEqual([20, 30, 40]);
  });

  it('filters select by string equality and skips empty selections', () => {
    expect(
      applyFilters(rows, columns, [{ controlId: 'r', column: 'region', value: { type: 'select', values: ['EMEA'] } }]).length,
    ).toBe(2);
    expect(applyFilters(rows, columns, [{ controlId: 'r', column: 'region', value: { type: 'select', values: [] } }]).length).toBe(4);
  });

  it('filters number ranges and open ends', () => {
    expect(
      applyFilters(rows, columns, [{ controlId: 'n', column: 'revenue', value: { type: 'number-range', min: 20, max: null } }]).length,
    ).toBe(3);
    expect(
      applyFilters(rows, columns, [{ controlId: 'n', column: 'revenue', value: { type: 'number-range', min: null, max: 20 } }]).length,
    ).toBe(2);
  });

  it('text filter is a case-insensitive substring match', () => {
    expect(applyFilters(rows, columns, [{ controlId: 'r', column: 'region', value: { type: 'text', text: 'em' } }]).length).toBe(2);
  });

  it('skips filters whose column the chart does not declare', () => {
    expect(applyFilters(rows, columns, [{ controlId: 'x', column: 'nope', value: { type: 'select', values: ['a'] } }]).length).toBe(4);
  });
});

describe('selectOptions', () => {
  it('unions distinct values across charts, sorted', () => {
    const out = selectOptions([rows, [{ region: 'LATAM' }, { region: null }]], 'region');
    expect(out).toEqual({ options: ['APAC', 'EMEA', 'LATAM', 'NA'], tooMany: false });
  });

  it('flags too many options', () => {
    const many: Row[] = Array.from({ length: MAX_SELECT_OPTIONS + 1 }, (_, i) => ({ region: `r${i}` }));
    expect(selectOptions([many], 'region')).toEqual({ options: [], tooMany: true });
  });
});

describe('resolveLast', () => {
  const today = new Date(2026, 8, 22); // 2026-09-22 local
  it('handles d, w, m, y', () => {
    expect(resolveLast('10d', today)).toEqual({ from: '2026-09-12', to: '2026-09-22' });
    expect(resolveLast('2w', today)).toEqual({ from: '2026-09-08', to: '2026-09-22' });
    expect(resolveLast('12m', today)).toEqual({ from: '2025-09-22', to: '2026-09-22' });
    expect(resolveLast('1y', today)).toEqual({ from: '2025-09-22', to: '2026-09-22' });
  });
  it('rejects malformed input', () => {
    expect(() => resolveLast('12', today)).toThrow();
  });
  it('clamps the day at month ends', () => {
    expect(resolveLast('6m', new Date(2026, 7, 31))).toEqual({ from: '2026-02-28', to: '2026-08-31' });
    expect(resolveLast('1y', new Date(2028, 1, 29))).toEqual({ from: '2027-02-28', to: '2028-02-29' });
    expect(resolveLast('1m', new Date(2026, 2, 31))).toEqual({ from: '2026-02-28', to: '2026-03-31' });
  });
});

describe('defaultFilterValue', () => {
  const today = new Date(2026, 8, 22);
  it('resolves control defaults', () => {
    const period: Control = { id: 'p', type: 'date-range', label: 'P', column: 'month', default: { last: '1y' } };
    expect(defaultFilterValue(period, today)).toEqual({ type: 'date-range', from: '2025-09-22', to: '2026-09-22' });
    const region: Control = { id: 'r', type: 'select', label: 'R', column: 'region', multi: true, default: ['EMEA', 'NA'] };
    expect(defaultFilterValue(region, today)).toEqual({ type: 'select', values: ['EMEA', 'NA'] });
    const single: Control = { id: 'r', type: 'select', label: 'R', column: 'region', default: 'EMEA' };
    expect(defaultFilterValue(single, today)).toEqual({ type: 'select', values: ['EMEA'] });
    const none: Control = { id: 'r', type: 'select', label: 'R', column: 'region', default: null };
    expect(defaultFilterValue(none, today)).toEqual({ type: 'select', values: [] });
    expect(defaultFilterValue(none, today, true)).toEqual({ type: 'text', text: '' });
    const n: Control = { id: 'n', type: 'number-range', label: 'N', column: 'revenue', default: { min: 5 } };
    expect(defaultFilterValue(n, today)).toEqual({ type: 'number-range', min: 5, max: null });
  });
});

describe('isActive and filterKey', () => {
  it('detects inactive values', () => {
    expect(isActive({ type: 'select', values: [] })).toBe(false);
    expect(isActive({ type: 'date-range', from: null, to: null })).toBe(false);
    expect(isActive({ type: 'number-range', min: null, max: null })).toBe(false);
    expect(isActive({ type: 'text', text: '' })).toBe(false);
    expect(isActive({ type: 'text', text: 'a' })).toBe(true);
  });
  it('filterKey is stable', () => {
    const f: Filter[] = [{ controlId: 'r', column: 'region', value: { type: 'select', values: ['a'] } }];
    expect(filterKey(f)).toBe(filterKey([...f]));
  });
});

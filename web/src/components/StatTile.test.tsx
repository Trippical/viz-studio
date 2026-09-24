import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SanitizeError } from '../renderers/common';
import { StatTile, aggregate, formatValue, parseStatSpec } from './StatTile';

const rows = [
  { revenue: 10, orders: 1 },
  { revenue: 20, orders: 2 },
  { revenue: 30, orders: 3 },
];

describe('aggregate', () => {
  it('computes every agg and ignores non-numeric values', () => {
    expect(aggregate(rows, 'revenue', 'sum')).toBe(60);
    expect(aggregate(rows, 'revenue', 'avg')).toBe(20);
    expect(aggregate(rows, 'revenue', 'min')).toBe(10);
    expect(aggregate(rows, 'revenue', 'max')).toBe(30);
    expect(aggregate(rows, 'revenue', 'count')).toBe(3);
    expect(aggregate(rows, 'revenue', 'last')).toBe(30);
    expect(aggregate([{ revenue: 'x' }, { revenue: 5 }], 'revenue', 'sum')).toBe(5);
    expect(aggregate([], 'revenue', 'sum')).toBeNull();
  });

  it('handles large row sets without argument overflow', () => {
    const largeRows = Array.from({ length: 200000 }, (_, i) => ({ v: i }));
    expect(aggregate(largeRows, 'v', 'min')).toBe(0);
    expect(aggregate(largeRows, 'v', 'max')).toBe(199999);
  });
});

describe('formatValue', () => {
  it('uses d3-format and falls back on a bad format', () => {
    expect(formatValue(1234.5, '$,.0f')).toBe('$1,235');
    expect(formatValue(1234.5)).toBe('1,234.5');
    expect(formatValue(1234.5, '%%%%q')).toBe('1234.5');
    expect(formatValue(null, '$,.0f')).toBe('–');
  });
});

describe('parseStatSpec', () => {
  it('accepts a valid spec and rejects unknown columns, aggs and shapes', () => {
    expect(parseStatSpec({ value: 'revenue', agg: 'sum' }, ['revenue'])).toEqual({ value: 'revenue', agg: 'sum' });
    expect(() => parseStatSpec({ value: 'nope', agg: 'sum' }, ['revenue'])).toThrow(SanitizeError);
    expect(() => parseStatSpec({ value: 'revenue', agg: 'median' }, ['revenue'])).toThrow(SanitizeError);
    expect(() => parseStatSpec({ value: 'revenue', agg: 'sum', compare: { column: 'x', agg: 'sum' } }, ['revenue'])).toThrow(SanitizeError);
    expect(() => parseStatSpec('sum', ['revenue'])).toThrow(SanitizeError);
    expect(() => parseStatSpec({ value: 'revenue', agg: 'sum', format: 123 }, ['revenue'])).toThrow(SanitizeError);
  });
});

describe('StatTile', () => {
  it('renders the value and the comparison line', () => {
    render(
      <StatTile
        spec={{ value: 'revenue', agg: 'sum', format: ',.0f', compare: { column: 'orders', agg: 'sum' } }}
        rows={rows}
        columns={['revenue', 'orders']}
      />,
    );
    expect(screen.getByTestId('stat-value')).toHaveTextContent('60');
    expect(screen.getByTestId('stat-compare')).toHaveTextContent('orders (sum): 6');
  });
});

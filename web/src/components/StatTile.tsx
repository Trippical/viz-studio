import { format as d3format } from 'd3-format';
import type { Row } from '../api/types';
import { AGGS, SanitizeError, isPlainObject, type Agg } from '../renderers/common';

export interface StatSpec {
  value: string;
  agg: Agg;
  format?: string;
  compare?: { column: string; agg: Agg };
}

function isAgg(v: unknown): v is Agg {
  return typeof v === 'string' && (AGGS as readonly string[]).includes(v);
}

export function parseStatSpec(spec: unknown, columns: string[]): StatSpec {
  if (!isPlainObject(spec)) throw new SanitizeError('stat spec must be an object');
  const { value, agg, format, compare } = spec;
  if (typeof value !== 'string' || !columns.includes(value)) throw new SanitizeError(`stat value column unknown: ${String(value)}`);
  if (!isAgg(agg)) throw new SanitizeError(`stat agg unknown: ${String(agg)}`);
  const out: StatSpec = { value, agg };
  if (format !== undefined) {
    if (typeof format !== 'string' || format.length > 32) throw new SanitizeError('stat format must be a short string');
    out.format = format;
  }
  if (compare !== undefined) {
    if (!isPlainObject(compare)) throw new SanitizeError('stat compare must be an object');
    if (typeof compare.column !== 'string' || !columns.includes(compare.column)) {
      throw new SanitizeError(`stat compare column unknown: ${String(compare.column)}`);
    }
    if (!isAgg(compare.agg)) throw new SanitizeError(`stat compare agg unknown: ${String(compare.agg)}`);
    out.compare = { column: compare.column, agg: compare.agg };
  }
  return out;
}

export function aggregate(rows: Row[], column: string, agg: Agg): number | null {
  const values = rows.map((r) => r[column]).filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
  if (agg === 'count') return rows.length === 0 ? null : values.length;
  if (values.length === 0) return null;
  switch (agg) {
    case 'sum':
      return values.reduce((a, b) => a + b, 0);
    case 'avg':
      return values.reduce((a, b) => a + b, 0) / values.length;
    case 'min':
      return Math.min(...values);
    case 'max':
      return Math.max(...values);
    case 'last':
      return values[values.length - 1];
  }
}

export function formatValue(value: number | null, format?: string): string {
  if (value === null) return '–';
  try {
    return d3format(format ?? ',')(value);
  } catch {
    return String(value);
  }
}

export function StatTile({ spec, rows, columns }: { spec: unknown; rows: Row[]; columns: string[] }) {
  const parsed = parseStatSpec(spec, columns);
  const main = aggregate(rows, parsed.value, parsed.agg);
  return (
    <div className="stat">
      <div className="stat-value" data-testid="stat-value">
        {formatValue(main, parsed.format)}
      </div>
      {parsed.compare && (
        <div className="stat-compare" data-testid="stat-compare">
          {parsed.compare.column} ({parsed.compare.agg}): {formatValue(aggregate(rows, parsed.compare.column, parsed.compare.agg), parsed.format)}
        </div>
      )}
    </div>
  );
}

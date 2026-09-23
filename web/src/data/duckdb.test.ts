import { describe, expect, it } from 'vitest';
import type { Column } from '../api/types';
import type { Filter } from './filters';
import {
  DuckDbError,
  INIT_STATEMENTS,
  ROW_LIMIT,
  arrowRowsToRows,
  buildFilteredQuery,
  checkSingleSelectSyntax,
  parseSerializedSql,
  tableName,
} from './duckdb';

const columns: Column[] = [
  { name: 'day', type: 'date' },
  { name: 'region', type: 'string' },
  { name: 'amount', type: 'number' },
];

describe('init statements', () => {
  it('are the spec 12.3 sequence, locked last', () => {
    expect(INIT_STATEMENTS).toEqual([
      'SET autoinstall_known_extensions=false',
      'SET autoload_known_extensions=false',
      "SET memory_limit='512MB'",
      'SET lock_configuration=true',
    ]);
  });
});

describe('tableName', () => {
  it('derives a safe identifier from the id', () => {
    expect(tableName('bakeoff/vega-lite/order-lines')).toBe('raw_bakeoff_vega_lite_order_lines');
  });
});

describe('checkSingleSelectSyntax', () => {
  it('accepts SELECT and WITH, strips comments', () => {
    expect(checkSingleSelectSyntax('  SELECT 1')).toBe('SELECT 1');
    expect(checkSingleSelectSyntax('-- note\nWITH x AS (SELECT 1) SELECT * FROM x')).toMatch(/^WITH/);
    expect(checkSingleSelectSyntax('/* c */ select day from data')).toBe('select day from data');
  });
  it('rejects multiple statements and non-selects', () => {
    expect(() => checkSingleSelectSyntax('SELECT 1; DROP TABLE x')).toThrow(DuckDbError);
    expect(() => checkSingleSelectSyntax('INSTALL httpfs')).toThrow(DuckDbError);
    expect(() => checkSingleSelectSyntax('COPY data TO \'x\'')).toThrow(DuckDbError);
    expect(() => checkSingleSelectSyntax('')).toThrow(DuckDbError);
  });
});

describe('parseSerializedSql', () => {
  it('accepts one SELECT node and rejects everything else', () => {
    expect(() => parseSerializedSql('{"error":false,"statements":[{"node":{"type":"SELECT_NODE"}}]}')).not.toThrow();
    expect(() => parseSerializedSql('{"error":true,"error_type":"parser","error_message":"syntax error"}')).toThrow(/syntax error/);
    expect(() => parseSerializedSql('{"error":false,"statements":[{"node":{"type":"SELECT_NODE"}},{"node":{"type":"SELECT_NODE"}}]}')).toThrow(/single/);
    expect(() => parseSerializedSql('{"error":false,"statements":[{"node":{"type":"COPY_STATEMENT"}}]}')).toThrow(/SELECT/);
    expect(() => parseSerializedSql('not json')).toThrow(DuckDbError);
  });
});

describe('buildFilteredQuery', () => {
  const aggregate = 'SELECT day, sum(amount) AS amount FROM data GROUP BY day ORDER BY day';

  it('wraps the aggregate in a data CTE with a row limit and no filters', () => {
    const q = buildFilteredQuery(aggregate, 'raw_x', columns, []);
    expect(q.sql).toBe(`WITH data AS (SELECT * FROM "raw_x") SELECT * FROM (${aggregate}) LIMIT ${ROW_LIMIT}`);
    expect(q.params).toEqual([]);
    expect(q.tempTables).toEqual([]);
  });

  it('binds ranges as parameters and selects as temp tables, in filter order', () => {
    const filters: Filter[] = [
      { controlId: 'days', column: 'day', value: { type: 'date-range', from: '2025-01-01', to: '2025-06-30' } },
      { controlId: 'region', column: 'region', value: { type: 'select', values: ['EMEA', "x'; DROP TABLE t; --"] } },
      { controlId: 'amt', column: 'amount', value: { type: 'number-range', min: 10, max: null } },
      { controlId: 'prod', column: 'region', value: { type: 'text', text: 'em' } },
    ];
    const q = buildFilteredQuery(aggregate, 'raw_x', columns, filters);
    expect(q.sql).toContain('WHERE CAST("day" AS DATE) >= CAST(? AS DATE) AND CAST("day" AS DATE) <= CAST(? AS DATE)');
    expect(q.sql).toMatch(/CAST\("region" AS VARCHAR\) IN \(SELECT v FROM "f_region_\d+"\)/);
    expect(q.sql).toContain('"amount" >= ?');
    expect(q.sql).toContain('contains(lower(CAST("region" AS VARCHAR)), lower(?))');
    expect(q.params).toEqual(['2025-01-01', '2025-06-30', 10, 'em']);
    expect(q.tempTables).toHaveLength(1);
    expect(q.tempTables[0].values).toEqual(['EMEA', "x'; DROP TABLE t; --"]);
    expect(q.sql).not.toContain('DROP');
  });

  it('skips inactive filters, undeclared columns and unsafe column names', () => {
    const filters: Filter[] = [
      { controlId: 'a', column: 'region', value: { type: 'select', values: [] } },
      { controlId: 'b', column: 'nope', value: { type: 'number-range', min: 1, max: 2 } },
      { controlId: 'c', column: 'bad"col', value: { type: 'number-range', min: 1, max: 2 } },
    ];
    const q = buildFilteredQuery(aggregate, 'raw_x', [...columns, { name: 'bad"col', type: 'number' }], filters);
    expect(q.sql).not.toContain('WHERE');
    expect(q.params).toEqual([]);
  });

  it('rejects a hostile aggregate before building', () => {
    expect(() => buildFilteredQuery('SELECT 1; SELECT 2', 'raw_x', columns, [])).toThrow(DuckDbError);
  });
});

describe('arrowRowsToRows', () => {
  it('normalizes bigint, Date and epoch numbers by declared column type', () => {
    const out = arrowRowsToRows(
      [
        { day: new Date(Date.UTC(2025, 0, 2)), region: 'EMEA', amount: 10n, total: 5 },
        { day: Date.UTC(2025, 0, 3), region: 'NA', amount: 2.5, total: 7n },
      ],
      columns,
    );
    expect(out).toEqual([
      { day: '2025-01-02', region: 'EMEA', amount: 10, total: 5 },
      { day: '2025-01-03', region: 'NA', amount: 2.5, total: 7 },
    ]);
  });
});

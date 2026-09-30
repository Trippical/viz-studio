import { describe, expect, it, vi } from 'vitest';
import type { Column } from '../api/types';
import type { Filter } from './filters';
import {
  DuckDbError,
  DATA_DIR,
  INIT_STATEMENTS,
  ROW_LIMIT,
  arrowRowsToRows,
  buildFilteredQuery,
  buildPreloadStatements,
  checkSingleSelectSyntax,
  parseSerializedSql,
  registeredFileName,
  tableName,
  withTempTables,
} from './duckdb';

const columns: Column[] = [
  { name: 'day', type: 'date' },
  { name: 'region', type: 'string' },
  { name: 'amount', type: 'number' },
];

describe('init statements', () => {
  it('are the spec 12.3 sequence plus the A4 external-access lockdown, locked last', () => {
    expect(INIT_STATEMENTS).toEqual([
      'SET autoinstall_known_extensions=false',
      'SET autoload_known_extensions=false',
      "SET memory_limit='512MB'",
      "SET allowed_directories=['/viz-data/']",
      'SET enable_external_access=false',
      'SET lock_configuration=true',
    ]);
  });
});

describe('registeredFileName', () => {
  it('puts every data file inside the one directory the lockdown allows', () => {
    expect(DATA_DIR).toBe('/viz-data/');
    expect(registeredFileName('bakeoff/vega-lite/order-lines')).toBe('/viz-data/raw_bakeoff_vega_lite_order_lines.parquet');
  });
});

describe('buildPreloadStatements', () => {
  it('points the extension repository at the given origin, same-origin only, before loading parquet', () => {
    expect(buildPreloadStatements('http://127.0.0.1:8000')).toEqual([
      "SET custom_extension_repository='http://127.0.0.1:8000/duckdb'",
      'LOAD parquet',
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
    expect(q.clean).toBe(aggregate);
  });

  it('exposes the comment-stripped aggregate as clean, the exact text embedded in the subquery', () => {
    const q = buildFilteredQuery('-- c\nSELECT 1', 'raw_x', columns, []);
    expect(q.clean).toBe('SELECT 1');
    expect(q.sql).toContain('SELECT * FROM (SELECT 1) LIMIT');
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

describe('withTempTables', () => {
  function fakeConn(opts: { failCreateFor?: string } = {}) {
    const queries: string[] = [];
    const created: string[] = [];
    const dropped: string[] = [];
    const inserts: { sql: string; params: unknown[] }[] = [];
    const closed: string[] = [];
    const conn = {
      query: vi.fn(async (sql: string) => {
        queries.push(sql);
        const createM = /^CREATE TEMP TABLE "([^"]+)" \(v VARCHAR\)$/.exec(sql);
        if (createM) {
          if (opts.failCreateFor === createM[1]) throw new Error(`create failed: ${createM[1]}`);
          created.push(createM[1]);
        }
        const dropM = /DROP TABLE IF EXISTS "([^"]+)"/.exec(sql);
        if (dropM) dropped.push(dropM[1]);
        return undefined;
      }),
      prepare: vi.fn(async (sql: string) => ({
        query: vi.fn(async (...params: unknown[]) => {
          inserts.push({ sql, params });
          return undefined;
        }),
        close: vi.fn(async () => {
          closed.push(sql);
        }),
      })),
    };
    return { conn, queries, created, dropped, inserts, closed };
  }

  it('creates each temp table and inserts its values through a prepared statement, never in the SQL text, then closes it and drops the tables on success', async () => {
    const { conn, queries, created, dropped, inserts, closed } = fakeConn();
    const tables = [{ name: 'a', values: ['x', "y'; DROP TABLE t; --"] }];
    const result = await withTempTables(conn, tables, async () => 'ok');
    expect(result).toBe('ok');
    expect(created).toEqual(['a']);
    expect(dropped).toEqual(['a']);
    expect(inserts).toEqual([{ sql: 'INSERT INTO "a" VALUES (?), (?)', params: ['x', "y'; DROP TABLE t; --"] }]);
    expect(closed).toEqual(['INSERT INTO "a" VALUES (?), (?)']);
    for (const sql of queries) {
      expect(sql).not.toContain('x');
      expect(sql).not.toContain("y'; DROP TABLE t; --");
    }
  });

  it('batches values into groups of up to 100 placeholders per INSERT', async () => {
    const { conn, inserts } = fakeConn();
    const values = Array.from({ length: 150 }, (_, i) => `v${i}`);
    await withTempTables(conn, [{ name: 'a', values }], async () => 'ok');
    expect(inserts).toHaveLength(2);
    expect(inserts[0].params).toHaveLength(100);
    expect(inserts[1].params).toHaveLength(50);
    expect(inserts[0].sql).toBe(`INSERT INTO "a" VALUES ${Array(100).fill('(?)').join(', ')}`);
  });

  it('drops every temp table even when the second CREATE fails, and lets the error propagate', async () => {
    const { conn, created, dropped } = fakeConn({ failCreateFor: 'b' });
    const tables = [
      { name: 'a', values: ['x'] },
      { name: 'b', values: ['y'] },
    ];
    const body = vi.fn(async () => 'unreachable');
    await expect(withTempTables(conn, tables, body)).rejects.toThrow('create failed: b');
    expect(created).toEqual(['a']);
    expect(dropped).toEqual(['a', 'b']);
    expect(body).not.toHaveBeenCalled();
  });

  it('skips the drop loop and skips closing the insert statement when canDrop returns false, even on the success path', async () => {
    const { conn, created, dropped, closed } = fakeConn();
    const tables = [{ name: 'a', values: ['x'] }];
    const result = await withTempTables(conn, tables, async () => 'ok', () => false);
    expect(result).toBe('ok');
    expect(created).toEqual(['a']);
    expect(dropped).toEqual([]);
    expect(closed).toEqual([]);
  });
});

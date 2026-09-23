// DuckDB-WASM large lane. Spec 12.3: locked configuration before any chart
// SQL runs, no extension fetches, no external access, control values only as
// parameters and temp tables, a 50k row cap and a wall-clock budget.
import { dataUrl } from '../api/client';
import type { Column, Row } from '../api/types';
import { isActive, type Filter } from './filters';

export const ROW_LIMIT = 50000;
export const DEFAULT_TIMEOUT_MS = 15000;
export const LARGE_LANE_MAX_BYTES = 209715200;

export const INIT_STATEMENTS: readonly string[] = [
  'SET autoinstall_known_extensions=false',
  'SET autoload_known_extensions=false',
  "SET memory_limit='512MB'",
  'SET lock_configuration=true',
];

const COLUMN_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

export class DuckDbError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'DuckDbError';
  }
}

export function tableName(chartId: string): string {
  return `raw_${chartId.replace(/[^a-z0-9]/g, '_')}`;
}

export function checkSingleSelectSyntax(aggregate: string): string {
  const stripped = aggregate
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/--[^\n]*/g, ' ')
    .trim();
  if (stripped === '') throw new DuckDbError('aggregate is empty');
  if (stripped.includes(';')) throw new DuckDbError('aggregate must be a single statement');
  if (!/^(select|with)\b/i.test(stripped)) throw new DuckDbError('aggregate must be a SELECT');
  return stripped;
}

export function parseSerializedSql(json: string): void {
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    throw new DuckDbError('could not parse the serialized aggregate');
  }
  const doc = parsed as { error?: boolean; error_message?: string; statements?: { node?: { type?: string } }[] };
  if (doc.error) throw new DuckDbError(`aggregate does not parse: ${doc.error_message ?? 'unknown error'}`);
  if (!Array.isArray(doc.statements) || doc.statements.length !== 1) throw new DuckDbError('aggregate must be a single statement');
  if (doc.statements[0]?.node?.type !== 'SELECT_NODE') throw new DuckDbError('aggregate must be a SELECT');
}

export interface BuiltQuery {
  sql: string;
  params: unknown[];
  tempTables: { name: string; values: string[] }[];
}

let tempCounter = 0;

export function buildFilteredQuery(aggregate: string, table: string, columns: Column[], filters: Filter[]): BuiltQuery {
  const clean = checkSingleSelectSyntax(aggregate);
  const types = new Map(columns.map((c) => [c.name, c.type]));
  const conds: string[] = [];
  const params: unknown[] = [];
  const tempTables: BuiltQuery['tempTables'] = [];
  for (const f of filters) {
    const type = types.get(f.column);
    if (!type || !COLUMN_NAME.test(f.column) || !isActive(f.value)) continue;
    const col = `"${f.column}"`;
    const value = f.value;
    switch (value.type) {
      case 'date-range': {
        const expr = type === 'date' || type === 'timestamp' ? `CAST(${col} AS DATE)` : col;
        if (value.from !== null) {
          conds.push(`${expr} >= CAST(? AS DATE)`);
          params.push(value.from);
        }
        if (value.to !== null) {
          conds.push(`${expr} <= CAST(? AS DATE)`);
          params.push(value.to);
        }
        break;
      }
      case 'number-range': {
        if (value.min !== null) {
          conds.push(`${col} >= ?`);
          params.push(value.min);
        }
        if (value.max !== null) {
          conds.push(`${col} <= ?`);
          params.push(value.max);
        }
        break;
      }
      case 'select': {
        tempCounter += 1;
        const name = `f_${f.controlId.replace(/[^a-z0-9]/g, '_')}_${tempCounter}`;
        tempTables.push({ name, values: value.values });
        conds.push(`CAST(${col} AS VARCHAR) IN (SELECT v FROM "${name}")`);
        break;
      }
      case 'text': {
        conds.push(`contains(lower(CAST(${col} AS VARCHAR)), lower(?))`);
        params.push(value.text);
        break;
      }
    }
  }
  const where = conds.length > 0 ? ` WHERE ${conds.join(' AND ')}` : '';
  const sql = `WITH data AS (SELECT * FROM "${table}"${where}) SELECT * FROM (${clean}) LIMIT ${ROW_LIMIT}`;
  return { sql, params, tempTables };
}

function normalize(v: unknown, type: Column['type'] | undefined): unknown {
  if (typeof v === 'bigint') return Number(v);
  if (v instanceof Date) return type === 'date' ? v.toISOString().slice(0, 10) : v.toISOString();
  if (typeof v === 'number' && type === 'date') return new Date(v).toISOString().slice(0, 10);
  if (typeof v === 'number' && type === 'timestamp') return new Date(v).toISOString();
  return v;
}

export function arrowRowsToRows(rows: Record<string, unknown>[], columns: Column[]): Row[] {
  const types = new Map(columns.map((c) => [c.name, c.type]));
  return rows.map((r) => {
    const out: Row = {};
    for (const key of Object.keys(r)) out[key] = normalize(r[key], types.get(key));
    return out;
  });
}

// ---- runtime -------------------------------------------------------------

type DuckDbModule = typeof import('@duckdb/duckdb-wasm');
type AsyncDuckDB = InstanceType<DuckDbModule['AsyncDuckDB']>;
type Connection = Awaited<ReturnType<AsyncDuckDB['connect']>>;

interface Runtime {
  db: AsyncDuckDB;
  conn: Connection;
  loaded: Set<string>;
  jsonCheck: boolean;
}

let runtime: Promise<Runtime> | null = null;
let chain: Promise<unknown> = Promise.resolve();

async function createRuntime(): Promise<Runtime> {
  const duckdb = await import('@duckdb/duckdb-wasm');
  const [{ default: wasmUrl }, { default: workerUrl }] = await Promise.all([
    import('@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url'),
    import('@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url'),
  ]);
  const worker = new Worker(workerUrl);
  const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
  await db.instantiate(wasmUrl);
  await db.open({ path: ':memory:', query: { castBigIntToDouble: true, castDecimalToDouble: true, castTimestampToDate: true } });
  const conn = await db.connect();
  for (const statement of INIT_STATEMENTS) await conn.query(statement);
  let jsonCheck = true;
  try {
    await conn.query("SELECT json_serialize_sql('SELECT 1')");
  } catch {
    jsonCheck = false;
    console.warn('duckdb: json_serialize_sql is unavailable in this build; relying on the syntax check and subquery wrapping');
  }
  return { db, conn, loaded: new Set(), jsonCheck };
}

function getRuntime(): Promise<Runtime> {
  if (!runtime) {
    runtime = createRuntime().catch((err: unknown) => {
      runtime = null;
      throw new DuckDbError(`could not start DuckDB: ${err instanceof Error ? err.message : String(err)}`);
    });
  }
  return runtime;
}

async function terminateRuntime(): Promise<void> {
  const current = runtime;
  runtime = null;
  if (!current) return;
  try {
    const rt = await current;
    await rt.db.terminate();
  } catch {
    // already gone
  }
}

async function ensureLoaded(rt: Runtime, chartId: string): Promise<void> {
  if (rt.loaded.has(chartId)) return;
  const res = await fetch(dataUrl(chartId));
  if (!res.ok) throw new DuckDbError(`data file request failed (${res.status})`);
  const declared = Number(res.headers.get('content-length'));
  if (Number.isFinite(declared) && declared > LARGE_LANE_MAX_BYTES) throw new DuckDbError(`data file is ${declared} bytes, above the large-lane cap`);
  const buffer = new Uint8Array(await res.arrayBuffer());
  if (buffer.byteLength > LARGE_LANE_MAX_BYTES) throw new DuckDbError(`data file is ${buffer.byteLength} bytes, above the large-lane cap`);
  const file = `${tableName(chartId)}.parquet`;
  await rt.db.registerFileBuffer(file, buffer);
  try {
    await rt.conn.query(`CREATE TABLE "${tableName(chartId)}" AS SELECT * FROM read_parquet('${file}')`);
  } finally {
    await rt.db.dropFile(file).catch(() => undefined);
  }
  rt.loaded.add(chartId);
}

async function assertSingleSelect(conn: Connection, aggregate: string): Promise<void> {
  const stmt = await conn.prepare('SELECT json_serialize_sql(?) AS j');
  try {
    const table = await stmt.query(aggregate);
    const first = table.toArray()[0] as { toJSON(): { j: unknown } } | undefined;
    parseSerializedSql(String(first?.toJSON().j ?? ''));
  } finally {
    await stmt.close().catch(() => undefined);
  }
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new DuckDbError(`query timed out after ${ms} ms`)), ms);
    promise.then(
      (v) => {
        clearTimeout(timer);
        resolve(v);
      },
      (e: unknown) => {
        clearTimeout(timer);
        reject(e);
      },
    );
  });
}

async function runQuery(chartId: string, aggregate: string, columns: Column[], filters: Filter[], timeoutMs: number): Promise<Row[]> {
  const built = buildFilteredQuery(aggregate, tableName(chartId), columns, filters);
  const rt = await getRuntime();
  await ensureLoaded(rt, chartId);
  if (rt.jsonCheck) await assertSingleSelect(rt.conn, aggregate);
  const arrow = await import('apache-arrow');
  for (const t of built.tempTables) {
    await rt.conn.insertArrowTable(arrow.tableFromArrays({ v: t.values }), { name: t.name, create: true });
  }
  try {
    const stmt = await rt.conn.prepare(built.sql);
    try {
      const table = await withTimeout(stmt.query(...built.params), timeoutMs);
      const rows = table.toArray().map((r) => (r as { toJSON(): Record<string, unknown> }).toJSON());
      return arrowRowsToRows(rows, columns);
    } finally {
      await stmt.close().catch(() => undefined);
    }
  } catch (err) {
    if (err instanceof DuckDbError && /timed out/.test(err.message)) {
      await terminateRuntime();
      throw err;
    }
    throw err instanceof DuckDbError ? err : new DuckDbError(err instanceof Error ? err.message : String(err));
  } finally {
    if (runtime) {
      for (const t of built.tempTables) await rt.conn.query(`DROP TABLE IF EXISTS "${t.name}"`).catch(() => undefined);
    }
  }
}

/** Run a chart's aggregate over its parquet file with the given filters. Serialized page-wide. */
export function queryLargeLane(chartId: string, aggregate: string, columns: Column[], filters: Filter[], timeoutMs = DEFAULT_TIMEOUT_MS): Promise<Row[]> {
  const next = chain.then(() => runQuery(chartId, aggregate, columns, filters, timeoutMs));
  chain = next.catch(() => undefined);
  return next;
}

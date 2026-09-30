// @vitest-environment node
//
// Runs the real duckdb-wasm build (the Node flavour of the same DuckDB
// v1.4.3 core the browser uses) to pin finding A4: after INIT_STATEMENTS,
// DuckDB can read a buffer registered under DATA_DIR and nothing else, and
// the lockdown cannot be undone. CSV is used because read_csv is built in;
// the permission check is the same for every file reader, parquet included.
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { INIT_STATEMENTS, buildDistinctAggregate, buildFilteredQuery, registeredFileName } from './duckdb';

const WEB = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const DIST = join(WEB, 'node_modules', '@duckdb', 'duckdb-wasm', 'dist');
const requireCjs = createRequire(import.meta.url);

interface NodeTable {
  toArray(): { toJSON(): Record<string, unknown> }[];
}
interface NodeConnection {
  query(sql: string): NodeTable;
  close(): void;
}
interface NodeDb {
  instantiate(progress: () => void): Promise<unknown>;
  open(config: { path: string }): void;
  connect(): NodeConnection;
  registerFileBuffer(name: string, buffer: Uint8Array): void;
}
interface NodeDuckDb {
  createDuckDB(bundles: unknown, logger: unknown, runtime: unknown): Promise<NodeDb>;
  VoidLogger: new () => unknown;
  NODE_RUNTIME: unknown;
}

const CSV = new TextEncoder().encode('a,b\n1,x\n2,y\n');

async function lockedDb(): Promise<{ db: NodeDb; conn: NodeConnection }> {
  const duckdb = requireCjs(join(DIST, 'duckdb-node-blocking.cjs')) as NodeDuckDb;
  const db = await duckdb.createDuckDB(
    {
      mvp: { mainModule: join(DIST, 'duckdb-mvp.wasm'), mainWorker: join(DIST, 'duckdb-node-mvp.worker.cjs') },
      eh: { mainModule: join(DIST, 'duckdb-eh.wasm'), mainWorker: join(DIST, 'duckdb-node-eh.worker.cjs') },
    },
    new duckdb.VoidLogger(),
    duckdb.NODE_RUNTIME,
  );
  await db.instantiate(() => undefined);
  db.open({ path: ':memory:' });
  const conn = db.connect();
  for (const statement of INIT_STATEMENTS) conn.query(statement);
  return { db, conn };
}

function csvName(chartId: string): string {
  return registeredFileName(chartId).replace(/\.parquet$/, '.csv');
}

describe('DuckDB lockdown (A4), real duckdb-wasm', () => {
  it('reads a buffer registered under the data directory after the lockdown', async () => {
    const { db, conn } = await lockedDb();
    const name = csvName('sales/x');
    db.registerFileBuffer(name, CSV);
    conn.query(`CREATE TABLE t AS SELECT * FROM read_csv('${name}')`);
    const count = conn.query('SELECT count(*)::INTEGER AS n FROM t').toArray()[0].toJSON().n;
    expect(count).toBe(2);
    conn.close();
  }, 60_000);

  it('refuses every other path and cannot be unlocked', async () => {
    const { db, conn } = await lockedDb();
    db.registerFileBuffer('other.csv', CSV);
    db.registerFileBuffer('/elsewhere/x.csv', CSV);
    for (const path of ['other.csv', '/elsewhere/x.csv', '/viz-data/../other.csv', 'https://example.com/x.csv']) {
      expect(() => conn.query(`SELECT * FROM read_csv('${path}')`), path).toThrow(/Permission Error/);
    }
    expect(() => conn.query('SET enable_external_access=true')).toThrow(/locked/);
    expect(() => conn.query("SET allowed_directories=['/']")).toThrow();
    conn.close();
  }, 60_000);

  it('runs the distinct-values aggregate over a locked database (A7)', async () => {
    const { db, conn } = await lockedDb();
    const name = csvName('sales/y');
    db.registerFileBuffer(name, new TextEncoder().encode('region,amount\nEMEA,1\nNA,2\nEMEA,3\n,4\n'));
    conn.query(`CREATE TABLE "raw_sales_y" AS SELECT * FROM read_csv('${name}')`);
    const cols = [
      { name: 'region', type: 'string' as const },
      { name: 'amount', type: 'number' as const },
    ];
    const q = buildFilteredQuery(buildDistinctAggregate('region', cols), 'raw_sales_y', cols, []);
    const values = conn
      .query(q.sql)
      .toArray()
      .map((r) => String(r.toJSON().v))
      .sort();
    expect(values).toEqual(['EMEA', 'NA']);
    conn.close();
  }, 60_000);
});

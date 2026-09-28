// Prints the size of each renderer's lazy chunk and of the DuckDB assets in web/dist.
import { readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const assets = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist', 'assets');
const files = readdirSync(assets)
  .map((name) => ({ name, bytes: statSync(join(assets, name)).size }))
  .sort((a, b) => b.bytes - a.bytes);

const groups = {
  'vega-lite': /^renderer-vega-/,
  duckdb: /^duckdb-.*\.js$|worker.*\.js$|\.wasm$/,
  main: /^index-/,
};

const kib = (n) => `${Math.round(n / 1024).toLocaleString('en-US')} KiB`;
console.log('group\tsize');
for (const [label, re] of Object.entries(groups)) {
  const total = files.filter((f) => re.test(f.name)).reduce((s, f) => s + f.bytes, 0);
  console.log(`${label}\t${kib(total)}`);
}
console.log('\nfile\tsize');
for (const f of files) console.log(`${f.name}\t${kib(f.bytes)}`);

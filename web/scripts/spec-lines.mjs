// Prints, per renderer, the pretty-printed line count of the bake-off specs and
// the number of sanitizer rules, for the scorecard.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const web = join(dirname(fileURLToPath(import.meta.url)), '..');
const bucket = join(web, '..', 'sample-bucket', 'viz', 'charts', 'bakeoff');
const renderers = { 'vega-lite': 'vegaLiteSanitize.ts' };

function specLines(renderer, chart) {
  const doc = JSON.parse(readFileSync(join(bucket, renderer, chart, 'chart.json'), 'utf8'));
  return JSON.stringify(doc.spec, null, 2).split('\n').length;
}

function ruleCount(file) {
  const src = readFileSync(join(web, 'src', 'renderers', file), 'utf8');
  const block = src.slice(src.indexOf('RULES: readonly string[] = ['), src.indexOf('];'));
  return block.split('\n').filter((line) => /^\s*'/.test(line)).length;
}

console.log('renderer\ttime-series lines\tgrouped-bar lines\torder-lines lines\tsanitizer rules');
for (const [renderer, file] of Object.entries(renderers)) {
  console.log(`${renderer}\t${specLines(renderer, 'time-series')}\t${specLines(renderer, 'grouped-bar')}\t${specLines(renderer, 'order-lines')}\t${ruleCount(file)}`);
}

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

// This file's own absolute path, so the walk can skip it: it must contain
// the literal strings this guard scans for in order to scan for them, and
// scanning every other file (test files included) is the whole point of
// this fix.
const SELF = fileURLToPath(import.meta.url);

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path, out);
    else if (/\.(ts|tsx)$/.test(name) && path !== SELF) out.push(path);
  }
  return out;
}

describe('no raw HTML injection anywhere in the app', () => {
  it('dangerouslySetInnerHTML is not used', () => {
    const src = join(dirname(SELF), '..');
    const offenders = walk(src).filter((path) => readFileSync(path, 'utf8').includes('dangerouslySetInnerHTML'));
    expect(offenders).toEqual([]);
  });

  it('innerHTML assignment is not used', () => {
    const src = join(dirname(SELF), '..');
    const offenders = walk(src).filter((path) => /\.innerHTML\s*=/.test(readFileSync(path, 'utf8')));
    expect(offenders).toEqual([]);
  });
});

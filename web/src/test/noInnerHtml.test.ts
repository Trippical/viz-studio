import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path, out);
    else if (/\.(ts|tsx)$/.test(name) && !name.endsWith('.test.ts') && !name.endsWith('.test.tsx')) out.push(path);
  }
  return out;
}

describe('no raw HTML injection anywhere in the app', () => {
  it('dangerouslySetInnerHTML is not used', () => {
    const src = join(__dirname, '..');
    const offenders = walk(src).filter((path) => readFileSync(path, 'utf8').includes('dangerouslySetInnerHTML'));
    expect(offenders).toEqual([]);
  });

  it('innerHTML assignment is not used', () => {
    const src = join(__dirname, '..');
    const offenders = walk(src).filter((path) => /\.innerHTML\s*=/.test(readFileSync(path, 'utf8')));
    expect(offenders).toEqual([]);
  });
});

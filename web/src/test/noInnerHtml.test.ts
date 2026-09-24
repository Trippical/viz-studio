import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

// This file's own absolute path, so the walk can skip it: it must contain
// the literal strings this guard scans for in order to scan for them, and
// scanning every other file (test files included) is the whole point of
// this fix.
const SELF = fileURLToPath(import.meta.url);

// Roots to scan: the app source, the Playwright e2e specs, and the build
// scripts. All three can grow raw-HTML injection just as easily as the
// renderer code can.
const ROOTS = ['src', 'e2e', 'scripts'];

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path, out);
    else if (/\.(ts|tsx|mjs|js)$/.test(name) && path !== SELF) out.push(path);
  }
  return out;
}

function allFiles(): string[] {
  const web = join(dirname(SELF), '..', '..');
  return ROOTS.flatMap((root) => walk(join(web, root)));
}

// Whole-token patterns for every raw-HTML / dynamic-code sink the CSP and
// the sanitizers are built to keep this app away from. Word boundaries on
// `eval(` and `new Function(` keep this from flagging unrelated identifiers
// that merely contain those substrings (for example Playwright's
// `page.evaluate`, which is Playwright's own API for running a callback in
// the browser context, not JavaScript `eval` of untrusted bucket content).
const FORBIDDEN: { name: string; pattern: RegExp }[] = [
  { name: 'dangerouslySetInnerHTML', pattern: /\bdangerouslySetInnerHTML\b/ },
  { name: '.innerHTML', pattern: /\.innerHTML\b/ },
  { name: '.outerHTML', pattern: /\.outerHTML\b/ },
  { name: 'insertAdjacentHTML', pattern: /\binsertAdjacentHTML\b/ },
  { name: 'document.write', pattern: /\bdocument\.write\b/ },
  { name: 'srcdoc', pattern: /\bsrcdoc\b/ },
  { name: 'new Function(', pattern: /\bnew\s+Function\s*\(/ },
  { name: 'eval(', pattern: /\beval\s*\(/ },
];

describe('no raw HTML injection anywhere in the app', () => {
  for (const { name, pattern } of FORBIDDEN) {
    it(`${name} is not used`, () => {
      const offenders = allFiles().filter((path) => pattern.test(readFileSync(path, 'utf8')));
      expect(offenders).toEqual([]);
    });
  }

  it('the e2e smoke spec is scanned and its Playwright page.evaluate calls, if any, are not flagged', () => {
    const smoke = allFiles().find((path) => path.endsWith(join('e2e', 'smoke.spec.ts')));
    expect(smoke).toBeDefined();
    const text = readFileSync(smoke!, 'utf8');
    if (text.includes('page.evaluate')) {
      for (const { pattern } of FORBIDDEN) expect(pattern.test(text)).toBe(false);
    }
  });
});

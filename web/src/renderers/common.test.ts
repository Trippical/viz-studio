import { describe, expect, it } from 'vitest';
import { SanitizeError, assertPlain, deepClone, walk } from './common';

describe('assertPlain', () => {
  it('accepts JSON-shaped values', () => {
    expect(() => assertPlain({ a: [1, 'x', null, { b: true }] })).not.toThrow();
    expect(() => assertPlain(Object.create(null))).not.toThrow();
  });
  it('rejects functions, class instances, Dates and Maps at any depth', () => {
    expect(() => assertPlain({ a: () => 1 })).toThrow(SanitizeError);
    expect(() => assertPlain({ a: [new Date()] })).toThrow(SanitizeError);
    expect(() => assertPlain(new Map())).toThrow(SanitizeError);
    class X {}
    expect(() => assertPlain({ x: new X() })).toThrow(SanitizeError);
  });
});

describe('deepClone', () => {
  it('copies and drops prototype-polluting keys', () => {
    const src = JSON.parse('{"a":{"b":1},"__proto__":{"polluted":true},"constructor":1}');
    const out = deepClone(src) as Record<string, unknown>;
    expect(out).toEqual({ a: { b: 1 } });
    expect(out.a).not.toBe(src.a);
    expect(Object.keys(out)).toEqual(['a']);
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
  });
});

describe('walk', () => {
  it('visits every key with its path and allows deletion', () => {
    const spec = { a: 1, b: { c: [{ d: 2 }], e: 3 } };
    const seen: string[] = [];
    walk(spec, (obj, key, _value, path) => {
      seen.push(path);
      if (key === 'e') delete obj[key];
    });
    expect(seen).toEqual(['spec/a', 'spec/b', 'spec/b/c', 'spec/b/c/0/d', 'spec/b/e']);
    expect(spec.b).toEqual({ c: [{ d: 2 }] });
  });
});

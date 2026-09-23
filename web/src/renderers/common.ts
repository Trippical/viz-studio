// Helpers shared by every renderer sanitizer. Pure: no DOM, no library imports.

export class SanitizeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SanitizeError';
  }
}

export type Agg = 'sum' | 'avg' | 'min' | 'max' | 'count' | 'last';
export const AGGS: readonly Agg[] = ['sum', 'avg', 'min', 'max', 'count', 'last'];

export const UNSAFE_KEYS = ['__proto__', 'constructor', 'prototype'];
export const MAX_DEPTH = 64;

export function isPlainObject(v: unknown): v is Record<string, unknown> {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) return false;
  const proto = Object.getPrototypeOf(v);
  return proto === Object.prototype || proto === null;
}

export function assertPlain(value: unknown, path = 'spec'): void {
  function assertPlainInner(value: unknown, path: string, depth: number): void {
    if (depth > MAX_DEPTH) {
      throw new SanitizeError(`${path}: nesting deeper than ${MAX_DEPTH} levels`);
    }
    if (value === null) return;
    const t = typeof value;
    if (t === 'string' || t === 'number' || t === 'boolean' || t === 'undefined') return;
    if (Array.isArray(value)) {
      value.forEach((v, i) => assertPlainInner(v, `${path}/${i}`, depth + 1));
      return;
    }
    if (isPlainObject(value)) {
      for (const key of Object.keys(value)) {
        let v: unknown;
        try {
          v = value[key];
        } catch {
          throw new SanitizeError(`${path}/${key}: property could not be read`);
        }
        assertPlainInner(v, `${path}/${key}`, depth + 1);
      }
      return;
    }
    throw new SanitizeError(`${path}: only plain JSON values are allowed`);
  }
  assertPlainInner(value, path, 0);
}

export function deepClone<T>(value: T): T {
  function deepCloneInner(value: unknown, path: string, depth: number): unknown {
    if (depth > MAX_DEPTH) {
      throw new SanitizeError(`${path}: nesting deeper than ${MAX_DEPTH} levels`);
    }
    if (value === null || value === undefined) return value;
    const t = typeof value;
    if (t === 'string' || t === 'number' || t === 'boolean') return value;
    if (t === 'symbol' || t === 'bigint') throw new SanitizeError(`${path}: only plain JSON values are allowed`);
    if (t === 'function') throw new SanitizeError(`${path}: only plain JSON values are allowed`);
    if (Array.isArray(value)) {
      return value.map((v, i) => deepCloneInner(v, `${path}/${i}`, depth + 1));
    }
    if (isPlainObject(value)) {
      const out: Record<string, unknown> = {};
      for (const key of Object.keys(value)) {
        if (UNSAFE_KEYS.includes(key)) continue;
        let v: unknown;
        try {
          v = value[key];
        } catch {
          throw new SanitizeError(`${path}/${key}: property could not be read`);
        }
        out[key] = deepCloneInner(v, `${path}/${key}`, depth + 1);
      }
      return out;
    }
    throw new SanitizeError(`${path}: only plain JSON values are allowed`);
  }
  return deepCloneInner(value, 'spec', 0) as T;
}

export function walk(
  node: unknown,
  visit: (obj: Record<string, unknown>, key: string, value: unknown, path: string) => void,
  path = 'spec',
): void {
  function walkInner(node: unknown, visit: (obj: Record<string, unknown>, key: string, value: unknown, path: string) => void, path: string, depth: number): void {
    if (depth > MAX_DEPTH) {
      throw new SanitizeError(`${path}: nesting deeper than ${MAX_DEPTH} levels`);
    }
    if (Array.isArray(node)) {
      node.forEach((v, i) => walkInner(v, visit, `${path}/${i}`, depth + 1));
      return;
    }
    if (!isPlainObject(node)) return;
    for (const key of Object.keys(node)) {
      const here = `${path}/${key}`;
      let v: unknown;
      try {
        v = node[key];
      } catch {
        throw new SanitizeError(`${here}: property could not be read`);
      }
      visit(node, key, v, here);
      if (key in node) {
        let current: unknown;
        try {
          current = node[key];
        } catch {
          throw new SanitizeError(`${here}: property could not be read`);
        }
        walkInner(current, visit, here, depth + 1);
      }
    }
  }
  walkInner(node, visit, path, 0);
}

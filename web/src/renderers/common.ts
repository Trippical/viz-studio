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

export function isPlainObject(v: unknown): v is Record<string, unknown> {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) return false;
  const proto = Object.getPrototypeOf(v);
  return proto === Object.prototype || proto === null;
}

export function assertPlain(value: unknown, path = 'spec'): void {
  if (value === null) return;
  const t = typeof value;
  if (t === 'string' || t === 'number' || t === 'boolean' || t === 'undefined') return;
  if (Array.isArray(value)) {
    value.forEach((v, i) => assertPlain(v, `${path}/${i}`));
    return;
  }
  if (isPlainObject(value)) {
    for (const key of Object.keys(value)) assertPlain(value[key], `${path}/${key}`);
    return;
  }
  throw new SanitizeError(`${path}: only plain JSON values are allowed`);
}

export function deepClone<T>(value: T): T {
  if (Array.isArray(value)) return value.map((v) => deepClone(v)) as unknown as T;
  if (isPlainObject(value)) {
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(value)) {
      if (UNSAFE_KEYS.includes(key)) continue;
      out[key] = deepClone(value[key]);
    }
    return out as T;
  }
  return value;
}

export function walk(
  node: unknown,
  visit: (obj: Record<string, unknown>, key: string, value: unknown, path: string) => void,
  path = 'spec',
): void {
  if (Array.isArray(node)) {
    node.forEach((v, i) => walk(v, visit, `${path}/${i}`));
    return;
  }
  if (!isPlainObject(node)) return;
  for (const key of Object.keys(node)) {
    const here = `${path}/${key}`;
    visit(node, key, node[key], here);
    if (key in node) walk(node[key], visit, here);
  }
}

import type { Column, Row } from '../api/types';
import { SanitizeError, UNSAFE_KEYS, isPlainObject } from './common';
import { BOUND_KEYS } from './plotlySanitize';

const ESCAPED_KEYS = new Set(['text', 'hovertext', 'customdata']);

export function escapeLt(v: unknown): unknown {
  return typeof v === 'string' ? v.replace(/</g, '&lt;') : v;
}

function columnArray(rows: Row[], column: string, escape: boolean): unknown[] {
  return rows.map((row) => (escape ? escapeLt(row[column]) : row[column]));
}

function bindOne(trace: Record<string, unknown>, rows: Row[], declared: Set<string>, index: number): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const key of Object.keys(trace)) {
    if (UNSAFE_KEYS.includes(key) || key === 'split') continue;
    const value = trace[key];
    if ((BOUND_KEYS as readonly string[]).includes(key)) {
      if (!isPlainObject(value) || typeof value.column !== 'string') {
        throw new SanitizeError(`spec/traces/${index}/${key}: must be a column binding`);
      }
      if (!declared.has(value.column)) throw new SanitizeError(`spec/traces/${index}/${key}: unknown column "${value.column}"`);
      out[key] = columnArray(rows, value.column, ESCAPED_KEYS.has(key));
    } else {
      out[key] = value;
    }
  }
  return out;
}

/** Replace {column} bindings with arrays from rows and expand `split` traces. */
export function bindTraces(traces: Record<string, unknown>[], rows: Row[], columns: Column[]): Record<string, unknown>[] {
  const declared = new Set(columns.map((c) => c.name));
  const out: Record<string, unknown>[] = [];
  traces.forEach((trace, i) => {
    const split = trace.split;
    if (split === undefined) {
      out.push(bindOne(trace, rows, declared, i));
      return;
    }
    if (typeof split !== 'string' || !declared.has(split)) throw new SanitizeError(`spec/traces/${i}/split: must name a declared column`);
    const groups = new Map<string, Row[]>();
    for (const row of rows) {
      const v = row[split];
      if (v === null || v === undefined) continue;
      const key = String(v);
      const group = groups.get(key);
      if (group) group.push(row);
      else groups.set(key, [row]);
    }
    for (const [name, group] of groups) {
      const bound = bindOne(trace, group, declared, i);
      out.push({ ...bound, name });
    }
  });
  return out;
}

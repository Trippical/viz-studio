import type { Column, Row } from '../api/types';
import { SanitizeError, UNSAFE_KEYS, isPlainObject } from './common';
import { BOUND_KEYS } from './plotlySanitize';

export function escapeLt(v: unknown): unknown {
  return typeof v === 'string' ? v.replace(/</g, '&lt;') : v;
}

// Plotly's pseudo-HTML parser renders `<` in more than just text/hovertext:
// labels, legend entries and category axis values (bound x/y) go through it
// too, so every bound column is escaped unconditionally. Non-strings (numbers,
// dates, null) pass through escapeLt unchanged.
function columnArray(rows: Row[], column: string): unknown[] {
  return rows.map((row) => escapeLt(row[column]));
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
      out[key] = columnArray(rows, value.column);
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

import type { Column, Control, Row } from '../api/types';

export type FilterValue =
  | { type: 'date-range'; from: string | null; to: string | null }
  | { type: 'select'; values: readonly string[] }
  | { type: 'number-range'; min: number | null; max: number | null }
  | { type: 'text'; text: string };

export interface Filter {
  controlId: string;
  column: string;
  value: FilterValue;
}

export const MAX_SELECT_OPTIONS = 500;

export interface SelectOptions {
  options: string[];
  tooMany: boolean;
}

export function isActive(value: FilterValue): boolean {
  switch (value.type) {
    case 'date-range':
      return value.from !== null || value.to !== null;
    case 'select':
      return value.values.length > 0;
    case 'number-range':
      return value.min !== null || value.max !== null;
    case 'text':
      return value.text !== '';
  }
}

function dateKey(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  if (v instanceof Date) return isoDate(v);
  return String(v).slice(0, 10);
}

function matches(v: unknown, value: FilterValue): boolean {
  switch (value.type) {
    case 'date-range': {
      const key = dateKey(v);
      if (key === null) return false;
      if (value.from !== null && key < value.from) return false;
      if (value.to !== null && key > value.to) return false;
      return true;
    }
    case 'select':
      return v !== null && v !== undefined && value.values.includes(String(v));
    case 'number-range': {
      const n = typeof v === 'number' ? v : Number(v);
      if (!Number.isFinite(n)) return false;
      if (value.min !== null && n < value.min) return false;
      if (value.max !== null && n > value.max) return false;
      return true;
    }
    case 'text':
      return v !== null && v !== undefined && String(v).toLowerCase().includes(value.text.toLowerCase());
  }
}

export function applyFilters(rows: Row[], columns: Column[], filters: Filter[]): Row[] {
  const declared = new Set(columns.map((c) => c.name));
  const active = filters.filter((f) => declared.has(f.column) && isActive(f.value));
  if (active.length === 0) return rows;
  return rows.filter((row) => active.every((f) => matches(row[f.column], f.value)));
}

export function selectOptions(rowSets: Row[][], column: string): SelectOptions {
  const seen = new Set<string>();
  for (const rows of rowSets) {
    for (const row of rows) {
      const v = row[column];
      if (v === null || v === undefined) continue;
      seen.add(String(v));
      if (seen.size > MAX_SELECT_OPTIONS) return { options: [], tooMany: true };
    }
  }
  return { options: [...seen].sort(), tooMany: false };
}

export function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function resolveLast(last: string, today: Date): { from: string; to: string } {
  const m = /^(\d{1,3})([dwmy])$/.exec(last);
  if (!m) throw new Error(`invalid date-range default: ${last}`);
  const n = Number(m[1]);
  const from = new Date(today.getTime());
  switch (m[2]) {
    case 'd':
      from.setDate(from.getDate() - n);
      break;
    case 'w':
      from.setDate(from.getDate() - 7 * n);
      break;
    case 'm':
      from.setMonth(from.getMonth() - n);
      break;
    case 'y':
      from.setFullYear(from.getFullYear() - n);
      break;
  }
  return { from: isoDate(from), to: isoDate(today) };
}

export function defaultFilterValue(control: Control, today: Date, tooMany = false): FilterValue {
  switch (control.type) {
    case 'date-range': {
      const d = control.default;
      if (!d) return { type: 'date-range', from: null, to: null };
      if ('last' in d) {
        const r = resolveLast(d.last, today);
        return { type: 'date-range', from: r.from, to: r.to };
      }
      return { type: 'date-range', from: d.from, to: d.to };
    }
    case 'select': {
      if (tooMany) return { type: 'text', text: '' };
      const d = control.default;
      if (d === null || d === undefined) return { type: 'select', values: [] };
      return { type: 'select', values: Array.isArray(d) ? d : [d] };
    }
    case 'number-range': {
      const d = control.default;
      return { type: 'number-range', min: d?.min ?? null, max: d?.max ?? null };
    }
  }
}

export function filterKey(filters: Filter[]): string {
  return JSON.stringify(filters.map((f) => [f.controlId, f.column, f.value]));
}

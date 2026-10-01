import type { Control } from '../api/types';
import { defaultFilterValue, isActive, type Filter, type FilterValue, type SelectOptions } from '../data/filters';

/**
 * Marks a control the user cleared. It contains ':', which encodeURIComponent
 * always escapes, so no encoded select value can equal it (finding A12: the
 * old marker "-" collided with a select value "-"). Text values start with
 * "~" and ranges contain "..", so they cannot equal it either.
 */
export const CLEARED = ':none';

/** The marker before plan 5c. Still read for range controls, where "-" can never be a value. */
const LEGACY_CLEARED = '-';

function encodeValue(value: FilterValue): string {
  if (!isActive(value)) return CLEARED;
  switch (value.type) {
    case 'date-range':
      return `${value.from ?? ''}..${value.to ?? ''}`;
    case 'number-range':
      return `${value.min ?? ''}..${value.max ?? ''}`;
    case 'select':
      return value.values.map(encodeURIComponent).join(',');
    case 'text':
      return `~${value.text}`;
  }
}

export function encodeFilters(filters: Filter[]): URLSearchParams {
  const params = new URLSearchParams();
  for (const f of filters) params.set(f.controlId, encodeValue(f.value));
  return params;
}

function parseDate(s: string): string | null | undefined {
  // undefined: malformed. null: open end. string: valid ISO date.
  if (s === '') return null;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return undefined;
  const d = new Date(`${s}T00:00:00Z`);
  if (Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== s) return undefined;
  return s;
}

function parseNumber(s: string): number | null | undefined {
  if (s === '') return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : undefined;
}

function decodeValue(raw: string, control: Control, opts: SelectOptions | undefined): FilterValue | undefined {
  switch (control.type) {
    case 'date-range': {
      const parts = raw.split('..');
      if (parts.length !== 2) return undefined;
      const from = parseDate(parts[0]);
      const to = parseDate(parts[1]);
      if (from === undefined || to === undefined) return undefined;
      return { type: 'date-range', from, to };
    }
    case 'number-range': {
      const parts = raw.split('..');
      if (parts.length !== 2) return undefined;
      const min = parseNumber(parts[0]);
      const max = parseNumber(parts[1]);
      if (min === undefined || max === undefined) return undefined;
      return { type: 'number-range', min, max };
    }
    case 'select': {
      if (opts?.tooMany) {
        return { type: 'text', text: raw.startsWith('~') ? raw.slice(1) : raw };
      }
      let values: string[];
      try {
        values = raw.split(',').map(decodeURIComponent).filter((v) => v !== '');
      } catch {
        return undefined;
      }
      if (opts) values = values.filter((v) => opts.options.includes(v));
      if (!control.multi && values.length > 1) values = values.slice(0, 1);
      return { type: 'select', values };
    }
  }
}

export function decodeFilters(
  params: URLSearchParams,
  controls: Control[],
  options: Record<string, SelectOptions | undefined>,
  today: Date,
): Filter[] {
  return controls.map((control) => {
    const opts = options[control.id];
    const tooMany = control.type === 'select' && opts?.tooMany === true;
    const fallback = defaultFilterValue(control, today, tooMany);
    const raw = params.get(control.id);
    let value: FilterValue = fallback;
    if (raw === CLEARED || (raw === LEGACY_CLEARED && control.type !== 'select')) {
      value = tooMany ? { type: 'text', text: '' } : clearedValue(control);
    } else if (raw !== null) {
      value = decodeValue(raw, control, opts) ?? fallback;
    }
    return { controlId: control.id, column: control.column, value };
  });
}

function clearedValue(control: Control): FilterValue {
  switch (control.type) {
    case 'date-range':
      return { type: 'date-range', from: null, to: null };
    case 'number-range':
      return { type: 'number-range', min: null, max: null };
    case 'select':
      return { type: 'select', values: [] };
  }
}

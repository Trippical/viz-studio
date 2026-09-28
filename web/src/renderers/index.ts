import type { Adapter } from './adapter';
import { SanitizeError } from './common';
import { createAdapter as createVegaLite } from './vegaLite';
import { RULES as VEGA_RULES, sanitize as sanitizeVegaLite } from './vegaLiteSanitize';

const ADAPTERS: Record<string, () => Adapter> = {
  'vega-lite': createVegaLite,
};

const SANITIZERS: Record<string, (spec: unknown) => unknown> = {
  'vega-lite': sanitizeVegaLite,
};

export const RULE_COUNTS = {
  'vega-lite': VEGA_RULES.length,
};

function own<T>(table: Record<string, T>, key: string): T | undefined {
  return Object.prototype.hasOwnProperty.call(table, key) ? table[key] : undefined;
}

export function getAdapter(renderer: string): Adapter {
  const factory = own(ADAPTERS, renderer);
  if (!factory) throw new SanitizeError(`unknown renderer: ${renderer}`);
  return factory();
}

export function sanitizeSpec(renderer: string, spec: unknown): unknown {
  const sanitize = own(SANITIZERS, renderer);
  if (!sanitize) throw new SanitizeError(`unknown renderer: ${renderer}`);
  return sanitize(spec);
}

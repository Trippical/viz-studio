import type { Adapter } from './adapter';
import { SanitizeError } from './common';
import { createAdapter as createEcharts } from './echarts';
import { RULES as ECHARTS_RULES, sanitize as sanitizeEcharts } from './echartsSanitize';
import { createAdapter as createPlotly } from './plotly';
import { RULES as PLOTLY_RULES, sanitize as sanitizePlotly } from './plotlySanitize';
import { createAdapter as createVegaLite } from './vegaLite';
import { RULES as VEGA_RULES, sanitize as sanitizeVegaLite } from './vegaLiteSanitize';

const ADAPTERS: Record<string, () => Adapter> = {
  'vega-lite': createVegaLite,
  plotly: createPlotly,
  echarts: createEcharts,
};

const SANITIZERS: Record<string, (spec: unknown) => unknown> = {
  'vega-lite': sanitizeVegaLite,
  plotly: sanitizePlotly,
  echarts: sanitizeEcharts,
};

export const RULE_COUNTS = {
  'vega-lite': VEGA_RULES.length,
  plotly: PLOTLY_RULES.length,
  echarts: ECHARTS_RULES.length,
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

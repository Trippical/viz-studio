import type { Column, Row } from '../api/types';
import type { Adapter } from './adapter';
import { bindTraces } from './plotlyBind';
import { sanitize, type PlotlySpec } from './plotlySanitize';

export const PLOTLY_CONFIG = {
  displaylogo: false,
  showSendToCloud: false,
  showEditInChartStudio: false,
  modeBarButtonsToRemove: ['sendDataToCloud', 'editInChartStudio'],
  responsive: true,
};

type PlotlyModule = typeof import('plotly.js-dist-min').default;

export function createAdapter(): Adapter {
  let el: HTMLElement | null = null;
  let plotly: PlotlyModule | null = null;
  let clean: PlotlySpec | null = null;
  let columns: Column[] = [];

  function layoutFor(spec: PlotlySpec): Record<string, unknown> {
    return { autosize: true, margin: { l: 48, r: 16, t: 32, b: 40 }, ...spec.layout };
  }

  return {
    async mount(target: HTMLElement, spec: unknown, rows: Row[], cols: Column[]): Promise<void> {
      clean = sanitize(spec);
      columns = cols;
      const traces = bindTraces(clean.traces, rows, columns);
      plotly = (await import('plotly.js-dist-min')).default;
      el = target;
      await plotly.newPlot(el, traces, layoutFor(clean), PLOTLY_CONFIG);
    },

    async update(rows: Row[]): Promise<void> {
      if (!el || !clean || !plotly) throw new Error('adapter is not mounted');
      const traces = bindTraces(clean.traces, rows, columns);
      await plotly.react(el, traces, layoutFor(clean), PLOTLY_CONFIG);
    },

    destroy(): void {
      if (el && plotly) plotly.purge(el);
      el = null;
      plotly = null;
      clean = null;
    },
  };
}

import type { Column, Row } from '../api/types';
import type { Adapter } from './adapter';
import { createTextTooltip, type TextTooltip } from './textTooltip';
import { sanitize } from './vegaLiteSanitize';

interface EmbedView {
  data(name: string, values: unknown[]): unknown;
  runAsync(): Promise<unknown>;
}

interface EmbedResult {
  view: EmbedView;
  finalize(): void;
}

/** A Vega loader that refuses every request. Specs cannot fetch anything. */
export function rejectingLoader() {
  const refuse = async (_uri?: unknown, _options?: unknown): Promise<never> => {
    throw new Error('external loads are disabled');
  };
  return { load: refuse, sanitize: refuse, http: refuse, file: refuse };
}

export function createAdapter(): Adapter {
  let result: EmbedResult | null = null;
  let tooltip: TextTooltip | null = null;

  return {
    async mount(el: HTMLElement, spec: unknown, rows: Row[], _columns: Column[]): Promise<void> {
      const clean = sanitize(spec);
      if (clean.width === undefined) clean.width = 'container';
      if (clean.height === undefined) clean.height = 'container';
      const [{ default: embed }, { expressionInterpreter }] = await Promise.all([import('vega-embed'), import('vega-interpreter')]);
      tooltip?.destroy();
      tooltip = createTextTooltip();
      // embed() runs the view once on the empty named dataset; the rows go in
      // right after. Both runs finish inside one task (vega-view and
      // vega-scenegraph render through microtasks only), so the empty frame
      // is never painted. Checked in plan 5c; no fix needed.
      const embedded = await embed(el, clean as never, {
        actions: false,
        renderer: 'canvas',
        ast: true,
        expr: expressionInterpreter as never,
        loader: rejectingLoader() as never,
        tooltip: tooltip.handler as never,
      });
      result = embedded as unknown as EmbedResult;
      result.view.data('data', rows);
      await result.view.runAsync();
    },

    async update(rows: Row[]): Promise<void> {
      if (!result) throw new Error('adapter is not mounted');
      result.view.data('data', rows);
      await result.view.runAsync();
    },

    destroy(): void {
      result?.finalize();
      result = null;
      tooltip?.destroy();
      tooltip = null;
    },
  };
}

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createAdapter, rejectingLoader } from './vegaLite';

const mocks = vi.hoisted(() => {
  const view = { data: vi.fn(), runAsync: vi.fn(async () => undefined) };
  const finalize = vi.fn();
  const embed = vi.fn(async () => ({ view, finalize }));
  return { view, finalize, embed };
});

vi.mock('vega-embed', () => ({ default: mocks.embed }));
vi.mock('vega-interpreter', () => ({ expressionInterpreter: { marker: 'interpreter' } }));

const spec = {
  data: { name: 'data' },
  mark: 'line',
  encoding: { x: { field: 'month', type: 'temporal' }, y: { field: 'revenue', type: 'quantitative' } },
};
const rows = [{ month: '2026-01-01', revenue: 1 }];
const columns = [
  { name: 'month', type: 'date' as const },
  { name: 'revenue', type: 'number' as const },
];

describe('vega-lite adapter', () => {
  beforeEach(() => {
    mocks.embed.mockClear();
    mocks.view.data.mockClear();
    mocks.finalize.mockClear();
  });

  it('mounts with the locked-down options and injects rows by name', async () => {
    const el = document.createElement('div');
    const adapter = createAdapter();
    await adapter.mount(el, spec, rows, columns);
    expect(mocks.embed).toHaveBeenCalledTimes(1);
    const [target, passedSpec, opts] = mocks.embed.mock.calls[0] as unknown as [HTMLElement, Record<string, unknown>, Record<string, unknown>];
    expect(target).toBe(el);
    expect(passedSpec.data).toEqual({ name: 'data' });
    expect(passedSpec.width).toBe('container');
    expect(passedSpec.height).toBe('container');
    expect(opts).toMatchObject({ actions: false, renderer: 'canvas', ast: true, expr: { marker: 'interpreter' } });
    const loader = opts.loader as Record<string, () => Promise<unknown>>;
    for (const name of ['load', 'sanitize', 'http', 'file']) await expect(loader[name]()).rejects.toThrow();
    expect(mocks.view.data).toHaveBeenCalledWith('data', rows);
    expect(mocks.view.runAsync).toHaveBeenCalled();
    adapter.destroy();
  });

  it('update replaces the dataset and destroy finalizes', async () => {
    const adapter = createAdapter();
    await adapter.mount(document.createElement('div'), spec, rows, columns);
    const next = [{ month: '2026-02-01', revenue: 2 }];
    await adapter.update(next);
    expect(mocks.view.data).toHaveBeenLastCalledWith('data', next);
    adapter.destroy();
    expect(mocks.finalize).toHaveBeenCalledTimes(1);
  });

  it('refuses a hostile spec before touching the library', async () => {
    const adapter = createAdapter();
    await expect(adapter.mount(document.createElement('div'), { ...spec, data: { url: 'https://x' } }, rows, columns)).rejects.toThrow(/data/);
    expect(mocks.embed).not.toHaveBeenCalled();
  });

  it('rejectingLoader refuses everything', async () => {
    const loader = rejectingLoader();
    await expect(loader.load('x')).rejects.toThrow(/disabled/);
    await expect(loader.http('x')).rejects.toThrow(/disabled/);
  });

  it('passes a text-only tooltip handler, never vega-tooltip (A6)', async () => {
    const adapter = createAdapter();
    await adapter.mount(document.createElement('div'), spec, rows, columns);
    const opts = (mocks.embed.mock.calls[0] as unknown as [HTMLElement, unknown, Record<string, unknown>])[2];
    expect(typeof opts.tooltip).toBe('function');
    const handler = opts.tooltip as (h: unknown, e: MouseEvent, item: unknown, value: unknown) => void;
    handler(null, new MouseEvent('mousemove', { clientX: 5, clientY: 6 }), {}, { title: '<b>x</b>', image: 'https://evil.example/x.png', revenue: 1 });
    expect(document.querySelector('img')).toBeNull();
    const tip = document.querySelector('.viz-tooltip');
    expect(tip?.textContent).toBe('<b>x</b>\nrevenue: 1');
    expect(tip?.querySelector('b')).toBeNull();
    adapter.destroy();
    expect(document.querySelector('.viz-tooltip')).toBeNull();
  });
});

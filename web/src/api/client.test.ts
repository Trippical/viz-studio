import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, DataTooLarge, SMALL_LANE_MAX_BYTES, dataUrl, fetchChart, fetchRows, fetchTree } from './client';

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
  const text = JSON.stringify(body);
  return new Response(text, {
    status,
    headers: { 'content-type': 'application/json', 'content-length': String(text.length), ...headers },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('client', () => {
  it('dataUrl keeps the id as a path', () => {
    expect(dataUrl('sales/emea/revenue')).toBe('/api/data/sales/emea/revenue');
  });

  it('fetchTree returns the parsed body', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ charts: {}, dashboards: {}, built_at: 'x' }));
    vi.stubGlobal('fetch', fetchMock);
    const tree = await fetchTree();
    expect(tree.built_at).toBe('x');
    expect(fetchMock).toHaveBeenCalledWith('/api/tree', expect.objectContaining({ headers: { Accept: 'application/json' } }));
  });

  it('non-2xx becomes ApiError with the detail', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: { errors: ['id: bad'] } }, 422)));
    await expect(fetchChart('sales/x')).rejects.toMatchObject({ status: 422, detail: { errors: ['id: bad'] } });
    await expect(fetchChart('sales/x')).rejects.toBeInstanceOf(ApiError);
  });

  it('non-JSON error bodies keep the text', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('gateway down', { status: 502 })));
    await expect(fetchChart('sales/x')).rejects.toMatchObject({ status: 502, detail: 'gateway down' });
  });

  it('fetchRows returns row objects', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse([{ a: 1 }, { a: 2 }])));
    expect(await fetchRows('sales/x')).toEqual([{ a: 1 }, { a: 2 }]);
  });

  it('fetchRows refuses oversized bodies by Content-Length', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse([], 200, { 'content-length': String(SMALL_LANE_MAX_BYTES + 1) })),
    );
    await expect(fetchRows('sales/x')).rejects.toBeInstanceOf(DataTooLarge);
  });

  it('fetchRows rejects a body that is not an array of objects', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ rows: [] })));
    await expect(fetchRows('sales/x')).rejects.toMatchObject({ status: 422 });
    vi.stubGlobal('fetch', vi.fn(async () => new Response('not json', { status: 200 })));
    await expect(fetchRows('sales/x')).rejects.toMatchObject({ status: 422 });
  });
});

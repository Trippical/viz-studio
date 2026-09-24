import type { Chart, Dashboard, Row, Tree } from './types';

export const SMALL_LANE_MAX_BYTES = 20971520;

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `request failed with status ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

export class DataTooLarge extends Error {
  bytes: number;
  constructor(bytes: number) {
    super(`data file is ${bytes} bytes, above the small-lane cap of ${SMALL_LANE_MAX_BYTES}`);
    this.name = 'DataTooLarge';
    this.bytes = bytes;
  }
}

export function dataUrl(id: string): string {
  return `/api/data/${id}`;
}

export function assertSmallLaneBytes(byteLength: number): void {
  if (byteLength > SMALL_LANE_MAX_BYTES) throw new DataTooLarge(byteLength);
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

async function readError(res: Response): Promise<unknown> {
  const text = await res.text();
  try {
    const body: unknown = JSON.parse(text);
    if (isPlainObject(body) && 'detail' in body) return body.detail;
    return body;
  } catch {
    return text;
  }
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  const text = await res.text();
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new ApiError(422, 'invalid JSON body');
  }
  return parsed as T;
}

export function fetchTree(): Promise<Tree> {
  return getJson<Tree>('/api/tree');
}

export function fetchDashboard(id: string): Promise<Dashboard> {
  return getJson<Dashboard>(`/api/dashboards/${id}`);
}

export function fetchChart(id: string): Promise<Chart> {
  return getJson<Chart>(`/api/charts/${id}`);
}

export async function fetchRows(id: string): Promise<Row[]> {
  const res = await fetch(dataUrl(id));
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  const declared = Number(res.headers.get('content-length'));
  if (Number.isFinite(declared) && declared > SMALL_LANE_MAX_BYTES) throw new DataTooLarge(declared);
  const buffer = await res.arrayBuffer();
  assertSmallLaneBytes(buffer.byteLength);
  const text = new TextDecoder().decode(buffer);
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new ApiError(422, 'data file is not valid JSON');
  }
  if (!Array.isArray(parsed) || !parsed.every(isPlainObject)) {
    throw new ApiError(422, 'data file is not an array of row objects');
  }
  return parsed as Row[];
}

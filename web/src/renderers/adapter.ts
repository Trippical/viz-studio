import type { Column, Row } from '../api/types';

/** One renderer. mount() sanitizes the spec itself; callers pass the raw spec from the bucket. */
export interface Adapter {
  mount(el: HTMLElement, spec: unknown, rows: Row[], columns: Column[]): Promise<void>;
  update(rows: Row[]): Promise<void>;
  destroy(): void;
}

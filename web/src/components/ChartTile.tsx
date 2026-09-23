import { Component, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ApiError, DataTooLarge, fetchChart, fetchRows } from '../api/client';
import type { Chart, Row } from '../api/types';
import { applyFilters, filterKey, type Filter } from '../data/filters';
import { getAdapter } from '../renderers';
import type { Adapter } from '../renderers/adapter';
import { SanitizeError, isPlainObject } from '../renderers/common';
import { ErrorCard } from './ErrorCard';
import { StatTile } from './StatTile';

export interface ChartTileProps {
  chartId: string;
  filters: Filter[];
  onRows?: (chartId: string, rows: Row[]) => void;
  showTitle?: boolean;
}

export function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 404) return 'not found';
    if (err.status === 413) return 'document too large';
    if (err.status === 422) {
      const detail = err.detail;
      const errors = isPlainObject(detail) && Array.isArray(detail.errors) ? detail.errors : [detail];
      return `invalid document: ${errors.map((e) => (typeof e === 'string' ? e : JSON.stringify(e))).join('; ')}`;
    }
    return `request failed (${err.status})`;
  }
  if (err instanceof DataTooLarge) return err.message;
  if (err instanceof SanitizeError) return `spec rejected: ${err.message}`;
  if (err instanceof Error && err.name === 'DuckDbError') return `query failed: ${err.message}`;
  if (err instanceof Error) return `render failed: ${err.message}`;
  return `render failed: ${String(err)}`;
}

class TileErrorBoundary extends Component<{ id: string; onError?: (err: unknown) => void; children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null };

  static getDerivedStateFromError(err: unknown) {
    return { error: describeError(err) };
  }

  componentDidCatch(err: unknown) {
    this.props.onError?.(err);
  }

  render() {
    if (this.state.error) return <ErrorCard id={this.props.id} reason={this.state.error} />;
    return this.props.children;
  }
}

export function ChartTile({ chartId, filters, onRows, showTitle = true }: ChartTileProps) {
  const [chart, setChart] = useState<Chart | null>(null);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rendered, setRendered] = useState(false);
  const mountRef = useRef<HTMLDivElement>(null);
  const adapterRef = useRef<Adapter | null>(null);
  const queueRef = useRef<Promise<void>>(Promise.resolve());
  const onRowsRef = useRef(onRows);
  onRowsRef.current = onRows;
  const key = filterKey(filters);

  // Load the chart document and its small-lane rows.
  useEffect(() => {
    let cancelled = false;
    setChart(null);
    setRows(null);
    setError(null);
    setRendered(false);
    (async () => {
      try {
        const doc = await fetchChart(chartId);
        if (doc.data.lane === 'large') throw new Error('large lane is not supported yet');
        const data = await fetchRows(chartId);
        if (cancelled) return;
        setChart(doc);
        setRows(data);
        onRowsRef.current?.(chartId, data);
      } catch (err) {
        if (!cancelled) setError(describeError(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chartId]);

  // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` stands in for `filters`
  const filtered = useMemo(() => (chart && rows ? applyFilters(rows, chart.data.columns, filters) : null), [chart, rows, key]);

  // Mount once, then update on every filter change. Operations are serialized.
  // The cleanup below also fires on a chartId change (it is in the deps), so
  // a mount that is still in flight when the chart switches is detected as
  // stale once its promise resolves: the adapter it just built is destroyed
  // instead of being written into adapterRef, so it never receives a later
  // update() call meant for the new chart.
  useEffect(() => {
    if (!chart || !filtered || error) return;
    if (chart.renderer === 'stat') {
      setRendered(true);
      return;
    }
    const el = mountRef.current;
    if (!el) return;
    let cancelled = false;
    queueRef.current = queueRef.current
      .then(async () => {
        if (cancelled) return;
        if (!adapterRef.current) {
          const adapter = getAdapter(chart.renderer);
          await adapter.mount(el, chart.spec, filtered, chart.data.columns);
          if (cancelled) {
            adapter.destroy();
            return;
          }
          adapterRef.current = adapter;
        } else {
          await adapterRef.current.update(filtered);
          if (cancelled) return;
        }
        setRendered(true);
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [chart, filtered, error, chartId]);

  // Tear the adapter down when the tile goes away or changes chart.
  useEffect(
    () => () => {
      adapterRef.current?.destroy();
      adapterRef.current = null;
    },
    [chartId],
  );

  const state = error ? 'error' : rendered ? 'ready' : 'loading';
  const columnNames = chart ? chart.data.columns.map((c) => c.name) : [];

  return (
    <div className="tile" data-tile={chartId} data-state={state} data-rows={filtered ? filtered.length : 0}>
      {showTitle && <h3 className="tile-title">{chart?.title ?? chartId}</h3>}
      <div className="tile-body">
        {error ? (
          <ErrorCard id={chartId} reason={error} />
        ) : chart && filtered && chart.renderer === 'stat' ? (
          <TileErrorBoundary
            id={chartId}
            onError={(err) => {
              setRendered(false);
              setError(describeError(err));
            }}
          >
            <StatTile spec={chart.spec} rows={filtered} columns={columnNames} />
          </TileErrorBoundary>
        ) : (
          <div className="tile-mount" ref={mountRef} />
        )}
        {!error && !rendered && <div className="muted tile-loading">Loading…</div>}
      </div>
    </div>
  );
}

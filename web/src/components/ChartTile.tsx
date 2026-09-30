import { Component, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ApiError, DataTooLarge, dataUrl, fetchChart, fetchRows } from '../api/client';
import type { Chart, Row } from '../api/types';
import { applyFilters, filterKey, isActive, type Filter } from '../data/filters';
import { getAdapter } from '../renderers';
import type { Adapter } from '../renderers/adapter';
import { SanitizeError, isPlainObject } from '../renderers/common';
import { ErrorCard } from './ErrorCard';
import { formatDataAsOf } from './freshness';
import { StatTile } from './StatTile';

let duckdbModule: Promise<typeof import('../data/duckdb')> | null = null;
function loadDuckdb(): Promise<typeof import('../data/duckdb')> {
  if (!duckdbModule) duckdbModule = import('../data/duckdb');
  return duckdbModule;
}

export interface ChartTileProps {
  chartId: string;
  filters: Filter[];
  onRows?: (chartId: string, rows: Row[]) => void;
  /** Columns of the dashboard's select controls; a large-lane tile lists their distinct values (A7). */
  optionColumns?: string[];
  /** Called once per loaded large-lane chart with the distinct values of each declared option column. */
  onOptions?: (chartId: string, values: Record<string, string[]>) => void;
  /** Called when the tile shows its error card, so a dashboard stops waiting for it (A8). */
  onFailed?: (chartId: string) => void;
  /** Control labels by control id, for the "not filtered by" badges (A9). */
  controlLabels?: Record<string, string>;
  /** A chart document the caller already fetched; the tile then skips its own fetch (A12). */
  chart?: Chart;
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

export function ChartTile({ chartId, chart: preloadedChart, filters, onRows, optionColumns, onOptions, onFailed, controlLabels, showTitle = true }: ChartTileProps) {
  const [chart, setChart] = useState<Chart | null>(null);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [largeRows, setLargeRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rendered, setRendered] = useState(false);
  const mountRef = useRef<HTMLDivElement>(null);
  const adapterRef = useRef<Adapter | null>(null);
  const queueRef = useRef<Promise<void>>(Promise.resolve());
  const onRowsRef = useRef(onRows);
  onRowsRef.current = onRows;
  const preloadedRef = useRef(preloadedChart);
  preloadedRef.current = preloadedChart;
  const onFailedRef = useRef(onFailed);
  onFailedRef.current = onFailed;
  const onOptionsRef = useRef(onOptions);
  onOptionsRef.current = onOptions;
  const optionColumnsRef = useRef(optionColumns);
  optionColumnsRef.current = optionColumns;
  const key = filterKey(filters);

  // Load the chart document and its small-lane rows.
  useEffect(() => {
    let cancelled = false;
    setChart(null);
    setRows(null);
    setLargeRows(null);
    setError(null);
    setRendered(false);
    (async () => {
      try {
        const preloaded = preloadedRef.current;
        const doc = preloaded && preloaded.id === chartId ? preloaded : await fetchChart(chartId);
        if (doc.data.lane === 'large') {
          if (!cancelled) setChart(doc);
          return;
        }
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
  const filtered = useMemo(() => {
    if (!chart) return null;
    if (chart.data.lane === 'large') return largeRows;
    return rows ? applyFilters(rows, chart.data.columns, filters) : null;
  }, [chart, rows, largeRows, key]);

  // Large lane: every filter change is a new DuckDB query over the parquet table.
  useEffect(() => {
    if (!chart || chart.data.lane !== 'large' || error) return;
    let cancelled = false;
    (async () => {
      try {
        const { queryLargeLane } = await loadDuckdb();
        const result = await queryLargeLane(chartId, chart.aggregate ?? '', chart.data.columns, filters);
        if (!cancelled) setLargeRows(result);
      } catch (err) {
        if (!cancelled) setError(describeError(err));
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` stands in for `filters`
  }, [chart, chartId, key, error]);

  // Large lane (finding A7): list the distinct values of every select-control
  // column this chart declares, once per loaded chart, over the unfiltered
  // data, and report them so the control bar can offer them.
  useEffect(() => {
    if (!chart || chart.id !== chartId || chart.data.lane !== 'large') return;
    let cancelled = false;
    const declared = new Set(chart.data.columns.map((c) => c.name));
    const wanted = (optionColumnsRef.current ?? []).filter((column, i, all) => declared.has(column) && all.indexOf(column) === i);
    (async () => {
      try {
        const { distinctValues } = await loadDuckdb();
        const out: Record<string, string[]> = {};
        for (const column of wanted) out[column] = await distinctValues(chartId, column, chart.data.columns);
        if (!cancelled) onOptionsRef.current?.(chartId, out);
      } catch (err) {
        if (!cancelled) setError(describeError(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chart, chartId]);

  // Finding A8: a failed tile will never report rows or options; say so.
  useEffect(() => {
    if (error) onFailedRef.current?.(chartId);
  }, [error, chartId]);

  // Mount once, then update on every filter change. Operations are serialized.
  // The cleanup below also fires on a chartId change (it is in the deps), so
  // a mount that is still in flight when the chart switches is detected as
  // stale once its promise resolves: the adapter it just built is destroyed
  // instead of being written into adapterRef, so it never receives a later
  // update() call meant for the new chart.
  //
  // The chart.id !== chartId check below covers the case where chartId
  // switches while the *previous* chart's document is still the current
  // `chart` state: chartId being in the deps re-runs this effect on the
  // stale `chart`/`filtered` closures before the new chart's document has
  // loaded. Without the id check that stale run would queue a fresh mount
  // of the old chart's spec, which could resolve after adapterRef has been
  // nulled by the chartId-keyed destroy effect and get written back in,
  // orphaning the adapter the next chart's update() should have used. It
  // also stops the stat branch below from synchronously reporting "ready"
  // for the old chart's stale spec in that same stale pass.
  useEffect(() => {
    if (!chart || chart.id !== chartId || !filtered || error) return;
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

  // Finding A9: an empty result says so, and the tile names every active
  // control it ignores because it does not declare that control's column.
  const declared = new Set(chart ? chart.data.columns.map((c) => c.name) : []);
  const activeFilters = chart ? filters.filter((f) => isActive(f.value)) : [];
  const ignored = activeFilters.filter((f) => !declared.has(f.column));
  const appliedCount = activeFilters.length - ignored.length;
  const empty = !error && rendered && filtered !== null && filtered.length === 0;

  // Finding A10: a text alternative for the canvas and a link to the data
  // file; plus when the data was published (no refresher runs in v1).
  const ariaLabel = chart ? (chart.description ? `${chart.title}. ${chart.description}` : chart.title) : chartId;
  const asOf = formatDataAsOf(chart?.updated_at);

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
          <div className="tile-chart" role="img" aria-label={ariaLabel}>
            <div className="tile-mount" ref={mountRef} />
          </div>
        )}
        {!error && !rendered && <div className="muted tile-loading">Loading…</div>}
        {empty && <div className="tile-empty muted">{appliedCount > 0 ? 'No rows match the filters' : 'No rows'}</div>}
      </div>
      <div className="tile-footer">
        {ignored.map((f) => (
          <span key={f.controlId} className="badge tile-badge">{`not filtered by ${controlLabels?.[f.controlId] ?? f.controlId}`}</span>
        ))}
        {asOf && <span className="muted tile-asof">{`Data as of ${asOf}`}</span>}
        {chart && (
          <a className="tile-download" href={dataUrl(chartId)} download>
            Download data
          </a>
        )}
      </div>
    </div>
  );
}

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { fetchDashboard } from '../api/client';
import type { Dashboard, Row } from '../api/types';
import { ChartTile, describeError } from '../components/ChartTile';
import { ControlBar } from '../components/ControlBar';
import { ErrorCard } from '../components/ErrorCard';
import { Markdown } from '../components/Markdown';
import { selectOptions, type FilterValue, type SelectOptions } from '../data/filters';
import { decodeFilters, encodeFilters } from '../state/urlState';

export function DashboardPage() {
  const id = useParams()['*'] ?? '';
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rowsByChart, setRowsByChart] = useState<Record<string, Row[]>>({});
  const [searchParams, setSearchParams] = useSearchParams();
  const today = useMemo(() => new Date(), []);

  useEffect(() => {
    let cancelled = false;
    setDashboard(null);
    setError(null);
    setRowsByChart({});
    fetchDashboard(id)
      .then((doc) => {
        if (!cancelled) setDashboard(doc);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(describeError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const controls = useMemo(() => dashboard?.controls ?? [], [dashboard]);

  const options = useMemo(() => {
    const out: Record<string, SelectOptions | undefined> = {};
    const sets = Object.values(rowsByChart);
    if (sets.length === 0) return out;
    for (const c of controls) if (c.type === 'select') out[c.id] = selectOptions(sets, c.column);
    return out;
  }, [controls, rowsByChart]);

  // Values restored from the URL are re-validated here: decodeFilters is
  // re-run whenever the derived select `options` change (i.e. whenever the
  // union of rows reported by the small-lane tiles grows), and any select
  // value that is not among the derived options is dropped by decodeFilters.
  const filters = useMemo(() => decodeFilters(searchParams, controls, options, today), [searchParams, controls, options, today]);

  const onChange = useCallback(
    (controlId: string, value: FilterValue) => {
      const next = filters.map((f) => (f.controlId === controlId ? { ...f, value } : f));
      setSearchParams(encodeFilters(next), { replace: true });
    },
    [filters, setSearchParams],
  );

  const onRows = useCallback((chartId: string, rows: Row[]) => {
    setRowsByChart((prev) => ({ ...prev, [chartId]: rows }));
  }, []);

  if (error) return <ErrorCard id={id} reason={error} />;
  if (!dashboard) return <div className="muted">Loading…</div>;

  return (
    <div className="dashboard-page">
      <h2>{dashboard.title}</h2>
      {dashboard.description && <Markdown text={dashboard.description} />}
      {controls.length > 0 && <ControlBar controls={controls} filters={filters} options={options} onChange={onChange} />}
      <div className="grid">
        {dashboard.layout.map((tile, i) => {
          const style = { gridColumn: `span ${tile.w}`, gridRow: `span ${tile.h}` };
          if ('markdown' in tile) {
            return (
              <div key={`md-${i}`} className="grid-cell" style={style}>
                <div className="tile tile-markdown">
                  <Markdown text={tile.markdown} />
                </div>
              </div>
            );
          }
          return (
            <div key={`${tile.chart}-${i}`} className="grid-cell" style={style}>
              <ChartTile chartId={tile.chart} filters={filters} onRows={onRows} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

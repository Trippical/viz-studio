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

/** Distinct values one large-lane tile reported, by column name (finding A7). */
type ValueLists = Record<string, string[]>;

export function DashboardPage() {
  const id = useParams()['*'] ?? '';
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rowsByChart, setRowsByChart] = useState<Record<string, Row[]>>({});
  const [valuesByChart, setValuesByChart] = useState<Record<string, ValueLists>>({});
  const [reported, setReported] = useState<Record<string, boolean>>({});
  const [searchParams, setSearchParams] = useSearchParams();
  const today = useMemo(() => new Date(), []);

  useEffect(() => {
    let cancelled = false;
    setDashboard(null);
    setError(null);
    setRowsByChart({});
    setValuesByChart({});
    setReported({});
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
  const selectColumns = useMemo(() => controls.filter((c) => c.type === 'select').map((c) => c.column), [controls]);
  const controlLabels = useMemo(() => Object.fromEntries(controls.map((c) => [c.id, c.label])), [controls]);
  const chartIds = useMemo(() => {
    const ids: string[] = [];
    for (const tile of dashboard?.layout ?? []) if ('chart' in tile && !ids.includes(tile.chart)) ids.push(tile.chart);
    return ids;
  }, [dashboard]);

  // Finding A8: until every chart tile has reported its rows, its options or
  // its failure, the option lists are incomplete, so select values restored
  // from the URL are not checked against them yet.
  const allReported = chartIds.every((chartId) => reported[chartId] === true);

  // Small-lane tiles report rows; large-lane tiles report distinct values per
  // column (finding A7). Both feed the same capped option list.
  const options = useMemo(() => {
    const out: Record<string, SelectOptions | undefined> = {};
    const rowSets = Object.values(rowsByChart);
    const valueSets = Object.values(valuesByChart);
    if (rowSets.length === 0 && valueSets.length === 0) return out;
    for (const c of controls) {
      if (c.type !== 'select') continue;
      const fromLarge: Row[][] = [];
      for (const lists of valueSets) {
        const values = lists[c.column];
        if (values) fromLarge.push(values.map((v) => ({ [c.column]: v })));
      }
      out[c.id] = selectOptions([...rowSets, ...fromLarge], c.column);
    }
    return out;
  }, [controls, rowsByChart, valuesByChart]);

  const filters = useMemo(
    () => decodeFilters(searchParams, controls, allReported ? options : {}, today),
    [searchParams, controls, options, allReported, today],
  );

  const onChange = useCallback(
    (controlId: string, value: FilterValue) => {
      const next = encodeFilters(filters.map((f) => (f.controlId === controlId ? { ...f, value } : f)));
      // Finding A8: every control the user did not touch keeps exactly the
      // value the URL has, even one not (yet) among the reported options.
      for (const control of controls) {
        if (control.id === controlId) continue;
        const raw = searchParams.get(control.id);
        if (raw !== null) next.set(control.id, raw);
      }
      setSearchParams(next, { replace: true });
    },
    [filters, controls, searchParams, setSearchParams],
  );

  const onRows = useCallback((chartId: string, rows: Row[]) => {
    setRowsByChart((prev) => ({ ...prev, [chartId]: rows }));
    setReported((prev) => ({ ...prev, [chartId]: true }));
  }, []);

  const onOptions = useCallback((chartId: string, values: ValueLists) => {
    setValuesByChart((prev) => ({ ...prev, [chartId]: values }));
    setReported((prev) => ({ ...prev, [chartId]: true }));
  }, []);

  const onFailed = useCallback((chartId: string) => {
    setReported((prev) => ({ ...prev, [chartId]: true }));
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
              <ChartTile
                chartId={tile.chart}
                filters={filters}
                onRows={onRows}
                onOptions={onOptions}
                onFailed={onFailed}
                optionColumns={selectColumns}
                controlLabels={controlLabels}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

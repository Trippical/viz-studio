import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { fetchChart } from '../api/client';
import type { Chart } from '../api/types';
import { ChartTile, describeError } from '../components/ChartTile';
import { ErrorCard } from '../components/ErrorCard';
import { Markdown } from '../components/Markdown';
import type { Filter } from '../data/filters';

const NO_FILTERS: Filter[] = [];

export function ChartPage() {
  const id = useParams()['*'] ?? '';
  const [chart, setChart] = useState<Chart | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setChart(null);
    setError(null);
    fetchChart(id)
      .then((doc) => {
        if (!cancelled) setChart(doc);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(describeError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (error) return <ErrorCard id={id} reason={error} />;
  if (!chart) return <div className="muted">Loading…</div>;

  // No refresher runs in v1, so the page names the source and nothing more
  // (findings intent item 2). The tile footer says when the data is from.
  const sql = chart.source?.show_sql === true && typeof chart.source.sql === 'string' && chart.source.sql !== '' ? chart.source.sql : null;

  return (
    <div className="chart-page">
      <h2>
        {chart.title}
        {!chart.source && <span className="badge">static</span>}
      </h2>
      <ChartTile chartId={id} chart={chart} filters={NO_FILTERS} showTitle={false} />
      {chart.description && <Markdown text={chart.description} />}
      <table className="columns-table">
        <thead>
          <tr>
            <th>Column</th>
            <th>Type</th>
          </tr>
        </thead>
        <tbody>
          {chart.data.columns.map((c) => (
            <tr key={c.name}>
              <td>{c.name}</td>
              <td>{c.type}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {chart.source && <p className="muted">Source: Databricks SQL</p>}
      {sql && <pre className="sql">{sql}</pre>}
      <p className="muted">
        {chart.data.lane} lane, {chart.data.rows} rows, {chart.data.bytes} bytes, renderer {chart.renderer}
      </p>
    </div>
  );
}

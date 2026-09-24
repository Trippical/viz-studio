import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { fetchChart } from '../api/client';
import type { Chart } from '../api/types';
import { ChartTile, describeError } from '../components/ChartTile';
import { ErrorCard } from '../components/ErrorCard';
import { Markdown } from '../components/Markdown';

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

  return (
    <div className="chart-page">
      <h2>
        {chart?.title ?? id}
        {chart && !chart.source && <span className="badge">static</span>}
      </h2>
      <ChartTile chartId={id} filters={[]} showTitle={false} />
      {chart?.description && <Markdown text={chart.description} />}
      {chart && (
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
      )}
      {chart?.source?.sql && <pre className="sql">{chart.source.sql}</pre>}
      {chart?.source && !chart.source.sql && (
        <p className="muted">Refreshable from Databricks SQL (SQL hidden by the publisher){chart.source.schedule ? `, schedule ${chart.source.schedule}` : ''}.</p>
      )}
      {chart && (
        <p className="muted">
          {chart.data.lane} lane, {chart.data.rows} rows, {chart.data.bytes} bytes, renderer {chart.renderer}
          {chart.updated_at ? `, updated ${chart.updated_at}` : ''}
        </p>
      )}
    </div>
  );
}

// "Data as of" text for tiles and the chart page. v1 has no refresher, so the
// publish time (`updated_at`) is when the data was last loaded.

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

/** `YYYY-MM-DD HH:MM UTC` for a readable ISO timestamp, otherwise null. */
export function formatDataAsOf(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
}

// A text-only tooltip for Vega (finding A6). vega-embed's default handler,
// vega-tooltip, builds HTML and turns an `image` key into an <img src> that a
// bucket spec could point anywhere. This handler only ever sets textContent,
// so no markup from a spec or a data row is ever parsed.

export const MAX_TOOLTIP_CHARS = 2000;

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return String(v);
  if (typeof v === 'string') return v;
  if (typeof v === 'number' || typeof v === 'boolean' || typeof v === 'bigint') return String(v);
  if (v instanceof Date) return v.toISOString();
  try {
    return JSON.stringify(v) ?? '';
  } catch {
    return '[unprintable]';
  }
}

/** The tooltip text for a Vega tooltip value. Pure. The `image` key is dropped. */
export function tooltipText(value: unknown): string {
  let text: string;
  if (value !== null && typeof value === 'object' && !Array.isArray(value) && !(value instanceof Date)) {
    const obj = value as Record<string, unknown>;
    const lines: string[] = [];
    if ('title' in obj) lines.push(formatValue(obj.title));
    for (const key of Object.keys(obj)) {
      if (key === 'title' || key === 'image') continue;
      lines.push(`${key}: ${formatValue(obj[key])}`);
    }
    text = lines.join('\n');
  } else {
    text = formatValue(value);
  }
  return text.length > MAX_TOOLTIP_CHARS ? `${text.slice(0, MAX_TOOLTIP_CHARS)}…` : text;
}

export interface TextTooltip {
  handler(handler: unknown, event: MouseEvent, item: unknown, value: unknown): void;
  destroy(): void;
}

/** One tooltip element per chart, appended to the body on first use. */
export function createTextTooltip(doc: Document = document): TextTooltip {
  let el: HTMLDivElement | null = null;
  return {
    handler(_handler: unknown, event: MouseEvent, _item: unknown, value: unknown): void {
      if (value === null || value === undefined || value === '') {
        if (el) el.style.display = 'none';
        return;
      }
      if (!el) {
        el = doc.createElement('div');
        el.className = 'viz-tooltip';
        el.setAttribute('role', 'tooltip');
        doc.body.appendChild(el);
      }
      el.textContent = tooltipText(value);
      el.style.display = 'block';
      el.style.left = `${event.clientX + 12}px`;
      el.style.top = `${event.clientY + 12}px`;
    },
    destroy(): void {
      el?.remove();
      el = null;
    },
  };
}

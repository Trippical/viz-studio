import type { Control } from '../api/types';
import type { Filter, FilterValue, SelectOptions } from '../data/filters';

export interface ControlBarProps {
  controls: Control[];
  filters: Filter[];
  options: Record<string, SelectOptions | undefined>;
  onChange: (controlId: string, value: FilterValue) => void;
}

function num(s: string): number | null {
  if (s.trim() === '') return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

function Widget({ control, value, opts, onChange }: { control: Control; value: FilterValue; opts: SelectOptions | undefined; onChange: (v: FilterValue) => void }) {
  const id = `ctl-${control.id}`;
  if (control.type === 'date-range' && value.type === 'date-range') {
    return (
      <div className="control">
        <span>{control.label}</span>
        <div className="range">
          <label htmlFor={`${id}-from`} className="muted">from</label>
          <input id={`${id}-from`} type="date" aria-label={`${control.label} from`} value={value.from ?? ''} onChange={(e) => onChange({ ...value, from: e.target.value || null })} />
          <label htmlFor={`${id}-to`} className="muted">to</label>
          <input id={`${id}-to`} type="date" aria-label={`${control.label} to`} value={value.to ?? ''} onChange={(e) => onChange({ ...value, to: e.target.value || null })} />
        </div>
      </div>
    );
  }
  if (control.type === 'number-range' && value.type === 'number-range') {
    return (
      <div className="control">
        <span>{control.label}</span>
        <div className="range">
          <label htmlFor={`${id}-from`} className="muted">from</label>
          <input id={`${id}-from`} type="number" aria-label={`${control.label} from`} value={value.min ?? ''} onChange={(e) => onChange({ ...value, min: num(e.target.value) })} />
          <label htmlFor={`${id}-to`} className="muted">to</label>
          <input id={`${id}-to`} type="number" aria-label={`${control.label} to`} value={value.max ?? ''} onChange={(e) => onChange({ ...value, max: num(e.target.value) })} />
        </div>
      </div>
    );
  }
  if (control.type === 'select' && value.type === 'text') {
    return (
      <div className="control">
        <label htmlFor={id}>{control.label}</label>
        <input id={id} type="text" placeholder="contains…" value={value.text} onChange={(e) => onChange({ type: 'text', text: e.target.value })} />
        {opts?.tooMany && <span className="muted">too many values to list</span>}
      </div>
    );
  }
  if (control.type === 'select' && value.type === 'select') {
    const list = opts?.options ?? value.values;
    const multi = control.multi === true;
    return (
      <div className="control">
        <label htmlFor={id}>{control.label}</label>
        <select
          id={id}
          multiple={multi}
          value={multi ? value.values : (value.values[0] ?? '')}
          onChange={(e) => {
            const picked = Array.from(e.target.selectedOptions).map((o) => o.value).filter((v) => v !== '');
            onChange({ type: 'select', values: multi ? picked : picked.slice(0, 1) });
          }}
        >
          {!multi && <option value="">(all)</option>}
          {list.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </div>
    );
  }
  return null;
}

export function ControlBar({ controls, filters, options, onChange }: ControlBarProps) {
  return (
    <div className="control-bar">
      {controls.map((control) => {
        const filter = filters.find((f) => f.controlId === control.id);
        if (!filter) return null;
        return <Widget key={control.id} control={control} value={filter.value} opts={options[control.id]} onChange={(v) => onChange(control.id, v)} />;
      })}
    </div>
  );
}

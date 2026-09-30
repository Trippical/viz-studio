import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Control } from '../api/types';
import type { Filter } from '../data/filters';
import { ControlBar } from './ControlBar';

const controls: Control[] = [
  { id: 'period', type: 'date-range', label: 'Period', column: 'month', default: null },
  { id: 'region', type: 'select', label: 'Region', column: 'region', multi: true, default: null },
  { id: 'one', type: 'select', label: 'One region', column: 'region', default: null },
  { id: 'minrev', type: 'number-range', label: 'Revenue', column: 'revenue', default: null },
];
const filters: Filter[] = [
  { controlId: 'period', column: 'month', value: { type: 'date-range', from: '2026-01-01', to: null } },
  { controlId: 'region', column: 'region', value: { type: 'select', values: ['EMEA'] } },
  { controlId: 'one', column: 'region', value: { type: 'select', values: [] } },
  { controlId: 'minrev', column: 'revenue', value: { type: 'number-range', min: null, max: 5 } },
];
const options = { region: { options: ['APAC', 'EMEA', 'NA'], tooMany: false }, one: { options: ['APAC', 'EMEA', 'NA'], tooMany: false } };

describe('ControlBar', () => {
  it('renders labelled widgets with current values', () => {
    render(<ControlBar controls={controls} filters={filters} options={options} onChange={() => undefined} />);
    expect(screen.getByLabelText('Period from')).toHaveValue('2026-01-01');
    expect(screen.getByLabelText('Period to')).toHaveValue('');
    const region = screen.getByLabelText('Region') as HTMLSelectElement;
    expect(region.multiple).toBe(true);
    expect(Array.from(region.selectedOptions).map((o) => o.value)).toEqual(['EMEA']);
    expect(screen.getByLabelText('One region')).toHaveValue('');
    expect(screen.getByLabelText('Revenue to')).toHaveValue(5);
  });

  it('emits typed values on change', () => {
    const onChange = vi.fn();
    render(<ControlBar controls={controls} filters={filters} options={options} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('Period to'), { target: { value: '2026-03-01' } });
    expect(onChange).toHaveBeenLastCalledWith('period', { type: 'date-range', from: '2026-01-01', to: '2026-03-01' });

    const region = screen.getByLabelText('Region') as HTMLSelectElement;
    for (const o of Array.from(region.options)) o.selected = o.value === 'APAC' || o.value === 'NA';
    fireEvent.change(region);
    expect(onChange).toHaveBeenLastCalledWith('region', { type: 'select', values: ['APAC', 'NA'] });

    fireEvent.change(screen.getByLabelText('One region'), { target: { value: 'NA' } });
    expect(onChange).toHaveBeenLastCalledWith('one', { type: 'select', values: ['NA'] });

    fireEvent.change(screen.getByLabelText('Revenue from'), { target: { value: '2.5' } });
    expect(onChange).toHaveBeenLastCalledWith('minrev', { type: 'number-range', min: 2.5, max: 5 });
    fireEvent.change(screen.getByLabelText('Revenue to'), { target: { value: '' } });
    expect(onChange).toHaveBeenLastCalledWith('minrev', { type: 'number-range', min: null, max: null });
  });

  it('falls back to a text box when there are too many options', () => {
    const onChange = vi.fn();
    render(
      <ControlBar
        controls={[controls[1]]}
        filters={[{ controlId: 'region', column: 'region', value: { type: 'text', text: 'em' } }]}
        options={{ region: { options: [], tooMany: true } }}
        onChange={onChange}
      />,
    );
    const box = screen.getByLabelText('Region');
    expect(box.tagName).toBe('INPUT');
    expect(box).toHaveValue('em');
    fireEvent.change(box, { target: { value: 'na' } });
    expect(onChange).toHaveBeenLastCalledWith('region', { type: 'text', text: 'na' });
  });
});

describe('ControlBar while options are still arriving (A8)', () => {
  it('keeps a current select value listed and selected even before the options include it', () => {
    render(
      <ControlBar
        controls={[controls[1]]}
        filters={[{ controlId: 'region', column: 'region', value: { type: 'select', values: ['LATAM'] } }]}
        options={{ region: { options: ['EMEA'], tooMany: false } }}
        onChange={() => undefined}
      />,
    );
    const region = screen.getByLabelText('Region') as HTMLSelectElement;
    expect(Array.from(region.options).map((o) => o.value)).toEqual(['EMEA', 'LATAM']);
    expect(Array.from(region.selectedOptions).map((o) => o.value)).toEqual(['LATAM']);
  });
});

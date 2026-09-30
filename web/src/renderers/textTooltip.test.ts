import { afterEach, describe, expect, it } from 'vitest';
import { MAX_TOOLTIP_CHARS, createTextTooltip, tooltipText } from './textTooltip';

afterEach(() => {
  for (const el of Array.from(document.querySelectorAll('.viz-tooltip'))) el.remove();
});

function move(x = 5, y = 6): MouseEvent {
  return new MouseEvent('mousemove', { clientX: x, clientY: y });
}

describe('tooltipText', () => {
  it('puts the title first, lists the other keys, and drops image', () => {
    expect(tooltipText({ revenue: 1, title: 'EMEA', image: 'https://evil.example/x.png', month: '2026-01-01' })).toBe(
      'EMEA\nrevenue: 1\nmonth: 2026-01-01',
    );
  });

  it('formats scalars, nulls, arrays and nested objects as text', () => {
    expect(tooltipText('plain')).toBe('plain');
    expect(tooltipText(42)).toBe('42');
    expect(tooltipText({ a: null, b: [1, 2], c: { d: true } })).toBe('a: null\nb: [1,2]\nc: {"d":true}');
  });

  it('keeps markup as literal text', () => {
    expect(tooltipText({ title: '<img src=x onerror=alert(1)>' })).toBe('<img src=x onerror=alert(1)>');
  });

  it('caps very long text', () => {
    const out = tooltipText('x'.repeat(MAX_TOOLTIP_CHARS + 50));
    expect(out).toHaveLength(MAX_TOOLTIP_CHARS + 1);
    expect(out.endsWith('…')).toBe(true);
  });
});

describe('createTextTooltip', () => {
  it('shows text only, never an element built from the value', () => {
    const tip = createTextTooltip();
    tip.handler(null, move(10, 20), {}, { title: '<b>bold</b>', image: 'https://evil.example/x.png' });
    const el = document.querySelector('.viz-tooltip') as HTMLElement;
    expect(el).not.toBeNull();
    expect(el.getAttribute('role')).toBe('tooltip');
    expect(el.textContent).toBe('<b>bold</b>');
    expect(el.children).toHaveLength(0);
    expect(document.querySelector('img')).toBeNull();
    expect(el.style.display).toBe('block');
    expect(el.style.left).toBe('22px');
    expect(el.style.top).toBe('32px');
  });

  it('hides on an empty value and is removed by destroy', () => {
    const tip = createTextTooltip();
    tip.handler(null, move(), {}, { a: 1 });
    tip.handler(null, move(), {}, null);
    expect((document.querySelector('.viz-tooltip') as HTMLElement).style.display).toBe('none');
    tip.destroy();
    expect(document.querySelector('.viz-tooltip')).toBeNull();
  });
});

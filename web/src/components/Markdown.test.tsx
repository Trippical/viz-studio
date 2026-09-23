import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Markdown, safeUrl } from './Markdown';

describe('safeUrl', () => {
  it('allows http, https, mailto and relative', () => {
    expect(safeUrl('https://example.com/x')).toBe('https://example.com/x');
    expect(safeUrl('http://example.com')).toBe('http://example.com');
    expect(safeUrl('mailto:a@b.c')).toBe('mailto:a@b.c');
    expect(safeUrl('/d/sales/overview')).toBe('/d/sales/overview');
    expect(safeUrl('sales/overview')).toBe('sales/overview');
  });

  it('blocks other schemes and protocol-relative URLs', () => {
    expect(safeUrl('javascript:alert(1)')).toBe('');
    expect(safeUrl('JAVASCRIPT:alert(1)')).toBe('');
    expect(safeUrl('data:text/html,hi')).toBe('');
    expect(safeUrl('vbscript:x')).toBe('');
    expect(safeUrl('//evil.example/x')).toBe('');
    expect(safeUrl('  javascript:1')).toBe('');
  });
});

describe('Markdown', () => {
  it('renders emphasis and GFM tables, never raw HTML', () => {
    const { container } = render(<Markdown text={'**bold** <script>alert(1)</script> <b>raw</b>\n\n| a | b |\n|---|---|\n| 1 | 2 |'} />);
    expect(screen.getByText('bold').tagName).toBe('STRONG');
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('b')).toBeNull();
    expect(container.querySelector('table')).not.toBeNull();
  });

  it('links open in a new tab with the safe rel and unsafe hrefs are dropped', () => {
    render(<Markdown text={'[ok](https://example.com) [bad](javascript:alert(1))'} />);
    const ok = screen.getByText('ok');
    expect(ok.tagName).toBe('A');
    expect(ok).toHaveAttribute('href', 'https://example.com');
    expect(ok).toHaveAttribute('target', '_blank');
    expect(ok).toHaveAttribute('rel', 'noopener noreferrer nofollow');
    const bad = screen.getByText('bad');
    expect(bad.tagName).not.toBe('A');
  });

  it('renders same-origin images only', () => {
    const { container } = render(<Markdown text={'![a](/assets/a.png) ![b](https://evil.example/b.png)'} />);
    const imgs = container.querySelectorAll('img');
    expect(imgs).toHaveLength(1);
    expect(imgs[0]).toHaveAttribute('src', '/assets/a.png');
    expect(container.textContent).toContain('[image blocked]');
  });
});

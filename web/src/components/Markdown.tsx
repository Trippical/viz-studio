import type { ComponentProps } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const ALLOWED_SCHEMES = new Set(['http', 'https', 'mailto']);

/** Returns the URL if it may be rendered, otherwise an empty string. */
export function safeUrl(url: string): string {
  const trimmed = url.trim();
  if (trimmed === '') return '';
  if (trimmed.startsWith('//')) return '';
  const colon = trimmed.indexOf(':');
  if (colon > 0 && /^[a-z][a-z0-9+.-]*$/i.test(trimmed.slice(0, colon))) {
    return ALLOWED_SCHEMES.has(trimmed.slice(0, colon).toLowerCase()) ? trimmed : '';
  }
  return trimmed;
}

export function isSameOrigin(url: string): boolean {
  try {
    return new URL(url, window.location.origin).origin === window.location.origin;
  } catch {
    return false;
  }
}

function Link({ href, children }: ComponentProps<'a'>) {
  if (!href) return <span>{children}</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer nofollow">
      {children}
    </a>
  );
}

function Image({ src, alt }: ComponentProps<'img'>) {
  if (typeof src !== 'string' || src === '' || !isSameOrigin(src)) return <span className="muted">[image blocked]</span>;
  return <img src={src} alt={alt ?? ''} />;
}

export function Markdown({ text }: { text: string }) {
  return (
    <ReactMarkdown
      skipHtml
      remarkPlugins={[remarkGfm]}
      urlTransform={(url) => safeUrl(url)}
      components={{ a: Link, img: Image }}
    >
      {text}
    </ReactMarkdown>
  );
}

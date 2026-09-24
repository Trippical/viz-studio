import type { ComponentProps } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const ALLOWED_SCHEMES = new Set(['http', 'https', 'mailto']);

/** Returns the URL if it may be rendered, otherwise an empty string. */
export function safeUrl(url: string): string {
  // Browsers strip ASCII tab, newline and carriage return from a URL
  // before parsing its scheme, so an attacker can hide "javascript:" as
  // "java\tscript:". Strip the same characters before any other check so
  // every later check runs against what the browser will actually see.
  const cleaned = url.trim().replace(/[\t\n\r]/g, '');
  if (cleaned === '') return '';
  if (cleaned.startsWith('//')) return '';
  const colon = cleaned.indexOf(':');
  const delimiter = cleaned.search(/[/?#]/);
  const hasScheme = colon > 0 && (delimiter === -1 || colon < delimiter);
  if (hasScheme) {
    return ALLOWED_SCHEMES.has(cleaned.slice(0, colon).toLowerCase()) ? cleaned : '';
  }
  return cleaned;
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

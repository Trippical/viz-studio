import { describe, expect, it } from 'vitest';
import { formatDataAsOf } from './freshness';

describe('formatDataAsOf', () => {
  it('formats an ISO timestamp as UTC minutes', () => {
    expect(formatDataAsOf('2026-09-22T10:00:00Z')).toBe('2026-09-22 10:00 UTC');
    expect(formatDataAsOf('2026-09-22T12:30:45+02:00')).toBe('2026-09-22 10:30 UTC');
    expect(formatDataAsOf('2026-01-05T03:04:00.123Z')).toBe('2026-01-05 03:04 UTC');
  });

  it('returns null for a missing or unreadable value', () => {
    expect(formatDataAsOf(undefined)).toBeNull();
    expect(formatDataAsOf(null)).toBeNull();
    expect(formatDataAsOf('')).toBeNull();
    expect(formatDataAsOf('yesterday')).toBeNull();
  });
});

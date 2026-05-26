import { describe, it, expect } from 'vitest';
import { formatPrice } from '../../src/lib/formatPrice';

describe('formatPrice', () => {
  it('formats GBP price correctly', () => {
    expect(formatPrice(9.99, 'GBP')).toBe('£9.99');
  });

  it('returns — for null', () => {
    expect(formatPrice(null, 'USD')).toBe('—');
  });

  it('returns — for undefined', () => {
    expect(formatPrice(undefined, 'GBP')).toBe('—');
  });

  it('formats EUR with thousands separator', () => {
    expect(formatPrice(1234.5, 'EUR')).toBe('€1,234.50');
  });

  it('formats USD price correctly', () => {
    expect(formatPrice(9.99, 'USD')).toBe('US$9.99');
  });

  it('returns — for non-numeric string', () => {
    expect(formatPrice('not-a-number', 'GBP')).toBe('—');
  });

  it('accepts numeric string input', () => {
    expect(formatPrice('9.99', 'GBP')).toBe('£9.99');
  });
});

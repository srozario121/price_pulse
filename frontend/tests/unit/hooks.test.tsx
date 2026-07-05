import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { usePrices } from '../../src/hooks/usePrices';
import { useScrapeProduct } from '../../src/hooks/useScrape';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe('usePrices', () => {
  it('returns price data for a product', async () => {
    const { result } = renderHook(() => usePrices(1), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.items).toHaveLength(5);
    expect(result.current.data?.items[0].product_id).toBe(1);
  });

  it('is not enabled when productId is 0', () => {
    const { result } = renderHook(() => usePrices(0), { wrapper: makeWrapper() });
    expect(result.current.isFetching).toBe(false);
  });
});

describe('useScrapeProduct', () => {
  it('mutation is ready to call', () => {
    const { result } = renderHook(() => useScrapeProduct(), { wrapper: makeWrapper() });
    expect(result.current.mutate).toBeTypeOf('function');
  });

  it('mutates and calls toast on success', async () => {
    const { toast } = await import('sonner');
    const { result } = renderHook(() => useScrapeProduct(), { wrapper: makeWrapper() });

    result.current.mutate(1);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(toast.success).toHaveBeenCalled();
  });
});

import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe('useScrapeJobs', () => {
  it('parses the paginated envelope', async () => {
    const { useScrapeJobs } = await import('../../src/hooks/useScrapeJobs');
    const { result } = renderHook(() => useScrapeJobs(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total).toBe(2);
    expect(result.current.data?.items[0].task_id).toBe('task-abc-123');
  });
});

describe('useProductScrapeJobs', () => {
  it('scopes results to a product', async () => {
    const { useProductScrapeJobs } = await import('../../src/hooks/useScrapeJobs');
    const { result } = renderHook(() => useProductScrapeJobs(2, 1), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items[0].product_id).toBe(2);
    expect(result.current.data?.items[0].status).toBe('failure');
  });
});

describe('useQueueDepth', () => {
  it('parses best-effort queue depth', async () => {
    const { useQueueDepth } = await import('../../src/hooks/useScrapeJobs');
    const { result } = renderHook(() => useQueueDepth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.workers_online).toBe(2);
    expect(result.current.data?.queues).toHaveLength(2);
  });
});

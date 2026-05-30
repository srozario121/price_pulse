import { describe, it, expect } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe('useAlerts', () => {
  it('fetches alerts list', async () => {
    const { useAlerts } = await import('../../src/hooks/useAlerts');
    const { result } = renderHook(() => useAlerts(1), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items.length).toBeGreaterThan(0);
  });
});

describe('useCreateAlert', () => {
  it('mutates to create an alert', async () => {
    const { useCreateAlert } = await import('../../src/hooks/useAlerts');
    const { result } = renderHook(() => useCreateAlert(), { wrapper: makeWrapper() });
    act(() => {
      result.current.mutate({
        product_id: 1,
        threshold_price: 9.99,
        direction: 'below',
        is_active: true,
        channel: 'email',
        webhook_url: null,
        whatsapp_number: null,
      });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe('useUpdateAlert', () => {
  it('mutates to update an alert', async () => {
    const { useUpdateAlert } = await import('../../src/hooks/useAlerts');
    const { result } = renderHook(() => useUpdateAlert(1), { wrapper: makeWrapper() });
    act(() => {
      result.current.mutate({ is_active: false });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe('useDeleteAlert', () => {
  it('mutates to delete an alert', async () => {
    const { useDeleteAlert } = await import('../../src/hooks/useAlerts');
    const { result } = renderHook(() => useDeleteAlert(), { wrapper: makeWrapper() });
    act(() => {
      result.current.mutate(1);
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

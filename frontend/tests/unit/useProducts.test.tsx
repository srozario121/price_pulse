import { describe, it, expect } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe('useProduct', () => {
  it('fetches a single product by id', async () => {
    const { useProduct } = await import('../../src/hooks/useProducts');
    const { result } = renderHook(() => useProduct(1), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe(1);
    expect(result.current.data?.name).toBe('Test Headphones');
  });
});

describe('useCreateProduct', () => {
  it('mutates to create a product', async () => {
    const { useCreateProduct } = await import('../../src/hooks/useProducts');
    const { result } = renderHook(() => useCreateProduct(), { wrapper: makeWrapper() });
    act(() => {
      result.current.mutate({
        name: 'New Product',
        url: 'https://example.com/new',
        source_type: 'generic',
        css_selector: '.price',
      });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.name).toBe('New Product');
  });
});

describe('useUpdateProduct', () => {
  it('mutates to update a product name', async () => {
    const { useUpdateProduct } = await import('../../src/hooks/useProducts');
    const { result } = renderHook(() => useUpdateProduct(1), { wrapper: makeWrapper() });
    act(() => {
      result.current.mutate({ name: 'Updated Name' });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.name).toBe('Updated Name');
  });
});

describe('useDeleteProduct', () => {
  it('mutates to delete a product', async () => {
    const { useDeleteProduct } = await import('../../src/hooks/useProducts');
    const { result } = renderHook(() => useDeleteProduct(), { wrapper: makeWrapper() });
    act(() => {
      result.current.mutate(1);
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

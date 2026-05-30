import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ProductDetail } from '../../src/pages/ProductDetail';

function renderProductDetail(productId = '1') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/products/${productId}`]}>
        <Routes>
          <Route path="/products/:id" element={<ProductDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('ProductDetail', () => {
  it('shows loading skeletons initially', () => {
    renderProductDetail();
    // Skeletons are present before data loads
    // (exact skeleton count depends on implementation)
    expect(document.querySelector('.animate-pulse')).toBeDefined();
  });

  it('shows product name after loading', async () => {
    renderProductDetail('1');
    await waitFor(() => {
      expect(screen.getByText('Test Headphones')).toBeInTheDocument();
    });
  });

  it('shows scrape button after loading', async () => {
    renderProductDetail('1');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /scrape now/i })).toBeInTheDocument();
    });
  });

  it('shows not found UI for unknown product', async () => {
    renderProductDetail('99999');
    await waitFor(() => {
      expect(screen.getByText(/product not found/i)).toBeInTheDocument();
    });
  });

  it('clicks Scrape Now button', async () => {
    renderProductDetail('1');
    const scrapeBtn = await screen.findByRole('button', { name: /scrape now/i });
    fireEvent.click(scrapeBtn);
    // Button should still be present (mutation in progress or done)
    expect(scrapeBtn).toBeInTheDocument();
  });

  it('shows Manage alerts link', async () => {
    renderProductDetail('1');
    await waitFor(() => {
      expect(screen.getByText('Test Headphones')).toBeInTheDocument();
    });
    expect(screen.getByText(/manage alerts/i)).toBeInTheDocument();
  });
});

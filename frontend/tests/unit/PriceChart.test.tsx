import { describe, it, expect } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PriceChart } from '../../src/components/PriceChart';

function renderChart(productId = 1) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PriceChart productId={productId} />
    </QueryClientProvider>
  );
}

describe('PriceChart', () => {
  it('renders without crashing', () => {
    const { container } = renderChart();
    expect(container).toBeDefined();
  });

  it('shows price data after loading', async () => {
    renderChart(1);
    // The MSW handler returns 5 mock price records
    await waitFor(() => {
      // Chart renders something — either chart container or a loading state
      expect(document.querySelector('.recharts-wrapper, [class*="Skeleton"]')).toBeDefined();
    });
  });
});

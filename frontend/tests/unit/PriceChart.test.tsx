import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { PriceChart } from '../../src/components/PriceChart';
import { server } from '../mocks/server';

// These replace two assertions that could never fail:
//   expect(container).toBeDefined()                    — always true
//   expect(document.querySelector(...)).toBeDefined()  — true even for null,
//                                                        since toBeDefined only
//                                                        rejects `undefined`
// The chart shipped permanently blank (it requested limit=200 against an API
// capped at 100, so every request 422'd) with both of them green.

function renderChart(productId = 1) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PriceChart productId={productId} />
    </QueryClientProvider>
  );
}

/** The rendered data series — the thing a user actually looks at. */
function chartLine() {
  return document.querySelector('.recharts-line-curve');
}


describe('PriceChart', () => {
  it('requests a limit the API will accept', async () => {
    // Arrange — capture what the component actually asks for. This is the
    // regression guard: the bug was a request the real API rejects outright.
    let requestedLimit: string | null = null;
    server.use(
      http.get('/api/v1/products/:id/prices', ({ request }) => {
        requestedLimit = new URL(request.url).searchParams.get('limit');
        return HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 });
      })
    );

    // Act
    renderChart();

    // Assert
    await waitFor(() => expect(requestedLimit).not.toBeNull());
    expect(Number(requestedLimit)).toBeLessThanOrEqual(100);
  });

  it('draws a data series when price records exist', async () => {
    // Act
    renderChart();

    // Assert — an actual plotted line, not merely "a container exists"
    await waitFor(() => expect(chartLine()).not.toBeNull());
    expect(screen.queryByText(/No price data available/i)).toBeNull();
  });

  it('renders a visible mark for a single record', async () => {
    // Arrange — one point draws a zero-length line, so with dots suppressed the
    // chart looks empty even though the data arrived. This is the state a user
    // is in immediately after their first scrape.
    server.use(
      http.get('/api/v1/products/:id/prices', () =>
        HttpResponse.json({
          items: [
            {
              id: 1,
              product_id: 1,
              price: '129.0000',
              currency: 'GBP',
              captured_at: '2026-07-28T21:01:43.700223Z',
              raw_html_hash: 'abc',
              extraction_status: 'ok',
            },
          ],
          total: 1,
          limit: 100,
          offset: 0,
        })
      )
    );

    // Act
    renderChart();

    // Assert
    await waitFor(() =>
      expect(document.querySelector('.recharts-line-dot')).not.toBeNull()
    );
  });

  it('shows an error state, not "no data", when the request fails', async () => {
    // Arrange — conflating these is what hid the bug: the chart reported an
    // absence of data that was really a failed request.
    server.use(
      http.get('/api/v1/products/:id/prices', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 422 })
      )
    );

    // Act
    renderChart();

    // Assert
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.getByRole('alert').textContent).toMatch(/could not load/i);
    expect(screen.queryByText(/No price data available/i)).toBeNull();
  });

  it('shows the empty state when there are genuinely no records', async () => {
    // Arrange
    server.use(
      http.get('/api/v1/products/:id/prices', () =>
        HttpResponse.json({ items: [], total: 0, limit: 100, offset: 0 })
      )
    );

    // Act
    renderChart();

    // Assert
    await waitFor(() =>
      expect(screen.getByText(/No price data available/i)).toBeTruthy()
    );
    expect(chartLine()).toBeNull();
  });
});

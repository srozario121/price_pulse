import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from '../../src/App';

function renderApp(initialPath = '/') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('App', () => {
  it('renders without crashing', () => {
    renderApp('/');
    // The nav logo is always present
    expect(screen.getByText('Price Pulse')).toBeInTheDocument();
  });

  it('renders the dashboard at root path', () => {
    renderApp('/');
    expect(screen.getByText('Price Pulse')).toBeInTheDocument();
  });
});

import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Jobs } from '../../src/pages/Jobs';

function renderJobs() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Jobs />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Jobs view', () => {
  it('renders the page heading', () => {
    renderJobs();
    expect(screen.getByRole('heading', { name: /scrape jobs/i })).toBeInTheDocument();
  });

  it('renders scrape job rows with status badges', async () => {
    renderJobs();
    await waitFor(() => {
      expect(screen.getByText('Success')).toBeInTheDocument();
      expect(screen.getByText('Failed')).toBeInTheDocument();
    });
    // Outcome column shows the raw extraction status.
    expect(screen.getByText('blocked')).toBeInTheDocument();
  });

  it('shows best-effort queue depth', async () => {
    renderJobs();
    await waitFor(() => {
      expect(screen.getByText(/2 workers online/i)).toBeInTheDocument();
    });
  });
});

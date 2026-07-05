import { describe, it, expect } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AlertManager } from '../../src/pages/AlertManager';

function renderAlertManager(productId = '1') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/products/${productId}/alerts`]}>
        <Routes>
          <Route path="/products/:id/alerts" element={<AlertManager />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('AlertManager', () => {
  it('renders the page heading', () => {
    renderAlertManager();
    expect(screen.getByRole('heading', { name: /price alerts/i })).toBeInTheDocument();
  });

  it('shows Add alert button', () => {
    renderAlertManager();
    expect(screen.getByRole('button', { name: /add alert/i })).toBeInTheDocument();
  });

  it('shows alerts after loading', async () => {
    renderAlertManager();
    await waitFor(() => {
      expect(screen.getAllByText(/below|above/i).length).toBeGreaterThan(0);
    });
  });

  it('shows back link to product', () => {
    renderAlertManager();
    expect(screen.getByText(/back to product/i)).toBeInTheDocument();
  });

  it('opens create dialog on Add alert click', async () => {
    renderAlertManager();
    const btn = screen.getByRole('button', { name: /add alert/i });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  it('filter buttons are clickable', () => {
    renderAlertManager();
    const allBtn = screen.getByRole('button', { name: /all/i });
    fireEvent.click(allBtn);
    const activeBtn = screen.getByRole('button', { name: /^active$/i });
    fireEvent.click(activeBtn);
    const inactiveBtn = screen.getByRole('button', { name: /inactive/i });
    fireEvent.click(inactiveBtn);
  });

  it('shows alert rows with edit/delete buttons after loading', async () => {
    renderAlertManager();
    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /edit/i }).length).toBeGreaterThan(0);
    });
  });

  it('opens edit dialog for an existing alert', async () => {
    renderAlertManager();
    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /edit/i }).length).toBeGreaterThan(0);
    });
    const editBtns = screen.getAllByRole('button', { name: /edit/i });
    fireEvent.click(editBtns[0]);
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  it('opens delete confirm dialog for an alert', async () => {
    renderAlertManager();
    const deleteBtns = await screen.findAllByRole('button', { name: /^delete$/i });
    fireEvent.click(deleteBtns[0]);
    await waitFor(() => {
      expect(screen.getByText('Delete alert')).toBeInTheDocument();
    });
  });
});

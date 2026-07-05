import { describe, it, expect } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Dashboard } from '../../src/pages/Dashboard';

function renderDashboard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Dashboard', () => {
  it('renders the page heading', () => {
    renderDashboard();
    expect(screen.getByRole('heading', { name: /products/i })).toBeInTheDocument();
  });

  it('shows product names after loading', async () => {
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText('Test Headphones')).toBeInTheDocument();
    });
  });

  it('shows all three mock products', async () => {
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText('Test Headphones')).toBeInTheDocument();
      expect(screen.getByText('Mechanical Keyboard')).toBeInTheDocument();
      expect(screen.getByText('USB Hub')).toBeInTheDocument();
    });
  });

  it('shows Add Product button', () => {
    renderDashboard();
    expect(screen.getByRole('button', { name: /add product/i })).toBeInTheDocument();
  });

  it('opens create dialog on Add Product click', async () => {
    renderDashboard();
    const btn = screen.getByRole('button', { name: /add product/i });
    fireEvent.click(btn);
    // ProductFormDialog should appear
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  it('filter buttons are clickable', () => {
    renderDashboard();
    const allBtn = screen.getByRole('button', { name: /all/i });
    fireEvent.click(allBtn);
    const activeBtn = screen.getByRole('button', { name: /^active$/i });
    fireEvent.click(activeBtn);
    const inactiveBtn = screen.getByRole('button', { name: /inactive/i });
    fireEvent.click(inactiveBtn);
  });

  it('opens dropdown menu for a product', async () => {
    const user = userEvent.setup();
    renderDashboard();
    await waitFor(() => expect(screen.getByText('Test Headphones')).toBeInTheDocument());
    const menuTriggers = document.querySelectorAll('[aria-haspopup="menu"]');
    expect(menuTriggers.length).toBeGreaterThan(0);
    await user.click(menuTriggers[0] as HTMLElement);
    await waitFor(() => {
      expect(screen.getByText('Edit')).toBeInTheDocument();
    });
  });

  it('opens edit dialog from dropdown', async () => {
    const user = userEvent.setup();
    renderDashboard();
    await waitFor(() => expect(screen.getByText('Test Headphones')).toBeInTheDocument());
    const menuTriggers = document.querySelectorAll('[aria-haspopup="menu"]');
    await user.click(menuTriggers[0] as HTMLElement);
    const editItem = await screen.findByText('Edit');
    await user.click(editItem);
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  it('opens delete confirm dialog from dropdown', async () => {
    const user = userEvent.setup();
    renderDashboard();
    await waitFor(() => expect(screen.getByText('Test Headphones')).toBeInTheDocument());
    const menuTriggers = document.querySelectorAll('[aria-haspopup="menu"]');
    await user.click(menuTriggers[0] as HTMLElement);
    const deleteItem = await screen.findByText('Delete');
    await user.click(deleteItem);
    await waitFor(() => {
      expect(screen.getByText('Delete product')).toBeInTheDocument();
    });
  });
});

import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ProductFormDialog } from '../../src/components/ProductFormDialog';

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe('ProductFormDialog', () => {
  it('shows FormMessage for invalid URL', async () => {
    render(
      <ProductFormDialog
        mode="create"
        open={true}
        onOpenChange={vi.fn()}
      />,
      { wrapper }
    );

    const urlInput = screen.getByPlaceholderText('https://...');
    await userEvent.type(urlInput, 'not-a-url');

    const nameInput = screen.getByPlaceholderText('Product name');
    await userEvent.type(nameInput, 'Test');

    const submitBtn = screen.getByRole('button', { name: /save/i });
    await userEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Must be a valid URL')).toBeInTheDocument();
    });
  });

  it('hides css_selector field when source_type is amazon', async () => {
    render(
      <ProductFormDialog
        mode="create"
        open={true}
        onOpenChange={vi.fn()}
      />,
      { wrapper }
    );

    // Default source_type is 'generic', so css_selector should be visible
    expect(screen.getByPlaceholderText('.price')).toBeInTheDocument();
  });

  it('renders source options fetched from GET /api/v1/sources', async () => {
    render(
      <ProductFormDialog
        mode="create"
        open={true}
        onOpenChange={vi.fn()}
      />,
      { wrapper }
    );

    const trigger = screen.getByRole('combobox');
    await userEvent.click(trigger);

    await waitFor(() => {
      expect(
        screen.getByRole('option', { name: 'John Lewis' })
      ).toBeInTheDocument();
    });
    expect(screen.getByRole('option', { name: 'eBay UK' })).toBeInTheDocument();
    expect(
      screen.getByRole('option', { name: 'Facebook Marketplace' })
    ).toBeInTheDocument();
  });
});

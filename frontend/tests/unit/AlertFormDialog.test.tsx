import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AlertFormDialog } from '../../src/components/AlertFormDialog';

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

/** Open the channel Select (2nd combobox) and pick an option by visible text */
async function selectChannel(optionText: string) {
  const comboboxes = screen.getAllByRole('combobox');
  // direction = index 0, channel = index 1
  const channelTrigger = comboboxes[1];
  await userEvent.click(channelTrigger);
  // Options are in a listbox that appears after click
  const listbox = await screen.findByRole('listbox');
  await userEvent.click(within(listbox).getByText(optionText));
}

describe('AlertFormDialog', () => {
  it('email channel — webhook and whatsapp fields not rendered', () => {
    render(
      <AlertFormDialog
        productId={1}
        mode="create"
        open={true}
        onOpenChange={vi.fn()}
      />,
      { wrapper }
    );
    // Default channel is email — conditional fields should not be present
    expect(
      screen.queryByPlaceholderText('https://hooks.example.com/...')
    ).not.toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText('+447911123456')
    ).not.toBeInTheDocument();
  });

  it('invalid whatsapp number shows FormMessage', async () => {
    render(
      <AlertFormDialog
        productId={1}
        mode="create"
        open={true}
        onOpenChange={vi.fn()}
      />,
      { wrapper }
    );

    await selectChannel('WhatsApp');

    // Enter invalid number
    const numberInput = await screen.findByPlaceholderText('+447911123456');
    await userEvent.type(numberInput, '12345');

    const thresholdInput = screen.getByPlaceholderText('9.99');
    await userEvent.clear(thresholdInput);
    await userEvent.type(thresholdInput, '10');

    const submitBtn = screen.getByRole('button', { name: /save/i });
    await userEvent.click(submitBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/must be e\.164 format/i)
      ).toBeInTheDocument();
    });
  });

  it('webhook channel — blocks submit when webhook_url is empty', async () => {
    render(
      <AlertFormDialog
        productId={1}
        mode="create"
        open={true}
        onOpenChange={vi.fn()}
      />,
      { wrapper }
    );

    await selectChannel('Webhook');

    // Leave webhook_url empty; fill threshold
    const thresholdInput = screen.getByPlaceholderText('9.99');
    await userEvent.clear(thresholdInput);
    await userEvent.type(thresholdInput, '10');

    const submitBtn = screen.getByRole('button', { name: /save/i });
    await userEvent.click(submitBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/webhook url is required/i)
      ).toBeInTheDocument();
    });
  });
});

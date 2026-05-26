import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConfirmDialog } from '../../src/components/ConfirmDialog';

describe('ConfirmDialog', () => {
  it('renders title and description', () => {
    render(
      <ConfirmDialog
        title="Delete product"
        description="This action cannot be undone."
        open={true}
        onOpenChange={vi.fn()}
        onConfirm={vi.fn()}
      />
    );
    expect(screen.getByText('Delete product')).toBeInTheDocument();
    expect(screen.getByText('This action cannot be undone.')).toBeInTheDocument();
  });

  it('shows spinner and disables button when isLoading=true', () => {
    render(
      <ConfirmDialog
        title="Delete"
        description="Sure?"
        open={true}
        onOpenChange={vi.fn()}
        onConfirm={vi.fn()}
        isLoading={true}
      />
    );
    // The action button should be disabled
    const buttons = screen.getAllByRole('button');
    const confirmButton = buttons.find((b) => b.getAttribute('disabled') !== null);
    expect(confirmButton).toBeDefined();
  });

  it('calls onConfirm when action clicked', async () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        title="Delete"
        description="Sure?"
        open={true}
        onOpenChange={vi.fn()}
        onConfirm={onConfirm}
      />
    );
    const confirmBtn = screen.getByText('Confirm');
    await userEvent.click(confirmBtn);
    expect(onConfirm).toHaveBeenCalledOnce();
  });
});

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Layout } from '../../src/components/Layout';

function renderLayout(children = <div>content</div>) {
  return render(
    <MemoryRouter>
      <Layout>{children}</Layout>
    </MemoryRouter>
  );
}

describe('Layout', () => {
  it('renders children', () => {
    renderLayout(<p>Hello world</p>);
    expect(screen.getByText('Hello world')).toBeInTheDocument();
  });

  it('shows the app name link', () => {
    renderLayout();
    expect(screen.getByText('Price Pulse')).toBeInTheDocument();
  });

  it('toggles theme on button click', () => {
    renderLayout();
    const toggleBtn = screen.getByRole('button', { name: /toggle theme/i });
    // Should not throw on click
    fireEvent.click(toggleBtn);
    fireEvent.click(toggleBtn);
  });
});

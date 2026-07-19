import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ScrapeJobStatusBadge } from '../../src/components/ScrapeJobStatusBadge';
import type { ScrapeJobStatus } from '../../src/api/types';

describe('ScrapeJobStatusBadge', () => {
  const cases: [ScrapeJobStatus, string][] = [
    ['queued', 'Queued'],
    ['started', 'Running'],
    ['success', 'Success'],
    ['failure', 'Failed'],
  ];

  it.each(cases)('renders %s as "%s"', (status, label) => {
    render(<ScrapeJobStatusBadge status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});

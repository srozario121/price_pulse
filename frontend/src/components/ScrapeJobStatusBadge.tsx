import { Badge } from '@/components/ui/badge';
import type { ScrapeJobStatus } from '@/api/types';

const STATUS_VARIANT: Record<
  ScrapeJobStatus,
  'default' | 'secondary' | 'success' | 'warning' | 'destructive'
> = {
  queued: 'secondary',
  started: 'warning',
  success: 'success',
  failure: 'destructive',
};

const STATUS_LABEL: Record<ScrapeJobStatus, string> = {
  queued: 'Queued',
  started: 'Running',
  success: 'Success',
  failure: 'Failed',
};

export function ScrapeJobStatusBadge({
  status,
  className,
}: {
  status: ScrapeJobStatus;
  className?: string;
}) {
  return (
    <Badge variant={STATUS_VARIANT[status]} className={className}>
      {STATUS_LABEL[status]}
    </Badge>
  );
}

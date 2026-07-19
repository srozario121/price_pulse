import { Link } from 'react-router-dom';
import { useScrapeJobs, useQueueDepth } from '@/hooks/useScrapeJobs';
import { ScrapeJobStatusBadge } from '@/components/ScrapeJobStatusBadge';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardContent } from '@/components/ui/card';

function formatTime(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

export function Jobs() {
  const { data, isLoading } = useScrapeJobs({}, { limit: 50 });
  const { data: depth } = useQueueDepth();

  const jobs = data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Scrape jobs</h1>
        {depth && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            {depth.queues.map((q) => (
              <Badge key={q.queue} variant="outline" className="text-xs">
                {q.queue}: {q.messages ?? '?'}
              </Badge>
            ))}
            <span className="hidden sm:inline">
              {depth.workers_online ?? '?'} worker
              {depth.workers_online === 1 ? '' : 's'} online
            </span>
          </div>
        )}
      </div>

      {isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      )}

      {!isLoading && jobs.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <p>No scrape jobs yet.</p>
          </CardContent>
        </Card>
      )}

      {!isLoading && jobs.length > 0 && (
        <div className="border rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-muted-foreground">
              <tr>
                <th className="p-3 font-medium">Status</th>
                <th className="p-3 font-medium">Product</th>
                <th className="p-3 font-medium">Trigger</th>
                <th className="p-3 font-medium">Queue</th>
                <th className="p-3 font-medium">Outcome</th>
                <th className="p-3 font-medium">Retries</th>
                <th className="p-3 font-medium">Enqueued</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {jobs.map((job) => (
                <tr key={job.id} className="hover:bg-muted/30">
                  <td className="p-3">
                    <ScrapeJobStatusBadge status={job.status} />
                  </td>
                  <td className="p-3">
                    <Link
                      to={`/products/${job.product_id}`}
                      className="hover:underline"
                    >
                      #{job.product_id}
                    </Link>
                  </td>
                  <td className="p-3 capitalize">
                    {job.trigger.replace('_', ' ')}
                  </td>
                  <td className="p-3">{job.queue}</td>
                  <td className="p-3 text-muted-foreground">
                    {job.extraction_status ?? job.detail ?? '—'}
                  </td>
                  <td className="p-3">{job.retries}</td>
                  <td className="p-3 text-muted-foreground whitespace-nowrap">
                    {formatTime(job.enqueued_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

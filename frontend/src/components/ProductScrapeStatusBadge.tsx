import { useProductScrapeJobs } from '@/hooks/useScrapeJobs';
import { ScrapeJobStatusBadge } from '@/components/ScrapeJobStatusBadge';

/** Latest scrape-job status for a product, shown on the Dashboard rows.
 *  Renders nothing until at least one job exists (keeps rows quiet for new products). */
export function ProductScrapeStatusBadge({ productId }: { productId: number }) {
  const { data } = useProductScrapeJobs(productId, 1);
  const latest = data?.items?.[0];
  if (!latest) return null;
  return <ScrapeJobStatusBadge status={latest.status} className="text-xs" />;
}

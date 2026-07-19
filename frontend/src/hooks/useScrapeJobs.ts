import { useQuery } from '@tanstack/react-query';
import { scrapeJobsApi } from '@/api/client';
import type { ScrapeJobStatus } from '@/api/types';

/** Recent scrape jobs, newest first. Polls so in-flight jobs update live. */
export function useScrapeJobs(
  filter: { productId?: number; status?: ScrapeJobStatus; queue?: string } = {},
  params: { limit?: number } = {}
) {
  return useQuery({
    queryKey: ['scrapeJobs', filter, params],
    queryFn: () =>
      scrapeJobsApi.list({
        product_id: filter.productId,
        status: filter.status,
        queue: filter.queue,
        limit: params.limit ?? 20,
      }),
    refetchInterval: 15_000,
  });
}

/** Scrape jobs scoped to a single product (used for the Dashboard status badge). */
export function useProductScrapeJobs(productId: number, limit = 1) {
  return useQuery({
    queryKey: ['scrapeJobs', 'product', productId, limit],
    queryFn: () => scrapeJobsApi.listForProduct(productId, { limit }),
    enabled: !!productId,
    refetchInterval: 15_000,
  });
}

/** Best-effort broker queue depth; degrades to null values when unavailable. */
export function useQueueDepth() {
  return useQuery({
    queryKey: ['scrapeJobs', 'queueDepth'],
    queryFn: () => scrapeJobsApi.queueDepth(),
    refetchInterval: 15_000,
  });
}

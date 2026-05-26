import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { productsApi } from '@/api/client';

export function useScrapeProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (productId: number) => productsApi.scrape(productId),
    onSuccess: (_data, productId) => {
      toast.success('Scrape job queued — price will update shortly');
      qc.invalidateQueries({ queryKey: ['prices', productId] });
    },
    onError: (err: { detail?: string }) => {
      toast.error(err.detail ?? 'Scrape failed');
    },
  });
}

import { useQuery } from '@tanstack/react-query';
import { pricesApi } from '@/api/client';

export function usePrices(
  productId: number,
  params: { limit?: number; fromDt?: string; toDt?: string } = {}
) {
  return useQuery({
    queryKey: ['prices', productId, params],
    queryFn: () =>
      pricesApi.list(productId, {
        limit: params.limit,
        from_dt: params.fromDt,
        to_dt: params.toDt,
      }),
    enabled: !!productId,
    refetchInterval: 60_000,
  });
}

import { useQuery } from '@tanstack/react-query';
import { sourcesApi } from '@/api/client';

export function useSources() {
  return useQuery({
    queryKey: ['sources'],
    queryFn: () => sourcesApi.list(),
    staleTime: 60 * 60 * 1000,
  });
}

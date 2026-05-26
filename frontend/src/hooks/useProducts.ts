import {
  useInfiniteQuery,
  useQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';
import { productsApi } from '@/api/client';
import type { ProductCreate, ProductUpdate } from '@/api/types';

export function useInfiniteProducts(filter: { isActive?: boolean }) {
  return useInfiniteQuery({
    queryKey: ['products', filter],
    queryFn: ({ pageParam }) =>
      productsApi.list({
        is_active: filter.isActive,
        limit: 20,
        offset: pageParam as number,
      }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, _allPages, lastPageParam) => {
      const nextOffset = (lastPageParam as number) + 20;
      return lastPage.total > nextOffset ? nextOffset : undefined;
    },
  });
}

export function useProduct(id: number) {
  return useQuery({
    queryKey: ['product', id],
    queryFn: () => productsApi.get(id),
    enabled: !!id,
  });
}

export function useCreateProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ProductCreate) => productsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['products'] }),
  });
}

export function useUpdateProduct(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ProductUpdate) => productsApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['products'] });
      qc.invalidateQueries({ queryKey: ['product', id] });
    },
  });
}

export function useDeleteProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => productsApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['products'] }),
  });
}

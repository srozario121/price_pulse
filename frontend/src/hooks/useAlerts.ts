import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { alertsApi } from '@/api/client';
import type { AlertCreate, AlertUpdate } from '@/api/types';

export function useAlerts(productId: number, filter?: { isActive?: boolean }) {
  return useQuery({
    queryKey: ['alerts', productId, filter],
    queryFn: () =>
      alertsApi.list({ product_id: productId, is_active: filter?.isActive }),
    enabled: !!productId,
  });
}

export function useCreateAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: AlertCreate) => alertsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });
}

export function useUpdateAlert(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: AlertUpdate) => alertsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });
}

export function useDeleteAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => alertsApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });
}

import axios, { type AxiosInstance } from 'axios';
import type {
  ProductRead,
  ProductCreate,
  ProductUpdate,
  PriceRecordRead,
  AlertRead,
  AlertCreate,
  AlertUpdate,
  PaginatedResponse,
  ScrapeJobResponse,
} from './types';

const instance: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '',
});

instance.interceptors.response.use(
  (res) => res,
  (error) => {
    const detail: string =
      error.response?.data?.detail ?? error.message ?? 'Unknown error';
    return Promise.reject({ detail });
  }
);

export const productsApi = {
  list: (params?: {
    is_active?: boolean;
    limit?: number;
    offset?: number;
  }) =>
    instance
      .get<PaginatedResponse<ProductRead>>('/api/v1/products', { params })
      .then((r) => r.data),

  get: (id: number) =>
    instance.get<ProductRead>(`/api/v1/products/${id}`).then((r) => r.data),

  create: (data: ProductCreate) =>
    instance.post<ProductRead>('/api/v1/products', data).then((r) => r.data),

  update: (id: number, data: ProductUpdate) =>
    instance.patch<ProductRead>(`/api/v1/products/${id}`, data).then((r) => r.data),

  remove: (id: number) =>
    instance.delete(`/api/v1/products/${id}`).then((r) => r.data),

  scrape: (id: number) =>
    instance
      .post<ScrapeJobResponse>(`/api/v1/products/${id}/scrape`)
      .then((r) => r.data),
};

export const pricesApi = {
  list: (
    productId: number,
    params?: { limit?: number; offset?: number; from_dt?: string; to_dt?: string }
  ) =>
    instance
      .get<PaginatedResponse<PriceRecordRead>>(
        `/api/v1/products/${productId}/prices`,
        { params }
      )
      .then((r) => r.data),
};

export const alertsApi = {
  list: (params?: {
    product_id?: number;
    is_active?: boolean;
    limit?: number;
    offset?: number;
  }) =>
    instance
      .get<PaginatedResponse<AlertRead>>('/api/v1/alerts', { params })
      .then((r) => r.data),

  get: (id: number) =>
    instance.get<AlertRead>(`/api/v1/alerts/${id}`).then((r) => r.data),

  create: (data: AlertCreate) =>
    instance.post<AlertRead>('/api/v1/alerts', data).then((r) => r.data),

  update: (id: number, data: AlertUpdate) =>
    instance.patch<AlertRead>(`/api/v1/alerts/${id}`, data).then((r) => r.data),

  remove: (id: number) =>
    instance.delete(`/api/v1/alerts/${id}`).then((r) => r.data),
};

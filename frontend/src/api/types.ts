// Run make generate-types to replace with generated types after item 6 is complete

// source_type is now registry-driven (validated server-side); no longer a fixed union.
export type SourceType = string;
export type AlertDirection = 'above' | 'below';
export type NotificationChannel = 'email' | 'webhook' | 'whatsapp';
export type ExtractionStatus = 'ok' | 'extraction_failed' | 'http_error';

export interface SourcePreset {
  key: string;
  label: string;
  queue: string;
}

export interface ProductRead {
  id: number;
  name: string;
  url: string;
  source_type: SourceType;
  css_selector: string | null;
  css_selector_currency: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProductCreate {
  name: string;
  url: string;
  source_type: SourceType;
  css_selector?: string | null;
  css_selector_currency?: string | null;
  is_active?: boolean;
}

export interface ProductUpdate {
  name?: string;
  url?: string;
  source_type?: SourceType;
  css_selector?: string | null;
  css_selector_currency?: string | null;
  is_active?: boolean;
}

export interface PriceRecordRead {
  id: number;
  product_id: number;
  price: string | null;
  currency: string | null;
  captured_at: string;
  raw_html_hash: string | null;
  extraction_status: ExtractionStatus;
}

export interface AlertRead {
  id: number;
  product_id: number;
  threshold_price: string;
  direction: AlertDirection;
  is_active: boolean;
  notified_at: string | null;
  channel: NotificationChannel;
  webhook_url: string | null;
  whatsapp_number: string | null;
}

export interface AlertCreate {
  product_id: number;
  threshold_price: number;
  direction: AlertDirection;
  is_active?: boolean;
  channel: NotificationChannel;
  webhook_url?: string | null;
  whatsapp_number?: string | null;
}

export interface AlertUpdate {
  threshold_price?: number;
  direction?: AlertDirection;
  is_active?: boolean;
  channel?: NotificationChannel;
  webhook_url?: string | null;
  whatsapp_number?: string | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ScrapeJobResponse {
  task_id: string;
  status: 'queued';
  product: ProductRead;
}

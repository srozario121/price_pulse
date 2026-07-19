import { http, HttpResponse } from 'msw';
import type {
  ProductRead,
  PriceRecordRead,
  AlertRead,
  PaginatedResponse,
  ScrapeJobResponse,
  ScrapeJobRead,
  QueueDepthResponse,
  SourcePreset,
} from '../../src/api/types';

const mockProduct: ProductRead = {
  id: 1,
  name: 'Test Headphones',
  url: 'https://example.com/headphones',
  source_type: 'generic',
  css_selector: '.price',
  css_selector_currency: null,
  is_active: true,
  created_at: '2026-05-01T10:00:00Z',
  updated_at: '2026-05-01T10:00:00Z',
};

const mockProduct2: ProductRead = {
  id: 2,
  name: 'Mechanical Keyboard',
  url: 'https://example.com/keyboard',
  source_type: 'amazon',
  css_selector: null,
  css_selector_currency: null,
  is_active: true,
  created_at: '2026-05-02T10:00:00Z',
  updated_at: '2026-05-02T10:00:00Z',
};

const mockProduct3: ProductRead = {
  id: 3,
  name: 'USB Hub',
  url: 'https://example.com/hub',
  source_type: 'generic',
  css_selector: '.price',
  css_selector_currency: null,
  is_active: false,
  created_at: '2026-05-03T10:00:00Z',
  updated_at: '2026-05-03T10:00:00Z',
};

const mockSources: SourcePreset[] = [
  { key: 'generic', label: 'Generic (CSS selector)', queue: 'default' },
  { key: 'amazon', label: 'Amazon', queue: 'playwright' },
  { key: 'ebay', label: 'eBay UK', queue: 'default' },
  { key: 'currys', label: 'Currys', queue: 'playwright' },
  { key: 'john_lewis', label: 'John Lewis', queue: 'playwright' },
  {
    key: 'facebook_marketplace',
    label: 'Facebook Marketplace',
    queue: 'playwright',
  },
];

const mockPrices: PriceRecordRead[] = Array.from({ length: 5 }, (_, i) => ({
  id: i + 1,
  product_id: 1,
  price: String(9.99 + i * 0.5),
  currency: 'GBP',
  captured_at: new Date(Date.now() - i * 3600 * 1000).toISOString(),
  raw_html_hash: `hash${i}`,
  extraction_status: 'ok' as const,
}));

const mockAlert: AlertRead = {
  id: 1,
  product_id: 1,
  threshold_price: '8.99',
  direction: 'below',
  is_active: true,
  notified_at: null,
  channel: 'email',
  webhook_url: null,
  whatsapp_number: null,
};

const mockAlert2: AlertRead = {
  id: 2,
  product_id: 1,
  threshold_price: '15.00',
  direction: 'above',
  is_active: true,
  notified_at: null,
  channel: 'webhook',
  webhook_url: 'https://hooks.example.com/notify',
  whatsapp_number: null,
};

const mockScrapeJobs: ScrapeJobRead[] = [
  {
    id: 1,
    product_id: 1,
    task_id: 'task-abc-123',
    queue: 'default',
    trigger: 'on_demand',
    status: 'success',
    extraction_status: 'ok',
    detail: null,
    retries: 0,
    enqueued_at: '2026-07-19T10:00:00Z',
    started_at: '2026-07-19T10:00:01Z',
    finished_at: '2026-07-19T10:00:03Z',
  },
  {
    id: 2,
    product_id: 2,
    task_id: 'task-def-456',
    queue: 'playwright',
    trigger: 'scheduled',
    status: 'failure',
    extraction_status: 'blocked',
    detail: null,
    retries: 2,
    enqueued_at: '2026-07-19T09:30:00Z',
    started_at: '2026-07-19T09:30:01Z',
    finished_at: '2026-07-19T09:30:05Z',
  },
];

export const handlers = [
  // Scrape jobs
  http.get('/api/v1/scrape-jobs/queue-depth', () => {
    const response: QueueDepthResponse = {
      queues: [
        { queue: 'default', messages: 0 },
        { queue: 'playwright', messages: 1 },
      ],
      workers_online: 2,
    };
    return HttpResponse.json(response);
  }),

  http.get('/api/v1/scrape-jobs', ({ request }) => {
    const url = new URL(request.url);
    const productId = url.searchParams.get('product_id');
    const items = productId
      ? mockScrapeJobs.filter((j) => j.product_id === Number(productId))
      : mockScrapeJobs;
    const response: PaginatedResponse<ScrapeJobRead> = {
      items,
      total: items.length,
      limit: Number(url.searchParams.get('limit') ?? 20),
      offset: 0,
    };
    return HttpResponse.json(response);
  }),

  http.get('/api/v1/products/:id/scrape-jobs', ({ params }) => {
    const id = Number(params.id);
    const items = mockScrapeJobs.filter((j) => j.product_id === id);
    const response: PaginatedResponse<ScrapeJobRead> = {
      items,
      total: items.length,
      limit: 20,
      offset: 0,
    };
    return HttpResponse.json(response);
  }),

  // Sources
  http.get('/api/v1/sources', () => {
    return HttpResponse.json(mockSources);
  }),

  // Products
  http.get('/api/v1/products', () => {
    const response: PaginatedResponse<ProductRead> = {
      items: [mockProduct, mockProduct2, mockProduct3],
      total: 3,
      limit: 20,
      offset: 0,
    };
    return HttpResponse.json(response);
  }),

  http.post('/api/v1/products', async ({ request }) => {
    const body = (await request.json()) as Partial<ProductRead>;
    const newProduct: ProductRead = {
      ...mockProduct,
      id: 99,
      name: body.name ?? 'New Product',
      url: body.url ?? 'https://example.com/new',
    };
    return HttpResponse.json(newProduct, { status: 201 });
  }),

  http.get('/api/v1/products/:id', ({ params }) => {
    const id = Number(params.id);
    if (id === 1) return HttpResponse.json(mockProduct);
    if (id === 2) return HttpResponse.json(mockProduct2);
    if (id === 3) return HttpResponse.json(mockProduct3);
    return HttpResponse.json({ detail: 'Not found' }, { status: 404 });
  }),

  http.patch('/api/v1/products/:id', async ({ params, request }) => {
    const id = Number(params.id);
    const body = (await request.json()) as Partial<ProductRead>;
    if (id === 1) return HttpResponse.json({ ...mockProduct, ...body });
    return HttpResponse.json({ detail: 'Not found' }, { status: 404 });
  }),

  http.delete('/api/v1/products/:id', ({ params }) => {
    const id = Number(params.id);
    if (id === 1 || id === 2 || id === 3) {
      return new HttpResponse(null, { status: 204 });
    }
    return HttpResponse.json({ detail: 'Not found' }, { status: 404 });
  }),

  // Prices
  http.get('/api/v1/products/:id/prices', () => {
    const response: PaginatedResponse<PriceRecordRead> = {
      items: mockPrices,
      total: mockPrices.length,
      limit: 200,
      offset: 0,
    };
    return HttpResponse.json(response);
  }),

  // Scrape
  http.post('/api/v1/products/:id/scrape', () => {
    const response: ScrapeJobResponse = {
      task_id: 'task-abc-123',
      status: 'queued',
      product: mockProduct,
    };
    return HttpResponse.json(response, { status: 202 });
  }),

  // Alerts
  http.get('/api/v1/alerts', () => {
    const response: PaginatedResponse<AlertRead> = {
      items: [mockAlert, mockAlert2],
      total: 2,
      limit: 100,
      offset: 0,
    };
    return HttpResponse.json(response);
  }),

  http.post('/api/v1/alerts', async ({ request }) => {
    const body = (await request.json()) as Partial<AlertRead>;
    const newAlert: AlertRead = {
      ...mockAlert,
      id: 99,
      threshold_price: String(body.threshold_price ?? 9.99),
    };
    return HttpResponse.json(newAlert, { status: 201 });
  }),

  http.patch('/api/v1/alerts/:id', async ({ params, request }) => {
    const id = Number(params.id);
    const body = (await request.json()) as Partial<AlertRead>;
    if (id === 1) return HttpResponse.json({ ...mockAlert, ...body });
    if (id === 2) return HttpResponse.json({ ...mockAlert2, ...body });
    return HttpResponse.json({ detail: 'Not found' }, { status: 404 });
  }),

  http.delete('/api/v1/alerts/:id', () => {
    return new HttpResponse(null, { status: 204 });
  }),
];

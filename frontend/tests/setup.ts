import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { server } from './mocks/server';

// Polyfill window.matchMedia (used by Layout theme logic)
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Polyfill IntersectionObserver (used by react-intersection-observer / Dashboard)
const IntersectionObserverMock = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));
Object.defineProperty(window, 'IntersectionObserver', {
  writable: true,
  value: IntersectionObserverMock,
});

// Polyfill Pointer Events API for Radix UI in jsdom
Object.defineProperty(window.HTMLElement.prototype, 'hasPointerCapture', {
  value: vi.fn(() => false),
  writable: true,
});
Object.defineProperty(window.HTMLElement.prototype, 'setPointerCapture', {
  value: vi.fn(),
  writable: true,
});
Object.defineProperty(window.HTMLElement.prototype, 'releasePointerCapture', {
  value: vi.fn(),
  writable: true,
});
// Radix UI also calls scrollIntoView
Object.defineProperty(window.HTMLElement.prototype, 'scrollIntoView', {
  value: vi.fn(),
  writable: true,
});

// Give jsdom elements a non-zero size, and a ResizeObserver to report it.
//
// Recharts' <ResponsiveContainer> renders nothing at all when it measures zero,
// which jsdom always reports — so a chart test could only ever assert that a
// wrapper element exists, never that a series was actually drawn. That is
// precisely the blind spot that let PriceChart ship permanently blank.
const RESIZE_BOX = { width: 800, height: 300 };

class ResizeObserverMock {
  constructor(private readonly callback: ResizeObserverCallback) {}
  observe(target: Element) {
    this.callback(
      [{ target, contentRect: { ...RESIZE_BOX, top: 0, left: 0, bottom: 300, right: 800, x: 0, y: 0 } } as unknown as ResizeObserverEntry],
      this as unknown as ResizeObserver
    );
  }
  unobserve() {}
  disconnect() {}
}
Object.defineProperty(window, 'ResizeObserver', {
  writable: true,
  value: ResizeObserverMock,
});

for (const [prop, value] of [
  ['offsetWidth', RESIZE_BOX.width],
  ['offsetHeight', RESIZE_BOX.height],
  ['clientWidth', RESIZE_BOX.width],
  ['clientHeight', RESIZE_BOX.height],
] as const) {
  Object.defineProperty(window.HTMLElement.prototype, prop, {
    configurable: true,
    value,
  });
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

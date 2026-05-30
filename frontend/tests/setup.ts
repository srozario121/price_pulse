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

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

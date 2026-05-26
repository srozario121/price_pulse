import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { server } from './mocks/server';

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

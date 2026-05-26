/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    exclude: ['**/node_modules/**', '**/dist/**', 'tests/e2e/**'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      thresholds: {
        global: { branches: 80, functions: 80, lines: 80, statements: 80 },
      },
      exclude: ['node_modules/', 'tests/', 'src/main.tsx', '**/*.d.ts', '**/*.config.*'],
    },
  },
});

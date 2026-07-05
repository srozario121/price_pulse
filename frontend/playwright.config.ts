import { defineConfig, devices } from '@playwright/test';
import { defineBddConfig } from 'playwright-bdd';

// Generate Playwright test files from the canonical Gherkin catalogue in
// docs/behaviour/. Step definitions live under tests/e2e/steps/.
const testDir = defineBddConfig({
  features: '../docs/behaviour/ui_journeys.feature',
  steps: 'tests/e2e/steps/*.steps.ts',
});

export default defineConfig({
  testDir,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['html', { open: 'never' }]],
  use: {
    // Defaults to the composed nginx stack (Item 13 e2e overlay), overridable in CI.
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});

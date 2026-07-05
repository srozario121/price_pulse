import { expect } from '@playwright/test';
import { createBdd } from 'playwright-bdd';

// Step definitions for docs/behaviour/ui_journeys.feature, run via playwright-bdd
// against the composed nginx stack (E2E_BASE_URL, default http://localhost).
const { Given, Then } = createBdd();

Given('I open the dashboard', async ({ page }) => {
  await page.goto('/');
});

Given('I open the alerts page for product 1', async ({ page }) => {
  await page.goto('/products/1/alerts');
});

Then(/^I see the "(.+)" heading$/, async ({ page }, text: string) => {
  await expect(page.getByText(text).first()).toBeVisible();
});

Then(/^I see an "(.+)" control$/, async ({ page }, text: string) => {
  await expect(page.getByText(text).first()).toBeVisible();
});

Then('I see the products area', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Products' })).toBeVisible();
});

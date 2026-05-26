import { test, expect } from '@playwright/test';

test.describe('Price Pulse smoke tests', () => {
  test('dashboard loads and shows navigation', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('Price Pulse')).toBeVisible();
  });

  test('navigate to product detail', async ({ page }) => {
    await page.goto('/');
    // Wait for products to load then click first product link
    const firstProductLink = page.getByRole('link').first();
    await firstProductLink.waitFor({ state: 'visible', timeout: 10000 });
    await firstProductLink.click();
    // Should be on a product detail page
    await expect(page).toHaveURL(/\/products\/\d+/);
  });

  test('navigate to alert manager', async ({ page }) => {
    await page.goto('/products/1/alerts');
    await expect(page.getByText('Price Alerts')).toBeVisible();
    await expect(page.getByText('Add alert')).toBeVisible();
  });
});

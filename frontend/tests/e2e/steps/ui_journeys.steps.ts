import { expect } from '@playwright/test';
import { createBdd } from 'playwright-bdd';

// Step definitions for docs/behaviour/ui_journeys.feature, run via playwright-bdd
// against the composed nginx stack (E2E_BASE_URL, default http://localhost).
const { Given, When, Then } = createBdd();

// Reached from the browser; nginx proxies /api to the backend, so the same origin
// serves both the SPA and the API.
const API = '/api/v1';

/** Per-scenario state, keyed so parallel scenarios cannot collide. */
const scenarioProductId = new Map<string, number>();

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

// ── Price chart (PP-E2E-046) ─────────────────────────────────────────────────

Given(
  'a product that has been scraped and has a recorded price',
  async ({ page, $testInfo }) => {
    // Seed through the real API, pointed at the deterministic fixture server, so
    // the scrape produces a genuine PriceRecord rather than a fabricated row.
    const slug = `chart-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
    const create = await page.request.post(`${API}/products`, {
      data: {
        name: `E2E chart ${slug}`,
        url: `http://fixture-server:9000/fixtures/${slug}`,
        source_type: 'generic',
        css_selector: '.price',
      },
    });
    expect(create.ok(), `create product: ${await create.text()}`).toBeTruthy();
    const productId = (await create.json()).id as number;

    // The fixture server creates the slug on first price write.
    const seed = await page.request.put(
      `http://localhost:9000/fixtures/${slug}/price`,
      { data: { price: '199.99' } }
    );
    expect(seed.ok(), `seed fixture price: ${await seed.text()}`).toBeTruthy();

    // Synchronous scrape hook: returns only once the PriceRecord is persisted,
    // so there is nothing to poll for.
    const scrape = await page.request.post(
      `${API}/_test/products/${productId}/scrape-sync`
    );
    expect(scrape.ok(), `scrape-sync: ${await scrape.text()}`).toBeTruthy();

    // Assert the precondition rather than assuming it — otherwise a scrape
    // regression would surface as a confusing chart failure.
    const prices = await page.request.get(
      `${API}/products/${productId}/prices?limit=10`
    );
    expect(prices.ok()).toBeTruthy();
    const body = await prices.json();
    expect(
      body.items.length,
      'expected the scrape to record a price'
    ).toBeGreaterThan(0);

    scenarioProductId.set($testInfo.testId, productId);
  }
);

When("I open that product's detail page", async ({ page, $testInfo }) => {
  const productId = scenarioProductId.get($testInfo.testId);
  await page.goto(`/products/${productId}`);
});

Then('the price chart plots at least one point', async ({ page }) => {
  // The rendered series itself — a wrapper element proves nothing, which is how
  // the blank chart passed its unit tests for so long. Recharts draws the line
  // path and, for a short series, dots.
  const drawn = page.locator('.recharts-line-curve, .recharts-line-dot').first();
  await expect(drawn).toBeAttached({ timeout: 15_000 });
});

Then('the chart does not report an error or missing data', async ({ page }) => {
  await expect(page.getByText(/No price data available/i)).toHaveCount(0);
  await expect(page.getByText(/Could not load price history/i)).toHaveCount(0);
});

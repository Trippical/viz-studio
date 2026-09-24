import { expect, test, type Page } from '@playwright/test';

const RENDERERS = ['vega-lite', 'plotly', 'echarts'] as const;
const ORIGIN = 'http://127.0.0.1:8000/';

function watch(page: Page) {
  const consoleErrors: string[] = [];
  const foreign: string[] = [];
  const failed: string[] = [];
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text());
  });
  page.on('pageerror', (e) => consoleErrors.push(String(e)));
  page.on('request', (r) => {
    if (!r.url().startsWith(ORIGIN)) foreign.push(r.url());
  });
  page.on('requestfailed', (r) => failed.push(`${r.url()} ${r.failure()?.errorText ?? ''}`));
  return { consoleErrors, foreign, failed };
}

for (const renderer of RENDERERS) {
  test(`bake-off dashboard renders with ${renderer} and the Region control filters it`, async ({ page }) => {
    const log = watch(page);
    await page.goto(`/d/bakeoff/${renderer}`);

    await expect(page.locator('[data-tile]')).toHaveCount(4);
    await expect(page.locator('[data-tile][data-state="ready"]')).toHaveCount(4, { timeout: 90_000 });
    await expect(page.locator('.error-card')).toHaveCount(0);

    const timeSeries = page.locator(`[data-tile="bakeoff/${renderer}/time-series"]`);
    const before = Number(await timeSeries.getAttribute('data-rows'));
    expect(before).toBeGreaterThan(0);
    const largeBefore = Number(await page.locator(`[data-tile="bakeoff/${renderer}/order-lines"]`).getAttribute('data-rows'));
    expect(largeBefore).toBeGreaterThan(0);

    await page.getByLabel('Region', { exact: true }).selectOption(['EMEA']);
    await expect(page).toHaveURL(/region=EMEA/);
    await expect.poll(async () => Number(await timeSeries.getAttribute('data-rows'))).toBeLessThan(before);
    await expect(page.locator('[data-tile][data-state="ready"]')).toHaveCount(4, { timeout: 60_000 });
    await expect(page.locator('.error-card')).toHaveCount(0);
    await expect(page.locator(`[data-tile="bakeoff/${renderer}/time-series"] canvas, [data-tile="bakeoff/${renderer}/time-series"] svg`).first()).toBeVisible();

    expect(log.foreign, 'every request stays on the site origin').toEqual([]);
    expect(log.failed, 'no request failed').toEqual([]);
    expect(log.consoleErrors.filter((m) => /Content Security Policy|Refused to/i.test(m)), 'no CSP violations').toEqual([]);
    expect(log.consoleErrors, 'no console errors').toEqual([]);
  });
}

test('the single chart page renders a large-lane chart and shows its columns', async ({ page }) => {
  const log = watch(page);
  await page.goto('/c/bakeoff/vega-lite/order-lines');
  await expect(page.locator('[data-tile][data-state="ready"]')).toHaveCount(1, { timeout: 90_000 });
  await expect(page.locator('.error-card')).toHaveCount(0);
  await expect(page.getByRole('cell', { name: 'amount' })).toBeVisible();
  expect(log.foreign).toEqual([]);
  expect(log.consoleErrors).toEqual([]);
});

test('a missing dashboard shows one error card and the header still renders', async ({ page }) => {
  await page.goto('/d/bakeoff/nope');
  await expect(page.locator('.error-card')).toHaveCount(1);
  await expect(page.getByRole('heading', { name: 'viz-site' })).toBeVisible();
});

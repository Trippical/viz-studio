import { expect, test, type Page } from '@playwright/test';
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const EXAMPLES_DIR = join(dirname(fileURLToPath(import.meta.url)), '../../skills/publish-viz/examples');
const EXAMPLES = readdirSync(EXAMPLES_DIR)
  .filter((name) => name.endsWith('.json'))
  .map((name) => JSON.parse(readFileSync(join(EXAMPLES_DIR, name), 'utf8')) as { renderer: string });
const VEGA_EXAMPLES = EXAMPLES.filter((e) => e.renderer === 'vega-lite').length;

const RENDERERS = ['vega-lite'] as const;
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

    // Every chart must fill its tile. A renderer stylesheet once collapsed the
    // Vega-Lite mounts to 21px tall while toBeVisible() still passed.
    for (const name of ['time-series', 'grouped-bar', 'order-lines']) {
      const tile = page.locator(`[data-tile="bakeoff/${renderer}/${name}"]`);
      const tileBox = await tile.boundingBox();
      const mountBox = await tile.locator('.tile-mount').boundingBox();
      expect(tileBox, `${name} tile has a box`).not.toBeNull();
      expect(mountBox, `${name} mount has a box`).not.toBeNull();
      expect(mountBox!.height, `${name} chart fills its tile`).toBeGreaterThan(tileBox!.height * 0.6);
    }

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

test('a deep-linked region survives another control change, and tiles carry download links and freshness', async ({ page }) => {
  const log = watch(page);
  await page.goto('/d/bakeoff/vega-lite?region=EMEA');
  await expect(page.locator('[data-tile][data-state="ready"]')).toHaveCount(4, { timeout: 90_000 });
  await expect(page.locator('.error-card')).toHaveCount(0);
  await expect(page.getByLabel('Region', { exact: true })).toHaveValues(['EMEA']);

  await page.getByLabel('Days from').fill('2025-01-01');
  await expect(page).toHaveURL(/days=2025-01-01/);
  await expect(page).toHaveURL(/region=EMEA/);
  await expect(page.locator('[data-tile][data-state="ready"]')).toHaveCount(4, { timeout: 60_000 });

  const links = page.getByRole('link', { name: 'Download data' });
  await expect(links).toHaveCount(4);
  await expect(page.locator('[data-tile="bakeoff/vega-lite/order-lines"] a.tile-download')).toHaveAttribute('href', '/api/data/bakeoff/vega-lite/order-lines');
  await expect(page.locator('[data-tile="bakeoff/vega-lite/order-lines"] .tile-chart')).toHaveAttribute('role', 'img');
  await expect(page.locator('[data-tile="bakeoff/vega-lite/order-lines"] .tile-chart')).toHaveAttribute('aria-label', /.+/);
  await expect(page.getByText(/^Data as of \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC$/).first()).toBeVisible();

  expect(log.foreign, 'every request stays on the site origin').toEqual([]);
  expect(log.failed, 'no request failed').toEqual([]);
  expect(log.consoleErrors, 'no console errors').toEqual([]);
});

test.describe('200% browser zoom (simulated with a narrow viewport)', () => {
  test.use({ viewport: { width: 640, height: 900 } });

  test('the stat tile value does not clip and the footer keeps the download link visible', async ({ page }) => {
    await page.goto('/d/bakeoff/vega-lite');
    const tile = page.locator('[data-tile="bakeoff/total-revenue"]');
    await expect(tile).toHaveAttribute('data-state', 'ready', { timeout: 90_000 });

    const value = tile.getByTestId('stat-value');
    const sizes = await value.evaluate((el) => ({ scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }));
    expect(sizes.scrollWidth, 'stat value does not overflow its box').toBeLessThanOrEqual(sizes.clientWidth);

    await expect(tile.getByRole('link', { name: 'Download data' })).toBeVisible();
  });
});

test('hashed assets are cached for a year', async ({ request }) => {
  const html = await (await request.get('/')).text();
  const match = /\/assets\/[^"']+\.js/.exec(html);
  expect(match, 'index.html references a hashed script').not.toBeNull();
  const res = await request.get(match![0]);
  expect(res.status()).toBe(200);
  expect(res.headers()['cache-control']).toBe('public, max-age=31536000, immutable');
});

test('a missing dashboard shows one error card and the header still renders', async ({ page }) => {
  await page.goto('/d/bakeoff/nope');
  await expect(page.locator('.error-card')).toHaveCount(1);
  await expect(page.getByRole('heading', { name: 'viz-site' })).toBeVisible();
});

test('the examples gallery renders every chart form from the skill', async ({ page }) => {
  const log = watch(page);
  await page.goto('/d/examples/gallery');
  await expect(page.locator('[data-tile]')).toHaveCount(EXAMPLES.length);
  await expect(page.locator('[data-tile][data-state="ready"]')).toHaveCount(EXAMPLES.length, { timeout: 90_000 });
  await expect(page.locator('.error-card')).toHaveCount(0);

  // Every Vega-Lite example draws one canvas of a readable height.
  const canvases = page.locator('[data-tile] canvas');
  await expect(canvases).toHaveCount(VEGA_EXAMPLES);
  for (let i = 0; i < VEGA_EXAMPLES; i++) {
    const box = await canvases.nth(i).boundingBox();
    expect(box, `canvas ${i} has a box`).not.toBeNull();
    expect(box!.height, `canvas ${i} is taller than 50px`).toBeGreaterThan(50);
  }

  expect(log.foreign, 'every request stays on the site origin').toEqual([]);
  expect(log.failed, 'no request failed').toEqual([]);
  expect(log.consoleErrors, 'no console errors').toEqual([]);
});

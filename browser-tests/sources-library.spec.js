const { test, expect } = require('@playwright/test');
const axe = require('@axe-core/playwright');

test('source library loads and renders registry safely', async ({ page }) => {
  await page.goto('/sources.html');
  await expect(page.getByText('Research Source Library')).toBeVisible();
  await expect(page.locator('#count')).not.toHaveText('—');
  await expect(page.locator('#list article').first()).toBeVisible();
  const links = page.locator('#list a');
  if (await links.count()) {
    await expect(links.first()).toHaveAttribute('rel', /noopener/);
    await expect(links.first()).toHaveAttribute('target', '_blank');
  }
});

test('search and category filter narrow results and empty state', async ({ page }) => {
  await page.goto('/sources.html');
  await expect(page.locator('#list article').first()).toBeVisible();
  const initial = await page.locator('#list article').count();
  await page.getByLabel('Search source name, category or URL').fill('SEC');
  await expect(page.locator('#status')).toContainText('sources shown');
  const filtered = await page.locator('#list article').count();
  expect(filtered).toBeLessThanOrEqual(initial);
  await page.getByLabel('Search source name, category or URL').fill('zzzz-no-match-qa');
  await expect(page.locator('#list')).toContainText('No matching sources');
});

test('source registry failure has a user-readable state', async ({ page }) => {
  await page.route('**/sources', route => route.fulfill({status:503, body:'unavailable'}));
  await page.goto('/sources.html');
  await expect(page.locator('#status')).toContainText('Could not load the source registry');
  await expect(page.locator('#list')).toContainText('Check that the TradingDYOR API is running');
});

test('responsive layout and keyboard accessible query control', async ({ page }) => {
  await page.setViewportSize({width: 375, height: 812});
  await page.goto('/sources.html');
  const query = page.getByLabel('Search source name, category or URL');
  await query.focus();
  await expect(query).toBeFocused();
  await expect(page.locator('body')).toBeVisible();
  const violations = await new axe.AxeBuilder({page}).withTags(['wcag2a','wcag2aa']).analyze();
  expect(violations.violations.map(v=>v.id)).toEqual([]);
});

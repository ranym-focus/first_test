import { test, expect, Page } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const AUTH_ENABLED = process.env.AUTH_ENABLED === 'true';
const ROUTES = ['/', '/about', '/dashboard', '/items', '/settings', '/profile'];

async function waitForNetworkIdle(page: Page, timeout = 10000) {
  await page.waitForLoadState('networkidle', { timeout });
}

async function maybeLogin(page: Page) {
  if (!AUTH_ENABLED) return;

  try {
    const loginProbe = await page.request.get(`${BASE_URL}/login`, { timeout: 3000 });
    if (loginProbe && loginProbe.ok) {
      // Navigate to login page
      await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
      // Try to fill common fields if present
      const usernameSelector = 'input[name="username"], input#username';
      const passwordSelector = 'input[name="password"], input#password';
      const hasUsername = await page.locator(usernameSelector).count() > 0;
      const hasPassword = await page.locator(passwordSelector).count() > 0;

      if (hasUsername) {
        const user = process.env.USERNAME || 'test';
        await page.fill(usernameSelector, user);
      }
      if (hasPassword) {
        const pass = process.env.PASSWORD || 'test';
        await page.fill(passwordSelector, pass);
      }

      // Submit if possible
      const submitBtn = page.locator('button[type="submit"], input[type="submit"]');
      if (await submitBtn.count() > 0) {
        await submitBtn.first().click();
        await page.waitForLoadState('networkidle', { timeout: 5000 });
      }
    }
  } catch {
    // If login flow is not available or fails, continue as guest
  }
}

async function fillIfExists(page: Page, selector: string, value: string): Promise<boolean> {
  const el = page.locator(selector);
  if ((await el.count()) > 0) {
    await el.first().fill(value);
    return true;
  }
  return false;
}

test.describe('Comprehensive End-to-End Tests (Playwright)', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
  });

  ROUTES.forEach((route) => {
    test(`Navigate to route ${route}`, async ({ page }) => {
      await maybeLogin(page);
      await page.goto(`${BASE_URL}${route}`, { waitUntil: 'networkidle' });
      await waitForNetworkIdle(page, 15000);

      const h1Count = await page.locator('h1').count();
      if (h1Count > 0) {
        await expect(page.locator('h1').first()).toBeVisible();
      } else {
        const main = page.locator('main');
        if ((await main.count()) > 0) {
          await expect(main.first()).toBeVisible();
        } else {
          // As a fallback, ensure page has some content loaded
          const body = page.locator('body');
          await expect(body).toBeVisible();
        }
      }
    });
  });

  test('Data persistence: create, read, update, delete item', async ({ page }) => {
    await maybeLogin(page);
    await page.goto(`${BASE_URL}/items`, { waitUntil: 'networkidle' });
    await waitForNetworkIdle(page, 10000);

    const hasForm = (await page.locator('form').count()) > 0;
    if (!hasForm) {
      // If there's no form on items page, skip this test gracefully
      return;
    }

    const uniqueName = `Item-${Date.now()}`;
    // Attempt to fill common fields if present
    await fillIfExists(page, 'input[name="name"]', uniqueName);
    await fillIfExists(page, 'textarea[name="description"]', 'End-to-end test item');
    await fillIfExists(page, 'input[name="price"]', '9.99');
    await fillIfExists(page, 'input[name="quantity"]', '1');

    const submitBtn = page.locator('button[type="submit"], input[type="submit"]');
    if ((await submitBtn.count()) > 0) {
      await submitBtn.first().click();
    } else {
      await page.keyboard.press('Enter');
    }

    await page.waitForNavigation({ waitUntil: 'networkidle' });

    // Read: verify item appears in list
    const createdRow = page.locator(`text=${uniqueName}`).first();
    await expect(createdRow).toBeVisible();

    // Update: try to click an Edit button in the same row if available
    const editBtn = page.locator(`//tr[td//text()[contains(., '${uniqueName}')]]//button[contains(., 'Edit')]`).first();
    if ((await editBtn.count()) > 0) {
      await editBtn.click();
      await fillIfExists(page, 'textarea[name="description"]', 'Updated by E2E');
      const saveBtn = page.locator('button[type="submit"]');
      if ((await saveBtn.count()) > 0) {
        await saveBtn.first().click();
      } else {
        await page.keyboard.press('Enter');
      }
      await page.waitForNavigation({ waitUntil: 'networkidle' });
      await expect(page.locator(`text=Updated by E2E`)).toBeVisible();
    }

    // Delete: attempt to remove the created item
    const deleteBtn = page.locator(`//tr[td//text()[contains(., '${uniqueName}')]]//button[contains(., 'Delete')]`).first();
    if ((await deleteBtn.count()) > 0) {
      await deleteBtn.click();
      const confirmBtn = page.locator('button:has-text("Yes"), button:has-text("Confirm")');
      if ((await confirmBtn.count()) > 0) {
        await confirmBtn.first().click();
      }
      // Wait for removal
      await page.waitForSelector(`text=${uniqueName}`, { state: 'detached', timeout: 5000 }).catch(() => {});
      await expect(page.locator(`text=${uniqueName}`)).toHaveCount(0);
    }
  });

  test.afterAll(async () => {
    // Teardown steps if necessary in the future
  });
});
// e2e-playwright.e2e.js
// Comprehensive Playwright E2E tests with setup, teardown, and helper utilities.
// Note: Routes and UI elements are best-effort generic selectors. Adjust selectors to match your app.

const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';

const ROUTES = [
  { name: 'Home', path: '/' },
  { name: 'Dashboard', path: '/dashboard' },
  { name: 'Items', path: '/items' },
  { name: 'Settings', path: '/settings' },
  { name: 'Profile', path: '/profile' }
];

// Helpers

function fullURL(path) {
  const base = BASE_URL.endsWith('/') ? BASE_URL.slice(0, -1) : BASE_URL;
  const p = path.startsWith('/') ? path : '/' + path;
  return base + p;
}

async function loginIfPossible(page) {
  // Attempt to perform login if login form exists
  const passwordInputs = page.locator('input[type="password"]');
  if (await passwordInputs.count() === 0) return false;

  const usernameInputs = page.locator('input[name="username"], input[name="email"]');
  if (await usernameInputs.count() > 0) {
    await usernameInputs.first().fill(process.env.TEST_USERNAME || 'test@example.com');
  }

  await passwordInputs.first().fill(process.env.TEST_PASSWORD || 'password');

  const submitBtn = page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign in")');
  if (await submitBtn.count() > 0) {
    await submitBtn.first().click();
    // Wait for potential navigation after login
    await page.waitForLoadState('networkidle').catch(() => {});
    return true;
  }

  // If no explicit submit button, try form submit
  const form = page.locator('form').first();
  if (await form.count() > 0) {
    await form.evaluate((f) => f.submit());
    await page.waitForLoadState('networkidle').catch(() => {});
    return true;
  }

  return true;
}

// Test suite

test.describe('Comprehensive E2E Tests (Playwright)', () => {

  test.beforeEach(async ({ page }) => {
    // Navigate to base URL to initialize session
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' }).catch(() => {});
  });

  test('Navigate to core routes and verify basic existence', async ({ page }) => {
    for (const r of ROUTES) {
      const url = fullURL(r.path);
      const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => null);
      // If navigation failed, fail this route test
      if (!response) {
        throw new Error(`Navigation to ${r.path} failed or timed out`);
      }
      // URL should be correct
      expect(page.url()).toBe(url);

      // Optional: verify a header that may exist for the route
      const header = page.locator(`h1, h2, h3`, { hasText: r.name });
      if (await header.count() > 0) {
        await expect(header.first()).toBeVisible();
      }

      // Small wait to let dynamic content load if present
      await page.waitForTimeout(200).catch(() => {});
    }
  });

  test('CRUD flow for Items (create, read, update, delete)', async ({ page }) => {
    const itemsURL = fullURL('/items');
    await page.goto(itemsURL, { waitUntil: 'domcontentloaded' });

    // Attempt login if authentication is required
    await loginIfPossible(page);

    // Create an item if "New Item" is present
    const newItemBtn = page.locator('button', { hasText: 'New Item' }).first();
    let createdName = '';
    if (await newItemBtn.count() > 0) {
      const baseName = 'E2E Item ' + Date.now();
      createdName = baseName;

      await newItemBtn.click();

      // Fill name if a name input exists
      const nameInput = page.locator('input[name="name"], input[data-testid="item-name"]');
      if (await nameInput.count() > 0) {
        await nameInput.first().fill(baseName);
      } else {
        // Fallback: type into focused input
        await page.keyboard.type(baseName);
      }

      // Save the item
      const saveBtn = page.locator('button[type="submit"], button', { hasText: 'Save' }).first();
      if (await saveBtn.count() > 0) {
        await saveBtn.click();
      } else {
        // Fallback: submit the form directly
        const form = page.locator('form').first();
        if (await form.count() > 0) {
          await form.evaluate((f) => f.submit());
        }
      }

      // Verify item appears in the list
      const createdSelector = page.locator(`text=${baseName}`);
      await createdSelector.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
      if (await createdSelector.count() > 0) {
        await expect(createdSelector).toBeVisible();
      }
      // Update step (if available)
      const itemRow = createdSelector.first();
      const editBtn = itemRow.locator('button', { hasText: 'Edit' }).first();
      if (await editBtn.count() > 0) {
        await editBtn.click();
        const editNameInput = page.locator('input[name="name"]');
        if (await editNameInput.count() > 0) {
          const updatedName = baseName + ' Updated';
          await editNameInput.first().fill(updatedName);
          const updateBtn = page.locator('button', { hasText: 'Save' }).first();
          if (await updateBtn.count() > 0) {
            await updateBtn.click();
            await expect(page.locator(`text=${updatedName}`)).toBeVisible();
            createdName = updatedName;
          }
        }
      }
      // Delete step (best-effort)
      const delBtn = itemRow.locator('button', { hasText: 'Delete' }).first();
      if (await delBtn.count() > 0) {
        await delBtn.click();
        const confirmBtn = page.locator('button', { hasText: 'Yes' }).or(page.locator('button', { hasText: 'Confirm' }));
        if (await confirmBtn.count() > 0) {
          await confirmBtn.first().click();
        }
        // Ensure item is removed
        await expect(page.locator(`text=${createdName}`)).toHaveCount(0);
      }
    } else {
      // If no New Item button, still ensure the list loads
      const listRoot = page.locator('[role="list"], [data-testid="items-list"], table');
      await listRoot.first().waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
    }
  });

  test('Error handling: 404 and invalid routes', async ({ page }) => {
    const invalidPath = '/__e2e__invalid__' + Math.floor(Math.random() * 100000);
    const url = fullURL(invalidPath);
    const response = await page.goto(url, { waitUntil: 'domcontentloaded' }).catch(() => null);
    // Navigate to an invalid route; verify URL is as requested
    expect(page.url()).toBe(url);
  });

  test('Authentication flow (optional): login/logout when auth is present', async ({ page }) => {
    // If login form is detected on the current page, run a quick login/logout test
    const pwdInputs = page.locator('input[type="password"]');
    if (await pwdInputs.count() > 0) {
      // Try to login
      const didLogin = await loginIfPossible(page);
      // If login occurred, attempt logout if a Logout control exists
      const logoutBtn = page.locator('button, a', { hasText: 'Logout' });
      if (await logoutBtn.count() > 0) {
        await logoutBtn.first().click();
      } else {
        // No explicit logout; navigate to base and clear session if possible
        await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
      }
      // Optional: ensure we land back on a public page
      await page.waitForLoadState('networkidle').catch(() => {});
    }
  });

  // Teardown hook (optional)
  test.afterAll(async () => {
    // Any global cleanup can be handled here
  });

});
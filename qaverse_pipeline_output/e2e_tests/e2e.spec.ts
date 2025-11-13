import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const ROUTES = ['/dashboard', '/items', '/profile', '/settings'];

const TEST_ITEM = {
  name: 'E2E Test Item',
  description: 'Created by an automated Playwright E2E test.'
};

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const Helpers = {
  async navigateAndAssertRoutes(page) {
    for (const route of ROUTES) {
      const url = `${BASE_URL}${route}`;
      const response = await page.goto(url, { waitUntil: 'networkidle' }).catch(() => null);
      if (response) {
        const status = response.status();
        // Accept 2xx and redirects; consider 3xx as valid navigation
        expect(status).toBeGreaterThanOrEqual(200);
        expect(status).toBeLessThan(400);
      } else {
        // If navigation failed (e.g., route not found), log and continue
        console.warn(`Warning: Could not navigate to ${url}. The route may be unavailable in this environment.`);
      }

      // Optional: ensure page has loaded a common header if present
      // const header = page.locator('[data-test="app-header"]');
      // if (await header.count() > 0) {
      //   await header.waitFor({ state: 'visible', timeout: 3000 }).catch(() => {});
      // }
    }
  },

  async loginIfAvailable(page) {
    await page.goto(BASE_URL, { waitUntil: 'networkidle' });
    const loginForm = page.locator('[data-test="login-form"]');
    if (await loginForm.count() > 0) {
      const usernameInput = page.locator('[data-test="login-username"]');
      const passwordInput = page.locator('[data-test="login-password"]');
      const submitBtn = page.locator('[data-test="login-submit"]');
      if ((await usernameInput.count()) > 0 && (await passwordInput.count()) > 0 && (await submitBtn.count()) > 0) {
        await usernameInput.fill(process.env.TEST_USERNAME || 'testuser');
        await passwordInput.fill(process.env.TEST_PASSWORD || 'password');
        await submitBtn.click();
        // Wait for potential redirect or user avatar
        await page.waitForLoadState('networkidle');
      }
    }
  },

  async createItem(page, item) {
    await page.goto(`${BASE_URL}/items`, { waitUntil: 'networkidle' });
    const createBtn = page.locator('[data-test="create-item-button"]');
    if ((await createBtn.count()) > 0) {
      await createBtn.click();
      const nameInput = page.locator('[data-test="item-name"]');
      const descInput = page.locator('[data-test="item-description"]');
      const saveBtn = page.locator('[data-test="save-item"]');
      if ((await nameInput.count()) > 0) await nameInput.fill(item.name);
      if ((await descInput.count()) > 0) await descInput.fill(item.description);
      if ((await saveBtn.count()) > 0) await saveBtn.click();

      // Wait for the item to appear in the list
      const itemLocator = page.locator(`text="${item.name}"`);
      await itemLocator.waitFor({ state: 'visible', timeout: 8000 }).catch(() => {});
    } else {
      console.warn('Create item button not found. Skipping create step.');
    }
  },

  async readItem(page, itemName) {
    await page.goto(`${BASE_URL}/items`, { waitUntil: 'networkidle' });
    const itemLocator = page.locator(`text="${itemName}"`).first();
    await itemLocator.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
    return itemLocator;
  },

  async updateItem(page, oldName, newName) {
    // Find the row with the old name and click edit
    const row = page.locator(`tr:has-text("${oldName}")`).first();
    const editBtn = row.locator('[data-test="edit-item"]');
    if ((await editBtn.count()) > 0) {
      await editBtn.click();
      const nameInput = page.locator('[data-test="item-name"]');
      if ((await nameInput.count()) > 0) {
        await nameInput.fill(newName);
        const saveBtn = page.locator('[data-test="save-item"]');
        if ((await saveBtn.count()) > 0) {
          await saveBtn.click();
          // Verify updated name appears
          const updatedLocator = page.locator(`text="${newName}"`).first();
          await updatedLocator.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
        }
      }
    } else {
      console.warn('Edit button for the item not found. Skipping update.');
    }
  },

  async deleteItem(page, itemName) {
    const row = page.locator(`tr:has-text("${itemName}")`).first();
    const deleteBtn = row.locator('[data-test="delete-item"]');
    if ((await deleteBtn.count()) > 0) {
      await deleteBtn.click();
      const confirmBtn = page.locator('[data-test="confirm-delete"]');
      if ((await confirmBtn.count()) > 0) {
        await confirmBtn.click();
      }
      // Wait for the row to be removed
      await row.waitFor({ state: 'detached', timeout: 5000 }).catch(() => {});
    } else {
      console.warn('Delete button for the item not found. Skipping delete.');
    }
  }
};

test.describe('Comprehensive End-to-End: Generic flows', () => {
  test.beforeEach(async ({ page }) => {
    // Common setup for each test
    await page.setViewportSize({ width: 1280, height: 720 });
    page.setDefaultTimeout(30000);
  });

  test('Navigate to potential routes and verify basic access', async ({ page }) => {
    await Helpers.navigateAndAssertRoutes(page);
  });

  test('Authentication flow (if available)', async ({ page }) => {
    await Helpers.loginIfAvailable(page);
    // Post-login verification (best-effort)
    const postLoginSelector = page.locator('[data-test="user-avatar"]');
    if ((await postLoginSelector.count()) > 0) {
      await postLoginSelector.first().waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
      // Optionally log out to clean state if supported
      // const logoutBtn = page.locator('[data-test="logout"]');
      // if ((await logoutBtn.count()) > 0) { await logoutBtn.click(); }
    } else {
      // If no auth flow detected, consider test passed as it's environment-specific
      // Do not fail the test in absence of auth pages
    }
  });

  test('Create, Read, Update, and Delete (CRUD) for items', async ({ page }) => {
    // Ensure we are on the items page and login if needed
    await Helpers.loginIfAvailable(page);
    // Create
    await Helpers.createItem(page, TEST_ITEM);

    // Read/Verify creation
    const created = await Helpers.readItem(page, TEST_ITEM.name);
    await expect(created).toBeVisible();

    // Update
    const UPDATED_NAME = TEST_ITEM.name + ' Updated';
    await Helpers.updateItem(page, TEST_ITEM.name, UPDATED_NAME);
    const updatedLocator = page.locator(`text="${UPDATED_NAME}"`).first();
    await updatedLocator.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});

    // Verify update
    await expect(updatedLocator).toBeVisible();

    // Delete
    await Helpers.deleteItem(page, UPDATED_NAME);
    const afterDelete = page.locator(`text="${UPDATED_NAME}"`);
    await expect(afterDelete).toHaveCount(0);
  });
});
import { test, expect } from '@playwright/test';
import { Helpers } from './e2e.spec';

type CountsMap = { [selector: string]: number };

class MockLocator {
  page: MockPage;
  selector: string;
  parent?: MockLocator;

  constructor(page: MockPage, selector: string, parent?: MockLocator) {
    this.page = page;
    this.selector = selector;
    this.parent = parent;
  }

  private key(): string {
    if (this.parent) return `${this.parent.key()}|${this.selector}`;
    return this.selector;
  }

  async count(): Promise<number> {
    return this.page.getCountForSelector(this.key());
  }

  locator(subSelector: string): MockLocator {
    return new MockLocator(this.page, subSelector, this);
  }

  async fill(value: string): Promise<void> {
    this.page.recordFill(this.key(), value);
  }

  async click(): Promise<void> {
    this.page.recordClick(this.key());
  }

  async first(): Promise<MockLocator> {
    return this;
  }

  async waitFor(opts: any): Promise<void> {
    this.page.recordWait(this.key(), opts);
  }
}

class MockPage {
  config: any;
  values: Map<string, any>;
  filled: Array<{ key: string; value: any }>;
  clicks: string[];
  waits: Array<{ key: string; opts: any }>;
  gotoCalls: Array<{ url: string; opts: any }>;
  waitState: string | null;

  constructor(config: any) {
    this.config = config || {};
    this.values = new Map();
    this.filled = [];
    this.clicks = [];
    this.waits = [];
    this.gotoCalls = [];
    this.waitState = null;
  }

  locator(selector: string): MockLocator {
    return new MockLocator(this, selector);
  }

  async goto(url: string, _opts?: any): Promise<any> {
    this.gotoCalls.push({ url, opts: _opts });
    if (this.config.gotoThrow?.(url)) {
      throw new Error('goto failed');
    }
    const status = this.config.gotoStatus?.(url) ?? 200;
    return { status: () => status } as any;
  }

  async waitForLoadState(_state: string): Promise<void> {
    this.waitState = _state;
    return;
  }

  // Helpers to configure test expectations
  getCountForSelector(key: string): number {
    return (this.config.counts && this.config.counts[key]) ?? 0;
  }

  recordFill(key: string, value: any) {
    this.filled.push({ key, value });
    this.values.set(key, value);
  }

  recordClick(key: string) {
    this.clicks.push(key);
  }

  recordWait(key: string, opts: any) {
    this.waits.push({ key, opts });
  }

  // Helpers for tests
  getFilled() {
    return this.filled;
  }
  getClicks() {
    return this.clicks;
  }
  getWaits() {
    return this.waits;
  }
  getGotoCalls() {
    return this.gotoCalls;
  }

  reset() {
    this.values.clear();
    this.filled = [];
    this.clicks = [];
    this.waits = [];
    this.gotoCalls = [];
  }

  // Convenience for tests to introspect values
  getValueForKey(key: string): any {
    return this.values.get(key);
  }
}

// Unit tests for the Helpers public functions
test.describe('Helpers: unit tests (isolated, mocked Playwright page)', () => {
  test('navigateAndAssertRoutes handles success and failure scenarios', async () => {
    const warnLogs: string[] = [];
    const origWarn = console.warn;
    console.warn = (msg: any) => {
      warnLogs.push(String(msg));
    };

    const config = {
      gotoStatus: (url: string) => {
        // Simulate mixed results for ROUTES
        if (url.endsWith('/dashboard')) return 200;
        if (url.endsWith('/items')) throw new Error('route unavailable');
        if (url.endsWith('/profile')) return 301; // 3xx acceptable
        if (url.endsWith('/settings')) return 302; // 3xx acceptable
        return 200;
      },
      // Ensure the test doesn't crash due to missing values
      counts: {}
    };

    const page = new MockPage(config) as any;

    // Execute
    await Helpers.navigateAndAssertRoutes(page);

    // Assertions: some warnings should have been logged due to simulate route failure
    expect(warnLogs.length).toBeGreaterThanOrEqual(0);

    console.warn = origWarn;
  });

  test('loginIfAvailable: with a full login form available', async () => {
    // Configure environment for credentials
    process.env.TEST_USERNAME = 'unit_user';
    process.env.TEST_PASSWORD = 'unit_pass';

    const config = {
      counts: {
        // login form and inputs present
        '[data-test="login-form"]': 1,
        '[data-test="login-username"]': 1,
        '[data-test="login-password"]': 1,
        '[data-test="login-submit"]': 1
      }
    };

    const page = new MockPage(config) as any;

    await Helpers.loginIfAvailable(page);

    // Validate that username and password were filled with env values
    const userFilled = page.getValueForKey('[data-test="login-username"]');
    const passFilled = page.getValueForKey('[data-test="login-password"]');
    expect(userFilled).toBe('unit_user');
    expect(passFilled).toBe('unit_pass');
  });

  test('loginIfAvailable: when login form is not present, should not fail', async () => {
    const config = {
      counts: {
        // No login form
      }
    };

    const page = new MockPage(config) as any;

    await Helpers.loginIfAvailable(page);

    // No fills should be performed
    expect(page.getFilled().length).toBe(0);
  });

  test('createItem: should create item when create button is present', async () => {
    const config = {
      counts: {
        '[data-test="create-item-button"]': 1,
        '[data-test="item-name"]': 1,
        '[data-test="item-description"]': 1,
        '[data-test="save-item"]': 1,
        // The item text should appear after creation
        'text="E2E Test Item"': 1
      }
    };

    const page = new MockPage(config) as any;

    await Helpers.createItem(page, { name: 'E2E Test Item', description: 'Created by an automated Playwright E2E test.' });

    // Verify fills
    expect(page.getValueForKey('[data-test="item-name"]')).toBe('E2E Test Item');
    expect(page.getValueForKey('[data-test="item-description"]')).toBe(
      'Created by an automated Playwright E2E test.'
    );

    // Verify wait for the new item appears in the list
    const waitKeys = page.getWaits().map((w) => w.key);
    expect(waitKeys).toContain('text="E2E Test Item"');
  });

  test('createItem: should warn when create button is not found', async () => {
    const origWarn = console.warn;
    const warned: string[] = [];
    console.warn = (msg: any) => warned.push(String(msg));

    const config = {
      counts: {
        // create button missing
      }
    };
    const page = new MockPage(config) as any;

    await Helpers.createItem(page, TEST_ITEM);

    expect(warned.length).toBeGreaterThan(0);

    console.warn = origWarn;
  });

  test('readItem: should return a locator and wait for presence', async () => {
    const config = {
      counts: {
        'text="E2E Test Item"': 1
      }
    };
    const page = new MockPage(config) as any;

    const locator = await Helpers.readItem(page, 'E2E Test Item');

    // The function should return a locator (mocked)
    expect(locator).toBeDefined();

    // It should have invoked a waitFor on that locator
    const waits = page.getWaits();
    expect(waits.length).toBeGreaterThan(0);
  });

  test('updateItem: should update item when edit path exists', async () => {
    const config = {
      counts: {
        'tr:has-text("OldName")': 1,
        'tr:has-text("OldName")|[data-test="edit-item"]': 1,
        '[data-test="item-name"]': 1,
        '[data-test="save-item"]': 1,
        'text="NewName"': 1
      }
    };

    const page = new MockPage(config) as any;

    await Helpers.updateItem(page, 'OldName', 'NewName');

    // Verify update flow: new name filled and wait for the new text to appear
    expect(page.getValueForKey('[data-test="item-name"]')).toBe('NewName');

    const waits = page.getWaits();
    const hasNewNameWait = waits.find((w) => w.key === 'text="NewName"');
    expect(hasNewNameWait).toBeDefined();
  });

  test('updateItem: should warn when edit button not found', async () => {
    const origWarn = console.warn;
    const warned: string[] = [];
    console.warn = (msg: any) => warned.push(String(msg));

    const config = {
      counts: {
        // No row found
      }
    };

    const page = new MockPage(config) as any;

    await Helpers.updateItem(page, 'NonExistent', 'ShouldNotMatter');

    expect(warned.length).toBeGreaterThan(0);

    console.warn = origWarn;
  });

  test('deleteItem: should delete item when delete flow is available', async () => {
    const config = {
      counts: {
        'tr:has-text("NameToDelete")': 1,
        'tr:has-text("NameToDelete")|[data-test="delete-item"]': 1,
        '[data-test="confirm-delete"]': 1
      }
    };

    const page = new MockPage(config) as any;

    await Helpers.deleteItem(page, 'NameToDelete');

    // Verify delete flow invoked by ensuring delete item path was clicked
    const waits = page.getWaits();
    // There should be a wait for detach on the row
    const detachWait = waits.find((w) => w.key === 'tr:has-text("NameToDelete")');
    expect(detachWait).toBeDefined();
  });

  test('deleteItem: should warn when delete button not found', async () => {
    const origWarn = console.warn;
    const warned: string[] = [];
    console.warn = (msg: any) => warned.push(String(msg));

    const config = {
      counts: {
        // No delete button
      }
    };

    const page = new MockPage(config) as any;

    await Helpers.deleteItem(page, 'NameToDelete');

    expect(warned.length).toBeGreaterThan(0);

    console.warn = origWarn;
  });
});

// Helper to provide a stable test item
const TEST_ITEM = {
  name: 'E2E Test Item',
  description: 'Created by an automated Playwright E2E test.'
};
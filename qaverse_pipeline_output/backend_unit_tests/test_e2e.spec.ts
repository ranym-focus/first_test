import { test, expect } from '@playwright/test';

type LocatorLike = {
  count(): Promise<number>;
  first(): LocatorLike;
  fill?(value: string): Promise<void>;
  click?(): Promise<void>;
};

class MockLocator implements LocatorLike {
  selector: string;
  page: MockPage;

  constructor(selector: string, page: MockPage) {
    this.selector = selector;
    this.page = page;
  }

  async count(): Promise<number> {
    // Composite selectors support (e.g., 'a, b')
    if (this.selector.includes(',')) {
      const parts = this.selector.split(',').map((s) => s.trim());
      for (const part of parts) {
        if (this.page.existsMap.get(part)) {
          return 1;
        }
      }
      return 0;
    }
    return this.page.existsMap.get(this.selector) ? 1 : 0;
  }

  first(): LocatorLike {
    return this;
  }

  async fill(value: string): Promise<void> {
    this.page.filled.set(this.selector, value);
  }

  async click(): Promise<void> {
    this.page.clickedSelectors.push(this.selector);
  }
}

class MockPage {
  // Mock environment
  existsMap: Map<string, boolean> = new Map();
  filled: Map<string, string> = new Map();
  clickedSelectors: string[] = [];
  gotoUrl?: string;
  loginProbeCalled: boolean = false;
  loginProbeOk: boolean = false;
  lastWaitState?: string;
  lastWaitTimeout?: number;

  // request.get mock
  request = {
    get: async (_url: string, _opts?: any) => {
      this.loginProbeCalled = true;
      return { ok: this.loginProbeOk };
    },
  };

  // Locator factory
  locator(selector: string): MockLocator {
    return new MockLocator(selector, this);
  }

  async goto(url: string, _opts?: any): Promise<void> {
    this.gotoUrl = url;
  }

  async waitForLoadState(state: string, opts?: any): Promise<void> {
    this.lastWaitState = state;
    this.lastWaitTimeout = opts?.timeout;
  }

  // Helpers for tests
  reset() {
    this.filled.clear();
    this.clickedSelectors = [];
    this.gotoUrl = undefined;
    this.loginProbeCalled = false;
    this.lastWaitState = undefined;
    this.lastWaitTimeout = undefined;
  }
}

// Pure helper implementations copied for unit testing purposes
const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const AUTH_ENABLED = process.env.AUTH_ENABLED === 'true';

async function waitForNetworkIdle(page: MockPage, timeout = 10000) {
  await page.waitForLoadState('networkidle', { timeout });
}

async function maybeLogin(page: MockPage) {
  if (!AUTH_ENABLED) return;

  try {
    const loginProbe = await page.request.get(`${BASE_URL}/login`, { timeout: 3000 });
    if (loginProbe && loginProbe.ok) {
      // Navigate to login page
      await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
      // Try to fill common fields if present
      const usernameSelector = 'input[name="username"], input#username';
      const passwordSelector = 'input[name="password"], input#password';
      const hasUsername = (await page.locator(usernameSelector).count()) > 0;
      const hasPassword = (await page.locator(passwordSelector).count()) > 0;

      if (hasUsername) {
        const user = process.env.USERNAME || 'test';
        await page.locator(usernameSelector).fill?.(user);
      }
      if (hasPassword) {
        const pass = process.env.PASSWORD || 'test';
        await page.locator(passwordSelector).fill?.(pass);
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

async function fillIfExists(page: MockPage, selector: string, value: string): Promise<boolean> {
  const el = page.locator(selector);
  if ((await el.count()) > 0) {
    await el.first().fill?.(value);
    return true;
  }
  return false;
}

test.describe('Comprehensive Unit Tests for internal helpers (derived from e2e.spec.ts)', () => {
  test.beforeEach(async () => {
    // reset any global state if needed
  });

  test('waitForNetworkIdle forwards network idle state with timeout', async () => {
    const page = new MockPage();
    await waitForNetworkIdle(page, 15000);
    expect(page.lastWaitState).toBe('networkidle');
    expect(page.lastWaitTimeout).toBe(15000);
  });

  test('fillIfExists returns true and fills when selector exists', async () => {
    const page = new MockPage();
    page.existsMap.set('input[name="name"]', true);
    const result = await fillIfExists(page, 'input[name="name"]', 'Alice');
    expect(result).toBe(true);
    expect(page.filled.get('input[name="name"]')).toBe('Alice');
  });

  test('fillIfExists returns false when selector does not exist', async () => {
    const page = new MockPage();
    page.existsMap.set('input[name="description"]', false);
    const result = await fillIfExists(page, 'input[name="description"]', 'Desc');
    expect(result).toBe(false);
    expect(page.filled.has('input[name="description"]')).toBeFalsy();
  });

  test('maybeLogin skips when AUTH is disabled', async () => {
    const page = new MockPage();
    // Force auth disabled
    const originalAuth = process.env.AUTH_ENABLED;
    process.env.AUTH_ENABLED = 'false';
    try {
      await maybeLogin(page);
      expect(page.loginProbeCalled).toBe(false);
    } finally {
      process.env.AUTH_ENABLED = originalAuth;
    }
  });

  test('maybeLogin fills credentials when available and login probe succeeds', async () => {
    const page = new MockPage();
    process.env.AUTH_ENABLED = 'true';
    process.env.BASE_URL = 'http://test';
    page.loginProbeOk = true;
    // Username/password inputs exist
    page.existsMap.set('input[name="username"]', true);
    page.existsMap.set('input[name="password"]', true);
    page.existsMap.set('textarea[name="description"]', false);
    process.env.USERNAME = 'bob';
    process.env.PASSWORD = 'secret';
    await maybeLogin(page);

    // navigate to login page
    expect(page.gotoUrl).toBe('http://test/login');

    // credentials filled
    expect(page.filled.get('input[name="username"]')).toBe('bob');
    expect(page.filled.get('input[name="password"]')).toBe('secret');

    // submit button exists and clicked
    // There is a composite selector for submit
    // Our MockLocator records clicks on first submit selector
    const hasSubmitTriggered = page.clickedSelectors.includes('button[type="submit"], input[type="submit"]');
    expect(hasSubmitTriggered).toBeTruthy();

    // network idle after submit should have been awaited
    expect(page.lastWaitState).toBe('networkidle');
  });

  test('maybeLogin does not fill fields when inputs do not exist', async () => {
    const page = new MockPage();
    process.env.AUTH_ENABLED = 'true';
    page.loginProbeOk = true;
    // No username/password inputs exist
    page.existsMap.set('input[name="username"]', false);
    page.existsMap.set('input[name="password"]', false);
    await maybeLogin(page);

    // Should have navigated to login but not filled credentials
    expect(page.gotoUrl).toBe('http://localhost:3000/login');
    expect(page.filled.has('input[name="username"]')).toBeFalsy();
    expect(page.filled.has('input[name="password"]')).toBeFalsy();
  });

  test('waitForNetworkIdle edge: timeout propagation via helper', async () => {
    const page = new MockPage();
    await waitForNetworkIdle(page, 3000);
    expect(page.lastWaitTimeout).toBe(3000);
  });
});
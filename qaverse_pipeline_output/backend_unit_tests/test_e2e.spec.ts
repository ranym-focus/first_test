import { test, expect } from '@playwright/test';

// Attempt to import the helper functions from the target file.
// If the functions are not exported in your environment, you may need to export them
// from e2e.spec.ts for these unit tests to work.
import {
  gotoSafe,
  pageHasForm,
  isAuthFormPresent,
  performLogin,
  ensureLogoutIfPresent,
} from './e2e.spec';

// Lightweight mock implementations to simulate Playwright Page and Locator behaviors
class MockElement {
  constructor(private page: MockPage, private selector: string, private attrs: { [k: string]: string | undefined }) {}

  async fill(value: string) {
    this.page.recordFill(this.selector, value);
  }

  async click() {
    this.page.recordClick(this.selector);
  }

  async press(_key: string) {
    this.page.recordKeyPress(_key);
  }

  async getAttribute(name: string): Promise<string | null> {
    return this.attrs[name] ?? null;
  }

  // Simulate evaluate((el) => el.tagName.toLowerCase())
  async evaluate<T>(fn: (el: any) => T): Promise<T> {
    const fakeEl = { tagName: (this.attrs['tagName'] ?? 'INPUT') };
    // @ts-ignore
    return fn(fakeEl);
  }
}

class MockLocator {
  constructor(private page: MockPage, private selector: string) {}

  first(): MockElement {
    // Determine basic attributes from selector for the mocked element
    const hasUsername = this.selector.includes('username');
    const hasPassword = this.selector.includes('password');
    const isSelect = this.selector.includes('select');
    const tagName = isSelect ? 'select' : 'input';
    const attrs: { [k: string]: string | undefined } = {
      name: hasUsername ? 'username' : hasPassword ? 'password' : (this.selector.includes('name=') ? 'name' : undefined),
      type: this.selector.includes('type="password"') ? 'password' : 'text',
      tagName,
    };
    return new MockElement(this.page, this.selector, attrs);
  }

  async count(): Promise<number> {
    return this.page.countForSelector(this.selector);
  }
}

class MockPage {
  // Map of selector -> count (to simulate presence of elements)
  private counts = new Map<string, number>();
  // Recording interactions
  public fills: Array<{ selector: string; value: string }> = [];
  public clicks: string[] = [];
  public keyPresses: string[] = [];
  public lastGoto: string | null = null;

  // Keyboard helper (as used by performLogin)
  public keyboard = {
    press: async (key: string) => {
      this.keyPresses.push(key);
    },
  };

  goto(url: string, _opts: any) {
    this.lastGoto = url;
    return Promise.resolve();
  }

  locator(selector: string) {
    // Return a mock locator for any selector
    return new MockLocator(this, selector);
  }

  waitForLoadState(_state: string, _opts?: any) {
    return Promise.resolve();
  }

  setCount(selector: string, count: number) {
    this.counts.set(selector, count);
  }

  countForSelector(selector: string): number {
    return this.counts.get(selector) ?? 0;
  }

  recordFill(selector: string, value: string) {
    this.fills.push({ selector, value });
  }

  recordClick(selector: string) {
    this.clicks.push(selector);
  }

  recordKeyPress(_key: string) {
    // Normalize to indicate a press happened
    this.keyPresses.push(_key);
  }

  // Helpers used by tests
  hasClicked(selector: string): boolean {
    return this.clicks.includes(selector);
  }
}

// Unit tests for helper functions
test.describe('Unit tests for e2e.spec helpers (Playwright)', () => {
  test('gotoSafe constructs the correct URL', async () => {
    const mockPage = new MockPage();
    // BASE_URL defaults to http://localhost:3000 per source; test against that
    await gotoSafe(mockPage as any, '/home');
    expect(mockPage.lastGoto).toBe('http://localhost:3000/home');
  });

  test('pageHasForm detects presence and absence of forms', async () => {
    const mockPage1 = new MockPage();
    mockPage1.setCount('form', 1);
    // @ts-ignore
    const hasForm1 = await pageHasForm(mockPage1 as any);
    expect(hasForm1).toBe(true);

    const mockPage2 = new MockPage();
    mockPage2.setCount('form', 0);
    // @ts-ignore
    const hasForm2 = await pageHasForm(mockPage2 as any);
    expect(hasForm2).toBe(false);
  });

  test('isAuthFormPresent detects basic auth form presence', async () => {
    const mockPage = new MockPage();
    // Simulate an auth form with username and password fields present
    mockPage.setCount('input[name="username"], input[name="email"]', 1);
    mockPage.setCount('input[name="password"]', 1);
    // @ts-ignore
    const result = await isAuthFormPresent(mockPage as any);
    expect(result).toBe(true);
  });

  test('performLogin returns true when auth form present and logout indicator exists', async () => {
    const mockPage = new MockPage();
    mockPage.setCount('input[name="username"], input[name="email"]', 1);
    mockPage.setCount('input[name="password"]', 1);
    mockPage.setCount('button[type="submit"], button:has-text("Login"), input[type="submit"]', 1);
    mockPage.setCount('text=Logout, text=Sign out, a[href*="logout"], button:has-text("Logout")', 1);

    // Execute
    // @ts-ignore
    const result = await performLogin(mockPage as any);
    expect(result).toBe(true);

    // Verify that a login submit was attempted (click on submit)
    // The exact selector used for submit is the composite; we recorded clicks to the locator
    // Since our mock doesn't tie the specific submit selector after first(), we check that some click happened
    expect(mockPage.clicks.length).toBeGreaterThanOrEqual(1);
  });

  test('performLogin returns false when no auth form is present', async () => {
    const mockPage = new MockPage();
    mockPage.setCount('input[name="username"], input[name="email"]', 0);
    mockPage.setCount('input[name="password"]', 0);

    // @ts-ignore
    const result = await performLogin(mockPage as any);
    expect(result).toBe(false);
  });

  test('ensureLogoutIfPresent clicks logout when present', async () => {
    const mockPage = new MockPage();
    mockPage.setCount('text=Logout, text=Sign out, a[href*="logout"], button:has-text("Logout")', 1);
    // @ts-ignore
    await ensureLogoutIfPresent(mockPage as any);
    // The mock should record a click on the logout locator selector
    expect(mockPage.clicks.length).toBeGreaterThan(0);
  });

  test('ensureLogoutIfPresent is a no-op when logout is not present', async () => {
    const mockPage = new MockPage();
    mockPage.setCount('text=Logout, text=Sign out, a[href*="logout"], button:has-text("Logout")', 0);
    // @ts-ignore
    await ensureLogoutIfPresent(mockPage as any);
    expect(mockPage.clicks.length).toBe(0);
  });
});
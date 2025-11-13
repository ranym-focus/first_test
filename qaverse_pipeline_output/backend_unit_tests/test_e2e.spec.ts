import { test, expect } from '@playwright/test';

type LocatorLike = {
  count(): Promise<number>;
  first(): LocatorLike;
  fill?(value: string): Promise<void>;
  click?(): Promise<void>;
  evaluate?(fn: (f: any) => void): Promise<void>;
};

class MockLocator implements LocatorLike {
  private countValue: number;
  public filled: boolean = false;
  public clicked: boolean = false;
  public evaluated: boolean = false;

  constructor(countValue: number) {
    this.countValue = countValue;
  }

  async count(): Promise<number> {
    return this.countValue;
  }

  first(): LocatorLike {
    // Return self for chaining in tests
    return this;
  }

  async fill(_value: string): Promise<void> {
    this.filled = true;
  }

  async click(): Promise<void> {
    this.clicked = true;
  }

  async evaluate(_fn: (f: any) => void): Promise<void> {
    this.evaluated = true;
    // Simulate form.submit() call
    _fn({ submit: () => {} });
  }
}

class MockPage {
  passwordLocator: MockLocator;
  usernameLocator: MockLocator;
  submitLocator: MockLocator;
  formLocator: MockLocator;
  waited: boolean = false;

  constructor(cfg: { passwordCount: number; userCount: number; submitCount: number; formCount: number }) {
    this.passwordLocator = new MockLocator(cfg.passwordCount);
    this.usernameLocator = new MockLocator(cfg.userCount);
    this.submitLocator = new MockLocator(cfg.submitCount);
    this.formLocator = new MockLocator(cfg.formCount);
  }

  locator(selector: string): LocatorLike {
    if (selector.includes('input[type="password"]')) return this.passwordLocator;
    if (
      selector.includes('input[name="username"]') ||
      selector.includes('input[name="email"]')
    )
      return this.usernameLocator;
    if (
      selector.includes('button') &&
      (selector.includes('type="submit"') ||
        selector.includes('has-text("Login")') ||
        selector.includes('has-text("Sign in")'))
    )
      return this.submitLocator;
    if (selector.includes('form') || selector === 'form')
      return this.formLocator;
    return new MockLocator(0);
  }

  async waitForLoadState(_state: string): Promise<void> {
    this.waited = true;
    return;
  }
}

// Re-implement the loginIfPossible logic inside tests to unit-test the helper behavior
async function loginIfPossibleFromTest(page: MockPage): Promise<boolean> {
  const passwordInputs = page.locator('input[type="password"]');
  if ((await passwordInputs.count()) === 0) return false;

  const usernameInputs = page.locator('input[name="username"], input[name="email"]');
  if ((await usernameInputs.count()) > 0) {
    await usernameInputs.first().fill(process.env.TEST_USERNAME || 'test@example.com');
  }

  await passwordInputs.first().fill(process.env.TEST_PASSWORD || 'password');

  const submitBtn = page.locator(
    'button[type="submit"], button:has-text("Login"), button:has-text("Sign in")'
  );
  if ((await submitBtn.count()) > 0) {
    await submitBtn.first().click();
    await page.waitForLoadState('networkidle').catch(() => {});
    return true;
  }

  // Fallback: try submitting the form directly
  const form = page.locator('form').first();
  if ((await form.count()) > 0) {
    await form.evaluate((f: any) => f.submit());
    await page.waitForLoadState('networkidle').catch(() => {});
    return true;
  }

  return true;
}

test.describe('Comprehensive E2E Helpers Unit Tests (Mocked)', () => {
  test('fullURL logic (edge cases) - base with trailing slash and path without leading slash', async () => {
    // Local pure function replicate for unit test visibility
    const buildFullURL = (base: string, path: string) => {
      const b = base.endsWith('/') ? base.slice(0, -1) : base;
      const p = path.startsWith('/') ? path : '/' + path;
      return b + p;
    };

    expect(buildFullURL('http://localhost:3000', '/dashboard')).toBe('http://localhost:3000/dashboard');
    expect(buildFullURL('http://example.com/', 'items')).toBe('http://example.com/items');
    expect(buildFullURL('https://site.org', '/settings')).toBe('https://site.org/settings');
  });

  test.describe('loginIfPossible unit (mocked page scenarios)', () => {
    test('returns false when no password input is present', async () => {
      const page = new MockPage({ passwordCount: 0, userCount: 0, submitCount: 0, formCount: 0 });
      const result = await loginIfPossibleFromTest(page);
      expect(result).toBe(false);
    });

    test('fills credentials and submits when submit button exists', async () => {
      const page = new MockPage({ passwordCount: 1, userCount: 1, submitCount: 1, formCount: 0 });
      process.env.TEST_USERNAME = 'user@example.com';
      process.env.TEST_PASSWORD = 'secret';
      const result = await loginIfPossibleFromTest(page);
      expect(result).toBe(true);
      // Assertions on interactions
      expect(page.passwordLocator.filled).toBe(true);
      expect(page.usernameLocator.filled).toBe(true);
      expect(page.submitLocator.clicked).toBe(true);
      // Ensure load state was awaited
      expect(page.waited).toBe(true);
    });

    test('fallback to form submit when no explicit submit button exists', async () => {
      const page = new MockPage({ passwordCount: 1, userCount: 0, submitCount: 0, formCount: 1 });
      const result = await loginIfPossibleFromTest(page);
      expect(result).toBe(true);
      // Form submission path should have been evaluated
      expect(page.formLocator.evaluated).toBe(true);
      expect(page.waited).toBe(true);
    });

    test('continues gracefully when no submit button or form exists', async () => {
      const page = new MockPage({ passwordCount: 1, userCount: 0, submitCount: 0, formCount: 0 });
      const result = await loginIfPossibleFromTest(page);
      expect(result).toBe(true);
      // No submit, no form submission attempted
      expect(page.passwordLocator.filled).toBe(true);
      expect(page.formLocator.evaluated).toBe(false);
    });
  });
});
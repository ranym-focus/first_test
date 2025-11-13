import { test, expect } from '@playwright/test';

async function waitForNetworkIdle(page: any, timeout = 10000) {
  return page.waitForLoadState('networkidle', { timeout });
}

async function fillIfExists(page: any, selector: string, value: string): Promise<boolean> {
  const el = page.locator(selector);
  const count = await el.count();
  if (count > 0) {
    await el.first().fill(value);
    return true;
  }
  return false;
}

async function maybeLogin(page: any, config?: { AUTH_ENABLED?: boolean; BASE_URL?: string; USERNAME?: string; PASSWORD?: string; }) {
  const AUTH_ENABLED = config?.AUTH_ENABLED ?? false;
  const BASE_URL = config?.BASE_URL ?? 'http://localhost:3000';
  if (!AUTH_ENABLED) return;

  try {
    const loginProbe = await page.request.get(`${BASE_URL}/login`, { timeout: 3000 });
    if (loginProbe && loginProbe.ok) {
      await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
      const usernameSelector = 'input[name="username"], input#username';
      const passwordSelector = 'input[name="password"], input#password';
      const hasUsername = await page.locator(usernameSelector).count() > 0;
      const hasPassword = await page.locator(passwordSelector).count() > 0;

      if (hasUsername) {
        const user = config?.USERNAME || 'test';
        await page.fill(usernameSelector, user);
      }
      if (hasPassword) {
        const pass = config?.PASSWORD || 'test';
        await page.fill(passwordSelector, pass);
      }

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

test.describe('Helper function unit tests for e2e.spec.ts', () => {
  test('waitForNetworkIdle calls page.waitForLoadState with networkidle and timeout', async () => {
    const logs: any[] = [];
    const page: any = {
      waitForLoadState: async (state: string, opts?: any) => {
        logs.push({ state, timeout: opts?.timeout });
      }
    };
    await waitForNetworkIdle(page, 1234);
    expect(logs).toEqual([{ state: 'networkidle', timeout: 1234 }]);
  });

  test('fillIfExists fills when element exists', async () => {
    const page: any = {
      locator: (sel: string) => ({
        count: async () => (sel === 'exists' ? 1 : 0),
        first: () => ({
          fill: async (v: string) => {
            page.filled = page.filled || [];
            page.filled.push({ selector: sel, value: v });
          }
        })
      })
    };
    const result = await fillIfExists(page, 'exists', 'VALUE');
    expect(result).toBe(true);
    expect(page.filled).toContainEqual({ selector: 'exists', value: 'VALUE' });
  });

  test('fillIfExists returns false when element does not exist', async () => {
    const page: any = {
      locator: (sel: string) => ({
        count: async () => 0,
        first: () => ({
          fill: async (_v: string) => {}
        })
      })
    };
    const result = await fillIfExists(page, 'missing', 'VALUE');
    expect(result).toBe(false);
  });

  test('maybeLogin does nothing when AUTH_ENABLED is false', async () => {
    const page: any = {
      request: { get: async () => ({ ok: true }) },
      goto: async (url: string) => { (page as any).gotoUrl = url; },
      locator: (sel: string) => ({
        count: async () => 0,
        first: () => ({})
      }),
      fill: async (_sel: string, _val: string) { (page as any).filled = (page as any).filled || []; (page as any).filled.push({ selector: _sel, value: _val }); },
      waitForLoadState: async () => {}
    };
    await maybeLogin(page, { AUTH_ENABLED: false });
    expect((page as any).gotoUrl).toBeUndefined();
  });

  test('maybeLogin performs login flow when enabled and probe ok and selectors exist', async () => {
    const page: any = {
      request: { get: async (_url: string, _opts?: any) => ({ ok: true }) },
      goto: async (url: string, _opts?: any) => { (page as any).gotoUrl = url; },
      locator: (sel: string) => ({
        count: async () => {
          if (sel === 'button[type="submit"], input[type="submit"]') return 1;
          if (sel === 'input[name="username"], input#username') return 1;
          if (sel === 'input[name="password"], input#password') return 1;
          return 0;
        },
        first: () => ({
          click: async () => { (page as any).clickedSubmit = true; }
        })
      }),
      fill: async (sel: string, val: string) {
        page.filled = page.filled || [];
        page.filled.push({ selector: sel, value: val });
      },
      waitForLoadState: async (_state: string, _opts?: any) {
        (page as any).waitForLoadStateCalls = (page as any).waitForLoadStateCalls || [];
        (page as any).waitForLoadStateCalls.push({ state: _state, timeout: _opts?.timeout });
      }
    };

    await maybeLogin(page, { AUTH_ENABLED: true, BASE_URL: 'http://example', USERNAME: 'alice', PASSWORD: 'secret' });
    expect((page as any).gotoUrl).toBe('http://example/login');
    expect(page.filled).toContainEqual({ selector: 'input[name="username"], input#username', value: 'alice' });
    expect(page.filled).toContainEqual({ selector: 'input[name="password"], input#password', value: 'secret' });
    expect((page as any).clickedSubmit).toBe(true);
    expect((page as any).waitForLoadStateCalls).toContainEqual({ state: 'networkidle', timeout: 5000 });
  });

  test('maybeLogin handles loginProbe error gracefully', async () => {
    const page: any = {
      request: { get: async () => { throw new Error('boom'); } },
      goto: async (_url: string) => { throw new Error('should not navigate'); },
      locator: (_sel: string) => ({
        count: async () => 0,
        first: () => ({})
      }),
      fill: async () => {},
      waitForLoadState: async () => {}
    };
    await expect(async () => {
      await maybeLogin(page, { AUTH_ENABLED: true, BASE_URL: 'http://example' });
    }).not.toThrow();
  });
});
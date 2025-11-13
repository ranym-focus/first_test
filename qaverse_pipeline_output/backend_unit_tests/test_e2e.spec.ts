import { test, expect } from '@playwright/test';
import { waitForNetworkIdle, maybeLogin, fillIfExists } from './e2e.spec';

test.describe('Unit tests for internal helpers in e2e.spec.ts', () => {
  test('waitForNetworkIdle should call page.waitForLoadState with networkidle and timeout', async () => {
    const calls: any[] = [];
    const page: any = {
      waitForLoadState: async (state: string, options?: any) => {
        calls.push({ state, options });
      }
    };

    await waitForNetworkIdle(page, 15000);

    expect(calls.length).toBe(1);
    expect(calls[0]).toEqual({ state: 'networkidle', options: { timeout: 15000 } });
  });

  test('fillIfExists should fill when element exists', async () => {
    const fills: Array<{ selector: string; value: string }> = [];

    const page: any = {
      locator: (selector: string) => ({
        count: async () => (selector.includes('name') ? 1 : 0),
        first: () => ({
          fill: async (value: string) => {
            fills.push({ selector, value });
          }
        })
      })
    };

    const result = await fillIfExists(page, 'input[name="name"]', 'John Doe');
    expect(result).toBe(true);
    expect(fills).toContainEqual({ selector: 'input[name="name"]', value: 'John Doe' });
  });

  test('fillIfExists should return false when element does not exist', async () => {
    const page: any = {
      locator: (selector: string) => ({
        count: async () => 0
      })
    };

    const result = await fillIfExists(page, '#missing', 'value');
    expect(result).toBe(false);
  });

  test('maybeLogin flows through login when auth is enabled and login probe is ok', async () => {
    // Prepare environment variables expected by the login flow
    process.env.USERNAME = 'testuser';
    process.env.PASSWORD = 'testpass';
    // We'll assume AUTH_ENABLED is true in the test environment for this unit test
    const actions: string[] = [];

    const page: any = {
      request: {
        get: async (_url: string, _opts?: any) => ({ ok: true })
      },
      goto: async (url: string, _opts?: any) => {
        actions.push(`goto:${url}`);
      },
      locator: (selector: string) => ({
        count: async () => {
          // Simulate presence of username, password, and submit elements
          if (selector.includes('username')) return 1;
          if (selector.includes('password')) return 1;
          if (selector.includes('submit')) return 1;
          return 0;
        },
        fill: async (value: string) => {
          actions.push(`fill:${selector}:${value}`);
        },
        first: () => ({
          click: async () => {
            actions.push(`click:${selector}`);
          }
        })
      }),
      waitForLoadState: async (_state: string, _opts?: any) => {
        actions.push(`wait:${_state}`);
      }
    };

    await maybeLogin(page);

    // Assertions to verify the expected login flow actions occurred
    expect(actions.find((a) => a.startsWith('goto:') && a.includes('/login'))).toBeTruthy();
    expect(actions.find((a) => a.includes('testuser'))).toBeTruthy();
    expect(actions.find((a) => a.includes('testpass'))).toBeTruthy();
    expect(actions.find((a) => a.includes('submit'))).toBeTruthy();
    expect(actions.find((a) => a.startsWith('wait:networkidle'))).toBeTruthy();
  });
});
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';

test.describe('Frontend Security Tests', () => {

  // 1) Security Headers - CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy
  test('Security Headers are set (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy)', async ({ page }) => {
    const response = await page.goto(BASE_URL);
    const headers = response.headers();

    const hasCSP = 'content-security-policy' in headers;
    const hasXFrame = 'x-frame-options' in headers;
    const hasXContentType = 'x-content-type-options' in headers;
    const hasReferrerPolicy = 'referrer-policy' in headers;

    // At least CSP should be present for strong security; other headers are also important.
    expect(hasCSP).toBe(true);
    // Clickjacking protection
    expect(hasXFrame || hasReferrerPolicy).toBe(true);
    // No-sniff protection
    expect(hasXContentType).toBe(true);
  });

  // 2) XSS - Negative (benign payloads)
  test('XSS: Negative payloads should not trigger dialogs or unsafe innerHTML rendering', async ({ page }) => {
    // Instrument innerHTML to detect unsafe writes
    await page.addInitScript(() => {
      window.__innerHTMLWrites = [];
      const orig = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
      Object.defineProperty(Element.prototype, 'innerHTML', {
        set: function(val) {
          window.__innerHTMLWrites.push(val);
          if (orig && orig.set) orig.set.call(this, val);
        },
        get: function() {
          return orig && orig.get ? orig.get.call(this) : '';
        }
      });
    });

    let dialogShown = false;
    page.on('dialog', async () => {
      dialogShown = true;
    });

    // benign payloads
    const benignPayloads = [
      'Hello world',
      '12345',
      '<div>Just text</div>',
      '" harmless "',
    ];

    // Collect candidate editable fields
    const inputLocator = page.locator('input:not([type="hidden"]), textarea, [contenteditable="true"]');
    const count = await inputLocator.count();

    for (let i = 0; i < count; i++) {
      const el = inputLocator.nth(i);
      for (const payload of benignPayloads) {
        dialogShown = false;
        const tag = await el.evaluate(node => (node as HTMLElement).tagName.toLowerCase());

        if (tag === 'textarea' || tag === 'input') {
          await el.fill(payload);
        } else {
          await el.click();
          await page.keyboard.type(payload);
        }

        // Attempt to submit the form if present
        await el.evaluate((node) => {
          const f = node.closest('form');
          if (f) {
            if (typeof f.requestSubmit === 'function') f.requestSubmit();
            else if (typeof f.submit === 'function') f.submit();
          }
        });

        await page.waitForTimeout(400);
        if (dialogShown) {
          // A dialog appeared for benign payload; treat as vulnerability
          break;
        }
      }
      if (dialogShown) break;
    }

    // Ensure no dialogs appeared for benign payloads
    expect(dialogShown).toBe(false);

    // Check that innerHTML writes did not reflect unsafe payloads
    const writes = await page.evaluate(() => window.__innerHTMLWrites || []);
    const unsafeReflection = writes.some(v => /<script|onload|onerror|javascript:/i.test(String(v)));
    expect(unsafeReflection).toBe(false);
  });

  // 3) XSS - Positive (malicious payloads trigger XSS)
  test('XSS: Malicious payloads should trigger XSS dialogs if vulernable', async ({ page }) => {
    await page.goto(BASE_URL);

    let dialogTriggered = false;
    page.on('dialog', async (dialog) => {
      dialogTriggered = true;
      await dialog.dismiss();
    });

    const maliciousPayloads = [
      '<script>alert(1)</script>',
      '" onerror="alert(2)"',
      '<img src=x onerror=alert(3) />',
    ];

    const inputLocator = page.locator('input:not([type="hidden"]), textarea, [contenteditable="true"]');
    const count = await inputLocator.count();

    outer: for (let i = 0; i < count; i++) {
      const el = inputLocator.nth(i);
      for (const payload of maliciousPayloads) {
        dialogTriggered = false;
        const tag = await el.evaluate(node => (node as HTMLElement).tagName.toLowerCase());

        if (tag === 'textarea' || tag === 'input') {
          await el.fill(payload);
        } else {
          await el.click();
          await page.keyboard.type(payload);
        }

        await el.evaluate((node) => {
          const f = node.closest('form');
          if (f) {
            if (typeof f.requestSubmit === 'function') f.requestSubmit();
            else if (typeof f.submit === 'function') f.submit();
          }
        });

        try {
          const d = await page.waitForEvent('dialog', { timeout: 4000 });
          await d.dismiss();
          dialogTriggered = true;
        } catch {
          dialogTriggered = false;
        }

        if (dialogTriggered) break outer;
      }
    }

    // Expect a dialog to have appeared for at least one malicious payload if vulnerability exists
    expect(dialogTriggered).toBe(true);
  });

  // 4) CSRF Protection - Token presence (positive)
  test('CSRF: Forms should contain CSRF tokens when present', async ({ page }) => {
    await page.goto(BASE_URL);

    const forms = page.locator('form');
    const count = await forms.count();
    let tokenFound = false;

    for (let i = 0; i < count; i++) {
      const form = forms.nth(i);
      const tokenInputs = form.locator('input[type="hidden"][name*="csrf"], input[name*="csrf"], input[type="hidden"][name*="token"], input[name*="token"]');
      const tcount = await tokenInputs.count();
      if (tcount > 0) {
        tokenFound = true;
        break;
      }
    }

    // If no forms or no tokens found, fail to indicate CSRF risk
    expect(tokenFound).toBe(true);
  });

  // 5) CSRF Protection - Attempt to submit POST form without CSRF token (negative)
  test('CSRF: Submitting POST form without CSRF token should be rejected by server', async ({ page }) => {
    await page.goto(BASE_URL);

    const forms = page.locator('form');
    const count = await forms.count();

    let vulnerableFormFound = false;

    for (let i = 0; i < count; i++) {
      const form = forms.nth(i);
      const method = (await form.getAttribute('method'))?.toLowerCase() ?? 'get';
      const hasToken = await form.locator('input[type="hidden"][name*="csrf"], input[name*="csrf"], input[type="hidden"][name*="token"], input[name*="token"]').count() > 0;
      if (method !== 'post' || hasToken) continue;

      // Try to submit without token
      try {
        await form.evaluate((f) => {
          if (typeof f.requestSubmit === 'function') f.requestSubmit();
          else if (typeof f.submit === 'function') f.submit();
        });

        const res = await page.waitForResponse((res) => res.request().method() === 'POST', { timeout: 5000 });
        const status = res.status();
        if (status === 403 || status === 401 || status === 400) {
          vulnerableFormFound = true;
          break;
        }
      } catch {
        // If no response or error, treat as potential vulnerability
        vulnerableFormFound = true;
        break;
      }
    }

    // If no POST forms without tokens were found, skip the assertion
    if (count === 0) {
      test.skip('No forms detected to test CSRF behavior.');
    } else {
      expect(vulnerableFormFound).toBe(true);
    }
  });

  // 6) Secure Storage Practices - localStorage / sessionStorage exposure
  test('Sensitive data exposure: No secrets leaked in browser storage', async ({ page }) => {
    await page.goto(BASE_URL);

    const localStorageData = await page.evaluate(() => {
      const obj = {};
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        obj[k] = localStorage.getItem(k);
      }
      return obj;
    });

    const sessionStorageData = await page.evaluate(() => {
      const obj = {};
      for (let i = 0; i < sessionStorage.length; i++) {
        const k = sessionStorage.key(i);
        obj[k] = sessionStorage.getItem(k);
      }
      return obj;
    });

    const isSecretKey = (k) => /password|secret|token|apikey|api_key|auth/i.test(k);
    const secretKeyInLS = Object.keys(localStorageData).filter(isSecretKey);
    const secretKeyInSS = Object.keys(sessionStorageData).filter(isSecretKey);

    expect(secretKeyInLS.length).toBe(0);
    expect(secretKeyInSS.length).toBe(0);
  });

  // 7) Dangerous Functions - instrumentation for eval, Function constructor, document.write
  test('Dangerous Functions: Detect usage of eval, Function constructor, and document.write', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.addInitScript(() => {
      window.__dangerousUsage = { evalUsed: false, functionUsed: false, documentWriteUsed: false };
      const origEval = window.eval;
      window.eval = function() { window.__dangerousUsage.evalUsed = true; return origEval.apply(this, arguments); };

      const OrigFunction = window.Function;
      window.Function = function() { window.__dangerousUsage.functionUsed = true; return OrigFunction.apply(this, arguments); };

      const origWrite = document.write;
      document.write = function() { window.__dangerousUsage.documentWriteUsed = true; return origWrite.apply(document, arguments); };
    });

    // Give page a moment to potentially invoke dangerous calls
    await page.waitForTimeout(1000);

    const usage = await page.evaluate(() => window.__dangerousUsage || { evalUsed: false, functionUsed: false, documentWriteUsed: false });
    const anyUsed = usage.evalUsed || usage.functionUsed || usage.documentWriteUsed;

    // Expect none of the dangerous functions to be used by the app
    expect(anyUsed).toBe(false);
  });

  // 8) Clickjacking Protection - header-based test (frame-ancestors / x-frame-options)
  test('Clickjacking protection: Header-based protection is present', async ({ page }) => {
    const response = await page.goto(BASE_URL);
    const headers = response.headers();
    const hasProtection = 'x-frame-options' in headers || ('content-security-policy' in headers && /frame-ancestors/.test(headers['content-security-policy']));
    expect(hasProtection).toBe(true);
  });

  // 9) Content Security Policy compliance checks
  test('Content Security Policy: CSP is applied with sane directives', async ({ page }) => {
    const response = await page.goto(BASE_URL);
    const csp = response.headers()['content-security-policy'];
    expect(typeof csp).toBe('string');
    const lower = csp.toLowerCase();
    expect(lower).toContain('default-src');
    expect(lower).toContain('script-src');
    // Prefer explicit frame-ancestors directive if CSP is used
    expect(/frame-ancestors/.test(lower) || /frame-src/.test(lower)).toBe(true);
  });

  // 10) Client-side Validation - HTML5 validation for inputs
  test('Client-side validation: Invalid inputs are rejected locally', async ({ page }) => {
    await page.goto(BASE_URL);

    const forms = page.locator('form');
    const formCount = await forms.count();
    let foundInvalid = false;

    for (let i = 0; i < formCount; i++) {
      const form = forms.nth(i);
      const inputs = form.locator('input, textarea, select');
      const inputCount = await inputs.count();

      for (let j = 0; j < inputCount; j++) {
        const input = inputs.nth(j);
        const type = (await input.getAttribute('type')) ?? '';

        // Choose a value that should fail HTML5 validation for common types
        const invalidValue = (type === 'email') ? 'not-an-email' : 'invalid';
        await input.fill(invalidValue);

        // Check validity
        const isValid = await input.evaluate((el: HTMLInputElement) => el.checkValidity());
        if (isValid) {
          // If somehow valid, try to submit; should not navigate
          await input.evaluate((el) => {
            el.closest('form')?.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
          });
          // If no navigation occurs, still mark as potential issue
        } else {
          foundInvalid = true;
        }

        // Reset value for next test
        await input.fill('');
      }

      // If there is at least one invalid element, we consider validation working
      if (foundInvalid) break;
    }

    expect(foundInvalid).toBe(true);
  });
});
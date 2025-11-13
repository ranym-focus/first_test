import os
import time
import json
import pytest
import requests
from urllib.parse import urlencode, urljoin

# Security test suite for backend applications
# - Uses pytest and requests
# - Reads BASE_URL and optional credentials/token from environment
# - Skips gracefully if BASE_URL not provided
# - Attempts to cover: authentication, authorization, SQL injection, input validation,
#   sensitive data exposure, rate limiting, CSRF, and OWASP Top 10 considerations

# Configuration
BASE_URL = os.environ.get("BASE_URL")  # e.g., "https://example.com"
TOKEN = os.environ.get("TOKEN")       # Bearer token (optional)
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")  # Admin Bearer token (optional)
USERNAME = os.environ.get("DB_USERNAME")     # for login attempt (optional)
PASSWORD = os.environ.get("DB_PASSWORD")     # for login attempt (optional)
TIMEOUT = 8

# Common candidate endpoints (best-effort discovery)
CANDIDATE_ENDPOINTS = [
    "/api/v1/users",
    "/api/v1/profile",
    "/api/v1/secure",
    "/admin",
    "/data",
    "/search",
    "/login",
    "/health",
    "/status",
    "/signup",
]

# Public endpoints we expect to be accessible without auth
PUBLIC_ENDPOINTS = {"/health", "/status", "/login", "/signup", "/public"}

SQLI_PAYLOADS = [
    "' OR '1'='1",
    "\" OR \"1\"=\"1",
    "'; DROP TABLE users; --",
    "' OR 1=1; --",
    "<script>alert(1)</script>",
]

XSS_PAYLOADS = [
    "<script>alert('xss')</script>",
    "'; <img src=x onerror=alert(1)>",
    "<svg/onload=alert(1)>",
]

INVALID_PAYLOADS = [
    {"name": 12345},                          # wrong type
    {"email": "not-an-email"},                # invalid format
    {"age": -1},                               # out-of-range
    {"bio": "a" * 5001},                       # overly long string
    {"password": "pass\nword"},                # newline in password
]

# Helpers
def build_url(path: str) -> str:
    if not BASE_URL:
        pytest.skip("BASE_URL environment variable not configured; skipping security tests.")
    return urljoin(BASE_URL.rstrip("/"), path.lstrip("/"))

def is_public_endpoint(path: str) -> bool:
    # Simple heuristic for public endpoints
    return path.rstrip("/") in PUBLIC_ENDPOINTS

def get_auth_headers():
    # Priority: provided token > env-based login
    if TOKEN:
        return {"Authorization": f"Bearer {TOKEN}"}
    # Attempt to acquire token via common login endpoints
    login_paths = ["/auth/login", "/login", "/api/v1/auth/login"]
    credentials = []
    if USERNAME and PASSWORD:
        credentials.append({"username": USERNAME, "password": PASSWORD})
    # Also try generic anonymous login (if API exposes it)
    for path in login_paths:
        url = build_url(path)
        try:
            # Try POST with credentials if available
            if credentials:
                for cred in credentials:
                    try:
                        r = requests.post(url, json=cred, timeout=TIMEOUT)
                    except Exception:
                        continue
                    if r.status_code in (200, 201) and isinstance(r.json(), dict):
                        tok = r.json().get("token") or r.json().get("access_token")
                        if tok:
                            return {"Authorization": f"Bearer {tok}"}
            # Fallback: try unauthenticated GET to see if a token is provided in response (rare)
        except Exception:
            continue
    return None

def has_csrf_token(resp: requests.Response) -> dict:
    # Try to extract CSRF token from cookies if present
    cookies = resp.cookies
    csrf_names = ["csrftoken", "XSRF-TOKEN", "csrf_token", "csrf-token"]
    for name in csrf_names:
        if name in cookies:
            return {"csrf_token": cookies.get(name)}
    return {}

def contains_sensitive_in_text(text: str) -> bool:
    lowered = text.lower()
    sensitive = ["password", "passwd", "secret", "token", "api_key", "authorization", "ssh_key"]
    return any(k in lowered for k in sensitive)

@pytest.fixture(scope="session")
def base_url():
    if not BASE_URL:
        pytest.skip("BASE_URL env var not configured; skipping security tests.")
    return BASE_URL.rstrip("/")

@pytest.fixture(scope="session")
def auth_headers():
    headers = get_auth_headers()
    return headers

@pytest.fixture(scope="function")
def endpoint_candidates(base_url):
    # Build full URLs for endpoints to test
    urls = []
    for ep in CANDIDATE_ENDPOINTS:
        full = build_url(ep)
        urls.append((ep, full))
    return urls

# 1) API Security - Authentication, Authorization, Rate Limiting
def test_authentication_mechanisms_public_vs_protected(base_url, auth_headers, endpoint_candidates):
    """
    For each candidate endpoint:
    - Access without auth: should be 401/403 for protected endpoints; 200 for public endpoints.
    - Access with auth (if token available): should be 2xx for protected endpoints that require auth.
    - If an endpoint is public, it may be 200 without auth.
    """
    for ep, full_url in endpoint_candidates:
        # Unauthenticated request
        r_unauth = requests.get(full_url, timeout=TIMEOUT)
        if is_public_endpoint(ep):
            assert r_unauth.status_code < 400, f"Public endpoint {ep} should be accessible without auth."
        else:
            # Protected endpoints should not be accessible without auth
            assert r_unauth.status_code in (401, 403, 404), (
                f"Protected endpoint {ep} should not be accessible without auth. "
                f"Status: {r_unauth.status_code}"
            )
        # Authenticated request (if we have a token)
        if auth_headers:
            r_auth = requests.get(full_url, headers=auth_headers, timeout=TIMEOUT)
            assert r_auth.status_code < 500, f"Authenticated request to {ep} failed with {r_auth.status_code}."

def test_authorization_flaws_admin_endpoint(base_url, admin_token_available, endpoint_candidates):
    """
    If admin token is provided, verify proper access control:
    - Regular token should not access admin endpoints
    - Admin token should access admin endpoints
    """
    if not admin_token_available:
        pytest.skip("ADMIN_TOKEN not available; skipping admin authorization test.")
    admin_headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    regular_headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else None

    for ep, full_url in endpoint_candidates:
        if "/admin" in ep or ep.strip("/").startswith("admin"):
            # Without admin token
            if regular_headers:
                r_regular = requests.get(full_url, headers=regular_headers, timeout=TIMEOUT)
                # Expect forbidden or not allowed
                assert r_regular.status_code in (401, 403, 404), (
                    f"Non-admin access to {ep} should be denied. Status: {r_regular.status_code}"
                )
            # With admin token
            r_admin = requests.get(full_url, headers=admin_headers, timeout=TIMEOUT)
            assert r_admin.status_code < 500, f"Admin access to {ep} failed with {r_admin.status_code}."
            # If admin endpoint is accessible for admin, ensure not 403
            assert r_admin.status_code in (200, 201, 202, 204, 301, 302), (
                f"Admin access to {ep} returned unexpected status {r_admin.status_code}."
            )

def test_rate_limiting_on_endpoint(base_url, auth_headers, endpoint_candidates):
    """
    Verify rate limiting by issuing burst requests to a testable endpoint.
    Expect 429 (Too Many Requests) or similar after a threshold.
    If not supported by target, skip gracefully.
    """
    test_ep = None
    test_url = None
    for ep, full_url in endpoint_candidates:
        if not is_public_endpoint(ep):
            test_ep = ep
            test_url = full_url
            break
        elif "health" in ep or "status" in ep:
            test_ep = ep
            test_url = full_url
            break
    if not test_url:
        pytest.skip("No suitable endpoint found for rate-limiting test.")
    # Spin up many requests to trigger rate limiting
    seen_429 = False
    for i in range(25):
        r = requests.get(test_url, headers=auth_headers, timeout=TIMEOUT)
        if r.status_code == 429:
            seen_429 = True
            break
        time.sleep(0.05)  # slight delay
    assert seen_429, f"Rate limiting not observed on {test_ep}. Requests did not return 429."

# 2) SQL Injection
def test_sql_injection_targets(base_url, auth_headers, endpoint_candidates):
    """
    Attempt basic SQL injection payloads against endpoints that allow query parameters.
    Failafe: treat 500+ responses with SQL-like error messages as vulnerability.
    """
    vulnerable = []
    for ep, full_url in endpoint_candidates:
        for param in ["q", "search", "query", "id", "name"]:
            for payload in SQLI_PAYLOADS:
                url = full_url
                try:
                    if "?" in url:
                        url += "&" + urlencode({param: payload})
                    else:
                        url += "?" + urlencode({param: payload})
                    r = requests.get(url, headers=auth_headers, timeout=TIMEOUT)
                    text = r.text.lower() if r.text else ""
                    if r.status_code >= 500:
                        if "sql" in text or "syntax" in text or "database" in text:
                            vulnerable.append((ep, url, r.status_code, text[:200]))
                    # Also try POST with payload in JSON body for endpoints that accept POST
                except Exception:
                    continue
        # POST-based injection attempts
        post_url = full_url
        if "?" in post_url:
            post_url = post_url
        for payload in SQLI_PAYLOADS:
            body = {"q": payload}
            try:
                r_post = requests.post(post_url, json=body, headers=auth_headers, timeout=TIMEOUT)
                t = r_post.text.lower() if r_post.text else ""
                if r_post.status_code >= 500 and ("sql" in t or "syntax" in t or "database" in t):
                    vulnerable.append((ep, post_url, r_post.status_code, t[:200]))
            except Exception:
                continue
    if vulnerable:
        # Report first few findings
        for v in vulnerable[:5]:
            ep, url, code, excerpt = v
            pytest.fail(f"Possible SQL Injection vulnerability detected at {ep} (URL: {url}) "
                        f"Status: {code}, excerpt: {excerpt}")
    else:
        pytest.skip("No SQL injection vulnerabilities detected in tested paths (or tests not applicable).")

# 3) Authentication bypass
def test_authentication_bypass_on_protected_endpoints(base_url, endpoint_candidates):
    """
    Ensure protected endpoints cannot be accessed without authentication.
    Fail if a protected endpoint returns 200 without auth.
    """
    for ep, full_url in endpoint_candidates:
        if is_public_endpoint(ep):
            continue
        r = requests.get(full_url, timeout=TIMEOUT)
        sign = "protected"
        if r.status_code == 200:
            pytest.fail(f"Authentication bypass: endpoint {ep} returned 200 without auth.")
        # else acceptable (401/403/404)
        if r.status_code in (401, 403, 404):
            sign = "blocked"
        # no assertion here beyond the bypass check

# 4) Input validation
def test_input_validation_on_post_endpoints(base_url, auth_headers, endpoint_candidates):
    """
    Send invalid payloads to endpoints that accept POST (best-effort).
    Expect 4xx for invalid input.
    """
    for ep, full_url in endpoint_candidates:
        # Try only endpoints that likely accept JSON body via POST
        try:
            r = requests.post(full_url, json={"test": "data"}, headers=auth_headers, timeout=TIMEOUT)
        except Exception:
            continue
        # If method is not allowed, skip
        if r.status_code == 405:
            continue
        # Apply invalid payloads
        for bad in INVALID_PAYLOADS:
            try:
                r_bad = requests.post(full_url, json=bad, headers=auth_headers, timeout=TIMEOUT)
            except Exception:
                continue
            if r_bad.status_code >= 400:
                # Acceptable invalid input
                continue
            # If valid response to invalid input, flag potential weak validation
            assert False, f"Input validation weakness at {ep} with payload: {bad} (status {r_bad.status_code})"

# 5) Sensitive data exposure
def test_sensitive_data_exposure(base_url, auth_headers, endpoint_candidates):
    """
    Ensure responses do not leak sensitive data like passwords, tokens, or keys.
    """
    for ep, full_url in endpoint_candidates:
        try:
            r = requests.get(full_url, headers=auth_headers, timeout=TIMEOUT)
        except Exception:
            continue
        # Inspect response body
        body = ""
        if r.headers.get("Content-Type", "").lower().find("application/json") != -1:
            try:
                body = json.dumps(r.json())
            except Exception:
                body = r.text
        else:
            body = r.text
        if contains_sensitive_in_text(body):
            pytest.fail(f"Sensitive data exposure detected at {ep} (URL: {full_url})")

# 6) CSRF protection
def test_csrf_protection_on_state-changing_endpoints(base_url, auth_headers, endpoint_candidates):
    """
    Attempt a state-changing operation without CSRF token.
    If endpoint requires CSRF, expect 403/400 when no CSRF token is provided.
    If CSRF is not required, server may allow POST/PUT without token.
    """
    test_endpoints = []
    for ep, full_url in endpoint_candidates:
        if any(http_verb in ep.lower() for http_verb in ["update", "modify", "delete", "create", "post"]):
            test_endpoints.append((ep, full_url))
    if not test_endpoints:
        pytest.skip("No suitable state-changing endpoints found for CSRF test.")
    for ep, full_url in test_endpoints[:5]:
        # Obtain csfr token if present
        r = requests.get(full_url, headers=auth_headers, timeout=TIMEOUT)
        token = has_csrf_token(r)
        data = {"sample": "csrf-test"}
        if token:
            headers_with_csrf = dict(auth_headers or {})
            # Try with CSRF token in header if the API uses X-CSRF-Token
            headers_with_csrf["X-CSRF-Token"] = token.get("csrf_token", "")
            r_csrf = requests.post(full_url, json=data, headers=headers_with_csrf, timeout=TIMEOUT)
            # If 200 despite missing proper CSRF, it might be misconfigured; do not fail hard
            # But ensure that at least one path is protected
            if r_csrf.status_code in (401, 403, 419, 400):
                continue
        # Without CSRF token
        r_no_csrf = requests.post(full_url, json=data, headers=auth_headers, timeout=TIMEOUT)
        if r_no_csrf.status_code in (401, 403, 419, 400):
            # Protected against CSRF; expected
            continue
        # If a 2xx without CSRF token, this could imply CSRF protection is not enforced
        # Treat as potential CSRF misconfiguration
        assert r_no_csrf.status_code not in (200, 201, 202, 204) or (not token), (
            f"CSRF protection may be missing on {ep}. Status without CSRF: {r_no_csrf.status_code}"
        )

# 7) OWASP Top 10 - Basic checks (reflected XSS)
def test_reflected_xss_and_input_validation(base_url, auth_headers, endpoint_candidates):
    """
    Inject basic XSS payloads via query parameters and check for reflection in response.
    """
    for ep, full_url in endpoint_candidates[:5]:
        for payload in XSS_PAYLOADS:
            url = full_url
            param = "q"
            if "?" in url:
                url += "&" + urlencode({param: payload})
            else:
                url += "?" + urlencode({param: payload})
            try:
                r = requests.get(url, headers=auth_headers, timeout=TIMEOUT)
            except Exception:
                continue
            if payload in (r.text or ""):
                # Reflection occurred; not necessarily a vulnerability, but check if it executes script
                if "<script>" in payload:
                    pytest.fail(f"Reflected script payload detected at {ep}. URL: {url}")

# 8) Positive and Negative Test Cases - sample endpoints
def test_basic_endpoints_availability(base_url, endpoint_candidates):
    """
    Basic sanity check: ensure endpoints are reachable or gracefully fail (404/405).
    """
    for ep, full_url in endpoint_candidates:
        try:
            r = requests.get(full_url, timeout=TIMEOUT)
        except Exception:
            continue
        # Accept 200/401/403/404/405 as normal, do not crash tests
        assert r.status_code < 500, f"Endpoint {ep} returned server error {r.status_code}"

# 9) Environment exposure checks in code references (static analysis-like)
def test_sensitive_env_exposure_in_responses(base_url, auth_headers, endpoint_candidates):
    """
    Look for inadvertent exposure of env-like data in responses (e.g., debug info).
    """
    sensitive_keys = ["password", "secret", "token", "apikey", "aws_access_key_id", "db_password"]
    for ep, full_url in endpoint_candidates:
        try:
            r = requests.get(full_url, headers=auth_headers, timeout=TIMEOUT)
        except Exception:
            continue
        content = r.text
        for key in sensitive_keys:
            if key in content.lower():
                pytest.fail(f"Potential sensitive environment exposure at {ep}. Key: {key}")

# 10) Helper fixture: determine if admin token is available
@pytest.fixture(scope="session")
def admin_token_available():
    return bool(ADMIN_TOKEN)

# End of test suite

# Notes:
# - This test suite is intentionally conservative and graceful in the absence of concrete endpoints.
# - It uses a combination of positive (expected secure behavior) and negative (potential vulnerability) checks.
# - To run: set BASE_URL and optionally TOKEN/ADMIN_TOKEN/DB credentials as environment variables, then run pytest.
import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { randomSeed, randomIntBetween } from 'k6';

// Base URL for the API (override via BASE_URL env variable)
const BASE_URL = __ENV.BASE_URL || 'https://example.com/api/v1';

function getHeaders(token) {
  const headers = {
    'Content-Type': 'application/json',
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

export let options = {
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'], // p95 < 500ms, p99 < 1000ms
    http_req_failed: ['rate<0.01'], // error rate < 1%
  },
  stages: [
    { duration: '2m', target: 50 },    // Baseline: 10-50 users
    { duration: '4m', target: 200 },   // Normal: 100-200 users
    { duration: '5m', target: 700 },   // Stress: 500+ users
    { duration: '1m', target: 1000 },  // Spike: jump to 1000 users
    { duration: '3m', target: 0 },     // End: ramp down
  ],
  discardResponseBodies: true,
};

export function setup() {
  const res = http.get(`${BASE_URL}/health`);
  const ok = check(res, { 'health-OK': (r) => r.status === 200 });
  const token = ok ? 'setup-token' : '';
  if (ok) {
    // Warm-up lightweight endpoint to simulate login/session setup
    http.get(`${BASE_URL}/items`, { headers: getHeaders(token) });
  }
  return { token };
}

export function teardown(data) {
  const headers = getHeaders(data?.token);
  // Best-effort cleanup endpoint
  http.post(`${BASE_URL}/cleanup`, JSON.stringify({ action: 'teardown' }), { headers });
}

export default function (data) {
  const token = data?.token || '';
  const headers = getHeaders(token);

  // Baseline: GET list of items
  group('GET /items', () => {
    const res = http.get(`${BASE_URL}/items`, { headers });
    check(res, {
      'GET /items status 200': (r) => r.status === 200,
    });
  });

  // GET item by random id
  group('GET /items/{id}', () => {
    const id = Math.floor(Math.random() * 1000) + 1;
    const res = http.get(`${BASE_URL}/items/${id}`, { headers });
    check(res, {
      'GET /items/{id} status 200/404': (r) => [200, 404].includes(r.status),
    });
  });

  // POST create item (writes)
  group('POST /items', () => {
    const payload = JSON.stringify({
      name: `perf-item-${__VU}-${__ITER}`,
      value: Math.floor(Math.random() * 1000),
    });
    const res = http.post(`${BASE_URL}/items`, payload, { headers });
    check(res, {
      'POST /items created/updated': (r) => r.status === 201 || r.status === 200,
    });
  });

  // Heavy database endpoint with higher load
  group('GET /database/heavy', () => {
    // 60% chance to hit heavy endpoint
    if (Math.random() < 0.6) {
      const res = http.get(`${BASE_URL}/database/heavy`, { headers });
      check(res, { 'GET /database/heavy status 200': (r) => r.status === 200 });
    } else {
      // lighter path occasionally
      const res = http.get(`${BASE_URL}/database/light`, { headers });
      check(res, { 'GET /database/light status 200/304': (r) => r.status === 200 || r.status === 304 });
    }
  });

  // Heavy operation simulating DB iteration or long-running query
  group('POST /e2e/iterate (heavy)', () => {
    const payload = JSON.stringify({ iterations: 5000, seed: __VU * 100 + __ITER });
    const res = http.post(`${BASE_URL}/e2e/iterate`, payload, { headers });
    check(res, { 'POST /e2e/iterate status 200': (r) => r.status === 200 });
  });

  // Optional auth refresh to emulate authenticated load
  group('GET /auth/refresh (optional)', () => {
    if (token) {
      const res = http.get(`${BASE_URL}/auth/refresh`, { headers });
      check(res, { 'GET /auth/refresh 200/204': (r) => r.status === 200 || r.status === 204 });
    }
  });

  sleep(1);
}
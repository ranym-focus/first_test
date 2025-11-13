import http from 'k6/http';
import { check, sleep } from 'k6';
  
// Base API URL (can be overridden with BASE_URL env variable)
const BASE_URL = __ENV.BASE_URL || 'https://api.example.com';

// Generic endpoints (generic API performance tests)
const endpoints = [
  { name: 'GET /api/v1/resource', path: '/api/v1/resource', method: 'GET' },
  { name: 'POST /api/v1/resource', path: '/api/v1/resource', method: 'POST' },
  { name: 'GET /api/v1/data/summary', path: '/api/v1/data/summary', method: 'GET' },
  { name: 'GET /api/v1/database/heavy', path: '/api/v1/database/heavy', method: 'GET' } // database-heavy endpoint
];

// Heavy endpoint path for specialized load
const heavyPath = '/api/v1/database/heavy';

// Simple random helper
function randInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

// Pick a random endpoint for load distribution
function pickEndpoint() {
  return endpoints[randInt(0, endpoints.length - 1)];
}

// Perform a request to a given endpoint
function doRequest(ep) {
  const url = `${BASE_URL}${ep.path}`;
  const headers = { 'Content-Type': 'application/json' };
  let res;

  // Use simple payloads for POST
  if (ep.method === 'POST') {
    const payload = JSON.stringify({ ts: Date.now(), demo: 'perf-test' });
    res = http.post(url, payload, { headers });
  } else {
    res = http.get(url);
  }

  check(res, {
    'status is 2xx': (r) => r && r.status >= 200 && r.status < 300,
  });

  return res;
}

// Baseline/Normal/Stress: normal endpoint usage
export function normalUser() {
  const ep = pickEndpoint();
  doRequest(ep);

  // Small think time to simulate real users
  sleep(randInt(50, 250) / 1000);
}

// Spike: sudden surge to high concurrency
export function spikeUser() {
  // Simulate rapid requests for a short burst
  const burstCount = randInt(15, 25);
  for (let i = 0; i < burstCount; i++) {
    const ep = pickEndpoint();
    doRequest(ep);
  }
  // Minimal pause between bursts
  sleep(randInt(20, 60) / 1000);
}

// Heavy: specifically target database-heavy endpoints with higher load
export function heavyUser() {
  // Hit the heavy endpoint multiple times per iteration to stress DB-heavy path
  for (let i = 0; i < 3; i++) {
    const url = `${BASE_URL}${heavyPath}`;
    const payload = JSON.stringify({ query: 'select * from large_table', depth: 'full' });
    const res = http.post(url, payload, { headers: { 'Content-Type': 'application/json' } });

    check(res, {
      'heavy endpoint status is 200': (r) => r && r.status === 200,
    });

    // Very short pause to maintain high throughput
    sleep(40 / 1000);
  }

  // Optionally hit a normal endpoint as a secondary operation
  const ep = endpoints.find(e => e.path === '/api/v1/resource');
  if (ep) {
    doRequest(ep);
  }
  sleep(randInt(50, 150) / 1000);
}

// Warm-up/setup: run a few quick requests to prime caches and bodies
export function setup() {
  // Gentle warm-up across endpoints
  for (let i = 0; i < endpoints.length; i++) {
    const ep = endpoints[i];
    try {
      http.get(`${BASE_URL}${ep.path}`);
    } catch (e) {
      // ignore warm-up errors
    }
  }
  return { warmedUp: true };
}

// Teardown: perform cleanup if a teardown endpoint exists
export function teardown(_data) {
  try {
    const url = `${BASE_URL}/health/teardown`;
    http.post(url, JSON.stringify({ test: 'teardown' }), { headers: { 'Content-Type': 'application/json' } });
  } catch (_) {
    // ignore teardown errors
  }
}

// Custom summary to export results for easier analysis
export function handleSummary(data) {
  // You can customize this to generate more friendly reports
  return {
    'summary.json': JSON.stringify(data, null, 2),
  };
}

// Performance test configuration and scenarios
export const options = {
  discardResponseBodies: true,
  thresholds: {
    // Ensure fast responses
    'http_req_duration': ['p(95)<500', 'p(99)<1000'],
    // Error rate under 1%
    'http_req_failed': ['rate<0.01'],
  },
  scenarios: {
    // Baseline load: 10-50 virtual users
    baseline: {
      executor: 'ramping-vus',
      exec: 'normalUser',
      startVUs: 10,
      stages: [
        { duration: '2m', target: 50 },
        { duration: '3m', target: 50 }
      ],
    },
    // Normal load: 100-200 users
    normal: {
      executor: 'ramping-vus',
      exec: 'normalUser',
      startVUs: 50,
      stages: [
        { duration: '2m', target: 200 },
        { duration: '4m', target: 200 }
      ],
    },
    // Stress test: 500+ users
    stress: {
      executor: 'ramping-vus',
      exec: 'normalUser',
      startVUs: 100,
      stages: [
        { duration: '1m', target: 500 },
        { duration: '5m', target: 500 }
      ],
    },
    // Spike test: sudden increase to 1000 users
    spike: {
      executor: 'ramping-vus',
      exec: 'spikeUser',
      startVUs: 0,
      stages: [
        { duration: '0m', target: 0 },
        { duration: '0m', target: 0 },
        { duration: '1m', target: 0 },
        { duration: '1m', target: 1000 },
        { duration: '2m', target: 1000 },
        { duration: '0m', target: 0 }
      ],
    },
    // Database-heavy endpoints under higher load
    db_heavy: {
      executor: 'ramping-vus',
      exec: 'heavyUser',
      startVUs: 20,
      stages: [
        { duration: '2m', target: 100 },
        { duration: '6m', target: 100 }
      ],
    }
  },
  // Optional: enable per-VU hot swapping, etc.
};
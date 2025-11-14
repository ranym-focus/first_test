import http from 'k6/http';
import { check, sleep } from 'k6';
 
// Base configuration
const BASE_URL = __ENV.BASE_URL || 'http://localhost:3000';
const ENABLE_AUTH = __ENV.ENABLE_AUTH === 'true';
const DB_HEAVY_WEIGHT = parseFloat(__ENV.DB_HEAVY_WEIGHT) || 0.25;
 
// Endpoints (generic placeholders; replace as needed)
const endpoints = [
  { name: 'Health', method: 'GET', url: '/health' },
  { name: 'Get Items', method: 'GET', url: '/api/public/items' },
  { name: 'Create Item', method: 'POST', url: '/api/public/items' },
  { name: 'DB Heavy Query', method: 'GET', url: '/api/db-heavy' }
];
 
// Pick endpoint with weighted distribution: heavy endpoint gets a share defined by DB_HEAVY_WEIGHT,
// the remaining share is distributed uniformly among the other three light endpoints.
function pickEndpoint() {
  const r = Math.random();
  if (r < DB_HEAVY_WEIGHT) {
    return endpoints[3]; // heavy endpoint
  }
  // Pick one of the light endpoints uniformly
  const idx = Math.floor(Math.random() * 3);
  return endpoints[idx];
}
 
export const options = {
  scenarios: {
    baseline: {
      executor: 'ramping-vus',
      startVUs: 10,
      stages: [
        { duration: '2m', target: 50 },
        { duration: '2m', target: 50 },
        { duration: '1m', target: 10 }
      ],
      exec: 'default'
    },
    normal: {
      executor: 'ramping-vus',
      startVUs: 100,
      stages: [
        { duration: '2m', target: 200 },
        { duration: '4m', target: 200 },
        { duration: '1m', target: 100 }
      ],
      exec: 'default'
    },
    stress: {
      executor: 'ramping-vus',
      startVUs: 500,
      stages: [
        { duration: '2m', target: 700 },
        { duration: '5m', target: 700 },
        { duration: '2m', target: 500 },
        { duration: '1m', target: 0 }
      ],
      exec: 'default'
    },
    spike: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 1000 },
        { duration: '2m', target: 1000 },
        { duration: '30s', target: 0 }
      ],
      exec: 'default'
    }
  },
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed: ['rate<0.01']
  }
};
 
export function setup() {
  let token = null;
  if (ENABLE_AUTH) {
    const loginUrl = `${BASE_URL}/auth/login`;
    const credentials = {
      username: __ENV.USERNAME || 'user',
      password: __ENV.PASSWORD || 'pass'
    };
    const payload = JSON.stringify(credentials);
    const headers = { 'Content-Type': 'application/json' };
    try {
      const res = http.post(loginUrl, payload, { headers });
      if (res && res.status >= 200 && res.status < 300) {
        const body = res.json();
        token = body.token || body.access_token || null;
      }
    } catch (e) {
      // Ignore login errors; tests will run unauthenticated if login fails
    }
  }
  return { token };
}
 
export function teardown(data) {
  // Optional: clean up test artifacts if needed
}
 
export default function (data) {
  const endpoint = pickEndpoint();
  const url = BASE_URL + endpoint.url;
  const headers = { 'Content-Type': 'application/json' };
  if (data?.token) {
    headers['Authorization'] = `Bearer ${data.token}`;
  }
 
  let payload = null;
  if (endpoint.method === 'POST') {
    payload = JSON.stringify({
      name: `item-${__VU}-${__ITER}`,
      value: Math.floor(Math.random() * 1000)
    });
  }
 
  const res = http.request(endpoint.method, url, payload, { headers });
  check(res, {
    'status is 2xx': (r) => r.status >= 200 && r.status < 300
  });
 
  // Small pause to simulate user think time
  sleep(1);
}
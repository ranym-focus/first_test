import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const AUTH_TOKEN = __ENV.AUTH_TOKEN || '';

function authHeaders() {
  const h = {};
  if (AUTH_TOKEN) h['Authorization'] = `Bearer ${AUTH_TOKEN}`;
  return h;
}

const ENDPOINTS = [
  { name: 'health', method: 'GET', path: '/health', body: null, headers: {} },
  { name: 'list_users', method: 'GET', path: '/api/v1/users', body: null, headers: {} },
  { name: 'db_heavy', method: 'GET', path: '/api/v1/db-heavy', body: null, headers: {} },
  { name: 'create_user', method: 'POST', path: '/api/v1/users', body: JSON.stringify({ name: 'test', email: 'test@example.com' }), headers: { 'Content-Type': 'application/json' } },
];

// Weighted random selection to simulate baseline, normal, and DB-heavy access patterns
function chooseEndpoint() {
  const r = Math.random();
  let acc = 0;
  const weights = [
    { name: 'health', w: 0.50 },
    { name: 'list_users', w: 0.25 },
    { name: 'db_heavy', w: 0.15 },
    { name: 'create_user', w: 0.10 },
  ];
  for (let i = 0; i < weights.length; i++) {
    acc += weights[i].w;
    if (r <= acc) return ENDPOINTS.find(e => e.name === weights[i].name);
  }
  return ENDPOINTS[0];
}

export function setup() {
  // Optional warm-up of the API
  try {
    http.get(BASE_URL + '/health', { headers: authHeaders() });
  } catch (_) {
    // ignore setup errors
  }
  return { token: AUTH_TOKEN };
}

export function teardown(_data) {
  // Optional cleanup hook
  if (BASE_URL && AUTH_TOKEN) {
    http.post(BASE_URL + '/teardown', null, { headers: { Authorization: `Bearer ${AUTH_TOKEN}` } });
  }
}

export function testUserFlow() {
  const endpoint = chooseEndpoint();
  const url = BASE_URL + endpoint.path;
  const headers = Object.assign({}, endpoint.headers, authHeaders());
  const res = http.request(endpoint.method, url, endpoint.body || null, { headers, tags: { endpoint: endpoint.name } });

  check(res, {
    [`${endpoint.name} status`]: (r) => r.status >= 200 && r.status < 300,
  });

  // Small pause to simulate think time
  sleep(0.25);
}

export function testDBHeavyFlow() {
  const endpoint = ENDPOINTS.find(e => e.name === 'db_heavy');
  const url = BASE_URL + endpoint.path;
  const headers = Object.assign({}, endpoint.headers, authHeaders());
  const res = http.request(endpoint.method, url, endpoint.body || null, { headers, tags: { endpoint: endpoint.name } });

  check(res, {
    [`${endpoint.name} status`]: (r) => r.status >= 200 && r.status < 300,
  });

  sleep(0.25);
}

export let options = {
  scenarios: {
    baseline: {
      executor: 'ramping-vus',
      exec: 'testUserFlow',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 10 },
        { duration: '3m', target: 50 },
        { duration: '2m', target: 10 },
      ],
    },
    normal: {
      executor: 'ramping-vus',
      exec: 'testUserFlow',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 100 },
        { duration: '8m', target: 200 },
        { duration: '2m', target: 0 },
      ],
    },
    stress: {
      executor: 'ramping-vus',
      exec: 'testUserFlow',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 500 },
        { duration: '10m', target: 500 },
        { duration: '3m', target: 0 },
      ],
    },
    spike: {
      executor: 'ramping-vus',
      exec: 'testUserFlow',
      startVUs: 0,
      stages: [
        { duration: '0m', target: 0 },
        { duration: '1m', target: 1000 },
        { duration: '2m', target: 1000 },
        { duration: '1m', target: 0 },
      ],
    },
    db_heavy_stress: {
      executor: 'ramping-vus',
      exec: 'testDBHeavyFlow',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 100 },
        { duration: '6m', target: 400 },
        { duration: '3m', target: 0 },
      ],
    },
  },
  thresholds: {
    'http_req_failed{endpoint:health}': ['rate<0.01'],
    'http_req_duration{endpoint:health}': ['p(95)<500', 'p(99)<1000'],
    'http_req_duration{endpoint:list_users}': ['p(95)<500', 'p(99)<1000'],
    'http_req_duration{endpoint:db_heavy}': ['p(95)<500', 'p(99)<1000'],
    'http_req_duration{endpoint:create_user}': ['p(95)<500', 'p(99)<1000'],
  },
  discardResponseBodies: true,
};
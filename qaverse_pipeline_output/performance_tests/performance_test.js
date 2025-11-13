import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

// Per-endpoint latency metrics
let endpointTimers = {};
function slugify(name) {
  return String(name).toLowerCase().replace(/[^a-z0-9]+/g, '_');
}
function getTimer(endpointName) {
  const key = slugify(endpointName);
  if (!endpointTimers[key]) endpointTimers[key] = new Trend(`rt_${key}`);
  return endpointTimers[key];
}

// Lightweight to database-heavy endpoints
const ENDPOINTS = [
  { name: 'List Resources', method: 'GET', path: '/api/v1/resources', heavy: false },
  { name: 'Get Resource by ID', method: 'GET', path: '/api/v1/resources/{id}', heavy: false },
  { name: 'Heavy DB Operation', method: 'POST', path: '/api/v1/db/heavy-operation', heavy: true, payload: { action: 'runHeavyQuery' } },
  { name: 'Init DB Iterate', method: 'POST', path: '/api/v1/init-db/iterate', heavy: true, payload: { iterations: 1000 } },
  { name: 'Health Check', method: 'GET', path: '/health', heavy: false }
];

// Simple weighting: heavy endpoints get chosen more often
function selectEndpoint() {
  const heavy = ENDPOINTS.filter(e => e.heavy);
  const light = ENDPOINTS.filter(e => !e.heavy);
  const r = Math.random();
  if (r < 0.6 && heavy.length > 0) {
    return heavy[Math.floor(Math.random() * heavy.length)];
  }
  return light.length > 0 ? light[Math.floor(Math.random() * light.length)] : ENDPOINTS[0];
}

// Thresholds for performance targets
export const options = {
  scenarios: {
    baseline: {
      executor: 'ramping-vus',
      exec: 'apiUser',
      startVUs: 0,
      stages: [
        { duration: '5m', target: 50 }
      ]
    },
    normal: {
      executor: 'ramping-vus',
      exec: 'apiUser',
      startVUs: 0,
      stages: [
        { duration: '6m', target: 200 }
      ]
    },
    stress: {
      executor: 'ramping-vus',
      exec: 'apiUser',
      startVUs: 0,
      stages: [
        { duration: '10m', target: 600 }
      ]
    },
    spike: {
      executor: 'ramping-vus',
      exec: 'apiUser',
      startVUs: 0,
      stages: [
        // Sudden jump to 1000 VUs, then sustain
        { duration: '30s', target: 1000 },
        { duration: '4m', target: 1000 }
      ]
    }
  },
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99']
  }
};

// Metrics for throughput and error rate
const errorsRate = new Rate('errors');
const throughputRPS = new Trend('throughput_rps'); // approximate requests per second

export function setup() {
  const baseURL = __ENV.BASE_URL || 'https://example.com';
  const username = __ENV.API_USERNAME;
  const password = __ENV.API_PASSWORD;
  let token = '';

  if (username && password) {
    try {
      const res = http.post(`${baseURL}/api/auth/login`, JSON.stringify({ username, password }), {
        headers: { 'Content-Type': 'application/json' }
      });
      if (res && res.status >= 200 && res.status < 300) {
        try {
          const body = res.json();
          if (body && body.token) token = body.token;
        } catch (_) {
          // ignore parse errors
        }
      }
    } catch (_) {
      // ignore login errors
    }
  }

  return { baseURL, token };
}

export function apiUser(setupData) {
  const baseURL = (setupData?.baseURL || __ENV.BASE_URL || 'https://example.com').replace(/\/+$/, '');
  const token = setupData?.token || '';
  let headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  while (true) {
    const ep = selectEndpoint();

    // Build URL; handle dynamic {id}
    let endpointPath = ep.path;
    let url = baseURL + endpointPath;
    if (endpointPath.includes('{id}')) {
      const id = Math.floor(Math.random() * 1000) + 1;
      url = baseURL + endpointPath.replace('{id}', id);
    }

    let res;
    try {
      if (ep.method === 'GET') {
        res = http.get(url, { headers });
      } else if (ep.method === 'POST') {
        const payload = ep.payload || {};
        res = http.post(url, JSON.stringify(payload), {
          headers: { ...headers, 'Content-Type': 'application/json' }
        });
      } else if (ep.method === 'PUT') {
        const payload = ep.payload || {};
        res = http.put(url, JSON.stringify(payload), {
          headers: { ...headers, 'Content-Type': 'application/json' }
        });
      } else {
        res = http.request(ep.method, url, null, { headers });
      }
    } catch (e) {
      res = { status: 0, timings: { duration: 0 } };
    }

    // Latency metric
    const timer = getTimer(ep.name);
    if (res && typeof res.timings?.duration === 'number') timer.add(res.timings.duration);

    // Error rate metric
    const isError = !(res && res.status >= 200 && res.status < 300);
    errorsRate.add(isError ? 1 : 0);

    // Basic assertion: 2xx expected
    check(res, { [`${ep.name} 2xx`]: (r) => r && r.status >= 200 && r.status < 300 });

    // Approximate throughput (requests per second) per request
    if (res && typeof res.timings?.duration === 'number') {
      const rps = 1000 / res.timings.duration; // since duration is ms
      throughputRPS.add(rps);
    }

    // Small randomized think time
    sleep(Math.random() * 0.5 + 0.1);
  }
}

export function teardown(setupData) {
  const baseURL = (setupData?.baseURL || __ENV.BASE_URL || 'https://example.com');
  const token = setupData?.token;
  if (token) {
    http.post(`${baseURL}/api/auth/logout`, {}, { headers: { 'Authorization': `Bearer ${token}` } });
  }
  // No additional teardown required
}
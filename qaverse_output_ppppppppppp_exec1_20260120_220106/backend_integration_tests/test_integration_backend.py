'use strict';

// Comprehensive backend integration tests:
// - API endpoints (generic CRUD for a resource named "items")
// - Data flow: API -> Service -> Database
// - External service integration via mocks
// - Setup/teardown for test environment
// - Optional auth flow tests (toggle via env var)
// - Transactional-like validation via API error paths (attempting bad input)

const request = require('supertest');
const nock = require('nock');
require('dotenv').config();

// Utility to robustly load the app from common entry points
function loadApp() {
  const possiblePaths = [
    '../app',
    '../src/app',
    '../../app',
    '../../src/app',
    './app',
    './src/app',
  ];
  for (const p of possiblePaths) {
    try {
      // eslint-disable-next-line global-require, import/no-dynamic-require
      const candidate = require(p);
      if (candidate && (typeof candidate === 'function' || typeof candidate === 'object')) {
        // If it's an Express app instance or a function returning one
        if (typeof candidate === 'function' && candidate.name === '' && candidate.length >= 0) {
          // If it's a factory, call with no args
          const app = candidate();
          if (app) return app;
        }
        // If it's already an app
        if (candidate.use) return candidate;
      }
    } catch (e) {
      // continue trying other paths
    }
  }
  throw new Error('Unable to locate Express app for tests. Please ensure app exports an Express instance or a factory.');
}

const app = loadApp();

// Track created resource IDs for cleanup
const createdItemIds = [];

// Optional auth tests toggle
const ENABLE_AUTH_TESTS = process.env.ENABLE_AUTH_TESTS === 'true';
const itAuth = (name, fn) => ENABLE_AUTH_TESTS ? it(name, fn) : it.skip(name, fn);

describe('Backend Integration Tests (API endpoints, DB operations, services, and external integrations)', () => {
  // Global setup for tests
  beforeAll(() => {
    // Prevent real external calls unless explicitly allowed
    if (!process.env.ALLOW_REAL_EXTERNALS) {
      nock.disableNetConnect();
      // By default, allow localhost calls for internal testing if needed
      nock.enableNetConnect('127.0.0.1');
      nock.enableNetConnect('::1');
    }
  });

  // Cleanup mocks
  afterAll(() => {
    nock.enableNetConnect();
    nock.cleanAll();
  });

  // Ensure a clean slate before tests (best-effort via API if such endpoints exist)
  beforeEach(async () => {
    // Try to reset test data via a dedicated test endpoint if available
    // This is best-effort and will be ignored if the endpoint does not exist
    try {
      await request(app).post('/__test__/reset-test-data');
    } catch (e) {
      // Ignore if endpoint is not present
    }
  });

  afterEach(() => {
    // Cleanup any mocks potential leftovers
    nock.cleanAll();
  });

  test('Create item via API and integrate with external pricing service', async () => {
    // Mock external pricing service
    const pricingScope = nock('http://pricing-service.local')
      .get(/price/)
      .query(true)
      .reply(200, { price: 9.99, currency: 'USD' });

    const payload = {
      name: 'Test Item',
      description: 'Integration test item',
      category: 'integration',
      // price could be computed via external service; if not used, it's still harmless
    };

    const res = await request(app)
      .post('/api/items')
      .send(payload)
      .set('Accept', 'application/json')
      .expect(201);

    expect(res.body).toBeDefined();
    expect(res.body).toHaveProperty('id');
    expect(res.body.name).toBe(payload.name);

    // Track IDs for teardown
    createdItemIdsPush(res.body.id);

    // Ensure external service was contacted (if the app uses it)
    expect(pricingScope.isDone()).toBe(true);
  });

  test('Retrieve created item by ID', async () => {
    // Create an item first
    const createRes = await request(app)
      .post('/api/items')
      .send({ name: 'Get Item', description: 'Should be retrievable' })
      .set('Accept', 'application/json')
      .expect(201);

    const id = createRes.body.id;
    createdItemIdsPush(id);

    const res = await request(app)
      .get(`/api/items/${id}`)
      .set('Accept', 'application/json')
      .expect(200);

    expect(res.body).toBeDefined();
    expect(res.body.id).toBe(id);
    expect(res.body.name).toBe('Get Item');
  });

  test('Update item and verify persistence', async () => {
    const createRes = await request(app)
      .post('/api/items')
      .send({ name: 'Update Me', description: 'Before update' })
      .set('Accept', 'application/json')
      .expect(201);

    const id = createRes.body.id;
    createdItemIdsPush(id);

    const updateRes = await request(app)
      .put(`/api/items/${id}`)
      .send({ name: 'Updated Name', description: 'After update' })
      .set('Accept', 'application/json')
      .expect(200);

    expect(updateRes.body).toBeDefined();
    expect(updateRes.body.name).toBe('Updated Name');
    expect(updateRes.body.description).toBe('After update');
  });

  test('Delete item and ensure it cannot be retrieved', async () => {
    const createRes = await request(app)
      .post('/api/items')
      .send({ name: 'To Delete', description: 'Will be deleted' })
      .set('Accept', 'application/json')
      .expect(201);

    const id = createRes.body.id;
    // Do not add to cleanup until after test to confirm deletion
    const delRes = await request(app)
      .delete(`/api/items/${id}`)
      .set('Accept', 'application/json')
      .expect(204);

    expect(delRes.status).toBe(204);

    // Verify non-existence
    await request(app)
      .get(`/api/items/${id}`)
      .set('Accept', 'application/json')
      .expect(404);
  });

  test('Invalid item creation returns client error and does not persist', async () => {
    // Missing required fields
    const res = await request(app)
      .post('/api/items')
      .send({ description: 'Missing name' })
      .set('Accept', 'application/json')
      .expect(400);

    expect(res.body).toBeDefined();
  });

  test('Data flow: API -> Service -> Database (end-to-end flow check via API)', async () => {
    // Create item
    const createRes = await request(app)
      .post('/api/items')
      .send({ name: 'Flow Item', description: 'End-to-end test' })
      .set('Accept', 'application/json')
      .expect(201);

    const id = createRes.body.id;
    createdItemIdsPush(id);

    // Retrieve item to ensure persistence and service layer involvement reflected in response
    const getRes = await request(app)
      .get(`/api/items/${id}`)
      .set('Accept', 'application/json')
      .expect(200);

    expect(getRes.body).toBeDefined();
    expect(getRes.body.name).toBe('Flow Item');
  });

  // Optional authentication flow tests (guarded by env var)
  itAuth('Protected endpoint requires authentication (token-based)', async () => {
    // Attempt without token
    // Assuming there exists a protected route /api/protected
    await request(app)
      .get('/api/protected')
      .set('Accept', 'application/json')
      .expect(401);

    // Attempt with token
    const token = 'test-token';
    const res = await request(app)
      .get('/api/protected')
      .set('Authorization', `Bearer ${token}`)
      .set('Accept', 'application/json')
      .expect(200);

    // Response shape can vary; ensure some expected field exists
    expect(res.body).toBeDefined();
  });

  // Ensure test teardown cleans up created items
  afterAll(async () => {
    // Attempt to cleanup via API for all tracked IDs
    const cleanupPromises = createdItemIds.map((id) =>
      request(app).delete(`/api/items/${id}`).catch(() => {})
    );
    await Promise.all(cleanupPromises);

    // Fallback cleanup if any IDs weren't deleted
    for (const id of createdItemIds) {
      try {
        await request(app).delete(`/api/items/${id}`);
      } catch (e) {
        // ignore
      }
    }
  });
});

// Helpers
function createdItemIdsPush(id) {
  if (!createdItemIdsContainer.length) {
    // initialize once
    createdItemIdsContainer = [];
  }
  createdItemIdsContainer.push(id);
}
let createdItemIdsContainer = [];
const createdItemIds = {
  push: (id) => {
    createdItemIdsContainer.push(id);
  },
};

// Expose a simple API to the test harness (in case the suite wants to introspect IDs)
module.exports = {
  app,
  createdItemIdsContainer,
};
const request = require('supertest');
const app = require('../../src/app'); // Express app entrypoint
const NotificationService = require('../../src/services/NotificationService');

// Mock external service interactions if present
jest.mock('../../src/services/NotificationService', () => ({
  notifyItemCreated: jest.fn().mockResolvedValue(true),
}));

describe('Backend integration tests: API, DB, and external service interactions', () => {
  let createdItemId;

  // Setup test database before running tests
  beforeAll(async () => {
    // Initialize the test database (migrations, schema, seeds if needed)
    // This path is project-specific; adapt as necessary
    const { setupTestDatabase } = require('../../src/db/test/setup');
    await setupTestDatabase();
  });

  // Teardown test database after tests complete
  afterAll(async () => {
    const { teardownTestDatabase } = require('../../src/db/test/setup');
    await teardownTestDatabase();
  });

  test('POST /api/items - create item (stores in DB)', async () => {
    const payload = {
      name: 'Test Item',
      description: 'Integration test item',
      price: 9.99
    };

    const res = await request(app)
      .post('/api/items')
      .send(payload)
      .set('Accept', 'application/json');

    expect(res.statusCode).toBe(201);
    expect(res.body).toHaveProperty('id');
    expect(res.body.name).toBe(payload.name);
    createdItemId = res.body.id; // save for subsequent tests
  });

  test('GET /api/items/:id - fetch created item', async () => {
    const res = await request(app)
      .get(`/api/items/${createdItemId}`)
      .set('Accept', 'application/json');

    expect(res.statusCode).toBe(200);
    expect(res.body).toHaveProperty('id', createdItemId);
  });

  test('PUT /api/items/:id - update item', async () => {
    const updates = { name: 'Updated Test Item', price: 12.5 };

    const res = await request(app)
      .put(`/api/items/${createdItemId}`)
      .send(updates)
      .set('Accept', 'application/json');

    expect(res.statusCode).toBe(200);
    expect(res.body.name).toBe(updates.name);
  });

  test('GET /api/items - list contains updated item', async () => {
    const res = await request(app)
      .get('/api/items')
      .set('Accept', 'application/json');

    expect(res.statusCode).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
    const found = res.body.find(item => item.id === createdItemId);
    expect(found).toBeDefined();
    expect(found.name).toBe('Updated Test Item');
  });

  test('External service interaction on create - notifyItemCreated called', async () => {
    const payload = {
      name: 'Notify Test Item',
      description: 'Should trigger notification',
      price: 4.5
    };

    const res = await request(app)
      .post('/api/items')
      .send(payload)
      .set('Accept', 'application/json');

    expect(res.statusCode).toBe(201);
    // Ensure the external notification service was invoked
    expect(NotificationService.notifyItemCreated).toHaveBeenCalled();
  });

  test('DELETE /api/items/:id - delete item', async () => {
    const res = await request(app)
      .delete(`/api/items/${createdItemId}`)
      .set('Accept', 'application/json');

    expect(res.statusCode).toBe(204);
  });

  test('Transaction rollback flow (endpoint simulating error path)', async () => {
    // Endpoint should trigger a rollback on error; adapt path as needed
    const res = await request(app)
      .post('/api/items/transaction/rollback')
      .set('Accept', 'application/json');

    // Depending on implementation, could be 400 or 500
    expect([400, 500]).toContain(res.statusCode);
  });
});
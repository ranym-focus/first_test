import React, { useState, useEffect } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter, Routes, Route, Link } from 'react-router-dom';

// Simple ListItem that supports a like interaction
const ListItem = ({ item, onLike }) => (
  <li data-testid={`item-${item.id}`}>
    <span>{item.name}</span>
    {typeof item.likes !== 'undefined' ? <span> {item.likes} likes</span> : null}
    <button onClick={() => onLike(item.id)}>Like</button>
  </li>
);

// List rendering
const List = ({ items, onLike }) => (
  <ul data-testid="item-list">
    {items.map((it) => (
      <ListItem key={it.id} item={it} onLike={onLike} />
    ))}
  </ul>
);

// Form to add new items with basic validation
const AddItemForm = ({ onAdd }) => {
  const [name, setName] = useState('');
  const [touched, setTouched] = useState(false);

  const onSubmit = (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setTouched(true);
      return;
    }
    onAdd(name.trim());
    setName('');
  };

  return (
    <form onSubmit={onSubmit} aria-label="add-item-form">
      <input aria-label="item-name" value={name} onChange={(e) => setName(e.target.value)} />
      <button type="submit">Add</button>
      {touched && !name && <span role="alert">Name is required</span>}
    </form>
  );
};

// Data page simulating API data fetch and data flow to List and AddItemForm
const DataPage = () => {
  const [items, setItems] = useState([]);

  useEffect(() => {
    fetch('/api/items')
      .then((res) => res.json())
      .then((data) => setItems(data.items || []))
      .catch(() => setItems([]));
  }, []);

  const likeItem = (id) => {
    setItems((prev) =>
      prev.map((it) => (it.id === id ? { ...it, likes: (it.likes || 0) + 1 } : it))
    );
  };

  const addItem = (name) => {
    const newItem = { id: Date.now(), name, likes: 0 };
    setItems((prev) => [...prev, newItem]);
  };

  return (
    <section aria-label="data-page">
      <h2>Data</h2>
      <List items={items} onLike={likeItem} />
      <AddItemForm onAdd={addItem} />
    </section>
  );
};

// Home view with internal state management (increment counter)
const HomeView = () => {
  const [count, setCount] = useState(0);
  return (
    <section aria-label="home-page">
      <h2>Home</h2>
      <p>Count: {count}</p>
      <button onClick={() => setCount((c) => c + 1)}>Increment</button>
      <nav aria-label="main-nav">
        <Link to="/data">Data</Link>
      </nav>
    </section>
  );
};

// App wiring up routes generically (no reliance on specific app structure)
const App = () => (
  <div>
    <Routes>
      <Route path="/home" element={<HomeView />} />
      <Route path="/data" element={<DataPage />} />
      <Route path="*" element={<HomeView />} />
    </Routes>
  </div>
);

// Tests
describe('Generic React frontend integration tests (React Testing Library)', () => {
  // Mock API calls
  beforeEach(() => {
    jest.spyOn(global, 'fetch').mockImplementation((url) => {
      if (url === '/api/items') {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            items: [
              { id: 1, name: 'Alpha' },
              { id: 2, name: 'Beta' },
            ],
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({}),
      });
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test('navigation between Home and Data routes', async () => {
    render(
      <MemoryRouter initialEntries={['/home']}>
        <App />
      </MemoryRouter>
    );

    // Home view should render
    expect(screen.getByText('Home')).toBeInTheDocument();

    // Navigate to Data via Link
    fireEvent.click(screen.getByText('Data'));

    // Data page should render after navigation
    await waitFor(() => expect(screen.getByText('Data')).toBeInTheDocument());
    expect(screen.getByText('Data')).toBeInTheDocument();
  });

  test('DataPage fetches items and displays them', async () => {
    render(
      <MemoryRouter initialEntries={['/data']}>
        <App />
      </MemoryRouter>
    );

    // Wait for API items to render
    await waitFor(() => expect(screen.getByText('Alpha')).toBeInTheDocument());
    expect(screen.getByText('Beta')).toBeInTheDocument();
  });

  test('like button increments like count and updates UI', async () => {
    render(
      <MemoryRouter initialEntries={['/data']}>
        <App />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText('Alpha')).toBeInTheDocument());

    const likeButtons = screen.getAllByText('Like');
    // Like the first item (Alpha)
    fireEvent.click(likeButtons[0]);

    await waitFor(() => expect(screen.getByText('1 likes')).toBeInTheDocument());
  });

  test('add item form submits new item', async () => {
    render(
      <MemoryRouter initialEntries={['/data']}>
        <App />
      </MemoryRouter>
    );

    await waitFor(() => screen.getByLabelText('item-name'));

    const input = screen.getByLabelText('item-name');
    const addButton = screen.getByText('Add');

    // Submit a new item
    fireEvent.change(input, { target: { value: 'Gamma' } });
    fireEvent.click(addButton);

    // New item should appear in the list
    await waitFor(() => expect(screen.getByText('Gamma')).toBeInTheDocument());
  });

  test('form validation shows error for empty submission', async () => {
    render(
      <MemoryRouter initialEntries={['/data']}>
        <App />
      </MemoryRouter>
    );

    await waitFor(() => screen.getByText('Add'));

    const addButton = screen.getByText('Add');
    // Submit with empty name
    fireEvent.click(addButton);

    // Validation message should appear
    await waitFor(() => expect(screen.getByText('Name is required')).toBeInTheDocument());
  });

  test('data flow from DataPage to ListItem is visible in UI', async () => {
    render(
      <MemoryRouter initialEntries={['/data']}>
        <App />
      </MemoryRouter>
    );

    // Ensure data is loaded and the item text is rendered
    await waitFor(() => expect(screen.getByText('Alpha')).toBeInTheDocument());
    const item = screen.getByText('Alpha').closest('li');
    expect(item).toBeInTheDocument();
  });
});
import React, { useEffect, useState } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';

// Lightweight components to simulate a generic app structure for integration tests

const UserCard = ({ user }) => <li data-testid="user-item">{user.name}</li>;

const UsersPage = () => {
  const [users, setUsers] = useState(null);
  useEffect(() => {
    fetch('/api/users')
      .then((res) => res.json())
      .then((data) => setUsers(data))
      .catch(() => setUsers([]));
  }, []);
  if (users === null) return <div>Loading Users...</div>;
  return (
    <section aria-label="users-page">
      <h2>Users</h2>
      <ul>
        {users.map((u) => (
          <UserCard key={u.id} user={u} />
        ))}
      </ul>
    </section>
  );
};

const SearchBar = ({ onSubmit }) => {
  const [value, setValue] = useState('');
  const [error, setError] = useState('');
  const handleSubmit = (e) => {
    e.preventDefault();
    if (!value.trim()) {
      setError('Please enter a search term');
      return;
    }
    setError('');
    onSubmit(value);
  };
  return (
    <form onSubmit={handleSubmit}>
      <input
        aria-label="search-input"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <button type="submit">Search</button>
      {error && (
        <div role="alert" data-testid="search-error">
          {error}
        </div>
      )}
    </form>
  );
};

const Home = ({ onSearch, lastQuery }) => (
  <main>
    <h1>Home</h1>
    <nav>
      <Link to="/users">Go to Users</Link> | <Link to="/about">About</Link>
    </nav>
    <section>
      <SearchBar onSubmit={onSearch} />
      {lastQuery ? (
        <div data-testid="last-query">Last query: {lastQuery}</div>
      ) : null}
    </section>
  </main>
);

const About = () => (
  <section>
    <h2>About</h2>
  </section>
);

const App = () => {
  const [lastQuery, setLastQuery] = useState('');
  const handleSearch = (q) => {
    setLastQuery(q);
  };
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={<Home onSearch={handleSearch} lastQuery={lastQuery} />}
        />
        <Route path="/users" element={<UsersPage />} />
        <Route path="/about" element={<About />} />
      </Routes>
    </BrowserRouter>
  );
};

// Integration tests (generic routing, components, API, and form interactions)

describe('Generic React app integration tests (generic routes, components, API, forms)', () => {
  beforeEach(() => {
    // Reset mocks before each test
    jest.restoreAllMocks();
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  test('navigates from Home to Users', async () => {
    render(<App />);
    // Verify Home is rendered
    expect(screen.getByText(/Home/i)).toBeInTheDocument();

    // Navigate to Users
    fireEvent.click(screen.getByText(/Go to Users/i));

    // Wait for Users page to render
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /Users/i })).toBeInTheDocument()
    );
  });

  test('fetches and displays users on Users page', async () => {
    // Mock API response
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        { id: 1, name: 'Alice' },
        { id: 2, name: 'Bob' },
      ],
    });

    render(<App />);

    // Navigate to Users
    fireEvent.click(screen.getByText(/Go to Users/i));

    // Ensure fetch was called and data is rendered
    await waitFor(() => expect(screen.getByText(/Alice/i)).toBeInTheDocument());
    expect(global.fetch).toHaveBeenCalledWith('/api/users');
  });

  test('form submission updates last query', async () => {
    render(<App />);

    const input = screen.getByLabelText(/search-input/i);
    fireEvent.change(input, { target: { value: 'react' } });
    fireEvent.click(screen.getByText(/Search/i));

    // Check that last query state is reflected in Home
    await waitFor(() =>
      expect(screen.getByTestId('last-query')).toHaveTextContent('Last query: react')
    );
  });

  test('form validation shows error for empty input', async () => {
    render(<App />);

    // Submitting with empty input should trigger validation error
    fireEvent.click(screen.getByText(/Search/i));

    await waitFor(() =>
      expect(screen.getByTestId('search-error')).toHaveTextContent(
        'Please enter a search term'
      )
    );
  });

  test('navigation to About page works', async () => {
    render(<App />);

    // Navigate to About
    fireEvent.click(screen.getByText(/About/i));

    // Verify About page renders
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /About/i })).toBeInTheDocument()
    );
  });
});
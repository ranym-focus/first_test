import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, Link } from 'react-router-dom';
import '@testing-library/jest-dom/extend-expect';

describe('Generic React frontend integration tests (navigation, components, API)', () => {

  // Components and routes for generic navigation tests
  const Home = () => <div>Home Page</div>;
  const Section = () => <div>Section Page</div>;
  const Details = () => <div>Details Page</div>;

  const Navbar = () => (
    <nav>
      <Link data-testid="link-home" to="/home">Home</Link>
      <Link data-testid="link-section" to="/section">Section</Link>
      <Link data-testid="link-details" to="/details">Details</Link>
    </nav>
  );

  const AppRouter = () => (
    <MemoryRouter initialEntries={['/home']}>
      <Navbar />
      <Routes>
        <Route path="/home" element={<Home />} />
        <Route path="/section" element={<Section />} />
        <Route path="/details" element={<Details />} />
      </Routes>
    </MemoryRouter>
  );

  test('navigation between generic routes updates content', async () => {
    render(<AppRouter />);

    // Initially on Home
    expect(screen.getByText('Home Page')).toBeInTheDocument();

    // Navigate to Section
    fireEvent.click(screen.getByTestId('link-section'));
    await waitFor(() => expect(screen.getByText('Section Page')).toBeInTheDocument());

    // Navigate to Details
    fireEvent.click(screen.getByTestId('link-details'));
    await waitFor(() => expect(screen.getByText('Details Page')).toBeInTheDocument());
  });

  // Data flow and component interaction tests
  const Child = ({ message, onMessageChange }) => (
    <div>
      <div data-testid="child-text">Child sees: {message}</div>
      <button data-testid="child-update-btn" onClick={() => onMessageChange('Updated by Child')}>
        Update from Child
      </button>
    </div>
  );

  const Parent = () => {
    const [message, setMessage] = React.useState('Hello');
    return (
      <div>
        <p data-testid="parent-text">{message}</p>
        <Child message={message} onMessageChange={setMessage} />
      </div>
    );
  };

  test('data flow between parent and child components via props and callbacks', () => {
    render(<Parent />);

    // Initial state check
    expect(screen.getByTestId('parent-text').textContent).toBe('Hello');
    expect(screen.getByTestId('child-text').textContent).toContain('Hello');

    // Child updates parent state through callback
    fireEvent.click(screen.getByTestId('child-update-btn'));

    // Parent should reflect update
    expect(screen.getByTestId('parent-text').textContent).toBe('Updated by Child');
    expect(screen.getByTestId('child-text').textContent).toContain('Updated by Child');
  });

  // API integration and data fetching tests
  const ApiList = () => {
    const [items, setItems] = React.useState([]);
    React.useEffect(() => {
      fetch('/api/items')
        .then((res) => res.json())
        .then((data) => setItems(data))
        .catch(() => setItems([]));
    }, []);
    return (
      <div>
        <h1>Items</h1>
        <ul>
          {items.map((it) => (
            <li key={it.id}>{it.name}</li>
          ))}
        </ul>
      </div>
    );
  };

  test('API integration: mocks fetch and renders items', async () => {
    // Mock fetch response
    const mockItems = [
      { id: 1, name: 'Item 1' },
      { id: 2, name: 'Item 2' },
    ];
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockItems),
      })
    );

    render(<ApiList />);

    // Ensure fetch was called with the expected URL
    expect(global.fetch).toHaveBeenCalledWith('/api/items');

    // Wait for items to render
    await waitFor(() => expect(screen.getByText('Item 1')).toBeInTheDocument());
    expect(screen.getByText('Item 2')).toBeInTheDocument();
  });

  // Cleanup mocks after each test
  afterEach(() => {
    jest.resetAllMocks();
  });
});
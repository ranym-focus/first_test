import React from 'react';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';

// Generic Components for Navigation Tests
const Home = () => <div data-testid="route-home">Home Page</div>;
const Dashboard = () => <div data-testid="route-dashboard">Dashboard Page</div>;
const Settings = () => <div data-testid="route-settings">Settings Page</div>;

const NavBar = () => (
  <nav>
    <ul>
      <li><Link to="/home">Home</Link></li>
      <li><Link to="/dashboard">Dashboard</Link></li>
      <li><Link to="/settings">Settings</Link></li>
    </ul>
  </nav>
);

function AppRouter() {
  return (
    <BrowserRouter>
      <NavBar />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/home" element={<Home />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </BrowserRouter>
  );
}

// Generic Components for Data Flow and API Integration Tests
const Child = ({ value, onIncrement }) => (
  <div>
    <span data-testid="child-value">{value}</span>
    <button data-testid="child-increment" onClick={onIncrement}>Increment</button>
  </div>
);

const Parent = () => {
  const [count, setCount] = React.useState(0);
  return (
    <div>
      <Child value={count} onIncrement={() => setCount((c) => c + 1)} />
      <div data-testid="parent-count">{count}</div>
    </div>
  );
};

const ItemList = ({ items }) => (
  <div>
    {items.map((it) => (
      <div key={it.id} data-testid={`item-${it.id}-name`}>
        {it.name}
      </div>
    ))}
  </div>
);

const DataFetcher = () => {
  const [items, setItems] = React.useState([]);
  React.useEffect(() => {
    fetch('/api/items')
      .then((res) => res.json())
      .then((data) => setItems(data));
  }, []);
  return <ItemList items={items} />;
};

// Tests
describe('Generic React App Integration Tests (Navigation, Components, API)', () => {
  afterEach(() => {
    cleanup();
    jest.resetAllMocks();
  });

  // 1. Test navigation between routes
  test('default route shows Home, and navigation links update route content', async () => {
    render(<AppRouter />);

    // Default route should render Home
    expect(screen.getByTestId('route-home')).toBeInTheDocument();

    // Navigate to Dashboard
    fireEvent.click(screen.getByText('Dashboard'));
    await waitFor(() => expect(screen.getByTestId('route-dashboard')).toBeInTheDocument());

    // Navigate to Settings
    fireEvent.click(screen.getByText('Settings'));
    await waitFor(() => expect(screen.getByTestId('route-settings')).toBeInTheDocument());

    // Navigate back to Home
    fireEvent.click(screen.getByText('Home'));
    await waitFor(() => expect(screen.getByTestId('route-home')).toBeInTheDocument());
  });

  // 2. Test interactions between components (data flow from Parent to Child)
  test('Parent passes data to Child and updates via callback', async () => {
    render(<Parent />);

    // Initial values
    expect(screen.getByTestId('child-value')).toHaveTextContent('0');
    expect(screen.getByTestId('parent-count')).toHaveTextContent('0');

    // Trigger child action to update value
    fireEvent.click(screen.getByTestId('child-increment'));

    // After update, both child and parent should reflect new count
    await waitFor(() => {
      expect(screen.getByTestId('child-value')).toHaveTextContent('1');
      expect(screen.getByTestId('parent-count')).toHaveTextContent('1');
    });
  });

  // 3 & 4. API integration: Mock API calls and test data rendering + data flow to child
  test('DataFetcher fetches API data and renders via ItemList, and API is called with correct endpoint', async () => {
    const mockItems = [
      { id: 1, name: 'Alpha' },
      { id: 2, name: 'Beta' },
    ];

    // Mock fetch
    const mockFetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => mockItems,
    });
    // @ts-ignore
    global.fetch = mockFetch;

    render(<DataFetcher />);

    // Ensure fetch was called with the API endpoint
    expect(mockFetch).toHaveBeenCalledWith('/api/items');

    // Data should render via ItemList -> item-name elements
    await waitFor(() => {
      expect(screen.getByTestId('item-1-name')).toHaveTextContent('Alpha');
      expect(screen.getByTestId('item-2-name')).toHaveTextContent('Beta');
    });
  });
});
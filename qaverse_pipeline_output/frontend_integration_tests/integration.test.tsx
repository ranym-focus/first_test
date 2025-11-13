import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, Link } from 'react-router-dom';
import { Provider, useDispatch, useSelector } from 'react-redux';
import { createStore } from 'redux';
import { rest, setupServer } from 'msw';
import '@testing-library/jest-dom/extend-expect';

// --------- Generic App Router for Navigation Tests ----------
const AppRouter = () => (
  <MemoryRouter initialEntries={['/']}>
    <nav>
      <Link to="/" data-testid="nav-home">Home</Link>
      <Link to="/about" data-testid="nav-about">About</Link>
      <Link to="/dashboard" data-testid="nav-dashboard">Dashboard</Link>
    </nav>
    <Routes>
      <Route path="/" element={<div data-testid="route-home">Home Page</div>} />
      <Route path="/about" element={<div data-testid="route-about">About Page</div>} />
      <Route path="/dashboard" element={<div data-testid="route-dashboard">Dashboard Page</div>} />
    </Routes>
  </MemoryRouter>
);

// --------- Component Interaction and Data Flow Components ----------
const CounterDisplay = ({ value }) => (
  <div data-testid="counter-display">Count: {value}</div>
);

const CounterControls = ({ onIncrement, onDecrement }) => (
  <div>
    <button onClick={onIncrement} data-testid="increment-btn">Increment</button>
    <button onClick={onDecrement} data-testid="decrement-btn">Decrement</button>
  </div>
);

const CounterContainer = () => {
  const [count, setCount] = React.useState(0);
  return (
    <div>
      <CounterDisplay value={count} />
      <CounterControls
        onIncrement={() => setCount((c) => c + 1)}
        onDecrement={() => setCount((c) => c - 1)}
      />
    </div>
  );
};

// --------- Redux State Management Test Components ----------
const initialReduxState = { value: 0 };

function reduxReducer(state = initialReduxState, action) {
  switch (action.type) {
    case 'INCREMENT':
      return { value: state.value + 1 };
    default:
      return state;
  }
}

const ReduxCounter = () => {
  const value = useSelector((s) => s.value);
  const dispatch = useDispatch();
  return (
    <div>
      <span data-testid="redux-value">{value}</span>
      <button onClick={() => dispatch({ type: 'INCREMENT' })}>Increment</button>
    </div>
  );
};

// --------- API Integration Components (MSW) ----------
function UserList() {
  const [users, setUsers] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    fetch('/api/users')
      .then((r) => r.json())
      .then((data) => {
        setUsers(data.users);
        setLoading(false);
      })
      .catch((err) => {
        setError(err);
        setLoading(false);
      });
  }, []);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error</div>;

  return (
    <ul>
      {users.map((u) => (
        <li key={u.id}>{u.name}</li>
      ))}
    </ul>
  );
}

// --------- Form Submission and Validation Components ----------
function LoginForm({ onSubmit }) {
  const [username, setUsername] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [error, setError] = React.useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!username || !password) {
      setError('Username and password required');
      return;
    }
    onSubmit({ username, password });
  };

  return (
    <form onSubmit={handleSubmit}>
      <input
        placeholder="Username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        data-testid="username"
      />
      <input
        placeholder="Password"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        data-testid="password"
      />
      <button type="submit" data-testid="submit-btn">Login</button>
      {error && <span role="alert">{error}</span>}
    </form>
  );
}

// --------- Data Flow Between Components (Parent/Child) ----------
function DataFlowChild({ value, onChange }) {
  return (
    <input
      data-testid="child-input"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function DataFlowParent() {
  const [text, setText] = React.useState('initial');
  return (
    <div>
      <DataFlowChild value={text} onChange={setText} />
      <div data-testid="parent-text">{text}</div>
    </div>
  );
}

// --------- MSW Server Setup for API Mocking ----------
const server = setupServer(
  rest.get('/api/users', (req, res, ctx) =>
    res(ctx.json({ users: [{ id: 1, name: 'Alice' }, { id: 2, name: 'Bob' }] }))
  )
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// --------- Tests: Comprehensive Frontend Integration Tests ----------
describe('Generic React App Integration (Synthetic Routes/Components)', () => {
  // Navigation tests
  test('navigation between generic routes updates content', async () => {
    render(<AppRouter />);

    // Default route
    expect(screen.getByTestId('route-home')).toBeInTheDocument();

    // Navigate to About
    userEvent.click(screen.getByTestId('nav-about'));
    await waitFor(() => {
      expect(screen.getByTestId('route-about')).toBeInTheDocument();
    });

    // Navigate to Dashboard
    userEvent.click(screen.getByTestId('nav-dashboard'));
    await waitFor(() => {
      expect(screen.getByTestId('route-dashboard')).toBeInTheDocument();
    });

    // Back to Home
    userEvent.click(screen.getByTestId('nav-home'));
    await waitFor(() => {
      expect(screen.getByTestId('route-home')).toBeInTheDocument();
    });
  });

  // Component interactions and data flow
  test('component interactions propagate data flow from parent to child', () => {
    render(<CounterContainer />);

    // Initial value
    expect(screen.getByTestId('counter-display').textContent).toContain('Count: 0');

    // Increment
    userEvent.click(screen.getByTestId('increment-btn'));
    expect(screen.getByTestId('counter-display').textContent).toContain('Count: 1');

    // Decrement
    userEvent.click(screen.getByTestId('decrement-btn'));
    expect(screen.getByTestId('counter-display').textContent).toContain('Count: 0');
  });

  // State management with Redux
  test('Redux state management updates via dispatch', () => {
    const store = createStore(reduxReducer);
    render(
      <Provider store={store}>
        <ReduxCounter />
      </Provider>
    );

    // Initial value
    expect(screen.getByTestId('redux-value').textContent).toBe('0');

    // Dispatch increment
    userEvent.click(screen.getByText('Increment'));
    expect(screen.getByTestId('redux-value').textContent).toBe('1');
  });

  // API integration and data fetching
  test('API integration: fetch and render users', async () => {
    render(<UserList />);

    // Loading state shown first
    expect(screen.getByText('Loading...')).toBeInTheDocument();

    // Wait for data
    await waitFor(() => expect(screen.getByText('Alice')).toBeInTheDocument());
    expect(screen.getByText('Bob')).toBeInTheDocument();
  });

  test('API integration: handles API failure gracefully', async () => {
    server.use(
      rest.get('/api/users', (req, res, ctx) =>
        res(ctx.status(500))
      )
    );

    render(<UserList />);

    // Loading state then error
    expect(screen.getByText('Loading...')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Error')).toBeInTheDocument());
  });

  // Form submissions and validations
  test('form submission passes data to onSubmit and validates inputs', async () => {
    const mockSubmit = jest.fn();
    render(<LoginForm onSubmit={mockSubmit} />);

    // Empty submission should trigger validation error
    userEvent.click(screen.getByTestId('submit-btn'));
    expect(screen.getByRole('alert')).toHaveTextContent('Username and password required');

    // Fill form and submit
    userEvent.type(screen.getByTestId('username'), 'john');
    userEvent.type(screen.getByTestId('password'), 'secret');
    userEvent.click(screen.getByTestId('submit-btn'));

    await waitFor(() =>
      expect(mockSubmit).toHaveBeenCalledWith({ username: 'john', password: 'secret' })
    );
  });

  // Data flow between components (parent passes data to child and child updates parent)
  test('data flow between parent and child components', () => {
    render(<DataFlowParent />);

    // Initial parent text
    expect(screen.getByTestId('parent-text').textContent).toBe('initial');

    // Change via child input
    userEvent.type(screen.getByTestId('child-input'), 'updated');
    // The input value updates immediately; ensure parent's text reflects change
    expect(screen.getByTestId('parent-text').textContent).toBe('updated');
  });
});
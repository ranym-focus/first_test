import React, { useEffect, useState } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, Link } from 'react-router-dom';
import '@testing-library/jest-dom';

//
// Lightweight test harness components (generic, no real app coupling)
//

const HomeView = () => <div data-testid="home-view">Home Page</div>;

const DataFetcher = () => {
  const [data, setData] = useState(null);
  useEffect(() => {
    fetch('/api/data')
      .then((res) => res.json())
      .then((d) => setData(d));
  }, []);
  if (!data) return <div>Loading...</div>;
  return <div data-testid="data-title">{data.title}</div>;
};

const DashboardView = () => (
  <div>
    <h1>Dashboard</h1>
    <DataFetcher />
  </div>
);

const LoginForm = ({ onSubmit }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit({ username, password });
  };
  return (
    <form onSubmit={handleSubmit} aria-label="login-form">
      <input
        aria-label="username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
      />
      <input
        aria-label="password"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <button type="submit">Login</button>
    </form>
  );
};

const FormsView = () => (
  <div>
    <h1>Forms</h1>
    <LoginForm onSubmit={() => {}} />
  </div>
);

const NavBar = () => (
  <nav>
    <Link to="/">Home</Link> | <Link to="/dashboard">Dashboard</Link> |{' '}
    <Link to="/forms">Forms</Link>
  </nav>
);

// Simple parent/child data-flow test components
const TextInput = ({ onChangeText }) => (
  <input aria-label="text-input" onChange={(e) => onChangeText(e.target.value)} />
);

const Display = ({ text }) => <div data-testid="display">{text}</div>;

const ParentFlow = () => {
  const [text, setText] = useState('');
  return (
    <div>
      <TextInput onChangeText={setText} />
      <Display text={text} />
    </div>
  );
};

// Harness that mimics a small portion of the app with routes
const Harness = () => (
  <MemoryRouter initialEntries={['/']}>
    <NavBar />
    <Routes>
      <Route path="/" element={<HomeView />} />
      <Route path="/dashboard" element={<DashboardView />} />
      <Route path="/forms" element={<FormsView />} />
    </Routes>
  </MemoryRouter>
);

describe('React App Integration Tests (Generic, Router, Data Flow, API, Forms)', () => {
  beforeEach(() => {
    // Reset mocks before each test
    jest.resetAllMocks();
  });

  afterEach(() => {
    // Clean up DOM after each test
    document.body.innerHTML = '';
  });

  test('navigation between routes (generic) updates content accordingly', async () => {
    render(<Harness />);

    // Initially on Home
    expect(screen.getByTestId('home-view')).toBeInTheDocument();

    // Navigate to Dashboard
    fireEvent.click(screen.getByText('Dashboard'));
    // Dashboard content should render
    expect(await screen.findByText('Dashboard')).toBeInTheDocument();

    // Navigate back to Home
    fireEvent.click(screen.getByText('Home'));
    expect(await screen.findByTestId('home-view')).toBeInTheDocument();
  });

  test('data flow between parent and child components updates across components', () => {
    render(<ParentFlow />);

    // Initially no text displayed
    expect(screen.queryByTestId('display')).toBeInTheDocument();
    // Type into input
    fireEvent.change(screen.getByLabelText('text-input'), { target: { value: 'Hello' } });
    // Display should reflect text
    expect(screen.getByTestId('display')).toHaveTextContent('Hello');
  });

  test('API integration: DataFetcher fetches and renders data', async () => {
    // Mock fetch to return test data
    const mockData = { title: 'Sample Data' };
    global.fetch = jest.fn(() =>
      Promise.resolve({
        json: () => Promise.resolve(mockData),
      })
    );

    // Render DashboardView directly (no routing needed)
    render(<DashboardView />);

    // Loading state should be visible initially
    expect(screen.getByText('Loading...')).toBeInTheDocument();

    // After fetch resolves, data title should render
    await waitFor(() => expect(screen.getByText('Sample Data')).toBeInTheDocument());
  });

  test('form submission: LoginForm calls onSubmit with entered data', () => {
    const onSubmit = jest.fn();
    render(<LoginForm onSubmit={onSubmit} />);

    // Fill in the form
    fireEvent.change(screen.getByLabelText('username'), { target: { value: 'alice' } });
    fireEvent.change(screen.getByLabelText('password'), { target: { value: 'secret' } });

    // Submit the form
    fireEvent.click(screen.getByText('Login'));

    // Expect onSubmit to have been called with credentials
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith({ username: 'alice', password: 'secret' });
  });
});
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, Link } from 'react-router-dom';

describe('Frontend integration tests - generic navigation, components, API, and forms', () => {
  // Components for routing tests
  function HomeRoute() {
    return <div data-testid="home-route">Home Page</div>;
  }

  function AboutRoute() {
    return <div data-testid="about-route">About Page</div>;
  }

  function RouterApp() {
    return (
      <MemoryRouter initialEntries={['/']}>
        <nav>
          <Link to="/home">Home</Link>
          <Link to="/about">About</Link>
        </nav>
        <Routes>
          <Route path="/" element={<div>Index</div>} />
          <Route path="/home" element={<HomeRoute />} />
          <Route path="/about" element={<AboutRoute />} />
        </Routes>
      </MemoryRouter>
    );
  }

  test('navigates between routes using in-app links', async () => {
    render(<RouterApp />);

    // initial content on root
    expect(screen.getByText('Index')).toBeInTheDocument();

    // navigate to Home
    const homeLink = screen.getByRole('link', { name: /home/i });
    userEvent.click(homeLink);
    await waitFor(() => expect(screen.getByTestId('home-route')).toBeInTheDocument());

    // navigate to About
    const aboutLink = screen.getByRole('link', { name: /about/i });
    userEvent.click(aboutLink);
    await waitFor(() => expect(screen.getByTestId('about-route')).toBeInTheDocument());
  });

  // Data flow between components
  function Child({ onAction }) {
    return <button onClick={() => onAction('child-clicked')}>Trigger</button>;
  }

  function Parent() {
    const [lastAction, setLastAction] = React.useState(null);
    return (
      <div>
        <Child onAction={setLastAction} />
        {lastAction && <span data-testid="parent-action">{lastAction}</span>}
      </div>
    );
  }

  test('data flow from child to parent via callback', () => {
    render(<Parent />);
    const button = screen.getByText(/trigger/i);
    userEvent.click(button);
    expect(screen.getByTestId('parent-action')).toHaveTextContent('child-clicked');
  });

  // API integration test
  function DataFetcher() {
    const [items, setItems] = React.useState([]);
    const [loading, setLoading] = React.useState(true);

    React.useEffect(() => {
      fetch('/api/items')
        .then((res) => res.json())
        .then((data) => {
          setItems(data);
          setLoading(false);
        });
    }, []);

    if (loading) return <div>Loading</div>;

    return (
      <ul>
        {items.map((it) => (
          <li key={it.id}>{it.name}</li>
        ))}
      </ul>
    );
  }

  test('fetches data from API and renders items', async () => {
    const mockData = [
      { id: 1, name: 'Item 1' },
      { id: 2, name: 'Item 2' },
    ];

    // Mock the global fetch
    global.fetch = jest.fn().mockResolvedValue({
      json: jest.fn().mockResolvedValue(mockData),
    });

    render(<DataFetcher />);

    // initial loading state
    expect(screen.getByText('Loading')).toBeInTheDocument();

    // wait for data to render
    await waitFor(() => expect(screen.getByText('Item 1')).toBeInTheDocument());
    expect(screen.getByText('Item 2')).toBeInTheDocument();

    // cleanup mock
    (global.fetch).mockRestore?.();
  });

  // Form submission test
  function SimpleForm({ onSubmit }) {
    const [value, setValue] = React.useState('');
    const handleSubmit = (e) => {
      e.preventDefault();
      onSubmit(value);
    };
    return (
      <form onSubmit={handleSubmit} aria-label="simple-form">
        <input aria-label="name" value={value} onChange={(e) => setValue(e.target.value)} />
        <button type="submit">Submit</button>
      </form>
    );
  }

  test('submits form data and calls onSubmit with input value', () => {
    const onSubmit = jest.fn();
    render(<SimpleForm onSubmit={onSubmit} />);
    const input = screen.getByLabelText(/name/i);

    userEvent.type(input, 'Alice');
    const submitBtn = screen.getByRole('button', { name: /submit/i });
    userEvent.click(submitBtn);

    expect(onSubmit).toHaveBeenCalledWith('Alice');
  });
});

afterEach(() => {
  jest.clearAllMocks();
});
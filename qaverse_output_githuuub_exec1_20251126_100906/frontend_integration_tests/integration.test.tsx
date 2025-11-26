import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, Link } from 'react-router-dom';

// Generic navigation components (no real app routes detected)
const NavigationTestApp = () => (
  <MemoryRouter initialEntries={['/home']}>
    <nav>
      <Link to="/home">Home</Link>
      <Link to="/about">About</Link>
      <Link to="/contact">Contact</Link>
    </nav>
    <Routes>
      <Route path="/home" element={<div>Home Page</div>} />
      <Route path="/about" element={<div>About Page</div>} />
      <Route path="/contact" element={<div>Contact Page</div>} />
    </Routes>
  </MemoryRouter>
);

// Data flow between components (parent -> child via props)
const ChildView = ({ value }) => <span data-testid="child-value">{value}</span>;

const ParentView = () => {
  const [value, setValue] = React.useState('initial');
  return (
    <div>
      <ChildView value={value} />
      <button onClick={() => setValue('updated')}>Update</button>
    </div>
  );
};

// Interaction: child triggering a callback to update parent state
const ChildButton = ({ onAction }) => (
  <button onClick={() => onAction('child-action')}>Do Action</button>
);

const ParentWithCallback = () => {
  const [logs, setLogs] = React.useState([]);
  const handleAction = (payload) => setLogs((l) => [...l, payload]);
  return (
    <div>
      <ChildButton onAction={handleAction} />
      <ul data-testid="actions">
        {logs.map((l, idx) => (
          <li key={idx}>{l}</li>
        ))}
      </ul>
    </div>
  );
};

// Simple form component for submission tests
const SimpleForm = ({ onSubmit }) => {
  const [name, setName] = React.useState('');
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(name);
      }}
    >
      <input
        data-testid="name-input"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Name"
      />
      <button type="submit">Submit</button>
    </form>
  );
};

// Generic API data fetch component
const ApiComponent = ({ endpoint, renderData }) => {
  const [data, setData] = React.useState(null);
  React.useEffect(() => {
    fetch(endpoint)
      .then((res) => res.json())
      .then((d) => setData(d));
  }, [endpoint]);
  if (!data) return <div>Loading</div>;
  return renderData(data);
};

// Tests
describe('Frontend integration tests (generic React app)', () => {
  test('navigation: can navigate between generic routes', async () => {
    render(<NavigationTestApp />);

    // Initial route content
    expect(screen.getByText('Home Page')).toBeInTheDocument();

    // Navigate to About
    userEvent.click(screen.getByText('About'));

    await waitFor(() => expect(screen.getByText('About Page')).toBeInTheDocument());

    // Navigate to Contact
    userEvent.click(screen.getByText('Contact'));
    await waitFor(() => expect(screen.getByText('Contact Page')).toBeInTheDocument());
  });

  test('data flow: parent passes data to child via props', () => {
    render(<ParentView />);

    // Child shows initial value from parent state
    expect(screen.getByTestId('child-value')).toHaveTextContent('initial');

    // Update parent state and ensure child reflects new value
    userEvent.click(screen.getByText('Update'));
    expect(screen.getByTestId('child-value')).toHaveTextContent('updated');
  });

  test('interaction: child triggers callback to update parent state', () => {
    render(<ParentWithCallback />);

    // Before action, log is empty
    expect(screen.queryByTestId('actions')).toBeInTheDocument();
    expect(screen.getByTestId('actions').querySelectorAll('li').length).toBe(0);

    // Perform action in child
    userEvent.click(screen.getByText('Do Action'));

    // Parent should update log
    waitFor(() =>
      expect(screen.getByTestId('actions').querySelectorAll('li').length).toBe(1)
    );
    waitFor(() => expect(screen.getByTestId('actions').textContent).toContain('child-action'));
  });

  test('form submission: collects input value and calls onSubmit', () => {
    const handleSubmit = jest.fn();
    render(<SimpleForm onSubmit={handleSubmit} />);

    const input = screen.getByTestId('name-input');
    userEvent.type(input, 'Alice');

    // Submit the form
    userEvent.click(screen.getByText('Submit'));

    expect(handleSubmit).toHaveBeenCalledWith('Alice');
  });

  test('API integration: fetches data and renders it', async () => {
    // Mock the API response
    const mockData = { message: 'Hello from API' };
    global.fetch = jest.fn().mockResolvedValue({
      json: jest.fn().mockResolvedValue(mockData),
    });

    const RenderData = (data) => (
      <div data-testid="message">{data.message}</div>
    );

    render(<ApiComponent endpoint="/api/hello" renderData={RenderData} />);

    // Initially shows loading
    expect(screen.getByText('Loading')).toBeInTheDocument();

    // Wait for data to render
    await waitFor(() =>
      expect(screen.getByTestId('message')).toHaveTextContent(mockData.message)
    );

    // Clean up mock
    global.fetch.mockClear();
    delete global.fetch;
  });
});
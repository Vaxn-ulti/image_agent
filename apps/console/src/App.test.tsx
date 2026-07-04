import { act, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./components/AppShell', () => ({
  AppShell: () => <div>Protected app shell</div>,
}));
vi.mock('./routes/DashboardPage', () => ({
  DashboardPage: () => <div>Dashboard route</div>,
}));

describe('App routing', () => {
  afterEach(() => {
    localStorage.clear();
    vi.resetModules();
  });

  it('shows the login form when opening the root route without a token', async () => {
    localStorage.clear();
    window.history.pushState({}, '', '/');
    const { App } = await import('./App');

    render(<App />);

    expect(await screen.findByText('Brain Image Agent Console')).toBeInTheDocument();
    expect(screen.getByLabelText('Username')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toHaveValue('');
  });

  it('returns a protected dashboard route to login when the stored session expires', async () => {
    localStorage.setItem('imageAgentAuthToken', 'stale-token');
    const { RequireAuth } = await import('./App');

    render(
      <MemoryRouter initialEntries={['/projects/33/dashboard']}>
        <Routes>
          <Route element={<div>Login route</div>} path="/login" />
          <Route
            element={
              <RequireAuth>
                <div>Protected app shell</div>
              </RequireAuth>
            }
            path="/projects/:projectId/dashboard"
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Protected app shell')).toBeInTheDocument();

    act(() => {
      window.dispatchEvent(new Event('image-agent-auth-expired'));
    });

    expect(await screen.findByText('Login route')).toBeInTheDocument();
  });
});

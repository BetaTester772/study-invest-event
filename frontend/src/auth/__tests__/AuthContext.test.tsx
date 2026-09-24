import { act, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ApiError, meApi, tokenStore, type Participant } from '../../api';
import { AuthProvider, useAuth } from '../AuthContext';
import { RequireAuth } from '../RequireAuth';

const ME: Participant = { id: 1, nickname: 'alice', status: 'normal', joined_at: '2026-10-06T09:00:00+09:00' };

function Probe() {
  const { status, participant } = useAuth();
  return (
    <p>
      {status}:{participant?.nickname ?? '-'}
    </p>
  );
}

function renderApp() {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/portfolio']}>
        <Routes>
          <Route
            path="/portfolio"
            element={
              <RequireAuth>
                <p>protected page</p>
              </RequireAuth>
            }
          />
          <Route path="/login" element={<p>login page</p>} />
        </Routes>
        <Probe />
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    tokenStore.set('valid-token');
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    tokenStore.set(null);
  });

  it('keeps the session on a network error and retries the profile', async () => {
    const me = vi
      .spyOn(meApi, 'me')
      .mockRejectedValueOnce(new ApiError(0, 'NETWORK', 'offline'))
      .mockResolvedValueOnce(ME);
    renderApp();
    await waitFor(() => expect(screen.getByText('authenticated:-')).toBeInTheDocument());
    expect(screen.getByText('protected page')).toBeInTheDocument(); // /login으로 보내지 않음
    expect(tokenStore.get()).toBe('valid-token');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });
    await waitFor(() => expect(screen.getByText('authenticated:alice')).toBeInTheDocument());
    expect(me).toHaveBeenCalledTimes(2);
  });

  it('keeps the session on a 5xx', async () => {
    vi.spyOn(meApi, 'me').mockRejectedValue(new ApiError(503, 'DB_BUSY', 'busy'));
    renderApp();
    await waitFor(() => expect(screen.getByText('protected page')).toBeInTheDocument());
  });

  it('ends the session only when the server rejects the token', async () => {
    vi.spyOn(meApi, 'me').mockRejectedValue(new ApiError(401, 'UNAUTHORIZED', 'no'));
    renderApp();
    await waitFor(() => expect(screen.getByText('login page')).toBeInTheDocument());
    expect(tokenStore.get()).toBeNull();
  });
});

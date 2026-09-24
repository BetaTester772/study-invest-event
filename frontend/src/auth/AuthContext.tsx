import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { ApiError, authApi, meApi, onUnauthorized, tokenStore, type Participant } from '../api';

type AuthStatus = 'loading' | 'authenticated' | 'anonymous';

export interface AuthContextValue {
  status: AuthStatus;
  participant: Participant | null;
  login: (identity: string, password: string) => Promise<Participant>;
  register: (identity: string, nickname: string, password: string) => Promise<Participant>;
  logout: () => Promise<void>;
  /** Re-fetch /me (e.g. after status changes). */
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [participant, setParticipant] = useState<Participant | null>(null);
  const [status, setStatus] = useState<AuthStatus>(() => (tokenStore.get() ? 'loading' : 'anonymous'));

  const clear = useCallback(() => {
    tokenStore.set(null);
    setParticipant(null);
    setStatus('anonymous');
  }, []);

  const refresh = useCallback(async () => {
    if (!tokenStore.get()) {
      clear();
      return;
    }
    try {
      const me = await meApi.me();
      setParticipant(me);
      setStatus('authenticated');
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        clear();
      } else {
        // Network hiccup: keep the token, treat as signed in with unknown profile.
        setStatus(participant ? 'authenticated' : 'anonymous');
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clear]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(
    () =>
      onUnauthorized((mode) => {
        if (mode === 'participant') clear();
      }),
    [clear],
  );

  const login = useCallback(async (identity: string, password: string) => {
    const res = await authApi.login({ identity, password });
    tokenStore.set(res.token);
    setParticipant(res.participant);
    setStatus('authenticated');
    return res.participant;
  }, []);

  const register = useCallback(async (identity: string, nickname: string, password: string) => {
    const res = await authApi.register({ identity, nickname, password });
    tokenStore.set(res.token);
    setParticipant(res.participant);
    setStatus('authenticated');
    return res.participant;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      /* token may already be invalid — clear locally regardless */
    }
    clear();
  }, [clear]);

  const value = useMemo(
    () => ({ status, participant, login, register, logout, refresh }),
    [status, participant, login, register, logout, refresh],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}

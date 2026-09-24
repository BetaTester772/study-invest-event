import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ApiError, authApi, meApi, onUnauthorized, tokenStore, type Participant } from '../api';

/**
 * 세션 상태는 **토큰**이 정한다. 프로필(/me)은 세션에 딸린 데이터일 뿐이다.
 * - loading: 토큰이 있고 첫 /me 결과를 기다리는 중
 * - authenticated: 토큰이 있고 서버가 거절하지 않음(프로필은 아직 못 받았을 수도 있음)
 * - anonymous: 토큰 없음, 또는 서버가 401/403으로 거절
 * 네트워크 오류·5xx는 세션을 끝내지 않는다(프로필만 다시 시도).
 */
type AuthStatus = 'loading' | 'authenticated' | 'anonymous';

/** 프로필 재시도 간격(ms). 실패할 때마다 늘리고 마지막 값에서 멈춘다. */
const PROFILE_RETRY_MS = [2_000, 5_000, 15_000, 30_000];

export interface AuthContextValue {
  status: AuthStatus;
  /** 서버에서 받은 프로필. 세션은 있지만 아직 못 받았으면 null. */
  participant: Participant | null;
  login: (identity: string, password: string) => Promise<Participant>;
  register: (identity: string, nickname: string, password: string) => Promise<Participant>;
  logout: () => Promise<void>;
  /** Re-fetch /me (e.g. after status changes). */
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function isRejection(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 401 || err.status === 403);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [participant, setParticipant] = useState<Participant | null>(null);
  const [status, setStatus] = useState<AuthStatus>(() => (tokenStore.get() ? 'loading' : 'anonymous'));
  const retry = useRef<{ timer: number | undefined; attempt: number }>({ timer: undefined, attempt: 0 });
  /** 로그인·로그아웃마다 증가. 이전 세션의 /me 응답이 새 세션을 덮지 않게 한다. */
  const session = useRef(0);

  const cancelRetry = useCallback(() => {
    window.clearTimeout(retry.current.timer);
    retry.current = { timer: undefined, attempt: 0 };
  }, []);

  const clear = useCallback(() => {
    session.current += 1;
    cancelRetry();
    tokenStore.set(null);
    setParticipant(null);
    setStatus('anonymous');
  }, [cancelRetry]);

  const refresh = useCallback(async (): Promise<void> => {
    if (!tokenStore.get()) {
      clear();
      return;
    }
    const mySession = session.current;
    window.clearTimeout(retry.current.timer);
    try {
      const me = await meApi.me();
      if (mySession !== session.current) return;
      retry.current.attempt = 0;
      setParticipant(me);
      setStatus('authenticated');
    } catch (err) {
      if (mySession !== session.current) return;
      if (isRejection(err)) {
        clear();
        return;
      }
      // 서버가 토큰을 거절하지 않았다 → 세션 유지, 프로필만 나중에 다시 받는다.
      setStatus('authenticated');
      const delay = PROFILE_RETRY_MS[Math.min(retry.current.attempt, PROFILE_RETRY_MS.length - 1)];
      retry.current.attempt += 1;
      retry.current.timer = window.setTimeout(() => void refresh(), delay);
    }
  }, [clear]);

  useEffect(() => {
    void refresh();
    return () => window.clearTimeout(retry.current.timer);
  }, [refresh]);

  useEffect(
    () =>
      onUnauthorized((mode) => {
        if (mode === 'participant') clear();
      }),
    [clear],
  );

  const startSession = useCallback(
    (token: string, me: Participant) => {
      session.current += 1;
      cancelRetry();
      tokenStore.set(token);
      setParticipant(me);
      setStatus('authenticated');
    },
    [cancelRetry],
  );

  const login = useCallback(async (identity: string, password: string) => {
    const res = await authApi.login({ identity, password });
    startSession(res.token, res.participant);
    return res.participant;
  }, [startSession]);

  const register = useCallback(async (identity: string, nickname: string, password: string) => {
    const res = await authApi.register({ identity, nickname, password });
    startSession(res.token, res.participant);
    return res.participant;
  }, [startSession]);

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

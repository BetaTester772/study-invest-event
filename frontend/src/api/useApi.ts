import { useCallback, useEffect, useRef, useState, type DependencyList } from 'react';
import { ApiError } from './client';

export interface UseApiResult<T> {
  data: T | undefined;
  error: ApiError | undefined;
  /** True while the first load (or a load after deps change) is in flight. */
  loading: boolean;
  /** True during any fetch, including background refetches. */
  fetching: boolean;
  refetch: () => Promise<T | undefined>;
  /** Optimistically replace data (e.g. after a mutation returns the new object). */
  setData: (updater: T | ((prev: T | undefined) => T)) => void;
}

export interface UseApiOptions {
  /** Skip fetching while false. */
  enabled?: boolean;
  /** Poll every N ms (paused while the tab is hidden). */
  refreshInterval?: number;
}

function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  return new ApiError(0, 'UNKNOWN', err instanceof Error ? err.message : '알 수 없는 오류가 생겼어요.');
}

/** 두 의존성 목록이 같은지(Object.is로 항목별 비교, React 의존성 규칙과 같음). */
function sameDeps(a: DependencyList, b: DependencyList): boolean {
  return a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
}

/** 결과(data·error)는 그것을 요청한 의존성 목록에 묶어 둔다. */
interface Entry<T> {
  deps: DependencyList;
  data: T | undefined;
  error: ApiError | undefined;
}

/**
 * Minimal query hook: runs `fetcher` on mount and whenever `deps` change,
 * ignores stale responses, and exposes loading/error/refetch.
 *
 * 결과는 요청한 의존성(`deps`)에 묶인다. 의존성이 바뀌거나 `enabled`가 false가 되면 그 즉시
 * (같은 렌더에서) 이전 결과를 돌려주지 않고, 진행 중이던 요청의 응답도 버린다. 그래서 로그아웃·
 * 계정 전환 뒤에 이전 사용자의 데이터가 한 순간도 보이지 않는다.
 */
export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: DependencyList,
  options: UseApiOptions = {},
): UseApiResult<T> {
  const { enabled = true, refreshInterval } = options;
  const [entry, setEntry] = useState<Entry<T> | undefined>(undefined);
  const [fetching, setFetching] = useState(enabled);
  const requestId = useRef(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const depsRef = useRef(deps);
  depsRef.current = deps;

  const run = useCallback(async (): Promise<T | undefined> => {
    const id = ++requestId.current;
    const requestDeps = depsRef.current;
    setFetching(true);
    try {
      const result = await fetcherRef.current();
      if (id === requestId.current) setEntry({ deps: requestDeps, data: result, error: undefined });
      return result;
    } catch (err) {
      if (id === requestId.current) {
        setEntry((prev) => ({
          deps: requestDeps,
          // 같은 의존성으로 다시 불렀다 실패하면 이전 데이터는 유지(재시도 중 화면 유지)
          data: prev && sameDeps(prev.deps, requestDeps) ? prev.data : undefined,
          error: toApiError(err),
        }));
      }
      return undefined;
    } finally {
      if (id === requestId.current) setFetching(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      requestId.current += 1; // 진행 중인 응답 무시
      setEntry(undefined);
      setFetching(false);
      return;
    }
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, run, ...deps]);

  useEffect(() => {
    if (!enabled || !refreshInterval) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'hidden') void run();
    }, refreshInterval);
    return () => window.clearInterval(timer);
  }, [enabled, refreshInterval, run]);

  const setData = useCallback((updater: T | ((prev: T | undefined) => T)) => {
    setEntry((prev) => {
      const current = prev && sameDeps(prev.deps, depsRef.current) ? prev.data : undefined;
      const data =
        typeof updater === 'function' ? (updater as (p: T | undefined) => T)(current) : updater;
      return { deps: depsRef.current, data, error: undefined };
    });
  }, []);

  // 렌더 시점에 현재 의존성과 맞는 결과만 노출한다(effect가 돌기 전 첫 렌더에서도).
  const current = enabled && entry && sameDeps(entry.deps, deps) ? entry : undefined;
  return {
    data: current?.data,
    error: current?.error,
    // 현재 의존성에 대한 결과(성공·실패)가 아직 없으면 로딩 중
    loading: enabled && current === undefined,
    fetching,
    refetch: run,
    setData,
  };
}

/** Load an auth-protected image into an object URL; revoked on change/unmount. */
export function useObjectUrl(load: (() => Promise<Blob>) | null, deps: DependencyList) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | undefined>(undefined);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!load) {
      setUrl(null);
      return;
    }
    let cancelled = false;
    let objectUrl: string | null = null;
    setLoading(true);
    setError(undefined);
    load()
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch((err) => {
        if (!cancelled) setError(toApiError(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setUrl(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { url, error, loading };
}

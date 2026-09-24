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

/**
 * Minimal query hook: runs `fetcher` on mount and whenever `deps` change,
 * ignores stale responses, and exposes loading/error/refetch.
 */
export function useApi<T>(fetcher: () => Promise<T>, deps: DependencyList, options: UseApiOptions = {}): UseApiResult<T> {
  const { enabled = true, refreshInterval } = options;
  const [data, setDataState] = useState<T | undefined>(undefined);
  const [error, setError] = useState<ApiError | undefined>(undefined);
  const [fetching, setFetching] = useState(enabled);
  const [loaded, setLoaded] = useState(false);
  const requestId = useRef(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const run = useCallback(async (): Promise<T | undefined> => {
    const id = ++requestId.current;
    setFetching(true);
    try {
      const result = await fetcherRef.current();
      if (id === requestId.current) {
        setDataState(result);
        setError(undefined);
      }
      return result;
    } catch (err) {
      if (id === requestId.current) setError(toApiError(err));
      return undefined;
    } finally {
      if (id === requestId.current) {
        setFetching(false);
        setLoaded(true);
      }
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      setFetching(false);
      return;
    }
    setLoaded(false);
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
    setDataState((prev) => (typeof updater === 'function' ? (updater as (p: T | undefined) => T)(prev) : updater));
  }, []);

  return { data, error, loading: enabled && !loaded && fetching, fetching, refetch: run, setData };
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

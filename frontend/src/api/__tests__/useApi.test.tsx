import { act, renderHook, waitFor } from '@testing-library/react';
import { useApi } from '../useApi';

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe('useApi', () => {
  it('drops data in the same render when disabled (e.g. logout)', async () => {
    const { result, rerender } = renderHook(({ enabled }) => useApi(async () => ['alice-cert'], [enabled], { enabled }), {
      initialProps: { enabled: true },
    });
    await waitFor(() => expect(result.current.data).toEqual(['alice-cert']));
    rerender({ enabled: false });
    expect(result.current.data).toBeUndefined();
    expect(result.current.loading).toBe(false);
  });

  it('never exposes the previous key’s data after deps change', async () => {
    const pending = deferred<string>();
    const fetcher = vi.fn(async (user: string) => (user === 'alice' ? 'alice-data' : pending.promise));
    const { result, rerender } = renderHook(({ user }) => useApi(() => fetcher(user), [user]), {
      initialProps: { user: 'alice' },
    });
    await waitFor(() => expect(result.current.data).toBe('alice-data'));
    rerender({ user: 'bob' });
    expect(result.current.data).toBeUndefined(); // 같은 렌더에서 바로
    expect(result.current.loading).toBe(true);
    await act(async () => pending.resolve('bob-data'));
    expect(result.current.data).toBe('bob-data');
  });

  it('ignores a response that arrives after being disabled', async () => {
    const pending = deferred<string>();
    const { result, rerender } = renderHook(({ enabled }) => useApi(() => pending.promise, [], { enabled }), {
      initialProps: { enabled: true },
    });
    rerender({ enabled: false });
    await act(async () => pending.resolve('late-previous-user-data'));
    expect(result.current.data).toBeUndefined();
  });

  it('keeps data for the same key when a refetch fails', async () => {
    let fail = false;
    const { result } = renderHook(() =>
      useApi(async () => {
        if (fail) throw new Error('boom');
        return 'ok';
      }, []),
    );
    await waitFor(() => expect(result.current.data).toBe('ok'));
    fail = true;
    await act(async () => {
      await result.current.refetch();
    });
    expect(result.current.data).toBe('ok');
    expect(result.current.error?.message).toBe('boom');
  });
});

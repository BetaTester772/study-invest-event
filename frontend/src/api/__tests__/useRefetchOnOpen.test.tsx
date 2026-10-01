import { renderHook } from '@testing-library/react';
import type { EventInfo } from '../types';
import { openedDay, useRefetchOnOpen } from '../useRefetchOnOpen';

function event(today: string, dayOpened: boolean): EventInfo {
  return { today, market: { day_opened: dayOpened } } as EventInfo;
}

function setup(initial: EventInfo | undefined) {
  const refetch = vi.fn();
  const hook = renderHook(({ ev }) => useRefetchOnOpen(ev, refetch), { initialProps: { ev: initial } });
  return { refetch, show: (ev: EventInfo | undefined) => hook.rerender({ ev }) };
}

describe('openedDay', () => {
  it('is the day only after its open', () => {
    expect(openedDay(undefined)).toBeUndefined();
    expect(openedDay(event('2026-10-06', false))).toBeNull();
    expect(openedDay(event('2026-10-06', true))).toBe('2026-10-06');
  });
});

describe('useRefetchOnOpen', () => {
  it('does not refetch for the first known state', () => {
    const { refetch, show } = setup(undefined);
    show(event('2026-10-06', true));
    show(event('2026-10-06', true));
    expect(refetch).not.toHaveBeenCalled();
  });

  it('refetches once when today’s open is published while the page is open', () => {
    const { refetch, show } = setup(event('2026-10-06', false));
    show(event('2026-10-06', true));
    show(event('2026-10-06', true));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('ignores the day change before the next open, then refetches on it', () => {
    const { refetch, show } = setup(event('2026-10-06', true));
    show(event('2026-10-07', false)); // 자정: 가격은 아직 그대로
    expect(refetch).not.toHaveBeenCalled();
    show(event('2026-10-07', true));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('refetches when a whole day passed between checks', () => {
    const { refetch, show } = setup(event('2026-10-06', true));
    show(event('2026-10-07', true));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});

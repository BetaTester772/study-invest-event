import { useEffect, useRef } from 'react';
import type { EventInfo } from './types';

/**
 * 공시된 운영일. 장 상태를 아직 모르면 undefined, 오늘 공시 전이면 null.
 * 시작가는 공시 때만 바뀌므로, 이 값이 바뀌면 가격이 바뀐 것이다.
 */
export function openedDay(event: EventInfo | undefined): string | null | undefined {
  if (!event) return undefined;
  return event.market.day_opened ? event.today : null;
}

/**
 * 화면을 연 뒤 새 시작가가 공시되면 `refetch`를 한 번 부른다(가격 그래프·현재가·보유 평가액).
 * 장 상태(`event`)는 호출하는 쪽이 주기적으로 받아 온다. 가격이 그대로면 추가 요청이 없다.
 */
export function useRefetchOnOpen(event: EventInfo | undefined, refetch: () => void): void {
  const day = openedDay(event);
  const seen = useRef(day);
  const refetchRef = useRef(refetch);
  refetchRef.current = refetch;

  useEffect(() => {
    if (day === undefined) return;
    const prev = seen.current;
    seen.current = day;
    if (prev !== undefined && day !== null && day !== prev) refetchRef.current();
  }, [day]);
}

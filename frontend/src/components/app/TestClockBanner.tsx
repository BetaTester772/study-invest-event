import { useEffect, useState } from 'react';
import { publicApi, useApi, type ClockInfo } from '../../api';
import { formatClockTime, formatDayLength } from '../../lib/format';
import { Alert, Container, Stack } from '../ui';

/** Explains a sped-up test clock (QA servers) in real-world time. */
export function TestClockNotice({ clock }: { clock: ClockInfo }) {
  // 먼저 오는 일정부터(장중에는 오늘 마감이 다음 날 공시보다 앞선다)
  const upcoming = [
    { label: '다음 장 마감(18:00)', at: clock.next_close_at },
    { label: '다음 공시(09:00)', at: clock.next_open_at },
  ]
    .filter((u): u is { label: string; at: string } => u.at !== null)
    .sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
  return (
    <Alert title={`QA 테스트 시계예요. 실제 ${formatDayLength(clock.scale)}이 이벤트 하루예요.`}>
      화면의 날짜와 시각은 테스트 시계 기준이에요.{' '}
      {upcoming.length === 0 ? (
        '테스트 시계로 이벤트 기간이 끝났어요.'
      ) : (
        <>
          실제 시각으로{' '}
          {upcoming.map((u, i) => (
            <span key={u.label}>
              {i > 0 && ', '}
              {u.label} <strong>{formatClockTime(u.at)}</strong>
            </span>
          ))}
          이에요.
        </>
      )}
    </Alert>
  );
}

/** QA unlimited mode: the event has no end date. */
export function UnlimitedNotice() {
  return (
    <Alert title="QA 무제한 모드예요.">
      이벤트 종료일 없이 매일 공시·정산이 이어져요. 실제 이벤트 기간과 상관없이 가격 추세를 길게 볼 수 있어요.
    </Alert>
  );
}

/** Top-of-page banner. Renders nothing on the real clock and period (production). */
export function TestClockBanner() {
  // Keep polling only where there is a test clock; production fetches once.
  const [poll, setPoll] = useState(false);
  const event = useApi(() => publicApi.event(), [], { refreshInterval: poll ? 30_000 : undefined });
  const clock = event.data?.clock ?? null;
  const unlimited = event.data?.end === null;
  useEffect(() => setPoll(clock !== null), [clock]);
  if (!clock && !unlimited) return null;
  return (
    <Container padTop>
      <Stack gap={3}>
        {unlimited && <UnlimitedNotice />}
        {clock && <TestClockNotice clock={clock} />}
      </Stack>
    </Container>
  );
}

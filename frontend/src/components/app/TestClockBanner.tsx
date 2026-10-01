import { useEffect, useState } from 'react';
import { publicApi, useApi, type ClockInfo } from '../../api';
import { formatClockTime, formatDayLength } from '../../lib/format';
import { Alert, Container } from '../ui';

/** Explains a sped-up test clock (QA servers) in real-world time. */
export function TestClockNotice({ clock }: { clock: ClockInfo }) {
  return (
    <Alert title={`QA 테스트 시계예요. 실제 ${formatDayLength(clock.scale)}이 이벤트 하루예요.`}>
      화면의 날짜와 시각은 테스트 시계 기준이에요. 실제 시각으로 다음 공시(09:00)는{' '}
      <strong>{formatClockTime(clock.next_open_at)}</strong>, 다음 마감·정산(18:00)은{' '}
      <strong>{formatClockTime(clock.next_close_at)}</strong>이에요.
    </Alert>
  );
}

/** Top-of-page banner. Renders nothing on the real clock (production). */
export function TestClockBanner() {
  // Keep polling only where there is a test clock; production fetches once.
  const [poll, setPoll] = useState(false);
  const event = useApi(() => publicApi.event(), [], { refreshInterval: poll ? 30_000 : undefined });
  const clock = event.data?.clock ?? null;
  useEffect(() => setPoll(clock !== null), [clock]);
  if (!clock) return null;
  return (
    <Container padTop>
      <TestClockNotice clock={clock} />
    </Container>
  );
}

import type { EventInfo } from '../../api';
import { dayStripWindow, describeMarket } from '../../lib/market';
import { formatDay } from '../../lib/format';
import { Badge, Card, DayStrip, Stack, Text } from '../ui';

/** Market-page hero: plain-language market state + the event as a planner row. */
export function MarketStatus({ event, stamped }: { event: EventInfo; stamped?: string[] }) {
  const s = describeMarket(event);
  const unlimited = event.end === null;
  return (
    <Card padding="lg" as="section" aria-labelledby="market-status-headline">
      <Stack gap={5}>
        <Stack gap={2}>
          <Stack direction="row" gap={2} align="center" wrap>
            <Badge tone={s.canTrade ? 'success' : 'neutral'} dot>
              {s.canTrade ? '주문 받는 중' : '주문 쉬는 중'}
            </Badge>
            {event.market.round != null && (
              <Badge tone="highlight">
                {event.total_rounds != null
                  ? `${event.market.round}회차 / 전체 ${event.total_rounds}회차`
                  : `${event.market.round}회차`}
              </Badge>
            )}
            {unlimited && <Badge tone="info">QA 무제한</Badge>}
          </Stack>
          <Text as="p" display size="3xl" tone="ink" id="market-status-headline">
            {s.headline}
          </Text>
          <Text tone="muted">{s.detail}</Text>
          <Text size="sm" tone="muted">
            오늘은 {formatDay(event.today)}
            {s.dayNumber == null
              ? '입니다.'
              : unlimited
                ? `, ${s.dayNumber}일째 날입니다.`
                : `, ${event.operating_days.length}일 중 ${s.dayNumber}일째 날입니다.`}
          </Text>
        </Stack>
        <DayStrip {...dayStripWindow(event)} today={event.today} stamped={stamped} label="이벤트 운영일" />
      </Stack>
    </Card>
  );
}

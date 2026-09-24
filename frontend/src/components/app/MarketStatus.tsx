import type { EventInfo } from '../../api';
import { describeMarket } from '../../lib/market';
import { formatDay } from '../../lib/format';
import { Badge, Card, DayStrip, Stack, Text } from '../ui';

/** Market-page hero: plain-language market state + the event as a planner row. */
export function MarketStatus({ event, stamped }: { event: EventInfo; stamped?: string[] }) {
  const s = describeMarket(event);
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
                {event.market.round}회차 / 전체 {event.total_rounds}회차
              </Badge>
            )}
          </Stack>
          <Text as="p" display size="3xl" tone="ink" id="market-status-headline">
            {s.headline}
          </Text>
          <Text tone="muted">{s.detail}</Text>
          <Text size="sm" tone="muted">
            오늘은 {formatDay(event.today)}
            {s.dayNumber != null ? `, ${event.operating_days.length}일 중 ${s.dayNumber}일째 날이에요.` : '이에요.'}
          </Text>
        </Stack>
        <DayStrip days={event.operating_days} today={event.today} stamped={stamped} label="이벤트 운영일" />
      </Stack>
    </Card>
  );
}

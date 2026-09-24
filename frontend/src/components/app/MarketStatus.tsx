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
        <Stack direction="row" justify="between" align="start" gap={4} wrap>
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
          </Stack>
          <Stack gap={1} align="end">
            <Text size="sm" tone="muted">
              오늘
            </Text>
            <Text weight="semibold">{formatDay(event.today)}</Text>
            {s.dayNumber != null && (
              <Text size="sm" tone="muted">
                {event.operating_days.length}일 중 {s.dayNumber}일째
              </Text>
            )}
          </Stack>
        </Stack>
        <DayStrip days={event.operating_days} today={event.today} stamped={stamped} label="이벤트 운영일" />
      </Stack>
    </Card>
  );
}

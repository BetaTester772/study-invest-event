import { Link } from 'react-router-dom';
import type { NewsItem } from '../../api';
import { formatDayShort } from '../../lib/format';
import { Card, Skeleton, Stack, Text } from '../ui';
import { NewsBadge } from './badges';
import styles from './NewsCard.module.css';

function Item({ item, showDay }: { item: NewsItem; showDay?: boolean }) {
  return (
    <li className={styles.item}>
      <NewsBadge kind={item.kind} rate={item.rate} />
      <Link to={`/instruments/${item.code}`} className={styles.headline}>
        {item.headline}
      </Link>
      <span className={styles.meta}>{showDay ? formatDayShort(item.day) : item.name}</span>
    </li>
  );
}

/**
 * Today's 호재·악재 and a short history. News is announced with the 09:00 prices and
 * multiplied into that day's 18:00 settlement, so it is something to trade on, not a result.
 */
export function NewsCard({
  news,
  loading,
  today,
}: {
  news?: NewsItem[];
  loading?: boolean;
  /** The quote board's day; news on this day is "today's". */
  today: string | null | undefined;
}) {
  if (loading && !news) {
    return (
      <Card title="오늘의 뉴스">
        <Skeleton lines={2} height="1.5rem" />
      </Card>
    );
  }
  const list = news ?? [];
  const todays = today ? list.filter((n) => n.day === today) : [];
  const past = list.filter((n) => !today || n.day !== today).slice(0, 10);
  return (
    <Card
      title="오늘의 뉴스"
      description="09:00 공시와 함께 발표되고, 오늘 18:00 정산 때 그 종목 변동률에 곱해져요. 호재 종목에 매수가 몰리면 쏠림 때문에 내려갈 수도 있어요."
    >
      <Stack gap={4}>
        {todays.length > 0 ? (
          <ul className={styles.list} aria-label="오늘의 뉴스">
            {todays.map((n) => (
              <Item key={n.id} item={n} />
            ))}
          </ul>
        ) : (
          <Text tone="muted">오늘은 발표된 뉴스가 없어요.</Text>
        )}
        {past.length > 0 && (
          <details className={styles.past}>
            <summary className={styles.summary}>지난 뉴스 {past.length}건</summary>
            <ul className={styles.list} aria-label="지난 뉴스">
              {past.map((n) => (
                <Item key={n.id} item={n} showDay />
              ))}
            </ul>
          </details>
        )}
      </Stack>
    </Card>
  );
}

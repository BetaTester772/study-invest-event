import { Link } from 'react-router-dom';
import type { NewsItem } from '../../api';
import { formatDayShort } from '../../lib/format';
import { Card, Skeleton, Stack, Text } from '../ui';
import { NewsBadge } from './badges';
import styles from './NewsCard.module.css';

/** One article. Headline is a link to the instrument; the body opens inline when there is one. */
export function NewsArticle({ item, showDay }: { item: NewsItem; showDay?: boolean }) {
  const head = (
    <span className={styles.head}>
      <NewsBadge kind={item.kind} rate={item.rate} />
      <Link to={`/instruments/${item.code}`} className={styles.headline}>
        {item.headline}
      </Link>
      <span className={styles.meta}>{showDay ? formatDayShort(item.day) : item.name}</span>
    </span>
  );
  if (!item.body && !item.subtitle) return <li className={styles.item}>{head}</li>;
  return (
    <li className={styles.item}>
      <details className={styles.article}>
        <summary className={styles.summary}>{head}</summary>
        <div className={styles.body}>
          {item.subtitle && <p className={styles.subtitle}>{item.subtitle}</p>}
          {item.body && <p className={styles.text}>{item.body}</p>}
          {item.byline && <p className={styles.byline}>{item.byline}</p>}
        </div>
      </details>
    </li>
  );
}

/**
 * Today's 호재·악재 and a short history. News is drawn in the previous evening's settlement and
 * already multiplied into today's opening price; it explains the move rather than predicting it.
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
      description="오늘 시작가에 이미 반영된 뉴스입니다. 제목을 누르면 기사를 확인할 수 있습니다."
    >
      <Stack gap={4}>
        {todays.length > 0 ? (
          <ul className={styles.list} aria-label="오늘의 뉴스">
            {todays.map((n) => (
              <NewsArticle key={n.id} item={n} />
            ))}
          </ul>
        ) : (
          <Text tone="muted">오늘은 발표된 뉴스가 없습니다.</Text>
        )}
        {past.length > 0 && (
          <details className={styles.past}>
            <summary className={styles.summary}>지난 뉴스 {past.length}건</summary>
            <ul className={styles.list} aria-label="지난 뉴스">
              {past.map((n) => (
                <NewsArticle key={n.id} item={n} showDay />
              ))}
            </ul>
          </details>
        )}
      </Stack>
    </Card>
  );
}

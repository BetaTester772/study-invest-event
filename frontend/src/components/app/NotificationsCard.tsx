import type { NotificationInbox, NotificationItem } from '../../api';
import { formatDateTime } from '../../lib/format';
import { cx } from '../../lib/cx';
import { Badge, Button, Card, Skeleton, Stack, Text } from '../ui';
import styles from './NotificationsCard.module.css';

const SHOWN = 5;

function Notification({ item, onOpen }: { item: NotificationItem; onOpen: (item: NotificationItem) => void }) {
  const unread = item.read_at == null;
  return (
    <li className={cx(styles.item, unread && styles.unread)}>
      <details
        onToggle={(e) => {
          if ((e.currentTarget as HTMLDetailsElement).open && unread) onOpen(item);
        }}
      >
        <summary className={styles.summary}>
          <span className={styles.titleRow}>
            {unread && (
              <Badge tone="highlight" size="sm" dot>
                새 알림
              </Badge>
            )}
            {item.personal && (
              <Badge tone="info" size="sm">
                나에게
              </Badge>
            )}
            <span className={styles.title}>{item.title}</span>
          </span>
          <span className={styles.meta}>{formatDateTime(item.created_at)}</span>
        </summary>
        <p className={styles.body}>{item.body}</p>
      </details>
    </li>
  );
}

/**
 * 운영진이 보낸 알림. 안 읽은 알림은 강조해 위에 보이고, 펼치면 읽음으로 바뀐다.
 * 읽음 상태는 서버에 남아 다른 기기에서도 같다.
 */
export function NotificationsCard({
  inbox,
  loading,
  onRead,
}: {
  inbox?: NotificationInbox;
  loading?: boolean;
  /** ids를 생략하면 모두 읽음. */
  onRead: (ids?: number[]) => void;
}) {
  if (loading && !inbox) {
    return (
      <Card title="알림">
        <Skeleton lines={2} height="1.5rem" />
      </Card>
    );
  }
  const items = inbox?.items ?? [];
  const unread = inbox?.unread ?? 0;
  // 안 읽은 알림을 먼저, 같은 상태끼리는 최신부터(서버 순서 유지).
  const ordered = [...items.filter((i) => i.read_at == null), ...items.filter((i) => i.read_at != null)];
  const shown = ordered.slice(0, Math.max(SHOWN, unread));
  const rest = ordered.slice(shown.length);
  const open = (item: NotificationItem) => onRead([item.id]);
  return (
    <Card
      title={
        <span className={styles.cardTitle}>
          알림
          {unread > 0 && (
            <Badge tone="highlight" aria-label={`안 읽은 알림 ${unread}개`}>
              {unread}
            </Badge>
          )}
        </span>
      }
      description={unread > 0 ? `안 읽은 알림이 ${unread}개 있습니다. 제목을 누르면 내용을 볼 수 있습니다.` : undefined}
      actions={
        unread > 0 ? (
          <Button size="sm" variant="secondary" onClick={() => onRead()}>
            모두 읽음
          </Button>
        ) : undefined
      }
    >
      {items.length === 0 ? (
        <Text tone="muted">아직 받은 알림이 없습니다.</Text>
      ) : (
        <Stack gap={3}>
          <ul className={styles.list} aria-label="알림">
            {shown.map((n) => (
              <Notification key={n.id} item={n} onOpen={open} />
            ))}
          </ul>
          {rest.length > 0 && (
            <details className={styles.more}>
              <summary>지난 알림 {rest.length}개</summary>
              <ul className={styles.list} aria-label="지난 알림">
                {rest.map((n) => (
                  <Notification key={n.id} item={n} onOpen={open} />
                ))}
              </ul>
            </details>
          )}
        </Stack>
      )}
    </Card>
  );
}

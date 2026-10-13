import { useState } from 'react';
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
          <span className={styles.meta}>
            {formatDateTime(item.created_at)}
            {item.updated_at && ' · 수정됨'}
          </span>
        </summary>
        <p className={styles.body}>{item.body}</p>
      </details>
    </li>
  );
}

/**
 * 운영진이 보낸 알림(최신부터). 안 읽은 알림은 강조하고 펼치면 읽음으로 바뀐다.
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
  // 이번 화면에서 펼친 알림. 읽음으로 바뀌어도 자리를 옮기지 않게(접힌 '지난 알림'으로 밀리지 않게) 기억한다.
  const [opened, setOpened] = useState<ReadonlySet<number>>(() => new Set());
  if (loading && !inbox) {
    return (
      <Card title="알림">
        <Skeleton lines={2} height="1.5rem" />
      </Card>
    );
  }
  const items = inbox?.items ?? [];
  const unread = inbox?.unread ?? 0;
  // 순서는 서버 그대로(최신부터) 두고, 안 읽은 알림과 이번에 펼친 알림은 모두 위 목록에 남긴다.
  // 읽음 여부로 순서를 바꾸면 펼친 알림이 읽음이 되는 순간 다른 자리로 옮겨 가 버린다.
  const lastKept = items.reduce((last, i, idx) => (i.read_at == null || opened.has(i.id) ? idx : last), -1);
  const shown = items.slice(0, Math.max(SHOWN, lastKept + 1));
  const rest = items.slice(shown.length);
  const open = (item: NotificationItem) => {
    setOpened((prev) => new Set(prev).add(item.id));
    onRead([item.id]);
  };
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

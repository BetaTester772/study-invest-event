import type { CertStatus, NewsKind, OrderStatus, ParticipantStatus, Side } from '../../api';
import { formatPercent } from '../../lib/format';
import { Badge } from '../ui';

export const CERT_STATUS_LABEL: Record<CertStatus, string> = {
  pending: '검수 대기',
  approved: '승인',
  rejected: '반려',
};

export function CertStatusBadge({ status }: { status: CertStatus }) {
  const tone = status === 'approved' ? 'success' : status === 'rejected' ? 'danger' : 'warning';
  return (
    <Badge tone={tone} dot>
      {CERT_STATUS_LABEL[status]}
    </Badge>
  );
}

export function SideBadge({ side }: { side: Side }) {
  return <Badge tone={side === 'buy' ? 'up' : 'down'}>{side === 'buy' ? '매수' : '매도'}</Badge>;
}

export function OrderStatusBadge({ status }: { status: OrderStatus }) {
  return (
    <Badge tone={status === 'filled' ? 'success' : 'danger'} dot>
      {status === 'filled' ? '체결' : '거부'}
    </Badge>
  );
}

export const PARTICIPANT_STATUS_LABEL: Record<ParticipantStatus, string> = {
  normal: '정상',
  warning: '경고',
  disqualified: '실격',
};

export function ParticipantStatusBadge({ status }: { status: ParticipantStatus }) {
  const tone = status === 'normal' ? 'success' : status === 'warning' ? 'warning' : 'danger';
  return (
    <Badge tone={tone} dot>
      {PARTICIPANT_STATUS_LABEL[status]}
    </Badge>
  );
}

export function KindBadge({ kind }: { kind: 'stock' | 'coin' }) {
  return <Badge tone={kind === 'coin' ? 'info' : 'neutral'}>{kind === 'coin' ? '코인' : '주식'}</Badge>;
}

export const NEWS_KIND_LABEL: Record<NewsKind, string> = { good: '호재', bad: '악재' };

/** "호재 +15%" / "악재 -15%". The sign follows the kind; `rate` is the magnitude. */
export function NewsBadge({ kind, rate, size }: { kind: NewsKind; rate: number; size?: 'sm' | 'md' }) {
  const signed = kind === 'good' ? rate : -rate;
  return (
    <Badge tone={kind === 'good' ? 'up' : 'down'} size={size}>
      {NEWS_KIND_LABEL[kind]} {formatPercent(signed, { digits: 0, sign: true })}
    </Badge>
  );
}

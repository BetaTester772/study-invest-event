import type { CertStatus, OrderStatus, ParticipantStatus, Side } from '../../api';
import { Badge } from '../ui';

export const CERT_STATUS_LABEL: Record<CertStatus, string> = { pending: '검수 대기', approved: '승인', rejected: '반려' };

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

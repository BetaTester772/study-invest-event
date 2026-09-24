import { useState } from 'react';
import { adminApi, ApiError, useApi, type AdminParticipant, type ParticipantStatus } from '../../api';
import { PARTICIPANT_STATUS_LABEL, ParticipantStatusBadge } from '../../components/app/badges';
import { LoadError } from '../../components/app/LoadError';
import { Button, Card, Modal, Money, Select, Stack, Table, Text, useToast, type Column } from '../../components/ui';
import { formatDateTime } from '../../lib/format';

const STATUS_OPTIONS = (Object.keys(PARTICIPANT_STATUS_LABEL) as ParticipantStatus[]).map((s) => ({
  value: s,
  label: PARTICIPANT_STATUS_LABEL[s],
}));

export function ParticipantsTab() {
  const toast = useToast();
  const participants = useApi(() => adminApi.participants(), []);
  const [confirm, setConfirm] = useState<{ p: AdminParticipant; status: ParticipantStatus } | null>(null);
  const [saving, setSaving] = useState<number | null>(null);

  const apply = async (p: AdminParticipant, status: ParticipantStatus) => {
    setSaving(p.id);
    try {
      const updated = await adminApi.setParticipantStatus(p.id, status);
      participants.setData((prev) => (prev ?? []).map((x) => (x.id === updated.id ? updated : x)));
      toast.success('참가자 상태를 바꿨어요', `${p.nickname}님은 이제 ${PARTICIPANT_STATUS_LABEL[status]} 상태예요.`);
    } catch (err) {
      toast.error('상태를 바꾸지 못했어요', err instanceof ApiError ? err.message : undefined);
    } finally {
      setSaving(null);
      setConfirm(null);
    }
  };

  const columns: Column<AdminParticipant>[] = [
    { key: 'id', header: 'ID', numeric: true, width: '4rem' },
    { key: 'nickname', header: '닉네임', render: (p) => p.nickname },
    { key: 'identity', header: '아이디', hideOnMobile: true, render: (p) => p.identity },
    { key: 'status', header: '상태', render: (p) => <ParticipantStatusBadge status={p.status} /> },
    { key: 'cash', header: '현금', numeric: true, hideOnMobile: true, render: (p) => <Money value={p.cash} /> },
    { key: 'total', header: '총자산', numeric: true, render: (p) => <Money value={p.total_assets} /> },
    {
      key: 'certs',
      header: '인증 승인/반려',
      numeric: true,
      render: (p) => `${p.approved_certifications} / ${p.rejected_certifications}`,
    },
    { key: 'joined', header: '가입', hideOnMobile: true, render: (p) => formatDateTime(p.joined_at) },
    {
      key: 'change',
      header: '상태 바꾸기',
      width: '9rem',
      render: (p) => (
        <Select
          label={`${p.nickname} 상태`}
          hideLabel
          value={p.status}
          options={STATUS_OPTIONS}
          disabled={saving === p.id}
          onChange={(status) => {
            if (status === p.status) return;
            if (status === 'disqualified') setConfirm({ p, status });
            else void apply(p, status);
          }}
        />
      ),
    },
  ];

  return (
    <Stack gap={4}>
      <Text size="sm" tone="muted">
        실격 처리한 참가자는 주문할 수 없고 랭킹에서 빠져요. 경고는 표시만 바뀌어요.
      </Text>
      <Card padding={participants.error ? 'md' : 'none'}>
        {participants.error ? (
          <LoadError error={participants.error} onRetry={participants.refetch} what="참가자 목록" />
        ) : (
          <Table
            caption="참가자 목록"
            columns={columns}
            rows={participants.data ?? []}
            rowKey={(p) => p.id}
            loading={participants.loading}
            empty="아직 참가자가 없어요."
          />
        )}
      </Card>
      <Modal
        open={confirm != null}
        onClose={() => setConfirm(null)}
        size="sm"
        title="실격 처리할까요?"
        description={confirm ? `${confirm.p.nickname}님은 더 이상 주문할 수 없고 랭킹에서 빠져요.` : undefined}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(null)}>
              취소
            </Button>
            <Button
              variant="danger"
              loading={confirm != null && saving === confirm.p.id}
              onClick={() => confirm && apply(confirm.p, confirm.status)}
            >
              실격 처리하기
            </Button>
          </>
        }
      />
    </Stack>
  );
}

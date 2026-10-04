import { useState } from 'react';
import { adminApi, ApiError, useApi, type AdminParticipant, type ParticipantStatus } from '../../api';
import { PARTICIPANT_STATUS_LABEL, ParticipantStatusBadge } from '../../components/app/badges';
import { LoadError } from '../../components/app/LoadError';
import {
  Badge,
  Button,
  Checkbox,
  Card,
  Modal,
  Money,
  Percent,
  Select,
  Stack,
  Table,
  Text,
  useToast,
  type Column,
} from '../../components/ui';
import { formatDateTime } from '../../lib/format';

const STATUS_OPTIONS = (Object.keys(PARTICIPANT_STATUS_LABEL) as ParticipantStatus[]).map((s) => ({
  value: s,
  label: PARTICIPANT_STATUS_LABEL[s],
}));

const VERIFY_LABEL = { email: '메일 인증', admin: '관리자 인증' } as const;

/** '인증된 참가자만 거래' 스위치. 평소에는 끄고, 부정 행위가 보이면 켠다. */
function TradingAccessCard({ unverified }: { unverified: number | null }) {
  const toast = useToast();
  const access = useApi(() => adminApi.tradingAccess(), []);
  const [confirmOn, setConfirmOn] = useState(false);
  const [saving, setSaving] = useState(false);
  const on = access.data?.verified_only ?? false;

  const save = async (verifiedOnly: boolean) => {
    setSaving(true);
    try {
      access.setData(await adminApi.setTradingAccess({ verified_only: verifiedOnly }));
      toast.success(
        verifiedOnly ? '인증된 참가자만 거래할 수 있어요' : '모든 참가자가 다시 거래할 수 있어요',
        verifiedOnly ? '미인증 참가자의 주문은 거부돼요. 화면에 인증 안내가 떠요.' : undefined,
      );
    } catch (err) {
      toast.error('바꾸지 못했어요', err instanceof ApiError ? err.message : undefined);
    } finally {
      setSaving(false);
      setConfirmOn(false);
    }
  };

  if (access.error) return <LoadError error={access.error} onRetry={access.refetch} what="거래 제한 설정" />;
  return (
    <Card>
      <Stack direction="row" justify="between" align="center" gap={3} wrap>
        <Stack gap={1}>
          <Text weight="semibold">
            인증된 참가자만 거래{' '}
            <Badge tone={on ? 'warning' : 'neutral'}>{access.loading ? '확인 중' : on ? '켜짐' : '꺼짐'}</Badge>
          </Text>
          <Text size="sm" tone="muted">
            평소에는 꺼 두세요. 켜면 미인증 참가자는 주문할 수 없어요(시세·자산 보기와 공부 인증은 그대로). 참가자는
            등록한 학교 메일로 코드를 받아 스스로 인증하거나, 아래 목록에서 관리자가 인증 처리할 수 있어요.
            {unverified != null && ` 지금 미인증 참가자 ${unverified}명.`}
          </Text>
        </Stack>
        <Button
          variant={on ? 'secondary' : 'danger'}
          loading={saving}
          disabled={access.loading}
          onClick={() => (on ? void save(false) : setConfirmOn(true))}
        >
          {on ? '제한 풀기' : '제한 켜기'}
        </Button>
      </Stack>
      <Modal
        open={confirmOn}
        onClose={() => setConfirmOn(false)}
        size="sm"
        title="인증된 참가자만 거래하게 할까요?"
        description={`미인증 참가자${unverified != null ? ` ${unverified}명` : ''}의 주문이 바로 거부돼요. 언제든 다시 풀 수 있어요.`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmOn(false)}>
              취소
            </Button>
            <Button variant="danger" loading={saving} onClick={() => void save(true)}>
              제한 켜기
            </Button>
          </>
        }
      />
    </Card>
  );
}

export function ParticipantsTab() {
  const toast = useToast();
  const participants = useApi(() => adminApi.participants(), []);
  const [confirm, setConfirm] = useState<{ p: AdminParticipant; status: ParticipantStatus } | null>(null);
  const [saving, setSaving] = useState<number | null>(null);
  const [verifying, setVerifying] = useState<number | null>(null);
  const [unverifiedOnly, setUnverifiedOnly] = useState(false);
  const all = participants.data ?? [];
  const unverifiedCount = participants.data ? all.filter((p) => !p.verified).length : null;
  const rows = unverifiedOnly ? all.filter((p) => !p.verified) : all;

  const setVerified = async (p: AdminParticipant, verified: boolean) => {
    setVerifying(p.id);
    try {
      const updated = await adminApi.setParticipantVerified(p.id, verified);
      participants.setData((prev) => (prev ?? []).map((x) => (x.id === updated.id ? updated : x)));
      toast.success(verified ? `${p.nickname}님을 인증 처리했어요` : `${p.nickname}님의 인증을 취소했어요`);
    } catch (err) {
      toast.error('인증 상태를 바꾸지 못했어요', err instanceof ApiError ? err.message : undefined);
    } finally {
      setVerifying(null);
    }
  };

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
    { key: 'name', header: '이름', hideOnMobile: true, render: (p) => p.name ?? '-' },
    { key: 'student_id', header: '학번', hideOnMobile: true, render: (p) => p.student_id ?? '-' },
    { key: 'department', header: '학과', hideOnMobile: true, render: (p) => p.department ?? '-' },
    {
      key: 'email',
      header: '학교 메일',
      hideOnMobile: true,
      render: (p) => p.email ?? (p.identity ? `(예전 아이디 ${p.identity})` : '-'),
    },
    {
      key: 'verified',
      header: '인증',
      nowrap: true,
      render: (p) => (
        <Stack direction="row" gap={2} align="center">
          {p.verified_via ? (
            <Badge tone="success">{VERIFY_LABEL[p.verified_via]}</Badge>
          ) : (
            <Badge tone="warning">미인증</Badge>
          )}
          <Button
            size="sm"
            variant="ghost"
            loading={verifying === p.id}
            onClick={() => void setVerified(p, !p.verified)}
          >
            {p.verified ? '취소' : '인증 처리'}
          </Button>
        </Stack>
      ),
    },
    { key: 'status', header: '상태', nowrap: true, render: (p) => <ParticipantStatusBadge status={p.status} /> },
    { key: 'cash', header: '현금', numeric: true, hideOnMobile: true, render: (p) => <Money value={p.cash} /> },
    { key: 'total', header: '총자산', numeric: true, render: (p) => <Money value={p.total_assets} /> },
    {
      key: 'principal',
      header: '투입 원금',
      numeric: true,
      hideOnMobile: true,
      render: (p) => <Money value={p.principal} />,
    },
    { key: 'rate', header: '수익률', numeric: true, render: (p) => <Percent value={p.return_rate} sign colorize /> },
    {
      key: 'certs',
      header: '인증 승인/반려',
      numeric: true,
      render: (p) => `${p.approved_certifications} / ${p.rejected_certifications}`,
    },
    { key: 'joined', header: '가입', nowrap: true, hideOnMobile: true, render: (p) => formatDateTime(p.joined_at) },
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
      <TradingAccessCard unverified={unverifiedCount} />
      <Checkbox
        label="미인증 참가자만 보기"
        hint="학번·이름·학과를 확인한 뒤 '인증 처리'를 누르면 인증된 참가자가 돼요."
        checked={unverifiedOnly}
        onChange={setUnverifiedOnly}
      />
      <Text size="sm" tone="muted">
        실격 처리한 참가자는 주문할 수 없고 랭킹에서 빠져요. 경고는 표시만 바뀌어요. 수익률은 투입 원금(시드 + 받은 인증
        보상) 대비 손익이에요.
      </Text>
      <Card padding={participants.error ? 'md' : 'none'}>
        {participants.error ? (
          <LoadError error={participants.error} onRetry={participants.refetch} what="참가자 목록" />
        ) : (
          <Table
            caption="참가자 목록"
            columns={columns}
            rows={rows}
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

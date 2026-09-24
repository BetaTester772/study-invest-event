import { useState } from 'react';
import {
  adminApi,
  ApiError,
  fetchImage,
  useApi,
  useObjectUrl,
  type AdminCertification,
  type CertStatus,
} from '../../api';
import { CertStatusBadge } from '../../components/app/badges';
import { LoadError } from '../../components/app/LoadError';
import {
  Alert,
  Badge,
  Button,
  Card,
  KeyValueList,
  Modal,
  SegmentedControl,
  Spinner,
  Stack,
  Table,
  TextArea,
  useToast,
  type Column,
} from '../../components/ui';
import { formatDateTime, formatDay } from '../../lib/format';

type Filter = CertStatus | 'all';

function ReviewModal({
  cert,
  onClose,
  onDone,
}: {
  cert: AdminCertification | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const toast = useToast();
  const [reason, setReason] = useState('');
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null);
  const image = useObjectUrl(cert?.image_url ? () => fetchImage(cert.image_url!, 'admin') : null, [cert?.id]);

  const close = () => {
    setReason('');
    setReasonError(null);
    onClose();
  };

  const review = async (approve: boolean) => {
    if (!cert) return;
    if (!approve && !reason.trim()) {
      setReasonError('반려 사유를 적어 주세요. 참가자에게 그대로 보여요.');
      return;
    }
    setBusy(approve ? 'approve' : 'reject');
    try {
      await adminApi.review(cert.id, approve ? { approve } : { approve, reason: reason.trim() });
      toast.success(
        approve ? '인증을 승인했어요' : '인증을 반려했어요',
        `${cert.nickname}, ${formatDay(cert.target_date)}`,
      );
      onDone();
      close();
    } catch (err) {
      toast.error('검수하지 못했어요', err instanceof ApiError ? err.message : undefined);
      if (err instanceof ApiError && err.code === 'ALREADY_REVIEWED') {
        onDone();
        close();
      }
    } finally {
      setBusy(null);
    }
  };

  const pending = cert?.status === 'pending';

  return (
    <Modal
      open={cert != null}
      onClose={close}
      size="lg"
      title={cert ? `${cert.nickname}의 ${formatDay(cert.target_date)} 인증` : ''}
      description={cert ? `인증 #${cert.id}, ${formatDateTime(cert.submitted_at)}에 올림` : undefined}
      footer={
        pending ? (
          <>
            <Button variant="danger" onClick={() => review(false)} loading={busy === 'reject'} disabled={busy != null}>
              반려하기
            </Button>
            <Button onClick={() => review(true)} loading={busy === 'approve'} disabled={busy != null}>
              승인하기
            </Button>
          </>
        ) : (
          <Button variant="secondary" onClick={close}>
            닫기
          </Button>
        )
      }
    >
      {cert && (
        <Stack gap={4}>
          {cert.duplicate_of != null && (
            <Alert tone="warning" title="같은 사진으로 보여요">
              인증 #{cert.duplicate_of}와 이미지 해시가 같아요. 재사용한 사진인지 확인해 주세요.
            </Alert>
          )}
          {image.loading && <Spinner label="사진을 불러오는 중" />}
          {image.error && (
            <Alert tone="danger" title="사진을 불러오지 못했어요">
              {image.error.message}
            </Alert>
          )}
          {!cert.image_url && <Alert title="사진이 삭제됐어요" />}
          {image.url && <img src={image.url} alt={`${cert.nickname}의 공부 인증 사진`} />}
          <KeyValueList
            items={[
              { label: '상태', value: <CertStatusBadge status={cert.status} /> },
              { label: '참가자 ID', value: cert.participant_id },
              { label: '이미지 해시', value: cert.image_hash.slice(0, 16) },
              ...(cert.reject_reason ? [{ label: '반려 사유', value: cert.reject_reason }] : []),
              ...(cert.reviewed_at ? [{ label: '검수 시각', value: formatDateTime(cert.reviewed_at) }] : []),
            ]}
          />
          {pending && (
            <TextArea
              label="반려 사유"
              hint="반려할 때만 필요해요. 승인할 때는 비워 두세요."
              value={reason}
              onChange={(e) => {
                setReason(e.target.value);
                setReasonError(null);
              }}
              error={reasonError ?? undefined}
            />
          )}
        </Stack>
      )}
    </Modal>
  );
}

export function CertReviewTab() {
  const [filter, setFilter] = useState<Filter>('pending');
  const certs = useApi(() => adminApi.certifications(filter === 'all' ? undefined : filter), [filter]);
  const [selected, setSelected] = useState<AdminCertification | null>(null);

  const columns: Column<AdminCertification>[] = [
    { key: 'id', header: 'ID', numeric: true, width: '4rem', render: (c) => `#${c.id}` },
    { key: 'nickname', header: '닉네임', render: (c) => c.nickname },
    { key: 'target', header: '인증 날짜', nowrap: true, render: (c) => formatDay(c.target_date) },
    {
      key: 'submitted',
      header: '올린 시각',
      nowrap: true,
      hideOnMobile: true,
      render: (c) => formatDateTime(c.submitted_at),
    },
    { key: 'status', header: '상태', nowrap: true, render: (c) => <CertStatusBadge status={c.status} /> },
    {
      key: 'dup',
      header: '중복 검사',
      render: (c) =>
        c.duplicate_of != null ? (
          <Badge tone="warning" dot>
            #{c.duplicate_of}와 같은 사진
          </Badge>
        ) : (
          <Badge>이상 없음</Badge>
        ),
    },
    {
      key: 'action',
      header: <span className="sr-only">동작</span>,
      align: 'right',
      render: (c) => (
        <Button size="sm" variant={c.status === 'pending' ? 'primary' : 'secondary'} onClick={() => setSelected(c)}>
          {c.status === 'pending' ? '검수하기' : '보기'}
        </Button>
      ),
    },
  ];

  return (
    <Stack gap={4}>
      <Stack direction="row" justify="between" align="center" wrap gap={3}>
        <SegmentedControl
          label="상태로 거르기"
          value={filter}
          onChange={setFilter}
          options={[
            { value: 'pending', label: '검수 대기' },
            { value: 'approved', label: '승인' },
            { value: 'rejected', label: '반려' },
            { value: 'all', label: '전체' },
          ]}
        />
        <Button variant="ghost" onClick={() => certs.refetch()} loading={certs.fetching && !certs.loading}>
          새로 고침
        </Button>
      </Stack>
      <Card padding={certs.error ? 'md' : 'none'}>
        {certs.error ? (
          <LoadError error={certs.error} onRetry={certs.refetch} what="인증 목록" />
        ) : (
          <Table
            caption="인증 목록"
            columns={columns}
            rows={certs.data ?? []}
            rowKey={(c) => c.id}
            loading={certs.loading}
            empty={
              filter === 'pending'
                ? '검수할 인증이 없어요. 새 인증이 올라오면 여기에 보여요.'
                : '해당하는 인증이 없어요.'
            }
          />
        )}
      </Card>
      <ReviewModal cert={selected} onClose={() => setSelected(null)} onDone={() => void certs.refetch()} />
    </Stack>
  );
}

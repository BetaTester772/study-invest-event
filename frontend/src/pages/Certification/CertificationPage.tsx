import { useState } from 'react';
import { ApiError, fetchImage, meApi, publicApi, useApi, useObjectUrl, type Certification } from '../../api';
import { CertStatusBadge } from '../../components/app/badges';
import { LoadError } from '../../components/app/LoadError';
import {
  Alert,
  Button,
  Card,
  Container,
  DayStrip,
  FileDropzone,
  Grid,
  Highlight,
  KeyValueList,
  Modal,
  PageHeader,
  Skeleton,
  Spinner,
  Stack,
  Table,
  Text,
  useToast,
  type Column,
} from '../../components/ui';
import { formatDateTime, formatDay, formatWon } from '../../lib/format';
import { dayStripWindow } from '../../lib/market';

const ACCEPT = 'image/jpeg,image/png,image/webp,image/heic';
const MAX_SIZE = 10 * 1024 * 1024;

function CertImageModal({ cert, onClose }: { cert: Certification | null; onClose: () => void }) {
  const image = useObjectUrl(cert?.image_url ? () => fetchImage(cert.image_url!, 'participant') : null, [cert?.id]);
  return (
    <Modal
      open={cert != null}
      onClose={onClose}
      title={cert ? `${formatDay(cert.target_date)} 인증 사진` : ''}
      size="lg"
      footer={
        <Button variant="secondary" onClick={onClose}>
          닫기
        </Button>
      }
    >
      {image.loading && <Spinner label="사진을 불러오는 중" />}
      {image.error && (
        <Alert tone="danger" title="사진을 불러오지 못했습니다">
          {image.error.message}
        </Alert>
      )}
      {image.url && <img src={image.url} alt={`${cert ? formatDay(cert.target_date) : ''} 공부 인증 사진`} />}
    </Modal>
  );
}

function rewardText(c: Certification, rewardCash: number | undefined, lastDay: string | undefined): string {
  if (c.rewarded_at) {
    // reward_cash가 없으면 현금 보상 전(v0.3, 병더리움 지급) 기록이다.
    const what = c.reward_cash != null ? `${formatWon(c.reward_cash)} 받음` : '보상 받음';
    return `${what} (${formatDateTime(c.rewarded_at)})`;
  }
  // 보상은 다음 운영일 09:00에 주므로 마지막 운영일 인증분은 지급일이 없다(인증 일수에는 들어간다).
  if (c.status !== 'rejected' && c.target_date === lastDay) return '마지막 날 인증은 보상이 없습니다';
  if (c.status === 'approved')
    return rewardCash != null
      ? `다음 운영일 09:00에 ${formatWon(rewardCash)} 지급 예정`
      : '다음 운영일 09:00 지급 예정';
  if (c.status === 'pending') return '승인되면 지급';
  return '—';
}

export function CertificationPage() {
  const toast = useToast();
  const event = useApi(() => publicApi.event(), [], { refreshInterval: 60_000 });
  const certs = useApi(() => meApi.certifications(), []);
  const status = useApi(() => meApi.certificationStatus(), [], { refreshInterval: 60_000 });
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [viewing, setViewing] = useState<Certification | null>(null);

  const e = event.data;
  const st = status.data;
  const target = st?.target_date;
  const rewardCash = e?.certification.reward_cash;
  const approvedDays = (certs.data ?? []).filter((c) => c.status === 'approved').map((c) => c.target_date);

  const upload = async () => {
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    try {
      const created = await meApi.uploadCertification(file);
      toast.success('인증 사진을 올렸습니다', `${formatDay(created.target_date)} 인증으로 검수를 기다립니다.`);
      setFile(null);
      certs.setData((prev) => [created, ...(prev ?? [])]);
      void certs.refetch();
      void status.refetch();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : '잠시 뒤 다시 시도해 주세요.';
      setUploadError(msg);
      toast.error('인증 사진을 올리지 못했습니다', msg);
      void status.refetch();
    } finally {
      setUploading(false);
    }
  };

  const columns: Column<Certification>[] = [
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
      key: 'reason',
      header: '반려 사유',
      render: (c) => c.reject_reason ?? (c.status === 'rejected' ? '사유 없음' : '—'),
    },
    { key: 'reward', header: '보상', hideOnMobile: true, render: (c) => rewardText(c, rewardCash, e?.end ?? undefined) },
    {
      key: 'image',
      header: <span className="sr-only">사진</span>,
      align: 'right',
      render: (c) =>
        c.image_url ? (
          <Button size="sm" variant="ghost" onClick={() => setViewing(c)}>
            사진 보기
          </Button>
        ) : (
          <Text as="span" size="xs" tone="subtle">
            삭제됨
          </Text>
        ),
    },
  ];

  return (
    <Container>
      <PageHeader
        title="공부 인증"
        description={`하루에 한 번, 공부한 모습을 사진 한 장으로 올립니다. 승인되면 다음 운영일에 투자금${rewardCash != null ? ` ${formatWon(rewardCash)}` : ''}을 받습니다. 인증하지 않아도 거래는 할 수 있지만 그날 보상은 없습니다.`}
      />
      <Stack gap={8}>
        {event.error && <LoadError error={event.error} onRetry={event.refetch} what="인증 일정" />}
        <Grid sidebar="minmax(16rem, 22rem)" gap={6}>
          <Card title="오늘 인증하기">
            {status.error ? (
              <LoadError error={status.error} onRetry={status.refetch} what="인증 가능 여부" />
            ) : !e || !st ? (
              <Skeleton lines={4} />
            ) : st.reason === 'OUTSIDE_EVENT' ? (
              <Alert title="지금은 인증 기간이 아닙니다">
                인증은 {formatDay(e.start)}부터 {e.end ? `${formatDay(e.end)}까지` : '기간 제한 없이'} 받습니다.
              </Alert>
            ) : st.reason === 'DISQUALIFIED' ? (
              <Alert tone="danger" title="인증을 올릴 수 없습니다">
                {st.message}
              </Alert>
            ) : st.existing ? (
              <Stack gap={4}>
                <Alert
                  tone={
                    st.existing.status === 'approved' ? 'success' : st.existing.status === 'rejected' ? 'warning' : 'info'
                  }
                  title={`${formatDay(st.existing.target_date)} 인증은 이미 올렸습니다`}
                >
                  {st.existing.status === 'approved'
                    ? `승인됐습니다. ${rewardText(st.existing, rewardCash, e.end ?? undefined)}.`
                    : st.existing.status === 'rejected'
                      ? `반려됐습니다(${st.existing.reject_reason ?? '사유 없음'}). 인증은 하루 한 번이라 이 날짜는 다시 올릴 수 없습니다.`
                      : '검수를 기다리는 중입니다. 결과는 아래 목록에서 확인할 수 있습니다.'}
                </Alert>
                <Text size="sm" tone="muted">
                  오늘 {st.cutoff}이 지나면 다음 날짜 인증을 올릴 수 있습니다.
                </Text>
              </Stack>
            ) : (
              <Stack gap={4}>
                <Text>
                  지금 올리면 <Highlight>{formatDay(target)}</Highlight> 인증으로 들어갑니다.
                </Text>
                <FileDropzone
                  label="인증 사진"
                  value={file}
                  onChange={(f) => {
                    setFile(f);
                    setUploadError(null);
                  }}
                  accept={ACCEPT}
                  maxSize={MAX_SIZE}
                  error={uploadError}
                  disabled={uploading}
                  hint="JPG, PNG, WEBP, HEIC 사진 한 장, 10MB까지 올릴 수 있습니다."
                />
                <Button size="lg" fullWidth onClick={upload} loading={uploading} disabled={!file}>
                  인증 사진 올리기
                </Button>
              </Stack>
            )}
          </Card>
          <Card title="보상과 마감" tone="sunken">
            <Stack gap={4}>
              {e ? (
                <KeyValueList
                  items={[
                    { label: '인증 날짜', value: formatDay(e.certification.target_date) },
                    { label: '접수 마감', value: `매일 ${e.certification.cutoff}` },
                    { label: '보상', value: `현금 ${formatWon(e.certification.reward_cash)}`, strong: true },
                  ]}
                />
              ) : (
                <Skeleton lines={3} />
              )}
              <Stack gap={2}>
                <Text size="sm" tone="muted">
                  승인되면 다음 운영일 09:00에 현금으로 받아서 그날 장중에 바로 주문할 수 있습니다. 받은 보상은 투입
                  원금에 더해져서 수익률에서는 손익으로 치지 않습니다. 마지막 날 인증은 다음 운영일이 없어 보상이 없지만
                  인증 일수에는 들어갑니다.
                </Text>
                <Text size="sm" tone="muted">
                  마감 시각이 지나서 올린 사진은 다음 날짜 인증으로 집계됩니다. 같은 사진을 다시 쓰면 반려될 수 있습니다.
                </Text>
              </Stack>
            </Stack>
          </Card>
        </Grid>

        {e && (
          <Card title="나의 인증 도장판" description="승인된 날에 도장이 찍힙니다.">
            <DayStrip {...dayStripWindow(e)} today={e.today} stamped={approvedDays} label="나의 인증 도장판" />
          </Card>
        )}

        <Card title="올린 인증" padding={certs.error ? 'md' : 'none'}>
          {certs.error ? (
            <LoadError error={certs.error} onRetry={certs.refetch} what="인증 내역" />
          ) : (
            <Table
              caption="올린 인증 목록"
              columns={columns}
              rows={certs.data ?? []}
              rowKey={(c) => c.id}
              loading={certs.loading}
              empty="아직 올린 인증이 없습니다. 오늘 공부한 사진으로 첫 도장을 받아 보세요."
            />
          )}
        </Card>
      </Stack>
      <CertImageModal cert={viewing} onClose={() => setViewing(null)} />
    </Container>
  );
}

import { useEffect, useState, type FormEvent } from 'react';
import { adminApi, adminKeyStore, ApiError, onUnauthorized } from '../../api';
import { Alert, Button, Card, Container, PageHeader, Stack, Tabs, TextField } from '../../components/ui';
import { AuditTab } from './AuditTab';
import { BatchTab } from './BatchTab';
import { CertReviewTab } from './CertReviewTab';
import { ParamsTab } from './ParamsTab';
import { ParticipantsTab } from './ParticipantsTab';
import { PriceTab } from './PriceTab';
import { SimulatorTab } from './SimulatorTab';

type AdminTab = 'certs' | 'participants' | 'params' | 'batch' | 'price' | 'sim' | 'audit';

function KeyGate({ onUnlock, notice }: { onUnlock: () => void; notice?: string | null }) {
  const [key, setKey] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!key.trim()) {
      setError('관리자 키를 입력해 주세요.');
      return;
    }
    setChecking(true);
    setError(null);
    adminKeyStore.set(key.trim());
    try {
      await adminApi.params();
      onUnlock();
    } catch (err) {
      adminKeyStore.set(null);
      setError(
        err instanceof ApiError && err.status === 401
          ? '관리자 키가 맞지 않아요. 다시 확인해 주세요.'
          : err instanceof ApiError
            ? err.message
            : '확인하지 못했어요. 잠시 뒤 다시 시도해 주세요.',
      );
    } finally {
      setChecking(false);
    }
  };

  return (
    <Container size="sm">
      <PageHeader title="관리자" description="관리자 키를 입력하면 이 탭을 닫을 때까지 기억해요." />
      <Card>
        <form onSubmit={submit} noValidate>
          <Stack gap={4}>
            {notice && <Alert tone="warning">{notice}</Alert>}
            <TextField
              label="관리자 키"
              type="password"
              autoComplete="off"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              error={error ?? undefined}
              required
            />
            <Button type="submit" size="lg" fullWidth loading={checking}>
              관리자 화면 열기
            </Button>
          </Stack>
        </form>
      </Card>
    </Container>
  );
}

export function AdminPage() {
  const [unlocked, setUnlocked] = useState(() => Boolean(adminKeyStore.get()));
  const [notice, setNotice] = useState<string | null>(null);
  const [tab, setTab] = useState<AdminTab>('certs');

  useEffect(
    () =>
      onUnauthorized((mode) => {
        if (mode !== 'admin') return;
        adminKeyStore.set(null);
        setNotice('관리자 키가 만료되었거나 바뀌었어요. 다시 입력해 주세요.');
        setUnlocked(false);
      }),
    [],
  );

  if (!unlocked) {
    return (
      <KeyGate
        notice={notice}
        onUnlock={() => {
          setNotice(null);
          setUnlocked(true);
        }}
      />
    );
  }

  return (
    <Container size="xl">
      <PageHeader
        title="관리자"
        description="인증 검수, 참가자 관리, 파라미터와 정산을 다뤄요. 모든 조작은 감사 로그에 남아요."
        actions={
          <Button
            variant="secondary"
            onClick={() => {
              adminKeyStore.set(null);
              setUnlocked(false);
            }}
          >
            관리자 키 지우기
          </Button>
        }
      />
      <Tabs
        label="관리 메뉴"
        value={tab}
        onChange={setTab}
        items={[
          { value: 'certs', label: '인증 검수', content: <CertReviewTab /> },
          { value: 'participants', label: '참가자', content: <ParticipantsTab /> },
          { value: 'params', label: '파라미터', content: <ParamsTab /> },
          { value: 'batch', label: '배치·정산', content: <BatchTab /> },
          { value: 'price', label: '가격 개입', content: <PriceTab /> },
          { value: 'sim', label: '시뮬레이터', content: <SimulatorTab /> },
          { value: 'audit', label: '감사 로그', content: <AuditTab /> },
        ]}
      />
    </Container>
  );
}

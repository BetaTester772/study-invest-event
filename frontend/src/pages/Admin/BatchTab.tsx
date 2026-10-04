import { useState } from 'react';
import { adminApi, ApiError, useApi, type BatchResult, type SettlementLog, type SettlementStock } from '../../api';
import { LoadError } from '../../components/app/LoadError';
import {
  Alert,
  Badge,
  Button,
  Card,
  CodeBlock,
  EmptyState,
  Grid,
  KeyValueList,
  Modal,
  Money,
  PriceChange,
  Skeleton,
  Stack,
  Table,
  Text,
  TextField,
  useToast,
  type Column,
} from '../../components/ui';
import { formatDateTime, formatDay, formatNumber } from '../../lib/format';

type Action = 'open' | 'settle' | 'run-due' | 'advance';

const ACTION_COPY: Record<Action, { title: string; button: string; description: string; done: string }> = {
  open: {
    title: '시작가를 공시할까요?',
    button: '시작가 공시하기',
    description: '대상 운영일의 시작가를 확정하고 전날 승인된 인증 보상을 지급해요. 되돌릴 수 없어요.',
    done: '시작가를 공시했어요',
  },
  settle: {
    title: '정산할까요?',
    button: '정산하기',
    description: '대상 운영일 주문을 집계해 다음 운영일 시작가를 정해요. 되돌릴 수 없어요.',
    done: '정산했어요',
  },
  'run-due': {
    title: '밀린 배치를 실행할까요?',
    button: '밀린 배치 실행하기',
    description: '지금 시각까지 실행됐어야 할 공시·정산을 순서대로 실행해요.',
    done: '밀린 배치를 실행했어요',
  },
  advance: {
    title: '가격을 지금 바로 변동시킬까요?',
    button: '지금 변동시키기',
    description:
      '최신 공시일을 18:00 전이어도 정산하고, 다음 운영일 시작가를 바로 공시해요. 시계를 앞질러 이벤트가 한 회차 진행되고 되돌릴 수 없어요.',
    done: '가격을 변동시켰어요',
  },
};

const STOCK_COLUMNS: Column<SettlementStock>[] = [
  { key: 'code', header: '종목', render: (s) => s.code },
  { key: 'buy', header: '매수금액 B', numeric: true, render: (s) => <Money value={s.buy_amount} /> },
  {
    key: 'adj',
    header: "유동성 반영 B'",
    numeric: true,
    hideOnMobile: true,
    render: (s) => <Money value={s.adjusted_amount} />,
  },
  {
    key: 'r',
    header: '쏠림 r',
    numeric: true,
    render: (s) => (s.concentration == null ? '—' : formatNumber(s.concentration, 3)),
  },
  { key: 'rate', header: '변동률', numeric: true, render: (s) => <PriceChange rate={s.rate} /> },
  { key: 'old', header: '이전가', numeric: true, hideOnMobile: true, render: (s) => <Money value={s.old_price} /> },
  { key: 'new', header: '새 시작가', numeric: true, render: (s) => <Money value={s.new_price} /> },
];

function SettlementCard({ log }: { log: SettlementLog }) {
  return (
    <Card
      title={`${log.round}회차 정산`}
      description={`${formatDay(log.trade_day)} 주문으로 ${formatDay(log.effective_day)} 시작가를 정했어요. ${formatDateTime(log.created_at)} 실행.`}
    >
      <Stack gap={4}>
        <Card padding="none" tone="sunken">
          <Table
            caption={`${log.round}회차 주식 정산`}
            columns={STOCK_COLUMNS}
            rows={log.stocks}
            rowKey={(s) => s.code}
            dense
          />
        </Card>
        <Grid min="14rem" gap={4}>
          <KeyValueList
            items={[
              {
                label: '병더리움 방향',
                value: (
                  <Stack direction="row" gap={2} justify="end" wrap>
                    <Badge tone={log.coin.direction}>{log.coin.direction === 'up' ? '상승일' : '하락일'}</Badge>
                    {log.coin.calm && <Badge tone="info">초반 안정기</Badge>}
                  </Stack>
                ),
              },
              { label: '확률 추첨 p', value: formatNumber(log.coin.p, 4) },
              { label: '크기 추첨 X', value: formatNumber(log.coin.x, 4) },
            ]}
          />
          <KeyValueList
            items={[
              { label: '변동률', value: <PriceChange rate={log.coin.rate} /> },
              { label: '이전가', value: <Money value={log.coin.old_price} /> },
              { label: '새 시작가', value: <Money value={log.coin.new_price} />, strong: true },
            ]}
          />
        </Grid>
      </Stack>
    </Card>
  );
}

export function BatchTab() {
  const toast = useToast();
  const settlements = useApi(() => adminApi.settlements(), []);
  const qa = useApi(() => adminApi.qaStatus(), []);
  const [day, setDay] = useState('');
  const [confirm, setConfirm] = useState<Action | null>(null);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<BatchResult[] | null>(null);

  const run = async (action: Action) => {
    setRunning(true);
    try {
      const res =
        action === 'open'
          ? [await adminApi.batchOpen(day || undefined)]
          : action === 'settle'
            ? [await adminApi.batchSettle(day || undefined)]
            : action === 'advance'
              ? [await adminApi.qaAdvancePrice()]
              : await adminApi.batchRunDue();
      setResults(res);
      toast.success(ACTION_COPY[action].done, res.length === 0 ? '실행할 배치가 없었어요.' : `${res.length}건 실행`);
      void settlements.refetch();
    } catch (err) {
      toast.error('배치를 실행하지 못했어요', err instanceof ApiError ? err.message : undefined);
    } finally {
      setRunning(false);
      setConfirm(null);
    }
  };

  const logs = [...(settlements.data ?? [])].sort((a, b) => b.round - a.round);

  return (
    <Stack gap={6}>
      <Card
        title="배치 실행"
        description="평소에는 09:00 공시와 18:00 정산이 자동으로 돌아요. 실패했거나 밀렸을 때만 직접 실행하세요."
      >
        <Stack gap={4}>
          <TextField
            label="대상 운영일"
            type="date"
            hint="비우면 오늘로 실행해요."
            value={day}
            onChange={(e) => setDay(e.target.value)}
          />
          <Stack direction="row" gap={2} wrap>
            <Button variant="secondary" onClick={() => setConfirm('open')}>
              시작가 공시하기
            </Button>
            <Button variant="secondary" onClick={() => setConfirm('settle')}>
              정산하기
            </Button>
            <Button variant="secondary" onClick={() => setConfirm('run-due')}>
              밀린 배치 실행하기
            </Button>
          </Stack>
          {results && (
            <Stack gap={2}>
              <Text size="sm" weight="semibold">
                마지막 실행 결과
              </Text>
              {results.length === 0 ? (
                <Text size="sm" tone="muted">
                  실행할 배치가 없었어요.
                </Text>
              ) : (
                <CodeBlock value={results} />
              )}
            </Stack>
          )}
        </Stack>
      </Card>

      {qa.data?.enabled && (
        <Card
          title="QA 도구"
          description="09:00·18:00을 기다리지 않고 가격이 한 회차 움직이는 걸 바로 확인해요. QA 서버에서만 보여요."
          tone="sunken"
        >
          <Stack gap={4}>
            <Alert tone="warning">
              최신 공시일을 정산하고 다음 운영일 시작가를 바로 공시해요. 누를 때마다 이벤트가 하루씩 앞서가요. 아직 공시된 날이 없으면 이벤트 첫날 시작가부터 공시해요. 무제한 모드(STUDY_INVEST_QA_UNLIMITED)면 이벤트 종료일 뒤로도 계속 진행돼요.
            </Alert>
            <Stack direction="row" gap={2} wrap>
              <Button onClick={() => setConfirm('advance')}>지금 가격 변동시키기</Button>
            </Stack>
          </Stack>
        </Card>
      )}

      <Stack gap={4}>
        <Text as="p" display size="xl" tone="ink">
          정산 기록
        </Text>
        {settlements.error ? (
          <LoadError error={settlements.error} onRetry={settlements.refetch} what="정산 기록" />
        ) : settlements.loading ? (
          <Skeleton lines={4} height="2rem" />
        ) : logs.length === 0 ? (
          <EmptyState
            compact
            title="아직 정산 기록이 없어요"
            description="첫 운영일 18:00 정산이 끝나면 여기에 쌓여요."
          />
        ) : (
          logs.map((log) => <SettlementCard key={log.id} log={log} />)
        )}
      </Stack>

      <Modal
        open={confirm != null}
        onClose={() => setConfirm(null)}
        size="sm"
        title={confirm ? ACTION_COPY[confirm].title : ''}
        description={
          confirm
            ? `${confirm === 'open' || confirm === 'settle' ? `${day ? formatDay(day) : '오늘'} 기준. ` : ''}${ACTION_COPY[confirm].description}`
            : undefined
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(null)}>
              취소
            </Button>
            <Button loading={running} onClick={() => confirm && run(confirm)}>
              {confirm ? ACTION_COPY[confirm].button : ''}
            </Button>
          </>
        }
      />
    </Stack>
  );
}

import { Link, useParams } from 'react-router-dom';
import { meApi, publicApi, useApi, type PricePoint } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { KindBadge } from '../../components/app/badges';
import { LoadError } from '../../components/app/LoadError';
import {
  Badge,
  Card,
  Container,
  EmptyState,
  Grid,
  LineChart,
  LinkButton,
  Money,
  PageHeader,
  PriceChange,
  Skeleton,
  Stack,
  Table,
  Text,
  type Column,
} from '../../components/ui';
import { formatDay, formatDayShort } from '../../lib/format';
import { OrderPanel } from './OrderPanel';

const SOURCE_LABEL: Record<PricePoint['source'], string> = {
  initial: '1일차 시작가',
  settlement: '정산',
  carry_over: '전일 유지',
  manual: '관리자 조정',
};

const HISTORY_COLUMNS: Column<PricePoint>[] = [
  { key: 'day', header: '운영일', nowrap: true, render: (p) => formatDay(p.day) },
  { key: 'price', header: '시작가', numeric: true, render: (p) => <Money value={p.price} /> },
  { key: 'change', header: '전일 대비', numeric: true, render: (p) => <PriceChange rate={p.change_rate} /> },
  {
    key: 'source',
    header: '근거',
    hideOnMobile: true,
    render: (p) => <Badge tone={p.source === 'manual' ? 'warning' : 'neutral'}>{SOURCE_LABEL[p.source]}</Badge>,
  },
];

export function InstrumentPage() {
  const { code = '' } = useParams();
  const { status } = useAuth();
  const instruments = useApi(() => publicApi.instruments(), []);
  const history = useApi(() => publicApi.history(code), [code]);
  const event = useApi(() => publicApi.event(), [], { refreshInterval: 60_000 });
  const portfolio = useApi(() => meApi.portfolio(), [status], { enabled: status === 'authenticated' });

  const instrument = instruments.data?.find((i) => i.code === code);
  const back = <Link to="/">시세판으로 돌아가기</Link>;

  if (instruments.error) {
    return (
      <Container>
        <PageHeader title="종목" back={back} />
        <LoadError error={instruments.error} onRetry={instruments.refetch} what="종목 정보" />
      </Container>
    );
  }

  if (instruments.data && !instrument) {
    return (
      <Container>
        <PageHeader title="종목을 찾을 수 없어요" back={back} />
        <EmptyState
          title={`'${code}' 종목은 없어요`}
          description="주소가 바뀌었을 수 있어요. 시세판에서 종목을 다시 골라 주세요."
          action={<LinkButton to="/">시세판 보기</LinkButton>}
        />
      </Container>
    );
  }

  const points = (history.data ?? []).map((p) => ({ x: p.day, y: p.price }));
  const rows = [...(history.data ?? [])].reverse();

  return (
    <Container>
      <PageHeader
        back={back}
        title={instrument ? instrument.name : <Skeleton width="10rem" height="2.25rem" />}
        description={
          instrument && (
            <Stack gap={3}>
              <Stack direction="row" gap={2} align="center" wrap>
                <Text as="span" tone="muted">
                  {instrument.alias}
                </Text>
                <KindBadge kind={instrument.kind} />
              </Stack>
              <Stack direction="row" gap={3} align="center" wrap>
                <Money value={instrument.price} display="xl" />
                <PriceChange rate={instrument.change_rate} pill />
                <Text as="span" size="sm" tone="muted">
                  {instrument.day ? `${formatDay(instrument.day)} 시작가` : '1일차 시작가'}
                </Text>
              </Stack>
            </Stack>
          )
        }
      />
      <Grid sidebar="minmax(18rem, 24rem)" gap={6} sideFirstOnMobile>
        <Stack gap={6}>
          <Card title="가격 이력" description="매일 18:00 정산으로 다음 운영일 시작가가 정해져요.">
            {history.error ? (
              <LoadError error={history.error} onRetry={history.refetch} what="가격 이력" />
            ) : history.loading ? (
              <Skeleton height="240px" />
            ) : (
              <LineChart points={points} label={`${instrument?.name ?? code} 시작가 이력`} formatX={formatDayShort} />
            )}
          </Card>
          <Card title="날짜별 시작가" padding="none">
            <Table
              caption={`${instrument?.name ?? code} 날짜별 시작가`}
              columns={HISTORY_COLUMNS}
              rows={rows}
              rowKey={(p) => p.day}
              loading={history.loading}
              empty="아직 공시된 가격이 없어요. 첫 운영일 09:00에 공시돼요."
            />
          </Card>
        </Stack>
        {instrument ? (
          <OrderPanel
            instrument={instrument}
            event={event.data}
            portfolio={portfolio.data}
            portfolioLoading={portfolio.loading}
            portfolioError={portfolio.error}
            onRetryPortfolio={portfolio.refetch}
            onFilled={() => {
              void portfolio.refetch();
              void event.refetch();
            }}
          />
        ) : (
          <Card title="주문">
            <Skeleton lines={4} />
          </Card>
        )}
      </Grid>
    </Container>
  );
}

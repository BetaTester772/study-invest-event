import { Link } from 'react-router-dom';
import { meApi, publicApi, useApi, type HoldingView, type Order } from '../../api';
import { OrderStatusBadge, SideBadge } from '../../components/app/badges';
import { LoadError } from '../../components/app/LoadError';
import {
  Badge,
  Card,
  Container,
  EmptyState,
  LinkButton,
  Money,
  PageHeader,
  Percent,
  PriceChange,
  Skeleton,
  Stack,
  Stat,
  StatGroup,
  Table,
  Text,
  type Column,
} from '../../components/ui';
import { formatDateTime, formatDay, formatQuantity } from '../../lib/format';

const HOLDING_COLUMNS: Column<HoldingView>[] = [
  {
    key: 'name',
    header: '종목',
    render: (h) => <Link to={`/instruments/${h.code}`}>{h.name}</Link>,
  },
  { key: 'quantity', header: '수량', numeric: true, render: (h) => formatQuantity(h.quantity, h.kind) },
  {
    key: 'avg',
    header: '평균단가',
    numeric: true,
    hideOnMobile: true,
    render: (h) => (h.cost === 0 ? '—' : <Money value={h.avg_price} />),
  },
  { key: 'price', header: '현재가', numeric: true, hideOnMobile: true, render: (h) => <Money value={h.price} /> },
  { key: 'value', header: '평가금액', numeric: true, render: (h) => <Money value={h.value} /> },
  { key: 'profit', header: '평가손익', numeric: true, render: (h) => <Money value={h.profit} sign colorize /> },
  {
    key: 'rate',
    header: '수익률',
    numeric: true,
    render: (h) =>
      h.profit_rate == null ? (
        <Badge tone="info">보상으로 받음</Badge>
      ) : (
        <Percent value={h.profit_rate} sign colorize />
      ),
  },
];

export function PortfolioPage() {
  const portfolio = useApi(() => meApi.portfolio(), []);
  const orders = useApi(() => meApi.orders(100), []);
  const instruments = useApi(() => publicApi.instruments(), []);
  const names = new Map((instruments.data ?? []).map((i) => [i.code, i]));

  const orderColumns: Column<Order>[] = [
    { key: 'at', header: '주문 시각', nowrap: true, render: (o) => formatDateTime(o.created_at) },
    {
      key: 'code',
      header: '종목',
      render: (o) => <Link to={`/instruments/${o.code}`}>{names.get(o.code)?.name ?? o.code}</Link>,
    },
    { key: 'side', header: '구분', nowrap: true, render: (o) => <SideBadge side={o.side} /> },
    {
      key: 'qty',
      header: '수량',
      numeric: true,
      render: (o) => formatQuantity(o.quantity, names.get(o.code)?.kind ?? 'stock'),
    },
    {
      key: 'price',
      header: '체결가',
      numeric: true,
      hideOnMobile: true,
      render: (o) => (o.status === 'filled' && o.price != null ? <Money value={o.price} /> : '—'),
    },
    {
      key: 'amount',
      header: '금액',
      numeric: true,
      render: (o) => (o.status === 'filled' && o.amount != null ? <Money value={o.amount} /> : '—'),
    },
    {
      key: 'status',
      header: '결과',
      nowrap: true,
      render: (o) => (
        <Stack gap={1} align="start">
          <OrderStatusBadge status={o.status} />
          {o.reject_message && (
            <Text as="span" size="xs" tone="muted">
              {o.reject_message}
            </Text>
          )}
        </Stack>
      ),
    },
  ];

  const p = portfolio.data;
  const totalProfit = p ? p.holdings.reduce((sum, h) => sum + h.profit, 0) : 0;

  return (
    <Container>
      <PageHeader
        title="내 자산"
        description={p?.day ? `${formatDay(p.day)} 시작가로 평가한 금액이에요.` : '오늘 시작가로 평가한 금액이에요.'}
      />
      <Stack gap={8}>
        {portfolio.error ? (
          <LoadError error={portfolio.error} onRetry={portfolio.refetch} what="내 자산" />
        ) : !p ? (
          <Card>
            <Skeleton lines={3} height="1.5rem" />
          </Card>
        ) : (
          <StatGroup>
            <Stat
              emphasis
              label="총자산"
              value={<Money value={p.total_assets} />}
              sub={
                <>
                  시작 금액 <Money value={p.initial_cash} /> 대비 <PriceChange rate={p.return_rate} />
                </>
              }
            />
            <Stat label="현금" value={<Money value={p.cash} />} sub="주문에 바로 쓸 수 있어요" />
            <Stat
              label="평가손익"
              value={<Money value={totalProfit} sign colorize />}
              sub={
                <>
                  보유 평가금액 <Money value={p.holdings_value} />
                </>
              }
            />
            <Stat
              label="수익률"
              value={<Percent value={p.return_rate} sign colorize />}
              sub="총자산 기준, 랭킹 순서와 같아요"
            />
          </StatGroup>
        )}

        <Card title="보유 종목" padding={p && p.holdings.length === 0 ? 'md' : 'none'}>
          {p && p.holdings.length === 0 ? (
            <EmptyState
              compact
              title="아직 가진 종목이 없어요"
              description="시세판에서 종목을 골라 첫 주문을 넣어 보세요. 공부를 인증하면 병더리움도 받아요."
              action={<LinkButton to="/">시세판에서 종목 고르기</LinkButton>}
            />
          ) : (
            <Table
              caption="보유 종목"
              columns={HOLDING_COLUMNS}
              rows={p?.holdings ?? []}
              rowKey={(h) => h.code}
              loading={portfolio.loading}
            />
          )}
        </Card>

        <Card title="최근 주문" description="거부된 주문도 사유와 함께 남아요." padding={orders.error ? 'md' : 'none'}>
          {orders.error ? (
            <LoadError error={orders.error} onRetry={orders.refetch} what="주문 내역" />
          ) : (
            <Table
              caption="최근 주문"
              columns={orderColumns}
              rows={orders.data ?? []}
              rowKey={(o) => o.id}
              loading={orders.loading}
              empty="아직 주문 내역이 없어요. 시세판에서 종목을 골라 주문해 보세요."
            />
          )}
        </Card>
      </Stack>
    </Container>
  );
}

import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { ApiError, meApi, type EventInfo, type Instrument, type Portfolio, type Side } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { LoadError } from '../../components/app/LoadError';
import {
  Alert,
  Button,
  Card,
  EmptyState,
  KeyValueList,
  LinkButton,
  Money,
  NumberField,
  SegmentedControl,
  Skeleton,
  Stack,
  Text,
  useToast,
  type KeyValueItem,
} from '../../components/ui';
import { formatPercent, formatQuantity, formatWon } from '../../lib/format';
import { describeMarket } from '../../lib/market';

interface OrderPanelProps {
  instrument: Instrument;
  event?: EventInfo;
  portfolio?: Portfolio;
  portfolioLoading: boolean;
  portfolioError?: ApiError;
  onRetryPortfolio?: () => void;
  onFilled: () => void;
}

/** Order ticket: side toggle, quantity stepper, live estimate and the relevant limits. */
export function OrderPanel({
  instrument,
  event,
  portfolio,
  portfolioLoading,
  portfolioError,
  onRetryPortfolio,
  onFilled,
}: OrderPanelProps) {
  const { status, participant } = useAuth();
  const toast = useToast();
  const location = useLocation();
  const [side, setSide] = useState<Side>('buy');
  const [qty, setQty] = useState(1);
  const [submitting, setSubmitting] = useState(false);

  if (status !== 'authenticated') {
    return (
      <Card title="주문">
        <EmptyState
          compact
          title="로그인하고 주문하세요"
          description="참가자는 1,000,000원으로 시작해요."
          action={
            <Stack direction="row" gap={2} wrap>
              <LinkButton to="/login" state={{ from: location.pathname }}>
                로그인하기
              </LinkButton>
              <LinkButton to="/register" variant="secondary">
                참가 신청하기
              </LinkButton>
            </Stack>
          }
        />
      </Card>
    );
  }

  if (portfolioError && !portfolio) {
    return (
      <Card title="주문">
        <LoadError error={portfolioError} onRetry={onRetryPortfolio} what="내 잔고" />
      </Card>
    );
  }

  if (portfolioLoading || !portfolio) {
    return (
      <Card title="주문">
        <Skeleton lines={5} height="1.25rem" />
      </Card>
    );
  }

  const unit = instrument.kind === 'coin' ? '개' : '주';
  const price = instrument.price;
  const holding = portfolio.holdings.find((h) => h.code === instrument.code);
  const held = holding?.quantity ?? 0;
  const remainingLimit = portfolio.buy_limit.remaining[instrument.code] ?? portfolio.buy_limit.limit_amount;
  const buyBudget = Math.min(portfolio.cash, remainingLimit);
  const maxQty = side === 'buy' ? (price > 0 ? Math.floor(buyBudget / price) : 0) : held;
  const quantity = Math.min(qty, Math.max(maxQty, 1));
  const estimate = price * quantity;
  const market = event ? describeMarket(event) : null;
  const disqualified = participant?.status === 'disqualified';

  let blocker: string | null = null;
  if (maxQty < 1) {
    if (side === 'sell') blocker = '아직 이 종목을 갖고 있지 않아요. 먼저 매수해 보세요.';
    else if (remainingLimit < price)
      blocker = `오늘 이 종목의 매수 한도(총자산의 ${formatPercent(portfolio.buy_limit.ratio, { digits: 0 })})를 다 썼어요. 내일 다시 살 수 있어요.`;
    else blocker = `현금이 부족해서 1${unit}도 살 수 없어요. 가진 종목을 팔면 현금이 생겨요.`;
  }

  const details: KeyValueItem[] = [{ label: '주문 가격(오늘 시작가)', value: <Money value={price} /> }];
  if (side === 'buy') {
    details.push(
      { label: '주문 가능 현금', value: <Money value={portfolio.cash} /> },
      {
        label: `오늘 남은 매수 한도`,
        value: <Money value={remainingLimit} />,
      },
      { label: '보유 수량', value: formatQuantity(held, instrument.kind) },
    );
  } else {
    details.push(
      { label: '보유 수량', value: formatQuantity(held, instrument.kind) },
      { label: '평균단가', value: holding ? <Money value={holding.avg_price} /> : '—' },
    );
  }
  details.push({ label: '예상 금액', value: <Money value={estimate} />, strong: true });

  const canSubmit = !blocker && !disqualified && (market?.canTrade ?? false);
  const verb = side === 'buy' ? '매수' : '매도';

  const submit = async () => {
    setSubmitting(true);
    try {
      const order = await meApi.placeOrder({ code: instrument.code, side, quantity });
      if (order.status === 'filled') {
        const amount = order.amount ?? (order.price ?? price) * order.quantity;
        toast.show({
          tone: side === 'buy' ? 'up' : 'down',
          title: `${verb} 체결됐어요`,
          description: `${instrument.name} ${formatQuantity(order.quantity, instrument.kind)}를 ${formatWon(amount)}에 ${side === 'buy' ? '샀어요' : '팔았어요'}.`,
        });
        setQty(1);
      } else {
        toast.error(`${verb}하지 못했어요`, order.reject_message ?? '주문이 거부됐어요.');
      }
      onFilled();
    } catch (err) {
      toast.error(`${verb}하지 못했어요`, err instanceof ApiError ? err.message : '잠시 뒤 다시 시도해 주세요.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card title="주문">
      <Stack gap={4}>
        <SegmentedControl
          label="주문 종류"
          size="lg"
          fullWidth
          value={side}
          onChange={(v) => {
            setSide(v);
            setQty(1);
          }}
          options={[
            { value: 'buy', label: '매수', tone: 'up' },
            { value: 'sell', label: '매도', tone: 'down' },
          ]}
        />
        <NumberField
          label="수량"
          value={quantity}
          onChange={setQty}
          min={1}
          max={Math.max(maxQty, 1)}
          suffix={unit}
          disabled={Boolean(blocker)}
          hint={
            blocker
              ? undefined
              : `최대 ${formatQuantity(maxQty, instrument.kind)}까지 ${side === 'buy' ? '살' : '팔'} 수 있어요.`
          }
          error={blocker ?? undefined}
          trailing={
            <Button variant="secondary" onClick={() => setQty(Math.max(maxQty, 1))} disabled={Boolean(blocker)}>
              최대
            </Button>
          }
        />
        <KeyValueList items={details} />
        {side === 'buy' && (
          <Text size="xs" tone="muted">
            한 종목은 하루에 총자산의 {formatPercent(portfolio.buy_limit.ratio, { digits: 0 })}(
            {formatWon(portfolio.buy_limit.limit_amount)})까지만 살 수 있어요.
          </Text>
        )}
        {disqualified && <Alert tone="danger" title="실격 처리되어 주문할 수 없어요" />}
        {market && !market.canTrade && !disqualified && <Alert title="지금은 주문할 수 없어요">{market.detail}</Alert>}
        <Button
          variant={side === 'buy' ? 'buy' : 'sell'}
          size="lg"
          fullWidth
          loading={submitting}
          disabled={!canSubmit}
          onClick={submit}
        >
          {formatQuantity(quantity, instrument.kind)} {verb}하기
        </Button>
      </Stack>
    </Card>
  );
}

import { meApi, publicApi, useApi } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { InstrumentBoard } from '../../components/app/InstrumentBoard';
import { LoadError } from '../../components/app/LoadError';
import { MarketStatus } from '../../components/app/MarketStatus';
import { NewsCard } from '../../components/app/NewsCard';
import { Card, Container, LinkButton, Skeleton, Stack, Text } from '../../components/ui';
import { formatDay } from '../../lib/format';

export function MarketPage() {
  const { status } = useAuth();
  const event = useApi(() => publicApi.event(), [], { refreshInterval: 60_000 });
  const instruments = useApi(() => publicApi.instruments(), [], { refreshInterval: 60_000 });
  const news = useApi(() => publicApi.news(), [], { refreshInterval: 60_000 });
  const certs = useApi(() => meApi.certifications(), [status], { enabled: status === 'authenticated' });

  const stamped = certs.data?.filter((c) => c.status === 'approved').map((c) => c.target_date);
  const priceDay = instruments.data?.find((i) => i.day)?.day;

  return (
    <Container padTop>
      <Stack gap={8}>
        {event.error ? (
          <LoadError error={event.error} onRetry={event.refetch} what="장 운영 정보" />
        ) : event.data ? (
          <MarketStatus event={event.data} stamped={stamped} />
        ) : (
          <Card padding="lg">
            <Skeleton lines={3} height="1.5rem" />
          </Card>
        )}

        {news.error ? (
          <LoadError error={news.error} onRetry={news.refetch} what="뉴스" />
        ) : (
          <NewsCard news={news.data} loading={news.loading} today={priceDay} />
        )}

        <Stack gap={3} as="section" aria-labelledby="board-title">
          <Stack direction="row" justify="between" align="end" wrap gap={2}>
            <Stack gap={1}>
              <Text as="p" display size="2xl" tone="ink" id="board-title">
                시세판
              </Text>
              <Text size="sm" tone="muted">
                {priceDay ? `${formatDay(priceDay)} 시작가예요.` : '1일차 시작가예요.'}
              </Text>
            </Stack>
            {status === 'anonymous' && (
              <LinkButton to="/register" variant="primary">
                참가 신청하기
              </LinkButton>
            )}
          </Stack>
          {instruments.error ? (
            <LoadError error={instruments.error} onRetry={instruments.refetch} what="시세" />
          ) : (
            <InstrumentBoard instruments={instruments.data} loading={instruments.loading} />
          )}
          <Text size="sm" tone="muted">
            종목을 눌러 가격 이력을 보고 주문하세요.
          </Text>
        </Stack>
      </Stack>
    </Container>
  );
}

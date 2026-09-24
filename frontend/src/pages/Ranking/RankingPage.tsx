import { publicApi, useApi, type RankingEntry } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { LoadError } from '../../components/app/LoadError';
import {
  Badge,
  Card,
  Container,
  Money,
  PageHeader,
  Percent,
  Stack,
  Stat,
  StatGroup,
  Table,
  Text,
  type Column,
} from '../../components/ui';
import { formatDay } from '../../lib/format';

const COLUMNS: Column<RankingEntry>[] = [
  { key: 'rank', header: '순위', nowrap: true, numeric: true, width: '4.5rem', render: (r) => `${r.rank}위` },
  {
    key: 'nickname',
    header: '닉네임',
    render: (r) => (
      <Stack direction="row" gap={2} align="center" wrap>
        <span>{r.nickname}</span>
        {r.is_me && (
          <Badge tone="highlight" size="sm">
            나
          </Badge>
        )}
      </Stack>
    ),
  },
  { key: 'total', header: '총자산', numeric: true, render: (r) => <Money value={r.total_assets} /> },
  { key: 'rate', header: '수익률', numeric: true, render: (r) => <Percent value={r.return_rate} sign colorize /> },
  { key: 'days', header: '인증일수', numeric: true, hideOnMobile: true, render: (r) => `${r.certified_days}일` },
  { key: 'streak', header: '연속', numeric: true, render: (r) => (r.streak > 0 ? `${r.streak}일` : '—') },
];

export function RankingPage() {
  const { status } = useAuth();
  const ranking = useApi(() => publicApi.ranking(), [status], { refreshInterval: 120_000 });
  const me = ranking.data?.entries.find((e) => e.is_me);
  const count = ranking.data?.entries.length ?? 0;

  return (
    <Container>
      <PageHeader
        title="랭킹"
        description={
          ranking.data?.day
            ? `${formatDay(ranking.data.day)} 시작가 기준 총자산 순위예요. 닉네임만 공개되고, 실격자는 빠져요.`
            : '총자산 순위예요. 닉네임만 공개되고, 실격자는 빠져요.'
        }
      />
      <Stack gap={6}>
        {me && (
          <StatGroup>
            <Stat emphasis label="내 순위" value={`${me.rank}위`} sub={`${count}명 중`} />
            <Stat
              label="총자산"
              value={<Money value={me.total_assets} />}
              sub={<Percent value={me.return_rate} sign colorize />}
            />
            <Stat label="인증일수" value={`${me.certified_days}일`} sub="승인된 인증 기준" />
            <Stat
              label="연속 인증"
              value={me.streak > 0 ? `${me.streak}일째` : '—'}
              sub={me.streak > 0 ? '오늘도 이어가 보세요' : '오늘 인증하면 1일째가 돼요'}
            />
          </StatGroup>
        )}
        <Card padding={ranking.error ? 'md' : 'none'}>
          {ranking.error ? (
            <LoadError error={ranking.error} onRetry={ranking.refetch} what="랭킹" />
          ) : (
            <Table
              caption="총자산 순위"
              columns={COLUMNS}
              rows={ranking.data?.entries ?? []}
              rowKey={(r) => `${r.rank}-${r.nickname}`}
              isRowHighlighted={(r) => Boolean(r.is_me)}
              loading={ranking.loading}
              empty="아직 순위가 없어요. 첫 참가자가 되어 보세요."
            />
          )}
        </Card>
        <Text size="sm" tone="muted">
          동점이면 같은 순위를 받아요(1, 2, 2, 4위). 연속은 오늘까지 끊기지 않고 인증한 날 수예요.
        </Text>
      </Stack>
    </Container>
  );
}

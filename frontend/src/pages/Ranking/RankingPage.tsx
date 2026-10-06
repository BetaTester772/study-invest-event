import { useMemo, useState } from 'react';
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
  SegmentedControl,
  Stack,
  Stat,
  StatGroup,
  Table,
  Text,
  type Column,
} from '../../components/ui';
import { formatDay } from '../../lib/format';
import { sortRanking, type RankingSort } from '../../lib/ranking';

const NICKNAME: Column<RankingEntry> = {
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
};
const TOTAL: Column<RankingEntry> = {
  key: 'total',
  header: '총자산',
  numeric: true,
  render: (r) => <Money value={r.total_assets} />,
};
const RATE: Column<RankingEntry> = {
  key: 'rate',
  header: '수익률',
  numeric: true,
  render: (r) => <Percent value={r.return_rate} sign colorize />,
};
const PROFIT: Column<RankingEntry> = {
  key: 'profit',
  header: '투자 손익',
  numeric: true,
  hideOnMobile: true,
  render: (r) => <Money value={r.profit} sign colorize />,
};
const PRINCIPAL: Column<RankingEntry> = {
  key: 'principal',
  header: '투입 원금',
  numeric: true,
  hideOnMobile: true,
  render: (r) => <Money value={r.principal} />,
};
const DAYS: Column<RankingEntry> = {
  key: 'days',
  header: '인증일수',
  numeric: true,
  hideOnMobile: true,
  render: (r) => `${r.certified_days}일`,
};
const STREAK: Column<RankingEntry> = {
  key: 'streak',
  header: '연속',
  numeric: true,
  render: (r) => (r.streak > 0 ? `${r.streak}일` : '—'),
};

const COLUMNS: Record<RankingSort, Column<RankingEntry>[]> = {
  total: [
    { key: 'rank', header: '순위', nowrap: true, numeric: true, width: '4.5rem', render: (r) => `${r.rank}위` },
    NICKNAME,
    TOTAL,
    PRINCIPAL,
    RATE,
    DAYS,
    STREAK,
  ],
  return: [
    {
      key: 'return_rank',
      header: '수익률 순위',
      nowrap: true,
      numeric: true,
      width: '6rem',
      render: (r) => `${r.return_rank}위`,
    },
    NICKNAME,
    RATE,
    PROFIT,
    PRINCIPAL,
    TOTAL,
    STREAK,
  ],
};

const SORT_OPTIONS = [
  { value: 'total' as const, label: '총자산 순' },
  { value: 'return' as const, label: '수익률 순' },
];

export function RankingPage() {
  const { status } = useAuth();
  const ranking = useApi(() => publicApi.ranking(), [status], { refreshInterval: 120_000 });
  const [sort, setSort] = useState<RankingSort>('total');
  const entries = useMemo(() => ranking.data?.entries ?? [], [ranking.data]);
  const rows = useMemo(() => sortRanking(entries, sort), [entries, sort]);
  const me = entries.find((e) => e.is_me);
  const count = entries.length;

  return (
    <Container>
      <PageHeader
        title="랭킹"
        description={`${ranking.data?.day ? `${formatDay(ranking.data.day)} 시작가 기준 ` : ''}총자산 순위입니다. 수익률 순으로도 확인할 수 있습니다. 닉네임만 공개되며, 실격자는 제외됩니다.`}
      />
      <Stack gap={6}>
        {me && (
          <StatGroup>
            <Stat emphasis label="내 순위" value={`${me.rank}위`} sub={`총자산 기준, ${count}명 중`} />
            <Stat
              label="총자산"
              value={<Money value={me.total_assets} />}
              sub={
                <>
                  투입 원금 <Money value={me.principal} />
                </>
              }
            />
            <Stat
              label="내 수익률"
              value={<Percent value={me.return_rate} sign colorize />}
              sub={`수익률 ${me.return_rank}위, ${count}명 중`}
            />
            <Stat
              label="연속 인증"
              value={me.streak > 0 ? `${me.streak}일째` : '—'}
              sub={me.streak > 0 ? `인증 ${me.certified_days}일, 오늘도 이어가 보세요` : '오늘 인증하면 1일째가 됩니다'}
            />
          </StatGroup>
        )}
        <Stack direction="row" justify="between" align="center" wrap gap={3}>
          <SegmentedControl label="순위 기준" value={sort} onChange={setSort} options={SORT_OPTIONS} />
        </Stack>
        <Card padding={ranking.error ? 'md' : 'none'}>
          {ranking.error ? (
            <LoadError error={ranking.error} onRetry={ranking.refetch} what="랭킹" />
          ) : (
            <Table
              caption={sort === 'total' ? '총자산 순위' : '수익률 순위'}
              columns={COLUMNS[sort]}
              rows={rows}
              rowKey={(r) => r.nickname}
              isRowHighlighted={(r) => Boolean(r.is_me)}
              loading={ranking.loading}
              empty="아직 순위가 없습니다. 첫 참가자가 되어 보세요."
            />
          )}
        </Card>
        <Stack gap={2}>
          <Text size="sm" tone="muted">
            수익률은 각자 넣은 투입 원금(시드 1,000,000원 + 받은 인증 보상) 대비 투자 손익입니다. 인증 보상은 손익이
            아니라 원금으로 쳐서, 보상을 받았다고 수익률이 오르지는 않습니다.
          </Text>
          <Text size="sm" tone="muted">
            동점이면 같은 순위를 받습니다(1, 2, 2, 4위). 연속은 오늘까지 끊기지 않고 인증한 날 수입니다.
          </Text>
        </Stack>
      </Stack>
    </Container>
  );
}

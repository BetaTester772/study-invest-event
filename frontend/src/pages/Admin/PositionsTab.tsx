import { useMemo, useState } from 'react';
import { adminApi, useApi, type AdminPosition } from '../../api';
import { ParticipantStatusBadge } from '../../components/app/badges';
import { LoadError } from '../../components/app/LoadError';
import { Card, Money, Percent, SegmentedControl, Select, Stack, Table, Text, type Column } from '../../components/ui';

type View = 'participant' | 'instrument';

interface Group {
  key: string;
  label: string;
  rows: AdminPosition[];
}

const sum = (rows: AdminPosition[], pick: (r: AdminPosition) => number) => rows.reduce((a, r) => a + pick(r), 0);

/** 관리자: 누가 무엇을 얼마나 샀고 지금 얼마나 들고 있는지(참가자별 / 종목별). */
export function PositionsTab() {
  const positions = useApi(() => adminApi.positions(), []);
  const [view, setView] = useState<View>('participant');
  const [holdingOnly, setHoldingOnly] = useState('all');
  const all = positions.data;

  const rows = useMemo(
    () => (all ?? []).filter((r) => holdingOnly === 'all' || r.quantity > 0),
    [all, holdingOnly],
  );

  const groups = useMemo<Group[]>(() => {
    const byKey = new Map<string, Group>();
    for (const r of rows) {
      const key = view === 'participant' ? String(r.participant_id) : r.code;
      const label = view === 'participant' ? r.nickname : r.name;
      const g = byKey.get(key) ?? { key, label, rows: [] };
      g.rows.push(r);
      byKey.set(key, g);
    }
    const list = [...byKey.values()];
    // 종목은 마스터 순서(첫 등장 순), 참가자는 평가액 큰 순.
    if (view === 'participant') list.sort((a, b) => sum(b.rows, (r) => r.value) - sum(a.rows, (r) => r.value));
    return list;
  }, [rows, view]);

  const byParticipant = view === 'participant';
  const columns: Column<AdminPosition>[] = [
    byParticipant
      ? { key: 'code', header: '종목', render: (r) => r.name }
      : {
          key: 'nick',
          header: '참가자',
          render: (r) => (
            <Stack direction="row" gap={2} align="center">
              {r.nickname}
              <ParticipantStatusBadge status={r.status} />
            </Stack>
          ),
        },
    { key: 'qty', header: '보유 수량', numeric: true, render: (r) => r.quantity.toLocaleString('ko-KR') },
    { key: 'value', header: '평가액', numeric: true, render: (r) => <Money value={r.value} /> },
    {
      key: 'avg',
      header: '평균 매입가',
      numeric: true,
      hideOnMobile: true,
      render: (r) => (r.quantity > 0 ? <Money value={Math.round(r.cost / r.quantity)} /> : '-'),
    },
    {
      key: 'pl',
      header: '평가손익',
      numeric: true,
      render: (r) => (r.quantity > 0 && r.cost > 0 ? <Percent value={(r.value - r.cost) / r.cost} sign colorize /> : '-'),
    },
    {
      key: 'bought',
      header: '누적 매수',
      numeric: true,
      hideOnMobile: true,
      render: (r) => (
        <>
          {r.bought_quantity.toLocaleString('ko-KR')}주 · <Money value={r.bought_amount} />
        </>
      ),
    },
    {
      key: 'sold',
      header: '누적 매도',
      numeric: true,
      hideOnMobile: true,
      render: (r) => (
        <>
          {r.sold_quantity.toLocaleString('ko-KR')}주 · <Money value={r.sold_amount} />
        </>
      ),
    },
  ];

  return (
    <Stack gap={4}>
      <Stack direction="row" gap={3} align="center" wrap>
        <SegmentedControl
          label="보기 기준"
          value={view}
          onChange={setView}
          options={[
            { value: 'participant', label: '참가자별' },
            { value: 'instrument', label: '종목별' },
          ]}
        />
        <Select
          label="표시 범위"
          hideLabel
          value={holdingOnly}
          onChange={setHoldingOnly}
          options={[
            { value: 'all', label: '매수 이력 있는 모두' },
            { value: 'holding', label: '현재 보유 중만' },
          ]}
        />
      </Stack>
      <Text size="sm" tone="muted">
        체결된 주문만 집계합니다(거부된 주문 제외). 평가액은 최신 공시 시작가 기준, 평가손익은 보유분 취득 원가 대비입니다.
      </Text>
      {positions.error ? (
        <Card>
          <LoadError error={positions.error} onRetry={positions.refetch} what="거래·보유 현황" />
        </Card>
      ) : positions.loading ? (
        <Card padding="none">
          <Table caption="거래·보유 현황" columns={columns} rows={[]} rowKey={() => 0} loading />
        </Card>
      ) : groups.length === 0 ? (
        <Card>
          <Text tone="muted">아직 표시할 거래·보유 내역이 없습니다.</Text>
        </Card>
      ) : (
        groups.map((g) => (
          <Card key={g.key} padding="none">
            <Stack gap={2}>
              <Stack direction="row" justify="between" align="center" gap={3} wrap>
                <Text weight="semibold">{g.label}</Text>
                <Text size="sm" tone="muted">
                  {byParticipant ? '평가액 합계' : `보유 ${g.rows.filter((r) => r.quantity > 0).length}명 · 평가액 합계`}{' '}
                  <Money value={sum(g.rows, (r) => r.value)} /> · 보유 {sum(g.rows, (r) => r.quantity).toLocaleString('ko-KR')}
                  주 · 누적 매수 <Money value={sum(g.rows, (r) => r.bought_amount)} /> · 누적 매도{' '}
                  <Money value={sum(g.rows, (r) => r.sold_amount)} />
                </Text>
              </Stack>
              <Table
                caption={`${g.label} 거래·보유`}
                columns={columns}
                rows={g.rows}
                rowKey={(r) => `${r.participant_id}-${r.code}`}
                dense
              />
            </Stack>
          </Card>
        ))
      )}
    </Stack>
  );
}

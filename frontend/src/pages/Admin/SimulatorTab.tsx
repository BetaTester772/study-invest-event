import { useState, type FormEvent } from 'react';
import { adminApi, ApiError, useApi, type SimulateOptions, type SimulationReport } from '../../api';
import { LoadError } from '../../components/app/LoadError';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Grid,
  NumberField,
  Percent,
  Skeleton,
  Stack,
  Stat,
  StatGroup,
  Table,
  Text,
  TextField,
} from '../../components/ui';
import { formatNumber, formatPercent } from '../../lib/format';

const q = (v: number) =>
  v === 0.5
    ? '중앙값'
    : v < 0.5
      ? `하위 ${formatPercent(v, { digits: 0 })}`
      : `상위 ${formatPercent(1 - v, { digits: 0 })}`;

function Report({ r }: { r: SimulationReport }) {
  return (
    <Stack gap={5}>
      <Text size="sm" tone="muted">
        경로 {formatNumber(r.paths)}개, {r.rounds}회, 시드 {r.seed ?? '무작위'}, 가격 상한{' '}
        {r.price_cap ? `${formatNumber(r.price_cap)}원` : '없음'}
      </Text>
      <StatGroup>
        <Stat label="상승일 비율" value={<Percent value={r.daily.up_ratio} />} sub="목표 약 30%" />
        <Stat label="상승일 평균" value={<Percent value={r.daily.mean_up} sign colorize />} sub="목표 약 +75%" />
        <Stat label="하락일 평균" value={<Percent value={r.daily.mean_down} sign colorize />} sub="목표 약 -16.7%" />
        <Stat label="일일 평균" value={<Percent value={r.daily.mean} sign colorize />} />
        <Stat
          label="로그 기대값"
          value={formatNumber(r.daily.mean_log, 4)}
          sub="0에 가까울수록 누적 중앙값이 원금 수준"
        />
        <Stat label="가격 상한 도달" value={<Percent value={r.cumulative.cap_hit_ratio} />} sub="경로 비율" />
      </StatGroup>
      <Grid min="16rem" gap={4}>
        <Card title="일일 변동률 분위" padding="none">
          <Table
            caption="일일 변동률 분위"
            dense
            columns={[
              { key: 'q', header: '구간', render: (x) => q(x.q) },
              { key: 'rate', header: '변동률', numeric: true, render: (x) => <Percent value={x.rate} sign colorize /> },
            ]}
            rows={r.daily.quantiles}
            rowKey={(x) => x.q}
          />
        </Card>
        <Card title="누적 배수 분위" padding="none">
          <Table
            caption="누적 배수 분위"
            dense
            columns={[
              { key: 'q', header: '구간', render: (x) => q(x.q) },
              { key: 'm', header: '누적 배수', numeric: true, render: (x) => `${formatNumber(x.multiple, 2)}배` },
            ]}
            rows={r.cumulative.quantiles}
            rowKey={(x) => x.q}
          />
        </Card>
        <Card title="배수 초과 확률" padding="none">
          <Table
            caption="배수 초과 확률"
            dense
            columns={[
              { key: 'm', header: '누적 배수', render: (x) => `${formatNumber(x.multiple, 1)}배 초과` },
              { key: 'p', header: '확률', numeric: true, render: (x) => <Percent value={x.prob} /> },
            ]}
            rows={r.cumulative.prob_above}
            rowKey={(x) => x.multiple}
          />
        </Card>
      </Grid>
    </Stack>
  );
}

export function SimulatorTab() {
  // 입력 범위·기본값은 서버가 정한다(서버 스키마가 유일한 출처).
  const options = useApi(() => adminApi.simulateOptions(), []);
  if (options.error) return <LoadError error={options.error} onRetry={options.refetch} what="시뮬레이터 설정" />;
  if (!options.data) return <Skeleton lines={4} />;
  return <SimulatorForm options={options.data} />;
}

function SimulatorForm({ options }: { options: SimulateOptions }) {
  const [paths, setPaths] = useState(options.paths.default);
  const [rounds, setRounds] = useState(options.rounds.default);
  const [seed, setSeed] = useState('');
  const [useCap, setUseCap] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<SimulationReport | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (seed && !/^-?\d+$/.test(seed.trim())) {
      setError('시드는 정수로 입력하세요. 비우면 매번 다른 결과가 나와요.');
      return;
    }
    setRunning(true);
    setError(null);
    try {
      setReport(
        await adminApi.simulate({
          paths,
          rounds,
          seed: seed.trim() ? Number(seed) : null,
          use_price_cap: useCap,
        }),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '시뮬레이션을 돌리지 못했어요.');
    } finally {
      setRunning(false);
    }
  };

  return (
    <Stack gap={6}>
      <Card
        title="코인 가격 경로 시뮬레이션"
        description="지금 저장된 파라미터로 병더리움 가격 경로를 여러 번 만들어 분포를 확인해요."
      >
        <form onSubmit={submit} noValidate>
          <Stack gap={4}>
            {error && <Alert tone="danger">{error}</Alert>}
            <Grid min="12rem" gap={4}>
              <NumberField
                label="경로 수"
                value={paths}
                onChange={setPaths}
                min={options.paths.min}
                max={options.paths.max}
                step={1000}
                suffix="개"
                hint={`${formatNumber(options.paths.min)}~${formatNumber(options.paths.max)}개`}
              />
              <NumberField
                label="회차"
                value={rounds}
                onChange={setRounds}
                min={options.rounds.min}
                max={options.rounds.max}
                suffix="회"
              />
              <TextField
                label="시드"
                hint="비우면 무작위"
                inputMode="numeric"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
              />
            </Grid>
            <Checkbox
              label="코인 가격 상한 적용"
              hint="파라미터의 코인 가격 상한으로 경로를 자릅니다."
              checked={useCap}
              onChange={setUseCap}
            />
            <Stack direction="row" justify="end">
              <Button type="submit" loading={running}>
                시뮬레이션 돌리기
              </Button>
            </Stack>
          </Stack>
        </form>
      </Card>
      {report && <Report r={report} />}
    </Stack>
  );
}

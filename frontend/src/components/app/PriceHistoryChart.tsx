import { useMemo, useState } from 'react';
import type { PricePoint } from '../../api';
import { formatDayShort, formatNumber, formatPercent, formatWon } from '../../lib/format';
import {
  bollinger,
  dailyChange,
  ema,
  INDICATOR_PERIODS as PERIODS,
  macd,
  rsi,
  sma,
  type Series,
} from '../../lib/indicators';
import { IndicatorPanel, LineChart, Text, type ChartBand, type ChartOverlay } from '../ui';
import styles from './PriceHistoryChart.module.css';

export type IndicatorId = 'sma3' | 'sma5' | 'ema5' | 'bollinger' | 'rsi' | 'macd' | 'change';

interface IndicatorOption {
  id: IndicatorId;
  label: string;
  /** Where it is drawn: on the price chart, or in its own panel under it. */
  where: 'overlay' | 'panel';
  /** CSS color of its line key; panels and bands without a hue use a neutral key. */
  color?: string;
  /** Number of daily prices needed before the first value exists. */
  from: number;
}

const OPTIONS: IndicatorOption[] = [
  {
    id: 'sma3',
    label: `이동평균 ${PERIODS.smaShort}일`,
    where: 'overlay',
    color: 'var(--chart-1)',
    from: PERIODS.smaShort,
  },
  {
    id: 'sma5',
    label: `이동평균 ${PERIODS.smaLong}일`,
    where: 'overlay',
    color: 'var(--chart-2)',
    from: PERIODS.smaLong,
  },
  { id: 'ema5', label: `지수이동평균 ${PERIODS.ema}일`, where: 'overlay', color: 'var(--chart-3)', from: PERIODS.ema },
  { id: 'bollinger', label: '볼린저 밴드', where: 'overlay', from: PERIODS.bollinger.period },
  { id: 'rsi', label: 'RSI', where: 'panel', from: PERIODS.rsi + 1 },
  { id: 'macd', label: 'MACD', where: 'panel', from: PERIODS.macd.slow },
  { id: 'change', label: '일간 변동률', where: 'panel', from: 2 },
];

const BY_ID = new Map(OPTIONS.map((o) => [o.id, o]));
const DEFAULT_ON: IndicatorId[] = ['sma3', 'sma5'];

const signedWon = (v: number) => formatWon(v, { sign: true });

/** Legend/empty-panel text while there are too few days for the indicator, e.g. `5일째부터`. */
function fromNote(id: IndicatorId): string {
  return `${BY_ID.get(id)?.from ?? 0}일째부터`;
}

/**
 * Price history with switchable technical indicators. Moving averages and Bollinger bands are drawn on
 * the price chart; RSI, MACD and the daily change sit in short panels beneath it, sharing one hover
 * position so a single day can be read across all of them.
 *
 * The event has only ~11 operating days, so the windows are short (3–5 days) rather than the textbook ones.
 */
export function PriceHistoryChart({ history, name }: { history: PricePoint[]; name: string }) {
  const [on, setOn] = useState<ReadonlySet<IndicatorId>>(() => new Set(DEFAULT_ON));
  const [active, setActive] = useState<number | null>(null);

  const prices = useMemo(() => history.map((p) => p.price), [history]);
  const days = useMemo(() => history.map((p) => p.day), [history]);
  const points = useMemo(() => history.map((p) => ({ x: p.day, y: p.price })), [history]);

  const calc = useMemo(() => {
    const b = bollinger(prices, PERIODS.bollinger.period, PERIODS.bollinger.k);
    const m = macd(prices, PERIODS.macd.fast, PERIODS.macd.slow, PERIODS.macd.signal);
    return {
      sma3: sma(prices, PERIODS.smaShort),
      sma5: sma(prices, PERIODS.smaLong),
      ema5: ema(prices, PERIODS.ema),
      band: b,
      rsi: rsi(prices, PERIODS.rsi),
      macd: m,
      change: dailyChange(prices),
    };
  }, [prices]);

  const overlays = useMemo<ChartOverlay[]>(() => {
    const series: Record<'sma3' | 'sma5' | 'ema5', Series> = {
      sma3: calc.sma3,
      sma5: calc.sma5,
      ema5: calc.ema5,
    };
    return OPTIONS.filter((o) => o.where === 'overlay' && o.color && on.has(o.id)).map((o) => ({
      id: o.id,
      label: o.label,
      values: series[o.id as 'sma3' | 'sma5' | 'ema5'],
      color: o.color as string,
      emptyNote: fromNote(o.id),
    }));
  }, [calc, on]);

  const bands = useMemo<ChartBand[]>(
    () =>
      on.has('bollinger')
        ? [
            {
              id: 'bollinger',
              label: `볼린저 밴드 (${PERIODS.bollinger.period}일, ±${PERIODS.bollinger.k}σ)`,
              upper: calc.band.upper,
              lower: calc.band.lower,
              emptyNote: fromNote('bollinger'),
            },
          ]
        : [],
    [calc, on],
  );

  const panelOrder = OPTIONS.filter((o) => o.where === 'panel' && on.has(o.id)).map((o) => o.id);
  const lastPanel = panelOrder[panelOrder.length - 1];

  // Memoised so the panels' own geometry is not rebuilt on every hover.
  const rsiLines = useMemo(
    () => [{ id: 'rsi', label: `RSI (${PERIODS.rsi}일)`, values: calc.rsi, color: 'var(--color-ink)' }],
    [calc],
  );
  const macdLines = useMemo(
    () => [
      { id: 'macd', label: 'MACD', values: calc.macd.macd, color: 'var(--color-ink)' },
      { id: 'signal', label: '시그널', values: calc.macd.signal, color: 'var(--chart-3)', dashed: true },
    ],
    [calc],
  );
  const macdBars = useMemo(() => ({ id: 'hist', label: '차이', values: calc.macd.histogram }), [calc]);
  const changeBars = useMemo(() => ({ id: 'change', label: '전일 대비', values: calc.change }), [calc]);
  const rsiGuides = useMemo(
    () => [
      { value: 70, label: '70' },
      { value: 30, label: '30' },
    ],
    [],
  );
  const rsiZones = useMemo(
    () => [
      { from: 70, to: 100 },
      { from: 0, to: 30 },
    ],
    [],
  );

  const toggle = (id: IndicatorId) =>
    setOn((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const common = { x: days, formatX: formatDayShort, activeIndex: active, onActiveChange: setActive };

  return (
    <div className={styles.root}>
      {history.length > 0 && (
        <fieldset className={styles.picker}>
          <legend className={styles.legend}>보조 지표</legend>
          <div className={styles.chips}>
            {OPTIONS.map((o) => (
              <label key={o.id} className={styles.chip} data-on={on.has(o.id) || undefined}>
                <input type="checkbox" className={styles.input} checked={on.has(o.id)} onChange={() => toggle(o.id)} />
                <span
                  className={o.where === 'overlay' && !o.color ? styles.keyBand : styles.keyLine}
                  style={o.color ? { background: o.color } : undefined}
                  aria-hidden="true"
                  data-panel={o.where === 'panel' || undefined}
                />
                {o.label}
              </label>
            ))}
          </div>
        </fieldset>
      )}

      <LineChart
        points={points}
        label={`${name} 시작가 이력`}
        formatX={formatDayShort}
        overlays={overlays}
        bands={bands}
        activeIndex={active}
        onActiveChange={setActive}
      />

      {panelOrder.length > 0 && (
        <div className={styles.panels}>
          {panelOrder.includes('rsi') && (
            <IndicatorPanel
              {...common}
              title={`RSI (${PERIODS.rsi}일)`}
              description="70 넘으면 단기 과열, 30 아래면 침체로 봅니다."
              lines={rsiLines}
              guides={rsiGuides}
              zones={rsiZones}
              domain={[0, 100]}
              formatValue={(v) => formatNumber(v, 1)}
              formatTick={(v) => formatNumber(v)}
              emptyNote={`${fromNote('rsi')} 표시됩니다.`}
              showXAxis={lastPanel === 'rsi'}
            />
          )}
          {panelOrder.includes('macd') && (
            <IndicatorPanel
              {...common}
              title={`MACD (${PERIODS.macd.fast}·${PERIODS.macd.slow}·${PERIODS.macd.signal}일)`}
              description="MACD선이 시그널선 위면 상승세, 아래면 하락세입니다. 막대는 둘의 차이입니다."
              lines={macdLines}
              bars={macdBars}
              zero
              formatValue={signedWon}
              formatTick={(v) => formatNumber(v)}
              emptyNote={`${fromNote('macd')} 표시됩니다.`}
              showXAxis={lastPanel === 'macd'}
            />
          )}
          {panelOrder.includes('change') && (
            <IndicatorPanel
              {...common}
              title="일간 변동률"
              description="전날 시작가와 비교한 변화율입니다."
              bars={changeBars}
              zero
              formatValue={(v) => formatPercent(v, { sign: true })}
              formatTick={(v) => formatPercent(v, { digits: 1 })}
              emptyNote={`${fromNote('change')} 표시됩니다.`}
              showXAxis={lastPanel === 'change'}
            />
          )}
        </div>
      )}

      {on.size > 0 && (
        <Text as="p" size="xs" tone="muted">
          참고용 지표입니다. 이 게임의 주식 가격은 참가자들의 매수 쏠림과 뉴스로 움직여서 실제 주식과 다르게 읽힐 수
          있어요.
        </Text>
      )}
    </div>
  );
}

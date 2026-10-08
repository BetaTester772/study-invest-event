/**
 * Technical indicators over a price series. Pure functions: every result has the same length as the
 * input, with `null` where the indicator is not defined yet (not enough history), so results line up
 * index-for-index with the chart's x positions.
 *
 * The event only has ~11 operating days of prices, so the periods used on screen are short (see
 * INDICATOR_PERIODS) rather than the textbook 14/20/12-26-9.
 */

export type Series = Array<number | null>;

/** Periods the price chart uses; kept in one place so labels and math cannot drift apart. */
export const INDICATOR_PERIODS = {
  smaShort: 3,
  smaLong: 5,
  ema: 5,
  bollinger: { period: 5, k: 2 },
  rsi: 5,
  macd: { fast: 3, slow: 5, signal: 3 },
} as const;

function assertPeriod(period: number): void {
  if (!Number.isInteger(period) || period < 1) throw new RangeError('period must be a positive integer');
}

/** Simple moving average of the last `period` values. Defined from index `period - 1`. */
export function sma(values: readonly number[], period: number): Series {
  assertPeriod(period);
  const out: Series = [];
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i] as number;
    if (i >= period) sum -= values[i - period] as number;
    out.push(i >= period - 1 ? sum / period : null);
  }
  return out;
}

/**
 * Exponential moving average with smoothing 2 / (period + 1), seeded with the SMA of the first
 * `period` values (the usual convention). Defined from index `period - 1`.
 */
export function ema(values: readonly number[], period: number): Series {
  assertPeriod(period);
  const out: Series = [];
  const alpha = 2 / (period + 1);
  let prev: number | null = null;
  let seed = 0;
  for (let i = 0; i < values.length; i++) {
    const v = values[i] as number;
    if (i < period - 1) {
      seed += v;
      out.push(null);
    } else if (prev == null) {
      prev = (seed + v) / period;
      out.push(prev);
    } else {
      prev = prev + alpha * (v - prev);
      out.push(prev);
    }
  }
  return out;
}

export interface BollingerBands {
  middle: Series;
  upper: Series;
  lower: Series;
}

/** Bollinger bands: SMA ± k × population standard deviation over the same window. */
export function bollinger(values: readonly number[], period: number, k: number): BollingerBands {
  assertPeriod(period);
  const middle = sma(values, period);
  const upper: Series = [];
  const lower: Series = [];
  for (let i = 0; i < values.length; i++) {
    const mean = middle[i];
    if (mean == null) {
      upper.push(null);
      lower.push(null);
      continue;
    }
    let sq = 0;
    for (let j = i - period + 1; j <= i; j++) sq += ((values[j] as number) - mean) ** 2;
    const sd = Math.sqrt(sq / period);
    upper.push(mean + k * sd);
    lower.push(mean - k * sd);
  }
  return { middle, upper, lower };
}

/**
 * Relative strength index (Wilder smoothing), 0–100. Defined from index `period` (it needs `period`
 * price changes). No losses in the window → 100; no movement at all → 50.
 */
export function rsi(values: readonly number[], period: number): Series {
  assertPeriod(period);
  const out: Series = values.map(() => null);
  if (values.length <= period) return out;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const d = (values[i] as number) - (values[i - 1] as number);
    if (d >= 0) gain += d;
    else loss -= d;
  }
  let avgGain = gain / period;
  let avgLoss = loss / period;
  const toRsi = () => (avgLoss === 0 ? (avgGain === 0 ? 50 : 100) : 100 - 100 / (1 + avgGain / avgLoss));
  out[period] = toRsi();
  for (let i = period + 1; i < values.length; i++) {
    const d = (values[i] as number) - (values[i - 1] as number);
    avgGain = (avgGain * (period - 1) + Math.max(d, 0)) / period;
    avgLoss = (avgLoss * (period - 1) + Math.max(-d, 0)) / period;
    out[i] = toRsi();
  }
  return out;
}

export interface Macd {
  macd: Series;
  signal: Series;
  histogram: Series;
}

/**
 * MACD: EMA(fast) − EMA(slow), its EMA(signal) as the signal line, and the gap between them as the
 * histogram. The line is defined from index `slow - 1`, signal and histogram `signal - 1` later.
 */
export function macd(values: readonly number[], fast: number, slow: number, signal: number): Macd {
  assertPeriod(fast);
  assertPeriod(slow);
  assertPeriod(signal);
  const fastEma = ema(values, fast);
  const slowEma = ema(values, slow);
  const line: Series = values.map((_, i) => {
    const f = fastEma[i];
    const s = slowEma[i];
    return f == null || s == null ? null : f - s;
  });
  const start = line.findIndex((v) => v != null);
  const signalLine: Series = values.map(() => null);
  if (start >= 0) {
    // The line is defined without gaps from `start` on, so smooth that stretch and put it back.
    const tail = ema(line.slice(start) as number[], signal);
    tail.forEach((v, i) => {
      signalLine[start + i] = v;
    });
  }
  const histogram: Series = line.map((v, i) => {
    const s = signalLine[i];
    return v == null || s == null ? null : v - s;
  });
  return { macd: line, signal: signalLine, histogram };
}

/** Day-over-day change as a decimal rate (0.032 = +3.2%). Index 0 has no previous day. */
export function dailyChange(values: readonly number[]): Series {
  return values.map((v, i) => {
    const prev = i === 0 ? null : (values[i - 1] as number);
    return prev == null || prev === 0 ? null : v / prev - 1;
  });
}

/** Last defined value of a series, or null. */
export function lastValue(series: Series): number | null {
  for (let i = series.length - 1; i >= 0; i--) {
    const v = series[i];
    if (v != null) return v;
  }
  return null;
}

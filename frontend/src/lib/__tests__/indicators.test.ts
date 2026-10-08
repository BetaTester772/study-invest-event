import { describe, expect, it } from 'vitest';
import { bollinger, dailyChange, ema, lastValue, macd, rsi, sma, type Series } from '../indicators';

function close(actual: Series, expected: Series, digits = 6) {
  expect(actual).toHaveLength(expected.length);
  expected.forEach((e, i) => {
    const a = actual[i];
    if (e == null) expect(a, `index ${i}`).toBeNull();
    else expect(a, `index ${i}`).toBeCloseTo(e, digits);
  });
}

describe('sma', () => {
  it('averages the last N values and is null until the window fills', () => {
    close(sma([1, 2, 3, 4, 5], 3), [null, null, 2, 3, 4]);
  });

  it('with period 1 is the series itself', () => {
    close(sma([4, 9, 2], 1), [4, 9, 2]);
  });

  it('is all null when there is less history than the period', () => {
    close(sma([1, 2], 5), [null, null]);
  });

  it('rejects a non-positive or fractional period', () => {
    expect(() => sma([1], 0)).toThrow(RangeError);
    expect(() => sma([1], 1.5)).toThrow(RangeError);
  });
});

describe('ema', () => {
  it('seeds with the SMA of the first N values, then smooths with 2 / (N + 1)', () => {
    // period 3 → alpha 0.5; seed = (1 + 2 + 3) / 3 = 2
    // next: 2 + 0.5 × (4 − 2) = 3, then 3 + 0.5 × (5 − 3) = 4
    close(ema([1, 2, 3, 4, 5], 3), [null, null, 2, 3, 4]);
  });

  it('stays flat on a flat series', () => {
    close(ema([7, 7, 7, 7], 2), [null, 7, 7, 7]);
  });

  it('reacts faster than the SMA of the same length', () => {
    const rising = [10, 10, 10, 20, 30];
    const e = ema(rising, 3).at(-1) as number;
    const s = sma(rising, 3).at(-1) as number;
    expect(e).toBeGreaterThan(s);
  });
});

describe('bollinger', () => {
  it('uses the SMA as the middle band and ± k population standard deviations', () => {
    // window [1, 2, 3]: mean 2, population variance 2/3
    const b = bollinger([1, 2, 3], 3, 2);
    const sd = Math.sqrt(2 / 3);
    close(b.middle, [null, null, 2]);
    close(b.upper, [null, null, 2 + 2 * sd]);
    close(b.lower, [null, null, 2 - 2 * sd]);
  });

  it('collapses to the middle band when the price is flat', () => {
    const b = bollinger([5, 5, 5, 5], 3, 2);
    close(b.upper, [null, null, 5, 5]);
    close(b.lower, [null, null, 5, 5]);
  });

  it('widens with k', () => {
    const narrow = bollinger([1, 3, 2, 5, 4], 3, 1).upper.at(-1) as number;
    const wide = bollinger([1, 3, 2, 5, 4], 3, 2).upper.at(-1) as number;
    expect(wide).toBeGreaterThan(narrow);
  });
});

describe('rsi', () => {
  it('is 100 when there are only gains in the window', () => {
    close(rsi([1, 2, 3, 4, 5, 6], 3), [null, null, null, 100, 100, 100]);
  });

  it('is 0 when there are only losses', () => {
    close(rsi([6, 5, 4, 3, 2, 1], 3), [null, null, null, 0, 0, 0]);
  });

  it('is 50 when nothing moves', () => {
    close(rsi([4, 4, 4, 4], 2), [null, null, 50, 50]);
  });

  it('matches a hand calculation with Wilder smoothing', () => {
    // changes: +2, −1, +3, −2 ; period 2
    // first window (+2, −1): avgGain 1, avgLoss 0.5 → RS 2 → RSI 66.667
    // then +3: avgGain (1×1 + 3)/2 = 2, avgLoss (0.5×1 + 0)/2 = 0.25 → RS 8 → RSI 88.889
    // then −2: avgGain (2×1 + 0)/2 = 1, avgLoss (0.25×1 + 2)/2 = 1.125 → RS 0.8889 → RSI 47.059
    close(rsi([10, 12, 11, 14, 12], 2), [null, null, 200 / 3, 800 / 9, 100 - 100 / (1 + 1 / 1.125)], 4);
  });

  it('stays within 0–100', () => {
    const noisy = [10, 40, 5, 60, 3, 90, 1, 50, 49, 48, 100];
    for (const v of rsi(noisy, 5)) {
      if (v == null) continue;
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThanOrEqual(100);
    }
  });

  it('is all null with too little history', () => {
    close(rsi([1, 2, 3], 3), [null, null, null]);
  });
});

describe('macd', () => {
  it('line = EMA(fast) − EMA(slow), signal = EMA of the line, histogram = their gap', () => {
    const values = [10, 11, 13, 12, 15, 17, 16, 18];
    const m = macd(values, 2, 4, 2);
    const fast = ema(values, 2);
    const slow = ema(values, 4);
    // line defined from index slow − 1 = 3
    expect(m.macd.slice(0, 3)).toEqual([null, null, null]);
    for (let i = 3; i < values.length; i++) {
      expect(m.macd[i]).toBeCloseTo((fast[i] as number) - (slow[i] as number), 9);
    }
    // signal defined signal − 1 = 1 index later
    expect(m.signal.slice(0, 4)).toEqual([null, null, null, null]);
    const expectedSignal = ema(m.macd.slice(3) as number[], 2);
    expectedSignal.forEach((v, i) => {
      if (v == null) expect(m.signal[3 + i]).toBeNull();
      else expect(m.signal[3 + i]).toBeCloseTo(v, 9);
    });
    for (let i = 0; i < values.length; i++) {
      const l = m.macd[i];
      const s = m.signal[i];
      if (l == null || s == null) expect(m.histogram[i]).toBeNull();
      else expect(m.histogram[i]).toBeCloseTo(l - s, 9);
    }
  });

  it('is all null with too little history, and has the input length otherwise', () => {
    const short = macd([1, 2, 3], 2, 5, 2);
    expect(short.macd).toEqual([null, null, null]);
    expect(short.signal).toEqual([null, null, null]);
    expect(short.histogram).toEqual([null, null, null]);
    expect(macd([], 3, 5, 3).macd).toEqual([]);
  });

  it('is zero on a flat series', () => {
    const m = macd([8, 8, 8, 8, 8, 8], 2, 3, 2);
    expect(m.histogram.at(-1)).toBeCloseTo(0, 12);
  });
});

describe('dailyChange', () => {
  it('is the day-over-day rate and null on the first day', () => {
    close(dailyChange([100, 110, 99]), [null, 0.1, -0.1]);
  });

  it('is null when the previous price is zero', () => {
    close(dailyChange([0, 5]), [null, null]);
  });
});

describe('lastValue', () => {
  it('skips trailing nulls and handles empty input', () => {
    expect(lastValue([1, 2, null])).toBe(2);
    expect(lastValue([null, null])).toBeNull();
    expect(lastValue([])).toBeNull();
  });
});

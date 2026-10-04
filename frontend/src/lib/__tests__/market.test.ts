import { describe, expect, it } from 'vitest';
import type { EventInfo } from '../../api/types';
import { dayStripWindow, describeMarket, UNLIMITED_STRIP_DAYS } from '../market';

const days = Array.from({ length: 11 }, (_, i) => `2026-10-${String(6 + i).padStart(2, '0')}`);

function event(
  overrides: Partial<Omit<EventInfo, 'market'>> & { market?: Partial<EventInfo['market']> } = {},
): EventInfo {
  const { market, ...rest } = overrides;
  return {
    start: '2026-10-06',
    end: '2026-10-16',
    operating_days: days,
    total_rounds: 10,
    now: '2026-10-08T10:00:00+09:00',
    today: '2026-10-08',
    is_operating_day: true,
    certification: { cutoff: '23:59', target_date: '2026-10-08', reward_cash: 250000 },
    coin: { cap: 2, floor: -0.4, calm_rounds: 3, calm_until: '2026-10-09', calm_cap: 0.3, calm_floor: -0.1 },
    initial_cash: 1000000,
    daily_buy_limit_ratio: 0.4,
    clock: null,
    signup: { email_verification: false, verified_only_trading: false },
    ...rest,
    market: {
      is_open: true,
      opens_at: '09:00',
      closes_at: '18:00',
      day_opened: true,
      day_settled: false,
      round: 3,
      ...market,
    },
  };
}

describe('describeMarket', () => {
  it('open market mentions close time and round', () => {
    const s = describeMarket(event());
    expect(s.phase).toBe('open');
    expect(s.canTrade).toBe(true);
    expect(s.dayNumber).toBe(3);
    expect(s.detail).toContain('18:00');
    expect(s.detail).toContain('3회차');
  });

  it('pre-open, settling and settled phases', () => {
    expect(describeMarket(event({ market: { is_open: false, day_opened: false } })).phase).toBe('pre_open');
    expect(describeMarket(event({ market: { is_open: false } })).phase).toBe('settling');
    expect(describeMarket(event({ market: { is_open: false, day_settled: true } })).phase).toBe('settled');
  });

  it('before and after the event', () => {
    expect(describeMarket(event({ today: '2026-10-01', is_operating_day: false })).phase).toBe('before_event');
    expect(describeMarket(event({ today: '2026-10-20', is_operating_day: false })).phase).toBe('after_event');
  });

  it('last day has no round', () => {
    const s = describeMarket(event({ today: '2026-10-16', market: { round: null } }));
    expect(s.dayNumber).toBe(11);
    expect(s.detail).toContain('마지막 운영일');
  });
});

describe('QA unlimited mode', () => {
  const longDays = Array.from({ length: 40 }, (_, i) => {
    const d = new Date(Date.UTC(2026, 9, 6 + i));
    return d.toISOString().slice(0, 10);
  });
  const unlimited = event({
    end: null,
    total_rounds: null,
    operating_days: longDays,
    today: '2026-11-14',
    market: { round: 40 },
  });

  it('never reaches the end or the last day', () => {
    const s = describeMarket(unlimited);
    expect(s.phase).toBe('open');
    expect(s.dayNumber).toBe(40);
    expect(s.detail).not.toContain('마지막');
  });

  it('day strip shows only the latest days, numbered from the start', () => {
    const w = dayStripWindow(unlimited);
    expect(w.days).toHaveLength(UNLIMITED_STRIP_DAYS);
    expect(w.days.at(-1)).toBe('2026-11-14');
    expect(w.dayOffset).toBe(40 - UNLIMITED_STRIP_DAYS);
    expect(w.openEnded).toBe(true);
  });

  it('bounded events keep every day', () => {
    expect(dayStripWindow(event())).toEqual({ days, dayOffset: 0, openEnded: false });
  });
});

import { describe, expect, it } from 'vitest';
import type { EventInfo } from '../../api/types';
import { describeMarket } from '../market';

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
    certification: { cutoff: '23:59', target_date: '2026-10-08', reward_coin_quantity: 1 },
    initial_cash: 1000000,
    daily_buy_limit_ratio: 0.4,
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

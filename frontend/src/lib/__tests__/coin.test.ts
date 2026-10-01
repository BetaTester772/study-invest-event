import { describe, expect, it } from 'vitest';
import type { CoinInfo } from '../../api/types';
import { calmAhead, coinBoardNote, describeCoinRange, formatRange } from '../coin';

const coin: CoinInfo = {
  cap: 3,
  floor: -0.5,
  calm_rounds: 3,
  calm_until: '2026-10-09',
  calm_cap: 0.3,
  calm_floor: -0.1,
};

describe('formatRange', () => {
  it('formats signed whole percents', () => {
    expect(formatRange(-0.5, 3)).toBe('-50%~+300%');
    expect(formatRange(-0.1, 0.3)).toBe('-10%~+30%');
  });
});

describe('calm period copy', () => {
  it('is ahead until the day whose price takes the last calm round', () => {
    expect(calmAhead(coin, '2026-10-01')).toBe(true); // before the event
    expect(calmAhead(coin, '2026-10-08')).toBe(true); // 10/8 settlement = round 3, still calm
    expect(calmAhead(coin, '2026-10-09')).toBe(false); // 10/9 settlement = round 4
    expect(calmAhead({ ...coin, calm_rounds: 0, calm_until: null }, '2026-10-06')).toBe(false);
  });

  it('mentions the calm range only while it is ahead', () => {
    expect(describeCoinRange(coin, '2026-10-06')).toBe(
      '병더리움은 매수와 상관없이 매일 확률로 정해져요(하루 -50%~+300%). 초반 3번, 10월 9일 시작가까지는 -10%~+30% 안에서만 움직여요.',
    );
    expect(describeCoinRange(coin, '2026-10-10')).toBe(
      '병더리움은 매수와 상관없이 매일 확률로 정해져요(하루 -50%~+300%).',
    );
    expect(coinBoardNote(coin, '2026-10-06')).toContain('10월 9일 시작가까지는 변동폭이 좁아요');
    expect(coinBoardNote(coin, '2026-10-12')).toBe('매일 확률로 크게 오르거나 내려요.');
  });
});

import type { CoinInfo } from '../api/types';
import { formatDay, formatPercent } from './format';

/** `(-0.1, 0.3)` → `-10%~+30%` */
export function formatRange(floor: number, cap: number): string {
  const pct = (v: number) => formatPercent(v, { digits: 0, sign: true });
  return `${pct(floor)}~${pct(cap)}`;
}

/**
 * Is the next coin move still in the early calm period? The settlement on `today`
 * sets the next day's price, so it is calm while `today` is before `calm_until`.
 */
export function calmAhead(coin: CoinInfo, today: string): boolean {
  return coin.calm_until != null && today < coin.calm_until;
}

/** Short note for the quote board row. */
export function coinBoardNote(coin: CoinInfo, today: string): string {
  if (!calmAhead(coin, today)) return '매일 확률로 크게 오르거나 내려요.';
  return `매일 확률로 오르거나 내려요. ${formatDay(coin.calm_until, { weekday: false })} 시작가까지는 변동폭이 좁아요.`;
}

/** Full rule sentence(s) with the daily ranges. */
export function describeCoinRange(coin: CoinInfo, today: string): string {
  const rule = `병더리움은 매수와 상관없이 매일 확률로 정해져요(하루 ${formatRange(coin.floor, coin.cap)}).`;
  if (!calmAhead(coin, today)) return rule;
  return `${rule} 초반 ${coin.calm_rounds}번, ${formatDay(coin.calm_until, { weekday: false })} 시작가까지는 ${formatRange(coin.calm_floor, coin.calm_cap)} 안에서만 움직여요.`;
}

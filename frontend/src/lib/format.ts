/**
 * Shared formatters. All money is integer KRW; all rates are decimals
 * (e.g. -0.3 = -30%). Locale is fixed to ko-KR.
 */

export type Direction = 'up' | 'down' | 'flat';

const integerFormatter = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 });

const decimalFormatters = new Map<number, Intl.NumberFormat>();
function decimalFormatter(digits: number): Intl.NumberFormat {
  let f = decimalFormatters.get(digits);
  if (!f) {
    f = new Intl.NumberFormat('ko-KR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
    decimalFormatters.set(digits, f);
  }
  return f;
}

/** Sign of a value; values within `epsilon` of 0 are flat. */
export function direction(value: number | null | undefined, epsilon = 1e-9): Direction {
  if (value == null || Number.isNaN(value)) return 'flat';
  if (value > epsilon) return 'up';
  if (value < -epsilon) return 'down';
  return 'flat';
}

/** `1234500` → `1,234,500` */
export function formatNumber(value: number, digits = 0): string {
  if (digits === 0) return integerFormatter.format(Math.round(value));
  return decimalFormatter(digits).format(value);
}

export interface WonOptions {
  /** Always show a leading `+` for positive numbers. */
  sign?: boolean;
}

/** `1234500` → `1,234,500원`, with `sign` → `+1,234,500원`. Negative values use `-`. */
export function formatWon(value: number, { sign = false }: WonOptions = {}): string {
  const rounded = Math.round(value);
  const abs = integerFormatter.format(Math.abs(rounded));
  const prefix = rounded < 0 ? '-' : sign && rounded > 0 ? '+' : '';
  return `${prefix}${abs}원`;
}

export interface PercentOptions {
  digits?: number;
  sign?: boolean;
}

/** Decimal rate → percent string. `0.12` → `12.00%`, with sign → `+12.00%`. */
export function formatPercent(rate: number, { digits = 2, sign = false }: PercentOptions = {}): string {
  const pct = rate * 100;
  const fixed = Number(pct.toFixed(digits));
  const abs = decimalFormatter(digits).format(Math.abs(fixed));
  const prefix = fixed < 0 ? '-' : sign && fixed > 0 ? '+' : '';
  return `${prefix}${abs}%`;
}

export const ARROW: Record<Direction, string> = { up: '▲', down: '▼', flat: '' };

/**
 * Korean-market style change label: `▲ 12.00%`, `▼ 3.50%`, flat → `0.00%`.
 * `null` → `—` (no previous price).
 */
export function formatChange(rate: number | null | undefined, digits = 2): string {
  if (rate == null || Number.isNaN(rate)) return '—';
  const rounded = Number((rate * 100).toFixed(digits));
  const dir = direction(rounded);
  const abs = decimalFormatter(digits).format(Math.abs(rounded));
  return dir === 'flat' ? `${abs}%` : `${ARROW[dir]} ${abs}%`;
}

/** Quantity with unit: stock → 주, coin → 개. */
export function formatQuantity(quantity: number, kind: 'stock' | 'coin' = 'stock'): string {
  return `${integerFormatter.format(quantity)}${kind === 'coin' ? '개' : '주'}`;
}

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

/** `2026-10-06` → `10월 6일 (화)`. Pure string math — no timezone drift. */
export function formatDay(day: string | null | undefined, { weekday = true } = {}): string {
  if (!day) return '—';
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day);
  if (!m) return day;
  const [, y, mo, d] = m;
  const base = `${Number(mo)}월 ${Number(d)}일`;
  if (!weekday) return base;
  const wd = new Date(Date.UTC(Number(y), Number(mo) - 1, Number(d))).getUTCDay();
  return `${base} (${WEEKDAYS[wd]})`;
}

/** `2026-10-06` → `10.06` (compact, for chart axes). */
export function formatDayShort(day: string): string {
  const m = /^\d{4}-(\d{2})-(\d{2})$/.exec(day);
  return m ? `${m[1]}.${m[2]}` : day;
}

const dateTimeFormatter = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  month: 'numeric',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

/** ISO 8601 → `10/6 09:00` in KST. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const parts = Object.fromEntries(dateTimeFormatter.formatToParts(d).map((p) => [p.type, p.value]));
  const hour = parts.hour === '24' ? '00' : parts.hour;
  return `${parts.month}/${parts.day} ${hour}:${parts.minute}`;
}

/** Bytes → `1.2MB` */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

/** Pick the right Korean object particle: 을 after a final consonant, 를 otherwise. */
export function withObjectParticle(word: string): string {
  const last = word.charCodeAt(word.length - 1);
  if (last < 0xac00 || last > 0xd7a3) return `${word}를`;
  return (last - 0xac00) % 28 === 0 ? `${word}를` : `${word}을`;
}

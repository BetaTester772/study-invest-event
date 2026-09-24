import type { HTMLAttributes } from 'react';
import { cx } from '../../../lib/cx';
import { direction, formatChange, formatPercent, formatWon } from '../../../lib/format';
import styles from './Money.module.css';

interface NumberDisplayProps extends Omit<HTMLAttributes<HTMLSpanElement>, 'children'> {
  /** Color by sign using market colors (up red / down blue). */
  colorize?: boolean;
  /** Display face at a large size (prices). */
  display?: 'sm' | 'md' | 'lg' | 'xl';
}

function toneClass(value: number | null | undefined, colorize?: boolean) {
  return colorize ? styles[direction(value)] : undefined;
}

export interface MoneyProps extends NumberDisplayProps {
  /** Integer won. */
  value: number;
  /** Always show `+` for positive values. */
  sign?: boolean;
}

/** `1,234,500원` */
export function Money({ value, sign, colorize, display, className, ...rest }: MoneyProps) {
  return (
    <span
      className={cx(styles.number, toneClass(value, colorize), display && styles[`display-${display}`], className)}
      {...rest}
    >
      {formatWon(value, { sign })}
    </span>
  );
}

export interface PercentProps extends NumberDisplayProps {
  /** Decimal rate, e.g. 0.12 = 12%. */
  value: number | null | undefined;
  digits?: number;
  sign?: boolean;
}

/** `+12.00%` (decimal rate in, percent out). */
export function Percent({ value, digits = 2, sign, colorize, display, className, ...rest }: PercentProps) {
  return (
    <span
      className={cx(styles.number, toneClass(value, colorize), display && styles[`display-${display}`], className)}
      {...rest}
    >
      {value == null ? '—' : formatPercent(value, { digits, sign })}
    </span>
  );
}

export interface PriceChangeProps extends Omit<NumberDisplayProps, 'colorize'> {
  /** Decimal change rate; `null` when there is no previous price. */
  rate: number | null | undefined;
  digits?: number;
  /** Render as a tinted pill. */
  pill?: boolean;
}

const DIR_LABEL = { up: '상승', down: '하락', flat: '보합' } as const;

/** Korean-market change: `▲ 12.00%` in red, `▼ 3.00%` in blue, flat in gray. */
export function PriceChange({ rate, digits = 2, pill, display, className, ...rest }: PriceChangeProps) {
  const rounded = rate == null ? null : Number((rate * 100).toFixed(digits));
  const dir = direction(rounded);
  const text = formatChange(rate, digits);
  const aria = rate == null ? '변동 없음' : `${DIR_LABEL[dir]} ${text.replace(/[▲▼]\s?/, '')}`;
  return (
    <span
      className={cx(
        styles.number,
        styles[dir],
        pill && styles.pill,
        display && styles[`display-${display}`],
        className,
      )}
      data-direction={dir}
      aria-label={aria}
      {...rest}
    >
      <span aria-hidden="true">{text}</span>
    </span>
  );
}

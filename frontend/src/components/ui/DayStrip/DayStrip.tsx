import type { CSSProperties } from 'react';
import { cx } from '../../../lib/cx';
import { formatDay } from '../../../lib/format';
import styles from './DayStrip.module.css';

export interface DayStripProps {
  /** Operating days in order (YYYY-MM-DD). */
  days: string[];
  /** Today (YYYY-MM-DD). */
  today: string;
  /** Days that get a study stamp (e.g. approved certifications). */
  stamped?: string[];
  /** Accessible name. */
  label?: string;
  className?: string;
}

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

function weekday(day: string): string {
  const [y, m, d] = day.split('-').map(Number);
  return WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
}

/**
 * The event as a study-planner row: one cell per operating day. Past days are inked,
 * today is highlighted, stamped days carry an ink stamp. Cell numbers are real dates.
 */
export function DayStrip({ days, today, stamped = [], label = '이벤트 일정', className }: DayStripProps) {
  const stampSet = new Set(stamped);
  return (
    <ol className={cx(styles.strip, className)} aria-label={label} style={{ '--days': days.length } as CSSProperties}>
      {days.map((day, i) => {
        const state = day < today ? 'past' : day === today ? 'today' : 'future';
        const isStamped = stampSet.has(day);
        const round = i < days.length - 1 ? i + 1 : null;
        const parts = [
          formatDay(day),
          state === 'today' ? '오늘' : state === 'past' ? '지난 날' : null,
          round ? `${round}회차 정산` : '마지막 날',
          isStamped ? '공부 인증 완료' : null,
        ].filter(Boolean);
        return (
          <li
            key={day}
            className={cx(styles.cell, styles[state], isStamped && styles.stamped)}
            aria-current={state === 'today' ? 'date' : undefined}
            aria-label={parts.join(', ')}
            title={parts.join(', ')}
          >
            <span className={styles.weekday} aria-hidden="true">
              {weekday(day)}
            </span>
            <span className={styles.date} aria-hidden="true">
              {Number(day.slice(8, 10))}
            </span>
            {isStamped && (
              <span className={styles.stamp} aria-hidden="true">
                인증
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

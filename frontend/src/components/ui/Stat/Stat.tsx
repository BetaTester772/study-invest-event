import type { ReactNode } from 'react';
import { cx } from '../../../lib/cx';
import styles from './Stat.module.css';

export interface StatProps {
  label: ReactNode;
  value: ReactNode;
  /** Secondary line: delta, explanation. */
  sub?: ReactNode;
  /** Make this the lead figure (larger, display face). */
  emphasis?: boolean;
  className?: string;
}

/** KPI tile: label on top, figure, then a supporting line. */
export function Stat({ label, value, sub, emphasis, className }: StatProps) {
  return (
    <div className={cx(styles.stat, emphasis && styles.emphasis, className)}>
      <dt className={styles.label}>{label}</dt>
      <dd className={styles.value}>{value}</dd>
      {sub != null && <dd className={styles.sub}>{sub}</dd>}
    </div>
  );
}

/** Wraps Stat tiles in a responsive definition list. */
export function StatGroup({ children, className }: { children: ReactNode; className?: string }) {
  return <dl className={cx(styles.group, className)}>{children}</dl>;
}

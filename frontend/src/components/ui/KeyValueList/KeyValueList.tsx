import type { ReactNode } from 'react';
import { cx } from '../../../lib/cx';
import styles from './KeyValueList.module.css';

export interface KeyValueItem {
  label: ReactNode;
  value: ReactNode;
  /** Visually emphasize (e.g. the order total). */
  strong?: boolean;
}

/** Label/value rows with right-aligned numeric values. */
export function KeyValueList({ items, className }: { items: KeyValueItem[]; className?: string }) {
  return (
    <dl className={cx(styles.list, className)}>
      {items.map((it, i) => (
        <div key={i} className={cx(styles.row, it.strong && styles.strong)}>
          <dt className={styles.label}>{it.label}</dt>
          <dd className={styles.value}>{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}

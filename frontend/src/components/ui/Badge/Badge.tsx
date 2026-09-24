import type { HTMLAttributes } from 'react';
import { cx } from '../../../lib/cx';
import styles from './Badge.module.css';

export type BadgeTone = 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'up' | 'down' | 'highlight';

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  /** Leading status dot. */
  dot?: boolean;
  size?: 'sm' | 'md';
}

export function Badge({ tone = 'neutral', dot, size = 'md', className, children, ...rest }: BadgeProps) {
  return (
    <span className={cx(styles.badge, styles[tone], styles[size], className)} {...rest}>
      {dot && <span className={styles.dot} aria-hidden="true" />}
      {children}
    </span>
  );
}

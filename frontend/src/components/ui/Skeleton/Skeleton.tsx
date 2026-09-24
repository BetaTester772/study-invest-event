import type { CSSProperties } from 'react';
import { cx } from '../../../lib/cx';
import styles from './Skeleton.module.css';

export interface SkeletonProps {
  width?: string;
  height?: string;
  /** Render N stacked text lines (last one shorter). */
  lines?: number;
  circle?: boolean;
  className?: string;
}

/** Loading placeholder. Hidden from assistive tech — pair with a status message where needed. */
export function Skeleton({ width = '100%', height = '1rem', lines, circle, className }: SkeletonProps) {
  if (lines && lines > 1) {
    return (
      <span className={styles.lines} aria-hidden="true">
        {Array.from({ length: lines }, (_, i) => (
          <span
            key={i}
            className={cx(styles.skeleton, className)}
            style={{ width: i === lines - 1 ? '60%' : width, height }}
          />
        ))}
      </span>
    );
  }
  const style: CSSProperties = { width, height: circle ? width : height };
  return <span className={cx(styles.skeleton, circle && styles.circle, className)} style={style} aria-hidden="true" />;
}

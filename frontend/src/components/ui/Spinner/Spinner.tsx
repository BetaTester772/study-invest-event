import { cx } from '../../../lib/cx';
import styles from './Spinner.module.css';

export interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  /** Screen-reader text. Pass `null` when a parent already announces the busy state. */
  label?: string | null;
  className?: string;
}

export function Spinner({ size = 'md', label = '불러오는 중', className }: SpinnerProps) {
  return (
    <span className={cx(styles.wrap, className)} role={label ? 'status' : undefined}>
      <span className={cx(styles.spinner, styles[size])} aria-hidden="true" />
      {label && <span className="sr-only">{label}</span>}
    </span>
  );
}

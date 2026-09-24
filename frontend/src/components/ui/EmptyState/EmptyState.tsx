import type { ReactNode } from 'react';
import { cx } from '../../../lib/cx';
import styles from './EmptyState.module.css';

export interface EmptyStateProps {
  title: ReactNode;
  description?: ReactNode;
  /** The next thing to do — empty screens invite action. */
  action?: ReactNode;
  icon?: ReactNode;
  compact?: boolean;
  className?: string;
}

export function EmptyState({ title, description, action, icon, compact, className }: EmptyStateProps) {
  return (
    <div className={cx(styles.empty, compact && styles.compact, className)}>
      {icon && <div className={styles.icon}>{icon}</div>}
      <p className={styles.title}>{title}</p>
      {description && <p className={styles.description}>{description}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}

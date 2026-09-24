import type { ReactNode } from 'react';
import { cx } from '../../../lib/cx';
import { Icon, type IconName } from '../Icon/Icon';
import styles from './Alert.module.css';

export type AlertTone = 'info' | 'success' | 'warning' | 'danger';

export interface AlertProps {
  tone?: AlertTone;
  title?: ReactNode;
  children?: ReactNode;
  /** Button or link on the right. */
  action?: ReactNode;
  className?: string;
}

const ICONS: Record<AlertTone, IconName> = { info: 'info', success: 'check', warning: 'alert', danger: 'alert' };

/** Inline message. `danger`/`warning` are announced assertively. */
export function Alert({ tone = 'info', title, children, action, className }: AlertProps) {
  const urgent = tone === 'danger' || tone === 'warning';
  return (
    <div className={cx(styles.alert, styles[tone], className)} role={urgent ? 'alert' : 'status'}>
      <Icon name={ICONS[tone]} className={styles.icon} />
      <div className={styles.content}>
        {title && <p className={styles.title}>{title}</p>}
        {children && <div className={styles.body}>{children}</div>}
      </div>
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}

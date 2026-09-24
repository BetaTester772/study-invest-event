import type { ReactNode } from 'react';
import styles from './PageHeader.module.css';

export interface PageHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  /** Small row above the title, e.g. a back link. */
  back?: ReactNode;
}

export function PageHeader({ title, description, actions, back }: PageHeaderProps) {
  return (
    <header className={styles.header}>
      {back && <div className={styles.back}>{back}</div>}
      <div className={styles.row}>
        <div className={styles.headings}>
          <h1 className={styles.title}>{title}</h1>
          {description && <div className={styles.description}>{description}</div>}
        </div>
        {actions && <div className={styles.actions}>{actions}</div>}
      </div>
    </header>
  );
}

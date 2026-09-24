import type { HTMLAttributes, ReactNode } from 'react';
import { cx } from '../../../lib/cx';
import styles from './Card.module.css';

export interface CardProps extends Omit<HTMLAttributes<HTMLElement>, 'title'> {
  /** Heading shown in the card header. */
  title?: ReactNode;
  /** Heading level for `title` (default h2). */
  titleAs?: 'h2' | 'h3' | 'h4';
  description?: ReactNode;
  /** Right side of the header (buttons, links, badges). */
  actions?: ReactNode;
  footer?: ReactNode;
  padding?: 'none' | 'sm' | 'md' | 'lg';
  /** `sunken` for secondary panels that sit inside a page section. */
  tone?: 'default' | 'sunken';
  as?: 'section' | 'div' | 'article' | 'aside';
}

/** A flat "sheet" surface with an optional header row and footer. */
export function Card({
  title,
  titleAs: Heading = 'h2',
  description,
  actions,
  footer,
  padding = 'md',
  tone = 'default',
  as: Tag = 'section',
  className,
  children,
  ...rest
}: CardProps) {
  const hasHeader = title != null || description != null || actions != null;
  return (
    <Tag className={cx(styles.card, styles[`pad-${padding}`], tone === 'sunken' && styles.sunken, className)} {...rest}>
      {hasHeader && (
        <header className={styles.header}>
          <div className={styles.headings}>
            {title != null && <Heading className={styles.title}>{title}</Heading>}
            {description != null && <p className={styles.description}>{description}</p>}
          </div>
          {actions != null && <div className={styles.actions}>{actions}</div>}
        </header>
      )}
      {children != null && <div className={styles.body}>{children}</div>}
      {footer != null && <footer className={styles.footer}>{footer}</footer>}
    </Tag>
  );
}

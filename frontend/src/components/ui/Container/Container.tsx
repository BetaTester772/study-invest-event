import type { HTMLAttributes } from 'react';
import { cx } from '../../../lib/cx';
import styles from './Container.module.css';

export interface ContainerProps extends HTMLAttributes<HTMLDivElement> {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  /** Add top spacing for pages without a PageHeader. */
  padTop?: boolean;
}

/** Centers content with a max width and responsive side gutters. */
export function Container({ size = 'lg', padTop, className, ...rest }: ContainerProps) {
  return <div className={cx(styles.container, styles[size], padTop && styles.padTop, className)} {...rest} />;
}

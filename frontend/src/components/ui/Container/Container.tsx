import type { HTMLAttributes } from 'react';
import { cx } from '../../../lib/cx';
import styles from './Container.module.css';

export interface ContainerProps extends HTMLAttributes<HTMLDivElement> {
  size?: 'sm' | 'md' | 'lg' | 'xl';
}

/** Centers content with a max width and responsive side gutters. */
export function Container({ size = 'lg', className, ...rest }: ContainerProps) {
  return <div className={cx(styles.container, styles[size], className)} {...rest} />;
}

import type { HTMLAttributes } from 'react';
import { cx } from '../../../lib/cx';
import styles from './Text.module.css';

export interface TextProps extends HTMLAttributes<HTMLElement> {
  as?: 'p' | 'span' | 'div' | 'strong' | 'small';
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl';
  tone?: 'default' | 'ink' | 'muted' | 'subtle' | 'up' | 'down' | 'danger' | 'success';
  weight?: 'regular' | 'medium' | 'semibold' | 'bold';
  /** Display face (Do Hyeon) for prices and big numbers. */
  display?: boolean;
  numeric?: boolean;
}

/** Body text with tone/size from tokens — use instead of ad-hoc styles in pages. */
export function Text({
  as: Tag = 'p',
  size = 'md',
  tone = 'default',
  weight,
  display,
  numeric,
  className,
  ...rest
}: TextProps) {
  return (
    <Tag
      className={cx(
        styles.text,
        styles[`size-${size}`],
        styles[`tone-${tone}`],
        weight && styles[`weight-${weight}`],
        display && styles.display,
        numeric && styles.numeric,
        className,
      )}
      {...rest}
    />
  );
}

/** Marks text with a highlighter swipe — reserved for "now / today / selected". */
export function Highlight({ className, ...rest }: HTMLAttributes<HTMLElement>) {
  return <mark className={cx(styles.highlight, className)} {...rest} />;
}

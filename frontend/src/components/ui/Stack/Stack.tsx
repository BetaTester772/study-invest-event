import type { CSSProperties, HTMLAttributes } from 'react';
import { cx } from '../../../lib/cx';
import styles from './Stack.module.css';

type Space = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12;

export interface StackProps extends HTMLAttributes<HTMLDivElement> {
  direction?: 'column' | 'row';
  gap?: Space;
  align?: 'start' | 'center' | 'end' | 'stretch' | 'baseline';
  justify?: 'start' | 'center' | 'end' | 'between';
  wrap?: boolean;
  as?: 'div' | 'section' | 'ul' | 'form';
}

const ALIGN = { start: 'flex-start', center: 'center', end: 'flex-end', stretch: 'stretch', baseline: 'baseline' };
const JUSTIFY = { start: 'flex-start', center: 'center', end: 'flex-end', between: 'space-between' };

/** Flex layout primitive. Pages compose with this instead of writing CSS. */
export function Stack({
  direction = 'column',
  gap = 4,
  align,
  justify,
  wrap,
  as: Tag = 'div',
  className,
  style,
  ...rest
}: StackProps) {
  const s: CSSProperties = {
    flexDirection: direction,
    gap: `var(--space-${gap})`,
    alignItems: align ? ALIGN[align] : undefined,
    justifyContent: justify ? JUSTIFY[justify] : undefined,
    flexWrap: wrap ? 'wrap' : undefined,
    ...style,
  };
  return <Tag className={cx(styles.stack, className)} style={s} {...(rest as HTMLAttributes<HTMLElement>)} />;
}

export interface GridProps extends HTMLAttributes<HTMLDivElement> {
  /** Minimum column width; columns auto-fit. */
  min?: string;
  gap?: Space;
  /** Fixed "sidebar" layout: main + side column (side width), stacks under 860px. */
  sidebar?: string;
  /** With `sidebar`: when stacked on small screens, show the side column first. */
  sideFirstOnMobile?: boolean;
}

export function Grid({ min = '16rem', gap = 4, sidebar, sideFirstOnMobile, className, style, ...rest }: GridProps) {
  const s = {
    '--grid-min': min,
    '--grid-gap': `var(--space-${gap})`,
    '--grid-side': sidebar,
    ...style,
  } as CSSProperties;
  return <div
      className={cx(sidebar ? styles.sidebar : styles.grid, sidebar && sideFirstOnMobile && styles.sideFirst, className)}
      style={s}
      {...rest}
    />;
}

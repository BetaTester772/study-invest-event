import type { ReactNode } from 'react';
import { cx } from '../../../lib/cx';
import { Skeleton } from '../Skeleton/Skeleton';
import styles from './Table.module.css';

export interface Column<T> {
  key: string;
  header: ReactNode;
  /** Cell renderer; defaults to `row[key]`. */
  render?: (row: T, index: number) => ReactNode;
  align?: 'left' | 'center' | 'right';
  /** Numeric column: right-aligned with tabular numerals. */
  numeric?: boolean;
  width?: string;
  /** Hide this column below 640px. */
  hideOnMobile?: boolean;
  /** Keep the cell on one line (dates, times, short labels). */
  nowrap?: boolean;
}

export interface TableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string | number;
  /** Shown instead of rows when `rows` is empty. */
  empty?: ReactNode;
  /** Visible or screen-reader caption describing the table. */
  caption?: ReactNode;
  hideCaption?: boolean;
  /** Emphasize a row (e.g. "my" ranking row). */
  isRowHighlighted?: (row: T) => boolean;
  loading?: boolean;
  dense?: boolean;
  className?: string;
}

/** Typed data table. Scrolls horizontally inside its own box, never the page. */
export function Table<T>({
  columns,
  rows,
  rowKey,
  empty = '표시할 내용이 없어요.',
  caption,
  hideCaption = true,
  isRowHighlighted,
  loading,
  dense,
  className,
}: TableProps<T>) {
  const alignOf = (c: Column<T>) => c.align ?? (c.numeric ? 'right' : 'left');
  const colClass = (c: Column<T>) =>
    cx(
      styles[`align-${alignOf(c)}`],
      c.numeric && styles.numeric,
      c.nowrap && styles.nowrap,
      c.hideOnMobile && styles.hideOnMobile,
    );

  return (
    <div
      className={cx(styles.scroller, className)}
      tabIndex={0}
      role="region"
      aria-label={typeof caption === 'string' ? caption : undefined}
    >
      <table className={cx(styles.table, dense && styles.dense)} aria-busy={loading || undefined}>
        {caption && <caption className={hideCaption ? 'sr-only' : styles.caption}>{caption}</caption>}
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className={colClass(c)} style={c.width ? { width: c.width } : undefined}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading && rows.length === 0 ? (
            Array.from({ length: 3 }, (_, i) => (
              <tr key={`sk-${i}`}>
                {columns.map((c) => (
                  <td key={c.key} className={colClass(c)}>
                    <Skeleton height="1em" width={c.numeric ? '5em' : '70%'} />
                  </td>
                ))}
              </tr>
            ))
          ) : rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className={styles.empty}>
                {empty}
              </td>
            </tr>
          ) : (
            rows.map((row, i) => {
              const highlighted = isRowHighlighted?.(row) ?? false;
              return (
                <tr
                  key={rowKey(row, i)}
                  className={highlighted ? styles.highlighted : undefined}
                  aria-current={highlighted || undefined}
                >
                  {columns.map((c) => (
                    <td key={c.key} className={colClass(c)}>
                      {c.render ? c.render(row, i) : String((row as Record<string, unknown>)[c.key] ?? '')}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

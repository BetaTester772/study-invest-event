import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { cx } from '../../../lib/cx';
import styles from './Tabs.module.css';

export interface TabItem<V extends string = string> {
  value: V;
  label: ReactNode;
  content: ReactNode;
  /** Small count/badge after the label. */
  count?: number;
}

export interface TabsProps<V extends string = string> {
  items: TabItem<V>[];
  /** Controlled value. */
  value?: V;
  defaultValue?: V;
  onChange?: (value: V) => void;
  /** Accessible name for the tab list. */
  label: string;
  className?: string;
}

/** WAI-ARIA tabs with automatic activation and arrow/Home/End keys. */
export function Tabs<V extends string = string>({
  items,
  value: controlled,
  defaultValue,
  onChange,
  label,
  className,
}: TabsProps<V>) {
  const [internal, setInternal] = useState<V>(defaultValue ?? items[0]?.value);
  const value = controlled ?? internal;
  const baseId = useId();
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  const select = (v: V) => {
    if (controlled === undefined) setInternal(v);
    onChange?.(v);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const idx = items.findIndex((t) => t.value === value);
    let next = idx;
    if (e.key === 'ArrowRight') next = (idx + 1) % items.length;
    else if (e.key === 'ArrowLeft') next = (idx - 1 + items.length) % items.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = items.length - 1;
    else return;
    e.preventDefault();
    select(items[next].value);
    refs.current[next]?.focus();
  };

  const active = items.find((t) => t.value === value) ?? items[0];

  return (
    <div className={cx(styles.tabs, className)}>
      <div role="tablist" aria-label={label} className={styles.list} onKeyDown={onKeyDown}>
        {items.map((t, i) => {
          const selected = t.value === active?.value;
          return (
            <button
              key={t.value}
              ref={(el) => {
                refs.current[i] = el;
              }}
              type="button"
              role="tab"
              id={`${baseId}-tab-${t.value}`}
              aria-selected={selected}
              aria-controls={`${baseId}-panel-${t.value}`}
              tabIndex={selected ? 0 : -1}
              className={cx(styles.tab, selected && styles.selected)}
              onClick={() => select(t.value)}
            >
              <span className={styles.tabLabel}>{t.label}</span>
              {t.count != null && <span className={styles.count}>{t.count}</span>}
            </button>
          );
        })}
      </div>
      {active && (
        <div
          role="tabpanel"
          id={`${baseId}-panel-${active.value}`}
          aria-labelledby={`${baseId}-tab-${active.value}`}
          tabIndex={0}
          className={styles.panel}
        >
          {active.content}
        </div>
      )}
    </div>
  );
}

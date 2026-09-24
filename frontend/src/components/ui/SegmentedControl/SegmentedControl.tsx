import { useRef, type CSSProperties, type KeyboardEvent, type ReactNode } from 'react';
import { cx } from '../../../lib/cx';
import styles from './SegmentedControl.module.css';

export interface SegmentOption<V extends string> {
  value: V;
  label: ReactNode;
  /** Selected tint: `up` (red, e.g. 매수), `down` (blue, e.g. 매도) or neutral highlighter. */
  tone?: 'neutral' | 'up' | 'down';
  disabled?: boolean;
}

export interface SegmentedControlProps<V extends string> {
  options: SegmentOption<V>[];
  value: V;
  onChange: (value: V) => void;
  /** Accessible name of the group. */
  label: string;
  size?: 'md' | 'lg';
  fullWidth?: boolean;
  className?: string;
}

/** Single-choice toggle (radio group semantics, arrow-key navigation). */
export function SegmentedControl<V extends string>({
  options,
  value,
  onChange,
  label,
  size = 'md',
  fullWidth,
  className,
}: SegmentedControlProps<V>) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const enabled = options.filter((o) => !o.disabled);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const keys = ['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp', 'Home', 'End'];
    if (!keys.includes(e.key) || enabled.length === 0) return;
    e.preventDefault();
    const cur = enabled.findIndex((o) => o.value === value);
    let next = cur;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (cur + 1) % enabled.length;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (cur - 1 + enabled.length) % enabled.length;
    if (e.key === 'Home') next = 0;
    if (e.key === 'End') next = enabled.length - 1;
    const target = enabled[next];
    if (!target) return;
    onChange(target.value);
    refs.current[options.indexOf(target)]?.focus();
  };

  const selectedIndex = Math.max(
    0,
    options.findIndex((o) => o.value === value),
  );
  const selectedTone = options[selectedIndex]?.tone ?? 'neutral';

  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cx(styles.group, styles[size], fullWidth && styles.fullWidth, className)}
      style={{ '--seg-count': options.length, '--seg-index': selectedIndex } as CSSProperties}
      data-tone={selectedTone}
      onKeyDown={onKeyDown}
    >
      <span className={styles.thumb} aria-hidden="true" />
      {options.map((o, i) => {
        const selected = o.value === value;
        return (
          <button
            key={o.value}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            disabled={o.disabled}
            className={cx(styles.option, selected && styles.selected)}
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

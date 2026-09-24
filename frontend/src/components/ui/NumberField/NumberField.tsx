import { useEffect, useState, type KeyboardEvent, type ReactNode } from 'react';
import { cx } from '../../../lib/cx';
import { Field, fieldStyles, type FieldBaseProps } from '../TextField/Field';
import { Icon } from '../Icon/Icon';
import styles from './NumberField.module.css';

export interface NumberFieldProps extends FieldBaseProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  /** Unit shown inside the field, e.g. "주". */
  suffix?: string;
  disabled?: boolean;
  /** Extra control rendered after the stepper (e.g. a "최대" button). */
  trailing?: ReactNode;
  id?: string;
  name?: string;
}

export function clampInt(n: number, min: number, max: number): number {
  if (!Number.isFinite(n)) return min;
  const i = Math.trunc(n);
  if (max < min) return min;
  return Math.min(max, Math.max(min, i));
}

/**
 * Integer input with − / + steppers. Typing is free-form; the value is clamped
 * to [min, max] when the field loses focus or Enter is pressed. Arrow keys step.
 */
export function NumberField({
  value,
  onChange,
  min = 0,
  max = Number.MAX_SAFE_INTEGER,
  step = 1,
  suffix,
  disabled,
  trailing,
  label,
  hideLabel,
  hint,
  error,
  required,
  className,
  id,
  name,
}: NumberFieldProps) {
  const [draft, setDraft] = useState(String(value));

  useEffect(() => {
    setDraft(String(value));
  }, [value]);

  const commit = (raw: string) => {
    const parsed = raw.trim() === '' || raw === '-' ? min : Number(raw);
    const next = clampInt(parsed, min, max);
    setDraft(String(next));
    if (next !== value) onChange(next);
  };

  const stepBy = (delta: number) => {
    const next = clampInt(value + delta, min, max);
    setDraft(String(next));
    if (next !== value) onChange(next);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      stepBy(step);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      stepBy(-step);
    } else if (e.key === 'Enter') {
      commit(draft);
    }
  };

  const atMin = value <= min;
  const atMax = value >= max;

  return (
    <Field
      label={label}
      hideLabel={hideLabel}
      hint={hint}
      error={error}
      required={required}
      className={className}
      id={id}
    >
      {(ids) => (
        <div className={styles.row}>
          <div
            className={cx(
              fieldStyles.control,
              styles.shell,
              ids.invalid && fieldStyles.invalid,
              disabled && styles.disabled,
            )}
          >
            <button
              type="button"
              className={styles.step}
              onClick={() => stepBy(-step)}
              disabled={disabled || atMin}
              aria-label="수량 줄이기"
              tabIndex={-1}
            >
              <Icon name="minus" size={18} />
            </button>
            <input
              id={ids.id}
              name={name}
              className={styles.input}
              type="text"
              inputMode="numeric"
              autoComplete="off"
              role="spinbutton"
              aria-valuemin={min}
              aria-valuemax={max === Number.MAX_SAFE_INTEGER ? undefined : max}
              aria-valuenow={value}
              aria-invalid={ids.invalid || undefined}
              aria-describedby={ids.describedBy}
              disabled={disabled}
              value={draft}
              onChange={(e) => {
                const raw = e.target.value.replace(min < 0 ? /[^\d-]/g : /\D/g, '');
                setDraft(raw);
                const n = Number(raw);
                if (raw !== '' && raw !== '-' && Number.isInteger(n) && n >= min && n <= max) onChange(n);
              }}
              onBlur={() => commit(draft)}
              onKeyDown={onKeyDown}
            />
            {suffix && (
              <span className={styles.suffix} aria-hidden="true">
                {suffix}
              </span>
            )}
            <button
              type="button"
              className={styles.step}
              onClick={() => stepBy(step)}
              disabled={disabled || atMax}
              aria-label="수량 늘리기"
              tabIndex={-1}
            >
              <Icon name="plus" size={18} />
            </button>
          </div>
          {trailing}
        </div>
      )}
    </Field>
  );
}

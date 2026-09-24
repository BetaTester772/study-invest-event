import { useId, type ReactNode } from 'react';
import { cx } from '../../../lib/cx';
import styles from './Field.module.css';

export interface FieldBaseProps {
  label: ReactNode;
  /** Visually hide the label (still announced). */
  hideLabel?: boolean;
  hint?: ReactNode;
  /** Error message; marks the control aria-invalid. */
  error?: ReactNode;
  required?: boolean;
  className?: string;
}

export interface FieldIds {
  id: string;
  describedBy: string | undefined;
  invalid: boolean;
}

/** Label + control + hint/error wiring shared by all form controls. */
export function Field({
  label,
  hideLabel,
  hint,
  error,
  required,
  className,
  id: idProp,
  children,
}: FieldBaseProps & { id?: string; children: (ids: FieldIds) => ReactNode }) {
  const autoId = useId();
  const id = idProp ?? autoId;
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(' ') || undefined;
  return (
    <div className={cx(styles.field, className)}>
      <label htmlFor={id} className={cx(styles.label, hideLabel && 'sr-only')}>
        {label}
        {required && (
          <span className={styles.required} aria-hidden="true">
            *
          </span>
        )}
      </label>
      {children({ id, describedBy, invalid: Boolean(error) })}
      {error && (
        <p id={errorId} className={styles.error}>
          {error}
        </p>
      )}
      {hint && (
        <p id={hintId} className={styles.hint}>
          {hint}
        </p>
      )}
    </div>
  );
}

export const fieldStyles = styles;

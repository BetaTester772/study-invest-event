import type { SelectHTMLAttributes } from 'react';
import { Field, fieldStyles, type FieldBaseProps } from '../TextField/Field';
import { Icon } from '../Icon/Icon';
import styles from './Select.module.css';

export interface SelectOption<V extends string = string> {
  value: V;
  label: string;
  disabled?: boolean;
}

export interface SelectProps<V extends string = string>
  extends
    FieldBaseProps,
    Omit<SelectHTMLAttributes<HTMLSelectElement>, 'className' | 'required' | 'onChange' | 'value'> {
  options: SelectOption<V>[];
  value: V;
  onChange: (value: V) => void;
  placeholder?: string;
}

export function Select<V extends string = string>({
  label,
  hideLabel,
  hint,
  error,
  required,
  className,
  id,
  options,
  value,
  onChange,
  placeholder,
  ...rest
}: SelectProps<V>) {
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
        <div className={styles.wrap}>
          <select
            id={ids.id}
            required={required}
            aria-invalid={ids.invalid || undefined}
            aria-describedby={ids.describedBy}
            className={`${fieldStyles.control} ${styles.select}`}
            value={value}
            onChange={(e) => onChange(e.target.value as V)}
            {...rest}
          >
            {placeholder && (
              <option value="" disabled>
                {placeholder}
              </option>
            )}
            {options.map((o) => (
              <option key={o.value} value={o.value} disabled={o.disabled}>
                {o.label}
              </option>
            ))}
          </select>
          <Icon name="chevronDown" size={16} className={styles.chevron} />
        </div>
      )}
    </Field>
  );
}

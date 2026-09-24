import type { InputHTMLAttributes, TextareaHTMLAttributes } from 'react';
import { cx } from '../../../lib/cx';
import { Field, fieldStyles, type FieldBaseProps } from './Field';

export interface TextFieldProps
  extends FieldBaseProps,
    Omit<InputHTMLAttributes<HTMLInputElement>, 'className' | 'required'> {
  inputClassName?: string;
}

export function TextField({
  label,
  hideLabel,
  hint,
  error,
  required,
  className,
  inputClassName,
  id,
  type = 'text',
  ...rest
}: TextFieldProps) {
  return (
    <Field label={label} hideLabel={hideLabel} hint={hint} error={error} required={required} className={className} id={id}>
      {(ids) => (
        <input
          id={ids.id}
          type={type}
          required={required}
          aria-invalid={ids.invalid || undefined}
          aria-describedby={ids.describedBy}
          className={cx(fieldStyles.control, inputClassName)}
          {...rest}
        />
      )}
    </Field>
  );
}

export interface TextAreaProps
  extends FieldBaseProps,
    Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'className' | 'required'> {}

export function TextArea({ label, hideLabel, hint, error, required, className, id, ...rest }: TextAreaProps) {
  return (
    <Field label={label} hideLabel={hideLabel} hint={hint} error={error} required={required} className={className} id={id}>
      {(ids) => (
        <textarea
          id={ids.id}
          required={required}
          aria-invalid={ids.invalid || undefined}
          aria-describedby={ids.describedBy}
          className={fieldStyles.control}
          {...rest}
        />
      )}
    </Field>
  );
}

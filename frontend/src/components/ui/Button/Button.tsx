import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Link, type LinkProps } from 'react-router-dom';
import { cx } from '../../../lib/cx';
import { Spinner } from '../Spinner/Spinner';
import styles from './Button.module.css';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'buy' | 'sell';
export type ButtonSize = 'sm' | 'md' | 'lg';

interface CommonProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  /** Icon rendered before the label. */
  icon?: ReactNode;
}

export interface ButtonProps extends CommonProps, ButtonHTMLAttributes<HTMLButtonElement> {
  /** Shows a spinner, sets aria-busy and blocks clicks. */
  loading?: boolean;
}

export function buttonClassName({
  variant = 'primary',
  size = 'md',
  fullWidth,
  className,
}: CommonProps & { className?: string }) {
  return cx(styles.button, styles[variant], styles[size], fullWidth && styles.fullWidth, className);
}

export function Button({
  variant,
  size,
  fullWidth,
  loading = false,
  disabled,
  icon,
  type = 'button',
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={buttonClassName({ variant, size, fullWidth, className })}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      data-loading={loading || undefined}
      {...rest}
    >
      {loading ? <Spinner size="sm" label={null} className={styles.spinner} /> : icon}
      <span className={styles.label}>{children}</span>
    </button>
  );
}

export interface LinkButtonProps extends CommonProps, LinkProps {}

/** A router link that looks like a button. */
export function LinkButton({ variant, size, fullWidth, icon, className, children, ...rest }: LinkButtonProps) {
  return (
    <Link className={buttonClassName({ variant, size, fullWidth, className })} {...rest}>
      {icon}
      <span className={styles.label}>{children}</span>
    </Link>
  );
}

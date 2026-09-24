import { useEffect, useId, useRef, useState, type DragEvent, type ReactNode } from 'react';
import { cx } from '../../../lib/cx';
import { formatBytes } from '../../../lib/format';
import { Button } from '../Button/Button';
import { Icon } from '../Icon/Icon';
import styles from './FileDropzone.module.css';

export interface FileDropzoneProps {
  label: ReactNode;
  value: File | null;
  onChange: (file: File | null) => void;
  /** Same syntax as <input accept>, e.g. "image/jpeg,image/png,.heic". */
  accept?: string;
  /** Max size in bytes. */
  maxSize?: number;
  hint?: ReactNode;
  /** External error (e.g. from the server). */
  error?: ReactNode;
  disabled?: boolean;
  /** Main line inside the empty zone. */
  prompt?: ReactNode;
}

const EXT_BY_MIME: Record<string, string[]> = {
  'image/jpeg': ['jpg', 'jpeg'],
  'image/png': ['png'],
  'image/webp': ['webp'],
  'image/heic': ['heic', 'heif'],
  'image/heif': ['heif', 'heic'],
  'image/gif': ['gif'],
};

/** Does `file` satisfy an accept string? Falls back to extensions when the browser gives no MIME type (e.g. HEIC). */
export function matchesAccept(file: File, accept?: string): boolean {
  if (!accept) return true;
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  const type = file.type.toLowerCase();
  return accept
    .split(',')
    .map((t) => t.trim().toLowerCase())
    .filter(Boolean)
    .some((token) => {
      if (token.startsWith('.')) return token.slice(1) === ext;
      if (token.endsWith('/*')) return type.startsWith(token.slice(0, -1));
      return type === token || (EXT_BY_MIME[token]?.includes(ext) ?? false);
    });
}

/** Drag-and-drop or click-to-pick single image upload with preview and validation. */
export function FileDropzone({
  label,
  value,
  onChange,
  accept,
  maxSize,
  hint,
  error,
  disabled,
  prompt = '사진을 끌어다 놓거나 눌러서 고르세요',
}: FileDropzoneProps) {
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [previewFailed, setPreviewFailed] = useState(false);

  useEffect(() => {
    setPreviewFailed(false);
    if (!value || typeof URL.createObjectURL !== 'function') {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(value);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [value]);

  const pick = (file: File | undefined | null) => {
    if (!file) return;
    if (!matchesAccept(file, accept)) {
      setLocalError('이 형식은 올릴 수 없어요. JPG, PNG, WEBP, HEIC 사진을 골라 주세요.');
      return;
    }
    if (maxSize && file.size > maxSize) {
      setLocalError(`사진이 너무 커요(${formatBytes(file.size)}). ${formatBytes(maxSize)} 이하로 줄여서 올려 주세요.`);
      return;
    }
    setLocalError(null);
    onChange(file);
  };

  const onDrop = (e: DragEvent<HTMLElement>) => {
    e.preventDefault();
    setDragging(false);
    if (disabled) return;
    pick(e.dataTransfer.files?.[0]);
  };

  const shownError = localError ?? error;
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;

  return (
    <div className={styles.field}>
      <span className={styles.label} id={`${id}-label`}>
        {label}
      </span>
      <input
        ref={inputRef}
        id={id}
        type="file"
        className={cx('sr-only', styles.input)}
        accept={accept}
        disabled={disabled}
        aria-labelledby={`${id}-label`}
        aria-describedby={[shownError ? errorId : null, hint ? hintId : null].filter(Boolean).join(' ') || undefined}
        aria-invalid={shownError ? true : undefined}
        onChange={(e) => {
          pick(e.target.files?.[0]);
          e.target.value = '';
        }}
      />
      {value ? (
        <div className={styles.selected}>
          <div className={styles.thumb}>
            {preview && !previewFailed ? (
              <img src={preview} alt="고른 사진 미리보기" onError={() => setPreviewFailed(true)} />
            ) : (
              <Icon name="image" size={32} />
            )}
          </div>
          <div className={styles.meta}>
            <p className={styles.fileName}>{value.name}</p>
            <p className={styles.fileSize}>{formatBytes(value.size)}</p>
            <div className={styles.metaActions}>
              <Button size="sm" variant="secondary" onClick={() => inputRef.current?.click()} disabled={disabled}>
                다른 사진 고르기
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setLocalError(null);
                  onChange(null);
                }}
                disabled={disabled}
              >
                지우기
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <label
          htmlFor={id}
          className={cx(styles.zone, dragging && styles.dragging, disabled && styles.disabled, Boolean(shownError) && styles.invalid)}
          onDragEnter={(e) => {
            e.preventDefault();
            if (!disabled) setDragging(true);
          }}
          onDragOver={(e) => e.preventDefault()}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <Icon name="upload" size={28} className={styles.zoneIcon} />
          <span className={styles.prompt}>{prompt}</span>
          {maxSize && <span className={styles.limit}>최대 {formatBytes(maxSize)}</span>}
        </label>
      )}
      {shownError && (
        <p id={errorId} className={styles.error} role="alert">
          {shownError}
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

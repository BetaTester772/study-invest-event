import styles from './CodeBlock.module.css';

/** Raw JSON viewer for admin/debug detail blobs. */
export function CodeBlock({ value, maxHeight = '16rem' }: { value: unknown; maxHeight?: string }) {
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  return (
    <pre className={styles.pre} style={{ maxHeight }} tabIndex={0}>
      <code>{text}</code>
    </pre>
  );
}

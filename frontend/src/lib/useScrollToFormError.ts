import { useCallback, useEffect, useRef, useState } from 'react';

const ERROR_SELECTOR = '[aria-invalid="true"], [role="alert"]';

/**
 * Scrolls the first error in a form (an invalid control or a danger alert) into view
 * whenever `errors` changes. Attach the returned ref to the `<form>`.
 * Call the returned `scrollToError` when the same error can be raised again with
 * unchanged state (e.g. repeating the same client-side validation message).
 */
export function useScrollToFormError(...errors: unknown[]) {
  const ref = useRef<HTMLFormElement>(null);
  const [tick, setTick] = useState(0);
  const scrollToError = useCallback(() => setTick((n) => n + 1), []);
  useEffect(() => {
    const target = ref.current?.querySelector<HTMLElement>(ERROR_SELECTOR);
    if (!target || typeof target.scrollIntoView !== 'function') return;
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    target.scrollIntoView({ block: 'center', behavior: reduceMotion ? 'auto' : 'smooth' });
    if (target.getAttribute('aria-invalid') === 'true') target.focus({ preventScroll: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...errors, tick]);
  return [ref, scrollToError] as const;
}

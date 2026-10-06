import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { Text } from '../components/ui';

/** Cloudflare Turnstile(봇 확인). 서버가 사이트 키(`signup.turnstile_site_key`)를 줄 때만 켠다. */

const SCRIPT_URL = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
/** 토큰이 아직 없을 때(확인 중·사용자 상호작용 대기) 기다리는 최대 시간. 넘으면 토큰 없이 보낸다. */
const TOKEN_WAIT_MS = 30_000;

interface TurnstileOptions {
  sitekey: string;
  action: string;
  appearance?: 'always' | 'execute' | 'interaction-only';
  size?: 'normal' | 'flexible' | 'compact';
  language?: string;
  callback?: (token: string) => void;
  'expired-callback'?: () => void;
  'error-callback'?: (code: string) => void;
}

interface TurnstileApi {
  render: (container: HTMLElement, options: TurnstileOptions) => string | undefined;
  reset: (widgetId: string) => void;
  remove: (widgetId: string) => void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

let loading: Promise<TurnstileApi> | null = null;

function loadTurnstile(): Promise<TurnstileApi> {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  loading ??= new Promise<TurnstileApi>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = SCRIPT_URL;
    script.async = true;
    script.onload = () => (window.turnstile ? resolve(window.turnstile) : reject(new Error('turnstile missing')));
    script.onerror = () => {
      script.remove();
      loading = null; // 다음 화면에서 다시 시도한다
      reject(new Error('turnstile load failed'));
    };
    document.head.appendChild(script);
  });
  return loading;
}

export interface Turnstile {
  /** 폼 안(제출 버튼 위)에 둔다. 확인이 필요할 때만 보인다. 꺼져 있으면 null. */
  widget: ReactNode;
  /**
   * 요청에 실을 토큰을 꺼낸다. 토큰은 한 번만 쓸 수 있으므로 꺼내면 곧바로 새 토큰을 받기 시작한다.
   * 꺼져 있거나 위젯을 불러오지 못했으면 undefined(서버가 거절하면 그 안내를 보여 준다).
   */
  take: () => Promise<string | undefined>;
}

/** siteKey: `signup.turnstile_site_key`. action: 서버 라우트가 기대하는 값(login·register·password_reset). */
export function useTurnstile(siteKey: string | null | undefined, action: string): Turnstile {
  // 콜백 ref: 위젯 자리가 사라졌다 다시 생기면(단계 전환 등) 새 자리에 다시 그린다.
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const widgetId = useRef<string | null>(null);
  const token = useRef<string | null>(null);
  const failed = useRef(false);
  const waiters = useRef<Array<(t: string | null) => void>>([]);
  const [loadError, setLoadError] = useState(false);

  const settle = (value: string | null) => {
    const pending = waiters.current;
    waiters.current = [];
    pending.forEach((resolve) => resolve(value));
  };

  useEffect(() => {
    if (!siteKey || !container) return;
    let cancelled = false;
    failed.current = false;
    setLoadError(false);
    loadTurnstile()
      .then((api) => {
        if (cancelled) return;
        widgetId.current =
          api.render(container, {
            sitekey: siteKey,
            action,
            appearance: 'interaction-only',
            size: 'flexible',
            language: 'ko',
            callback: (t) => {
              token.current = t;
              settle(t);
            },
            'expired-callback': () => {
              token.current = null;
            },
          }) ?? null;
      })
      .catch(() => {
        if (cancelled) return;
        failed.current = true;
        setLoadError(true);
        settle(null);
      });
    return () => {
      cancelled = true;
      if (widgetId.current) window.turnstile?.remove(widgetId.current);
      widgetId.current = null;
      token.current = null;
      settle(null);
    };
  }, [siteKey, action, container]);

  const take = useCallback(async (): Promise<string | undefined> => {
    if (!siteKey || failed.current) return undefined;
    let value = token.current;
    if (!value) {
      value = await new Promise<string | null>((resolve) => {
        const timer = window.setTimeout(() => {
          waiters.current = waiters.current.filter((w) => w !== done);
          resolve(null);
        }, TOKEN_WAIT_MS);
        const done = (t: string | null) => {
          window.clearTimeout(timer);
          resolve(t);
        };
        waiters.current.push(done);
      });
    }
    token.current = null;
    if (widgetId.current) window.turnstile?.reset(widgetId.current);
    return value ?? undefined;
  }, [siteKey]);

  const widget = siteKey ? (
    <div>
      <div ref={setContainer} />
      {loadError && (
        <Text size="sm" tone="danger" role="alert">
          보안 확인을 불러오지 못했어요. 광고 차단기를 끄거나 다른 브라우저에서 다시 시도해 주세요.
        </Text>
      )}
    </div>
  ) : null;

  return { widget, take };
}

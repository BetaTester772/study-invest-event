import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError } from '../api';
import { Text } from '../components/ui';

/** Cloudflare Turnstile(봇 확인). 서버가 사이트 키(`signup.turnstile_site_key`)를 줄 때만 켠다. */

const SCRIPT_URL = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
/** 토큰이 아직 없을 때(확인 중·사용자 상호작용 대기) 기다리는 최대 시간. 넘으면 요청하지 않고 안내한다. */
const TOKEN_WAIT_MS = 60_000;

interface TurnstileOptions {
  sitekey: string;
  action: string;
  appearance?: 'always' | 'execute' | 'interaction-only';
  size?: 'normal' | 'flexible' | 'compact';
  language?: string;
  callback?: (token: string) => void;
  'expired-callback'?: () => void;
  'error-callback'?: (code: string) => void;
  'before-interactive-callback'?: () => void;
  'after-interactive-callback'?: () => void;
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
   * 토큰이 아직 없으면(확인 중, 사람이 상자를 눌러야 함) 받을 때까지 기다린다(`waiting`).
   * 꺼져 있으면 undefined. 위젯을 불러오지 못했거나 오류가 나거나 오래 걸리면 ApiError(안내 문구)를
   * 던진다(토큰 없이 보내 봐야 서버가 거절한다).
   */
  take: () => Promise<string | undefined>;
  /** take()가 토큰을 기다리는 중. 제출 버튼을 '로그인 중'처럼 보이지 않게 할 때 쓴다. */
  waiting: boolean;
}

const LOAD_FAILED = '보안 확인을 불러오지 못했습니다. 광고 차단기를 끄거나 다른 브라우저에서 다시 시도해 주세요.';
const NOT_DONE = '보안 확인을 마치지 못했습니다. 보안 확인 상자를 눌러 완료한 뒤 다시 시도해 주세요.';

function captchaError(message: string): ApiError {
  return new ApiError(0, 'CAPTCHA_PENDING', message);
}

/** siteKey: `signup.turnstile_site_key`. action: 서버 라우트가 기대하는 값(login·register·password_reset). */
export function useTurnstile(siteKey: string | null | undefined, action: string): Turnstile {
  // 콜백 ref: 위젯 자리가 사라졌다 다시 생기면(단계 전환 등) 새 자리에 다시 그린다.
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const widgetId = useRef<string | null>(null);
  const token = useRef<string | null>(null);
  /** 위젯을 쓸 수 없는 이유(불러오기 실패·위젯 오류). 있으면 take()가 바로 이 안내를 던진다. */
  const failure = useRef<string | null>(null);
  const waiters = useRef<Array<(t: string | null) => void>>([]);
  const [error, setError] = useState<string | null>(null);
  const [waiting, setWaiting] = useState(false);
  const [interactive, setInteractive] = useState(false);

  const fail = (message: string | null) => {
    failure.current = message;
    setError(message);
  };

  const settle = (value: string | null) => {
    const pending = waiters.current;
    waiters.current = [];
    pending.forEach((resolve) => resolve(value));
  };

  useEffect(() => {
    if (!siteKey || !container) return;
    let cancelled = false;
    fail(null);
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
              fail(null);
              settle(t);
            },
            'expired-callback': () => {
              token.current = null;
            },
            // 예: 110200(이 도메인이 위젯에 등록되지 않음), 600xxx(확인 실패). 위젯은 스스로 다시 시도한다.
            'error-callback': (code) => {
              token.current = null;
              fail(`보안 확인 중 오류가 났습니다(${code}). 페이지를 새로고침한 뒤 다시 시도해 주세요.`);
              settle(null);
            },
            'before-interactive-callback': () => setInteractive(true),
            'after-interactive-callback': () => setInteractive(false),
          }) ?? null;
      })
      .catch(() => {
        if (cancelled) return;
        fail(LOAD_FAILED);
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
    if (!siteKey) return undefined;
    let value = token.current;
    if (!value) {
      if (failure.current) throw captchaError(failure.current);
      setWaiting(true);
      try {
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
      } finally {
        setWaiting(false);
      }
      if (!value) throw captchaError(failure.current ?? NOT_DONE);
    }
    token.current = null;
    if (widgetId.current) window.turnstile?.reset(widgetId.current);
    return value;
  }, [siteKey]);

  const widget = siteKey ? (
    <div>
      <div ref={setContainer} />
      {error ? (
        <Text size="sm" tone="danger" role="alert">
          {error}
        </Text>
      ) : (
        waiting && (
          <Text size="sm" tone="muted" role="status">
            {interactive
              ? '보안 확인 상자를 눌러 주세요. 확인이 끝나면 자동으로 이어서 진행합니다.'
              : '보안 확인 중입니다. 잠시만 기다려 주세요.'}
          </Text>
        )
      )}
    </div>
  ) : null;

  return { widget, take, waiting };
}

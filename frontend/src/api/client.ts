import { adminKeyStore, tokenStore } from './storage';
import type { ApiErrorBody } from './types';

export const API_BASE = '/api';

/** Error thrown for any non-2xx response or network failure. `message` is user-facing Korean. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly body: unknown;

  constructor(status: number, code: string, message: string, body?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

export type AuthMode = 'none' | 'participant' | 'optional' | 'admin';

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  /** JSON body (ignored when `form` is given). */
  body?: unknown;
  /** multipart/form-data body. */
  form?: FormData;
  query?: Record<string, string | number | boolean | null | undefined>;
  /** `participant` = Bearer (required), `optional` = Bearer if present, `admin` = X-Admin-Key. */
  auth?: AuthMode;
  signal?: AbortSignal;
  /** Parse as blob instead of JSON. */
  responseType?: 'json' | 'blob';
}

type UnauthorizedListener = (mode: AuthMode) => void;
const unauthorizedListeners = new Set<UnauthorizedListener>();

/** Subscribe to 401 responses (used by AuthContext to drop a stale session). */
export function onUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

const STATUS_MESSAGES: Record<number, string> = {
  400: '요청이 올바르지 않아요.',
  401: '로그인이 필요해요. 다시 로그인해 주세요.',
  403: '이 작업을 할 수 있는 권한이 없어요.',
  404: '찾는 항목이 없어요.',
  409: '이미 처리된 요청이에요.',
  422: '입력한 값을 다시 확인해 주세요.',
  429: '요청이 너무 많아요. 잠시 뒤 다시 시도해 주세요.',
  500: '서버에서 문제가 생겼어요. 잠시 뒤 다시 시도해 주세요.',
};

/** Turn any error body into (code, message). Exported for tests. */
export function parseErrorBody(status: number, body: unknown): { code: string; message: string } {
  const fallback = STATUS_MESSAGES[status] ?? `요청을 처리하지 못했어요. (HTTP ${status})`;
  const detail = (body as ApiErrorBody | null)?.detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    return { code: detail.code ?? `HTTP_${status}`, message: detail.message ?? fallback };
  }
  if (Array.isArray(detail)) {
    const first = detail[0];
    const field = Array.isArray(first?.loc) ? first.loc[first.loc.length - 1] : undefined;
    const msg = first?.msg ? `${field ? `${String(field)}: ` : ''}${first.msg}` : fallback;
    return { code: 'VALIDATION_ERROR', message: `입력한 값을 다시 확인해 주세요. (${msg})` };
  }
  if (typeof detail === 'string') return { code: `HTTP_${status}`, message: detail };
  return { code: `HTTP_${status}`, message: fallback };
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = `${API_BASE}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== '') params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

export function authHeaders(auth: AuthMode): Record<string, string> {
  const headers: Record<string, string> = {};
  if (auth === 'participant' || auth === 'optional') {
    const token = tokenStore.get();
    if (token) headers.Authorization = `Bearer ${token}`;
  } else if (auth === 'admin') {
    const key = adminKeyStore.get();
    if (key) headers['X-Admin-Key'] = key;
  }
  return headers;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, form, query, auth = 'none', signal, responseType = 'json' } = options;
  const headers: Record<string, string> = {
    Accept: responseType === 'json' ? 'application/json' : '*/*',
    ...authHeaders(auth),
  };
  let payload: BodyInit | undefined;
  if (form) {
    payload = form;
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }

  let res: Response;
  try {
    res = await fetch(buildUrl(path, query), { method, headers, body: payload, signal });
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') throw err;
    throw new ApiError(0, 'NETWORK_ERROR', '서버에 연결하지 못했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.');
  }

  if (!res.ok) {
    let parsed: unknown = null;
    try {
      parsed = await res.json();
    } catch {
      /* non-JSON error body */
    }
    const { code, message } = parseErrorBody(res.status, parsed);
    if (res.status === 401 && auth !== 'none') unauthorizedListeners.forEach((l) => l(auth));
    throw new ApiError(res.status, code, message, parsed);
  }

  if (res.status === 204) return undefined as T;
  if (responseType === 'blob') return (await res.blob()) as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

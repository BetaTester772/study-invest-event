import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, parseErrorBody, request } from '../client';
import { adminKeyStore, tokenStore } from '../storage';

afterEach(() => {
  vi.unstubAllGlobals();
  tokenStore.set(null);
  adminKeyStore.set(null);
});

describe('parseErrorBody', () => {
  it('reads {detail:{code,message}}', () => {
    expect(parseErrorBody(409, { detail: { code: 'ALREADY_CERTIFIED', message: '이미 인증했어요' } })).toEqual({
      code: 'ALREADY_CERTIFIED',
      message: '이미 인증했어요',
    });
  });

  it('turns FastAPI 422 lists into VALIDATION_ERROR', () => {
    const r = parseErrorBody(422, { detail: [{ loc: ['body', 'nickname'], msg: 'too short', type: 'x' }] });
    expect(r.code).toBe('VALIDATION_ERROR');
    expect(r.message).toContain('nickname: too short');
  });

  it('falls back to a Korean status message', () => {
    expect(parseErrorBody(500, null).message).toContain('서버');
  });
});

describe('request', () => {
  it('attaches Bearer token for participant calls and parses JSON', async () => {
    tokenStore.set('abc');
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: 1 }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(request('/me', { auth: 'participant', query: { limit: 5 } })).resolves.toEqual({ ok: 1 });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/me?limit=5');
    expect(init.headers.Authorization).toBe('Bearer abc');
  });

  it('attaches X-Admin-Key for admin calls', async () => {
    adminKeyStore.set('secret');
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);
    await request('/admin/params', { auth: 'admin', method: 'PUT', body: { a: 1 } });
    const init = fetchMock.mock.calls[0][1];
    expect(init.headers['X-Admin-Key']).toBe('secret');
    expect(init.headers['Content-Type']).toBe('application/json');
  });

  it('throws ApiError with server code/message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: { code: 'INVALID_CREDENTIALS', message: '틀렸어요' } }), {
          status: 401,
        }),
      ),
    );
    const err = await request<never>('/auth/login', { method: 'POST', body: {} }).catch((e: unknown) => e as ApiError);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(401);
    expect(err.code).toBe('INVALID_CREDENTIALS');
    expect(err.message).toBe('틀렸어요');
  });

  it('maps network failures to NETWORK_ERROR', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    const err = await request<never>('/event').catch((e: unknown) => e as ApiError);
    expect(err.code).toBe('NETWORK_ERROR');
  });
});

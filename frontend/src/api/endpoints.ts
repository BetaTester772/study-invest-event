import { request } from './client';
import type {
  AdminCertification,
  AdminParticipant,
  AuditEntry,
  AuthResponse,
  BatchResult,
  CertStatus,
  Certification,
  EventInfo,
  Instrument,
  LoginRequest,
  Order,
  OrderRequest,
  Params,
  Participant,
  ParticipantStatus,
  Portfolio,
  PriceOverrideRequest,
  PricePoint,
  Ranking,
  RegisterRequest,
  ReviewRequest,
  SettlementLog,
  SimulationReport,
  SimulationRequest,
} from './types';

/** Public endpoints. */
export const publicApi = {
  health: () => request<{ status: string }>('/health'),
  event: () => request<EventInfo>('/event'),
  instruments: () => request<Instrument[]>('/instruments'),
  history: (code: string) => request<PricePoint[]>(`/instruments/${encodeURIComponent(code)}/history`),
  /** Sends the Bearer token when logged in so the server can mark `is_me`. */
  ranking: () => request<Ranking>('/ranking', { auth: 'optional' }),
};

export const authApi = {
  register: (body: RegisterRequest) => request<AuthResponse>('/auth/register', { method: 'POST', body }),
  login: (body: LoginRequest) => request<AuthResponse>('/auth/login', { method: 'POST', body }),
  logout: () => request<void>('/auth/logout', { method: 'POST', auth: 'participant' }),
};

/** Participant endpoints (Bearer). */
export const meApi = {
  me: () => request<Participant>('/me', { auth: 'participant' }),
  portfolio: () => request<Portfolio>('/me/portfolio', { auth: 'participant' }),
  orders: (limit = 100) => request<Order[]>('/me/orders', { auth: 'participant', query: { limit } }),
  placeOrder: (body: OrderRequest) => request<Order>('/me/orders', { method: 'POST', auth: 'participant', body }),
  certifications: () => request<Certification[]>('/me/certifications', { auth: 'participant' }),
  uploadCertification: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<Certification>('/me/certifications', { method: 'POST', auth: 'participant', form });
  },
};

/** Admin endpoints (X-Admin-Key). */
export const adminApi = {
  participants: () => request<AdminParticipant[]>('/admin/participants', { auth: 'admin' }),
  setParticipantStatus: (id: number, status: ParticipantStatus) =>
    request<AdminParticipant>(`/admin/participants/${id}`, { method: 'PATCH', auth: 'admin', body: { status } }),
  certifications: (status?: CertStatus) =>
    request<AdminCertification[]>('/admin/certifications', { auth: 'admin', query: { status } }),
  review: (id: number, body: ReviewRequest) =>
    request<AdminCertification>(`/admin/certifications/${id}/review`, { method: 'POST', auth: 'admin', body }),
  params: () => request<Params>('/admin/params', { auth: 'admin' }),
  updateParams: (body: Params) => request<Params>('/admin/params', { method: 'PUT', auth: 'admin', body }),
  overridePrice: (day: string, code: string, body: PriceOverrideRequest) =>
    request<PricePoint>(`/admin/prices/${day}/${encodeURIComponent(code)}`, { method: 'PUT', auth: 'admin', body }),
  batchOpen: (day?: string) =>
    request<BatchResult>('/admin/batch/open', { method: 'POST', auth: 'admin', body: day ? { day } : {} }),
  batchSettle: (day?: string) =>
    request<BatchResult>('/admin/batch/settle', { method: 'POST', auth: 'admin', body: day ? { day } : {} }),
  batchRunDue: () => request<BatchResult[]>('/admin/batch/run-due', { method: 'POST', auth: 'admin' }),
  settlements: () => request<SettlementLog[]>('/admin/settlements', { auth: 'admin' }),
  audit: (limit = 200) => request<AuditEntry[]>('/admin/audit', { auth: 'admin', query: { limit } }),
  simulate: (body: SimulationRequest) =>
    request<SimulationReport>('/admin/simulate', { method: 'POST', auth: 'admin', body }),
};

/** Fetch an auth-protected image (<img> can't send headers) as a Blob. */
export function fetchImage(url: string, auth: 'participant' | 'admin'): Promise<Blob> {
  const path = url.startsWith('/api') ? url.slice(4) : url;
  return request<Blob>(path, { auth, responseType: 'blob' });
}

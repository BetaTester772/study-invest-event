/**
 * Mirrors docs/dev/api.md (API 계약 v0.1) exactly. Money/prices are integer won,
 * rates are decimals (-0.3 = -30%), days are YYYY-MM-DD, times are ISO 8601 KST.
 */

export type Side = 'buy' | 'sell';
export type InstrumentKind = 'stock' | 'coin';
export type ParticipantStatus = 'normal' | 'warning' | 'disqualified';
export type OrderStatus = 'filled' | 'rejected';
export type RejectReason =
  | 'MARKET_CLOSED'
  | 'MARKET_NOT_OPENED'
  | 'INVALID_QUANTITY'
  | 'UNKNOWN_INSTRUMENT'
  | 'INSUFFICIENT_CASH'
  | 'INSUFFICIENT_HOLDINGS'
  | 'DAILY_BUY_LIMIT'
  | 'DISQUALIFIED';
export type CertStatus = 'pending' | 'approved' | 'rejected';
export type PriceSource = 'initial' | 'settlement' | 'carry_over' | 'manual';

export interface Instrument {
  code: string;
  name: string;
  alias: string;
  kind: InstrumentKind;
  price: number;
  previous_price: number | null;
  change_rate: number | null;
  day: string | null;
}

export interface PricePoint {
  day: string;
  price: number;
  change_rate: number | null;
  source: PriceSource;
}

export interface Participant {
  id: number;
  nickname: string;
  status: ParticipantStatus;
  joined_at: string;
}

export interface HoldingView {
  code: string;
  name: string;
  kind: InstrumentKind;
  quantity: number;
  avg_price: number;
  price: number;
  value: number;
  cost: number;
  profit: number;
  profit_rate: number | null;
}

export interface Portfolio {
  cash: number;
  holdings: HoldingView[];
  holdings_value: number;
  total_assets: number;
  initial_cash: number;
  return_rate: number;
  day: string | null;
  buy_limit: {
    ratio: number;
    limit_amount: number;
    remaining: Record<string, number>;
  };
}

export interface Order {
  id: number;
  code: string;
  side: Side;
  quantity: number;
  price: number | null;
  amount: number | null;
  status: OrderStatus;
  reject_reason: RejectReason | null;
  reject_message: string | null;
  trade_day: string | null;
  created_at: string;
}

/** 지금 인증을 올릴 수 있는지. 서버가 제출 검사와 같은 규칙으로 계산한다(화면은 이 값만 따른다). */
export interface CertificationStatus {
  target_date: string;
  cutoff: string;
  can_submit: boolean;
  reason: 'DISQUALIFIED' | 'OUTSIDE_EVENT' | 'ALREADY_CERTIFIED' | null;
  message: string | null;
  /** 집계 날짜에 이미 낸 인증(반려 포함). 1인 1일 1회라 반려돼도 다시 낼 수 없다. */
  existing: Certification | null;
}

export interface Certification {
  id: number;
  target_date: string;
  status: CertStatus;
  reject_reason: string | null;
  submitted_at: string;
  reviewed_at: string | null;
  rewarded_at: string | null;
  reward_quantity: number | null;
  image_url: string | null;
}

export interface EventInfo {
  start: string;
  end: string;
  operating_days: string[];
  total_rounds: number;
  now: string;
  today: string;
  is_operating_day: boolean;
  market: {
    is_open: boolean;
    opens_at: string;
    closes_at: string;
    day_opened: boolean;
    day_settled: boolean;
    round: number | null;
  };
  certification: { cutoff: string; target_date: string; reward_coin_quantity: number };
  initial_cash: number;
  daily_buy_limit_ratio: number;
}

export interface RankingEntry {
  rank: number;
  nickname: string;
  total_assets: number;
  return_rate: number;
  certified_days: number;
  streak: number;
  is_me?: boolean;
}

export interface Ranking {
  day: string | null;
  entries: RankingEntry[];
}

export interface AuthResponse {
  token: string;
  participant: Participant;
}

export interface RegisterRequest {
  identity: string;
  nickname: string;
  password: string;
}

export interface LoginRequest {
  identity: string;
  password: string;
}

export interface OrderRequest {
  code: string;
  side: Side;
  quantity: number;
}

// ---- Admin ----

export interface AdminParticipant extends Participant {
  identity: string;
  cash: number;
  total_assets: number;
  rejected_certifications: number;
  approved_certifications: number;
}

export interface AdminCertification extends Certification {
  participant_id: number;
  nickname: string;
  image_hash: string;
  duplicate_of: number | null;
  image_url: string | null;
}

export interface Params {
  coin_p_up: number;
  coin_up_exp: number;
  coin_down_exp: number;
  coin_cap: number;
  coin_floor: number;
  coin_price_cap: number | null;
  stock_sensitivity: number;
  stock_min_price: number;
  virtual_liquidity: number;
  daily_buy_limit_ratio: number;
  reward_coin_quantity: number;
  certification_cutoff: string;
}

export interface SettlementStock {
  code: string;
  buy_amount: number;
  adjusted_amount: number;
  concentration: number | null;
  rate: number;
  old_price: number;
  new_price: number;
}

export interface SettlementLog {
  id: number;
  round: number;
  trade_day: string;
  effective_day: string;
  created_at: string;
  stocks: SettlementStock[];
  coin: { p: number; x: number; direction: 'up' | 'down'; rate: number; old_price: number; new_price: number };
  params: Params;
}

export interface SimulationReport {
  paths: number;
  rounds: number;
  seed: number | null;
  price_cap: number | null;
  daily: {
    up_ratio: number;
    mean_up: number;
    mean_down: number;
    mean: number;
    mean_log: number;
    quantiles: { q: number; rate: number }[];
  };
  cumulative: {
    quantiles: { q: number; multiple: number }[];
    prob_above: { multiple: number; prob: number }[];
    cap_hit_ratio: number;
  };
}

/** 시뮬레이터 입력 한계(서버 스키마에서 생성). */
export interface IntRange {
  min: number;
  max: number;
  default: number;
}
export interface SimulateOptions {
  paths: IntRange;
  rounds: IntRange;
}

export interface SimulationRequest {
  paths?: number;
  rounds?: number;
  seed?: number | null;
  use_price_cap?: boolean;
}

export interface BatchResult {
  action: 'open' | 'settle';
  day: string;
  detail: Record<string, unknown>;
}

export interface AuditEntry {
  id: number;
  at: string;
  actor: string;
  action: string;
  detail: Record<string, unknown>;
}

export interface ReviewRequest {
  approve: boolean;
  reason?: string;
}

export interface PriceOverrideRequest {
  price: number;
  reason: string;
}

/** Error body: {"detail": {"code", "message"}}; FastAPI 422 uses its default list format. */
export interface ApiErrorBody {
  detail?: { code?: string; message?: string } | Array<{ loc?: unknown[]; msg?: string; type?: string }> | string;
}

/**
 * Mirrors docs/dev/api.md (API 계약 v0.2) exactly. Money/prices are integer won,
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
  /** 가린 등록 메일(k***@g.skku.edu). 본인 응답에도 전체 주소는 오지 않는다. 없으면 null. */
  masked_email: string | null;
  /** 학교 메일 코드나 관리자 확인으로 인증했는지. `signup.verified_only_trading`이면 false인 동안 주문 불가. */
  verified: boolean;
  /** 학교 메일 코드로 인증했는지. false면 메일 인증을 할 수 있다(미인증 또는 관리자 인증만). */
  email_verified: boolean;
  /** 이름·학번·학과가 없는 계정(메일 인증 도입 전 가입). 인증할 때 함께 받는다. */
  needs_profile: boolean;
}

/** 가입·인증 운영 설정. */
export interface SignupInfo {
  /** true면 가입할 때 학교 메일 인증 코드가 필요하다. false(기본)면 메일 주소만 받고 미인증으로 가입. */
  email_verification: boolean;
  /** true면 인증된 참가자만 주문할 수 있다(관리자가 부정 대응으로 켠다). */
  verified_only_trading: boolean;
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
  /** Study-reward cash received so far. */
  rewards_received: number;
  /** 투입 원금 = initial_cash + rewards_received (the return-rate base). */
  principal: number;
  /** 투자 손익 = total_assets − principal. Rewards are principal, not profit. */
  profit: number;
  /** profit / principal. */
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
  /** Cash paid for this certification (won). `null` until paid. */
  reward_cash: number | null;
  image_url: string | null;
}

export interface EventInfo {
  start: string;
  /** `null` in QA unlimited mode (no end date). */
  end: string | null;
  /** In QA unlimited mode: start through the later of today and the latest opened day. */
  operating_days: string[];
  /** `null` in QA unlimited mode. */
  total_rounds: number | null;
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
  /** `reward_cash`: won paid at the next operating day's 09:00 per approved certification. */
  certification: { cutoff: string; target_date: string; reward_cash: number };
  coin: CoinInfo;
  initial_cash: number;
  daily_buy_limit_ratio: number;
  /** Test clock (QA servers only). `null` on the real clock. */
  clock: ClockInfo | null;
  signup: SignupInfo;
}

/** BYUNG daily move range (rates are decimals: 2 = +200%). */
export interface CoinInfo {
  cap: number;
  floor: number;
  /** Early calm rounds (0 = none); rounds 1..calm_rounds use calm_cap/calm_floor. */
  calm_rounds: number;
  /** Operating day whose opening price takes the last calm round. */
  calm_until: string | null;
  calm_cap: number;
  calm_floor: number;
}

/** Real-world times for a sped-up test clock. */
export interface ClockInfo {
  /** 24 → one real hour is one event day. */
  scale: number;
  real_now: string;
  /** Real time of the next operating day's 09:00 (open). `null` when none is left. */
  next_open_at: string | null;
  /** Real time of the next operating day's 18:00 (close & settlement). `null` when none is left. */
  next_close_at: string | null;
}

export interface RankingEntry {
  /** Total-assets rank (prizes 1–3). Ties share a rank. */
  rank: number;
  nickname: string;
  total_assets: number;
  /** 투입 원금 = seed + study rewards received. */
  principal: number;
  /** total_assets − principal. */
  profit: number;
  /** profit / principal. */
  return_rate: number;
  /** Return-rate rank, highest first. Ties share a rank. */
  return_rank: number;
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

export interface EmailCodeRequest {
  email: string;
}

export interface EmailCodeResponse {
  /** 코드를 보낸 주소. 등록 메일로 보냈으면 가린 주소. */
  email: string;
  /** 코드 유효시간(초). */
  expires_in: number;
  /** 다시 요청할 수 있을 때까지(초). */
  resend_after: number;
}

/** 이름·학번·학과. 관리자만 본다(랭킹에는 닉네임만). */
export interface ProfileFields {
  name: string;
  /** 숫자 10자리. 한 학번에 한 계정. */
  student_id: string;
  department: string;
}

export interface RegisterRequest extends ProfileFields {
  email: string;
  /** 학교 메일 인증 코드. `signup.email_verification`이 꺼져 있으면 생략(미인증으로 가입). */
  code?: string;
  nickname: string;
  password: string;
  privacy_consent: boolean;
}

/** 비우면 등록 메일로, 주소를 주면 그 주소로 인증 코드를 보낸다. */
export interface MyEmailCodeRequest {
  email?: string;
}

/**
 * 학교 메일 코드 인증. 등록 메일로 받았으면 코드만, 다른 주소로 받았으면 그 주소도.
 * 이름·학번·학과·동의는 `needs_profile`인 계정만 보낸다.
 */
export interface VerifyEmailRequest extends Partial<ProfileFields> {
  email?: string;
  code: string;
  privacy_consent?: boolean;
}

export type VerifyMethod = 'email' | 'admin';

/** 학번(학교 메일도 받는다). 코드는 그 계정의 등록 메일로만 간다. */
export interface PasswordResetCodeRequest {
  identity: string;
}

/** 새 비밀번호를 받기 전에 코드만 확인한다(코드는 쓰지 않는다). */
export interface PasswordResetVerifyRequest {
  identity: string;
  code: string;
}

export interface PasswordResetRequest {
  identity: string;
  code: string;
  /** 새 비밀번호(8자 이상). */
  password: string;
}

export interface LoginRequest {
  /** 학번(숫자 10자리). 학교 메일이나 메일 인증 도입 전 식별자도 받는다. */
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
  /** 메일 인증 도입 전 아이디. 그 뒤 가입한 참가자는 null. */
  identity: string | null;
  /** 등록 학교 메일 전체 주소(관리자만). */
  email: string | null;
  /** 이름·학번·학과. 재인증 전 계정이거나 이벤트 후 파기했으면 null. */
  name: string | null;
  student_id: string | null;
  department: string | null;
  verified_at: string | null;
  /** email(학교 메일 코드) 또는 admin(관리자 확인). 미인증이면 null. */
  verified_via: VerifyMethod | null;
  cash: number;
  total_assets: number;
  principal: number;
  return_rate: number;
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
  coin_calm_rounds: number;
  coin_calm_cap: number;
  coin_calm_floor: number;
  stock_sensitivity: number;
  stock_min_price: number;
  virtual_liquidity: number;
  /** 매수지분 잡음 세기 τ (0~2). 0이면 잡음 없음. */
  stock_noise_scale: number;
  daily_buy_limit_ratio: number;
  reward_cash: number;
  certification_cutoff: string;
  /** 인증된 참가자만 거래. 파라미터 폼은 보내지 않는다(서버가 현재 값 유지). */
  verified_only_trading?: boolean | null;
}

export interface TradingAccess {
  verified_only: boolean;
}

export interface SettlementStock {
  code: string;
  buy_amount: number;
  adjusted_amount: number;
  /** Gumbel noise multiplier on the buy share; null when noise is off or for older logs. */
  noise_factor: number | null;
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
  coin: {
    p: number;
    x: number;
    direction: 'up' | 'down';
    rate: number;
    old_price: number;
    new_price: number;
    /** Drawn with the early calm-period range. */
    calm: boolean;
  };
  params: Params;
}

export interface SimulationDaily {
  days: number;
  up_ratio: number;
  mean_up: number;
  mean_down: number;
  mean: number;
  mean_log: number;
  quantiles: { q: number; rate: number }[];
}

export interface SimulationReport {
  paths: number;
  rounds: number;
  seed: number | null;
  price_cap: number | null;
  /** Rounds per path drawn with the calm range (from round 1). */
  calm_rounds: number;
  /** Normal rounds only; `null` when every round was calm. */
  daily: SimulationDaily | null;
  /** Calm rounds only; `null` when there is no calm period. */
  calm_daily: SimulationDaily | null;
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
  action: 'open' | 'settle' | 'advance';
  day: string;
  detail: Record<string, unknown>;
}

export interface QaStatus {
  enabled: boolean;
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

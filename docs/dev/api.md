# API 계약 (v0.1)

백엔드(FastAPI)와 프론트엔드(React)가 공유하는 HTTP 계약이다. 모든 경로는 `/api` 접두사를 가진다.

## 공통 규칙

- 요청·응답 본문은 JSON(UTF-8). 인증 사진 업로드만 `multipart/form-data`.
- 금액·가격은 **정수 원**(`int`). 변동률·비율은 **소수**(`float`, 예: `-0.3` = -30%).
- 날짜는 `YYYY-MM-DD`, 시각은 KST 오프셋이 붙은 ISO 8601(`2026-10-06T09:00:00+09:00`).
- 오류 응답: `{"detail": {"code": "<ERROR_CODE>", "message": "<한국어 설명>"}}`. FastAPI 검증 오류(422)는 기본 형식.
- 참가자 인증: `Authorization: Bearer <token>`. 관리자 인증: `X-Admin-Key: <key>`.

| HTTP | code 예 | 의미 |
|---|---|---|
| 401 | `UNAUTHORIZED` | 토큰/관리자 키 없음·불일치 |
| 403 | `DISQUALIFIED` | 실격 참가자 |
| 404 | `NOT_FOUND` | 리소스 없음 |
| 409 | `CONFLICT` 계열 | 중복 등록, 중복 인증, 배치 순서 위반 등 |

## 공용 타입

```ts
type Side = "buy" | "sell";
type InstrumentKind = "stock" | "coin";
type ParticipantStatus = "normal" | "warning" | "disqualified";
type OrderStatus = "filled" | "rejected";
type RejectReason =
  | "MARKET_CLOSED"          // 09:00–18:00 밖, 운영일 아님, 당일 정산 완료
  | "MARKET_NOT_OPENED"      // 당일 시작가 미공시(09:00 배치 전)
  | "INVALID_QUANTITY"       // 정수 1 이상 아님
  | "UNKNOWN_INSTRUMENT"
  | "INSUFFICIENT_CASH"
  | "INSUFFICIENT_HOLDINGS"
  | "DAILY_BUY_LIMIT"        // 1일 1종목 매수 상한(총자산 40%) 초과
  | "DISQUALIFIED";
type CertStatus = "pending" | "approved" | "rejected";
type PriceSource = "initial" | "settlement" | "carry_over" | "manual";

interface Instrument {
  code: string;            // "SAMSU" | "SKLOW" | "MIRAE" | "LB" | "BYUNG"
  name: string;            // "삼수전자"
  alias: string;           // "MIRAE DAI"
  kind: InstrumentKind;
  price: number;           // 최신 공시일 시작가
  previous_price: number | null;
  change_rate: number | null;   // 전일 대비, 소수
  day: string | null;      // 최신 공시 운영일 (공시 전이면 null, price는 1일차 시작가)
}

interface PricePoint { day: string; price: number; change_rate: number | null; source: PriceSource; }

interface Participant {
  id: number;
  nickname: string;
  status: ParticipantStatus;
  joined_at: string;
}

interface HoldingView {
  code: string; name: string; kind: InstrumentKind;
  quantity: number;
  avg_price: number;       // 평균단가(원, 반올림)
  price: number;           // 현재가
  value: number;           // 평가금액 = quantity × price
  cost: number;            // 매입금액(보상 코인은 0원)
  profit: number;          // 평가손익 = value − cost
  profit_rate: number | null;   // cost=0이면 null
}

interface Portfolio {
  cash: number;
  holdings: HoldingView[];      // 수량 0 종목 제외
  holdings_value: number;
  total_assets: number;         // cash + holdings_value
  initial_cash: number;         // 1,000,000
  return_rate: number;          // total_assets / initial_cash − 1
  day: string | null;           // 평가 기준 운영일
  buy_limit: {                  // 당일 종목별 남은 매수 한도
    ratio: number;              // 0.4
    limit_amount: number;       // floor(total_assets × ratio)
    remaining: Record<string, number>;  // code → 남은 금액
  };
}

interface Order {
  id: number;
  code: string;
  side: Side;
  quantity: number;
  price: number | null;         // 체결가(거부 시 참고용 당일가 또는 null)
  amount: number | null;        // price × quantity
  status: OrderStatus;
  reject_reason: RejectReason | null;
  reject_message: string | null;   // 한국어 설명
  trade_day: string | null;
  created_at: string;
}

interface Certification {
  id: number;
  target_date: string;
  status: CertStatus;
  reject_reason: string | null;
  submitted_at: string;
  reviewed_at: string | null;
  rewarded_at: string | null;   // 병더리움 지급 시각
  reward_quantity: number | null;
  image_url: string | null;     // 참가자: /api/me/certifications/{id}/image, 삭제 후 null
}

interface EventInfo {
  start: string; end: string;
  operating_days: string[];
  total_rounds: number;          // 10
  now: string;                   // 서버 시각(KST)
  today: string;
  is_operating_day: boolean;
  market: {
    is_open: boolean;            // 지금 주문 가능한가(시간·공시·정산 모두 고려)
    opens_at: string; closes_at: string;   // "09:00", "18:00"
    day_opened: boolean;         // 오늘 시작가 공시 여부
    day_settled: boolean;        // 오늘 18:00 정산 완료 여부
    round: number | null;        // 오늘 정산 회차(마지막 날 null)
  };
  certification: { cutoff: string; target_date: string; reward_coin_quantity: number };
  initial_cash: number;
  daily_buy_limit_ratio: number;
}

interface RankingEntry {
  rank: number;                  // 동점 공동 순위(1,2,2,4)
  nickname: string;
  total_assets: number;
  return_rate: number;
  certified_days: number;        // 승인된 인증 일수
  streak: number;                // 인증 연속일수
  is_me?: boolean;               // Bearer 토큰이 있으면 표시
}
```

## 공개

| 메서드 | 경로 | 응답 |
|---|---|---|
| GET | `/api/health` | `{"status":"ok"}` |
| GET | `/api/event` | `EventInfo` |
| GET | `/api/instruments` | `Instrument[]` |
| GET | `/api/instruments/{code}/history` | `PricePoint[]` (공시된 운영일만, 오름차순) |
| GET | `/api/ranking` | `{ day: string\|null, entries: RankingEntry[] }` (총자산 100% 기준, 실격자 제외) |

## 참가자 인증

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| POST | `/api/auth/register` | `{identity, nickname, password}` | 201 `{token, participant: Participant}` / 409 `IDENTITY_TAKEN`, `NICKNAME_TAKEN` |
| POST | `/api/auth/login` | `{identity, password}` | `{token, participant}` / 401 `INVALID_CREDENTIALS` |
| POST | `/api/auth/logout` | – | 204 |

- `identity`: 1인 1계정 식별자(사내 계정·학번 등). 앞뒤 공백 제거·대소문자 무시로 정규화해 중복 검사.
- `nickname`: 2~20자, 랭킹 공개명. `password`: 8자 이상.

## 참가자 (Bearer)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| GET | `/api/me` | – | `Participant` |
| GET | `/api/me/portfolio` | – | `Portfolio` |
| GET | `/api/me/orders` | `?limit=100` | `Order[]` (최신순) |
| POST | `/api/me/orders` | `{code, side, quantity}` | 201 `Order` (체결·거부 모두 201, `status`로 구분) |
| GET | `/api/me/certifications` | – | `Certification[]` (최신순) |
| POST | `/api/me/certifications` | multipart `file` (image/jpeg·png·webp·heic, ≤10MB) | 201 `Certification` / 409 `ALREADY_CERTIFIED`, 422 `OUTSIDE_EVENT`, `INVALID_IMAGE` |
| GET | `/api/me/certifications/{id}/image` | – | 이미지 바이너리 |

## 관리자 (X-Admin-Key)

```ts
interface AdminParticipant extends Participant {
  identity: string; cash: number; total_assets: number;
  rejected_certifications: number; approved_certifications: number;
}
interface AdminCertification extends Certification {
  participant_id: number; nickname: string;
  image_hash: string;
  duplicate_of: number | null;   // 같은 이미지 해시의 최초 인증 ID(중복 의심)
  image_url: string | null;      // /api/admin/certifications/{id}/image
}
interface Params {
  coin_p_up: number; coin_up_exp: number; coin_down_exp: number;
  coin_cap: number; coin_floor: number; coin_price_cap: number | null;
  stock_sensitivity: number; stock_min_price: number; virtual_liquidity: number;
  daily_buy_limit_ratio: number;
  reward_coin_quantity: number;          // 인증 1건당 병더리움 지급 수량(가격 무관)
  certification_cutoff: string;          // "23:59"
}
interface SettlementLog {
  id: number; round: number; trade_day: string; effective_day: string; created_at: string;
  stocks: { code: string; buy_amount: number; adjusted_amount: number;
            concentration: number | null; rate: number; old_price: number; new_price: number }[];
  coin: { p: number; x: number; direction: "up" | "down"; rate: number; old_price: number; new_price: number };
  params: Params;
}
interface SimulationReport {
  paths: number; rounds: number; seed: number | null; price_cap: number | null;
  daily: { up_ratio: number; mean_up: number; mean_down: number; mean: number; mean_log: number;
           quantiles: { q: number; rate: number }[] };
  cumulative: { quantiles: { q: number; multiple: number }[]; prob_above: { multiple: number; prob: number }[];
                cap_hit_ratio: number };
}
interface BatchResult { action: "open" | "settle"; day: string; detail: Record<string, unknown>; }
interface AuditEntry { id: number; at: string; actor: string; action: string; detail: Record<string, unknown>; }
```

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| GET | `/api/admin/participants` | – | `AdminParticipant[]` |
| PATCH | `/api/admin/participants/{id}` | `{status}` | `AdminParticipant` |
| GET | `/api/admin/certifications` | `?status=pending` | `AdminCertification[]` |
| GET | `/api/admin/certifications/{id}/image` | – | 이미지 |
| POST | `/api/admin/certifications/{id}/review` | `{approve: boolean, reason?: string}` | `AdminCertification` / 409 `ALREADY_REVIEWED`, 422 `REASON_REQUIRED` |
| GET | `/api/admin/params` | – | `Params` |
| PUT | `/api/admin/params` | `Params` | `Params` |
| PUT | `/api/admin/prices/{day}/{code}` | `{price, reason}` | `PricePoint` / 409 `DAY_ALREADY_OPENED` |
| POST | `/api/admin/batch/open` | `{day?}` (기본 오늘) | `BatchResult` |
| POST | `/api/admin/batch/settle` | `{day?}` | `BatchResult` |
| POST | `/api/admin/batch/run-due` | – | `BatchResult[]` (현재 시각에 밀린 배치 실행) |
| GET | `/api/admin/settlements` | – | `SettlementLog[]` |
| GET | `/api/admin/audit` | `?limit=200` | `AuditEntry[]` |
| POST | `/api/admin/simulate` | `{paths?=10000, rounds?=10, seed?, use_price_cap?=false}` | `SimulationReport` |

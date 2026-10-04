# API 계약 (v0.3)

백엔드(FastAPI)와 프론트엔드(React)가 공유하는 HTTP 계약이다. 모든 경로는 `/api` 접두사를 가진다.

v0.3 (2026-10-04): 1인 1계정을 학교 메일(@skku.edu·@g.skku.edu)·학번으로 확인. `register` 요청을 `{email, code?, name, student_id, department, nickname, password, privacy_consent}`로 변경(기본은 코드 없이 미인증 가입), 로그인은 학번으로. `POST /api/auth/email-code`(가입용 코드), `POST /api/me/email/code`·`/api/me/email`(로그인 후 메일 인증), `POST /api/auth/password-reset/code`·`/api/auth/password-reset`(학번으로 비밀번호 재설정), `GET·PUT /api/admin/trading-access`('인증된 참가자만 거래' 스위치) 추가. `Participant.masked_email`·`verified`·`email_verified`·`needs_profile`, `EventInfo.signup`, `AdminParticipant`의 `email`·`name`·`student_id`·`department`·`verified_at`·`verified_via` 추가, `identity`는 nullable. `PATCH /api/admin/participants/{id}`가 `verified`도 받는다. 스위치가 켜지면 미인증 참가자의 주문은 403 `VERIFICATION_REQUIRED`.

v0.2 (2026-10-01, 규격서 v0.4): 인증 보상을 현금으로(`reward_coin_quantity`·`reward_quantity` → `reward_cash`), 투입 원금 기준 수익률(`Portfolio`·`RankingEntry`·`AdminParticipant`), 코인 초반 안정기(`EventInfo.coin`, `coin_calm_*` 파라미터, 정산 로그 `calm`, 시뮬레이터 `calm_daily`).

## 공통 규칙

- 요청·응답 본문은 JSON(UTF-8). 인증 사진 업로드만 `multipart/form-data`.
- 금액·가격은 **정수 원**(`int`). 변동률·비율은 **소수**(`float`, 예: `-0.3` = -30%).
- 날짜는 `YYYY-MM-DD`, 시각은 KST 오프셋이 붙은 ISO 8601(`2026-10-06T09:00:00+09:00`).
- 오류 응답: `{"detail": {"code": "<ERROR_CODE>", "message": "<한국어 설명>"}}`. FastAPI 검증 오류(422)는 기본 형식.
- 참가자 인증: `Authorization: Bearer <token>`. 관리자 인증: `X-Admin-Key: <key>`.

| HTTP | code 예 | 의미 |
|---|---|---|
| 401 | `UNAUTHORIZED` | 토큰/관리자 키 없음·불일치 |
| 400 | `INVALID_CODE`, `CODE_EXPIRED`, `CODE_ATTEMPTS_EXCEEDED` | 메일 인증 코드가 틀림·만료(10분)·5번 틀림 |
| 403 | `DISQUALIFIED`, `VERIFICATION_REQUIRED` | 실격 참가자 / '인증된 참가자만 거래'가 켜진 동안 미인증 참가자의 주문 |
| 404 | `NOT_FOUND` | 리소스 없음 |
| 409 | `CONFLICT` 계열 | 중복 등록, 중복 인증, 배치 순서 위반, 동시 요청 충돌(`CONFLICT`) |
| 429 | `CODE_RECENTLY_SENT`, `TOO_MANY_CODES` | 인증 코드 재요청 60초 대기 / 메일 하나에 24시간 5통 초과 |
| 413 | `PAYLOAD_TOO_LARGE` | 요청 본문이 한도 초과(업로드 10MB+여유, 그 외 1MiB). 본문을 받기 전에 거부 |
| 503 | `DB_BUSY`, `DB_UNAVAILABLE` | api 연결 풀이 가득 참(10초 대기 초과) / DB 연결 불가. `Retry-After: 2` |
| 503 | `MAIL_SEND_FAILED`, `MAIL_BUSY`, `MAIL_QUOTA_EXCEEDED` | 인증 메일 발송 실패(코드 기록은 남아 60초 뒤 재요청) / 동시 발송이 꽉 참(코드를 만들기 전 거절, 바로 재요청 가능) / 24시간 발송 상한(`STUDY_INVEST_MAIL_DAILY_LIMIT`) 도달 |

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
  masked_email: string | null; // 가린 등록 메일(k***@skku.edu). 본인 응답에도 전체 주소는 없다. 없으면 null
  verified: boolean;         // 학교 메일 코드나 관리자 확인으로 인증했는지
  email_verified: boolean;   // 학교 메일 코드로 인증했는지. false면 메일 인증 가능(미인증·관리자 인증만)
  needs_profile: boolean;    // 이름·학번·학과가 없음(메일 인증 도입 전 계정) → 인증할 때 함께 받는다
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
  initial_cash: number;         // 1,000,000 (시드)
  rewards_received: number;     // 지금까지 받은 인증 보상 현금 합계
  principal: number;            // 투입 원금 = initial_cash + rewards_received
  profit: number;               // 투자 손익 = total_assets − principal (실현·미실현 합)
  return_rate: number;          // profit / principal. 인증 보상은 손익이 아니라 원금
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
  rewarded_at: string | null;   // 보상 지급 시각
  reward_cash: number | null;   // 지급한 현금(원). v0.3(병더리움 지급) 기록은 null
  image_url: string | null;     // 참가자: /api/me/certifications/{id}/image, 삭제 후 null
}

interface CertificationStatus {
  target_date: string;           // 지금 올리면 집계되는 날짜
  cutoff: string;                // "23:59"
  can_submit: boolean;
  reason: "DISQUALIFIED" | "OUTSIDE_EVENT" | "ALREADY_CERTIFIED" | null;
  message: string | null;
  existing: Certification | null; // 그 날짜에 이미 낸 인증(반려 포함, 1인 1일 1회라 재제출 불가)
}

interface EventInfo {
  start: string; end: string | null;      // QA 무제한 모드(STUDY_INVEST_QA_UNLIMITED)면 end null
  operating_days: string[];      // 무제한 모드면 시작일부터 오늘·최신 공시일 중 늦은 날까지
  total_rounds: number | null;   // 10. 무제한 모드면 null
  now: string;                   // 서버 시각(KST). 테스트 시계면 그 시계의 시각
  today: string;
  is_operating_day: boolean;
  market: {
    is_open: boolean;            // 지금 주문 가능한가(시간·공시·정산 모두 고려)
    opens_at: string; closes_at: string;   // "09:00", "18:00"
    day_opened: boolean;         // 오늘 시작가 공시 여부
    day_settled: boolean;        // 오늘 18:00 정산 완료 여부
    round: number | null;        // 오늘 정산 회차(마지막 날 null)
  };
  certification: { cutoff: string; target_date: string; reward_cash: number };  // 승인 1건당 현금
  coin: {                        // 병더리움 하루 변동폭(변동률은 소수, 2 = +200%)
    cap: number; floor: number;  // 평소 상·하한(2, -0.4)
    calm_rounds: number;         // 초반 안정기 회차 수(이벤트 회차 수 이내). 0이면 없음
    calm_until: string | null;   // 안정기 마지막 회차가 반영되는 운영일(기본 2026-10-09)
    calm_cap: number; calm_floor: number;  // 안정기 상·하한(0.3, -0.1)
  };
  initial_cash: number;
  daily_buy_limit_ratio: number;
  clock: {                       // 테스트 시계(STUDY_INVEST_TIME_*)일 때만. 운영(실제 시계)은 null
    scale: number;               // 24면 실제 1시간이 이벤트 하루
    real_now: string;            // 실제 시각. 위 now는 테스트 시계 시각
    next_open_at: string | null;   // 다음 운영일 09:00이 되는 실제 시각. 남은 운영일이 없으면 null
    next_close_at: string | null;  // 다음 운영일 18:00이 되는 실제 시각. 남은 운영일이 없으면 null
  } | null;
  signup: {
    email_verification: boolean;     // true면 가입 때 학교 메일 코드 필수(STUDY_INVEST_EMAIL_VERIFICATION). 기본 false
    verified_only_trading: boolean;  // true면 인증된 참가자만 주문(관리자 스위치). 기본 false
  };
}

interface RankingEntry {
  rank: number;                  // 총자산 순위(1~3위 시상). 동점 공동 순위(1,2,2,4)
  nickname: string;
  total_assets: number;
  principal: number;             // 투입 원금 = 시드 + 받은 인증 보상
  profit: number;                // total_assets − principal
  return_rate: number;           // profit / principal
  return_rank: number;           // 수익률 순위(높은 순, 동점 공동)
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
| GET | `/api/ranking` | `{ day: string\|null, entries: RankingEntry[] }` (총자산 순 정렬, 실격자 제외. 항목마다 수익률 순위 표시) |

## 참가자 인증

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| POST | `/api/auth/email-code` | `{email}` | 202 `{email, expires_in, resend_after}` (코드를 보낸 주소, 600, 60) / 422 `INVALID_EMAIL`, `EMAIL_DOMAIN_NOT_ALLOWED`, 409 `EMAIL_TAKEN`, `REGISTRATION_CLOSED`, 429, 503 |
| POST | `/api/auth/register` | `{email, code?, name, student_id, department, nickname, password, privacy_consent}` | 201 `{token, participant: Participant}` / 400 코드 오류, 409 `EMAIL_TAKEN`, `STUDENT_ID_TAKEN`, `NICKNAME_TAKEN`, 422 `PRIVACY_CONSENT_REQUIRED`, `CODE_REQUIRED` |
| POST | `/api/auth/login` | `{identity, password}` | `{token, participant}` / 401 `INVALID_CREDENTIALS` |
| POST | `/api/auth/password-reset/code` | `{identity}` | 202 `{email, expires_in, resend_after}` — `identity`는 학번(학교 메일도 받음). 코드는 그 계정의 **등록 메일로만** 가고 `email`은 가린 주소 / 404 `ACCOUNT_NOT_FOUND`(없는 학번, 메일 없는 예전 계정), 429, 503 |
| POST | `/api/auth/password-reset` | `{identity, code, password}` | `{token, participant}` — 새 비밀번호로 로그인, 다른 기기 로그인은 모두 끊는다(재설정과 동시에 옛 비밀번호로 한 로그인도) / 400 코드 오류, 404 |
| POST | `/api/auth/logout` | – | 204 |

- `email`: 학교 메일만(`@skku.edu`, `@g.skku.edu`, 하위 도메인 불가). NFKC·대소문자 무시·앞뒤 공백 제거 뒤 검사한다. ID는 영문 소문자·숫자·`.`·`_`·`-` 1~64자(`+` 별칭 불가). **같은 ID의 두 도메인은 한 사람**으로 보고 `ID@g.skku.edu`로 합쳐 저장·중복 검사한다. 코드 메일은 입력한 주소 그대로 보낸다.
- `code`: 메일로 받은 6자리 숫자. 가입 때는 **선택**: 내면 인증된 채로 가입하고, 안 내면 미인증으로 가입한다. `signup.email_verification`이 true면 필수(없으면 422 `CODE_REQUIRED`). 메일이 미인증 계정의 것이면 코드는 보내지만(본인 인증용) 그 메일로 다른 사람이 가입할 수는 없다. 비밀번호 재설정 코드(`password-reset/code`)와 가입·인증 코드는 서로 바꿔 쓸 수 없다. 10분 유효, 메일마다 가장 최근 코드만 유효, 5번 틀리면 다시 받아야 한다. 가입이 다른 이유(닉네임 중복 등)로 실패하면 코드는 쓰이지 않는다. 재요청은 60초 뒤, 메일 하나에 24시간 5통까지.
- `name` 1~30자, `student_id` 숫자 10자리(전각 숫자 허용, **한 학번에 한 계정**), `department` 1~50자. 관리자만 본다(랭킹·본인 응답에 없음).
- `privacy_consent`: 개인정보(학교 메일·이름·학번·학과) 수집·이용 동의. `true`가 아니면 422.
- 로그인 `identity`: **학번**. 학교 메일(두 도메인 어느 쪽이든)이나 메일 인증 도입 전 식별자도 받는다. 맞는 계정을 학번 → 메일 → 예전 식별자 순으로 찾아 비밀번호가 맞는 첫 계정으로 로그인한다.
- `nickname`: NFC 정규화·앞뒤 공백 제거 **후** 2~20자, 랭킹 공개명(조합형·완성형 한글은 같은 닉네임). `password`: 8자 이상.

## 참가자 (Bearer)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| GET | `/api/me` | – | `Participant` |
| POST | `/api/me/email/code` | `{email?}` | 202 `{email, expires_in, resend_after}` — 비우면 등록 메일로 보내고 `email`은 가린 주소. 주소를 주면 그 주소로(등록 메일을 잘못 적었거나 메일이 없는 예전 계정) / 409 `ALREADY_VERIFIED`, `EMAIL_TAKEN`, 422 `EMAIL_REQUIRED`(메일 없는 계정이 주소를 비움), 429, 503 |
| POST | `/api/me/email` | `{email?, code, name?, student_id?, department?, privacy_consent?}` | `Participant` — 학교 메일 코드 인증. 등록 메일로 받았으면 코드만, 다른 주소로 받았으면 그 주소도(인증하면 등록 메일이 그 주소로 바뀜). 메일 코드로 아직 인증하지 않은 계정만(미인증, 관리자 인증만): 메일 코드로 인증된 계정은 409 `ALREADY_VERIFIED`. `needs_profile`인 계정은 이름·학번·학과·동의도(없으면 422 `PROFILE_REQUIRED`). 409 `EMAIL_TAKEN`, `STUDENT_ID_TAKEN` |
| GET | `/api/me/portfolio` | – | `Portfolio` |
| GET | `/api/me/orders` | `?limit=100` | `Order[]` (최신순) |
| POST | `/api/me/orders` | `{code, side, quantity}` | 201 `Order` (체결·거부 모두 201, `status`로 구분). `code`는 1~16자, `quantity`는 정수(64비트 범위 밖이면 422). '인증된 참가자만 거래'가 켜져 있고 미인증이면 403 `VERIFICATION_REQUIRED` |
| GET | `/api/me/certifications` | – | `Certification[]` (최신순) |
| GET | `/api/me/certification-status` | – | `CertificationStatus` — 지금 올릴 수 있는지(제출 API와 같은 판단). 화면은 이 값만 따른다 |
| POST | `/api/me/certifications` | multipart `file` (image/jpeg·png·webp·heic, ≤10MB) | 201 `Certification` / 409 `ALREADY_CERTIFIED`, 422 `OUTSIDE_EVENT`, `INVALID_IMAGE` |
| GET | `/api/me/certifications/{id}/image` | – | 이미지 바이너리 |

## 관리자 (X-Admin-Key)

```ts
interface AdminParticipant extends Participant {
  identity: string | null;   // 메일 인증 도입 전 식별자. 그 뒤 가입한 참가자는 null
  email: string | null;      // 등록 학교 메일 전체 주소(코드를 보내는 주소). 관리자만
  name: string | null; student_id: string | null; department: string | null;  // 도입 전 계정·파기 후 null
  verified_at: string | null;
  verified_via: "email" | "admin" | null;   // 학교 메일 코드 / 관리자 확인. 미인증이면 null
  cash: number; total_assets: number;
  principal: number; return_rate: number;   // 투입 원금, 수익률(RankingEntry와 같은 정의)
  rejected_certifications: number; approved_certifications: number;
}
interface AdminCertification extends Certification {
  participant_id: number; nickname: string;
  image_hash: string;
  duplicate_of: number | null;   // 같은 이미지 해시의 최초 인증 ID(중복 의심)
  image_url: string | null;      // /api/admin/certifications/{id}/image
}
// 범위: 가격 파라미터는 10원 단위로 10원~1,000,000,000원, reward_cash 0~100,000,000,
// virtual_liquidity 0~10^15, coin_cap·coin_calm_cap (0, 10], coin_floor·coin_calm_floor (-1, 0),
// coin_calm_rounds 0~100, 실수 파라미터는 유한값만(NaN·Infinity는 422).
interface Params {
  coin_p_up: number; coin_up_exp: number; coin_down_exp: number;
  coin_cap: number; coin_floor: number; coin_price_cap: number | null;
  coin_calm_rounds: number;              // 1회차부터 이 회차까지 안정기 상·하한(기본 3)
  coin_calm_cap: number; coin_calm_floor: number;   // 안정기 상·하한(0.3, -0.1)
  stock_sensitivity: number; stock_min_price: number; virtual_liquidity: number;
  daily_buy_limit_ratio: number;
  reward_cash: number;                   // 인증 1건당 지급 현금(기본 250,000원 = 시드의 1/4)
  certification_cutoff: string;          // "23:59"
  verified_only_trading?: boolean | null; // 인증된 참가자만 거래. PUT에서 null·생략이면 현재 값 유지
}
interface SettlementLog {
  id: number; round: number; trade_day: string; effective_day: string; created_at: string;
  stocks: { code: string; buy_amount: number; adjusted_amount: number;
            concentration: number | null; rate: number; old_price: number; new_price: number }[];
  coin: { p: number; x: number; direction: "up" | "down"; rate: number; old_price: number; new_price: number;
          calm: boolean };   // 초반 안정기 상·하한으로 뽑았는지(v0.4 전 기록은 false)
  params: Params;
}
interface SimulationDaily {
  days: number; up_ratio: number; mean_up: number; mean_down: number; mean: number; mean_log: number;
  quantiles: { q: number; rate: number }[];
}
interface SimulationReport {
  paths: number; rounds: number; seed: number | null; price_cap: number | null;
  calm_rounds: number;                  // 경로마다 안정기로 돈 회차 수(1회차부터)
  daily: SimulationDaily | null;        // 평소 회차만. 모든 회차가 안정기면 null
  calm_daily: SimulationDaily | null;   // 안정기 회차만. 안정기가 없으면 null
  cumulative: { quantiles: { q: number; multiple: number }[]; prob_above: { multiple: number; prob: number }[];
                cap_hit_ratio: number };
}
interface BatchResult { action: "open" | "settle" | "advance"; day: string; detail: Record<string, unknown>; }
interface AuditEntry { id: number; at: string; actor: string; action: string; detail: Record<string, unknown>; }
```

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| GET | `/api/admin/participants` | – | `AdminParticipant[]` |
| PATCH | `/api/admin/participants/{id}` | `{status?, verified?}` | `AdminParticipant` — `verified: true`면 관리자 인증 처리, `false`면 인증 취소 |
| GET | `/api/admin/trading-access` | – | `{verified_only}` |
| PUT | `/api/admin/trading-access` | `{verified_only}` | `{verified_only}` — '인증된 참가자만 거래' 스위치. 파라미터(`verified_only_trading`)로 저장되어 이력·감사 로그에 남는다 |
| GET | `/api/admin/certifications` | `?status=pending` | `AdminCertification[]` |
| GET | `/api/admin/certifications/{id}/image` | – | 이미지 |
| POST | `/api/admin/certifications/{id}/review` | `{approve: boolean, reason?: string}` | `AdminCertification` / 409 `ALREADY_REVIEWED`, 422 `REASON_REQUIRED` |
| GET | `/api/admin/params` | – | `Params` |
| PUT | `/api/admin/params` | `Params` | `Params` |
| PUT | `/api/admin/prices/{day}/{code}` | `{price, reason}` | `PricePoint` / 409 `DAY_ALREADY_OPENED` |
| POST | `/api/admin/batch/open` | `{day?}` (기본 오늘) | `BatchResult` |
| POST | `/api/admin/batch/settle` | `{day?}` | `BatchResult` |
| POST | `/api/admin/batch/run-due` | – | `BatchResult[]` (현재 시각에 밀린 배치 실행) |
| GET | `/api/admin/qa` | – | `{enabled: boolean}` — QA 도구 사용 가능 여부(`STUDY_INVEST_QA_TOOLS`). 화면이 QA 버튼을 보일지 정한다 |
| POST | `/api/admin/qa/advance-price` | – | `BatchResult`(`action: "advance"`, `day`는 새로 공시된 운영일) / 403 `QA_DISABLED`, 409 `NO_ROUND`(마지막 운영일. 무제한 모드에는 없음) — 최신 공시일을 시각과 무관하게 정산하고 다음 운영일 시작가를 바로 공시한다(이미 정산됐다면 공시만, 공시된 날이 없으면 이벤트 첫날 공시만). 한 트랜잭션이며 감사 로그에 `qa.advance_price`가 남는다 |
| GET | `/api/admin/settlements` | – | `SettlementLog[]` |
| GET | `/api/admin/audit` | `?limit=200` | `AuditEntry[]` |
| GET | `/api/admin/db-pools` | – | `{api: PoolStatus, batch: PoolStatus}` — 앱 연결 풀 현황(`size` 설정 크기, `opened` 열린 연결, `checked_out` 사용 중, `idle`, `overflow` 초과분, `timeout`) |
| GET | `/api/admin/simulate/options` | – | `{paths: IntRange, rounds: IntRange}` (`IntRange = {min, max, default}`) — 시뮬레이터 입력 한계. 서버 스키마에서 생성되며 화면 입력 범위의 유일한 출처 |
| POST | `/api/admin/simulate` | `{paths?=10000, rounds?=10, seed?, use_price_cap?=false}` | `SimulationReport` |

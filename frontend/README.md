# 프론트엔드 (React + TypeScript + Vite)

공부장려 모의투자 이벤트의 참가자·관리자 웹 화면이다. API 계약은 [`docs/dev/api.md`](../docs/dev/api.md), 디자인 플랜은
[`DESIGN.md`](DESIGN.md)를 따른다.

## 스크립트

| 명령 | 설명 |
|---|---|
| `npm install` | 의존성 설치 (Node 22) |
| `npm run dev` | 개발 서버 `http://localhost:5173`. `/api` 요청은 `http://localhost:8000`(FastAPI)으로 프록시 |
| `npm run build` | `tsc -b` 타입 검사 후 `dist/`로 번들 |
| `npm run typecheck` / `npm run lint` | 타입 검사만 (`tsc -b`) |
| `npm test` | vitest 감시 모드. CI에서는 `npm test -- --run` |
| `npm run preview` | 빌드 결과 미리보기 |

## 구조: 공용 컴포넌트 먼저

화면은 공용 컴포넌트만 조합해서 만든다. 페이지에는 전용 CSS를 거의 두지 않는다.

```
src/
  styles/tokens.css      디자인 토큰(색·간격·반경·서체·그림자). 라이트/다크 모두 여기서만 정의
  styles/global.css      리셋, 포커스 링, sr-only
  lib/format.ts          금액·비율·날짜 포맷터 (Intl ko-KR)
  lib/market.ts          EventInfo → 장 운영 상태 문구
  components/ui/         공용 컴포넌트 라이브러리 (index.ts 배럴, 컴포넌트마다 폴더 + CSS 모듈)
  components/app/        도메인 조합 컴포넌트 (시세판, 장 상태 히어로, 상태 배지, 로드 오류)
  api/                   types.ts(계약 미러), client.ts(fetch 래퍼·ApiError), endpoints.ts, useApi 훅
  auth/                  AuthContext(참가자 세션), RequireAuth(비로그인 → /login)
  pages/                 라우트별 화면
```

- 살아있는 스타일 가이드: **`/ui`** — 모든 공용 컴포넌트와 변형을 한 화면에 보여준다(라이트/다크 전환 포함).
- 시장 관례: 상승 빨강(`--color-up`), 하락 파랑(`--color-down`), 보합 회색(`--color-flat`).
- 참가자 토큰은 `localStorage`, 관리자 키는 `sessionStorage`에 저장한다(접근 실패 시 메모리로 대체).

## 라우트

| 경로 | 화면 | 로그인 |
|---|---|---|
| `/` | 시장: 장 운영 상태·회차, 이벤트 일정, 시세판 | 불필요 |
| `/instruments/:code` | 가격 이력 차트 + 주문 | 주문만 필요 |
| `/portfolio` | 총자산·현금·평가손익·수익률, 보유 종목, 최근 주문 | 필요 |
| `/certification` | 인증 사진 올리기, 도장판, 인증 내역 | 필요 |
| `/ranking` | 총자산 순위 | 불필요(로그인 시 내 순위 강조) |
| `/login`, `/register` | 로그인, 참가 신청 | — |
| `/admin` | 관리자 키 입력 후 검수·참가자·파라미터·배치·가격 개입·시뮬레이터·감사 로그 | 관리자 키 |
| `/ui` | 컴포넌트 목록(스타일 가이드) | — |

## 개발 프록시

`vite.config.ts`의 `server.proxy`가 `/api` → `http://localhost:8000`으로 넘긴다. 백엔드를 먼저 띄운 뒤 `npm run dev`를 실행한다.
Docker 배포에서는 `Caddyfile`(Caddy)이 같은 역할을 한다.

## 링크 공유 미리보기

`public/images/study-invest-preview.jpg`는 공부 책상·청잉크·형광펜 콘셉트의 1200×630 JPEG다.
Open Graph와 Twitter 메타태그는 React 실행 전의 HTML에 포함되므로 공유 크롤러가 읽을 수 있다.
제작 방향과 프롬프트는 [`docs/preview-image.md`](docs/preview-image.md)에 기록했다.

공개 배포 시 `VITE_SITE_URL`에 실제 웹 주소를 지정한다(경로·쿼리·해시 제외).
이미지 주소와 `og:url`은 이 값을 기준으로 빌드 시 생성된다.

```bash
VITE_SITE_URL=https://study.example.com npm run build
```

Docker Compose는 저장소 루트 `.env`의 `VITE_SITE_URL`을 빌드 인자로 전달한다.
주소를 바꾸면 `docker compose build frontend` 후 프론트엔드 컨테이너를 다시 생성한다.
로컬 개발·CI에서 비워 두면 이미지는 루트 상대 경로를 사용하고 `og:url`은 생략한다.
공유 서비스 호환성을 위해 공개 배포에서는 반드시 실제 주소를 설정한다.

배포 후 `/images/study-invest-preview.jpg`가 로그인 없이 `image/jpeg`로 반환되는지 확인한다.
기존에 공유한 링크는 공유 서비스 캐시가 남을 수 있어 해당 서비스의 미리보기 재수집이 필요할 수 있다.

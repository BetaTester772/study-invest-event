# 공유 미리보기 이미지

- 파일: `public/images/study-invest-preview.jpg` (1200×630, JPEG)
- 기존 `DESIGN.md`의 공부 책상·청잉크·형광펜 소재를 따른다.
- 제작: 기본 imagegen 도구. 문구를 포함한 이미지를 생성한 뒤 배포용 JPEG로 크기와 용량만 최적화했다.
- 실제 서비스 화면이나 투자 성과를 묘사하지 않는 이벤트 표지다.
- 프론트엔드 HTML의 Open Graph / Twitter 미리보기에서 사용한다.

## 생성 프롬프트

```text
Use case: ads-marketing.
Asset type: final Korean website social link preview, landscape 1200 x 630 pixels (1.905:1). A beautifully art-directed, believable photographed study-desk editorial cover, matching a Korean study encouragement simulated investing event. The visual must feel made by a skilled human designer, restrained and specific, not generic AI art.
Composition: cool white #F5F7FB matte paper background. Left 60 percent clean typographic space, generous 70px safe margins. Right 40 percent a tightly composed overhead real-life still life of an open slightly worn squared-paper study notebook, a simple navy pen and one real yellow highlighter resting naturally. Real paper fibers, subtle imperfect page edges, unforced soft daylight shadows. The notebook can have minimal handwritten short abstract ticks but NO charts, fake data, financial numbers, or additional legible text. Objects stay out of the title. No money, no coins, no floating objects, no 3D icons, no gradients, no decorative confetti.
Typography: exceptionally crisp, correct Korean rounded bold sans-serif in ink navy #1E2A5A, carefully left-aligned as an actual graphic design cover, not text physically on notebook.
Exact main headline in two lines:
"공부장려"
"모의투자"
Exact smaller subtitle underneath: "공부 인증으로 시작하는 2주 투자 게임"
Leave the bottom-left area below the subtitle empty, with only the paper surface. No footer keywords.
Only these texts. Text should remain easy to read at thumbnail size. The header occupies most of the left area. No English eyebrow, no button, no logo, no border framing the entire design. Yellow comes only from the actual highlighter on the desk. Color palette cool paper white, dark navy, restrained pencil gray. This is a polished Korean event identity, warm in spirit but cool-neutral in color. Photography should be mundane and tactile rather than hyperreal or glossy.
```

## 수정 프롬프트 — 하단 키워드 삭제

기본 imagegen 편집 도구로 왼쪽 아래 키워드 문구를 삭제했다. 제목·부제·책상 구도는 유지했다.

```text
Edit this exact website preview image. Remove ONLY the small bottom-left footer text '공부 인증 · 모의투자 · 랭킹' and seamlessly fill its former area with the same cool white paper surface and subtle natural texture. Keep the entire rest of the image unchanged: the big navy Korean title '공부장려 모의투자', the subtitle '공부 인증으로 시작하는 2주 투자 게임', their typography, positions and sizes, the notebook, pen, highlighter, cup, lighting, crop, and 1200×630 landscape proportions. No new text or objects. This is a precise localized text-removal edit, not a redesign.
```

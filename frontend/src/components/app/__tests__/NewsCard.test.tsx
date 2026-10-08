import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import type { NewsItem } from '../../../api';
import { NewsCard } from '../NewsCard';

function item(id: number, overrides: Partial<NewsItem> = {}): NewsItem {
  return {
    id,
    day: '2026-10-08',
    code: 'SAMSU',
    name: '삼수전자',
    kind: 'good',
    rate: 0.15,
    headline: `뉴스 ${id}`,
    subtitle: null,
    body: null,
    byline: null,
    ...overrides,
  };
}

function renderCard(news: NewsItem[], today = '2026-10-08') {
  return render(
    <MemoryRouter>
      <NewsCard news={news} today={today} />
    </MemoryRouter>,
  );
}

describe('NewsCard', () => {
  it("lists every one of today's news items when a day has several", () => {
    renderCard([
      item(3, { code: 'LB', name: 'LB', kind: 'bad', rate: 0.12, headline: 'LB 공장 화재' }),
      item(2, { code: 'SKLOW', name: 'SK로우닉스', headline: 'SK로우닉스 신제품 호평' }),
      item(1, { headline: '삼수전자 양산 성공' }),
    ]);
    const list = screen.getByRole('list', { name: '오늘의 뉴스' });
    const links = within(list).getAllByRole('link');
    expect(links.map((a) => a.textContent)).toEqual(['LB 공장 화재', 'SK로우닉스 신제품 호평', '삼수전자 양산 성공']);
    expect(links.map((a) => a.getAttribute('href'))).toEqual([
      '/instruments/LB',
      '/instruments/SKLOW',
      '/instruments/SAMSU',
    ]);
    expect(within(list).getByText('악재 -12%')).toBeInTheDocument();
    expect(within(list).getAllByText('호재 +15%')).toHaveLength(2);
  });

  it('keeps earlier days under the collapsed history, several per day', () => {
    renderCard([
      item(4, { headline: '오늘 뉴스' }),
      item(3, { day: '2026-10-07', code: 'LB', name: 'LB', headline: '어제 뉴스 A' }),
      item(2, { day: '2026-10-07', headline: '어제 뉴스 B' }),
    ]);
    expect(within(screen.getByRole('list', { name: '오늘의 뉴스' })).getAllByRole('link')).toHaveLength(1);
    expect(screen.getByText('지난 뉴스 2건')).toBeInTheDocument();
    const past = screen.getByRole('list', { name: '지난 뉴스', hidden: true });
    expect(within(past).getAllByRole('link', { hidden: true })).toHaveLength(2);
  });

  it('says so when nothing was announced today', () => {
    renderCard([item(1, { day: '2026-10-07' })]);
    expect(screen.getByText('오늘은 발표된 뉴스가 없습니다.')).toBeInTheDocument();
  });
});

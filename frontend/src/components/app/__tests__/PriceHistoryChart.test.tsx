import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import type { PricePoint } from '../../../api';
import { PriceHistoryChart } from '../PriceHistoryChart';

const PRICES = [75000, 71200, 73900, 80100, 78400, 82000, 79300, 85600, 83100, 88400, 91200];

function history(count = PRICES.length): PricePoint[] {
  return PRICES.slice(0, count).map((price, i) => ({
    day: `2026-10-${String(6 + i).padStart(2, '0')}`,
    price,
    change_rate: null,
    source: i === 0 ? 'initial' : 'settlement',
  }));
}

function legend() {
  return screen.getByRole('list', { name: '차트 범례' });
}

describe('PriceHistoryChart', () => {
  it('offers every indicator and starts with the two moving averages on', () => {
    render(<PriceHistoryChart history={history()} name="삼수전자" />);
    for (const name of [
      '이동평균 3일',
      '이동평균 5일',
      '지수이동평균 5일',
      '볼린저 밴드',
      'RSI',
      'MACD',
      '일간 변동률',
    ]) {
      expect(screen.getByRole('checkbox', { name })).toBeInTheDocument();
    }
    expect(screen.getByRole('checkbox', { name: '이동평균 3일' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: '이동평균 5일' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'RSI' })).not.toBeChecked();
    expect(screen.queryByRole('heading', { name: /RSI/ })).not.toBeInTheDocument();
  });

  it('shows the latest value of each line in the legend', () => {
    render(<PriceHistoryChart history={history()} name="삼수전자" />);
    const items = within(legend());
    expect(items.getByText('시작가').parentElement).toHaveTextContent('91,200원');
    // SMA(3) of the last three prices: (83,100 + 88,400 + 91,200) / 3 = 87,566.67
    expect(items.getByText('이동평균 3일').parentElement).toHaveTextContent('87,567원');
    // SMA(5): (79,300 + 85,600 + 83,100 + 88,400 + 91,200) / 5 = 85,520
    expect(items.getByText('이동평균 5일').parentElement).toHaveTextContent('85,520원');
  });

  it('adds and removes lines and panels as chips are toggled', async () => {
    const user = userEvent.setup();
    render(<PriceHistoryChart history={history()} name="삼수전자" />);

    await user.click(screen.getByRole('checkbox', { name: '지수이동평균 5일' }));
    expect(within(legend()).getByText('지수이동평균 5일')).toBeInTheDocument();

    await user.click(screen.getByRole('checkbox', { name: '볼린저 밴드' }));
    expect(within(legend()).getByText(/볼린저 밴드 \(5일, ±2σ\)/)).toBeInTheDocument();

    await user.click(screen.getByRole('checkbox', { name: 'RSI' }));
    await user.click(screen.getByRole('checkbox', { name: 'MACD' }));
    await user.click(screen.getByRole('checkbox', { name: '일간 변동률' }));
    expect(screen.getByRole('heading', { name: 'RSI (5일)' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'MACD (3·5·3일)' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '일간 변동률' })).toBeInTheDocument();

    await user.click(screen.getByRole('checkbox', { name: 'RSI' }));
    expect(screen.queryByRole('heading', { name: /RSI/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: '이동평균 3일' }));
    expect(within(legend()).queryByText('이동평균 3일')).not.toBeInTheDocument();
  });

  it('says when an indicator needs more days instead of drawing nothing', async () => {
    const user = userEvent.setup();
    render(<PriceHistoryChart history={history(4)} name="삼수전자" />);
    // 4 days: SMA(3) exists, SMA(5) does not yet
    expect(within(legend()).getByText('이동평균 3일').parentElement).toHaveTextContent('75,067원');
    expect(within(legend()).getByText('이동평균 5일').parentElement).toHaveTextContent('5일째부터');

    await user.click(screen.getByRole('checkbox', { name: 'RSI' }));
    await user.click(screen.getByRole('checkbox', { name: 'MACD' }));
    expect(screen.getByText('6일째부터 표시됩니다.')).toBeInTheDocument();
    expect(screen.getByText('5일째부터 표시됩니다.')).toBeInTheDocument();
  });

  it('moves the legend readout with the hover position', () => {
    render(<PriceHistoryChart history={history()} name="삼수전자" />);
    const svg = screen.getAllByRole('img')[0] as HTMLElement;
    // jsdom has no layout: the chart falls back to 640 units wide, the plot spans x = 64…624 over 11 days,
    // so x = 344 is the 6th day (index 5, 10/11).
    fireEvent.pointerMove(svg, { clientX: 344 });
    expect(within(legend()).getByText('시작가').parentElement).toHaveTextContent('82,000원');
    // SMA(3) at index 5: (80,100 + 78,400 + 82,000) / 3 = 80,166.67
    expect(within(legend()).getByText('이동평균 3일').parentElement).toHaveTextContent('80,167원');
    fireEvent.pointerLeave(svg);
    expect(within(legend()).getByText('시작가').parentElement).toHaveTextContent('91,200원');
  });

  it('shares the hover position with the indicator panels', async () => {
    const user = userEvent.setup();
    render(<PriceHistoryChart history={history()} name="삼수전자" />);
    await user.click(screen.getByRole('checkbox', { name: '일간 변동률' }));
    const [main, panel] = screen.getAllByRole('img') as [HTMLElement, HTMLElement];
    expect(panel).toHaveAccessibleName(/일간 변동률.*\+3\.17%/); // latest day: 91,200 / 88,400 − 1
    fireEvent.pointerMove(main, { clientX: 344 });
    // 10/11 vs 10/10: 82,000 / 78,400 − 1 = +4.59%
    expect(panel).toHaveAccessibleName(/일간 변동률.*\+4\.59%/);
  });

  it('renders no controls for an empty history', () => {
    render(<PriceHistoryChart history={[]} name="삼수전자" />);
    expect(screen.getByText('아직 가격 이력이 없습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });
});

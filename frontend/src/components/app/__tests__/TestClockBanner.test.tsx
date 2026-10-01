import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { publicApi, type EventInfo } from '../../../api';
import { TestClockBanner, TestClockNotice } from '../TestClockBanner';

const clock = {
  scale: 24,
  real_now: '2026-10-01T13:08:21+09:00',
  next_open_at: '2026-10-01T14:22:30+09:00',
  next_close_at: '2026-10-01T13:45:00+09:00',
};

afterEach(() => vi.restoreAllMocks());

describe('TestClockNotice', () => {
  it('lists the upcoming real times, soonest first', () => {
    const { container } = render(<TestClockNotice clock={clock} />);
    expect(screen.getByText('QA 테스트 시계예요. 실제 1시간이 이벤트 하루예요.')).toBeInTheDocument();
    expect(container).toHaveTextContent('실제 시각으로 다음 장 마감(18:00) 13:45:00, 다음 공시(09:00) 14:22:30이에요.');
  });

  it('shows only what is left on the last day', () => {
    const { container } = render(<TestClockNotice clock={{ ...clock, next_open_at: null }} />);
    expect(container).toHaveTextContent('실제 시각으로 다음 장 마감(18:00) 13:45:00이에요.');
    expect(container).not.toHaveTextContent('다음 공시');
  });

  it('says the event is over when nothing is left', () => {
    render(<TestClockNotice clock={{ ...clock, next_open_at: null, next_close_at: null }} />);
    expect(screen.getByText(/테스트 시계로 이벤트 기간이 끝났어요/)).toBeInTheDocument();
  });
});

describe('TestClockBanner', () => {
  it('renders nothing on the real clock', async () => {
    const spy = vi.spyOn(publicApi, 'event').mockResolvedValue({ clock: null } as EventInfo);
    const { container } = render(<TestClockBanner />);
    await vi.waitFor(() => expect(spy).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the notice under a test clock', async () => {
    vi.spyOn(publicApi, 'event').mockResolvedValue({ clock } as EventInfo);
    render(<TestClockBanner />);
    expect(await screen.findByText('14:22:30')).toBeInTheDocument();
  });
});

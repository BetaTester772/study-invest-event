import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { publicApi, type EventInfo } from '../../../api';
import { TestClockBanner, TestClockNotice } from '../TestClockBanner';

const clock = {
  scale: 24,
  real_now: '2026-10-01T13:08:21+09:00',
  next_open_at: '2026-10-01T13:22:30+09:00',
  next_close_at: '2026-10-01T13:45:00+09:00',
};

afterEach(() => vi.restoreAllMocks());

describe('TestClockNotice', () => {
  it('shows the day length and the next real batch times', () => {
    render(<TestClockNotice clock={clock} />);
    expect(screen.getByText('QA 테스트 시계예요. 실제 1시간이 이벤트 하루예요.')).toBeInTheDocument();
    expect(screen.getByText('13:22:30')).toBeInTheDocument();
    expect(screen.getByText('13:45:00')).toBeInTheDocument();
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
    expect(await screen.findByText('13:22:30')).toBeInTheDocument();
  });
});

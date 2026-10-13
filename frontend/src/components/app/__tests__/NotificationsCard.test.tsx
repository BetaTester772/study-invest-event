import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { NotificationInbox } from '../../../api';
import { NotificationsCard } from '../NotificationsCard';

const inbox: NotificationInbox = {
  unread: 1,
  items: [
    { id: 3, title: '보상 안내', body: '첫 줄\n둘째 줄', created_at: '2026-10-13T16:00:00+09:00', personal: true, read_at: null },
    { id: 2, title: '지난 공지', body: '본문', created_at: '2026-10-12T10:00:00+09:00', personal: false, read_at: '2026-10-12T11:00:00+09:00' },
  ],
};

describe('NotificationsCard', () => {
  it('marks unread notifications and shows the count', () => {
    render(<NotificationsCard inbox={inbox} onRead={() => {}} />);
    expect(screen.getByLabelText('안 읽은 알림 1개')).toBeInTheDocument();
    const list = screen.getByRole('list', { name: '알림' });
    const items = within(list).getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('새 알림');
    expect(items[0]).toHaveTextContent('나에게');
    expect(items[1]).not.toHaveTextContent('새 알림');
  });

  it('reads one notification when opened and all with the button', () => {
    const onRead = vi.fn();
    render(<NotificationsCard inbox={inbox} onRead={onRead} />);
    const details = screen.getByText('보상 안내').closest('details') as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event('toggle'));
    expect(onRead).toHaveBeenCalledWith([3]);
    fireEvent.click(screen.getByRole('button', { name: '모두 읽음' }));
    expect(onRead).toHaveBeenLastCalledWith();
  });

  it('does not re-read an already read notification', () => {
    const onRead = vi.fn();
    render(<NotificationsCard inbox={inbox} onRead={onRead} />);
    const details = screen.getByText('지난 공지').closest('details') as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event('toggle'));
    expect(onRead).not.toHaveBeenCalled();
  });

  it('shows an empty state and no button when there is nothing', () => {
    render(<NotificationsCard inbox={{ unread: 0, items: [] }} onRead={() => {}} />);
    expect(screen.getByText('아직 받은 알림이 없습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '모두 읽음' })).not.toBeInTheDocument();
  });
});

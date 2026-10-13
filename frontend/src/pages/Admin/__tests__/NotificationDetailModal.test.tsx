import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { adminApi, type AdminNotificationDetail } from '../../../api';
import { ToastProvider } from '../../../components/ui';
import { NotificationDetailModal } from '../NotificationDetailModal';

const detail: AdminNotificationDetail = {
  id: 1,
  title: '공지',
  body: '첫 줄\n둘째 줄',
  created_at: '2026-10-13T16:25:00+09:00',
  updated_at: null,
  participant_id: null,
  nickname: null,
  read_count: 1,
  recipients: 2,
  readers: [
    { participant_id: 3, nickname: '앨리스', read_at: '2026-10-13T16:30:00+09:00' },
    { participant_id: 4, nickname: '밥', read_at: null },
  ],
};

afterEach(() => vi.restoreAllMocks());

function renderModal(onChanged = () => {}) {
  return render(
    <ToastProvider>
      <NotificationDetailModal id={1} onClose={() => {}} onChanged={onChanged} />
    </ToastProvider>,
  );
}

describe('NotificationDetailModal', () => {
  it('shows the body and who has and has not read it', async () => {
    vi.spyOn(adminApi, 'notification').mockResolvedValue(detail);
    renderModal();
    expect(await screen.findByText('#3 앨리스')).toBeInTheDocument();
    expect(screen.getByText('#4 밥')).toBeInTheDocument();
    expect(screen.getByText('안 읽음')).toBeInTheDocument();
    expect(screen.getByText('받는 사람 2명 중 1명 읽음, 1명 안 읽음')).toBeInTheDocument();
    expect(document.body).toHaveTextContent('첫 줄');
  });

  it('edits title and body and can reset reads', async () => {
    vi.spyOn(adminApi, 'notification').mockResolvedValue(detail);
    const update = vi
      .spyOn(adminApi, 'updateNotification')
      .mockResolvedValue({ ...detail, title: '공지(정정)', read_count: 0, updated_at: '2026-10-13T17:00:00+09:00' });
    const onChanged = vi.fn();
    renderModal(onChanged);
    fireEvent.click(await screen.findByRole('button', { name: '수정' }));
    fireEvent.change(screen.getByLabelText(/제목/), { target: { value: '공지(정정)' } });
    fireEvent.click(screen.getByLabelText('읽은 사람에게도 다시 새 알림으로 표시'));
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(1, { title: '공지(정정)', body: '첫 줄\n둘째 줄', reset_reads: true }),
    );
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(await screen.findByText('마지막 수정')).toBeInTheDocument();
  });

  it('ignores a save that finishes after another notification was opened', async () => {
    const other: AdminNotificationDetail = { ...detail, id: 2, title: '다른 알림', body: '다른 내용', readers: [] };
    vi.spyOn(adminApi, 'notification').mockImplementation(async (id) => (id === 1 ? detail : other));
    let finish: (d: AdminNotificationDetail) => void = () => {};
    vi.spyOn(adminApi, 'updateNotification').mockImplementation(
      () => new Promise<AdminNotificationDetail>((resolve) => (finish = resolve)),
    );
    const view = (id: number) => (
      <ToastProvider>
        <NotificationDetailModal id={id} onClose={() => {}} onChanged={() => {}} />
      </ToastProvider>
    );
    const { rerender } = render(view(1));
    fireEvent.click(await screen.findByRole('button', { name: '수정' }));
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    rerender(view(2));
    expect(await screen.findByText('다른 내용')).toBeInTheDocument();
    finish({ ...detail, title: '저장된 옛 알림' });
    await waitFor(() => expect(screen.queryByText('저장된 옛 알림')).not.toBeInTheDocument());
    expect(screen.getByText('다른 내용')).toBeInTheDocument();
  });
});

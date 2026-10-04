import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { publicApi, type EventInfo, type Participant } from '../../../api';
import * as auth from '../../../auth/AuthContext';
import { EmailVerificationBanner } from '../EmailVerificationBanner';

const ME: Participant = {
  id: 1,
  nickname: 'kim',
  status: 'normal',
  joined_at: '2026-10-06T09:00:00+09:00',
  masked_email: 'k***@g.skku.edu',
  verified: false,
  email_verified: false,
  needs_profile: false,
};

function renderWith(participant: Participant, verifiedOnly: boolean) {
  vi.spyOn(auth, 'useAuth').mockReturnValue({ participant } as auth.AuthContextValue);
  const event = vi.spyOn(publicApi, 'event').mockResolvedValue({
    signup: { email_verification: false, verified_only_trading: verifiedOnly },
  } as EventInfo);
  render(
    <MemoryRouter>
      <EmailVerificationBanner />
    </MemoryRouter>,
  );
  return event;
}

describe('EmailVerificationBanner', () => {
  afterEach(() => vi.restoreAllMocks());

  it('asks unverified participants to verify only while the admin switch is on', async () => {
    renderWith(ME, true);
    expect(await screen.findByText('지금은 인증된 참가자만 거래할 수 있어요')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '인증하기' })).toHaveAttribute('href', '/verify-email');
  });

  it('stays hidden while everyone can trade', async () => {
    const event = renderWith(ME, false);
    await waitFor(() => expect(event).toHaveBeenCalled());
    expect(screen.queryByText(/인증된 참가자만/)).not.toBeInTheDocument();
  });

  it('does not even load settings for verified participants', () => {
    const event = renderWith({ ...ME, verified: true }, true);
    expect(event).not.toHaveBeenCalled();
    expect(screen.queryByText(/인증된 참가자만/)).not.toBeInTheDocument();
  });
});

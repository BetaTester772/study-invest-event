import { useLocation } from 'react-router-dom';
import { publicApi, useApi } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { Alert, Container, LinkButton } from '../ui';

/**
 * 관리자가 '인증된 참가자만 거래'를 켰을 때 미인증 참가자에게 인증을 안내한다.
 * 평소(꺼져 있을 때)에는 미인증이어도 모든 기능을 쓸 수 있어 아무것도 보이지 않는다.
 */
export function EmailVerificationBanner() {
  const { participant } = useAuth();
  const location = useLocation();
  const unverified = !!participant && !participant.verified;
  const event = useApi(() => publicApi.event(), [], { enabled: unverified, refreshInterval: 60_000 });
  if (!unverified || !event.data?.signup.verified_only_trading || location.pathname === '/verify-email') return null;
  return (
    <Container padTop>
      <Alert
        tone="warning"
        title="지금은 인증된 참가자만 거래할 수 있어요"
        action={
          <LinkButton to="/verify-email" size="sm" state={{ from: `${location.pathname}${location.search}` }}>
            인증하기
          </LinkButton>
        }
      >
        가입할 때 등록한 학교 메일로 코드를 받아 인증하면 바로 다시 거래할 수 있어요. 시세·내 자산 보기와 공부 인증은
        그대로 쓸 수 있어요.
      </Alert>
    </Container>
  );
}

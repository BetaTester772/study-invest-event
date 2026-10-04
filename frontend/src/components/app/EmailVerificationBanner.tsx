import { useLocation } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { Alert, Container, LinkButton } from '../ui';

/** 메일 인증 도입 전에 가입한 참가자에게 재인증을 안내한다(인증 전에는 거래·공부 인증 불가). */
export function EmailVerificationBanner() {
  const { participant } = useAuth();
  const location = useLocation();
  if (!participant || participant.email_verified || location.pathname === '/verify-email') return null;
  return (
    <Container padTop>
      <Alert
        tone="warning"
        title="학교 메일 인증이 필요해요"
        action={
          <LinkButton to="/verify-email" size="sm" state={{ from: `${location.pathname}${location.search}` }}>
            인증하기
          </LinkButton>
        }
      >
        중복 가입을 막기 위해 모든 참가자가 학교 메일로 본인 확인을 해요. 인증 전에는 거래와 공부 인증을 할 수 없어요.
      </Alert>
    </Container>
  );
}

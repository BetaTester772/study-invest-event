import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Container, Spinner, Stack } from '../components/ui';
import { useAuth } from './AuthContext';

/**
 * Redirects anonymous visitors to /login, remembering where they were going.
 * 학교 메일 인증 전 계정(메일 인증 도입 전 가입)은 /verify-email로 보낸다.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status, participant } = useAuth();
  const location = useLocation();
  if (status === 'loading') {
    return (
      <Container padTop>
        <Stack align="center">
          <Spinner size="lg" label="로그인 정보를 확인하는 중" />
        </Stack>
      </Container>
    );
  }
  if (status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  }
  if (participant && !participant.email_verified && location.pathname !== '/verify-email') {
    return <Navigate to="/verify-email" replace state={{ from: `${location.pathname}${location.search}` }} />;
  }
  return <>{children}</>;
}

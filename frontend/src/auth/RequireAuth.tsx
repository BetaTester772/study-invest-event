import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Container, Spinner, Stack } from '../components/ui';
import { useAuth } from './AuthContext';

/** Redirects anonymous visitors to /login, remembering where they were going. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
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
  return <>{children}</>;
}

import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { Alert, Button, Card, Container, PageHeader, Stack, Text, TextField, useToast } from '../../components/ui';

export function LoginPage() {
  const { login, status } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const from = (location.state as { from?: string } | null)?.from ?? '/';
  const [identity, setIdentity] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (status === 'authenticated' && !submitting) return <Navigate to={from} replace />;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!identity.trim() || !password) {
      setError('아이디와 비밀번호를 모두 입력해 주세요.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const p = await login(identity.trim(), password);
      toast.success(`${p.nickname}님, 반가워요`);
      navigate(from, { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === 'INVALID_CREDENTIALS'
          ? '아이디나 비밀번호가 맞지 않아요. 다시 확인해 주세요.'
          : err instanceof ApiError
            ? err.message
            : '로그인하지 못했어요. 잠시 뒤 다시 시도해 주세요.',
      );
      setSubmitting(false);
    }
  };

  return (
    <Container size="sm">
      <PageHeader title="로그인" description="참가 신청할 때 쓴 아이디로 로그인하세요." />
      <Card>
        <form onSubmit={onSubmit} noValidate>
          <Stack gap={4}>
            {error && <Alert tone="danger">{error}</Alert>}
            <TextField
              label="아이디"
              hint="사내 계정이나 학번처럼 참가 신청할 때 쓴 식별자예요."
              autoComplete="username"
              value={identity}
              onChange={(e) => setIdentity(e.target.value)}
              required
            />
            <TextField
              label="비밀번호"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <Button type="submit" size="lg" fullWidth loading={submitting}>
              로그인하기
            </Button>
            <Text size="sm" tone="muted">
              아직 참가하지 않았나요?{' '}
              <Link to="/register" state={location.state}>
                참가 신청하기
              </Link>
            </Text>
          </Stack>
        </form>
      </Card>
    </Container>
  );
}

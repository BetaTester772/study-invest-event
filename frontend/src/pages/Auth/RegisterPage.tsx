import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { Alert, Button, Card, Container, PageHeader, Stack, Text, TextField, useToast } from '../../components/ui';

interface Errors {
  identity?: string;
  nickname?: string;
  password?: string;
  confirm?: string;
  form?: string;
}

export function validateRegister(identity: string, nickname: string, password: string, confirm: string): Errors {
  const errors: Errors = {};
  if (!identity.trim()) errors.identity = '아이디를 입력해 주세요.';
  const nick = nickname.trim();
  if (nick.length < 2 || nick.length > 20) errors.nickname = '닉네임은 2~20자로 정해 주세요.';
  if (password.length < 8) errors.password = '비밀번호는 8자 이상이어야 해요.';
  if (confirm !== password) errors.confirm = '비밀번호가 서로 달라요. 같은 비밀번호를 한 번 더 입력해 주세요.';
  return errors;
}

export function RegisterPage() {
  const { register, status } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const from = (location.state as { from?: string } | null)?.from ?? '/';
  const [identity, setIdentity] = useState('');
  const [nickname, setNickname] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);

  if (status === 'authenticated' && !submitting) return <Navigate to={from} replace />;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const v = validateRegister(identity, nickname, password, confirm);
    setErrors(v);
    if (Object.keys(v).length > 0) return;
    setSubmitting(true);
    try {
      await register(identity.trim(), nickname.trim(), password);
      toast.success('참가 신청을 마쳤어요', '1,000,000원으로 시작해요. 첫 종목을 골라 보세요.');
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === 'IDENTITY_TAKEN') {
        setErrors({ identity: '이미 참가한 아이디예요. 로그인해 주세요.' });
      } else if (err instanceof ApiError && err.code === 'NICKNAME_TAKEN') {
        setErrors({ nickname: '다른 참가자가 쓰는 닉네임이에요. 다른 닉네임을 골라 주세요.' });
      } else {
        setErrors({ form: err instanceof ApiError ? err.message : '참가 신청을 하지 못했어요. 잠시 뒤 다시 시도해 주세요.' });
      }
      setSubmitting(false);
    }
  };

  return (
    <Container size="sm">
      <PageHeader
        title="참가 신청"
        description="한 사람당 한 계정이에요. 모두 같은 1,000,000원으로 시작하고, 중간에 들어와도 똑같이 받아요."
      />
      <Card>
        <form onSubmit={onSubmit} noValidate>
          <Stack gap={4}>
            {errors.form && <Alert tone="danger">{errors.form}</Alert>}
            <TextField
              label="아이디"
              hint="사내 계정이나 학번처럼 나를 확인할 수 있는 값이에요. 공개되지 않아요."
              autoComplete="username"
              value={identity}
              onChange={(e) => setIdentity(e.target.value)}
              error={errors.identity}
              required
            />
            <TextField
              label="닉네임"
              hint="2~20자. 랭킹에는 닉네임만 보여요."
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              error={errors.nickname}
              maxLength={20}
              required
            />
            <TextField
              label="비밀번호"
              type="password"
              hint="8자 이상"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={errors.password}
              required
            />
            <TextField
              label="비밀번호 확인"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              error={errors.confirm}
              required
            />
            <Button type="submit" size="lg" fullWidth loading={submitting}>
              참가 신청하기
            </Button>
            <Text size="sm" tone="muted">
              이미 참가했나요? <Link to="/login" state={location.state}>로그인하기</Link>
            </Text>
          </Stack>
        </form>
      </Card>
    </Container>
  );
}

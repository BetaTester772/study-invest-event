import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { Alert, Button, Card, Container, PageHeader, Stack, Text, TextField, useToast } from '../../components/ui';
import { CODE_ERRORS, SchoolEmailFields, codeError, schoolEmailError } from './SchoolEmailFields';

interface Errors {
  email?: string;
  code?: string;
  password?: string;
  confirm?: string;
  form?: string;
}

export function validateReset(email: string, code: string, password: string, confirm: string): Errors {
  const errors: Errors = {};
  const emailErr = schoolEmailError(email);
  if (emailErr) errors.email = emailErr;
  const codeErr = codeError(code);
  if (codeErr) errors.code = codeErr;
  if (password.length < 8) errors.password = '비밀번호는 8자 이상이어야 해요.';
  if (confirm !== password) errors.confirm = '비밀번호가 서로 달라요. 같은 비밀번호를 한 번 더 입력해 주세요.';
  return errors;
}

/** 학교 메일로 받은 코드로 비밀번호를 바꾸고 바로 로그인한다. 다른 기기의 로그인은 끊긴다. */
export function ResetPasswordPage() {
  const { resetPassword } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const v = validateReset(email, code, password, confirm);
    setErrors(v);
    if (Object.keys(v).length > 0) return;
    setSubmitting(true);
    try {
      const p = await resetPassword({ email: email.trim(), code, password });
      toast.success('비밀번호를 바꿨어요', `${p.nickname}님, 새 비밀번호로 로그인했어요. 다른 기기에서는 로그아웃됐어요.`);
      navigate('/', { replace: true });
    } catch (err) {
      if (err instanceof ApiError && CODE_ERRORS.has(err.code)) {
        setErrors({ code: err.message });
      } else if (err instanceof ApiError && err.code === 'EMAIL_NOT_REGISTERED') {
        setErrors({ email: '이 학교 메일로 가입한 계정이 없어요.' });
      } else {
        setErrors({
          form: err instanceof ApiError ? err.message : '비밀번호를 바꾸지 못했어요. 잠시 뒤 다시 시도해 주세요.',
        });
      }
      setSubmitting(false);
    }
  };

  return (
    <Container size="sm">
      <PageHeader
        title="비밀번호 재설정"
        description="가입할 때 인증한 학교 메일로 코드를 받아 새 비밀번호를 정해요."
      />
      <Card>
        <form onSubmit={onSubmit} noValidate>
          <Stack gap={4}>
            {errors.form && <Alert tone="danger">{errors.form}</Alert>}
            <SchoolEmailFields
              purpose="reset"
              email={email}
              onEmailChange={setEmail}
              code={code}
              onCodeChange={setCode}
              emailError={errors.email}
              codeError={errors.code}
              onEmailError={(message) => setErrors((prev) => ({ ...prev, email: message }))}
            />
            <TextField
              label="새 비밀번호"
              type="password"
              hint="8자 이상. 학교 메일 비밀번호와 다르게 정해 주세요."
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={errors.password}
              required
            />
            <TextField
              label="새 비밀번호 확인"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              error={errors.confirm}
              required
            />
            <Button type="submit" size="lg" fullWidth loading={submitting}>
              비밀번호 바꾸기
            </Button>
            <Text size="sm" tone="muted">
              가입할 때 학교 메일을 등록하지 않은 예전 계정은 재설정할 수 없어요. 운영진에게 문의해 주세요.
              {' '}
              <Link to="/login">로그인으로 돌아가기</Link>
            </Text>
          </Stack>
        </form>
      </Card>
    </Container>
  );
}

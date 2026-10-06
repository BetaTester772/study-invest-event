import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError, authApi } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { Alert, Button, Card, Container, PageHeader, Stack, Text, TextField, useToast } from '../../components/ui';
import { CODE_ERRORS, CodeSender, codeError } from './SchoolEmailFields';
import { PASSWORD_HINT, WEAK_PASSWORD_MESSAGE } from './password';
import { useScrollToFormError } from '../../lib/useScrollToFormError';

interface Errors {
  identity?: string;
  code?: string;
  password?: string;
  confirm?: string;
  form?: string;
}

/** 1단계: 학번과 메일로 받은 코드. */
export function validateResetCode(identity: string, code: string): Errors {
  const errors: Errors = {};
  if (!identity.trim()) errors.identity = '학번을 입력해 주세요.';
  const codeErr = codeError(code);
  if (codeErr) errors.code = codeErr;
  return errors;
}

/** 2단계: 새 비밀번호. */
export function validateNewPassword(password: string, confirm: string): Errors {
  const errors: Errors = {};
  if (password.length < 8) errors.password = '비밀번호는 8자 이상이어야 합니다.';
  if (confirm !== password) errors.confirm = '비밀번호가 서로 다릅니다. 같은 비밀번호를 한 번 더 입력해 주세요.';
  return errors;
}

/**
 * 학번을 입력하면 그 계정의 등록 메일로 코드를 보낸다. 코드가 맞는지 먼저 확인한 뒤에
 * 새 비밀번호를 받고, 비밀번호를 바꾼 뒤 바로 로그인한다.
 * 코드는 등록 메일로만 간다(다른 주소로 받을 수 없다). 다른 기기의 로그인은 끊긴다.
 */
export function ResetPasswordPage() {
  const { resetPassword } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [step, setStep] = useState<'code' | 'password'>('code');
  const [identity, setIdentity] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [formRef] = useScrollToFormError(errors);
  const [submitting, setSubmitting] = useState(false);

  /** 코드·학번 오류면 칸 옆에 보여 주고 true. */
  const showCodeStepError = (err: unknown): boolean => {
    if (err instanceof ApiError && CODE_ERRORS.has(err.code)) {
      setErrors({ code: err.message });
      return true;
    }
    if (err instanceof ApiError && err.code === 'ACCOUNT_NOT_FOUND') {
      setErrors({ identity: err.message });
      return true;
    }
    return false;
  };

  const onVerify = async (e: FormEvent) => {
    e.preventDefault();
    const v = validateResetCode(identity, code);
    setErrors(v);
    if (Object.keys(v).length > 0) return;
    setSubmitting(true);
    try {
      await authApi.verifyPasswordResetCode({ identity: identity.trim(), code });
      setPassword('');
      setConfirm('');
      setStep('password');
    } catch (err) {
      if (!showCodeStepError(err)) {
        setErrors({
          form: err instanceof ApiError ? err.message : '코드를 확인하지 못했습니다. 잠시 뒤 다시 시도해 주세요.',
        });
      }
    } finally {
      setSubmitting(false);
    }
  };

  const onReset = async (e: FormEvent) => {
    e.preventDefault();
    const v = validateNewPassword(password, confirm);
    setErrors(v);
    if (Object.keys(v).length > 0) return;
    setSubmitting(true);
    try {
      const p = await resetPassword({ identity: identity.trim(), code, password });
      toast.success('비밀번호를 바꿨습니다', `${p.nickname}님, 새 비밀번호로 로그인했습니다. 다른 기기에서는 로그아웃됐습니다.`);
      navigate('/', { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === 'WEAK_PASSWORD') {
        setErrors({ password: WEAK_PASSWORD_MESSAGE });
      } else if (showCodeStepError(err)) {
        // 그 사이 코드가 만료됐거나 다시 받았다: 코드부터 다시 확인한다.
        setCode('');
        setStep('code');
      } else {
        setErrors({
          form: err instanceof ApiError ? err.message : '비밀번호를 바꾸지 못했습니다. 잠시 뒤 다시 시도해 주세요.',
        });
      }
      setSubmitting(false);
    }
  };

  const restart = () => {
    setCode('');
    setPassword('');
    setConfirm('');
    setErrors({});
    setStep('code');
  };

  return (
    <Container size="sm">
      <PageHeader
        title="비밀번호 재설정"
        description={
          step === 'code'
            ? '학번을 입력하면 가입할 때 등록한 학교 메일로 코드를 보냅니다. 받은 코드를 확인하면 새 비밀번호를 정할 수 있습니다.'
            : '코드를 확인했습니다. 새 비밀번호를 정하세요.'
        }
      />
      <Card>
        {step === 'code' ? (
          <form ref={formRef} onSubmit={onVerify} noValidate>
            <Stack gap={4}>
              {errors.form && <Alert tone="danger">{errors.form}</Alert>}
              <TextField
                label="학번"
                hint="숫자 10자리. 학교 메일 주소를 입력해도 됩니다."
                autoComplete="username"
                placeholder="2026310000"
                value={identity}
                onChange={(e) => setIdentity(e.target.value)}
                error={errors.identity}
                required
              />
              <CodeSender
                label="등록한 메일로 코드 받기"
                request={() => authApi.requestPasswordResetCode({ identity: identity.trim() })}
                validate={() => {
                  const message = identity.trim() ? undefined : '학번을 입력해 주세요.';
                  setErrors((prev) => ({ ...prev, identity: message }));
                  return message;
                }}
                onRequestError={(err) => {
                  if (err instanceof ApiError && err.code === 'ACCOUNT_NOT_FOUND') {
                    setErrors((prev) => ({ ...prev, identity: err.message }));
                    return true;
                  }
                  return false;
                }}
                code={code}
                onCodeChange={setCode}
                codeError={errors.code}
              />
              <Button type="submit" size="lg" fullWidth loading={submitting}>
                코드 확인
              </Button>
              <Text size="sm" tone="muted">
                가입할 때 학교 메일을 등록하지 않은 예전 계정은 재설정할 수 없습니다. 운영진에게 문의해 주세요.{' '}
                <Link to="/login">로그인으로 돌아가기</Link>
              </Text>
            </Stack>
          </form>
        ) : (
          <form ref={formRef} onSubmit={onReset} noValidate>
            <Stack gap={4}>
              {errors.form && <Alert tone="danger">{errors.form}</Alert>}
              <Alert tone="info">인증 코드를 확인했습니다. 학번 {identity.trim()}의 새 비밀번호를 입력해 주세요.</Alert>
              {/* 비밀번호 관리자가 어느 계정의 비밀번호인지 알 수 있게 */}
              <input type="hidden" autoComplete="username" value={identity.trim()} readOnly />
              <TextField
                label="새 비밀번호"
                type="password"
                hint={PASSWORD_HINT}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                error={errors.password}
                autoFocus
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
              <Button variant="secondary" fullWidth onClick={restart} disabled={submitting}>
                처음부터 다시 하기
              </Button>
            </Stack>
          </form>
        )}
      </Card>
    </Container>
  );
}

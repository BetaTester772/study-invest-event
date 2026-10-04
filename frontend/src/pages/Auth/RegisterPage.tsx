import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ApiError, publicApi, useApi, type ProfileFields as ProfileFieldsValue } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { Alert, Button, Card, Container, PageHeader, Stack, Text, TextField, useToast } from '../../components/ui';
import { EMPTY_PROFILE, ProfileFields, profileErrors, trimProfile, type ProfileErrors } from './ProfileFields';
import { CODE_ERRORS, PrivacyConsent, SchoolEmailFields, codeError, schoolEmailError } from './SchoolEmailFields';

interface Errors extends ProfileErrors {
  email?: string;
  code?: string;
  nickname?: string;
  password?: string;
  confirm?: string;
  consent?: string;
  form?: string;
}

export interface RegisterForm extends ProfileFieldsValue {
  email: string;
  code: string;
  nickname: string;
  password: string;
  confirm: string;
  consent: boolean;
}

/** requireCode: 학교 메일 인증 코드를 받는 운영(`signup.email_verification`)인지. */
export function validateRegister(f: RegisterForm, requireCode = true): Errors {
  const errors: Errors = profileErrors(f);
  const email = schoolEmailError(f.email);
  if (email) errors.email = email;
  const code = requireCode ? codeError(f.code) : undefined;
  if (code) errors.code = code;
  const nick = f.nickname.trim();
  if (nick.length < 2 || nick.length > 20) errors.nickname = '닉네임은 2~20자로 정해 주세요.';
  if (f.password.length < 8) errors.password = '비밀번호는 8자 이상이어야 해요.';
  if (f.confirm !== f.password) errors.confirm = '비밀번호가 서로 달라요. 같은 비밀번호를 한 번 더 입력해 주세요.';
  if (!f.consent) errors.consent = '개인정보 수집·이용에 동의해야 참가할 수 있어요.';
  return errors;
}

export function RegisterPage() {
  const { register, status } = useAuth();
  const event = useApi(() => publicApi.event(), []);
  // 설정을 못 받으면 코드 없는 가입 폼(기본값)을 보여 준다. 서버가 코드를 요구하면 CODE_REQUIRED로 알려 준다.
  const requireCode = event.data?.signup.email_verification ?? false;
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const from = (location.state as { from?: string } | null)?.from ?? '/';
  const [form, setForm] = useState<RegisterForm>({
    email: '',
    code: '',
    ...EMPTY_PROFILE,
    nickname: '',
    password: '',
    confirm: '',
    consent: false,
  });
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);
  const set = <K extends keyof RegisterForm>(key: K, value: RegisterForm[K]) => setForm((f) => ({ ...f, [key]: value }));

  if (status === 'authenticated' && !submitting) return <Navigate to={from} replace />;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const v = validateRegister(form, requireCode);
    setErrors(v);
    if (Object.keys(v).length > 0) return;
    setSubmitting(true);
    try {
      await register({
        email: form.email.trim(),
        ...(requireCode ? { code: form.code } : {}),
        ...trimProfile(form),
        nickname: form.nickname.trim(),
        password: form.password,
        privacy_consent: form.consent,
      });
      toast.success('참가 신청을 마쳤어요', '1,000,000원으로 시작해요. 첫 종목을 골라 보세요.');
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === 'EMAIL_TAKEN') {
        setErrors({ email: '이미 참가한 학교 메일이에요. 로그인해 주세요.' });
      } else if (err instanceof ApiError && (CODE_ERRORS.has(err.code) || err.code === 'CODE_REQUIRED')) {
        if (err.code === 'CODE_REQUIRED') event.refetch();
        setErrors({ code: err.message });
      } else if (err instanceof ApiError && err.code === 'STUDENT_ID_TAKEN') {
        setErrors({ student_id: '이미 다른 계정에 등록된 학번이에요. 본인 학번이 맞다면 운영진에게 문의해 주세요.' });
      } else if (err instanceof ApiError && err.code === 'NICKNAME_TAKEN') {
        setErrors({ nickname: '다른 참가자가 쓰는 닉네임이에요. 다른 닉네임을 골라 주세요.' });
      } else {
        setErrors({
          form: err instanceof ApiError ? err.message : '참가 신청을 하지 못했어요. 잠시 뒤 다시 시도해 주세요.',
        });
      }
      setSubmitting(false);
    }
  };

  return (
    <Container size="sm">
      <PageHeader
        title="참가 신청"
        description="학교 메일과 학번으로 한 사람당 한 계정만 만들 수 있어요. 모두 같은 1,000,000원으로 시작하고, 중간에 들어와도 똑같이 받아요."
      />
      <Card>
        <form onSubmit={onSubmit} noValidate>
          <Stack gap={4}>
            {errors.form && <Alert tone="danger">{errors.form}</Alert>}
            <SchoolEmailFields
              withCode={requireCode}
              hint={
                requireCode
                  ? undefined
                  : '@skku.edu 또는 @g.skku.edu. 비밀번호를 잊었을 때 재설정 코드를 받는 주소예요. 한 메일에 한 계정이에요.'
              }
              email={form.email}
              onEmailChange={(v) => set('email', v)}
              code={form.code}
              onCodeChange={(v) => set('code', v)}
              emailError={errors.email}
              codeError={errors.code}
              onEmailError={(message) => setErrors((prev) => ({ ...prev, email: message }))}
            />
            <ProfileFields
              value={{ name: form.name, student_id: form.student_id, department: form.department }}
              onChange={(p) => setForm((f) => ({ ...f, ...p }))}
              errors={errors}
            />
            <TextField
              label="닉네임"
              hint="2~20자. 랭킹에는 닉네임만 보여요."
              value={form.nickname}
              onChange={(e) => set('nickname', e.target.value)}
              error={errors.nickname}
              maxLength={20}
              required
            />
            <TextField
              label="비밀번호"
              type="password"
              hint="8자 이상. 학교 메일 비밀번호와 다르게 정해 주세요."
              autoComplete="new-password"
              value={form.password}
              onChange={(e) => set('password', e.target.value)}
              error={errors.password}
              required
            />
            <TextField
              label="비밀번호 확인"
              type="password"
              autoComplete="new-password"
              value={form.confirm}
              onChange={(e) => set('confirm', e.target.value)}
              error={errors.confirm}
              required
            />
            <PrivacyConsent checked={form.consent} onChange={(v) => set('consent', v)} error={errors.consent} />
            <Button type="submit" size="lg" fullWidth loading={submitting}>
              참가 신청하기
            </Button>
            <Text size="sm" tone="muted">
              이미 참가했나요?{' '}
              <Link to="/login" state={location.state}>
                로그인하기
              </Link>
            </Text>
          </Stack>
        </form>
      </Card>
    </Container>
  );
}

import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { Alert, Button, Card, Container, PageHeader, Stack, useToast } from '../../components/ui';
import { EMPTY_PROFILE, ProfileFields, profileErrors, trimProfile, type ProfileErrors } from './ProfileFields';
import { CODE_ERRORS, PrivacyConsent, SchoolEmailFields, codeError, schoolEmailError } from './SchoolEmailFields';

interface Errors extends ProfileErrors {
  email?: string;
  code?: string;
  consent?: string;
  form?: string;
}

/** 메일 인증 도입 전에 가입한 참가자의 학교 메일 재인증. 마치기 전에는 거래·공부 인증을 할 수 없다. */
export function VerifyEmailPage() {
  const { participant, verifyEmail } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const from = (location.state as { from?: string } | null)?.from ?? '/';
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [consent, setConsent] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);

  if (participant?.email_verified && !submitting) return <Navigate to={from} replace />;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const v: Errors = profileErrors(profile);
    const emailErr = schoolEmailError(email);
    if (emailErr) v.email = emailErr;
    const codeErr = codeError(code);
    if (codeErr) v.code = codeErr;
    if (!consent) v.consent = '개인정보 수집·이용에 동의해야 계속 참가할 수 있어요.';
    setErrors(v);
    if (Object.keys(v).length > 0) return;
    setSubmitting(true);
    try {
      await verifyEmail({ email: email.trim(), code, ...trimProfile(profile), privacy_consent: consent });
      toast.success('학교 메일 인증을 마쳤어요', '이제 학교 메일로도 로그인할 수 있어요.');
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === 'EMAIL_TAKEN') {
        setErrors({ email: '다른 계정이 이미 인증한 학교 메일이에요. 한 사람당 한 계정만 쓸 수 있어요.' });
      } else if (err instanceof ApiError && err.code === 'STUDENT_ID_TAKEN') {
        setErrors({ student_id: '이미 다른 계정에 등록된 학번이에요. 본인 학번이 맞다면 운영진에게 문의해 주세요.' });
      } else if (err instanceof ApiError && CODE_ERRORS.has(err.code)) {
        setErrors({ code: err.message });
      } else {
        setErrors({ form: err instanceof ApiError ? err.message : '인증하지 못했어요. 잠시 뒤 다시 시도해 주세요.' });
      }
      setSubmitting(false);
    }
  };

  return (
    <Container size="sm">
      <PageHeader
        title="학교 메일 인증"
        description="중복 가입을 막기 위해 모든 참가자가 학교 메일로 본인 확인을 하고 이름·학번·학과를 등록해요. 인증을 마쳐야 거래와 공부 인증을 할 수 있어요."
      />
      <Card>
        <form onSubmit={onSubmit} noValidate>
          <Stack gap={4}>
            {errors.form && <Alert tone="danger">{errors.form}</Alert>}
            <SchoolEmailFields
              email={email}
              onEmailChange={setEmail}
              code={code}
              onCodeChange={setCode}
              emailError={errors.email}
              codeError={errors.code}
              onEmailError={(message) => setErrors((prev) => ({ ...prev, email: message }))}
            />
            <ProfileFields value={profile} onChange={setProfile} errors={errors} />
            <PrivacyConsent checked={consent} onChange={setConsent} error={errors.consent} />
            <Button type="submit" size="lg" fullWidth loading={submitting}>
              인증하기
            </Button>
          </Stack>
        </form>
      </Card>
    </Container>
  );
}

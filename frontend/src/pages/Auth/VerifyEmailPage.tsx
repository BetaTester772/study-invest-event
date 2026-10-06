import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ApiError, meApi } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { Alert, Button, Card, Container, PageHeader, Stack, Text, useToast } from '../../components/ui';
import { EMPTY_PROFILE, ProfileFields, profileErrors, trimProfile, type ProfileErrors } from './ProfileFields';
import { CODE_ERRORS, CodeSender, PrivacyConsent, SchoolEmailFields, codeError, schoolEmailError } from './SchoolEmailFields';
import { useScrollToFormError } from '../../lib/useScrollToFormError';

interface Errors extends ProfileErrors {
  email?: string;
  code?: string;
  consent?: string;
  form?: string;
}

/**
 * 학교 메일 코드 인증. 보통은 등록 메일(가린 주소만 보여 줌)로 코드를 받아 코드만 입력한다.
 * '다른 메일로 인증하기'는 등록 메일을 잘못 적었을 때, 메일이 없는 예전 계정은 처음부터 주소를 입력한다.
 * 메일 코드로 아직 인증하지 않은 계정(미인증, 관리자 인증만)만 쓸 수 있다.
 */
export function VerifyEmailPage() {
  const { participant, verifyEmail } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const from = (location.state as { from?: string } | null)?.from ?? '/';
  const registered = participant?.masked_email ?? null;
  const needsProfile = participant?.needs_profile ?? false;
  const [otherEmail, setOtherEmail] = useState(registered == null);
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [consent, setConsent] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [formRef] = useScrollToFormError(errors);
  const [submitting, setSubmitting] = useState(false);

  if (participant?.email_verified && !submitting) return <Navigate to={from} replace />;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const v: Errors = needsProfile ? profileErrors(profile) : {};
    if (otherEmail) {
      const emailErr = schoolEmailError(email);
      if (emailErr) v.email = emailErr;
    }
    const codeErr = codeError(code);
    if (codeErr) v.code = codeErr;
    if (needsProfile && !consent) v.consent = '개인정보 수집·이용에 동의해야 계속 참가할 수 있어요.';
    setErrors(v);
    if (Object.keys(v).length > 0) return;
    setSubmitting(true);
    try {
      await verifyEmail({
        ...(otherEmail ? { email: email.trim() } : {}),
        code,
        ...(needsProfile ? { ...trimProfile(profile), privacy_consent: consent } : {}),
      });
      toast.success('학교 메일 인증을 마쳤어요', '이제 인증된 참가자예요.');
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
        description="등록한 학교 메일로 코드를 받아 입력하면 인증됩니다. 운영진이 부정 대응으로 '인증된 참가자만 거래'를 켜도 계속 거래할 수 있습니다."
      />
      <Card>
        <form ref={formRef} onSubmit={onSubmit} noValidate>
          <Stack gap={4}>
            {errors.form && <Alert tone="danger">{errors.form}</Alert>}
            {otherEmail ? (
              <SchoolEmailFields
                send={(address) => meApi.requestEmailCode({ email: address })}
                hint="인증하면 이 주소가 등록 메일이 됩니다. 비밀번호 재설정 코드도 이 주소로 발송됩니다."
                email={email}
                onEmailChange={setEmail}
                code={code}
                onCodeChange={setCode}
                emailError={errors.email}
                codeError={errors.code}
                onEmailError={(message) => setErrors((prev) => ({ ...prev, email: message }))}
              />
            ) : (
              <>
                <Text>
                  등록한 메일: <strong>{registered}</strong>
                </Text>
                <CodeSender
                  label="등록한 메일로 코드 받기"
                  request={() => meApi.requestEmailCode()}
                  code={code}
                  onCodeChange={setCode}
                  codeError={errors.code}
                />
              </>
            )}
            {registered != null && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setOtherEmail((v) => !v);
                  setCode('');
                  setErrors({});
                }}
              >
                {otherEmail ? '등록한 메일로 인증하기' : '다른 메일로 인증하기'}
              </Button>
            )}
            {needsProfile && (
              <>
                <ProfileFields value={profile} onChange={setProfile} errors={errors} />
                <PrivacyConsent checked={consent} onChange={setConsent} error={errors.consent} />
              </>
            )}
            <Button type="submit" size="lg" fullWidth loading={submitting}>
              인증하기
            </Button>
          </Stack>
        </form>
      </Card>
    </Container>
  );
}

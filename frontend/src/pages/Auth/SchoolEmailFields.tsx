import { useEffect, useState } from 'react';
import { ApiError, authApi } from '../../api';
import { Alert, Button, Checkbox, Stack, Text, TextField } from '../../components/ui';
import styles from './SchoolEmailFields.module.css';

/** 가입을 받는 학교 메일 도메인. 서버(normalize.py)와 같은 규칙으로 미리 확인한다. */
const SCHOOL_EMAIL = /^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?@(?:g\.)?skku\.edu$/;

/** 학교 메일 형식 오류 문구. 괜찮으면 undefined. 최종 판단은 서버가 한다. */
export function schoolEmailError(email: string): string | undefined {
  const value = email.trim().toLowerCase();
  if (!value) return '학교 메일을 입력해 주세요.';
  const domain = value.slice(value.lastIndexOf('@') + 1);
  if (!value.includes('@') || (domain !== 'skku.edu' && domain !== 'g.skku.edu')) {
    return '학교 메일(@skku.edu 또는 @g.skku.edu)만 쓸 수 있어요.';
  }
  if (!SCHOOL_EMAIL.test(value) || value.includes('..')) {
    return '메일 주소를 다시 확인해 주세요. +가 들어간 별칭 주소는 쓸 수 없어요.';
  }
  return undefined;
}

export function codeError(code: string): string | undefined {
  return /^\d{6}$/.test(code) ? undefined : '메일로 받은 6자리 숫자를 입력해 주세요.';
}

const REQUEST_ERRORS: Record<string, string> = {
  EMAIL_DOMAIN_NOT_ALLOWED: '학교 메일(@skku.edu 또는 @g.skku.edu)만 쓸 수 있어요.',
  INVALID_EMAIL: '메일 주소를 다시 확인해 주세요. +가 들어간 별칭 주소는 쓸 수 없어요.',
  EMAIL_TAKEN: '이미 참가한 학교 메일이에요. @skku.edu와 @g.skku.edu는 같은 계정으로 봐요.',
  EMAIL_NOT_REGISTERED: '이 학교 메일로 가입한 계정이 없어요. 메일 주소를 확인하거나 참가 신청을 해 주세요.',
};

/** verify: 참가 신청·재인증(아직 안 쓴 메일). reset: 비밀번호 재설정(가입한 메일). */
export type CodePurpose = 'verify' | 'reset';

const HINTS: Record<CodePurpose, string> = {
  verify: '@skku.edu 또는 @g.skku.edu. 같은 ID의 두 주소는 한 사람으로 봐요.',
  reset: '가입할 때 인증한 학교 메일이에요. @skku.edu와 @g.skku.edu 어느 쪽을 써도 돼요.',
};

/** 코드 확인 단계(가입·재인증 제출)에서 나오는 오류 중 코드 칸에 보여 줄 것. */
export const CODE_ERRORS = new Set(['INVALID_CODE', 'CODE_EXPIRED', 'CODE_ATTEMPTS_EXCEEDED']);

interface SchoolEmailFieldsProps {
  email: string;
  onEmailChange: (email: string) => void;
  code: string;
  onCodeChange: (code: string) => void;
  emailError?: string;
  codeError?: string;
  onEmailError: (message: string | undefined) => void;
  purpose?: CodePurpose;
}

/** 학교 메일 입력 + 인증 코드 받기 + 코드 입력. 참가 신청·재인증·비밀번호 재설정 화면이 함께 쓴다. */
export function SchoolEmailFields({
  email,
  onEmailChange,
  code,
  onCodeChange,
  emailError,
  codeError: codeErr,
  onEmailError,
  purpose = 'verify',
}: SchoolEmailFieldsProps) {
  const [sending, setSending] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [resendLeft, setResendLeft] = useState(0);

  useEffect(() => {
    if (resendLeft <= 0) return;
    const timer = window.setTimeout(() => setResendLeft((s) => s - 1), 1_000);
    return () => window.clearTimeout(timer);
  }, [resendLeft]);

  const requestCode = async () => {
    const invalid = schoolEmailError(email);
    onEmailError(invalid);
    if (invalid) return;
    setSending(true);
    setNotice(null);
    try {
      const send = purpose === 'reset' ? authApi.requestPasswordResetCode : authApi.requestEmailCode;
      const res = await send({ email: email.trim() });
      setSentTo(res.email);
      setResendLeft(res.resend_after);
      onCodeChange('');
    } catch (err) {
      if (err instanceof ApiError && REQUEST_ERRORS[err.code]) {
        onEmailError(REQUEST_ERRORS[err.code]);
      } else {
        setNotice(err instanceof ApiError ? err.message : '인증 메일을 보내지 못했어요. 잠시 뒤 다시 시도해 주세요.');
      }
    } finally {
      setSending(false);
    }
  };

  return (
    <Stack gap={3}>
      <TextField
        label="학교 메일"
        hint={HINTS[purpose]}
        type="email"
        autoComplete="email"
        inputMode="email"
        placeholder="example@g.skku.edu"
        value={email}
        onChange={(e) => {
          onEmailChange(e.target.value);
          setSentTo(null);
        }}
        error={emailError}
        required
      />
      <Button variant="secondary" onClick={requestCode} loading={sending} disabled={resendLeft > 0}>
        {resendLeft > 0 ? `${resendLeft}초 뒤에 다시 받을 수 있어요` : sentTo ? '코드 다시 받기' : '인증 코드 받기'}
      </Button>
      {notice && <Alert tone="danger">{notice}</Alert>}
      {sentTo && (
        <Alert tone="info">
          {sentTo}(으)로 인증 코드를 보냈어요. 10분 안에 입력해 주세요. 메일이 안 보이면 스팸함도 확인해 주세요.
        </Alert>
      )}
      <TextField
        label="인증 코드"
        hint="메일로 받은 6자리 숫자"
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        value={code}
        onChange={(e) => onCodeChange(e.target.value.replace(/\D/g, '').slice(0, 6))}
        error={codeErr}
        required
      />
    </Stack>
  );
}

/** 개인정보 수집·이용 동의(개인정보 보호법 제15조: 항목·목적·보유 기간·거부 권리). */
export function PrivacyConsent({
  checked,
  onChange,
  error,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  error?: string;
}) {
  return (
    <Stack gap={2}>
      <Text size="sm" weight="semibold">
        개인정보 수집·이용 안내
      </Text>
      <Text as="div" size="sm" tone="muted">
        <ul className={styles.consent}>
          <li>수집 항목: 학교 메일 주소, 이름, 학번, 학과</li>
          <li>이용 목적: 본인 확인, 1인 1계정(중복 가입 방지), 비밀번호 재설정</li>
          <li>보유 기간: 이벤트가 끝나면 지체 없이 파기해요</li>
          <li>랭킹에는 닉네임만 보이고, 메일·이름·학번·학과는 운영진만 봐요.</li>
          <li>동의하지 않을 수 있어요. 다만 동의하지 않으면 이벤트에 참가할 수 없어요.</li>
        </ul>
      </Text>
      <Checkbox
        label="개인정보(학교 메일·이름·학번·학과) 수집·이용에 동의해요 (필수)"
        checked={checked}
        onChange={onChange}
        aria-invalid={error ? true : undefined}
      />
      {error && (
        <Text size="sm" tone="danger" role="alert">
          {error}
        </Text>
      )}
    </Stack>
  );
}

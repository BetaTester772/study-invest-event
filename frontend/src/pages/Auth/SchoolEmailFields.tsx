import { useEffect, useState } from 'react';
import { ApiError, authApi, type EmailCodeResponse } from '../../api';
import { Alert, Button, Checkbox, Stack, Text, TextField } from '../../components/ui';
import styles from './SchoolEmailFields.module.css';

/** 가입을 받는 학교 메일 도메인. 서버(normalize.py)와 같은 규칙으로 미리 확인한다. */
const SCHOOL_EMAIL = /^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?@(?:g\.)?skku\.edu$/;

/** 학교 메일 형식 오류 문구. 괜찮으면 undefined. 최종 판단은 서버가 한다. */
export function schoolEmailError(email: string): string | undefined {
  // 서버(normalize.py)처럼 NFKC로 먼저 정규화한다: 전각 'ＡＢＣ＠Ｇ.ＳＫＫＵ.ＥＤＵ'도 같은 주소다.
  const value = email.normalize('NFKC').toLowerCase().trim();
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

/** 숫자만 남긴다. 서버(NFKC)처럼 전각 숫자 '２０２１'도 먼저 반각으로 바꾼 뒤 거른다. */
export function digitsOnly(value: string, max: number): string {
  return value.normalize('NFKC').replace(/\D/g, '').slice(0, max);
}

export function codeError(code: string): string | undefined {
  return /^\d{6}$/.test(code) ? undefined : '메일로 받은 6자리 숫자를 입력해 주세요.';
}

const REQUEST_ERRORS: Record<string, string> = {
  EMAIL_DOMAIN_NOT_ALLOWED: '학교 메일(@skku.edu 또는 @g.skku.edu)만 쓸 수 있어요.',
  INVALID_EMAIL: '메일 주소를 다시 확인해 주세요. +가 들어간 별칭 주소는 쓸 수 없어요.',
  EMAIL_TAKEN: '이미 참가한 학교 메일이에요. @skku.edu와 @g.skku.edu는 같은 계정으로 봐요.',
};

/** 코드 확인 단계(가입·인증·재설정 제출)에서 나오는 오류 중 코드 칸에 보여 줄 것. */
export const CODE_ERRORS = new Set(['INVALID_CODE', 'CODE_EXPIRED', 'CODE_ATTEMPTS_EXCEEDED']);

/** 코드 요청 상태: 보내는 중, 보낸 주소, 재요청 카운트다운, 오류 안내. */
function useCodeRequest() {
  const [sending, setSending] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [resendLeft, setResendLeft] = useState(0);

  useEffect(() => {
    if (resendLeft <= 0) return;
    const timer = window.setTimeout(() => setResendLeft((s) => s - 1), 1_000);
    return () => window.clearTimeout(timer);
  }, [resendLeft]);

  /** onError가 true를 돌려주면(칸 옆에 보여 줌) 공통 안내는 띄우지 않는다. */
  const run = async (send: () => Promise<EmailCodeResponse>, onError?: (err: unknown) => boolean) => {
    setSending(true);
    setNotice(null);
    try {
      const res = await send();
      setSentTo(res.email);
      setResendLeft(res.resend_after);
      return true;
    } catch (err) {
      if (!onError?.(err)) {
        setNotice(err instanceof ApiError ? err.message : '인증 메일을 보내지 못했어요. 잠시 뒤 다시 시도해 주세요.');
      }
      return false;
    } finally {
      setSending(false);
    }
  };
  /** 주소를 고치면 처음부터: 재요청 대기는 서버가 주소마다 세므로 새 주소는 바로 받을 수 있다. */
  const reset = () => {
    setSentTo(null);
    setResendLeft(0);
    setNotice(null);
  };
  return { sending, sentTo, notice, resendLeft, run, reset };
}

function CodeSteps({
  state,
  label,
  onClick,
  disabled,
  code,
  onCodeChange,
  codeError,
}: {
  state: ReturnType<typeof useCodeRequest>;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  code: string;
  onCodeChange: (code: string) => void;
  codeError?: string;
}) {
  const { sending, sentTo, notice, resendLeft } = state;
  return (
    <>
      <Button variant="secondary" onClick={onClick} loading={sending} disabled={disabled || resendLeft > 0}>
        {resendLeft > 0 ? `${resendLeft}초 뒤에 다시 받을 수 있어요` : sentTo ? '코드 다시 받기' : label}
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
        onChange={(e) => onCodeChange(digitsOnly(e.target.value, 6))}
        error={codeError}
        required
      />
    </>
  );
}

interface CodeSenderProps {
  /** 코드를 요청한다(등록 메일로, 또는 학번으로 찾은 계정의 등록 메일로). 응답 주소는 가려져 온다. */
  request: () => Promise<EmailCodeResponse>;
  /** 요청 전에 확인할 것(예: 학번 형식). 오류 문구를 돌려주면 요청하지 않는다. */
  validate?: () => string | undefined;
  /** 요청 오류를 칸 옆에 보여 줬으면 true. */
  onRequestError?: (err: unknown) => boolean;
  label?: string;
  code: string;
  onCodeChange: (code: string) => void;
  codeError?: string;
}

/** 주소를 입력받지 않고 코드를 받는다: 등록 메일 인증, 학번으로 비밀번호 재설정. */
export function CodeSender({
  request,
  validate,
  onRequestError,
  label = '인증 코드 받기',
  code,
  onCodeChange,
  codeError: codeErr,
}: CodeSenderProps) {
  const state = useCodeRequest();
  const onClick = async () => {
    if (validate?.()) return;
    if (await state.run(request, onRequestError)) onCodeChange('');
  };
  return (
    <Stack gap={3}>
      <CodeSteps
        state={state}
        label={label}
        onClick={() => void onClick()}
        code={code}
        onCodeChange={onCodeChange}
        codeError={codeErr}
      />
    </Stack>
  );
}

interface SchoolEmailFieldsProps {
  email: string;
  onEmailChange: (email: string) => void;
  code: string;
  onCodeChange: (code: string) => void;
  emailError?: string;
  codeError?: string;
  onEmailError: (message: string | undefined) => void;
  /** 코드를 보내는 API. 기본은 참가 신청용(POST /api/auth/email-code). */
  send?: (email: string) => Promise<EmailCodeResponse>;
  /** false면 메일 주소만 받는다(메일 인증 없이 가입하는 운영). */
  withCode?: boolean;
  hint?: string;
}

/** 학교 메일 입력 + 인증 코드 받기 + 코드 입력. 참가 신청과 다른 메일로 인증할 때 쓴다. */
export function SchoolEmailFields({
  email,
  onEmailChange,
  code,
  onCodeChange,
  emailError,
  codeError: codeErr,
  onEmailError,
  send = (address) => authApi.requestEmailCode({ email: address }),
  withCode = true,
  hint = '@skku.edu 또는 @g.skku.edu. 같은 ID의 두 주소는 한 사람으로 봐요.',
}: SchoolEmailFieldsProps) {
  const state = useCodeRequest();

  const requestCode = async () => {
    const invalid = schoolEmailError(email);
    onEmailError(invalid);
    if (invalid) return;
    const ok = await state.run(
      () => send(email.trim()),
      (err) => {
        if (err instanceof ApiError && REQUEST_ERRORS[err.code]) {
          onEmailError(REQUEST_ERRORS[err.code]);
          return true;
        }
        return false;
      },
    );
    if (ok) onCodeChange('');
  };

  return (
    <Stack gap={3}>
      <TextField
        label="학교 메일"
        hint={hint}
        type="email"
        autoComplete="email"
        inputMode="email"
        placeholder="example@g.skku.edu"
        value={email}
        onChange={(e) => {
          onEmailChange(e.target.value);
          state.reset();
        }}
        error={emailError}
        required
      />
      {withCode && (
        <CodeSteps
          state={state}
          label="인증 코드 받기"
          onClick={() => void requestCode()}
          code={code}
          onCodeChange={onCodeChange}
          codeError={codeErr}
        />
      )}
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

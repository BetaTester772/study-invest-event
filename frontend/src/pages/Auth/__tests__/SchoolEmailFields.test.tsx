import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { ApiError, authApi } from '../../../api';
import { profileErrors } from '../ProfileFields';
import { validateRegister } from '../RegisterPage';
import { validateNewPassword, validateResetCode } from '../ResetPasswordPage';
import { CodeSender, SchoolEmailFields, codeError, digitsOnly, schoolEmailError } from '../SchoolEmailFields';

describe('schoolEmailError', () => {
  it.each(['abc@g.skku.edu', 'abc@skku.edu', ' ABC@G.SKKU.EDU ', 'a.b_c-1@g.skku.edu', 'ＡＢＣ＠Ｇ.ＳＫＫＵ.ＥＤＵ'])(
    'accepts %s',
    (email) => {
      expect(schoolEmailError(email)).toBeUndefined();
    },
  );

  it.each([
    ['', '입력'],
    ['abc@gmail.com', '학교 메일'],
    ['abc@evilskku.edu', '학교 메일'],
    ['abc@mail.skku.edu', '학교 메일'],
    ['abc', '학교 메일'],
    ['abc+1@g.skku.edu', '별칭'],
    ['a..b@g.skku.edu', '확인'],
  ])('rejects %s', (email, fragment) => {
    expect(schoolEmailError(email)).toContain(fragment);
  });
});

describe('digitsOnly', () => {
  it('keeps full-width digits by normalizing them first', () => {
    expect(digitsOnly('２０２１３１０１２３', 10)).toBe('2021310123');
    expect(digitsOnly('2021-310 123', 10)).toBe('2021310123');
    expect(digitsOnly('１２３４５６７', 6)).toBe('123456');
  });
});

describe('validateRegister', () => {
  const ok = {
    email: 'kim@g.skku.edu',
    code: '123456',
    name: '김성균',
    student_id: '2021310123',
    department: '소프트웨어학과',
    nickname: 'kim',
    password: 'password123',
    confirm: 'password123',
    consent: true,
  };

  it('passes a complete form', () => {
    expect(validateRegister(ok)).toEqual({});
  });

  it('checks name, 10-digit student ID and department', () => {
    const errors = validateRegister({ ...ok, name: ' ', student_id: '202131012', department: '' });
    expect(Object.keys(errors).sort()).toEqual(['department', 'name', 'student_id']);
    expect(profileErrors({ name: '가'.repeat(31), student_id: '20213101234', department: 'x' })).toEqual({
      name: '이름은 30자까지 쓸 수 있습니다.',
      student_id: '학번 10자리 숫자를 입력해 주세요.',
    });
  });

  it('does not need a code when the event runs without email verification', () => {
    expect(validateRegister({ ...ok, code: '' }, false)).toEqual({});
    expect(Object.keys(validateRegister({ ...ok, code: '' }, true))).toEqual(['code']);
  });

  it('requires a 6-digit code and consent', () => {
    expect(codeError('12345')).toBeDefined();
    const errors = validateRegister({ ...ok, code: '', consent: false });
    expect(Object.keys(errors).sort()).toEqual(['code', 'consent']);
  });
});

describe('password reset validation', () => {
  it('checks the student ID and code first', () => {
    expect(validateResetCode('2021310123', '123456')).toEqual({});
    expect(Object.keys(validateResetCode(' ', '1')).sort()).toEqual(['code', 'identity']);
  });

  it('then needs a matching new password', () => {
    expect(validateNewPassword('newpass456', 'newpass456')).toEqual({});
    expect(Object.keys(validateNewPassword('short', 'other')).sort()).toEqual(['confirm', 'password']);
  });
});

function Harness() {
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | undefined>();
  return (
    <SchoolEmailFields
      email={email}
      onEmailChange={setEmail}
      code={code}
      onCodeChange={setCode}
      emailError={error}
      onEmailError={setError}
    />
  );
}

describe('SchoolEmailFields', () => {
  afterEach(() => vi.restoreAllMocks());

  it('requests a code and blocks resending during the cooldown', async () => {
    const request = vi
      .spyOn(authApi, 'requestEmailCode')
      .mockResolvedValue({ email: 'kim@skku.edu', expires_in: 600, resend_after: 60 });
    render(<Harness />);
    await userEvent.type(screen.getByLabelText(/학교 메일/), 'Kim@SKKU.edu');
    await userEvent.click(screen.getByRole('button', { name: '인증 코드 받기' }));
    expect(request).toHaveBeenCalledWith({ email: 'Kim@SKKU.edu' });
    expect(await screen.findByText(/kim@skku.edu\(으\)로 인증 코드를 보냈습니다/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /초 뒤에 다시/ })).toBeDisabled();
  });

  it('lets a corrected address get a code right away', async () => {
    const request = vi
      .spyOn(authApi, 'requestEmailCode')
      .mockResolvedValue({ email: 'kmi@skku.edu', expires_in: 600, resend_after: 60 });
    render(<Harness />);
    const field = screen.getByLabelText(/학교 메일/);
    await userEvent.type(field, 'kmi@skku.edu');
    await userEvent.click(screen.getByRole('button', { name: '인증 코드 받기' }));
    expect(await screen.findByRole('button', { name: /초 뒤에 다시/ })).toBeDisabled();
    await userEvent.clear(field);
    await userEvent.type(field, 'kim@skku.edu'); // 오타 수정
    expect(screen.getByRole('button', { name: '인증 코드 받기' })).toBeEnabled();
    await userEvent.click(screen.getByRole('button', { name: '인증 코드 받기' }));
    expect(request).toHaveBeenLastCalledWith({ email: 'kim@skku.edu' });
  });

  it('does not call the API for a non-school address', async () => {
    const request = vi.spyOn(authApi, 'requestEmailCode');
    render(<Harness />);
    await userEvent.type(screen.getByLabelText(/학교 메일/), 'kim@gmail.com');
    await userEvent.click(screen.getByRole('button', { name: '인증 코드 받기' }));
    expect(request).not.toHaveBeenCalled();
    expect(screen.getByText(/학교 메일\(@skku.edu 또는 @g.skku.edu\)만/)).toBeInTheDocument();
  });

  it('sends to the registered address without asking for it and shows the masked address', async () => {
    const request = vi
      .fn()
      .mockResolvedValue({ email: 'k***@skku.edu', expires_in: 600, resend_after: 60 });
    function Sender() {
      const [code, setCode] = useState('');
      return <CodeSender label="등록한 메일로 코드 받기" request={request} code={code} onCodeChange={setCode} />;
    }
    render(<Sender />);
    expect(screen.queryByLabelText(/학교 메일/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '등록한 메일로 코드 받기' }));
    expect(request).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/k\*\*\*@skku.edu\(으\)로 인증 코드를 보냈습니다/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /초 뒤에 다시/ })).toBeDisabled();
  });

  it('shows that it waits for the security check instead of a sending spinner', () => {
    render(<CodeSender request={vi.fn()} code="" onCodeChange={() => {}} captchaWaiting />);
    const button = screen.getByRole('button', { name: '보안 확인을 기다리는 중' });
    expect(button).toBeDisabled();
    expect(button).not.toHaveAttribute('aria-busy', 'true');
  });

  it('does not request when validation fails and shows request errors next to the field', async () => {
    const request = vi.fn().mockRejectedValue(new ApiError(404, 'ACCOUNT_NOT_FOUND', '없는 학번'));
    const onError = vi.fn().mockReturnValue(true);
    let invalid = '학번을 입력해 주세요.' as string | undefined;
    render(
      <CodeSender
        request={request}
        validate={() => invalid}
        onRequestError={onError}
        code=""
        onCodeChange={() => {}}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: '인증 코드 받기' }));
    expect(request).not.toHaveBeenCalled();
    invalid = undefined;
    await userEvent.click(screen.getByRole('button', { name: '인증 코드 받기' }));
    await waitFor(() => expect(onError).toHaveBeenCalled());
    expect(screen.queryByText('없는 학번')).not.toBeInTheDocument(); // 칸 옆에서 처리
  });

  it('shows only the email field without the code step', () => {
    render(
      <SchoolEmailFields
        email=""
        onEmailChange={() => {}}
        code=""
        onCodeChange={() => {}}
        onEmailError={() => {}}
        withCode={false}
        hint="재설정 코드를 받는 주소입니다."
      />,
    );
    expect(screen.getByText('재설정 코드를 받는 주소입니다.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '인증 코드 받기' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/인증 코드/)).not.toBeInTheDocument();
  });

  it('shows an already-registered address on the email field', async () => {
    vi.spyOn(authApi, 'requestEmailCode').mockRejectedValue(new ApiError(409, 'EMAIL_TAKEN', 'taken'));
    render(<Harness />);
    await userEvent.type(screen.getByLabelText(/학교 메일/), 'kim@skku.edu');
    await userEvent.click(screen.getByRole('button', { name: '인증 코드 받기' }));
    await waitFor(() => expect(screen.getByText(/이미 참가한 학교 메일입니다/)).toBeInTheDocument());
  });
});

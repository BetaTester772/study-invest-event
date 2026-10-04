import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { ApiError, authApi } from '../../../api';
import { profileErrors } from '../ProfileFields';
import { validateRegister } from '../RegisterPage';
import { validateReset } from '../ResetPasswordPage';
import { SchoolEmailFields, codeError, schoolEmailError } from '../SchoolEmailFields';

describe('schoolEmailError', () => {
  it.each(['abc@g.skku.edu', 'abc@skku.edu', ' ABC@G.SKKU.EDU ', 'a.b_c-1@g.skku.edu'])('accepts %s', (email) => {
    expect(schoolEmailError(email)).toBeUndefined();
  });

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
      name: '이름은 30자까지 쓸 수 있어요.',
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

describe('validateReset', () => {
  it('needs a school email, a code and a matching new password', () => {
    expect(validateReset('kim@skku.edu', '123456', 'newpass456', 'newpass456')).toEqual({});
    expect(Object.keys(validateReset('kim@gmail.com', '1', 'short', 'other')).sort()).toEqual([
      'code',
      'confirm',
      'email',
      'password',
    ]);
  });
});

function Harness({ purpose }: { purpose?: 'verify' | 'reset' }) {
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
      purpose={purpose}
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
    expect(await screen.findByText(/kim@skku.edu\(으\)로 인증 코드를 보냈어요/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /초 뒤에 다시/ })).toBeDisabled();
  });

  it('does not call the API for a non-school address', async () => {
    const request = vi.spyOn(authApi, 'requestEmailCode');
    render(<Harness />);
    await userEvent.type(screen.getByLabelText(/학교 메일/), 'kim@gmail.com');
    await userEvent.click(screen.getByRole('button', { name: '인증 코드 받기' }));
    expect(request).not.toHaveBeenCalled();
    expect(screen.getByText(/학교 메일\(@skku.edu 또는 @g.skku.edu\)만/)).toBeInTheDocument();
  });

  it('uses the password reset endpoint for the reset purpose', async () => {
    const verify = vi.spyOn(authApi, 'requestEmailCode');
    const reset = vi
      .spyOn(authApi, 'requestPasswordResetCode')
      .mockRejectedValue(new ApiError(404, 'EMAIL_NOT_REGISTERED', 'none'));
    render(<Harness purpose="reset" />);
    await userEvent.type(screen.getByLabelText(/학교 메일/), 'kim@g.skku.edu');
    await userEvent.click(screen.getByRole('button', { name: '인증 코드 받기' }));
    expect(reset).toHaveBeenCalledWith({ email: 'kim@g.skku.edu' });
    expect(verify).not.toHaveBeenCalled();
    expect(await screen.findByText(/이 학교 메일로 가입한 계정이 없어요/)).toBeInTheDocument();
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
        hint="재설정 코드를 받는 주소예요."
      />,
    );
    expect(screen.getByText('재설정 코드를 받는 주소예요.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '인증 코드 받기' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/인증 코드/)).not.toBeInTheDocument();
  });

  it('shows an already-registered address on the email field', async () => {
    vi.spyOn(authApi, 'requestEmailCode').mockRejectedValue(new ApiError(409, 'EMAIL_TAKEN', 'taken'));
    render(<Harness />);
    await userEvent.type(screen.getByLabelText(/학교 메일/), 'kim@skku.edu');
    await userEvent.click(screen.getByRole('button', { name: '인증 코드 받기' }));
    await waitFor(() => expect(screen.getByText(/이미 참가한 학교 메일이에요/)).toBeInTheDocument());
  });
});

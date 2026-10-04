import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { ApiError, authApi } from '../../../api';
import { validateRegister } from '../RegisterPage';
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
    nickname: 'kim',
    password: 'password123',
    confirm: 'password123',
    consent: true,
  };

  it('passes a complete form', () => {
    expect(validateRegister(ok)).toEqual({});
  });

  it('requires a 6-digit code and consent', () => {
    expect(codeError('12345')).toBeDefined();
    const errors = validateRegister({ ...ok, code: '', consent: false });
    expect(Object.keys(errors).sort()).toEqual(['code', 'consent']);
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

  it('shows an already-registered address on the email field', async () => {
    vi.spyOn(authApi, 'requestEmailCode').mockRejectedValue(new ApiError(409, 'EMAIL_TAKEN', 'taken'));
    render(<Harness />);
    await userEvent.type(screen.getByLabelText(/학교 메일/), 'kim@skku.edu');
    await userEvent.click(screen.getByRole('button', { name: '인증 코드 받기' }));
    await waitFor(() => expect(screen.getByText(/이미 참가한 학교 메일이에요/)).toBeInTheDocument());
  });
});

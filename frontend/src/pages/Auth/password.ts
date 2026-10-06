/** 서버(services/auth.py ensure_strong_password, zxcvbn)가 거부하는 비밀번호 안내. 판단은 서버가 한다. */
export const PASSWORD_HINT = '8자 이상. 흔한 비밀번호나 학번·이름이 들어간 비밀번호는 쓸 수 없습니다.';

export const WEAK_PASSWORD_MESSAGE =
  '너무 쉬운 비밀번호입니다. 흔한 단어·연속된 숫자·학번·이름을 피하고 더 길게 정해 주세요.';

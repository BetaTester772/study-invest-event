import type { ProfileFields as Profile } from '../../api';
import { TextField } from '../../components/ui';
import { digitsOnly } from './SchoolEmailFields';

export type ProfileErrors = Partial<Record<keyof Profile, string>>;

export const EMPTY_PROFILE: Profile = { name: '', student_id: '', department: '' };

/** 서버(api/schemas.py)와 같은 규칙: 이름 1~30자, 학번 숫자 10자리, 학과 1~50자(앞뒤 공백 제외). */
export function profileErrors(p: Profile): ProfileErrors {
  const errors: ProfileErrors = {};
  const name = p.name.trim();
  if (!name) errors.name = '이름을 입력해 주세요.';
  else if (name.length > 30) errors.name = '이름은 30자까지 쓸 수 있어요.';
  if (!/^\d{10}$/.test(p.student_id.trim())) errors.student_id = '학번 10자리 숫자를 입력해 주세요.';
  const department = p.department.trim();
  if (!department) errors.department = '학과를 입력해 주세요.';
  else if (department.length > 50) errors.department = '학과는 50자까지 쓸 수 있어요.';
  return errors;
}

export function trimProfile(p: Profile): Profile {
  return { name: p.name.trim(), student_id: p.student_id.trim(), department: p.department.trim() };
}

/** 이름·학번·학과 입력. 운영진만 보고, 랭킹에는 닉네임만 보인다. */
export function ProfileFields({
  value,
  onChange,
  errors,
}: {
  value: Profile;
  onChange: (value: Profile) => void;
  errors: ProfileErrors;
}) {
  const set = (key: keyof Profile, v: string) => onChange({ ...value, [key]: v });
  return (
    <>
      <TextField
        label="이름"
        hint="실명. 운영진만 봐요."
        autoComplete="name"
        value={value.name}
        onChange={(e) => set('name', e.target.value)}
        error={errors.name}
        maxLength={30}
        required
      />
      <TextField
        label="학번"
        hint="숫자 10자리. 한 학번에 한 계정만 만들 수 있어요."
        inputMode="numeric"
        placeholder="2026310000"
        value={value.student_id}
        onChange={(e) => set('student_id', digitsOnly(e.target.value, 10))}
        error={errors.student_id}
        required
      />
      <TextField
        label="학과"
        hint="예: 소프트웨어학과"
        value={value.department}
        onChange={(e) => set('department', e.target.value)}
        error={errors.department}
        maxLength={50}
        required
      />
    </>
  );
}

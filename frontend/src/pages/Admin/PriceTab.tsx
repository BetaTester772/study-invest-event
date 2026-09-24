import { useState, type FormEvent } from 'react';
import { adminApi, ApiError, publicApi, useApi, type PricePoint } from '../../api';
import {
  Alert,
  Button,
  Card,
  Grid,
  KeyValueList,
  Money,
  NumberField,
  Select,
  Stack,
  TextArea,
  TextField,
  useToast,
} from '../../components/ui';
import { formatDay } from '../../lib/format';

export function PriceTab() {
  const toast = useToast();
  const instruments = useApi(() => publicApi.instruments(), []);
  const [day, setDay] = useState('');
  const [code, setCode] = useState('');
  const [price, setPrice] = useState(0);
  const [reason, setReason] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<{ code: string; point: PricePoint } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const selected = instruments.data?.find((i) => i.code === code);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!day) errs.day = '가격을 바꿀 운영일을 고르세요.';
    if (!code) errs.code = '종목을 고르세요.';
    if (price < 10) errs.price = '10원 이상으로 입력하세요.';
    if (!reason.trim()) errs.reason = '감사 로그에 남길 사유를 적어 주세요.';
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setSaving(true);
    setFormError(null);
    try {
      const point = await adminApi.overridePrice(day, code, { price, reason: reason.trim() });
      setResult({ code, point });
      toast.success('시작가를 바꿨어요', `${selected?.name ?? code}, ${formatDay(point.day)}`);
      setReason('');
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : '가격을 바꾸지 못했어요.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Grid sidebar="minmax(16rem, 22rem)" gap={6}>
      <Card
        title="시작가 직접 정하기"
        description="아직 공시되지 않은 운영일의 시작가만 바꿀 수 있어요. 사유는 감사 로그에 남아요."
      >
        <form onSubmit={submit} noValidate>
          <Stack gap={4}>
            {formError && (
              <Alert tone="danger" title="가격을 바꾸지 못했어요">
                {formError}
              </Alert>
            )}
            <Grid min="12rem" gap={4}>
              <TextField
                label="운영일"
                type="date"
                value={day}
                onChange={(e) => setDay(e.target.value)}
                error={errors.day}
                required
              />
              <Select
                label="종목"
                value={code}
                onChange={(v) => {
                  setCode(v);
                  const ins = instruments.data?.find((i) => i.code === v);
                  if (ins && price === 0) setPrice(ins.price);
                }}
                placeholder="종목 고르기"
                options={(instruments.data ?? []).map((i) => ({ value: i.code, label: `${i.name} (${i.code})` }))}
                error={errors.code}
                required
              />
            </Grid>
            <NumberField
              label="새 시작가"
              value={price}
              onChange={setPrice}
              min={0}
              step={10}
              suffix="원"
              hint={
                selected
                  ? `현재 공시가 ${selected.price.toLocaleString('ko-KR')}원. 10원 단위로 반올림돼요.`
                  : '10원 단위로 반올림돼요.'
              }
              error={errors.price}
              required
            />
            <TextArea
              label="사유"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              error={errors.reason}
              placeholder="예: 정산 배치 오류로 전일 가격 유지"
              required
            />
            <Stack direction="row" justify="end">
              <Button type="submit" loading={saving}>
                시작가 바꾸기
              </Button>
            </Stack>
          </Stack>
        </form>
      </Card>
      <Card title="마지막으로 바꾼 가격" tone="sunken">
        {result ? (
          <KeyValueList
            items={[
              { label: '종목', value: result.code },
              { label: '운영일', value: formatDay(result.point.day) },
              { label: '근거', value: result.point.source === 'manual' ? '관리자 조정' : result.point.source },
              { label: '시작가', value: <Money value={result.point.price} />, strong: true },
            ]}
          />
        ) : (
          <Alert>아직 이번 접속에서 바꾼 가격이 없어요.</Alert>
        )}
      </Card>
    </Grid>
  );
}
